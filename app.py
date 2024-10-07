import nest_asyncio
nest_asyncio.apply()

import httpx
from fredapi import Fred
from schwab.auth import easy_client
from schwab.orders.equities import equity_buy_market, equity_sell_short_market, equity_sell_market, equity_buy_to_cover_market
import asyncio
import os
from datetime import datetime
from dotenv import load_dotenv
from models import calculate_delta, calculate_implied_volatility_baw

# Load environment variables from .env file
load_dotenv()

# Constants and Global Variables
config = {}
risk_free_rate = 0.0
client = None

async def main():
    """
    Main function to initialize the bot.
    """
    global client, risk_free_rate
    
    precompile_numba_functions()
    load_config()

    try:
        fred = Fred(api_key=config["FRED_API_KEY"])
        sofr_data = fred.get_series('SOFR')
        risk_free_rate = (sofr_data.iloc[-1] / 100)
    except Exception as e:
        print("FRED API Error", f"Invalid FRED API Key: {str(e)}")
        return

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
        resp = await client.get_account_numbers()
        assert resp.status_code == httpx.codes.OK

        account_ID_data = resp.json()
        print(account_ID_data, "\n")
    except Exception as e:
        print("Error fetching account IDs:", f"An error occurred: {str(e)}")
        return

    while True:
        stocks, options, streamers_tickers, deltas, stocks_to_hedge = {}, {}, {}, {}, {}

        try:
            resp = await client.get_account(config["SCHWAB_ACCOUNT_HASH"], fields=[client.Account.Fields.POSITIONS])
            assert resp.status_code == httpx.codes.OK

            account_data = resp.json()
            positions = account_data["securitiesAccount"]["positions"]

            for position in positions:
                asset_type = position["instrument"]["assetType"]

                if asset_type == "EQUITY":
                    symbol = position["instrument"]["symbol"]
                    stocks[symbol] = round(float(position["longQuantity"]) - float(position["shortQuantity"]))

                elif asset_type == "OPTION":
                    underlying_symbol = position["instrument"]["underlyingSymbol"]
                    if underlying_symbol not in streamers_tickers:
                        options[underlying_symbol] = {}
                        streamers_tickers[underlying_symbol] = []
                    options[underlying_symbol][position["instrument"]["symbol"]] = position
                    streamers_tickers[underlying_symbol].append(position["instrument"]["symbol"])
        except Exception as e:
            print("Error fetching account positions:", f"An error occurred: {str(e)}")

        for ticker in options:
            total_deltas = 0.0
            if len(streamers_tickers[ticker]) != 0:
                try:
                    resp = await client.get_quote(ticker)
                    assert resp.status_code == httpx.codes.OK

                    stock_quote_data = resp.json()
                    S = round((stock_quote_data[ticker]['quote']['bidPrice'] + stock_quote_data[ticker]['quote']['askPrice']) / 2, 3)
                    div_yield = float(stock_quote_data[ticker]["fundamental"]["divYield"]) / 100
                    current_time = datetime.now()

                    resp = await client.get_quotes(streamers_tickers[ticker])
                    assert resp.status_code == httpx.codes.OK

                    quote_data = resp.json()
                    for quote in quote_data:
                        price = (quote_data[quote]["quote"]["bidPrice"] + quote_data[quote]["quote"]["askPrice"]) / 2
                        expiration_time = datetime(quote_data[quote]['reference']['expirationYear'], quote_data[quote]['reference']['expirationMonth'], quote_data[quote]['reference']['expirationDay'])
                        T = (expiration_time - current_time).total_seconds() / (365 * 24 * 3600)
                        K = float(quote_data[quote]['reference']['strikePrice'])
                        option_type = 'calls' if quote_data[quote]['reference']['contractType'] == 'C' else 'puts'

                        sigma = calculate_implied_volatility_baw(price, S, K, risk_free_rate, T, q=div_yield, option_type=option_type)
                        delta = calculate_delta(S, K, T, risk_free_rate, sigma, q=div_yield, option_type=option_type)
                        if (sigma < 0.005):
                            stocks_to_hedge[ticker] = False

                        quantity = float(options[ticker][quote]["longQuantity"]) - float(options[ticker][quote]["shortQuantity"])
                        total_deltas += (delta * quantity * 100.0)
                except Exception as e:
                    print("Error fetching quotes:", f"An error occurred: {str(e)}")
            deltas[ticker] = round(total_deltas)
            if ticker not in stocks_to_hedge:
                stocks_to_hedge[ticker] = True

            total_shares = stocks.get(ticker, 0)
            total_deltas = deltas.get(ticker, 0)

            if stocks_to_hedge[ticker] == True:
                delta_imbalance = total_shares + total_deltas
            else:
                delta_imbalance = 0

            print(f"UNDERLYING SYMBOL: {ticker}")
            print(f"TOTAL SHARES: {total_shares}")
            print(f"TOTAL DELTAS: {total_deltas}")
            print(f"DELTA IMBALANCE: {delta_imbalance}")

            if delta_imbalance != 0:
                if delta_imbalance > 0:
                    print(f"ADJUSTMENT NEEDED: Going short {delta_imbalance} shares to hedge the delta exposure.")

                    try:
                        if config["DRY_RUN"] != True:
                            order = equity_sell_short_market(ticker, int(delta_imbalance)).build()
                            print(f"Order placed for -{delta_imbalance} shares...")
                            resp = await client.place_order(config["SCHWAB_ACCOUNT_HASH"], order)
                            assert resp.status_code == httpx.codes.OK
                    except Exception as e:
                        print(f"{e}")

                else:
                    print(f"ADJUSTMENT NEEDED: Going long {-1 * delta_imbalance} shares to hedge the delta exposure.")

                    try:
                        if config["DRY_RUN"] != True:
                            order = equity_buy_market(ticker, int(-1 * delta_imbalance)).build()
                            print(f"Order placed for +{-1 * delta_imbalance} shares...")
                            resp = await client.place_order(config["SCHWAB_ACCOUNT_HASH"], order)
                            assert resp.status_code == httpx.codes.OK
                    except Exception as e:
                        print(f"{e}")
            else:
                print(f"No adjustment needed. Delta is perfectly hedged with shares.")  
            print()

        for ticker in stocks:
            if ticker not in options:
                total_shares = stocks.get(ticker, 0)
                total_deltas = 0

                print(f"UNDERLYING SYMBOL: {ticker}")
                print(f"TOTAL SHARES: {total_shares}")
                print(f"TOTAL DELTAS: {total_deltas}")
                print(f"DELTA IMBALANCE: {delta_imbalance}")

                delta_imbalance = total_shares + total_deltas

                if delta_imbalance != 0:
                    if delta_imbalance > 0:
                        print(f"ADJUSTMENT NEEDED: Going short {delta_imbalance} shares to hedge the delta exposure.")

                        try:
                            if config["DRY_RUN"] != True:
                                order = equity_sell_market(ticker, int(delta_imbalance)).build()
                                print(f"Order placed for -{delta_imbalance} shares...")
                                resp = await client.place_order(config["SCHWAB_ACCOUNT_HASH"], order)
                                assert resp.status_code == httpx.codes.OK
                        except Exception as e:
                            print(f"{e}")

                    else:
                        print(f"ADJUSTMENT NEEDED: Going long {-1 * delta_imbalance} shares to hedge the delta exposure.")

                        try:
                            if config["DRY_RUN"] != True:
                                order = equity_buy_to_cover_market(ticker, int(-1 * delta_imbalance)).build()
                                print(f"Order placed for +{-1 * delta_imbalance} shares...")
                                resp = await client.place_order(config["SCHWAB_ACCOUNT_HASH"], order)
                                assert resp.status_code == httpx.codes.OK
                        except Exception as e:
                            print(f"{e}")
                else:
                    print(f"No adjustment needed. Delta is perfectly hedged with shares.")  
                print()

        await asyncio.sleep(config["HEDGING_FREQUENCY"])
        
def load_config():
    """
    Load configuration from environment variables and validate them.
    
    Raises:
        ValueError: If any required environment variable is not set.
    """
    global config
    config = {
        "SCHWAB_API_KEY": os.getenv('SCHWAB_API_KEY'),
        "SCHWAB_SECRET": os.getenv('SCHWAB_SECRET'),
        "SCHWAB_CALLBACK_URL": os.getenv('SCHWAB_CALLBACK_URL'),
        "SCHWAB_ACCOUNT_HASH": os.getenv('SCHWAB_ACCOUNT_HASH'),
        "FRED_API_KEY": os.getenv('FRED_API_KEY'),
        "HEDGING_FREQUENCY": os.getenv('HEDGING_FREQUENCY'),
        "DRY_RUN": os.getenv('DRY_RUN', 'True').lower() in ['true', '1', 'yes']
    }

    for key, value in config.items():
        if value is None:
            raise ValueError(f"{key} environment variable not set")

    try:
        config["HEDGING_FREQUENCY"] = float(config["HEDGING_FREQUENCY"])
    except ValueError:
        raise ValueError("HEDGING_FREQUENCY environment variable must be a valid float")
    
def precompile_numba_functions():
    """
    Precompile Numba functions to improve performance.

    This method calls Numba-compiled functions with sample data to ensure they are precompiled,
    reducing latency during actual execution.
    """
    calculate_implied_volatility_baw(0.1, 100.0, 100.0, 0.01, 0.5, option_type='calls')
    calculate_delta(100.0, 100.0, 0.5, 0.01, 0.2, option_type='calls')

if __name__ == "__main__":
    asyncio.run(main())
