from datetime import datetime, timedelta
from collections import defaultdict
import httpx
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import asyncio
import nest_asyncio

nest_asyncio.apply()

from schwab.auth import easy_client
from schwab.orders.equities import equity_buy_market, equity_sell_short_market, equity_sell_market, equity_buy_to_cover_market
from src.helpers import calculate_rmse, filter_strikes, is_nyse_open, load_config, precompile_numba_functions, get_risk_free_rate, write_csv
from src.models import barone_adesi_whaley_american_option_price, calculate_delta, calculate_implied_volatility_baw
from src.interpolations import fit_model, rbf_model, rfv_model

# Constants and Global Variables
config = {}
client = None

S = 0.0
r = 0.0
q = 0.0
option_type = ""

ticker = ""
date = ""
quote_data = defaultdict(lambda: {"bid": None, "ask": None, "mid": None, "open_interest": None, "bid_IV": None, "ask_IV": None, "mid_IV": None})

async def fetch_streamer_quotes_and_calculate_deltas(ticker, streamers_tickers, expiration_time, options, total_shares):
    """
    Fetch streamer quotes and calculate deltas for options on the specified ticker.

    Args:
        ticker (str): The ticker symbol of the underlying security.
        streamers_tickers (list): A list of option ticker symbols.
        expiration_time (datetime): The expiration time of the options.
        options (dict): Dictionary of options positions.
        total_shares (int): The total number of shares held for the ticker.

    Returns:
        tuple: A tuple containing total_deltas (float) and delta_imbalance (float).
    """
    total_deltas = 0.0
    enable_hedge = False

    try:
        resp = await client.get_quote(ticker)
        assert resp.status_code == httpx.codes.OK
        stock_quote_data = resp.json()

        S = round((stock_quote_data[ticker]['quote']['bidPrice'] + stock_quote_data[ticker]['quote']['askPrice']) / 2, 3)

        resp = await client.get_quotes(streamers_tickers)
        assert resp.status_code == httpx.codes.OK
        options_quote_data = resp.json()

        current_time = datetime.now()

        for quote in options_quote_data:
            price = (options_quote_data[quote]["quote"]["bidPrice"] + options_quote_data[quote]["quote"]["askPrice"]) / 2
            T = (expiration_time - current_time).total_seconds() / (365 * 24 * 3600)
            K = float(options_quote_data[quote]['reference']['strikePrice'])
            option_type = 'calls' if options_quote_data[quote]['reference']['contractType'] == 'C' else 'puts'

            sigma = calculate_implied_volatility_baw(price, S, K, r, T, q=q, option_type=option_type)
            delta = calculate_delta(S, K, T, r, sigma, q=q, option_type=option_type)

            if sigma > 0.005:
                enable_hedge = True

            quantity = float(options[quote]["longQuantity"]) - float(options[quote]["shortQuantity"])
            total_deltas += (delta * quantity * 100.0)
    except Exception as e:
        print(f"Error fetching quotes: {str(e)}")

    total_deltas = round(total_deltas)
    if enable_hedge:
        delta_imbalance = total_shares + total_deltas
    else:
        delta_imbalance = 0

    return total_deltas, delta_imbalance

async def adjust_delta_imbalance(ticker, delta_imbalance, config, is_closing_position=False):
    """
    Adjust the delta imbalance by placing appropriate market orders to hedge the exposure or close the position.

    Args:
        ticker (str): The ticker symbol of the security.
        delta_imbalance (float): The calculated delta imbalance that needs to be hedged.
        total_shares (int): The total number of shares held for the ticker.
        is_closing_position (bool, optional): If True, the function will close the position rather than hedging. Defaults to False.

    Returns:
        None
    """
    if delta_imbalance > 0:
        print(f"ADJUSTMENT NEEDED: Go short {delta_imbalance} shares.")
        if config["DRY_RUN"] != True:
            try:
                if is_closing_position:
                    order = equity_sell_market(ticker, int(delta_imbalance)).build()
                else:
                    order = equity_sell_short_market(ticker, int(delta_imbalance)).build()
                print(f"Order placed for -{delta_imbalance} shares...")
                resp = await client.place_order(config["SCHWAB_ACCOUNT_HASH"], order)
                assert resp.status_code == httpx.codes.OK
            except Exception as e:
                print(f"{e}")
    else:
        print(f"ADJUSTMENT NEEDED: Go long {-1 * delta_imbalance} shares.")
        if config["DRY_RUN"] != True:
            try:
                if is_closing_position:
                    order = equity_buy_to_cover_market(ticker, int(-1 * delta_imbalance)).build()
                else:
                    order = equity_buy_market(ticker, int(-1 * delta_imbalance)).build()
                print(f"Order placed for +{-1 * delta_imbalance} shares...")
                resp = await client.place_order(config["SCHWAB_ACCOUNT_HASH"], order)
                assert resp.status_code == httpx.codes.OK
            except Exception as e:
                print(f"{e}")

async def main():
    """
    Main function to initialize the bot.
    """
    global client, S, r, q, option_type, ticker, date, quote_data
    
    precompile_numba_functions()
    config = load_config()
    r = get_risk_free_rate(config["FRED_API_KEY"])
    if r is None:
        return
    ticker = config["TICKER"]
    option_type = config["OPTION_TYPE"]

    try:
        client = easy_client(
            token_path='token.json',
            api_key=config["SCHWAB_API_KEY"],
            app_secret=config["SCHWAB_SECRET"],
            callback_url=config["SCHWAB_CALLBACK_URL"],
            asyncio=True)
        print("Login successful.\n")

        resp = await client.get_account_numbers()
        assert resp.status_code == httpx.codes.OK

        account_ID_data = resp.json()
        print(account_ID_data, "\n")
    except Exception as e:
        print("Login Failed", f"An error occurred: {str(e)}")
        return
    
    try:
        resp = await client.get_option_expiration_chain(ticker)        
        assert resp.status_code == httpx.codes.OK
        expirations = resp.json()

        if expirations is not None and expirations["expirationList"]:
            expiration_dates_list = []

            for expiration in expirations["expirationList"]:
                expiration_dates_list.append(expiration["expirationDate"])
                
            date = expiration_dates_list[config["DATE_INDEX"]]
        else:
            print("Validation Failed", f"Invalid ticker symbol: {ticker}. Please use a valid ticker.")
            return
    except Exception as e:
        print("Validation Failed", f"An error occurred: {str(e)}")
        return
    
    try:
        respDiv = await client.get_quote(ticker)
        assert respDiv.status_code == httpx.codes.OK
        div = respDiv.json()

        q = float(div[ticker]["fundamental"]["divYield"]) / 100
    except Exception as e:
        print(f"An unexpected error occurred in options stream: {e}")
        return

    option_date = datetime.strptime(date, "%Y-%m-%d").date()
    expiration_time =datetime.combine(datetime.strptime(date, '%Y-%m-%d'), datetime.min.time()) + timedelta(hours=16)

    contract_type = client.Options.ContractType.CALL if option_type == "calls" else client.Options.ContractType.PUT
    chain_primary_key = "callExpDateMap" if option_type == "calls" else "putExpDateMap"












    while True:
        if (is_nyse_open() or config["DRY_RUN"]):
            streamers_tickers = []
            options = {}
            total_shares = 0

            try:
                resp = await client.get_account(config["SCHWAB_ACCOUNT_HASH"], fields=[client.Account.Fields.POSITIONS])
                assert resp.status_code == httpx.codes.OK

                account_data = resp.json()

                if "positions" in account_data["securitiesAccount"]:
                    positions = account_data["securitiesAccount"]["positions"]
                    for position in positions:
                        asset_type = position["instrument"]["assetType"]

                        if asset_type == "EQUITY":
                            symbol = position["instrument"]["symbol"]
                            if symbol == ticker:
                                total_shares = round(float(position["longQuantity"]) - float(position["shortQuantity"]))

                        elif asset_type == "OPTION":
                            underlying_symbol = position["instrument"]["underlyingSymbol"]
                            if underlying_symbol == ticker:
                                options[position["instrument"]["symbol"]] = position
                                streamers_tickers.append(position["instrument"]["symbol"])
            except Exception as e:
                print("Error fetching account positions:", f"An error occurred: {str(e)}")

            if len(streamers_tickers) != 0:
                total_deltas, delta_imbalance = await fetch_streamer_quotes_and_calculate_deltas(
                    ticker, streamers_tickers, expiration_time, options, total_shares
                )
                print(f"UNDERLYING SYMBOL: {ticker}")
                print(f"TOTAL SHARES: {total_shares}")
                print(f"TOTAL DELTAS: {total_deltas}")
                print(f"DELTA IMBALANCE: {delta_imbalance}")
                if delta_imbalance != 0:
                    await adjust_delta_imbalance(ticker, delta_imbalance, config)
            elif total_shares != 0:
                total_deltas = 0
                delta_imbalance = total_shares + total_deltas
                print(f"UNDERLYING SYMBOL: {ticker}")
                print(f"TOTAL SHARES: {total_shares}")
                print(f"TOTAL DELTAS: {total_deltas}")
                print(f"DELTA IMBALANCE: {delta_imbalance}")
                if delta_imbalance != 0:
                    await adjust_delta_imbalance(ticker, delta_imbalance, config, is_closing_position=True)


























            try:
                respChain = await client.get_option_chain(ticker, from_date=option_date, to_date=option_date, contract_type=contract_type)
                assert respChain.status_code == httpx.codes.OK
                chain = respChain.json()

                if chain["underlyingPrice"] is not None:
                    S = float(chain["underlyingPrice"])

                chain_secondary_key = next(iter(chain[chain_primary_key].keys()))
                for strike_price in chain[chain_primary_key][chain_secondary_key]:
                    option_json = chain[chain_primary_key][chain_secondary_key][strike_price][0]
                    bid_price = option_json["bid"]
                    ask_price = option_json["ask"]
                    open_interest = option_json["openInterest"]

                    if strike_price is not None and bid_price is not None and ask_price is not None and open_interest is not None:
                        mid_price = round(float((bid_price + ask_price) / 2), 3)
                        quote_data[float(strike_price)] = {
                            "bid": float(bid_price),
                            "ask": float(ask_price),
                            "mid": float(mid_price),
                            "open_interest": float(open_interest),
                            "bid_IV": 0.0,
                            "ask_IV": 0.0,
                            "mid_IV": 0.0
                        }
            except Exception as e:
                print(f"An unexpected error occurred in options stream: {e}")

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
