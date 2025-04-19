from flask import (
    Blueprint, render_template, redirect, url_for, 
    request, flash, session, jsonify
)
from app.database.db_manager import query_db, execute_db, backup_database, get_db
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger('app.routes.account')

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
    
    return redirect(url_for('main.index'))

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
    
    db = None
    try:
        # Create backup before making changes
        backup_database()
        
        # Start a transaction
        db = get_db()
        db.execute('BEGIN TRANSACTION')
        
        # Delete related data in the correct order to maintain foreign key constraints
        # 1. Delete from expanded_state
        db.execute('DELETE FROM expanded_state WHERE account_id = ?', [account_id])
        
        # 2. Find all identifiers used by this account that need to be checked for deletion
        identifiers = query_db('''
            SELECT DISTINCT identifier 
            FROM companies 
            WHERE account_id = ? AND identifier IS NOT NULL AND identifier != ''
        ''', [account_id])
        
        # 3. Delete from company_shares (using subquery to find companies of this account)
        db.execute('''
            DELETE FROM company_shares 
            WHERE company_id IN (
                SELECT id FROM companies WHERE account_id = ?
            )
        ''', [account_id])
        
        # 4. Delete from companies
        db.execute('DELETE FROM companies WHERE account_id = ?', [account_id])
        
        # 5. Delete from portfolios
        db.execute('DELETE FROM portfolios WHERE account_id = ?', [account_id])
        
        # 6. Delete market_prices entries that are now orphaned (not used by any other accounts)
        deleted_count = 0
        try:
            # Check if this is the last account being deleted
            remaining_accounts = query_db('SELECT COUNT(*) as count FROM accounts WHERE id != ?', [account_id])
            is_last_account = remaining_accounts[0]['count'] == 0
            
            if is_last_account:
                # If this is the last account, we can safely delete all market prices
                logger.info("This is the last account - deleting all market prices")
                market_prices_count = query_db('SELECT COUNT(*) as count FROM market_prices')
                count_to_delete = market_prices_count[0]['count']
                
                if count_to_delete > 0:
                    db.execute('DELETE FROM market_prices')
                    logger.info(f"Deleted all {count_to_delete} market prices as the last account was deleted")
                    deleted_count = count_to_delete
            else:
                # Normal case: check each identifier
                logger.info(f"Checking {len(identifiers)} market prices for potential cleanup after account deletion")
                for item in identifiers:
                    identifier = item['identifier']
                    
                    # Check if this identifier is used by any other companies in other accounts
                    other_usages = query_db('''
                        SELECT 1 FROM companies 
                        WHERE identifier = ? 
                        LIMIT 1
                    ''', [identifier])
                    
                    # If no other account uses this identifier, delete it from market_prices
                    if not other_usages:
                        logger.info(f"Deleting orphaned market price for identifier: {identifier}")
                        db.execute('DELETE FROM market_prices WHERE identifier = ?', [identifier])
                        deleted_count += 1
            
            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} orphaned market prices during account deletion")
                
            # Double-check for any orphaned market prices (safety check)
            # This helps catch any market prices that might have been missed
            if not is_last_account:  # Skip if we already deleted everything
                all_company_identifiers = query_db('''
                    SELECT DISTINCT identifier FROM companies 
                    WHERE identifier IS NOT NULL AND identifier != ''
                ''')
                
                # Convert to a set for faster lookups
                used_identifiers = {item['identifier'] for item in all_company_identifiers} if all_company_identifiers else set()
                
                # Get all identifiers in market_prices
                all_price_records = query_db('SELECT identifier FROM market_prices')
                
                # Find and delete any orphaned identifiers that were missed
                for item in all_price_records:
                    identifier = item['identifier']
                    if identifier not in used_identifiers:
                        logger.info(f"Found additional orphaned market price to delete: {identifier}")
                        db.execute('DELETE FROM market_prices WHERE identifier = ?', [identifier])
                        deleted_count += 1
        except Exception as e:
            # Log but don't abort the account deletion if this fails
            logger.error(f"Error while cleaning up market prices: {str(e)}")
            # We don't re-raise the exception as we still want the account deletion to proceed
        
        # 7. Finally delete the account
        db.execute('DELETE FROM accounts WHERE id = ?', [account_id])
        
        # Commit the transaction
        db.commit()
        
        # Clear session
        session.pop('account_id', None)
        session.pop('username', None)
        
        flash('Account deleted successfully', 'success')
        
    except Exception as e:
        # Rollback in case of error
        if db is not None:
            db.rollback()
        flash(f'Error deleting account: {str(e)}', 'error')
    
    return redirect(url_for('main.index'))