import re

import pandas as pd

# A year-first date: "2026-06-01", "2026/06/01", "2026.06.01", or compact "20260601".
_YEAR_FIRST = re.compile(r"^(?:\d{4}\D|\d{8}$)")


def parse_csv_date(raw) -> str:
    """Normalise a CSV date cell to YYYY-MM-DD.

    Year-first dates (ISO) are read as year-month-day. Anything else is read
    day-first (DD/MM/YYYY), which is the European convention this app expects.
    pandas' ``dayfirst=True`` alone swaps day and month for ISO dates
    ("2026-06-01" -> 2026-01-06), hence the explicit check.

    Raises ValueError (or a pandas parsing error) if the value is not a date.
    """
    text = str(raw).strip()
    parsed = pd.to_datetime(text, dayfirst=not _YEAR_FIRST.match(text))
    if pd.isna(parsed):
        raise ValueError(f"Not a date: {raw!r}")
    return parsed.strftime("%Y-%m-%d")
