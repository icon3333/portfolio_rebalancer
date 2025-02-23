import requests
import time
import random
import logging
import os
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor, as_completed
from cachetools import TTLCache
from threading import Lock
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class RateLimitError(Exception):
    pass

class AdaptiveRateLimit:
    def __init__(self, initial_rate=5.0):  # Tiingo allows higher rate
        self.current_rate = initial_rate
        self.last_request = 0
        self.lock = Lock()
        self.failures = 0
        self.successes = 0
    
    def wait(self):
        with self.lock:
            now = time.time()
            wait_time = max(0, (1.0 / self.current_rate) - (now - self.last_request))
            if wait_time > 0:
                time.sleep(wait_time)
            self.last_request = time.time()
    
    def update(self, success=True):
        with self.lock:
            if success:
                self.successes += 1
                if self.successes > 10:
                    self.current_rate = min(10.0, self.current_rate * 1.1)  # Tiingo allows higher rate
                    self.successes = 0
            else:
                self.failures += 1
                if self.failures > 2:
                    self.current_rate = max(0.5, self.current_rate * 0.5)
                    self.failures = 0

class PriceManager:
    def __init__(self):
        self.cache = TTLCache(maxsize=1000, ttl=300)  # 5 minutes cache
        self.failed = TTLCache(maxsize=100, ttl=3600)  # 1 hour failure cache
        self.rate_limiter = AdaptiveRateLimit()
        self.isin_cache = TTLCache(maxsize=1000, ttl=86400)  # 24 hour ISIN to identifier cache
        self.lock = Lock()
        # Known crypto identifiers
        self.KNOWN_CRYPTO = {'BTC', 'ETH', 'USDT', 'XRP', 'DOGE'}
        
        # Tiingo configuration
        self.api_key = os.getenv('TIINGO_API_KEY')
        if not self.api_key:
            raise ValueError("TIINGO_API_KEY environment variable not set")
        
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Token {self.api_key}'
        }
        
        # Base URLs
        self.EOD_URL = "https://api.tiingo.com/tiingo/daily"
        self.FX_URL = "https://api.tiingo.com/tiingo/fx"
        self.CRYPTO_URL = "https://api.tiingo.com/tiingo/crypto"
    
    def fetch_with_retry(self, identifier, max_retries=3):
        """Fetch price data with exponential backoff retry"""
        for attempt in range(max_retries):
            try:
                self.rate_limiter.wait()
                
                # Handle crypto currencies differently
                if any(crypto in identifier.upper() for crypto in self.KNOWN_CRYPTO):
                    return self._fetch_crypto_price(identifier)
                
                # Get EOD data
                url = f"{self.EOD_URL}/{identifier}/prices"
                params = {
                    'startDate': (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d'),
                    'endDate': datetime.now().strftime('%Y-%m-%d')
                }
                
                response = requests.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                
                if not data:
                    return None
                
                # Get latest price
                price = data[-1]['adjClose']  # Using adjusted close
                
                # Get meta data for currency
                meta_response = requests.get(f"{self.EOD_URL}/{identifier}", headers=self.headers)
                meta_response.raise_for_status()
                meta_data = meta_response.json()
                currency = meta_data.get('currency', 'USD')
                
                # Convert to EUR if needed
                price_eur = price
                if currency != 'EUR':
                    try:
                        fx_pair = f"{currency}/EUR"
                        fx_url = f"{self.FX_URL}/prices"
                        fx_params = {'tickers': fx_pair}
                        fx_response = requests.get(fx_url, headers=self.headers, params=fx_params)
                        fx_response.raise_for_status()
                        fx_data = fx_response.json()
                        if fx_data:
                            rate = fx_data[0]['adjClose']
                            price_eur = price * rate
                    except Exception as e:
                        logger.warning(f"Failed to convert currency: {str(e)}")
                
                self.rate_limiter.update(True)
                return price, currency, price_eur
                
            except Exception as e:
                self.rate_limiter.update(False)
                delay = (2 ** attempt) + random.uniform(0, 1)
                if attempt < max_retries - 1:  # Don't sleep on last attempt
                    time.sleep(delay)
                logger.warning(f"Attempt {attempt + 1} failed for {identifier}: {str(e)}")
        
        raise RateLimitError(f"Failed to fetch price after {max_retries} attempts")
    
    def _fetch_crypto_price(self, identifier):
        """Fetch cryptocurrency price from Tiingo Crypto API"""
        crypto_symbol = identifier.upper().replace('USD', '')
        url = f"{self.CRYPTO_URL}/prices"
        params = {
            'tickers': f"{crypto_symbol}USD",
            'resampleFreq': '1day'
        }
        
        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()
        data = response.json()
        
        if not data:
            return None
        
        price = data[0]['close']
        currency = 'USD'
        
        # Convert to EUR
        try:
            fx_pair = "USD/EUR"
            fx_url = f"{self.FX_URL}/prices"
            fx_params = {'tickers': fx_pair}
            fx_response = requests.get(fx_url, headers=self.headers, params=fx_params)
            fx_response.raise_for_status()
            fx_data = fx_response.json()
            if fx_data:
                rate = fx_data[0]['adjClose']
                price_eur = price * rate
        except Exception as e:
            logger.warning(f"Failed to convert crypto currency: {str(e)}")
            price_eur = price
            
        return price, currency, price_eur
    
    def get_price(self, identifier):
        """Get price with caching"""
        with self.lock:
            if identifier in self.failed:
                return None
            
            if identifier in self.cache:
                return self.cache[identifier]
            
            try:
                result = self.fetch_with_retry(identifier)
                if result:
                    self.cache[identifier] = result
                else:
                    self.failed[identifier] = True
                return result
            except Exception as e:
                logger.error(f"Error fetching price for {identifier}: {str(e)}")
                self.failed[identifier] = True
                return None
    
    def isin_to_identifier(self, isin):
        """Convert ISIN to identifier with caching"""
        if not isin:
            return None, "No ISIN provided"
            
        # Handle crypto identifiers (assumed to be shorter than 12 chars without dots)
        if len(isin) < 12 and '.' not in isin:
            upper_isin = isin.upper()
            if upper_isin in self.KNOWN_CRYPTO:
                identifier = f"{upper_isin}-USD" if not upper_isin.endswith("-USD") else upper_isin
                return identifier, None
            return None, f"Unknown crypto identifier: {isin}"
            
        # Basic ISIN validation
        if not (len(isin) == 12 and isin.isalnum()):
            return None, "Invalid ISIN format. ISIN should be 12 alphanumeric characters."
            
        # Check cache
        if isin in self.isin_cache:
            return self.isin_cache[isin]
            
        try:
            self.rate_limiter.wait()
            ticker = requests.get(f"{self.EOD_URL}/{isin}", headers=self.headers)
            ticker.raise_for_status()
            info = ticker.json()
            
            if info and 'ticker' in info:
                result = (info['ticker'], None)
                self.isin_cache[isin] = result
                self.rate_limiter.update(True)
                return result
                
            self.rate_limiter.update(False)
            return None, "Could not find identifier for this ISIN"
        except Exception as e:
            self.rate_limiter.update(False)
            return None, f"Error processing ISIN: {str(e)}"
    
    def process_identifiers_batch(self, identifiers, batch_size=5):
        """Process multiple identifiers in batches"""
        results = {}
        for i in range(0, len(identifiers), batch_size):
            batch = identifiers[i:i+batch_size]
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                futures = {executor.submit(self.get_price, t): t for t in batch}
                for future in as_completed(futures):
                    identifier = futures[future]
                    try:
                        results[identifier] = future.result(timeout=10)
                    except Exception as e:
                        logger.error(f"Error processing {identifier}: {e}")
                        results[identifier] = (None, None, None, str(e))
        return results

# Global instance
price_manager = PriceManager()
