from flask import (
    Blueprint, render_template, redirect, url_for, 
    request, flash, session, jsonify
)
from app.database.db_manager import query_db, execute_db
import json
from datetime import datetime
import pandas as pd
import numpy as np

analysis_bp = Blueprint('analysis', __name__)

@analysis_bp.route('/')
def index():
    """Portfolio analysis page"""
    # Check if user is authenticated with an account
    if 'account_id' not in session:
        flash('Please select an account first', 'warning')
        return redirect(url_for('main.index'))
    
    account_id = session['account_id']
    
    # Get portfolio data
    portfolio_data = get_portfolio_data(account_id)
    
    # Calculate portfolio metrics
    metrics = calculate_portfolio_metrics(portfolio_data)
    
    # Get portfolio allocations
    allocations = get_portfolio_allocations(account_id)
    
    # Get allocation view preference
    allocation_view = get_user_preference(account_id, 'analyse', 'allocation_view', 'relative')
    
    return render_template('pages/analyse.html',
                           portfolio_data=portfolio_data,
                           metrics=metrics,
                           allocations=allocations,
                           allocation_view=allocation_view)

@analysis_bp.route('/api/metrics')
def get_metrics_api():
    """API endpoint to get portfolio metrics"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    account_id = session['account_id']
    portfolio_data = get_portfolio_data(account_id)
    metrics = calculate_portfolio_metrics(portfolio_data)
    
    return jsonify(metrics)

@analysis_bp.route('/api/allocations')
def get_allocations_api():
    """API endpoint to get portfolio allocations"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    account_id = session['account_id']
    allocations = get_portfolio_allocations(account_id)
    
    return jsonify(allocations)

@analysis_bp.route('/api/set_preference', methods=['POST'])
def set_preference_api():
    """API endpoint to set user preferences"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        account_id = session['account_id']
        data = request.json
        
        if not data or 'name' not in data or 'value' not in data:
            return jsonify({'error': 'Invalid request format'}), 400
        
        page_name = data.get('page', 'analyse')
        variable_name = data['name']
        variable_value = data['value']
        variable_type = data.get('type', 'str')
        
        # Save preference
        save_user_preference(account_id, page_name, variable_name, variable_value, variable_type)
        
        return jsonify({'success': True})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@analysis_bp.route('/api/portfolio_sunburst')
def get_sunburst_data():
    """API endpoint to get sunburst chart data"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    account_id = session['account_id']
    portfolio_data = get_portfolio_data(account_id)
    
    # Generate sunburst data
    sunburst_data = generate_sunburst_data(portfolio_data)
    
    return jsonify(sunburst_data)

def calculate_portfolio_metrics(portfolio_data):
    """Calculate portfolio metrics"""
    if not portfolio_data:
        return {}
    
    # Convert to DataFrame for easier analysis
    df = pd.DataFrame(portfolio_data)
    
    # Calculate basic metrics
    total_value = df['total_value_eur'].sum()
    total_invested = df['total_invested'].sum()
    unrealized_gain = total_value - total_invested
    unrealized_gain_percent = (unrealized_gain / total_invested * 100) if total_invested > 0 else 0
    position_count = len(df)
    
    # Calculate portfolio breakdown
    portfolio_breakdown = {}
    for portfolio, group in df.groupby('portfolio'):
        if portfolio == '-':
            continue
            
        portfolio_value = group['total_value_eur'].sum()
        portfolio_percent = (portfolio_value / total_value * 100) if total_value > 0 else 0
        portfolio_positions = len(group)
        
        portfolio_breakdown[portfolio] = {
            'value': portfolio_value,
            'percent': portfolio_percent,
            'positions': portfolio_positions
        }
    
    # Calculate category breakdown
    category_breakdown = {}
    for category, group in df.groupby('category'):
        if category == '-':
            continue
            
        category_value = group['total_value_eur'].sum()
        category_percent = (category_value / total_value * 100) if total_value > 0 else 0
        category_positions = len(group)
        
        category_breakdown[category] = {
            'value': category_value,
            'percent': category_percent,
            'positions': category_positions
        }
    
    # Calculate currency exposure
    currency_exposure = {}
    for currency, group in df.groupby('currency'):
        if not currency:
            continue
            
        currency_value = group['total_value_eur'].sum()
        currency_percent = (currency_value / total_value * 100) if total_value > 0 else 0
        
        currency_exposure[currency] = {
            'value': currency_value,
            'percent': currency_percent
        }
    
    # Calculate concentration score (Herfindahl index)
    if total_value > 0:
        weights = df['total_value_eur'] / total_value
        concentration_score = (weights ** 2).sum() * 100
    else:
        concentration_score = 0
    
    return {
        'total_value': total_value,
        'total_invested': total_invested,
        'unrealized_gain': unrealized_gain,
        'unrealized_gain_percent': unrealized_gain_percent,
        'position_count': position_count,
        'portfolio_breakdown': portfolio_breakdown,
        'category_breakdown': category_breakdown,
        'currency_exposure': currency_exposure,
        'concentration_score': concentration_score
    }

def get_portfolio_allocations(account_id):
    """Get portfolio allocations with targets"""
    # Get portfolio data
    portfolio_data = get_portfolio_data(account_id)
    
    if not portfolio_data:
        return {}
    
    # Convert to DataFrame
    df = pd.DataFrame(portfolio_data)
    
    # Calculate total value
    total_value = df['total_value_eur'].sum()
    
    if total_value == 0:
        return {}
    
    # Get current allocations at portfolio level
    portfolio_allocations = {}
    for portfolio, group in df.groupby('portfolio'):
        portfolio_value = group['total_value_eur'].sum()
        current_percent = (portfolio_value / total_value * 100) if total_value > 0 else 0
        
        # Get target allocation from user preferences
        target_percent = float(get_user_preference(
            account_id,
            'allocation_builder',
            f'{portfolio.lower()}_percent',
            100 / df['portfolio'].nunique() if df['portfolio'].nunique() > 0 else 100
        ))
        
        portfolio_allocations[portfolio] = {
            'current': current_percent,
            'target': target_percent,
            'deviation': current_percent - target_percent,
            'value': portfolio_value
        }
        
        # Get position-level allocation
        positions = {}
        for _, row in group.iterrows():
            company = row['company']
            position_value = row['total_value_eur']
            position_percent = (position_value / total_value * 100) if total_value > 0 else 0
            
            # Get target allocation for position
            weighted_positions = json.loads(get_user_preference(
                account_id,
                'allocation_builder',
                f'{portfolio.lower()}_weighted_positions',
                '{}'
            ))
            
            position_target = None
            if company in weighted_positions:
                # If explicitly weighted
                position_target = float(weighted_positions[company]['percentage'])
            else:
                # Calculate based on even distribution
                remaining_allocation = 100.0
                total_positions = float(get_user_preference(
                    account_id,
                    'allocation_builder',
                    f'{portfolio.lower()}_positions',
                    len(group)
                ))
                
                # Subtract weighted positions
                weighted_total = sum(float(w['percentage']) for w in weighted_positions.values())
                remaining_allocation -= weighted_total
                remaining_positions = total_positions - len(weighted_positions)
                
                if remaining_positions > 0:
                    position_target = remaining_allocation / remaining_positions
                else:
                    position_target = 0
            
            positions[company] = {
                'current': position_percent,
                'target': position_target,
                'deviation': position_percent - position_target,
                'value': position_value
            }
            
        portfolio_allocations[portfolio]['positions'] = positions
    
    return portfolio_allocations

def generate_sunburst_data(portfolio_data):
    """Generate data structure for sunburst visualization"""
    if not portfolio_data:
        return {}
        
    # Convert to DataFrame
    df = pd.DataFrame(portfolio_data)
    
    # Calculate total portfolio value
    total_value = df['total_value_eur'].sum()
    
    if total_value == 0:
        return {}
    
    # Create nodes for sunburst chart
    nodes = []
    
    # Add root node
    nodes.append({
        'id': 'total',
        'parent': '',
        'name': 'Total Portfolio',
        'value': total_value,
        'percentage': 100
    })
    
    # Add portfolio nodes
    for portfolio, group in df.groupby('portfolio'):
        portfolio_value = group['total_value_eur'].sum()
        portfolio_percent = (portfolio_value / total_value * 100)
        
        nodes.append({
            'id': f'portfolio_{portfolio}',
            'parent': 'total',
            'name': portfolio,
            'value': portfolio_value,
            'percentage': portfolio_percent
        })
        
        # Add category nodes
        for category, cat_group in group.groupby('category'):
            if category == '-':
                # For uncategorized stocks, add directly to portfolio
                for _, row in cat_group.iterrows():
                    stock_value = row['total_value_eur']
                    stock_percent = (stock_value / portfolio_value * 100)
                    
                    nodes.append({
                        'id': f'stock_{row["company"]}',
                        'parent': f'portfolio_{portfolio}',
                        'name': row['company'],
                        'value': stock_value,
                        'percentage': stock_percent,
                        'ticker': row['ticker']
                    })
            else:
                # Add category node
                category_value = cat_group['total_value_eur'].sum()
                category_percent = (category_value / portfolio_value * 100)
                
                nodes.append({
                    'id': f'category_{portfolio}_{category}',
                    'parent': f'portfolio_{portfolio}',
                    'name': category,
                    'value': category_value,
                    'percentage': category_percent
                })
                
                # Add stock nodes under category
                for _, row in cat_group.iterrows():
                    stock_value = row['total_value_eur']
                    stock_percent = (stock_value / category_value * 100)
                    
                    nodes.append({
                        'id': f'stock_{row["company"]}',
                        'parent': f'category_{portfolio}_{category}',
                        'name': row['company'],
                        'value': stock_value,
                        'percentage': stock_percent,
                        'ticker': row['ticker']
                    })
    
    return nodes

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
            item['effective_shares'] = item['shares'] if item['shares'] is not None else 0
            
        # Calculate total value
        if item['price_eur'] is not None and item['effective_shares'] is not None:
            item['total_value_eur'] = item['price_eur'] * item['effective_shares']
        else:
            item['total_value_eur'] = 0
    
    return data

def get_user_preference(account_id, page_name, variable_name, default_value):
    """Get user preference from expanded_state table"""
    result = query_db('''
        SELECT variable_value, variable_type
        FROM expanded_state
        WHERE account_id = ? AND page_name = ? AND variable_name = ?
    ''', [account_id, page_name, variable_name], one=True)
    
    if result:
        return result['variable_value']
    else:
        return default_value

def save_user_preference(account_id, page_name, variable_name, variable_value, variable_type):
    """Save user preference to expanded_state table"""
    # Convert value to string for storage
    if not isinstance(variable_value, str):
        variable_value = json.dumps(variable_value)
    
    # Check if preference exists
    existing = query_db('''
        SELECT id FROM expanded_state
        WHERE account_id = ? AND page_name = ? AND variable_name = ?
    ''', [account_id, page_name, variable_name], one=True)
    
    if existing:
        # Update existing
        execute_db('''
            UPDATE expanded_state
            SET variable_value = ?, variable_type = ?
            WHERE id = ?
        ''', [variable_value, variable_type, existing['id']])
    else:
        # Insert new
        execute_db('''
            INSERT INTO expanded_state 
            (account_id, page_name, variable_name, variable_type, variable_value)
            VALUES (?, ?, ?, ?, ?)
        ''', [account_id, page_name, variable_name, variable_type, variable_value])