import httpx
import asyncio
import nest_asyncio
nest_asyncio.apply()

from schwab.auth import easy_client
from helpers import load_config, precompile_numba_functions, get_risk_free_rate

# Constants and Global Variables
config = {}
client = None

r = 0.0
q = 0.0
option_type = ""

ticker = ""
chain_primary_key = ""

async def main():
    """
    Main function to initialize the bot.
    """
    global client, r, q, option_type, chain_primary_key, ticker
    
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
                
            print(expiration_dates_list)
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

    #option_date = datetime.strptime(self.selected_date, "%Y-%m-%d").date()
    option_type = client.Options.ContractType.CALL if config["OPTION_TYPE"] == "calls" else client.Options.ContractType.PUT
    chain_primary_key = "callExpDateMap" if config["OPTION_TYPE"] == "calls" else "putExpDateMap"

    print(q)
    print(r)

    await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
