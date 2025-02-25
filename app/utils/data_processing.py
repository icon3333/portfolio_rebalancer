"""
Utility functions for data processing and cache management.
"""
from functools import wraps
from flask import g

def clear_data_caches():
    """
    Clear any cached data in the application context.
    This helps ensure fresh data is fetched when needed.
    """
    if hasattr(g, 'portfolio_data'):
        delattr(g, 'portfolio_data')
    if hasattr(g, 'cached_prices'):
        delattr(g, 'cached_prices')
    if hasattr(g, 'cached_portfolios'):
        delattr(g, 'cached_portfolios')
