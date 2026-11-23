# Tool Contracts

Function signatures and behaviour the Gemini agent relies on (`expense_tracker_agent/tools.py`, registered in `agent.py`).
Any change here requires updating both the implementation and the agent instruction (`_build_instruction`).

Dates are ISO `YYYY-MM-DD`; amounts are in euros. `category` must be one of `CATEGORIES` (16 values, see `data-model.md`).

---

## add_expense

```python
def add_expense(amount: float, description: str, category: str,
                merchant: str | None = None, date: str | None = None) -> str
```

1. Resolves `date` to today if omitted and normalises `merchant` to its canonical name.
2. If a merchant is given and the same date + merchant + amount already exists, returns a "Possible duplicate" warning and does **not** save.
3. Otherwise inserts the expense and returns a confirmation including the assigned id.

The agent must always supply a `category` (inferred if the user did not state one).

## force_add_expense

Same signature as `add_expense`, but skips the duplicate check. Use only after the user explicitly confirms ("add anyway").

## add_expense_item

```python
def add_expense_item(parent_id: int, amount: float, description: str, category: str) -> str
```

Adds a sub-item to an existing parent expense.

## list_expense_items

```python
def list_expense_items(parent_id: int) -> str
```

Lists sub-items of a parent expense, or "No items found".

## find_parent_expense_id

```python
def find_parent_expense_id(merchant: str, date: str) -> str
```

Returns the id of the parent expense for a merchant and date, as a string, or `not found`.

## import_csv_row

```python
def import_csv_row(date: str, amount: float, merchant: str, category: str = "Miscellaneous") -> str
```

Imports a single CSV row; returns an "Imported" or "Skipped (duplicate)" message.

## calculate_total_spending

```python
def calculate_total_spending(start_date: str | None = None, end_date: str | None = None) -> str
```

Sums spending, optionally within an inclusive date range.

## get_spending_by_category

```python
def get_spending_by_category(start_date: str | None = None, end_date: str | None = None) -> str
```

Spending per category, optionally within an inclusive date range.

## list_recent_expenses

```python
def list_recent_expenses(count: int = 5, category: str | None = None) -> str
```

Most recent `count` expenses, optionally filtered by category (case-insensitive).

---

## Agent Instruction Contract

The system prompt built by `_build_instruction(today)` must include:
1. Today's date, injected on every request
2. The category list with inference rules
3. Merchant extraction guidance, including the recognised merchant names (e.g. Action, Tedi, Woolworth, Amazon, Rossmann, Kaufland) and the "at [Store] for [item]" pattern
4. Relative date resolution ("yesterday", "last Monday")
5. The duplicate flow: on a duplicate warning, ask the user, and call `force_add_expense` only after they confirm
