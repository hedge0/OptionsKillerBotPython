from enum import Enum

class TradeState(Enum):
    """
    Enum representing different trade states.

    Attributes:
        NOT_IN_POSITION (str): Indicates that the stock is not currently in a position.
        PENDING_BUY (str): Indicates that a buy trade is pending.
        PENDING_SELL (str): Indicates that a sell trade is pending.
        IN_POSITION (str): Indicates that the stock is currently in a position.
    """
    
    NOT_IN_POSITION = "not in position"
    PENDING_BUY = "pending buy"
    PENDING_SELL = "pending sell"
    IN_POSITION = "in position"
