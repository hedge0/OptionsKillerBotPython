import numpy as np
from scipy.optimize import minimize
from scipy.interpolate import RBFInterpolator
from numba import njit

@njit
def rfv_model(k, params):
    """
    RFV Model function.

    Args:
        k (float or array-like): Log-moneyness of the option.
        params (list): Parameters [a, b, c, d, e] for the RFV model.

    Returns:
        float or array-like: The RFV model value for the given log-moneyness.
    """
    a, b, c, d, e = params
    return (a + b*k + c*k**2) / (1 + d*k + e*k**2)

def rbf_model(k, y, epsilon=None):
    """
    RBF Interpolation model function.

    Args:
        k (array-like): Log-moneyness of the option.
        y (array-like): Implied volatilities corresponding to log-moneyness.
        epsilon (float, optional): Regularization parameter for RBF. Defaults to None.

    Returns:
        function: A callable function that interpolates implied volatilities for given log-moneyness.
    """
    if epsilon is None:
        epsilon = np.mean(np.diff(np.sort(k)))
    rbf = RBFInterpolator(k[:, np.newaxis], y, kernel='multiquadric', epsilon=epsilon, smoothing=0.000000000001)
    return rbf

@njit
def objective_function(params, k, y_mid, y_bid, y_ask, model):
    """
    Objective function to minimize during model fitting using WLS method.

    Args:
        params (list): Model parameters.
        k (array-like): Log-moneyness of the options.
        y_mid (array-like): Mid prices of the options.
        y_bid (array-like): Bid prices of the options.
        y_ask (array-like): Ask prices of the options.
        model (function): The volatility model to be fitted.

    Returns:
        float: The calculated objective value to be minimized.
    """
    spread = y_ask - y_bid
    epsilon = 1e-8
    weights = 1 / (spread + epsilon)
    residuals = model(k, params) - y_mid
    weighted_residuals = weights * residuals ** 2
    return np.sum(weighted_residuals)

def fit_model(x, y_mid, y_bid, y_ask, model):
    """
    Fit the chosen volatility model to the market data using WLS method.

    Args:
        x (array-like): Strikes of the options.
        y_mid (array-like): Mid prices of the options.
        y_bid (array-like): Bid prices of the options.
        y_ask (array-like): Ask prices of the options.
        model (function): The volatility model to be fitted.

    Returns:
        list: The fitted model parameters.
    """
    k = np.log(x)

    initial_guess = [0.2, 0.3, 0.1, 0.2, 0.1]
    bounds = [(None, None), (None, None), (None, None), (None, None), (None, None)]
    
    result = minimize(objective_function, initial_guess, args=(k, y_mid, y_bid, y_ask, model), method='L-BFGS-B', bounds=bounds)
    return result.x
