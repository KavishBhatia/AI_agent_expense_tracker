# tests/test_pages_import_scan_add.py
"""
Callback and helper tests for pages/import_csv.py, pages/scan_receipt.py and
pages/add_expense.py.

Callbacks are plain functions (dash's @callback returns the original), so they are
called directly. The DB is a throw-away temp file; the agent, the categoriser and the
Gemini receipt scanner are mocked, so nothing touches the network or the real expenses.db.
Pure helpers already covered elsewhere (tests/test_fallback_parser.py for
_try_fallback_parse, tests/test_receipt_scanner.py for parse_receipt and the date
helpers) are not repeated here.
"""
import base64
import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import dash
from dash import dash_table

import expense_tracker_agent.db as db_module
from expense_tracker_agent.db import (
    fetch_expense_items,
    fetch_expenses,
    init_db,
    insert_expense,
    insert_expense_item,
)
from expense_tracker_agent.receipt_scanner import ReceiptData, ReceiptItem, ReceiptScanError
from expense_tracker_agent.tools import CATEGORIES
from pages import add_expense as add_page
from pages import import_csv as import_page
from pages import scan_receipt as scan_page

NO_UPDATE = dash.no_update


# ── helpers ───────────────────────────────────────────────────────────────────

def _temp_db() -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    os.unlink(f.name)
    return Path(f.name)


class BaseDbTest(unittest.TestCase):
    """Runs each test against its own empty temp database."""

    def setUp(self):
        self.tmp_db = _temp_db()
        self.db_patcher = patch.object(db_module, "DB_PATH", self.tmp_db)
        self.db_patcher.start()
        init_db()

    def tearDown(self):
        self.db_patcher.stop()
        if self.tmp_db.exists():
            self.tmp_db.unlink()


def _walk(component):
    """Yield a Dash component and all of its descendants."""
    if component is None or isinstance(component, (str, int, float, bool)):
        return
    if isinstance(component, (list, tuple)):
        for c in component:
            yield from _walk(c)
        return
    yield component
    yield from _walk(getattr(component, "children", None))


def _text(component) -> str:
    """All visible text in a component tree, joined by spaces."""
    parts = []

    def rec(c):
        if c is None or isinstance(c, bool):
            return
        if isinstance(c, (str, int, float)):
            parts.append(str(c))
        elif isinstance(c, (list, tuple)):
            for x in c:
                rec(x)
        else:
            rec(getattr(c, "children", None))

    rec(component)
    return " ".join(parts)


def _find(component, component_id):
    for c in _walk(component):
        if getattr(c, "id", None) == component_id:
            return c
    return None


def _alerts(component):
    return [c for c in _walk(component) if type(c).__name__ == "Alert"]


def _csv_upload(text: str, encoding: str = "utf-8") -> str:
    b64 = base64.b64encode(text.encode(encoding)).decode()
    return f"data:text/csv;base64,{b64}"


def _image_upload(raw: bytes = b"\x89PNGfake") -> str:
    return "data:image/png;base64," + base64.b64encode(raw).decode()


# ══════════════════════════════════════════════════════════════════════════════
# pages/import_csv.py
# ══════════════════════════════════════════════════════════════════════════════

class TestDetectColumns(unittest.TestCase):
    def test_detects_english_columns(self):
        m = import_page._detect_columns(["Date", "Cost", "Supermarket Name"])
        self.assertEqual(m, {"date": "Date", "cost": "Cost", "merchant": "Supermarket Name"})

    def test_detection_is_case_insensitive_and_keeps_original_name(self):
        m = import_page._detect_columns(["DATE", "aMoUnT", "MERCHANT"])
        self.assertEqual(m, {"date": "DATE", "cost": "aMoUnT", "merchant": "MERCHANT"})

    def test_detects_german_columns(self):
        m = import_page._detect_columns(["Datum", "Betrag", "Markt"])
        self.assertEqual(m, {"date": "Datum", "cost": "Betrag", "merchant": "Markt"})

    def test_unknown_columns_are_not_mapped(self):
        self.assertEqual(import_page._detect_columns(["foo", "bar"]), {})

    def test_partial_mapping(self):
        self.assertEqual(import_page._detect_columns(["date", "notes"]), {"date": "date"})


class TestShowPreview(unittest.TestCase):
    CSV = "Date,Cost,Supermarket\n10/06/2026,9.49,Edeka\n11/06/2026,3.20,Lidl\n"

    def test_none_contents_returns_no_update(self):
        self.assertIs(import_page.show_preview(None, "x.csv"), NO_UPDATE)

    def test_preview_shows_filename_rows_and_import_button(self):
        out = import_page.show_preview(_csv_upload(self.CSV), "june.csv")
        self.assertIn("Preview: june.csv", _text(out))
        self.assertIn("Import 2 rows", _text(out))
        table = next(c for c in _walk(out) if isinstance(c, dash_table.DataTable))
        self.assertEqual(len(table.data), 2)
        self.assertEqual(table.data[0]["Supermarket"], "Edeka")

    def test_columns_are_auto_detected_into_selectors(self):
        out = import_page.show_preview(_csv_upload(self.CSV), "june.csv")
        self.assertEqual(_find(out, "col-date").value, "Date")
        self.assertEqual(_find(out, "col-cost").value, "Cost")
        self.assertEqual(_find(out, "col-merchant").value, "Supermarket")

    def test_unrecognised_columns_leave_selectors_empty(self):
        out = import_page.show_preview(_csv_upload("a,b\n1,2\n"), "x.csv")
        self.assertIsNone(_find(out, "col-date").value)
        self.assertEqual([o["value"] for o in _find(out, "col-date").options], ["a", "b"])

    def test_preview_table_is_capped_at_10_rows_but_button_counts_all(self):
        rows = "\n".join(f"01/06/2026,{i}.00,Shop" for i in range(1, 26))
        out = import_page.show_preview(_csv_upload("date,cost,merchant\n" + rows), "big.csv")
        table = next(c for c in _walk(out) if isinstance(c, dash_table.DataTable))
        self.assertEqual(len(table.data), 10)
        self.assertIn("Import 25 rows", _text(out))

    def test_store_holds_every_row_as_json_strings(self):
        out = import_page.show_preview(_csv_upload(self.CSV), "june.csv")
        stored = json.loads(_find(out, "csv-data-store").data)
        self.assertEqual(len(stored), 2)
        self.assertEqual(stored[0]["Cost"], "9.49")  # dtype=str keeps the raw text

    def test_empty_file_shows_a_danger_alert(self):
        out = import_page.show_preview(_csv_upload(""), "empty.csv")
        self.assertEqual(type(out).__name__, "Alert")
        self.assertEqual(out.color, "danger")
        self.assertIn("Could not parse CSV", _text(out))

    def test_header_only_file_previews_zero_rows(self):
        out = import_page.show_preview(_csv_upload("date,cost,merchant\n"), "h.csv")
        self.assertIn("Import 0 rows", _text(out))


class TestRunImport(BaseDbTest):
    DATE, COST, MERCHANT = "Date", "Cost", "Shop"

    def _json(self, rows):
        return json.dumps(rows)

    def _run(self, rows, categories=None, date_col="Date", cost_col="Cost",
             merchant_col="Shop", n_clicks=1):
        cats = categories if categories is not None else ["Groceries"] * len(rows)
        with patch("expense_tracker_agent.categoriser.classify_expenses",
                   return_value=cats) as classify:
            out = import_page.run_import(n_clicks, self._json(rows), date_col, cost_col, merchant_col)
        return out, classify

    def test_no_clicks_or_no_data_returns_no_update(self):
        self.assertIs(import_page.run_import(0, "[]", "d", "c", "m"), NO_UPDATE)
        self.assertIs(import_page.run_import(1, None, "d", "c", "m"), NO_UPDATE)

    def test_missing_date_or_cost_mapping_warns_and_does_not_classify(self):
        with patch("expense_tracker_agent.categoriser.classify_expenses") as classify:
            out = import_page.run_import(1, "[]", None, "Cost", "Shop")
            out2 = import_page.run_import(1, "[]", "Date", None, "Shop")
        for o in (out, out2):
            self.assertEqual(o.color, "warning")
            self.assertIn("map at least Date and Cost", _text(o))
        classify.assert_not_called()

    def test_imports_rows_with_normalised_date_amount_merchant_and_category(self):
        rows = [
            {"Date": "10/06/2026", "Cost": "9,49", "Shop": "edeka"},
            {"Date": "11/06/2026", "Cost": "3.20", "Shop": "Bakery X"},
        ]
        out, _ = self._run(rows, categories=["Groceries", "Food & Dining"])
        saved = fetch_expenses()
        self.assertEqual(len(saved), 2)
        self.assertEqual(
            [(r["date"], r["amount"], r["merchant"], r["category"], r["source"]) for r in saved],
            [("2026-06-10", 9.49, "Edeka", "Groceries", "csv_import"),
             ("2026-06-11", 3.20, "Bakery X", "Food & Dining", "csv_import")],
        )
        self.assertIn("2 rows imported successfully", _text(out))

    def test_dates_are_parsed_day_first(self):
        self._run([{"Date": "03/04/2026", "Cost": "1", "Shop": "Aldi"}])
        self.assertEqual(fetch_expenses()[0]["date"], "2026-04-03")  # 3 April, not 4 March

    def test_iso_dates_are_not_day_month_swapped(self):
        # Regression: pd.to_datetime(..., dayfirst=True) turned "2026-06-01" into 2026-01-06.
        self._run([{"Date": "2026-06-01", "Cost": "1", "Shop": "Aldi"},
                   {"Date": "2026-03-04", "Cost": "2", "Shop": "Lidl"}])
        self.assertEqual(sorted(r["date"] for r in fetch_expenses()), ["2026-03-04", "2026-06-01"])

    def test_singular_success_message(self):
        out, _ = self._run([{"Date": "01/06/2026", "Cost": "1", "Shop": "Aldi"}])
        self.assertIn("1 row imported successfully", _text(out))

    def test_classifier_receives_merchant_as_description_and_merchant(self):
        rows = [{"Date": "01/06/2026", "Cost": "1", "Shop": "  Aldi "}]
        _, classify = self._run(rows)
        classify.assert_called_once_with([{"description": "Aldi", "merchant": "Aldi"}])

    def test_existing_duplicate_is_skipped_and_reported(self):
        insert_expense(9.49, "Groceries", "x", merchant="Edeka", date="2026-06-10")
        out, _ = self._run([{"Date": "10/06/2026", "Cost": "9.49", "Shop": "Edeka"}])
        self.assertEqual(len(fetch_expenses()), 1)
        self.assertIn("1 duplicate skipped", _text(out))
        self.assertNotIn("imported successfully", _text(out))

    def test_duplicate_within_the_same_file_is_skipped(self):
        row = {"Date": "10/06/2026", "Cost": "9.49", "Shop": "Edeka"}
        out, _ = self._run([row, dict(row)])
        self.assertEqual(len(fetch_expenses()), 1)
        self.assertIn("1 row imported successfully", _text(out))
        self.assertIn("1 duplicate skipped", _text(out))

    def test_bad_rows_are_reported_and_good_rows_still_import(self):
        rows = [
            {"Date": "not-a-date", "Cost": "5", "Shop": "Aldi"},
            {"Date": "10/06/2026", "Cost": "abc", "Shop": "Lidl"},
            {"Date": "11/06/2026", "Cost": "2.50", "Shop": "Rewe"},
        ]
        out, _ = self._run(rows, categories=["Groceries"] * 3)
        saved = fetch_expenses()
        self.assertEqual([r["merchant"] for r in saved], ["Rewe"])
        text = _text(out)
        self.assertIn("1 row imported successfully", text)
        self.assertIn("2 rows failed to import:", text)
        self.assertIn("not-a-date", text)
        self.assertIn("abc", text)
        failed = [a for a in _alerts(out) if a.color == "danger"]
        self.assertEqual(len(failed), 1)

    def test_category_stays_aligned_with_row_when_an_earlier_row_fails(self):
        rows = [
            {"Date": "bad", "Cost": "1", "Shop": "Aldi"},
            {"Date": "10/06/2026", "Cost": "2", "Shop": "Lidl"},
        ]
        self._run(rows, categories=["Groceries", "Gifts"])
        self.assertEqual(fetch_expenses()[0]["category"], "Gifts")

    def test_merchant_column_is_optional(self):
        rows = [{"Date": "10/06/2026", "Cost": "4.00"}]
        out, classify = self._run(rows, merchant_col=None)
        classify.assert_called_once_with([{"description": "", "merchant": ""}])
        self.assertEqual(len(fetch_expenses()), 1)
        self.assertIn("1 row imported successfully", _text(out))

    def test_without_a_merchant_duplicates_are_not_detected(self):
        # Documented limitation (specs/data-model.md): duplicate detection needs a merchant.
        row = {"Date": "10/06/2026", "Cost": "4.00"}
        self._run([row, dict(row)], merchant_col=None)
        self.assertEqual(len(fetch_expenses()), 2)

    def test_empty_data_reports_nothing_imported(self):
        out, _ = self._run([], categories=[])
        self.assertIn("Nothing was imported", _text(out))


class TestRecategoriseAll(BaseDbTest):
    def test_no_clicks_returns_no_update(self):
        self.assertIs(import_page.recategorise_all(0), NO_UPDATE)

    def test_empty_db_shows_info_alert_without_calling_the_classifier(self):
        with patch("expense_tracker_agent.categoriser.classify_expenses") as classify:
            out = import_page.recategorise_all(1)
        self.assertEqual(out.color, "info")
        self.assertIn("No expenses in the database yet", _text(out))
        classify.assert_not_called()

    def test_updates_categories_and_reports_count(self):
        a = insert_expense(5, "Miscellaneous", "Receipt: Edeka", merchant="Edeka", date="2026-06-01")
        b = insert_expense(7, "Miscellaneous", "coffee", merchant="Cafe", date="2026-06-02")
        with patch("expense_tracker_agent.categoriser.classify_expenses",
                   return_value=["Groceries", "Food & Dining"]):
            out = import_page.recategorise_all(1)
        cats = {r["id"]: r["category"] for r in fetch_expenses()}
        self.assertEqual(cats[a], "Groceries")
        self.assertEqual(cats[b], "Food & Dining")
        self.assertIn("re-categorised 2 expenses", _text(out))

    def test_singular_message(self):
        insert_expense(5, "Miscellaneous", "x", merchant="Edeka", date="2026-06-01")
        with patch("expense_tracker_agent.categoriser.classify_expenses", return_value=["Groceries"]):
            out = import_page.recategorise_all(1)
        self.assertIn("re-categorised 1 expense with AI", _text(out))

    def test_description_includes_sub_item_descriptions(self):
        pid = insert_expense(20, "Miscellaneous", "Receipt: Edeka", merchant="Edeka", date="2026-06-01")
        insert_expense_item(pid, 3, "beer", "Alcohol")
        insert_expense_item(pid, 4, "  ", "Miscellaneous")   # blank descriptions are dropped
        insert_expense_item(pid, 5, "bread", "Groceries")
        insert_expense(2, "Miscellaneous", "gum", merchant=None, date="2026-06-02")
        with patch("expense_tracker_agent.categoriser.classify_expenses",
                   return_value=["Groceries", "Miscellaneous"]) as classify:
            import_page.recategorise_all(1)
        items = classify.call_args.args[0]
        self.assertEqual(items[0], {"description": "Receipt: Edeka; beer, bread", "merchant": "Edeka"})
        self.assertEqual(items[1], {"description": "gum", "merchant": ""})

    def test_soft_deleted_expenses_are_not_recategorised(self):
        keep = insert_expense(5, "Miscellaneous", "x", merchant="Edeka", date="2026-06-01")
        gone = insert_expense(6, "Miscellaneous", "y", merchant="Lidl", date="2026-06-02")
        db_module.delete_expense(gone)
        with patch("expense_tracker_agent.categoriser.classify_expenses",
                   return_value=["Groceries"]) as classify:
            import_page.recategorise_all(1)
        self.assertEqual(len(classify.call_args.args[0]), 1)
        self.assertEqual(db_module.fetch_expense(keep)["category"], "Groceries")


# ══════════════════════════════════════════════════════════════════════════════
# pages/scan_receipt.py
# ══════════════════════════════════════════════════════════════════════════════

def _receipt(**kw):
    base = dict(
        merchant="Edeka", date="2026-06-10", total=12.5,
        items=[ReceiptItem("milk", 1.5, "Groceries"), ReceiptItem("beer", 11.0, "Alcohol")],
    )
    base.update(kw)
    return ReceiptData(**base)


class TestProcessReceipt(unittest.TestCase):
    def _run(self, contents, filename="r.jpg", receipt=None, raises=None):
        with patch.object(scan_page, "parse_receipt", return_value=receipt,
                          side_effect=raises) as parse:
            out = scan_page.process_receipt(contents, filename)
        return out, parse

    def test_no_contents_returns_no_update_pair(self):
        out, parse = self._run(None)
        self.assertEqual(out, (NO_UPDATE, NO_UPDATE))
        parse.assert_not_called()

    def test_successful_parse_builds_the_store_dict(self):
        (store, _), parse = self._run(_image_upload(b"imgbytes"), receipt=_receipt())
        self.assertEqual(store, {
            "merchant": "Edeka", "date": "2026-06-10", "total": 12.5,
            "items": [
                {"description": "milk", "amount": 1.5, "category": "Groceries"},
                {"description": "beer", "amount": 11.0, "category": "Alcohol"},
            ],
        })
        self.assertEqual(parse.call_args.args[0], b"imgbytes")

    def test_mime_type_from_extension(self):
        for filename, mime in [("a.png", "image/png"), ("A.PNG", "image/png"),
                               ("a.jpg", "image/jpeg"), ("a.heic", "image/jpeg"), (None, "image/jpeg")]:
            _, parse = self._run(_image_upload(), filename=filename, receipt=_receipt())
            self.assertEqual(parse.call_args.kwargs["mime_type"], mime, filename)

    def test_invalid_base64_returns_error_store_without_calling_gemini(self):
        (store, _), parse = self._run("data:image/png;base64,@@@not-base64@@@")
        self.assertIn("Could not read the uploaded file", store["error"])
        parse.assert_not_called()

    def test_stray_characters_in_base64_are_rejected_not_silently_dropped(self):
        # "AAAA@@@@" decodes fine if the '@'s are discarded; only strict validation rejects it
        (store, _), parse = self._run("data:image/png;base64,AAAA@@@@")
        self.assertIn("Could not read the uploaded file", store["error"])
        parse.assert_not_called()

    def test_contents_without_a_comma_return_error_store(self):
        (store, _), parse = self._run("garbage-without-comma")
        self.assertIn("Could not read the uploaded file", store["error"])
        parse.assert_not_called()

    def test_scan_error_message_is_passed_through(self):
        (store, _), _ = self._run(_image_upload(), raises=ReceiptScanError("API key is invalid"))
        self.assertEqual(store, {"error": "API key is invalid"})

    def test_unparseable_receipt_returns_friendly_error(self):
        (store, _), _ = self._run(_image_upload(), receipt=None)
        self.assertIn("Could not parse this receipt", store["error"])


class TestRenderReview(unittest.TestCase):
    STORE = {"merchant": "Edeka", "date": "2026-06-10", "total": 12.5,
             "items": [{"description": "milk", "amount": 1.5, "category": "Groceries"}]}

    def test_empty_store_renders_nothing_and_no_edit_data(self):
        out, edit = scan_page.render_review(None)
        self.assertEqual(_text(out), "")
        self.assertIsNone(edit)

    def test_error_store_renders_danger_alert(self):
        out, edit = scan_page.render_review({"error": "Quota exceeded"})
        self.assertEqual(out.color, "danger")
        self.assertIn("Quota exceeded", _text(out))
        self.assertIsNone(edit)

    def test_form_is_prefilled_and_edit_store_seeded(self):
        out, edit = scan_page.render_review(self.STORE)
        self.assertEqual(_find(out, "receipt-merchant").value, "Edeka")
        self.assertEqual(_find(out, "receipt-date").value, "2026-06-10")
        self.assertEqual(_find(out, "receipt-total").value, "12.5")
        table = _find(out, "receipt-items-table")
        self.assertEqual(table.data, self.STORE["items"])
        self.assertEqual(edit, self.STORE)

    def test_category_dropdown_offers_every_category(self):
        out, _ = scan_page.render_review(self.STORE)
        options = _find(out, "receipt-items-table").dropdown["category"]["options"]
        self.assertEqual([o["value"] for o in options], CATEGORIES)


class TestSyncEdits(unittest.TestCase):
    CURRENT = {"merchant": "Edeka", "date": "2026-06-10", "total": 12.5,
               "items": [{"description": "milk", "amount": 1.5, "category": "Groceries"}]}

    def test_no_edit_store_returns_no_update(self):
        self.assertIs(scan_page.sync_edits([], "x", "2026-01-01", 1, None), NO_UPDATE)

    def test_applies_user_edits(self):
        items = [{"description": "beer", "amount": 3, "category": "Alcohol"}]
        out = scan_page.sync_edits(items, "Lidl", "2026-06-11", 3, self.CURRENT)
        self.assertEqual(out, {"merchant": "Lidl", "date": "2026-06-11", "total": 3, "items": items})

    def test_blank_merchant_and_date_fall_back_to_current(self):
        out = scan_page.sync_edits(None, "", "", None, self.CURRENT)
        self.assertEqual(out, self.CURRENT)

    def test_total_of_zero_is_kept_not_replaced(self):
        out = scan_page.sync_edits(self.CURRENT["items"], "Edeka", "2026-06-10", 0, self.CURRENT)
        self.assertEqual(out["total"], 0)

    def test_removing_all_rows_is_respected(self):
        out = scan_page.sync_edits([], "Edeka", "2026-06-10", 1, self.CURRENT)
        self.assertEqual(out["items"], [])


class TestSmallScanCallbacks(unittest.TestCase):
    def test_use_today(self):
        self.assertIs(scan_page.use_today_date(0), NO_UPDATE)
        self.assertEqual(scan_page.use_today_date(1), date.today().isoformat())

    def test_show_actions_only_for_a_valid_receipt(self):
        self.assertEqual(scan_page.show_actions({"merchant": "x"}), {})
        self.assertEqual(scan_page.show_actions({"error": "x"}), {"display": "none"})
        self.assertEqual(scan_page.show_actions(None), {"display": "none"})

    def test_cancel_clears_the_store(self):
        self.assertIs(scan_page.cancel_receipt(0), NO_UPDATE)
        self.assertIsNone(scan_page.cancel_receipt(1))


class TestToggleDateModal(unittest.TestCase):
    def _call(self, trigger, confirm=1, edit_data=None, parsed=None):
        with patch.object(dash, "ctx", MagicMock(triggered_id=trigger)):
            return scan_page.toggle_date_modal(confirm, 0, 0, edit_data, parsed)

    def test_modal_buttons_close_the_modal(self):
        valid = {"date": date.today().isoformat()}
        for trigger in ("receipt-date-edit-btn", "receipt-date-confirm-btn"):
            self.assertEqual(self._call(trigger, edit_data=valid), (False, NO_UPDATE))

    def test_confirm_with_zero_clicks_is_ignored(self):
        self.assertEqual(self._call("receipt-confirm-btn", confirm=0), (NO_UPDATE, NO_UPDATE))

    def test_no_data_or_error_data_keeps_modal_closed(self):
        self.assertEqual(self._call("receipt-confirm-btn"), (False, NO_UPDATE))
        self.assertEqual(self._call("receipt-confirm-btn", edit_data={"error": "x"}),
                         (False, NO_UPDATE))

    def test_recent_date_opens_modal_with_pretty_date_and_no_warning(self):
        today = date.today()
        is_open, body = self._call("receipt-confirm-btn", edit_data={"date": today.isoformat()})
        self.assertTrue(is_open)
        self.assertIn(today.strftime("%A, %d %B %Y"), _text(body))
        self.assertEqual(_alerts(body), [])

    def test_stale_date_adds_a_warning(self):
        old = (date.today() - timedelta(days=90)).isoformat()
        is_open, body = self._call("receipt-confirm-btn", edit_data={"date": old})
        self.assertTrue(is_open)
        self.assertEqual(len(_alerts(body)), 1)
        self.assertIn("more than 30 days ago", _text(body))

    def test_future_date_adds_a_warning(self):
        future = (date.today() + timedelta(days=5)).isoformat()
        _, body = self._call("receipt-confirm-btn", edit_data={"date": future})
        self.assertEqual(len(_alerts(body)), 1)

    def test_unparseable_date_is_shown_raw_with_a_warning(self):
        _, body = self._call("receipt-confirm-btn", edit_data={"date": "10.06.2026"})
        self.assertIn("10.06.2026", _text(body))
        self.assertEqual(len(_alerts(body)), 1)

    def test_missing_date_shows_placeholder(self):
        _, body = self._call("receipt-confirm-btn", edit_data={"merchant": "x"})
        self.assertIn("(no date)", _text(body))

    def test_edit_store_wins_over_parsed_store(self):
        today = date.today().isoformat()
        _, body = self._call("receipt-confirm-btn",
                             edit_data={"date": today}, parsed={"date": "2020-01-01"})
        self.assertEqual(_alerts(body), [])

    def test_falls_back_to_parsed_store(self):
        _, body = self._call("receipt-confirm-btn", edit_data=None, parsed={"date": "2020-01-01"})
        self.assertEqual(len(_alerts(body)), 1)


class TestSaveReceipt(BaseDbTest):
    DATA = {
        "merchant": "Edeka", "date": "2026-06-10", "total": 12.5,
        "items": [
            {"description": "milk", "amount": 1.5, "category": "Groceries"},
            {"description": "bread", "amount": 2.0, "category": "Groceries"},
            {"description": "beer", "amount": 9.0, "category": "Alcohol"},
        ],
    }

    def test_no_clicks_returns_three_no_updates(self):
        self.assertEqual(scan_page.save_receipt(0, self.DATA, None), (NO_UPDATE,) * 3)

    def test_no_data_or_error_data_warns_and_saves_nothing(self):
        for edit, parsed in [(None, None), ({"error": "x"}, None)]:
            result, recent, store = scan_page.save_receipt(1, edit, parsed)
            self.assertEqual(result.color, "warning")
            self.assertIn("No receipt data to save", _text(result))
            self.assertIs(recent, NO_UPDATE)
            self.assertIs(store, NO_UPDATE)
        self.assertEqual(fetch_expenses(), [])

    def test_saves_parent_and_items_and_clears_the_store(self):
        result, recent, store = scan_page.save_receipt(1, self.DATA, None)
        saved = fetch_expenses()
        self.assertEqual(len(saved), 1)
        parent = saved[0]
        self.assertEqual(
            (parent["amount"], parent["merchant"], parent["date"], parent["description"], parent["source"]),
            (12.5, "Edeka", "2026-06-10", "Receipt: Edeka", "receipt_scan"),
        )
        items = fetch_expense_items(parent["id"])
        self.assertEqual([(i["description"], i["amount"], i["category"]) for i in items],
                         [("milk", 1.5, "Groceries"), ("bread", 2.0, "Groceries"), ("beer", 9.0, "Alcohol")])
        self.assertEqual(result.color, "success")
        self.assertIn(f"#{parent['id']}", _text(result))
        self.assertIn("3 items", _text(result))
        self.assertIn("12.50", _text(result))
        self.assertIsNone(store)
        self.assertIn("Edeka", _text(recent))

    def test_parent_category_is_the_most_common_item_category(self):
        items = [  # the first item is NOT the most common category
            {"description": "beer", "amount": 9.0, "category": "Alcohol"},
            {"description": "milk", "amount": 1.5, "category": "Groceries"},
            {"description": "bread", "amount": 2.0, "category": "Groceries"},
        ]
        scan_page.save_receipt(1, {**self.DATA, "items": items}, None)
        self.assertEqual(fetch_expenses()[0]["category"], "Groceries")

    def test_no_items_gives_miscellaneous_parent(self):
        scan_page.save_receipt(1, {**self.DATA, "items": []}, None)
        self.assertEqual(fetch_expenses()[0]["category"], "Miscellaneous")

    def test_missing_merchant_is_saved_as_unknown(self):
        scan_page.save_receipt(1, {**self.DATA, "merchant": ""}, None)
        self.assertEqual(fetch_expenses()[0]["description"], "Receipt: Unknown")

    def test_items_with_missing_fields_get_defaults(self):
        data = {**self.DATA, "items": [{"description": None, "amount": None, "category": None}]}
        scan_page.save_receipt(1, data, None)
        item = fetch_expense_items(fetch_expenses()[0]["id"])[0]
        self.assertEqual((item["description"], item["amount"], item["category"]), ("", 0.0, "Miscellaneous"))

    def test_edit_store_wins_over_parsed_store(self):
        scan_page.save_receipt(1, {**self.DATA, "merchant": "Lidl"}, {**self.DATA, "merchant": "Edeka"})
        self.assertEqual(fetch_expenses()[0]["merchant"], "Lidl")

    def test_falls_back_to_parsed_store(self):
        scan_page.save_receipt(1, None, self.DATA)
        self.assertEqual(len(fetch_expenses()), 1)

    def test_invalid_dates_are_rejected_before_anything_is_written(self):
        for bad in ("", "10/06/2026", "2026-13-40", "20260610", "not a date"):
            result, recent, store = scan_page.save_receipt(1, {**self.DATA, "date": bad}, None)
            self.assertEqual(result.color, "warning", bad)
            self.assertIn("is not valid", _text(result), bad)
            self.assertIs(recent, NO_UPDATE)
            self.assertIs(store, NO_UPDATE)
        self.assertEqual(fetch_expenses(), [])

    def test_database_failure_is_reported_not_raised(self):
        with patch.object(scan_page, "insert_expense", side_effect=RuntimeError("disk full")):
            result, recent, store = scan_page.save_receipt(1, self.DATA, None)
        self.assertEqual(result.color, "danger")
        self.assertIn("Save failed: disk full", _text(result))
        self.assertIs(recent, NO_UPDATE)
        self.assertIs(store, NO_UPDATE)


class TestRecentSaves(BaseDbTest):
    def test_empty_state(self):
        self.assertIn("No saved receipts yet", _text(scan_page._recent_saves()))

    def test_only_receipt_scans_are_listed(self):
        insert_expense(1, "Groceries", "manual one", merchant="Manual", date="2026-06-01")
        insert_expense(2, "Groceries", "Receipt: Scanned", merchant="Scanned",
                       date="2026-06-02", source="receipt_scan")
        text = _text(scan_page._recent_saves())
        self.assertIn("Scanned", text)
        self.assertNotIn("Manual", text)

    def test_newest_save_first_regardless_of_receipt_date_and_capped_at_five(self):
        for n in range(7):
            # later saves carry EARLIER receipt dates
            insert_expense(n + 1, "Groceries", f"Receipt: Shop{n}", merchant=f"Shop{n}",
                           date=f"2026-06-{20 - n:02d}", source="receipt_scan")
        table = scan_page._recent_saves()
        rows = [tr for tr in _walk(table) if type(tr).__name__ == "Tr"][1:]  # skip header
        self.assertEqual(len(rows), 5)
        first_row_text = _text(rows[0])
        self.assertIn("Shop6", first_row_text)
        for dropped in ("Shop0", "Shop1"):  # the two oldest saves fell off the list
            self.assertNotIn(dropped, _text(table))

    def test_date_is_shown_day_first(self):
        insert_expense(2, "Groceries", "Receipt: Scanned", merchant="Scanned",
                       date="2026-06-02", source="receipt_scan")
        self.assertIn("02/06/2026", _text(scan_page._recent_saves()))


# ══════════════════════════════════════════════════════════════════════════════
# pages/add_expense.py
# ══════════════════════════════════════════════════════════════════════════════

class TestInferCategory(unittest.TestCase):
    def test_keyword_groups(self):
        cases = {
            "weekly shop at Edeka": "Groceries",
            "pizza night": "Food & Dining",
            "taxi home": "Commute",
            "cinema tickets": "Entertainment",
            "shampoo": "Personal Care",
            "red wine": "Alcohol",
            "something unrecognisable": "Miscellaneous",
        }
        for text, category in cases.items():
            self.assertEqual(add_page._infer_category(text), category, text)

    def test_alcohol_takes_priority_over_groceries(self):
        self.assertEqual(add_page._infer_category("beer at Edeka"), "Alcohol")

    def test_personal_care_takes_priority_over_groceries(self):
        self.assertEqual(add_page._infer_category("shampoo at Rewe"), "Personal Care")

    def test_is_case_insensitive(self):
        self.assertEqual(add_page._infer_category("EDEKA"), "Groceries")


class TestBubble(unittest.TestCase):
    def test_user_and_agent_bubbles_differ(self):
        user = add_page._bubble("hi", True)
        agent = add_page._bubble("hello", False)
        self.assertEqual(user.children, "hi")
        self.assertNotEqual(user.style["background"], agent.style["background"])
        self.assertEqual(user.style["marginLeft"], "auto")
        self.assertEqual(agent.style["marginLeft"], "0")


class TestHandleChatImmediate(unittest.TestCase):
    def _call(self, text, messages=None, selected_date=None):
        return add_page.handle_chat_immediate(1, None, text, messages, selected_date)

    def test_blank_input_changes_nothing(self):
        for text in (None, "", "   "):
            self.assertEqual(self._call(text), (NO_UPDATE,) * 6)

    def test_shows_user_bubble_and_typing_indicator_and_locks_ui(self):
        bubbles, input_value, messages, pending, send_disabled, input_disabled = self._call(
            "  €10 at Edeka  ")
        self.assertEqual(input_value, "")
        self.assertEqual(messages, [{"role": "user", "text": "€10 at Edeka"}])
        self.assertIs(bubbles[-1], add_page._TYPING_INDICATOR)
        self.assertEqual(len(bubbles), 2)
        self.assertEqual(pending["agent_text"], "€10 at Edeka")
        self.assertTrue(send_disabled)
        self.assertTrue(input_disabled)

    def test_selected_date_prefixes_agent_text_and_decorates_display_text(self):
        _, _, messages, pending, _, _ = self._call("€10 at Edeka", selected_date="2026-06-17")
        self.assertEqual(messages[0]["text"], "€10 at Edeka  [2026-06-17]")
        self.assertEqual(pending["agent_text"], "On 2026-06-17: €10 at Edeka")
        self.assertEqual(pending["selected_date"], "2026-06-17")

    def test_datetime_string_from_the_picker_is_cut_to_the_date(self):
        _, _, _, pending, _, _ = self._call("5 beer", selected_date="2026-06-17T00:00:00")
        self.assertEqual(pending["agent_text"], "On 2026-06-17: 5 beer")

    def test_cleared_date_sends_plain_text(self):
        _, _, _, pending, _, _ = self._call("5 beer", selected_date=None)
        self.assertEqual(pending["agent_text"], "5 beer")

    def test_existing_history_is_kept_in_order(self):
        history = [{"role": "user", "text": "a"}, {"role": "agent", "text": "b"}]
        bubbles, _, messages, _, _, _ = self._call("c", messages=history)
        self.assertEqual([m["text"] for m in messages], ["a", "b", "c"])
        self.assertEqual(len(bubbles), 4)  # 3 messages + typing indicator
        self.assertEqual(history[-1]["text"], "b")  # input list is not mutated


class TestHandleChatResponse(BaseDbTest):
    def _call(self, pending, messages=None):
        return add_page.handle_chat_response(pending, messages if messages is not None else [])

    def test_non_dict_or_incomplete_pending_changes_nothing(self):
        for pending in (None, "x", {}, {"status": "waiting"}):
            self.assertEqual(self._call(pending), (NO_UPDATE,) * 6)

    def test_success_appends_agent_reply_updates_recent_list_and_unlocks(self):
        def fake_chat(text):
            insert_expense(10, "Groceries", "Edeka", merchant="Edeka", date="2026-06-10")
            return "Added expense #1."

        with patch.object(add_page.agent_bridge, "chat", side_effect=fake_chat) as chat:
            bubbles, messages, recent, pending, send_dis, input_dis = self._call(
                {"agent_text": "€10 at Edeka", "display_text": "€10 at Edeka"},
                [{"role": "user", "text": "€10 at Edeka"}],
            )
        chat.assert_called_once_with("€10 at Edeka")
        self.assertEqual(messages[-1], {"role": "agent", "text": "Added expense #1."})
        self.assertEqual(len(bubbles), 2)
        self.assertIn("Edeka", _text(recent))
        self.assertIn("10/06/2026 · Groceries", _text(recent))
        self.assertEqual(pending, {"status": "idle"})
        self.assertFalse(send_dis)
        self.assertFalse(input_dis)

    def test_recent_list_is_empty_state_when_no_expenses(self):
        with patch.object(add_page.agent_bridge, "chat", return_value="Hi"):
            _, _, recent, _, _, _ = self._call({"agent_text": "hello"})
        self.assertIn("No expenses yet", _text(recent))

    def test_recent_list_shows_at_most_eight_newest_first(self):
        for n in range(10):
            insert_expense(n + 1, "Groceries", f"item{n}", date=f"2026-06-{n + 1:02d}")
        with patch.object(add_page.agent_bridge, "chat", return_value="ok"):
            _, _, recent, _, _, _ = self._call({"agent_text": "x"})
        text = _text(recent)
        self.assertIn("item9", text)
        self.assertIn("item2", text)
        self.assertNotIn("item1", text)
        self.assertNotIn("item0", text)
        self.assertLess(text.index("item9"), text.index("item8"))

    def test_agent_error_after_the_expense_was_saved_reports_the_saved_expense(self):
        def chat_saves_then_fails(text):
            insert_expense(12.5, "Groceries", "Edeka run", merchant="Edeka", date="2026-06-10")
            raise RuntimeError("429 rate limit")

        with patch.object(add_page.agent_bridge, "chat", side_effect=chat_saves_then_fails):
            _, messages, _, pending, send_dis, input_dis = self._call({"agent_text": "€12.50 at Edeka"})
        reply = messages[-1]["text"]
        self.assertIn("your expense was saved", reply)
        self.assertIn("Edeka run", reply)
        self.assertIn("€12.50", reply)
        self.assertEqual(len(fetch_expenses()), 1)  # not saved twice by the fallback
        self.assertEqual(pending, {"status": "idle"})
        self.assertFalse(send_dis or input_dis)

    def test_agent_error_uses_regex_fallback_and_strips_the_date_prefix(self):
        with patch.object(add_page.agent_bridge, "chat", side_effect=RuntimeError("down")):
            _, messages, _, _, _, _ = self._call(
                {"agent_text": "On 2026-06-17: €12.50 at Edeka", "selected_date": "2026-06-17"})
        reply = messages[-1]["text"]
        self.assertIn("AI unavailable (rate limit hit)", reply)
        saved = fetch_expenses()
        self.assertEqual(len(saved), 1)
        self.assertEqual((saved[0]["amount"], saved[0]["merchant"], saved[0]["date"],
                          saved[0]["category"]),
                         (12.5, "Edeka", "2026-06-17", "Groceries"))

    def test_agent_error_with_unparseable_text_asks_for_a_clearer_format(self):
        with patch.object(add_page.agent_bridge, "chat", side_effect=RuntimeError("down")):
            _, messages, recent, pending, send_dis, input_dis = self._call({"agent_text": "hello there"})
        self.assertIn("Could not auto-parse", messages[-1]["text"])
        self.assertEqual(fetch_expenses(), [])
        self.assertEqual(pending, {"status": "idle"})
        self.assertFalse(send_dis or input_dis)  # UI is never left locked after a failure

    def test_history_is_preserved_and_input_not_mutated(self):
        history = [{"role": "user", "text": "hello"}]
        with patch.object(add_page.agent_bridge, "chat", return_value="hi"):
            _, messages, _, _, _, _ = self._call({"agent_text": "hello"}, history)
        self.assertEqual([m["role"] for m in messages], ["user", "agent"])
        self.assertEqual(len(history), 1)


if __name__ == "__main__":
    unittest.main()
