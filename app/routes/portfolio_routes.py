from flask import (
    Blueprint, render_template, redirect, url_for, 
    request, flash, session, jsonify, current_app
)
from app.database.db_manager import query_db, execute_db, backup_database, get_db
from app.utils.db_utils import (
    load_portfolio_data, process_portfolio_dataframe,
    update_prices, update_price_in_db, calculate_portfolio_composition,
    get_portfolios, update_batch_prices_in_db
)
from app.utils.data_processing import clear_data_caches
from app.utils.yfinance_utils import get_isin_data, get_price_for_ticker, find_ticker_for_isin
from app.utils.batch_processing import start_batch_process, get_job_status
import pandas as pd
import io
import logging
from datetime import datetime
import os
import time
from flask import g, Response
import traceback

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
    
    # Calculate metrics safely handling None values
    last_updates = [item['last_updated'] for item in portfolio_data if item['last_updated'] is not None]
    total_value = sum(
        (item['price_eur'] or 0) * (item['shares'] or 0) 
        for item in portfolio_data
    )
    missing_prices = sum(1 for item in portfolio_data if not item['price_eur'])
    total_items = len(portfolio_data)
    health = int(((total_items - missing_prices) / total_items * 100) if total_items > 0 else 100)
    
    return render_template('pages/enrich.html',
                         portfolio_data=portfolio_data,
                         portfolios=[p['name'] for p in portfolios],
                         metrics={
                             'total': total_items,
                             'health': health,
                             'missing': missing_prices,
                             'totalValue': total_value,
                             'lastUpdate': max(last_updates) if last_updates else None
                         })

@portfolio_bp.route('/api/portfolio_data', methods=['GET'])
def get_portfolio_data_api():
    """Get portfolio data from the database"""
    try:
        account_id = session['account_id']
        if not account_id:
            return jsonify({'error': 'Not authenticated'}), 401

        # Get data from database without triggering any yfinance updates
        portfolio_data = get_portfolio_data(account_id)
        if not portfolio_data:
            return jsonify([])

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
                    SET identifier = ?, category = ?, portfolio_id = ?
                    WHERE id = ?
                ''', [
                    item.get('identifier', ''),
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
                        'SELECT company_id, shares FROM company_shares WHERE company_id = ?',
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
            portfolio_name = request.form.get('add_portfolio_name', '').strip()
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
            portfolio_name = request.form.get('delete_portfolio_name', '').strip()
            
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

@portfolio_bp.route('/api/update_price', methods=['POST'])
def update_price_api():
    """API endpoint to update a company's price"""
    try:
        data = request.get_json() if request.is_json else request.form
        identifier = data.get('identifier', '').strip().upper()
        
        if not identifier:
            return jsonify({'error': 'No identifier provided'}), 400
            
        # Backup database before making changes
        backup_database()
        
        # Get current price
        result = get_stock_info(identifier)
        if not result['success']:
            return jsonify({'error': f'Failed to fetch price for {identifier}: {result.get("error")}'}), 400
            
        data = result['data']
        price = data.get('currentPrice')
        currency = data.get('currency')
        price_eur = data.get('priceEUR')  # Get EUR price from the result
        
        if price is None:
            return jsonify({'error': f'Failed to fetch price for {identifier}'}), 400
            
        # Update price in database
        if update_price_in_db(identifier, price, currency, price_eur):
            return jsonify({
                'success': True,
                'data': {
                    'identifier': identifier,
                    'price': price,
                    'currency': currency,
                    'price_eur': price_eur
                }
            })
        else:
            return jsonify({'error': f'Failed to update price in database for {identifier}'}), 500
            
    except Exception as e:
        logger.error(f"Error updating price: {str(e)}")
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
            
            # Get current company data
            current_company = query_db('''
                SELECT * FROM companies WHERE id = ?
            ''', [company_id], one=True)
            
            if not current_company:
                return jsonify({
                    'success': False,
                    'error': 'Company not found'
                }), 404
            
            # Prepare update fields and values
            update_fields = []
            update_values = []
            
            # Only update fields that are provided in the request
            if 'category' in data:
                update_fields.append('category = ?')
                update_values.append(data['category'])
            
            if 'portfolio' in data:
                update_fields.append('portfolio_id = ?')
                update_values.append(portfolio_id)
            
            if 'identifier' in data:
                update_fields.append('identifier = ?')
                update_values.append(data['identifier'])
            
            # If no fields to update, return success
            if not update_fields:
                return jsonify({
                    'success': True,
                    'message': 'No fields to update'
                })
            
            # Build and execute update query
            update_query = f'''
                UPDATE companies 
                SET {', '.join(update_fields)}
                WHERE id = ?
            '''
            update_values.append(company_id)
            
            cursor.execute(update_query, update_values)
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
                    'category': updated_company['category'],
                    'identifier': updated_company['identifier']
                }
            })
            
        except Exception as e:
            db.rollback()
            return jsonify({'error': str(e)}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@portfolio_bp.route('/api/companies/<int:company_id>/price', methods=['PUT'])
def update_single_price_api(company_id):
    """API endpoint to update price for a specific company"""
    try:
        # Get company info from database
        company = query_db(
            'SELECT * FROM portfolio WHERE id = ?', 
            [company_id],
            one=True
        )
        
        if not company:
            return jsonify({'error': f'Company with id {company_id} not found'}), 404
            
        identifier = company.get('identifier')
        if not identifier:
            return jsonify({'error': f'No identifier available for company {company["name"]}'}), 400
            
        # Get latest price for the company
        result = get_stock_info(identifier)
        if not result['success']:
            return jsonify({'error': f'Could not fetch price for {identifier}: {result.get("error")}'}), 400
            
        data = result['data']
        price = data.get('currentPrice')
        currency = data.get('currency')
        price_eur = data.get('priceEUR')  # Get EUR price from the result
        
        if price is None:
            return jsonify({'error': f'No price data available for {identifier}'}), 400
            
        # Update price in database
        success = update_price_in_db(identifier, price, currency, price_eur)
        
        if not success:
            return jsonify({'error': f'Failed to update price in database'}), 500
            
        return jsonify({
            'success': True,
            'price': price,
            'currency': currency,
            'price_eur': price_eur
        })
        
    except Exception as e:
        logger.error(f"Error in update_single_price_api: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

@portfolio_bp.route('/api/update_price/<int:company_id>', methods=['POST'])
def update_price_by_id_api(company_id):
    """API endpoint to update price for a specific company by ID"""
    try:
        logger.info(f"Starting price update for company ID: {company_id}")
        
        # Get company identifier from database
        company = query_db('SELECT identifier, name FROM companies WHERE id = ?', [company_id], one=True)
        if not company:
            error_msg = f'Company with ID {company_id} not found'
            logger.error(error_msg)
            return jsonify({'error': error_msg}), 404
            
        identifier = company['identifier']
        company_name = company['name']
        
        if not identifier:
            error_msg = f'Company {company_id} ({company_name}) has no identifier'
            logger.error(error_msg)
            return jsonify({'error': error_msg}), 400
            
        logger.info(f"Processing company: {company_name} (ID: {company_id}, Identifier: {identifier})")
        
        # Instead of using batch processing for a single item, call get_isin_data directly
        result = get_isin_data(identifier)
        
        if not result['success']:
            return jsonify({
                'error': f"Failed to get price for {company_name}: {result.get('error', 'Unknown error')}"
            }), 400
            
        # Update price in database
        price = result.get('price')
        currency = result.get('currency', 'USD')
        price_eur = result.get('price_eur', price)
        
        if price and update_price_in_db(identifier, price, currency, price_eur):
            return jsonify({
                'success': True,
                'message': f'Updated price for {company_name}',
                'data': {
                    'price': price,
                    'currency': currency,
                    'price_eur': price_eur,
                    'updated_at': datetime.now().isoformat()
                }
            })
        else:
            return jsonify({
                'error': f'Failed to update price for {company_name}'
            }), 500
            
    except Exception as e:
        logger.error(f"Error updating price: {str(e)}")
        return jsonify({'error': str(e)}), 500

@portfolio_bp.route('/api/update_all_prices', methods=['POST'])
def update_all_prices_api():
    try:
        # Get current account_id from session
        account_id = session.get('account_id')
        if not account_id:
            return jsonify({'error': 'No account selected'}), 400

        # Load portfolio data
        portfolio_items = load_portfolio_data(account_id)
        
        if not portfolio_items:  # Check if list is empty
            return jsonify({'message': 'No portfolio items found'}), 200
            
        # Convert list of dicts to pandas DataFrame
        import pandas as pd
        df = pd.DataFrame(portfolio_items)
        
        if df.empty:
            return jsonify({'message': 'No portfolio items found'}), 200

        # Get list of ISINs
        isins = df['identifier'].dropna().unique().tolist()
        
        # Filter out empty strings and non-strings
        isins = [isin for isin in isins if isinstance(isin, str) and isin.strip()]
        
        if not isins:
            return jsonify({'message': 'No valid identifiers found'}), 200
        
        # Start batch processing
        job_id = start_batch_process(isins)
        
        if not job_id:
            return jsonify({'error': 'Failed to start batch process'}), 500
        
        # Return job ID for status checking
        return jsonify({
            'status': 'processing',
            'job_id': job_id,
            'message': f'Processing {len(isins)} portfolio items'
        })

    except Exception as e:
        logger.error(f"Error in update_all_prices: {str(e)}")
        return jsonify({'error': str(e)}), 500

@portfolio_bp.route('/api/price_update_status/<job_id>', methods=['GET'])
def get_price_update_status(job_id):
    """Get status of price update job."""
    try:
        # Get job status
        status = get_job_status(job_id)
        
        if status['status'] == 'not_found':
            return jsonify({'error': 'Job not found'}), 404
            
        if status['status'] == 'completed' and status.get('results'):
            # Process results if completed
            results = status.get('results')
            if isinstance(results, dict):
                # Handle both old and new format
                if 'items' in results and 'summary' in results:
                    # New format with summary
                    items = results.get('items', {})
                    summary = results.get('summary', {})
                    success = update_batch_prices_in_db(items)
                    logger.info(f"Price update processed with status: {success}")
                    
                    # Add information about the update to the status
                    status['price_update'] = {
                        'success': success,
                        'total': summary.get('total', 0),
                        'success_count': summary.get('success_count', 0),
                        'failure_count': summary.get('failure_count', 0)
                    }
                else:
                    # Old format (just items)
                    success = update_batch_prices_in_db(results)
                    logger.info(f"Price update processed with status: {success}")
                    # Add information about the update to the status
                    status['price_update'] = {
                        'success': success
                    }
            else:
                logger.warning(f"Invalid results format or empty results: {type(results)}")
                status['price_update'] = {
                    'success': False,
                    'error': 'Invalid results format'
                }
        
        return jsonify(status)
    
    except Exception as e:
        logger.error(f"Error checking price update status: {str(e)}")
        return jsonify({'error': str(e)}), 500

def update_prices_in_db(results):
    """Update portfolio items with new prices."""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        for isin, result in results.items():
            if result['success'] and result['price'] is not None:
                cursor.execute('''
                    UPDATE portfolio_items 
                    SET price_eur = ?, last_updated = ? 
                    WHERE identifier = ?
                ''', (result['price'], datetime.now(), isin))
        
        conn.commit()
        
    except Exception as e:
        logger.error(f"Error updating prices in database: {str(e)}")
        raise

@portfolio_bp.route('/api/batch_update_price/<int:company_id>', methods=['GET', 'POST'])
def batch_update_price_by_id_api(company_id):
    """API endpoint to update price for a specific company by ID using batch processing"""
    try:
        logger.info(f"Starting batch price update for company ID: {company_id}")
        
        # Get company identifier from database
        company = query_db('SELECT identifier, name FROM companies WHERE id = ?', [company_id], one=True)
        if not company:
            error_msg = f'Company with ID {company_id} not found'
            logger.error(error_msg)
            return jsonify({'error': error_msg}), 404
            
        identifier = company['identifier']
        company_name = company['name']
        
        if not identifier:
            error_msg = f'Company {company_id} ({company_name}) has no identifier'
            logger.error(error_msg)
            return jsonify({'error': error_msg}), 400
            
        logger.info(f"Starting batch process for company: {company_name} (ID: {company_id}, Identifier: {identifier})")
        
        # Start batch process for single ISIN
        job_id = start_batch_process([identifier])
        
        return jsonify({
            'status': 'processing',
            'job_id': job_id,
            'message': f'Processing price update for {company_name}'
        })
            
    except Exception as e:
        logger.error(f"Error updating price: {str(e)}")
        return jsonify({'error': str(e)}), 500

@portfolio_bp.route('/api/update_progress')
def update_progress():
    def generate():
        while True:
            progress = g.get('update_progress', 0)
            yield f"data: {progress}\n\n"
            if progress >= 100:
                break
            time.sleep(0.5)
    
    return Response(generate(), mimetype='text/event-stream')

def get_portfolio_data(account_id):
    """Get portfolio data from the database"""
    try:
        logger.info(f"Loading portfolio data for account_id: {account_id}")
        df = load_portfolio_data(account_id)
        
        if df is None:
            logger.warning("load_portfolio_data returned None")
            return []
        if not df:  # Check if list is empty
            logger.info("No portfolio data found")
            return []
            
        import pandas as pd
        # Convert list of dicts to pandas DataFrame
        df = pd.DataFrame(df)
        
        if df.empty:
            logger.info("DataFrame is empty after conversion")
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
                item = {
                    'id': row['id'],  # Add the id field
                    'company': row['name'],  # Changed from 'company' to 'name'
                    'identifier': row['identifier'],
                    'portfolio': row.get('portfolio_name', ''),  # Try to get portfolio_name or fall back to empty string
                    'category': row['category'],
                    'shares': float(row['shares']) if pd.notna(row['shares']) else 0,
                    'override_share': float(row['override_share']) if pd.notna(row['override_share']) else None,
                    'price_eur': float(row['price_eur']) if pd.notna(row['price_eur']) else None,
                    'currency': row['currency'],
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

def process_csv_data(account_id, file_content):
    """Process and import CSV data into the database"""
    db = None
    cursor = None
    try:
        # Get database connection and cursor
        db = get_db()
        cursor = db.cursor()
        
        # Get all existing companies for this account
        existing_companies = query_db(
            'SELECT id, name, identifier, total_invested FROM companies WHERE account_id = ?',
            [account_id]
        )
        
        # Create a mapping of company names to their data for quick lookup
        existing_company_map = {company['name']: company for company in existing_companies}
        
        # Create a set to track processed company IDs
        processed_company_ids = set()
        
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
        
        # Group by company name to handle duplicates in the CSV
        logger.info(f"Before grouping: {len(df)} rows")
        # Check for duplicate company names
        duplicate_names = df[df.duplicated('holdingname', keep=False)]['holdingname'].unique()
        if len(duplicate_names) > 0:
            logger.info(f"Found duplicate company names in CSV: {duplicate_names}")
            
            # Group by company name and aggregate
            df = df.groupby('holdingname', as_index=False).agg({
                'identifier': 'first',  # Take the first identifier
                'shares': 'sum',        # Sum the shares
                'price': 'mean',        # Average the price
                'total_invested': 'sum' # Sum the total invested
            })
            logger.info(f"After grouping: {len(df)} rows")
        
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
        
        # Get existing shares data for comparison
        existing_shares = query_db(
            '''SELECT cs.company_id, cs.shares, c.name 
               FROM company_shares cs 
               JOIN companies c ON cs.company_id = c.id 
               WHERE c.account_id = ?''',
            [account_id]
        )
        
        # Create a mapping of company names to their current shares
        company_shares_map = {}
        for share_data in existing_shares:
            company_shares_map[share_data['name']] = share_data['shares']
        
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
            company = existing_company_map.get(company_name)
            
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
                # Check if data has actually changed
                current_shares = company_shares_map.get(company_name, 0)
                current_identifier = company['identifier']
                current_total_invested = company['total_invested']
                
                # Only mark as updated if something significant changed
                data_changed = (
                    abs(current_shares - share_count) > 1e-10 or
                    current_identifier != identifier or
                    abs(current_total_invested - total_invested) > 1e-10
                )
                
                # Update existing company
                cursor.execute('''
                    UPDATE companies 
                    SET identifier = ?, total_invested = ?
                    WHERE id = ?
                ''', [identifier, total_invested, company['id']])
                
                # Update shares
                share_exists = query_db(
                    'SELECT company_id, shares FROM company_shares WHERE company_id = ?',
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
                
                # Only add to positions_updated if data actually changed
                if data_changed:
                    positions_updated.append(company_name)
                
                processed_company_ids.add(company['id'])  # Track this company as processed
            else:
                # Insert new company
                cursor.execute('''
                    INSERT INTO companies (
                        name, identifier, category, portfolio_id, 
                        account_id, total_invested
                    ) VALUES (?, ?, ?, ?, ?, ?)
                ''', [
                    company_name,
                    identifier,
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
                processed_company_ids.add(company_id)  # Track new company as processed
        
        # Now delete companies that were not in the CSV
        for company in existing_companies:
            if company['id'] not in processed_company_ids:
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
                positions_removed.append(company['name'])
        
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

@portfolio_bp.route('/api/company/<int:company_id>', methods=['DELETE'])
def delete_company(company_id):
    """API endpoint to delete a company"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    account_id = session['account_id']
    
    try:
        # Create backup before making changes
        backup_database()
        
        # Get company info before deletion
        company = query_db(
            'SELECT name, identifier FROM companies WHERE id = ? AND account_id = ?',
            [company_id, account_id],
            one=True
        )
        
        if not company:
            return jsonify({'error': 'Company not found or access denied'}), 404
            
        identifier = company['identifier']
        
        # Start transaction
        db = get_db()
        cursor = db.cursor()
        cursor.execute('BEGIN TRANSACTION')
        
        try:
            # Delete from company_shares first (due to foreign key constraints)
            cursor.execute('DELETE FROM company_shares WHERE company_id = ?', [company_id])
            
            # Delete from companies
            cursor.execute('DELETE FROM companies WHERE id = ? AND account_id = ?', [company_id, account_id])
            
            # Check if any other company uses this identifier
            other_companies = query_db(
                'SELECT 1 FROM companies WHERE identifier = ? LIMIT 1',
                [identifier]
            )
            
            # If no other companies use this identifier, delete from market_prices
            if not other_companies and identifier:
                cursor.execute('DELETE FROM market_prices WHERE identifier = ?', [identifier])
            
            # Commit transaction
            db.commit()
            
            logger.info(f"Company '{company['name']}' (ID: {company_id}) deleted successfully")
            return jsonify({
                'success': True,
                'message': f'Company "{company["name"]}" deleted successfully'
            })
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error in transaction: {str(e)}")
            return jsonify({'error': str(e)}), 500
            
    except Exception as e:
        logger.error(f"Error deleting company: {str(e)}")
        return jsonify({'error': str(e)}), 500