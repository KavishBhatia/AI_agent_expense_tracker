# expense_tracker_agent/receipt_scanner.py
import json
import re
from dataclasses import dataclass, field
from typing import Optional

import google.generativeai as genai

from expense_tracker_agent.tools import CATEGORIES

_PROMPT = """
You are a receipt parser. Analyse this receipt image and return ONLY valid JSON with this structure:
{
  "merchant": "store name",
  "date": "YYYY-MM-DD",
  "total": 0.00,
  "items": [
    {"description": "item name", "amount": 0.00, "category": "one of CATEGORIES"}
  ]
}

Categories allowed: CATEGORY_LIST

Rules:
- date must be YYYY-MM-DD; use today if unclear
- amounts in euros as floats
- category must be exactly one of the allowed values
- return ONLY the JSON object, no markdown fences
""".replace("CATEGORY_LIST", ", ".join(CATEGORIES))


@dataclass
class ReceiptItem:
    description: str
    amount: float
    category: str


@dataclass
class ReceiptData:
    merchant: str
    date: str
    total: float
    items: list[ReceiptItem] = field(default_factory=list)


def parse_receipt(image_bytes: bytes, mime_type: str = "image/jpeg") -> Optional[ReceiptData]:
    model = genai.GenerativeModel("gemini-2.5-flash")
    image_part = {"mime_type": mime_type, "data": image_bytes}
    response = model.generate_content([_PROMPT, image_part])
    raw = response.text.strip()
    # strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        items = [
            ReceiptItem(
                description=it["description"],
                amount=float(it["amount"]),
                category=it.get("category", "Other"),
            )
            for it in data.get("items", [])
        ]
        return ReceiptData(
            merchant=data.get("merchant", "Unknown"),
            date=data.get("date", ""),
            total=float(data.get("total", 0.0)),
            items=items,
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return None
