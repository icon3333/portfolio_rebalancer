import logging
import yfinance as yf
import requests
from datetime import datetime
from typing import Dict, Any
import warnings

# Suppress specific yfinance warnings that might clutter the logs
warnings.filterwarnings("ignore", message="^[Tt]he 'period'")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def find_ticker_for_isin(isin: str) -> str:
    """
    Find ticker symbol for an ISIN using direct yfinance approach.
    With fallback for when the standard approach fails.
    """
    logger.info(f"Finding ticker for ISIN: {isin}")
    
    # Special case handling for common European ISINs that cause issues
    # This is a fallback mapping for known problematic ISINs
    isin_to_ticker_map = {
        # Common European stocks that might cause issues
        'NL00150001Q9': 'STLA', # Stellantis
        'DE0007664005': 'VWAGY', # Volkswagen
        # Crypto currencies
        'BTC': 'BTC-USD',
        'ETH': 'ETH-USD',
        'LRC': 'LRC-USD',
        'ATOM': 'ATOM-USD',
        'SOL': 'SOL-USD',
        'DOGE': 'DOGE-USD',
        'PEPE': 'PEPE-USD',
        'IOTA': 'IOTA-USD',
        'TRX': 'TRX-USD',
        'LINK': 'LINK-USD',
        # Add more mappings as needed
    }
    
    # Check if we have a direct mapping
    if isin in isin_to_ticker_map:
        ticker = isin_to_ticker_map[isin]
        logger.info(f"Using direct mapping for ISIN {isin} to ticker {ticker}")
        return ticker
    
    # Try standard approach
    try:
        # Use more cautious approach instead of direct Ticker instantiation
        try:
            # Try to get ticker information without creating a full Ticker object
            search_result = yf.Ticker(isin)
            
            # Check if the ticker was successfully resolved
            if hasattr(search_result, 'ticker'):
                ticker = search_result.ticker
                logger.info(f"Successfully mapped ISIN {isin} to ticker {ticker}")
                return ticker
        except Exception as inner_e:
            logger.warning(f"Primary lookup method failed for ISIN {isin}: {str(inner_e)}")
            
        # If we reach here, the primary method failed - try fallback approach
        logger.info(f"Trying fallback approach for ISIN {isin}")
        
        # For European ISINs, try adding common exchange suffixes
        if isin.startswith('DE'):
            # Try German stock exchange
            return f"{isin}.DE"  # Frankfurt exchange
        elif isin.startswith('FR'):
            return f"{isin}.PA"  # Paris exchange
        elif isin.startswith('NL'):
            return f"{isin}.AS"  # Amsterdam exchange
        elif isin.startswith('GB'):
            return f"{isin}.L"   # London exchange
        
        # Default fallback - just use the ISIN directly
        logger.warning(f"Using ISIN directly as ticker: {isin}")
        return isin
            
    except Exception as e:
        logger.error(f"Error finding ticker for ISIN {isin}: {str(e)}")
        # Return the ISIN as a last resort
        return isin

# Changes for get_price_for_ticker() function
# Create a session creation function that we can reset when needed
def get_fresh_session():
    """Create a fresh requests session with appropriate headers to avoid Yahoo Finance blocking"""
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Connection': 'keep-alive',
    })
    return session


def get_price_for_ticker(ticker: str) -> Dict[str, Any]:
    """
    Get the current price and currency for a ticker symbol.
    
    Args:
        ticker (str): Ticker symbol (e.g., 'AAPL')
        
    Returns:
        Dict with price, currency and error information
    """
    if not ticker:
        return {"price": None, "currency": None, "error": "No ticker provided", "success": False}
    
    logger.info(f"Getting price for ticker: {ticker}")
    
    # Initialize variables
    price = None
    currency = None
    error_messages = []
    
    # Create a fresh session for this request
    session = get_fresh_session()
    
    try:
        # Use our custom session to avoid the 'cookies.update' error
        ticker_obj = yf.Ticker(ticker, session=session)
        
        # Method 1: Use info approach - most reliable for getting both price and currency
        try:
            # Create a timeout to prevent hanging
            info_result = [None]
            info_error = [None]
            
            def get_info():
                try:
                    info_result[0] = ticker_obj.info
                except Exception as e:
                    info_error[0] = str(e)
            
            import threading
            info_thread = threading.Thread(target=get_info)
            info_thread.daemon = True
            info_thread.start()
            info_thread.join(timeout=5)  # 5 second timeout
            
            if info_error[0]:
                error_msg = f"Error getting info data: {info_error[0]}"
                logger.warning(error_msg)
                error_messages.append(error_msg)
            elif info_result[0]:
                info = info_result[0]
                
                # Extract currency information - required for valid result
                if 'currency' in info and info['currency'] is not None:
                    currency = info['currency']
                    
                    # Validate currency format (must be 3 characters)
                    if not isinstance(currency, str) or len(currency) != 3:
                        error_msg = f"Invalid currency format from info: {currency}"
                        logger.warning(error_msg)
                        error_messages.append(error_msg)
                        currency = None
                else:
                    error_msg = "No currency information found in ticker info"
                    logger.warning(error_msg)
                    error_messages.append(error_msg)
                
                # Check if we have both price and currency before returning
                if currency:
                    # Try different price fields
                    if 'currentPrice' in info and info['currentPrice'] is not None:
                        price = float(info['currentPrice'])
                    elif 'regularMarketPrice' in info and info['regularMarketPrice'] is not None:
                        price = float(info['regularMarketPrice'])
                    
                    if price is not None:
                        return {
                            "price": price,
                            "currency": currency,
                            "error": None,
                            "success": True
                        }
        except Exception as e:
            error_msg = f"Error in info method: {str(e)}"
            logger.warning(error_msg)
            error_messages.append(error_msg)
        
        # Method 2: Try fast_info if info method didn't provide both price and currency
        if price is None or currency is None:
            try:
                if hasattr(ticker_obj, 'fast_info'):
                    # First, try to get currency from fast_info
                    if hasattr(ticker_obj.fast_info, 'currency'):
                        currency = ticker_obj.fast_info.currency
                        # Validate currency format
                        if not isinstance(currency, str) or len(currency) != 3:
                            error_msg = f"Invalid currency format from fast_info: {currency}"
                            logger.warning(error_msg)
                            error_messages.append(error_msg)
                            currency = None
                    
                    # Then try to get price if we have a valid currency
                    if currency:
                        if isinstance(ticker_obj.fast_info, dict):
                            price = ticker_obj.fast_info.get('last_price') or ticker_obj.fast_info.get('regularMarketPrice')
                        else:
                            try:
                                price = ticker_obj.fast_info.last_price
                            except:
                                try:
                                    price = ticker_obj.fast_info.regular_market_price
                                except:
                                    price = None
                                    
                        if price is not None and isinstance(price, (int, float)):
                            return {
                                "price": float(price),
                                "currency": currency,
                                "error": None,
                                "success": True
                            }
            except Exception as e:
                error_msg = f"Error in fast_info method: {str(e)}"
                logger.warning(error_msg)
                error_messages.append(error_msg)
        
        # Method 3: Try to get currency directly from the ticker symbol
        # Only for special cases where the ticker contains exchange information
        if currency is None:
            # Don't proceed further without currency info - this is a requirement
            logger.error(f"Could not determine currency for {ticker}")
            error_messages.append("Could not determine currency from any available method")
            return {
                "price": price,  # Return price if we found it
                "currency": None,
                "error": "No currency information available. " + " | ".join(error_messages),
                "success": False
            }
        
        # If we reach here, we have currency but no price - try historical data
        if price is None and currency is not None:
            try:
                # For yfinance 0.2.54, we can use the standard approach
                data = ticker_obj.history(period="1d")
                if not data.empty and 'Close' in data.columns:
                    last_close = data['Close'].iloc[-1]
                    if isinstance(last_close, (int, float)) and last_close > 0:
                        return {
                            "price": float(last_close),
                            "currency": currency,
                            "error": None,
                            "success": True
                        }
            except Exception as e:
                error_msg = f"Error getting historical price: {str(e)}"
                logger.warning(error_msg)
                error_messages.append(error_msg)
        
        # If we still have no price, try direct download method
        if price is None and currency is not None:
            try:
                import datetime
                end_date = datetime.datetime.now()
                start_date = end_date - datetime.timedelta(days=7)
                
                # Format the dates as strings for the download call
                end_str = end_date.strftime('%Y-%m-%d')
                start_str = start_date.strftime('%Y-%m-%d')
                
                logger.info(f"Trying direct download with date range: {start_str} to {end_str}")
                data = yf.download(ticker, start=start_str, end=end_str, progress=False)
                if not data.empty and 'Close' in data.columns:
                    last_close = data['Close'].iloc[-1]
                    if isinstance(last_close, (int, float)) and last_close > 0:
                        return {
                            "price": float(last_close),
                            "currency": currency,
                            "error": None,
                            "success": True
                        }
            except Exception as e:
                error_msg = f"Error with direct download: {str(e)}"
                logger.warning(error_msg)
                error_messages.append(error_msg)
                
        # If we get here, we couldn't get both valid price and currency
        return {
            "price": price,
            "currency": currency,
            "error": f"Failed to retrieve complete data: {' | '.join(error_messages)}",
            "success": False
        }
        
    except Exception as e:
        logger.error(f"Error getting price data for {ticker}: {str(e)}")
        return {"price": None, "currency": None, "error": str(e), "success": False}

# Function to get exchange rate for currency conversion
def get_crypto_price(crypto_ticker: str) -> Dict[str, Any]:
    """
    Get the current price for a crypto ticker symbol using a specialized approach for yfinance 0.2.54.
    
    Args:
        crypto_ticker (str): Crypto ticker symbol with -USD suffix (e.g., 'BTC-USD')
        
    Returns:
        Dict with price, currency and error information
    """
    logger.info(f"Getting price for crypto ticker: {crypto_ticker}")
    
    try:
        # Create a fresh session for this request to prevent cookie errors
        session = get_fresh_session()
        
        # Use a more direct approach for crypto tickers with our custom session
        ticker_obj = yf.Ticker(crypto_ticker, session=session)
        
        # Try the info approach first with basic error handling
        try:
            info = ticker_obj.info
            if 'regularMarketPrice' in info and info['regularMarketPrice'] is not None:
                return {
                    "price": float(info['regularMarketPrice']),
                    "currency": "USD",  # Crypto prices are typically in USD
                    "error": None,
                    "success": True
                }
        except Exception as e:
            logger.warning(f"Error getting info for crypto {crypto_ticker}: {str(e)}")
        
        # Try a simple history approach as fallback
        try:
            # Use standard history call for yfinance 0.2.54
            data = ticker_obj.history(period="1d")
            if not data.empty and 'Close' in data.columns:
                last_close = data['Close'].iloc[-1]
                if isinstance(last_close, (int, float)) and last_close > 0:
                    return {
                        "price": float(last_close),
                        "currency": "USD",
                        "error": None,
                        "success": True
                    }
        except Exception as e:
            logger.warning(f"Error getting history for crypto {crypto_ticker}: {str(e)}")
        
        # Try direct download as a last resort
        try:
            # For yfinance 0.2.54, we can use datetime subtraction
            import datetime
            end_date = datetime.datetime.now()
            start_date = end_date - datetime.timedelta(days=3)  # Use a shorter window for crypto
            
            # Format the dates as strings for the download call
            end_str = end_date.strftime('%Y-%m-%d')
            start_str = start_date.strftime('%Y-%m-%d')
            
            data = yf.download(crypto_ticker, start=start_str, end=end_str, progress=False, session=session)
            if not data.empty and 'Close' in data.columns:
                last_close = data['Close'].iloc[-1]
                if isinstance(last_close, (int, float)) and last_close > 0:
                    return {
                        "price": float(last_close),
                        "currency": "USD",
                        "error": None,
                        "success": True
                    }
        except Exception as e:
            logger.warning(f"Error with direct download for crypto {crypto_ticker}: {str(e)}")
        
        # If all methods failed
        return {
            "price": None,
            "currency": "USD",
            "error": f"Failed to retrieve price data for crypto {crypto_ticker}",
            "success": False
        }
    except Exception as e:
        logger.error(f"Error getting crypto price data for {crypto_ticker}: {str(e)}")
        return {"price": None, "currency": "USD", "error": str(e), "success": False}

def get_exchange_rate(from_currency: str, to_currency: str = 'EUR') -> float:
    """
    Get exchange rate from one currency to another.
    Defaults to converting to EUR.
    
    Args:
        from_currency (str): Source currency code
        to_currency (str): Target currency code (default: EUR)
        
    Returns:
        float: Exchange rate (1 unit of from_currency in to_currency)
    """
    if from_currency == to_currency:
        return 1.0
        
    if not from_currency or not to_currency:
        logger.warning(f"Missing currency code: from={from_currency}, to={to_currency}")
        return 1.0
    
    # Special handling for GBp (British pence)
    # GBp needs to be converted to GBP first (divide by 100)
    if from_currency == 'GBp':
        logger.info(f"Converting from GBp (pence) to {to_currency}")
        # First get GBP to target currency rate - use direct approach to avoid recursive call
        try:
            # Use yfinance to get the GBP to target currency exchange rate
            ticker = f"GBP{to_currency}=X"
            forex = yf.Ticker(ticker)
            
            # Try to get the latest price
            data = forex.history(period="1d")
            if not data.empty and 'Close' in data.columns:
                gbp_rate = float(data['Close'].iloc[-1])
                logger.info(f"GBp conversion: Exchange rate GBP to {to_currency}: {gbp_rate}")
                # Apply 1/100 conversion from pence to pounds
                final_rate = gbp_rate / 100.0
                logger.info(f"GBp conversion: Final rate (with 1/100 factor): {final_rate}")
                return final_rate
        except Exception as e:
            logger.warning(f"Error in GBp special handling: {str(e)}")
            # Fallback: use 1/100 of the standard rate (approximation)
            return 0.01  # Approximate GBp to EUR rate as fallback
    
    try:
        # Use yfinance to get the exchange rate
        ticker = f"{from_currency}{to_currency}=X"
        forex = yf.Ticker(ticker)
        
        # Try to get the latest price
        try:
            data = forex.history(period="1d")
            if not data.empty and 'Close' in data.columns:
                rate = float(data['Close'].iloc[-1])
                logger.info(f"Exchange rate {from_currency} to {to_currency}: {rate}")
                return rate
        except Exception as e:
            logger.warning(f"Error getting forex rate for {ticker}: {str(e)}")
        
        # Fallback: try info
        try:
            info = forex.info
            if 'regularMarketPrice' in info and info['regularMarketPrice'] is not None:
                rate = float(info['regularMarketPrice'])
                logger.info(f"Exchange rate {from_currency} to {to_currency} (info): {rate}")
                return rate
        except Exception as e:
            logger.warning(f"Error getting forex info for {ticker}: {str(e)}")
        
        # If all fails, use USD-EUR as fallback if needed
        if from_currency == 'USD' and to_currency == 'EUR':
            logger.warning("Using fallback USD-EUR rate")
            return 0.93  # Approximate USD to EUR rate as fallback
            
        logger.warning(f"Could not get exchange rate for {from_currency}-{to_currency}, using 1.0")
        return 1.0
        
    except Exception as e:
        logger.error(f"Error getting exchange rate {from_currency}-{to_currency}: {str(e)}")
        return 1.0

# Updated get_isin_data function
def get_isin_data(isin: str) -> Dict[str, Any]:
    """
    Get stock data for a given ISIN or ticker
    
    Args:
        isin (str): ISIN code (e.g., 'US0378331005') or ticker symbol
        
    Returns:
        Dict[str, Any]: Dictionary containing ISIN/ticker information including country, sector, and industry
    """
    logger.info(f"Processing identifier: {isin}")
    
    # Initialize variables
    price = None
    ticker = None
    currency = None
    modified_identifier = None
    success = False
    error_message = None
    tried_crypto_format = False
    price_eur = None
    country = None
    sector = None
    industry = None
    
    try:
        # Step 1: Try standard approach with original identifier
        try:
            ticker = find_ticker_for_isin(isin)
            if ticker:
                price_result = get_price_for_ticker(ticker)
                price = price_result.get("price")
                currency = price_result.get("currency", "USD")  # Get currency, default to USD if not found
                
                if price is not None:
                    success = True
                else:
                    error_message = price_result.get("error", "No price data available")
        except Exception as e:
            error_message = str(e)
            logger.warning(f"Standard approach failed for {isin}: {error_message}")
        
        # Step 2: If standard approach failed AND identifier is likely a crypto symbol,
        # try appending -USD if not already present
        if (not success) and (len(isin) < 12):
            tried_crypto_format = True
            
            # Check if "-USD" is already in the isin
            if isin.endswith("-USD"):
                crypto_identifier = isin
                logger.info(f"🔄 Using existing crypto format: {crypto_identifier}")
            else:
                crypto_identifier = f"{isin}-USD"
                logger.info(f"🔄 Trying crypto format: {crypto_identifier}")
            
            try:
                # Try to get price with the modified identifier
                logger.info(f"Getting price for crypto ticker: {crypto_identifier}")
                price_result = get_price_for_ticker(crypto_identifier)
                crypto_price = price_result.get("price")
                
                # Log detailed response for debugging
                logger.info(f"Crypto price result: {price_result}")
                
                # If successful, use this price and modified identifier
                if crypto_price is not None:
                    price = crypto_price
                    ticker = crypto_identifier
                    modified_identifier = crypto_identifier
                    currency = "USD"  # Crypto is always in USD
                    success = True
                    logger.info(f"✅ Crypto format successful for {isin}! Using {crypto_identifier} with price {price}")
                else:
                    error_message = price_result.get("error", "No price data available for crypto format")
                    logger.warning(f"Crypto format failed for {isin}: {error_message}")
            except Exception as e:
                error_message = str(e)
                logger.warning(f"Error trying crypto format for {isin}: {error_message}")
        
        # Convert price to EUR if needed
        if success and price is not None:
            if currency == "EUR":
                price_eur = price  # Already in EUR, no conversion needed
            else:
                # Convert to EUR using exchange rate
                exchange_rate = get_exchange_rate(currency, "EUR")
                price_eur = price * exchange_rate
                logger.info(f"Converted {price} {currency} to {price_eur} EUR (rate: {exchange_rate})")
                
                # Log additional information for GBp conversions
                if currency == "GBp":
                    logger.info(f"GBp conversion: {price} pence = {price/100.0} GBP, final EUR value: {price_eur}")
                
        # Fetch additional data like country, sector, and industry if we have a ticker
        if ticker and success:
            try:
                # Skip metadata fetch for cryptocurrencies (they don't have country, sector, industry)
                if '-USD' in ticker or ticker.lower() in ['btc', 'eth', 'doge', 'atom', 'sol', 'ada', 'link', 'pepe', 'apu'] or ticker.endswith('.X'):
                    logger.info(f"Skipping metadata fetch for cryptocurrency {ticker}")
                    country = 'Global'
                    sector = 'Cryptocurrency'
                    industry = 'Digital Currency'
                else:
                    # Try to get additional information from yfinance
                    # Avoid the cookie clearing issue
                    try:
                        import importlib
                        requests_module = importlib.import_module('requests')
                        # Add a clear method to cookies if it doesn't exist
                        if not hasattr(requests_module.cookies, 'clear'):
                            requests_module.cookies.clear = lambda: None
                    except Exception as e:
                        logger.warning(f"Failed to patch requests.cookies: {str(e)}")
                    
                    # Try multiple approaches to get ticker info
                    ticker_obj = yf.Ticker(ticker)
                    info = ticker_obj.info
                    
                    # Extract additional data
                    country = info.get('country')
                    sector = info.get('sector')
                    industry = info.get('industry')
                    
                    # If we couldn't get the data, try a fallback approach
                    if not country or not sector or not industry:
                        logger.info(f"Missing metadata for {ticker}, trying fallback approach")
                        try:
                            # Try to infer data based on ticker patterns
                            if ticker.endswith('.DE'):
                                country = country or 'Germany'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.L'):
                                country = country or 'United Kingdom'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.PA'):
                                country = country or 'France'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.AS'):
                                country = country or 'Netherlands'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.MI'):
                                country = country or 'Italy'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.MC'):
                                country = country or 'Spain'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.SW') or ticker.endswith('.VX'):
                                country = country or 'Switzerland'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.BR'):
                                country = country or 'Belgium'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.VI'):
                                country = country or 'Austria'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.HE'):
                                country = country or 'Finland'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.CO'):
                                country = country or 'Denmark'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.ST'):
                                country = country or 'Sweden'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.OL'):
                                country = country or 'Norway'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.LS'):
                                country = country or 'Portugal'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.AT'):
                                country = country or 'Greece'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.IR'):
                                country = country or 'Ireland'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.PR'):
                                country = country or 'Czech Republic'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.WA'):
                                country = country or 'Poland'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            elif ticker.endswith('.BU'):
                                country = country or 'Hungary'
                                sector = sector or 'Unknown'
                                industry = industry or 'Unknown'
                            else:
                                # For US tickers without suffix
                                if not any(char in ticker for char in ['.', '-', '/']):
                                    country = country or 'United States'
                                    sector = sector or 'Unknown'
                                    industry = industry or 'Unknown'
                        except Exception as e:
                            logger.warning(f"Error in fallback metadata approach for {ticker}: {str(e)}")
                    
                    logger.info(f"Additional data for {ticker}: country={country}, sector={sector}, industry={industry}")
            except Exception as e:
                logger.warning(f"Error fetching additional data for {ticker}: {str(e)}")
                # Continue with None values if we had an error
                country = None
                sector = None
                industry = None
        
        # Prepare result
        result = {
            'success': success,
            'isin': isin,
            'ticker': ticker,
            'price': price,
            'currency': currency,  # Now using actual currency
            'price_eur': price_eur,  # Converted to EUR if needed
            'country': country,     # Include country data
            'sector': sector,       # Include sector data
            'industry': industry,   # Include industry data
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
            logger.info(f"Successfully retrieved price {price} {currency} ({price_eur} EUR) for {isin} (ticker: {ticker}), with country={country}, sector={sector}, industry={industry}")
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
        Dict[str, Any]: Dictionary containing stock information including country, sector, and industry
    """
    logger.info(f"Fetching data for identifier={identifier!r}")
    
    # Get data using our enhanced get_isin_data function which now includes country, sector, and industry
    result = get_isin_data(identifier)
    
    # Extract ticker and additional fields
    ticker = result.get('ticker')
    
    # Format return value for compatibility with expected structure
    response = {
        "success": result['success'],
        "identifier": identifier,
        "ticker": ticker,
        "price": result.get('price'),
        "currency": result.get('currency', 'USD'),
        "price_eur": result.get('price_eur'),
        "country": result.get('country'),  # Use country from get_isin_data
        "sector": result.get('sector'),    # Use sector from get_isin_data
        "industry": result.get('industry'), # Use industry from get_isin_data
        "error": result.get('error'),
        "timestamp": result.get('timestamp')
    }
    
    # Include modified identifier if present
    if 'modified_identifier' in result:
        response['modified_identifier'] = result['modified_identifier']
    
    return response