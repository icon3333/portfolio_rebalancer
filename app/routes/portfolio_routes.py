from flask import (
    Blueprint, render_template, redirect, url_for, 
    request, flash, session, jsonify, current_app
)
from app.database.db_manager import query_db, execute_db, backup_database, get_db
import pandas as pd
import json
import sqlite3
from datetime import datetime
import os

portfolio_bp = Blueprint('portfolio', __name__)

@portfolio_bp.route('/enrich')
def enrich():
    """Portfolio data enrichment page"""
    # Check if user is authenticated with an account
    if 'account_id' not in session:
        flash('Please select an account first', 'warning')
        return redirect(url_for('main.index'))
    
    account_id = session['account_id']
    
    # Get portfolio data
    portfolio_data = get_portfolio_data(account_id)
    
    # Get portfolios for dropdown
    portfolios = query_db('''
        SELECT id, name FROM portfolios 
        WHERE account_id = ? AND name != '-' 
        ORDER BY name
    ''', [account_id])
    
    return render_template('pages/enrich.html',
                           portfolio_data=portfolio_data,
                           portfolios=portfolios)

@portfolio_bp.route('/api/portfolio_data')
def get_portfolio_data_api():
    """API endpoint to get portfolio data"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    account_id = session['account_id']
    portfolio_data = get_portfolio_data(account_id)
    
    return jsonify(portfolio_data)

@portfolio_bp.route('/api/update_portfolio', methods=['POST'])
def update_portfolio_api():
    """API endpoint to update portfolio data"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
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
        db.execute('BEGIN TRANSACTION')
        
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
                        db.execute(
                            'INSERT INTO portfolios (name, account_id) VALUES (?, ?)',
                            [item['portfolio'], account_id]
                        )
                        portfolio_id = db.lastrowid
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
                        db.execute(
                            'INSERT INTO portfolios (name, account_id) VALUES (?, ?)',
                            ['-', account_id]
                        )
                        portfolio_id = db.lastrowid
                    else:
                        portfolio_id = portfolio_result['id']
                
                # Update company
                db.execute('''
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
                        db.execute('''
                            UPDATE company_shares
                            SET shares = ?, override_share = ?
                            WHERE company_id = ?
                        ''', [shares, override_share, company_id])
                    else:
                        db.execute('''
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
        
        # Read CSV file
        df = pd.read_csv(file, delimiter=';')
        
        # Validate required columns
        required_columns = [
            "datetime", "date", "time", "price", "shares", "amount", "tax", 
            "fee", "realizedgains", "type", "broker", "assettype", "identifier",
            "wkn", "originalcurrency", "currency", "fxrate", "holding",
            "holdingname", "holdingnickname", "exchange", "avgholdingperiod"
        ]
        
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            flash(f'Missing required columns: {", ".join(missing_columns)}', 'error')
            return redirect(url_for('portfolio.enrich'))
        
        # Process and import the data
        process_csv_data(df, account_id)
        
        flash('CSV data imported successfully', 'success')
        
    except Exception as e:
        flash(f'Error processing CSV: {str(e)}', 'error')
    
    return redirect(url_for('portfolio.enrich'))

@portfolio_bp.route('/api/portfolios')
def get_portfolios_api():
    """API endpoint to get portfolios for an account"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    account_id = session['account_id']
    portfolios = query_db('''
        SELECT id, name FROM portfolios 
        WHERE account_id = ? AND name != '-'
        ORDER BY name
    ''', [account_id])
    
    return jsonify(portfolios)

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

def get_portfolio_data(account_id):
    """Get portfolio data from the database"""
    # Query to get portfolio data with prices
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
    
    # Process data for frontend
    for item in data:
        # Handle empty values
        if item['portfolio'] is None or item['portfolio'] == '':
            item['portfolio'] = '-'
        if item['category'] is None or item['category'] == '':
            item['category'] = '-'
        
        # Calculate effective shares
        if item['override_share'] is not None and item['override_share'] > 0:
            item['effective_shares'] = item['override_share']
        else:
            item['effective_shares'] = item['shares']
            
        # Calculate total value
        if item['price_eur'] is not None and item['effective_shares'] is not None:
            item['total_value_eur'] = item['price_eur'] * item['effective_shares']
        else:
            item['total_value_eur'] = 0
    
    return data

def process_csv_data(df, account_id):
    """Process and import CSV data into the database"""
    # Filter to valid transaction types
    valid_types = ['Buy', 'Sell', 'TransferOut', 'TransferIn']
    df['type'] = df['type'].str.strip()
    df = df[df['type'].isin(valid_types)]
    
    if df.empty:
        raise ValueError('No valid transactions found in CSV file')
    
    # Clean data
    df['identifier'] = df['identifier'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
    df['holdingname'] = df['holdingname'].apply(lambda x: str(x).strip() if pd.notna(x) else '')
    df = df[df['identifier'].str.len() > 0]
    
    if df.empty:
        raise ValueError('No valid entries found in CSV file after cleaning')
    
    # Calculate shares effect
    df['shares_effect'] = df.apply(
        lambda row: row['shares'] if row['type'] in ['Buy', 'TransferIn'] else -row['shares'],
        axis=1
    )
    df['total_invested_effect'] = df['shares_effect'] * df['price']
    
    # Aggregate data
    aggregated_data = df.groupby(['holdingname', 'identifier']).agg({
        'shares_effect': 'sum',
        'total_invested_effect': 'sum'
    }).reset_index()
    
    # Get database connection
    db = get_db()
    db.execute('BEGIN TRANSACTION')
    
    try:
        # Ensure default portfolio exists
        default_portfolio = query_db(
            'SELECT id FROM portfolios WHERE name = "-" AND account_id = ?',
            [account_id],
            one=True
        )
        
        if not default_portfolio:
            db.execute(
                'INSERT INTO portfolios (name, account_id) VALUES (?, ?)',
                ['-', account_id]
            )
            default_portfolio_id = db.lastrowid
        else:
            default_portfolio_id = default_portfolio['id']
        
        # Process each aggregated row
        positions_added = []
        positions_updated = []
        positions_removed = []
        
        for _, row in aggregated_data.iterrows():
            company_name = row['holdingname']
            identifier = row['identifier']
            share_count = float(row['shares_effect'])
            total_invested = float(row['total_invested_effect'])
            
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
                    db.execute(
                        'DELETE FROM company_shares WHERE company_id = ?',
                        [company['id']]
                    )
                    # Then delete company
                    db.execute(
                        'DELETE FROM companies WHERE id = ?',
                        [company['id']]
                    )
                    positions_removed.append(company_name)
                continue
            
            if company:
                # Update existing company
                db.execute('''
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
                    db.execute('''
                        UPDATE company_shares 
                        SET shares = ?
                        WHERE company_id = ?
                    ''', [share_count, company['id']])
                else:
                    db.execute('''
                        INSERT INTO company_shares (company_id, shares)
                        VALUES (?, ?)
                    ''', [company['id'], share_count])
                
                positions_updated.append(company_name)
            else:
                # Insert new company
                db.execute('''
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
                
                company_id = db.lastrowid
                
                # Insert shares
                db.execute('''
                    INSERT INTO company_shares (company_id, shares)
                    VALUES (?, ?)
                ''', [company_id, share_count])
                
                positions_added.append(company_name)
        
        # Commit transaction
        db.commit()
        
        return {
            'added': positions_added,
            'updated': positions_updated,
            'removed': positions_removed
        }
        
    except Exception as e:
        db.rollback()
        raise e