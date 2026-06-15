# Tool Contracts

These are the function signatures and behaviours the Gemini agent relies on.
Any change to these contracts requires updating both the implementation and the agent instruction.

---

## add_expense

```python
def add_expense(
    amount: float,
    description: str,
    category: str,
    merchant: str | None = None,
    date: str | None = None,        # ISO YYYY-MM-DD; defaults to today
) -> str
```

**Behaviour**:
1. Assigns `id` = len(current expenses) + 1
2. Assigns `timestamp` = current datetime ISO string
3. Resolves `date` to today if not provided
4. Appends `Expense` to in-memory `expenses` list
5. Appends row to `expenses.csv` (creates file + header if not exists)
6. Returns: `"Added: {description} — ${amount:.2f} [{category}] on {date}"`

**Gemini calling guidance**: Gemini must always populate `category` (inferred if not stated). `merchant` and `date` are optional.

---

## calculate_total_spending

```python
def calculate_total_spending(
    start_date: str | None = None,   # ISO YYYY-MM-DD, inclusive
    end_date: str | None = None,     # ISO YYYY-MM-DD, inclusive
) -> str
```

**Behaviour**: Sums `amount` for all expenses within optional date range.
Returns: `"Total spending: ${total:.2f}"` (optionally with date range note)

---

## get_spending_by_category

```python
def get_spending_by_category(
    start_date: str | None = None,
    end_date: str | None = None,
) -> str
```

**Behaviour**: Groups expenses by category within optional date range.
Returns formatted multi-line string: `"- {category}: ${amount:.2f}\n"`

---

## list_recent_expenses

```python
def list_recent_expenses(
    count: int = 5,
    category: str | None = None,    # filter by category (case-insensitive)
) -> str
```

**Behaviour**: Returns the most recent `count` expenses, optionally filtered by category.
Returns formatted multi-line string.

---

## Agent Instruction Contract

The Gemini system prompt must include:
1. Today's date (injected at agent construction time)
2. The predefined category list with inference rules
3. Instructions to extract `merchant` and resolve relative dates
4. Instruction to always call `add_expense` with a resolved `category`
