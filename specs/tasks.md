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
- [ ] Tests for `categoriser.py` (rule match, Gemini fallback, chunking)
- [ ] Tests for `scripts/backup_db.py`
- [ ] Tests for `pages/*` callbacks (dashboard, budgets, trips, trip_detail, scan_receipt, import_csv, add_expense)
- [ ] Budget alert tests; more `agent_bridge` tests (currently 3)

### Design cleanups
- [ ] Decide on soft delete for trip expenses (currently hard delete, unlike main expenses)
- [ ] Resolve DB paths relative to the project root instead of the working directory
- [ ] Add a schema version table instead of running all migrations on every start
- [x] Recompute the agent's "today" per request (`_instruction_provider` in `agent.py`)
