import numpy as np
from numba import njit

@njit
def filter_strikes(x, S, num_stdev=1.25, two_sigma_move=False):
    """
    Filter strike prices around the underlying asset's price.

    Args:
        x (array-like): Array of strike prices.
        S (float): Current underlying price.
        num_stdev (float, optional): Number of standard deviations for filtering. Defaults to 1.25.
        two_sigma_move (bool, optional): Adjust upper bound for a 2-sigma move. Defaults to False.

    Returns:
        array-like: Filtered array of strike prices within the specified range.
    """
    stdev = np.std(x)
    lower_bound = S - num_stdev * stdev
    upper_bound = S + num_stdev * stdev

    if two_sigma_move:
        upper_bound = S + 2 * stdev

    return x[(x >= lower_bound) & (x <= upper_bound)]

def filter_by_bid_price(sorted_data, filtered_strikes):
    """
    Filter sorted strike data by ensuring strikes are in filtered_strikes and bid prices are not zero.

    Args:
        sorted_data (dict): Dictionary containing strike prices and their corresponding price data.
        filtered_strikes (array-like): Array of filtered strike prices.

    Returns:
        dict: Filtered dictionary containing only strikes in filtered_strikes with non-zero bid prices.
    """
    return {strike: prices for strike, prices in sorted_data.items() if strike in filtered_strikes and prices['bid'] != 0.0}

def filter_by_mid_iv(sorted_data, min_mid_iv=0.005):
    """
    Filter sorted strike data by ensuring mid IV is greater than a minimum threshold.

    Args:
        sorted_data (dict): Dictionary containing strike prices and their corresponding price data.
        min_mid_iv (float, optional): Minimum threshold for mid implied volatility (mid_IV). Defaults to 0.005.

    Returns:
        dict: Filtered dictionary containing only strikes where mid_IV is greater than the minimum threshold.
    """
    return {strike: prices for strike, prices in sorted_data.items() if prices['mid_IV'] > min_mid_iv}
