# User-Edited Shares Feature

## Overview
This feature allows users to manually edit share quantities in the portfolio and tracks these edits with visual indicators. When CSV imports are performed, the system intelligently handles user-edited shares by updating both original and override values simultaneously.

## Visual Indicators

### 🟠 Orange Font (User-Edited)
- **When**: User manually edits share quantity
- **Meaning**: This value was manually changed by the user
- **Tooltip**: Shows original shares value and when the manual edit was made

### 🔴 Red Font (CSV-Modified After Edit)  
- **When**: User edited shares, then a CSV import with newer transactions modified the value
- **Meaning**: User edit + automatic adjustment from newer CSV transactions
- **Tooltip**: Shows original shares value and that CSV modified the user edit

## Database Schema

### **Column Usage:**
- **`shares`**: Original CSV-calculated shares (updated with each CSV import)
- **`override_share`**: User-edited shares (takes priority for display)
- **`effective_shares`**: Computed field = `override_share || shares` (what user sees)

### **New Tracking Columns:**
```sql
manual_edit_date DATETIME          -- When user last edited shares
is_manually_edited BOOLEAN         -- Flag indicating user has edited
csv_modified_after_edit BOOLEAN    -- Flag indicating CSV modified after user edit
```

## How It Works

### 1. Manual Share Editing
- User clicks on shares field and changes the value
- System stores the edit in **`override_share`** column
- System records:
  - `manual_edit_date`: Timestamp of the edit
  - `is_manually_edited`: Flag set to `true`
  - `csv_modified_after_edit`: Flag set to `false`
- **`shares`** column remains unchanged (preserves original CSV value)
- Visual indicator: **Orange font**
- Hover tooltip: Shows original shares value

### 2. CSV Import Behavior

#### For Non-Edited Shares
- Normal behavior: CSV transactions are processed and `shares` column updated
- **`override_share`** remains `NULL`
- Visual indicator: Normal black font

#### For User-Edited Shares
- System compares CSV transaction dates with `manual_edit_date`
- **Updates BOTH columns simultaneously:**
  - **`shares`**: Updated with new CSV calculation
  - **`override_share`**: Updated with user edit + net change from newer transactions
- **If CSV has newer transactions**:
  - Calculates net change from newer transactions (buy = +, sell = -)
  - `shares` = new CSV total
  - `override_share` = old_user_edit + net_change
  - Sets `csv_modified_after_edit = true`
  - Visual indicator: **Red font**
- **If no newer transactions**:
  - `shares` = new CSV total  
  - `override_share` = unchanged user edit
  - Visual indicator: **Orange font**

### 3. Re-Editing Shares
- When user edits shares again:
  - Updates `override_share` with new value
  - Updates `manual_edit_date` to current time
  - Resets `csv_modified_after_edit = false`
  - Visual indicator: Back to **Orange font**

### 4. Display Logic
- **Frontend always shows**: `effective_shares = override_share || shares`
- **Hover tooltip shows**: Original shares value from `shares` column
- **Calculations use**: `effective_shares` for all value computations

## Example Scenarios

### Scenario 1: Simple Manual Edit
1. Original CSV shares: 100
2. User changes to 150
3. Database: `shares=100, override_share=150`
4. Display: 150 (orange font)
5. Tooltip: "Original shares: 100"

### Scenario 2: Manual Edit + Newer CSV Transactions
1. User edits to 150 on Jan 15
2. CSV import includes: Jan 20: Buy 50, Jan 25: Sell 25
3. Net change: +25 shares
4. Database: `shares=125, override_share=175` (150 + 25)
5. Display: 175 (red font)
6. Tooltip: "Original shares: 125"

### Scenario 3: Manual Edit + Older CSV Transactions  
1. User edits to 150 on Jan 15
2. CSV import includes only transactions before Jan 15
3. Database: `shares=100, override_share=150` (unchanged)
4. Display: 150 (orange font)
5. Tooltip: "Original shares: 100"

## Technical Implementation

### Backend Changes
- **User Edits**: Store in `override_share` column via portfolio API
- **CSV Processing**: Update both `shares` and `override_share` simultaneously
- **Date Comparison**: Check transaction dates vs manual edit dates

### Frontend Changes
- **Display**: Show `effective_shares` (computed from `override_share || shares`)
- **Calculations**: Use `effective_shares` for all value computations
- **Tooltips**: Show original shares value with edit status
- **Styling**: Conditional CSS based on edit flags

### API Changes
- **User Edit Endpoint**: `POST /portfolio/api/update_portfolio/<id>` with `override_share`
- **Data Structure**: Include `effective_shares` in portfolio data responses

## Benefits
1. **Data Integrity**: Original CSV values always preserved in `shares` column
2. **User Control**: Manual edits clearly separated in `override_share` column  
3. **Smart Updates**: CSV imports intelligently update both values
4. **Transparency**: Hover tooltips show original vs edited values
5. **Flexibility**: Users can re-edit anytime to override system calculations

## Testing
✅ **Database Schema**: New columns added successfully  
✅ **User Edits**: Stored correctly in `override_share` column  
✅ **Display Logic**: `effective_shares` calculation working  
✅ **Tooltips**: Show original shares value  
✅ **Visual Indicators**: Orange/red styling implemented  

The feature is fully implemented and ready for production use! 