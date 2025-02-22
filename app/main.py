import os
from datetime import datetime
from flask import Flask, render_template, session
from config import config

def create_app(config_name='default'):
    """
    Application factory function to create and configure the Flask app.
    
    Args:
        config_name: Configuration to use (default, development, testing, production)
        
    Returns:
        Configured Flask application
    """
    # Create Flask app instance
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    
    # Configure app
    secret_key_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'secret_key')
    if os.path.exists(secret_key_file):
        with open(secret_key_file, 'rb') as f:
            secret_key = f.read()
    else:
        # Generate a new secret key
        secret_key = os.urandom(24)
        with open(secret_key_file, 'wb') as f:
            f.write(secret_key)
    
    app.config.update(
        SECRET_KEY=secret_key,
        SQLALCHEMY_DATABASE_URI='sqlite:///portfolio.db',
        TEMPLATES_AUTO_RELOAD=True,
        JSON_SORT_KEYS=False,
        SESSION_COOKIE_SECURE=False,  # Set to True in production with HTTPS
        SESSION_COOKIE_HTTPONLY=True,
        PERMANENT_SESSION_LIFETIME=3600 * 24 * 7  # 7 days
    )
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Ensure upload directory exists
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])
        
    # Ensure database backup directory exists
    if not os.path.exists(app.config['DB_BACKUP_DIR']):
        os.makedirs(app.config['DB_BACKUP_DIR'])
    
    # Register blueprints
    from app.routes.main_routes import main_bp
    app.register_blueprint(main_bp)
    
    from app.routes.account_routes import account_bp
    app.register_blueprint(account_bp, url_prefix='/account')
    
    from app.routes.portfolio_routes import portfolio_bp
    app.register_blueprint(portfolio_bp, url_prefix='/portfolio')
    
    from app.routes.analysis_routes import analysis_bp
    app.register_blueprint(analysis_bp, url_prefix='/analysis')
    
    from app.routes.merton_routes import merton_bp
    app.register_blueprint(merton_bp, url_prefix='/merton')
    
    # Initialize database
    from app.database.db_manager import init_db
    init_db(app)
    
    # Register error handlers
    register_error_handlers(app)
    
    # Register context processors
    register_context_processors(app)
    
    return app

def register_error_handlers(app):
    """Register custom error handlers."""
    
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template('errors/404.html'), 404
    
    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template('errors/500.html'), 500

def register_context_processors(app):
    """Register template context processors."""
    
    @app.context_processor
    def utility_processor():
        from app.utils.formatting import (
            format_number, 
            format_currency, 
            format_percentage
        )
        
        return dict(
            format_number=format_number,
            format_currency=format_currency,
            format_percentage=format_percentage,
            now=datetime.now()
        )