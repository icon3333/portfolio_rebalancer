from flask import (
    Blueprint, render_template, redirect, url_for, 
    request, flash, session, jsonify, current_app
)
from app.database.db_manager import query_db, execute_db, backup_database, get_db
from app.utils.db_utils import (
    load_portfolio_data, process_portfolio_dataframe,
    update_prices, update_price_in_db, calculate_portfolio_composition,
    get_portfolios
)
from app.utils.data_processing import clear_data_caches
from app.utils.price_fetcher import price_fetcher
from app.utils.isin_utils import isin_to_ticker

import pandas as pd
import io
import logging
from datetime import datetime
import os

# Set up logger
logger = logging.getLogger(__name__)

portfolio_bp = Blueprint('portfolio', __name__, 
                       url_prefix='/portfolio',
                       template_folder='../../templates')

@portfolio_bp.route('/enrich')
def enrich():
    """Portfolio data enrichment page"""
    logger.info("Accessing enrich page")
    
    # Check if user is authenticated with an account
    if 'account_id' not in session:
        logger.warning("No account_id in session")
        flash('Please select an account first', 'warning')
        return redirect(url_for('main.index'))
    
    account_id = session['account_id']
    logger.info(f"Loading enrich page for account_id: {account_id}")
    
    # Verify account exists
    account = query_db('SELECT * FROM accounts WHERE id = ?', 
                      [account_id], one=True)
    if not account:
        logger.warning(f"Account {account_id} not found")
        flash('Account not found', 'error')
        return redirect(url_for('main.index'))
    
    logger.info(f"Account found: {account['username']}")
    
    # Get portfolio data
    portfolio_data = get_portfolio_data(account_id)
    logger.info(f"Retrieved {len(portfolio_data)} portfolio items")
    
    # Get portfolios for dropdown
    with get_db() as db:
        portfolios = query_db('''
            SELECT name FROM portfolios 
            WHERE account_id = ? AND name != '-' 
            ORDER BY name
        ''', [account_id])
        logger.info(f"Retrieved {len(portfolios)} portfolios")
    
    # Log template variables for debugging
    logger.debug(f"Template variables:")
    logger.debug(f"- portfolio_data: {portfolio_data}")
    logger.debug(f"- portfolios: {[p['name'] for p in portfolios]}")
    
    return render_template('pages/enrich.html',
                         portfolio_data=portfolio_data,
                         portfolios=[p['name'] for p in portfolios])

@portfolio_bp.route('/api/portfolio_data')
def get_portfolio_data_api():
    """API endpoint to get portfolio data"""
    logger.info("Accessing portfolio data API")
    logger.info(f"Current session: {dict(session)}")
    logger.info(f"Request headers: {dict(request.headers)}")
    
    if 'account_id' not in session:
        logger.warning("No account_id in session")
        return jsonify({'error': 'Not authenticated. Please select an account from the home page.'}), 401
    
    try:
        account_id = session['account_id']
        logger.info(f"Getting portfolio data for account_id: {account_id}")
        
        # Get account info
        account = query_db('SELECT * FROM accounts WHERE id = ?', [account_id], one=True)
        if not account:
            logger.error(f"Account {account_id} not found")
            return jsonify({'error': 'Account not found'}), 404
            
        logger.info(f"Found account: {account['username']}")
        
        # Get portfolio data
        portfolio_data = get_portfolio_data(account_id)
        
        # Log response details
        logger.info(f"Retrieved {len(portfolio_data)} portfolio items")
        if portfolio_data:
            logger.info("Sample portfolio item:")
            logger.info(f"Keys: {list(portfolio_data[0].keys())}")
            logger.info(f"First item: {portfolio_data[0]}")
        else:
            logger.warning("No portfolio data returned")
            
        return jsonify(portfolio_data)
    except Exception as e:
        logger.error(f"Error getting portfolio data: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@portfolio_bp.route('/api/portfolios')
def get_portfolios_api():
    """API endpoint to get portfolios for an account"""
    logger.info("Accessing portfolios API")
    
    if 'account_id' not in session:
        logger.warning("No account_id in session")
        return jsonify({'error': 'Not authenticated. Please select an account from the home page.'}), 401
    
    try:
        account_id = session['account_id']
        logger.info(f"Getting portfolios for account_id: {account_id}")
        
        # Get portfolios
        portfolios = query_db('''
            SELECT name FROM portfolios 
            WHERE account_id = ? AND name != '-'
            ORDER BY name
        ''', [account_id])
        logger.info(f"Retrieved {len(portfolios)} portfolios")
        
        # Return just the portfolio names array
        portfolio_names = [p['name'] for p in portfolios]
        logger.info(f"Returning portfolio names: {portfolio_names}")
        return jsonify(portfolio_names)
        
    except Exception as e:
        logger.error(f"Error getting portfolios: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@portfolio_bp.route('/upload', methods=['POST'])
def upload_csv():
    """Upload and process CSV data"""
    if 'account_id' not in session:
        flash('Please select an account first', 'warning')
        return redirect(url_for('portfolio.enrich'))
    
    account_id = session['account_id']
    
    # Check if file was uploaded
    if 'csv_file' not in request.files:
        flash('No file uploaded', 'error')
        return redirect(url_for('portfolio.enrich'))
    
    file = request.files['csv_file']
    
    # Check if file is empty
    if file.filename == '':
        flash('No file selected', 'error')
        return redirect(url_for('portfolio.enrich'))
    
    # Process the file
    try:
        # Create backup
        backup_database()
        
        # Read file content
        file_content = file.read().decode('utf-8')
        
        # Try to process the data
        success, message, result = process_csv_data(account_id, file_content)
        
        if success:
            # Show detailed success message
            message_parts = []
            if result.get('added'):
                message_parts.append(f"Added {len(result['added'])} new positions")
            if result.get('updated'):
                message_parts.append(f"Updated {len(result['updated'])} existing positions")
            if result.get('removed'):
                message_parts.append(f"Removed {len(result['removed'])} positions with zero shares")
            
            flash(f"CSV data imported successfully. {' | '.join(message_parts)}", 'success')
            
            # Show warnings if any
            warnings = []
            if result.get('failed'):
                warnings.append(f"Failed to process {len(result['failed'])} companies")
            if result.get('failed_prices'):
                warnings.append(f"Failed to fetch prices for {len(result['failed_prices'])} tickers")
            
            if warnings:
                flash(' | '.join(warnings), 'warning')
        else:
            flash(message, 'error')
            
    except Exception as e:
        logger.error(f"Error processing CSV: {str(e)}", exc_info=True)
        flash(f'Error processing CSV: {str(e)}', 'error')
    
    return redirect(url_for('portfolio.enrich'))

@portfolio_bp.route('/api/update_portfolio', methods=['POST'])
def update_portfolio_api():
    """API endpoint to update portfolio data"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated. Please select an account from the home page.'}), 401
    
    try:
        account_id = session['account_id']
        data = request.json
        
        # Validate data
        if not data or not isinstance(data, list):
            return jsonify({'error': 'Invalid data format'}), 400
        
        # Create backup
        backup_database()
        
        # Start transaction
        db = get_db()
        cursor = db.cursor()
        cursor.execute('BEGIN TRANSACTION')
        
        updated_count = 0
        failed_items = []
        
        for item in data:
            try:
                # Get company ID
                company_result = query_db(
                    'SELECT id FROM companies WHERE name = ? AND account_id = ?',
                    [item['company'], account_id],
                    one=True
                )
                
                if not company_result:
                    failed_items.append({
                        'company': item['company'],
                        'error': 'Company not found'
                    })
                    continue
                    
                company_id = company_result['id']
                
                # Get portfolio ID
                if item.get('portfolio') and item['portfolio'] != 'None':
                    portfolio_result = query_db(
                        'SELECT id FROM portfolios WHERE name = ? AND account_id = ?',
                        [item['portfolio'], account_id],
                        one=True
                    )
                    
                    if not portfolio_result:
                        # Create portfolio if it doesn't exist
                        cursor.execute(
                            'INSERT INTO portfolios (name, account_id) VALUES (?, ?)',
                            [item['portfolio'], account_id]
                        )
                        portfolio_id = cursor.lastrowid
                    else:
                        portfolio_id = portfolio_result['id']
                else:
                    # Get default portfolio
                    portfolio_result = query_db(
                        'SELECT id FROM portfolios WHERE name = "-" AND account_id = ?',
                        [account_id],
                        one=True
                    )
                    
                    if not portfolio_result:
                        # Create default portfolio if doesn't exist
                        cursor.execute(
                            'INSERT INTO portfolios (name, account_id) VALUES (?, ?)',
                            ['-', account_id]
                        )
                        portfolio_id = cursor.lastrowid
                    else:
                        portfolio_id = portfolio_result['id']
                
                # Update company
                cursor.execute('''
                    UPDATE companies 
                    SET ticker = ?, category = ?, portfolio_id = ?
                    WHERE id = ?
                ''', [
                    item.get('ticker', ''),
                    item.get('category', ''),
                    portfolio_id,
                    company_id
                ])
                
                # Update shares
                if 'shares' in item or 'override_share' in item:
                    shares = item.get('shares')
                    override_share = item.get('override_share')
                    
                    # Check if shares record exists
                    share_exists = query_db(
                        'SELECT 1 FROM company_shares WHERE company_id = ?',
                        [company_id],
                        one=True
                    )
                    
                    if share_exists:
                        cursor.execute('''
                            UPDATE company_shares
                            SET shares = ?, override_share = ?
                            WHERE company_id = ?
                        ''', [shares, override_share, company_id])
                    else:
                        cursor.execute('''
                            INSERT INTO company_shares (company_id, shares, override_share)
                            VALUES (?, ?, ?)
                        ''', [company_id, shares, override_share])
                
                updated_count += 1
                
            except Exception as e:
                failed_items.append({
                    'company': item.get('company', 'Unknown'),
                    'error': str(e)
                })
        
        if failed_items:
            db.rollback()
            return jsonify({
                'success': False,
                'message': f'Failed to update {len(failed_items)} items',
                'failed_items': failed_items
            }), 400
        else:
            db.commit()
            return jsonify({
                'success': True,
                'message': f'Successfully updated {updated_count} items'
            })
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@portfolio_bp.route('/manage_portfolios', methods=['POST'])
def manage_portfolios():
    """Add, rename, or delete portfolios"""
    if 'account_id' not in session:
        flash('Please select an account first', 'warning')
        return redirect(url_for('portfolio.enrich'))
    
    account_id = session['account_id']
    action = request.form.get('action')
    
    try:
        # Create backup
        backup_database()
        
        if action == 'add':
            portfolio_name = request.form.get('portfolio_name', '').strip()
            if not portfolio_name:
                flash('Portfolio name cannot be empty', 'error')
                return redirect(url_for('portfolio.enrich'))
                
            # Check if portfolio already exists
            existing = query_db(
                'SELECT 1 FROM portfolios WHERE name = ? AND account_id = ?',
                [portfolio_name, account_id],
                one=True
            )
            
            if existing:
                flash(f'Portfolio "{portfolio_name}" already exists', 'error')
                return redirect(url_for('portfolio.enrich'))
                
            # Add new portfolio
            execute_db(
                'INSERT INTO portfolios (name, account_id) VALUES (?, ?)',
                [portfolio_name, account_id]
            )
            
            flash(f'Portfolio "{portfolio_name}" added successfully', 'success')
            
        elif action == 'rename':
            old_name = request.form.get('old_name', '').strip()
            new_name = request.form.get('new_name', '').strip()
            
            if not old_name or not new_name:
                flash('Both old and new portfolio names are required', 'error')
                return redirect(url_for('portfolio.enrich'))
                
            # Check if new name already exists
            existing = query_db(
                'SELECT 1 FROM portfolios WHERE name = ? AND account_id = ?',
                [new_name, account_id],
                one=True
            )
            
            if existing:
                flash(f'Portfolio "{new_name}" already exists', 'error')
                return redirect(url_for('portfolio.enrich'))
                
            # Rename portfolio
            execute_db(
                'UPDATE portfolios SET name = ? WHERE name = ? AND account_id = ?',
                [new_name, old_name, account_id]
            )
            
            flash(f'Portfolio renamed from "{old_name}" to "{new_name}"', 'success')
            
        elif action == 'delete':
            portfolio_name = request.form.get('portfolio_name', '').strip()
            
            if not portfolio_name:
                flash('Portfolio name is required', 'error')
                return redirect(url_for('portfolio.enrich'))
                
            # Check if portfolio is empty
            companies = query_db('''
                SELECT COUNT(*) as count FROM companies c
                JOIN portfolios p ON c.portfolio_id = p.id
                WHERE p.name = ? AND p.account_id = ?
            ''', [portfolio_name, account_id], one=True)
            
            if companies and companies['count'] > 0:
                flash(f'Cannot delete portfolio "{portfolio_name}" because it contains companies', 'error')
                return redirect(url_for('portfolio.enrich'))
                
            # Delete portfolio
            execute_db(
                'DELETE FROM portfolios WHERE name = ? AND account_id = ?',
                [portfolio_name, account_id]
            )
            
            flash(f'Portfolio "{portfolio_name}" deleted successfully', 'success')
    
    except Exception as e:
        flash(f'Error managing portfolios: {str(e)}', 'error')
    
    return redirect(url_for('portfolio.enrich'))

@portfolio_bp.route('/api/portfolio_update_price', methods=['POST'])
def update_price_api():
    """API endpoint to update a company's price"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated. Please select an account from the home page.'}), 401
    
    try:
        account_id = session['account_id']
        data = request.json
        identifier = data.get('ticker')  # Can be either ISIN or ticker
        
        if not identifier:
            return jsonify({'error': 'Identifier (ISIN/ticker) is required'}), 400
            
        # Create backup before price update
        backup_database()
        
        # Convert ISIN to ticker if needed
        ticker_map = isin_to_ticker([identifier])
        ticker = ticker_map.get(identifier)
        
        if not ticker:
            return jsonify({'error': f'Failed to map {identifier} to a valid ticker'}), 400
        
        # Get current price from yfinance
        price, currency, price_eur = price_fetcher.get_cached_price(ticker)
        
        if price is None:
            return jsonify({'error': f'Failed to fetch price for {ticker}'}), 400
            
        now = datetime.now().isoformat()
        
        # Update price in database using the original identifier
        db = get_db()
        cursor = db.cursor()
        cursor.execute('BEGIN TRANSACTION')
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO market_prices 
                (ticker, price, currency, price_eur, last_updated)
                VALUES (?, ?, ?, ?, ?)
            ''', [identifier, price, currency, price_eur, now])  # Use original identifier as ticker
            
            # Update account's last price update timestamp
            cursor.execute('''
                UPDATE accounts 
                SET last_price_update = ? 
                WHERE id = ?
            ''', [now, account_id])
            
            db.commit()
            
            return jsonify({
                'price': price,
                'currency': currency,
                'price_eur': price_eur,
                'last_updated': now
            })
            
        except Exception as e:
            db.rollback()
            raise e
            
    except Exception as e:
        logger.error(f"Error updating price: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@portfolio_bp.route('/api/portfolio_update_all_prices', methods=['POST'])
def update_all_prices_api():
    """API endpoint to update all company prices"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated. Please select an account from the home page.'}), 401
    
    try:
        account_id = session['account_id']
        
        # Create backup before price update
        backup_database()
        
        # Get all unique identifiers (ISINs/tickers) from portfolio
        db = get_db()
        cursor = db.cursor()
        cursor.execute('''
            SELECT DISTINCT c.isin 
            FROM companies c
            JOIN portfolio_companies pc ON c.id = pc.company_id
            JOIN portfolios p ON pc.portfolio_id = p.id
            WHERE p.account_id = ?
        ''', [account_id])
        identifiers = [row[0] for row in cursor.fetchall()]
        
        if not identifiers:
            return jsonify({'message': 'No companies found to update'}), 200
            
        # Convert ISINs to tickers
        ticker_map = isin_to_ticker(identifiers)
        
        # Update prices for each identifier
        now = datetime.now().isoformat()
        updated = 0
        failed = 0
        
        for identifier in identifiers:
            ticker = ticker_map.get(identifier)
            if not ticker:
                logger.warning(f"No ticker found for identifier: {identifier}")
                failed += 1
                continue
                
            try:
                price, currency, price_eur = price_fetcher.get_cached_price(ticker)
                
                if price is None:
                    logger.warning(f"Failed to fetch price for {ticker}")
                    failed += 1
                    continue
                    
                cursor.execute('''
                    INSERT OR REPLACE INTO market_prices 
                    (ticker, price, currency, price_eur, last_updated)
                    VALUES (?, ?, ?, ?, ?)
                ''', [identifier, price, currency, price_eur, now])  # Use original identifier
                updated += 1
                
            except Exception as e:
                logger.error(f"Error updating price for {identifier}: {str(e)}")
                failed += 1
        
        # Update account's last price update timestamp
        cursor.execute('''
            UPDATE accounts 
            SET last_price_update = ? 
            WHERE id = ?
        ''', [now, account_id])
        
        db.commit()
        
        message = f"Updated {updated} prices"
        if failed > 0:
            message += f", {failed} failed"
            
        return jsonify({'message': message}), 200
        
    except Exception as e:
        logger.error(f"Error in update_all_prices_api: {str(e)}")
        return jsonify({'error': str(e)}), 500

@portfolio_bp.route('/api/portfolio_update_missing_prices', methods=['POST'])
def update_missing_prices_api():
    """API endpoint to update prices for companies with missing prices"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated. Please select an account from the home page.'}), 401
    
    try:
        account_id = session['account_id']
        
        # Get ISINs for companies with missing or old prices
        isins = query_db('''
            SELECT DISTINCT c.isin
            FROM companies c
            LEFT JOIN market_prices mp ON c.isin = mp.ticker
            WHERE c.account_id = ? 
            AND c.isin IS NOT NULL
            AND (
                mp.price_eur IS NULL 
                OR mp.last_updated < datetime('now', '-24 hours')
            )
        ''', [account_id])
        
        if not isins:
            return jsonify({'message': 'No companies found with missing prices'}), 200
            
        # Extract ISINs from query result
        isin_list = [row['isin'] for row in isins]
        logger.info(f"Updating prices for {len(isin_list)} ISINs with missing prices")
        
        # Create backup before price update
        backup_database()
        
        # Update prices
        results, failed = update_prices(isin_list, account_id, force_update=True)
        
        if failed:
            logger.warning(f"Failed to update prices for {len(failed)} ISINs: {failed}")
            
        return jsonify({
            'success': results['success'],
            'failed': results['failed'],
            'skipped': results['skipped'],
            'failed_isins': failed
        })
        
    except Exception as e:
        logger.error(f"Error updating missing prices: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@portfolio_bp.route('/api/portfolio_delete_company', methods=['POST'])
def delete_company_api():
    """API endpoint to delete a company"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated. Please select an account from the home page.'}), 401
    
    try:
        account_id = session['account_id']
        data = request.json
        company_id = data.get('id')
        
        if not company_id:
            return jsonify({'error': 'Company ID is required'}), 400
            
        # Check if company exists and belongs to account
        company = query_db(
            'SELECT 1 FROM companies WHERE id = ? AND account_id = ?',
            [company_id, account_id],
            one=True
        )
        
        if not company:
            return jsonify({'error': 'Company not found'}), 404
            
        # Create backup before deletion
        backup_database()
        
        # Delete company and related data
        db = get_db()
        cursor = db.cursor()
        cursor.execute('BEGIN TRANSACTION')
        
        try:
            # Delete shares
            cursor.execute('DELETE FROM company_shares WHERE company_id = ?', [company_id])
            # Then delete company
            cursor.execute('DELETE FROM companies WHERE id = ?', [company_id])
            db.commit()
            
        except Exception as e:
            db.rollback()
            raise e
            
        return jsonify({'message': 'Company deleted successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@portfolio_bp.route('/api/update_portfolio/<int:company_id>', methods=['POST'])
def update_single_portfolio_api(company_id):
    """API endpoint to update a single portfolio item"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated. Please select an account from the home page.'}), 401
    
    try:
        account_id = session['account_id']
        data = request.json
        
        # Validate data
        if not data:
            return jsonify({'error': 'Invalid data format'}), 400
            
        # Verify company belongs to account
        company = query_db(
            'SELECT id FROM companies WHERE id = ? AND account_id = ?',
            [company_id, account_id],
            one=True
        )
        
        if not company:
            return jsonify({'error': 'Company not found or access denied'}), 404
            
        # Start transaction
        db = get_db()
        cursor = db.cursor()
        cursor.execute('BEGIN TRANSACTION')
        
        try:
            # Get or create portfolio
            portfolio_name = data.get('portfolio', '-')
            portfolio_result = query_db(
                'SELECT id FROM portfolios WHERE name = ? AND account_id = ?',
                [portfolio_name, account_id],
                one=True
            )
            
            if not portfolio_result:
                cursor.execute(
                    'INSERT INTO portfolios (name, account_id) VALUES (?, ?)',
                    [portfolio_name, account_id]
                )
                portfolio_id = cursor.lastrowid
            else:
                portfolio_id = portfolio_result['id']
            
            # Update company
            cursor.execute('''
                UPDATE companies 
                SET category = ?, portfolio_id = ?
                WHERE id = ?
            ''', [
                data.get('category', ''),
                portfolio_id,
                company_id
            ])
            
            db.commit()
            
            # Get updated company data
            updated_company = query_db('''
                SELECT c.*, p.name as portfolio_name 
                FROM companies c
                LEFT JOIN portfolios p ON c.portfolio_id = p.id
                WHERE c.id = ?
            ''', [company_id], one=True)
            
            return jsonify({
                'success': True,
                'data': {
                    'id': updated_company['id'],
                    'portfolio': updated_company['portfolio_name'],
                    'category': updated_company['category']
                }
            })
            
        except Exception as e:
            db.rollback()
            return jsonify({'error': str(e)}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@portfolio_bp.route('/api/update_price/<int:company_id>', methods=['GET', 'POST'])
def update_single_price_api(company_id):
    """API endpoint to update price for a specific company"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated. Please select an account from the home page.'}), 401
        
    try:
        account_id = session['account_id']
        
        # Verify company belongs to account and get ticker
        company = query_db(
            'SELECT id, name, ticker FROM companies WHERE id = ? AND account_id = ?',
            [company_id, account_id],
            one=True
        )
        
        if not company:
            return jsonify({'error': 'Company not found or access denied'}), 404
            
        ticker = company['ticker']
        if not ticker:
            return jsonify({'error': f'No ticker available for company {company["name"]}'}), 400
            
        # Get latest price for the company using price_fetcher
        try:
            price_data = price_fetcher.get_current_prices([ticker])
            if not price_data or ticker not in price_data:
                return jsonify({'error': f'Could not fetch price for {ticker}'}), 400
                
            price = price_data[ticker]
            
            # Update price in database
            execute_db(
                'UPDATE market_prices SET price = ?, last_updated = CURRENT_TIMESTAMP WHERE ticker = ?',
                [price, ticker]
            )
            
            return jsonify({
                'message': 'Price updated successfully',
                'company_id': company_id,
                'ticker': ticker,
                'price': price
            })
            
        except Exception as e:
            logger.error(f"Error fetching price for {ticker}: {str(e)}")
            return jsonify({'error': f'Error fetching price for {ticker}: {str(e)}'}), 500
        
    except Exception as e:
        logger.error(f"Error in update_single_price_api: {str(e)}")
        return jsonify({'error': str(e)}), 500

def get_portfolio_data(account_id):
    """Get portfolio data from the database"""
    try:
        logger.info(f"Loading portfolio data for account_id: {account_id}")
        df = load_portfolio_data(account_id)
        
        if df is None:
            logger.warning("load_portfolio_data returned None")
            return []
        if df.empty:
            logger.info("No portfolio data found")
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
                c.ticker,
                c.isin,
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
                item = {
                    'id': row['id'],  # Add the id field
                    'company': row['company'],
                    'isin': row['isin'],
                    'ticker': row['ticker'],
                    'portfolio': row['portfolio'],
                    'category': row['category'],
                    'shares': float(row['shares']) if pd.notna(row['shares']) else 0,
                    'override_share': float(row['override_share']) if pd.notna(row['override_share']) else None,
                    'price_eur': float(row['price_eur']) if pd.notna(row['price_eur']) else None,
                    'currency': row['currency'],
                    'total_invested': float(row['total_invested']) if pd.notna(row['total_invested']) else 0,
                    'last_updated': row['last_updated'].isoformat() if pd.notna(row['last_updated']) else None
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

def process_csv_data(account_id, file_content):
    """Process and import CSV data into the database"""
    db = None
    cursor = None
    try:
        # Get database connection and cursor
        db = get_db()
        cursor = db.cursor()
        
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
                if any(col for col in df.columns if alt in col):
                    matching_col = next(col for col in df.columns if alt in col)
                    column_mapping[required_col] = matching_col
                    found = True
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
                matching_cols = [col for col in df.columns if alt in col]
                if matching_cols and opt_col not in column_mapping:
                    column_mapping[opt_col] = matching_cols[0]
                    break
        
        # Rename columns to match our format
        df = df.rename(columns=column_mapping)
        
        # Set default values for missing optional columns
        if 'type' not in df.columns:
            df['type'] = 'Buy'  # Default to Buy type
        if 'currency' not in df.columns:
            df['currency'] = 'EUR'  # Default to EUR
        
        # Clean up data
        df['identifier'] = df['identifier'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
        df['holdingname'] = df['holdingname'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
        
        # Filter out rows with empty identifiers
        df = df[df['identifier'].str.len() > 0]
        
        if len(df) == 0:
            return False, "No valid entries found in CSV file", {}
        
        # Convert numeric columns - handle both string and numeric inputs
        def convert_numeric(val):
            if pd.isna(val):
                return None
            if isinstance(val, (int, float)):
                return float(val)
            try:
                # Convert string to float, handling European number format
                val_str = str(val).strip().replace(',', '.')
                return float(val_str)
            except (ValueError, TypeError):
                return None

        df['shares'] = df['shares'].apply(convert_numeric)
        df['price'] = df['price'].apply(convert_numeric)
        
        # Remove rows with invalid numeric values
        df = df.dropna(subset=['shares', 'price'])
        
        if df.empty:
            return False, "No valid entries found in CSV file after converting numeric values", {}
        
        # Calculate total invested
        df['total_invested'] = df['shares'] * df['price']
        
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
        
        # Process each row
        positions_added = []
        positions_updated = []
        positions_removed = []
        
        for _, row in df.iterrows():
            company_name = row['holdingname']
            identifier = row['identifier']
            share_count = float(row['shares'])
            total_invested = float(row['total_invested'])
            
            # Handle floating point precision
            if abs(share_count) < 1e-10:
                share_count = 0
                total_invested = 0
            
            # Check if company exists
            company = query_db(
                'SELECT id FROM companies WHERE name = ? AND account_id = ?',
                [company_name, account_id],
                one=True
            )
            
            if share_count <= 0:
                # Remove company if it exists
                if company:
                    # Delete shares first
                    cursor.execute(
                        'DELETE FROM company_shares WHERE company_id = ?',
                        [company['id']]
                    )
                    # Then delete company
                    cursor.execute(
                        'DELETE FROM companies WHERE id = ?',
                        [company['id']]
                    )
                    positions_removed.append(company_name)
                continue
            
            if company:
                # Update existing company
                cursor.execute('''
                    UPDATE companies 
                    SET ticker = ?, total_invested = ?
                    WHERE id = ?
                ''', [identifier, total_invested, company['id']])
                
                # Update shares
                share_exists = query_db(
                    'SELECT 1 FROM company_shares WHERE company_id = ?',
                    [company['id']],
                    one=True
                )
                
                if share_exists:
                    cursor.execute('''
                        UPDATE company_shares 
                        SET shares = ?
                        WHERE company_id = ?
                    ''', [share_count, company['id']])
                else:
                    cursor.execute('''
                        INSERT INTO company_shares (company_id, shares)
                        VALUES (?, ?)
                    ''', [company['id'], share_count])
                
                positions_updated.append(company_name)
            else:
                # Insert new company
                cursor.execute('''
                    INSERT INTO companies (
                        name, ticker, isin, category, portfolio_id, 
                        account_id, total_invested
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', [
                    company_name,
                    identifier,
                    identifier if len(identifier) == 12 else '',  # Assume ISIN if 12 chars
                    '',  # Empty category
                    default_portfolio_id,
                    account_id,
                    total_invested
                ])
                
                company_id = cursor.lastrowid
                
                # Insert shares
                cursor.execute('''
                    INSERT INTO company_shares (company_id, shares)
                    VALUES (?, ?)
                ''', [company_id, share_count])
                
                positions_added.append(company_name)
        
        # Commit transaction
        db.commit()
        
        # Clear data caches to force refresh
        clear_data_caches()
        
        return True, "CSV data imported successfully", {
            'added': positions_added,
            'updated': positions_updated,
            'removed': positions_removed
        }
        
    except Exception as e:
        logger.error(f"Error processing CSV: {str(e)}", exc_info=True)
        if db:
            db.rollback()
        return False, str(e), {}
    finally:
        # Clean up cursor and connection
        if cursor:
            cursor.close()