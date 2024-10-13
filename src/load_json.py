import json

from src.trade_state import TradeState 

class StockNode:
    """
    Class representing a node in the circular linked list, holding stock data.
    
    Attributes:
        ticker (str): Ticker symbol of the stock.
        date_index (int): Date index for the option expiration.
        option_type (str): Type of option ('call' or 'put').
        min_overpriced (float): Minimum overpriced threshold.
        min_oi (float): Minimum open interest.
        q (float): Dividend yield.
        trade_state (TradeState): Current trade state of the stock.
        option_date (datetime or None): Date of the option.
        expiration_time (datetime or None): Expiration time of the option.
        from_entered_datetime (datetime or None): Start time for entered datetime.
        to_entered_datetime (datetime or None): End time for entered datetime.
        next (StockNode or None): Pointer to the next node in the circular linked list.
    """
    
    def __init__(self, ticker, date_index, option_type, min_overpriced, min_oi):
        """
        Initializes a StockNode instance.

        Args:
            ticker (str): Ticker symbol of the stock.
            date_index (int): Date index for the option expiration.
            option_type (str): Type of option ('call' or 'put').
            min_overpriced (float): Minimum overpriced threshold.
            min_oi (float): Minimum open interest.
        """
        self.ticker = ticker
        self.date_index = date_index
        self.option_type = option_type
        self.min_overpriced = min_overpriced
        self.min_oi = min_oi
        self.q = 0.0
        self.trade_state = TradeState.NOT_IN_POSITION
        self.option_date = None
        self.expiration_time = None
        self.from_entered_datetime = None
        self.to_entered_datetime = None
        self.next = None

    def set_q(self, q_value):
        """
        Sets the dividend yield (q) for the stock.

        Args:
            q_value (float): The dividend yield value to be set.
        """
        self.q = q_value

    def set_trade_state(self, trade_state_value):
        """
        Sets the trade state for the stock.

        Args:
            trade_state_value (TradeState): The trade state to be set.
        
        Raises:
            ValueError: If the provided trade state is not a valid TradeState enum.
        """
        if isinstance(trade_state_value, TradeState):
            self.trade_state = trade_state_value
        else:
            raise ValueError("Invalid trade state. Must be a TradeState enum value.")

    def set_option_date(self, option_date_value):
        """
        Sets the option date for the stock.

        Args:
            option_date_value (datetime): The option date to be set.
        """
        self.option_date = option_date_value

    def set_expiration_time(self, expiration_time_value):
        """
        Sets the expiration time for the stock.

        Args:
            expiration_time_value (datetime): The expiration time to be set.
        """
        self.expiration_time = expiration_time_value

    def set_from_entered_datetime(self, from_entered_datetime_value):
        """
        Sets the 'from entered' datetime for the stock.

        Args:
            from_entered_datetime_value (datetime): The 'from entered' datetime to be set.
        """
        self.from_entered_datetime = from_entered_datetime_value

    def set_to_entered_datetime(self, to_entered_datetime_value):
        """
        Sets the 'to entered' datetime for the stock.

        Args:
            to_entered_datetime_value (datetime): The 'to entered' datetime to be set.
        """
        self.to_entered_datetime = to_entered_datetime_value

class CircularLinkedList:
    """
    Circular linked list to store stock nodes.
    
    Attributes:
        head (StockNode or None): Head node of the circular linked list.
    """
    
    def __init__(self):
        """Initializes an empty CircularLinkedList."""
        self.head = None

    def append(self, stock_data):
        """
        Appends a new StockNode to the circular linked list.

        Args:
            stock_data (dict): Dictionary containing the stock data to be added.
        """
        new_node = StockNode(**stock_data)
        if not self.head:
            self.head = new_node
            new_node.next = self.head
        else:
            current = self.head
            while current.next != self.head:
                current = current.next
            current.next = new_node
            new_node.next = self.head

def load_json_file(filename):
    """
    Loads stock data from a JSON file and returns it as a circular linked list.

    Args:
        filename (str): Path to the JSON file containing stock data.

    Returns:
        CircularLinkedList: Circular linked list containing the loaded stock data.
    """
    with open(filename, 'r') as file:
        stocks_data = json.load(file)

    stocks_list = CircularLinkedList()
    for stock in stocks_data:
        stocks_list.append(stock)

    return stocks_list
