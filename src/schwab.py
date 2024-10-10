import httpx
from collections import defaultdict
from datetime import datetime
from schwab.auth import easy_client
from schwab.orders.equities import equity_buy_market, equity_sell_short_market, equity_sell_market, equity_buy_to_cover_market

from src.models import calculate_delta, calculate_implied_volatility_baw

client = None

async def initialize_client(config):
    """
    Initialize the Schwab client and authenticate the user.

    Args:
        config (dict): Configuration settings containing API credentials.

    Returns:
        None
    """
    global client
    try:
        client = easy_client(
            token_path='token.json',
            api_key=config["SCHWAB_API_KEY"],
            app_secret=config["SCHWAB_SECRET"],
            callback_url=config["SCHWAB_CALLBACK_URL"],
            asyncio=True
        )
        print("Login successful.\n")

        resp = await client.get_account_numbers()
        assert resp.status_code == httpx.codes.OK

        account_ID_data = resp.json()
        print(account_ID_data, "\n")
    except Exception as e:
        print("Login Failed", f"An error occurred: {str(e)}")
        client = None

async def get_option_expiration_date(ticker, date_index):
    """
    Fetch the option expiration date for a given ticker and date index.

    Args:
        ticker (str): The ticker symbol of the underlying security.
        date_index (int): The index to select the expiration date from the list.

    Returns:
        str: The selected expiration date if successful, None otherwise.
    """
    try:
        resp = await client.get_option_expiration_chain(ticker)        
        assert resp.status_code == httpx.codes.OK
        expirations = resp.json()

        if expirations is not None and expirations["expirationList"]:
            expiration_dates_list = []

            for expiration in expirations["expirationList"]:
                expiration_dates_list.append(expiration["expirationDate"])
                
            return expiration_dates_list[date_index]
        else:
            print("Validation Failed", f"Invalid ticker symbol: {ticker}. Please use a valid ticker.")
            return None
    except Exception as e:
        print("Validation Failed", f"An error occurred: {str(e)}")
        return None

async def get_dividend_yield(ticker):
    """
    Fetch the dividend yield for a given ticker.

    Args:
        ticker (str): The ticker symbol of the underlying security.

    Returns:
        float: The dividend yield as a decimal (e.g., 0.02 for 2%), or None if an error occurs.
    """
    try:
        resp = await client.get_quote(ticker)
        assert resp.status_code == httpx.codes.OK
        div = resp.json()

        return float(div[ticker]["fundamental"]["divYield"]) / 100
    except Exception as e:
        print(f"An unexpected error occurred in options stream: {e}")
        return None

async def cancel_existing_orders(ticker, account_hash, from_date, to_date):
    """
    Cancel existing orders for the specified ticker.

    Args:
        ticker (str): The ticker symbol of the underlying security.
        account_hash (str): The account identifier for order management.
        from_date (datetime): The start date for filtering orders.
        to_date (datetime): The end date for filtering orders.

    Returns:
        None
    """
    order_data = []

    try:
        resp = await client.get_orders_for_account(
            account_hash, 
            from_entered_datetime=from_date, 
            to_entered_datetime=to_date, 
            status=client.Order.Status.WORKING
        )
        assert resp.status_code == httpx.codes.OK
        order_data = resp.json()
    except Exception as e:
        print("Error fetching account orders:", f"An error occurred: {str(e)}")
        return

    for order in order_data:
        asset_type = order["orderLegCollection"][0]["instrument"]["assetType"]
        order_id = order["orderId"]

        if asset_type == "EQUITY" and order["orderLegCollection"][0]["instrument"]["symbol"] == ticker:
            try:
                resp = await client.cancel_order(order_id, account_hash)
                assert resp.status_code == httpx.codes.OK
            except Exception as e:
                print(f"Error cancelling equity order {order_id}:", f"An error occurred: {str(e)}")
        elif asset_type == "OPTION" and order["orderLegCollection"][0]["instrument"]["underlyingSymbol"] == ticker:
            try:
                resp = await client.cancel_order(order_id, account_hash)
                assert resp.status_code == httpx.codes.OK
            except Exception as e:
                print(f"Error cancelling option order {order_id}:", f"An error occurred: {str(e)}")

async def get_account_positions(ticker, account_hash):
    """
    Fetch the account positions for the specified ticker.

    Args:
        ticker (str): The ticker symbol of the underlying security.
        account_hash (str): The account identifier for retrieving positions.

    Returns:
        tuple: A tuple containing:
            - streamers_tickers (list): A list of option ticker symbols.
            - options (dict): Dictionary of options positions.
            - total_shares (int): The total number of shares held for the ticker.
    """
    streamers_tickers = []
    options = {}
    total_shares = 0

    try:
        resp = await client.get_account(account_hash, fields=[client.Account.Fields.POSITIONS])
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

    return streamers_tickers, options, total_shares

async def handle_delta_adjustments(ticker, streamers_tickers, expiration_time, options, total_shares, config, r, q):
    """
    Handle the calculation of deltas and adjust the delta imbalance for a given ticker.

    Args:
        ticker (str): The ticker symbol of the underlying security.
        streamers_tickers (list): A list of option ticker symbols.
        expiration_time (datetime): The expiration time of the options.
        options (dict): Dictionary of options positions.
        total_shares (int): The total number of shares held for the ticker.
        config (dict): Configuration settings.
        r (float): The risk-free rate.
        q (float): The dividend yield.

    Returns:
        None
    """
    if len(streamers_tickers) != 0:
        total_deltas, delta_imbalance = await fetch_streamer_quotes_and_calculate_deltas(
            ticker, streamers_tickers, expiration_time, options, total_shares, r, q
        )
        if delta_imbalance != 0:
            await adjust_delta_imbalance(ticker, delta_imbalance, config)
    elif total_shares != 0:
        total_deltas = 0
        delta_imbalance = total_shares + total_deltas
        if delta_imbalance != 0:
            await adjust_delta_imbalance(ticker, delta_imbalance, config, is_closing_position=True)

async def fetch_streamer_quotes_and_calculate_deltas(ticker, streamers_tickers, expiration_time, options, total_shares, r, q):
    """
    Fetch streamer quotes and calculate deltas for options on the specified ticker.

    Args:
        ticker (str): The ticker symbol of the underlying security.
        streamers_tickers (list): A list of option ticker symbols.
        expiration_time (datetime): The expiration time of the options.
        options (dict): Dictionary of options positions.
        total_shares (int): The total number of shares held for the ticker.
        r (float): The risk-free rate.
        q (float): The dividend yield.

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

async def get_option_chain_data(ticker, option_date, option_type):
    """
    Fetch the option chain data for the specified ticker and date.

    Args:
        ticker (str): The ticker symbol of the underlying security.
        option_date (datetime.date): The option expiration date.
        option_type (str): The contract type (CALL or PUT).

    Returns:
        tuple: A tuple containing:
            - quote_data (defaultdict): The quote data for each strike.
            - S (float): The underlying stock price.
    """
    quote_data = defaultdict(lambda: {"bid": None, "ask": None, "mid": None, "open_interest": None, "bid_IV": None, "ask_IV": None, "mid_IV": None})
    S = 0.0
    contract_type = client.Options.ContractType.CALL if option_type == "calls" else client.Options.ContractType.PUT
    chain_primary_key = "callExpDateMap" if option_type == "calls" else "putExpDateMap"

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

    return quote_data, S
