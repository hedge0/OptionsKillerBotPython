import httpx
from collections import defaultdict
from datetime import datetime
from schwab.auth import easy_client
from schwab.orders.equities import equity_buy_market, equity_sell_short_market, equity_sell_market, equity_buy_to_cover_market

from src.models import calculate_delta, calculate_implied_volatility_baw

client = None

async def authenticate_schwab_client(config):
    """
    Authenticate the user using the Schwab client.

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
    except Exception as e:
        print(f"Login Failed: An error occurred: {str(e)}")
        client = None

async def fetch_account_numbers():
    """
    Fetch account numbers from the authenticated Schwab client.

    Returns:
        dict: Account ID data or None if retrieval fails.
    """
    try:
        resp = await client.get_account_numbers()
        assert resp.status_code == httpx.codes.OK
        return resp.json()
    except Exception as e:
        print(f"Failed to fetch account numbers: {str(e)}")
        return None

async def fetch_option_expiration_chain(ticker):
    """
    Fetch the option expiration chain for a given ticker.

    Args:
        ticker (str): The ticker symbol of the underlying security.

    Returns:
        dict: The expiration chain if successful, None otherwise.
    """
    try:
        resp = await client.get_option_expiration_chain(ticker)
        assert resp.status_code == httpx.codes.OK
        return resp.json()
    except Exception as e:
        print(f"Failed to fetch expiration chain: {str(e)}")
        return None

async def fetch_dividend_data(ticker):
    """
    Fetch the raw dividend data for a given ticker.

    Args:
        ticker (str): The ticker symbol of the underlying security.

    Returns:
        dict: The raw dividend data, or None if an error occurs.
    """
    try:
        resp = await client.get_quote(ticker)
        assert resp.status_code == httpx.codes.OK
        return resp.json()
    except Exception as e:
        print(f"Failed to fetch dividend data for {ticker}: {e}")
        return None

async def fetch_orders_for_account(account_hash, from_date, to_date):
    """
    Fetch orders for a given account within a specified date range.

    Args:
        account_hash (str): The account identifier for order management.
        from_date (datetime): The start date for filtering orders.
        to_date (datetime): The end date for filtering orders.

    Returns:
        list: A list of orders, or None if an error occurs.
    """
    try:
        resp = await client.get_orders_for_account(
            account_hash, 
            from_entered_datetime=from_date, 
            to_entered_datetime=to_date, 
            status=client.Order.Status.WORKING
        )
        assert resp.status_code == httpx.codes.OK
        return resp.json()
    except Exception as e:
        print(f"Error fetching account orders: {str(e)}")
        return None

async def cancel_order(order_id, account_hash):
    """
    Cancel an existing order for a given account.

    Args:
        order_id (str): The order ID to cancel.
        account_hash (str): The account identifier for order management.

    Returns:
        bool: True if the order was successfully canceled, False otherwise.
    """
    try:
        resp = await client.cancel_order(order_id, account_hash)
        assert resp.status_code == httpx.codes.OK
        return True
    except Exception as e:
        print(f"Error cancelling order {order_id}: {str(e)}")
        return False

async def fetch_account_data(account_hash):
    """
    Fetch the account data for the specified account.

    Args:
        account_hash (str): The account identifier.

    Returns:
        dict: The account data if successful, None otherwise.
    """
    try:
        resp = await client.get_account(account_hash, fields=[client.Account.Fields.POSITIONS])
        assert resp.status_code == httpx.codes.OK
        return resp.json()
    except Exception as e:
        print(f"Error fetching account data: {str(e)}")
        return None












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
