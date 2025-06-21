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
    get_portfolio_data, process_csv_data, has_companies_in_default, get_stock_info
)
from app.utils.yfinance_utils import get_isin_data
from app.utils.db_utils import update_price_in_db

import pandas as pd
import logging
from datetime import datetime
import time
import uuid
import json
import io
from typing import Dict, Any, Optional, List

# Set up logger
logger = logging.getLogger(__name__)


def _apply_company_update(cursor, company_id, data, account_id):
    """Internal helper to update company and share data."""
    portfolio_name = data.get('portfolio')
    if portfolio_name and portfolio_name != 'None':
        portfolio = query_db(
            'SELECT id FROM portfolios WHERE name = ? AND account_id = ?',
            [portfolio_name, account_id],
            one=True
        )
        if not portfolio:
            cursor.execute(
                'INSERT INTO portfolios (name, account_id) VALUES (?, ?)',
                [portfolio_name, account_id]
            )
            portfolio_id = cursor.lastrowid
        else:
            portfolio_id = portfolio['id'] if isinstance(portfolio, dict) else None
    else:
        # Assign to 'Default' portfolio if no portfolio is specified
        default_portfolio = query_db(
            'SELECT id FROM portfolios WHERE name = ? AND account_id = ?',
            ['Default', account_id], one=True)

        if not default_portfolio:
            # Create 'Default' portfolio if it doesn't exist
            cursor.execute(
                'INSERT INTO portfolios (name, account_id) VALUES (?, ?)',
                ['Default', account_id]
            )
            portfolio_id = cursor.lastrowid
            logger.info(
                f"Created 'Default' portfolio for account_id: {account_id}")
        else:
            portfolio_id = default_portfolio['id'] if isinstance(default_portfolio, dict) else None

    # Build the SET clause dynamically based on what data is provided
    set_clause_parts = []
    params = []
    
    if 'identifier' in data:
        set_clause_parts.append('identifier = ?')
        params.append(data.get('identifier', ''))
    
    if 'category' in data:
        set_clause_parts.append('category = ?')
        params.append(data.get('category', ''))
    
    # Always update portfolio_id since this is called for portfolio changes
    set_clause_parts.append('portfolio_id = ?')
    params.append(portfolio_id)
    
    # Add the company_id for the WHERE clause
    params.append(company_id)
    
    if set_clause_parts:
        set_clause = ', '.join(set_clause_parts)
        cursor.execute(f'UPDATE companies SET {set_clause} WHERE id = ?', params)

    if 'shares' in data or 'override_share' in data:
        shares = data.get('shares')
        override = data.get('override_share')
        exists = query_db(
            'SELECT company_id FROM company_shares WHERE company_id = ?',
            [company_id], one=True)
        if exists:
            cursor.execute(
                'UPDATE company_shares SET shares = ?, override_share = ? WHERE company_id = ?',
                [shares, override, company_id]
            )
        else:
            cursor.execute(
                'INSERT INTO company_shares (company_id, shares, override_share) VALUES (?, ?, ?)',
                [company_id, shares, override]
            )

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
                if isinstance(var, dict):
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

            with get_db() as db:
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

            logger.info(
                f"State saved successfully for account {account_id}, page {page_name}")
            return jsonify({'success': True, 'message': 'State saved successfully'})

        except Exception as e:
            logger.error(f"Error saving state: {str(e)}")
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Method not allowed'}), 405

# API endpoint to get companies for a specific portfolio


def get_allocate_portfolio_data():
    """API endpoint to get structured portfolio data for the rebalancing feature"""
    logger.info("API request for allocate portfolio data")

    if 'account_id' not in session:
        logger.warning("No account_id in session")
        return jsonify({'error': 'Not authenticated'}), 401

    account_id = session['account_id']
    logger.info(
        f"Getting portfolio data for rebalancing, account_id: {account_id}")

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
        if target_allocation_data and isinstance(target_allocation_data, dict):
            variable_value = target_allocation_data.get('variable_value')
            if variable_value:
                try:
                    target_allocations = json.loads(variable_value)
                    logger.info(
                        f"Found target allocations in expanded_state: {len(target_allocations)} portfolios")
                except json.JSONDecodeError:
                    logger.error("Failed to parse target allocations JSON")

        # Create comprehensive builder data maps
        position_target_weights = {}
        portfolio_builder_data = {}
        
        for portfolio in target_allocations:
            portfolio_id = portfolio.get('id')
            if not portfolio_id:
                continue

            # Store complete builder configuration for each portfolio
            portfolio_builder_data[portfolio_id] = {
                'minPositions': portfolio.get('minPositions', 0),
                'allocation': portfolio.get('allocation', 0),
                'positions': portfolio.get('positions', []),
                'name': portfolio.get('name', 'Unknown')
            }

            # Store target weights for real positions
            for position in portfolio.get('positions', []):
                if not position.get('isPlaceholder'):
                    position_key = (portfolio_id, position.get('companyName'))
                    position_target_weights[position_key] = position.get('weight', 0)

        # Count total positions across all portfolios to determine
        # the flat weight for each position
        total_positions = 0
        portfolio_positions_count = {}
        portfolio_min_positions = {}  # Store minimum positions needed per portfolio

        # First pass: Count all positions (real + placeholder) across ALL portfolios
        for portfolio in target_allocations:
            portfolio_id = portfolio.get('id')
            real_positions = [p for p in portfolio.get(
                'positions', []) if not p.get('isPlaceholder', False)]
            placeholder = next((p for p in portfolio.get(
                'positions', []) if p.get('isPlaceholder', False)), None)

            positions_count = len(real_positions)
            if placeholder:
                positions_count += placeholder.get('positionsRemaining', 0)

            portfolio_positions_count[portfolio_id] = positions_count

            # Extract minimum positions needed from target allocations
            # For "dividend" portfolio, this should be 20 positions
            min_positions = portfolio.get('minPositions', positions_count)
            portfolio_min_positions[portfolio_id] = max(
                min_positions, positions_count)

            # Log minimum positions for each portfolio
            portfolio_name = portfolio.get('name', 'Unknown')
            logger.info(
                f"Portfolio {portfolio_name} needs minimum {portfolio_min_positions[portfolio_id]} positions")

            total_positions += positions_count

        # Calculate uniform global weight for all positions
        flat_position_weight = 100.0 / total_positions if total_positions > 0 else 0
        logger.info(
            f"FLAT DISTRIBUTION: {total_positions} total positions with {flat_position_weight:.2f}% each"
        )

        result = {'portfolios': []}

        # Fetch all portfolio/company data in one query
        data = query_db('''
            SELECT p.id AS portfolio_id, p.name AS portfolio_name,
                   c.category, c.name AS company_name, c.identifier,
                   cs.shares, mp.price_eur
            FROM portfolios p
            LEFT JOIN companies c ON c.portfolio_id = p.id AND c.account_id = p.account_id
            LEFT JOIN company_shares cs ON c.id = cs.company_id
            LEFT JOIN market_prices mp ON c.identifier = mp.identifier
            WHERE p.account_id = ? AND p.name IS NOT NULL
            ORDER BY p.name, c.category, c.name
        ''', [account_id])

        # Group data by portfolio and category
        portfolio_map = {}
        if data:  # Check if data is not None
            for row in data:
                if isinstance(row, dict):
                    pid = row['portfolio_id']
                    pname = row['portfolio_name']
                    portfolio = portfolio_map.setdefault(
                        pid, {'name': pname, 'categories': {}, 'currentValue': 0})

                    if row['company_name']:
                        # Use 'Uncategorized' as default category for positions without a category
                        category_name = row['category'] if row['category'] else 'Uncategorized'
                        cat = portfolio['categories'].setdefault(
                            category_name, {'positions': [], 'currentValue': 0})
                        pos_value = (row['price_eur'] or 0) * (row['shares'] or 0)
                        portfolio['currentValue'] += pos_value
                        cat['currentValue'] += pos_value
                        target_weight = position_target_weights.get(
                            (pid, row['company_name']), 0)
                        cat['positions'].append({
                            'name': row['company_name'],
                            'currentValue': pos_value,
                            'targetAllocation': target_weight,
                            'identifier': row['identifier']
                        })

        # Calculate total current value across all portfolios
        total_current_value = sum(pdata['currentValue'] for pdata in portfolio_map.values())
        logger.info(f"Total current value across all portfolios: {total_current_value}")

        for portfolio_id, pdata in portfolio_map.items():
            portfolio_name = pdata['name']

            portfolio_target_weight = 0
            target_portfolio = next(
                (p for p in target_allocations if p.get('id') == portfolio_id), None)
            if target_portfolio:
                portfolio_target_weight = target_portfolio.get('allocation', 0)
                logger.info(
                    f"Found target weight for portfolio {portfolio_name}: {portfolio_target_weight}%")

            # Get builder data for this portfolio
            builder_data = portfolio_builder_data.get(portfolio_id, {})
            
            portfolio_entry = {
                'name': portfolio_name,
                'currentValue': pdata['currentValue'],
                'targetWeight': portfolio_target_weight,
                'color': '',
                'categories': [],
                # Add builder configuration data
                'minPositions': builder_data.get('minPositions', 0),
                'builderPositions': builder_data.get('positions', []),
                'builderAllocation': builder_data.get('allocation', 0)
            }

            for cat_name, cat_data in pdata['categories'].items():
                category_entry = {
                    'name': cat_name,
                    'positions': cat_data['positions'],
                    'currentValue': cat_data['currentValue'],
                    'positionCount': len(cat_data['positions'])
                }
                portfolio_entry['categories'].append(category_entry)
            
            # Add placeholder positions based on builder configuration
            builder_positions = builder_data.get('positions', [])
            min_positions = builder_data.get('minPositions', 0)
            
            # Count current real positions
            current_positions_count = sum(len(cat_data['positions']) for cat_data in pdata['categories'].values())
            placeholder_position = next((pos for pos in builder_positions if pos.get('isPlaceholder')), None)
            
            if placeholder_position and current_positions_count < min_positions:
                positions_remaining = min_positions - current_positions_count
                
                # Create Missing Positions category if needed
                missing_positions_category = {
                    'name': 'Missing Positions',
                    'positions': [{
                        'name': f'Position Slot {i+1} (Unfilled)',
                        'currentValue': 0,
                        'targetAllocation': placeholder_position.get('weight', 0),
                        'identifier': None,
                        'isPlaceholder': True,
                        'positionSlot': i+1
                    } for i in range(positions_remaining)],
                    'currentValue': 0,
                    'positionCount': positions_remaining,
                    'isPlaceholder': True
                }
                portfolio_entry['categories'].append(missing_positions_category)

            portfolio_target_value = (portfolio_target_weight / 100) * total_current_value
            portfolio_entry['targetValue'] = portfolio_target_value

            for cat in portfolio_entry['categories']:
                cat_target_value = 0
                for pos in cat['positions']:
                    pos_target_value = (
                        pos['targetAllocation'] / 100) * portfolio_target_value
                    pos['targetValue'] = pos_target_value
                    cat_target_value += pos_target_value

                cat['targetValue'] = cat_target_value
                cat['targetWeight'] = (
                    cat_target_value / portfolio_target_value * 100) if portfolio_target_value > 0 else 0

            portfolio_entry['targetAllocation_portfolio'] = portfolio_target_value
            result['portfolios'].append(portfolio_entry)

        logger.info(
            f"Returning {len(result['portfolios'])} portfolios with flat {flat_position_weight:.2f}% weight per position")
        return jsonify(result)

    except Exception as e:
        logger.error(f"Error getting portfolio data for rebalancing: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Ensure this function exists to prevent import errors


def get_portfolio_data_api():
    """Get portfolio data from the database"""
    try:
        # Check if account_id exists in session
        if 'account_id' not in session:
            logger.error(
                "No account_id in session when calling portfolio_data API")
            return jsonify({'error': 'Not authenticated - account_id missing'}), 401

        account_id = session['account_id']
        if not account_id:
            logger.error(
                "Empty account_id in session when calling portfolio_data API")
            return jsonify({'error': 'Not authenticated - empty account_id'}), 401

        # Log the attempt to fetch data
        logger.info(f"Fetching portfolio data for account_id: {account_id}")

        # Get data from database without triggering any yfinance updates
        portfolio_data = get_portfolio_data(account_id)

        # Detailed logging of result
        if not portfolio_data:
            logger.warning(
                f"No portfolio data found for account_id: {account_id}")
            return jsonify({'error': 'Portfolio data could not be loaded. It may have been deleted or is missing from the database.'}), 404
        else:
            logger.info(
                f"Successfully retrieved {len(portfolio_data)} portfolio items")

        return jsonify(portfolio_data)
    except KeyError as ke:
        logger.error(
            f"KeyError accessing portfolio data: {str(ke)}", exc_info=True)
        return jsonify({'error': f'Session key error: {str(ke)}'}), 401
    except Exception as e:
        logger.error(f"Error getting portfolio data: {str(e)}", exc_info=True)
        return jsonify({'error': f'Portfolio data could not be loaded: {str(e)}'}), 500


def get_portfolios_api():
    """API endpoint to get portfolios for an account"""
    logger.info("Accessing portfolios API")

    if 'account_id' not in session:
        logger.warning("No account_id in session")
        return jsonify({'error': 'Not authenticated. Please select an account from the home page.'}), 401

    try:
        account_id = session['account_id']
        include_ids = request.args.get(
            'include_ids', 'false').lower() == 'true'
        has_companies = request.args.get(
            'has_companies', 'false').lower() == 'true'
        logger.info(
            f"Getting portfolios for account_id: {account_id}, include_ids: {include_ids}, has_companies: {has_companies}")

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
                logger.info(
                    f"Filtering for portfolios with associated companies")
            else:
                # Get all portfolios
                portfolios_from_table = query_db('''
                    SELECT id, name FROM portfolios 
                    WHERE account_id = ? AND name IS NOT NULL
                    ORDER BY name
                ''', [account_id])

            # Convert to list of objects with id and name
            portfolios = []
            if portfolios_from_table:
                portfolios = [{'id': p['id'], 'name': p['name']}
                              for p in portfolios_from_table if isinstance(p, dict)]
            logger.info(
                f"Retrieved {len(portfolios)} portfolios with IDs: {portfolios}")

            # Ensure we're not missing the Default portfolio if it has companies or if we're not filtering
            has_default = any(p['name'] == 'Default' for p in portfolios)
            if not has_default and (not has_companies or has_companies_in_default(account_id)):
                default_portfolio = query_db('''
                    SELECT id FROM portfolios
                    WHERE account_id = ? AND name = 'Default'
                ''', [account_id], one=True)

                if default_portfolio and isinstance(default_portfolio, dict):
                    portfolios.append(
                        {'id': default_portfolio['id'], 'name': 'Default'})
                    logger.info("Added Default portfolio to the response")
                else:
                    # Create Default portfolio if it doesn't exist
                    portfolio_id = execute_db('''
                        INSERT INTO portfolios (account_id, name)
                        VALUES (?, 'Default')
                    ''', [account_id])

                    portfolios.append({'id': portfolio_id, 'name': 'Default'})
                    logger.info(
                        "Created and added Default portfolio to the response")

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
                logger.info(
                    f"Filtering for portfolios with associated companies")
            else:
                # Get all portfolios
                portfolios_from_table = query_db('''
                    SELECT name FROM portfolios 
                    WHERE account_id = ? AND name IS NOT NULL
                    ORDER BY name
                ''', [account_id])

            # Extract names from the query results - don't filter out any valid names
            names = []
            if portfolios_from_table:
                names = [p['name'] for p in portfolios_from_table if isinstance(p, dict)]
            logger.info(
                f"Retrieved {len(names)} portfolio names from portfolios table: {names}")

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
                    logger.info(
                        "Created and added Default portfolio name to the response")

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
                message_parts.append(
                    f"Added {len(result['added'])} new positions")
            if result.get('updated'):
                message_parts.append(
                    f"Updated {len(result['updated'])} existing positions")
            if result.get('removed'):
                message_parts.append(
                    f"Removed {len(result['removed'])} positions with zero shares")

            flash(
                f"CSV data imported successfully. {' | '.join(message_parts)}", 'success')

            # Show warnings if any
            warnings = []
            if result.get('failed'):
                warnings.append(
                    f"Failed to process {len(result['failed'])} companies")

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
                    if company and isinstance(company, dict) and company.get('identifier'):
                        company_identifiers[company['identifier']] = company_name

                # Now filter the failed_prices to only those that match our newly added companies
                session_failed_prices = []
                for identifier in result.get('failed_prices', []):
                    if identifier in company_identifiers:
                        session_failed_prices.append(identifier)

                # Only report and log the failures from this session
                if session_failed_prices:
                    current_failure_count = len(session_failed_prices)
                    logger.warning(
                        f"Failed to fetch prices for {current_failure_count} identifiers from this upload: {', '.join(session_failed_prices)}")
                    warnings.append(
                        f"Failed to fetch prices for {current_failure_count} identifiers from this upload. Check logs for details.")

            # Show price update success message if relevant
            added_count = len(result.get('added', []))
            if added_count > 0:
                # Calculate the success count - if session_failed_prices exists, use it, otherwise assume all succeeded
                failure_count = len(session_failed_prices) if 'session_failed_prices' in locals(
                ) and session_failed_prices else 0
                prices_updated_count = added_count - failure_count
                if prices_updated_count > 0:
                    flash(
                        f"Successfully updated prices for {prices_updated_count} out of {added_count} newly added companies", 'success')

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

        db = get_db()
        cursor = db.cursor()

        # Preload existing data
        company_rows = query_db(
            'SELECT id, name, identifier FROM companies WHERE account_id = ?',
            [account_id]
        )
        company_map = {}
        if company_rows:
            company_map = {row['name']: row for row in company_rows if isinstance(row, dict)}

        portfolio_rows = query_db(
            'SELECT id, name FROM portfolios WHERE account_id = ?',
            [account_id]
        )
        portfolio_map = {}
        if portfolio_rows:
            portfolio_map = {row['name']: row['id'] for row in portfolio_rows if isinstance(row, dict)}

        share_rows = query_db(
            '''SELECT cs.company_id FROM company_shares cs
               JOIN companies c ON cs.company_id = c.id
               WHERE c.account_id = ?''',
            [account_id]
        )
        shares_set = set()
        if share_rows:
            shares_set = {row['company_id'] for row in share_rows if isinstance(row, dict)}

        cursor.execute('BEGIN TRANSACTION')

        updated_count = 0
        failed_items = []

        for item in data:
            try:
                company_result = company_map.get(item['company'])

                if not company_result:
                    failed_items.append({
                        'company': item['company'],
                        'error': 'Company not found'
                    })
                    continue

                company_id = company_result['id']
                original_identifier = company_result.get('identifier')
                new_identifier = item.get('identifier', '')

                portfolio_name = item.get('portfolio')
                if portfolio_name and portfolio_name != 'None':
                    portfolio_id = portfolio_map.get(portfolio_name)
                    if portfolio_id is None:
                        cursor.execute(
                            'INSERT INTO portfolios (name, account_id) VALUES (?, ?)',
                            [portfolio_name, account_id]
                        )
                        portfolio_id = cursor.lastrowid
                        portfolio_map[portfolio_name] = portfolio_id
                else:
                    portfolio_id = portfolio_map.get('-')
                    if portfolio_id is None:
                        cursor.execute(
                            'INSERT INTO portfolios (name, account_id) VALUES (?, ?)',
                            ['-', account_id]
                        )
                        portfolio_id = cursor.lastrowid
                        portfolio_map['-'] = portfolio_id

                # Update company
                cursor.execute('''
                    UPDATE companies 
                    SET identifier = ?, category = ?, portfolio_id = ?
                    WHERE id = ?
                ''', [
                    new_identifier,
                    item.get('category', ''),
                    portfolio_id,
                    company_id
                ])

                # If identifier was added or changed, fetch new price
                if new_identifier and new_identifier != original_identifier:
                    logger.info(
                        f"Identifier for {item['company']} changed to {new_identifier}, fetching price...")
                    try:
                        price_data = get_isin_data(new_identifier)
                        if price_data.get('price_eur') is not None:
                            # Safely extract values with defaults
                            price = price_data.get('price', 0.0)
                            currency = price_data.get('currency', 'EUR')
                            price_eur = price_data.get('price_eur', 0.0)
                            country = price_data.get('country')
                            sector = price_data.get('sector')
                            industry = price_data.get('industry')
                            exchange = price_data.get('exchange')
                            modified_identifier = price_data.get('modified_identifier')
                            
                            # Ensure required parameters are not None
                            if price is not None and currency is not None and price_eur is not None:
                                update_price_in_db(
                                    identifier=new_identifier,
                                    price=float(price),
                                    currency=str(currency),
                                    price_eur=float(price_eur),
                                    country=country,
                                    sector=sector,
                                    industry=industry,
                                    exchange=exchange,
                                    modified_identifier=modified_identifier
                                )
                                logger.info(
                                    f"Successfully updated price for {new_identifier}")
                            else:
                                logger.warning(
                                    f"Missing required price data for {new_identifier}")
                        else:
                            logger.warning(
                                f"Failed to fetch price for {new_identifier}: {price_data.get('error')}")
                    except Exception as e:
                        logger.error(
                            f"An error occurred while fetching price for {new_identifier}: {str(e)}")

                # Update shares
                if 'shares' in item or 'override_share' in item:
                    shares = item.get('shares')
                    override_share = item.get('override_share')

                    if company_id in shares_set:
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
                        shares_set.add(company_id)

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

            flash(
                f'Portfolio "{portfolio_name}" added successfully', 'success')

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

            flash(
                f'Portfolio renamed from "{old_name}" to "{new_name}"', 'success')

        elif action == 'delete':
            portfolio_name = request.form.get(
                'delete_portfolio_name', '').strip()

            if not portfolio_name:
                flash('Portfolio name is required', 'error')
                return redirect(url_for('portfolio.enrich'))

            # Check if portfolio is empty
            companies = query_db('''
                SELECT COUNT(*) as count FROM companies c
                JOIN portfolios p ON c.portfolio_id = p.id
                WHERE p.name = ? AND p.account_id = ?
            ''', [portfolio_name, account_id], one=True)

            if companies and isinstance(companies, dict) and companies.get('count', 0) > 0:
                flash(
                    f'Cannot delete portfolio "{portfolio_name}" because it contains companies', 'error')
                return redirect(url_for('portfolio.enrich'))

            # Delete portfolio
            execute_db(
                'DELETE FROM portfolios WHERE name = ? AND account_id = ?',
                [portfolio_name, account_id]
            )

            flash(
                f'Portfolio "{portfolio_name}" deleted successfully', 'success')

    except Exception as e:
        flash(f'Error managing portfolios: {str(e)}', 'error')

    return redirect(url_for('portfolio.enrich'))
