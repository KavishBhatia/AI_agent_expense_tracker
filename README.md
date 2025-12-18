# Expense Tracker Agent

A simple, conversational agent to track your daily expenses, built using the Google Agent Development Kit (ADK).

## Features

-   **Add Expenses**: Log new expenses with amount, category, and a description.
-   **Calculate Total Spending**: Get a real-time calculation of your total expenses.
-   **View Spending by Category**: See a breakdown of your spending by category.
-   **List Recent Expenses**: Retrieve a list of your most recent transactions.

## Setup

1.  **Clone the Repository**

    ```bash
    git clone https://github.com/your-username/expense-tracker-agent.git
    cd expense-tracker-agent
    ```

2.  **Create a Virtual Environment**

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

3.  **Install Dependencies**

    Install all the required packages using the `requirements.txt` file:

    ```bash
    pip install -r requirements.txt
    ```
    
    Alternatively, you can install the project in editable mode, which is useful for development: 
    
    ```bash
    pip install -e .
    ```

4.  **Set Up Environment Variables**

    The agent requires a Gemini API key to function. Create a `.env` file in the root of the project:

    ```bash
    cp .env.example .env
    ```

    Then, open the `.env` file and add your API key:

    ```
    GEMINI_API_KEY="YOUR_API_KEY"
    ```

## How to Run

You can run the agent by executing the `test_agent.py` script. This script simulates a conversation with the agent and demonstrates its key features.

```bash
python test_agent.py
```

You should see an output where the agent processes several commands, adds expenses, and reports the totals.

## Example Usage

The `test_agent.py` script provides a clear example of how to interact with the agent. Here's a snippet:

```python
import asyncio
from expense_tracker_agent.agent import root_agent

async def run_agent_test():
    print("--- Adding an expense (Food) ---")
    response = root_agent.chat("Add an expense of 50 for food, description: Lunch with friends")
    print(response)

    print("\n--- Getting total expenses ---")
    response = root_agent.chat("What are my total expenses?")
    print(response)
    
    print("\n--- Listing recent expenses ---")
    response = root_agent.chat("List my recent expenses")
    print(response)

if __name__ == "__main__":
    asyncio.run(run_agent_test())
```

This demonstrates how you can import the `root_agent` and use its `.chat()` method to have a conversation.