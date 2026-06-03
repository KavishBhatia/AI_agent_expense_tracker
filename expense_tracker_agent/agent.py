from datetime import date

from google.adk.agents import Agent
from google.adk.models import Gemini
from expense_tracker_agent.tools import (
    CATEGORIES,
    add_expense,
    calculate_total_spending,
    get_spending_by_category,
    list_recent_expenses,
)


def _build_instruction(today: str) -> str:
    categories_str = ", ".join(CATEGORIES)
    return (
        f"You are an expense tracking agent. Today's date is {today}.\n"
        "Use the tools to log user expenses, calculate total spending, "
        "get spending by category, and list recent expenses.\n\n"
        "## Adding expenses\n"
        "When the user describes an expense, extract all fields from their message:\n"
        "- amount: the number (required)\n"
        "- description: a short label for the expense (required)\n"
        "- merchant: the store or restaurant name if mentioned (optional)\n"
        f"- category: infer from the description using the rules below (required)\n"
        "- date: resolve relative dates like 'yesterday' or 'last Monday' to "
        f"YYYY-MM-DD using today ({today}) as reference; default to today if omitted\n\n"
        f"## Category inference rules\n"
        f"Always assign one of: {categories_str}.\n"
        "Rules:\n"
        "- grocery stores, supermarkets → Groceries\n"
        "- restaurants, cafes, fast food → Food\n"
        "- Uber, taxi, fuel, bus, train, metro → Transport\n"
        "- Netflix, cinema, games, concerts, events → Entertainment\n"
        "- electricity, gas, internet, rent, insurance → Bills\n"
        "- pharmacy, doctor, hospital, dentist → Healthcare\n"
        "- clothing, electronics, Amazon, online shopping → Shopping\n"
        "- anything else → Other\n\n"
        "If the user does not provide the amount, ask for it before calling add_expense. "
        "Never ask for the category — infer it yourself. "
        "Never ask for merchant or date — extract them from context or omit them."
    )


root_agent = Agent(
    name="expense_tracker",
    model=Gemini(model="gemini-2.5-flash"),
    instruction=_build_instruction(today=date.today().isoformat()),
    tools=[
        add_expense,
        calculate_total_spending,
        get_spending_by_category,
        list_recent_expenses,
    ],
)
