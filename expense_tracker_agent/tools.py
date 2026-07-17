# expense_tracker_agent/tools.py
from datetime import date as _date
from typing import Optional

from expense_tracker_agent.db import (
    expense_exists,
    fetch_expense_items,
    fetch_expenses,
    find_parent_expense,
    init_db,
    insert_expense,
    insert_expense_item,
    normalize_merchant,
)

CATEGORIES = [
    "Groceries",
    "Food & Dining",
    "Commute",
    "Entertainment",
    "Clothing & Fashion",
    "Pharmacy",
    "Health & Fitness",
    "Housing & Utilities",
    "Travel",
    "Electronics",
    "Subscriptions",
    "Personal Care",
    "Education",
    "Gifts",
    "Alcohol",
    "Miscellaneous",
]

init_db()


def add_expense(
    amount: float,
    description: str,
    category: str,
    merchant: Optional[str] = None,
    date: Optional[str] = None,
) -> str:
    """
    Adds an expense to the tracker. Checks for duplicates when a merchant is
    provided (same date + merchant + amount). Returns a warning without saving
    if a duplicate is found — call force_add_expense if the user confirms.

    Args:
        amount: The numerical amount of the expense.
        description: A brief description of the expense.
        category: The category (must be one of CATEGORIES).
        merchant: Optional merchant or store name.
        date: ISO date YYYY-MM-DD; defaults to today.

    Returns:
        A confirmation message including the assigned expense id, or a
        duplicate warning if an identical expense already exists.
    """
    resolved_date = date or _date.today().isoformat()
    canonical = normalize_merchant(merchant)
    if canonical and expense_exists(resolved_date, canonical, amount):
        return (
            f"⚠️ Possible duplicate: a {canonical} expense of €{amount:.2f} "
            f"already exists on {resolved_date}. Expense was NOT saved. "
            f"If this is intentional, say 'add anyway'."
        )
    eid = insert_expense(
        amount=amount,
        category=category,
        description=description,
        merchant=merchant,
        date=resolved_date,
        source="ai_chat",
    )
    return f"Added expense #{eid}: {description} — €{amount:.2f} [{category}] on {resolved_date}"


def force_add_expense(
    amount: float,
    description: str,
    category: str,
    merchant: Optional[str] = None,
    date: Optional[str] = None,
) -> str:
    """
    Adds an expense, bypassing the duplicate check. Use ONLY when the user
    has explicitly confirmed they want to save despite a detected duplicate.

    Args:
        amount: The numerical amount of the expense.
        description: A brief description of the expense.
        category: The category (must be one of CATEGORIES).
        merchant: Optional merchant or store name.
        date: ISO date YYYY-MM-DD; defaults to today.

    Returns:
        A confirmation message including the assigned expense id.
    """
    resolved_date = date or _date.today().isoformat()
    eid = insert_expense(
        amount=amount,
        category=category,
        description=description,
        merchant=merchant,
        date=resolved_date,
        source="ai_chat",
    )
    return f"Added expense #{eid}: {description} — €{amount:.2f} [{category}] on {resolved_date}"


def add_expense_item(
    parent_id: int,
    amount: float,
    description: str,
    category: str,
) -> str:
    """
    Adds a sub-item to an existing parent expense.

    Args:
        parent_id: The id of the parent expense (from add_expense).
        amount: The numerical amount of the sub-item.
        description: A brief description (e.g. 'beer').
        category: The category of the sub-item.

    Returns:
        A confirmation message.
    """
    existing_ids = {e["id"] for e in fetch_expenses()}
    if parent_id not in existing_ids:
        return f"Error: expense #{parent_id} not found."
    iid = insert_expense_item(parent_id, amount, description, category)
    return f"Added item #{iid}: {description} — €{amount:.2f} [{category}] under expense #{parent_id}"


def list_expense_items(parent_id: int) -> str:
    """
    Lists all sub-items for a parent expense.

    Args:
        parent_id: The id of the parent expense.

    Returns:
        A formatted list of sub-items.
    """
    items = fetch_expense_items(parent_id)
    if not items:
        return f"No items found for expense #{parent_id}."
    lines = [f"Items for expense #{parent_id}:"]
    for it in items:
        lines.append(f"  - {it['description']} ({it['category']}): €{it['amount']:.2f}")
    return "\n".join(lines)


def find_parent_expense_id(merchant: str, date: str) -> str:
    """
    Finds an existing parent expense by merchant and date.

    Args:
        merchant: The store or restaurant name.
        date: ISO date YYYY-MM-DD.

    Returns:
        The parent expense id as a string, or 'not found'.
    """
    eid = find_parent_expense(merchant, date)
    if eid is None:
        return "not found"
    return str(eid)


def import_csv_row(date: str, amount: float, merchant: str, category: str = "Miscellaneous") -> str:
    """
    Imports a single row from a CSV file, skipping duplicates.

    Args:
        date: ISO date YYYY-MM-DD.
        amount: The expense amount.
        merchant: The supermarket or store name.
        category: Pre-classified category (defaults to Miscellaneous).

    Returns:
        'Imported' or 'Skipped (duplicate)' message.
    """
    if expense_exists(date, merchant, amount):
        return f"Skipped (duplicate): {merchant} €{amount:.2f} on {date}"
    insert_expense(
        amount=amount,
        category=category,
        description=f"Import: {merchant}",
        merchant=merchant,
        date=date,
        source="csv_import",
    )
    return f"Imported: {merchant} €{amount:.2f} on {date}"


def calculate_total_spending(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    Calculates total spending, optionally within a date range.

    Args:
        start_date: ISO date inclusive lower bound.
        end_date: ISO date inclusive upper bound.

    Returns:
        A string with the total spending.
    """
    rows = fetch_expenses(start_date, end_date)
    total = sum(r["amount"] for r in rows)
    return f"Total spending: €{total:.2f}"


def get_spending_by_category(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> str:
    """
    Gets spending per category, optionally within a date range.

    Args:
        start_date: ISO date inclusive lower bound.
        end_date: ISO date inclusive upper bound.

    Returns:
        A string with spending per category.
    """
    rows = fetch_expenses(start_date, end_date)
    if not rows:
        return "No spending to report."
    totals: dict[str, float] = {}
    for r in rows:
        totals[r["category"]] = totals.get(r["category"], 0) + r["amount"]
    lines = ["Spending by category:"]
    for cat, amt in sorted(totals.items(), key=lambda x: -x[1]):
        lines.append(f"  - {cat}: €{amt:.2f}")
    return "\n".join(lines)


def list_recent_expenses(count: int = 5, category: Optional[str] = None) -> str:
    """
    Lists the most recent expenses.

    Args:
        count: Number of expenses to return.
        category: Optional case-insensitive category filter.

    Returns:
        A formatted string of recent expenses.
    """
    rows = fetch_expenses()
    if category:
        rows = [r for r in rows if r["category"].lower() == category.lower()]
    if not rows:
        return "No expenses to report."
    recent = rows[-count:]
    lines = ["Recent expenses:"]
    for r in recent:
        lines.append(f"  - {r['description']} ({r['category']}): €{r['amount']:.2f} on {r['date']}")
    return "\n".join(lines)
