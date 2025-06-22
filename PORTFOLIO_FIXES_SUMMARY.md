# Portfolio Management Fixes Summary

## Issues Identified and Fixed

### 1. Duplicate Portfolio Names Issue
**Problem**: The system was creating both "-" and "Default" portfolios, leading to confusion and inconsistency.

**Root Cause**: 
- CSV processing created "-" portfolios (`portfolio_processing.py` line 254-266)
- API updates created "Default" portfolios (`portfolio_api.py` line 47-61)

**Solution**:
- Standardized all portfolio creation to use "-" as the default portfolio name
- Updated all references from "Default" to "-" across the codebase
- Migrated existing "Default" portfolios to "-" in the database
- Removed all "Default" portfolios from the database

**Files Modified**:
- `app/utils/portfolio_processing.py`
- `app/routes/portfolio_api.py`
- `app/routes/portfolio_routes.py`
- `app/utils/portfolio_utils.py`

### 2. Portfolio Assignment Loss During CSV Upload
**Problem**: When uploading CSV files, all companies were reassigned to the "-" portfolio, losing their custom portfolio assignments.

**Root Cause**: The CSV processing code was forcing all companies to the default portfolio regardless of their existing portfolio assignment (line 282 in `portfolio_processing.py`).

**Solution**:
- Modified CSV processing to preserve existing portfolio assignments
- Only assign to "-" portfolio if the company doesn't have an existing valid portfolio
- Added logic to check for existing portfolio_id and preserve it

**Code Changes**:
```python
# Before
cursor.execute(
    'UPDATE companies SET identifier = ?, portfolio_id = ?, total_invested = ? WHERE id = ?',
    [position['identifier'], default_portfolio_id, total_invested, company_id],
)

# After
existing_portfolio_id = existing_company_map[company_name]['portfolio_id']
final_portfolio_id = existing_portfolio_id if existing_portfolio_id else default_portfolio_id
cursor.execute(
    'UPDATE companies SET identifier = ?, portfolio_id = ?, total_invested = ? WHERE id = ?',
    [position['identifier'], final_portfolio_id, total_invested, company_id],
)
```

### 3. Manual Share Override Loss During CSV Upload
**Problem**: When uploading CSV files, manually set share overrides (`override_share`) were being lost.

**Root Cause**: The CSV processing only updated the `shares` field but didn't preserve existing `override_share` values.

**Solution**:
- Added code to retrieve and preserve existing `override_share` values before processing
- Modified the share update logic to maintain `override_share` values
- Updated both INSERT and UPDATE operations to handle `override_share`

**Code Changes**:
```python
# Added before processing
existing_overrides = query_db(
    'SELECT cs.company_id, cs.override_share FROM company_shares cs JOIN companies c ON cs.company_id = c.id WHERE c.account_id = ?',
    [account_id]
)
override_map = {row['company_id']: row['override_share'] for row in existing_overrides if row['override_share'] is not None}

# Modified share updates
existing_override = override_map.get(company_id)
cursor.execute(
    'UPDATE company_shares SET shares = ?, override_share = ? WHERE company_id = ?',
    [current_shares, existing_override, company_id],
)
```

## Database Changes Made

1. **Migrated Portfolio Names**:
   ```sql
   UPDATE companies SET portfolio_id = (
       SELECT id FROM portfolios WHERE name = '-' AND account_id = companies.account_id
   ) WHERE portfolio_id = (
       SELECT id FROM portfolios WHERE name = 'Default' AND account_id = companies.account_id
   );
   ```

2. **Removed Duplicate Portfolios**:
   ```sql
   DELETE FROM portfolios WHERE name = 'Default';
   ```

## Current Database State

After fixes:
- Only "-" portfolios exist as default portfolios (no more "Default" portfolios)
- All existing portfolio assignments are preserved
- Manual share overrides are maintained during CSV uploads

## Testing Recommendations

1. **Test CSV Upload with Existing Data**:
   - Upload a CSV file with companies that already exist
   - Verify portfolio assignments are preserved
   - Verify manual share overrides remain intact

2. **Test Portfolio Assignment**:
   - Manually assign companies to custom portfolios
   - Upload CSV containing those companies
   - Confirm they remain in their assigned portfolios

3. **Test Share Overrides**:
   - Set manual share overrides for some companies
   - Upload CSV with updated transaction data
   - Verify overrides are preserved

## Benefits of These Fixes

1. **Consistency**: Single default portfolio name ("-") across the entire system
2. **Data Preservation**: Portfolio assignments and manual overrides are no longer lost
3. **User Experience**: Users can safely upload CSV files without losing their manual configurations
4. **Data Integrity**: No more duplicate or conflicting portfolio entries

## Files Modified

- `app/utils/portfolio_processing.py` - Fixed CSV processing logic
- `app/routes/portfolio_api.py` - Standardized portfolio creation
- `app/routes/portfolio_routes.py` - Updated portfolio references
- `app/utils/portfolio_utils.py` - Updated helper functions
- Database: Cleaned up duplicate portfolios and migrated data 