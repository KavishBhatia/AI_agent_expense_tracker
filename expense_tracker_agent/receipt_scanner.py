# expense_tracker_agent/receipt_scanner.py
import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from google import genai
from google.genai import errors, types

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
- today's date is TODAY; use it only if the receipt shows no readable date
- date must be YYYY-MM-DD; receipts often print DD.MM.YY or DD.MM.YYYY, convert accordingly
- amounts in euros as floats
- category must be exactly one of the allowed values
- return ONLY the JSON object, no markdown fences
""".replace("CATEGORY_LIST", ", ".join(CATEGORIES))

# A receipt older than this (or dated in the future) gets an extra warning in the confirm dialog.
STALE_DATE_DAYS = 30


def normalize_receipt_date(raw: str, today: Optional[date] = None) -> str:
    """Return raw if it is a valid ISO date, otherwise today's date. Past dates are kept."""
    today = today or date.today()
    try:
        return date.fromisoformat(raw.strip() if isinstance(raw, str) else "").isoformat()
    except ValueError:
        return today.isoformat()


def date_needs_attention(iso_date: str, today: Optional[date] = None) -> bool:
    """True if the date is in the future or more than STALE_DATE_DAYS old (or invalid)."""
    today = today or date.today()
    try:
        d = date.fromisoformat(iso_date)
    except ValueError:
        return True
    return d > today or (today - d).days > STALE_DATE_DAYS


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


class ReceiptScanError(Exception):
    """The scan could not reach or use Gemini; the message is safe to show to the user."""


def _api_error_message(exc: errors.APIError) -> str:
    if exc.code in (401, 403):
        return "Gemini rejected the API key. Check GOOGLE_API_KEY in .env."
    if exc.code == 429:
        return "Gemini quota exceeded. Wait a bit and try again."
    return f"Gemini request failed ({exc.code}). Try again in a moment."


def parse_receipt(image_bytes: bytes, mime_type: str = "image/jpeg") -> Optional[ReceiptData]:
    """Return parsed data, None if the reply isn't a valid receipt, or raise ReceiptScanError."""
    try:
        client = genai.Client()
    except ValueError as exc:
        raise ReceiptScanError(
            "Gemini API key is missing or invalid. Check GOOGLE_API_KEY in .env."
        ) from exc
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[_PROMPT.replace("TODAY", date.today().isoformat()), image_part],
        )
    except errors.APIError as exc:
        raise ReceiptScanError(_api_error_message(exc)) from exc
    if not response.text:
        raise ReceiptScanError("Gemini returned no text for this image. Try a clearer photo.")
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
            date=normalize_receipt_date(data.get("date", "")),
            total=float(data.get("total", 0.0)),
            items=items,
        )
    except (json.JSONDecodeError, KeyError, ValueError):
        return None
