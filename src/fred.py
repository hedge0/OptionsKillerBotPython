import logging
from fredapi import Fred

def fetch_risk_free_rate(fred_api_key):
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
        logging.error(f"FRED API Error: Invalid FRED API Key or failed to fetch SOFR data: {str(e)}")
        return None
    