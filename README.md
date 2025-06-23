# Portfolio Rebalancer 📈

A Flask web application for tracking and analyzing investment portfolios with automated rebalancing calculations and market data integration.

[![Python](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Flask](https://img.shields.io/badge/flask-latest-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Security](https://img.shields.io/badge/security-production%20ready-green.svg)](#security)

## 🚀 Features

- **Portfolio Management**: Track multiple investment portfolios with real-time valuation
- **Market Data Integration**: Automatic price fetching from Yahoo Finance
- **Rebalancing Calculator**: Smart allocation recommendations based on target percentages
- **Risk Analysis**: Portfolio composition and risk assessment tools
- **Bulk Operations**: Import/export portfolios via CSV files
- **Responsive UI**: Modern, mobile-friendly web interface
- **Security First**: Production-ready with comprehensive security measures

## 📋 Table of Contents

- [Quick Start](#-quick-start)
- [Installation](#-installation)
- [Configuration](#️-configuration)
- [Usage](#-usage)
- [Deployment](#-deployment)
- [Security](#-security)
- [Development](#️-development)
- [Testing](#-testing)
- [Contributing](#-contributing)
- [License](#-license)
- [Support](#-support)

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/your-username/portfolio-rebalancing-flask.git
cd portfolio-rebalancing-flask

# Install dependencies
pip install -r requirements.txt

# Run the application (will automatically set up environment if needed)
python run.py --port 5000
```

The app will automatically detect if you need environment setup and run the interactive configuration on first launch!

⚠️ **IMPORTANT**: This is now a production-ready application that requires proper environment configuration. No fallback values are used - all environment variables must be explicitly set.

Visit `http://localhost:5000` to access the application.

## 📦 Installation

### Prerequisites

- Python 3.12 or higher
- pip package manager

### Step-by-Step Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/your-username/portfolio-rebalancing-flask.git
   cd portfolio-rebalancing-flask
   ```

2. **Create a virtual environment** (recommended)
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Database setup** (automatic on first run)
   - SQLite database will be created automatically
   - For existing databases, add the performance index:
   ```sql
   CREATE INDEX idx_companies_identifier ON companies(identifier);
   ```

## ⚙️ Configuration

### Environment Variables

The application uses python-dotenv to automatically load environment variables from a `.env` file.

#### Option 1: Automatic Setup (Recommended)

```bash
# Just run the app - it will automatically set up environment if needed
python run.py --port 5000
```

Or run setup manually with different options:
```bash
# Default setup (development, SQLite, auto-generated secret)
python setup_env.py

# Production setup (production, SQLite, auto-generated secret)
python setup_env.py --production

# Interactive setup (prompts for all options)
python setup_env.py --interactive
```

**Default automatic setup provides:**
- ✅ Secure auto-generated SECRET_KEY
- ✅ SQLite database (good for development/small deployments)
- ✅ Development environment settings
- ✅ No user interaction required

#### Option 2: Manual Setup

1. Copy the example file:
```bash
cp .env.example .env
```

2. **IMPORTANT**: Edit `.env` and replace ALL placeholder values:
```bash
# REQUIRED: Generate a secure secret key (replace CHANGE_THIS_SECRET_KEY)
SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"

# REQUIRED: Database configuration (replace CHANGE_THIS_DATABASE_URL)
DATABASE_URL="sqlite:///app/database/portfolio.db"
# Or for PostgreSQL: DATABASE_URL="postgresql://user:pass@localhost/portfolio_db"

# REQUIRED: Flask environment (replace CHANGE_THIS_ENVIRONMENT)
FLASK_ENV="development"  # or "production"
```

⚠️ **The app will NOT start if any placeholder values remain unchanged!**

#### Option 3: Traditional Export (Not Recommended)

```bash
# Set environment variables manually (required each time)
export SECRET_KEY="your-secure-secret-key-here"
export DATABASE_URL="sqlite:///app/database/portfolio.db"
export FLASK_ENV="development"

# Run with skip flag to avoid automatic setup check
python run.py --port 5000 --skip-setup
```

### Benefits of Using .env File

- ✅ No need to set variables every time you run the app
- ✅ Different settings for different environments
- ✅ Automatically loaded by the application
- ✅ Gitignored - won't accidentally commit secrets
- ✅ Easy to share configuration templates
- ✅ **NEW**: Automatic setup on first run!

## 🎯 Usage

### Web Interface

1. **Start the application**
   ```bash
   python run.py --port 5000
   ```

2. **Access the dashboard** at `http://localhost:5000`

3. **Create your first portfolio**
   - Navigate to "Build Portfolio"
   - Add holdings manually or import via CSV
   - Set target allocations

4. **Analyze and rebalance**
   - View current allocations vs targets
   - Get rebalancing recommendations
   - Track performance over time

### CSV Import Format

```csv
symbol,shares,target_percentage
AAPL,100,25.0
GOOGL,50,30.0
MSFT,75,20.0
TSLA,25,25.0
```

### API Endpoints

- `GET /api/portfolio` - Get portfolio data
- `POST /api/portfolio/rebalance` - Calculate rebalancing
- `GET /health` - Health check endpoint

## 🚀 Deployment

> **📖 Complete deployment guide**: See [DEPLOYMENT.md](DEPLOYMENT.md) for comprehensive production deployment instructions.

### Quick Deployment Options

#### Option 1: Gunicorn (Recommended)
```bash
# Install Gunicorn
pip install gunicorn

# Run with multiple workers
gunicorn -w 4 -b 0.0.0.0:8000 run:app
```

#### Option 2: Docker
```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
EXPOSE 8000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8000", "run:app"]
```

```bash
docker build -t portfolio-rebalancer .
docker run -p 8000:8000 -e SECRET_KEY="your-secret" portfolio-rebalancer
```

#### Option 3: Cloud Platforms
- **Heroku**: Use the included `run.py` and `requirements.txt`
- **Railway**: Deploy directly from GitHub
- **DigitalOcean App Platform**: Configure via dashboard

### Reverse Proxy (Nginx)

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        
        # Security headers
        add_header X-Content-Type-Options nosniff;
        add_header X-Frame-Options DENY;
        add_header X-XSS-Protection "1; mode=block";
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains";
    }
}
```

## 🔒 Security

> **🔐 Complete security guide**: See [SECURITY.md](SECURITY.md) for detailed security guidelines and implementation checklist.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🆘 Support

### Getting Help

- **Issues**: [GitHub Issues](https://github.com/your-username/portfolio-rebalancing-flask/issues)
- **Discussions**: [GitHub Discussions](https://github.com/your-username/portfolio-rebalancing-flask/discussions)
- **Security**: Report security issues privately via email

### Common Issues

<details>
<summary>Database connection errors</summary>

Ensure your DATABASE_URL is correctly set and the database is accessible.
</details>

<details>
<summary>Market data not updating</summary>

Check your internet connection and Yahoo Finance API availability.
</details>

<details>
<summary>Import/export issues</summary>

Verify CSV format matches the expected schema with proper headers.
</details>

---

⭐ **If you find this project helpful, please give it a star!**

**Repository Status**: ✅ Production Ready | ✅ Security Audited | ✅ Safe for Public Release