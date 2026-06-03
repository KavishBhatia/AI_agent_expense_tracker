import csv
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

CSV_FILE = Path("expenses.csv")

CATEGORIES = ["Food", "Groceries", "Transport", "Entertainment",
               "Bills", "Healthcare", "Shopping", "Other"]


class Expense(BaseModel):
    id: int = Field(description="Auto-assigned sequential ID.")
    amount: float = Field(description="The numerical amount of the expense.")
    category: str = Field(description="The category of the expense.")
    description: str = Field(description="A brief description of the expense.")
    merchant: Optional[str] = Field(default=None, description="Merchant or store name.")
    date: str = Field(description="ISO date YYYY-MM-DD of the expense.")
    timestamp: str = Field(description="ISO datetime when the expense was recorded.")
    model_config = {"extra": "allow"}


def _load_expenses() -> list[Expense]:
    if not CSV_FILE.exists():
        return []
    with open(CSV_FILE, newline="") as f:
        return [Expense(**row) for row in csv.DictReader(f)]


def _save_expense(expense: Expense) -> None:
    write_header = not CSV_FILE.exists()
    fieldnames = ["id", "amount", "category", "description", "merchant", "date", "timestamp"]
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            writer.writeheader()
        writer.writerow({k: getattr(expense, k, None) for k in fieldnames})


expenses: list[Expense] = _load_expenses()


def add_expense(
    amount: float,
    description: str,
    category: str,
    merchant: Optional[str] = None,
    date: Optional[str] = None,
) -> str:
    """
    Adds an expense to the tracker.

    Args:
        amount: The numerical amount of the expense.
        description: A brief description of the expense.
        category: The category (must be one of CATEGORIES).
        merchant: Optional merchant or store name.
        date: ISO date YYYY-MM-DD; defaults to today.

    Returns:
        A confirmation message.
    """
    resolved_date = date if date else _today()
    expense = Expense(
        id=len(expenses) + 1,
        amount=amount,
        category=category,
        description=description,
        merchant=merchant,
        date=resolved_date,
        timestamp=datetime.now().isoformat(timespec="seconds"),
    )
    expenses.append(expense)
    _save_expense(expense)
    return f"Added: {description} — ${amount:.2f} [{category}] on {resolved_date}"


def calculate_total_spending(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    Calculates the total spending, optionally within a date range.

    Args:
        start_date: ISO date inclusive lower bound.
        end_date: ISO date inclusive upper bound.

    Returns:
        A string with the total spending.
    """
    filtered = _filter_by_date(expenses, start_date, end_date)
    total = sum(e.amount for e in filtered)
    return f"Total spending: ${total:.2f}"


def get_spending_by_category(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    Gets the spending for each category, optionally within a date range.

    Args:
        start_date: ISO date inclusive lower bound.
        end_date: ISO date inclusive upper bound.

    Returns:
        A string with the spending per category.
    """
    filtered = _filter_by_date(expenses, start_date, end_date)
    totals: dict[str, float] = {}
    for e in filtered:
        totals[e.category] = totals.get(e.category, 0) + e.amount

    if not totals:
        return "No spending to report."

    report = "Spending by category:\n"
    for category, amount in totals.items():
        report += f"- {category}: ${amount:.2f}\n"
    return report


def list_recent_expenses(count: int = 5, category: Optional[str] = None) -> str:
    """
    Lists the most recent expenses.

    Args:
        count: The number of recent expenses to list.
        category: Optional case-insensitive category filter.

    Returns:
        A string with the recent expenses.
    """
    pool = expenses
    if category:
        pool = [e for e in pool if e.category.lower() == category.lower()]

    if not pool:
        return "No expenses to report."

    recent = pool[-count:]
    report = "Recent expenses:\n"
    for e in recent:
        report += f"- {e.description} ({e.category}): ${e.amount:.2f} on {e.date}\n"
    return report


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _today() -> str:
    from datetime import date as _date
    return _date.today().isoformat()


def _filter_by_date(
    expense_list: list[Expense],
    start_date: Optional[str],
    end_date: Optional[str],
) -> list[Expense]:
    result = expense_list
    if start_date:
        result = [e for e in result if e.date >= start_date]
    if end_date:
        result = [e for e in result if e.date <= end_date]
    return result
