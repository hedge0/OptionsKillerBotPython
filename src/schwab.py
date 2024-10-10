import httpx
from datetime import datetime
from schwab.auth import easy_client
from schwab.orders.equities import equity_buy_market, equity_sell_short_market, equity_sell_market, equity_buy_to_cover_market

from models import calculate_delta, calculate_implied_volatility_baw

client = None

