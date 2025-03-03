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

def get_price_for_ticker(ticker: str) -> Dict[str, Any]:
    """
    Get the current price for a ticker symbol.
    
    Args:
        ticker (str): Ticker symbol (e.g., 'AAPL')
        
    Returns:
        Dict with price and error information
    """
    if not ticker:
        return {"price": None, "error": "No ticker provided", "success": False}
    
    logger.info(f"Getting price for ticker: {ticker}")
    try:
        ticker_obj = yf.Ticker(ticker)
        
        # Try different approaches to get the price
        # Method 1: Try info.currentPrice - most reliable but slower
        try:
            info = ticker_obj.info
            if 'currentPrice' in info and info['currentPrice'] is not None:
                return {
                    "price": float(info['currentPrice']),
                    "error": None,
                    "success": True
                }
            if 'regularMarketPrice' in info and info['regularMarketPrice'] is not None:
                return {
                    "price": float(info['regularMarketPrice']),
                    "error": None,
                    "success": True
                }
        except Exception as e:
            logger.warning(f"Error getting info price for {ticker}: {str(e)}")
        
        # Method 2: Try fast_info (newer versions of yfinance)
        try:
            if hasattr(ticker_obj, 'fast_info'):
                price = ticker_obj.fast_info.get('last_price') or ticker_obj.fast_info.get('regularMarketPrice')
                if price is not None:
                    return {
                        "price": float(price),
                        "error": None,
                        "success": True
                    }
        except Exception as e:
            logger.warning(f"Error getting fast_info price for {ticker}: {str(e)}")
        
        # Method 3: Fallback to historical data
        try:
            data = ticker_obj.history(period="1d")
            if not data.empty and 'Close' in data.columns:
                return {
                    "price": float(data['Close'].iloc[-1]),
                    "error": None,
                    "success": True
                }
        except Exception as e:
            logger.warning(f"Error getting historical price for {ticker}: {str(e)}")
        
        logger.warning(f"All methods failed to get price for {ticker}")
        return {"price": None, "error": "All price fetch methods failed", "success": False}
    except Exception as e:
        logger.error(f"Error getting price data for {ticker}: {str(e)}")
        return {"price": None, "error": str(e), "success": False}

def get_isin_data(isin: str) -> Dict[str, Any]:
    """
    Get stock data for a given ISIN or ticker
    
    Args:
        isin (str): ISIN code (e.g., 'US0378331005') or ticker symbol
        
    Returns:
        Dict[str, Any]: Dictionary containing ISIN/ticker information
    """
    logger.info(f"Processing identifier: {isin}")
    
    # Initialize variables
    price = None
    ticker = None
    modified_identifier = None
    success = False
    error_message = None
    tried_crypto_format = False
    
    try:
        # Step 1: Try standard approach with original identifier
        try:
            ticker = find_ticker_for_isin(isin)
            if ticker:
                price_result = get_price_for_ticker(ticker)
                price = price_result.get("price")
                if price is not None:
                    success = True
                else:
                    error_message = price_result.get("error", "No price data available")
        except Exception as e:
            error_message = str(e)
            logger.warning(f"Standard approach failed for {isin}: {error_message}")
        
        # Step 2: If standard approach failed AND identifier is likely a crypto symbol,
        # try appending -USD
        if (not success) and (len(isin) < 12):
            tried_crypto_format = True
            crypto_identifier = f"{isin}-USD"
            logger.info(f"🔄 Trying crypto format: {crypto_identifier}")
            
            try:
                # Try to get price with the modified identifier
                price_result = get_price_for_ticker(crypto_identifier)
                crypto_price = price_result.get("price")
                
                # If successful, use this price and modified identifier
                if crypto_price is not None:
                    price = crypto_price
                    ticker = crypto_identifier
                    modified_identifier = crypto_identifier
                    success = True
                    logger.info(f"✅ Crypto format successful for {isin}! Using {crypto_identifier} with price {price}")
                else:
                    error_message = price_result.get("error", "No price data available for crypto format")
                    logger.warning(f"Crypto format failed for {isin}: {error_message}")
            except Exception as e:
                error_message = str(e)
                logger.warning(f"Error trying crypto format for {isin}: {error_message}")
        
        # Prepare result
        result = {
            'success': success,
            'isin': isin,
            'ticker': ticker,
            'price': price,
            'currency': 'USD',  # Default currency
            'price_eur': price,  # Assuming 1:1 for simplicity
            'status': 'processed' if success else 'failed',
            'error': error_message,
            'timestamp': datetime.now().isoformat(),
            'tried_crypto_format': tried_crypto_format
        }
        
        # Add modified_identifier if applicable 
        if modified_identifier:
            result['modified_identifier'] = modified_identifier
            
        # Log appropriate message based on result
        if result['success']:
            logger.info(f"Successfully retrieved price {price} for {isin} (ticker: {ticker})")
        else:
            logger.warning(f"Failed to retrieve valid data for {isin}: ticker={ticker}, price={price}, error={error_message}")
            
        return result
            
    except Exception as e:
        logger.error(f"Error processing identifier {isin}: {str(e)}")
        return {
            'success': False,
            'isin': isin,
            'error': str(e),
            'status': 'error',
            'timestamp': datetime.now().isoformat(),
            'tried_crypto_format': tried_crypto_format
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
    
    # Get data using our enhanced get_isin_data function
    result = get_isin_data(identifier)
    
    # Format return value for compatibility with expected structure
    response = {
        "success": result['success'],
        "identifier": identifier,
        "ticker": result.get('ticker'),
        "price": result.get('price'),
        "currency": result.get('currency', 'USD'),
        "price_eur": result.get('price_eur'),
        "error": result.get('error'),
        "timestamp": result.get('timestamp')
    }
    
    # Include modified identifier if present
    if 'modified_identifier' in result:
        response['modified_identifier'] = result['modified_identifier']
    
    return response