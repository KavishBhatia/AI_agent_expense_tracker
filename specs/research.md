# Research: Expense Tracker Improvements

## 1. CSV Persistence for Python Agent Tools

**Decision**: Use Python's built-in `csv.DictWriter` / `csv.DictReader` with a fixed `expenses.csv` path.

**Rationale**:
- Zero new dependencies (user confirmed CSV; stdlib `csv` module handles it)
- Human-readable, editable in Excel/Numbers
- `DictWriter` preserves column ordering; `DictReader` handles missing fields gracefully
- Thread-safety not a concern (single-user local tool)

**Implementation pattern**:
```python
CSV_FILE = Path("expenses.csv")
FIELDNAMES = ["id", "amount", "category", "description", "merchant", "date", "timestamp"]

def _load_expenses():
    if CSV_FILE.exists():
        with open(CSV_FILE, newline="") as f:
            return [Expense(**row) for row in csv.DictReader(f)]
    return []

def _save_expense(expense: Expense):
    write_header = not CSV_FILE.exists()
    with open(CSV_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(expense.model_dump())
```

**Alternative considered**: SQLite — overkill for personal single-user tool; no benefit over CSV for this scale.

---

## 2. Auto-categorization Strategy

**Decision**: Extend the Gemini system prompt with a predefined category list and explicit inference rules. No separate API call.

**Rationale**:
- The agent already invokes Gemini for every user turn; adding category inference to the same prompt adds zero latency
- Gemini 2.5 Flash is capable of reliable category mapping from merchant/description context
- A keyword-based fallback (e.g., "grocery"→Groceries) would be brittle and hard to maintain

**Category list** (8 categories, intentionally small to avoid ambiguity):
```
Food, Groceries, Transport, Entertainment, Bills, Healthcare, Shopping, Other
```

**Prompt addition**:
```
When calling add_expense, infer the category from the description or merchant 
if the user has not specified one. Use only these categories: 
Food, Groceries, Transport, Entertainment, Bills, Healthcare, Shopping, Other.
Rules: grocery stores → Groceries; restaurants/cafes/fast food → Food; 
Uber/taxi/fuel/bus/train → Transport; Netflix/cinema/games → Entertainment; 
electricity/gas/internet/rent/insurance → Bills; 
pharmacy/doctor/hospital → Healthcare; clothing/electronics/Amazon → Shopping; 
default → Other.
```

**Alternative considered**: A separate Python keyword-matching function — rejected because Gemini handles edge cases (e.g., "Pret a Manger" → Food) better than a regex table.

---

## 3. Natural Language Input Parsing

**Decision**: Rely on Gemini for NL parsing via improved system prompt; no external NLP library.

**Rationale**:
- `add_expense` tool call is already triggered by Gemini — the model extracts `amount`, `description`, `category` from user text. We extend this to also extract `merchant` and `date`.
- Adding `merchant` as an optional tool parameter is the key change; Gemini populates it from context ("Whole Foods", "McDonald's").
- Date handling: Gemini can resolve "yesterday"/"today" if the current date is injected into the system prompt.

**Date injection pattern**:
```python
from datetime import date

instruction = (
    "You are an expense tracking agent. Today's date is {today}. ..."
).format(today=date.today().isoformat())
```

**Prompt addition for date**:
```
When the user mentions a relative date ("yesterday", "last Monday"), resolve it 
to YYYY-MM-DD format using today's date. If no date is mentioned, use today.
Pass date as the `date` parameter to add_expense.
```

**Alternative considered**: `dateparser` library — unnecessary dependency when Gemini handles it.

---

## 4. Expense ID Strategy

**Decision**: Use auto-incrementing integer IDs (1, 2, 3 ...) computed from current CSV row count + 1.

**Rationale**:
- Simpler than UUID; easier to reference in delete operations ("remove expense 5")
- CSV is append-only; ID is assigned on write
- Collision risk: zero (single user, single process)

**Alternative considered**: UUID4 — overkill; harder for users to reference verbally.

---

## 5. Existing Code Assessment

| Component | Assessment |
|-----------|-----------|
| `agent.py` | Clean. Needs: updated `instruction` with categories, date injection, merchant extraction |
| `tools.py` | Good structure. Needs: `Expense` model extended, `add_expense` signature updated, CSV persistence added |
| `test_agent.py` | Good mock pattern. Needs: minor updates for new `Expense` fields and `date` parameter |
| `requirements.txt` | LangChain/LangGraph present but unused — can be removed if not needed |
| In-memory `expenses = []` | Replace with `_load_expenses()` on module load |
