import logging
import threading
import uuid
import json
from datetime import datetime
from typing import Dict, Any, List
import sqlite3

# Import yfinance utility functions
from app.utils.yfinance_utils import get_isin_data
from app.utils.db_utils import update_price_in_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# This list is just a reference. Actual ISINs will come from the database or user input
ISIN_LIST = [
    'US88579Y1010',  # MMM
    'US36467W1099',  # GME
    'DE000BAY0017',  # Bayer
    'US0231351067',  # Amazon
    'US88160R1014',  # Tesla
    # (ISIN list shortened for clarity)
]

def init_db():
    """Initialize SQLite database with required table."""
    conn = sqlite3.connect('batch_jobs.db')
    c = conn.cursor()
    
    # We won't drop the table as in the working code sample
    # Instead, we'll create it if it doesn't exist
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

def process_isins(app, job_id, isins):
    """Process all ISINs in the list and fetch their data."""
    # We need to use app context for some database operations
    with app.app_context():
        conn = sqlite3.connect('batch_jobs.db')
        c = conn.cursor()
        
        results = {}
        total = len(isins)
        processed = 0
        success_count = 0
        failure_count = 0
        
        for isin in isins:
            try:
                logger.info(f"Processing ISIN {isin} ({processed+1}/{total})")
                result = get_isin_data(isin)
                results[isin] = result
                
                # Update price in database if successful
                if result.get('success') and result.get('price') is not None:
                    success = update_price_in_db(
                        isin, 
                        result.get('price'), 
                        result.get('currency', 'USD'),
                        result.get('price_eur', result.get('price')),
                        result.get('country'),  # Add country information
                        result.get('sector'),   # Add sector information
                        result.get('industry')  # Add industry information
                    )
                    
                    if success:
                        logger.info(f"Successfully updated price for {isin}: {result.get('price')} {result.get('currency', 'USD')}")
                        success_count += 1
                    else:
                        logger.warning(f"Failed to update price for {isin} in database")
                        failure_count += 1
                else:
                    logger.warning(f"No valid price data for {isin}: success={result.get('success')}, price={result.get('price')}")
                    failure_count += 1
                    
            except Exception as e:
                logger.error(f"Error processing {isin}: {str(e)}")
                results[isin] = {
                    'success': False,
                    'isin': isin,
                    'error': str(e),
                    'status': 'error',
                    'timestamp': datetime.now().isoformat()
                }
                failure_count += 1
            
            # Update progress
            processed += 1
            c.execute('''
                UPDATE batch_jobs 
                SET progress = ?, updated_at = ?
                WHERE job_id = ?
            ''', (processed, datetime.now().isoformat(), job_id))
            conn.commit()
        
        # Add success/failure counts to results
        summary = {
            'total': total,
            'success_count': success_count,
            'failure_count': failure_count,
            'completion_time': datetime.now().isoformat()
        }
        
        # Update final status and results
        c.execute('''
            UPDATE batch_jobs 
            SET status = ?, results = ?, progress = ?, updated_at = ?
            WHERE job_id = ?
        ''', ('completed', json.dumps({'items': results, 'summary': summary}), total, datetime.now().isoformat(), job_id))
        
        logger.info(f"Batch processing complete. Total: {total}, Success: {success_count}, Failed: {failure_count}")
        conn.commit()
        conn.close()

def start_batch_process(isins):
    """Start a new batch processing job."""
    # Ensure database is initialized
    init_db()
    
    job_id = str(uuid.uuid4())
    conn = sqlite3.connect('batch_jobs.db')
    c = conn.cursor()
    
    # Initialize new job
    total = len(isins)
    c.execute('''
        INSERT INTO batch_jobs (job_id, status, progress, total, created_at, updated_at)
        VALUES (?, 'processing', 0, ?, ?, ?)
    ''', (job_id, total, datetime.now().isoformat(), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    
    # Capture current app before starting thread
    from flask import current_app
    app = current_app._get_current_object()
    
    # Start processing in background
    thread = threading.Thread(target=process_isins, args=(app, job_id, isins))
    thread.daemon = True
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
    conn = sqlite3.connect('batch_jobs.db')
    c = conn.cursor()
    
    c.execute('SELECT * FROM batch_jobs WHERE job_id = ?', (job_id,))
    row = c.fetchone()
    
    if row is None:
        return {'status': 'not_found'}
    
    # Convert row to dictionary since SQLite Row objects might not be JSON serializable
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