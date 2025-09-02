"""
Simple Rule-Based Identifier Normalization for Crypto/Stock Detection

This module implements simple rule-based identifier normalization that automatically detects
and converts cryptocurrency symbols to their correct yfinance format (SYMBOL-USD)
while preserving stock tickers and ISINs in their original format.

Core concept: Use simple 5-rule system with fallback pattern instead of expensive dual-testing.
Fallback approach tries original format first, then crypto format if rules suggest it.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def normalize_identifier(identifier: str) -> str:
    """
    Primary entry point for identifier normalization using 5-rule system.
    
    Simple rule-based approach that directly applies crypto format if rules suggest it,
    avoiding expensive dual API testing during normalization.
    
    Args:
        identifier: Raw identifier from CSV/user input
        
    Returns:
        Normalized identifier for database storage
    """
    if not identifier or not identifier.strip():
        logger.warning("Empty identifier provided to normalize_identifier")
        return identifier
    
    clean_identifier = identifier.strip().upper()
    logger.info(f"Normalizing identifier: '{clean_identifier}'")
    
    # Apply 5-rule system directly
    if should_try_crypto_format(clean_identifier):
        crypto_format = f"{clean_identifier}-USD"
        logger.info(f"Applying crypto format: '{clean_identifier}' -> '{crypto_format}'")
        return crypto_format
    else:
        logger.info(f"Using stock format: '{clean_identifier}'")
        return clean_identifier


def should_try_crypto_format(identifier: str) -> bool:
    """
    Simple 5-rule crypto detection system.
    
    Rules (in order):
    1. Already ends with -USD? → Use as-is (False)
    2. Is ISIN (12 chars)? → Stock format (False) 
    3. Has exchange suffix (.)? → Stock format (False)
    4. Is ≤6 chars alphabetic? → Try crypto fallback (True)
    5. Default → Stock format (False)
    
    Args:
        identifier: Cleaned identifier string
        
    Returns:
        True if identifier should get crypto fallback attempt
    """
    clean_id = identifier.upper().strip()
    
    # Rule 1: Already crypto format
    if clean_id.endswith('-USD'):
        logger.debug(f"'{identifier}' already crypto format")
        return False
    
    # Rule 2: ISIN format (12 chars starting with 2 letters)
    if len(clean_id) == 12 and clean_id[:2].isalpha() and clean_id[2:].isalnum():
        logger.debug(f"'{identifier}' identified as ISIN (stock format)")
        return False
    
    # Rule 3: Exchange suffix
    if '.' in clean_id:
        logger.debug(f"'{identifier}' has exchange suffix (stock format)")
        return False
        
    # Rule 4: Short alphabetic (main crypto pattern)
    if len(clean_id) <= 6 and clean_id.isalpha():
        logger.debug(f"'{identifier}' is ≤6 chars alphabetic (try crypto fallback)")
        return True
    
    # Rule 5: Default to stock format
    logger.debug(f"'{identifier}' defaults to stock format")
    return False


def fetch_price_with_crypto_fallback(identifier: str) -> Dict[str, Any]:
    """
    Universal fallback pattern - replaces dual testing with simple fallback.
    
    Process:
    1. Try original identifier first (1 API call)
    2. If failed and rules suggest crypto, try with -USD (1 more API call)
    3. Return best result
    
    This replaces the expensive dual-testing approach with a fast fallback pattern.
    
    Args:
        identifier: Identifier to fetch price for
        
    Returns:
        Price data dictionary with success status
    """
    from .yfinance_utils import _fetch_yfinance_data_robust
    
    logger.info(f"Fetching price with crypto fallback for: '{identifier}'")
    
    # Always try original identifier first
    result = _fetch_yfinance_data_robust(identifier)
    
    # If failed and rules suggest crypto, try with -USD
    if not result and should_try_crypto_format(identifier):
        crypto_identifier = f"{identifier}-USD"
        logger.info(f"Trying crypto fallback: {identifier} → {crypto_identifier}")
        
        result = _fetch_yfinance_data_robust(crypto_identifier)
        
        if result:
            logger.info(f"Crypto fallback successful for: {crypto_identifier}")
            return {**result, 'effective_identifier': crypto_identifier}
    
    if result:
        logger.info(f"Original format successful for: {identifier}")
        return {**result, 'effective_identifier': identifier}
    else:
        logger.warning(f"Both original and crypto fallback failed for: {identifier}")
        return {}


# Legacy dual testing function removed
# Dual testing has been replaced with simple fallback pattern in fetch_price_with_crypto_fallback()
# This eliminates the expensive 2-API-calls-per-identifier approach during normalization


def cleanup_crypto_duplicates() -> Dict[str, Any]:
    """
    One-time cleanup of existing duplicate entries caused by crypto format mismatch.
    
    Process:
    1. Find duplicate pairs in market_prices (base + -USD formats)
    2. Check which companies are using which format
    3. Remove unused duplicate market_prices entries
    4. Log all changes for audit trail
    
    Returns:
        Dictionary with cleanup results and statistics
    """
    from .db_utils import query_db
    from ..database.db_manager import get_db
    
    logger.info("Starting crypto duplicates cleanup")
    
    try:
        db = get_db()
        cursor = db.cursor()
        
        # Find duplicate pairs in market_prices using a direct approach
        duplicates_found = query_db('''
            SELECT 
                mp1.identifier as base_id,
                mp2.identifier as crypto_id,
                mp1.price as base_price,
                mp2.price as crypto_price,
                mp1.last_updated as base_updated,
                mp2.last_updated as crypto_updated
            FROM market_prices mp1
            JOIN market_prices mp2 ON mp2.identifier = mp1.identifier || '-USD'
            WHERE LENGTH(mp1.identifier) <= 5
            AND mp1.identifier NOT LIKE '%.%'
            AND mp1.identifier NOT LIKE '%-%'
            ORDER BY mp1.identifier
        ''')
        
        if not duplicates_found:
            logger.info("No duplicate pairs found in market_prices")
            return {
                'success': True,
                'companies_updated': 0,
                'market_prices_removed': 0,
                'pairs_found': [],
                'message': 'No duplicate pairs found - database is clean'
            }
        
        logger.info(f"Found {len(duplicates_found)} duplicate pairs in market_prices")
        
        pairs_processed = []
        companies_updated = 0
        market_prices_removed = 0
        
        for dup in duplicates_found:
            base_id = dup['base_id']
            crypto_id = dup['crypto_id']
            
            logger.info(f"Processing duplicate pair: '{base_id}' ↔ '{crypto_id}'")
            
            # Check which companies are using each format
            companies_using_base = query_db(
                'SELECT COUNT(*) as count FROM companies WHERE identifier = ?',
                [base_id],
                one=True
            )['count']
            
            companies_using_crypto = query_db(
                'SELECT COUNT(*) as count FROM companies WHERE identifier = ?', 
                [crypto_id],
                one=True
            )['count']
            
            logger.info(f"  Companies using '{base_id}': {companies_using_base}")
            logger.info(f"  Companies using '{crypto_id}': {companies_using_crypto}")
            
            action_taken = ""
            
            if companies_using_crypto > 0 and companies_using_base == 0:
                # Companies are using crypto format, remove base format from market_prices
                cursor.execute(
                    'DELETE FROM market_prices WHERE identifier = ?',
                    [base_id]
                )
                market_prices_removed += 1
                action_taken = "removed_unused_base_format"
                logger.info(f"  ✅ Removed unused base format '{base_id}' from market_prices")
                
            elif companies_using_base > 0 and companies_using_crypto == 0:
                # Companies are using base format, remove crypto format from market_prices
                cursor.execute(
                    'DELETE FROM market_prices WHERE identifier = ?',
                    [crypto_id]
                )
                market_prices_removed += 1
                action_taken = "removed_unused_crypto_format"
                logger.info(f"  ✅ Removed unused crypto format '{crypto_id}' from market_prices")
                
            elif companies_using_crypto > 0 and companies_using_base > 0:
                # Both formats are being used - need to decide which to keep
                # Test which format actually works with yfinance
                if _test_yfinance_format(crypto_id):
                    # Crypto format works - migrate base format companies to crypto
                    companies_to_update = query_db(
                        'SELECT id, name FROM companies WHERE identifier = ?',
                        [base_id]
                    )
                    
                    for company in companies_to_update:
                        cursor.execute('''
                            UPDATE companies 
                            SET identifier = ?
                            WHERE id = ?
                        ''', [crypto_id, company['id']])
                        companies_updated += 1
                        logger.info(f"  ✅ Updated company '{company['name']}': '{base_id}' → '{crypto_id}'")
                    
                    # Remove base format from market_prices
                    cursor.execute(
                        'DELETE FROM market_prices WHERE identifier = ?',
                        [base_id]
                    )
                    market_prices_removed += 1
                    action_taken = "migrated_to_crypto_format"
                    
                elif _test_yfinance_format(base_id):
                    # Base format works - migrate crypto format companies to base
                    companies_to_update = query_db(
                        'SELECT id, name FROM companies WHERE identifier = ?',
                        [crypto_id]
                    )
                    
                    for company in companies_to_update:
                        cursor.execute('''
                            UPDATE companies 
                            SET identifier = ?
                            WHERE id = ?
                        ''', [base_id, company['id']])
                        companies_updated += 1
                        logger.info(f"  ✅ Updated company '{company['name']}': '{crypto_id}' → '{base_id}'")
                    
                    # Remove crypto format from market_prices
                    cursor.execute(
                        'DELETE FROM market_prices WHERE identifier = ?',
                        [crypto_id]
                    )
                    market_prices_removed += 1
                    action_taken = "migrated_to_base_format"
                    
                else:
                    # Neither works reliably - keep crypto format (safer assumption)
                    companies_to_update = query_db(
                        'SELECT id, name FROM companies WHERE identifier = ?',
                        [base_id]
                    )
                    
                    for company in companies_to_update:
                        cursor.execute('''
                            UPDATE companies 
                            SET identifier = ?
                            WHERE id = ?
                        ''', [crypto_id, company['id']])
                        companies_updated += 1
                        logger.info(f"  ⚠️ Updated company '{company['name']}': '{base_id}' → '{crypto_id}' (fallback)")
                    
                    # Remove base format from market_prices
                    cursor.execute(
                        'DELETE FROM market_prices WHERE identifier = ?',
                        [base_id]
                    )
                    market_prices_removed += 1
                    action_taken = "fallback_to_crypto_format"
                    
            else:
                # Neither format is being used by companies - keep the more recent one
                base_updated = dup['base_updated']
                crypto_updated = dup['crypto_updated']
                
                if crypto_updated > base_updated:
                    cursor.execute(
                        'DELETE FROM market_prices WHERE identifier = ?',
                        [base_id]
                    )
                    market_prices_removed += 1
                    action_taken = "kept_more_recent_crypto"
                    logger.info(f"  ✅ Kept more recent crypto format '{crypto_id}', removed '{base_id}'")
                else:
                    cursor.execute(
                        'DELETE FROM market_prices WHERE identifier = ?',
                        [crypto_id]
                    )
                    market_prices_removed += 1
                    action_taken = "kept_more_recent_base"
                    logger.info(f"  ✅ Kept more recent base format '{base_id}', removed '{crypto_id}'")
            
            pairs_processed.append({
                'base': base_id,
                'crypto': crypto_id,
                'action': action_taken,
                'companies_affected': companies_using_base + companies_using_crypto
            })
        
        # Commit changes
        db.commit()
        
        result = {
            'success': True,
            'companies_updated': companies_updated,
            'market_prices_removed': market_prices_removed,
            'pairs_found': pairs_processed,
            'message': f'Cleanup completed: {companies_updated} companies updated, {market_prices_removed} duplicate prices removed from {len(duplicates_found)} pairs'
        }
        
        logger.info(f"Cleanup completed successfully: {result['message']}")
        return result
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")
        if 'db' in locals():
            db.rollback()
        return {
            'success': False,
            'error': str(e),
            'companies_updated': 0,
            'market_prices_removed': 0,
            'pairs_found': [],
            'message': f'Cleanup failed: {str(e)}'
        }


# Test data for validation
TEST_CASES = [
    # Clear stocks - should not be normalized
    ("US0378331005", "US0378331005"),  # Apple ISIN
    ("AAPL.DE", "AAPL.DE"),           # Exchange-specific
    ("2222.SR", "2222.SR"),           # Saudi exchange
    
    # Clear crypto - will be tested and normalized if appropriate
    ("BTC", "BTC-USD"),               # Bitcoin (expected)
    ("ETH", "ETH-USD"),               # Ethereum (expected)
    ("ATOM", "ATOM-USD"),             # Cosmos (expected)
    
    # Ambiguous cases - will be tested to determine correct format (now preferring crypto)
    ("AAPL", "AAPL-USD"),             # Could be stock or crypto - prefer crypto format if both work
    ("LINK", "LINK-USD"),             # Crypto symbol (expected)
    
    # Edge cases
    ("", ""),                         # Empty
    ("INVALID", "INVALID"),           # Neither format works (expected)
]


def run_test_cases() -> Dict[str, Any]:
    """
    Run test cases to validate normalization logic.
    
    Returns:
        Test results with success/failure statistics
    """
    logger.info("Running identifier normalization test cases")
    
    results = {
        'total_tests': len(TEST_CASES),
        'passed': 0,
        'failed': 0,
        'details': []
    }
    
    for input_id, expected_output in TEST_CASES:
        try:
            actual_output = normalize_identifier(input_id)
            passed = actual_output == expected_output
            
            if passed:
                results['passed'] += 1
                logger.info(f"✅ Test passed: '{input_id}' -> '{actual_output}'")
            else:
                results['failed'] += 1
                logger.warning(f"❌ Test failed: '{input_id}' -> expected '{expected_output}', got '{actual_output}'")
            
            results['details'].append({
                'input': input_id,
                'expected': expected_output, 
                'actual': actual_output,
                'passed': passed
            })
            
        except Exception as e:
            results['failed'] += 1
            logger.error(f"❌ Test error for '{input_id}': {e}")
            results['details'].append({
                'input': input_id,
                'expected': expected_output,
                'actual': f"ERROR: {str(e)}",
                'passed': False
            })
    
    success_rate = (results['passed'] / results['total_tests']) * 100 if results['total_tests'] > 0 else 0
    logger.info(f"Test results: {results['passed']}/{results['total_tests']} passed ({success_rate:.1f}%)")
    
    return results 