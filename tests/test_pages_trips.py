# tests/test_pages_trips.py
"""Tests for the callbacks and helpers in pages/trips.py and pages/trip_detail.py.

Dash's @callback returns the original function, so callbacks are called directly.
`dash.callback_context` is patched where a callback inspects what triggered it.
All DB access goes to a temp trips.db; nothing touches the real databases.
"""
import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

import expense_tracker_agent.trip_db as trip_db_module
import pages.trip_detail as td
import pages.trips as trips_page
from expense_tracker_agent.trip_db import (
    create_trip, fetch_trip, fetch_trip_expenses, fetch_trips,
    init_trip_db, insert_trip_expense,
)

NO_UPDATE = dash.no_update


# ── helpers ───────────────────────────────────────────────────────────────────

def _temp_db() -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    os.unlink(f.name)
    return Path(f.name)


def _walk(node):
    """Yield every Dash component / string in a nested component tree."""
    yield node
    children = getattr(node, "children", None)
    if children is None and isinstance(node, (list, tuple)):
        children = node
    if isinstance(children, (list, tuple)):
        for c in children:
            yield from _walk(c)
    elif children is not None:
        yield from _walk(children)


def _text(node) -> str:
    """All string content in a component tree, joined."""
    return " ".join(str(n) for n in _walk(node) if isinstance(n, (str, int, float)))


def _find(node, cls):
    return [n for n in _walk(node) if isinstance(n, cls)]


def _ctx(triggered_id=None, triggered=None):
    return SimpleNamespace(
        triggered_id=triggered_id,
        triggered=triggered if triggered is not None else
        ([{"prop_id": f"{triggered_id}.n_clicks", "value": 1}] if triggered_id else []),
    )


def _pattern_trigger(type_, index, value=1):
    return [{"prop_id": json.dumps({"index": index, "type": type_}, separators=(",", ":")) + ".n_clicks",
             "value": value}]


def _csv_contents(text: str, encoding="utf-8") -> str:
    return "data:text/csv;base64," + base64.b64encode(text.encode(encoding)).decode()


class BaseTripPageTest(unittest.TestCase):
    def setUp(self):
        self.tmp_db = _temp_db()
        self.patcher = patch.object(trip_db_module, "TRIP_DB_PATH", self.tmp_db)
        self.patcher.start()
        init_trip_db()

    def tearDown(self):
        self.patcher.stop()
        if self.tmp_db.exists():
            self.tmp_db.unlink()

    def add(self, trip_id, amount=10.0, merchant="Cafe", category="Food & Dining",
            description=None, date="2026-05-01"):
        return insert_trip_expense(trip_id, amount, merchant, category, description, date)


# ══════════════════════════════════════════════════════════════════════════════
# pages/trips.py
# ══════════════════════════════════════════════════════════════════════════════

class TestFmtRange(unittest.TestCase):
    def test_no_start_means_no_expenses(self):
        self.assertEqual(trips_page._fmt_range(None, None), "No expenses yet")

    def test_same_day_shows_single_date(self):
        self.assertEqual(trips_page._fmt_range("2026-05-01", "2026-05-01"), "2026-05-01")

    def test_range_uses_arrow(self):
        self.assertEqual(trips_page._fmt_range("2026-05-01", "2026-05-04"),
                         "2026-05-01  →  2026-05-04")


class TestTripCard(unittest.TestCase):
    def _trip(self, **kw):
        base = {"id": 7, "name": "Lisbon", "start_date": "2026-05-01",
                "end_date": "2026-05-03", "total": 123.456, "count": 3}
        base.update(kw)
        return base

    def test_shows_name_total_and_count(self):
        text = _text(trips_page._trip_card(self._trip()))
        self.assertIn("Lisbon", text)
        self.assertIn("€123.46", text)
        self.assertIn("3 expenses", text)

    def test_singular_expense_label(self):
        self.assertIn("1 expense", _text(trips_page._trip_card(self._trip(count=1))))
        self.assertNotIn("1 expenses", _text(trips_page._trip_card(self._trip(count=1))))

    def test_empty_trip_shows_placeholder_range(self):
        card = trips_page._trip_card(self._trip(start_date=None, end_date=None, total=0.0, count=0))
        self.assertIn("No expenses yet", _text(card))
        self.assertIn("0 expenses", _text(card))

    def test_buttons_carry_trip_id(self):
        card = trips_page._trip_card(self._trip(id=42))
        ids = [b.id for b in _find(card, dbc.Button)]
        self.assertIn({"type": "open-trip-btn", "index": 42}, ids)
        self.assertIn({"type": "del-trip-btn", "index": 42}, ids)


class TestRefreshTrips(BaseTripPageTest):
    def test_empty_state(self):
        out = trips_page.refresh_trips("/trips")
        self.assertIn("No trips yet", _text(out))

    def test_lists_a_card_per_trip(self):
        create_trip("A")
        create_trip("B")
        out = trips_page.refresh_trips("/trips")
        self.assertEqual(len(out), 2)
        text = _text(out)
        self.assertIn("A", text)
        self.assertIn("B", text)


class TestToggleModal(unittest.TestCase):
    def test_new_trip_button_opens_and_clears(self):
        with patch.object(dash, "callback_context", _ctx("new-trip-btn")):
            self.assertEqual(trips_page.toggle_modal(1, None, False), (True, "", ""))

    def test_cancel_closes_and_clears(self):
        with patch.object(dash, "callback_context", _ctx("new-trip-cancel")):
            self.assertEqual(trips_page.toggle_modal(1, 1, True), (False, "", ""))

    def test_nothing_triggered_keeps_state(self):
        with patch.object(dash, "callback_context", _ctx()):
            self.assertEqual(trips_page.toggle_modal(None, None, True),
                             (True, NO_UPDATE, NO_UPDATE))


class TestValidateAndClose(unittest.TestCase):
    def test_empty_name_keeps_modal_open_with_error(self):
        for name in (None, "", "   "):
            is_open, msg = trips_page.validate_and_close(1, name)
            self.assertTrue(is_open, repr(name))
            self.assertIn("cannot be empty", msg)

    def test_valid_name_closes_modal(self):
        self.assertEqual(trips_page.validate_and_close(1, "Rome"), (False, ""))


class TestCreateAndRedirect(BaseTripPageTest):
    def test_creates_trip_and_redirects_to_it(self):
        href = trips_page.create_and_redirect(1, "  Rome  ")
        trips = fetch_trips()
        self.assertEqual(len(trips), 1)
        self.assertEqual(trips[0]["name"], "Rome")  # stripped
        self.assertEqual(href, f"/trip?id={trips[0]['id']}")

    def test_blank_name_creates_nothing(self):
        for name in (None, "", "   "):
            self.assertEqual(trips_page.create_and_redirect(1, name), NO_UPDATE)
        self.assertEqual(fetch_trips(), [])

    def test_no_clicks_creates_nothing(self):
        self.assertEqual(trips_page.create_and_redirect(0, "Rome"), NO_UPDATE)
        self.assertEqual(fetch_trips(), [])


class TestOpenDeleteTripModal(BaseTripPageTest):
    def test_click_opens_modal_with_trip_name_and_stores_id(self):
        tid = create_trip("Porto")
        trig = _pattern_trigger("del-trip-btn", tid)
        with patch.object(dash, "callback_context", _ctx(triggered=trig)):
            is_open, body, stored = trips_page.open_del_trip_modal([1])
        self.assertTrue(is_open)
        self.assertEqual(stored, tid)
        self.assertIn("Porto", _text(body))

    def test_unknown_trip_falls_back_to_id_label(self):
        trig = _pattern_trigger("del-trip-btn", 999)
        with patch.object(dash, "callback_context", _ctx(triggered=trig)):
            is_open, body, stored = trips_page.open_del_trip_modal([1])
        self.assertTrue(is_open)
        self.assertIn("trip #999", _text(body))
        self.assertEqual(stored, 999)

    def test_falsy_click_value_is_ignored(self):
        # Dash fires the pattern callback with value None when cards are re-rendered
        trig = _pattern_trigger("del-trip-btn", 1, value=None)
        with patch.object(dash, "callback_context", _ctx(triggered=trig)):
            self.assertEqual(trips_page.open_del_trip_modal([None]),
                             (NO_UPDATE, NO_UPDATE, NO_UPDATE))

    def test_no_trigger(self):
        with patch.object(dash, "callback_context", _ctx()):
            self.assertEqual(trips_page.open_del_trip_modal([]),
                             (NO_UPDATE, NO_UPDATE, NO_UPDATE))


class TestHandleDelTripConfirm(BaseTripPageTest):
    def test_confirm_deletes_trip_and_expenses_and_refreshes_list(self):
        keep = create_trip("Keep")
        gone = create_trip("Gone")
        self.add(gone)
        with patch.object(dash, "callback_context", _ctx("confirm-del-trip-btn")):
            is_open, children = trips_page.handle_del_trip_confirm(1, None, gone)
        self.assertFalse(is_open)
        self.assertEqual([t["id"] for t in fetch_trips()], [keep])
        self.assertEqual(fetch_trip_expenses(gone), [])
        self.assertEqual(len(children), 1)

    def test_confirm_last_trip_shows_empty_state(self):
        tid = create_trip("Only")
        with patch.object(dash, "callback_context", _ctx("confirm-del-trip-btn")):
            _, children = trips_page.handle_del_trip_confirm(1, None, tid)
        self.assertIn("No trips yet", _text(children))

    def test_cancel_deletes_nothing(self):
        tid = create_trip("Stay")
        with patch.object(dash, "callback_context", _ctx("confirm-del-trip-cancel")):
            result = trips_page.handle_del_trip_confirm(None, 1, tid)
        self.assertEqual(result, (False, NO_UPDATE))
        self.assertEqual(len(fetch_trips()), 1)

    def test_confirm_without_pending_id_deletes_nothing(self):
        create_trip("Stay")
        with patch.object(dash, "callback_context", _ctx("confirm-del-trip-btn")):
            result = trips_page.handle_del_trip_confirm(1, None, None)
        self.assertEqual(result, (False, NO_UPDATE))
        self.assertEqual(len(fetch_trips()), 1)


class TestHandleOpen(unittest.TestCase):
    def test_click_navigates_to_trip(self):
        trig = _pattern_trigger("open-trip-btn", 5)
        with patch.object(dash, "callback_context", _ctx(triggered=trig)):
            self.assertEqual(trips_page.handle_open([1]), "/trip?id=5")

    def test_falsy_value_is_ignored(self):
        trig = _pattern_trigger("open-trip-btn", 5, value=None)
        with patch.object(dash, "callback_context", _ctx(triggered=trig)):
            self.assertEqual(trips_page.handle_open([None]), NO_UPDATE)

    def test_no_trigger(self):
        with patch.object(dash, "callback_context", _ctx()):
            self.assertEqual(trips_page.handle_open([]), NO_UPDATE)


# ══════════════════════════════════════════════════════════════════════════════
# pages/trip_detail.py — helpers
# ══════════════════════════════════════════════════════════════════════════════

class TestDetailHelpers(unittest.TestCase):
    def test_fmt_iso_to_dd_mm_yyyy(self):
        self.assertEqual(td._fmt("2026-05-01"), "01/05/2026")

    def test_fmt_returns_input_when_not_iso(self):
        self.assertEqual(td._fmt("garbage"), "garbage")
        self.assertEqual(td._fmt(None), None)

    def test_days_count_inclusive(self):
        self.assertEqual(td._days_count("2026-05-01", "2026-05-01"), 1)
        self.assertEqual(td._days_count("2026-05-01", "2026-05-04"), 4)

    def test_days_count_zero_for_missing_or_bad_dates(self):
        self.assertEqual(td._days_count(None, None), 0)
        self.assertEqual(td._days_count("2026-05-01", None), 0)
        self.assertEqual(td._days_count("nope", "2026-05-04"), 0)

    def test_layout_contains_expected_stores_and_modals(self):
        ids = {getattr(n, "id", None) for n in _walk(td.layout())}
        for expected in ("trip-location", "trip-id-store", "te-pending-force-data",
                         "confirm-delete-trip-expense-modal", "edit-trip-expense-modal",
                         "trip-detail-content", "te-feedback", "trip-csv-feedback"):
            self.assertIn(expected, ids)


# ══════════════════════════════════════════════════════════════════════════════
# pages/trip_detail.py — render_trip
# ══════════════════════════════════════════════════════════════════════════════

class TestRenderTrip(BaseTripPageTest):
    def test_no_search_means_no_trip_selected(self):
        content, tid = td.render_trip(None)
        self.assertIn("No trip selected", _text(content))
        self.assertIsNone(tid)

    def test_search_without_id_or_with_bad_id(self):
        for search in ("?foo=bar", "?id=abc", "?id=", "?id=0"):
            content, tid = td.render_trip(search)
            self.assertIn("No trip selected", _text(content), search)
            self.assertIsNone(tid, search)

    def test_unknown_trip(self):
        content, tid = td.render_trip("?id=999")
        self.assertIn("Trip not found", _text(content))
        self.assertIsNone(tid)

    def test_id_is_found_among_other_query_params(self):
        t = create_trip("Oslo")
        content, tid = td.render_trip(f"?x=1&id={t}")
        self.assertEqual(tid, t)
        self.assertIn("Oslo", _text(content))

    def test_empty_trip(self):
        t = create_trip("Empty")
        content, tid = td.render_trip(f"?id={t}")
        text = _text(content)
        self.assertEqual(tid, t)
        self.assertIn("No expenses yet", text)
        self.assertIn("0 days", text)
        self.assertIn("0 expenses", text)
        self.assertIn("€0.00", text)

    def test_summary_cards_and_table_rows(self):
        t = create_trip("Lisbon")
        self.add(t, 10.0, "Cafe", "Food & Dining", "coffee", "2026-05-01")
        self.add(t, 20.5, None, "Commute", None, "2026-05-03")
        content, _ = td.render_trip(f"?id={t}")
        text = _text(content)
        self.assertIn("Lisbon", text)
        self.assertIn("01/05/2026 – 03/05/2026", text)
        self.assertIn("€30.50", text)
        self.assertIn("3 days", text)
        self.assertIn("2 expenses", text)
        # rows: formatted date, em dash for missing merchant/description
        self.assertIn("Cafe", text)
        self.assertIn("coffee", text)
        self.assertIn("—", text)
        self.assertIn("€20.50", text)

    def test_single_day_trip_uses_singular_day_and_expense(self):
        t = create_trip("Day trip")
        self.add(t, 5.0, "Bakery", date="2026-05-01")
        text = _text(td.render_trip(f"?id={t}")[0])
        self.assertIn("1 day", text)
        self.assertNotIn("1 days", text)
        self.assertIn("1 expense", text)
        self.assertNotIn("1 expenses", text)

    def test_row_buttons_carry_expense_id(self):
        t = create_trip("Buttons")
        eid = self.add(t)
        content, _ = td.render_trip(f"?id={t}")
        ids = [getattr(b, "id", None) for b in _find(content, dbc.Button)]
        self.assertIn({"type": "edit-trip-expense", "index": eid}, ids)
        self.assertIn({"type": "del-trip-expense", "index": eid}, ids)

    def test_daily_chart_sums_per_day_in_date_order(self):
        t = create_trip("Chart")
        self.add(t, 10.0, "A", date="2026-05-03")
        self.add(t, 5.0, "B", date="2026-05-01")
        self.add(t, 7.0, "C", date="2026-05-01")
        content, _ = td.render_trip(f"?id={t}")
        graph = _find(content, dcc.Graph)[0]
        trace = graph.figure.data[0]
        self.assertEqual(list(trace.x), ["01/05/2026", "03/05/2026"])
        self.assertEqual(list(trace.y), [12.0, 10.0])

    def test_empty_trip_chart_is_placeholder_annotation(self):
        t = create_trip("Empty")
        content, _ = td.render_trip(f"?id={t}")
        graph = _find(content, dcc.Graph)[0]
        self.assertEqual(graph.figure.layout.annotations[0].text, "No expenses yet")

    def test_chart_column_width_grows_with_number_of_days(self):
        def chart_md(n_days):
            t = create_trip(f"T{n_days}")
            for d in range(1, n_days + 1):
                self.add(t, 1.0, f"M{d}", date=f"2026-05-{d:02d}")
            content, _ = td.render_trip(f"?id={t}")
            for col in _find(content, dbc.Col):
                if _find(col, dcc.Graph):
                    return col.md
        self.assertEqual(chart_md(3), 4)
        self.assertEqual(chart_md(4), 6)
        self.assertEqual(chart_md(6), 6)
        self.assertEqual(chart_md(7), 12)


# ══════════════════════════════════════════════════════════════════════════════
# pages/trip_detail.py — simple toggles
# ══════════════════════════════════════════════════════════════════════════════

class TestToggles(unittest.TestCase):
    def test_toggle_add_expense(self):
        self.assertTrue(td.toggle_add_expense(1, False))
        self.assertFalse(td.toggle_add_expense(2, True))

    def test_toggle_import_csv(self):
        self.assertTrue(td.toggle_import_csv(1, False))
        self.assertFalse(td.toggle_import_csv(2, True))

    def test_toggle_chart(self):
        self.assertEqual(td.toggle_chart(1, False), (True, "▲ Hide Chart"))
        self.assertEqual(td.toggle_chart(2, True), (False, "▼ Daily Spending"))


# ══════════════════════════════════════════════════════════════════════════════
# pages/trip_detail.py — add expense / duplicate detection / force save
# ══════════════════════════════════════════════════════════════════════════════

class TestSaveExpense(BaseTripPageTest):
    def setUp(self):
        super().setUp()
        self.tid = create_trip("Trip")
        self.search = f"?id={self.tid}"

    def save(self, amount=12.5, merchant="Cafe", category="Food & Dining",
             description="lunch", date_val="2026-05-02", trip_id="default", n_clicks=1):
        trip_id = self.tid if trip_id == "default" else trip_id
        return td.save_expense(n_clicks, amount, merchant, category, description,
                               date_val, trip_id, self.search)

    def test_no_clicks_is_a_noop(self):
        self.assertEqual(self.save(n_clicks=0), (NO_UPDATE,) * 5)
        self.assertEqual(fetch_trip_expenses(self.tid), [])

    def test_invalid_amounts_rejected(self):
        for amount in (None, 0, -1, "0"):
            fb, content, tid, pending, style = self.save(amount=amount)
            self.assertIn("greater than 0", _text(fb), repr(amount))
            self.assertEqual((content, tid, pending, style), (NO_UPDATE, NO_UPDATE, None, td._FORCE_BTN_HIDE))
        self.assertEqual(fetch_trip_expenses(self.tid), [])

    def test_missing_category_rejected(self):
        fb, *_ = self.save(category=None)
        self.assertIn("Category is required", _text(fb))
        self.assertEqual(fetch_trip_expenses(self.tid), [])

    def test_missing_trip_rejected(self):
        fb, *_ = self.save(trip_id=None)
        self.assertIn("Trip not found", _text(fb))

    def test_saves_expense_and_rerenders(self):
        fb, content, tid, pending, style = self.save(merchant="  Cafe  ", description="  lunch  ",
                                                     date_val="2026-05-02T00:00:00")
        rows = fetch_trip_expenses(self.tid)
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]["merchant"], rows[0]["description"], rows[0]["date"]),
                         ("Cafe", "lunch", "2026-05-02"))  # stripped, date cut to 10 chars
        self.assertEqual(rows[0]["amount"], 12.5)
        self.assertIn("Expense saved", _text(fb))
        self.assertEqual(tid, self.tid)
        self.assertIn("Cafe", _text(content))
        self.assertIsNone(pending)
        self.assertEqual(style, td._FORCE_BTN_HIDE)

    def test_blank_merchant_and_description_stored_as_null(self):
        self.save(merchant="   ", description="  ")
        row = fetch_trip_expenses(self.tid)[0]
        self.assertIsNone(row["merchant"])
        self.assertIsNone(row["description"])

    def test_missing_date_defaults_to_today(self):
        self.save(date_val=None)
        from datetime import date
        self.assertEqual(fetch_trip_expenses(self.tid)[0]["date"], date.today().isoformat())

    def test_duplicate_is_not_saved_and_offers_force_save(self):
        self.add(self.tid, 12.5, "Cafe", date="2026-05-02")
        fb, content, tid, pending, style = self.save()
        self.assertEqual(len(fetch_trip_expenses(self.tid)), 1)
        self.assertIn("already exists", _text(fb))
        self.assertIn("Cafe", _text(fb))
        self.assertEqual(style, td._FORCE_BTN_SHOW)
        self.assertEqual(pending["trip_id"], self.tid)
        self.assertEqual(pending["amount"], 12.5)
        self.assertEqual(pending["merchant"], "Cafe")
        self.assertEqual(pending["date"], "2026-05-02")
        self.assertEqual(pending["description"], "lunch")
        self.assertEqual((content, tid), (NO_UPDATE, NO_UPDATE))

    def test_same_amount_on_a_different_day_is_not_a_duplicate(self):
        self.add(self.tid, 12.5, "Cafe", date="2026-05-01")
        fb, *_ = self.save(date_val="2026-05-02")
        self.assertIn("Expense saved", _text(fb))
        self.assertEqual(len(fetch_trip_expenses(self.tid)), 2)

    def test_expenses_without_merchant_are_never_flagged_as_duplicates(self):
        self.add(self.tid, 12.5, None, date="2026-05-02")
        fb, *_ = self.save(merchant=None)
        self.assertIn("Expense saved", _text(fb))
        self.assertEqual(len(fetch_trip_expenses(self.tid)), 2)

    def test_duplicate_in_another_trip_is_allowed(self):
        other = create_trip("Other")
        self.add(other, 12.5, "Cafe", date="2026-05-02")
        fb, *_ = self.save()
        self.assertIn("Expense saved", _text(fb))


class TestForceSaveExpense(BaseTripPageTest):
    def setUp(self):
        super().setUp()
        self.tid = create_trip("Trip")
        self.pending = {"trip_id": self.tid, "amount": 12.5, "merchant": "Cafe",
                        "category": "Food & Dining", "description": "lunch", "date": "2026-05-02"}

    def test_inserts_pending_expense_despite_duplicate(self):
        self.add(self.tid, 12.5, "Cafe", date="2026-05-02")
        fb, content, tid, pending, style = td.force_save_expense(1, self.pending, f"?id={self.tid}")
        self.assertEqual(len(fetch_trip_expenses(self.tid)), 2)
        self.assertIn("Expense saved", _text(fb))
        self.assertEqual(tid, self.tid)
        self.assertIsNone(pending)
        self.assertEqual(style, td._FORCE_BTN_HIDE)

    def test_noop_without_clicks_or_pending(self):
        self.assertEqual(td.force_save_expense(0, self.pending, ""), (NO_UPDATE,) * 5)
        self.assertEqual(td.force_save_expense(1, None, ""), (NO_UPDATE,) * 5)
        self.assertEqual(fetch_trip_expenses(self.tid), [])

    def test_reset_force_save_state_on_navigation(self):
        self.assertEqual(td.reset_force_save_state("?id=1"), ("", None, td._FORCE_BTN_HIDE))


# ══════════════════════════════════════════════════════════════════════════════
# pages/trip_detail.py — CSV import
# ══════════════════════════════════════════════════════════════════════════════

class TestImportCsv(BaseTripPageTest):
    def setUp(self):
        super().setUp()
        self.tid = create_trip("Trip")
        self.search = f"?id={self.tid}"
        # Never call Gemini: categorise everything as Groceries unless a test overrides it
        self.classify_patcher = patch.object(
            td, "classify_expenses", side_effect=lambda items: ["Groceries"] * len(items))
        self.classify = self.classify_patcher.start()

    def tearDown(self):
        self.classify_patcher.stop()
        super().tearDown()

    def run_import(self, csv_text, trip_id="default", filename="t.csv", encoding="utf-8"):
        trip_id = self.tid if trip_id == "default" else trip_id
        return td.import_csv(_csv_contents(csv_text, encoding), filename, trip_id, self.search)

    def test_no_contents_is_a_noop(self):
        self.assertEqual(td.import_csv(None, "x.csv", self.tid, self.search), (NO_UPDATE,) * 3)

    def test_missing_trip_id(self):
        fb, content, tid = self.run_import("date,cost\n2026-05-01,5\n", trip_id=None)
        self.assertIn("Trip ID missing", _text(fb))
        self.assertEqual((content, tid), (NO_UPDATE, NO_UPDATE))

    def test_imports_rows_with_categories_and_rerenders(self):
        fb, content, tid = self.run_import(
            "Date,Cost,Item\n13/05/2026,4.50,Bakery\n14/05/2026,20,Hotel bar\n")
        rows = fetch_trip_expenses(self.tid)
        self.assertEqual([(r["date"], r["amount"], r["merchant"], r["category"], r["description"])
                          for r in rows],
                         [("2026-05-13", 4.5, "Bakery", "Groceries", None),
                          ("2026-05-14", 20.0, "Hotel bar", "Groceries", None)])
        self.assertIn("Imported 2 expenses", _text(fb))
        self.assertNotIn("skipped", _text(fb))
        self.assertEqual(tid, self.tid)
        self.assertIn("Bakery", _text(content))

    def test_classifier_receives_description_merchant_amount_date(self):
        self.run_import("date,amount,merchant\n13/05/2026,3,Kiosk\n")
        (items,), _ = self.classify.call_args
        self.assertEqual(items, [{"description": "Kiosk", "merchant": "Kiosk",
                                  "amount": 3.0, "date": "2026-05-13"}])

    def test_semicolon_delimiter_and_decimal_comma(self):
        self.run_import("datum;betrag;beschreibung\n13/05/2026;4,50;Bäckerei\n")
        row = fetch_trip_expenses(self.tid)[0]
        self.assertEqual((row["amount"], row["merchant"]), (4.5, "Bäckerei"))

    def test_latin1_file_is_decoded(self):
        self.run_import("date;kosten;laden\n13/05/2026;4,50;Café\n", encoding="latin-1")
        self.assertEqual(fetch_trip_expenses(self.tid)[0]["merchant"], "Café")

    def test_currency_symbols_are_stripped_from_amounts(self):
        self.run_import("date,price,name\n13/05/2026,€12.30,Shop\n")
        self.assertEqual(fetch_trip_expenses(self.tid)[0]["amount"], 12.3)

    def test_cost_column_prefix_fallback(self):
        self.run_import("date,Cost for 2,name\n13/05/2026,40,Dinner\n")
        self.assertEqual(fetch_trip_expenses(self.tid)[0]["amount"], 40.0)

    def test_header_case_and_whitespace_are_ignored(self):
        self.run_import("  DATE ,  Amount ,Name\n13/05/2026,5,Shop\n")
        self.assertEqual(len(fetch_trip_expenses(self.tid)), 1)

    def test_missing_name_column_imports_with_null_merchant(self):
        self.run_import("date,amount\n13/05/2026,5\n")
        row = fetch_trip_expenses(self.tid)[0]
        self.assertIsNone(row["merchant"])
        (items,), _ = self.classify.call_args
        self.assertEqual(items[0]["description"], "import")

    def test_blank_and_nan_names_become_null(self):
        self.run_import("date,amount,name\n13/05/2026,5,\n14/05/2026,6,nan\n")
        self.assertEqual([r["merchant"] for r in fetch_trip_expenses(self.tid)], [None, None])

    def test_zero_and_unparseable_amounts_are_skipped_and_counted(self):
        fb, *_ = self.run_import(
            "date,amount,name\n13/05/2026,0,Free\n14/05/2026,abc,Bad\n15/05/2026,7,Good\n")
        self.assertEqual([r["merchant"] for r in fetch_trip_expenses(self.tid)], ["Good"])
        self.assertIn("Imported 1 expenses (2 rows skipped)", _text(fb))

    def test_bad_date_row_is_skipped(self):
        fb, *_ = self.run_import("date,amount,name\nnot-a-date,5,X\n13/05/2026,6,Y\n")
        self.assertEqual([r["merchant"] for r in fetch_trip_expenses(self.tid)], ["Y"])
        self.assertIn("1 rows skipped", _text(fb))

    def test_undetectable_columns_reports_what_was_found(self):
        fb, content, tid = self.run_import("foo,bar\n1,2\n")
        text = _text(fb)
        self.assertIn("Could not detect date or amount columns", text)
        self.assertIn("foo", text)
        self.assertEqual((content, tid), (NO_UPDATE, NO_UPDATE))
        self.assertEqual(fetch_trip_expenses(self.tid), [])

    def test_missing_date_column_only(self):
        fb, *_ = self.run_import("amount,name\n5,X\n")
        self.assertIn("Could not detect date or amount columns", _text(fb))

    def test_no_valid_rows(self):
        fb, content, tid = self.run_import("date,amount\n13/05/2026,0\n14/05/2026,x\n")
        self.assertIn("No valid rows found in CSV (skipped 2 rows)", _text(fb))
        self.assertEqual((content, tid), (NO_UPDATE, NO_UPDATE))
        self.assertEqual(fetch_trip_expenses(self.tid), [])

    def test_unparseable_csv_is_reported(self):
        fb, content, tid = self.run_import("")
        self.assertIn("Could not parse CSV", _text(fb))
        self.assertEqual((content, tid), (NO_UPDATE, NO_UPDATE))

    def test_classifier_exception_falls_back_to_miscellaneous(self):
        self.classify.side_effect = RuntimeError("API down")
        fb, *_ = self.run_import("date,amount,name\n13/05/2026,5,X\n14/05/2026,6,Y\n")
        self.assertEqual([r["category"] for r in fetch_trip_expenses(self.tid)],
                         ["Miscellaneous", "Miscellaneous"])
        self.assertIn("Imported 2 expenses", _text(fb))

    def test_classifier_wrong_length_falls_back_to_miscellaneous(self):
        self.classify.side_effect = lambda items: ["Groceries"]
        self.run_import("date,amount,name\n13/05/2026,5,X\n14/05/2026,6,Y\n")
        self.assertEqual([r["category"] for r in fetch_trip_expenses(self.tid)],
                         ["Miscellaneous", "Miscellaneous"])

    def test_classifier_empty_result_falls_back_to_miscellaneous(self):
        self.classify.side_effect = lambda items: []
        self.run_import("date,amount,name\n13/05/2026,5,X\n")
        self.assertEqual(fetch_trip_expenses(self.tid)[0]["category"], "Miscellaneous")

    def test_import_does_not_deduplicate_against_existing_expenses(self):
        # Documents current behaviour: the CSV import (unlike the manual form) has no duplicate check.
        self.add(self.tid, 5.0, "X", date="2026-05-13")
        self.run_import("date,amount,name\n13/05/2026,5,X\n")
        self.assertEqual(len(fetch_trip_expenses(self.tid)), 2)

    @unittest.expectedFailure
    def test_iso_dates_are_not_day_month_swapped(self):
        # BUG (pages/trip_detail.py:497): pd.to_datetime(..., dayfirst=True) swaps day and
        # month for ISO dates on this pandas version: "2026-06-01" -> 2026-01-06.
        # Remove @expectedFailure once the importer parses ISO dates correctly.
        self.run_import("date,amount,name\n2026-06-01,5,X\n")
        self.assertEqual(fetch_trip_expenses(self.tid)[0]["date"], "2026-06-01")


# ══════════════════════════════════════════════════════════════════════════════
# pages/trip_detail.py — delete expense
# ══════════════════════════════════════════════════════════════════════════════

class TestDeleteExpenseFlow(BaseTripPageTest):
    def setUp(self):
        super().setUp()
        self.tid = create_trip("Trip")
        self.eid = self.add(self.tid, 9.0, "Cafe")
        self.search = f"?id={self.tid}"

    def test_click_opens_modal_and_stores_expense_id(self):
        trig = _pattern_trigger("del-trip-expense", self.eid)
        with patch.object(dash, "callback_context", _ctx(triggered=trig)):
            stored, is_open, body = td.open_del_trip_expense_modal([1])
        self.assertEqual((stored, is_open), (self.eid, True))
        self.assertIn("Permanently delete", _text(body))

    def test_falsy_click_is_ignored(self):
        trig = _pattern_trigger("del-trip-expense", self.eid, value=None)
        with patch.object(dash, "callback_context", _ctx(triggered=trig)):
            self.assertEqual(td.open_del_trip_expense_modal([None]), (NO_UPDATE,) * 3)

    def test_no_trigger(self):
        with patch.object(dash, "callback_context", _ctx()):
            self.assertEqual(td.open_del_trip_expense_modal([]), (NO_UPDATE,) * 3)

    def test_confirm_deletes_and_rerenders(self):
        with patch.object(dash, "callback_context", _ctx("confirm-del-trip-expense-btn")):
            is_open, content, tid = td.handle_del_trip_expense_confirm(1, None, self.eid, self.search)
        self.assertFalse(is_open)
        self.assertEqual(fetch_trip_expenses(self.tid), [])
        self.assertEqual(tid, self.tid)
        self.assertIn("No expenses yet", _text(content))

    def test_cancel_keeps_expense(self):
        with patch.object(dash, "callback_context", _ctx("confirm-del-trip-expense-cancel")):
            result = td.handle_del_trip_expense_confirm(None, 1, self.eid, self.search)
        self.assertEqual(result, (False, NO_UPDATE, NO_UPDATE))
        self.assertEqual(len(fetch_trip_expenses(self.tid)), 1)

    def test_confirm_without_pending_id_keeps_expense(self):
        with patch.object(dash, "callback_context", _ctx("confirm-del-trip-expense-btn")):
            result = td.handle_del_trip_expense_confirm(1, None, None, self.search)
        self.assertEqual(result, (False, NO_UPDATE, NO_UPDATE))
        self.assertEqual(len(fetch_trip_expenses(self.tid)), 1)


# ══════════════════════════════════════════════════════════════════════════════
# pages/trip_detail.py — edit expense
# ══════════════════════════════════════════════════════════════════════════════

class TestEditExpenseFlow(BaseTripPageTest):
    def setUp(self):
        super().setUp()
        self.tid = create_trip("Trip")
        self.eid = self.add(self.tid, 9.0, "Cafe", "Food & Dining", "note", "2026-05-01")
        self.search = f"?id={self.tid}"

    def test_click_opens_modal_prefilled(self):
        trig = _pattern_trigger("edit-trip-expense", self.eid)
        with patch.object(dash, "callback_context", _ctx(triggered=trig)):
            out = td.open_edit_expense_modal([1])
        self.assertEqual(out, (self.eid, True, 9.0, "Cafe", "Food & Dining", "note", "2026-05-01"))

    def test_click_on_missing_expense_is_ignored(self):
        trig = _pattern_trigger("edit-trip-expense", 999)
        with patch.object(dash, "callback_context", _ctx(triggered=trig)):
            self.assertEqual(td.open_edit_expense_modal([1]), (NO_UPDATE,) * 7)

    def test_falsy_click_and_no_trigger_are_ignored(self):
        trig = _pattern_trigger("edit-trip-expense", self.eid, value=None)
        with patch.object(dash, "callback_context", _ctx(triggered=trig)):
            self.assertEqual(td.open_edit_expense_modal([None]), (NO_UPDATE,) * 7)
        with patch.object(dash, "callback_context", _ctx()):
            self.assertEqual(td.open_edit_expense_modal([]), (NO_UPDATE,) * 7)

    def save(self, **overrides):
        args = dict(save_clicks=1, cancel_clicks=None, expense_id=self.eid, amount=15.0,
                    merchant="Bistro", category="Commute", description="taxi",
                    date_val="2026-05-04", search=self.search)
        args.update(overrides)
        with patch.object(dash, "callback_context", _ctx("edit-te-save")):
            return td.save_edit_expense(**args)

    def test_save_updates_expense_and_rerenders(self):
        is_open, content, tid, feedback = self.save()
        self.assertFalse(is_open)
        self.assertEqual(feedback, "")
        self.assertEqual(tid, self.tid)
        row = fetch_trip_expenses(self.tid)[0]
        self.assertEqual((row["amount"], row["merchant"], row["category"],
                          row["description"], row["date"]),
                         (15.0, "Bistro", "Commute", "taxi", "2026-05-04"))
        self.assertIn("Bistro", _text(content))

    def test_blank_merchant_and_description_stored_as_null(self):
        self.save(merchant="", description="")
        row = fetch_trip_expenses(self.tid)[0]
        self.assertIsNone(row["merchant"])
        self.assertIsNone(row["description"])

    def test_validation_errors_keep_modal_open_and_do_not_save(self):
        cases = [({"amount": None}, "greater than 0"), ({"amount": 0}, "greater than 0"),
                 ({"amount": -2}, "greater than 0"), ({"category": None}, "Category is required"),
                 ({"date_val": None}, "Date is required")]
        for overrides, message in cases:
            is_open, content, tid, feedback = self.save(**overrides)
            self.assertTrue(is_open, overrides)
            self.assertIn(message, _text(feedback), overrides)
            self.assertEqual((content, tid), (NO_UPDATE, NO_UPDATE))
        row = fetch_trip_expenses(self.tid)[0]
        self.assertEqual((row["amount"], row["merchant"]), (9.0, "Cafe"))

    def test_cancel_closes_without_saving(self):
        with patch.object(dash, "callback_context", _ctx("edit-te-cancel")):
            result = td.save_edit_expense(None, 1, self.eid, 99.0, "X", "Commute", "d",
                                          "2026-06-01", self.search)
        self.assertEqual(result, (False, NO_UPDATE, NO_UPDATE, ""))
        self.assertEqual(fetch_trip_expenses(self.tid)[0]["amount"], 9.0)

    def test_save_without_expense_id_or_clicks_is_a_noop(self):
        self.assertEqual(self.save(expense_id=None), (NO_UPDATE,) * 4)
        self.assertEqual(self.save(save_clicks=0), (NO_UPDATE,) * 4)
        self.assertEqual(fetch_trip_expenses(self.tid)[0]["amount"], 9.0)


if __name__ == "__main__":
    unittest.main()
