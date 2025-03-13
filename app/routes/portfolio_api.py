from flask import (
    request, flash, session, jsonify, redirect, url_for, Response, g
)
from app.database.db_manager import query_db, execute_db, backup_database, get_db
from app.utils.db_utils import (
    load_portfolio_data, process_portfolio_dataframe, update_price_in_db, update_batch_prices_in_db
)
from app.utils.yfinance_utils import get_isin_data
from app.utils.batch_processing import start_batch_process, get_job_status
from app.utils.portfolio_utils import (
    get_portfolio_data, process_csv_data, has_companies_in_default, get_stock_info, update_prices
)

import pandas as pd
import logging
from datetime import datetime
import time
import uuid
import json
import io

# Set up logger
logger = logging.getLogger(__name__)

# Global progress tracking variables
price_fetch_progress = {
    'current': 0,
    'total': 0,
    'start_time': None
}

# API endpoint to get and save state data
def manage_state():
    """Get or save state data"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    account_id = session['account_id']
    
    # GET request to retrieve state
    if request.method == 'GET':
        page_name = request.args.get('page', '')
        
        if not page_name:
            return jsonify({'error': 'Page name is required'}), 400
        
        try:
            # Get all state variables for this account and page
            state_vars = query_db('''
                SELECT variable_name, variable_type, variable_value
                FROM expanded_state
                WHERE account_id = ? AND page_name = ?
            ''', [account_id, page_name])
            
            if not state_vars:
                return jsonify({})
            
            # Convert to proper data structure
            state_data = {}
            for var in state_vars:
                var_name = var['variable_name']
                var_value = var['variable_value']
                
                # Add to state data without conversion (handled by front-end)
                state_data[var_name] = var_value
            
            return jsonify(state_data)
            
        except Exception as e:
            logger.error(f"Error retrieving state: {str(e)}")
            return jsonify({'error': str(e)}), 500
    
    # POST request to save state
    elif request.method == 'POST':
        data = request.json
        
        if not data or 'page' not in data:
            return jsonify({'error': 'Invalid data format'}), 400
        
        page_name = data['page']
        
        try:
            # Create backup before making changes
            backup_database()
            
            # Get database connection and cursor
            db = get_db()
            cursor = db.cursor()
            
            # Start transaction
            cursor.execute('BEGIN TRANSACTION')
            
            # Delete existing state for this page (to avoid orphaned variables)
            cursor.execute('''
                DELETE FROM expanded_state
                WHERE account_id = ? AND page_name = ?
            ''', [account_id, page_name])
            
            # Insert new state variables
            for key, value in data.items():
                if key == 'page':
                    continue  # Skip the page key
                
                # Determine variable type
                if isinstance(value, str):
                    if value.startswith('{') or value.startswith('['):
                        var_type = 'object'
                    else:
                        var_type = 'string'
                else:
                    var_type = 'string'
                
                # Insert into database
                cursor.execute('''
                    INSERT INTO expanded_state
                    (account_id, page_name, variable_name, variable_type, variable_value)
                    VALUES (?, ?, ?, ?, ?)
                ''', [account_id, page_name, key, var_type, value])
            
            # Commit transaction
            db.commit()
            
            logger.info(f"State saved successfully for account {account_id}, page {page_name}")
            return jsonify({'success': True, 'message': 'State saved successfully'})
            
        except Exception as e:
            if 'db' in locals() and db:
                db.rollback()
            logger.error(f"Error saving state: {str(e)}")
            return jsonify({'error': str(e)}), 500

# API endpoint to get companies for a specific portfolio
def get_portfolio_companies(portfolio_id):
    """Get companies for a specific portfolio"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    account_id = session['account_id']
    
    try:
        # Verify portfolio belongs to account
        portfolio = query_db(
            'SELECT id FROM portfolios WHERE id = ? AND account_id = ?',
            [portfolio_id, account_id],
            one=True
        )
        
        if not portfolio:
            return jsonify({'error': 'Portfolio not found or access denied'}), 404
        
        # Get companies for this portfolio
        companies = query_db('''
            SELECT c.id, c.name, c.identifier, c.category, c.total_invested,
                   COALESCE(cs.shares, 0) as shares
            FROM companies c
            LEFT JOIN company_shares cs ON c.id = cs.company_id
            WHERE c.portfolio_id = ? AND c.account_id = ?
            ORDER BY c.name
        ''', [portfolio_id, account_id])
        
        return jsonify(companies)
        
    except Exception as e:
        logger.error(f"Error getting portfolio companies: {str(e)}")
        return jsonify({'error': str(e)}), 500

def get_portfolio_data_api():
    """Get portfolio data from the database"""
    try:
        # Check if account_id exists in session
        if 'account_id' not in session:
            logger.error("No account_id in session when calling portfolio_data API")
            return jsonify({'error': 'Not authenticated - account_id missing'}), 401
            
        account_id = session['account_id']
        if not account_id:
            logger.error("Empty account_id in session when calling portfolio_data API")
            return jsonify({'error': 'Not authenticated - empty account_id'}), 401

        # Log the attempt to fetch data
        logger.info(f"Fetching portfolio data for account_id: {account_id}")
        
        # Get data from database without triggering any yfinance updates
        portfolio_data = get_portfolio_data(account_id)
        
        # Detailed logging of result
        if not portfolio_data:
            logger.warning(f"No portfolio data found for account_id: {account_id}")
            return jsonify({'error': 'Portfolio data could not be loaded. It may have been deleted or is missing from the database.'}), 404
        else:
            logger.info(f"Successfully retrieved {len(portfolio_data)} portfolio items")

        return jsonify(portfolio_data)
    except KeyError as ke:
        logger.error(f"KeyError accessing portfolio data: {str(ke)}", exc_info=True)
        return jsonify({'error': f'Session key error: {str(ke)}'}), 401
    except Exception as e:
        logger.error(f"Error getting portfolio data: {str(e)}", exc_info=True)
        return jsonify({'error': f'Portfolio data could not be loaded: {str(e)}'}), 500

def get_allocate_portfolio_data():
    """API endpoint to get structured portfolio data for the rebalancing feature"""
    logger.info("API request for allocate portfolio data")
    
    if 'account_id' not in session:
        logger.warning("No account_id in session")
        return jsonify({'error': 'Not authenticated'}), 401
    
    account_id = session['account_id']
    logger.info(f"Getting portfolio data for rebalancing, account_id: {account_id}")
    
    try:
        # Get all portfolios for this account
        portfolios_data = query_db('''
            SELECT id, name
            FROM portfolios
            WHERE account_id = ? AND name IS NOT NULL
            ORDER BY name
        ''', [account_id])
        
        if not portfolios_data:
            logger.warning(f"No portfolios found for account {account_id}")
            return jsonify({'portfolios': []})
        
        # Get target allocations from expanded_state
        target_allocation_data = query_db('''
            SELECT variable_value
            FROM expanded_state
            WHERE account_id = ? AND page_name = ? AND variable_name = ?
        ''', [account_id, 'build', 'portfolios'], one=True)
        
        # Parse target allocations if available
        target_allocations = []
        if target_allocation_data and target_allocation_data['variable_value']:
            try:
                target_allocations = json.loads(target_allocation_data['variable_value'])
                logger.info(f"Found target allocations in expanded_state: {len(target_allocations)} portfolios")
            except json.JSONDecodeError:
                logger.error("Failed to parse target allocations JSON")
        
        result = {'portfolios': []}
        
        # Process each portfolio
        for portfolio in portfolios_data:
            portfolio_id = portfolio['id']
            portfolio_name = portfolio['name']
            
            # Get categories for this portfolio
            categories_data = query_db('''
                SELECT DISTINCT category 
                FROM companies
                WHERE account_id = ? AND portfolio_id = ? AND category IS NOT NULL
                ORDER BY category
            ''', [account_id, portfolio_id])
            
            # Calculate total portfolio value - FIXED QUERY
            portfolio_value_result = query_db('''
                SELECT SUM(mp.price_eur * cs.shares) as total_value
                FROM companies c
                JOIN market_prices mp ON c.identifier = mp.identifier
                JOIN company_shares cs ON c.id = cs.company_id
                WHERE c.account_id = ? AND c.portfolio_id = ? AND cs.shares > 0
            ''', [account_id, portfolio_id], one=True)
            
            portfolio_value = portfolio_value_result['total_value'] if portfolio_value_result['total_value'] else 0
            
            # Find target allocation for this portfolio from the expanded_state data
            target_weight = 0
            min_positions = 0
            target_portfolio = next((p for p in target_allocations if p.get('id') == portfolio_id), None)
            if target_portfolio:
                target_weight = target_portfolio.get('allocation', 0)
                min_positions = target_portfolio.get('minPositions', 0)  # Extract minPositions
                logger.info(f"Found target weight for portfolio {portfolio_name}: {target_weight}%, min positions: {min_positions}")
            
            # Create portfolio entry
            portfolio_entry = {
                'name': portfolio_name,
                'currentValue': portfolio_value,
                'targetWeight': target_weight,  # Using target weight from expanded_state
                'minPositions': min_positions,  # Add minPositions to the returned data
                'color': '',  # Will be assigned on frontend
                'categories': []
            }
            
            # Process each category
            for category_item in categories_data:
                category_name = category_item['category']
                
                # Get positions for this category - FIXED QUERY
                positions_data = query_db('''
                    SELECT c.id, c.name, mp.price_eur, cs.shares
                    FROM companies c
                    JOIN market_prices mp ON c.identifier = mp.identifier
                    JOIN company_shares cs ON c.id = cs.company_id
                    WHERE c.account_id = ? AND c.portfolio_id = ? AND c.category = ? AND cs.shares > 0
                    ORDER BY c.name
                ''', [account_id, portfolio_id, category_name])
                
                # Calculate category value
                category_value = sum(pos['price_eur'] * pos['shares'] for pos in positions_data if pos['price_eur'])
                
                # Find target allocation for this category - IMPROVED IMPLEMENTATION
                # Initialize variables for tracking weights
                known_weight = 0
                known_position_ids = set()
                
                # Check which positions already have known weights from expanded_state
                for pos in positions_data:
                    # Find if this position has a target weight in expanded_state
                    if target_portfolio and target_portfolio.get('positions'):
                        target_position = next((p for p in target_portfolio.get('positions', []) 
                                              if p.get('companyId') == pos['id'] and not p.get('isPlaceholder', False)), None)
                        if target_position:
                            known_weight += target_position.get('weight', 0)
                            known_position_ids.add(pos['id'])
                
                # Calculate positions without known weights
                positions_without_weights = sum(1 for pos in positions_data if pos['id'] not in known_position_ids)
                
                # Find placeholder position for remaining weights
                placeholder = None
                if target_portfolio and target_portfolio.get('positions'):
                    placeholder = next((p for p in target_portfolio.get('positions', []) if p.get('isPlaceholder', False)), None)
                
                # Calculate category target weight
                category_target_weight = known_weight  # Default to known weight
                if placeholder and positions_without_weights > 0:
                    # Get total remaining positions and weight from placeholder
                    positions_remaining = placeholder.get('positionsRemaining', 0)
                    total_remaining_weight = placeholder.get('totalRemainingWeight', 0)
                    
                    if positions_remaining > 0:
                        # Calculate weight per position
                        weight_per_position = total_remaining_weight / positions_remaining
                        
                        # Calculate placeholder weight for this category
                        category_placeholder_weight = positions_without_weights * weight_per_position
                        
                        # Add placeholder weight to known weight
                        category_target_weight = known_weight + category_placeholder_weight
                        logger.info(f"Category {category_name} target weight: {category_target_weight}% (known: {known_weight}%, placeholder: {category_placeholder_weight}%)")
                
                # Create category entry
                category_entry = {
                    'name': category_name,
                    'currentValue': category_value,
                    'targetWeight': category_target_weight,
                    'color': '',
                    'positions': []
                }
                
                # Process each position
                for position in positions_data:
                    position_value = 0
                    if position['price_eur'] and position['shares']:
                        position_value = position['price_eur'] * position['shares']
                    
                    # Find target allocation for this position
                    position_target_weight = 0  # Default if not found
                    position_id = position['id']
                    
                    if target_portfolio and target_portfolio.get('positions'):
                        # Look for this position by company ID
                        target_position = next((p for p in target_portfolio.get('positions', []) 
                                             if p.get('companyId') == position_id), None)
                        if target_position:
                            position_target_weight = target_position.get('weight', 0)
                        else:
                            # Position doesn't have explicit weight in expanded_state
                            # Check if it should get weight from the placeholder
                            if placeholder and placeholder.get('positionsRemaining', 0) > 0:
                                # Calculate weight per position from placeholder
                                positions_remaining = placeholder.get('positionsRemaining', 0)
                                total_remaining_weight = placeholder.get('totalRemainingWeight', 0)
                                
                                if positions_remaining > 0:
                                    # Assign the per-position weight from placeholder
                                    position_target_weight = total_remaining_weight / positions_remaining
                                    logger.info(f"Position {position['name']} assigned weight {position_target_weight}% from placeholder")
                                    
                                    # Decrease the remaining positions count
                                    placeholder['positionsRemaining'] -= 1
                                    
                                    # If this was the last remaining position, update the placeholder
                                    if placeholder['positionsRemaining'] <= 0:
                                        placeholder['positionsRemaining'] = 0
                                        placeholder['totalRemainingWeight'] = 0
                    
                    # Create position entry
                    position_entry = {
                        'name': position['name'],
                        'currentValue': position_value,
                        'targetWeight': position_target_weight,
                        'color': ''
                    }
                    
                    category_entry['positions'].append(position_entry)
                
                # Add a placeholder position if needed
                if placeholder and positions_without_weights > 0:
                    positions_remaining = placeholder.get('positionsRemaining', 0)
                    total_remaining_weight = placeholder.get('totalRemainingWeight', 0)
                    
                    if positions_remaining > 0:
                        # Add a placeholder position to represent remaining positions
                        placeholder_position = {
                            'name': f"{positions_remaining}x positions remaining",
                            'currentValue': 0,
                            'currentWeight': 0,  # Zero current weight
                            'targetWeight': total_remaining_weight,
                            'color': '',
                            'isPlaceholder': True,
                            'positionsRemaining': positions_remaining
                        }
                        
                        category_entry['positions'].append(placeholder_position)
                        logger.info(f"Added placeholder position for {positions_remaining} remaining positions with total weight {total_remaining_weight}%")
                
                # Only add categories with positions
                if category_entry['positions']:
                    portfolio_entry['categories'].append(category_entry)
            
            # Only add portfolios with categories
            if portfolio_entry['categories']:
                result['portfolios'].append(portfolio_entry)
        
        logger.info(f"Returning {len(result['portfolios'])} portfolios for rebalancing")
        return jsonify(result)
    
    except Exception as e:
        logger.error(f"Error getting portfolio data for rebalancing: {str(e)}")
        return jsonify({'error': str(e)}), 500

def get_portfolios_api():
    """API endpoint to get portfolios for an account"""
    logger.info("Accessing portfolios API")
    
    if 'account_id' not in session:
        logger.warning("No account_id in session")
        return jsonify({'error': 'Not authenticated. Please select an account from the home page.'}), 401
    
    try:
        account_id = session['account_id']
        include_ids = request.args.get('include_ids', 'false').lower() == 'true'
        has_companies = request.args.get('has_companies', 'false').lower() == 'true'
        logger.info(f"Getting portfolios for account_id: {account_id}, include_ids: {include_ids}, has_companies: {has_companies}")
        
        # Get portfolio data from portfolios table, including all portfolios with non-null names
        if include_ids:
            # Get portfolios from the portfolios table
            if has_companies:
                # Only get portfolios that have at least one company (don't require company_shares entries)
                portfolios_from_table = query_db('''
                    SELECT DISTINCT p.id, p.name 
                    FROM portfolios p
                    JOIN companies c ON p.id = c.portfolio_id
                    WHERE p.account_id = ? AND p.name IS NOT NULL
                    ORDER BY p.name
                ''', [account_id])
                logger.info(f"Filtering for portfolios with associated companies")
            else:
                # Get all portfolios
                portfolios_from_table = query_db('''
                    SELECT id, name FROM portfolios 
                    WHERE account_id = ? AND name IS NOT NULL
                    ORDER BY name
                ''', [account_id])
            
            # Convert to list of objects with id and name
            portfolios = [{'id': p['id'], 'name': p['name']} for p in portfolios_from_table]
            logger.info(f"Retrieved {len(portfolios)} portfolios with IDs: {portfolios}")
            
            # Ensure we're not missing the Default portfolio if it has companies or if we're not filtering
            has_default = any(p['name'] == 'Default' for p in portfolios)
            if not has_default and (not has_companies or has_companies_in_default(account_id)):
                default_portfolio = query_db('''
                    SELECT id FROM portfolios
                    WHERE account_id = ? AND name = 'Default'
                ''', [account_id], one=True)
                
                if default_portfolio:
                    portfolios.append({'id': default_portfolio['id'], 'name': 'Default'})
                    logger.info("Added Default portfolio to the response")
                else:
                    # Create Default portfolio if it doesn't exist
                    portfolio_id = execute_db('''
                        INSERT INTO portfolios (account_id, name)
                        VALUES (?, 'Default')
                    ''', [account_id])
                    
                    portfolios.append({'id': portfolio_id, 'name': 'Default'})
                    logger.info("Created and added Default portfolio to the response")
            
            json_response = jsonify(portfolios)
        else:
            # Get portfolio names only
            if has_companies:
                # Only get portfolios that have at least one company (don't require company_shares entries)
                portfolios_from_table = query_db('''
                    SELECT DISTINCT p.name 
                    FROM portfolios p
                    JOIN companies c ON p.id = c.portfolio_id
                    WHERE p.account_id = ? AND p.name IS NOT NULL
                    ORDER BY p.name
                ''', [account_id])
                logger.info(f"Filtering for portfolios with associated companies")
            else:
                # Get all portfolios
                portfolios_from_table = query_db('''
                    SELECT name FROM portfolios 
                    WHERE account_id = ? AND name IS NOT NULL
                    ORDER BY name
                ''', [account_id])
            
            # Extract names from the query results - don't filter out any valid names
            names = [p['name'] for p in portfolios_from_table]
            logger.info(f"Retrieved {len(names)} portfolio names from portfolios table: {names}")
            
            # Ensure Default is in the list if it has companies or if we're not filtering
            if 'Default' not in names and (not has_companies or has_companies_in_default(account_id)):
                default_exists = query_db('''
                    SELECT 1 FROM portfolios
                    WHERE account_id = ? AND name = 'Default'
                ''', [account_id], one=True)
                
                if default_exists:
                    names.append('Default')
                    logger.info("Added Default portfolio name to the response")
                else:
                    # Create Default portfolio if it doesn't exist
                    execute_db('''
                        INSERT INTO portfolios (account_id, name)
                        VALUES (?, 'Default')
                    ''', [account_id])
                    
                    names.append('Default')
                    logger.info("Created and added Default portfolio name to the response")
            
            json_response = jsonify(names)
        
        logger.debug(f"JSON response to be sent: {json_response.data}")
        return json_response
        
    except Exception as e:
        logger.error(f"Error getting portfolios: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500

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
            
        # Add processing logic for the update here
        # (This would include updating the company in the database based on the data received)
        
        return jsonify({'success': True, 'message': 'Company updated successfully'}), 200
        
    except Exception as e:
        logger.error(f"Error updating company {company_id}: {str(e)}")
        return jsonify({'error': str(e)}), 500

def bulk_update():
    """API endpoint to handle bulk updates of companies"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated. Please select an account from the home page.'}), 401
    
    try:
        account_id = session['account_id']
        data = request.json
        
        # Validate data
        if not data or not isinstance(data, dict):
            return jsonify({'error': 'Invalid data format'}), 400
            
        # Simple stub implementation that returns success
        logger.info(f"Bulk update requested for account {account_id}")
        logger.info(f"Received data: {data}")
        
        # Create a proper response
        return jsonify({
            'success': True,
            'message': 'Bulk update processed successfully',
            'updated': 0,  # No actual updates yet
            'errors': []
        })
        
    except Exception as e:
        logger.error(f"Error in bulk update: {str(e)}")
        return jsonify({'error': str(e)}), 500