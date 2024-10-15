import numpy as np
import pytz
from datetime import datetime, time, timedelta

from src.filters import filter_strikes
from src.interpolations import objective_function, rfv_model
from src.models import barone_adesi_whaley_american_option_price, calculate_delta, calculate_implied_volatility_baw

ny_timezone = pytz.timezone("America/New_York")

def is_nyse_open():
    """
    Check if the New York Stock Exchange (NYSE) is currently open.
    
    The NYSE operates Monday through Friday from 9:30 AM to 3:50 PM EST.
    This function checks if the current time falls within the trading hours 
    in EST and excludes weekends (Saturday and Sunday).
    
    Returns:
        bool: True if NYSE is currently open, False otherwise.
    """
    now_utc = datetime.now(pytz.utc)
    now_ny = now_utc.astimezone(ny_timezone)
    
    if now_ny.weekday() >= 5:
        return False

    open_time = time(9, 30)
    close_time = time(15, 50)

    current_time = now_ny.time()

    return open_time <= current_time < close_time

def should_wait_for_market_open():
    """
    Check if the current time is before the market opens in EST on a weekday.

    Returns:
        bool: True if the current time is before 9:30 AM EST on a weekday, False otherwise.
    """
    now_utc = datetime.now(pytz.utc)
    now_ny = now_utc.astimezone(ny_timezone)

    if now_ny.weekday() < 5 and now_ny.time() < time(9, 30):
        return True
    return False

def calculate_time_to_wait_for_market_open():
    """
    Calculate the time to wait until the market opens at 9:30 AM EST on the current day.

    Returns:
        timedelta: The time duration to wait until market opens, plus 15 seconds.
    """
    now_utc = datetime.now(pytz.utc)
    now_ny = now_utc.astimezone(ny_timezone)

    market_open_time = datetime.combine(now_ny.date(), time(9, 30))
    market_open_time = ny_timezone.localize(market_open_time)

    time_to_wait = (market_open_time - now_ny) + timedelta(seconds=15)
    return time_to_wait

def precompile_numba_functions():
    """
    Precompile Numba functions to improve performance.

    This method calls Numba-compiled functions with sample data to ensure they are precompiled,
    reducing latency during actual execution.
    """
    barone_adesi_whaley_american_option_price(100.0, 100.0, 0.05, 0.01, 1.0, 0.2, option_type='calls')
    calculate_implied_volatility_baw(0.1, 100.0, 100.0, 0.01, 0.5, option_type='calls')
    calculate_delta(100.0, 100.0, 0.5, 0.01, 0.2, option_type='calls')
    k = np.array([0.1])
    rfv_model(k, [0.1, 0.2, 0.3, 0.4, 0.5])
    y_mid = np.array([0.15, 0.18, 0.2, 0.22, 0.25])
    y_bid = np.array([0.14, 0.17, 0.19, 0.21, 0.24])
    y_ask = np.array([0.16, 0.19, 0.21, 0.23, 0.26])
    params = [0.1, 0.2, 0.3, 0.4, 0.5]
    objective_function(params, k, y_mid, y_bid, y_ask, rfv_model)
    strikes = np.array([90, 95, 100, 105, 110])
    filter_strikes(strikes, 100.0, num_stdev=1.25)
    