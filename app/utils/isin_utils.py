"""
Utility functions for handling ISIN to ticker conversions.
"""
import logging
import yfinance as yf
import warnings
import time
import pandas as pd
from typing import Dict, List, Optional, Tuple
from functools import lru_cache

# Suppress yfinance warnings
warnings.filterwarnings('ignore', category=FutureWarning)
warnings.filterwarnings('ignore', category=UserWarning)

logger = logging.getLogger(__name__)

# Rate limiting settings
REQUEST_DELAY = 2.0  # Delay between requests in seconds
MAX_RETRIES = 3     # Maximum number of retries per request
RETRY_DELAY = 5.0   # Delay between retries in seconds

def _get_ticker_info(ticker_obj, max_retries=MAX_RETRIES) -> Optional[Dict]:
    """Helper function to get ticker info with retries"""
    for attempt in range(max_retries):
        try:
            info = ticker_obj.info
            return info
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:  # Too Many Requests
                logger.warning(f"Rate limit hit, waiting {RETRY_DELAY} seconds before retry {attempt + 1}")
                time.sleep(RETRY_DELAY)
                continue
            elif "404" in str(e):  # Not Found
                logger.warning(f"Ticker not found (404)")
                return None
            elif attempt < max_retries - 1:
                logger.warning(f"Error getting ticker info (attempt {attempt + 1}): {e}")
                time.sleep(RETRY_DELAY)
                continue
            raise
    return None

def _get_ticker_history(ticker_obj, max_retries=MAX_RETRIES) -> Optional[pd.DataFrame]:
    """Helper function to get ticker history with retries"""
    for attempt in range(max_retries):
        try:
            history = ticker_obj.history(period='5d')
            if not history.empty:
                return history
            elif attempt < max_retries - 1:
                logger.warning(f"Empty history, retrying (attempt {attempt + 1})")
                time.sleep(RETRY_DELAY)
                continue
            return None
        except Exception as e:
            if "429" in str(e) and attempt < max_retries - 1:  # Too Many Requests
                logger.warning(f"Rate limit hit, waiting {RETRY_DELAY} seconds before retry {attempt + 1}")
                time.sleep(RETRY_DELAY)
                continue
            elif attempt < max_retries - 1:
                logger.warning(f"Error getting history (attempt {attempt + 1}): {e}")
                time.sleep(RETRY_DELAY)
                continue
            raise
    return None

@lru_cache(maxsize=1000)
def _validate_ticker(test_ticker: str) -> bool:
    """Validate a ticker with caching to reduce API calls"""
    try:
        ticker_obj = yf.Ticker(test_ticker)
        
        # Try to get history first (more reliable)
        history = _get_ticker_history(ticker_obj)
        if history is not None and not history.empty:
            return True
            
        # Fall back to info if history fails
        info = _get_ticker_info(ticker_obj)
        return bool(info and 'symbol' in info)
        
    except Exception as e:
        logger.debug(f"Failed to validate ticker {test_ticker}: {str(e)}")
        return False

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
            # Skip empty identifiers
            if not identifier or not isinstance(identifier, str):
                logger.warning(f"Invalid identifier: {identifier}")
                results[identifier] = None
                continue
                
            identifier = identifier.strip().upper()
            
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
                results[identifier] = None
                continue

            # Try using the ISIN directly first
            time.sleep(REQUEST_DELAY)
            if _validate_ticker(identifier):
                logger.info(f"Successfully validated ISIN as ticker: {identifier}")
                results[identifier] = identifier
                continue
            
            # If direct ISIN fails, try to get the ticker from yfinance info
            try:
                time.sleep(REQUEST_DELAY)
                ticker_obj = yf.Ticker(identifier)
                info = _get_ticker_info(ticker_obj)
                
                if info and 'symbol' in info:
                    ticker = info['symbol']
                    logger.info(f"Successfully mapped {identifier} to {ticker} using info")
                    results[identifier] = ticker
                else:
                    logger.warning(f"No ticker found for identifier: {identifier}")
                    results[identifier] = None
                    
            except Exception as e:
                error_msg = str(e)
                if "404" in error_msg:
                    logger.warning(f"Ticker not found for {identifier} (404)")
                elif "429" in error_msg:
                    logger.warning(f"Rate limit exceeded for {identifier}")
                else:
                    logger.error(f"Error getting ticker for {identifier}: {error_msg}")
                results[identifier] = None

        except Exception as e:
            logger.error(f"Error converting identifier {identifier}: {str(e)}")
            results[identifier] = None

    successful = sum(1 for v in results.values() if v is not None)
    logger.info(f"Completed identifier to Ticker conversion. Successful conversions: {successful}/{len(identifier_list)}")
    return results
