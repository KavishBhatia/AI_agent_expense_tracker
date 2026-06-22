# tests/test_history.py
import unittest
from datetime import date, timedelta

from pages.history import compute_weekly_avg, compute_monthly_avg, last_purchase_info


def _row(date_str, category, amount, merchant="Edeka"):
    return {"date": date_str, "category": category, "amount": amount,
            "merchant": merchant, "description": "", "id": 1}


class TestComputeWeeklyAvg(unittest.TestCase):

    def test_returns_zero_when_no_rows(self):
        self.assertEqual(compute_weekly_avg([], "Groceries"), 0.0)

    def test_returns_zero_when_no_matching_category(self):
        rows = [_row("2026-01-05", "Transport", 10.0)]
        self.assertEqual(compute_weekly_avg(rows, "Groceries"), 0.0)

    def test_averages_complete_weeks_only(self):
        # Two complete past weeks each with €20 → 40 / 8 windows = 5.0
        monday_last = date.today() - timedelta(days=date.today().weekday() + 7)
        monday_prev = monday_last - timedelta(weeks=1)
        rows = [
            _row(monday_last.isoformat(), "Groceries", 20.0),
            _row(monday_prev.isoformat(), "Groceries", 20.0),
        ]
        result = compute_weekly_avg(rows, "Groceries", n_weeks=8)
        self.assertAlmostEqual(result, 5.0)

    def test_excludes_current_incomplete_week(self):
        # A row dated today (current week) should not be counted
        today_str = date.today().isoformat()
        rows = [_row(today_str, "Groceries", 100.0)]
        result = compute_weekly_avg(rows, "Groceries", n_weeks=8)
        self.assertAlmostEqual(result, 0.0)


class TestComputeMonthlyAvg(unittest.TestCase):

    def test_returns_zero_when_no_rows(self):
        self.assertEqual(compute_monthly_avg([], "Groceries"), 0.0)

    def test_averages_over_n_months(self):
        today = date.today()
        m1 = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        m2 = (m1 - timedelta(days=1)).replace(day=1)
        m3 = (m2 - timedelta(days=1)).replace(day=1)
        rows = [
            _row(m1.isoformat(), "Groceries", 30.0),
            _row(m2.isoformat(), "Groceries", 30.0),
            _row(m3.isoformat(), "Groceries", 30.0),
        ]
        result = compute_monthly_avg(rows, "Groceries", n_months=3)
        self.assertAlmostEqual(result, 30.0)

    def test_excludes_current_month(self):
        today_str = date.today().isoformat()
        rows = [_row(today_str, "Groceries", 999.0)]
        result = compute_monthly_avg(rows, "Groceries", n_months=3)
        self.assertAlmostEqual(result, 0.0)

    def test_excludes_months_older_than_n_months(self):
        # A row from 6 months ago should NOT be included in a 3-month window
        today = date.today()
        old_month = today.replace(day=1)
        for _ in range(6):
            old_month = (old_month - timedelta(days=1)).replace(day=1)
        rows = [_row(old_month.isoformat(), "Groceries", 500.0)]
        result = compute_monthly_avg(rows, "Groceries", n_months=3)
        self.assertAlmostEqual(result, 0.0)


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


if __name__ == "__main__":
    unittest.main()
