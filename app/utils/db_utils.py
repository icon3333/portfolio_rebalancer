# app/utils/db_utils.py
import logging
from datetime import datetime
from app.database.db_manager import query_db, execute_db

logger = logging.getLogger(__name__)

def update_price_in_db(identifier: str, price: float, currency: str, price_eur: float, country: str = None, sector: str = None, industry: str = None, modified_identifier: str = None) -> bool:
    """
    Update price in database for a single identifier.
    
    Args:
        identifier: Stock identifier (ISIN or ticker)
        price: Price in original currency
        currency: Currency code
        price_eur: Price in EUR
        country: Country of the company
        sector: Sector of the company
        industry: Industry of the company
        modified_identifier: If provided, update the company's identifier to this value
        
    Returns:
        Success status
    """
    try:
        if not identifier or price is None:
            logger.warning(f"Missing identifier or price: {identifier}, {price}")
            return False
            
        now = datetime.now().isoformat()
        
        # If we have a modified identifier, update the company records first
        if modified_identifier:
            logger.info(f"⚠️ Updating identifier in database from {identifier} to {modified_identifier}")
            
            # Update identifier in companies table
            rows_updated = execute_db('''
                UPDATE companies 
                SET identifier = ?
                WHERE identifier = ?
            ''', [modified_identifier, identifier])
            
            logger.info(f"Updated {rows_updated} company records with new identifier {modified_identifier}")
            
            # Use the modified identifier for all subsequent operations
            identifier = modified_identifier
        
        # Check if the record exists in market_prices
        existing = query_db(
            'SELECT 1 FROM market_prices WHERE identifier = ?',
            [identifier],
            one=True
        )
        
        if existing:
            # Update existing record
            execute_db('''
                UPDATE market_prices 
                SET price = ?, currency = ?, price_eur = ?, last_updated = ?, 
                    country = ?, sector = ?, industry = ?
                WHERE identifier = ?
            ''', [price, currency, price_eur, now, country, sector, industry, identifier])
            logger.info(f"Updated existing price record for {identifier} with additional data")
        else:
            # Insert new record
            execute_db('''
                INSERT INTO market_prices 
                (identifier, price, currency, price_eur, last_updated, country, sector, industry)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', [identifier, price, currency, price_eur, now, country, sector, industry])
            logger.info(f"Created new price record for {identifier} with additional data")
        
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
        
        logger.info(f"Successfully updated price for {identifier}: {price} {currency} ({price_eur} EUR) with country={country}, sector={sector}, industry={industry}")
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
                   mp.country, mp.sector, mp.industry, p.name as portfolio_name
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
        
        # Execute query and get results
        results = query_db(query, params)
        
        # Add debugging to log sample results
        if results and len(results) > 0:
            sample = results[0]
            logger.debug(f"Sample portfolio data keys: {list(sample.keys())}")
            if 'portfolio_name' in sample:
                logger.debug(f"Sample portfolio_name value: '{sample['portfolio_name']}'")
            else:
                logger.debug("portfolio_name key not found in results")
                
        return results
        
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
    modified_count = 0
    failed_count = 0
    
    try:
        for isin, result in results.items():
            if result.get('success') and result.get('price') is not None:
                # Check if we have a modified identifier
                modified_identifier = result.get('modified_identifier')
                
                if modified_identifier:
                    logger.info(f"📝 Found modified identifier: {isin} -> {modified_identifier}")
                    modified_count += 1
                
                success = update_price_in_db(
                    isin,
                    result.get('price'),
                    result.get('currency', 'USD'),
                    result.get('price_eur', result.get('price')),
                    result.get('country'),  # Add country information
                    result.get('sector'),    # Add sector information 
                    result.get('industry'),  # Add industry information
                    modified_identifier      # Pass modified_identifier if present
                )
                
                if success:
                    success_count += 1
                    if modified_identifier:
                        logger.info(f"✅ Successfully updated price AND identifier for {isin} -> {modified_identifier}")
                else:
                    failed_count += 1
                    logger.warning(f"❌ Failed to update price for {isin}")
        
        logger.info(f"Batch update complete. Success: {success_count}, Modified: {modified_count}, Failed: {failed_count}")
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
            from app.utils.yfinance_utils import get_yfinance_info
            result = get_yfinance_info(identifier)  # Use get_yfinance_info which includes all data fields
            success = result.get('success', False)
            price_data = result if success else None
            
        if success and price_data:
            # Extract price details from result
            price = price_data.get('price')
            currency = price_data.get('currency', 'USD')
            price_eur = price_data.get('price_eur', price)
            country = price_data.get('country')
            sector = price_data.get('sector')
            industry = price_data.get('industry')
            
            # Update database
            updated = update_price_in_db(
                identifier, price, currency, price_eur, country, sector, industry
            )
            
            if updated:
                # Update item with new price and additional data
                item['price'] = price
                item['currency'] = currency
                item['price_eur'] = price_eur
                item['country'] = country
                item['sector'] = sector
                item['industry'] = industry
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