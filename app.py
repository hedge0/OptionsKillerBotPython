from datetime import datetime, timedelta
from collections import defaultdict
import httpx
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import asyncio
import nest_asyncio

nest_asyncio.apply()

from schwab.auth import easy_client
from helpers import calculate_rmse, filter_strikes, load_config, precompile_numba_functions, get_risk_free_rate
from models import calculate_implied_volatility_baw
from interpolations import fit_model, rbf_model, rfv_model

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




        print(sorted_data)
        print(S)
        print(T)    




        x = np.array(list(sorted_data.keys())) 
        y_bid = np.array([prices['bid_IV'] for prices in sorted_data.values()])
        y_ask = np.array([prices['ask_IV'] for prices in sorted_data.values()])
        y_mid = np.array([prices['mid_IV'] for prices in sorted_data.values()])
        open_interest = np.array([prices['open_interest'] for prices in sorted_data.values()])

        scaler = MinMaxScaler()
        x_normalized = scaler.fit_transform(x.reshape(-1, 1)).flatten()
        x_normalized = x_normalized + 0.5

        rbf_interpolator = rbf_model(np.log(x_normalized), y_mid, epsilon=0.5)
        rfv_params = fit_model(x_normalized, y_mid, y_bid, y_ask, rfv_model)

        fine_x_normalized = np.linspace(np.min(x_normalized), np.max(x_normalized), 800)
        rbf_interpolated_y = rbf_interpolator(np.log(fine_x_normalized).reshape(-1, 1))
        rfv_interpolated_y = rfv_model(np.log(fine_x_normalized), rfv_params)
        
        # Weighted Averaging: RFV 75%, RBF 25%
        interpolated_y = 0.75 * rfv_interpolated_y + 0.25 * rbf_interpolated_y

        fine_x = np.linspace(np.min(x), np.max(x), 800)

        y_pred = np.interp(x_normalized, fine_x_normalized, interpolated_y)
        rmse = calculate_rmse(y_mid, y_pred)




        await asyncio.sleep(config["TIME_TO_REST"])

        # ADDED FOR NOW
        break

if __name__ == "__main__":
    asyncio.run(main())
