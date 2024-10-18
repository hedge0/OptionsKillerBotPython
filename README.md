# Options Killer Bot Python

This is a Python-based trading bot for options trading using Schwab's API and FRED API. The bot handles trade logic, delta hedging, option mispricing, and more.

## Requirements

Make sure you have the following Python libraries installed:

- python-dotenv
- schwab-py
- fredapi
- numba
- httpx
- scikit-learn
- scipy
- nest-asyncio

You can install these libraries by running the following command:

`pip install python-dotenv schwab-py fredapi numba httpx scikit-learn scipy nest-asyncio`

## Configuration

1. Create a `.env` file in the root directory with the following structure:
 ```env
    SCHWAB_API_KEY=your_schwab_api_key 
    SCHWAB_SECRET=your_schwab_secret 
    SCHWAB_CALLBACK_URL=your_callback_url 
    SCHWAB_ACCOUNT_HASH=your_account_hash 
    FRED_API_KEY=your_fred_api_key 
    DRY_RUN=false 
    TIME_TO_REST=2
```

2. Create a `stocks.json` file in the root directory with the following structure:
 ```json
[   { "ticker": "JPM", "date_index": 0, "option_type": "calls", "min_overpriced": 0.14, "min_oi": 400.0 } ]
```

## Usage

1. Clone the repository and navigate to the project folder:

`git clone https://github.com/hedge0/OptionsKillerBotPython.git cd OptionsKillerBotPython`

2. Run the bot using the following command:

`python app.py`

## Features

- **Trade Execution**: Executes option trades based on mispricing and open interest.
- **Delta Hedging**: Automatically hedges delta exposure by buying or selling shares.
- **Option Chain Filtering**: Filters option chains based on bid price, implied volatility, and open interest.
- **Model Fitting**: Fits various models (RBF, RFV) to the implied volatility data to find the best fit for pricing.

## License

This project is licensed under an All Rights Reserved (ARR) license.
