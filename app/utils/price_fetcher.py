"""
Utility for fetching stock prices from external APIs.
Handles rate limiting, caching, and error handling.
"""

import time
import logging
import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional, Union
from datetime import datetime, timedelta
from functools import lru_cache
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Setup logging
logger = logging.getLogger(__name__)

class AdaptiveRateLimit:
    """Rate limiter that adapts to API response patterns"""
    def __init__(self, initial_rate=0.1):
        self.rate = initial_rate
        self.failures = 0
        self.last_call = 0
    
    def __enter__(self):
        if self.failures > 5:
            self.rate = min(1.0, self.rate * 1.5)  # Slow down if too many failures
        
        time_since_last = time.time() - self.last_call
        if time_since_last < self.rate:
            time.sleep(self.rate - time_since_last)
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.last_call = time.time()
        if exc_type is not None:
            self.failures += 1
        else:
            self.failures = max(0, self.failures - 1)
            self.rate = max(0.1, self.rate * 0.95)  # Speed up if successful

class PriceFetchManager:
    """Handles all external API interactions for price fetching"""
    def __init__(self):
        self.rate_limiter = AdaptiveRateLimit()
        self.cache = {}
        self.cache_expiry = {}
        self.failed_tickers = set()  # Cache for failed lookups
        self.cache_duration = 300  # 5 minutes in seconds
        self.lock = threading.Lock()
        
    def get_cached_price(self, ticker: str) -> Optional[Tuple[float, str, float]]:
        """Get price from cache or fetch if expired"""
        # Skip invalid tickers
        if not isinstance(ticker, str):
            logger.warning(f"Invalid ticker type: {type(ticker)}")
            return None
            
        # Clean and validate ticker
        try:
            ticker = str(ticker).strip().upper()
        except:
            logger.warning(f"Could not process ticker: {ticker}")
            return None
            
        if not ticker:
            logger.warning("Empty ticker")
            return None
            
        # Check if ticker is in failed cache
        with self.lock:
            if ticker in self.failed_tickers:
                logger.debug(f"Skipping previously failed ticker: {ticker}")
                return None, None, None
                
            now = time.time()
            if ticker in self.cache and now < self.cache_expiry.get(ticker, 0):
                return self.cache[ticker]
            
        # Fetch new price
        result = self.fetch_price_and_currency(ticker)
        
        # Update cache
        with self.lock:
            if result[0] is not None:
                self.cache[ticker] = result
                self.cache_expiry[ticker] = now + self.cache_duration
            else:
                self.failed_tickers.add(ticker)
                
        return result

    def fetch_price_and_currency(self, ticker: str) -> Tuple[Optional[float], Optional[str], Optional[float]]:
        """Fetch single ticker price data"""
        logger.debug(f"Fetching price for ticker: {ticker}")
        
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                with self.rate_limiter:
                    yf_data = yf.Ticker(ticker)
                    logger.info(f"Getting history for {ticker} (attempt {attempt + 1}/{max_retries})")
                    history = yf_data.history(period='5d')  
                    logger.info(f"History data for {ticker}: {len(history)} rows received")
                    
                    if history.empty:
                        logger.info(f"No price data available for {ticker}")
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                        return None, None, None
                    
                    try:
                        # Try to get the most recent price
                        price = history['Close'].iloc[-1]
                        if pd.isna(price) and len(history) > 1:
                            # If latest is NaN, try previous day
                            price = history['Close'].iloc[-2]
                            
                        if pd.isna(price):
                            logger.warning(f"No valid price found for {ticker}")
                            if attempt < max_retries - 1:
                                time.sleep(retry_delay)
                                continue
                            return None, None, None
                            
                        logger.info(f"Got price for {ticker}: {price}")
                        
                        # Try to get currency from yfinance info first
                        try:
                            info = yf_data.info
                            currency = info.get('currency', None)
                            logger.info(f"Got currency from yfinance for {ticker}: {currency}")
                        except Exception as e:
                            logger.warning(f"Failed to get currency from yfinance for {ticker}: {e}")
                            currency = None
                        
                        # Fall back to suffix-based detection if yfinance fails
                        if not currency:
                            if any(ticker.upper().endswith(suffix) for suffix in ['.DE', '.F', '.MU']):
                                currency = 'EUR'
                            elif any(ticker.upper().endswith(suffix) for suffix in ['.L']):
                                currency = 'GBP'
                            else:
                                currency = 'USD'  # Default to USD for NYSE/NASDAQ stocks
                            logger.info(f"Using suffix-based currency for {ticker}: {currency}")
                        
                        # Handle GBp (British pence) to GBP conversion
                        if currency == 'GBp':
                            price = price / 100  # Convert pence to pounds
                            currency = 'GBP'
                            logger.info(f"Converted GBp to GBP for {ticker}: {price} GBP")
                        
                        # Calculate EUR price if needed
                        price_eur = price
                        if currency != 'EUR':
                            eur_rate = self._get_eur_rate(currency)
                            if eur_rate is not None:
                                price_eur = price * eur_rate
                                logger.info(f"Converted {ticker} price to EUR: {price_eur} (rate: {eur_rate})")
                            else:
                                logger.warning(f"Failed to get EUR rate for {currency}")
                                if attempt < max_retries - 1:
                                    time.sleep(retry_delay)
                                    continue
                                return price, currency, None
                                
                        return price, currency, price_eur
                        
                    except Exception as e:
                        logger.warning(f"Error processing data for {ticker}: {str(e)}")
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                        return None, None, None
                        
            except Exception as e:
                logger.warning(f"Failed to fetch data for {ticker} (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                
                with self.lock:
                    self.failed_tickers.add(ticker)
                return None, None, None

    def _get_eur_rate(self, currency: str) -> Optional[float]:
        """Get EUR conversion rate"""
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                with self.rate_limiter:
                    eur_ticker = f"{currency}EUR=X"
                    eur_data = yf.Ticker(eur_ticker)
                    eur_history = eur_data.history(period='5d')  
                    if not eur_history.empty:
                        rate = eur_history['Close'].iloc[-1]
                        if pd.isna(rate) and len(eur_history) > 1:
                            # If latest is NaN, try previous day
                            rate = eur_history['Close'].iloc[-2]
                        
                        if not pd.isna(rate):
                            return rate
                            
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

    def fetch_batch(self, tickers: List[str], timeout: int = 10) -> Dict[str, Tuple[float, str, float]]:
        """Batch process multiple tickers with timeout"""
        results = {}
        logger.info(f"Starting batch fetch for {len(tickers)} tickers: {tickers}")
        
        # Filter out known failed tickers
        with self.lock:
            valid_tickers = [ticker for ticker in tickers if ticker not in self.failed_tickers]
        
        if len(valid_tickers) != len(tickers):
            skipped = set(tickers) - set(valid_tickers)
            logger.info(f"Skipping {len(skipped)} previously failed tickers: {skipped}")
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_ticker = {
                executor.submit(self.get_cached_price, ticker): ticker 
                for ticker in valid_tickers
            }
            
            for future in as_completed(future_to_ticker):
                ticker = future_to_ticker[future]
                try:
                    result = future.result(timeout=timeout)
                    results[ticker] = result
                    if result[0] is not None:
                        logger.info(f"Successfully fetched {ticker}: Price={result[0]} {result[1]} (EUR: {result[2]})")
                    else:
                        logger.warning(f"Failed to fetch {ticker}: No price data")
                except TimeoutError:
                    logger.warning(f"Timeout fetching {ticker}")
                    results[ticker] = (None, None, None)
                    with self.lock:
                        self.failed_tickers.add(ticker)
                except Exception as e:
                    if '404' in str(e):
                        logger.info(f"Failed to fetch {ticker}: ticker not found")
                    else:
                        logger.error(f"Error fetching {ticker}: {e}")
                    results[ticker] = (None, None, None)
                    with self.lock:
                        self.failed_tickers.add(ticker)
        
        logger.info(f"Batch fetch completed. Success rate: {sum(1 for r in results.values() if r[0] is not None)}/{len(tickers)}")
        return results

    def clear_cache(self, tickers: Optional[List[str]] = None):
        """Clear price cache for specific tickers or all"""
        with self.lock:
            if tickers:
                # Clear only specified tickers
                for ticker in tickers:
                    ticker = ticker.strip().upper()
                    if ticker in self.cache:
                        del self.cache[ticker]
                    if ticker in self.cache_expiry:
                        del self.cache_expiry[ticker]
                    if ticker in self.failed_tickers:
                        self.failed_tickers.remove(ticker)
            else:
                # Clear entire cache
                self.cache.clear()
                self.cache_expiry.clear()
                self.failed_tickers.clear()

@lru_cache(maxsize=20)
def get_historical_data(tickers_str: str, years: int = 5) -> pd.DataFrame:
    """
    Get historical data for multiple tickers.
    
    Args:
        tickers_str: Comma-separated string of tickers (for caching)
        years: Number of years of historical data to retrieve
        
    Returns:
        DataFrame with historical prices
    """
    tickers = tickers_str.split(',')
    logger.info(f"Fetching historical data for {len(tickers)} tickers")
    end_date = datetime.now()
    start_date = end_date - timedelta(days=years * 365)
    
    all_data = pd.DataFrame()
    failed_tickers = []
    
    for ticker in tickers:
        try:
            ticker_obj = yf.Ticker(ticker)
            hist = ticker_obj.history(start=start_date, end=end_date)
            
            if hist.empty:
                logger.warning(f"No data found for ticker {ticker}")
                failed_tickers.append(ticker)
                continue
                
            prices = hist['Close'].rename(ticker)
            if all_data.empty:
                all_data = pd.DataFrame(prices)
            else:
                all_data = pd.concat([all_data, prices], axis=1)
                
        except Exception as e:
            logger.warning(f"Failed to fetch data for {ticker}: {str(e)}")
            failed_tickers.append(ticker)
            continue
    
    if failed_tickers:
        logger.warning(f"Failed to fetch data for tickers: {failed_tickers}")
        
    return all_data

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

# Create a global instance
price_fetcher = PriceFetchManager()