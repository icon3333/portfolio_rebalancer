import logging
import yfinance as yf
from typing import Dict, Any, List, Tuple
import sqlite3
import threading
import uuid
import json
from datetime import datetime
import time
from ratelimit import limits, sleep_and_retry
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting decorators
@sleep_and_retry
@limits(calls=1, period=2)  # 1 call every 2 seconds
def rate_limited_request(func, *args, **kwargs):
    return func(*args, **kwargs)

# ISIN to ticker mapping
ISIN_TO_TICKER = {
    'US88579Y1010': 'MMM',     # 3M
    'US36467W1099': 'GME',     # GameStop
    'DE000BAY0017': 'BAYN.DE', # Bayer
    'US0231351067': 'AMZN',    # Amazon
    'US88160R1014': 'TSLA',    # Tesla
    'US30303M1027': 'META',    # Meta
    'US92826C8394': 'V',       # Visa
    'US67066G1040': 'NVDA',    # NVIDIA
    'US0846707026': 'BRK-B',   # Berkshire Hathaway
    'US7427181091': 'PG',      # Procter & Gamble
    'US7170811035': 'PFE',     # Pfizer
    'US4581401001': 'IBM',     # IBM
    'US17275R1023': 'CSCO',    # Cisco
    'US46625H1005': 'JPM',     # JPMorgan Chase
    'US9311421039': 'WMT',     # Walmart
    'US5801351017': 'MCD',     # McDonald's
    'US1912161007': 'KO',      # Coca-Cola
    'US0605051046': 'BAC',     # Bank of America
    'US2546871060': 'DIS',     # Disney
    'US91324P1021': 'UNH'      # UnitedHealth Group
}

def find_ticker_for_isin(isin: str) -> str:
    """
    Find ticker symbol for an ISIN using direct yfinance approach.
    
    Args:
        isin (str): ISIN code (e.g., 'US0378331005')
        
    Returns:
        str: Ticker symbol or None if not found
    """
    logger.info(f"Finding ticker for ISIN: {isin}")
    
    try:
        # Direct approach - yfinance can handle ISINs in newer versions
        ticker_obj = yf.Ticker(isin)
        
        # Get info to force ticker resolution
        try:
            info = ticker_obj.info
            if info and 'symbol' in info:
                ticker = info['symbol']
                logger.info(f"Successfully mapped ISIN {isin} to ticker {ticker}")
                return ticker
        except Exception as e:
            logger.warning(f"Error getting info for {isin}: {str(e)}")
        
        # Fallback: try to get ticker from the ticker object directly
        if hasattr(ticker_obj, 'ticker') and ticker_obj.ticker:
            ticker = ticker_obj.ticker
            logger.info(f"Successfully mapped ISIN {isin} to ticker {ticker}")
            return ticker
            
        logger.warning(f"No ticker found for ISIN: {isin}")
        return None
            
    except Exception as e:
        logger.error(f"Error finding ticker for ISIN {isin}: {str(e)}")
        return None

def get_price_for_ticker(ticker: str) -> float:
    """
    Get the current price for a ticker symbol.
    
    Args:
        ticker (str): Ticker symbol (e.g., 'AAPL')
        
    Returns:
        float: Current price or None if not available
    """
    if not ticker:
        return None
    
    logger.info(f"Getting price for ticker: {ticker}")
    try:
        # Create ticker object
        ticker_obj = yf.Ticker(ticker)
        
        # Get current price from info
        try:
            info = rate_limited_request(lambda: ticker_obj.info)
            if info:
                # Try different price fields in order of reliability
                price_fields = ['currentPrice', 'regularMarketPrice', 'previousClose', 'open']
                for field in price_fields:
                    if field in info and info[field] is not None and info[field] > 0:
                        price = float(info[field])
                        logger.info(f"Got price from {field} for {ticker}: {price}")
                        return price
        except Exception as e:
            logger.warning(f"Error getting info price for {ticker}: {str(e)}")
        
        # Try historical data as fallback
        try:
            time.sleep(2)  # Add delay before historical request
            data = rate_limited_request(lambda: ticker_obj.history(period="1d"))
            if not data.empty:
                # Try different price columns in order of reliability
                price_cols = ['Close', 'Open', 'High', 'Low']
                for col in price_cols:
                    if col in data.columns:
                        price = float(data[col].iloc[-1])
                        if price > 0:
                            logger.info(f"Got price from history {col} for {ticker}: {price}")
                            return price
        except Exception as e:
            logger.warning(f"Error getting historical price for {ticker}: {str(e)}")
        
        logger.warning(f"No valid price found for {ticker}")
        return None
        
    except Exception as e:
        logger.error(f"Error getting price data for {ticker}: {str(e)}")
        return None

def get_isin_data(isin: str) -> Dict[str, Any]:
    """
    Get stock data for a given ISIN
    
    Args:
        isin (str): ISIN code (e.g., 'US0378331005')
        
    Returns:
        Dict[str, Any]: Dictionary containing ISIN information
    """
    logger.info(f"Processing ISIN: {isin}")
    try:
        # Step 1: Get the ticker for this ISIN
        ticker = ISIN_TO_TICKER.get(isin)
        if not ticker:
            logger.warning(f"No ticker mapping found for ISIN: {isin}")
            return {
                'success': False,
                'isin': isin,
                'ticker': None,
                'price': None,
                'status': 'ticker_not_found',
                'timestamp': datetime.now().isoformat()
            }
            
        # Step 2: Get the price for this ticker
        price = get_price_for_ticker(ticker)
        if price is None:
            logger.warning(f"No price found for ticker {ticker} (ISIN: {isin})")
            return {
                'success': False,
                'isin': isin,
                'ticker': ticker,
                'price': None,
                'status': 'price_not_found',
                'timestamp': datetime.now().isoformat()
            }
            
        return {
            'success': True,
            'isin': isin,
            'ticker': ticker,
            'price': price,
            'status': 'processed',
            'timestamp': datetime.now().isoformat()
        }
            
    except Exception as e:
        logger.error(f"Error processing ISIN {isin}: {str(e)}")
        return {
            'success': False,
            'isin': isin,
            'error': str(e),
            'status': 'error',
            'timestamp': datetime.now().isoformat()
        }

# Database and batch processing functions
def init_db():
    """Initialize SQLite database with required table."""
    conn = sqlite3.connect('portfolio.db')
    c = conn.cursor()
    
    # Drop the table if it exists and recreate with correct schema
    c.execute('DROP TABLE IF EXISTS batch_jobs')
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS batch_jobs (
            job_id TEXT PRIMARY KEY,
            status TEXT,
            progress INTEGER,
            total INTEGER,
            results TEXT,
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def process_isins(job_id):
    """Process all ISINs in the pre-defined list and fetch their data."""
    conn = sqlite3.connect('portfolio.db')
    c = conn.cursor()
    
    results = {}
    total = len(ISIN_TO_TICKER)
    processed = 0
    
    for isin in ISIN_TO_TICKER:
        try:
            result = get_isin_data(isin)
            results[isin] = result
        except Exception as e:
            logger.error(f"Error processing {isin}: {str(e)}")
            results[isin] = {
                'status': 'error',
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            }
        
        # Update progress
        processed += 1
        c.execute('''
            UPDATE batch_jobs 
            SET progress = ?, updated_at = ?
            WHERE job_id = ?
        ''', (processed, datetime.now().isoformat(), job_id))
        conn.commit()
    
    # Update final status and results
    c.execute('''
        UPDATE batch_jobs 
        SET status = ?, results = ?, progress = ?, updated_at = ?
        WHERE job_id = ?
    ''', ('completed', json.dumps(results), total, datetime.now().isoformat(), job_id))
    
    conn.commit()
    conn.close()

def start_batch_process():
    """Start a new batch processing job."""
    # Ensure database is initialized
    init_db()
    
    job_id = str(uuid.uuid4())
    conn = sqlite3.connect('portfolio.db')
    c = conn.cursor()
    
    # Initialize new job
    total = len(ISIN_TO_TICKER)
    c.execute('''
        INSERT INTO batch_jobs (job_id, status, progress, total, created_at, updated_at)
        VALUES (?, 'processing', 0, ?, ?, ?)
    ''', (job_id, total, datetime.now().isoformat(), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    # Start processing in background
    thread = threading.Thread(target=process_isins, args=(job_id,))
    thread.start()
    
    return job_id

def get_job_status(job_id: str) -> Dict[str, Any]:
    """
    Get the status and results of a batch processing job.
    
    Args:
        job_id (str): The ID of the job to check
        
    Returns:
        Dict[str, Any]: Job status and results
    """
    conn = sqlite3.connect('portfolio.db')
    c = conn.cursor()
    
    c.execute('SELECT * FROM batch_jobs WHERE job_id = ?', (job_id,))
    row = c.fetchone()
    
    if row is None:
        return {'status': 'not_found'}
        
    status = {
        'job_id': row[0],
        'status': row[1],
        'progress': row[2],
        'total': row[3],
        'results': json.loads(row[4]) if row[4] else None,
        'created_at': row[5],
        'updated_at': row[6]
    }
    
    conn.close()
    return status
