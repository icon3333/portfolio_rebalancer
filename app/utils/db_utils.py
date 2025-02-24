"""
Database utility functions for data loading and processing.
"""

import logging
import json
import pandas as pd
import numpy as np
from typing import Tuple, Dict, List, Any, Optional
from app.database.db_manager import query_db, execute_db, backup_database
from datetime import datetime, timedelta

# Set up logger
logger = logging.getLogger(__name__)

class PriceFetchManager:
    """Handles all external API interactions for price fetching"""
    def __init__(self):
        self.cache = {}
        self.cache_expiry = {}
        self.failed_isins = set()  # Cache for failed lookups
        self.cache_duration = 300  # 5 minutes in seconds
        
    def get_cached_price(self, isin: str) -> Optional[Tuple[float, str, float]]:
        """Get price from cache or fetch if expired"""
        # Skip invalid ISINs
        if not isinstance(isin, str) or not isin.strip():
            logger.warning("Invalid ISIN format")
            return None, None, None
            
        # Clean and validate ISIN
        try:
            isin = str(isin).strip().upper()
        except:
            logger.warning(f"Could not process ISIN: {isin}")
            return None, None, None
            
        if not isin:
            logger.warning("Empty ISIN")
            return None, None, None
            
        # Check if ISIN is in failed cache
        if isin in self.failed_isins:
            logger.debug(f"Skipping previously failed ISIN: {isin}")
            return None, None, None
            
        now = time.time()
        if isin in self.cache and now < self.cache_expiry.get(isin, 0):
            return self.cache[isin]
            
        result = self.fetch_price_and_currency(isin)
        if result[0] is not None:
            self.cache[isin] = result
            self.cache_expiry[isin] = now + self.cache_duration
        return result

    def fetch_price_and_currency(self, isin: str) -> Tuple[Optional[float], Optional[str], Optional[float]]:
        """Fetch single ISIN price data"""
        logger.debug(f"Fetching price for ISIN: {isin}")
        
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                with self.rate_limiter:
                    yf_data = yf.Ticker(isin)
                    logger.info(f"Getting history for {isin} (attempt {attempt + 1}/{max_retries})")
                    history = yf_data.history(period='5d')  
                    logger.info(f"History data for {isin}: {history if not history.empty else 'Empty'}")
                    
                    if history.empty:
                        logger.info(f"No price data available for {isin}")
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
                            logger.warning(f"No valid price found for {isin}")
                            if attempt < max_retries - 1:
                                time.sleep(retry_delay)
                                continue
                            return None, None, None
                            
                        logger.info(f"Got price for {isin}: {price}")
                        
                        # Try to get currency from yfinance info first
                        try:
                            info = yf_data.info
                            currency = info.get('currency', None)
                            logger.info(f"Got currency from yfinance for {isin}: {currency}")
                        except Exception as e:
                            logger.warning(f"Failed to get currency from yfinance for {isin}: {e}")
                            currency = None
                        
                        # Fall back to USD if no currency info available
                        if not currency:
                            currency = 'USD'  # Default to USD if no currency info available
                            logger.info(f"Using default USD currency for {isin}")
                        
                        # Handle GBp (British pence) to GBP conversion
                        if currency == 'GBp':
                            price = price / 100  # Convert pence to pounds
                            currency = 'GBP'
                            logger.info(f"Converted GBp to GBP for {isin}: {price} GBP")
                        
                        # Calculate EUR price if needed
                        price_eur = price
                        if currency != 'EUR':
                            eur_rate = self._get_eur_rate(currency)
                            if eur_rate is not None:
                                price_eur = price * eur_rate
                                logger.info(f"Converted {isin} price to EUR: {price_eur} (rate: {eur_rate})")
                            else:
                                logger.warning(f"Failed to get EUR rate for {currency}")
                                if attempt < max_retries - 1:
                                    time.sleep(retry_delay)
                                    continue
                                return price, currency, None
                                
                        return price, currency, price_eur
                        
                    except Exception as e:
                        logger.warning(f"Error processing data for {isin}: {str(e)}")
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                            continue
                        return None, None, None
                        
            except Exception as e:
                logger.warning(f"Failed to fetch data for {isin} (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                self.failed_isins.add(isin)
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

    def fetch_batch(self, isins: list, timeout: int = 10) -> Dict[str, Tuple[float, str, float]]:
        """Batch process multiple ISINs with timeout"""
        results = {}
        logger.info(f"Starting batch fetch for {len(isins)} ISINs: {isins}")
        
        with ThreadPoolExecutor(max_workers=10) as executor:
            future_to_isin = {
                executor.submit(self.get_cached_price, isin): isin 
                for isin in isins
                if isin not in self.failed_isins  # Skip known failed ISINs
            }
            
            if len(future_to_isin) != len(isins):
                skipped = set(isins) - {isin for isin in future_to_isin.values()}
                logger.info(f"Skipping {len(skipped)} previously failed ISINs: {skipped}")
            
            for future in as_completed(future_to_isin):
                isin = future_to_isin[future]
                try:
                    result = future.result(timeout=timeout)
                    results[isin] = result
                    if result[0] is not None:
                        logger.info(f"Successfully fetched {isin}: Price={result[0]} {result[1]} (EUR: {result[2]})")
                    else:
                        logger.warning(f"Failed to fetch {isin}: No price data")
                except TimeoutError:
                    logger.warning(f"Timeout fetching {isin}")
                    results[isin] = (None, None, None)
                except Exception as e:
                    logger.error(f"Error fetching {isin}: {str(e)}")
                    results[isin] = (None, None, None)
                    
        return results

# Create a global instance
price_fetcher = PriceFetchManager()

def load_portfolio_data(account_id: int) -> pd.DataFrame:
    """
    Load portfolio data from the database.
    
    Args:
        account_id: Account ID to load data for
        
    Returns:
        DataFrame with portfolio data
    """
    try:
        logger.info(f"Loading portfolio data for account_id: {account_id}")
        
        # Enhanced query with explicit company fields
        data = query_db('''
            SELECT
                c.id,
                c.name AS company,
                c.identifier,
                c.category,
                COALESCE(p.name, '-') AS portfolio,
                COALESCE(cs.shares, 0) AS shares,
                COALESCE(cs.override_share, 0) AS override_share,
                mp.price_eur,
                mp.currency,
                mp.last_updated,
                COALESCE(c.total_invested, 0) AS total_invested
            FROM companies c
            LEFT JOIN company_shares cs ON c.id = cs.company_id
            LEFT JOIN portfolios p ON c.portfolio_id = p.id
            LEFT JOIN market_prices mp ON c.identifier = mp.identifier
            WHERE c.account_id = ?
            ORDER BY c.name
        ''', [account_id])
        
        if not data:
            logger.warning(f"No portfolio data found for account {account_id}")
            logger.info("Checking if account exists...")
            account = query_db('SELECT * FROM accounts WHERE id = ?', [account_id], one=True)
            if account:
                logger.info(f"Account exists: {account['username']}")
            else:
                logger.warning("Account not found in database")
            return pd.DataFrame()
        
        # Convert to DataFrame efficiently
        logger.debug(f"Converting {len(data)} rows to DataFrame")
        df = pd.DataFrame([dict(row) for row in data])
        
        # Process numeric columns efficiently
        numeric_cols = ['shares', 'override_share', 'price_eur', 'total_invested']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Convert last_updated to datetime
        if 'last_updated' in df.columns:
            df['last_updated'] = pd.to_datetime(df['last_updated'], errors='coerce')
        
        logger.info(f"Loaded {len(df)} portfolio items")
        return df
        
    except Exception as e:
        logger.error(f"Error loading portfolio data: {str(e)}", exc_info=True)
        return pd.DataFrame()

def process_portfolio_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Process portfolio data DataFrame"""
    try:
        # Fill missing values
        df['portfolio'] = df['portfolio'].fillna('-')
        df['category'] = df['category'].fillna('-')
        df['shares'] = pd.to_numeric(df['shares'], errors='coerce').fillna(0)
        df['override_share'] = pd.to_numeric(df['override_share'], errors='coerce')
        df['price_eur'] = pd.to_numeric(df['price_eur'], errors='coerce')
        df['total_invested'] = pd.to_numeric(df['total_invested'], errors='coerce').fillna(0)
        
        # Convert last_updated to datetime
        df['last_updated'] = pd.to_datetime(df['last_updated'], errors='coerce')
        
        # Ensure required columns exist
        required_columns = [
            'company', 'identifier', 'portfolio', 'category',
            'shares', 'override_share', 'price_eur', 'currency',
            'total_invested', 'last_updated'
        ]
        for col in required_columns:
            if col not in df.columns:
                df[col] = None
                
        # Add validation for company-specific fields
        required_company_columns = ['company', 'identifier']
        for col in required_company_columns:
            if col not in df.columns:
                df[col] = 'N/A'
                logger.warning(f"Added missing company column: {col}")
        
        return df
    except Exception as e:
        logger.error(f"Error processing DataFrame: {str(e)}", exc_info=True)
        return df

def update_prices(identifiers: List[str], account_id: Optional[int] = None, force_update: bool = False) -> Tuple[Dict[str, Any], List[str]]:
    """
    Get last update time for identifiers from database.
    
    Args:
        identifiers: List of identifiers to check
        account_id: Account ID to update last_price_update field
        force_update: Whether to force update regardless of time since last update
        
    Returns:
        Tuple of (results_dict, failed_identifiers_list)
    """
    if not force_update:
        # Check last update time
        last_updates = query_db('''
            SELECT identifier, last_price_update 
            FROM portfolio 
            WHERE identifier IN ({})
        '''.format(','.join('?' * len(identifiers))), identifiers)
        
        if last_updates:
            now = datetime.now()
            all_recent = True
            for update in last_updates:
                if update['last_price_update']:
                    last_update = datetime.strptime(update['last_price_update'], '%Y-%m-%d %H:%M:%S')
                    if (now - last_update).total_seconds() > 24 * 3600:  # 24 hours
                        all_recent = False
                        break
                else:
                    all_recent = False
                    break
                    
            if all_recent:
                logger.info("Skipping price update - less than 24 hours since last update")
                return {'skipped': len(identifiers)}, []
    
    return {'checked': len(identifiers)}, []

def update_price_in_db(identifier: str, price: float, currency: str, price_eur: float) -> bool:
    """
    Update price in database for a single identifier.
    
    Args:
        identifier: Stock identifier
        price: Price in original currency
        currency: Currency code
        price_eur: Price in EUR
        
    Returns:
        Success status
    """
    try:
        # First try to update existing record
        execute_db('''
            INSERT INTO market_prices (identifier, price, currency, price_eur, last_updated)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(identifier) DO UPDATE SET
                price = excluded.price,
                currency = excluded.currency,
                price_eur = excluded.price_eur,
                last_updated = CURRENT_TIMESTAMP
        ''', [identifier, price, currency, price_eur])
        logger.info(f"Updated price for {identifier}: {price} {currency}")
        return True
    except Exception as e:
        logger.error(f"Error updating price for {identifier}: {str(e)}")
        return False

def calculate_portfolio_composition(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame, float, pd.DataFrame, str]:
    """
    Calculate portfolio and category composition from the provided DataFrame.
    
    Args:
        df: DataFrame containing portfolio data with prices
        
    Returns:
        Tuple containing:
        - portfolio_composition: Portfolio-level aggregations
        - category_composition: Category-level aggregations
        - total_value: Total portfolio value in EUR
        - df_clean: Cleaned DataFrame
        - warning_message: Any warning messages
    """
    logger.info(f"Initial DataFrame shape: {df.shape}")
    warning_message = ""

    # Basic data validation
    required_columns = ['portfolio', 'category', 'price_eur', 'shares', 'override_share']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        # Add missing columns with default values
        for col in missing_columns:
            if col in ['shares', 'override_share', 'price_eur']:
                df[col] = 0.0
            else:
                df[col] = '-'
        warning_message = f"Added missing columns with default values: {missing_columns}"
        logger.warning(warning_message)

    # Check for unassigned portfolios
    companies_without_portfolio = df[df['portfolio'].isin(['-', '', 'nan', None])].shape[0]
    if companies_without_portfolio > 0:
        warning_message = f"{companies_without_portfolio} companies without a defined portfolio. Results may be based on incomplete data."
        logger.warning(warning_message)

    # Filter and clean data
    df_clean = df[~df['portfolio'].isin(['-', '', 'nan', None])].copy()

    if df_clean.empty:
        logger.warning("No data available after filtering unassigned portfolios")
        return None, None, 0, df_clean, warning_message

    # Convert object columns to strings and handle NaN values
    object_columns = df_clean.select_dtypes(include=['object']).columns
    for col in object_columns:
        df_clean[col] = df_clean[col].fillna('-').astype(str)
        df_clean.loc[df_clean[col].str.lower() == 'nan', col] = '-'

    # Calculate effective shares
    df_clean['effective_shares'] = pd.to_numeric(df_clean['override_share'], errors='coerce').fillna(
        pd.to_numeric(df_clean['shares'], errors='coerce').fillna(0)
    )

    # Convert and validate price data
    df_clean['price_eur'] = pd.to_numeric(df_clean['price_eur'], errors='coerce').fillna(0)
    
    # Calculate total values
    df_clean['total_value_eur'] = df_clean['effective_shares'] * df_clean['price_eur']
    
    # Remove rows with zero or invalid values
    df_clean = df_clean[df_clean['total_value_eur'] > 0]
    
    if df_clean.empty:
        logger.warning("All rows were dropped due to invalid calculations")
        return None, None, 0, df_clean, warning_message

    # Calculate total portfolio value
    total_value = df_clean['total_value_eur'].sum()

    # Calculate portfolio composition
    portfolio_composition = (df_clean.groupby('portfolio')
                           .agg({
                               'total_value_eur': 'sum',
                               'company': 'count'
                           })
                           .rename(columns={'company': 'stock_count'})
                           .reset_index())
    
    portfolio_composition['percentage'] = (portfolio_composition['total_value_eur'] / total_value * 100)
    portfolio_composition = portfolio_composition.sort_values('percentage', ascending=False)

    # Calculate category composition
    category_composition = (df_clean.groupby('category')
                          .agg({
                              'total_value_eur': 'sum',
                              'company': 'count'
                          })
                          .rename(columns={'company': 'stock_count'})
                          .reset_index())
    
    category_composition['percentage'] = (category_composition['total_value_eur'] / total_value * 100)
    category_composition = category_composition.sort_values('percentage', ascending=False)

    # Log results
    logger.info(f"Final portfolio composition calculated: {len(portfolio_composition)} portfolios")
    logger.info(f"Final category composition calculated: {len(category_composition)} categories")
    logger.info(f"Total portfolio value: €{total_value:,.2f}")

    return portfolio_composition, category_composition, total_value, df_clean, warning_message

def get_portfolios(account_id):
    """Get list of portfolios for an account"""
    portfolios = query_db('''
        SELECT id, name
        FROM portfolios
        WHERE account_id = ?
        ORDER BY name
    ''', [account_id])
    
    return [{'id': p['id'], 'name': p['name']} for p in portfolios]

def save_state(account_id: int, page_name: str, variable_name: str, variable_value: Any, variable_type: str) -> bool:
    """
    Save state to the expanded_state table.
    
    Args:
        account_id: Account ID
        page_name: Page name
        variable_name: Variable name
        variable_value: Variable value (will be JSON serialized)
        variable_type: Variable type
        
    Returns:
        Success status
    """
    try:
        # Convert value to JSON string if it's not already a string
        if not isinstance(variable_value, str):
            variable_value = json.dumps(variable_value)
        
        # Check if state exists
        existing = query_db(
            '''SELECT id FROM expanded_state 
               WHERE account_id = ? AND page_name = ? AND variable_name = ?''',
            [account_id, page_name, variable_name],
            one=True
        )
        
        if existing:
            # Update existing state
            execute_db(
                '''UPDATE expanded_state 
                   SET variable_value = ?, variable_type = ? 
                   WHERE id = ?''',
                [variable_value, variable_type, existing['id']]
            )
        else:
            # Insert new state
            execute_db(
                '''INSERT INTO expanded_state 
                   (account_id, page_name, variable_name, variable_type, variable_value)
                   VALUES (?, ?, ?, ?, ?)''',
                [account_id, page_name, variable_name, variable_type, variable_value]
            )
            
        return True
        
    except Exception as e:
        logger.error(f"Error saving state: {str(e)}")
        return False

def load_state(account_id: int, page_name: str, variable_name: str, default_value: Any, variable_type: str) -> Any:
    """
    Load state from the expanded_state table.
    
    Args:
        account_id: Account ID
        page_name: Page name
        variable_name: Variable name
        default_value: Default value if state doesn't exist
        variable_type: Expected variable type
        
    Returns:
        State value or default value
    """
    try:
        result = query_db(
            '''SELECT variable_value, variable_type 
               FROM expanded_state 
               WHERE account_id = ? AND page_name = ? AND variable_name = ?''',
            [account_id, page_name, variable_name],
            one=True
        )
        
        if not result:
            return default_value
            
        # Parse JSON value based on type
        value = result['variable_value']
        
        if variable_type in ['dict', 'list', 'object']:
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                logger.warning(f"Failed to decode JSON for {page_name}.{variable_name}")
                return default_value
        elif variable_type == 'int':
            try:
                return int(value)
            except ValueError:
                return default_value
        elif variable_type == 'float':
            try:
                return float(value)
            except ValueError:
                return default_value
        elif variable_type == 'bool':
            return value.lower() in ('true', 't', 'yes', 'y', '1')
        else:
            # Return as string
            return value
            
    except Exception as e:
        logger.error(f"Error loading state: {str(e)}")
        return default_value

def process_csv_data(account_id: int, file_content: str) -> Tuple[bool, str, Dict]:
    """
    Process CSV data and import to database.
    
    Args:
        account_id: Account ID
        file_content: CSV file content
        
    Returns:
        Tuple of (success, message, results_dict)
    """
    try:
        import io
        import pandas as pd
        
        # Create backup before making changes
        backup_database()
        
        # Parse CSV
        df = pd.read_csv(io.StringIO(file_content), delimiter=';')
        
        # Make column names lowercase and remove spaces/underscores for comparison
        df.columns = df.columns.str.lower()
        df.columns = df.columns.str.replace(' ', '').str.replace('_', '')
        
        # Define essential columns that must be present
        essential_columns = {
            "identifier": ["identifier", "isin", "symbol"],
            "holdingname": ["holdingname", "name", "securityname"],
            "shares": ["shares", "quantity", "units"],
            "price": ["price", "unitprice", "priceperunit"]
        }
        
        # Optional columns with defaults
        optional_columns = {
            "type": ["type", "transactiontype"],
            "broker": ["broker", "brokername"],
            "assettype": ["assettype", "type", "securitytype"],
            "wkn": ["wkn"],
            "currency": ["currency"],
            "exchange": ["exchange", "market"]
        }
        
        # Try to map essential columns first
        column_mapping = {}
        missing_columns = []
        
        # Try to find matching columns for essential fields
        for required_col, alternatives in essential_columns.items():
            found = False
            for alt in alternatives:
                for col in df.columns:
                    if alt in col:
                        column_mapping[required_col] = col
                        found = True
                        break
                if found:
                    break
            
            if not found:
                missing_columns.append(required_col)
        
        # Check for essential columns
        if missing_columns:
            logger.warning(f"Missing essential columns: {missing_columns}")
            return False, f"Missing required columns: {', '.join(missing_columns)}", {}
        
        # Try to map optional columns
        for opt_col, alternatives in optional_columns.items():
            for alt in alternatives:
                for col in df.columns:
                    if alt in col and opt_col not in column_mapping:
                        column_mapping[opt_col] = col
                        break
        
        # Log found columns
        logger.info(f"Found columns: {column_mapping}")
        
        # Rename columns to match our format
        df = df.rename(columns=column_mapping)
        
        # Set default values for missing optional columns
        if 'type' not in df.columns:
            df['type'] = 'Buy'  # Default to Buy type
        if 'currency' not in df.columns:
            df['currency'] = 'EUR'  # Default to EUR
        
        # Filter to valid transaction types
        valid_types = ['Buy', 'Sell', 'TransferOut', 'TransferIn']
        df['type'] = df['type'].str.strip()
        ignored_types = df[~df['type'].isin(valid_types)]['type'].unique().tolist()
        df = df[df['type'].isin(valid_types)]
        
        if df.empty:
            return False, "No valid transactions found in CSV file", {}
        
        # Clean data
        df['identifier'] = df['identifier'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
        df['holdingname'] = df['holdingname'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
        df = df[df['identifier'].str.len() > 0]
        
        if df.empty:
            return False, "No valid entries found in CSV file after cleaning", {}
        
        # Process numeric values
        def process_value(value):
            try:
                if pd.isna(value):
                    return 0.0
                
                if isinstance(value, (int, float)):
                    return float(value)
                
                value_str = str(value).strip()
                
                # Remove any currency symbols and thousand separators
                currency_symbols = ['€', '£', '¥', '$']
                for symbol in currency_symbols:
                    value_str = value_str.replace(symbol, '')
                value_str = value_str.replace(',', '')  # Remove thousand separators
                
                # Try to convert directly first
                try:
                    return float(value_str)
                except ValueError:
                    pass
                
                # If that fails, try more aggressive cleaning
                # Keep only valid number characters (digits, decimal point, minus sign)
                value_str = ''.join(c for c in value_str if c.isdigit() or c in '.-')
                
                # Handle case of multiple decimal points
                parts = value_str.split('.')
                if len(parts) > 2:  # Multiple decimal points
                    value_str = parts[0] + '.' + parts[1]  # Keep only first decimal point
                
                # Log the value transformation
                logger.debug(f"Converting value: original='{value}', cleaned='{value_str}'")
                
                return float(value_str) if value_str else 0.0
            except Exception as e:
                logger.warning(f"Failed to convert value '{value}' to float: {str(e)}")
                return 0.0
        
        # Add debug logging for raw values
        logger.info("Raw transaction data before processing:")
        for _, row in df.iterrows():
            logger.info(f"Type: {row['type']}, Shares: {row['shares']}, Price: {row['price']}, Holding: {row['holdingname']}")
        
        df['shares'] = df['shares'].apply(process_value)
        df['price'] = df['price'].apply(process_value)
        
        # Calculate share effects
        df['shares_effect'] = df.apply(
            lambda row: row['shares'] if row['type'] in ['Buy', 'TransferIn'] else -row['shares'],
            axis=1
        )
        df['total_invested_effect'] = df['shares_effect'] * df['price']
        
        # Aggregate data
        aggregated_data = df.groupby(['holdingname', 'identifier']).agg({
            'shares_effect': 'sum',
            'total_invested_effect': 'sum'
        }).reset_index()
        
        # Process aggregated data
        with get_db_connection() as db:
            cursor = db.cursor()
            try:
                cursor.execute("BEGIN TRANSACTION")
                
                # Ensure default portfolio exists
                cursor.execute(
                    "SELECT id FROM portfolios WHERE name = '-' AND account_id = ?",
                    [account_id]
                )
                default_portfolio = cursor.fetchone()
                
                if not default_portfolio:
                    cursor.execute(
                        "INSERT INTO portfolios (name, account_id) VALUES (?, ?)",
                        ['-', account_id]
                    )
                    default_portfolio_id = cursor.lastrowid
                else:
                    default_portfolio_id = default_portfolio['id']
                
                # Initialize tracking
                positions_added = []
                positions_updated = []
                positions_removed = []
                failed_companies = []
                
                # Process each company
                for _, row in aggregated_data.iterrows():
                    try:
                        company_name = row['holdingname']
                        share_count = float(row['shares_effect'])
                        total_invested = float(row['total_invested_effect'])
                        
                        # Handle floating point precision
                        if abs(share_count) < 1e-10:
                            share_count = 0
                            total_invested = 0
                        
                        # Check if company exists
                        cursor.execute(
                            "SELECT id FROM companies WHERE name = ? AND account_id = ?",
                            [company_name, account_id]
                        )
                        company = cursor.fetchone()
                        
                        if share_count <= 0:
                            # Remove company if it exists and shares are zero/negative
                            if company:
                                # Delete shares first (foreign key constraint)
                                cursor.execute(
                                    "DELETE FROM company_shares WHERE company_id = ?",
                                    [company['id']]
                                )
                                # Then delete company
                                cursor.execute(
                                    "DELETE FROM companies WHERE id = ?",
                                    [company['id']]
                                )
                                positions_removed.append(company_name)
                            continue
                        
                        if company:
                            # Update existing company
                            cursor.execute(
                                """UPDATE companies 
                                   SET total_invested = ?
                                   WHERE id = ?""",
                                [total_invested, company['id']]
                            )
                            
                            # Check if shares record exists
                            cursor.execute(
                                "SELECT 1 FROM company_shares WHERE company_id = ?",
                                [company['id']]
                            )
                            if cursor.fetchone():
                                cursor.execute(
                                    """UPDATE company_shares 
                                       SET shares = ?
                                       WHERE company_id = ?""",
                                    [share_count, company['id']]
                                )
                            else:
                                cursor.execute(
                                    """INSERT INTO company_shares (company_id, shares)
                                       VALUES (?, ?)""",
                                    [company['id'], share_count]
                                )
                                
                            positions_updated.append(company_name)
                        else:
                            # Insert new company
                            cursor.execute(
                                """INSERT INTO companies 
                                   (name, identifier, category, portfolio_id, account_id, total_invested)
                                   VALUES (?, ?, ?, ?, ?, ?)""",
                                [
                                    company_name,
                                    row['identifier'],
                                    '',  # Empty category
                                    default_portfolio_id,
                                    account_id,
                                    total_invested
                                ]
                            )
                            
                            company_id = cursor.lastrowid
                            
                            # Insert shares
                            cursor.execute(
                                """INSERT INTO company_shares (company_id, shares)
                                   VALUES (?, ?)""",
                                [company_id, share_count]
                            )
                            
                            positions_added.append(company_name)
                            
                    except Exception as e:
                        logger.error(f"Failed to process company {row['holdingname']}: {str(e)}")
                        failed_companies.append(row['holdingname'])
                
                # Commit transaction
                db.commit()
                
                # Update prices for new/updated companies
                isins_to_update = []
                if positions_added:
                    isins_to_update.extend([
                        row['identifier'] for _, row in aggregated_data.iterrows()
                        if row['holdingname'] in positions_added
                    ])
                
                price_update_results = {'success': 0, 'failed': 0, 'skipped': 0}
                failed_price_isins = []
                
                if isins_to_update:
                    price_update_results, failed_price_isins = update_prices(
                        isins_to_update, account_id, force_update=True
                    )
                
                # Prepare result
                results = {
                    'added': positions_added,
                    'updated': positions_updated,
                    'removed': positions_removed,
                    'failed': failed_companies,
                    'price_update': price_update_results,
                    'failed_prices': failed_price_isins
                }
                
                # Create success message
                messages = []
                if positions_added:
                    messages.append(f"Added {len(positions_added)} new positions")
                if positions_updated:
                    messages.append(f"Updated {len(positions_updated)} existing positions")
                if positions_removed:
                    messages.append(f"Removed {len(positions_removed)} positions with zero/negative shares")
                if price_update_results['success'] > 0:
                    messages.append(f"Updated prices for {price_update_results['success']} positions")
                
                success_message = ". ".join(messages) if messages else "CSV imported successfully"
                
                # Add warnings
                warnings = []
                if failed_companies:
                    warnings.append(f"Failed to process {len(failed_companies)} companies")
                if failed_price_isins:
                    warnings.append(f"Failed to fetch prices for {len(failed_price_isins)} ISINs")
                if ignored_types:
                    warnings.append(f"Ignored transaction types: {', '.join(ignored_types)}")
                
                warning_message = ". ".join(warnings) if warnings else None
                
                return True, success_message, results
                
            except Exception as e:
                db.rollback()
                logger.error(f"Database error while processing CSV: {str(e)}")
                return False, f"Database error: {str(e)}", {}
                
    except Exception as e:
        logger.error(f"Error processing CSV: {str(e)}")
        return False, f"Error processing CSV: {str(e)}", {}