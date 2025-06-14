from app.database.db_manager import query_db
from app.utils.db_utils import (
    load_portfolio_data, process_portfolio_dataframe
)
from app.utils.yfinance_utils import get_isin_data
import pandas as pd
import logging
from .portfolio_processing import process_csv_data

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

