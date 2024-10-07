import numpy as np
from math import log, sqrt, exp
from numba import njit

@njit
def erf(x):
    """
    Approximation of the error function (erf) using a high-precision method.

    Parameters:
    - x (float): The input value.

    Returns:
    - float: The calculated error function value.
    """
    a1, a2, a3, a4, a5 = (
        0.254829592,
        -0.284496736,
        1.421413741,
        -1.453152027,
        1.061405429,
    )
    p = 0.3275911

    sign = 1 if x >= 0 else -1
    x = abs(x)
    
    t = 1.0 / (1.0 + p * x)
    y = 1.0 - (((((a5 * t + a4) * t + a3) * t + a2) * t + a1) * t * np.exp(-x * x))

    return sign * y

@njit
def normal_cdf(x):
    """
    Approximation of the cumulative distribution function (CDF) for a standard normal distribution.

    Parameters:
    - x (float): The input value.

    Returns:
    - float: The CDF value.
    """
    return 0.5 * (1.0 + erf(x / np.sqrt(2.0)))

@njit
def barone_adesi_whaley_american_option_price(S, K, T, r, sigma, q=0.0, option_type='calls'):
    """
    Calculate the price of an American option using the Barone-Adesi Whaley model with dividends.

    Args:
        S (float): Current stock price.
        K (float): Strike price of the option.
        T (float): Time to expiration in years.
        r (float): Risk-free interest rate.
        sigma (float): Implied volatility.
        q (float, optional): Continuous dividend yield. Defaults to 0.0.
        option_type (str, optional): Type of option ('calls' or 'puts'). Defaults to 'calls'.

    Returns:
        float: The calculated option price.
    """
    M = 2 * (r - q) / sigma**2
    n = 2 * (r - q - 0.5 * sigma**2) / sigma**2
    q2 = (-(n - 1) - sqrt((n - 1)**2 + 4 * M)) / 2
    
    d1 = (log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    
    if option_type == 'calls':
        european_price = S * exp(-q * T) * normal_cdf(d1) - K * exp(-r * T) * normal_cdf(d2)
        if q >= r:
            return european_price
        if q2 < 0:
            return european_price
        S_critical = K / (1 - 1 / q2)
        if S >= S_critical:
            return S - K
        else:
            A2 = (S_critical - K) * (S_critical**-q2)
            return european_price + A2 * (S / S_critical)**q2
    
    elif option_type == 'puts':
        european_price = K * exp(-r * T) * normal_cdf(-d2) - S * exp(-q * T) * normal_cdf(-d1)
        if q >= r:
            return european_price
        if q2 < 0:
            return european_price
        S_critical = K / (1 + 1 / q2)
        if S <= S_critical:
            return K - S
        else:
            A2 = (K - S_critical) * (S_critical**-q2)
            return european_price + A2 * (S / S_critical)**q2
    
    else:
        raise ValueError("option_type must be 'calls' or 'puts'.")

@njit
def calculate_implied_volatility_baw(option_price, S, K, r, T, q=0.0, option_type='calls', max_iterations=100, tolerance=1e-8):
    """
    Calculate the implied volatility using the Barone-Adesi Whaley model with dividends.

    Parameters:
    - option_price (float): Observed option price (mid-price).
    - S (float): Current stock price.
    - K (float): Strike price of the option.
    - r (float): Risk-free interest rate.
    - T (float): Time to expiration in years.
    - q (float, optional): Continuous dividend yield. Defaults to 0.0.
    - option_type (str, optional): Type of option ('calls' or 'puts'). Defaults to 'calls'.
    - max_iterations (int, optional): Maximum number of iterations for the bisection method. Defaults to 100.
    - tolerance (float, optional): Convergence tolerance. Defaults to 1e-8.

    Returns:
    - float: The implied volatility.
    """
    lower_vol = 1e-5
    upper_vol = 10.0

    for i in range(max_iterations):
        mid_vol = (lower_vol + upper_vol) / 2
        price = barone_adesi_whaley_american_option_price(S, K, T, r, mid_vol, q, option_type)

        if abs(price - option_price) < tolerance:
            return mid_vol

        if price > option_price:
            upper_vol = mid_vol
        else:
            lower_vol = mid_vol

        if upper_vol - lower_vol < tolerance:
            break

    return mid_vol
