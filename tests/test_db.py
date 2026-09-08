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
    fetch_expense,
    fetch_expense_items,
    fetch_expense_items_by_parent_ids,
    fetch_expenses,
    find_parent_expense,
    get_all_budgets,
    init_db,
    insert_expense,
    insert_expense_item,
    migrate_from_csv,
    set_budget,
    update_expense,
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
        self.assertEqual(tables, {"expenses", "expense_items", "budgets"})


class TestAmazonMigration(BaseDbTest):
    def _insert_raw(self, description, merchant=None, deleted=0):
        conn = sqlite3.connect(self.tmp_db)
        conn.execute(
            "INSERT INTO expenses (amount, merchant, category, description, date, timestamp, source, deleted) "
            "VALUES (?, ?, ?, ?, ?, ?, 'manual', ?)",
            (20.0, merchant, "Electronics", description, "2026-03-01", "2026-03-01T10:00:00", deleted),
        )
        conn.commit()
        conn.close()

    def test_splits_amazon_for_item_pattern(self):
        self._insert_raw("amazon for phone case")
        init_db()  # re-run migration against the seeded row
        row = fetch_expenses()[0]
        self.assertEqual(row["merchant"], "Amazon")
        self.assertEqual(row["description"], "phone case")

    def test_fallback_sets_merchant_without_touching_description(self):
        self._insert_raw("bought a cable on amazon")
        init_db()
        row = fetch_expenses()[0]
        self.assertEqual(row["merchant"], "Amazon")
        self.assertEqual(row["description"], "bought a cable on amazon")

    def test_splits_store_for_item_patterns_for_new_merchants(self):
        self._insert_raw("rossmann for shampoo")
        self._insert_raw("kaufland for groceries")
        init_db()
        rows = fetch_expenses()
        self.assertEqual(
            [(row["merchant"], row["description"]) for row in rows],
            [("Rossmann", "shampoo"), ("Kaufland", "groceries")],
        )

    def test_does_not_touch_rows_with_existing_merchant(self):
        self._insert_raw("amazon for headphones", merchant="SomeOtherStore")
        init_db()
        row = fetch_expenses()[0]
        self.assertEqual(row["merchant"], "SomeOtherStore")
        self.assertEqual(row["description"], "amazon for headphones")

    def test_does_not_match_substring_word(self):
        self._insert_raw("amazonite crystal gift")
        init_db()
        row = fetch_expenses()[0]
        self.assertIsNone(row["merchant"])


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

    def test_normalizes_merchant_casing_and_whitespace(self):
        insert_expense(5.50, "Groceries", "bread", merchant="ALDI")
        insert_expense(3.25, "Personal Care", "soap", merchant=" dm ")
        insert_expense(2.00, "Shopping", "socks", merchant="action")
        insert_expense(4.00, "Shopping", "toy", merchant=" TEDI ")
        insert_expense(6.00, "Shopping", "shirt", merchant="wOoLwOrTh")
        insert_expense(20.00, "Electronics", "cable", merchant="AMAZON")
        insert_expense(8.00, "Personal Care", "shampoo", merchant="ROSSMANN")
        insert_expense(30.00, "Groceries", "weekly shop", merchant=" kaufland ")

        rows = fetch_expenses()

        self.assertEqual(
            [row["merchant"] for row in rows],
            ["Aldi", "dm", "Action", "Tedi", "Woolworth", "Amazon", "Rossmann", "Kaufland"],
        )

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

    def test_fetch_items_by_parent_ids_groups_results(self):
        parent_a = insert_expense(10.0, "Groceries", "A")
        parent_b = insert_expense(12.0, "Groceries", "B")
        insert_expense_item(parent_a, 2.0, "bread", "Groceries")
        insert_expense_item(parent_b, 3.0, "milk", "Groceries")
        insert_expense_item(parent_a, 1.5, "eggs", "Groceries")

        grouped = fetch_expense_items_by_parent_ids([parent_a, parent_b])

        self.assertEqual([i["description"] for i in grouped[parent_a]], ["bread", "eggs"])
        self.assertEqual([i["description"] for i in grouped[parent_b]], ["milk"])


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

    def test_normalizes_merchant_before_lookup(self):
        insert_expense(10.0, "Groceries", "shop", merchant="Edeka", date="2026-06-01")
        self.assertTrue(expense_exists("2026-06-01", " edeka ", 10.0))


class TestFetchExpense(BaseDbTest):
    def test_fetch_returns_correct_row(self):
        eid = insert_expense(12.5, "Groceries", "shop", merchant="Edeka", date="2026-06-01")
        row = fetch_expense(eid)
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], eid)
        self.assertAlmostEqual(row["amount"], 12.5)
        self.assertEqual(row["merchant"], "Edeka")
        self.assertEqual(row["description"], "shop")

    def test_fetch_returns_none_for_missing(self):
        self.assertIsNone(fetch_expense(9999))


class TestUpdateExpense(BaseDbTest):
    def test_update_changes_all_fields(self):
        eid = insert_expense(10.0, "Commute", "old note", merchant="OldMerchant", date="2026-01-01")
        update_expense(eid, 25.0, "NewMerchant", "Food & Dining", "new note", "2026-02-01")
        row = fetch_expense(eid)
        self.assertAlmostEqual(row["amount"], 25.0)
        self.assertEqual(row["merchant"], "NewMerchant")
        self.assertEqual(row["category"], "Food & Dining")
        self.assertEqual(row["description"], "new note")
        self.assertEqual(row["date"], "2026-02-01")

    def test_update_normalizes_merchant_casing(self):
        eid = insert_expense(10.0, "Groceries", "shop", date="2026-01-01")
        update_expense(eid, 10.0, "aldi", "Groceries", "shop", "2026-01-01")
        row = fetch_expense(eid)
        self.assertEqual(row["merchant"], "Aldi")

    def test_update_merchant_none_clears_it(self):
        eid = insert_expense(10.0, "Groceries", "shop", merchant="Edeka", date="2026-01-01")
        update_expense(eid, 10.0, None, "Groceries", "shop", "2026-01-01")
        row = fetch_expense(eid)
        self.assertIsNone(row["merchant"])


class TestFindParentExpense(BaseDbTest):
    def test_finds_parent_by_merchant_and_date(self):
        eid = insert_expense(10.0, "Groceries", "Edeka shop", merchant="Edeka", date="2026-06-01")
        found = find_parent_expense("Edeka", "2026-06-01")
        self.assertEqual(found, eid)

    def test_returns_none_when_no_match(self):
        self.assertIsNone(find_parent_expense("Rewe", "2026-06-01"))

    def test_normalizes_merchant_before_lookup(self):
        eid = insert_expense(10.0, "Groceries", "Edeka shop", merchant="Edeka", date="2026-06-01")
        self.assertEqual(find_parent_expense("edeka", "2026-06-01"), eid)


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


class TestBudgets(BaseDbTest):
    def test_get_all_budgets_empty(self):
        self.assertEqual(get_all_budgets(), {})

    def test_set_and_get_budget(self):
        set_budget("Groceries", 200.0)
        result = get_all_budgets()
        self.assertAlmostEqual(result["Groceries"], 200.0)

    def test_set_budget_upserts(self):
        set_budget("Groceries", 200.0)
        set_budget("Groceries", 300.0)
        result = get_all_budgets()
        self.assertAlmostEqual(result["Groceries"], 300.0)
        self.assertEqual(len(result), 1)

    def test_set_budget_none_removes_row(self):
        set_budget("Groceries", 200.0)
        set_budget("Groceries", None)
        self.assertNotIn("Groceries", get_all_budgets())

    def test_set_budget_zero_removes_row(self):
        set_budget("Groceries", 200.0)
        set_budget("Groceries", 0)
        self.assertNotIn("Groceries", get_all_budgets())

    def test_multiple_categories(self):
        set_budget("Groceries", 200.0)
        set_budget("Transport", 80.0)
        result = get_all_budgets()
        self.assertEqual(len(result), 2)
        self.assertAlmostEqual(result["Transport"], 80.0)
