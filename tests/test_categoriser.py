# tests/test_categoriser.py
import json
import unittest
from unittest.mock import MagicMock, patch

from expense_tracker_agent.categoriser import (
    _CHUNK_SIZE,
    _rule_match,
    classify_expenses,
)


def _item(description="thing", merchant=""):
    return {"description": description, "merchant": merchant}


def _mock_genai(*responses):
    """Patch target: a genai module whose client returns the given response texts in order.

    A response that is an Exception instance is raised instead of returned.
    Returns (genai_mock, generate_content_mock).
    """
    genai_mock = MagicMock()
    generate = genai_mock.Client.return_value.models.generate_content
    side_effects = []
    for r in responses:
        if isinstance(r, Exception):
            side_effects.append(r)
        else:
            side_effects.append(MagicMock(text=r))
    generate.side_effect = side_effects
    return genai_mock, generate


class TestRuleMatch(unittest.TestCase):
    def test_exact_match(self):
        self.assertEqual(_rule_match("edeka"), "Groceries")

    def test_case_and_whitespace_insensitive(self):
        self.assertEqual(_rule_match("  EDEKA  "), "Groceries")

    def test_prefix_followed_by_space(self):
        self.assertEqual(_rule_match("Edeka Berlin Mitte"), "Groceries")

    def test_prefix_followed_by_hyphen(self):
        self.assertEqual(_rule_match("Lidl-Markt"), "Groceries")

    def test_multi_word_rule(self):
        self.assertEqual(_rule_match("Deutsche Bahn"), "Commute")

    def test_umlaut_and_ascii_variants(self):
        self.assertEqual(_rule_match("Müller"), "Personal Care")
        self.assertEqual(_rule_match("Muller"), "Personal Care")

    def test_drugstores(self):
        self.assertEqual(_rule_match("dm"), "Personal Care")
        self.assertEqual(_rule_match("Rossmann"), "Personal Care")

    def test_fuel_and_transport(self):
        for merchant in ("Shell", "Aral", "Esso", "Uber", "Bolt", "FlixBus"):
            self.assertEqual(_rule_match(merchant), "Commute", merchant)

    def test_prefix_must_end_at_a_word_boundary(self):
        # "dm" must not match "dmitri", "hit" must not match "hitman"
        self.assertIsNone(_rule_match("dmitri"))
        self.assertIsNone(_rule_match("hitman store"))

    def test_unknown_merchant_returns_none(self):
        self.assertIsNone(_rule_match("Some Random Shop"))

    def test_empty_merchant_returns_none(self):
        self.assertIsNone(_rule_match(""))
        self.assertIsNone(_rule_match("   "))


class TestClassifyExpensesRules(unittest.TestCase):
    def test_empty_list_returns_empty_without_calling_gemini(self):
        with patch("expense_tracker_agent.categoriser.genai") as genai_mock:
            self.assertEqual(classify_expenses([]), [])
        genai_mock.Client.assert_not_called()

    def test_all_rule_matches_skip_gemini(self):
        items = [_item("milk", "Edeka"), _item("shampoo", "dm"), _item("ticket", "Uber")]
        with patch("expense_tracker_agent.categoriser.genai") as genai_mock:
            result = classify_expenses(items)
        self.assertEqual(result, ["Groceries", "Personal Care", "Commute"])
        genai_mock.Client.assert_not_called()

    def test_missing_or_none_merchant_goes_to_gemini(self):
        genai_mock, generate = _mock_genai(json.dumps(["Gifts", "Education"]))
        items = [{"description": "book"}, {"description": "course", "merchant": None}]
        with patch("expense_tracker_agent.categoriser.genai", genai_mock):
            result = classify_expenses(items)
        self.assertEqual(result, ["Gifts", "Education"])
        self.assertEqual(generate.call_count, 1)


class TestClassifyExpensesGemini(unittest.TestCase):
    def test_rule_items_are_not_sent_to_gemini_and_order_is_preserved(self):
        items = [
            _item("milk", "Edeka"),          # rule
            _item("concert", "Ticketshop"),  # gemini
            _item("ticket", "Uber"),         # rule
            _item("gym", "FitX"),            # gemini
        ]
        genai_mock, generate = _mock_genai(json.dumps(["Entertainment", "Health & Fitness"]))
        with patch("expense_tracker_agent.categoriser.genai", genai_mock):
            result = classify_expenses(items)
        self.assertEqual(result, ["Groceries", "Entertainment", "Commute", "Health & Fitness"])
        prompt = generate.call_args.kwargs["contents"]
        self.assertIn("concert", prompt)
        self.assertIn("gym", prompt)
        self.assertNotIn("milk", prompt)
        self.assertNotIn("Uber", prompt)

    def test_strips_markdown_json_fences(self):
        genai_mock, _ = _mock_genai('```json\n["Gifts"]\n```')
        with patch("expense_tracker_agent.categoriser.genai", genai_mock):
            self.assertEqual(classify_expenses([_item("present", "Shop")]), ["Gifts"])

    def test_strips_plain_fences(self):
        genai_mock, _ = _mock_genai('```\n["Gifts"]\n```')
        with patch("expense_tracker_agent.categoriser.genai", genai_mock):
            self.assertEqual(classify_expenses([_item("present", "Shop")]), ["Gifts"])

    def test_unknown_category_becomes_miscellaneous(self):
        genai_mock, _ = _mock_genai(json.dumps(["Spaceships", "Gifts"]))
        with patch("expense_tracker_agent.categoriser.genai", genai_mock):
            result = classify_expenses([_item("a", "X"), _item("b", "Y")])
        self.assertEqual(result, ["Miscellaneous", "Gifts"])

    def test_wrong_length_response_falls_back_to_miscellaneous(self):
        genai_mock, _ = _mock_genai(json.dumps(["Gifts"]))
        with patch("expense_tracker_agent.categoriser.genai", genai_mock):
            result = classify_expenses([_item("a", "X"), _item("b", "Y")])
        self.assertEqual(result, ["Miscellaneous", "Miscellaneous"])

    def test_non_list_json_falls_back_to_miscellaneous(self):
        genai_mock, _ = _mock_genai(json.dumps({"category": "Gifts"}))
        with patch("expense_tracker_agent.categoriser.genai", genai_mock):
            self.assertEqual(classify_expenses([_item("a", "X")]), ["Miscellaneous"])

    def test_invalid_json_falls_back_to_miscellaneous(self):
        genai_mock, _ = _mock_genai("sorry, I cannot do that")
        with patch("expense_tracker_agent.categoriser.genai", genai_mock):
            self.assertEqual(classify_expenses([_item("a", "X")]), ["Miscellaneous"])

    def test_gemini_exception_falls_back_to_miscellaneous(self):
        genai_mock, _ = _mock_genai(RuntimeError("API down"))
        with patch("expense_tracker_agent.categoriser.genai", genai_mock):
            result = classify_expenses([_item("a", "X"), _item("b", "Y")])
        self.assertEqual(result, ["Miscellaneous", "Miscellaneous"])

    def test_gemini_failure_does_not_affect_rule_matched_items(self):
        genai_mock, _ = _mock_genai(RuntimeError("API down"))
        with patch("expense_tracker_agent.categoriser.genai", genai_mock):
            result = classify_expenses([_item("milk", "Edeka"), _item("a", "X")])
        self.assertEqual(result, ["Groceries", "Miscellaneous"])

    def test_prompt_lists_allowed_categories_and_keeps_non_ascii(self):
        genai_mock, generate = _mock_genai(json.dumps(["Gifts"]))
        with patch("expense_tracker_agent.categoriser.genai", genai_mock):
            classify_expenses([_item("Geschenk für Oma", "Bücherei")])
        prompt = generate.call_args.kwargs["contents"]
        self.assertIn("Housing & Utilities", prompt)
        self.assertIn("Geschenk für Oma", prompt)  # ensure_ascii=False


class TestClassifyExpensesChunking(unittest.TestCase):
    def test_chunk_size_is_50(self):
        # Documented in specs/spec.md (Gemini fallback runs in chunks of 50).
        self.assertEqual(_CHUNK_SIZE, 50)

    def test_splits_into_chunks_of_chunk_size(self):
        n = _CHUNK_SIZE * 2 + 20
        items = [_item(f"item{i}", f"Shop{i}") for i in range(n)]
        responses = [
            json.dumps(["Gifts"] * _CHUNK_SIZE),
            json.dumps(["Education"] * _CHUNK_SIZE),
            json.dumps(["Alcohol"] * 20),
        ]
        genai_mock, generate = _mock_genai(*responses)
        with patch("expense_tracker_agent.categoriser.genai", genai_mock):
            result = classify_expenses(items)
        self.assertEqual(generate.call_count, 3)
        self.assertEqual(len(result), n)
        self.assertEqual(result[:_CHUNK_SIZE], ["Gifts"] * _CHUNK_SIZE)
        self.assertEqual(result[_CHUNK_SIZE:2 * _CHUNK_SIZE], ["Education"] * _CHUNK_SIZE)
        self.assertEqual(result[2 * _CHUNK_SIZE:], ["Alcohol"] * 20)

    def test_exactly_one_chunk_makes_one_call(self):
        items = [_item(f"item{i}", f"Shop{i}") for i in range(_CHUNK_SIZE)]
        genai_mock, generate = _mock_genai(json.dumps(["Gifts"] * _CHUNK_SIZE))
        with patch("expense_tracker_agent.categoriser.genai", genai_mock):
            classify_expenses(items)
        self.assertEqual(generate.call_count, 1)

    def test_one_failing_chunk_does_not_affect_the_others(self):
        n = _CHUNK_SIZE + 5
        items = [_item(f"item{i}", f"Shop{i}") for i in range(n)]
        genai_mock, _ = _mock_genai(RuntimeError("boom"), json.dumps(["Gifts"] * 5))
        with patch("expense_tracker_agent.categoriser.genai", genai_mock):
            result = classify_expenses(items)
        self.assertEqual(result[:_CHUNK_SIZE], ["Miscellaneous"] * _CHUNK_SIZE)
        self.assertEqual(result[_CHUNK_SIZE:], ["Gifts"] * 5)

    def test_creates_one_client_for_all_chunks(self):
        items = [_item(f"item{i}", f"Shop{i}") for i in range(_CHUNK_SIZE + 1)]
        genai_mock, _ = _mock_genai(json.dumps(["Gifts"] * _CHUNK_SIZE), json.dumps(["Gifts"]))
        with patch("expense_tracker_agent.categoriser.genai", genai_mock):
            classify_expenses(items)
        genai_mock.Client.assert_called_once()


if __name__ == "__main__":
    unittest.main()
