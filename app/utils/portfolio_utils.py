from flask import session
from app.database.db_manager import query_db, execute_db, backup_database, get_db
from app.utils.db_utils import (
    load_portfolio_data, process_portfolio_dataframe, update_price_in_db
)
from app.utils.yfinance_utils import get_isin_data, get_exchange_rate
from app.utils.data_processing import clear_data_caches
import pandas as pd
import logging
from datetime import datetime
import time
import io

# Set up logger
logger = logging.getLogger(__name__)

def get_portfolio_data(account_id):
    """Get portfolio data from the database"""
    try:
        if not account_id:
            logger.error("Invalid account_id provided to get_portfolio_data: empty or None")
            return []
            
        logger.info(f"Loading portfolio data for account_id: {account_id}")
        
        # First check if the account exists
        account = query_db('SELECT * FROM accounts WHERE id = ?', [account_id], one=True)
        if not account:
            logger.error(f"Account with ID {account_id} not found in database")
            return []
            
        # Then check if any portfolios exist for this account
        portfolios = query_db('SELECT COUNT(*) as count FROM portfolios WHERE account_id = ?', [account_id], one=True)
        if not portfolios or portfolios['count'] == 0:
            logger.error(f"No portfolios found for account_id: {account_id}")
            return []
            
        # Now load the actual portfolio data
        df = load_portfolio_data(account_id)
        
        if df is None:
            logger.error("load_portfolio_data returned None - database query failed")
            return []
        if not df:  # Check if list is empty
            logger.warning(f"No portfolio data found for account_id: {account_id} - empty result set")
            return []
            
        # Convert list of dicts to pandas DataFrame
        df = pd.DataFrame(df)
        
        if df.empty:
            logger.warning("DataFrame is empty after conversion - result structure may be invalid")
            return []
            
        logger.info(f"Raw DataFrame columns: {df.columns.tolist()}")
        logger.info(f"Raw DataFrame shape: {df.shape}")
            
        # Process the DataFrame
        df = process_portfolio_dataframe(df)
        logger.info(f"Processed DataFrame columns: {df.columns.tolist()}")
        logger.info(f"Processed DataFrame shape: {df.shape}")
            
        # Get companies with portfolio names
        companies = query_db('''
            SELECT
                c.id,
                c.name,
                c.identifier,
                c.category,
                COALESCE(cs.shares, 0) as shares,
                COALESCE(cs.override_share, 0) as override_share,
                p.name as portfolio_name
            FROM companies c
            LEFT JOIN company_shares cs ON c.id = cs.company_id
            JOIN portfolios p ON c.portfolio_id = p.id
            WHERE c.account_id = ?
        ''', [account_id])
        
        # Convert DataFrame to dictionary format
        portfolio_data = []
        for _, row in df.iterrows():
            try:
                # Check all column names for debugging
                logger.debug(f"Available columns: {row.index.tolist()}")
                
                # Try both portfolio_name and name variations to be safe
                portfolio_value = ''
                if 'portfolio_name' in row:
                    portfolio_value = row['portfolio_name']
                elif 'portfolio' in row:
                    portfolio_value = row['portfolio']
                
                logger.debug(f"Portfolio value for {row['name']}: '{portfolio_value}'")
                
                item = {
                    'id': row['id'],  # Add the id field
                    'company': row['name'],  # Changed from 'company' to 'name'
                    'identifier': row['identifier'],
                    'portfolio': portfolio_value,  # Use the extracted portfolio value
                    'category': row['category'],
                    'shares': float(row['shares']) if pd.notna(row['shares']) else 0,
                    'override_share': float(row['override_share']) if pd.notna(row['override_share']) else None,
                    'price_eur': float(row['price_eur']) if pd.notna(row['price_eur']) else None,
                    'currency': row['currency'],
                    'country': row['country'] if 'country' in row and pd.notna(row['country']) else None,
                    'industry': row['industry'] if 'industry' in row and pd.notna(row['industry']) else None,
                    'sector': row['sector'] if 'sector' in row and pd.notna(row['sector']) else None,
                    'total_invested': float(row['total_invested']) if pd.notna(row['total_invested']) else 0,
                    'last_updated': row['last_updated'] if isinstance(row['last_updated'], str) else 
                                   (row['last_updated'].isoformat() if pd.notna(row['last_updated']) else None)
                }
                portfolio_data.append(item)
            except Exception as e:
                logger.error(f"Error processing row: {row}")
                logger.error(f"Error details: {str(e)}")
                continue
        
        logger.info(f"Returning {len(portfolio_data)} portfolio items")
        return portfolio_data
    except Exception as e:
        logger.error(f"Error getting portfolio data: {str(e)}", exc_info=True)
        return []

def has_companies_in_default(account_id):
    """Check if the Default portfolio has any companies with shares"""
    default_portfolio = query_db('''
        SELECT id FROM portfolios
        WHERE account_id = ? AND name = 'Default'
    ''', [account_id], one=True)
    
    if default_portfolio:
        # Check if this portfolio has any companies with shares
        companies_count = query_db('''
            SELECT COUNT(*) as count
            FROM companies c
            JOIN company_shares cs ON c.id = cs.company_id
            WHERE c.portfolio_id = ? AND c.account_id = ?
        ''', [default_portfolio['id'], account_id], one=True)
        
        return companies_count and companies_count['count'] > 0
    
    return False

def get_stock_info(identifier):
    """Wrapper for get_isin_data to keep consistent interface"""
    try:
        result = get_isin_data(identifier)
        
        if result['success']:
            return {
                'success': True,
                'data': {
                    'currentPrice': result.get('price'),
                    'currency': result.get('currency', 'USD'),
                    'priceEUR': result.get('price_eur', result.get('price'))
                }
            }
        else:
            return {
                'success': False,
                'error': result.get('error', 'Unknown error')
            }
    except Exception as e:
        logger.error(f"Error in get_stock_info: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

def process_csv_data(account_id, file_content):
    """Process and import CSV data into the database using simple +/- approach"""
    db = None
    cursor = None
    try:
        # Get database connection and cursor
        db = get_db()
        cursor = db.cursor()
        
        # Create backup before making changes
        backup_database()
        
        # Clean data
        df = pd.read_csv(io.StringIO(file_content), 
                         delimiter=';',
                         decimal=',',  # Use comma as decimal separator
                         thousands='.')  # Use dot as thousands separator
        
        # Make column names lowercase for comparison
        df.columns = df.columns.str.lower()
        
        # Define essential columns that must be present
        essential_columns = {
            "identifier": ["identifier", "isin", "symbol"],
            "holdingname": ["holdingname", "name", "securityname"],
            "shares": ["shares", "quantity", "units"],
            "price": ["price", "unitprice", "priceperunit"],
            "type": ["type", "transactiontype"]
        }
        
        # Optional columns with defaults
        optional_columns = {
            "broker": ["broker", "brokername"],
            "assettype": ["assettype", "securitytype"],
            "wkn": ["wkn"],
            "currency": ["currency"],
            "exchange": ["exchange", "market"],
            "date": ["date", "transactiondate", "datetime"],
            "fee": ["fee", "commission", "costs"],
            "tax": ["tax", "taxes"]
        }
        
        # Map columns
        column_mapping = {}
        missing_columns = []
        
        for required_col, alternatives in essential_columns.items():
            found = False
            for alt in alternatives:
                if any(col for col in df.columns if alt in col):
                    matching_col = next(col for col in df.columns if alt in col)
                    column_mapping[required_col] = matching_col
                    found = True
                    break
            if not found:
                missing_columns.append(required_col)
        
        if missing_columns:
            logger.warning(f"Missing essential columns: {missing_columns}")
            return False, f"Missing required columns: {', '.join(missing_columns)}", {}
        
        for opt_col, alternatives in optional_columns.items():
            for alt in alternatives:
                matching_cols = [col for col in df.columns if alt in col]
                if matching_cols and opt_col not in column_mapping:
                    column_mapping[opt_col] = matching_cols[0]
                    break
        
        # Rename columns
        df = df.rename(columns=column_mapping)
        
        # Set defaults
        if 'currency' not in df.columns:
            df['currency'] = 'EUR'
        if 'fee' not in df.columns:
            df['fee'] = 0
        if 'tax' not in df.columns:
            df['tax'] = 0
        if 'date' not in df.columns:
            df['date'] = pd.Timestamp.now()
        
        # Clean data
        df['identifier'] = df['identifier'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
        df['holdingname'] = df['holdingname'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
        
        # Normalized transaction types to handle variations in case and formatting
        def normalize_transaction_type(t):
            if pd.isna(t):
                return 'buy'  # Default to buy if missing
            
            t = str(t).strip().lower()
            # Map similar transaction types to our standard types
            if t in ['buy', 'purchase', 'bought', 'acquire', 'deposit']:
                return 'buy'
            elif t in ['sell', 'sold', 'dispose', 'withdrawal']:
                return 'sell'
            elif t in ['transferin', 'transfer in', 'transfer-in', 'move in', 'movein', 'deposit']:
                return 'transferin'
            elif t in ['transferout', 'transfer out', 'transfer-out', 'move out', 'moveout', 'withdrawal']:
                return 'transferout'
            elif t in ['dividend', 'div', 'dividends', 'income', 'interest']:
                return 'dividend'  # Explicitly recognize dividend transactions
            else:
                # If unknown, default to buy
                logger.warning(f"Unknown transaction type '{t}', defaulting to 'buy'")
                return 'buy'
                
        df['type'] = df['type'].apply(normalize_transaction_type)
        
        # Filter out rows with empty identifiers
        df = df[df['identifier'].str.len() > 0]
        if len(df) == 0:
            return False, "No valid entries found in CSV file", {}
        
        # Convert numeric columns with improved precision
        def convert_numeric(val):
            if pd.isna(val):
                return 0
            if isinstance(val, (int, float)):
                return float(val)
            try:
                val_str = str(val).strip().replace(',', '.')
                return float(val_str)
            except (ValueError, TypeError):
                return 0
        
        df['shares'] = df['shares'].apply(convert_numeric)
        df['price'] = df['price'].apply(convert_numeric)
        df['fee'] = df['fee'].apply(convert_numeric)
        df['tax'] = df['tax'].apply(convert_numeric)
        
        # Remove rows with invalid numeric values
        df = df.dropna(subset=['shares', 'price'])
        if df.empty:
            return False, "No valid entries found in CSV file after converting numeric values", {}
        
        # Convert dates and ensure proper chronological ordering
        try:
            # First try to parse datetime column which is more reliable
            if 'datetime' in df.columns:
                df['parsed_date'] = pd.to_datetime(df['datetime'], errors='coerce')
                # Only fall back to date column for rows where datetime parsing failed
                mask = df['parsed_date'].isna()
                if mask.any():
                    # Try European format first for the date column
                    df.loc[mask, 'parsed_date'] = pd.to_datetime(df.loc[mask, 'date'], format='%d.%m.%Y', errors='coerce')
                    
                    # For any remaining NaT values, try flexible parsing as last resort
                    still_mask = df['parsed_date'].isna()
                    if still_mask.any():
                        df.loc[still_mask, 'parsed_date'] = pd.to_datetime(df.loc[still_mask, 'date'], dayfirst=True, errors='coerce')
            else:
                # No datetime column, so use date column directly
                # First attempt with explicit European format
                df['parsed_date'] = pd.to_datetime(df['date'], format='%d.%m.%Y', errors='coerce')
                
                # For any remaining NaT values, try flexible parsing
                mask = df['parsed_date'].isna()
                if mask.any():
                    df.loc[mask, 'parsed_date'] = pd.to_datetime(df.loc[mask, 'date'], dayfirst=True, errors='coerce')
        except Exception as e:
            logger.warning(f"Error during date parsing: {str(e)}. Falling back to default parsing.")
            # Fallback to more flexible parsing with dayfirst=True to handle European format
            df['parsed_date'] = pd.to_datetime(df['date'], dayfirst=True, errors='coerce')
        
        # Log any remaining NaT values before filling them
        nat_count = df['parsed_date'].isna().sum()
        if nat_count > 0:
            logger.warning(f"{nat_count} dates could not be parsed and will be set to current time")
            
        # Ensure all dates are valid; use current time for invalid dates
        df['parsed_date'] = df['parsed_date'].fillna(pd.Timestamp.now())
        
        # Explicitly ensure we're sorting in ascending order (oldest first)
        df = df.sort_values('parsed_date', ascending=True)
        
        # Debug log to verify sort order
        logger.info(f"Transaction order after sorting:")
        for idx, row in df.iterrows():
            logger.info(f"Processing order: {row['parsed_date']} - {row['type']} - {row['holdingname']} - {row['shares']} shares")
        
        # Initialize company data structure - simplified without FIFO
        company_positions = {}
        
        # Two-pass approach: first buy/transferin, then sell/transferout
        # Separating buys and sells allows us to ensure all buys are processed before sells
        
        # First pass: Process only buy and transferin transactions
        logger.info("FIRST PASS: Processing buy and transferin transactions")
        for idx, row in df.iterrows():
            company_name = row['holdingname']
            transaction_type = row['type']  # Already normalized above
            
            # Skip 'dividend' transactions completely
            if transaction_type == 'dividend':
                logger.info(f"Skipping dividend transaction for {company_name}")
                continue
                
            # ONLY PROCESS BUY AND TRANSFERIN in first pass
            if transaction_type not in ['buy', 'transferin']:
                continue
                
            shares = round(float(row['shares']), 6)  # Round to 6 decimal places for precision
            price = float(row['price'])
            identifier = row['identifier']
            fee = float(row['fee']) if 'fee' in row else 0
            tax = float(row['tax']) if 'tax' in row else 0
            
            # Skip transactions with zero shares
            if shares <= 0:
                logger.info(f"Skipping {transaction_type} transaction with zero shares for {company_name}")
                continue
            
            # Initialize company data if not exists
            if company_name not in company_positions:
                company_positions[company_name] = {
                    'identifier': identifier,
                    'total_shares': 0,         # Total shares 
                    'total_invested': 0        # Total cost basis 
                }
            
            company = company_positions[company_name]
            
            # Calculate transaction amount
            transaction_amount = shares * price
            
            # Add shares and investment
            company['total_shares'] = round(company['total_shares'] + shares, 6)
            company['total_invested'] = round(company['total_invested'] + transaction_amount, 2)
            
            logger.info(f"Buy/TransferIn: {company_name}, +{shares} @ {price}, " 
                       f"total shares: {company['total_shares']}, total invested: {company['total_invested']:.2f}")
        
        # Second pass: Process only sell and transferout transactions
        logger.info("SECOND PASS: Processing sell and transferout transactions")
        for idx, row in df.iterrows():
            company_name = row['holdingname']
            transaction_type = row['type']
            
            # Skip 'dividend' transactions completely
            if transaction_type == 'dividend':
                logger.info(f"Skipping dividend transaction for {company_name}")
                continue
                
            # ONLY PROCESS SELL AND TRANSFEROUT in second pass
            if transaction_type not in ['sell', 'transferout']:
                continue
                
            shares = round(float(row['shares']), 6)
            price = float(row['price'])
            fee = float(row['fee']) if 'fee' in row else 0
            tax = float(row['tax']) if 'tax' in row else 0
            
            # Skip transactions with zero shares
            if shares <= 0:
                logger.info(f"Skipping {transaction_type} transaction with zero shares for {company_name}")
                continue
                
            # Skip if company doesn't exist (should not happen normally)
            if company_name not in company_positions:
                logger.warning(f"Cannot {transaction_type} shares of {company_name} - company not in positions")
                continue
                
            company = company_positions[company_name]
            
            # Log before processing
            logger.info(f"Processing {transaction_type} of {shares} shares for {company_name} (current total: {company['total_shares']}")
            
            # Limit to available shares with a small tolerance for floating point issues
            if shares > (company['total_shares'] + 1e-6):
                logger.warning(f"Attempting to {transaction_type} more shares ({shares}) than available ({company['total_shares']}). Limiting to available shares.")
                shares = company['total_shares']
            
            if shares <= 0:
                logger.info(f"Skipping {transaction_type} with zero or negative shares")
                continue
            
            # Calculate proportion of total investment being sold
            proportion_sold = shares / company['total_shares'] if company['total_shares'] > 0 else 0
            investment_reduction = company['total_invested'] * proportion_sold
            
            # Subtract shares and reduce investment proportionally
            company['total_shares'] = round(company['total_shares'] - shares, 6)
            company['total_invested'] = round(company['total_invested'] - investment_reduction, 2)
            
            # If all shares are sold (or very close to it), zero out both shares and investment
            # This ensures we don't have floating point issues where tiny amounts remain
            if abs(company['total_shares']) < 1e-6 or company['total_shares'] <= 0:
                logger.info(f"All shares sold for {company_name}, zeroing out shares and investment")
                company['total_shares'] = 0
                company['total_invested'] = 0
            
            # We're ignoring fees and taxes as requested
            
            logger.info(f"Sell/TransferOut: {company_name}, -{shares} @ {price}, " 
                       f"remaining shares: {company['total_shares']}, remaining invested: {company['total_invested']:.2f}")
                
            # This additional check is redundant since we now handle zeroing immediately after share calculation
            # Keeping it as a safety net with a more lenient threshold
            if abs(company['total_shares']) < 1e-6 or company['total_shares'] < 0:
                logger.info(f"Zeroing out shares for {company_name}: was {company['total_shares']}, setting to 0")
                company['total_shares'] = 0
                company['total_invested'] = 0
        
        # Start database transaction
        cursor.execute('BEGIN TRANSACTION')
        
        # Ensure default portfolio exists
        default_portfolio = query_db(
            'SELECT id FROM portfolios WHERE name = "-" AND account_id = ?',
            [account_id],
            one=True
        )
        if not default_portfolio:
            cursor.execute(
                'INSERT INTO portfolios (name, account_id) VALUES (?, ?)',
                ['-', account_id]
            )
            default_portfolio_id = cursor.lastrowid
        else:
            default_portfolio_id = default_portfolio['id']
        
        # Get existing companies
        existing_companies = query_db(
            'SELECT id, name, identifier FROM companies WHERE account_id = ?',
            [account_id]
        )
        existing_company_map = {company['name']: company for company in existing_companies}
        
        # Track results
        positions_added = []
        positions_updated = []
        positions_removed = []
        failed_prices = []
        
        # Track all unique company names in CSV for later comparison
        csv_company_names = set(company_positions.keys())
        
        # Update database based on final positions
        for company_name, position in company_positions.items():
            # Handle floating point precision
            current_shares = position['total_shares']
            total_invested = position['total_invested']
            
            # Use a more lenient threshold for zeroing out shares to catch floating point issues
            if abs(current_shares) < 1e-6 or current_shares <= 0:
                logger.info(f"Zeroing out final shares for {company_name}: was {current_shares}, setting to 0")
                current_shares = 0
                total_invested = 0
            else:
                # Keep the precise value, but round for display
                current_shares = round(current_shares, 6)
                total_invested = round(total_invested, 2)
            
            # Skip or remove companies with zero shares (using <= to catch both zero and negative cases)
            # Add extra logging to debug share calculation issues
            logger.info(f"Final share calculation for {company_name}: {current_shares} shares, total_invested: {total_invested}")
            if current_shares <= 0:
                logger.info(f"Company {company_name} has {current_shares} shares - marking for removal or skipping")
                if company_name in existing_company_map:
                    company_id = existing_company_map[company_name]['id']
                    identifier = existing_company_map[company_name]['identifier']
                    
                    # Log before deleting to confirm what's being removed
                    existing_shares = query_db(
                        'SELECT shares FROM company_shares WHERE company_id = ?', 
                        [company_id], 
                        one=True
                    )
                    logger.info(f"Removing company {company_name} (ID: {company_id}) with {existing_shares['shares'] if existing_shares else 0} shares")
                    
                    # Delete from company_shares
                    cursor.execute('DELETE FROM company_shares WHERE company_id = ?', [company_id])
                    
                    # Delete from companies
                    cursor.execute('DELETE FROM companies WHERE id = ?', [company_id])
                    
                    # Only clean up market_prices if no other account uses this identifier
                    if identifier:
                        other_companies_count = query_db(
                            'SELECT COUNT(*) as count FROM companies WHERE identifier = ? AND account_id != ?', 
                            [identifier, account_id],
                            one=True
                        )
                        
                        if other_companies_count and other_companies_count['count'] == 0:
                            logger.info(f"No other accounts use {identifier}, removing from market_prices")
                            cursor.execute('DELETE FROM market_prices WHERE identifier = ?', [identifier])
                    
                    positions_removed.append(company_name)
                continue
            
            # Average cost per share (for information only)
            avg_cost_per_share = total_invested / current_shares if current_shares > 0 else 0
            logger.info(f"Final position: {company_name}, Shares: {current_shares}, " 
                       f"Total Invested: {total_invested:.2f}, Avg Cost: {avg_cost_per_share:.4f}")
            
            # Update or add company
            if company_name in existing_company_map:
                company_id = existing_company_map[company_name]['id']
                # Update company with the new data
                cursor.execute('''
                    UPDATE companies 
                    SET identifier = ?, total_invested = ?
                    WHERE id = ?
                ''', [
                    position['identifier'], 
                    total_invested,
                    company_id
                ])
                
                # Check if company_shares record exists
                share_exists = query_db(
                    'SELECT company_id, shares FROM company_shares WHERE company_id = ?',
                    [company_id],
                    one=True
                )
                
                if share_exists:
                    cursor.execute('''
                        UPDATE company_shares 
                        SET shares = ?
                        WHERE company_id = ?
                    ''', [current_shares, company_id])
                else:
                    cursor.execute('''
                        INSERT INTO company_shares (company_id, shares)
                        VALUES (?, ?)
                    ''', [company_id, current_shares])
                    
                positions_updated.append(company_name)
            else:
                cursor.execute('''
                    INSERT INTO companies (
                        name, identifier, category, portfolio_id, 
                        account_id, total_invested
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', [
                    company_name,
                    position['identifier'],
                    '',
                    default_portfolio_id,
                    account_id,
                    total_invested
                ])
                company_id = cursor.lastrowid
                
                cursor.execute('''
                    INSERT INTO company_shares (company_id, shares)
                    VALUES (?, ?)
                ''', [company_id, current_shares])
                
                positions_added.append(company_name)
        
        # Remove companies that exist in the database but not in the CSV
        # This makes the CSV the single source of truth
        db_company_names = {company['name'] for company in existing_companies}
        companies_to_remove = db_company_names - csv_company_names
        
        for company_name in companies_to_remove:
            company_id = existing_company_map[company_name]['id']
            identifier = existing_company_map[company_name]['identifier']
            
            logger.info(f"Removing company {company_name} (not present in CSV)")
            
            # Delete from company_shares
            cursor.execute('DELETE FROM company_shares WHERE company_id = ?', [company_id])
            
            # Delete from companies
            cursor.execute('DELETE FROM companies WHERE id = ?', [company_id])
            
            # Only clean up market_prices if no other account uses this identifier
            if identifier:
                other_companies_count = query_db(
                    'SELECT COUNT(*) as count FROM companies WHERE identifier = ? AND account_id != ?', 
                    [identifier, account_id],
                    one=True
                )
                
                if other_companies_count and other_companies_count['count'] == 0:
                    logger.info(f"No other accounts use {identifier}, removing from market_prices")
                    cursor.execute('DELETE FROM market_prices WHERE identifier = ?', [identifier])
            
            positions_removed.append(company_name)
        
        # Commit transaction
        db.commit()
        
        # Clear data caches
        clear_data_caches()
        
        # Collect all identifiers that need metadata updates (both new and existing companies)
        all_identifiers = set()
        for company_name in positions_added + positions_updated:
            company = query_db(
                'SELECT id, identifier FROM companies WHERE name = ? AND account_id = ?',
                [company_name, account_id],
                one=True
            )
            if company and company['identifier']:
                all_identifiers.add(company['identifier'])
        
        # Update prices and metadata for all companies (new and existing)
        if all_identifiers:
            logger.info(f"Updating prices and metadata for {len(all_identifiers)} companies")
            
            for i, identifier in enumerate(all_identifiers):
                try:
                    result = get_isin_data(identifier)
                    if result['success'] and result.get('price') is not None:
                        price = result.get('price')
                        currency = result.get('currency', 'USD')
                        price_eur = result.get('price_eur', price)
                        country = result.get('country')
                        sector = result.get('sector')
                        industry = result.get('industry')
                        
                        logger.info(f"Updating metadata for {identifier}: Country: {country}, Sector: {sector}, Industry: {industry}")
                        
                        if not update_price_in_db(identifier, price, currency, price_eur, country, sector, industry):
                            logger.warning(f"Failed to update price and metadata in database for {identifier}")
                            failed_prices.append(identifier)
                    else:
                        error_reason = "No price data returned" if result.get('success') else result.get('error', 'Unknown error')
                        logger.warning(f"Failed to fetch price for {identifier}: {error_reason}")
                        failed_prices.append(identifier)
                except Exception as e:
                    logger.error(f"Error updating price for {identifier}: {str(e)}")
                    failed_prices.append(identifier)
        
        # Prepare message with notification about removed companies
        message = "CSV data imported successfully with simple add/subtract calculation"
        if positions_removed:
            removed_details = ', '.join(positions_removed)
            if len(removed_details) > 100:  # Truncate if too long
                removed_details = removed_details[:97] + '...'
            message += f". <strong>Removed {len(positions_removed)} companies</strong> that had zero shares or were not in the CSV: {removed_details}"
            
        return True, message, {
            'added': positions_added,
            'updated': positions_updated,
            'removed': positions_removed,
            'failed_prices': failed_prices
        }
        
    except Exception as e:
        logger.error(f"Error processing CSV: {str(e)}", exc_info=True)
        if db:
            db.rollback()
        return False, str(e), {}
    finally:
        if cursor:
            cursor.close()
