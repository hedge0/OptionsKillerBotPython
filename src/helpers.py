import os
import csv
import numpy as np
from datetime import datetime, time
from dotenv import load_dotenv
from fredapi import Fred
from src.schwab import cancel_order, fetch_account_data, fetch_dividend_data, fetch_option_expiration_chain, fetch_orders_for_account
from src.interpolations import rfv_model
from src.models import barone_adesi_whaley_american_option_price, calculate_delta, calculate_implied_volatility_baw

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
        "DATE_INDEX": int(os.getenv('DATE_INDEX', 0)),
        "OPTION_TYPE": os.getenv('OPTION_TYPE'),
        "TIME_TO_REST": int(os.getenv('TIME_TO_REST', 1)),
        "MIN_OI": float(os.getenv('MIN_OI', 0.0)),
        "MIN_UNDERPRICED": float(os.getenv('MIN_UNDERPRICED', 0.50))
    }

    for key, value in config.items():
        if value is None:
            raise ValueError(f"{key} environment variable not set")
    
    return config

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

def write_csv(filename, x_vals, y_vals):
    """
    Write x and y values to a CSV file.
    
    Args:
        filename (str): The name of the CSV file.
        x_vals (np.array): Array of x values (strikes).
        y_vals (np.array): Array of y values (implied volatilities).
    """
    with open(filename, mode='w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(["Strike", "IV"])
        for x, y in zip(x_vals, y_vals):
            writer.writerow([x, y])

    print(f"Data written to {filename}")

async def get_option_expiration_date(ticker, date_index):
    """
    Fetch the option expiration date for a given ticker and date index.

    Args:
        ticker (str): The ticker symbol of the underlying security.
        date_index (int): The index to select the expiration date from the list.

    Returns:
        str: The selected expiration date if successful, None otherwise.
    """
    expirations = await fetch_option_expiration_chain(ticker)
    
    if expirations is not None and expirations.get("expirationList"):
        expiration_dates_list = [expiration["expirationDate"] for expiration in expirations["expirationList"]]
        return expiration_dates_list[date_index] if date_index < len(expiration_dates_list) else None
    else:
        print(f"Validation Failed: Invalid ticker symbol: {ticker}. Please use a valid ticker.")
        return None

async def get_dividend_yield(ticker):
    """
    Fetch and parse the dividend yield for a given ticker.

    Args:
        ticker (str): The ticker symbol of the underlying security.

    Returns:
        float: The dividend yield as a decimal (e.g., 0.02 for 2%), or None if an error occurs.
    """
    div_data = await fetch_dividend_data(ticker)
    
    if div_data and ticker in div_data:
        try:
            return float(div_data[ticker]["fundamental"]["divYield"]) / 100
        except (KeyError, ValueError) as e:
            print(f"Error parsing dividend yield for {ticker}: {e}")
            return None
    else:
        print(f"Invalid data for {ticker}.")
        return None

async def cancel_existing_orders(ticker, account_hash, from_date, to_date):
    """
    Cancel existing orders for the specified ticker.

    Args:
        ticker (str): The ticker symbol of the underlying security.
        account_hash (str): The account identifier for order management.
        from_date (datetime): The start date for filtering orders.
        to_date (datetime): The end date for filtering orders.

    Returns:
        None
    """
    order_data = await fetch_orders_for_account(account_hash, from_date, to_date)

    if not order_data:
        return

    for order in order_data:
        asset_type = order["orderLegCollection"][0]["instrument"]["assetType"]
        order_id = order["orderId"]

        if asset_type == "EQUITY" and order["orderLegCollection"][0]["instrument"]["symbol"] == ticker:
            await cancel_order(order_id, account_hash)
        elif asset_type == "OPTION" and order["orderLegCollection"][0]["instrument"]["underlyingSymbol"] == ticker:
            await cancel_order(order_id, account_hash)

async def get_account_positions(ticker, account_hash):
    """
    Fetch the account positions for the specified ticker.

    Args:
        ticker (str): The ticker symbol of the underlying security.
        account_hash (str): The account identifier for retrieving positions.

    Returns:
        tuple: A tuple containing:
            - streamers_tickers (list): A list of option ticker symbols.
            - options (dict): Dictionary of options positions.
            - total_shares (int): The total number of shares held for the ticker.
    """
    account_data = await fetch_account_data(account_hash)
    if not account_data:
        return [], {}, 0

    streamers_tickers = [
        position["instrument"]["symbol"]
        for position in account_data["securitiesAccount"].get("positions", [])
        if position["instrument"]["assetType"] == "OPTION" and position["instrument"]["underlyingSymbol"] == ticker
    ]

    options = {
        position["instrument"]["symbol"]: position
        for position in account_data["securitiesAccount"].get("positions", [])
        if position["instrument"]["assetType"] == "OPTION" and position["instrument"]["underlyingSymbol"] == ticker
    }

    total_shares = sum(
        round(float(position["longQuantity"]) - float(position["shortQuantity"]))
        for position in account_data["securitiesAccount"].get("positions", [])
        if position["instrument"]["assetType"] == "EQUITY" and position["instrument"]["symbol"] == ticker
    )

    return streamers_tickers, options, total_shares
