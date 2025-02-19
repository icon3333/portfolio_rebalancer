from flask import (
    Blueprint, render_template, redirect, url_for, 
    request, flash, session, jsonify
)
from app.database.db_manager import query_db, execute_db, backup_database
import sqlite3
from datetime import datetime

account_bp = Blueprint('account', __name__)

@account_bp.route('/')
def index():
    """Account management page"""
    # Check if user is authenticated with an account
    if 'account_id' not in session:
        flash('Please select an account first', 'warning')
        return redirect(url_for('main.index'))
    
    account_id = session['account_id']
    account = query_db('SELECT * FROM accounts WHERE id = ?', [account_id], one=True)
    
    # Get all accounts for the account switcher
    all_accounts = query_db('SELECT * FROM accounts WHERE username != "_global" ORDER BY username')
    
    return render_template('pages/account.html', 
                           account=account,
                           all_accounts=all_accounts)

@account_bp.route('/create', methods=['POST'])
def create_account():
    """Create a new account"""
    username = request.form.get('username', '').strip()
    
    if not username:
        flash('Username cannot be empty', 'error')
        return redirect(url_for('account.index'))
    
    try:
        # Create backup before making changes
        backup_database()
        
        # Insert new account
        created_at = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        execute_db(
            'INSERT INTO accounts (username, created_at) VALUES (?, ?)',
            [username, created_at]
        )
        
        # Get the new account ID
        new_account = query_db(
            'SELECT id FROM accounts WHERE username = ?',
            [username],
            one=True
        )
        
        if new_account:
            # Create default portfolio for the account
            execute_db(
                'INSERT INTO portfolios (name, account_id) VALUES (?, ?)',
                ['-', new_account['id']]
            )
            
            # Update session to use the new account
            session['account_id'] = new_account['id']
            session['username'] = username
            
            flash(f'Account "{username}" created successfully', 'success')
        else:
            flash('Failed to create account', 'error')
            
    except sqlite3.IntegrityError:
        flash(f'Account "{username}" already exists', 'error')
    except Exception as e:
        flash(f'Error creating account: {str(e)}', 'error')
    
    return redirect(url_for('account.index'))

@account_bp.route('/update', methods=['POST'])
def update_account():
    """Update account username"""
    if 'account_id' not in session:
        flash('Please select an account first', 'warning')
        return redirect(url_for('main.index'))
    
    account_id = session['account_id']
    new_username = request.form.get('new_username', '').strip()
    
    if not new_username:
        flash('Username cannot be empty', 'error')
        return redirect(url_for('account.index'))
    
    try:
        # Create backup before making changes
        backup_database()
        
        # Update username
        rows_affected = execute_db(
            'UPDATE accounts SET username = ? WHERE id = ?',
            [new_username, account_id]
        )
        
        if rows_affected > 0:
            # Update session with new username
            session['username'] = new_username
            flash(f'Username updated to "{new_username}"', 'success')
        else:
            flash('No changes made', 'warning')
            
    except sqlite3.IntegrityError:
        flash(f'Username "{new_username}" already exists', 'error')
    except Exception as e:
        flash(f'Error updating username: {str(e)}', 'error')
    
    return redirect(url_for('account.index'))

@account_bp.route('/delete', methods=['POST'])
def delete_account():
    """Delete an account and all associated data"""
    if 'account_id' not in session:
        flash('Please select an account first', 'warning')
        return redirect(url_for('main.index'))
    
    account_id = session['account_id']
    confirmation = request.form.get('confirmation', '')
    
    if confirmation != 'DELETE':
        flash('Please type DELETE to confirm account deletion', 'error')
        return redirect(url_for('account.index'))
    
    try:
        # Create backup before making changes
        backup_database()
        
        # Start a transaction
        db = get_db()
        db.execute('BEGIN TRANSACTION')
        
        # Delete related data in the correct order to maintain foreign key constraints
        # 1. Delete from expanded_state
        db.execute('DELETE FROM expanded_state WHERE account_id = ?', [account_id])
        
        # 2. Delete from company_shares (using subquery to find companies of this account)
        db.execute('''
            DELETE FROM company_shares 
            WHERE company_id IN (
                SELECT id FROM companies WHERE account_id = ?
            )
        ''', [account_id])
        
        # 3. Delete from companies
        db.execute('DELETE FROM companies WHERE account_id = ?', [account_id])
        
        # 4. Delete from portfolios
        db.execute('DELETE FROM portfolios WHERE account_id = ?', [account_id])
        
        # 5. Finally delete the account
        db.execute('DELETE FROM accounts WHERE id = ?', [account_id])
        
        # Commit the transaction
        db.commit()
        
        # Clear session
        session.pop('account_id', None)
        session.pop('username', None)
        
        flash('Account deleted successfully', 'success')
        
    except Exception as e:
        # Rollback in case of error
        db.rollback()
        flash(f'Error deleting account: {str(e)}', 'error')
    
    return redirect(url_for('main.index'))