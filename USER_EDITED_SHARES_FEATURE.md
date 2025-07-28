# User-Edited Shares Feature

## Overview
This feature allows users to manually edit share quantities in the portfolio and tracks these edits with visual indicators. When CSV imports are performed, the system intelligently handles user-edited shares.

## Visual Indicators

### 🟠 Orange Font (User-Edited)
- **When**: User manually edits share quantity
- **Meaning**: This value was manually changed by the user
- **Tooltip**: Shows when the manual edit was made

### 🔴 Red Font (CSV-Modified After Edit)  
- **When**: User edited shares, then a CSV import with newer transactions modified the value
- **Meaning**: User edit + automatic adjustment from newer CSV transactions
- **Tooltip**: Shows original edit date and that CSV modified the value

## How It Works

### 1. Manual Share Editing
- User clicks on shares field and changes the value
- System records:
  - `manual_edit_date`: Timestamp of the edit
  - `is_manually_edited`: Flag set to `true`
  - `csv_modified_after_edit`: Flag set to `false`
- Visual indicator: **Orange font**

### 2. CSV Import Behavior

#### For Non-Edited Shares
- Normal behavior: CSV transactions are processed and total shares calculated
- Visual indicator: Normal black font

#### For User-Edited Shares
- System compares CSV transaction dates with `manual_edit_date`
- **If CSV has newer transactions**:
  - Calculates net change from newer transactions (buy = +, sell = -)
  - Applies change to user-edited value: `final_shares = manual_shares + net_change`
  - Sets `csv_modified_after_edit = true`
  - Visual indicator: **Red font**
- **If no newer transactions**:
  - Keeps user-edited value unchanged
  - Visual indicator: **Orange font**

### 3. Re-Editing Shares
- When user edits shares again:
  - Updates `manual_edit_date` to current time
  - Resets `csv_modified_after_edit = false`
  - Visual indicator: Back to **Orange font**

## Database Schema Changes

### New Columns in `company_shares` table:
```sql
manual_edit_date DATETIME          -- When user last edited shares
is_manually_edited BOOLEAN         -- Flag indicating user has edited
csv_modified_after_edit BOOLEAN    -- Flag indicating CSV modified after user edit
```

## Example Scenarios

### Scenario 1: Simple Manual Edit
1. User changes shares from 100 to 150
2. Result: **Orange font**, tooltip shows edit date

### Scenario 2: Manual Edit + Newer CSV Transactions
1. User edits shares to 150 on Jan 15
2. CSV import includes:
   - Jan 20: Buy 50 shares
   - Jan 25: Sell 25 shares
3. Net change: +25 shares
4. Final shares: 150 + 25 = 175
5. Result: **Red font**, tooltip shows original edit + CSV modification

### Scenario 3: Manual Edit + Older CSV Transactions
1. User edits shares to 150 on Jan 15
2. CSV import includes only transactions before Jan 15
3. Result: Shares stay at 150, **Orange font**

### Scenario 4: Re-editing After CSV Modification
1. Following Scenario 2 (shares = 175, red font)
2. User manually changes shares to 200
3. Result: **Orange font**, new edit date recorded

## Technical Implementation

### Frontend Changes
- **CSS Classes**: `.shares-user-edited` (orange), `.shares-csv-modified` (red)
- **Vue.js**: Conditional styling based on `is_manually_edited` and `csv_modified_after_edit` flags
- **API**: Sends `is_user_edit: true` flag when user makes manual changes

### Backend Changes
- **Portfolio API**: Tracks user edits with timestamps and flags
- **CSV Processing**: Enhanced logic to handle user-edited shares with date comparison
- **Database Migration**: Automatic addition of new columns on app startup

## Benefits
1. **User Control**: Manual adjustments are preserved and clearly indicated
2. **Smart Updates**: CSV imports intelligently handle user edits
3. **Transparency**: Clear visual feedback about data origin and modifications
4. **Flexibility**: Users can re-edit at any time to override system calculations

## Future Enhancements
- Audit log of all share changes
- Bulk edit support for user-edited shares
- Import conflict resolution UI
- Export functionality including edit metadata 