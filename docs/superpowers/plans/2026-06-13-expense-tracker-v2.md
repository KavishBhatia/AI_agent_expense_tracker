# Expense Tracker v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the expense tracker from a terminal-only CSV agent to a Plotly Dash web app with SQLite persistence, 6 dashboard charts, sub-expense line items, CSV import, and Gemini Vision receipt scanning.

**Architecture:** A Plotly Dash multi-page app (`app.py`) at `localhost:8050` sits on top of a SQLite database (`expenses.db`) managed by `expense_tracker_agent/db.py`. The existing ADK agent is wrapped by `agent_bridge.py` for sync use in Dash callbacks. Receipt scanning uses the `google-generativeai` client directly (already a dependency).

**Tech Stack:** Python 3.11+, SQLite (stdlib), Plotly Dash 2.x, dash-bootstrap-components, Plotly Express, pandas, Google ADK (existing), google-generativeai (existing)

---

## File Map

| File | Status | Responsibility |
|---|---|---|
| `expense_tracker_agent/db.py` | **CREATE** | SQLite schema, CRUD, migration from CSV |
| `expense_tracker_agent/tools.py` | **MODIFY** | Use SQLite, add new tools, extend CATEGORIES |
| `expense_tracker_agent/agent.py` | **MODIFY** | Register new tools, update system prompt |
| `expense_tracker_agent/receipt_scanner.py` | **CREATE** | Gemini Vision receipt parsing |
| `app.py` | **CREATE** | Dash app instance, navbar, page container |
| `charts.py` | **CREATE** | Plotly figure builders (queries + chart construction) |
| `agent_bridge.py` | **CREATE** | Thread-safe async-to-sync ADK wrapper |
| `pages/__init__.py` | **CREATE** | Empty — marks pages as package |
| `pages/dashboard.py` | **CREATE** | Dashboard page: KPIs + 6 charts |
| `pages/add_expense.py` | **CREATE** | Add Expense page: AI chat + recent list |
| `pages/import_csv.py` | **CREATE** | CSV Import page: upload → preview → confirm |
| `pages/scan_receipt.py` | **CREATE** | Scan Receipt page: upload → review → confirm |
| `pyproject.toml` | **MODIFY** | Add dash, dbc, plotly, pandas deps |
| `test_tools.py` | **MODIFY** | Patch DB_PATH instead of CSV_FILE |
| `tests/test_db.py` | **CREATE** | Unit tests for db.py |
| `tests/test_receipt_scanner.py` | **CREATE** | Unit tests for receipt_scanner.py (mocked) |
| `tests/test_charts.py` | **CREATE** | Unit tests for charts.py data queries |

---

## Task 1: SQLite Database Layer

**Files:**
- Create: `expense_tracker_agent/db.py`
- Create: `tests/__init__.py`
- Create: `tests/test_db.py`

- [ ] **Step 1: Write failing tests for db.py**

Create `tests/__init__.py` (empty), then create `tests/test_db.py`:

```python
# tests/test_db.py
import csv
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import expense_tracker_agent.db as db_module
from expense_tracker_agent.db import (
    expense_exists,
    fetch_expense_items,
    fetch_expenses,
    find_parent_expense,
    init_db,
    insert_expense,
    insert_expense_item,
    migrate_from_csv,
)


def _temp_db() -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    os.unlink(f.name)
    return Path(f.name)


class BaseDbTest(unittest.TestCase):
    def setUp(self):
        self.tmp_db = _temp_db()
        self.patcher = patch.object(db_module, "DB_PATH", self.tmp_db)
        self.patcher.start()
        init_db()

    def tearDown(self):
        self.patcher.stop()
        if self.tmp_db.exists():
            self.tmp_db.unlink()


class TestInitDb(BaseDbTest):
    def test_creates_expenses_table(self):
        conn = sqlite3.connect(self.tmp_db)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='expenses'"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)

    def test_creates_expense_items_table(self):
        conn = sqlite3.connect(self.tmp_db)
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='expense_items'"
        ).fetchone()
        conn.close()
        self.assertIsNotNone(row)

    def test_init_idempotent(self):
        init_db()  # second call must not raise
        conn = sqlite3.connect(self.tmp_db)
        count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        conn.close()
        self.assertEqual(count, 2)


class TestInsertExpense(BaseDbTest):
    def test_returns_integer_id(self):
        eid = insert_expense(10.0, "Food", "lunch")
        self.assertIsInstance(eid, int)
        self.assertGreater(eid, 0)

    def test_persists_to_db(self):
        insert_expense(5.50, "Groceries", "bread", merchant="Edeka", date="2026-06-01")
        rows = fetch_expenses()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["merchant"], "Edeka")
        self.assertAlmostEqual(rows[0]["amount"], 5.50)

    def test_default_source_is_manual(self):
        insert_expense(3.0, "Food", "coffee")
        rows = fetch_expenses()
        self.assertEqual(rows[0]["source"], "manual")

    def test_custom_source(self):
        insert_expense(20.0, "Groceries", "weekly shop", source="csv_import")
        rows = fetch_expenses()
        self.assertEqual(rows[0]["source"], "csv_import")


class TestInsertExpenseItem(BaseDbTest):
    def test_links_to_parent(self):
        parent_id = insert_expense(10.0, "Groceries", "Edeka shop", merchant="Edeka")
        item_id = insert_expense_item(parent_id, 3.0, "beer", "Alcohol")
        items = fetch_expense_items(parent_id)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["description"], "beer")
        self.assertEqual(items[0]["category"], "Alcohol")
        self.assertEqual(items[0]["parent_id"], parent_id)

    def test_returns_integer_id(self):
        parent_id = insert_expense(10.0, "Groceries", "shop")
        item_id = insert_expense_item(parent_id, 2.0, "bread", "Groceries")
        self.assertIsInstance(item_id, int)


class TestFetchExpenses(BaseDbTest):
    def test_date_filter_start(self):
        insert_expense(5.0, "Food", "lunch", date="2026-05-01")
        insert_expense(8.0, "Food", "dinner", date="2026-06-01")
        rows = fetch_expenses(start_date="2026-06-01")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2026-06-01")

    def test_date_filter_end(self):
        insert_expense(5.0, "Food", "lunch", date="2026-05-01")
        insert_expense(8.0, "Food", "dinner", date="2026-06-01")
        rows = fetch_expenses(end_date="2026-05-31")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2026-05-01")

    def test_no_filter_returns_all(self):
        insert_expense(5.0, "Food", "a")
        insert_expense(8.0, "Food", "b")
        self.assertEqual(len(fetch_expenses()), 2)


class TestExpenseExists(BaseDbTest):
    def test_returns_true_when_exists(self):
        insert_expense(10.0, "Groceries", "shop", merchant="Edeka", date="2026-06-01")
        self.assertTrue(expense_exists("2026-06-01", "Edeka", 10.0))

    def test_returns_false_when_not_exists(self):
        self.assertFalse(expense_exists("2026-06-01", "Edeka", 10.0))


class TestFindParentExpense(BaseDbTest):
    def test_finds_parent_by_merchant_and_date(self):
        eid = insert_expense(10.0, "Groceries", "Edeka shop", merchant="Edeka", date="2026-06-01")
        found = find_parent_expense("Edeka", "2026-06-01")
        self.assertEqual(found, eid)

    def test_returns_none_when_no_match(self):
        self.assertIsNone(find_parent_expense("Rewe", "2026-06-01"))


class TestMigrateFromCsv(BaseDbTest):
    def test_migrates_rows(self):
        tmp_csv = Path(tempfile.mktemp(suffix=".csv"))
        with open(tmp_csv, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["id", "amount", "category", "description", "merchant", "date", "timestamp"]
            )
            writer.writeheader()
            writer.writerow({
                "id": 1, "amount": 15.0, "category": "Food", "description": "pizza",
                "merchant": "Dominos", "date": "2026-05-10",
                "timestamp": "2026-05-10T12:00:00"
            })
        count = migrate_from_csv(tmp_csv)
        tmp_csv.unlink()
        self.assertEqual(count, 1)
        rows = fetch_expenses()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["description"], "pizza")

    def test_skips_duplicates(self):
        insert_expense(15.0, "Food", "pizza", merchant="Dominos", date="2026-05-10")
        tmp_csv = Path(tempfile.mktemp(suffix=".csv"))
        with open(tmp_csv, "w", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["id", "amount", "category", "description", "merchant", "date", "timestamp"]
            )
            writer.writeheader()
            writer.writerow({
                "id": 1, "amount": 15.0, "category": "Food", "description": "pizza",
                "merchant": "Dominos", "date": "2026-05-10",
                "timestamp": "2026-05-10T12:00:00"
            })
        count = migrate_from_csv(tmp_csv)
        tmp_csv.unlink()
        self.assertEqual(count, 0)

    def test_returns_zero_when_csv_missing(self):
        self.assertEqual(migrate_from_csv(Path("nonexistent.csv")), 0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/kavishbhatia/hobby/AI_agent_expense_tracker
python -m pytest tests/test_db.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'expense_tracker_agent.db'`

- [ ] **Step 3: Write `expense_tracker_agent/db.py`**

```python
# expense_tracker_agent/db.py
import csv as _csv
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path("expenses.db")


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                amount    REAL    NOT NULL,
                merchant  TEXT,
                category  TEXT    NOT NULL,
                description TEXT  NOT NULL,
                date      TEXT    NOT NULL,
                timestamp TEXT    NOT NULL,
                source    TEXT    NOT NULL DEFAULT 'manual'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expense_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id   INTEGER NOT NULL REFERENCES expenses(id),
                amount      REAL    NOT NULL,
                description TEXT    NOT NULL,
                category    TEXT    NOT NULL,
                timestamp   TEXT    NOT NULL
            )
        """)


def insert_expense(
    amount: float,
    category: str,
    description: str,
    merchant: Optional[str] = None,
    date: Optional[str] = None,
    source: str = "manual",
) -> int:
    ts = datetime.now().isoformat(timespec="seconds")
    d = date or datetime.now().date().isoformat()
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO expenses (amount, merchant, category, description, date, timestamp, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (amount, merchant, category, description, d, ts, source),
        )
        return cur.lastrowid


def insert_expense_item(parent_id: int, amount: float, description: str, category: str) -> int:
    ts = datetime.now().isoformat(timespec="seconds")
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO expense_items (parent_id, amount, description, category, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (parent_id, amount, description, category, ts),
        )
        return cur.lastrowid


def fetch_expenses(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    sql = "SELECT * FROM expenses WHERE 1=1"
    params: list = []
    if start_date:
        sql += " AND date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND date <= ?"
        params.append(end_date)
    sql += " ORDER BY date ASC, id ASC"
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def fetch_expense_items(parent_id: int) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM expense_items WHERE parent_id = ? ORDER BY id",
            (parent_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def expense_exists(date: str, merchant: str, amount: float) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM expenses WHERE date=? AND merchant=? AND amount=?",
            (date, merchant, amount),
        ).fetchone()
    return row is not None


def find_parent_expense(merchant: str, date: str) -> Optional[int]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM expenses WHERE merchant=? AND date=? ORDER BY id DESC LIMIT 1",
            (merchant, date),
        ).fetchone()
    return row["id"] if row else None


def migrate_from_csv(csv_path: Path) -> int:
    if not csv_path.exists():
        return 0
    count = 0
    with open(csv_path, newline="") as f:
        for row in _csv.DictReader(f):
            merchant = row.get("merchant") or None
            if not expense_exists(row["date"], merchant or "", float(row["amount"])):
                insert_expense(
                    amount=float(row["amount"]),
                    category=row["category"],
                    description=row["description"],
                    merchant=merchant,
                    date=row["date"],
                    source="csv_import",
                )
                count += 1
    return count
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_db.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add expense_tracker_agent/db.py tests/__init__.py tests/test_db.py
git commit -m "feat: add SQLite database layer with schema and migration"
```

---

## Task 2: Migrate tools.py to SQLite

**Files:**
- Modify: `expense_tracker_agent/tools.py`
- Modify: `test_tools.py`

- [ ] **Step 1: Update `test_tools.py` to patch DB_PATH instead of CSV_FILE**

Replace the `BaseToolsTest` class and imports at the top of `test_tools.py`:

```python
# test_tools.py — replace the imports section and BaseToolsTest
import os
import sqlite3
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import expense_tracker_agent.db as db_module
import expense_tracker_agent.tools as tools_module
from expense_tracker_agent.db import init_db
from expense_tracker_agent.tools import (
    CATEGORIES,
    add_expense,
    add_expense_item,
    calculate_total_spending,
    get_spending_by_category,
    import_csv_row,
    list_expense_items,
    list_recent_expenses,
)


def _temp_db() -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    os.unlink(f.name)
    return Path(f.name)


class BaseToolsTest(unittest.TestCase):
    def setUp(self):
        self.tmp_db = _temp_db()
        self.db_patcher = patch.object(db_module, "DB_PATH", self.tmp_db)
        self.db_patcher.start()
        init_db()

    def tearDown(self):
        self.db_patcher.stop()
        if self.tmp_db.exists():
            self.tmp_db.unlink()
```

Also add tests for the three new tools at the bottom of `test_tools.py`:

```python
class TestAddExpenseItem(BaseToolsTest):
    def test_adds_item_to_existing_parent(self):
        add_expense(10.0, "Edeka shop", "Groceries", merchant="Edeka")
        from expense_tracker_agent.db import find_parent_expense
        from datetime import date as _date
        today = _date.today().isoformat()
        parent_id = find_parent_expense("Edeka", today)
        result = add_expense_item(parent_id, 3.0, "beer", "Alcohol")
        self.assertIn("beer", result)
        self.assertIn("3.00", result)

    def test_returns_error_for_invalid_parent(self):
        result = add_expense_item(9999, 3.0, "beer", "Alcohol")
        self.assertIn("not found", result.lower())


class TestListExpenseItems(BaseToolsTest):
    def test_lists_items_for_parent(self):
        add_expense(10.0, "Edeka shop", "Groceries", merchant="Edeka")
        from expense_tracker_agent.db import find_parent_expense
        from datetime import date as _date
        today = _date.today().isoformat()
        parent_id = find_parent_expense("Edeka", today)
        add_expense_item(parent_id, 3.0, "beer", "Alcohol")
        add_expense_item(parent_id, 2.0, "bread", "Groceries")
        result = list_expense_items(parent_id)
        self.assertIn("beer", result)
        self.assertIn("bread", result)

    def test_returns_empty_message_when_no_items(self):
        add_expense(10.0, "TestShop", "Groceries", merchant="TestShop")
        from expense_tracker_agent.db import find_parent_expense
        from datetime import date as _date
        today = _date.today().isoformat()
        parent_id = find_parent_expense("TestShop", today)
        self.assertIsNotNone(parent_id)
        result = list_expense_items(parent_id)
        self.assertIn("no items", result.lower())


class TestImportCsvRow(BaseToolsTest):
    def test_inserts_new_row(self):
        result = import_csv_row("2026-05-01", 15.0, "Edeka")
        self.assertIn("imported", result.lower())

    def test_skips_duplicate(self):
        import_csv_row("2026-05-01", 15.0, "Edeka")
        result = import_csv_row("2026-05-01", 15.0, "Edeka")
        self.assertIn("skipped", result.lower())


class TestCategoriesIncludesAlcohol(unittest.TestCase):
    def test_alcohol_in_categories(self):
        self.assertIn("Alcohol", CATEGORIES)
```

- [ ] **Step 2: Run tests to verify the new test classes fail**

```bash
python -m pytest test_tools.py -v -k "TestAddExpenseItem or TestListExpenseItems or TestImportCsvRow or TestCategoriesIncludesAlcohol" 2>&1 | head -30
```

Expected: ImportError or AttributeError on the new functions.

- [ ] **Step 3: Rewrite `expense_tracker_agent/tools.py`**

```python
# expense_tracker_agent/tools.py
from datetime import date as _date
from typing import Optional

from expense_tracker_agent.db import (
    fetch_expenses,
    fetch_expense_items,
    find_parent_expense,
    init_db,
    insert_expense,
    insert_expense_item,
    expense_exists,
)

CATEGORIES = [
    "Food", "Groceries", "Transport", "Entertainment",
    "Bills", "Healthcare", "Shopping", "Alcohol", "Other",
]

init_db()


def add_expense(
    amount: float,
    description: str,
    category: str,
    merchant: Optional[str] = None,
    date: Optional[str] = None,
) -> str:
    """
    Adds an expense to the tracker.

    Args:
        amount: The numerical amount of the expense.
        description: A brief description of the expense.
        category: The category (must be one of CATEGORIES).
        merchant: Optional merchant or store name.
        date: ISO date YYYY-MM-DD; defaults to today.

    Returns:
        A confirmation message including the assigned expense id.
    """
    resolved_date = date or _date.today().isoformat()
    eid = insert_expense(
        amount=amount,
        category=category,
        description=description,
        merchant=merchant,
        date=resolved_date,
        source="ai_chat",
    )
    return f"Added expense #{eid}: {description} — €{amount:.2f} [{category}] on {resolved_date}"


def add_expense_item(
    parent_id: int,
    amount: float,
    description: str,
    category: str,
) -> str:
    """
    Adds a sub-item to an existing parent expense.

    Args:
        parent_id: The id of the parent expense (from add_expense).
        amount: The numerical amount of the sub-item.
        description: A brief description (e.g. 'beer').
        category: The category of the sub-item.

    Returns:
        A confirmation message.
    """
    existing = fetch_expenses()
    ids = {e["id"] for e in existing}
    if parent_id not in ids:
        return f"Error: expense #{parent_id} not found."
    iid = insert_expense_item(parent_id, amount, description, category)
    return f"Added item #{iid}: {description} — €{amount:.2f} [{category}] under expense #{parent_id}"


def list_expense_items(parent_id: int) -> str:
    """
    Lists all sub-items for a parent expense.

    Args:
        parent_id: The id of the parent expense.

    Returns:
        A formatted list of sub-items.
    """
    items = fetch_expense_items(parent_id)
    if not items:
        return f"No items found for expense #{parent_id}."
    lines = [f"Items for expense #{parent_id}:"]
    for it in items:
        lines.append(f"  - {it['description']} ({it['category']}): €{it['amount']:.2f}")
    return "\n".join(lines)


def find_parent_expense_id(merchant: str, date: str) -> str:
    """
    Finds an existing parent expense by merchant and date.

    Args:
        merchant: The store or restaurant name.
        date: ISO date YYYY-MM-DD.

    Returns:
        The parent expense id as a string, or 'not found'.
    """
    from expense_tracker_agent.db import find_parent_expense
    eid = find_parent_expense(merchant, date)
    if eid is None:
        return f"not found"
    return str(eid)


def import_csv_row(date: str, amount: float, merchant: str) -> str:
    """
    Imports a single row from a CSV file, skipping duplicates.

    Args:
        date: ISO date YYYY-MM-DD.
        amount: The expense amount.
        merchant: The supermarket or store name.

    Returns:
        'Imported' or 'Skipped (duplicate)' message.
    """
    if expense_exists(date, merchant, amount):
        return f"Skipped (duplicate): {merchant} €{amount:.2f} on {date}"
    insert_expense(
        amount=amount,
        category="Groceries",
        description=f"Import: {merchant}",
        merchant=merchant,
        date=date,
        source="csv_import",
    )
    return f"Imported: {merchant} €{amount:.2f} on {date}"


def calculate_total_spending(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    Calculates total spending, optionally within a date range.

    Args:
        start_date: ISO date inclusive lower bound.
        end_date: ISO date inclusive upper bound.

    Returns:
        A string with the total spending.
    """
    rows = fetch_expenses(start_date, end_date)
    total = sum(r["amount"] for r in rows)
    return f"Total spending: €{total:.2f}"


def get_spending_by_category(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    Gets spending per category, optionally within a date range.

    Args:
        start_date: ISO date inclusive lower bound.
        end_date: ISO date inclusive upper bound.

    Returns:
        A string with spending per category.
    """
    rows = fetch_expenses(start_date, end_date)
    if not rows:
        return "No spending to report."
    totals: dict[str, float] = {}
    for r in rows:
        totals[r["category"]] = totals.get(r["category"], 0) + r["amount"]
    lines = ["Spending by category:"]
    for cat, amt in sorted(totals.items(), key=lambda x: -x[1]):
        lines.append(f"  - {cat}: €{amt:.2f}")
    return "\n".join(lines)


def list_recent_expenses(count: int = 5, category: Optional[str] = None) -> str:
    """
    Lists the most recent expenses.

    Args:
        count: Number of expenses to return.
        category: Optional case-insensitive category filter.

    Returns:
        A formatted string of recent expenses.
    """
    rows = fetch_expenses()
    if category:
        rows = [r for r in rows if r["category"].lower() == category.lower()]
    if not rows:
        return "No expenses to report."
    recent = rows[-count:]
    lines = ["Recent expenses:"]
    for r in recent:
        lines.append(f"  - {r['description']} ({r['category']}): €{r['amount']:.2f} on {r['date']}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run all tools tests**

```bash
python -m pytest test_tools.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add expense_tracker_agent/tools.py test_tools.py
git commit -m "feat: migrate tools.py to SQLite, add Alcohol category and new agent tools"
```

---

## Task 3: Update agent.py

**Files:**
- Modify: `expense_tracker_agent/agent.py`

- [ ] **Step 1: Update `agent.py` with new tools and instruction**

```python
# expense_tracker_agent/agent.py
from datetime import date

from google.adk.agents import Agent
from google.adk.models import Gemini

from expense_tracker_agent.tools import (
    CATEGORIES,
    add_expense,
    add_expense_item,
    calculate_total_spending,
    find_parent_expense_id,
    get_spending_by_category,
    import_csv_row,
    list_expense_items,
    list_recent_expenses,
)


def _build_instruction(today: str) -> str:
    categories_str = ", ".join(CATEGORIES)
    return (
        f"You are an expense tracking agent. Today's date is {today}.\n"
        "Use the tools to log user expenses, calculate total spending, "
        "get spending by category, and list recent expenses.\n\n"
        "## Adding expenses\n"
        "When the user describes an expense, extract all fields from their message:\n"
        "- amount: the number (required)\n"
        "- description: a short label for the expense (required)\n"
        "- merchant: the store or restaurant name if mentioned (optional)\n"
        f"- category: infer from the description using the rules below (required)\n"
        "- date: resolve relative dates like 'yesterday' or 'last Monday' to "
        f"YYYY-MM-DD using today ({today}) as reference; default to today if omitted\n\n"
        "## Sub-items\n"
        "If the user says something like '3 euro beer, part of today's Edeka shop', "
        "call find_parent_expense_id(merchant, date) first. "
        "If it returns a number, use that as parent_id for add_expense_item(parent_id, amount, description, category). "
        "If it returns 'not found', call add_expense() to create the parent first, then add_expense_item().\n\n"
        f"## Category inference rules\n"
        f"Always assign one of: {categories_str}.\n"
        "Rules:\n"
        "- grocery stores, supermarkets → Groceries\n"
        "- restaurants, cafes, fast food → Food\n"
        "- Uber, taxi, fuel, bus, train, metro → Transport\n"
        "- Netflix, cinema, games, concerts, events → Entertainment\n"
        "- electricity, gas, internet, rent, insurance → Bills\n"
        "- pharmacy, doctor, hospital, dentist → Healthcare\n"
        "- clothing, electronics, Amazon, online shopping → Shopping\n"
        "- beer, wine, spirits, cocktails, alcohol → Alcohol\n"
        "- anything else → Other\n\n"
        "If the user does not provide the amount, ask for it before calling add_expense. "
        "Never ask for the category — infer it yourself. "
        "Never ask for merchant or date — extract them from context or omit them."
    )


root_agent = Agent(
    name="expense_tracker",
    model=Gemini(model="gemini-2.5-flash"),
    instruction=_build_instruction(today=date.today().isoformat()),
    tools=[
        add_expense,
        add_expense_item,
        find_parent_expense_id,
        list_expense_items,
        calculate_total_spending,
        get_spending_by_category,
        list_recent_expenses,
        import_csv_row,
    ],
)
```

- [ ] **Step 2: Run existing agent tests**

```bash
python -m pytest test_agent.py -v
```

Expected: all tests PASS (agent tests mock Gemini, so tool additions don't break them).

- [ ] **Step 3: Commit**

```bash
git add expense_tracker_agent/agent.py
git commit -m "feat: register new agent tools and add Alcohol category rule to instruction"
```

---

## Task 4: Dash App Shell + Dependencies

**Files:**
- Modify: `pyproject.toml`
- Create: `app.py`
- Create: `pages/__init__.py`

- [ ] **Step 1: Update `pyproject.toml`**

```toml
[project]
name = "expense-tracker-agent"
version = "0.2.0"
description = "An expense tracking agent with Dash dashboard."
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
    "google-adk",
    "pydantic",
    "uvicorn",
    "google-generativeai",
    "dash>=2.14",
    "dash-bootstrap-components>=1.5",
    "plotly>=5.18",
    "pandas>=2.0",
]

[tool.setuptools.packages]
find = {}
```

- [ ] **Step 2: Install new dependencies**

```bash
pip install "dash>=2.14" "dash-bootstrap-components>=1.5" "plotly>=5.18" "pandas>=2.0"
```

Expected: packages install without errors.

- [ ] **Step 3: Create `pages/__init__.py`**

```python
# pages/__init__.py
```

- [ ] **Step 4: Create `app.py`**

```python
# app.py
import dash
import dash_bootstrap_components as dbc
from dash import html

from expense_tracker_agent.db import DB_PATH, init_db, migrate_from_csv
from pathlib import Path

# Ensure DB is ready and migrate any existing CSV data
init_db()
migrate_from_csv(Path("expenses.csv"))

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
)

navbar = dbc.Navbar(
    dbc.Container(
        [
            dbc.NavbarBrand("ExpenseAI", href="/", className="fw-bold"),
            dbc.Nav(
                [
                    dbc.NavLink("Dashboard", href="/", active="exact"),
                    dbc.NavLink("Add Expense", href="/add", active="exact"),
                    dbc.NavLink("Import CSV", href="/import", active="exact"),
                    dbc.NavLink("Scan Receipt", href="/scan", active="exact"),
                ],
                navbar=True,
                className="ms-auto",
            ),
        ],
        fluid=True,
    ),
    color="white",
    className="border-bottom mb-4 shadow-sm",
    light=True,
)

app.layout = html.Div(
    [
        navbar,
        dbc.Container(dash.page_container, fluid=False, className="pb-5"),
    ]
)

if __name__ == "__main__":
    app.run(debug=True, port=8050)
```

- [ ] **Step 5: Verify app starts**

```bash
python app.py
```

Expected: `Dash is running on http://127.0.0.1:8050/` — no import errors, blank page is fine.

Stop with Ctrl+C.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml app.py pages/__init__.py
git commit -m "feat: add Dash app shell with navbar and multi-page routing"
```

---

## Task 5: Dashboard Page

**Files:**
- Create: `charts.py`
- Create: `pages/dashboard.py`
- Create: `tests/test_charts.py`

- [ ] **Step 1: Write failing tests for chart data functions**

```python
# tests/test_charts.py
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import expense_tracker_agent.db as db_module
from expense_tracker_agent.db import init_db, insert_expense, insert_expense_item
from charts import (
    kpi_stats,
    monthly_trend_data,
    category_breakdown_data,
    weekly_bar_data,
    top_merchants_data,
    sub_expense_breakdown_data,
    heatmap_data,
)


def _temp_db() -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    os.unlink(f.name)
    return Path(f.name)


class BaseChartsTest(unittest.TestCase):
    def setUp(self):
        self.tmp_db = _temp_db()
        self.patcher = patch.object(db_module, "DB_PATH", self.tmp_db)
        self.patcher.start()
        init_db()

    def tearDown(self):
        self.patcher.stop()
        if self.tmp_db.exists():
            self.tmp_db.unlink()


class TestKpiStats(BaseChartsTest):
    def test_returns_zeros_with_no_data(self):
        stats = kpi_stats("2026-06-01", "2026-06-30")
        self.assertEqual(stats["total"], 0.0)
        self.assertEqual(stats["count"], 0)
        self.assertEqual(stats["avg_per_day"], 0.0)

    def test_counts_correctly(self):
        insert_expense(10.0, "Food", "lunch", date="2026-06-05")
        insert_expense(20.0, "Food", "dinner", date="2026-06-05")
        stats = kpi_stats("2026-06-01", "2026-06-30")
        self.assertAlmostEqual(stats["total"], 30.0)
        self.assertEqual(stats["count"], 2)


class TestMonthlyTrendData(BaseChartsTest):
    def test_groups_by_month(self):
        insert_expense(10.0, "Food", "a", date="2026-05-10")
        insert_expense(20.0, "Food", "b", date="2026-06-05")
        df = monthly_trend_data()
        self.assertIn("month", df.columns)
        self.assertIn("total", df.columns)
        self.assertEqual(len(df), 2)


class TestCategoryBreakdownData(BaseChartsTest):
    def test_groups_by_category(self):
        insert_expense(10.0, "Food", "lunch", date="2026-06-01")
        insert_expense(20.0, "Groceries", "shop", date="2026-06-01")
        df = category_breakdown_data("2026-06-01", "2026-06-30")
        self.assertIn("category", df.columns)
        self.assertIn("total", df.columns)
        cats = list(df["category"])
        self.assertIn("Food", cats)
        self.assertIn("Groceries", cats)


class TestTopMerchantsData(BaseChartsTest):
    def test_ranks_by_total(self):
        insert_expense(50.0, "Groceries", "big shop", merchant="Edeka", date="2026-06-01")
        insert_expense(10.0, "Groceries", "small shop", merchant="Rewe", date="2026-06-02")
        df = top_merchants_data("2026-06-01", "2026-06-30")
        self.assertEqual(df.iloc[0]["merchant"], "Edeka")

    def test_excludes_null_merchants(self):
        insert_expense(10.0, "Food", "no merchant")
        df = top_merchants_data("2026-01-01", "2026-12-31")
        self.assertEqual(len(df), 0)


class TestSubExpenseBreakdownData(BaseChartsTest):
    def test_only_includes_merchants_with_items(self):
        eid = insert_expense(10.0, "Groceries", "shop", merchant="Edeka", date="2026-06-01")
        insert_expense_item(eid, 3.0, "beer", "Alcohol")
        insert_expense(5.0, "Food", "lunch", merchant="Bistro", date="2026-06-01")
        df = sub_expense_breakdown_data("2026-06-01", "2026-06-30")
        merchants = list(df["merchant"].unique())
        self.assertIn("Edeka", merchants)
        self.assertNotIn("Bistro", merchants)


class TestHeatmapData(BaseChartsTest):
    def test_sums_by_date(self):
        insert_expense(10.0, "Food", "a", date="2026-06-01")
        insert_expense(5.0, "Food", "b", date="2026-06-01")
        insert_expense(20.0, "Food", "c", date="2026-06-02")
        df = heatmap_data("2026-06-01", "2026-06-30")
        june1 = df[df["date"] == "2026-06-01"]["total"].values[0]
        self.assertAlmostEqual(june1, 15.0)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_charts.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'charts'`

- [ ] **Step 3: Create `charts.py`**

```python
# charts.py
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.graph_objects import Figure

from expense_tracker_agent.db import fetch_expenses, fetch_expense_items


def kpi_stats(start_date: str, end_date: str) -> dict:
    rows = fetch_expenses(start_date, end_date)
    total = sum(r["amount"] for r in rows)
    count = len(rows)
    if rows:
        dates = sorted({r["date"] for r in rows})
        days = max(len(dates), 1)
        avg = total / days
    else:
        avg = 0.0
    return {"total": total, "count": count, "avg_per_day": avg}


def monthly_trend_data() -> pd.DataFrame:
    rows = fetch_expenses()
    if not rows:
        return pd.DataFrame(columns=["month", "total"])
    df = pd.DataFrame(rows)
    df["month"] = pd.to_datetime(df["date"]).dt.to_period("M").astype(str)
    return df.groupby("month")["amount"].sum().reset_index().rename(columns={"amount": "total"})


def category_breakdown_data(start_date: str, end_date: str) -> pd.DataFrame:
    rows = fetch_expenses(start_date, end_date)
    if not rows:
        return pd.DataFrame(columns=["category", "total"])
    df = pd.DataFrame(rows)
    return df.groupby("category")["amount"].sum().reset_index().rename(columns={"amount": "total"})


def weekly_bar_data(start_date: str, end_date: str) -> pd.DataFrame:
    rows = fetch_expenses(start_date, end_date)
    if not rows:
        return pd.DataFrame(columns=["week", "total"])
    df = pd.DataFrame(rows)
    df["week"] = pd.to_datetime(df["date"]).dt.to_period("W").astype(str)
    return df.groupby("week")["amount"].sum().reset_index().rename(columns={"amount": "total"})


def top_merchants_data(start_date: str, end_date: str, n: int = 10) -> pd.DataFrame:
    rows = fetch_expenses(start_date, end_date)
    if not rows:
        return pd.DataFrame(columns=["merchant", "total"])
    df = pd.DataFrame(rows)
    df = df[df["merchant"].notna() & (df["merchant"] != "")]
    if df.empty:
        return pd.DataFrame(columns=["merchant", "total"])
    result = (
        df.groupby("merchant")["amount"].sum()
        .reset_index()
        .rename(columns={"amount": "total"})
        .sort_values("total", ascending=False)
        .head(n)
    )
    return result


def sub_expense_breakdown_data(start_date: str, end_date: str) -> pd.DataFrame:
    expenses = fetch_expenses(start_date, end_date)
    rows = []
    for exp in expenses:
        if not exp["merchant"]:
            continue
        items = fetch_expense_items(exp["id"])
        for item in items:
            rows.append({
                "merchant": exp["merchant"],
                "category": item["category"],
                "amount": item["amount"],
            })
    if not rows:
        return pd.DataFrame(columns=["merchant", "category", "amount"])
    return pd.DataFrame(rows)


def heatmap_data(start_date: str, end_date: str) -> pd.DataFrame:
    rows = fetch_expenses(start_date, end_date)
    if not rows:
        return pd.DataFrame(columns=["date", "total"])
    df = pd.DataFrame(rows)
    return df.groupby("date")["amount"].sum().reset_index().rename(columns={"amount": "total"})


# --- Figure builders ---

def fig_monthly_trend() -> Figure:
    df = monthly_trend_data()
    if df.empty:
        return go.Figure().add_annotation(text="No data yet", showarrow=False)
    return px.line(df, x="month", y="total", markers=True,
                   labels={"month": "Month", "total": "€ Spent"},
                   title="Monthly Spending Trend")


def fig_category_donut(start_date: str, end_date: str) -> Figure:
    df = category_breakdown_data(start_date, end_date)
    if df.empty:
        return go.Figure().add_annotation(text="No data yet", showarrow=False)
    return px.pie(df, names="category", values="total", hole=0.45,
                  title="Spending by Category")


def fig_weekly_bar(start_date: str, end_date: str) -> Figure:
    df = weekly_bar_data(start_date, end_date)
    if df.empty:
        return go.Figure().add_annotation(text="No data yet", showarrow=False)
    return px.bar(df, x="week", y="total",
                  labels={"week": "Week", "total": "€ Spent"},
                  title="Weekly Spending")


def fig_top_merchants(start_date: str, end_date: str) -> Figure:
    df = top_merchants_data(start_date, end_date)
    if df.empty:
        return go.Figure().add_annotation(text="No data yet", showarrow=False)
    return px.bar(df.sort_values("total"), x="total", y="merchant",
                  orientation="h",
                  labels={"total": "€ Spent", "merchant": ""},
                  title="Top Merchants")


def fig_sub_expense_breakdown(start_date: str, end_date: str) -> Figure:
    df = sub_expense_breakdown_data(start_date, end_date)
    if df.empty:
        return go.Figure().add_annotation(text="No receipt data yet", showarrow=False)
    return px.bar(df, x="merchant", y="amount", color="category",
                  title="Sub-expense Breakdown by Store",
                  labels={"amount": "€", "merchant": "Store"})


def fig_heatmap(start_date: str, end_date: str) -> Figure:
    df = heatmap_data(start_date, end_date)
    if df.empty:
        return go.Figure().add_annotation(text="No data yet", showarrow=False)
    df["date_obj"] = pd.to_datetime(df["date"])
    df["weekday"] = df["date_obj"].dt.day_name()
    df["week"] = df["date_obj"].dt.isocalendar().week.astype(str)
    pivot = df.pivot_table(index="weekday", columns="week", values="total", aggfunc="sum")
    day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    pivot = pivot.reindex([d for d in day_order if d in pivot.index])
    return px.imshow(pivot, color_continuous_scale="Blues",
                     title="Daily Spending Heatmap",
                     labels={"color": "€ Spent"})
```

- [ ] **Step 4: Run chart tests**

```bash
python -m pytest tests/test_charts.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Create `pages/dashboard.py`**

```python
# pages/dashboard.py
from datetime import date, timedelta

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html

import charts

dash.register_page(__name__, path="/", name="Dashboard")

_PERIODS = {
    "this_month": "This Month",
    "last_month": "Last Month",
    "last_3_months": "Last 3 Months",
}


def _date_range(period: str) -> tuple[str, str]:
    today = date.today()
    if period == "this_month":
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat()
    if period == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        start = last_prev.replace(day=1)
        return start.isoformat(), last_prev.isoformat()
    # last_3_months
    start = (today - timedelta(days=90)).replace(day=1)
    return start.isoformat(), today.isoformat()


layout = html.Div([
    dbc.Row([
        dbc.Col(
            dbc.Select(
                id="period-select",
                options=[{"label": v, "value": k} for k, v in _PERIODS.items()],
                value="this_month",
                style={"maxWidth": "200px"},
            ),
            width="auto",
        ),
    ], className="mb-4"),

    # KPI cards
    dbc.Row(id="kpi-cards", className="mb-4 g-3"),

    # Charts row 1
    dbc.Row([
        dbc.Col(dcc.Graph(id="chart-trend"), md=8),
        dbc.Col(dcc.Graph(id="chart-donut"), md=4),
    ], className="mb-3"),

    # Charts row 2
    dbc.Row([
        dbc.Col(dcc.Graph(id="chart-weekly"), md=6),
        dbc.Col(dcc.Graph(id="chart-merchants"), md=6),
    ], className="mb-3"),

    # Charts row 3
    dbc.Row([
        dbc.Col(dcc.Graph(id="chart-sub-breakdown"), md=6),
        dbc.Col(dcc.Graph(id="chart-heatmap"), md=6),
    ]),
])


@callback(
    Output("kpi-cards", "children"),
    Output("chart-trend", "figure"),
    Output("chart-donut", "figure"),
    Output("chart-weekly", "figure"),
    Output("chart-merchants", "figure"),
    Output("chart-sub-breakdown", "figure"),
    Output("chart-heatmap", "figure"),
    Input("period-select", "value"),
)
def update_dashboard(period: str):
    start, end = _date_range(period)
    stats = charts.kpi_stats(start, end)

    kpi_cards = [
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("Total Spent", className="text-muted small mb-1"),
            html.H3(f"€{stats['total']:.2f}", className="mb-0"),
        ])), md=4),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("Transactions", className="text-muted small mb-1"),
            html.H3(str(stats["count"]), className="mb-0"),
        ])), md=4),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("Avg / Day", className="text-muted small mb-1"),
            html.H3(f"€{stats['avg_per_day']:.2f}", className="mb-0"),
        ])), md=4),
    ]

    return (
        kpi_cards,
        charts.fig_monthly_trend(),
        charts.fig_category_donut(start, end),
        charts.fig_weekly_bar(start, end),
        charts.fig_top_merchants(start, end),
        charts.fig_sub_expense_breakdown(start, end),
        charts.fig_heatmap(start, end),
    )
```

- [ ] **Step 6: Verify dashboard renders**

```bash
python app.py
```

Open `http://localhost:8050` — dashboard loads with KPI cards and 6 chart placeholders ("No data yet"). Stop with Ctrl+C.

- [ ] **Step 7: Commit**

```bash
git add charts.py pages/dashboard.py tests/test_charts.py
git commit -m "feat: add dashboard page with 6 charts and KPI cards"
```

---

## Task 6: Add Expense Page (Agent Chat)

**Files:**
- Create: `agent_bridge.py`
- Create: `pages/add_expense.py`

- [ ] **Step 1: Create `agent_bridge.py`**

This wraps the async ADK agent in a thread-safe sync interface for Dash callbacks.

```python
# agent_bridge.py
import asyncio
import threading
from typing import Optional

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from expense_tracker_agent.agent import root_agent

_APP_NAME = "expense_tracker_dash"
_USER_ID = "dash_user"
_SESSION_ID = "dash_session"

_loop: Optional[asyncio.AbstractEventLoop] = None
_runner: Optional[Runner] = None
_lock = threading.Lock()


def _get_runner() -> Runner:
    global _runner
    if _runner is None:
        session_service = InMemorySessionService()
        _runner = Runner(
            agent=root_agent,
            app_name=_APP_NAME,
            session_service=session_service,
        )
    return _runner


def _get_loop() -> asyncio.AbstractEventLoop:
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        t = threading.Thread(target=_loop.run_forever, daemon=True)
        t.start()
    return _loop


async def _ensure_session(runner: Runner) -> None:
    existing = await runner.session_service.get_session(
        app_name=_APP_NAME, user_id=_USER_ID, session_id=_SESSION_ID
    )
    if existing is None:
        await runner.session_service.create_session(
            app_name=_APP_NAME, user_id=_USER_ID, session_id=_SESSION_ID
        )


async def _send_message(message: str) -> str:
    from google.genai.types import Content, Part
    runner = _get_runner()
    await _ensure_session(runner)
    content = Content(role="user", parts=[Part(text=message)])
    response_text = ""
    async for event in runner.run_async(
        user_id=_USER_ID,
        session_id=_SESSION_ID,
        new_message=content,
    ):
        if hasattr(event, "content") and event.content:
            for part in event.content.parts:
                if hasattr(part, "text") and part.text:
                    response_text += part.text
    return response_text or "Done."


def chat(message: str) -> str:
    with _lock:
        loop = _get_loop()
        future = asyncio.run_coroutine_threadsafe(_send_message(message), loop)
        return future.result(timeout=60)
```

- [ ] **Step 2: Create `pages/add_expense.py`**

```python
# pages/add_expense.py
import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html

import agent_bridge
from expense_tracker_agent.db import fetch_expenses

dash.register_page(__name__, path="/add", name="Add Expense")

layout = dbc.Row([
    # Left: chat panel
    dbc.Col([
        html.H5("Chat with your expense agent", className="mb-3"),
        html.Div(id="chat-history", style={
            "height": "420px", "overflowY": "auto",
            "border": "1px solid #e9ecef", "borderRadius": "8px",
            "padding": "12px", "background": "#fafafa",
            "marginBottom": "12px",
        }),
        dbc.InputGroup([
            dbc.Input(
                id="chat-input",
                placeholder='e.g. "10 euro at Edeka today" or "3 euro beer, part of Edeka shop"',
                type="text",
                debounce=False,
            ),
            dbc.Button("Send", id="chat-send", color="primary", n_clicks=0),
        ]),
        dcc.Store(id="chat-messages", data=[]),
    ], md=7),

    # Right: recent expenses
    dbc.Col([
        html.H5("Recent expenses", className="mb-3"),
        html.Div(id="recent-expenses-list"),
    ], md=5),
])


@callback(
    Output("chat-history", "children"),
    Output("chat-messages", "data"),
    Output("chat-input", "value"),
    Output("recent-expenses-list", "children"),
    Input("chat-send", "n_clicks"),
    Input("chat-input", "n_submit"),
    State("chat-input", "value"),
    State("chat-messages", "data"),
    prevent_initial_call=True,
)
def handle_chat(n_clicks, n_submit, user_input, messages):
    if not user_input or not user_input.strip():
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    response = agent_bridge.chat(user_input.strip())
    messages = messages + [
        {"role": "user", "text": user_input.strip()},
        {"role": "agent", "text": response},
    ]

    bubbles = []
    for msg in messages:
        is_user = msg["role"] == "user"
        bubbles.append(
            html.Div(msg["text"], style={
                "background": "#0d6efd" if is_user else "#e9ecef",
                "color": "white" if is_user else "#333",
                "padding": "8px 12px",
                "borderRadius": "12px",
                "marginBottom": "8px",
                "maxWidth": "85%",
                "marginLeft": "auto" if is_user else "0",
                "fontSize": "14px",
            })
        )

    recent = fetch_expenses()[-8:][::-1]
    recent_items = [
        dbc.ListGroupItem(
            [
                html.Span(r["description"], className="fw-semibold"),
                html.Span(f" — €{r['amount']:.2f}", className="text-muted"),
                html.Br(),
                html.Small(f"{r['date']} · {r['category']}", className="text-muted"),
            ]
        )
        for r in recent
    ]
    recent_list = dbc.ListGroup(recent_items) if recent_items else html.P("No expenses yet.", className="text-muted")

    return bubbles, messages, "", recent_list
```

- [ ] **Step 3: Verify chat page renders**

```bash
python app.py
```

Open `http://localhost:8050/add` — chat panel and recent list render. Type a test message like "5 euro coffee" and verify a response appears. Stop with Ctrl+C.

- [ ] **Step 4: Commit**

```bash
git add agent_bridge.py pages/add_expense.py
git commit -m "feat: add expense chat page with ADK agent bridge"
```

---

## Task 7: CSV Import Page

**Files:**
- Create: `pages/import_csv.py`

- [ ] **Step 1: Create `pages/import_csv.py`**

```python
# pages/import_csv.py
import base64
import io

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, State, callback, dash_table, dcc, html

from expense_tracker_agent.tools import import_csv_row

dash.register_page(__name__, path="/import", name="Import CSV")

_KNOWN_DATE_COLS = {"date", "datum", "day"}
_KNOWN_COST_COLS = {"cost", "amount", "price", "kosten", "betrag", "preis"}
_KNOWN_MERCHANT_COLS = {"supermarket name", "supermarket", "merchant", "store",
                        "shop", "markt", "laden"}

layout = html.Div([
    html.H5("Import CSV", className="mb-3"),
    html.P(
        "Upload a CSV with columns for date, cost, and supermarket name. "
        "Column names are detected automatically.",
        className="text-muted mb-4",
    ),
    dcc.Upload(
        id="csv-upload",
        children=html.Div([
            "Drag & drop or ", html.A("browse"),
        ]),
        style={
            "width": "100%", "height": "80px", "lineHeight": "80px",
            "borderWidth": "1px", "borderStyle": "dashed",
            "borderRadius": "8px", "textAlign": "center",
            "color": "#6c757d",
        },
        accept=".csv",
    ),
    html.Div(id="csv-preview-section", className="mt-4"),
    html.Div(id="csv-import-result", className="mt-3"),
])


def _detect_columns(columns: list[str]) -> dict:
    mapping = {}
    lower = {c.lower(): c for c in columns}
    for key in lower:
        if key in _KNOWN_DATE_COLS:
            mapping["date"] = lower[key]
        elif key in _KNOWN_COST_COLS:
            mapping["cost"] = lower[key]
        elif key in _KNOWN_MERCHANT_COLS:
            mapping["merchant"] = lower[key]
    return mapping


@callback(
    Output("csv-preview-section", "children"),
    Input("csv-upload", "contents"),
    State("csv-upload", "filename"),
    prevent_initial_call=True,
)
def show_preview(contents, filename):
    if contents is None:
        return dash.no_update
    _, b64 = contents.split(",", 1)
    decoded = base64.b64decode(b64).decode("utf-8")
    try:
        df = pd.read_csv(io.StringIO(decoded))
    except Exception as e:
        return dbc.Alert(f"Could not parse CSV: {e}", color="danger")

    mapping = _detect_columns(list(df.columns))
    missing = [k for k in ("date", "cost", "merchant") if k not in mapping]

    col_selectors = []
    for role in ("date", "cost", "merchant"):
        col_selectors.append(
            dbc.Col([
                html.Label(role.capitalize(), className="small fw-semibold"),
                dbc.Select(
                    id=f"col-{role}",
                    options=[{"label": c, "value": c} for c in df.columns],
                    value=mapping.get(role),
                ),
            ], md=4)
        )

    preview_table = dash_table.DataTable(
        data=df.head(10).to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        style_table={"overflowX": "auto"},
        style_cell={"fontSize": "13px", "padding": "6px"},
        page_size=10,
    )

    return html.Div([
        html.H6(f"Preview: {filename}", className="mb-2"),
        preview_table,
        html.Hr(),
        html.P("Map columns (auto-detected, adjust if needed):", className="mb-2 fw-semibold"),
        dbc.Row(col_selectors, className="mb-3"),
        dbc.Button(
            f"Import {len(df)} rows",
            id="import-confirm-btn",
            color="primary",
            n_clicks=0,
        ),
        dcc.Store(id="csv-data-store", data=df.to_json(orient="records")),
    ])


@callback(
    Output("csv-import-result", "children"),
    Input("import-confirm-btn", "n_clicks"),
    State("csv-data-store", "data"),
    State("col-date", "value"),
    State("col-cost", "value"),
    State("col-merchant", "value"),
    prevent_initial_call=True,
)
def run_import(n_clicks, json_data, date_col, cost_col, merchant_col):
    if not n_clicks or not json_data:
        return dash.no_update
    if not all([date_col, cost_col, merchant_col]):
        return dbc.Alert("Please map all three columns before importing.", color="warning")

    df = pd.read_json(io.StringIO(json_data), orient="records")
    imported, skipped, errors = 0, 0, 0
    for _, row in df.iterrows():
        try:
            result = import_csv_row(
                date=str(row[date_col])[:10],
                amount=float(row[cost_col]),
                merchant=str(row[merchant_col]),
            )
            if "skipped" in result.lower():
                skipped += 1
            else:
                imported += 1
        except Exception:
            errors += 1

    return dbc.Alert(
        f"Done — {imported} imported, {skipped} skipped (duplicates), {errors} errors.",
        color="success" if errors == 0 else "warning",
    )
```

- [ ] **Step 2: Verify import page renders**

```bash
python app.py
```

Open `http://localhost:8050/import` — upload area renders. Upload a CSV with columns `date,cost,supermarket name` and 3 rows. Verify preview shows, import button triggers result message. Stop with Ctrl+C.

- [ ] **Step 3: Commit**

```bash
git add pages/import_csv.py
git commit -m "feat: add CSV import page with column mapping and duplicate detection"
```

---

## Task 8: Receipt Scanner

**Files:**
- Create: `expense_tracker_agent/receipt_scanner.py`
- Create: `tests/test_receipt_scanner.py`
- Create: `pages/scan_receipt.py`

- [ ] **Step 1: Write failing tests for receipt_scanner.py**

```python
# tests/test_receipt_scanner.py
import unittest
from unittest.mock import MagicMock, patch

from expense_tracker_agent.receipt_scanner import parse_receipt, ReceiptData, ReceiptItem


class TestReceiptDataModel(unittest.TestCase):
    def test_receipt_data_has_required_fields(self):
        r = ReceiptData(
            merchant="Edeka",
            date="2026-06-01",
            total=15.0,
            items=[ReceiptItem(description="beer", amount=3.0, category="Alcohol")],
        )
        self.assertEqual(r.merchant, "Edeka")
        self.assertEqual(len(r.items), 1)


class TestParseReceipt(unittest.TestCase):
    @patch("expense_tracker_agent.receipt_scanner.genai")
    def test_returns_receipt_data_on_success(self, mock_genai):
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        mock_response = MagicMock()
        mock_response.text = '{"merchant":"Edeka","date":"2026-06-01","total":10.0,"items":[{"description":"beer","amount":3.0,"category":"Alcohol"},{"description":"bread","amount":7.0,"category":"Groceries"}]}'
        mock_model.generate_content.return_value = mock_response

        result = parse_receipt(b"fake_image_bytes")

        self.assertIsInstance(result, ReceiptData)
        self.assertEqual(result.merchant, "Edeka")
        self.assertEqual(len(result.items), 2)
        self.assertAlmostEqual(result.total, 10.0)

    @patch("expense_tracker_agent.receipt_scanner.genai")
    def test_returns_none_on_invalid_json(self, mock_genai):
        mock_model = MagicMock()
        mock_genai.GenerativeModel.return_value = mock_model
        mock_response = MagicMock()
        mock_response.text = "Sorry, I cannot read this image."
        mock_model.generate_content.return_value = mock_response

        result = parse_receipt(b"bad_image")
        self.assertIsNone(result)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_receipt_scanner.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'expense_tracker_agent.receipt_scanner'`

- [ ] **Step 3: Create `expense_tracker_agent/receipt_scanner.py`**

```python
# expense_tracker_agent/receipt_scanner.py
import json
import re
from dataclasses import dataclass, field
from typing import Optional

import google.generativeai as genai

from expense_tracker_agent.tools import CATEGORIES

_PROMPT = """
You are a receipt parser. Analyse this receipt image and return ONLY valid JSON with this structure:
{
  "merchant": "store name",
  "date": "YYYY-MM-DD",
  "total": 0.00,
  "items": [
    {"description": "item name", "amount": 0.00, "category": "one of CATEGORIES"}
  ]
}

Categories allowed: CATEGORY_LIST

Rules:
- date must be YYYY-MM-DD; use today if unclear
- amounts in euros as floats
- category must be exactly one of the allowed values
- return ONLY the JSON object, no markdown fences
""".replace("CATEGORY_LIST", ", ".join(CATEGORIES))


@dataclass
class ReceiptItem:
    description: str
    amount: float
    category: str


@dataclass
class ReceiptData:
    merchant: str
    date: str
    total: float
    items: list[ReceiptItem] = field(default_factory=list)


def parse_receipt(image_bytes: bytes, mime_type: str = "image/jpeg") -> Optional[ReceiptData]:
    model = genai.GenerativeModel("gemini-2.5-flash")
    image_part = {"mime_type": mime_type, "data": image_bytes}
    response = model.generate_content([_PROMPT, image_part])
    raw = response.text.strip()
    # strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        items = [
            ReceiptItem(
                description=it["description"],
                amount=float(it["amount"]),
                category=it.get("category", "Other"),
            )
            for it in data.get("items", [])
        ]
        return ReceiptData(
            merchant=data.get("merchant", "Unknown"),
            date=data.get("date", ""),
            total=float(data.get("total", 0.0)),
            items=items,
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return None
```

- [ ] **Step 4: Run receipt scanner tests**

```bash
python -m pytest tests/test_receipt_scanner.py -v
```

Expected: all tests PASS.

- [ ] **Step 5: Create `pages/scan_receipt.py`**

```python
# pages/scan_receipt.py
import base64

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dash_table, dcc, html

from expense_tracker_agent.db import insert_expense, insert_expense_item
from expense_tracker_agent.receipt_scanner import parse_receipt

dash.register_page(__name__, path="/scan", name="Scan Receipt")

layout = html.Div([
    html.H5("Scan a Receipt", className="mb-3"),
    html.P(
        "Upload a photo of your receipt. Gemini will extract the items automatically.",
        className="text-muted mb-4",
    ),
    dcc.Upload(
        id="receipt-upload",
        children=html.Div(["Drag & drop or ", html.A("browse"), " (JPG / PNG)"]),
        style={
            "width": "100%", "height": "80px", "lineHeight": "80px",
            "borderWidth": "1px", "borderStyle": "dashed",
            "borderRadius": "8px", "textAlign": "center", "color": "#6c757d",
        },
        accept="image/*",
    ),
    dcc.Store(id="receipt-parsed-store"),
    html.Div(id="receipt-review-section", className="mt-4"),
    html.Div(id="receipt-save-result", className="mt-3"),
])


@callback(
    Output("receipt-review-section", "children"),
    Output("receipt-parsed-store", "data"),
    Input("receipt-upload", "contents"),
    State("receipt-upload", "filename"),
    prevent_initial_call=True,
)
def process_receipt(contents, filename):
    if not contents:
        return dash.no_update, dash.no_update

    header, b64 = contents.split(",", 1)
    image_bytes = base64.b64decode(b64)
    mime = "image/png" if filename and filename.lower().endswith(".png") else "image/jpeg"

    receipt = parse_receipt(image_bytes, mime_type=mime)
    if receipt is None:
        return dbc.Alert("Could not parse this receipt. Try a clearer photo.", color="danger"), None

    store_data = {
        "merchant": receipt.merchant,
        "date": receipt.date,
        "total": receipt.total,
        "items": [{"description": it.description, "amount": it.amount, "category": it.category}
                  for it in receipt.items],
    }

    items_table = dash_table.DataTable(
        id="receipt-items-table",
        data=store_data["items"],
        columns=[
            {"name": "Description", "id": "description", "editable": True},
            {"name": "Amount (€)", "id": "amount", "editable": True, "type": "numeric"},
            {"name": "Category", "id": "category", "editable": True,
             "presentation": "dropdown"},
        ],
        editable=True,
        style_cell={"fontSize": "13px", "padding": "6px"},
        style_table={"overflowX": "auto"},
    )

    review = html.Div([
        dbc.Row([
            dbc.Col([html.Label("Store"), dbc.Input(id="receipt-merchant", value=receipt.merchant)], md=4),
            dbc.Col([html.Label("Date"), dbc.Input(id="receipt-date", value=receipt.date)], md=4),
            dbc.Col([html.Label("Total (€)"), dbc.Input(id="receipt-total", value=str(receipt.total), type="number")], md=4),
        ], className="mb-3"),
        html.H6("Line items (editable)"),
        items_table,
        html.Div(className="mt-3 d-flex gap-2", children=[
            dbc.Button("Confirm & Save", id="receipt-confirm-btn", color="success", n_clicks=0),
            dbc.Button("Cancel", id="receipt-cancel-btn", color="secondary", outline=True, n_clicks=0),
        ]),
    ])

    return review, store_data


@callback(
    Output("receipt-save-result", "children"),
    Output("receipt-review-section", "children", allow_duplicate=True),
    Input("receipt-confirm-btn", "n_clicks"),
    State("receipt-merchant", "value"),
    State("receipt-date", "value"),
    State("receipt-total", "value"),
    State("receipt-items-table", "data"),
    prevent_initial_call=True,
)
def save_receipt(n_clicks, merchant, date, total, items):
    if not n_clicks:
        return dash.no_update, dash.no_update

    parent_id = insert_expense(
        amount=float(total or 0),
        category="Groceries",
        description=f"Receipt: {merchant}",
        merchant=merchant,
        date=date,
        source="receipt_scan",
    )
    for item in (items or []):
        insert_expense_item(
            parent_id=parent_id,
            amount=float(item.get("amount", 0)),
            description=item.get("description", ""),
            category=item.get("category", "Other"),
        )

    return (
        dbc.Alert(
            f"Saved! Expense #{parent_id} ({merchant}, €{total}) with {len(items or [])} items.",
            color="success",
        ),
        html.Div(),
    )


@callback(
    Output("receipt-review-section", "children", allow_duplicate=True),
    Output("receipt-parsed-store", "data", allow_duplicate=True),
    Input("receipt-cancel-btn", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_receipt(n_clicks):
    if not n_clicks:
        return dash.no_update, dash.no_update
    return html.Div(), None
```

- [ ] **Step 6: Verify receipt page renders**

```bash
python app.py
```

Open `http://localhost:8050/scan` — upload area renders. Stop with Ctrl+C.

- [ ] **Step 7: Run all tests one final time**

```bash
python -m pytest tests/ test_tools.py test_agent.py -v
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add expense_tracker_agent/receipt_scanner.py tests/test_receipt_scanner.py pages/scan_receipt.py
git commit -m "feat: add receipt scanner with Gemini Vision and scan receipt page"
```

---

## End-to-End Verification

Follow the steps in the spec's Verification section:

- [ ] Run `python app.py` → opens at `localhost:8050`
- [ ] Dashboard: KPI cards show 0s, all 6 charts show "No data yet"
- [ ] Add Expense: type "lunch €8 at Mensa today" → appears in recent list, dashboard updates
- [ ] Add sub-item: "beer €3 at Edeka, part of today's shop" → agent links to Edeka parent
- [ ] CSV Import: upload 3-column CSV → preview shows → import → dashboard updates
- [ ] Scan Receipt: upload receipt image → items extracted → confirm → parent + sub-items saved
- [ ] All 6 charts render with real data after adding several expenses
- [ ] `python -m pytest tests/ test_tools.py test_agent.py` → all pass

- [ ] **Final commit**

```bash
git add -A
git commit -m "feat: expense tracker v2 — SQLite, Dash dashboard, receipt scanner, CSV import"
```
