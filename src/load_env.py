import os
from dotenv import load_dotenv

load_dotenv()

def load_env_file():
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