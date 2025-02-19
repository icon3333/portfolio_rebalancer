import os
from config import config
from app import (
    Flask, init_db,
    main_bp, account_bp, portfolio_bp, analysis_bp, merton_bp,
    register_error_handlers, register_context_processors
)

def create_app(config_name='default'):
    """Application factory function to create and configure the Flask app.
    
    Args:
        config_name: Configuration to use (default, development, testing, production)
        
    Returns:
        Configured Flask application
    """
    # Create Flask app instance
    app = Flask(__name__,
                template_folder='templates',
                static_folder='static')
    
    # Load configuration
    app.config.from_object(config[config_name])
    
    # Ensure required directories exist
    for directory in ['UPLOAD_FOLDER', 'DB_BACKUP_DIR']:
        if not os.path.exists(app.config[directory]):
            os.makedirs(app.config[directory])
    
    # Register blueprints
    blueprints = [
        (main_bp, ''),
        (account_bp, '/account'),
        (portfolio_bp, '/portfolio'),
        (analysis_bp, '/analysis'),
        (merton_bp, '/merton')
    ]
    
    for blueprint, url_prefix in blueprints:
        app.register_blueprint(blueprint, url_prefix=url_prefix)
    
    # Initialize database
    init_db(app)
    
    # Register error handlers and context processors
    register_error_handlers(app)
    register_context_processors(app)
    
    return app

if __name__ == '__main__':
    app = create_app()
    app.run()
