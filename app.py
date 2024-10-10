from datetime import datetime, timedelta, timezone
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import asyncio
import nest_asyncio

nest_asyncio.apply()

from src.schwab import cancel_existing_orders, get_account_positions, get_dividend_yield, get_option_chain_data, get_option_expiration_date, handle_delta_adjustments, initialize_client
from src.helpers import calculate_rmse, filter_strikes, is_nyse_open, load_config, precompile_numba_functions, get_risk_free_rate, write_csv
from src.models import barone_adesi_whaley_american_option_price, calculate_implied_volatility_baw
from src.interpolations import fit_model, rbf_model, rfv_model

# Constants and Global Variables
config = {}

async def main():
    """
    Main function to initialize the bot.
    """
    
    precompile_numba_functions()
    config = load_config()

    r = get_risk_free_rate(config["FRED_API_KEY"])
    if r is None:
        return
    
    ticker = config["TICKER"]
    option_type = config["OPTION_TYPE"]

    await initialize_client(config)
    
    date = await get_option_expiration_date(ticker, config["DATE_INDEX"])
    if date is None:
        return
    
    q = await get_dividend_yield(ticker)
    if q is None:
        return

    option_date = datetime.strptime(date, "%Y-%m-%d").date()
    expiration_time =datetime.combine(datetime.strptime(date, '%Y-%m-%d'), datetime.min.time()) + timedelta(hours=16)

    current_date = datetime.now().date()
    from_entered_datetime = datetime.combine(current_date, datetime.min.time()).replace(
        tzinfo=timezone(timedelta(hours=-5))
    )
    to_entered_datetime = datetime.combine(current_date, datetime.max.time()).replace(
        tzinfo=timezone(timedelta(hours=-5))
    )

    while True:
        if (is_nyse_open() or config["DRY_RUN"]):
            if config["DRY_RUN"] != True:
                await cancel_existing_orders(ticker, config["SCHWAB_ACCOUNT_HASH"], from_entered_datetime, to_entered_datetime)

            streamers_tickers, options, total_shares = await get_account_positions(ticker, config["SCHWAB_ACCOUNT_HASH"])
            await handle_delta_adjustments(ticker, streamers_tickers, expiration_time, options, total_shares, config, r, q)

            quote_data, S = await get_option_chain_data(ticker, option_date, option_type)

            sorted_data = dict(sorted(quote_data.items()))
            filtered_strikes = filter_strikes(np.array(list(sorted_data.keys())), S, num_stdev=1.25)
            sorted_data = {strike: prices for strike, prices in sorted_data.items() if strike in filtered_strikes and prices['bid'] != 0.0}

            current_time = datetime.now()
            T = (expiration_time - current_time).total_seconds() / (365 * 24 * 3600)

            for strike, prices in sorted_data.items():
                sorted_data[strike] = {
                    "bid": prices["bid"],
                    "ask": prices["ask"],
                    "mid": prices["mid"],
                    "open_interest": prices["open_interest"],
                    "mid_IV": calculate_implied_volatility_baw(prices["mid"], S, strike, r, T, q=q, option_type=option_type),
                    "ask_IV": calculate_implied_volatility_baw(prices["ask"], S, strike, r, T, q=q, option_type=option_type),
                    "bid_IV": calculate_implied_volatility_baw(prices["bid"], S, strike, r, T, q=q, option_type=option_type)
                }

            sorted_data = {strike: prices for strike, prices in sorted_data.items() if prices['mid_IV'] > 0.005}

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

                rbf_interpolator = rbf_model(np.log(x_normalized), y_mid_iv, epsilon=0.5)
                rfv_params = fit_model(x_normalized, y_mid_iv, y_bid_iv, y_ask_iv, rfv_model)

                fine_x_normalized = np.linspace(np.min(x_normalized), np.max(x_normalized), 800)
                rbf_interpolated_y = rbf_interpolator(np.log(fine_x_normalized).reshape(-1, 1))
                rfv_interpolated_y = rfv_model(np.log(fine_x_normalized), rfv_params)
                
                # Weighted Averaging: RFV 75%, RBF 25%
                interpolated_y = 0.75 * rfv_interpolated_y + 0.25 * rbf_interpolated_y

                y_pred = np.interp(x_normalized, fine_x_normalized, interpolated_y)
                rmse = calculate_rmse(y_mid_iv, y_pred)
                print(rmse)

                fine_x = np.linspace(np.min(x), np.max(x), 800)

                if config["MIN_OI"] > 0.0:
                    mask = open_interest > config["MIN_OI"]
                    x = x[mask]
                    y_bid_iv = y_bid_iv[mask]
                    y_ask_iv = y_ask_iv[mask]
                    y_mid_iv = y_mid_iv[mask]
                    open_interest = open_interest[mask]
                    y_mid = y_mid[mask]

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

                for i in range(len(x)):
                    print(f"Strike: {x[i]}, Mid Price: {y_mid[i]}, Mispricing: {mispricings[i]}")
                
                # Write to CSV files
                write_csv("original_strikes_mid_iv.csv", x, y_mid_iv)
                write_csv("interpolated_strikes_iv.csv", fine_x, interpolated_y)
                print("Data written to CSV files successfully.")
        else:
            print("NYSE is currently closed.")
            break

        await asyncio.sleep(config["TIME_TO_REST"])

        # ADDED FOR NOW
        break

if __name__ == "__main__":
    asyncio.run(main())
