# Research: Design Decisions

Current decisions behind the app. The original CSV-era research (stdlib `csv` persistence, integer ids from row count) is in git history; it was superseded when the app moved to SQLite (see `docs/superpowers/specs/2026-06-13-expense-tracker-v2-design.md`).

## 1. Storage

**Decision**: SQLite via the stdlib `sqlite3` module, one file for expenses (`expenses.db`) and one for trips (`trips.db`).

**Rationale**: Zero extra dependencies, queryable for dashboards, history search and budgets, soft delete and migrations are straightforward. Fine at personal scale.

**Trade-offs**: DB paths are relative to the working directory, and migrations run on every start with no version table. Both are listed as known gaps in `plan.md`.

## 2. Categorisation

**Decision**: Three layers.
1. The agent infers the category from its instruction, with no extra API call.
2. `categoriser.py` applies rule-based merchant matching for CSV import.
3. Anything unmatched goes to Gemini in chunks of 50.

**Rationale**: Rules are cheap and deterministic for known merchants; Gemini covers the long tail. The fixed list of 16 categories keeps output consistent (see `docs/superpowers/specs/2026-06-22-categoriser-improvements.md`).

## 3. Natural-language parsing

**Decision**: Rely on Gemini via the system prompt, with no NLP library. Today's date is injected into the instruction on every request (an ADK `InstructionProvider`, `_instruction_provider` in `agent.py`), so relative dates stay correct in a long-running process.

## 4. Merchant normalisation

**Decision**: `normalize_merchant` in `db.py` maps variants to canonical names. Startup migrations fix historical rows, including rows where the agent stored "[Store] for [item]" as the description.

## 5. Duplicate detection

**Decision**: Same date + merchant + amount counts as a duplicate. `add_expense` warns without saving; `force_add_expense` saves after the user confirms. Trips have their own check.

## 6. Receipt scanning

**Decision**: Gemini Vision returns structured `ReceiptData`; the UI makes it editable and requires date confirmation, because dates older than 30 days are usually misreads. API failures (including `API_KEY_INVALID` 400s and transport errors) are shown in the UI.

## 7. UI stack

**Decision**: Plotly Dash with Dash Bootstrap Components, multi-page, plus an `agent_bridge` that wraps the async ADK runner behind a sync `chat()` call on a background event loop.

## 8. Backup

**Decision**: A standalone script copies both databases locally and to Google Drive via OAuth, run daily by a macOS schedule installed with `scripts/install_backup_schedule.sh`.
