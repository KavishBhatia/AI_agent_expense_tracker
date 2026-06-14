# tests/test_charts.py
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import expense_tracker_agent.db as db_module
from expense_tracker_agent.db import init_db, insert_expense, insert_expense_item
from charts import (
    category_breakdown_data,
    heatmap_data,
    kpi_stats,
    monthly_trend_data,
    sub_expense_breakdown_data,
    top_merchants_data,
    weekly_bar_data,
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
        df = monthly_trend_data("2026-05-01", "2026-06-30")
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
