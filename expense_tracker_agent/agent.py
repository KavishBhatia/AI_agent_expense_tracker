from datetime import date

from google.adk.agents import Agent
from google.adk.models import Gemini

from expense_tracker_agent.tools import (
    CATEGORIES,
    add_expense,
    add_expense_item,
    calculate_total_spending,
    find_parent_expense_id,
    get_spending_by_category,
    import_csv_row,
    list_expense_items,
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
        "- merchant: extract from patterns like 'at X', 'from X', 'bei X', '@ X', "
        "OR when a known store name appears at the start of the message followed by 'for' "
        "(e.g. 'Aldi for pink dress' → merchant='Aldi', 'dm for shampoo' → merchant='dm'). "
        "Use whatever follows those keywords verbatim, even if it is a short abbreviation "
        "(e.g. 'at dm' → merchant='dm', 'at Edeka' → merchant='Edeka', 'bei Rewe' → merchant='Rewe')\n"
        "- description: the item or purpose of the expense — for '[Store] for [item]' patterns "
        "use the part after 'for' as the description (e.g. 'Aldi for pink night dress set' → "
        "description='pink night dress set')\n"
        f"- category: infer from the **description** (not the merchant) using the rules below. "
        "The merchant is just where it was bought — what was bought determines the category. "
        "E.g. 'pink night dress at Aldi' → Clothing & Fashion, 'protein powder at dm' → Health & Fitness (required)\n"
        "- date: resolve relative dates like 'yesterday' or 'last Monday' to "
        f"YYYY-MM-DD using today ({today}) as reference; default to today if omitted\n\n"
        "## Sub-items\n"
        "If the user says something like '3 euro beer, part of today's Edeka shop', "
        "call find_parent_expense_id(merchant, date) first. "
        "If it returns a number, use that as parent_id for add_expense_item(parent_id, amount, description, category). "
        "If it returns 'not found', call add_expense() to create the parent first, then add_expense_item().\n\n"
        f"## Category inference rules\n"
        f"Always assign one of: {categories_str}.\n"
        "Rules:\n"
        "- groceries, food items, supermarket purchases → Groceries\n"
        "- restaurants, cafes, fast food, takeaway → Food & Dining\n"
        "- Uber, taxi, fuel, bus, train, metro, DB, FlixBus → Transport\n"
        "- Netflix, cinema, games, concerts, events, streaming → Entertainment\n"
        "- electricity, gas, internet, rent, insurance → Housing & Utilities\n"
        "- pharmacy, doctor, hospital, dentist, apotheke, medicine → Pharmacy\n"
        "- clothing, shoes, accessories, fashion → Clothing & Fashion\n"
        "- electronics, gadgets, computers, cables → Electronics\n"
        "- fitness, gym, protein, supplements, sports → Health & Fitness\n"
        "- shampoo, skincare, cosmetics, toiletries, personal hygiene → Personal Care\n"
        "- beer, wine, spirits, cocktails, alcohol → Alcohol\n"
        "- anything else → Miscellaneous\n\n"
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
        add_expense_item,
        find_parent_expense_id,
        list_expense_items,
        calculate_total_spending,
        get_spending_by_category,
        list_recent_expenses,
        import_csv_row,
    ],
)
