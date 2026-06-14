# tests/test_receipt_scanner.py
import unittest
from unittest.mock import MagicMock, patch

from expense_tracker_agent.receipt_scanner import ReceiptData, ReceiptItem, parse_receipt


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


class TestParseReceipt(unittest.TestCase):
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
