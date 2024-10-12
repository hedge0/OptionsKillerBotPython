import httpx
from schwab.auth import easy_client

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
    
async def fetch_quote(ticker):
    """
    Fetch the quote for the specified ticker.

    Args:
        ticker (str): The ticker symbol of the underlying security.

    Returns:
        dict: The quote data if successful, None otherwise.
    """
    try:
        resp = await client.get_quote(ticker)
        assert resp.status_code == httpx.codes.OK
        return resp.json()
    except Exception as e:
        print(f"Failed to fetch quote: {str(e)}")
        return None

async def fetch_quotes(streamers_tickers):
    """
    Fetch the quotes for the specified tickers.

    Args:
        streamers_tickers (list): A list of option ticker symbols.

    Returns:
        dict: The quote data if successful, None otherwise.
    """
    try:
        resp = await client.get_quotes(streamers_tickers)
        assert resp.status_code == httpx.codes.OK
        return resp.json()
    except Exception as e:
        print(f"Failed to fetch quotes: {str(e)}")
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

async def fetch_option_chain(ticker, option_date, option_type):
    """
    Fetch the option chain for a given ticker and date.

    Args:
        ticker (str): The ticker symbol of the underlying security.
        option_date (datetime.date): The option expiration date.
        option_type (str): The contract type, 'calls' for CALL or 'puts' for PUT.

    Returns:
        dict: The option chain data if successful, None otherwise.
    """
    try:
        respChain = await client.get_option_chain(
            ticker, 
            from_date=option_date, 
            to_date=option_date, 
            contract_type=client.Options.ContractType.CALL if option_type == "calls" else client.Options.ContractType.PUT
        )
        assert respChain.status_code == httpx.codes.OK
        return respChain.json()
    except Exception as e:
        print(f"Failed to fetch option chain: {str(e)}")
        return None
    
async def place_order(account_hash, order):
    """
    Place an order with the given account hash.

    Args:
        account_hash (str): The account identifier.
        order (object): The order object to place.

    Returns:
        bool: True if the order was successful, False otherwise.
    """
    try:
        resp = await client.place_order(account_hash, order)
        assert resp.status_code == httpx.codes.OK
        return True
    except Exception as e:
        print(f"Failed to place order: {e}")
        return False

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
    