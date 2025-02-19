from flask import (
    Blueprint, render_template, redirect, url_for, 
    request, flash, session, jsonify
)
from app.database.db_manager import query_db, execute_db
import numpy as np
import pandas as pd
import yfinance as yf
import json
import requests
from bs4 import BeautifulSoup
from typing import List, Tuple, Dict, Optional
from datetime import datetime, timedelta

merton_bp = Blueprint('merton', __name__)

@merton_bp.route('/')
def index():
    """Merton share calculation page"""
    # Check if user is authenticated with an account
    if 'account_id' not in session:
        flash('Please select an account first', 'warning')
        return redirect(url_for('main.index'))
    
    account_id = session['account_id']
    
    # Get portfolios
    portfolios = get_portfolios(account_id)
    
    # Get current parameters
    current_params = get_merton_parameters(account_id)
    
    # Get market indicators
    effektivzins = get_effektivzins()
    buffett_indicator = get_buffett_indicator()
    
    # Get previous results if available
    merton_results = get_merton_results(account_id)
    
    return render_template('pages/merton.html',
                           portfolios=portfolios,
                           params=current_params,
                           effektivzins=effektivzins,
                           buffett_indicator=buffett_indicator,
                           results=merton_results)

@merton_bp.route('/api/calculate', methods=['POST'])
def calculate_api():
    """API endpoint to perform Merton share calculation"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    try:
        account_id = session['account_id']
        data = request.json
        
        # Validate inputs
        if not validate_merton_inputs(data):
            return jsonify({'error': 'Invalid input parameters'}), 400
        
        # Save parameters
        save_merton_parameters(account_id, data)
        
        # Perform calculation
        results = perform_merton_calculations(account_id, data)
        
        # Save results
        save_merton_results(account_id, results)
        
        return jsonify(results)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@merton_bp.route('/api/parameters')
def get_parameters_api():
    """API endpoint to get current Merton parameters"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    account_id = session['account_id']
    params = get_merton_parameters(account_id)
    
    return jsonify(params)

@merton_bp.route('/api/results')
def get_results_api():
    """API endpoint to get previous Merton calculation results"""
    if 'account_id' not in session:
        return jsonify({'error': 'Not authenticated'}), 401
    
    account_id = session['account_id']
    results = get_merton_results(account_id)
    
    return jsonify(results)

@merton_bp.route('/api/effektivzins')
def get_effektivzins_api():
    """API endpoint to get current Effektivzins"""
    effektivzins = get_effektivzins()
    return jsonify(effektivzins)

@merton_bp.route('/api/buffett_indicator')
def get_buffett_indicator_api():
    """API endpoint to get current Buffett Indicator"""
    buffett_indicator = get_buffett_indicator()
    return jsonify(buffett_indicator)

def get_portfolios(account_id):
    """Get portfolios for an account"""
    return query_db('''
        SELECT name FROM portfolios 
        WHERE account_id = ? AND name != '-'
        ORDER BY name
    ''', [account_id])

def get_merton_parameters(account_id):
    """Get saved Merton parameters for account"""
    result = query_db('''
        SELECT variable_value
        FROM expanded_state
        WHERE account_id = ? AND page_name = 'merton' AND variable_name = 'parameters'
    ''', [account_id], one=True)
    
    if result:
        try:
            return json.loads(result['variable_value'])
        except:
            pass
    
    # Default parameters
    default_params = {
        "risk_free_rate": 1.5,
        "risk_aversion": 2.0,
        "years": 5,
        "projected_years": 5,
        "target_growth_rates": {}
    }
    
    # Add default growth rates for each portfolio
    portfolios = [p['name'] for p in get_portfolios(account_id)]
    for portfolio in portfolios:
        default_params["target_growth_rates"][portfolio] = {
            "rate": 7.0,
            "type": "yearly"
        }
    
    return default_params

def save_merton_parameters(account_id, parameters):
    """Save Merton parameters to the database"""
    variable_value = json.dumps(parameters)
    
    # Check if parameters exist
    existing = query_db('''
        SELECT id FROM expanded_state
        WHERE account_id = ? AND page_name = 'merton' AND variable_name = 'parameters'
    ''', [account_id], one=True)
    
    if existing:
        # Update existing
        execute_db('''
            UPDATE expanded_state
            SET variable_value = ?
            WHERE id = ?
        ''', [variable_value, existing['id']])
    else:
        # Insert new
        execute_db('''
            INSERT INTO expanded_state 
            (account_id, page_name, variable_name, variable_type, variable_value)
            VALUES (?, ?, ?, ?, ?)
        ''', [account_id, 'merton', 'parameters', 'dict', variable_value])

def get_merton_results(account_id):
    """Get saved Merton calculation results"""
    result = query_db('''
        SELECT variable_value
        FROM expanded_state
        WHERE account_id = ? AND page_name = 'merton' AND variable_name = 'results'
    ''', [account_id], one=True)
    
    if result:
        try:
            return json.loads(result['variable_value'])
        except:
            pass
    
    return {}

def save_merton_results(account_id, results):
    """Save Merton calculation results to the database"""
    variable_value = json.dumps(results)
    
    # Check if results exist
    existing = query_db('''
        SELECT id FROM expanded_state
        WHERE account_id = ? AND page_name = 'merton' AND variable_name = 'results'
    ''', [account_id], one=True)
    
    if existing:
        # Update existing
        execute_db('''
            UPDATE expanded_state
            SET variable_value = ?
            WHERE id = ?
        ''', [variable_value, existing['id']])
    else:
        # Insert new
        execute_db('''
            INSERT INTO expanded_state 
            (account_id, page_name, variable_name, variable_type, variable_value)
            VALUES (?, ?, ?, ?, ?)
        ''', [account_id, 'merton', 'results', 'dict', variable_value])

def validate_merton_inputs(data):
    """Validate Merton calculation inputs"""
    required_fields = ['risk_free_rate', 'risk_aversion', 'years', 'projected_years', 'target_growth_rates']
    
    # Check required fields
    if not all(field in data for field in required_fields):
        return False
    
    # Validate numeric fields
    try:
        float(data['risk_free_rate'])
        float(data['risk_aversion'])
        int(data['years'])
        int(data['projected_years'])
    except (ValueError, TypeError):
        return False
    
    # Validate growth rates
    if not isinstance(data['target_growth_rates'], dict):
        return False
    
    for portfolio, growth in data['target_growth_rates'].items():
        if not isinstance(growth, dict) or 'rate' not in growth or 'type' not in growth:
            return False
        
        try:
            float(growth['rate'])
        except (ValueError, TypeError):
            return False
        
        if growth['type'] not in ['yearly', 'total']:
            return False
    
    return True

def get_effektivzins():
    """Get the current Effektivzins from DKB website"""
    url = 'https://www.kontofinder.de/banken/dkb/tagesgeld/'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        popover_link = soup.find('a', class_='popover-link', attrs={
            'data-content': lambda value: value and 'Effektivzins:' in value
        })
        
        if popover_link:
            data_content = popover_link['data-content']
            effektivzins_text = [line.strip() for line in data_content.split('<br>') if 'Effektivzins:' in line][0]
            effektivzins = effektivzins_text.split(':')[1].strip().replace(',', '.').replace('%', '')
            return {
                'value': float(effektivzins),
                'error': None
            }
        
        return {
            'value': None,
            'error': "Effektivzins not found on the page."
        }
        
    except Exception as e:
        return {
            'value': None,
            'error': f"Failed to fetch Effektivzins: {str(e)}"
        }

def get_buffett_indicator():
    """Get the current Buffett Indicator from CurrentMarketValuation"""
    try:
        url = "https://www.currentmarketvaluation.com/models/buffett-indicator.php"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        indicator_span = soup.select_one('span.text-danger span.fw-bold')
        
        if indicator_span:
            indicator_text = indicator_span.text.strip('%')
            indicator_value = float(indicator_text)
            interpretation = interpret_buffett_indicator(indicator_value)
            
            return {
                'value': indicator_value,
                'interpretation': interpretation,
                'error': None
            }
        else:
            return {
                'value': None,
                'interpretation': None,
                'error': "Unable to find Buffett Indicator value on the page"
            }
            
    except Exception as e:
        return {
            'value': None,
            'interpretation': None,
            'error': f"Error fetching Buffett Indicator: {str(e)}"
        }

def interpret_buffett_indicator(indicator: float) -> str:
    """Interpret Buffett Indicator value."""
    if indicator < 50:
        return "significantly undervalued"
    elif 50 <= indicator < 75:
        return "modestly undervalued"
    elif 75 <= indicator < 90:
        return "fairly valued"
    elif 90 <= indicator < 115:
        return "overvalued"
    else:
        return "significantly overvalued"

def perform_merton_calculations(account_id, params):
    """
    Perform Merton share calculations.
    
    This implements a simplified Merton model for portfolio optimization
    based on historical returns and user-defined parameters.
    """
    start_time = datetime.now()
    
    # Get parameters
    risk_free_rate = float(params['risk_free_rate'])
    risk_aversion = float(params['risk_aversion'])
    years = int(params['years'])
    projected_years = int(params['projected_years'])
    target_growth_rates = params['target_growth_rates']
    
    # Tracking variables
    excluded_tickers = []
    warning_message = None
    warnings = []
    stats = {
        'portfolios_processed': 0,
        'valid_tickers': 0,
        'invalid_tickers': 0,
        'total_returns_calculated': 0
    }
    
    # Get portfolio data
    portfolio_data = get_portfolio_data(account_id)
    
    if not portfolio_data:
        return {
            'allocations': {},
            'portfolios': [],
            'warning_message': "No data available for this account.",
            'excluded_tickers': [],
            'calculation_time': 0,
            'stats': stats
        }
    
    # Convert to DataFrame
    df = pd.DataFrame(portfolio_data)
    
    # Get valid portfolios
    valid_portfolios = df[df["portfolio"] != "-"]["portfolio"].unique()
    
    if len(valid_portfolios) == 0:
        return {
            'allocations': {},
            'portfolios': [],
            'warning_message': "No valid portfolios found.",
            'excluded_tickers': [],
            'calculation_time': (datetime.now() - start_time).total_seconds(),
            'stats': stats
        }
    
    # Process target growth rates
    processed_target_returns = process_target_returns(target_growth_rates, projected_years)
    
    # Calculate portfolio returns
    portfolio_returns = {}
    
    for portfolio in valid_portfolios:
        try:
            # Filter valid tickers
            portfolio_df = df[df['portfolio'] == portfolio]
            valid_tickers, invalid_tickers = filter_valid_tickers(portfolio_df)
            
            stats['valid_tickers'] += len(valid_tickers)
            stats['invalid_tickers'] += len(invalid_tickers)
            
            # Log excluded tickers
            if invalid_tickers:
                invalid_companies = portfolio_df[portfolio_df['ticker'].isin(invalid_tickers)]['company'].tolist()
                excluded_tickers.extend(invalid_companies)
                warnings.append(f"Excluded companies from {portfolio}: {', '.join(invalid_companies)}")
            
            if not valid_tickers:
                warnings.append(f"No valid tickers found for portfolio {portfolio}")
                continue
            
            # Get historical data
            historical_data = get_historical_data(valid_tickers, years)
            
            if historical_data.empty:
                warnings.append(f"No historical prices available for portfolio {portfolio}")
                continue
            
            # Check which tickers we got data for
            received_tickers = historical_data.columns.tolist()
            missing_tickers = list(set(valid_tickers) - set(received_tickers))
            
            if missing_tickers:
                missing_companies = portfolio_df[portfolio_df['ticker'].isin(missing_tickers)]['company'].tolist()
                warnings.append(f"Missing price data for companies in {portfolio}: {', '.join(missing_companies)}")
                excluded_tickers.extend(missing_companies)
            
            if not received_tickers:
                warnings.append(f"No valid price data for portfolio {portfolio}")
                continue
            
            # Calculate weekly returns
            returns = historical_data.pct_change().dropna()
            if returns.empty:
                warnings.append(f"No valid returns for portfolio {portfolio}")
                continue
            
            # Calculate portfolio return (equal weighted)
            weights = np.ones(len(returns.columns)) / len(returns.columns)
            portfolio_return_series = returns.dot(weights)
            portfolio_returns[portfolio] = portfolio_return_series
            
            stats['portfolios_processed'] += 1
            stats['total_returns_calculated'] += 1
            
        except Exception as e:
            warnings.append(f"Error processing {portfolio}: {str(e)}")
            continue
    
    if not portfolio_returns:
        return {
            'allocations': {},
            'portfolios': list(valid_portfolios),
            'warning_message': "No valid portfolio returns calculated.",
            'excluded_tickers': excluded_tickers,
            'calculation_time': (datetime.now() - start_time).total_seconds(),
            'stats': stats
        }
    
    # Calculate optimal allocations
    try:
        # Combine portfolio returns
        returns_df = pd.DataFrame(portfolio_returns)
        
        # Calculate metrics
        expected_returns, covariance = calculate_portfolio_metrics(
            returns_df,
            risk_free_rate,
            processed_target_returns
        )
        
        # Calculate Merton shares
        merton_shares = calculate_merton_shares(
            expected_returns,
            covariance,
            risk_free_rate,
            risk_aversion
        )
        
        # Create result structure
        allocations = {
            portfolio: float(share)
            for portfolio, share in zip(returns_df.columns, merton_shares)
        }
        
        warning_message = ". ".join(warnings) if warnings else None
        
        return {
            'allocations': allocations,
            'portfolios': list(returns_df.columns),
            'warning_message': warning_message,
            'excluded_tickers': excluded_tickers,
            'calculation_time': (datetime.now() - start_time).total_seconds(),
            'stats': stats
        }
        
    except Exception as e:
        # Fall back to equal weights on error
        equal_weight = 1.0 / len(portfolio_returns)
        allocations = {p: equal_weight for p in portfolio_returns.keys()}
        
        warnings.append(f"Error in optimization: {str(e)}. Using equal weights.")
        warning_message = ". ".join(warnings)
        
        return {
            'allocations': allocations,
            'portfolios': list(portfolio_returns.keys()),
            'warning_message': warning_message,
            'excluded_tickers': excluded_tickers,
            'calculation_time': (datetime.now() - start_time).total_seconds(),
            'stats': stats
        }

def filter_valid_tickers(df):
    """Filter out invalid tickers and return both valid and invalid lists."""
    all_tickers = df['ticker'].unique().tolist()
    
    valid_tickers = []
    invalid_tickers = []
    
    for ticker in all_tickers:
        if pd.isna(ticker) or ticker in ['', '-', 'None', 'NO TICKER FOUND', None]:
            invalid_tickers.append(str(ticker))
        else:
            valid_tickers.append(str(ticker).strip())
            
    return valid_tickers, invalid_tickers

def get_historical_data(tickers, years=5):
    """Get historical data for multiple tickers"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=years * 365)
    
    all_data = pd.DataFrame()
    
    for ticker in tickers:
        try:
            ticker_obj = yf.Ticker(ticker)
            hist = ticker_obj.history(start=start_date, end=end_date)
            
            if hist.empty:
                continue
                
            prices = hist['Close'].rename(ticker)
            if all_data.empty:
                all_data = pd.DataFrame(prices)
            else:
                all_data = pd.concat([all_data, prices], axis=1)
                
        except Exception:
            continue
    
    return all_data

def calculate_portfolio_metrics(returns, risk_free_rate, target_returns, ann_factor=52):
    """Calculate portfolio metrics with proper annualization"""
    # Clean returns
    returns = returns.replace([np.inf, -np.inf], np.nan).dropna(how='all')
    
    if returns.empty:
        raise ValueError("No valid return data after cleaning")
    
    # Calculate historical metrics (weekly)
    hist_returns = returns.mean() * ann_factor
    hist_vol = returns.std() * np.sqrt(ann_factor)
    
    # Calculate covariance
    covariance = returns.cov() * ann_factor
    
    # Blend historical and target returns (50/50)
    expected_returns = np.zeros(len(returns.columns))
    for i, portfolio in enumerate(returns.columns):
        if portfolio in target_returns:
            hist_ret = hist_returns[portfolio]
            target_ret = target_returns[portfolio] / 100  # Convert from percentage
            expected_returns[i] = 0.5 * hist_ret + 0.5 * target_ret
        else:
            expected_returns[i] = hist_returns[portfolio]
    
    return expected_returns, covariance

def calculate_merton_shares(expected_returns, covariance_matrix, risk_free_rate, risk_aversion):
    """Calculate optimal Merton portfolio weights"""
    try:
        # Ensure covariance matrix is well-conditioned
        min_eigenval = np.min(np.linalg.eigvals(covariance_matrix))
        if min_eigenval < 1e-10:
            covariance_matrix += np.eye(len(covariance_matrix)) * 1e-10
        
        # Calculate inverse
        inv_cov = np.linalg.pinv(covariance_matrix)
        
        # Convert risk-free rate if needed
        rf_rate = risk_free_rate / 100 if risk_free_rate > 1 else risk_free_rate
        
        # Calculate excess returns and shares
        excess_returns = expected_returns - rf_rate
        raw_shares = (1 / risk_aversion) * inv_cov @ excess_returns
        
        # Ensure non-negative allocations
        shares = np.maximum(raw_shares, 0)
        if shares.sum() > 0:
            shares = shares / shares.sum()
        else:
            shares = np.ones_like(raw_shares) / len(raw_shares)
        
        return shares
        
    except np.linalg.LinAlgError:
        # Return equal weights on error
        return np.ones(len(expected_returns)) / len(expected_returns)

def process_target_returns(target_rates, projected_years):
    """Process target growth rates to annualized returns"""
    processed_returns = {}
    
    for portfolio, data in target_rates.items():
        rate = float(data['rate'])
        if data['type'] == 'total':
            yearly_rate = (1 + rate/100) ** (1/projected_years) - 1
            processed_returns[portfolio] = yearly_rate * 100
        else:
            processed_returns[portfolio] = rate
            
    return processed_returns

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