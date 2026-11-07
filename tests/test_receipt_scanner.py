# tests/test_receipt_scanner.py
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from expense_tracker_agent.receipt_scanner import (
    ReceiptData,
    ReceiptItem,
    date_needs_attention,
    normalize_receipt_date,
    parse_receipt,
)


class TestReceiptDataModel(unittest.TestCase):
    def test_receipt_data_has_required_fields(self):
        r = ReceiptData(
            merchant="Edeka",
            date="2026-06-01",
            total=15.0,
            items=[ReceiptItem(description="beer", amount=3.0, category="Alcohol")],
        )
        self.assertEqual(r.merchant, "Edeka")
        self.assertEqual(len(r.items), 1)


class TestNormalizeReceiptDate(unittest.TestCase):
    TODAY = date(2026, 11, 7)

    def test_keeps_valid_iso_date(self):
        self.assertEqual(normalize_receipt_date("2026-10-30", today=self.TODAY), "2026-10-30")

    def test_keeps_old_valid_date(self):
        # receipts can legitimately be from the past; the user confirms before saving
        self.assertEqual(normalize_receipt_date("2023-10-27", today=self.TODAY), "2023-10-27")

    def test_unparseable_falls_back_to_today(self):
        self.assertEqual(normalize_receipt_date("not a date", today=self.TODAY), "2026-11-07")
        self.assertEqual(normalize_receipt_date("", today=self.TODAY), "2026-11-07")
        self.assertEqual(normalize_receipt_date("27.10.2023", today=self.TODAY), "2026-11-07")


class TestDateNeedsAttention(unittest.TestCase):
    TODAY = date(2026, 11, 7)

    def test_recent_date_is_fine(self):
        self.assertFalse(date_needs_attention("2026-10-20", today=self.TODAY))

    def test_old_date_is_flagged(self):
        self.assertTrue(date_needs_attention("2023-10-27", today=self.TODAY))

    def test_future_date_is_flagged(self):
        self.assertTrue(date_needs_attention("2026-11-08", today=self.TODAY))


class TestParseReceipt(unittest.TestCase):
    @patch("expense_tracker_agent.receipt_scanner.genai")
    def test_old_model_date_is_kept(self, mock_genai):
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"merchant":"Kaufland","date":"2023-10-27","total":50.96,"items":[]}'
        mock_client.models.generate_content.return_value = mock_response

        result = parse_receipt(b"fake_image_bytes")

        self.assertEqual(result.date, "2023-10-27")

    @patch("expense_tracker_agent.receipt_scanner.genai")
    def test_prompt_contains_todays_date(self, mock_genai):
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"merchant":"Edeka","date":"","total":1.0,"items":[]}'
        mock_client.models.generate_content.return_value = mock_response

        result = parse_receipt(b"fake_image_bytes")

        prompt = mock_client.models.generate_content.call_args.kwargs["contents"][0]
        self.assertIn(date.today().isoformat(), prompt)
        self.assertEqual(result.date, date.today().isoformat())

    @patch("expense_tracker_agent.receipt_scanner.genai")
    def test_returns_receipt_data_on_success(self, mock_genai):
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = '{"merchant":"Edeka","date":"2026-06-01","total":10.0,"items":[{"description":"beer","amount":3.0,"category":"Alcohol"},{"description":"bread","amount":7.0,"category":"Groceries"}]}'
        mock_client.models.generate_content.return_value = mock_response

        result = parse_receipt(b"fake_image_bytes")

        self.assertIsInstance(result, ReceiptData)
        self.assertEqual(result.merchant, "Edeka")
        self.assertEqual(len(result.items), 2)
        self.assertAlmostEqual(result.total, 10.0)

    @patch("expense_tracker_agent.receipt_scanner.genai")
    def test_returns_none_on_invalid_json(self, mock_genai):
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client
        mock_response = MagicMock()
        mock_response.text = "Sorry, I cannot read this image."
        mock_client.models.generate_content.return_value = mock_response

        result = parse_receipt(b"bad_image")
        self.assertIsNone(result)
