import yfinance as yf
from typing import Dict, Any, Optional, Tuple, List
import logging
import requests
import pandas as pd
import time
from ratelimit import limits, sleep_and_retry

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
                    
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
                
            return None
                    
        except Exception as e:
            if '404' in str(e):
                logger.info(f"EUR rate not available for {currency}")
                return None
            else:
                logger.error(f"Failed to get EUR rate for {currency} (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return None

def isin_to_symbol(isin: str) -> Optional[str]:
    """
    Convert ISIN to stock symbol. This is a simple mapping for now.
    In a real implementation, you would need to use a proper ISIN to symbol mapping service.
    
    Args:
        isin (str): ISIN code
        
    Returns:
        Optional[str]: Stock symbol if found, None otherwise
    """
    # Simple mapping for common stocks
    isin_to_symbol_map = {
        'US88579Y1010': 'MMM',  # 3M Company
    }
    return isin_to_symbol_map.get(isin)

def get_stock_price_and_currency(symbol: str) -> Tuple[Optional[float], Optional[str], Optional[float]]:
    """
    Get the latest stock price, currency, and EUR-converted price for a given symbol
    
    Args:
        symbol (str): Stock symbol (e.g., 'MMM')
        
    Returns:
        Tuple[Optional[float], Optional[str], Optional[float]]: 
            - Original price in local currency
            - Currency code
            - Price in EUR
    """
    logger.info(f"Getting stock price and currency for symbol: {symbol}")
    
    max_retries = 3
    retry_delay = 1  # seconds
    
    for attempt in range(max_retries):
        try:
            _rate_limited_call()
            stock = yf.Ticker(symbol)
            
            # Get price from history
            history = stock.history(period='5d')
            if history.empty:
                logger.info(f"No price data available for {symbol}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return None, None, None
            
            # Get the most recent price
            price = history['Close'].iloc[-1]
            if pd.isna(price) and len(history) > 1:
                price = history['Close'].iloc[-2]
                
            if pd.isna(price):
                logger.warning(f"No valid price found for {symbol}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return None, None, None
                
            # Try to get currency from info
            try:
                info = stock.info
                currency = info.get('currency', None)
                logger.info(f"Got currency from yfinance for {symbol}: {currency}")
            except Exception as e:
                logger.warning(f"Failed to get currency from yfinance for {symbol}: {e}")
                currency = None
            
           
            # Handle GBp (British pence) to GBP conversion
            if currency == 'GBp':
                price = price / 100
                currency = 'GBP'
                logger.info(f"Converted GBp to GBP for {symbol}: {price} GBP")
            
            # Calculate EUR price if needed
            price_eur = price
            if currency != 'EUR':
                eur_rate = _get_eur_rate(currency)
                if eur_rate is not None:
                    price_eur = price * eur_rate
                    logger.info(f"Converted {symbol} price to EUR: {price_eur} (rate: {eur_rate})")
                else:
                    logger.warning(f"Failed to get EUR rate for {currency}")
                    return float(price), currency, None
                    
            return float(price), currency, float(price_eur)
            
        except Exception as e:
            logger.warning(f"Failed to fetch data for {symbol} (attempt {attempt + 1}/{max_retries}): {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return None, None, None

def batch_get_stock_prices(symbols: List[str]) -> Dict[str, Tuple[Optional[float], Optional[str], Optional[float]]]:
    """
    Get stock prices, currencies, and EUR prices for multiple symbols in batch
    
    Args:
        symbols (List[str]): List of stock symbols
        
    Returns:
        Dict[str, Tuple[Optional[float], Optional[str], Optional[float]]]: 
            Dictionary mapping symbols to tuples of (price, currency, price_eur)
    """
    logger.info(f"Batch getting stock prices for {len(symbols)} symbols")
    results = {}
    
    # Process in smaller batches to avoid rate limits
    batch_size = 5
    max_retries = 3
    retry_delay = 2  # seconds
    
    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        
        # Process each symbol in the batch with retries
        for symbol in batch:
            for attempt in range(max_retries):
                try:
                    _rate_limited_call()  # Ensure we respect rate limits
                    price, currency, price_eur = get_stock_price_and_currency(symbol)
                    if price is not None or attempt == max_retries - 1:
                        results[symbol] = (price, currency, price_eur)
                        break
                except Exception as e:
                    logger.error(f"Error getting price for {symbol} (attempt {attempt + 1}/{max_retries}): {str(e)}")
                    if attempt == max_retries - 1:
                        results[symbol] = (None, None, None)
                    else:
                        time.sleep(retry_delay)
            
        # Add delay between batches to avoid overwhelming the API
        if i + batch_size < len(symbols):
            time.sleep(2)
            
    return results

def get_stock_info(identifier: str) -> Dict[str, Any]:
    """
    Get detailed information about a stock using yfinance
    
    Args:
        identifier (str): ISIN or stock symbol (e.g., 'US88579Y1010' or 'MMM')
        
    Returns:
        Dict[str, Any]: Dictionary containing stock information
    """
    # Convert ISIN to symbol if needed
    symbol = isin_to_symbol(identifier)
    if not symbol:
        symbol = identifier  # Use identifier as is if no mapping found
        
    price, currency, price_eur = get_stock_price_and_currency(symbol)
    
    if price is None:
        logger.error(f"Failed to get price for {symbol}: No price data available")
        return {
            'success': False,
            'error': f"No price data available for {symbol}"
        }
    
    stock = yf.Ticker(symbol)
    
    # Then try to get additional info
    try:
        info = stock.info
        
        return {
            'success': True,
            'data': {
                'ticker': info.get('symbol'),
                'currentPrice': price,
                'currency': currency,
                'priceEUR': price_eur,
                'marketCap': info.get('marketCap'),
                'dividendYield': info.get('dividendYield'),
                'peRatio': info.get('trailingPE'),
                '52WeekHigh': info.get('fiftyTwoWeekHigh'),
                '52WeekLow': info.get('fiftyTwoWeekLow'),
                'volume': info.get('volume'),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
                'country': info.get('country'),
                'exchange': info.get('exchange'),
                'description': info.get('longBusinessSummary'),
                'website': info.get('website')
            }
        }
            
    except requests.exceptions.HTTPError as e:
        logger.warning(f"HTTP error while fetching info for {symbol}: {str(e)}")
        return {
            'success': True,
            'data': {
                'ticker': symbol,
                'currentPrice': price,
                'currency': currency,
                'priceEUR': price_eur
            }
        }
    except Exception as e:
        logger.warning(f"Failed to get info for {symbol}: {str(e)}")
        return {
            'success': True,
            'data': {
                'ticker': symbol,
                'currentPrice': price,
                'currency': currency,
                'priceEUR': price_eur
            }
        }