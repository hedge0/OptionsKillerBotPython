import numpy as np
from datetime import datetime, time, timedelta

from src.interpolations import rfv_model
from src.models import barone_adesi_whaley_american_option_price, calculate_delta, calculate_implied_volatility_baw

def is_nyse_open():
    """
    Check if the New York Stock Exchange (NYSE) is currently open.
    
    The NYSE operates Monday through Friday from 9:30 AM to 3:50 PM EST.
    This function checks if the current time falls within the trading hours 
    and excludes weekends (Saturday and Sunday).
    
    Returns:
        bool: True if NYSE is currently open, False otherwise.
    """
    now = datetime.now()
    if now.weekday() >= 5:
        return False

    open_time = time(9, 30)
    close_time = time(15, 50)

    current_time = now.time()

    return open_time <= current_time < close_time

def should_wait_for_market_open():
    """
    Check if the current time is before the market opens on a weekday.

    This function determines if the current time is before 9:30 AM on a weekday 
    (Monday to Friday). If true, it indicates that the code should wait until the market opens.

    Returns:
        bool: True if the current time is before 9:30 AM on a weekday, False otherwise.
    """
    now = datetime.now()
    if now.weekday() < 5 and now.time() < time(9, 30):
        return True
    return False

def calculate_time_to_wait_for_market_open():
    """
    Calculate the time to wait until the market opens at 9:30 AM on the current day.

    This function computes the time difference between the current time and 9:30 AM 
    on the current day, then adds an additional 15 seconds to the wait time.

    Returns:
        timedelta: The time duration to wait until market opens, plus 15 seconds.
    """
    market_open_time = datetime.combine(datetime.now().date(), time(9, 30))
    time_to_wait = (market_open_time - datetime.now()) + timedelta(seconds=15)
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
