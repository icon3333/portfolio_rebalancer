# Portfolio Rebalancer

This project provides a small Flask application for tracking investment portfolios. It stores holdings in a SQLite database and fetches price data from the internet.

## Requirements

- Python 3.12
- Dependencies from `requirements.txt`

Install them using:

```bash
pip install -r requirements.txt
```

## Configuration

Set the `SECRET_KEY` environment variable before running the application. If unset, a random value will be generated.

```bash
export SECRET_KEY="your-secret-key"
```

## Running

Start the app using:

```bash
python run.py --port 5000
```

The application will be available at `http://localhost:5000`.

## Database changes

An index has been added on `companies.identifier` to speed up lookups. If you
have an existing database, recreate it or add the index manually:

```sql
CREATE INDEX idx_companies_identifier ON companies(identifier);
```
