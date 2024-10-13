from enum import Enum

class TradeState(Enum):
    """
    Enum representing different trade states.

    Attributes:
        NOT_IN_POSITION (str): Indicates that the stock is not currently in a position.
        PENDING (str): Indicates that the stock trade is pending.
        IN_POSITION (str): Indicates that the stock is currently in a position.
    """
    
    NOT_IN_POSITION = "not in position"
    PENDING = "pending"
    IN_POSITION = "in position"
