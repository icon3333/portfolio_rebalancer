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
        db_path = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        g.db = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES)
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    """Close the database connection at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db(app):
    """
    Initialize the database and create tables if they don't exist.
    Then verify schema, run migrations, and optionally insert sample data if empty.
    """
    with app.app_context():
        db = get_db()
        try:
            # Create tables if not present
            cursor = db.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [row[0] for row in cursor.fetchall()]

            if not tables or 'accounts' not in tables:
                logger.info("Initializing database schema from schema.sql ...")
                schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
                with open(schema_path, 'r', encoding='utf-8') as f:
                    db.executescript(f.read())
                db.commit()
                logger.info("Database schema initialized.")

            # Verify that required columns exist, etc.
            verify_schema(db)

            # Run custom migration to fix old ISIN-based records
            migrate_market_prices_to_tickers(db)

            # Check if database is empty and insert sample data if you want
            if is_database_empty(db):
                logger.info("Database appears empty. Optionally adding sample data.")
                create_default_data(db)

            # Assign teardown
            app.teardown_appcontext(close_db)

        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
            raise

def verify_schema(db):
    """
    Verify that all required tables/columns are present.
    If something is missing, you can recreate or raise an error.
    """
    required_tables = [
        'accounts', 'portfolios', 'companies', 'company_shares',
        'market_prices', 'expanded_state'
    ]
    cursor = db.cursor()
    for table in required_tables:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", [table])
        result = cursor.fetchone()
        if not result:
            logger.warning(f"Missing table: {table}. You might need to re-run schema.sql or migrations.")

    # Example check for a column in 'companies'
    columns_check = cursor.execute("PRAGMA table_info(companies)").fetchall()
    col_names = [col[1] for col in columns_check]
    if 'total_invested' not in col_names:
        logger.warning("Column 'total_invested' missing in 'companies' table? Migration needed.")

def migrate_market_prices_to_tickers(db):
    """
    Perform a migration that converts old ISIN fields in market_prices
    to real ticker symbols if needed. 
    This is just an example - adapt to your actual needs.
    """
    logger.info("Running migrate_market_prices_to_tickers ...")
    cursor = db.cursor()

    # Example: Suppose old code stored `ticker` as ISIN if no real ticker was found.
    # We'll detect those (12 chars) and attempt to transform them.
    # In real usage, you might map them properly or remove them if invalid.

    # 1. Identify potential ISIN-based records
    cursor.execute("""
        SELECT ticker FROM market_prices
        WHERE LENGTH(ticker) = 12
    """)
    isin_rows = cursor.fetchall()
    if not isin_rows:
        logger.info("No ISIN-based ticker rows found. Migration not needed.")
        return

    # 2. For each row, do a fake transform or an actual transform:
    for row in isin_rows:
        old_ticker = row['ticker']
        # Example logic: just append '.DE' or do real mapping
        new_ticker = old_ticker + '.DE'
        logger.info(f"Migrating old ticker {old_ticker} -> {new_ticker}")

        cursor.execute("""
            UPDATE market_prices
            SET ticker = ?
            WHERE ticker = ?
        """, [new_ticker, old_ticker])

    db.commit()
    logger.info("migrate_market_prices_to_tickers complete.")

def is_database_empty(db):
    """
    Check if the database is basically empty (e.g., no user accounts or portfolios).
    Return True if it's empty, False otherwise.
    """
    cursor = db.cursor()
    # For instance, check if there are any accounts besides a global one
    cursor.execute("SELECT COUNT(*) as cnt FROM accounts")
    row = cursor.fetchone()
    if row and row['cnt'] == 0:
        return True
    return False

def create_default_data(db):
    """
    Insert any default or sample data if needed.
    This function is called when the database is detected as empty.
    """
    logger.info("Creating default sample data...")
    cursor = db.cursor()

    # Example: Create a placeholder global account
    cursor.execute("""
        INSERT INTO accounts (username, created_at) 
        VALUES ('_global', datetime('now'))
    """)
    db.commit()
    logger.info("Default global account created.")

def backup_database():
    """
    Create a backup of the current database.
    """
    try:
        db_path = current_app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')
        backup_dir = current_app.config['DB_BACKUP_DIR']
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_filename = os.path.join(backup_dir, f"backup_{timestamp}.db")

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
        backup_files = [
            os.path.join(directory, f) for f in os.listdir(directory)
            if f.endswith(".db") and os.path.isfile(os.path.join(directory, f))
        ]
        backup_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)

        for old_backup in backup_files[max_files:]:
            os.remove(old_backup)
            logger.info(f"Removed old backup: {old_backup}")

    except Exception as e:
        logger.error(f"Error cleaning up old backups: {e}")

def query_db(query, args=(), one=False):
    """
    Query the database and return results as dictionary objects.
    """
    cur = get_db().execute(query, args)
    rv = cur.fetchall()
    cur.close()
    result = [dict(row) for row in rv]
    return (result[0] if result else None) if one else result

def execute_db(query, args=()):
    """
    Execute a statement and commit changes, returning the rowcount.
    """
    db = get_db()
    cursor = db.execute(query, args)
    db.commit()
    return cursor.rowcount
