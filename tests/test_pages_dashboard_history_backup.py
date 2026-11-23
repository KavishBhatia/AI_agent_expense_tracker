# tests/test_pages_dashboard_history_backup.py
"""Callback and helper tests for pages/dashboard.py, pages/history.py and pages/backup.py.

Callbacks are plain functions (``@callback`` returns the original), so they are called
directly. ``dash.callback_context`` is replaced with a small fake where a callback reads
it. The expenses DB is always a temp file; backup paths and subprocess are mocked.
"""
import json
import os
import subprocess
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import dash
import dash_bootstrap_components as dbc
from dash import html

import expense_tracker_agent.db as db_module
from expense_tracker_agent.db import (
    delete_expense,
    fetch_expense,
    fetch_expenses,
    init_db,
    insert_expense,
    restore_expense,
    set_budget,
)

import pages.backup as backup
import pages.dashboard as dashboard
import pages.history as history

NO_UPDATE = dash.no_update


# ── helpers ───────────────────────────────────────────────────────────────────

def _temp_db() -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    os.unlink(f.name)
    return Path(f.name)


class BaseDbTest(unittest.TestCase):
    def setUp(self):
        self.tmp_db = _temp_db()
        self._patcher = patch.object(db_module, "DB_PATH", self.tmp_db)
        self._patcher.start()
        init_db()

    def tearDown(self):
        self._patcher.stop()
        if self.tmp_db.exists():
            self.tmp_db.unlink()


def _walk(node):
    """Yield a Dash component tree depth-first, including plain string/number leaves."""
    yield node
    children = getattr(node, "children", None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        yield from _walk(child)


def _text(node) -> str:
    return " ".join(str(n) for n in _walk(node) if isinstance(n, (str, int, float)))


def _find(node, cls):
    return [n for n in _walk(node) if isinstance(n, cls)]


def _fake_ctx(triggered=None, triggered_id=None):
    return SimpleNamespace(triggered=triggered or [], triggered_id=triggered_id)


def _trigger(component_type, index, prop, value):
    prop_id = json.dumps({"index": index, "type": component_type}, separators=(",", ":"))
    return {"prop_id": f"{prop_id}.{prop}", "value": value}


def _frozen_date(y, m, d):
    class _D(date):
        @classmethod
        def today(cls):
            return date(y, m, d)
    return _D


def _all_no_update(result, n):
    return len(result) == n and all(r is NO_UPDATE for r in result)


# ══════════════════════════════════════════════════════════════════════════════
# pages/dashboard.py
# ══════════════════════════════════════════════════════════════════════════════

class TestDateRange(unittest.TestCase):
    def _range(self, period, today=(2026, 7, 15)):
        with patch.object(dashboard, "date", _frozen_date(*today)):
            return dashboard._date_range(period)

    def test_last_14_days_is_inclusive_of_today(self):
        self.assertEqual(self._range("last_14_days"), ("2026-07-02", "2026-07-15"))

    def test_this_month(self):
        self.assertEqual(self._range("this_month"), ("2026-07-01", "2026-07-15"))

    def test_last_month(self):
        self.assertEqual(self._range("last_month"), ("2026-06-01", "2026-06-30"))

    def test_last_month_across_year_boundary(self):
        self.assertEqual(
            self._range("last_month", today=(2026, 1, 10)), ("2025-12-01", "2025-12-31")
        )

    def test_last_month_handles_short_february(self):
        self.assertEqual(
            self._range("last_month", today=(2026, 3, 5)), ("2026-02-01", "2026-02-28")
        )

    def test_last_3_months_starts_on_first_of_month(self):
        # 90 days before 2026-07-15 is 2026-04-16 -> snapped to 2026-04-01
        self.assertEqual(self._range("last_3_months"), ("2026-04-01", "2026-07-15"))

    def test_all_time_and_unknown_period_have_no_bounds(self):
        self.assertEqual(self._range("all_time"), (None, None))
        self.assertEqual(self._range("nonsense"), (None, None))

    def test_every_dropdown_period_is_handled(self):
        for key in dashboard._PERIODS:
            start, end = self._range(key)
            if key != "all_time":
                self.assertLessEqual(start, end, key)

    def test_current_month_range(self):
        with patch.object(dashboard, "date", _frozen_date(2026, 7, 15)):
            self.assertEqual(dashboard._current_month_range(), ("2026-07-01", "2026-07-15"))


class TestRenderBudgetBars(BaseDbTest):
    MONTH = ("2026-06-01", "2026-06-30")

    def _bars(self, budgets):
        return dashboard._render_budget_bars(budgets, *self.MONTH)

    def _progress(self, budgets):
        bars = self._bars(budgets)
        return [_find(b, dbc.Progress)[0] for b in bars]

    def test_no_budgets_shows_hint(self):
        bars = self._bars({})
        self.assertEqual(len(bars), 1)
        self.assertIn("No budgets set", _text(bars[0]))

    def test_below_80_percent_is_success(self):
        insert_expense(79.0, "Groceries", "food", date="2026-06-10")
        p = self._progress({"Groceries": 100.0})[0]
        self.assertEqual(p.color, "success")
        self.assertAlmostEqual(p.value, 79.0)

    def test_exactly_80_percent_is_warning(self):
        insert_expense(80.0, "Groceries", "food", date="2026-06-10")
        self.assertEqual(self._progress({"Groceries": 100.0})[0].color, "warning")

    def test_just_below_100_percent_is_warning(self):
        insert_expense(99.0, "Groceries", "food", date="2026-06-10")
        self.assertEqual(self._progress({"Groceries": 100.0})[0].color, "warning")

    def test_exactly_100_percent_is_danger(self):
        insert_expense(100.0, "Groceries", "food", date="2026-06-10")
        self.assertEqual(self._progress({"Groceries": 100.0})[0].color, "danger")

    def test_over_budget_is_danger_and_bar_is_capped_but_label_is_not(self):
        insert_expense(250.0, "Groceries", "food", date="2026-06-10")
        bars = self._bars({"Groceries": 100.0})
        p = _find(bars[0], dbc.Progress)[0]
        self.assertEqual(p.color, "danger")
        self.assertEqual(p.value, 100)
        self.assertIn("€250 / €100 · 250%", _text(bars[0]))

    def test_label_shows_category_spend_limit_and_percent(self):
        insert_expense(30.0, "Groceries", "a", date="2026-06-02")
        insert_expense(20.0, "Groceries", "b", date="2026-06-03")
        text = _text(self._bars({"Groceries": 200.0})[0])
        self.assertIn("Groceries", text)
        self.assertIn("€50 / €200 · 25%", text)

    def test_category_without_spend_is_zero_percent_success(self):
        p = self._progress({"Travel": 300.0})[0]
        self.assertEqual(p.value, 0)
        self.assertEqual(p.color, "success")

    def test_only_spend_inside_the_month_counts(self):
        insert_expense(500.0, "Groceries", "last month", date="2026-05-31")
        insert_expense(500.0, "Groceries", "next month", date="2026-07-01")
        insert_expense(10.0, "Groceries", "in month", date="2026-06-15")
        self.assertIn("€10 / €100", _text(self._bars({"Groceries": 100.0})[0]))

    def test_only_matching_category_counts(self):
        insert_expense(90.0, "Commute", "train", date="2026-06-10")
        self.assertIn("€0 / €100", _text(self._bars({"Groceries": 100.0})[0]))

    def test_deleted_expenses_do_not_count(self):
        eid = insert_expense(90.0, "Groceries", "food", date="2026-06-10")
        delete_expense(eid)
        self.assertIn("€0 / €100", _text(self._bars({"Groceries": 100.0})[0]))

    def test_bars_are_sorted_by_category(self):
        bars = self._bars({"Travel": 100.0, "Alcohol": 100.0, "Groceries": 100.0})
        order = [_text(b).split(" ")[0] for b in bars]
        self.assertEqual(order, ["Alcohol", "Groceries", "Travel"])

    def test_zero_limit_does_not_divide_by_zero(self):
        insert_expense(10.0, "Groceries", "food", date="2026-06-10")
        p = self._progress({"Groceries": 0.0})[0]
        self.assertEqual(p.value, 0.0)
        self.assertEqual(p.color, "success")


class TestUpdateBudgetSection(BaseDbTest):
    def test_renders_card_with_bars_for_saved_budgets(self):
        set_budget("Groceries", 100.0)
        insert_expense(85.0, "Groceries", "food", date="2026-06-10")
        with patch.object(dashboard, "_current_month_range", return_value=("2026-06-01", "2026-06-30")):
            card = dashboard.update_budget_section(None, None)
        text = _text(card)
        self.assertIn("Monthly Budgets", text)
        self.assertIn("€85 / €100 · 85%", text)
        self.assertEqual(_find(card, dbc.Progress)[0].color, "warning")

    def test_renders_hint_without_budgets(self):
        card = dashboard.update_budget_section(None, None)
        self.assertIn("No budgets set", _text(card))


class TestToggleBudgetCollapse(unittest.TestCase):
    def test_opens_with_down_arrow(self):
        self.assertEqual(dashboard.toggle_budget_collapse(1, False), (True, "Monthly Budgets ▼"))

    def test_closes_with_right_arrow(self):
        self.assertEqual(dashboard.toggle_budget_collapse(2, True), (False, "Monthly Budgets ▶"))


class TestUpdateDashboard(BaseDbTest):
    def test_returns_kpis_and_seven_figures(self):
        today = date.today().isoformat()
        insert_expense(10.0, "Groceries", "a", date=today)
        insert_expense(5.5, "Commute", "b", date=today)
        result = dashboard.update_dashboard("all_time", None)
        self.assertEqual(len(result), 8)
        cards = result[0]
        self.assertEqual(len(cards), 3)
        self.assertIn("Total Spent €15.50", _text(html.Div(cards[0])))
        self.assertIn("Transactions 2", _text(html.Div(cards[1])))
        self.assertIn("Avg / Day €15.50", _text(html.Div(cards[2])))  # one day only

    def test_empty_database_yields_zero_kpis(self):
        text = _text(html.Div(dashboard.update_dashboard("all_time", None)[0]))
        self.assertIn("Total Spent €0.00", text)
        self.assertIn("Transactions 0", text)
        self.assertIn("Avg / Day €0.00", text)

    def test_period_filters_kpis(self):
        today = date.today()
        insert_expense(10.0, "Groceries", "recent", date=today.isoformat())
        insert_expense(99.0, "Groceries", "old", date=(today - timedelta(days=200)).isoformat())
        recent = _text(html.Div(dashboard.update_dashboard("last_14_days", None)[0]))
        everything = _text(html.Div(dashboard.update_dashboard("all_time", None)[0]))
        self.assertIn("€10.00", recent)
        self.assertIn("€109.00", everything)

    def test_deleted_expenses_are_excluded(self):
        eid = insert_expense(10.0, "Groceries", "a", date=date.today().isoformat())
        delete_expense(eid)
        text = _text(html.Div(dashboard.update_dashboard("all_time", None)[0]))
        self.assertIn("Transactions 0", text)

    def test_a_failing_chart_becomes_an_error_figure_without_breaking_the_others(self):
        with patch.object(dashboard.charts, "fig_monthly_trend", side_effect=ValueError("boom")):
            result = dashboard.update_dashboard("all_time", None)
        trend = result[1]
        self.assertEqual(trend.layout.annotations[0].text, "Chart error: boom")
        for fig in result[2:]:
            self.assertFalse(any("Chart error" in (a.text or "") for a in fig.layout.annotations))

    def test_passes_period_bounds_to_charts(self):
        with patch.object(dashboard.charts, "kpi_stats",
                          return_value={"total": 0, "count": 0, "avg_per_day": 0}) as kpi, \
             patch.object(dashboard, "_date_range", return_value=("2026-01-01", "2026-01-31")):
            dashboard.update_dashboard("this_month", None)
        kpi.assert_called_once_with("2026-01-01", "2026-01-31")


class TestShowDayDetail(BaseDbTest):
    @staticmethod
    def _click(x):
        return {"points": [{"x": x}]}

    def test_no_click_data_is_no_update(self):
        self.assertIs(dashboard.show_day_detail(None), NO_UPDATE)

    def test_lists_the_days_transactions_with_total(self):
        insert_expense(12.5, "Groceries", "milk", merchant="Lidl", date="2026-06-05")
        insert_expense(7.5, "Commute", "bus", date="2026-06-05")
        insert_expense(99.0, "Groceries", "other day", merchant="Lidl", date="2026-06-06")
        card = dashboard.show_day_detail(self._click("05/06/2026"))
        text = _text(card)
        self.assertIn("Breakdown for 05/06/2026", text)
        self.assertIn("2 transactions · €20.00 total", text)
        self.assertIn("Lidl", text)
        self.assertIn("milk", text)
        self.assertNotIn("other day", text)

    def test_chart_date_is_parsed_day_first(self):
        # 03/06/2026 is 3 June, not 6 March
        insert_expense(4.0, "Groceries", "june", date="2026-06-03")
        insert_expense(8.0, "Groceries", "march", date="2026-03-06")
        text = _text(dashboard.show_day_detail(self._click("03/06/2026")))
        self.assertIn("june", text)
        self.assertNotIn("march", text)

    def test_missing_merchant_is_shown_as_dash(self):
        insert_expense(4.0, "Groceries", "no store", date="2026-06-03")
        self.assertIn("—", _text(dashboard.show_day_detail(self._click("03/06/2026"))))

    def test_day_without_transactions_shows_info_alert(self):
        result = dashboard.show_day_detail(self._click("07/06/2026"))
        self.assertIsInstance(result, dbc.Alert)
        self.assertEqual(result.color, "info")
        self.assertIn("No transactions found for 07/06/2026.", _text(result))

    def test_unparseable_date_falls_back_to_raw_value(self):
        result = dashboard.show_day_detail(self._click("garbage"))
        self.assertIsInstance(result, dbc.Alert)
        self.assertIn("No transactions found for garbage.", _text(result))

    def test_one_transaction_wording(self):
        insert_expense(4.0, "Groceries", "solo", date="2026-06-03")
        text = _text(dashboard.show_day_detail(self._click("03/06/2026")))
        self.assertIn("1 transactions · €4.00 total", text)  # current wording (no singular form)


class TestOpenDelExpenseModal(BaseDbTest):
    def _call(self, triggered):
        with patch("dash.callback_context", _fake_ctx(triggered)):
            return dashboard.open_del_expense_modal([None])

    def test_no_trigger_is_no_update(self):
        self.assertTrue(_all_no_update(self._call([]), 3))

    def test_falsy_click_value_is_no_update(self):
        self.assertTrue(_all_no_update(self._call([_trigger("del-expense", 1, "n_clicks", None)]), 3))
        self.assertTrue(_all_no_update(self._call([_trigger("del-expense", 1, "n_clicks", 0)]), 3))

    def test_opens_modal_with_expense_label(self):
        eid = insert_expense(12.5, "Groceries", "milk", merchant="Lidl", date="2026-06-05")
        row = fetch_expense(eid)
        expense_id, is_open, body = self._call([_trigger("del-expense", eid, "n_clicks", 1)])
        self.assertEqual(expense_id, eid)
        self.assertTrue(is_open)
        self.assertIn(f"{row['merchant']} €12.50", _text(html.Div(body)))

    def test_label_falls_back_to_description_without_merchant(self):
        eid = insert_expense(3.0, "Groceries", "loose change item", date="2026-06-05")
        _, _, body = self._call([_trigger("del-expense", eid, "n_clicks", 1)])
        self.assertIn("loose change item €3.00", _text(html.Div(body)))

    def test_unknown_expense_uses_generic_label(self):
        expense_id, is_open, body = self._call([_trigger("del-expense", 99, "n_clicks", 1)])
        self.assertEqual((expense_id, is_open), (99, True))
        self.assertIn("expense #99", _text(html.Div(body)))

    def test_deleted_expense_uses_generic_label(self):
        eid = insert_expense(3.0, "Groceries", "gone", date="2026-06-05")
        delete_expense(eid)
        _, _, body = self._call([_trigger("del-expense", eid, "n_clicks", 1)])
        self.assertIn(f"expense #{eid}", _text(html.Div(body)))


class TestHandleDelete(BaseDbTest):
    def test_no_clicks_or_no_pending_id_is_no_update(self):
        self.assertTrue(_all_no_update(dashboard.handle_delete(None, 1), 5))
        self.assertTrue(_all_no_update(dashboard.handle_delete(1, None), 5))

    def test_soft_deletes_and_reports(self):
        eid = insert_expense(4.2, "Groceries", "milk", merchant="Lidl", date="2026-06-05")
        label = f"{fetch_expense(eid)['merchant']} €4.20"
        result = dashboard.handle_delete(1, eid)
        self.assertEqual(
            result,
            ({"action": "delete", "id": eid}, {"id": eid, "label": label},
             dashboard._TOAST_VISIBLE, f"Deleted: {label}", False),
        )
        self.assertEqual(fetch_expenses(), [])
        self.assertEqual(fetch_expense(eid)["deleted"], 1)  # soft delete: row is kept

    def test_label_uses_description_without_merchant(self):
        eid = insert_expense(4.2, "Groceries", "mystery item", date="2026-06-05")
        self.assertEqual(dashboard.handle_delete(1, eid)[3], "Deleted: mystery item €4.20")

    def test_unknown_id_is_harmless(self):
        result = dashboard.handle_delete(1, 99)
        self.assertEqual(result[1], {"id": 99, "label": "#99"})
        self.assertEqual(result[3], "Deleted: #99")


class TestCancelAndRestore(BaseDbTest):
    def test_cancel_closes_modal(self):
        self.assertIs(dashboard.cancel_del_expense(1), False)

    def test_restore_without_click_or_last_deleted_is_no_update(self):
        self.assertTrue(_all_no_update(dashboard.handle_restore(None, {"id": 1}), 3))
        self.assertTrue(_all_no_update(dashboard.handle_restore(1, None), 3))

    def test_restore_brings_back_the_deleted_expense_and_hides_toast(self):
        eid = insert_expense(4.2, "Groceries", "milk", date="2026-06-05")
        dashboard.handle_delete(1, eid)
        self.assertEqual(fetch_expenses(), [])
        result = dashboard.handle_restore(1, {"id": eid, "label": "x"})
        self.assertEqual(result, ({"action": "restore", "id": eid}, None, dashboard._TOAST_HIDDEN))
        self.assertEqual([r["id"] for r in fetch_expenses()], [eid])

    def test_toast_styles_differ_only_in_display(self):
        self.assertEqual(dashboard._TOAST_HIDDEN["display"], "none")
        self.assertEqual(dashboard._TOAST_VISIBLE["display"], "block")
        self.assertEqual(
            {k: v for k, v in dashboard._TOAST_VISIBLE.items() if k != "display"},
            {k: v for k, v in dashboard._TOAST_HIDDEN.items() if k != "display"},
        )


# ══════════════════════════════════════════════════════════════════════════════
# pages/history.py (callbacks not covered by tests/test_history.py)
# ══════════════════════════════════════════════════════════════════════════════

def _seed_history(n=25):
    """n Groceries expenses on consecutive days (newest = highest day number)."""
    ids = []
    for i in range(n):
        d = date(2026, 5, 1) + timedelta(days=i)
        ids.append(insert_expense(float(i + 1), "Groceries", f"item {i}", merchant="Lidl", date=d.isoformat()))
    return ids


def _table_rows(table):
    body = [n for n in _walk(table) if isinstance(n, html.Tbody)][0]
    return body.children


class TestHistoryUpdateStatCards(BaseDbTest):
    def test_without_category_shows_hint(self):
        result = history.update_stat_cards(None, None, None, None)
        self.assertIn("Select a specific category", _text(result))

    def test_category_without_purchases(self):
        text = _text(history.update_stat_cards("Travel", None, None, None))
        self.assertIn("No purchases yet", text)
        self.assertIn("€0.00", text)

    def test_last_purchase_and_averages(self):
        today = date.today()
        last_monday = today - timedelta(days=today.weekday() + 7)
        insert_expense(30.0, "Groceries", "old", merchant="Edeka", date=last_monday.isoformat())
        insert_expense(8.0, "Groceries", "today", merchant="Lidl", date=today.isoformat())
        text = _text(history.update_stat_cards("Groceries", None, None, None))
        self.assertIn("Avg / Week", text)
        self.assertIn("€30.00", text)  # only the complete past week counts
        self.assertIn(history._fmt(today.isoformat()), text)
        self.assertIn("Lidl", text)
        self.assertIn("€8.00 · today", text)

    def test_other_categories_are_ignored(self):
        insert_expense(50.0, "Commute", "train", date=date.today().isoformat())
        self.assertIn("No purchases yet", _text(history.update_stat_cards("Groceries", None, None, None)))


class TestHistoryUpdateTable(BaseDbTest):
    def setUp(self):
        super().setUp()
        self.ids = _seed_history(25)

    def _call(self, category=None, keyword=None, page=1):
        return history.update_table(category, keyword, None, None, None, page)

    def test_first_page_has_ten_rows_newest_first(self):
        count, table, info, prev_disabled, next_disabled = self._call()
        rows = _table_rows(table)
        self.assertEqual(count, "25 transactions found")
        self.assertEqual(info, "Page 1 of 3")
        self.assertEqual((prev_disabled, next_disabled), (True, False))
        self.assertEqual(len(rows), 10)
        self.assertIn("item 24", _text(rows[0]))
        self.assertIn("item 15", _text(rows[-1]))

    def test_last_page_has_remainder_and_disables_next(self):
        count, table, info, prev_disabled, next_disabled = self._call(page=3)
        self.assertEqual(len(_table_rows(table)), 5)
        self.assertEqual(info, "Page 3 of 3")
        self.assertEqual((prev_disabled, next_disabled), (False, True))

    def test_page_number_is_clamped(self):
        self.assertEqual(self._call(page=99)[2], "Page 3 of 3")
        self.assertEqual(self._call(page=0)[2], "Page 1 of 3")
        self.assertEqual(self._call(page=None)[2], "Page 1 of 3")

    def test_keyword_matches_merchant_and_description_case_insensitively(self):
        insert_expense(1.0, "Groceries", "zebra stripes", merchant="Rewe", date="2026-07-01")
        by_desc = self._call(keyword="  ZEBRA ")
        by_merchant = self._call(keyword="rewe")
        self.assertEqual(by_desc[0], "1 transaction found")
        self.assertEqual(by_merchant[0], "1 transaction found")
        self.assertIn("zebra stripes", _text(by_desc[1]))

    def test_category_filter(self):
        insert_expense(1.0, "Commute", "train", date="2026-07-01")
        self.assertEqual(self._call(category="Commute")[0], "1 transaction found")
        self.assertEqual(self._call(category="Groceries")[0], "25 transactions found")

    def test_category_and_keyword_combine(self):
        insert_expense(1.0, "Commute", "item 3 on the train", date="2026-07-01")
        self.assertEqual(self._call(category="Commute", keyword="item 3")[0], "1 transaction found")
        self.assertEqual(self._call(category="Groceries", keyword="train")[0], "0 transactions found")

    def test_no_match_returns_empty_state(self):
        count, table, info, prev_disabled, next_disabled = self._call(keyword="nothing-like-this")
        self.assertEqual((count, info, prev_disabled, next_disabled), ("0 transactions found", "", True, True))
        self.assertIn("No transactions match your search.", _text(table))

    def test_deleted_expenses_are_not_listed(self):
        delete_expense(self.ids[-1])
        count, table, *_ = self._call()
        self.assertEqual(count, "24 transactions found")
        self.assertNotIn("item 24", _text(table))

    def test_rows_have_edit_delete_and_category_controls_keyed_by_id(self):
        _, table, *_ = self._call()
        newest_id = self.ids[-1]
        ids = [getattr(n, "id", None) for n in _walk(table)]
        self.assertIn({"type": "edit-expense", "index": newest_id}, ids)
        self.assertIn({"type": "del-expense", "index": newest_id}, ids)
        self.assertIn({"type": "hist-cat-select", "index": newest_id}, ids)

    def test_missing_merchant_is_shown_as_dash(self):
        insert_expense(1.0, "Groceries", "no store here", date="2026-08-01")
        _, table, *_ = self._call(keyword="no store here")
        self.assertIn("—", _text(table))


class TestHistoryPaging(unittest.TestCase):
    def test_parse_page_info(self):
        self.assertEqual(history._parse_page_info("Page 2 of 7"), (2, 7))
        self.assertEqual(history._parse_page_info(None), (1, 1))
        self.assertEqual(history._parse_page_info(""), (1, 1))
        self.assertEqual(history._parse_page_info("garbage"), (1, 1))

    def test_go_prev(self):
        self.assertEqual(history.go_prev(1, "Page 3 of 5"), 2)
        self.assertEqual(history.go_prev(1, "Page 1 of 5"), 1)  # clamped
        self.assertEqual(history.go_prev(1, None), 1)

    def test_go_next(self):
        self.assertEqual(history.go_next(1, "Page 3 of 5"), 4)
        self.assertEqual(history.go_next(1, "Page 5 of 5"), 5)  # clamped
        self.assertEqual(history.go_next(1, None), 1)

    def test_filter_change_resets_to_first_page(self):
        self.assertEqual(history.reset_page_on_filter_change("Groceries", "x"), 1)


class TestHistoryInlineCategory(BaseDbTest):
    def test_persists_category_and_returns_trigger_id(self):
        eid = insert_expense(5.0, "Groceries", "thing", date="2026-06-01")
        trig = _trigger("hist-cat-select", eid, "value", "Gifts")
        ctx = _fake_ctx([trig], triggered_id="the-id")
        with patch("dash.callback_context", ctx):
            result = history.update_category_inline(["Gifts"])
        self.assertEqual(fetch_expense(eid)["category"], "Gifts")
        self.assertEqual(result, "the-id")

    def test_empty_value_does_not_change_anything(self):
        eid = insert_expense(5.0, "Groceries", "thing", date="2026-06-01")
        ctx = _fake_ctx([_trigger("hist-cat-select", eid, "value", None)])
        with patch("dash.callback_context", ctx):
            history.update_category_inline([None])
        self.assertEqual(fetch_expense(eid)["category"], "Groceries")


class TestHistoryOpenEditModal(BaseDbTest):
    def _call(self, triggered):
        with patch("dash.callback_context", _fake_ctx(triggered)):
            return history.open_edit_expense_modal([None])

    def test_no_trigger(self):
        self.assertTrue(_all_no_update(self._call([]), 7))

    def test_falsy_click(self):
        self.assertTrue(_all_no_update(self._call([_trigger("edit-expense", 1, "n_clicks", 0)]), 7))

    def test_unknown_expense(self):
        self.assertTrue(_all_no_update(self._call([_trigger("edit-expense", 99, "n_clicks", 1)]), 7))

    def test_prefills_the_modal(self):
        eid = insert_expense(12.5, "Groceries", "weekly shop", merchant="Lidl", date="2026-06-05")
        row = fetch_expense(eid)
        result = self._call([_trigger("edit-expense", eid, "n_clicks", 1)])
        self.assertEqual(
            result, (eid, True, 12.5, row["merchant"], "Groceries", "weekly shop", "2026-06-05")
        )


class TestHistorySaveEdit(BaseDbTest):
    def setUp(self):
        super().setUp()
        self.eid = insert_expense(10.0, "Groceries", "original", merchant="Lidl", date="2026-06-05")

    def _save(self, amount=20.0, merchant="Edeka", category="Gifts", description="  new text  ",
              date_val="2026-07-01T00:00:00", expense_id="default", save_clicks=1, trigger="edit-e-save"):
        eid = self.eid if expense_id == "default" else expense_id
        with patch("dash.callback_context", _fake_ctx(triggered_id=trigger)):
            return history.save_edit_expense(save_clicks, None, eid, amount, merchant,
                                             category, description, date_val)

    def test_cancel_closes_modal_without_saving(self):
        result = self._save(trigger="edit-e-cancel", amount=999.0)
        self.assertEqual(result, (False, NO_UPDATE, ""))
        self.assertEqual(fetch_expense(self.eid)["amount"], 10.0)

    def test_no_clicks_or_no_expense_id_is_no_update(self):
        self.assertTrue(_all_no_update(self._save(save_clicks=None), 3))
        self.assertTrue(_all_no_update(self._save(expense_id=None), 3))

    def _assert_rejected(self, result, message):
        is_open, store, feedback = result
        self.assertTrue(is_open)
        self.assertIs(store, NO_UPDATE)
        self.assertIn(message, _text(feedback))
        row = fetch_expense(self.eid)
        self.assertEqual((row["amount"], row["description"]), (10.0, "original"))

    def test_amount_must_be_positive(self):
        for bad in (None, 0, -5):
            self._assert_rejected(self._save(amount=bad), "Amount must be greater than 0.")

    def test_category_required(self):
        self._assert_rejected(self._save(category=None), "Category is required.")

    def test_description_required_and_whitespace_only_is_rejected(self):
        self._assert_rejected(self._save(description=None), "Description is required.")
        self._assert_rejected(self._save(description="   "), "Description is required.")

    def test_date_required(self):
        self._assert_rejected(self._save(date_val=None), "Date is required.")

    def test_successful_save_updates_row_and_signals_refresh(self):
        result = self._save()
        self.assertEqual(result, (False, self.eid, ""))
        row = fetch_expense(self.eid)
        self.assertEqual(row["amount"], 20.0)
        self.assertEqual(row["category"], "Gifts")
        self.assertEqual(row["description"], "new text")  # stripped
        self.assertEqual(row["date"], "2026-07-01")        # time part dropped
        self.assertEqual(row["merchant"], "Edeka")

    def test_empty_merchant_is_stored_as_null(self):
        self._save(merchant="")
        self.assertIsNone(fetch_expense(self.eid)["merchant"])

    def test_amount_is_stored_as_float(self):
        self._save(amount="12.5")
        self.assertEqual(fetch_expense(self.eid)["amount"], 12.5)


class TestHistoryExportCsvExtras(BaseDbTest):
    def test_without_filters_exports_everything_newest_first(self):
        insert_expense(1.0, "Groceries", "old", date="2026-06-01")
        insert_expense(2.0, "Commute", "new", date="2026-06-09")
        result = history.export_csv(1, None, None)
        self.assertEqual(result["filename"], f"expenses_all_{date.today().isoformat()}.csv")
        lines = result["content"].splitlines()
        self.assertEqual(lines[0], "date,merchant,category,amount,description")
        self.assertTrue(lines[1].startswith("2026-06-09"))
        self.assertTrue(lines[2].startswith("2026-06-01"))

    def test_keyword_matches_description(self):
        insert_expense(1.0, "Groceries", "special cheese", date="2026-06-01")
        insert_expense(2.0, "Groceries", "bread", date="2026-06-02")
        content = history.export_csv(1, None, "CHEESE")["content"]
        self.assertIn("special cheese", content)
        self.assertNotIn("bread", content)


# ══════════════════════════════════════════════════════════════════════════════
# pages/backup.py
# ══════════════════════════════════════════════════════════════════════════════

class BaseBackupTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name) / "backups"
        self.log = Path(self._tmp.name) / "backup.log"
        for name, value in (("_BACKUP_DIR", self.dir), ("_LOG_FILE", self.log)):
            p = patch.object(backup, name, value)
            p.start()
            self.addCleanup(p.stop)

    def _touch(self, *names):
        self.dir.mkdir(parents=True, exist_ok=True)
        for n in names:
            (self.dir / n).write_text("x")


class TestLastLocalBackup(BaseBackupTest):
    def test_missing_directory(self):
        self.assertEqual(backup._last_local_backup(), ("Never", ""))

    def test_empty_directory(self):
        self.dir.mkdir()
        self.assertEqual(backup._last_local_backup(), ("Never", ""))

    def test_picks_the_most_recent_file(self):
        self._touch("expenses_2026-06-01.db", "expenses_2026-07-15.db", "expenses_2026-06-30.db")
        self.assertEqual(backup._last_local_backup(), ("15 Jul 2026", "expenses_2026-07-15.db"))

    def test_ignores_trips_backups(self):
        self._touch("trips_2026-09-01.db", "expenses_2026-07-15.db")
        self.assertEqual(backup._last_local_backup(), ("15 Jul 2026", "expenses_2026-07-15.db"))

    def test_unparseable_name_falls_back_to_stem(self):
        self._touch("expenses_manual.db")
        self.assertEqual(backup._last_local_backup(), ("expenses_manual", "expenses_manual.db"))


class TestLastLocalTripsBackup(BaseBackupTest):
    def test_missing_directory(self):
        self.assertEqual(backup._last_local_trips_backup(), ("Never", ""))

    def test_empty_directory(self):
        self.dir.mkdir()
        self.assertEqual(backup._last_local_trips_backup(), ("Never", ""))

    def test_picks_the_most_recent_file_and_ignores_expenses(self):
        self._touch("trips_2026-06-01.db", "trips_2026-07-15.db", "expenses_2026-09-01.db")
        self.assertEqual(backup._last_local_trips_backup(), ("15 Jul 2026", "trips_2026-07-15.db"))

    def test_unparseable_name_falls_back_to_stem(self):
        self._touch("trips_manual.db")
        self.assertEqual(backup._last_local_trips_backup(), ("trips_manual", "trips_manual.db"))


class TestLastGdriveBackup(BaseBackupTest):
    def _log(self, *lines):
        self.log.write_text("\n".join(lines) + "\n")

    def test_missing_log(self):
        self.assertEqual(backup._last_gdrive_backup(), "Never")

    def test_formats_timestamp_of_last_upload(self):
        self._log("2026-07-01 02:00:05,123  INFO  Google Drive: uploaded expenses_2026-07-01.db")
        self.assertEqual(backup._last_gdrive_backup(), "01 Jul 2026 02:00")

    def test_update_lines_count_and_latest_wins(self):
        self._log(
            "2026-07-01 02:00:05,123  INFO  Google Drive: uploaded a.db",
            "2026-07-02 02:00:07,456  INFO  Google Drive: updated a.db",
            "2026-07-03 02:00:09,789  INFO  Local backup saved: x",
        )
        self.assertEqual(backup._last_gdrive_backup(), "02 Jul 2026 02:00")

    def test_other_gdrive_messages_are_ignored(self):
        self._log(
            "2026-07-01 02:00:05,123  ERROR  Google Drive not authenticated",
            "2026-07-01 02:00:06,123  INFO  Google Drive: Created folder",
        )
        self.assertEqual(backup._last_gdrive_backup(), "Never")

    def test_malformed_timestamp_is_unknown(self):
        self._log("not-a-date  INFO  Google Drive: uploaded a.db")
        self.assertEqual(backup._last_gdrive_backup(), "Unknown")

    def test_unreadable_log_is_unknown(self):
        self._log("2026-07-01 02:00:05,123  INFO  Google Drive: uploaded a.db")
        with patch.object(Path, "read_text", side_effect=OSError("denied")):
            self.assertEqual(backup._last_gdrive_backup(), "Unknown")


class TestStatusCards(unittest.TestCase):
    @staticmethod
    def _card(col):
        return col.children

    def test_ok_card_is_teal_and_shows_title_value_and_sub(self):
        col = backup._status_card("Title", "Value", "sub text", ok=True)
        self.assertEqual(col.md, 3)
        self.assertIn(backup._TEAL, self._card(col).style["borderTop"])
        text = _text(col)
        for part in ("Title", "Value", "sub text"):
            self.assertIn(part, text)

    def test_failed_card_is_red(self):
        col = backup._status_card("Title", "Never", ok=False)
        self.assertIn("#dc3545", self._card(col).style["borderTop"])

    def test_sub_text_is_optional(self):
        col = backup._status_card("Title", "Value")
        self.assertEqual(len(_find(col, html.Small)), 0)

    def test_build_status_marks_missing_backups_as_failed(self):
        with patch.object(backup, "_last_local_backup", return_value=("Never", "")), \
             patch.object(backup, "_last_local_trips_backup", return_value=("Never", "")), \
             patch.object(backup, "_last_gdrive_backup", return_value="Never"):
            row = backup._build_status()
        cards = [c.children for c in row.children]
        self.assertEqual(len(cards), 4)
        for card in cards[:3]:
            self.assertIn("#dc3545", card.style["borderTop"])
        self.assertIn(backup._TEAL, cards[3].style["borderTop"])  # location card is always ok

    def test_build_status_marks_existing_backups_as_ok(self):
        with patch.object(backup, "_last_local_backup", return_value=("15 Jul 2026", "e.db")), \
             patch.object(backup, "_last_local_trips_backup", return_value=("15 Jul 2026", "t.db")), \
             patch.object(backup, "_last_gdrive_backup", return_value="15 Jul 2026 02:00"):
            row = backup._build_status()
        cards = [c.children for c in row.children]
        for card in cards:
            self.assertIn(backup._TEAL, card.style["borderTop"])
        text = _text(row)
        self.assertIn("e.db", text)
        self.assertIn("t.db", text)
        self.assertIn("15 Jul 2026 02:00", text)

    def test_unknown_gdrive_status_is_failed(self):
        with patch.object(backup, "_last_local_backup", return_value=("15 Jul 2026", "e.db")), \
             patch.object(backup, "_last_local_trips_backup", return_value=("15 Jul 2026", "t.db")), \
             patch.object(backup, "_last_gdrive_backup", return_value="Unknown"):
            row = backup._build_status()
        gdrive_card = row.children[2].children
        self.assertIn("#dc3545", gdrive_card.style["borderTop"])


class TestRunBackupHelper(unittest.TestCase):
    def _run(self, local_only, **run_kwargs):
        with patch.object(backup.subprocess, "run", **run_kwargs) as run:
            result = backup._run_backup(local_only)
        return result, run

    @staticmethod
    def _completed(returncode=0, stdout="", stderr=""):
        return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)

    def test_success_returns_combined_output(self):
        (ok, msg), _ = self._run(False, return_value=self._completed(0, "out", "err"))
        self.assertEqual((ok, msg), (True, "outerr"))

    def test_empty_output_gets_default_message(self):
        (ok, msg), _ = self._run(False, return_value=self._completed(0, "", ""))
        self.assertEqual((ok, msg), (True, "Backup complete."))

    def test_nonzero_exit_is_failure_with_output(self):
        (ok, msg), _ = self._run(False, return_value=self._completed(1, "", "Database not found"))
        self.assertEqual((ok, msg), (False, "Database not found"))

    def test_timeout(self):
        (ok, msg), _ = self._run(False, side_effect=subprocess.TimeoutExpired(cmd="x", timeout=300))
        self.assertEqual((ok, msg), (False, "Backup timed out after 300 seconds."))

    def test_unexpected_exception(self):
        (ok, msg), _ = self._run(False, side_effect=OSError("no python"))
        self.assertEqual((ok, msg), (False, "Error: no python"))

    def test_full_backup_command_has_no_local_flag(self):
        _, run = self._run(False, return_value=self._completed())
        cmd = run.call_args.args[0]
        self.assertEqual(cmd, [backup.sys.executable, str(backup._SCRIPT)])
        self.assertEqual(run.call_args.kwargs["timeout"], 300)
        self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_local_only_adds_flag(self):
        _, run = self._run(True, return_value=self._completed())
        self.assertEqual(run.call_args.args[0][-1], "--local")

    def test_script_path_points_at_backup_script(self):
        self.assertEqual(backup._SCRIPT.name, "backup_db.py")
        self.assertTrue(backup._SCRIPT.exists())


class TestRunBackupCallback(unittest.TestCase):
    def _call(self, triggered_id, result):
        with patch("dash.callback_context", _fake_ctx(triggered_id=triggered_id)), \
             patch.object(backup, "_run_backup", return_value=result) as run, \
             patch.object(backup, "_build_status", return_value="STATUS"):
            out = backup.run_backup(1, 0)
        return out, run

    def test_local_button_runs_local_only(self):
        _, run = self._call("backup-local-btn", (True, "done"))
        run.assert_called_once_with(True)

    def test_full_button_runs_full_backup(self):
        _, run = self._call("backup-run-btn", (True, "done"))
        run.assert_called_once_with(False)

    def test_success_alert_and_refreshed_status(self):
        (alert, status), _ = self._call("backup-run-btn", (True, "all good"))
        self.assertEqual(alert.color, "success")
        self.assertEqual(alert.children, "all good")
        self.assertEqual(status, "STATUS")

    def test_failure_alert_is_danger(self):
        (alert, _), _ = self._call("backup-run-btn", (False, "boom"))
        self.assertEqual(alert.color, "danger")
        self.assertEqual(alert.children, "boom")


if __name__ == "__main__":
    unittest.main()
