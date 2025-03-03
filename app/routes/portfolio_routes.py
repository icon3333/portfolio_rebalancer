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

# Global progress tracking variables
price_fetch_progress = {
    'current': 0,
    'total': 0,
    'start_time': None
}

portfolio_bp = Blueprint('portfolio', __name__, 
                       url_prefix='/portfolio',
                       template_folder='../../templates')

# Ensure session persistence
@portfolio_bp.before_request
def make_session_permanent():
    session.permanent = True  # This makes the session last longer
    session.modified = True   # This ensures changes are saved

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
    
    # Get portfolios for dropdown (including valid portfolio names)
    with get_db() as db:
        # Get portfolio names from portfolios table - include all valid portfolios
        portfolios_from_table = query_db('''
            SELECT name FROM portfolios 
            WHERE account_id = ? AND name IS NOT NULL
            ORDER BY name
        ''', [account_id])
        logger.info(f"Retrieved {len(portfolios_from_table)} portfolios from portfolios table")
        
        # Get all portfolios directly from the portfolios table
        portfolios_from_companies = query_db('''
            SELECT DISTINCT p.name as name
            FROM portfolios p
            WHERE p.account_id = ? AND p.name IS NOT NULL
        ''', [account_id])
        logger.info(f"Retrieved {len(portfolios_from_companies)} portfolios from portfolios table")
        
        # Combine both sources and remove duplicates
        portfolio_names = set()
        for p in portfolios_from_table:
            if p['name'] and p['name'].strip():
                portfolio_names.add(p['name'])
        
        for p in portfolios_from_companies:
            if p['name'] and p['name'].strip():
                portfolio_names.add(p['name'])
        
        # Convert set to list and sort alphabetically
        portfolios = [{'name': name} for name in sorted(portfolio_names)]
        logger.info(f"Combined unique portfolios: {[p['name'] for p in portfolios]}")
    
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
    
    # Check if we should use the default portfolio
    use_default_portfolio = session.pop('use_default_portfolio', False)
    
    return render_template('pages/enrich.html',
                         portfolio_data=portfolio_data,
                         portfolios=[p['name'] for p in portfolios],
                         use_default_portfolio=use_default_portfolio,
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

@portfolio_bp.route('/analyse')
def analyse():
    """Portfolio analysis page"""
    logger.info("Accessing analyse page")
    
    # Check if user is authenticated with an account
    if 'account_id' not in session:
        logger.warning("No account_id in session")
        flash('Please select an account first', 'warning')
        return redirect(url_for('main.index'))
    
    account_id = session['account_id']
    logger.info(f"Loading analyse page for account_id: {account_id}")
    
    # Verify account exists
    account = query_db('SELECT * FROM accounts WHERE id = ?', 
                      [account_id], one=True)
    if not account:
        logger.warning(f"Account {account_id} not found")
        flash('Account not found', 'error')
        return redirect(url_for('main.index'))
    
    logger.info(f"Account found: {account['username']}")
    
    return render_template('pages/analyse.html')

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
        
        # Get portfolios using the same approach as in the enrich function
        # Get portfolio names from portfolios table
        portfolios_from_table = query_db('''
            SELECT name FROM portfolios 
            WHERE account_id = ? AND name IS NOT NULL
            ORDER BY name
        ''', [account_id])
        
        # Get all portfolios directly from the portfolios table
        portfolios_from_companies = query_db('''
            SELECT DISTINCT p.name as name
            FROM portfolios p
            WHERE p.account_id = ? AND p.name IS NOT NULL
        ''', [account_id])
        
        # Combine both sources and remove duplicates
        portfolio_names = set()
        for p in portfolios_from_table:
            if p['name'] and p['name'].strip():
                portfolio_names.add(p['name'])
        
        for p in portfolios_from_companies:
            if p['name'] and p['name'].strip():
                portfolio_names.add(p['name'])
        
        # Convert set to list and sort alphabetically
        names = sorted(portfolio_names)
        
        # Ensure the default portfolio '-' is always available
        if '-' not in names:
            names.insert(0, '-')  # Add Default portfolio at the beginning
            logger.info("Added default portfolio '-' to the results")
        
        logger.info(f"Combined portfolio names with Default: {names}")
        
        # Debug the JSON serialization
        json_response = jsonify(names)
        logger.debug(f"JSON response to be sent: {json_response.data}")
        
        return json_response
        
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
    
    # Reset global progress tracking
    global price_fetch_progress
    price_fetch_progress['current'] = 0
    price_fetch_progress['total'] = 0
    price_fetch_progress['start_time'] = datetime.now().isoformat()
    
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
                
            # If there are failed price fetches, only report the ones from this session
            if result.get('failed_prices') and result.get('added'):
                # Get only the failed prices from this upload session
                # by checking if the companies are also in the 'added' list
                current_failed_prices = []
                
                # Map company names to their identifiers
                company_identifiers = {}
                for company_name in result.get('added', []):
                    company = query_db(
                        'SELECT identifier FROM companies WHERE name = ? AND account_id = ?',
                        [company_name, account_id],
                        one=True
                    )
                    if company and company['identifier']:
                        company_identifiers[company['identifier']] = company_name
                
                # Now filter the failed_prices to only those that match our newly added companies
                session_failed_prices = []
                for identifier in result.get('failed_prices', []):
                    if identifier in company_identifiers:
                        session_failed_prices.append(identifier)
                
                # Only report and log the failures from this session
                if session_failed_prices:
                    current_failure_count = len(session_failed_prices)
                    logger.warning(f"Failed to fetch prices for {current_failure_count} identifiers from this upload: {', '.join(session_failed_prices)}")
                    warnings.append(f"Failed to fetch prices for {current_failure_count} identifiers from this upload. Check logs for details.")
            
            # Show price update success message if relevant
            added_count = len(result.get('added', []))
            if added_count > 0:
                # Calculate the success count - if session_failed_prices exists, use it, otherwise assume all succeeded
                failure_count = len(session_failed_prices) if 'session_failed_prices' in locals() and session_failed_prices else 0
                prices_updated_count = added_count - failure_count
                if prices_updated_count > 0:
                    flash(f"Successfully updated prices for {prices_updated_count} out of {added_count} newly added companies", 'success')
            
            if warnings:
                flash(' | '.join(warnings), 'warning')
                
            # Set session variable to indicate we should use "-" as the default portfolio
            session['use_default_portfolio'] = True
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
        
        # Improved error handling
        if not result['success']:
            error_message = result.get('error', 'Unknown error')
            logger.warning(f"Price lookup failed for {company_name} ({identifier}): {error_message}")
            
            # Return more useful error message to frontend
            return jsonify({
                'error': f"Failed to get price for {company_name}: {error_message}",
                'details': "The system could not find a valid stock ticker for this identifier. "
                          "If this is a valid stock, try manually updating the identifier in the database."
            }), 400
            
        # Update price in database
        price = result.get('price')
        currency = result.get('currency', 'USD')
        price_eur = result.get('price_eur', price)
        
        if price is None:
            logger.warning(f"No price found for {company_name} ({identifier})")
            return jsonify({
                'error': f'No price data available for {company_name}',
                'details': "The system found the ticker but could not retrieve its current price."
            }), 400
        
        # Attempt to update the price in the database
        if update_price_in_db(identifier, price, currency, price_eur):
            logger.info(f"Successfully updated price for {company_name} to {price} {currency} ({price_eur} EUR)")
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
            logger.error(f"Database update failed for {company_name}")
            return jsonify({
                'error': f'Failed to update price for {company_name} in database'
            }), 500
            
    except Exception as e:
        logger.error(f"Error updating price: {str(e)}")
        return jsonify({'error': str(e)}), 500

@portfolio_bp.route('/api/update_all_prices', methods=['POST'])
def update_all_prices_api():
    """API endpoint to update all prices"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    account_id = session['account_id']
    
    try:
        # Get all companies for this account
        companies = query_db('''
            SELECT id, name, identifier 
            FROM companies 
            WHERE account_id = ?
        ''', [account_id])
        
        if not companies:
            return jsonify({'message': 'No companies found to update'}), 200
        
        # Initialize progress tracking
        global price_fetch_progress
        price_fetch_progress['current'] = 0
        price_fetch_progress['total'] = len(companies)
        price_fetch_progress['start_time'] = datetime.now().isoformat()
        
        # Create a job to update prices
        job_id = start_batch_process(
            update_prices, 
            [companies, account_id],
            callback=update_prices_in_db
        )
        
        return jsonify({
            'success': True,
            'message': f'Started updating prices for {len(companies)} companies',
            'job_id': job_id
        })
        
    except Exception as e:
        logger.error(f"Error updating all prices: {str(e)}")
        return jsonify({'error': str(e)}), 500

def update_prices(companies, account_id):
    """Update prices for all companies"""
    global price_fetch_progress
    results = []
    
    for i, company in enumerate(companies):
        try:
            # Update progress
            price_fetch_progress['current'] = i + 1
            
            identifier = company['identifier']
            if not identifier:
                continue
                
            result = get_isin_data(identifier)
            
            if result['success'] and result.get('price') is not None:
                price = result.get('price')
                currency = result.get('currency', 'USD')
                
                # Convert to EUR if needed
                price_eur = price
                if currency != 'EUR':
                    # Conversion logic would go here
                    pass
                
                results.append({
                    'company_id': company['id'],
                    'price': price,
                    'price_eur': price_eur,
                    'currency': currency,
                    'identifier': identifier
                })
                
        except Exception as e:
            logger.error(f"Error updating price for {company['name']}: {str(e)}")
    
    return results

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

@portfolio_bp.route('/api/price_fetch_progress', methods=['GET'])
def get_price_fetch_progress():
    """Get the current progress of price fetching"""
    global price_fetch_progress
    
    current = price_fetch_progress['current']
    total = price_fetch_progress['total']
    start_time = price_fetch_progress['start_time']
    
    # Calculate percentage - handle division by zero
    percentage = 0
    if total > 0:
        percentage = round((current / total) * 100)
    
    # Log for debugging
    logger.debug(f"Progress: {current}/{total} ({percentage}%)")
    
    return jsonify({
        'current': current,
        'total': total,
        'start_time': start_time,
        'percentage': percentage
    })

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
                    'SELECT 1 FROM company_shares WHERE company_id = ?',
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
            # Initialize progress tracking
            global price_fetch_progress
            price_fetch_progress['current'] = 0
            price_fetch_progress['total'] = len(all_identifiers)
            price_fetch_progress['start_time'] = datetime.now().isoformat()
            
            logger.info(f"Updating prices and metadata for {len(all_identifiers)} companies")
            
            for i, identifier in enumerate(all_identifiers):
                # Update progress counter
                price_fetch_progress['current'] = i + 1
                
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

@portfolio_bp.route('/api/bulk_update', methods=['POST'])
def bulk_update():
    """API endpoint to update multiple companies at once"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated. Please select an account from the home page.'}), 401
    
    try:
        account_id = session['account_id']
        data = request.json
        
        # Validate data
        if not data or 'companies' not in data:
            return jsonify({'error': 'Invalid data format, companies array is required'}), 400
            
        company_ids = data.get('companies', [])
        if not company_ids or not isinstance(company_ids, list):
            return jsonify({'error': 'No companies selected or invalid companies format'}), 400
            
        # Create backup
        backup_database()
        
        # Start transaction
        db = get_db()
        cursor = db.cursor()
        cursor.execute('BEGIN TRANSACTION')
        
        updated_companies = []
        errors = []
        
        try:
            # Handle different update types
            if 'portfolio' in data:
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
                
                # Update all selected companies
                for company_id in company_ids:
                    # Verify company belongs to account
                    company = query_db(
                        'SELECT id, name FROM companies WHERE id = ? AND account_id = ?',
                        [company_id, account_id],
                        one=True
                    )
                    
                    if not company:
                        errors.append(f"Company ID {company_id} not found or access denied")
                        continue
                    
                    # Update portfolio
                    cursor.execute(
                        'UPDATE companies SET portfolio_id = ? WHERE id = ?',
                        [portfolio_id, company_id]
                    )
                    
                    updated_companies.append({
                        'id': company_id,
                        'name': company.get('name', 'Unknown'),
                        'portfolio': portfolio_name
                    })
            
            elif 'category' in data:
                # Update category for all selected companies
                new_category = data.get('category', '')
                
                for company_id in company_ids:
                    # Verify company belongs to account
                    company = query_db(
                        'SELECT id, name FROM companies WHERE id = ? AND account_id = ?',
                        [company_id, account_id],
                        one=True
                    )
                    
                    if not company:
                        errors.append(f"Company ID {company_id} not found or access denied")
                        continue
                    
                    # Update category
                    cursor.execute(
                        'UPDATE companies SET category = ? WHERE id = ?',
                        [new_category, company_id]
                    )
                    
                    updated_companies.append({
                        'id': company_id,
                        'name': company.get('name', 'Unknown'),
                        'category': new_category
                    })
            else:
                return jsonify({'error': 'No update type specified (portfolio or category)'}), 400
            
            # Commit transaction
            db.commit()
            
            return jsonify({
                'success': True,
                'message': f'Successfully updated {len(updated_companies)} companies',
                'updated': updated_companies,
                'errors': errors
            })
            
        except Exception as e:
            db.rollback()
            return jsonify({'error': str(e)}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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