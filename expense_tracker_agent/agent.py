from google.adk.agents import Agent
from expense_tracker_agent.tools import (
    add_expense,
    calculate_total_spending,
    get_spending_by_category,
    list_recent_expenses,
)

root_agent = Agent(
    name="expense_tracker",
    model="gemini-2.5-flash",
    instruction=(
        "You are an expense tracking agent."
        " Use the tools to log user expenses, calculate total spending, get spending by category, and list recent expenses."
        " If the user does not provide all the necessary information, "
        " ask for the missing details."
    ),
    tools=[
        add_expense,
        calculate_total_spending,
        get_spending_by_category,
        list_recent_expenses,
    ],
)
