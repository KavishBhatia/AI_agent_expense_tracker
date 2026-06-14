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
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()}
        conn.close()
        self.assertEqual(tables, {"expenses", "expense_items"})


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
