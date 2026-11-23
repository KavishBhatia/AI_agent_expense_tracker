# Data Model

Two SQLite files in the working directory, both gitignored: `expenses.db` (`expense_tracker_agent/db.py`) and `trips.db` (`expense_tracker_agent/trip_db.py`).

## expenses.db

```sql
CREATE TABLE expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    amount      REAL    NOT NULL,
    merchant    TEXT,
    category    TEXT    NOT NULL,
    description TEXT    NOT NULL,
    date        TEXT    NOT NULL,                 -- ISO YYYY-MM-DD
    timestamp   TEXT    NOT NULL,                 -- ISO datetime, write time
    source      TEXT    NOT NULL DEFAULT 'manual',
    deleted     INTEGER NOT NULL DEFAULT 0        -- soft delete
);

CREATE TABLE expense_items (                      -- sub-items of a parent expense
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    parent_id   INTEGER NOT NULL REFERENCES expenses(id),
    amount      REAL    NOT NULL,
    description TEXT    NOT NULL,
    category    TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL
);

CREATE TABLE budgets (
    category      TEXT PRIMARY KEY,
    monthly_limit REAL NOT NULL
);
```

### Categories

`CATEGORIES` in `expense_tracker_agent/tools.py` (16 values): Groceries, Food & Dining, Commute, Entertainment, Clothing & Fashion, Pharmacy, Health & Fitness, Housing & Utilities, Travel, Electronics, Subscriptions, Personal Care, Education, Gifts, Alcohol, Miscellaneous.

### Migrations (run on every `init_db()`, idempotent)

- add the `deleted` column to older databases
- rename category Transport to Commute (expenses, expense_items, budgets)
- normalise known merchant names to canonical casing
- back-fill rows where the agent stored "[Store] for [item]" as the description
- `migrate_from_csv` imports a legacy `expenses.csv`

There is no schema version table.

## trips.db

```sql
CREATE TABLE trips (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE trip_expenses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trip_id     INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
    amount      REAL NOT NULL,
    merchant    TEXT,
    category    TEXT NOT NULL,
    description TEXT,
    date        TEXT NOT NULL
);
```

Trip expenses are hard-deleted.

## Data flow

```
Chat message -> Gemini agent -> add_expense (duplicate check when a merchant is supplied)
CSV row -> local date/amount parsing + categoriser -> import_csv_row (duplicate detection requires a non-empty merchant)
Receipt photo -> Gemini Vision -> editable review + date confirmation (no duplicate check)
    -> insert into expenses.db
    -> dashboard, history and budgets read from the same DB
```
