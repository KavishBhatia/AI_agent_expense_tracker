# test_tools.py
import os
import tempfile
import unittest
from datetime import date
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
    find_parent_expense_id,
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


# ---------------------------------------------------------------------------
# CATEGORIES
# ---------------------------------------------------------------------------

class TestCategories(unittest.TestCase):
    def test_categories_is_a_list(self):
        self.assertIsInstance(CATEGORIES, list)

    def test_categories_contains_core_values(self):
        for cat in ["Groceries", "Transport", "Entertainment", "Alcohol", "Miscellaneous"]:
            self.assertIn(cat, CATEGORIES)

    def test_alcohol_in_categories(self):
        self.assertIn("Alcohol", CATEGORIES)


# ---------------------------------------------------------------------------
# add_expense
# ---------------------------------------------------------------------------

class TestAddExpense(BaseToolsTest):
    def test_return_message_contains_amount(self):
        result = add_expense(45.0, "groceries", "Groceries")
        self.assertIn("45.00", result)

    def test_return_message_contains_category(self):
        result = add_expense(45.0, "groceries", "Groceries")
        self.assertIn("Groceries", result)

    def test_return_message_contains_date(self):
        result = add_expense(45.0, "groceries", "Groceries", date="2026-06-03")
        self.assertIn("2026-06-03", result)

    def test_defaults_date_to_today(self):
        result = add_expense(10.0, "lunch", "Food")
        self.assertIn(date.today().isoformat(), result)

    def test_persists_to_db(self):
        add_expense(10.0, "coffee", "Food", merchant="Mensa")
        from expense_tracker_agent.db import fetch_expenses
        rows = fetch_expenses()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["merchant"], "Mensa")


# ---------------------------------------------------------------------------
# calculate_total_spending
# ---------------------------------------------------------------------------

class TestCalculateTotalSpending(BaseToolsTest):
    def setUp(self):
        super().setUp()
        add_expense(10.0, "a", "Food", date="2026-05-01")
        add_expense(20.0, "b", "Food", date="2026-06-01")
        add_expense(30.0, "c", "Food", date="2026-06-15")

    def test_total_no_filter_sums_all(self):
        result = calculate_total_spending()
        self.assertIn("60.00", result)

    def test_total_start_date_excludes_earlier(self):
        result = calculate_total_spending(start_date="2026-06-01")
        self.assertIn("50.00", result)

    def test_total_end_date_excludes_later(self):
        result = calculate_total_spending(end_date="2026-06-01")
        self.assertIn("30.00", result)

    def test_total_date_range(self):
        result = calculate_total_spending(start_date="2026-06-01", end_date="2026-06-01")
        self.assertIn("20.00", result)


# ---------------------------------------------------------------------------
# get_spending_by_category
# ---------------------------------------------------------------------------

class TestGetSpendingByCategory(BaseToolsTest):
    def setUp(self):
        super().setUp()
        add_expense(10.0, "a", "Food", date="2026-05-01")
        add_expense(20.0, "b", "Food", date="2026-06-01")
        add_expense(15.0, "c", "Transport", date="2026-06-01")

    def test_category_report_no_filter(self):
        result = get_spending_by_category()
        self.assertIn("Food", result)
        self.assertIn("Transport", result)

    def test_category_report_start_date_excludes_earlier(self):
        result = get_spending_by_category(start_date="2026-06-01")
        self.assertIn("20.00", result)

    def test_category_report_end_date(self):
        result = get_spending_by_category(end_date="2026-05-31")
        self.assertIn("Food", result)
        self.assertNotIn("Transport", result)


# ---------------------------------------------------------------------------
# list_recent_expenses
# ---------------------------------------------------------------------------

class TestListRecentExpenses(BaseToolsTest):
    def setUp(self):
        super().setUp()
        add_expense(10.0, "lunch", "Food", date="2026-06-01")
        add_expense(20.0, "taxi", "Transport", date="2026-06-02")
        add_expense(30.0, "dinner", "Food", date="2026-06-03")

    def test_list_no_filter_returns_all(self):
        result = list_recent_expenses(count=10)
        self.assertIn("lunch", result)
        self.assertIn("taxi", result)
        self.assertIn("dinner", result)

    def test_list_category_filter_excludes_others(self):
        result = list_recent_expenses(count=10, category="Food")
        self.assertIn("lunch", result)
        self.assertIn("dinner", result)
        self.assertNotIn("taxi", result)

    def test_list_category_filter_case_insensitive(self):
        result = list_recent_expenses(count=10, category="food")
        self.assertIn("lunch", result)
        self.assertNotIn("taxi", result)

    def test_list_category_filter_empty_when_no_match(self):
        result = list_recent_expenses(count=10, category="Healthcare")
        self.assertIn("No expenses", result)


# ---------------------------------------------------------------------------
# add_expense_item
# ---------------------------------------------------------------------------

class TestAddExpenseItem(BaseToolsTest):
    def test_adds_item_to_existing_parent(self):
        add_expense(10.0, "Edeka shop", "Groceries", merchant="Edeka")
        from expense_tracker_agent.db import find_parent_expense
        today = date.today().isoformat()
        parent_id = find_parent_expense("Edeka", today)
        result = add_expense_item(parent_id, 3.0, "beer", "Alcohol")
        self.assertIn("beer", result)
        self.assertIn("3.00", result)

    def test_returns_error_for_invalid_parent(self):
        result = add_expense_item(9999, 3.0, "beer", "Alcohol")
        self.assertIn("not found", result.lower())


# ---------------------------------------------------------------------------
# list_expense_items
# ---------------------------------------------------------------------------

class TestListExpenseItems(BaseToolsTest):
    def test_lists_items_for_parent(self):
        add_expense(10.0, "Edeka shop", "Groceries", merchant="Edeka")
        from expense_tracker_agent.db import find_parent_expense
        today = date.today().isoformat()
        parent_id = find_parent_expense("Edeka", today)
        add_expense_item(parent_id, 3.0, "beer", "Alcohol")
        add_expense_item(parent_id, 2.0, "bread", "Groceries")
        result = list_expense_items(parent_id)
        self.assertIn("beer", result)
        self.assertIn("bread", result)

    def test_returns_empty_message_when_no_items(self):
        add_expense(10.0, "TestShop", "Groceries", merchant="TestShop")
        from expense_tracker_agent.db import find_parent_expense
        today = date.today().isoformat()
        parent_id = find_parent_expense("TestShop", today)
        self.assertIsNotNone(parent_id)
        result = list_expense_items(parent_id)
        self.assertIn("no items", result.lower())


# ---------------------------------------------------------------------------
# import_csv_row
# ---------------------------------------------------------------------------

class TestImportCsvRow(BaseToolsTest):
    def test_inserts_new_row(self):
        result = import_csv_row("2026-05-01", 15.0, "Edeka")
        self.assertIn("imported", result.lower())

    def test_skips_duplicate(self):
        import_csv_row("2026-05-01", 15.0, "Edeka")
        result = import_csv_row("2026-05-01", 15.0, "Edeka")
        self.assertIn("skipped", result.lower())


# ---------------------------------------------------------------------------
# find_parent_expense_id
# ---------------------------------------------------------------------------

class TestFindParentExpenseId(BaseToolsTest):
    def test_returns_id_when_found(self):
        add_expense(10.0, "shop", "Groceries", merchant="Edeka", date="2026-06-01")
        result = find_parent_expense_id("Edeka", "2026-06-01")
        self.assertTrue(result.isdigit())

    def test_returns_not_found_when_missing(self):
        result = find_parent_expense_id("Rewe", "2026-06-01")
        self.assertEqual(result, "not found")


if __name__ == "__main__":
    unittest.main()
