# tests/test_trip_db.py
import os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

import expense_tracker_agent.trip_db as trip_db_module
from expense_tracker_agent.trip_db import (
    init_trip_db, create_trip, fetch_trips, fetch_trip,
    fetch_trip_expenses, insert_trip_expense, delete_trip, delete_trip_expense,
    fetch_trip_expense, update_trip_expense, trip_expense_exists,
)

def _temp_db() -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    os.unlink(f.name)
    return Path(f.name)

class BaseTripDbTest(unittest.TestCase):
    def setUp(self):
        self.tmp_db = _temp_db()
        self.patcher = patch.object(trip_db_module, "TRIP_DB_PATH", self.tmp_db)
        self.patcher.start()
        init_trip_db()

    def tearDown(self):
        self.patcher.stop()
        if self.tmp_db.exists():
            self.tmp_db.unlink()

class TestCreateFetchTrip(BaseTripDbTest):
    def test_create_returns_id(self):
        tid = create_trip("Barcelona")
        self.assertIsInstance(tid, int)
        self.assertGreater(tid, 0)

    def test_fetch_trips_empty(self):
        self.assertEqual(fetch_trips(), [])

    def test_fetch_trips_returns_trip(self):
        tid = create_trip("Lisbon")
        trips = fetch_trips()
        self.assertEqual(len(trips), 1)
        self.assertEqual(trips[0]["name"], "Lisbon")
        self.assertEqual(trips[0]["id"], tid)

    def test_fetch_trip_none_for_missing(self):
        self.assertIsNone(fetch_trip(999))

    def test_fetch_trip_totals_computed(self):
        tid = create_trip("Rome")
        insert_trip_expense(tid, 20.0, "Ristorante", "Food & Dining", "pasta", "2026-05-10")
        insert_trip_expense(tid, 10.0, None, "Commute", None, "2026-05-11")
        t = fetch_trip(tid)
        self.assertAlmostEqual(t["total"], 30.0)
        self.assertEqual(t["count"], 2)
        self.assertEqual(t["start_date"], "2026-05-10")
        self.assertEqual(t["end_date"], "2026-05-11")

class TestTripExpenses(BaseTripDbTest):
    def test_insert_and_fetch(self):
        tid = create_trip("Paris")
        insert_trip_expense(tid, 15.0, "Boulangerie", "Food & Dining", "croissant", "2026-04-01")
        rows = fetch_trip_expenses(tid)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["merchant"], "Boulangerie")
        self.assertAlmostEqual(rows[0]["amount"], 15.0)

    def test_nullable_fields(self):
        tid = create_trip("Berlin")
        insert_trip_expense(tid, 5.0, None, "Miscellaneous", None, "2026-03-01")
        rows = fetch_trip_expenses(tid)
        self.assertIsNone(rows[0]["merchant"])
        self.assertIsNone(rows[0]["description"])

    def test_sorted_by_date_asc(self):
        tid = create_trip("Vienna")
        insert_trip_expense(tid, 10.0, "A", "Food & Dining", None, "2026-06-05")
        insert_trip_expense(tid, 20.0, "B", "Groceries", None, "2026-06-03")
        rows = fetch_trip_expenses(tid)
        self.assertEqual(rows[0]["date"], "2026-06-03")
        self.assertEqual(rows[1]["date"], "2026-06-05")

class TestDeleteTrip(BaseTripDbTest):
    def test_delete_removes_trip_and_expenses(self):
        tid = create_trip("Madrid")
        insert_trip_expense(tid, 12.0, "Mercado", "Groceries", None, "2026-07-01")
        delete_trip(tid)
        self.assertEqual(fetch_trips(), [])
        self.assertEqual(fetch_trip_expenses(tid), [])


class TestDeleteTripExpense(BaseTripDbTest):
    def test_delete_removes_single_expense(self):
        tid = create_trip("Amsterdam")
        eid = insert_trip_expense(tid, 8.0, "Bakker", "Food & Dining", None, "2026-08-01")
        insert_trip_expense(tid, 15.0, "Fiets", "Transport", None, "2026-08-02")
        delete_trip_expense(eid)
        rows = fetch_trip_expenses(tid)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["merchant"], "Fiets")

    def test_delete_updates_trip_total(self):
        tid = create_trip("Prague")
        eid = insert_trip_expense(tid, 20.0, "Pivnice", "Food & Dining", None, "2026-09-01")
        insert_trip_expense(tid, 10.0, "Tram", "Transport", None, "2026-09-02")
        delete_trip_expense(eid)
        t = fetch_trip(tid)
        self.assertAlmostEqual(t["total"], 10.0)
        self.assertEqual(t["count"], 1)

    def test_delete_nonexistent_is_silent(self):
        delete_trip_expense(999)  # should not raise


class TestFetchTripExpense(BaseTripDbTest):
    def test_fetch_returns_correct_row(self):
        tid = create_trip("Seville")
        eid = insert_trip_expense(tid, 12.5, "Tapas Bar", "Food & Dining", "tapas", "2026-10-01")
        row = fetch_trip_expense(eid)
        self.assertIsNotNone(row)
        self.assertEqual(row["id"], eid)
        self.assertAlmostEqual(row["amount"], 12.5)
        self.assertEqual(row["merchant"], "Tapas Bar")
        self.assertEqual(row["category"], "Food & Dining")
        self.assertEqual(row["description"], "tapas")
        self.assertEqual(row["date"], "2026-10-01")

    def test_fetch_returns_none_for_missing(self):
        self.assertIsNone(fetch_trip_expense(9999))

    def test_fetch_nullable_fields(self):
        tid = create_trip("Bruges")
        eid = insert_trip_expense(tid, 5.0, None, "Miscellaneous", None, "2026-11-01")
        row = fetch_trip_expense(eid)
        self.assertIsNone(row["merchant"])
        self.assertIsNone(row["description"])


class TestUpdateTripExpense(BaseTripDbTest):
    def test_update_changes_fields(self):
        tid = create_trip("Ghent")
        eid = insert_trip_expense(tid, 10.0, "OldMerchant", "Transport", "old note", "2026-12-01")
        update_trip_expense(eid, 25.0, "NewMerchant", "Food & Dining", "new note", "2026-12-05")
        row = fetch_trip_expense(eid)
        self.assertAlmostEqual(row["amount"], 25.0)
        self.assertEqual(row["merchant"], "NewMerchant")
        self.assertEqual(row["category"], "Food & Dining")
        self.assertEqual(row["description"], "new note")
        self.assertEqual(row["date"], "2026-12-05")

    def test_update_reflects_in_trip_total(self):
        tid = create_trip("Antwerp")
        eid = insert_trip_expense(tid, 10.0, "Shop", "Groceries", None, "2026-12-10")
        update_trip_expense(eid, 30.0, "Shop", "Groceries", None, "2026-12-10")
        t = fetch_trip(tid)
        self.assertAlmostEqual(t["total"], 30.0)

    def test_update_nullable_to_none(self):
        tid = create_trip("Liege")
        eid = insert_trip_expense(tid, 8.0, "Bistro", "Food & Dining", "lunch", "2026-12-15")
        update_trip_expense(eid, 8.0, None, "Food & Dining", None, "2026-12-15")
        row = fetch_trip_expense(eid)
        self.assertIsNone(row["merchant"])
        self.assertIsNone(row["description"])


class TestTripExpenseExists(BaseTripDbTest):
    def test_returns_true_for_exact_match(self):
        tid = create_trip("Porto")
        insert_trip_expense(tid, 12.0, "Francesinha", "Food & Dining", None, "2026-05-01")
        self.assertTrue(trip_expense_exists(tid, "2026-05-01", "Francesinha", 12.0))

    def test_returns_false_when_no_match(self):
        tid = create_trip("Faro")
        self.assertFalse(trip_expense_exists(tid, "2026-05-01", "Cafe", 5.0))

    def test_returns_false_when_no_merchant(self):
        tid = create_trip("Coimbra")
        insert_trip_expense(tid, 10.0, None, "Miscellaneous", None, "2026-05-01")
        self.assertFalse(trip_expense_exists(tid, "2026-05-01", None, 10.0))

    def test_returns_false_for_different_amount(self):
        tid = create_trip("Braga")
        insert_trip_expense(tid, 20.0, "Shop", "Groceries", None, "2026-06-01")
        self.assertFalse(trip_expense_exists(tid, "2026-06-01", "Shop", 25.0))

    def test_returns_false_for_different_date(self):
        tid = create_trip("Evora")
        insert_trip_expense(tid, 15.0, "Adega", "Food & Dining", None, "2026-06-01")
        self.assertFalse(trip_expense_exists(tid, "2026-06-02", "Adega", 15.0))

    def test_does_not_cross_trips(self):
        tid1 = create_trip("Trip A")
        tid2 = create_trip("Trip B")
        insert_trip_expense(tid1, 10.0, "Market", "Groceries", None, "2026-07-01")
        self.assertFalse(trip_expense_exists(tid2, "2026-07-01", "Market", 10.0))
