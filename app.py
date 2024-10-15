from datetime import datetime, timedelta, timezone
import logging
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import asyncio
import nest_asyncio

nest_asyncio.apply()

from src.custom_logger import init_custom_logger
from src.trade_state import TradeState 
from src.load_json import load_json_file
from src.filters import filter_by_bid_price, filter_by_mid_iv, filter_strikes
from src.load_env import load_env_file
from src.fred import fetch_risk_free_rate
from src.schwab_manager import SchwabManager
from src.helpers import calculate_time_to_wait_for_market_open, is_nyse_open, precompile_numba_functions, should_wait_for_market_open
from src.models import barone_adesi_whaley_american_option_price, calculate_implied_volatility_baw
from src.interpolations import fit_model, rbf_model, rfv_model

precompile_numba_functions()
init_custom_logger()

# Constants and Global Variables
config = load_env_file()
stocks_list = load_json_file("stocks.json")
manager = SchwabManager(config)
r = fetch_risk_free_rate(config["FRED_API_KEY"])

async def handle_trades(ticker, option_type, q, min_overpriced, min_oi, trade_state, option_date, expiration_time, from_entered_datetime, to_entered_datetime):
    """
    Handles the trade logic for a given ticker and option type.

    Args:
        ticker (str): Ticker symbol for the asset being traded.
        option_type (str): Type of option ('call' or 'put').
        q (float): Dividend yield for the underlying asset.
        min_overpriced (float): Minimum threshold for mispricing detection.
        min_oi (float): Minimum open interest to filter options.
        trade_state (TradeState): Current trade state (e.g., PENDING, IN_POSITION).
        option_date (datetime): Date of the option to trade.
        expiration_time (datetime): Time until option expiration.
        from_entered_datetime (datetime): Starting datetime to filter orders.
        to_entered_datetime (datetime): Ending datetime to filter orders.

    Returns:
        TradeState: Updated trade state based on the trade logic.
    """
    if config["DRY_RUN"] != True:
        await manager.cancel_existing_orders(ticker, from_entered_datetime, to_entered_datetime)

    if trade_state in {TradeState.PENDING, TradeState.IN_POSITION}:
        streamers_tickers, options, total_shares = await manager.get_account_positions(ticker)

        if trade_state == TradeState.PENDING:
            trade_state = TradeState.IN_POSITION if len(streamers_tickers) > 0 else TradeState.NOT_IN_POSITION
 
        await manager.handle_delta_adjustments(ticker, streamers_tickers, expiration_time, options, total_shares, r, q)

    quote_data, S = await manager.get_option_chain_data(ticker, option_date, option_type)

    sorted_data = dict(sorted(quote_data.items()))
    filtered_strikes = filter_strikes(np.array(list(sorted_data.keys())), S, num_stdev=1.25)
    sorted_data = filter_by_bid_price(sorted_data, filtered_strikes)

    current_time = datetime.now()
    T = (expiration_time - current_time).total_seconds() / (365 * 24 * 3600)

    for K, prices in sorted_data.items():
        sorted_data[K] = {
            "bid": prices["bid"],
            "ask": prices["ask"],
            "mid": prices["mid"],
            "open_interest": prices["open_interest"],
            "mid_IV": calculate_implied_volatility_baw(prices["mid"], S, K, r, T, q=q, option_type=option_type),
            "ask_IV": calculate_implied_volatility_baw(prices["ask"], S, K, r, T, q=q, option_type=option_type),
            "bid_IV": calculate_implied_volatility_baw(prices["bid"], S, K, r, T, q=q, option_type=option_type)
        }

    sorted_data = filter_by_mid_iv(sorted_data)

    x = np.array(list(sorted_data.keys())) 
    y_bid_iv = np.array([prices['bid_IV'] for prices in sorted_data.values()])
    y_ask_iv = np.array([prices['ask_IV'] for prices in sorted_data.values()])
    y_mid_iv = np.array([prices['mid_IV'] for prices in sorted_data.values()])
    open_interest = np.array([prices['open_interest'] for prices in sorted_data.values()])
    y_mid = np.array([prices['mid'] for prices in sorted_data.values()])

    if len(x) >= 20:
        scaler = MinMaxScaler()
        x_normalized = scaler.fit_transform(x.reshape(-1, 1)).flatten()
        x_normalized = x_normalized + 0.5

        rbf_interpolator = rbf_model(np.log(x_normalized), y_mid_iv, epsilon=0.3)
        rfv_params = fit_model(x_normalized, y_mid_iv, y_bid_iv, y_ask_iv, rfv_model)

        fine_x_normalized = np.linspace(np.min(x_normalized), np.max(x_normalized), 800)
        rbf_interpolated_y = rbf_interpolator(np.log(fine_x_normalized).reshape(-1, 1))
        rfv_interpolated_y = rfv_model(np.log(fine_x_normalized), rfv_params)
        interpolated_y = 0.8 * rfv_interpolated_y + 0.2 * rbf_interpolated_y

        fine_x = np.linspace(np.min(x), np.max(x), 800)
        mispricings = np.zeros(len(x))

        for i in range(len(x)):
            strike = x[i]
            diff = np.abs(fine_x - strike)
            closest_index = np.argmin(diff)

            interpolated_iv = interpolated_y[closest_index]
            mid_value = y_mid[i]
            option_price = barone_adesi_whaley_american_option_price(S, strike, T, r, interpolated_iv, q, option_type)
            diff_price = mid_value - option_price

            mispricings[i] = diff_price

        if trade_state in {TradeState.NOT_IN_POSITION}:
            if min_oi > 0.0:
                mask = open_interest > min_oi
                x = x[mask]
                y_bid_iv = y_bid_iv[mask]
                y_ask_iv = y_ask_iv[mask]
                y_mid_iv = y_mid_iv[mask]
                open_interest = open_interest[mask]
                y_mid = y_mid[mask]
                mispricings = mispricings[mask]

            max_oi_mispricing = float('-inf')
            best_option = (None, None, None)

            for i in range(len(x)):
                if mispricings[i] > min_overpriced:
                    oi_mispricing = open_interest[i] * mispricings[i]
                    if oi_mispricing > max_oi_mispricing:
                        max_oi_mispricing = oi_mispricing
                        best_option = (x[i], y_mid[i], mispricings[i])

            best_strike, best_mid_price, best_mispricing = best_option

            if best_strike is not None:
                await manager.sell_option(ticker, option_type, option_date, best_strike, best_mid_price, best_mispricing)
                trade_state = TradeState.PENDING
        else:
            print()
            # BOILER PLATE FOR NOW

    return trade_state

async def main():
    """
    Main function to initialize the bot.
    """
    await manager.initialize()

    if stocks_list.head is not None:
        current_node = stocks_list.head
        while True:
            ticker = current_node.ticker
            date_index = current_node.date_index

            q = await manager.get_dividend_yield(ticker)
            current_node.set_q(q)

            date = await manager.get_option_expiration_date(ticker, date_index)
            option_date = datetime.strptime(date, "%Y-%m-%d").date()
            expiration_time = datetime.combine(datetime.strptime(date, '%Y-%m-%d'), datetime.min.time()) + timedelta(hours=16)

            current_node.set_option_date(option_date)
            current_node.set_expiration_time(expiration_time)

            current_date = datetime.now().date()
            from_entered_datetime = datetime.combine(current_date, datetime.min.time()).replace(
                tzinfo=timezone(timedelta(hours=-5))
            )
            to_entered_datetime = datetime.combine(current_date, datetime.max.time()).replace(
                tzinfo=timezone(timedelta(hours=-5))
            )

            current_node.set_from_entered_datetime(from_entered_datetime)
            current_node.set_to_entered_datetime(to_entered_datetime)

            current_node = current_node.next
            if current_node == stocks_list.head:
                break

    while True:
        if (is_nyse_open() or config["DRY_RUN"]):
            trade_state = await handle_trades(
                current_node.ticker,
                current_node.option_type,
                current_node.q,
                current_node.min_overpriced,
                current_node.min_oi,
                current_node.trade_state,
                current_node.option_date,
                current_node.expiration_time,
                current_node.from_entered_datetime,
                current_node.to_entered_datetime
            )

            current_node.set_trade_state(trade_state)
            current_node = current_node.next
        elif should_wait_for_market_open():
            time_to_wait = calculate_time_to_wait_for_market_open()

            logging.getLogger().custom(f"NYSE is closed. Waiting for {time_to_wait.total_seconds()} seconds until market opens.")
            await asyncio.sleep(time_to_wait.total_seconds())
        else:
            logging.getLogger().custom("NYSE is closed now.")
            break

        await asyncio.sleep(config["TIME_TO_REST"])

        # ADDED FOR NOW
        #break

if __name__ == "__main__":
    asyncio.run(main())
