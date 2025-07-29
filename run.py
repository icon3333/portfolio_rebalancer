import os
import sys
from pathlib import Path
from app.main import create_app
import argparse


def check_and_setup_environment():
    """Check if .env file exists and run setup if needed."""
    env_file = Path(".env")
    
    if not env_file.exists():
        print("🔧 No .env file found. Running environment setup...")
        print("=" * 50)
        
        try:
            # Import and run the setup
            from setup_env import setup_environment
            setup_environment()
            
            # Check if setup was successful
            if not env_file.exists():
                print("\n❌ Environment setup was cancelled or failed.")
                print("   Please run 'python setup_env.py' manually or create a .env file.")
                sys.exit(1)
                
        except KeyboardInterrupt:
            print("\n\n❌ Environment setup cancelled by user.")
            print("   Please run 'python setup_env.py' manually or create a .env file.")
            sys.exit(1)
        except Exception as e:
            print(f"\n❌ Error during environment setup: {e}")
            print("   Please run 'python setup_env.py' manually or create a .env file.")
            sys.exit(1)


# Create Flask app for gunicorn (must be at module level)
# In Docker, environment variables are already set, so we can create the app directly
try:
    app = create_app()
except Exception as e:
    # If app creation fails, it might be due to missing .env file
    # This should only happen in development, not in Docker
    print(f"Failed to create app: {e}")
    print("Trying to set up environment...")
    check_and_setup_environment()
    app = create_app()

if __name__ == '__main__':
    # Parse command line arguments first to check for skip flag
    parser = argparse.ArgumentParser(
        description='Run the Portfolio Rebalancing Flask application')
    parser.add_argument('--port', type=int, default=5000,
                        help='Port to run the application on')
    parser.add_argument('--skip-setup', action='store_true',
                        help='Skip automatic environment setup check')
    args = parser.parse_args()
    
    # Check environment setup before creating app (unless skipped)
    if not args.skip_setup:
        check_and_setup_environment()
    
    # Run the application with the specified port (app already created above)
    app.run(host='0.0.0.0', port=args.port, debug=True)
