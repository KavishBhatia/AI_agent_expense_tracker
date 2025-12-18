from pydantic import BaseModel, Field

# In-memory database for expenses
expenses = []


class Expense(BaseModel):
    """Data model for a single expense."""
    amount: float = Field(description="The numerical amount of the expense.")
    category: str = Field(description="The category of the expense (e.g., Food, Transport, Bills).")
    description: str = Field(description="A brief description of the expense.")
    model_config = {
        "extra": "allow"  # allow unknown fields
    }


def add_expense(amount: float, category: str, description: str) -> str:
    """
    Adds an expense to the tracker.

    Args:
        amount: The numerical amount of the expense.
        category: The category of the expense.
        description: A brief description of the expense.
    
    Returns:
        A confirmation message that the expense has been added.
    """
    expense = Expense(amount=amount, category=category, description=description)
    expenses.append(expense)
    return f"Successfully added expense: {description} ({amount}) in {category}"


def calculate_total_spending() -> str:
    """
    Calculates the total spending.

    Returns:
        A string with the total spending.
    """
    total = sum(expense.amount for expense in expenses)
    return f"Total spending: ${total:.2f}"


def get_spending_by_category() -> str:
    """
    Gets the spending for each category.

    Returns:
        A string with the spending for each category.
    """
    spending_by_category = {}
    for expense in expenses:
        if expense.category not in spending_by_category:
            spending_by_category[expense.category] = 0
        spending_by_category[expense.category] += expense.amount

    if not spending_by_category:
        return "No spending to report."

    report = "Spending by category:\n"
    for category, amount in spending_by_category.items():
        report += f"- {category}: ${amount:.2f}\n"
    return report


def list_recent_expenses(count: int = 5) -> str:
    """
    Lists the most recent expenses.

    Args:
        count: The number of recent expenses to list.

    Returns:
        A string with the recent expenses.
    """
    if not expenses:
        return "No expenses to report."

    recent_expenses = expenses[-count:]
    report = "Recent expenses:\n"
    for expense in recent_expenses:
        report += f"- {expense.description} ({expense.category}): ${expense.amount:.2f}\n"
    return report

