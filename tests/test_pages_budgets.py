# tests/test_pages_budgets.py
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import expense_tracker_agent.db as db_module
from expense_tracker_agent.db import get_all_budgets, init_db, set_budget
from expense_tracker_agent.tools import CATEGORIES
from pages import budgets as page


def _temp_db() -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    os.unlink(f.name)
    return Path(f.name)


def _slider_ids(component):
    """Collect the ids of every dcc.Slider under a Dash component tree."""
    found = []

    def walk(node):
        if isinstance(node, (list, tuple)):
            for n in node:
                walk(n)
            return
        if type(node).__name__ == "Slider":
            found.append(node.id)
        children = getattr(node, "children", None)
        if children is not None:
            walk(children)

    walk(component)
    return found


class BudgetPageTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp_db = _temp_db()
        patcher = patch.object(db_module, "DB_PATH", self.tmp_db)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(lambda: self.tmp_db.exists() and self.tmp_db.unlink())
        init_db()


class TestCategoryPartition(unittest.TestCase):
    def test_primary_and_extra_do_not_overlap(self):
        self.assertFalse(set(page._PRIMARY_CATEGORIES) & set(page._EXTRA_CATEGORIES))

    def test_primary_and_extra_cover_every_category(self):
        self.assertEqual(
            set(page._PRIMARY_CATEGORIES) | set(page._EXTRA_CATEGORIES), set(CATEGORIES)
        )

    def test_primary_categories_are_valid(self):
        for cat in page._PRIMARY_CATEGORIES:
            self.assertIn(cat, CATEGORIES)


class TestSliderRows(unittest.TestCase):
    def test_two_categories_per_row(self):
        rows = page._slider_rows(["A", "B", "C", "D"], {})
        self.assertEqual(len(rows), 2)
        self.assertEqual([len(r.children) for r in rows], [2, 2])

    def test_odd_count_leaves_last_row_with_one_column(self):
        rows = page._slider_rows(["A", "B", "C"], {})
        self.assertEqual([len(r.children) for r in rows], [2, 1])

    def test_empty_list_gives_no_rows(self):
        self.assertEqual(page._slider_rows([], {}), [])

    def test_slider_ids_use_pattern_matching_with_category(self):
        rows = page._slider_rows(["Groceries", "Travel"], {})
        self.assertEqual(
            _slider_ids(rows),
            [{"type": "budget-slider", "index": "Groceries"},
             {"type": "budget-slider", "index": "Travel"}],
        )

    def test_slider_value_comes_from_budgets_default_zero(self):
        rows = page._slider_rows(["Groceries", "Travel"], {"Groceries": 300})
        sliders = []

        def walk(node):
            if isinstance(node, (list, tuple)):
                for n in node:
                    walk(n)
                return
            if type(node).__name__ == "Slider":
                sliders.append(node)
            if getattr(node, "children", None) is not None:
                walk(node.children)

        walk(rows)
        self.assertEqual([s.value for s in sliders], [300, 0])


class TestLayout(BudgetPageTestCase):
    def _collapse(self, layout):
        found = []

        def walk(node):
            if isinstance(node, (list, tuple)):
                for n in node:
                    walk(n)
                return
            if getattr(node, "id", None) == "budget-more-collapse":
                found.append(node)
            if getattr(node, "children", None) is not None:
                walk(node.children)

        walk(layout)
        return found[0]

    def test_extra_section_closed_when_only_primary_budgets_set(self):
        set_budget("Groceries", 400)
        self.assertFalse(self._collapse(page.layout()).is_open)

    def test_extra_section_closed_when_no_budgets(self):
        self.assertFalse(self._collapse(page.layout()).is_open)

    def test_extra_section_opens_when_an_extra_category_has_a_budget(self):
        extra = page._EXTRA_CATEGORIES[0]
        set_budget(extra, 100)
        self.assertTrue(self._collapse(page.layout()).is_open)

    def test_layout_has_a_slider_for_every_category(self):
        ids = {i["index"] for i in _slider_ids(page.layout())}
        self.assertEqual(ids, set(CATEGORIES))


class TestToggleMoreCategories(unittest.TestCase):
    def test_toggles_open_state(self):
        self.assertTrue(page.toggle_more_categories(1, False))
        self.assertFalse(page.toggle_more_categories(2, True))


class TestSaveBudgets(BudgetPageTestCase):
    @staticmethod
    def _ids(*cats):
        return [{"type": "budget-slider", "index": c} for c in cats]

    def test_saves_positive_values(self):
        page.save_budgets(1, [300, 150], self._ids("Groceries", "Travel"))
        self.assertEqual(get_all_budgets(), {"Groceries": 300.0, "Travel": 150.0})

    def test_zero_removes_existing_budget(self):
        set_budget("Groceries", 300)
        page.save_budgets(1, [0], self._ids("Groceries"))
        self.assertNotIn("Groceries", get_all_budgets())

    def test_none_value_removes_existing_budget(self):
        set_budget("Groceries", 300)
        page.save_budgets(1, [None], self._ids("Groceries"))
        self.assertNotIn("Groceries", get_all_budgets())

    def test_updates_existing_budget(self):
        set_budget("Groceries", 300)
        page.save_budgets(1, [450], self._ids("Groceries"))
        self.assertEqual(get_all_budgets()["Groceries"], 450.0)

    def test_untouched_categories_not_in_form_are_left_alone(self):
        set_budget("Travel", 99)
        page.save_budgets(1, [300], self._ids("Groceries"))
        self.assertEqual(get_all_budgets()["Travel"], 99.0)

    def test_returns_success_alert_and_timestamp_signal(self):
        alert, signal = page.save_budgets(1, [100], self._ids("Groceries"))
        self.assertEqual(alert.color, "success")
        self.assertEqual(alert.children, "Budgets saved.")
        # the dashboard reacts to this store changing, so it must be a fresh ISO timestamp
        datetime.fromisoformat(signal["saved_at"])

    def test_empty_form_saves_nothing_but_still_signals(self):
        alert, signal = page.save_budgets(1, [], [])
        self.assertEqual(get_all_budgets(), {})
        self.assertIn("saved_at", signal)


if __name__ == "__main__":
    unittest.main()
