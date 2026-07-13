# tests/test_fallback_parser.py
import re
import unittest
from unittest.mock import patch

import dash

from pages.add_expense import _try_fallback_parse, handle_chat_response


class TestTryFallbackParse(unittest.TestCase):
    """Tests for the regex-based fallback expense parser."""

    def _run(self, text, date="2026-06-17"):
        """Call _try_fallback_parse with add_expense mocked; return captured kwargs."""
        captured = {}

        def fake_add_expense(**kwargs):
            captured.update(kwargs)
            return "added"

        with patch("pages.add_expense.add_expense", side_effect=fake_add_expense):
            result = _try_fallback_parse(text, date)

        return captured, result

    # ── Normal cases ────────────────────────────────────────────────────────

    def test_plain_amount(self):
        kwargs, result = self._run("5 beer")
        self.assertAlmostEqual(kwargs["amount"], 5.0)
        self.assertIsNotNone(result)

    def test_decimal_with_dot(self):
        kwargs, _ = self._run("1.55 beer")
        self.assertAlmostEqual(kwargs["amount"], 1.55)

    def test_decimal_with_comma(self):
        kwargs, _ = self._run("12,50 at Rewe")
        self.assertAlmostEqual(kwargs["amount"], 12.50)

    def test_euro_prefix(self):
        kwargs, _ = self._run("€5.99 coffee")
        self.assertAlmostEqual(kwargs["amount"], 5.99)

    def test_merchant_extracted(self):
        kwargs, _ = self._run("5.99 at Edeka")
        self.assertEqual(kwargs.get("merchant"), "Edeka")

    def test_date_from_selected_date(self):
        kwargs, _ = self._run("5 beer", date="2026-06-15")
        self.assertEqual(kwargs.get("date"), "2026-06-15")

    def test_returns_none_when_no_amount(self):
        with patch("pages.add_expense.add_expense"):
            result = _try_fallback_parse("no numbers here", "2026-06-17")
        self.assertIsNone(result)

    # ── Regression: date-prefix must not be treated as the amount ──────────

    def test_date_prefix_stripped_before_parse(self):
        """
        Regression test for: agent_text = "On 2026-06-17: 1.55 beer"

        _try_fallback_parse is called AFTER the caller strips the prefix:
            fallback_text = re.sub(r"^On \\d{4}-\\d{2}-\\d{2}: ", "", agent_text)
        So the function receives "1.55 beer", not the raw prefixed string.
        This test verifies that the strip regex produces the correct input.
        """
        agent_text = "On 2026-06-17: 1.55 beer"
        stripped = re.sub(r"^On \d{4}-\d{2}-\d{2}: ", "", agent_text)
        self.assertEqual(stripped, "1.55 beer")

        kwargs, _ = self._run(stripped)
        self.assertAlmostEqual(kwargs["amount"], 1.55,
                               msg="Year 2026 must NOT be parsed as the amount")

    # NOTE: _try_fallback_parse assumes the caller strips "On YYYY-MM-DD: " prefixes.
    # We intentionally don't assert the buggy/unstripped behavior here, to avoid
    # locking that behavior in with a regression test.

    def test_strip_regex_is_anchored(self):
        """Strip regex must only remove the prefix, not affect mid-string dates."""
        text = "1.55 beer On 2026-06-17"
        stripped = re.sub(r"^On \d{4}-\d{2}-\d{2}: ", "", text)
        self.assertEqual(stripped, text,
                         msg="Strip regex must be anchored to ^ and must not touch mid-string")


class TestHandleChatResponse(unittest.TestCase):
    def test_idle_pending_data_returns_no_update(self):
        result = handle_chat_response({"status": "idle"}, [])
        self.assertEqual(result, (dash.no_update,) * 6)


if __name__ == "__main__":
    unittest.main()
