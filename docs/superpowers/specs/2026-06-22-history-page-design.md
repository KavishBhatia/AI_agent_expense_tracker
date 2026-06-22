# History Page — Design Spec

**Date:** 2026-06-22  
**Status:** Implemented — see changelog at end of document

---

## Goal

Add a dedicated **History** page (`/history`) to the sidebar that lets the user:
1. See average weekly and monthly spending for any category (e.g. Groceries)
2. Browse and search all past transactions by category and keyword — answering questions like "when did I last buy protein powder?"

Recent Transactions moves from the Dashboard to this page.

---

## Page Layout

### Section 1 — Category Insights

A category dropdown (default: "Groceries") drives three stat cards below it:

| Card | Content |
|------|---------|
| **Avg / Week** | Mean weekly spend for selected category, computed over all complete Mon–Sun weeks with data |
| **Avg / Month** | Mean monthly spend for selected category, computed over all complete calendar months with data |
| **Last Purchase** | Most recent transaction in that category — date, store name, amount + days-ago string |

When "All Categories" is selected the stat cards are hidden (averages are only meaningful per-category).

Clicking a category in the dropdown also syncs the Transaction Browser filter below so both sections stay in step.

### Section 2 — Transaction Browser

- **Category dropdown** (same options as above; synced with Section 1 selector)
- **Keyword search input** — filters on `merchant` and `description` fields, case-insensitive substring match
- **Results count** label (e.g. "12 transactions found")
- **Table** columns: Date | Store | Category (badge) | Amount | Description — sorted newest-first
- Empty state: "No transactions match your search." message

### Dashboard change

Remove the Recent Transactions table and heading from `pages/dashboard.py`. Replace with a small "→ View History" link pointing to `/history`.

---

## Data

No new DB functions are needed. `fetch_expenses()` already returns all non-deleted rows with all required fields. Filtering by category and keyword happens in Python inside the Dash callback.

Weekly / monthly averages are computed in Python:
- Group rows by ISO week number / year-month
- Drop the current (incomplete) week/month
- Average across all complete weeks / complete months with data

---

## Files

| File | Change |
|------|--------|
| `pages/history.py` | New page — layout + callbacks |
| `pages/dashboard.py` | Remove recent transactions section, add "→ View History" link |
| `app.py` | Add History nav link; lift delete/undo stores + toast into app layout so they persist across pages |

---

## Callbacks

**`update_history(cat, keyword)`**  
- Inputs: category dropdown value, search input value  
- State: none  
- Outputs: stat cards section (hidden or values), results count label, table rows  
- Triggered on any change to either input

---

## Verification

1. `uv run pytest tests/ -q` — all 69 existing tests pass
2. Start app: `uv run python app.py`
3. Navigate to `/history` via sidebar
4. Select "Groceries" → stat cards appear with correct avg/week, avg/month, last purchase
5. Type "protein" in search → only matching rows shown
6. Select "All Categories" → stat cards hide, all transactions shown
7. Confirm dashboard no longer shows Recent Transactions table

---

## Changelog (post-approval changes)

### Average calculation method changed
Original spec called for last-8-weeks / last-3-months windows. Implemented as **all-time calendar averages**: weekly avg divides by the actual number of complete Mon–Sun weeks with data; monthly avg divides by the actual number of complete 1st–last-day months with data. Subtitles updated to "Mon–Sun, all time" / "1st–last day, all time".

### Default category changed
Spec said default "All Categories". Changed to **"Groceries"** on both selectors (stat cards and transaction browser) to avoid slow initial load of the full DB on large datasets.

### Transaction browser pagination added
Replaced "All Categories capped at 20" with proper **10-rows-per-page pagination**: Prev / Next buttons + "Page X of Y" indicator. Filters reset to page 1 on any category or keyword change. Pagination works for all categories, not just "All Categories".

### Inline category editing added
Category column in the transaction table is a **live `dbc.Select` dropdown** instead of a static badge. Changing it writes to the DB immediately via `update_expense_category`. A `history-cat-updated-store` drives table refresh after each inline edit.

### app.py stores lifted
`expense-deleted-store`, `last-deleted-store`, and undo toast were moved from `pages/dashboard.py` into `app.py` so delete/undo works from the History page.
