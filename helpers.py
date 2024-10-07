import os
from dotenv import load_dotenv
from fredapi import Fred
from models import calculate_delta, calculate_implied_volatility_baw

# Load environment variables from .env file
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
        "DRY_RUN": os.getenv('DRY_RUN', 'True').lower() in ['true', '1', 'yes']
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
    calculate_implied_volatility_baw(0.1, 100.0, 100.0, 0.01, 0.5, option_type='calls')
    calculate_delta(100.0, 100.0, 0.5, 0.01, 0.2, option_type='calls')

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
