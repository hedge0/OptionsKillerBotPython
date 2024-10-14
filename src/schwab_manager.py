from collections import defaultdict
from datetime import datetime
import logging
import math
from schwab.orders.equities import equity_buy_market, equity_sell_short_market, equity_sell_market, equity_buy_to_cover_market, equity_sell_short_limit
from schwab.orders.options import OptionSymbol

from src.models import calculate_delta, calculate_implied_volatility_baw
from src.client_manager import ClientManager

class SchwabManager:
    """
    A manager class that handles various operations with the Schwab API, such as fetching account positions, 
    handling delta adjustments, placing orders, fetching options chain data, and more.

    Attributes:
        config (dict): Configuration settings for Schwab API, including account hash and other parameters.
        client_manager (ClientManager): Manages authentication and communication with the Schwab API.

    Methods:
        initialize(): Authenticates the Schwab client and fetches account numbers.
        get_option_expiration_date(ticker, date_index): Fetches the option expiration date for a given ticker and index.
        get_dividend_yield(ticker): Fetches and parses the dividend yield for a given ticker.
        cancel_existing_orders(ticker, from_date, to_date): Cancels existing orders for a specified ticker within a date range.
        get_account_positions(ticker): Fetches the account positions for a specified ticker.
        fetch_streamer_quotes_and_calculate_deltas(ticker, streamers_tickers, expiration_time, options, total_shares, r, q): 
            Fetches streamer quotes and calculates delta values for options on the specified ticker.
        adjust_delta_imbalance(ticker, delta_imbalance, is_closing_position=False): Adjusts the delta imbalance by placing appropriate market orders to hedge or close the position.
        handle_delta_adjustments(ticker, streamers_tickers, expiration_time, options, total_shares, r, q): Handles delta calculations and adjusts delta imbalance for the given ticker.
        get_option_chain_data(ticker, option_date, option_type): Fetches the option chain data for the specified ticker and expiration date.
    """

    def __init__(self, config):
        """
        Initialize the SchwabManager and set up the client manager.
        
        Args:
            config (dict): Configuration settings for Schwab API.
        """
        self.config = config
        self.client_manager = ClientManager(config)

    async def initialize(self):
        """
        Authenticate the Schwab client and fetch account numbers.
        """
        await self.client_manager.authenticate_schwab_client()
        logging.getLogger().custom(await self.client_manager.fetch_account_numbers())

    async def get_option_expiration_date(self, ticker, date_index):
        """
        Fetch the option expiration date for a given ticker and index.

        Args:
            ticker (str): The ticker symbol of the underlying security.
            date_index (int): Index to select the expiration date from the expiration list.

        Returns:
            str: Selected expiration date if successful, None otherwise.
        """
        expirations = await self.client_manager.fetch_option_expiration_chain(ticker)
        
        if expirations is not None and expirations.get("expirationList"):
            expiration_dates_list = [expiration["expirationDate"] for expiration in expirations["expirationList"]]
            return expiration_dates_list[date_index] if date_index < len(expiration_dates_list) else None
        else:
            logging.error(f"Validation Failed: Invalid ticker symbol: {ticker}. Please use a valid ticker.")
            return None

    async def get_dividend_yield(self, ticker):
        """
        Fetch and parse the dividend yield for a given ticker.

        Args:
            ticker (str): The ticker symbol of the underlying security.

        Returns:
            float: The dividend yield as a decimal (e.g., 0.02 for 2%), or None if an error occurs.
        """
        div_data = await self.client_manager.fetch_quote(ticker)
        
        if div_data and ticker in div_data:
            try:
                return float(div_data[ticker]["fundamental"]["divYield"]) / 100
            except (KeyError, ValueError) as e:
                logging.error(f"Error parsing dividend yield for {ticker}: {e}")
                return None
        else:
            logging.error(f"Invalid data for {ticker}.")
            return None

    async def cancel_existing_orders(self, ticker, from_date, to_date):
        """
        Cancel existing orders for a specified ticker within a date range.

        Args:
            ticker (str): The ticker symbol of the underlying security.
            from_date (datetime): The start date for filtering orders.
            to_date (datetime): The end date for filtering orders.

        Returns:
            None
        """
        order_data = await self.client_manager.fetch_orders_for_account(self.config["SCHWAB_ACCOUNT_HASH"], from_date, to_date)

        if not order_data:
            return

        for order in order_data:
            asset_type = order["orderLegCollection"][0]["instrument"]["assetType"]
            order_id = order["orderId"]

            if asset_type == "EQUITY" and order["orderLegCollection"][0]["instrument"]["symbol"] == ticker:
                await self.client_manager.cancel_order(order_id, self.config["SCHWAB_ACCOUNT_HASH"])
            elif asset_type == "OPTION" and order["orderLegCollection"][0]["instrument"]["underlyingSymbol"] == ticker:
                await self.client_manager.cancel_order(order_id, self.config["SCHWAB_ACCOUNT_HASH"])

    async def get_account_positions(self, ticker):
        """
        Fetch the account positions for a specified ticker.

        Args:
            ticker (str): The ticker symbol of the underlying security.

        Returns:
            tuple: Contains:
                - streamers_tickers (list): List of option ticker symbols.
                - options (dict): Dictionary of options positions.
                - total_shares (int): Total number of shares held for the ticker.
        """
        account_data = await self.client_manager.fetch_account_data(self.config["SCHWAB_ACCOUNT_HASH"])
        if not account_data:
            return [], {}, 0

        streamers_tickers = [
            position["instrument"]["symbol"]
            for position in account_data["securitiesAccount"].get("positions", [])
            if position["instrument"]["assetType"] == "OPTION" and position["instrument"]["underlyingSymbol"] == ticker
        ]

        options = {
            position["instrument"]["symbol"]: position
            for position in account_data["securitiesAccount"].get("positions", [])
            if position["instrument"]["assetType"] == "OPTION" and position["instrument"]["underlyingSymbol"] == ticker
        }

        total_shares = sum(
            round(float(position["longQuantity"]) - float(position["shortQuantity"]))
            for position in account_data["securitiesAccount"].get("positions", [])
            if position["instrument"]["assetType"] == "EQUITY" and position["instrument"]["symbol"] == ticker
        )

        return streamers_tickers, options, total_shares

    async def fetch_streamer_quotes_and_calculate_deltas(self, ticker, streamers_tickers, expiration_time, options, total_shares, r, q):
        """
        Fetch streamer quotes and calculate delta values for options on the specified ticker.

        Args:
            ticker (str): The ticker symbol of the underlying security.
            streamers_tickers (list): A list of option ticker symbols.
            expiration_time (datetime): The expiration time of the options.
            options (dict): Dictionary of options positions.
            total_shares (int): The total number of shares held for the ticker.
            r (float): The risk-free rate.
            q (float): The dividend yield.

        Returns:
            tuple: Contains:
                - total_deltas (float): Total delta values.
                - delta_imbalance (float): Calculated delta imbalance.
        """
        total_deltas = 0.0
        enable_hedge = False

        stock_quote_data = await self.client_manager.fetch_quote(ticker)
        if not stock_quote_data:
            return total_deltas, 0

        S = round((stock_quote_data[ticker]['quote']['bidPrice'] + stock_quote_data[ticker]['quote']['askPrice']) / 2, 3)

        options_quote_data = await self.client_manager.fetch_quotes(streamers_tickers)
        if not options_quote_data:
            return total_deltas, 0

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

        total_deltas = round(total_deltas)
        delta_imbalance = total_shares + total_deltas if enable_hedge else 0

        return total_deltas, delta_imbalance

    async def adjust_delta_imbalance(self, ticker, delta_imbalance, is_closing_position=False):
        """
        Adjust the delta imbalance by placing appropriate market orders to hedge or close the position.

        Args:
            ticker (str): The ticker symbol of the security.
            delta_imbalance (float): The calculated delta imbalance that needs to be hedged.
            is_closing_position (bool, optional): If True, close the position rather than hedging.

        Returns:
            None
        """
        if delta_imbalance > 0:
            logging.getLogger().custom(f"ADJUSTMENT NEEDED: Go short {delta_imbalance} shares.")
            if not self.config["DRY_RUN"]:
                if is_closing_position:
                    order = equity_sell_market(ticker, int(delta_imbalance)).build()
                else:
                    order = equity_sell_short_market(ticker, int(delta_imbalance)).build()

                logging.getLogger().custom(f"Placing order for -{delta_imbalance} shares...")
                await self.client_manager.place_order(self.config["SCHWAB_ACCOUNT_HASH"], order)
        else:
            logging.getLogger().custom(f"ADJUSTMENT NEEDED: Go long {-1 * delta_imbalance} shares.")
            if not self.config["DRY_RUN"]:
                if is_closing_position:
                    order = equity_buy_to_cover_market(ticker, int(-1 * delta_imbalance)).build()
                else:
                    order = equity_buy_market(ticker, int(-1 * delta_imbalance)).build()

                logging.getLogger().custom(f"Placing order for +{-1 * delta_imbalance} shares...")
                await self.client_manager.place_order(self.config["SCHWAB_ACCOUNT_HASH"], order)

    async def handle_delta_adjustments(self, ticker, streamers_tickers, expiration_time, options, total_shares, r, q):
        """
        Handle delta calculations and adjust delta imbalance for the given ticker.

        Args:
            ticker (str): The ticker symbol of the underlying security.
            streamers_tickers (list): A list of option ticker symbols.
            expiration_time (datetime): The expiration time of the options.
            options (dict): Dictionary of options positions.
            total_shares (int): The total number of shares held for the ticker.
            r (float): The risk-free rate.
            q (float): The dividend yield.

        Returns:
            None
        """
        if len(streamers_tickers) != 0:
            total_deltas, delta_imbalance = await self.fetch_streamer_quotes_and_calculate_deltas(
                ticker, streamers_tickers, expiration_time, options, total_shares, r, q
            )
            if delta_imbalance != 0:
                await self.adjust_delta_imbalance(ticker, delta_imbalance)
        elif total_shares != 0:
            total_deltas = 0
            delta_imbalance = total_shares + total_deltas
            if delta_imbalance != 0:
                await self.adjust_delta_imbalance(ticker, delta_imbalance, is_closing_position=True)

    async def get_option_chain_data(self, ticker, option_date, option_type):
        """
        Fetch the option chain data for the specified ticker and expiration date.

        Args:
            ticker (str): The ticker symbol of the underlying security.
            option_date (datetime.date): The option expiration date.
            option_type (str): The contract type (either 'calls' or 'puts').

        Returns:
            tuple: Contains:
                - quote_data (defaultdict): The quote data for each strike.
                - S (float): The underlying stock price.
        """
        quote_data = defaultdict(lambda: {"bid": None, "ask": None, "mid": None, "open_interest": None, "bid_IV": None, "ask_IV": None, "mid_IV": None})
        S = 0.0
        chain_primary_key = "callExpDateMap" if option_type == "calls" else "putExpDateMap"

        chain = await self.client_manager.fetch_option_chain(ticker, option_date, option_type)
        if not chain:
            return quote_data, S

        if chain.get("underlyingPrice") is not None:
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

        return quote_data, S

    async def sell_option(self, ticker, option_type, option_date, strike, mid_price, best_mispricing):
        """
        Places a limit order to sell an option contract.

        Args:
            ticker (str): The ticker symbol of the underlying security.
            option_type (str): The type of option ('calls' or 'puts').
            option_date (datetime.date): The expiration date of the option contract.
            strike (float): The strike price of the option contract.
            mid_price (float): The calculated mid-price of the option contract.
            best_mispricing (float): The best mispricing value used for decision making.

        Returns:
            None
        """
        mid_price_floored = math.floor(float(mid_price) * 100) / 100
        contract_type = 'C' if option_type == 'calls' else 'P'
        symbol = OptionSymbol(
            ticker, option_date, contract_type, str(strike)).build()

        logging.getLogger().custom(f"Go short {symbol} at LIMIT {mid_price_floored} with mispricing: {best_mispricing}.")
        if not self.config["DRY_RUN"]:
            order = equity_sell_short_limit(symbol, int(1), mid_price_floored).build()

            logging.getLogger().custom(f"Placing order to SELL {symbol} at {mid_price_floored}...")
            await self.client_manager.place_order(self.config["SCHWAB_ACCOUNT_HASH"], order)
