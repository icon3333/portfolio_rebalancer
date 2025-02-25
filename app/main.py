from flask import Flask, render_template, request, jsonify
import logging
import os
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_app(config_name='default'):
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
        JSON_SORT_KEYS=False
    )
    
    # Add context processor for datetime
    @app.context_processor
    def inject_now():
        return {'now': datetime.now()}
    
    # Register blueprints
    from app.routes.main_routes import main_bp
    app.register_blueprint(main_bp)
    
    from app.routes.account_routes import account_bp
    app.register_blueprint(account_bp, url_prefix='/account')
    
    from app.routes.portfolio_routes import portfolio_bp
    app.register_blueprint(portfolio_bp)
    
    from app.routes.merton_routes import merton_bp
    app.register_blueprint(merton_bp, url_prefix='/merton')
    
    from app.routes.analysis_routes import analysis_bp
    app.register_blueprint(analysis_bp, url_prefix='/analysis')
    
    # Initialize the database
    from app.database.db_manager import init_db
    init_db(app)
    
    @app.route('/profile', methods=['POST'])
    def get_profile():
        data = request.get_json() if request.is_json else request.form
        symbol = data.get('identifier', '').strip().upper()
        
        if not symbol:
            return jsonify({'error': 'No symbol provided'})
        
        try:
            from app.utils.yfinance_utils import get_yfinance_info
            result = get_yfinance_info(symbol)
            return jsonify(result)
                
        except Exception as e:
            logger.error(f"Error processing request: {str(e)}")
            return jsonify({'error': str(e)})
    
    return app