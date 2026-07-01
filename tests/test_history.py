# tests/test_history.py
import unittest
from datetime import date, timedelta
from unittest.mock import patch

from pages.history import (
    compute_monthly_avg,
    compute_weekly_avg,
    export_csv,
    last_purchase_info,
)


def _row(date_str, category, amount, merchant="Edeka"):
    return {"date": date_str, "category": category, "amount": amount,
            "merchant": merchant, "description": "", "id": 1}


class TestComputeWeeklyAvg(unittest.TestCase):

    def test_returns_zero_when_no_rows(self):
        self.assertEqual(compute_weekly_avg([], "Groceries"), 0.0)

    def test_returns_zero_when_no_matching_category(self):
        rows = [_row("2026-01-05", "Transport", 10.0)]
        self.assertEqual(compute_weekly_avg(rows, "Groceries"), 0.0)

    def test_averages_across_complete_weeks(self):
        # Two complete past weeks: €20 and €40 → avg = (20+40)/2 = 30
        monday_last = date.today() - timedelta(days=date.today().weekday() + 7)
        monday_prev = monday_last - timedelta(weeks=1)
        rows = [
            _row(monday_last.isoformat(), "Groceries", 20.0),
            _row(monday_prev.isoformat(), "Groceries", 40.0),
        ]
        result = compute_weekly_avg(rows, "Groceries")
        self.assertAlmostEqual(result, 30.0)

    def test_excludes_current_incomplete_week(self):
        today_str = date.today().isoformat()
        rows = [_row(today_str, "Groceries", 100.0)]
        result = compute_weekly_avg(rows, "Groceries")
        self.assertAlmostEqual(result, 0.0)


class TestComputeMonthlyAvg(unittest.TestCase):

    def test_returns_zero_when_no_rows(self):
        self.assertEqual(compute_monthly_avg([], "Groceries"), 0.0)

    def test_averages_across_complete_months(self):
        # Three months: €30 each → avg = 30
        today = date.today()
        m1 = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        m2 = (m1 - timedelta(days=1)).replace(day=1)
        m3 = (m2 - timedelta(days=1)).replace(day=1)
        rows = [
            _row(m1.isoformat(), "Groceries", 30.0),
            _row(m2.isoformat(), "Groceries", 60.0),
            _row(m3.isoformat(), "Groceries", 90.0),
        ]
        result = compute_monthly_avg(rows, "Groceries")
        self.assertAlmostEqual(result, 60.0)  # (30+60+90)/3

    def test_excludes_current_month(self):
        today_str = date.today().isoformat()
        rows = [_row(today_str, "Groceries", 999.0)]
        result = compute_monthly_avg(rows, "Groceries")
        self.assertAlmostEqual(result, 0.0)

    def test_includes_all_historical_months(self):
        # A row from 6 months ago IS included (no cutoff)
        today = date.today()
        old_month = today.replace(day=1)
        for _ in range(6):
            old_month = (old_month - timedelta(days=1)).replace(day=1)
        rows = [_row(old_month.isoformat(), "Groceries", 120.0)]
        result = compute_monthly_avg(rows, "Groceries")
        self.assertAlmostEqual(result, 120.0)  # 1 month, €120 → avg = 120


class TestLastPurchaseInfo(unittest.TestCase):

    def test_returns_none_when_no_rows(self):
        self.assertIsNone(last_purchase_info([], "Groceries"))

    def test_returns_most_recent(self):
        rows = [
            _row("2026-06-01", "Groceries", 10.0, "Lidl"),
            _row("2026-06-15", "Groceries", 20.0, "Edeka"),
            _row("2026-06-10", "Groceries", 15.0, "Rewe"),
        ]
        result = last_purchase_info(rows, "Groceries")
        self.assertEqual(result["date"], "2026-06-15")
        self.assertEqual(result["merchant"], "Edeka")
        self.assertAlmostEqual(result["amount"], 20.0)

    def test_returns_none_for_wrong_category(self):
        rows = [_row("2026-06-01", "Transport", 10.0)]
        self.assertIsNone(last_purchase_info(rows, "Groceries"))


class TestExportCsv(unittest.TestCase):

    @patch("pages.history.fetch_expenses")
    def test_applies_filters_and_generates_filename(self, mock_fetch_expenses):
        mock_fetch_expenses.return_value = [
            _row("2026-06-01", "Groceries", 10.0, "Lidl"),
            _row("2026-06-02", "Groceries", 20.0, "Rewe"),
            _row("2026-06-03", "Transport", 30.0, "Lidl"),
        ]

        result = export_csv(1, "Groceries", "lidl")

        self.assertEqual(
            result["filename"], f"expenses_Groceries_{date.today().isoformat()}.csv"
        )
        self.assertIn("2026-06-01,Lidl,Groceries,10.0", result["content"])
        self.assertNotIn("2026-06-02,Rewe,Groceries,20.0", result["content"])
        self.assertNotIn("2026-06-03,Lidl,Transport,30.0", result["content"])


if __name__ == "__main__":
    unittest.main()
