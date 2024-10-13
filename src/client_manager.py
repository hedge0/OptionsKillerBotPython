import httpx
from schwab.auth import easy_client

class ClientManager:
    """
    Manages the authentication and interaction with the Schwab API. Handles operations such as fetching account data, 
    quotes, orders, option chains, and placing/canceling orders.

    Attributes:
        config (dict): Configuration settings containing API credentials and other relevant parameters.
        client (object): The authenticated client object used to interact with the Schwab API.

    Methods:
        authenticate_schwab_client(): Authenticates the Schwab client.
        fetch_account_numbers(): Fetches the account numbers associated with the authenticated client.
        fetch_option_expiration_chain(ticker): Fetches the option expiration chain for the given ticker.
        fetch_quote(ticker): Fetches a quote for a specific ticker.
        fetch_quotes(streamers_tickers): Fetches quotes for a list of option tickers.
        fetch_orders_for_account(account_hash, from_date, to_date): Fetches orders for the specified account within the date range.
        fetch_account_data(account_hash): Fetches the account data, including positions, for a specified account.
        fetch_option_chain(ticker, option_date, option_type): Fetches the option chain for the specified ticker, date, and option type.
        place_order(account_hash, order): Places an order for the specified account.
        cancel_order(order_id, account_hash): Cancels an order with the given order ID for the specified account.
    """

    def __init__(self, config):
        """
        Initialize SchwabClientManager and set up client.

        Args:
            config (dict): Configuration settings containing API credentials.
        """
        self.config = config
        self.client = None

    async def authenticate_schwab_client(self):
        """
        Authenticate the user using the Schwab client.

        Returns:
            None
        """
        try:
            self.client = easy_client(
                token_path='token.json',
                api_key=self.config["SCHWAB_API_KEY"],
                app_secret=self.config["SCHWAB_SECRET"],
                callback_url=self.config["SCHWAB_CALLBACK_URL"],
                asyncio=True
            )
            print("Login successful.\n")
        except Exception as e:
            print(f"Login Failed: An error occurred: {str(e)}")
            self.client = None

    async def fetch_account_numbers(self):
        """
        Fetch account numbers from the authenticated Schwab client.

        Returns:
            dict: Account ID data or None if retrieval fails.
        """
        try:
            resp = await self.client.get_account_numbers()
            assert resp.status_code == httpx.codes.OK
            return resp.json()
        except Exception as e:
            print(f"Failed to fetch account numbers: {str(e)}")
            return None

    async def fetch_option_expiration_chain(self, ticker):
        """
        Fetch the option expiration chain for a given ticker.

        Args:
            ticker (str): The ticker symbol of the underlying security.

        Returns:
            dict: The expiration chain if successful, None otherwise.
        """
        try:
            resp = await self.client.get_option_expiration_chain(ticker)
            assert resp.status_code == httpx.codes.OK
            return resp.json()
        except Exception as e:
            print(f"Failed to fetch expiration chain: {str(e)}")
            return None

    async def fetch_quote(self, ticker):
        """
        Fetch the quote for the specified ticker.

        Args:
            ticker (str): The ticker symbol of the underlying security.

        Returns:
            dict: The quote data if successful, None otherwise.
        """
        try:
            resp = await self.client.get_quote(ticker)
            assert resp.status_code == httpx.codes.OK
            return resp.json()
        except Exception as e:
            print(f"Failed to fetch quote: {str(e)}")
            return None

    async def fetch_quotes(self, streamers_tickers):
        """
        Fetch the quotes for the specified tickers.

        Args:
            streamers_tickers (list): A list of option ticker symbols.

        Returns:
            dict: The quote data if successful, None otherwise.
        """
        try:
            resp = await self.client.get_quotes(streamers_tickers)
            assert resp.status_code == httpx.codes.OK
            return resp.json()
        except Exception as e:
            print(f"Failed to fetch quotes: {str(e)}")
            return None

    async def fetch_orders_for_account(self, account_hash, from_date, to_date):
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
            resp = await self.client.get_orders_for_account(
                account_hash, 
                from_entered_datetime=from_date, 
                to_entered_datetime=to_date, 
                status=self.client.Order.Status.WORKING
            )
            assert resp.status_code == httpx.codes.OK
            return resp.json()
        except Exception as e:
            print(f"Error fetching account orders: {str(e)}")
            return None

    async def fetch_account_data(self, account_hash):
        """
        Fetch the account data for the specified account.

        Args:
            account_hash (str): The account identifier.

        Returns:
            dict: The account data if successful, None otherwise.
        """
        try:
            resp = await self.client.get_account(account_hash, fields=[self.client.Account.Fields.POSITIONS])
            assert resp.status_code == httpx.codes.OK
            return resp.json()
        except Exception as e:
            print(f"Error fetching account data: {str(e)}")
            return None

    async def fetch_option_chain(self, ticker, option_date, option_type):
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
            respChain = await self.client.get_option_chain(
                ticker, 
                from_date=option_date, 
                to_date=option_date, 
                contract_type=self.client.Options.ContractType.CALL if option_type == "calls" else self.client.Options.ContractType.PUT
            )
            assert respChain.status_code == httpx.codes.OK
            return respChain.json()
        except Exception as e:
            print(f"Failed to fetch option chain: {str(e)}")
            return None

    async def place_order(self, account_hash, order):
        """
        Place an order with the given account hash.

        Args:
            account_hash (str): The account identifier.
            order (object): The order object to place.

        Returns:
            bool: True if the order was successful, False otherwise.
        """
        try:
            resp = await self.client.place_order(account_hash, order)
            assert resp.status_code == httpx.codes.OK
            return True
        except Exception as e:
            print(f"Failed to place order: {e}")
            return False

    async def cancel_order(self, order_id, account_hash):
        """
        Cancel an existing order for a given account.

        Args:
            order_id (str): The order ID to cancel.
            account_hash (str): The account identifier for order management.

        Returns:
            bool: True if the order was successfully canceled, False otherwise.
        """
        try:
            resp = await self.client.cancel_order(order_id, account_hash)
            assert resp.status_code == httpx.codes.OK
            return True
        except Exception as e:
            print(f"Error cancelling order {order_id}: {str(e)}")
            return False
