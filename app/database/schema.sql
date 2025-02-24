-- Drop tables if they exist
DROP TABLE IF EXISTS expanded_state;
DROP TABLE IF EXISTS market_prices;
DROP TABLE IF EXISTS company_shares;
DROP TABLE IF EXISTS companies;
DROP TABLE IF EXISTS portfolios;
DROP TABLE IF EXISTS accounts;

-- Create accounts table
CREATE TABLE accounts (
    id INTEGER PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    created_at TEXT NOT NULL,
    last_price_update DATETIME
);

-- Create portfolios table
CREATE TABLE portfolios (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    account_id INTEGER NOT NULL,
    FOREIGN KEY (account_id) REFERENCES accounts (id),
    UNIQUE (account_id, name)
);

-- Create companies table
CREATE TABLE companies (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    identifier TEXT NOT NULL,
    category TEXT NOT NULL,
    portfolio_id INTEGER NOT NULL,
    account_id INTEGER NOT NULL,
    total_invested REAL DEFAULT 0,
    FOREIGN KEY (portfolio_id) REFERENCES portfolios (id),
    FOREIGN KEY (account_id) REFERENCES accounts (id),
    UNIQUE (account_id, name)
);

-- Create company_shares table
CREATE TABLE company_shares (
    company_id INTEGER PRIMARY KEY,
    shares REAL,
    override_share REAL,
    FOREIGN KEY (company_id) REFERENCES companies (id)
);

-- Create market_prices table
CREATE TABLE market_prices (
    identifier TEXT PRIMARY KEY,
    price REAL,
    currency TEXT,
    price_eur REAL,
    last_updated DATETIME
);

-- Create expanded_state table
CREATE TABLE expanded_state (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,
    page_name TEXT NOT NULL,
    variable_name TEXT NOT NULL,
    variable_type TEXT NOT NULL,
    variable_value TEXT NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (account_id) REFERENCES accounts (id),
    UNIQUE (account_id, page_name, variable_name)
);

-- Create indexes for market_prices
CREATE INDEX idx_market_prices_last_updated ON market_prices(last_updated);
CREATE INDEX idx_market_prices_identifier ON market_prices(identifier);

-- Create indexes for expanded_state
CREATE INDEX idx_state_lookup ON expanded_state(account_id, page_name, variable_name);
CREATE INDEX idx_state_type ON expanded_state(variable_type);
CREATE INDEX idx_state_updated ON expanded_state(last_updated);

-- Indexes for portfolio data query performance
CREATE INDEX idx_companies_account_id ON companies(account_id);
CREATE INDEX idx_company_shares_company_id ON company_shares(company_id);
CREATE INDEX idx_companies_portfolio_id ON companies(portfolio_id);

-- Create trigger for expanded_state
CREATE TRIGGER update_state_timestamp 
AFTER UPDATE ON expanded_state
BEGIN
    UPDATE expanded_state SET last_updated = CURRENT_TIMESTAMP
    WHERE id = NEW.id;
END;