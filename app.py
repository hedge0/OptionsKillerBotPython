from datetime import datetime, timedelta
from collections import defaultdict
import httpx
import asyncio
import nest_asyncio
nest_asyncio.apply()

import numpy as np
from schwab.auth import easy_client
from helpers import filter_strikes, load_config, precompile_numba_functions, get_risk_free_rate

# Constants and Global Variables
config = {}
client = None

S = 0.0
r = 0.0
q = 0.0
option_type = ""

ticker = ""
date = ""
quote_data = defaultdict(lambda: {"bid": None, "ask": None, "mid": None, "open_interest": None})

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

    option_type = client.Options.ContractType.CALL if config["OPTION_TYPE"] == "calls" else client.Options.ContractType.PUT
    chain_primary_key = "callExpDateMap" if config["OPTION_TYPE"] == "calls" else "putExpDateMap"

    while True:
        try:
            respChain = await client.get_option_chain(ticker, from_date=option_date, to_date=option_date, contract_type=option_type)
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
                        "open_interest": float(open_interest)
                    }

        except Exception as e:
            print(f"An unexpected error occurred in options stream: {e}")

        sorted_data = dict(sorted(quote_data.items()))
        filtered_strikes = filter_strikes(np.array(list(sorted_data.keys())), S, num_stdev=1.25)
        sorted_data = {strike: prices for strike, prices in sorted_data.items() if strike in filtered_strikes}

        current_time = datetime.now()
        T = (expiration_time - current_time).total_seconds() / (365 * 24 * 3600)

        print(sorted_data)
        print(S)
        print(T)

        await asyncio.sleep(config["TIME_TO_REST"])

        # ADDED FOR NOW
        break

if __name__ == "__main__":
    asyncio.run(main())
