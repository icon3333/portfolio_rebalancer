import logging
import yfinance as yf
import requests
from datetime import datetime
from typing import Dict, Any, Optional
import warnings

# Suppress specific yfinance warnings
warnings.filterwarnings("ignore", message="^[Tt]he 'period'")
logger = logging.getLogger(__name__)

# --- Helper Functions ---


def get_exchange_rate(from_currency: str, to_currency: str = "EUR") -> float:
    """Fetch the exchange rate between two currencies."""
    if from_currency == to_currency:
        return 1.0

    # yfinance uses 'GBp' for pence, which needs to be converted to 'GBP'
    if from_currency == 'GBp':
        from_currency = 'GBP'
        base_rate = 0.01
    else:
        base_rate = 1.0

    try:
        # Construct the currency pair ticker
        ticker = f"{from_currency}{to_currency}=X"
        rate_data = yf.Ticker(ticker)

        # Get the current price
        rate = rate_data.history(period='1d')['Close'].iloc[0]
        if rate:
            return rate * base_rate
        else:
            logger.warning(
                f"Could not retrieve exchange rate for {from_currency}-{to_currency}")
            return 1.0 * base_rate  # Fallback
    except Exception as e:
        logger.error(
            f"Error fetching exchange rate for {from_currency}-{to_currency}: {e}")
        return 1.0 * base_rate  # Fallback

# --- Helper Functions for Identifier Detection ---


def _is_likely_crypto(identifier: str) -> bool:
    """
    Determine if an identifier is likely a cryptocurrency.
    
    Since all traditional stocks will be ISINs (12 characters), 
    any short identifier (≤4 characters) that's alphabetic is likely crypto.
    This greatly simplifies the detection logic.
    """
    if not identifier:
        return False
    
    # Clean identifier
    clean_id = identifier.upper().strip()
    
    # ISINs are 12 characters - exclude them
    if len(clean_id) == 12 and clean_id[:2].isalpha() and clean_id[2:].isalnum():
        return False
    
    # Skip if it contains exchange suffixes (e.g., ".PA", ".L")
    if '.' in clean_id:
        return False
    
    # Short identifiers (≤4 chars) that are alphabetic are crypto
    # since all traditional stocks will be ISINs
    if len(clean_id) <= 4 and clean_id.isalpha():
        return True
    
    return False


# --- Main Data Fetching Function ---


def get_isin_data(identifier: str) -> Dict[str, Any]:
    """
    Get stock data for a given ISIN or ticker, with a fallback for crypto.
    Uses the same approach as the working script example.
    Automatically detects crypto based on identifier characteristics.
    """
    logger.info(f"Processing identifier: {identifier}")

    # Check if this looks like a crypto identifier first
    if _is_likely_crypto(identifier):
        logger.info(f"'{identifier}' appears to be cryptocurrency, trying crypto format first")
        crypto_identifier = f"{identifier}-USD"
        data = _fetch_yfinance_data_robust(crypto_identifier)
        if data:
            # Mark that we used crypto format
            data['modified_identifier'] = crypto_identifier
            data['sector'] = 'Cryptocurrency'
            data['industry'] = 'Digital Currency'
            data['country'] = 'N/A'
            logger.info(f"Successfully retrieved crypto data for {identifier} as {crypto_identifier}")
        else:
            # If crypto format fails, try standard format as fallback
            logger.warning(f"Crypto format '{crypto_identifier}' failed, trying standard format")
            data = _fetch_yfinance_data_robust(identifier)
    else:
        # Use the exact same pattern as the working script for non-crypto
        data = _fetch_yfinance_data_robust(identifier)

        # If the initial fetch fails, try a crypto-specific format as fallback
        if not data:
            logger.warning(
                f"Standard lookup for '{identifier}' failed, trying crypto format.")
            crypto_identifier = f"{identifier}-USD"
            data = _fetch_yfinance_data_robust(crypto_identifier)
            if data:
                # Mark that we used a fallback
                data['modified_identifier'] = crypto_identifier
                data['sector'] = 'Cryptocurrency'
                data['industry'] = 'Digital Currency'
                data['country'] = 'N/A'

    if not data:
        logger.error(
            f"Failed to fetch data for '{identifier}' as standard or crypto.")
        return {'success': False, 'error': f"Could not find data for identifier {identifier}."}

    # --- Post-processing and Currency Conversion ---

    price = data.get('price')
    currency = data.get('currency', 'USD')

    # Convert price to EUR if not already
    if price is not None and currency != 'EUR':
        exchange_rate = get_exchange_rate(currency, "EUR")
        data['priceEUR'] = price * exchange_rate
        logger.info(
            f"Converted {price:.2f} {currency} to {data['priceEUR']:.2f} EUR (rate: {exchange_rate})")
    elif price is not None:
        data['priceEUR'] = price  # Already in EUR

    return {
        'success': True,
        'data': {
            'currentPrice': data.get('price'),
            'priceEUR': data.get('priceEUR'),
            'currency': currency,
            'country': data.get('country'),
            'sector': data.get('sector'),
            'industry': data.get('industry')
        },
        'modified_identifier': data.get('modified_identifier')
    }


def _fetch_yfinance_data_robust(identifier: str) -> Optional[Dict[str, Any]]:
    """
    Robust yfinance data fetching using the exact same pattern as the working script.
    Handles yfinance session/cookie bugs by mimicking the working script's approach.
    """
    try:
        # The working script shows this pattern works - follow it exactly
        ticker = yf.Ticker(identifier)

        # The working script uses this exact pattern for error handling
        try:
            info = ticker.info
        except Exception as e:
            logger.warning(f"Error fetching ticker info for {identifier}: {e}")
            info = {}

        # The working script checks for empty info like this
        if not info:
            logger.debug(f"Empty info dictionary for '{identifier}'")
            return None

        # The working script validates price data this way
        price = info.get('regularMarketPrice') or info.get('currentPrice')
        
        # The working script only proceeds if price exists
        if price is not None:
            return {
                'price': price,
                'currency': info.get('currency'),
                'country': info.get('country'),
                'sector': info.get('sector'),
                'industry': info.get('industry'),
            }
        else:
            logger.debug(f"No valid price found for '{identifier}'")
            return None
            
    except Exception as e:
        # The working script shows that this level of error handling works
        logger.warning(f"yfinance lookup for '{identifier}' failed with error: {e}")
        return None


def _fetch_yfinance_data(identifier: str) -> Optional[Dict[str, Any]]:
    """
    Legacy function - redirects to robust implementation.
    """
    return _fetch_yfinance_data_robust(identifier)

# --- Other Utility Functions (can be expanded) ---


def get_yfinance_info(identifier: str) -> Dict[str, Any]:
    """Simple wrapper to get the full info dictionary from yfinance."""
    try:
        ticker = yf.Ticker(identifier)
        return ticker.info
    except Exception as e:
        logger.error(f"Could not get yfinance info for {identifier}: {e}")
        return {'error': str(e)}


def get_historical_prices(identifiers, years=5):
    """Fetches historical price data for a list of identifiers."""
    try:
        end_date = datetime.now()
        start_date = end_date.replace(year=end_date.year - years)

        data = yf.download(identifiers, start=start_date,
                           end=end_date, auto_adjust=True)['Close']
        return data.fillna(method='ffill')
    except Exception as e:
        logger.error(f"Error fetching historical prices: {e}")
        return None

# (Add other historical data functions as needed)
