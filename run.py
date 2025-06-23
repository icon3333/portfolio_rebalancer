from app.main import create_app
import argparse

# Create the Flask application
app = create_app()

if __name__ == '__main__':
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description='Run the Portfolio Rebalancing Flask application')
    parser.add_argument('--port', type=int, default=5000,
                        help='Port to run the application on')
    args = parser.parse_args()

    # Run the application with the specified port
    app.run(host='0.0.0.0', port=args.port)
