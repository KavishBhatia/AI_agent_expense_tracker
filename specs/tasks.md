# Tasks

**Last refreshed**: 2026-11-23. The original CSV-era task list (T001–T028) is in git history; all of it shipped or was superseded by the SQLite/Dash rewrite.

**Status key**: `[x]` = complete, `[ ]` = remaining

## Shipped

- [x] SQLite persistence with idempotent migrations (`db.py`)
- [x] ADK agent with auto-categorisation, merchant extraction and relative-date resolution (`agent.py`, `tools.py`)
- [x] Dash multi-page app and dashboard charts (`app.py`, `pages/`, `charts.py`)
- [x] Sub-expense line items
- [x] CSV import with auto-detection and per-row errors
- [x] Receipt scanning with date confirmation and API error handling
- [x] Rule-based categoriser with Gemini fallback (`categoriser.py`)
- [x] History page: search, edit, delete with undo
- [x] Duplicate detection (chat and trips)
- [x] Budgets with dashboard progress and alerts
- [x] Trips (separate DB, list/detail, CSV import, edit)
- [x] Daily backup to Google Drive and local
- [x] Merchant normalisation and recognised merchants (Action, Tedi, Woolworth, Amazon, Rossmann, Kaufland)
- [x] Refresh `specs/` and `README.md` to match the current app

## Remaining

### Test coverage
- [x] Tests for `categoriser.py` (rule match, Gemini fallback, chunking) in `tests/test_categoriser.py`
- [x] Tests for `scripts/backup_db.py` in `tests/test_backup_script.py`
- [x] Tests for `pages/*` callbacks (`tests/test_pages_*.py`: dashboard, history, backup, budgets, trips, trip_detail, scan_receipt, import_csv, add_expense)
- [x] Budget progress/threshold tests (dashboard) and more `agent_bridge` tests

### Design cleanups
- [ ] Decide on soft delete for trip expenses (currently hard delete, unlike main expenses)
- [ ] Resolve DB paths relative to the project root instead of the working directory
- [ ] Add a schema version table instead of running all migrations on every start
- [x] Recompute the agent's "today" per request (`_instruction_provider` in `agent.py`)

### Bugs found by the new tests (not yet fixed)
- [ ] Dashboard monthly view: clicking a month point (`MM/YYYY`) shows only the 1st of that month (`show_day_detail` in `pages/dashboard.py`)
- [ ] After an agent error, Add Expense can report the wrong expense as saved, because `fetch_expenses()` is sorted by date (`pages/add_expense.py`)
- [ ] Main CSV import crashes on non-UTF-8 files (e.g. Latin-1 from German Excel): the decode is outside the `try` (`pages/import_csv.py`)
- [ ] Backup page can show a stray file such as `expenses_manual.db` as the latest backup (reverse filename sort)
- [ ] `_infer_category` fallback matches substrings ("business lunch" becomes Commute, "barcelona trip" becomes Alcohol)
- [ ] Minor: "1 transactions" wording on the dashboard drill-down; failed CSV rows are numbered off by one; trip CSV amounts with thousands separators are silently skipped
