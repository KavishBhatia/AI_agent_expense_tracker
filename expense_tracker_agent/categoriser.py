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

# Deterministic merchant → category rules applied BEFORE sending to Gemini.
# Keys are lowercase; matched when the merchant name equals or starts with the key.
_MERCHANT_RULES: dict[str, str] = {
    # Grocery chains (DE)
    "edeka": "Groceries",
    "aldi": "Groceries",
    "lidl": "Groceries",
    "netto": "Groceries",
    "rewe": "Groceries",
    "kaufland": "Groceries",
    "penny": "Groceries",
    "tegut": "Groceries",
    "norma": "Groceries",
    "nahkauf": "Groceries",
    "hit": "Groceries",
    # Drugstores (DE)
    "dm": "Personal Care",
    "rossmann": "Personal Care",
    "müller": "Personal Care",
    "muller": "Personal Care",
    # Pharmacies
    # Commute
    "db": "Commute",
    "deutsche bahn": "Commute",
    "flixbus": "Commute",
    "uber": "Commute",
    "bolt": "Commute",
    # Fuel
    "shell": "Commute",
    "aral": "Commute",
    "esso": "Commute",
    "total": "Commute",
}


def _rule_match(merchant: str) -> str | None:
    """Return a category if the merchant matches a known rule, else None."""
    m = merchant.strip().lower()
    for prefix, category in _MERCHANT_RULES.items():
        if m == prefix or m.startswith(prefix + " ") or m.startswith(prefix + "-"):
            return category
    return None


def classify_expenses(items: list[dict]) -> list[str]:
    """
    Classify a list of expenses using merchant rules first, then Gemini for the rest.

    items: list of {"description": str, "merchant": str}
    Returns: list of category strings (same length/order).
    Falls back to "Miscellaneous" on any Gemini error.
    """
    if not items:
        return []

    # Apply deterministic merchant rules; track which indices still need Gemini
    results: list[str | None] = [None] * len(items)
    ai_indices: list[int] = []
    for i, item in enumerate(items):
        rule = _rule_match(item.get("merchant") or "")
        if rule:
            results[i] = rule
        else:
            ai_indices.append(i)

    if ai_indices:
        ai_items = [items[i] for i in ai_indices]
        client = genai.Client()
        ai_results: list[str] = []

        for start in range(0, len(ai_items), _CHUNK_SIZE):
            chunk = ai_items[start: start + _CHUNK_SIZE]
            prompt = f"{_SYSTEM}\n\nExpenses:\n{json.dumps(chunk, ensure_ascii=False)}"
            try:
                response = client.models.generate_content(model=_MODEL, contents=prompt)
                raw = response.text.strip()
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
                parsed = json.loads(raw)
                if isinstance(parsed, list) and len(parsed) == len(chunk):
                    ai_results.extend(c if c in CATEGORIES else "Miscellaneous" for c in parsed)
                    continue
            except Exception:
                pass
            ai_results.extend(["Miscellaneous"] * len(chunk))

        for idx, cat in zip(ai_indices, ai_results):
            results[idx] = cat

    return [r or "Miscellaneous" for r in results]
