# Feature Spec: ExpenseAI

**Last refreshed**: 2026-11-23 (the original 2026-06-03 CSV-era spec is in git history)

## Overview

A local, single-user expense tracker with two ways in: a conversational Gemini agent and a Dash web UI. Expenses are stored in SQLite and explored through charts, history, budgets and trips.

## Requirements

### R1 — Persistence
- Expenses are stored in `expenses.db` (SQLite); trips in `trips.db`.
- Databases are created automatically on first run; schema changes are applied by idempotent migrations in `init_db()`.
- Main expenses are soft-deleted (`deleted` flag) so deletes can be undone. On every app startup, `app.py` attempts to import a legacy `expenses.csv`; archive it after verifying migration to avoid reimporting rows, especially those without a merchant.

### R2 — Conversational entry and auto-categorisation
- The agent (Gemini 2.5 Flash via Google ADK) turns free-form input such as "€9.49 at Edeka on 10/06" into amount, merchant, description, category and date.
- Categories come from a fixed list of 16 (`CATEGORIES` in `expense_tracker_agent/tools.py`), including Groceries, Food & Dining, Commute, Housing & Utilities and Miscellaneous. The agent infers the category and never asks for it.
- Relative dates ("yesterday") resolve against today's date, which is injected into the agent instruction on every request.
- Known merchants are normalised to a canonical name (`normalize_merchant` in `db.py`).
- Sub-items can be attached to a parent expense (`expense_items`).

### R3 — Duplicate protection
- `add_expense` warns without saving when the same date + merchant + amount already exists. `force_add_expense` saves after the user confirms.
- Trip expenses have their own duplicate detection.

### R4 — Bulk input
- **CSV import**: the main `/import` page accepts UTF-8, comma-separated files, auto-detects date/cost/merchant columns (DD/MM/YYYY aware; ISO year-first dates are read as year-month-day, via `parse_csv_date` in `dates.py`, which the trip importer also uses), shows a preview, reports per-row errors, and skips duplicates when a non-empty merchant matches. Categories come from `categoriser.py` (rules first, Gemini fallback in chunks of 50). Delimiter detection and a Latin-1 encoding fallback are available in the trip importer only.
- **Receipt scan**: Gemini Vision extracts merchant, total and line items into an editable table. The date is confirmed before saving (dates older than 30 days are flagged), and API errors surface as a message in the UI.

### R5 — Review and edit
- **Dashboard**: KPI cards, monthly trend, category donut, weekly bars, top merchants, weekly groceries trend, heatmap, and click-through day drill-down.
- **History**: keyword search, per-category averages, edit, delete with confirm and undo.

### R6 — Budgets
- Monthly limit per category (`budgets` table), set with sliders; the dashboard shows progress bars and alerts.

### R7 — Trips
- Separate expense lists per trip (`trips.db`): manual add, CSV import, edit, delete, duplicate detection, daily chart.

### R8 — Backup
- `scripts/backup_db.py` backs up both databases locally and to Google Drive (OAuth); a macOS schedule can be installed or removed with the scripts in `scripts/`.

## Constraints
- Local-only, single-user, personal scale (hundreds to low thousands of rows).
- Python >=3.11, managed with `uv`; `GOOGLE_API_KEY` is required for the agent, categoriser fallback and receipt scan.

## Out of Scope
- Multi-user accounts, cloud-hosted storage, mobile apps, bank-feed integration.
