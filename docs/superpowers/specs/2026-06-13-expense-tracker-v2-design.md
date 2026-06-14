# Expense Tracker v2 — Design Spec

**Date:** 2026-06-13  
**Status:** Approved

---

## Context

The current expense tracker is a working Google ADK + Gemini 2.5 Flash agent that persists data to a flat CSV file and is interacted with only via terminal chat. It has no visual interface and no way to review spending patterns at a glance.

This upgrade adds a proper database, a Plotly Dash web dashboard, receipt scanning, CSV import, and a parent-child expense model to support itemised shopping trips.

---

## Goals

1. Replace CSV persistence with SQLite
2. Build a clean Plotly Dash web UI (minimal top nav, white background, hero numbers)
3. Dashboard with 6 charts: monthly trend, category donut, weekly bar, top merchants, sub-expense stacked bar, spending heatmap
4. Sub-expense model: a store visit can have individual line items (e.g. "beer €3" as a child of "Edeka €10")
5. Receipt scanning via Gemini Vision: upload photo → extract items → review → save
6. CSV import: upload a file with `date`, `cost`, `supermarket name` columns → bulk import as parent expenses
7. Keep the existing AI chat interface embedded in the app (Add Expense page)

---

## Data Model

Two SQLite tables in `expenses.db`.

### `expenses` — every expense (parent or standalone)

| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | auto-increment |
| `amount` | REAL | total for this expense |
| `merchant` | TEXT | store/restaurant name |
| `category` | TEXT | one of the predefined categories (see below) |
| `description` | TEXT | free-form |
| `date` | TEXT | ISO date (YYYY-MM-DD) |
| `timestamp` | TEXT | ISO datetime when recorded |
| `source` | TEXT | `manual`, `csv_import`, `receipt_scan`, `ai_chat` |

### `expense_items` — sub-items belonging to a parent expense

| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | auto-increment |
| `parent_id` | INTEGER FK | → `expenses.id` |
| `amount` | REAL | e.g. 3.00 |
| `description` | TEXT | e.g. "beer" |
| `category` | TEXT | inferred by Gemini, e.g. "Alcohol" |
| `timestamp` | TEXT | ISO datetime |

**Categories** — the existing list is extended from 8 to 9 to support itemised receipts:
`Food`, `Groceries`, `Transport`, `Entertainment`, `Bills`, `Healthcare`, `Shopping`, `Alcohol`, `Other`

The agent system prompt and `CATEGORIES` constant in `tools.py` are updated accordingly.

On first run, existing `expenses.csv` data is migrated to SQLite automatically.

---

## Architecture

```
Plotly Dash App (localhost:8050)
├── Dashboard page        — 6 charts + KPI cards + date range filter
├── Add Expense page      — AI chat panel (ADK agent)
├── Import CSV page       — file upload → preview → confirm
└── Scan Receipt page     — image upload → Gemini Vision → review → confirm

          ↕ reads/writes
    SQLite (expenses.db)

          ↕ called by chat + receipt scanner
    Google ADK Agent (Gemini 2.5 Flash)
    + Gemini Vision (receipt scanning)
```

---

## Pages

### Dashboard
- Top nav: `ExpenseAI | Dashboard | Add | Import | Scan`
- Hero number: total spent this month, with % change vs last month
- Secondary KPIs: number of trips, average per day
- Date range filter (dropdown: this month / last month / last 3 months / custom)
- 6 charts below (2-column grid, scroll for more):
  1. Monthly spending trend — line chart
  2. Spending by category — donut chart
  3. Weekly bar chart — spending per week in selected period
  4. Top merchants — horizontal bar ranked by total spend
  5. Sub-expense breakdown — stacked bar per store (only stores with line items)
  6. Spending heatmap — calendar view, darker = more spent

### Add Expense
- AI chat panel occupies the full page
- Conversation history shown above the input box
- Recent expenses list on the right refreshes after each new entry
- Agent handles natural language: "10 euro at Edeka", "beer €3, part of today's Edeka shop"

### Import CSV
- Drag & drop file upload (CSV only)
- Expects exactly 3 columns: `date`, `cost`, `supermarket name` (flexible naming)
- Preview first 10 rows in a table
- Manual column mapping UI if column names don't match exactly
- "Import N rows" confirm button
- Duplicate detection: skip rows where date + merchant + amount already exist in DB
- Imported rows become parent expenses with `source = "csv_import"` (no sub-items)

### Scan Receipt
- Image upload (JPG/PNG)
- Gemini Vision prompt extracts: store name, date, each line item + price, total
- Editable review table rendered in Dash before anything is saved
- "Confirm" creates one parent expense row + one `expense_items` row per line item
- "Cancel" discards and returns to upload

---

## Sub-expense Workflow

Hybrid: both paths work seamlessly.

**Path 1 — total first, items later (explicit):**
1. "Spent 10 euro at Edeka today" → creates parent expense
2. "3 euro beer, part of today's Edeka shop" → creates sub-item linked by merchant + date

**Path 2 — items only (auto-group):**
1. "Beer €3 at Edeka", "Bread €4 at Edeka" logged on same day → auto-grouped into an Edeka session
2. Dashboard shows Edeka session total with expandable sub-items

**Path 3 — receipt scan:**
1. Upload receipt photo → Gemini reads all items
2. One confirm action creates parent + all children atomically

The agent uses merchant name + date to determine which parent to attach sub-items to. If ambiguous (same store visited twice in one day), agent asks for clarification.

---

## Agent Tools (additions to existing)

| tool | purpose |
|---|---|
| `find_parent_expense_id(merchant, date)` | look up an existing parent expense id by merchant + date |
| `add_expense_item(parent_id, amount, description, category)` | add a sub-item to an existing parent expense |
| `list_expense_items(parent_id)` | fetch sub-items for a parent |
| `import_csv_row(date, amount, merchant)` | insert a single CSV row, deduplication logic inside |

Existing tools (`add_expense`, `calculate_total_spending`, `get_spending_by_category`, `list_recent_expenses`) are updated to use SQLite instead of CSV.

---

## Tech Stack

| concern | choice |
|---|---|
| Database | SQLite via `sqlite3` stdlib |
| Web UI | Plotly Dash (`dash`, `dash-bootstrap-components`) |
| Charts | Plotly Express / `plotly.graph_objects` |
| Agent | Google ADK + Gemini 2.5 Flash (existing) |
| Receipt OCR | Gemini Vision (via `google-generativeai`) |
| CSV parsing | `pandas` |
| Styling | `dash-bootstrap-components` light theme, custom overrides for minimal look |

---

## Migration

On app startup, `db.py` checks whether `expenses.db` exists. If not, it creates the schema and migrates all rows from `expenses.csv` (if present) as parent expenses with `source = "csv_import"`.

---

## Verification

1. Run `python app.py` → Dash app opens at `localhost:8050`
2. Dashboard loads with charts (empty state if no data yet)
3. Add Expense page: type "lunch €8 at Mensa today" → expense appears in recent list and dashboard updates
4. Add a sub-item: "beer €3 at Edeka, part of today's shop" → appears as child under parent in dashboard
5. CSV Import: upload a 3-column file → preview shows correctly → import → dashboard updates
6. Scan Receipt: upload a test receipt image → Gemini extracts items → confirm → parent + sub-items in DB
7. All 6 charts render correctly with real data
8. Existing unit tests still pass (`python -m pytest`)
