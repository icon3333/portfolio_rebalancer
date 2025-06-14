import logging
import yfinance as yf
import requests
from datetime import datetime
from typing import Dict, Any, Optional
import warnings

# Suppress specific yfinance warnings that might clutter the logs
warnings.filterwarnings("ignore", message="^[Tt]he 'period'")
def find_ticker_for_isin(isin: str) -> str:
    """
    Find ticker symbol for an ISIN using direct yfinance approach.
    With fallback for when the standard approach fails.
    """
    logger.info(f"Finding ticker for ISIN: {isin}")
    
   
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
    try:
        session = requests.Session()
        # Add headers but don't use the update method to avoid the cookies.update error
        session.headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        session.headers['Accept'] = 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8'
        session.headers['Accept-Language'] = 'en-US,en;q=0.9'
        session.headers['Connection'] = 'keep-alive'
        return session
    except Exception as e:
        logger.warning(f"Error creating session: {str(e)}")
        return None


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



# wrappers for moved functions
from . import yfinance_price as _price

def get_price_for_ticker(ticker: str) -> Dict[str, Any]:
    return _price.get_price_for_ticker(ticker)


def get_crypto_price(crypto_ticker: str) -> Dict[str, Any]:
    return _price.get_crypto_price(crypto_ticker)


def get_exchange_rate(from_currency: str, to_currency: str = "EUR") -> float:
    return _price.get_exchange_rate(from_currency, to_currency)

from . import yfinance_history as _history

def get_enhanced_historical_data(identifiers, years=5):
    return _history.get_enhanced_historical_data(identifiers, years)

def get_historical_prices(identifiers, years=5):
    return _history.get_historical_prices(identifiers, years)

def get_historical_returns(identifiers, years=5, freq="W"):
    return _history.get_historical_returns(identifiers, years, freq)

