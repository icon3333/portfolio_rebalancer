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

# Set environment variables
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"

# Run the application
python run.py --port 5000
```

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

Set these environment variables before running:

```bash
# Required for production
export SECRET_KEY="your-secure-secret-key-here"

# Optional - Database configuration
export DATABASE_URL="sqlite:///app/database/portfolio.db"  # Default
# Or for PostgreSQL: export DATABASE_URL="postgresql://user:pass@localhost/portfolio_db"

# Optional - Environment
export FLASK_ENV="development"  # or "production"
```

### Generate Secure Secret Key

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

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

### Production Security Checklist

✅ **Implemented Security Measures:**
- SSH keys removed from repository
- Database files properly ignored by git
- No hardcoded secrets in source code
- Secure session configuration with HTTPOnly cookies
- CSRF protection enabled
- File upload restrictions (CSV only, 16MB limit)
- Enhanced .gitignore with security patterns

### Required for Production

1. **Environment Variables**
   ```bash
   export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_hex(32))')"
   export DATABASE_URL="your-production-database-url"
   export FLASK_ENV="production"
   ```

2. **HTTPS Configuration**
   - Configure SSL/TLS certificates
   - Use reverse proxy with security headers
   - Enable HSTS (HTTP Strict Transport Security)

3. **Database Security**
   - Use PostgreSQL for production
   - Encrypt database backups
   - Implement connection pooling

### Security Monitoring

- Monitor failed login attempts
- Log database connection errors
- Track unusual portfolio access patterns
- Set up automated backups

### Backup Strategy
```bash
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
sqlite3 app/database/portfolio.db ".backup app/database/backups/backup_$DATE.db"
```

## 🛠️ Development

### Project Structure

```
portfolio_rebalancing_flask/
├── app/
│   ├── database/          # Database management
│   ├── routes/           # Flask routes
│   ├── utils/            # Utility functions
│   └── main.py          # Application factory
├── static/              # CSS, JS assets
├── templates/           # HTML templates
├── tests/              # Unit tests
├── config.py           # Configuration
└── run.py             # Application entry point
```

### Local Development Setup

1. Install development dependencies
2. Enable debug mode: `export FLASK_ENV="development"`
3. Use SQLite for local development
4. Run with auto-reload: `python run.py --debug`

## 🧪 Testing

Run the test suite:

```bash
# Install test dependencies
pip install -r requirements.txt

# Run tests
pytest -q

# Run with coverage
pytest --cov=app tests/
```

### Test Structure
- `tests/test_*.py` - Unit tests
- `tests/conftest.py` - Test configuration
- Coverage reports available in `htmlcov/`

## 🤝 Contributing

We welcome contributions! Please see our contributing guidelines:

1. **Fork the repository**
2. **Create a feature branch**
   ```bash
   git checkout -b feature/amazing-feature
   ```
3. **Make your changes**
   - Follow PEP 8 style guidelines
   - Add tests for new functionality
   - Update documentation as needed
4. **Run tests**
   ```bash
   pytest
   ```
5. **Submit a pull request**

### Development Guidelines

- Use meaningful commit messages
- Write tests for new features
- Update documentation
- Follow existing code style
- Ensure security best practices

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