import os
import sqlite3
import shutil
from datetime import datetime
import logging
from flask import g, current_app

# Configure logging
logger = logging.getLogger(__name__)

def get_db():
    """
    Get a database connection for the current request.
    The connection is cached and reused for the same request.
    """
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', ''),
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row
    
    return g.db

def close_db(e=None):
    """Close the database connection at the end of the request."""
    db = g.pop('db', None)
    
    if db is not None:
        db.close()

def init_db(app):
    """Initialize the database and create tables if they don't exist."""
    with app.app_context():
        db = get_db()
        
        try:
            # Check if tables exist
            cursor = db.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [table[0] for table in cursor.fetchall()]
            
            if not tables or 'accounts' not in tables:
                logger.info("Initializing database schema...")
                # Create tables from schema
                with open(os.path.join(os.path.dirname(__file__), 'schema.sql'), 'r') as f:
                    db.executescript(f.read())
                db.commit()
                logger.info("Database schema initialized.")
                
                # Create default data if needed
                create_default_data(db)
            else:
                # Verify schema is correct
                verify_schema(db)
                
            # Set up request teardown to close the db connection
            app.teardown_appcontext(close_db)
            
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise
            
def verify_schema(db):
    """Verify that the database schema is correct and up-to-date."""
    # This function would check if all required tables and columns exist
    # and optionally run migrations if needed
    pass

def create_default_data(db):
    """Create default data in the database if needed."""
    cursor = db.cursor()
    
    # Check if we need to create a default account
    cursor.execute("SELECT COUNT(*) FROM accounts")
    if cursor.fetchone()[0] == 0:
        # Create a default account
        cursor.execute("""
            INSERT INTO accounts (id, username, created_at)
            VALUES (1, '_global', datetime('now'))
        """)
        db.commit()
        logger.info("Created default global account (ID: 1)")

def backup_database():
    """Create a backup of the current database."""
    try:
        # Get database path
        db_path = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        backup_dir = current_app.config['DB_BACKUP_DIR']
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = os.path.join(backup_dir, f"backup_{timestamp}.db")
        
        # Create the backup
        shutil.copy(db_path, backup_filename)
        logger.info(f"Database backed up successfully to {backup_filename}")
        
        # Clean up old backups
        cleanup_old_backups(backup_dir, current_app.config['MAX_BACKUP_FILES'])
        
        return backup_filename
    except Exception as e:
        logger.error(f"Database backup failed: {e}")
        return None

def cleanup_old_backups(directory, max_files=10):
    """
    Remove older backup files to maintain a limit on the number of backups.
    Keeps the most recent 'max_files' backup files.
    """
    try:
        # Get a list of all backup files
        backup_files = [os.path.join(directory, f) for f in os.listdir(directory) 
                       if f.endswith(".db") and os.path.isfile(os.path.join(directory, f))]
        
        # Sort by modification time (newest first)
        backup_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
        
        # Remove older backups
        for old_backup in backup_files[max_files:]:
            os.remove(old_backup)
            logger.info(f"Removed old backup: {old_backup}")
            
    except Exception as e:
        logger.error(f"Error cleaning up old backups: {e}")

def query_db(query, args=(), one=False):
    """
    Query the database and return the results.
    
    Args:
        query: SQL query string
        args: Parameters for the query
        one: If True, return one result or None, otherwise return all results
        
    Returns:
        Query results as dict or list of dicts
    """
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    
    # Convert row objects to dictionaries
    result = [dict(row) for row in rv]
    return (result[0] if result else None) if one else result

def execute_db(query, args=()):
    """
    Execute a database command and commit changes.
    
    Args:
        query: SQL query to execute
        args: Parameters for the query
        
    Returns:
        Number of affected rows
    """
    db = get_db()
    cursor = db.execute(query, args)
    db.commit()
    return cursor.rowcount