import logging
import yfinance as yf
from datetime import datetime
from typing import Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def find_ticker_for_isin(isin: str) -> str:
    """
    Find ticker symbol for an ISIN using direct yfinance approach.
    """
    logger.info(f"Finding ticker for ISIN: {isin}")
    
    try:
        # Direct approach - yfinance can handle ISINs in newer versions
        ticker_obj = yf.Ticker(isin)
        
        # Check if the ticker was successfully resolved
        if hasattr(ticker_obj, 'ticker'):
            ticker = ticker_obj.ticker
            logger.info(f"Successfully mapped ISIN {isin} to ticker {ticker}")
            return ticker
        else:
            logger.warning(f"No ticker found for ISIN: {isin}")
            return None
            
    except Exception as e:
        logger.error(f"Error finding ticker for ISIN {isin}: {str(e)}")
        return None

def get_price_for_ticker(ticker: str) -> float:
    """
    Get the current price for a ticker symbol.
    
    Args:
        ticker (str): Ticker symbol (e.g., 'AAPL')
        
    Returns:
        float: Current price or None if not available
    """
    if not ticker:
        return None
    
    logger.info(f"Getting price for ticker: {ticker}")
    try:
        ticker_obj = yf.Ticker(ticker)
        
        # Try different approaches to get the price
        # Method 1: Try info.currentPrice - most reliable but slower
        try:
            info = ticker_obj.info
            if 'currentPrice' in info and info['currentPrice'] is not None:
                return float(info['currentPrice'])
            if 'regularMarketPrice' in info and info['regularMarketPrice'] is not None:
                return float(info['regularMarketPrice'])
        except Exception as e:
            logger.warning(f"Error getting info price for {ticker}: {str(e)}")
        
        # Method 2: Try fast_info (newer versions of yfinance)
        try:
            if hasattr(ticker_obj, 'fast_info'):
                price = ticker_obj.fast_info.get('last_price') or ticker_obj.fast_info.get('regularMarketPrice')
                if price is not None:
                    return float(price)
        except Exception as e:
            logger.warning(f"Error getting fast_info price for {ticker}: {str(e)}")
        
        # Method 3: Fallback to historical data
        try:
            data = ticker_obj.history(period="1d")
            if not data.empty and 'Close' in data.columns:
                return float(data['Close'].iloc[-1])
        except Exception as e:
            logger.warning(f"Error getting historical price for {ticker}: {str(e)}")
        
        logger.warning(f"All methods failed to get price for {ticker}")
        return None
    except Exception as e:
        logger.error(f"Error getting price data for {ticker}: {str(e)}")
        return None

def get_isin_data(isin: str) -> Dict[str, Any]:
    """
    Get stock data for a given ISIN
    
    Args:
        isin (str): ISIN code (e.g., 'US0378331005')
        
    Returns:
        Dict[str, Any]: Dictionary containing ISIN information
    """
    logger.info(f"Processing ISIN: {isin}")
    try:
        # Step 1: Find the ticker for this ISIN
        ticker = find_ticker_for_isin(isin)
        
        # Step 2: Get the price for this ticker
        price = None
        if ticker:
            price = get_price_for_ticker(ticker)
            
        # Step 3: Prepare result
        result = {
            'success': ticker is not None and price is not None,
            'isin': isin,
            'ticker': ticker,
            'price': price,
            'currency': 'USD',  # Default currency
            'price_eur': price,  # Assuming 1:1 for simplicity
            'status': 'processed' if (ticker and price is not None) else 'ticker_not_found' if not ticker else 'price_not_found',
            'timestamp': datetime.now().isoformat()
        }
        
        # Log appropriate message based on result
        if result['success']:
            logger.info(f"Successfully retrieved price {price} for {isin} (ticker: {ticker})")
        else:
            logger.warning(f"Failed to retrieve valid data for {isin}: ticker={ticker}, price={price}")
            
        return result
            
    except Exception as e:
        logger.error(f"Error processing ISIN {isin}: {str(e)}")
        return {
            'success': False,
            'isin': isin,
            'error': str(e),
            'status': 'error',
            'timestamp': datetime.now().isoformat()
        }

def get_yfinance_info(identifier: str) -> Dict[str, Any]:
    """
    Get stock information for a given identifier (ticker or ISIN).
    
    Args:
        identifier (str): Stock identifier (ticker or ISIN)
        
    Returns:
        Dict[str, Any]: Dictionary containing stock information
    """
    logger.info(f"Fetching data for identifier={identifier!r}")
    
    # Just use get_isin_data for consistency - it handles both ISINs and tickers
    result = get_isin_data(identifier)
    
    # Format return value for compatibility with expected structure
    return {
        "success": result['success'],
        "identifier": identifier,
        "ticker": result.get('ticker'),
        "price": result.get('price'),
        "currency": result.get('currency', 'USD'),
        "price_eur": result.get('price_eur'),
        "error": result.get('error'),
        "timestamp": result.get('timestamp')
    }