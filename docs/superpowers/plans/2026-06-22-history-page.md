# History Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `/history` page with per-category spending averages and a keyword-searchable transaction browser; move Recent Transactions from the Dashboard there.

**Architecture:** Three tasks in order — (1) lift the shared delete stores/toast out of the dashboard layout into `app.py` so they survive page navigation; (2) strip Recent Transactions from `dashboard.py`; (3) build `pages/history.py` with pure helper functions for stat computation (testable) and two Dash callbacks for the UI.

**Tech Stack:** Python 3.11, Dash 2.x, dash-bootstrap-components, SQLite via existing `fetch_expenses()`.

## Global Constraints

- Python 3.11 — no `match` statements, no walrus in f-strings
- All amounts in euros (float), dates as ISO strings `YYYY-MM-DD`
- Teal accent colour: `#14b8a6`; card border-top style: `{"borderTop": "3px solid #14b8a6", "borderRadius": "8px"}`
- Existing `CATEGORIES` list lives in `expense_tracker_agent/tools.py` — import from there, do not duplicate
- Run `uv run pytest tests/ -q` after every task — must stay at 69 passed

---

### Task 1: Lift shared delete stores and undo toast to app.py + add History nav link

The delete buttons will live on the History page, but the callbacks that handle them (`handle_delete`, `handle_restore`) write to `expense-deleted-store`, `last-deleted-store`, and the undo toast — all currently defined inside the Dashboard layout. Moving them to `app.py` makes them always present in the DOM regardless of which page is active.

**Files:**
- Modify: `app.py`
- Modify: `pages/dashboard.py`

**Interfaces:**
- Produces: `dcc.Store(id="expense-deleted-store")`, `dcc.Store(id="last-deleted-store")`, `html.Div(id="undo-toast-container", ...)` now live in `app.py` layout — available to callbacks on any page.

- [ ] **Step 1: Confirm baseline tests pass**

```bash
uv run pytest tests/ -q
```
Expected: `69 passed`

- [ ] **Step 2: Update `app.py` — add History nav link, move stores and toast**

Replace the entire `app.py` with:

```python
# app.py
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
from dash import dcc, html

from expense_tracker_agent.db import init_db, migrate_from_csv

init_db()
migrate_from_csv(Path("expenses.csv"))

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
)

_TOAST_HIDDEN = {"position": "fixed", "bottom": "20px", "right": "20px",
                 "zIndex": 9999, "display": "none"}

navbar = dbc.Navbar(
    dbc.Container(
        [
            dbc.NavbarBrand("ExpenseAI", href="/", style={"color": "#ffffff", "fontWeight": "700", "fontSize": "18px"}),
            dbc.NavbarToggler(id="navbar-toggler"),
            dbc.Collapse(
                dbc.Nav(
                    [
                        dbc.NavLink("Dashboard", href="/", active="exact",
                                    style={"color": "#ccfbf1", "fontWeight": "500"}),
                        dbc.NavLink("Add Expense", href="/add", active="exact",
                                    style={"color": "#ccfbf1", "fontWeight": "500"}),
                        dbc.NavLink("History", href="/history", active="exact",
                                    style={"color": "#ccfbf1", "fontWeight": "500"}),
                        dbc.NavLink("Import CSV", href="/import", active="exact",
                                    style={"color": "#ccfbf1", "fontWeight": "500"}),
                        dbc.NavLink("Scan Receipt", href="/scan", active="exact",
                                    style={"color": "#ccfbf1", "fontWeight": "500"}),
                    ],
                    navbar=True,
                    className="ms-auto gap-2",
                ),
                id="navbar-collapse",
                navbar=True,
            ),
        ],
        fluid=True,
    ),
    style={"backgroundColor": "#0f766e", "boxShadow": "0 2px 8px rgba(0,0,0,0.15)"},
    className="mb-4 px-3",
)

app.layout = html.Div(
    [
        # Global stores — must be in app layout so callbacks work on any page
        dcc.Store(id="expense-deleted-store"),
        dcc.Store(id="last-deleted-store"),
        # Undo toast — always in DOM
        html.Div(
            id="undo-toast-container",
            style=_TOAST_HIDDEN,
            children=dbc.Alert(
                [
                    html.Span(id="undo-toast-text", className="me-3 small"),
                    dbc.Button("Undo", id="undo-expense-btn", size="sm", n_clicks=0,
                               style={"backgroundColor": "#0d9488", "borderColor": "#0d9488",
                                      "color": "#fff"}),
                ],
                color="dark",
                className="d-flex align-items-center mb-0 py-2 shadow",
            ),
        ),
        navbar,
        dbc.Container(dash.page_container, fluid=False, className="pb-5"),
    ]
)

server = app.server

if __name__ == "__main__":
    app.run(debug=True, port=8050)
```

- [ ] **Step 3: Remove stores and toast from `pages/dashboard.py` layout**

In `pages/dashboard.py`, replace the `layout` definition. Remove the three components that are now in `app.py` (`expense-deleted-store`, `last-deleted-store`, `undo-toast-container`) from the top of `layout`. The new layout starts directly with `dbc.Row` for the period selector:

```python
layout = html.Div([
    dbc.Row([
        dbc.Col(
            dbc.Select(
                id="period-select",
                options=[{"label": v, "value": k} for k, v in _PERIODS.items()],
                value="last_14_days",
                style={"maxWidth": "200px"},
            ),
            width="auto",
        ),
    ], className="mb-4"),

    # Recent transactions — top of page
    dbc.Row([
        dbc.Col([
            html.H6("Recent Transactions", className="fw-semibold mb-2"),
            html.Div(id="recent-transactions"),
        ]),
    ], className="mb-4"),

    # KPI cards
    dbc.Row(id="kpi-cards", className="mb-4 g-3"),

    # Charts row 1
    dbc.Row([
        dbc.Col(dcc.Graph(id="chart-trend"), md=8),
        dbc.Col(dcc.Graph(id="chart-donut"), md=4),
    ], className="mb-1"),

    # Day drill-down (appears when a bar is clicked)
    dbc.Row([
        dbc.Col(html.Div(id="day-drilldown"), md=8),
    ], className="mb-3"),

    # Charts row 2
    dbc.Row([
        dbc.Col(dcc.Graph(id="chart-weekly"), md=6),
        dbc.Col(dcc.Graph(id="chart-merchants"), md=6),
    ], className="mb-3"),

    # Charts row 3
    dbc.Row([
        dbc.Col(dcc.Graph(id="chart-sub-breakdown"), md=6),
        dbc.Col(dcc.Graph(id="chart-heatmap"), md=6),
    ]),
])
```

- [ ] **Step 4: Run tests — must still be 69 passed**

```bash
uv run pytest tests/ -q
```
Expected: `69 passed`

- [ ] **Step 5: Commit**

```bash
git add app.py pages/dashboard.py
git commit -m "refactor: lift delete stores and undo toast to app layout; add History nav link"
```

---

### Task 2: Remove Recent Transactions from Dashboard

**Files:**
- Modify: `pages/dashboard.py`

**Interfaces:**
- Consumes: nothing new
- Produces: `update_dashboard` callback now returns 7 values instead of 8 (no `recent-transactions`)

- [ ] **Step 1: Remove `_recent_table` function and `recent-transactions` div from layout**

Delete the entire `_recent_table()` function (lines 46–76) and the `dbc.Row` block containing `recent-transactions` from the layout. Replace that row with a "→ View History" link:

```python
# Replace the recent-transactions Row with this:
dbc.Row([
    dbc.Col(
        dbc.Button(
            "→ View History",
            href="/history",
            color="link",
            size="sm",
            className="ps-0 text-muted",
            style={"fontSize": "13px"},
        ),
    ),
], className="mb-4"),
```

- [ ] **Step 2: Update `update_dashboard` callback — remove `recent-transactions` output**

Remove `Output("recent-transactions", "children")` from the `@callback` decorator and remove `recent = _recent_table(rows, limit=6)` plus `recent` from the return tuple.

The updated callback decorator and return:

```python
@callback(
    Output("kpi-cards", "children"),
    Output("chart-trend", "figure"),
    Output("chart-donut", "figure"),
    Output("chart-weekly", "figure"),
    Output("chart-merchants", "figure"),
    Output("chart-sub-breakdown", "figure"),
    Output("chart-heatmap", "figure"),
    Input("period-select", "value"),
    Input("expense-deleted-store", "data"),
)
def update_dashboard(period: str, _deleted):
    start, end = _date_range(period)
    stats = charts.kpi_stats(start, end)

    _card_style = {"borderTop": "3px solid #14b8a6", "borderRadius": "8px"}
    kpi_cards = [
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("Total Spent", className="text-muted small mb-1"),
            html.H3(f"€{stats['total']:.2f}", className="mb-0"),
        ]), style=_card_style), md=4),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("Transactions", className="text-muted small mb-1"),
            html.H3(str(stats["count"]), className="mb-0"),
        ]), style=_card_style), md=4),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("Avg / Day", className="text-muted small mb-1"),
            html.H3(f"€{stats['avg_per_day']:.2f}", className="mb-0"),
        ]), style=_card_style), md=4),
    ]

    def _safe(fn, *args):
        try:
            return fn(*args)
        except Exception as exc:
            import plotly.graph_objects as go
            return go.Figure().add_annotation(text=f"Chart error: {exc}", showarrow=False)

    return (
        kpi_cards,
        _safe(charts.fig_monthly_trend, start, end),
        _safe(charts.fig_category_donut, start, end),
        _safe(charts.fig_weekly_bar, start, end),
        _safe(charts.fig_top_merchants, start, end),
        _safe(charts.fig_sub_expense_breakdown, start, end),
        _safe(charts.fig_heatmap, start, end),
    )
```

- [ ] **Step 3: Run tests — must still be 69 passed**

```bash
uv run pytest tests/ -q
```
Expected: `69 passed`

- [ ] **Step 4: Commit**

```bash
git add pages/dashboard.py
git commit -m "feat: remove Recent Transactions from dashboard, add View History link"
```

---

### Task 3: Build History page

**Files:**
- Create: `pages/history.py`
- Create: `tests/test_history.py`

**Interfaces:**
- Consumes: `fetch_expenses()` from `expense_tracker_agent.db`; `CATEGORIES` from `expense_tracker_agent.tools`; `dcc.Store(id="expense-deleted-store")` from `app.py`
- Produces: page at `/history` with `history-cat-select`, `history-search`, stat cards, transaction table with delete buttons `{"type": "del-expense", "index": r["id"]}`

- [ ] **Step 1: Write failing tests for stat helper functions**

Create `tests/test_history.py`:

```python
# tests/test_history.py
import unittest
from datetime import date, timedelta

# Pure helper functions to be implemented in pages/history.py
from pages.history import compute_weekly_avg, compute_monthly_avg, last_purchase_info


def _row(date_str, category, amount, merchant="Edeka"):
    return {"date": date_str, "category": category, "amount": amount,
            "merchant": merchant, "description": "", "id": 1}


class TestComputeWeeklyAvg(unittest.TestCase):

    def test_returns_zero_when_no_rows(self):
        self.assertEqual(compute_weekly_avg([], "Groceries"), 0.0)

    def test_returns_zero_when_no_matching_category(self):
        rows = [_row("2026-01-05", "Transport", 10.0)]
        self.assertEqual(compute_weekly_avg(rows, "Groceries"), 0.0)

    def test_averages_complete_weeks_only(self):
        # Two complete past weeks each with €20
        monday_last = date.today() - timedelta(days=date.today().weekday() + 7)
        monday_prev = monday_last - timedelta(weeks=1)
        rows = [
            _row(monday_last.isoformat(), "Groceries", 20.0),
            _row(monday_prev.isoformat(), "Groceries", 20.0),
        ]
        result = compute_weekly_avg(rows, "Groceries", n_weeks=8)
        self.assertAlmostEqual(result, 5.0)  # 40 / 8 weeks = 5.0


class TestComputeMonthlyAvg(unittest.TestCase):

    def test_returns_zero_when_no_rows(self):
        self.assertEqual(compute_monthly_avg([], "Groceries"), 0.0)

    def test_averages_over_n_months(self):
        # €90 spread across 3 complete past months
        today = date.today()
        m1 = (today.replace(day=1) - timedelta(days=1)).replace(day=1)   # 1st of last month
        m2 = (m1 - timedelta(days=1)).replace(day=1)                      # 1st of month before
        m3 = (m2 - timedelta(days=1)).replace(day=1)                      # 1st of month before that
        rows = [
            _row(m1.isoformat(), "Groceries", 30.0),
            _row(m2.isoformat(), "Groceries", 30.0),
            _row(m3.isoformat(), "Groceries", 30.0),
        ]
        result = compute_monthly_avg(rows, "Groceries", n_months=3)
        self.assertAlmostEqual(result, 30.0)


class TestLastPurchaseInfo(unittest.TestCase):

    def test_returns_none_when_no_rows(self):
        self.assertIsNone(last_purchase_info([], "Groceries"))

    def test_returns_most_recent(self):
        rows = [
            _row("2026-06-01", "Groceries", 10.0, "Lidl"),
            _row("2026-06-15", "Groceries", 20.0, "Edeka"),
            _row("2026-06-10", "Groceries", 15.0, "Rewe"),
        ]
        result = last_purchase_info(rows, "Groceries")
        self.assertEqual(result["date"], "2026-06-15")
        self.assertEqual(result["merchant"], "Edeka")
        self.assertAlmostEqual(result["amount"], 20.0)

    def test_returns_none_for_wrong_category(self):
        rows = [_row("2026-06-01", "Transport", 10.0)]
        self.assertIsNone(last_purchase_info(rows, "Groceries"))
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
uv run pytest tests/test_history.py -v
```
Expected: `ImportError` or `ModuleNotFoundError` (history.py does not exist yet)

- [ ] **Step 3: Create `pages/history.py` with helpers + layout + callbacks**

```python
# pages/history.py
from datetime import date, timedelta

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, html

from expense_tracker_agent.db import fetch_expenses
from expense_tracker_agent.tools import CATEGORIES

dash.register_page(__name__, path="/history", name="History")

# ── Pure stat helpers (tested in tests/test_history.py) ──────────────────────

def compute_weekly_avg(rows: list[dict], category: str, n_weeks: int = 8) -> float:
    """Average weekly spend for `category` over the last `n_weeks` complete weeks."""
    filtered = [r for r in rows if r["category"] == category]
    if not filtered:
        return 0.0
    today = date.today()
    # Monday of current week — exclude (incomplete)
    current_monday = today - timedelta(days=today.weekday())
    cutoff = current_monday - timedelta(weeks=n_weeks)
    weekly: dict[tuple, float] = {}
    for r in filtered:
        d = date.fromisoformat(r["date"])
        if d >= current_monday or d < cutoff:
            continue
        week_key = d.isocalendar()[:2]  # (year, week)
        weekly[week_key] = weekly.get(week_key, 0.0) + r["amount"]
    if not weekly:
        return 0.0
    return sum(weekly.values()) / n_weeks


def compute_monthly_avg(rows: list[dict], category: str, n_months: int = 3) -> float:
    """Average monthly spend for `category` over the last `n_months` complete months."""
    filtered = [r for r in rows if r["category"] == category]
    if not filtered:
        return 0.0
    today = date.today()
    current_month_start = today.replace(day=1)
    monthly: dict[tuple, float] = {}
    for r in filtered:
        d = date.fromisoformat(r["date"])
        if d >= current_month_start:
            continue
        key = (d.year, d.month)
        monthly[key] = monthly.get(key, 0.0) + r["amount"]
    if not monthly:
        return 0.0
    return sum(monthly.values()) / n_months


def last_purchase_info(rows: list[dict], category: str) -> dict | None:
    """Return the most recent row for `category`, or None."""
    filtered = [r for r in rows if r["category"] == category]
    if not filtered:
        return None
    return max(filtered, key=lambda r: r["date"])


# ── Layout ────────────────────────────────────────────────────────────────────

_CAT_OPTIONS = [{"label": "All Categories", "value": ""}] + [
    {"label": c, "value": c} for c in CATEGORIES
]

_CARD_STYLE = {"borderTop": "3px solid #14b8a6", "borderRadius": "8px"}


def _stat_card(label: str, value: str, sub: str = ""):
    return dbc.Col(dbc.Card(dbc.CardBody([
        html.P(label, className="text-muted small mb-1"),
        html.H4(value, className="mb-0"),
        html.Small(sub, className="text-muted") if sub else None,
    ]), style=_CARD_STYLE), md=4)


layout = html.Div([
    html.H5("History", className="mb-1"),
    html.P("Browse past transactions and track spending by category.",
           className="text-muted mb-4"),

    # ── Category insights ──
    dbc.Card(dbc.CardBody([
        html.H6("Category Insights", className="fw-semibold mb-3"),
        dbc.Row([
            dbc.Col([
                html.Label("Category", className="small text-muted mb-1"),
                dbc.Select(
                    id="history-cat-select",
                    options=_CAT_OPTIONS,
                    value="",
                ),
            ], md=4),
        ], className="mb-3"),
        html.Div(id="history-stat-cards"),
    ]), className="mb-4"),

    # ── Transaction browser ──
    dbc.Card(dbc.CardBody([
        html.H6("Transactions", className="fw-semibold mb-3"),
        dbc.Row([
            dbc.Col([
                html.Label("Category", className="small text-muted mb-1"),
                dbc.Select(id="history-filter-cat", options=_CAT_OPTIONS, value=""),
            ], md=4),
            dbc.Col([
                html.Label("Search", className="small text-muted mb-1"),
                dbc.Input(
                    id="history-search",
                    placeholder='e.g. "protein", "dm", "Rewe"',
                    type="text",
                    debounce=False,
                ),
            ], md=8),
        ], className="mb-3"),
        html.Div(id="history-results-count", className="text-muted small mb-2"),
        html.Div(id="history-table"),
    ])),
])


# ── Callbacks ─────────────────────────────────────────────────────────────────

def _fmt(iso: str) -> str:
    try:
        y, m, d = iso.split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return iso


def _days_ago(iso: str) -> str:
    try:
        delta = (date.today() - date.fromisoformat(iso)).days
        if delta == 0:
            return "today"
        if delta == 1:
            return "yesterday"
        return f"{delta} days ago"
    except Exception:
        return ""


@callback(
    Output("history-stat-cards", "children"),
    Output("history-filter-cat", "value"),
    Input("history-cat-select", "value"),
)
def update_stat_cards(category: str):
    if not category:
        return html.P("Select a category to see averages.", className="text-muted small"), ""
    rows = fetch_expenses()
    avg_week = compute_weekly_avg(rows, category)
    avg_month = compute_monthly_avg(rows, category)
    last = last_purchase_info(rows, category)
    if last:
        last_text = f"{_fmt(last['date'])} · {last.get('merchant') or '—'}"
        last_sub = f"€{last['amount']:.2f} · {_days_ago(last['date'])}"
    else:
        last_text = "No purchases yet"
        last_sub = ""
    cards = dbc.Row([
        _stat_card("Avg / Week", f"€{avg_week:.2f}", "last 8 complete weeks"),
        _stat_card("Avg / Month", f"€{avg_month:.2f}", "last 3 complete months"),
        _stat_card("Last Purchase", last_text, last_sub),
    ])
    return cards, category


@callback(
    Output("history-results-count", "children"),
    Output("history-table", "children"),
    Input("history-filter-cat", "value"),
    Input("history-search", "value"),
    Input("expense-deleted-store", "data"),
)
def update_table(category: str, keyword: str, _deleted):
    rows = fetch_expenses()
    kw = (keyword or "").strip().lower()
    filtered = [
        r for r in rows
        if (not category or r["category"] == category)
        and (not kw or kw in (r.get("merchant") or "").lower()
             or kw in r.get("description", "").lower())
    ]
    filtered.sort(key=lambda r: r["date"], reverse=True)

    if not filtered:
        return "0 transactions found", html.P(
            "No transactions match your search.", className="text-muted small mt-2"
        )

    count_text = f"{len(filtered)} transaction{'s' if len(filtered) != 1 else ''} found"
    table = dbc.Table(
        [
            html.Thead(html.Tr([
                html.Th("Date"), html.Th("Store"), html.Th("Category"),
                html.Th("Amount", className="text-end"), html.Th("Description"), html.Th(),
            ])),
            html.Tbody([
                html.Tr([
                    html.Td(_fmt(r["date"]), className="text-muted small"),
                    html.Td(r.get("merchant") or "—"),
                    html.Td(html.Span(
                        r["category"], className="small",
                        style={"backgroundColor": "#14b8a6", "color": "#fff",
                               "borderRadius": "4px", "padding": "2px 7px"},
                    )),
                    html.Td(f"€{r['amount']:.2f}", className="fw-semibold text-end"),
                    html.Td(r["description"], className="text-muted small"),
                    html.Td(
                        dbc.Button("×", id={"type": "del-expense", "index": r["id"]},
                                   size="sm", color="link",
                                   style={"color": "#dc3545", "padding": "0 4px", "lineHeight": "1"}),
                        className="text-center",
                    ),
                ])
                for r in filtered
            ]),
        ],
        hover=True, responsive=True, size="sm", className="mb-0",
    )
    return count_text, table
```

- [ ] **Step 4: Run tests — must be 72 passed (69 existing + 3 new)**

```bash
uv run pytest tests/ -q
```
Expected: `72 passed`

- [ ] **Step 5: Commit**

```bash
git add pages/history.py tests/test_history.py
git commit -m "feat: add History page with category averages and transaction browser"
```

---

## Verification

After all tasks complete:

```bash
uv run pytest tests/ -q   # expect 72 passed
uv run python app.py
```

1. Open `http://localhost:8050` — Dashboard should NOT show Recent Transactions; a "→ View History" link appears instead.
2. Click "History" in the nav bar — page loads at `/history`.
3. Select "Groceries" in the Category Insights dropdown — three stat cards appear (Avg/Week, Avg/Month, Last Purchase); the Transactions table below filters to Groceries automatically.
4. Type `protein` in the Search box — only rows whose merchant or description contains "protein" show.
5. Select "All Categories", clear search — stat cards hide, all transactions show.
6. Click `×` on a transaction — it disappears and an undo toast appears (bottom-right). Click Undo — it comes back.
7. Navigate back to Dashboard — the undo toast still works from the Dashboard's day-drilldown delete buttons.
