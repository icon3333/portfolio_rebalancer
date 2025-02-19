"""
Database utility functions for data loading and processing.
"""

import logging
import json
import pandas as pd
import numpy as np
from typing import Tuple, Dict, List, Any, Optional
from app.database.db_manager import query_db, execute_db, backup_database
from app.utils.price_fetcher import price_fetcher

# Set up logger
logger = logging.getLogger(__name__)

def load_portfolio_data(account_id: int) -> pd.DataFrame:
    """
    Load portfolio data from the database.
    
    Args:
        account_id: Account ID to load data for
        
    Returns:
        DataFrame with portfolio data
    """
    try:
        # Query portfolio data
        data = query_db('''
            SELECT 
                c.name AS company,
                c.ticker,
                c.isin,
                p.name AS portfolio,
                c.category,
                cs.shares,
                cs.override_share,
                mp.price_eur,
                mp.currency,
                mp.last_updated,
                c.total_invested
            FROM companies c
            LEFT JOIN company_shares cs ON c.id = cs.company_id
            LEFT JOIN portfolios p ON c.portfolio_id = p.id
            LEFT JOIN market_prices mp ON c.ticker = mp.ticker
            WHERE c.account_id = ?
        ''', [account_id])
        
        if not data:
            logger.info(f"No portfolio data found for account {account_id}")
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(data)
        
        # Process data
        df = process_portfolio_dataframe(df)
        
        return df
        
    except Exception as e:
        logger.error(f"Error loading portfolio data: {str(e)}")
        return pd.DataFrame()

def process_portfolio_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Process portfolio DataFrame to ensure consistent data.
    
    Args:
        df: Raw portfolio DataFrame
        
    Returns:
        Processed DataFrame
    """
    if df.empty:
        return df
    
    # Ensure columns exist
    required_columns = [
        'company', 'ticker', 'portfolio', 'category', 
        'shares', 'override_share', 'price_eur', 'currency',
        'last_updated', 'total_invested'
    ]
    
    for col in required_columns:
        if col not in df.columns:
            df[col] = None
    
    # Replace missing values with defaults
    df['portfolio'] = df['portfolio'].fillna('-')
    df['category'] = df['category'].fillna('-')
    
    # Calculate effective shares
    df['effective_shares'] = df.apply(
        lambda row: row['override_share'] if pd.notna(row['override_share']) and row['override_share'] > 0 
                    else row['shares'] if pd.notna(row['shares']) else 0,
        axis=1
    )
    
    # Calculate total value
    df['total_value_eur'] = df.apply(
        lambda row: row['effective_shares'] * row['price_eur'] if pd.notna(row['price_eur']) else 0,
        axis=1
    )
    
    return df

def update_prices(
    tickers: List[str], 
    account_id: Optional[int] = None, 
    force_update: bool = False
) -> Tuple[Dict[str, int], List[str]]:
    """
    Update prices for the given tickers.
    
    Args:
        tickers: List of tickers to update prices for
        account_id: Account ID to update last_price_update field
        force_update: Whether to force update regardless of time since last update
        
    Returns:
        Tuple of (results_dict, failed_tickers_list)
    """
    try:
        # Initialize counters
        results = {
            'success': 0,
            'failed': 0,
            'skipped': 0
        }
        failed_tickers = []
        
        # Skip update if not forced and last update was recent
        if not force_update and account_id:
            last_update = query_db(
                'SELECT last_price_update FROM accounts WHERE id = ?', 
                [account_id],
                one=True
            )
            
            if last_update and last_update['last_price_update']:
                from datetime import datetime, timedelta
                last_update_time = datetime.strptime(last_update['last_price_update'], '%Y-%m-%d %H:%M:%S')
                if datetime.now() - last_update_time < timedelta(hours=24):
                    logger.info("Skipping price update - less than 24 hours since last update")
                    results['skipped'] = len(tickers)
                    return results, failed_tickers
        
        # Process in batches to avoid rate limiting
        BATCH_SIZE = 5
        total_batches = (len(tickers) + BATCH_SIZE - 1) // BATCH_SIZE
        
        for batch_num in range(total_batches):
            start_idx = batch_num * BATCH_SIZE
            end_idx = min(start_idx + BATCH_SIZE, len(tickers))
            batch_tickers = tickers[start_idx:end_idx]
            
            logger.info(f"Processing batch {batch_num + 1}/{total_batches}: {batch_tickers}")
            
            # Fetch batch prices
            batch_results = price_fetcher.fetch_batch(batch_tickers)
            
            for ticker, (price, currency, price_eur) in batch_results.items():
                if price is not None:
                    # Update price in database
                    success = update_price_in_db(ticker, price, currency, price_eur)
                    if success:
                        results['success'] += 1
                        logger.info(f"Updated price for {ticker}: {price} {currency} (EUR: {price_eur})")
                    else:
                        results['failed'] += 1
                        failed_tickers.append(ticker)
                        logger.warning(f"Failed to update price in database for {ticker}")
                else:
                    results['failed'] += 1
                    failed_tickers.append(ticker)
                    logger.warning(f"Failed to fetch price for {ticker}")
        
        # Update last price update timestamp for account
        if account_id:
            from datetime import datetime
            execute_db(
                'UPDATE accounts SET last_price_update = ? WHERE id = ?',
                [datetime.now().strftime('%Y-%m-%d %H:%M:%S'), account_id]
            )
            
        return results, failed_tickers
            
    except Exception as e:
        logger.error(f"Error updating prices: {str(e)}")
        return {'success': 0, 'failed': len(tickers), 'skipped': 0}, tickers

def update_price_in_db(ticker: str, price: float, currency: str, price_eur: float) -> bool:
    """
    Update price in database for a single ticker.
    
    Args:
        ticker: Ticker symbol
        price: Price in original currency
        currency: Currency code
        price_eur: Price in EUR
        
    Returns:
        Success status
    """
    try:
        from datetime import datetime
        
        # Update or insert price
        execute_db('''
            INSERT OR REPLACE INTO market_prices 
            (ticker, price, currency, price_eur, last_updated)
            VALUES (?, ?, ?, ?, ?)
        ''', [
            ticker,
            price,
            currency,
            price_eur,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        ])
        
        return True
        
    except Exception as e:
        logger.error(f"Error updating price in database for {ticker}: {str(e)}")
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
        from app.utils.price_fetcher import isin_to_ticker
        
        # Create backup before making changes
        backup_database()
        
        # Parse CSV
        df = pd.read_csv(io.StringIO(file_content), delimiter=';')
        
        # Validate required columns
        required_columns = [
            "datetime", "date", "time", "price", "shares", "amount", "tax", 
            "fee", "realizedgains", "type", "broker", "assettype", "identifier",
            "wkn", "originalcurrency", "currency", "fxrate", "holding",
            "holdingname", "holdingnickname", "exchange", "avgholdingperiod"
        ]
        
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return False, f"Missing required columns: {', '.join(missing_columns)}", {}
        
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
        
        # Convert identifiers to tickers
        unique_identifiers = df['identifier'].unique().tolist()
        ticker_results = isin_to_ticker(unique_identifiers)
        
        # Add ticker column
        df['ticker'] = df['identifier'].map(ticker_results)
        
        # Remove rows with failed ticker resolution
        df = df[~df['ticker'].str.contains('Error|No data found|Invalid', na=False)]
        
        if df.empty:
            return False, "No valid entries remained after identifier resolution", {}
        
        # Process numeric values
        def process_value(value):
            if isinstance(value, (int, float)):
                return float(value)
            
            value_str = str(value).strip()
            # Remove currency symbols first
            currency_symbols = ['€', '£', '¥', '$']
            for symbol in currency_symbols:
                value_str = value_str.replace(symbol, '')
            
            # Clean and standardize the number format
            value_str = value_str.replace(',', '.')
            
            # Keep only valid number characters (digits, decimal point, minus sign)
            value_str = ''.join(c for c in value_str if c.isdigit() or c in '.-')
            
            # Handle case of multiple decimal points
            parts = value_str.split('.')
            if len(parts) > 2:  # Multiple decimal points
                value_str = parts[0] + '.' + parts[1]  # Keep only first decimal point
            
            return float(value_str) if value_str else 0
        
        df['shares'] = df['shares'].apply(process_value)
        df['price'] = df['price'].apply(process_value)
        
        # Calculate share effects
        df['shares_effect'] = df.apply(
            lambda row: row['shares'] if row['type'] in ['Buy', 'TransferIn'] else -row['shares'],
            axis=1
        )
        df['total_invested_effect'] = df['shares_effect'] * df['price']
        
        # Aggregate data
        aggregated_data = df.groupby(['holdingname', 'identifier', 'ticker']).agg({
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
                        ticker = row['ticker']
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
                                   SET ticker = ?, total_invested = ?
                                   WHERE id = ?""",
                                [ticker, total_invested, company['id']]
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
                                   (name, ticker, isin, category, portfolio_id, account_id, total_invested)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                [
                                    company_name,
                                    ticker,
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
                tickers_to_update = []
                if positions_added:
                    tickers_to_update.extend([
                        row['ticker'] for _, row in aggregated_data.iterrows()
                        if row['holdingname'] in positions_added
                    ])
                
                price_update_results = {'success': 0, 'failed': 0, 'skipped': 0}
                failed_price_tickers = []
                
                if tickers_to_update:
                    price_update_results, failed_price_tickers = update_prices(
                        tickers_to_update, account_id, force_update=True
                    )
                
                # Prepare result
                results = {
                    'added': positions_added,
                    'updated': positions_updated,
                    'removed': positions_removed,
                    'failed': failed_companies,
                    'price_update': price_update_results,
                    'failed_prices': failed_price_tickers
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
                if failed_price_tickers:
                    warnings.append(f"Failed to fetch prices for {len(failed_price_tickers)} tickers")
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