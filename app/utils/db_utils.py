# app/utils/db_utils.py
import logging
from datetime import datetime
from app.database.db_manager import query_db, execute_db

logger = logging.getLogger(__name__)

def update_price_in_db(identifier: str, price: float, currency: str, price_eur: float) -> bool:
    """
    Update price in database for a single identifier.
    
    Args:
        identifier: Stock identifier (ISIN)
        price: Price in original currency
        currency: Currency code
        price_eur: Price in EUR
        
    Returns:
        Success status
    """
    try:
        if not identifier or price is None:
            logger.warning(f"Missing identifier or price: {identifier}, {price}")
            return False
            
        now = datetime.now().isoformat()
        
        # Check if the record exists
        existing = query_db(
            'SELECT 1 FROM market_prices WHERE identifier = ?',
            [identifier],
            one=True
        )
        
        if existing:
            # Update existing record
            execute_db('''
                UPDATE market_prices 
                SET price = ?, currency = ?, price_eur = ?, last_updated = ?
                WHERE identifier = ?
            ''', [price, currency, price_eur, now, identifier])
        else:
            # Insert new record
            execute_db('''
                INSERT INTO market_prices 
                (identifier, price, currency, price_eur, last_updated)
                VALUES (?, ?, ?, ?, ?)
            ''', [identifier, price, currency, price_eur, now])
        
        # Update last_price_update in accounts table for all accounts that have this identifier
        execute_db('''
            UPDATE accounts 
            SET last_price_update = ? 
            WHERE id IN (
                SELECT DISTINCT account_id 
                FROM companies 
                WHERE identifier = ?
            )
        ''', [now, identifier])
        
        logger.info(f"Successfully updated price for {identifier}: {price} {currency} ({price_eur} EUR)")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update price in database for {identifier}: {str(e)}")
        return False

def get_portfolios(account_id):
    """Get list of portfolios for an account"""
    try:
        portfolios = query_db('''
            SELECT id, name
            FROM portfolios
            WHERE account_id = ?
            ORDER BY name
        ''', [account_id])
        
        return [{'id': p['id'], 'name': p['name']} for p in portfolios]
    except Exception as e:
        logger.error(f"Error getting portfolios: {str(e)}")
        return []

def load_portfolio_data(account_id=None, portfolio_id=None):
    """
    Load portfolio data from the database.
    
    Args:
        account_id: Optional account ID to filter by
        portfolio_id: Optional portfolio ID to filter by
        
    Returns:
        List of portfolio items
    """
    try:
        params = []
        query = '''
            SELECT c.*, cs.shares, cs.override_share, mp.price, mp.currency, mp.price_eur, mp.last_updated,
                   p.name as portfolio_name
            FROM companies c
            LEFT JOIN company_shares cs ON c.id = cs.company_id
            LEFT JOIN market_prices mp ON c.identifier = mp.identifier
            LEFT JOIN portfolios p ON c.portfolio_id = p.id
            WHERE 1=1
        '''
        
        if account_id:
            query += ' AND c.account_id = ?'
            params.append(account_id)
            
        if portfolio_id:
            query += ' AND c.portfolio_id = ?'
            params.append(portfolio_id)
            
        return query_db(query, params)
        
    except Exception as e:
        logger.error(f"Error loading portfolio data: {str(e)}")
        return []

def process_portfolio_dataframe(df, account_id=None, portfolio_id=None):
    """
    Process a portfolio dataframe and calculate additional metrics.
    
    Args:
        df: Pandas DataFrame with portfolio data
        account_id: Optional account ID to filter by
        portfolio_id: Optional portfolio ID to filter by
        
    Returns:
        Processed DataFrame with additional columns
    """
    try:
        if df.empty:
            return df
            
        # Make a copy to avoid SettingWithCopyWarning
        df = df.copy()
        
        # Calculate value in EUR
        df['value_eur'] = df.apply(
            lambda row: row.get('quantity', 0) * row.get('price_eur', 0) 
            if row.get('price_eur') is not None else 0, 
            axis=1
        )
        
        # Calculate value in original currency
        df['value'] = df.apply(
            lambda row: row.get('quantity', 0) * row.get('price', 0) 
            if row.get('price') is not None else 0, 
            axis=1
        )
        
        # Calculate totals
        total_value_eur = df['value_eur'].sum()
        
        # Calculate portfolio weights
        if total_value_eur > 0:
            df['weight'] = df['value_eur'] / total_value_eur
        else:
            df['weight'] = 0
            
        return df
        
    except Exception as e:
        logger.error(f"Error processing portfolio dataframe: {str(e)}")
        return df

def update_batch_prices_in_db(results):
    """Update market prices with results from batch processing."""
    success_count = 0
    failed_count = 0
    
    try:
        for isin, result in results.items():
            if result.get('success') and result.get('price') is not None:
                success = update_price_in_db(
                    isin,
                    result.get('price'),
                    result.get('currency', 'USD'),
                    result.get('price_eur', result.get('price'))
                )
                
                if success:
                    success_count += 1
                else:
                    failed_count += 1
        
        logger.info(f"Batch update complete. Success: {success_count}, Failed: {failed_count}")
        return True
    except Exception as e:
        logger.error(f"Error updating batch prices in database: {str(e)}")
        return False

def update_prices(portfolio_items, get_price_function=None):
    """
    Update prices for portfolio items.
    
    Args:
        portfolio_items: List of portfolio items
        get_price_function: Optional function to get price for an identifier
        
    Returns:
        Tuple of (updated items, success count, failure count)
    """
    if not portfolio_items:
        return [], 0, 0
        
    success_count = 0
    failure_count = 0
    updated_items = []
    
    for item in portfolio_items:
        identifier = item.get('identifier')
        if not identifier:
            failure_count += 1
            updated_items.append(item)
            continue
            
        if get_price_function:
            # Use provided price function
            success, price_data = get_price_function(identifier)
        else:
            # Use default implementation
            from app.utils.yfinance_utils import get_isin_data
            result = get_isin_data(identifier)
            success = result.get('success', False)
            price_data = result if success else None
            
        if success and price_data:
            # Extract price details from result
            price = price_data.get('price')
            currency = price_data.get('currency', 'USD')
            price_eur = price_data.get('price_eur', price)
            
            # Update database
            updated = update_price_in_db(
                identifier, price, currency, price_eur
            )
            
            if updated:
                # Update item with new price
                item['price'] = price
                item['currency'] = currency
                item['price_eur'] = price_eur
                item['last_updated'] = datetime.now().isoformat()
                success_count += 1
            else:
                failure_count += 1
        else:
            failure_count += 1
            
        updated_items.append(item)
        
    return updated_items, success_count, failure_count

def calculate_portfolio_composition(portfolio_data):
    """
    Calculate portfolio composition metrics.
    
    Args:
        portfolio_data: List of portfolio items or DataFrame
        
    Returns:
        Dictionary with portfolio metrics
    """
    import pandas as pd
    
    try:
        # Convert to DataFrame if list
        if isinstance(portfolio_data, list):
            df = pd.DataFrame(portfolio_data)
        else:
            df = portfolio_data
            
        if df.empty:
            return {
                'total_value_eur': 0,
                'holdings_count': 0,
                'holdings_by_currency': {},
                'holdings_by_type': {},
                'sectors': {}
            }
            
        # Calculate total portfolio value in EUR
        total_value_eur = df['value_eur'].sum() if 'value_eur' in df.columns else 0
        
        # Count holdings
        holdings_count = len(df)
        
        # Group by currency
        holdings_by_currency = {}
        if 'currency' in df.columns and 'value' in df.columns:
            currency_groups = df.groupby('currency')['value'].sum()
            for currency, value in currency_groups.items():
                holdings_by_currency[currency] = float(value)
                
        # Group by asset type
        holdings_by_type = {}
        if 'type' in df.columns and 'value_eur' in df.columns:
            type_groups = df.groupby('type')['value_eur'].sum()
            for asset_type, value in type_groups.items():
                if total_value_eur > 0:
                    holdings_by_type[asset_type] = {
                        'value': float(value),
                        'percentage': float(value / total_value_eur * 100)
                    }
                else:
                    holdings_by_type[asset_type] = {
                        'value': float(value),
                        'percentage': 0
                    }
                    
        # Group by sector
        sectors = {}
        if 'sector' in df.columns and 'value_eur' in df.columns:
            sector_groups = df.groupby('sector')['value_eur'].sum()
            for sector, value in sector_groups.items():
                if sector and total_value_eur > 0:
                    sectors[sector] = {
                        'value': float(value),
                        'percentage': float(value / total_value_eur * 100)
                    }
                    
        return {
            'total_value_eur': float(total_value_eur),
            'holdings_count': holdings_count,
            'holdings_by_currency': holdings_by_currency,
            'holdings_by_type': holdings_by_type,
            'sectors': sectors
        }
        
    except Exception as e:
        logger.error(f"Error calculating portfolio composition: {str(e)}")
        return {
            'total_value_eur': 0,
            'holdings_count': 0,
            'holdings_by_currency': {},
            'holdings_by_type': {},
            'sectors': {}
        }