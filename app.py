import nest_asyncio
nest_asyncio.apply()

from schwab.auth import easy_client
import asyncio
from helpers import load_config, precompile_numba_functions, get_risk_free_rate

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

    await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
