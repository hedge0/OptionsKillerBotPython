import httpx
import nest_asyncio
nest_asyncio.apply()

from schwab.auth import easy_client
import asyncio
from helpers import load_config, precompile_numba_functions, get_risk_free_rate

# Constants and Global Variables
config = {}
risk_free_rate = 0.0
div_yield = 0.0
client = None

async def main():
    """
    Main function to initialize the bot.
    """
    global client, risk_free_rate, div_yield
    
    precompile_numba_functions()
    config = load_config()
    risk_free_rate = get_risk_free_rate(config["FRED_API_KEY"])
    if risk_free_rate is None:
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
        respDiv = await client.get_quote(config["TICKER"])
        assert respDiv.status_code == httpx.codes.OK
        div = respDiv.json()
        div_yield = float(div[config["TICKER"]]["fundamental"]["divYield"]) / 100
    except Exception as e:
        print(f"An unexpected error occurred in options stream: {e}")

    #option_date = datetime.strptime(self.selected_date, "%Y-%m-%d").date()
    contract_type = client.Options.ContractType.CALL if config["OPTION_TYPE"] == "calls" else client.Options.ContractType.PUT
    chain_primary_key = "callExpDateMap" if config["OPTION_TYPE"] == "calls" else "putExpDateMap"

    await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
