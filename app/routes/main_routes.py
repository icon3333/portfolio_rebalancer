from flask import Blueprint, render_template, redirect, url_for, session, request, flash, jsonify
import logging
logger = logging.getLogger(__name__)
from app.database.db_manager import query_db
from app.utils.portfolio_utils import get_portfolio_data

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    """Homepage route"""
    logger.info("Accessing homepage")
    
    # Check if user has an account selected
    account_id = session.get('account_id')
    logger.info(f"Current account_id in session: {account_id}")
    
    if account_id:
        # Get account information
        account = query_db('SELECT * FROM accounts WHERE id = ?', 
                         [account_id], one=True)
        
        if account:
            logger.info(f"Found account: {account['username']}")
            
            # Get portfolio summary for the account - only count portfolios with value > 0
            portfolios = query_db('''
                SELECT p.id, p.name, 
                       COUNT(DISTINCT c.id) as company_count,
                       SUM(cs.shares * mp.price_eur) as total_value
                FROM portfolios p
                LEFT JOIN companies c ON p.id = c.portfolio_id
                LEFT JOIN company_shares cs ON c.id = cs.company_id
                LEFT JOIN market_prices mp ON c.identifier = mp.identifier
                WHERE p.account_id = ?
                GROUP BY p.id, p.name
                HAVING SUM(cs.shares * mp.price_eur) > 0
            ''', [account_id])
            
            # Get portfolio data to calculate total value consistently with enrich page
            portfolio_data = get_portfolio_data(account_id)
            
            # Calculate total value the same way as in enrich page
            total_value = sum(
                (item['price_eur'] or 0) * (item['shares'] or 0) 
                for item in portfolio_data
            )
            
            # Count total assets (positions) with actual shares and prices
            total_assets = sum(1 for item in portfolio_data if (item['shares'] or 0) > 0 and (item['price_eur'] or 0) > 0)
            
            # Get all accounts for account switcher
            all_accounts = query_db('SELECT * FROM accounts WHERE username != "_global" ORDER BY username')
            
            logger.info(f"Found {len(portfolios)} portfolios with value > 0")
            return render_template('pages/index.html',
                               account=account,
                               portfolios=portfolios,
                               total_value=total_value,
                               total_assets=total_assets,
                               all_accounts=all_accounts)
        else:
            logger.warning(f"Account {account_id} not found")
            session.pop('account_id', None)
            session.pop('username', None)
    
    # If no account is selected or account not found, show the welcome page
    accounts = query_db('SELECT * FROM accounts WHERE username != "_global" ORDER BY username')
    logger.info(f"Found {len(accounts)} accounts")
    return render_template('pages/index.html', accounts=accounts)

@main_bp.route('/select_account/<int:account_id>')
def select_account(account_id):
    """Select an account and store it in the session"""
    logger.info(f"Selecting account: {account_id}")
    
    account = query_db('SELECT * FROM accounts WHERE id = ?', 
                     [account_id], one=True)
    
    if account:
        session.permanent = True  # Make session permanent
        session['account_id'] = account_id
        session['username'] = account['username']
        logger.info(f"Account selected: {account['username']} (ID: {account_id})")
        logger.info(f"Updated session: {dict(session)}")
        flash(f'Switched to account: {account["username"]}', 'success')
    else:
        logger.warning(f"Account not found: {account_id}")
        flash('Account not found', 'error')
        
    return redirect(url_for('main.index'))

@main_bp.route('/clear_account')
def clear_account():
    """Clear the selected account from session"""
    if 'account_id' in session:
        del session['account_id']
    if 'username' in session:
        del session['username']
        
    return redirect(url_for('main.index'))

@main_bp.route('/api/accounts')
def get_accounts():
    """API endpoint to get all accounts"""
    accounts = query_db('SELECT id, username, created_at FROM accounts WHERE username != "_global"')
    return jsonify(accounts)