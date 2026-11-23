# Implementation Plan: Expense Tracker

**Last refreshed**: 2026-11-23 (rewritten to match the current app; the original CSV-era plan is in git history)

## Summary

A personal expense tracker: a Dash multi-page web app plus a Google ADK chat agent (Gemini 2.5 Flash) that records expenses from natural language. Data lives in local SQLite databases. Extras include CSV import, receipt scanning (Gemini Vision), monthly budgets, per-trip expense tracking, charts, and daily backups to Google Drive.

## Technical Context

- **Language**: Python >=3.11, managed with `uv` (`uv.lock`), hatchling build
- **Dependencies**: `google-adk==2.3.0`, `google-generativeai`, `pydantic`, `dash>=2.14`, `dash-bootstrap-components>=1.5`, `plotly>=5.18`, `pandas>=2`, `google-auth-oauthlib` and `google-api-python-client` (Drive backup only)
- **Dev**: `pytest>=8` (tests are `unittest`-style classes run under pytest)
- **Model**: Gemini 2.5 Flash, used by the agent, the categoriser fallback and the receipt scanner
- **Setup**: `uv sync --dev`; copy `.env.example` to `.env` and set `GOOGLE_API_KEY`
- **Run**: `uv run python app.py` (http://localhost:8050); `expense_start.command` / `expense_stop.command` are macOS launchers
- **Test**: `uv run pytest tests/ -v`
- **Constraints**: local-only, single-user, personal scale

## Project Structure

```text
app.py                         # Dash shell: navbar, tools drawer, global stores, undo toast
assets/custom.css
pages/
├── dashboard.py               # KPI cards, charts, day drill-down, budget progress
├── add_expense.py             # chat UI over agent_bridge, date picker
├── history.py                 # search, per-category averages, edit, delete + undo
├── import_csv.py              # CSV upload, column auto-detect, preview
├── scan_receipt.py            # receipt scan -> editable table -> save
├── budgets.py                 # monthly budget sliders per category
├── backup.py                  # backup page
├── trips.py                   # trip list / create / delete
└── trip_detail.py             # trip expenses: add, import, edit, delete, duplicate detection
expense_tracker_agent/
├── agent.py                   # ADK root agent, _build_instruction(today)
├── agent_bridge.py            # sync chat() wrapper over the async ADK runner
├── tools.py                   # agent tools + CATEGORIES
├── categoriser.py             # rule-based merchant match, Gemini fallback
├── receipt_scanner.py         # Gemini Vision parse, date normalisation, API error handling
├── charts.py                  # KPI stats and Plotly figure builders
├── db.py                      # expenses.db access, migrations, merchant normalisation
├── dates.py                   # parse_csv_date: ISO read year-first, other formats day-first
└── trip_db.py                 # trips.db access
scripts/
├── backup_db.py               # local + Google Drive backup (--auth, --local)
└── install_backup_schedule.sh / uninstall_backup_schedule.sh
tests/                         # test_db, test_tools, test_trip_db, test_receipt_scanner,
                               # test_agent, test_agent_bridge, test_history, test_charts,
                               # test_fallback_parser, test_categoriser, test_dates
docs/superpowers/{specs,plans}/ # design docs for v2, history page, categoriser, trips
```

## Data Model

Both databases are SQLite files in the working directory (`expenses.db`, `trips.db`; both gitignored).

**`expenses.db`**
- `expenses`: id, amount, merchant, category, description, date, timestamp, source (default `manual`), deleted (soft delete)
- `expense_items`: line items, `parent_id` -> `expenses`
- `budgets`: category (PK), monthly_limit
- `init_db()` runs idempotent migrations on every start (add `deleted`, rename Transport -> Commute, normalise merchant casing, back-fill mis-parsed descriptions, import a legacy `expenses.csv`)

**`trips.db`**
- `trips`: id, name, created_at
- `trip_expenses`: id, trip_id (`ON DELETE CASCADE`), amount, merchant, category, description, date (hard delete)

## Agent Tools (`tools.py`)

`add_expense` (with duplicate detection), `force_add_expense`, `add_expense_item`, `list_expense_items`, `find_parent_expense_id`, `import_csv_row`, `calculate_total_spending`, `get_spending_by_category`, `list_recent_expenses`.

## Shipped

- CSV-based agent evolved into a Dash app on SQLite (v2), with six-plus charts and sub-expense line items
- History page: search, edit, delete with confirm and undo
- Budgets with progress bars and alerts on the dashboard
- Trips: separate DB, list/detail pages, CSV import, edit, duplicate detection
- CSV import hardening: delimiter/encoding detection, header fallbacks, per-row errors
- Chat duplicate-expense detection with force-add
- Merchant normalisation and recognition (Action, Tedi, Woolworth, Amazon, Rossmann, Kaufland)
- Receipt scan: date confirmation, API error handling (`API_KEY_INVALID`, transport failures)
- Daily backup of both DBs, local and Google Drive

## Backlog / Known Gaps

**Test coverage**
- Page callbacks are tested by calling them directly; Dash wiring (callback registration, layouts) and browser behaviour are not covered
- Several bugs found by these tests are listed in `tasks.md` under "Bugs found by the new tests"

**Documentation**
- `specs/` and `README.md` were refreshed on 2026-11-23 to match the current app; keep them in sync when features change (see `tasks.md`)

**Design inconsistencies**
- Trip expenses are hard-deleted while main expenses are soft-deleted
- DB paths are relative to the working directory, so running from elsewhere creates new DBs
- Migrations run on every start with no schema version table
