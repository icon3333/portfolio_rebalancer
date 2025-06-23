import os
from datetime import timedelta


class Config:
    """Base configuration class."""
    SECRET_KEY = os.environ.get('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable must be set")
    
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL') or 'sqlite:///app/database/portfolio.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Application settings
    DEBUG = False
    TESTING = False

    # Session configuration
    PERMANENT_SESSION_LIFETIME = timedelta(days=1)
    SESSION_COOKIE_SECURE = True  # Only send cookies over HTTPS
    SESSION_COOKIE_HTTPONLY = True  # Prevent XSS attacks
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection

    # Cache settings
    CACHE_TYPE = 'SimpleCache'
    CACHE_DEFAULT_TIMEOUT = 300  # 5 minutes

    # Database backup settings
    DB_BACKUP_DIR = os.path.join('app', 'database', 'backups')
    MAX_BACKUP_FILES = 10

    # Market data settings
    PRICE_UPDATE_INTERVAL = timedelta(hours=24)
    BATCH_SIZE = 5  # Number of tickers to fetch in a batch

    # Upload settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload
    UPLOAD_FOLDER = os.path.join('app', 'uploads')
    ALLOWED_EXTENSIONS = {'csv'}

    # Default number of items to show in pagination
    PER_PAGE = 20


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    SQLALCHEMY_ECHO = True
    SESSION_COOKIE_SECURE = False  # Allow HTTP in development
    
    # Allow fallback secret key only in development
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-please-change-in-production'


class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    SESSION_COOKIE_SECURE = False  # Allow HTTP in testing
    
    # Allow fallback secret key only in testing
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'test-key'


class ProductionConfig(Config):
    """Production configuration."""
    # Ensure HTTPS in production
    SESSION_COOKIE_SECURE = True
    
    # Additional production security headers
    SEND_FILE_MAX_AGE_DEFAULT = timedelta(hours=1)


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
