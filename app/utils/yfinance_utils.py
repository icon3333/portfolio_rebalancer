import yfinance as yf
from typing import Dict, Any, Optional, Tuple, List
import logging
import requests
import pandas as pd
import time
import warnings
from ratelimit import limits, sleep_and_retry

# Suppress yfinance warnings
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=UserWarning)

# Configure logger
logger = logging.getLogger(__name__)

# Rate limiting configuration
CALLS_PER_SECOND = 2
PERIOD = 1  # seconds

@sleep_and_retry
@limits(calls=CALLS_PER_SECOND, period=PERIOD)
def _rate_limited_call():
    """Helper function to implement rate limiting"""
    pass

def isin_to_ticker(identifier_list: List[str]) -> Dict[str, str]:
    """
    Convert a list of identifiers (ISINs or crypto tickers) to ticker symbols using yfinance.
    Returns {identifier: Ticker or error message}.
    """
    logger.info("Starting identifier to Ticker conversion.")
    results = {}
    
    for identifier in identifier_list:
        logger.debug(f"Processing identifier: {identifier}")
        
        try:
            # Check if it's a crypto ticker (assuming they don't contain dots and are shorter than 12 chars)
            if len(identifier) < 12 and '.' not in identifier:
                # Append -USD for crypto tickers if not already present
                ticker = f"{identifier}-USD" if not identifier.endswith("-USD") else identifier
                logger.info(f"Processed crypto ticker: {identifier} -> {ticker}")
                results[identifier] = ticker
                continue
            
            # Handle ISIN (should be 12 characters)
            if len(identifier) != 12:
                logger.warning(f"Invalid ISIN length for {identifier}. Expected 12 characters.")
                results[identifier] = "Invalid ISIN length."
                continue

            # Create a Ticker object and get the ticker symbol
            ticker_obj = yf.Ticker(identifier)
            ticker = ticker_obj.ticker if hasattr(ticker_obj, 'ticker') else None
            
            if ticker:
                logger.info(f"Successfully mapped {identifier} to {ticker}")
                results[identifier] = ticker
            else:
                logger.warning(f"No ticker found for identifier: {identifier}")
                results[identifier] = "No ticker found"

        except Exception as e:
            logger.error(f"Error converting identifier {identifier}: {str(e)}")
            results[identifier] = f"Error converting identifier {identifier}: {str(e)}"

    logger.info(f"Completed identifier to Ticker conversion. Successful conversions: {sum(1 for v in results.values() if not isinstance(v, str) or not v.startswith(('Error', 'No ', 'Invalid')))}")
    return results

def get_stock_price_and_currency(identifier: str) -> Tuple[Optional[float], Optional[str], Optional[float]]:
    """
    Get the latest stock price, currency, and EUR-converted price for a given identifier
    
    Args:
        identifier (str): ISIN or stock symbol
        
    Returns:
        Tuple[Optional[float], Optional[str], Optional[float]]: 
            - Original price in local currency
            - Currency code
            - Price in EUR
    """
    logger.info(f"Getting stock price and currency for symbol: {identifier}")
    
    try:
        # Use the improved price fetching from batch_processing
        from app.utils.batch_processing import find_ticker_for_isin, get_price_for_ticker
        
        # Convert ISIN to ticker if needed
        ticker = find_ticker_for_isin(identifier)
        if not ticker:
            logger.error(f"Failed to get ticker for {identifier}")
            return None, None, None
            
        # Get the latest price
        price = get_price_for_ticker(ticker)
        if price is None:
            logger.warning(f"No valid price found for {identifier}")
            return None, None, None
            
        # Get currency information
        ticker_info = yf.Ticker(ticker).info
        currency = ticker_info.get('currency', None)
        
        if currency:
            # Convert to EUR if needed
            eur_rate = _get_eur_rate(currency)
            price_eur = price * eur_rate if eur_rate is not None else None
            
            logger.info(f"Successfully got price for {identifier}: {price} {currency} ({price_eur} EUR)")
            return float(price), currency, price_eur
        else:
            logger.warning(f"No currency information found for {identifier}")
            return float(price), None, None
            
    except Exception as e:
        logger.error(f"Failed to get price for {identifier}: {str(e)}")
        return None, None, None

def batch_get_stock_prices(identifiers: List[str]) -> Dict[str, Tuple[Optional[float], Optional[str], Optional[float]]]:
    """
    Get stock prices, currencies, and EUR prices for multiple identifiers in batch
    
    Args:
        identifiers (List[str]): List of ISINs or stock symbols
        
    Returns:
        Dict[str, Tuple[Optional[float], Optional[str], Optional[float]]]: 
            Dictionary mapping identifiers to tuples of (price, currency, price_eur)
    """
    logger.info(f"Batch getting stock prices for {len(identifiers)} identifiers")
    results = {}
    
    # Process in smaller batches to avoid rate limits
    batch_size = 5
    
    for i in range(0, len(identifiers), batch_size):
        batch = identifiers[i:i + batch_size]
        
        # Process each identifier in the batch
        for identifier in batch:
            try:
                price, currency, price_eur = get_stock_price_and_currency(identifier)
                results[identifier] = (price, currency, price_eur)
            except Exception as e:
                logger.error(f"Error getting price for {identifier}: {str(e)}")
                results[identifier] = (None, None, None)
            
        # Add delay between batches to avoid overwhelming the API
        if i + batch_size < len(identifiers):
            time.sleep(2)
            
    return results

def _get_eur_rate(currency: str) -> Optional[float]:
    """
    Get EUR conversion rate for a given currency
    
    Args:
        currency (str): Source currency code (e.g., 'USD', 'GBP')
        
    Returns:
        Optional[float]: Conversion rate to EUR if available, None otherwise
    """
    if currency == 'EUR':
        return 1.0
        
    max_retries = 3
    retry_delay = 1  # seconds
    
    for attempt in range(max_retries):
        try:
            _rate_limited_call()
            eur_ticker = f"{currency}EUR=X"
            eur_data = yf.Ticker(eur_ticker)
            eur_history = eur_data.history(period='5d')
            
            if not eur_history.empty:
                rate = eur_history['Close'].iloc[-1]
                if pd.isna(rate) and len(eur_history) > 1:
                    rate = eur_history['Close'].iloc[-2]
                
                if not pd.isna(rate):
                    return float(rate)
                    
            logger.warning(f"No valid exchange rate found for {currency} to EUR (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                
        except Exception as e:
            logger.error(f"Error getting exchange rate for {currency} to EUR (attempt {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                
    return None

def get_stock_info(identifier: str) -> Dict[str, Any]:
    """
    Get detailed information about a stock using yfinance
    
    Args:
        identifier (str): ISIN or stock symbol
        
    Returns:
        Dict[str, Any]: Dictionary containing stock information
    """
    try:
        # Convert ISIN to ticker if needed
        ticker_result = isin_to_ticker([identifier])
        ticker = ticker_result[identifier]
        
        if isinstance(ticker, str) and (ticker.startswith("Error") or ticker.startswith("No ") or ticker.startswith("Invalid")):
            logger.error(f"Failed to get ticker for {identifier}: {ticker}")
            return {}
            
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # Extract relevant information
        return {
            'symbol': info.get('symbol'),
            'shortName': info.get('shortName'),
            'longName': info.get('longName'),
            'currency': info.get('currency'),
            'exchange': info.get('exchange'),
            'industry': info.get('industry'),
            'sector': info.get('sector'),
            'country': info.get('country'),
            'marketCap': info.get('marketCap'),
            'volume': info.get('volume'),
            'website': info.get('website'),
        }
        
    except Exception as e:
        logger.error(f"Error getting stock info for {identifier}: {str(e)}")
        return {}