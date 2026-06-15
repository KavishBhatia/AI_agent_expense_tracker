import json
import re

from google import genai

from expense_tracker_agent.tools import CATEGORIES

_MODEL = "gemini-2.5-flash"

_SYSTEM = (
    "You are an expense categoriser. Assign each expense exactly one category.\n"
    f"Allowed categories: {json.dumps(CATEGORIES)}\n\n"
    "Given a JSON array of expenses (each has 'description' and 'merchant'), "
    "return ONLY a JSON array of category strings in the same order. "
    "No explanation, no markdown fences."
)

_CHUNK_SIZE = 50


def classify_expenses(items: list[dict]) -> list[str]:
    """
    Classify a list of expenses using Gemini.

    items: list of {"description": str, "merchant": str}
    Returns: list of category strings (same length/order).
    Falls back to "Miscellaneous" on any error.
    """
    if not items:
        return []

    results: list[str] = []
    client = genai.Client()

    for start in range(0, len(items), _CHUNK_SIZE):
        chunk = items[start: start + _CHUNK_SIZE]
        prompt = f"{_SYSTEM}\n\nExpenses:\n{json.dumps(chunk, ensure_ascii=False)}"
        try:
            response = client.models.generate_content(model=_MODEL, contents=prompt)
            raw = response.text.strip()
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
            parsed = json.loads(raw)
            if isinstance(parsed, list) and len(parsed) == len(chunk):
                results.extend(c if c in CATEGORIES else "Miscellaneous" for c in parsed)
                continue
        except Exception:
            pass
        results.extend(["Miscellaneous"] * len(chunk))

    return results
