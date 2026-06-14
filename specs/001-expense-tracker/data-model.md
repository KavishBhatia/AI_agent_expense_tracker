# Data Model

## Expense

The core entity. Stored as rows in `expenses.csv`.

```python
class Expense(BaseModel):
    id: int                          # auto-increment, assigned on save
    amount: float                    # positive number, e.g. 12.50
    category: str                    # one of the 8 predefined categories
    description: str                 # user-provided or LLM-inferred text
    merchant: Optional[str] = None   # store/restaurant name if extractable
    date: str                        # ISO date YYYY-MM-DD (resolved from NL)
    timestamp: str                   # ISO datetime YYYY-MM-DDTHH:MM:SS (write time)

    model_config = {"extra": "allow"}
```

### Field rules

| Field | Required | Source | Validation |
|-------|----------|--------|-----------|
| `id` | auto | assigned on `add_expense` | positive int |
| `amount` | yes | user / LLM extract | > 0 |
| `category` | auto | user or LLM infer | one of 8 values |
| `description` | yes | user text | non-empty string |
| `merchant` | no | LLM extract | string or null |
| `date` | auto | user or resolved | YYYY-MM-DD |
| `timestamp` | auto | write time | YYYY-MM-DDTHH:MM:SS |

### Predefined Categories

```python
CATEGORIES = [
    "Food",           # restaurants, cafes, fast food
    "Groceries",      # supermarkets, grocery stores
    "Transport",      # Uber, taxi, fuel, public transport
    "Entertainment",  # Netflix, cinema, games, events
    "Bills",          # electricity, gas, internet, rent, insurance
    "Healthcare",     # pharmacy, doctor, hospital
    "Shopping",       # clothing, electronics, Amazon
    "Other",          # fallback
]
```

## CSV Layout

File: `./expenses.csv` (project root, gitignored)

```
id,amount,category,description,merchant,date,timestamp
1,45.00,Groceries,Weekly groceries,Whole Foods,2026-06-03,2026-06-03T10:15:30
2,12.50,Food,Lunch,McDonald's,2026-06-03,2026-06-03T13:00:00
3,80.00,Bills,Electricity bill,,2026-06-01,2026-06-03T18:30:00
```

## State Transitions

```
User input (natural language)
    ↓  Gemini parses: amount, description, merchant, date, category
add_expense() called
    ↓  assigns id, timestamp
Expense appended to in-memory list + written to CSV row
    ↓
CSV file updated (append mode)
```

On agent restart: `expenses = _load_expenses()` reads all rows from CSV back into memory.
