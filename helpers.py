import os
import numpy as np
from dotenv import load_dotenv
from fredapi import Fred
from interpolations import rfv_model
from models import barone_adesi_whaley_american_option_price, calculate_implied_volatility_baw

load_dotenv()

def load_config():
    """
    Load configuration from environment variables and validate them.
    
    Raises:
        ValueError: If any required environment variable is not set.
    """
    config = {
        "SCHWAB_API_KEY": os.getenv('SCHWAB_API_KEY'),
        "SCHWAB_SECRET": os.getenv('SCHWAB_SECRET'),
        "SCHWAB_CALLBACK_URL": os.getenv('SCHWAB_CALLBACK_URL'),
        "SCHWAB_ACCOUNT_HASH": os.getenv('SCHWAB_ACCOUNT_HASH'),
        "FRED_API_KEY": os.getenv('FRED_API_KEY'),
        "DRY_RUN": os.getenv('DRY_RUN', 'True').lower() in ['true', '1', 'yes'],
        "TICKER": os.getenv('TICKER'),
        "OPTION_TYPE": os.getenv('OPTION_TYPE')
    }

    for key, value in config.items():
        if value is None:
            raise ValueError(f"{key} environment variable not set")
    
    return config

def precompile_numba_functions():
    """
    Precompile Numba functions to improve performance.

    This method calls Numba-compiled functions with sample data to ensure they are precompiled,
    reducing latency during actual execution.
    """
    barone_adesi_whaley_american_option_price(100.0, 100.0, 0.05, 0.01, 1.0, 0.2, option_type='calls')
    calculate_implied_volatility_baw(0.1, 100.0, 100.0, 0.01, 0.5, option_type='calls')
    k = np.array([0.1])
    rfv_model(k, [0.1, 0.2, 0.3, 0.4, 0.5])

def get_risk_free_rate(fred_api_key):
    """
    Fetches the risk-free rate (SOFR) using the FRED API.

    Args:
        fred_api_key (str): The FRED API key.

    Returns:
        float: The calculated risk-free rate.
    """
    try:
        fred = Fred(api_key=fred_api_key)
        sofr_data = fred.get_series('SOFR')
        risk_free_rate = (sofr_data.iloc[-1] / 100)
        return risk_free_rate
    except Exception as e:
        print(f"FRED API Error: Invalid FRED API Key or failed to fetch SOFR data: {str(e)}")
        return None

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

def calculate_rmse(y_true, y_pred):
    """
    Calculate the Root Mean Squared Error (RMSE) between the observed and predicted implied volatilities.

    Args:
        x_normalized (array-like): Normalized strike prices.
        y_true (array-like): Observed implied volatilities.
        y_pred (array-like): Predicted implied volatilities from the interpolation model.

    Returns:
        float: The computed RMSE value.
    """
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
    return rmse
