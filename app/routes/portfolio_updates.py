from flask import request, session, jsonify
from app.database.db_manager import query_db, backup_database, get_db
from app.utils.portfolio_utils import get_stock_info
from app.utils.db_utils import update_price_in_db
import logging

logger = logging.getLogger(__name__)


def update_price_api():
    """API endpoint to update a company's price"""
    try:
        data = request.get_json() if request.is_json else request.form
        identifier = data.get('identifier', '').strip().upper()
        if not identifier:
            return jsonify({'error': 'No identifier provided'}), 400
        backup_database()
        result = get_stock_info(identifier)
        if not result['success']:
            return jsonify({'error': f"Failed to fetch price for {identifier}: {result.get('error')}"}), 400
        data = result['data']
        price = data.get('currentPrice')
        currency = data.get('currency')
        price_eur = data.get('priceEUR')
        if price is None:
            return jsonify({'error': f'Failed to fetch price for {identifier}'}), 400
        if update_price_in_db(identifier, price, currency, price_eur):
            return jsonify({'success': True, 'data': {'identifier': identifier, 'price': price, 'currency': currency, 'price_eur': price_eur}})
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
        data = request.json or {}
        if not isinstance(data, dict):
            return jsonify({'error': 'Invalid data format'}), 400
        company = query_db('SELECT id FROM companies WHERE id = ? AND account_id = ?', [company_id, account_id], one=True)
        if not company:
            return jsonify({'error': 'Company not found or access denied'}), 404
        with get_db() as db:
            cursor = db.cursor()
            from .portfolio_api import _apply_company_update
            _apply_company_update(cursor, company_id, data, account_id)
        return jsonify({'success': True, 'message': 'Company updated successfully'})
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
        if not data or not isinstance(data, list):
            return jsonify({'error': 'Invalid data format'}), 400
        updated = 0
        errors = []
        with get_db() as db:
            cursor = db.cursor()
            from .portfolio_api import _apply_company_update
            for item in data:
                cid = item.get('id')
                if not cid:
                    errors.append({'id': None, 'error': 'Missing id'})
                    continue
                company = query_db('SELECT id FROM companies WHERE id = ? AND account_id = ?', [cid, account_id], one=True)
                if not company:
                    errors.append({'id': cid, 'error': 'Company not found'})
                    continue
                try:
                    _apply_company_update(cursor, cid, item, account_id)
                    updated += 1
                except Exception as exc:
                    errors.append({'id': cid, 'error': str(exc)})
        if errors:
            return jsonify({'success': False, 'updated': updated, 'errors': errors}), 400
        return jsonify({'success': True, 'updated': updated, 'errors': []})
    except Exception as e:
        logger.error(f"Error in bulk update: {str(e)}")
        return jsonify({'error': str(e)}), 500


def get_portfolio_companies(portfolio_id):
    """API endpoint to get all companies for a portfolio"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated. Please select an account from the home page.'}), 401
    try:
        account_id = session['account_id']
        if not portfolio_id:
            return jsonify({'error': 'No portfolio ID provided'}), 400
        companies = query_db('''
            SELECT c.id, c.name, c.identifier, c.category, cs.shares, mp.price_eur
            FROM companies c
            LEFT JOIN company_shares cs ON c.id = cs.company_id
            LEFT JOIN market_prices mp ON c.identifier = mp.identifier
            WHERE c.account_id = ? AND c.portfolio_id = ?
            ORDER BY c.name
        ''', [account_id, portfolio_id])
        result = []
        for company in companies:
            result.append({
                'id': company['id'],
                'name': company['name'],
                'identifier': company['identifier'],
                'category': company['category'],
                'shares': company['shares'],
                'price_eur': company['price_eur'],
                'value_eur': company['price_eur'] * company['shares'] if company['price_eur'] and company['shares'] else 0
            })
        return jsonify(result)
    except Exception as e:
        logger.error(f"Error getting companies for portfolio: {str(e)}")
        return jsonify({'error': str(e)}), 500
