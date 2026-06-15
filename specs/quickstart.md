# Quickstart

## Prerequisites

```bash
pip install -e .
# Set GEMINI_API_KEY in .env or environment
export GEMINI_API_KEY=<your-key>
```

## Run the agent

```bash
adk run expense_tracker_agent
```

Or via the ADK web UI:
```bash
adk web
```

## Example interactions

```
You: Spent $45 at Whole Foods today
Agent: Added: Whole Foods — $45.00 [Groceries] on 2026-06-03

You: Lunch at McDonald's was $12.50 yesterday
Agent: Added: McDonald's — $12.50 [Food] on 2026-06-02

You: electricity bill 80
Agent: Added: electricity bill — $80.00 [Bills] on 2026-06-03

You: How much have I spent total?
Agent: Total spending: $137.50

You: Show me spending by category
Agent: Spending by category:
       - Groceries: $45.00
       - Food: $12.50
       - Bills: $80.00

You: List my last 3 expenses
Agent: Recent expenses:
       - electricity bill (Bills): $80.00 on 2026-06-03
       - McDonald's (Food): $12.50 on 2026-06-02
       - Whole Foods (Groceries): $45.00 on 2026-06-03
```

## Data file

Expenses are saved to `./expenses.csv` in the project root. This file persists between sessions and can be opened in Excel or Numbers.

## Run tests

```bash
python -m pytest test_agent.py -v
# or
python -m unittest test_agent.py
```
