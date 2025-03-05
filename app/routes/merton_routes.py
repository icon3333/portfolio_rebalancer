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
import logging

logger = logging.getLogger(__name__)

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
    Perform Merton share calculations with portfolio and company level allocations.
    """
    start_time = datetime.now()
    
    # Extract parameters
    years = int(params['years'])
    risk_free_rate = float(params['risk_free_rate']) / 100
    risk_aversion = float(params['risk_aversion'])
    projected_years = int(params['projected_years'])
    target_growth_rates = params['target_growth_rates']
    
    # Tracking variables
    excluded_identifiers = []
    warning_message = None
    warnings = []
    stats = {
        'portfolios_processed': 0,
        'valid_identifiers': 0,
        'invalid_identifiers': 0,
        'total_returns_calculated': 0
    }
    
    # Get portfolio data
    portfolio_data = get_portfolio_data(account_id)
    
    if not portfolio_data:
        return {
            'allocations': {},
            'company_allocations': {},
            'portfolios': [],
            'warning_message': "No data available for this account.",
            'excluded_identifiers': [],
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
            'company_allocations': {},
            'portfolios': [],
            'warning_message': "No valid portfolios found.",
            'excluded_identifiers': [],
            'calculation_time': (datetime.now() - start_time).total_seconds(),
            'stats': stats
        }
    
    # Process target growth rates
    processed_target_returns = process_target_returns(target_growth_rates, projected_years)
    
    # Calculate portfolio returns
    portfolio_returns = {}
    all_company_returns = {}  # Store returns for all companies for later company-level allocation
    company_identifiers = {}  # Map from identifiers to company names
    
    for portfolio in valid_portfolios:
        try:
            # Filter valid identifiers
            portfolio_df = df[df['portfolio'] == portfolio]
            valid_identifiers, invalid_identifiers = filter_valid_identifiers(portfolio_df)
            
            stats['valid_identifiers'] += len(valid_identifiers)
            stats['invalid_identifiers'] += len(invalid_identifiers)
            
            # Log excluded identifiers
            if invalid_identifiers:
                invalid_companies = portfolio_df[portfolio_df['identifier'].isin(invalid_identifiers)]['company'].tolist()
                excluded_identifiers.extend(invalid_companies)
                warnings.append(f"Excluded companies from {portfolio}: {', '.join(invalid_companies)}")
            
            if not valid_identifiers:
                warnings.append(f"No valid identifiers found for portfolio {portfolio}")
                continue
            
            # Create mapping from identifier to company name for this portfolio
            for _, row in portfolio_df.iterrows():
                if row['identifier'] and isinstance(row['identifier'], str):
                    company_identifiers[row['identifier']] = row['company']
            
            # Get historical data
            historical_data = get_historical_data(valid_identifiers, years)
            
            if historical_data.empty:
                warnings.append(f"No historical prices available for portfolio {portfolio}")
                continue
            
            # Check which identifiers we got data for
            received_identifiers = historical_data.columns.tolist()
            missing_identifiers = list(set(valid_identifiers) - set(received_identifiers))
            
            if missing_identifiers:
                missing_companies = portfolio_df[portfolio_df['identifier'].isin(missing_identifiers)]['company'].tolist()
                warnings.append(f"Missing price data for companies in {portfolio}: {', '.join(missing_companies)}")
                excluded_identifiers.extend(missing_companies)
            
            if not received_identifiers:
                warnings.append(f"No valid price data for portfolio {portfolio}")
                continue
            
            # Calculate weekly returns for both portfolio and company level
            returns = historical_data.pct_change().dropna()
            if returns.empty:
                warnings.append(f"No valid returns for portfolio {portfolio}")
                continue
            
            # Store company returns for this portfolio
            all_company_returns[portfolio] = returns
            
            # Calculate portfolio return (equal weighted)
            weights = np.ones(len(returns.columns)) / len(returns.columns)
            portfolio_return_series = returns.dot(weights)
            portfolio_returns[portfolio] = portfolio_return_series
            
            stats['portfolios_processed'] += 1
            stats['total_returns_calculated'] += 1
            
        except Exception as e:
            logger.error(f"Error processing portfolio {portfolio}: {str(e)}")
            warnings.append(f"Error processing portfolio {portfolio}: {str(e)}")
            continue
    
    if not portfolio_returns:
        warning_message = "No valid portfolios to process"
        return {
            'allocations': {},
            'company_allocations': {},
            'portfolios': [],
            'warning_message': warning_message,
            'excluded_identifiers': excluded_identifiers,
            'calculation_time': (datetime.now() - start_time).total_seconds(),
            'stats': stats
        }
    
    try:
        # PORTFOLIO LEVEL ALLOCATIONS
        # Combine portfolio returns into a DataFrame for cross-portfolio analysis
        combined_portfolio_returns = pd.DataFrame({portfolio: returns for portfolio, returns in portfolio_returns.items()})
        
        # Calculate expected returns and covariance across portfolios
        portfolio_expected_returns = combined_portfolio_returns.mean() * 52  # Annualize
        portfolio_covariance = combined_portfolio_returns.cov() * 52  # Annualize
        
        # Blend with target returns
        for portfolio in combined_portfolio_returns.columns:
            if portfolio in processed_target_returns:
                hist_ret = portfolio_expected_returns[portfolio]
                target_ret = processed_target_returns[portfolio] / 100  # Convert percentage
                portfolio_expected_returns[portfolio] = 0.5 * hist_ret + 0.5 * target_ret
        
        # Calculate Merton allocation weights across portfolios
        portfolio_merton_shares = calculate_merton_shares(
            portfolio_expected_returns.values,
            portfolio_covariance.values,
            risk_free_rate,
            risk_aversion
        )
        
        # Format portfolio allocations
        portfolio_allocations = {
            portfolio: float(share) 
            for portfolio, share in zip(combined_portfolio_returns.columns, portfolio_merton_shares)
        }
        
        # COMPANY LEVEL ALLOCATIONS
        company_allocations = {}
        
        # For each portfolio, calculate company-level Merton allocations
        for portfolio, company_returns in all_company_returns.items():
            if company_returns.empty:
                continue
                
            # Calculate expected returns and covariance for companies
            company_expected_returns = company_returns.mean() * 52  # Annualize
            company_covariance = company_returns.cov() * 52  # Annualize
            
            # Calculate Merton allocation weights for companies within this portfolio
            company_merton_shares = calculate_merton_shares(
                company_expected_returns.values,
                company_covariance.values,
                risk_free_rate,
                risk_aversion
            )
            
            # Map identifiers to company names for clearer display
            company_allocation_dict = {}
            for i, identifier in enumerate(company_returns.columns):
                # Get company name if available, otherwise use identifier
                company_name = company_identifiers.get(identifier, identifier)
                company_allocation_dict[company_name] = float(company_merton_shares[i])
            
            company_allocations[portfolio] = company_allocation_dict
        
        # Format warnings
        if warnings:
            warning_message = "\n".join(warnings)
        
        return {
            'allocations': portfolio_allocations,
            'company_allocations': company_allocations,
            'portfolios': list(portfolio_returns.keys()),
            'warning_message': warning_message,
            'excluded_identifiers': excluded_identifiers,
            'calculation_time': (datetime.now() - start_time).total_seconds(),
            'stats': stats
        }
        
    except Exception as e:
        logger.error(f"Error in Merton calculations: {str(e)}")
        return {
            'allocations': {},
            'company_allocations': {},
            'portfolios': [],
            'warning_message': f"Error in calculations: {str(e)}",
            'excluded_identifiers': excluded_identifiers,
            'calculation_time': (datetime.now() - start_time).total_seconds(),
            'stats': stats
        }

def filter_valid_identifiers(df):
    """Filter out invalid identifiers and return both valid and invalid lists."""
    # Get all identifiers
    identifiers = df['identifier'].unique().tolist()
    
    # Remove None and empty strings
    valid_identifiers = [i for i in identifiers if i and isinstance(i, str)]
    invalid_identifiers = [i for i in identifiers if not i or not isinstance(i, str)]
    
    return valid_identifiers, invalid_identifiers

def get_historical_data(identifiers, years=5):
    """Get historical data for multiple identifiers"""
    end_date = datetime.now()
    start_date = end_date - timedelta(days=years*365)
    
    # Initialize empty DataFrame for results
    historical_data = pd.DataFrame()
    
    for identifier in identifiers:
        try:
            logger.info(f"Fetching historical prices for {identifier}...")
            
            # Try the primary approach with explicit parameters
            data = yf.download(
                identifier,
                start=start_date,
                end=end_date,
                auto_adjust=True,  # Explicitly set auto_adjust=True
                progress=False
            )
            
            if not data.empty and 'Close' in data.columns:
                # With auto_adjust=True, use Close
                historical_data[identifier] = data['Close']
                logger.info(f"Successfully fetched {len(data)} data points for {identifier}")
            else:
                # Try backup approach with different interval
                logger.warning(f"Initial attempt failed for {identifier}, trying daily data...")
                backup_data = yf.download(
                    identifier,
                    start=start_date,
                    end=end_date,
                    interval='1d',  # Try daily data
                    auto_adjust=True,
                    progress=False
                )
                
                if not backup_data.empty and 'Close' in backup_data.columns:
                    # Resample daily data if needed
                    historical_data[identifier] = backup_data['Close']
                    logger.info(f"Successfully fetched data using daily fallback for {identifier}")
                else:
                    # Special handling for crypto tickers
                    if '-' not in identifier and identifier.upper() in ['BTC', 'ETH', 'LRC', 'ATOM', 'SOL', 'DOGE', 'PEPE', 'IOTA', 'TRX', 'LINK']:
                        # Try with -USD suffix
                        crypto_id = f"{identifier.upper()}-USD"
                        logger.info(f"Trying crypto fallback: {crypto_id}")
                        crypto_data = yf.download(
                            crypto_id,
                            start=start_date,
                            end=end_date,
                            auto_adjust=True,
                            progress=False
                        )
                        
                        if not crypto_data.empty and 'Close' in crypto_data.columns:
                            historical_data[identifier] = crypto_data['Close']
                            logger.info(f"Successfully fetched crypto data for {identifier} using {crypto_id}")
                        else:
                            logger.warning(f"No price data found for {identifier} or {crypto_id}")
                    else:
                        logger.warning(f"No price data found for {identifier}")
                
        except Exception as e:
            logger.error(f"Error fetching data for {identifier}: {str(e)}")
            continue
    
    return historical_data

def get_portfolio_data(account_id):
    """Get portfolio data from the database"""
    return query_db('''
        SELECT 
            c.name AS company,
            c.identifier,
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
        LEFT JOIN market_prices mp ON c.identifier = mp.identifier
        WHERE c.account_id = ?
    ''', [account_id])

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