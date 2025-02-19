from flask import Flask, render_template
from app.database.db_manager import init_db
from app.routes.main_routes import main_bp
from app.routes.account_routes import account_bp
from app.routes.portfolio_routes import portfolio_bp
from app.routes.analysis_routes import analysis_bp
from app.routes.merton_routes import merton_bp

def register_error_handlers(app):
    """Register error handlers for the application."""
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        return render_template('errors/500.html'), 500

def register_context_processors(app):
    """Register context processors for the application."""
    @app.context_processor
    def utility_processor():
        return {
            'app_name': 'Portfolio Rebalancing'
        }

def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    
    # Configure database
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
    
    # Register blueprints
    app.register_blueprint(main_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(portfolio_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(merton_bp)
    
    # Initialize database
    init_db(app)
    
    # Register error handlers and context processors
    register_error_handlers(app)
    register_context_processors(app)
    
    return app

__all__ = [
    'Flask',
    'init_db',
    'main_bp',
    'account_bp',
    'portfolio_bp',
    'analysis_bp',
    'merton_bp',
    'register_error_handlers',
    'register_context_processors',
    'create_app'
]