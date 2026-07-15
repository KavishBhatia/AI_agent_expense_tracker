# Trips Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fully self-contained Trips section to the expense tracker, backed by a separate `trips.db`, where users can create trips, import CSV expenses into them, add expenses manually, and view trip analytics.

**Architecture:** A new `trip_db.py` module manages a separate `trips.db` SQLite file (two tables: `trips` and `trip_expenses`). Two new Dash pages handle the trip list (`/trips`) and trip detail (`/trip?id=N`). The main dashboard and `expenses.db` are never touched. The ☰ off-canvas drawer in `app.py` gets a "Trips" link.

**Tech Stack:** Python, SQLite (separate `trips.db`), Dash/DBC, Plotly, pandas (reused from existing import logic), Gemini batch classifier (reused from `categoriser.py`).

## Global Constraints

- **Never commit to `main` directly** — all changes must go on branch `feat/trips` and be merged via PR.
- `trips.db` is created next to `expenses.db` in the project root.
- The main `expenses.db` and all existing pages/dashboard are never modified.
- Use existing `CATEGORIES` list from `expense_tracker_agent/tools.py` for category dropdowns.
- Use existing `classify_expenses()` from `expense_tracker_agent/categoriser.py` for CSV import categorisation.
- Column-detection sets (`_KNOWN_DATE_COLS`, `_KNOWN_COST_COLS`, `_KNOWN_MERCHANT_COLS`) are copied verbatim from `pages/import_csv.py` into `pages/trip_detail.py` — do not import across page modules.
- `description` is nullable in `trip_expenses`.
- Trip start/end dates are computed from `MIN(date)` / `MAX(date)` in `trip_expenses`, not stored.
- All tests use a temporary DB file patched via `patch.object(trip_db_module, "TRIP_DB_PATH", tmp_path)`, matching the pattern in `tests/test_db.py`.
- Run tests with: `uv run pytest tests/ -q`

---

### Task 1: `expense_tracker_agent/trip_db.py` + tests

**Files:**
- Create: `expense_tracker_agent/trip_db.py`
- Create: `tests/test_trip_db.py`

**Interfaces — produces:**
- `TRIP_DB_PATH: Path` — module-level constant (patch target in tests)
- `init_trip_db() -> None`
- `create_trip(name: str) -> int`
- `fetch_trips() -> list[dict]` — each dict: `id, name, created_at, start_date, end_date, total, count`; sorted by most recent expense date DESC
- `fetch_trip(trip_id: int) -> dict | None`
- `fetch_trip_expenses(trip_id: int) -> list[dict]` — each dict: `id, trip_id, amount, merchant, category, description, date`; sorted by `date ASC`
- `insert_trip_expense(trip_id, amount, merchant, category, description, date) -> int`
- `delete_trip(trip_id: int) -> None` — hard delete, cascades to trip_expenses

- [ ] **Step 1: Write failing tests**

```python
# tests/test_trip_db.py
import os, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

import expense_tracker_agent.trip_db as trip_db_module
from expense_tracker_agent.trip_db import (
    init_trip_db, create_trip, fetch_trips, fetch_trip,
    fetch_trip_expenses, insert_trip_expense, delete_trip,
)

def _temp_db() -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    f.close()
    os.unlink(f.name)
    return Path(f.name)

class BaseTripDbTest(unittest.TestCase):
    def setUp(self):
        self.tmp_db = _temp_db()
        self.patcher = patch.object(trip_db_module, "TRIP_DB_PATH", self.tmp_db)
        self.patcher.start()
        init_trip_db()

    def tearDown(self):
        self.patcher.stop()
        if self.tmp_db.exists():
            self.tmp_db.unlink()

class TestCreateFetchTrip(BaseTripDbTest):
    def test_create_returns_id(self):
        tid = create_trip("Barcelona")
        self.assertIsInstance(tid, int)
        self.assertGreater(tid, 0)

    def test_fetch_trips_empty(self):
        self.assertEqual(fetch_trips(), [])

    def test_fetch_trips_returns_trip(self):
        tid = create_trip("Lisbon")
        trips = fetch_trips()
        self.assertEqual(len(trips), 1)
        self.assertEqual(trips[0]["name"], "Lisbon")
        self.assertEqual(trips[0]["id"], tid)

    def test_fetch_trip_none_for_missing(self):
        self.assertIsNone(fetch_trip(999))

    def test_fetch_trip_totals_computed(self):
        tid = create_trip("Rome")
        insert_trip_expense(tid, 20.0, "Ristorante", "Food & Dining", "pasta", "2026-05-10")
        insert_trip_expense(tid, 10.0, None, "Commute", None, "2026-05-11")
        t = fetch_trip(tid)
        self.assertAlmostEqual(t["total"], 30.0)
        self.assertEqual(t["count"], 2)
        self.assertEqual(t["start_date"], "2026-05-10")
        self.assertEqual(t["end_date"], "2026-05-11")

class TestTripExpenses(BaseTripDbTest):
    def test_insert_and_fetch(self):
        tid = create_trip("Paris")
        insert_trip_expense(tid, 15.0, "Boulangerie", "Food & Dining", "croissant", "2026-04-01")
        rows = fetch_trip_expenses(tid)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["merchant"], "Boulangerie")
        self.assertAlmostEqual(rows[0]["amount"], 15.0)

    def test_nullable_fields(self):
        tid = create_trip("Berlin")
        insert_trip_expense(tid, 5.0, None, "Miscellaneous", None, "2026-03-01")
        rows = fetch_trip_expenses(tid)
        self.assertIsNone(rows[0]["merchant"])
        self.assertIsNone(rows[0]["description"])

    def test_sorted_by_date_asc(self):
        tid = create_trip("Vienna")
        insert_trip_expense(tid, 10.0, "A", "Food & Dining", None, "2026-06-05")
        insert_trip_expense(tid, 20.0, "B", "Groceries", None, "2026-06-03")
        rows = fetch_trip_expenses(tid)
        self.assertEqual(rows[0]["date"], "2026-06-03")
        self.assertEqual(rows[1]["date"], "2026-06-05")

class TestDeleteTrip(BaseTripDbTest):
    def test_delete_removes_trip_and_expenses(self):
        tid = create_trip("Madrid")
        insert_trip_expense(tid, 12.0, "Mercado", "Groceries", None, "2026-07-01")
        delete_trip(tid)
        self.assertEqual(fetch_trips(), [])
        self.assertEqual(fetch_trip_expenses(tid), [])
```

- [ ] **Step 2: Run tests — confirm they fail**

```bash
uv run pytest tests/test_trip_db.py -q
```

Expected: ImportError or AttributeError (module doesn't exist yet).

- [ ] **Step 3: Implement `trip_db.py`**

```python
# expense_tracker_agent/trip_db.py
import sqlite3
from datetime import datetime
from pathlib import Path

TRIP_DB_PATH = Path("trips.db")


def _conn():
    return sqlite3.connect(TRIP_DB_PATH)


def init_trip_db() -> None:
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS trips (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trip_expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id     INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
                amount      REAL    NOT NULL,
                merchant    TEXT,
                category    TEXT    NOT NULL,
                description TEXT,
                date        TEXT    NOT NULL
            );
            PRAGMA foreign_keys = ON;
        """)


def create_trip(name: str) -> int:
    ts = datetime.now().isoformat()
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO trips (name, created_at) VALUES (?, ?)", (name, ts)
        )
        return cur.lastrowid


def _row_to_trip(row) -> dict:
    return {
        "id": row[0], "name": row[1], "created_at": row[2],
        "start_date": row[3], "end_date": row[4],
        "total": row[5] or 0.0, "count": row[6] or 0,
    }


def fetch_trips() -> list[dict]:
    sql = """
        SELECT t.id, t.name, t.created_at,
               MIN(e.date) AS start_date, MAX(e.date) AS end_date,
               COALESCE(SUM(e.amount), 0.0) AS total,
               COUNT(e.id) AS count
        FROM trips t
        LEFT JOIN trip_expenses e ON e.trip_id = t.id
        GROUP BY t.id
        ORDER BY MAX(e.date) DESC NULLS LAST, t.created_at DESC
    """
    with _conn() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(sql).fetchall()
    return [_row_to_trip(r) for r in rows]


def fetch_trip(trip_id: int) -> dict | None:
    sql = """
        SELECT t.id, t.name, t.created_at,
               MIN(e.date) AS start_date, MAX(e.date) AS end_date,
               COALESCE(SUM(e.amount), 0.0) AS total,
               COUNT(e.id) AS count
        FROM trips t
        LEFT JOIN trip_expenses e ON e.trip_id = t.id
        WHERE t.id = ?
        GROUP BY t.id
    """
    with _conn() as con:
        con.row_factory = sqlite3.Row
        row = con.execute(sql, (trip_id,)).fetchone()
    return _row_to_trip(row) if row else None


def fetch_trip_expenses(trip_id: int) -> list[dict]:
    sql = """
        SELECT id, trip_id, amount, merchant, category, description, date
        FROM trip_expenses
        WHERE trip_id = ?
        ORDER BY date ASC
    """
    with _conn() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, (trip_id,)).fetchall()
    return [dict(r) for r in rows]


def insert_trip_expense(
    trip_id: int,
    amount: float,
    merchant: str | None,
    category: str,
    description: str | None,
    date: str,
) -> int:
    with _conn() as con:
        con.execute("PRAGMA foreign_keys = ON")
        cur = con.execute(
            """INSERT INTO trip_expenses
               (trip_id, amount, merchant, category, description, date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (trip_id, amount, merchant, category, description, date),
        )
        return cur.lastrowid


def delete_trip(trip_id: int) -> None:
    with _conn() as con:
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("DELETE FROM trips WHERE id = ?", (trip_id,))
```

- [ ] **Step 4: Run tests — confirm they pass**

```bash
uv run pytest tests/test_trip_db.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add expense_tracker_agent/trip_db.py tests/test_trip_db.py
git commit -m "feat: add trip_db module with trips/trip_expenses schema and CRUD"
```

---

### Task 2: `/trips` list page

**Files:**
- Create: `pages/trips.py`

**Interfaces:**
- Consumes: `create_trip`, `fetch_trips`, `delete_trip` from `expense_tracker_agent/trip_db.py`
- Produces: Dash page at `/trips`; redirects to `/trip?id=N` on card open or after create

- [ ] **Step 1: Write the page**

```python
# pages/trips.py
import json

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, dcc, html

from expense_tracker_agent.trip_db import create_trip, delete_trip, fetch_trips

dash.register_page(__name__, path="/trips", name="Trips")


def _fmt_range(start, end):
    if not start:
        return "No expenses yet"
    if start == end:
        return start
    return f"{start}  →  {end}"


def _trip_card(trip: dict):
    date_range = _fmt_range(trip["start_date"], trip["end_date"])
    return dbc.Card(
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.H6(trip["name"], className="mb-1 fw-semibold"),
                    html.Small(date_range, className="text-muted"),
                ], md=7),
                dbc.Col([
                    html.Div(f"€{trip['total']:.2f}", className="fw-semibold text-end"),
                    html.Small(f"{trip['count']} expense{'s' if trip['count'] != 1 else ''}",
                               className="text-muted d-block text-end"),
                ], md=3),
                dbc.Col([
                    dbc.Button("Open", id={"type": "open-trip-btn", "index": trip["id"]},
                               color="outline-primary", size="sm", className="me-1"),
                    dbc.Button("✕", id={"type": "del-trip-btn", "index": trip["id"]},
                               color="outline-danger", size="sm"),
                ], md=2, className="d-flex align-items-center justify-content-end"),
            ], align="center"),
        ]),
        className="mb-3",
        style={"borderLeft": "3px solid #0d9488", "borderRadius": "8px"},
    )


layout = html.Div([
    dcc.Location(id="trips-location", refresh=True),
    dbc.Row([
        dbc.Col(html.H4("Trips", className="mb-0"), width="auto"),
        dbc.Col(
            dbc.Button("+ New Trip", id="new-trip-btn", color="primary", size="sm", n_clicks=0),
            width="auto", className="ms-auto",
        ),
    ], align="center", className="mb-4"),

    html.Div(id="trips-list"),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("New Trip")),
        dbc.ModalBody([
            dbc.Label("Trip name"),
            dbc.Input(id="new-trip-name", placeholder='e.g. "Barcelona May 2026"', type="text"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="new-trip-cancel", color="secondary", n_clicks=0),
            dbc.Button("Create", id="new-trip-create", color="primary", n_clicks=0),
        ]),
    ], id="new-trip-modal", is_open=False),
])


@callback(
    Output("trips-list", "children"),
    Input("trips-location", "pathname"),
)
def refresh_trips(_):
    trips = fetch_trips()
    if not trips:
        return html.P("No trips yet. Create one with '+ New Trip'.", className="text-muted")
    return [_trip_card(t) for t in trips]


@callback(
    Output("new-trip-modal", "is_open"),
    Input("new-trip-btn", "n_clicks"),
    Input("new-trip-cancel", "n_clicks"),
    Input("new-trip-create", "n_clicks"),
    State("new-trip-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_modal(open_clicks, cancel_clicks, create_clicks, is_open):
    ctx = dash.callback_context
    if not ctx.triggered:
        return is_open
    if ctx.triggered_id == "new-trip-btn":
        return True
    return False


@callback(
    Output("trips-location", "href"),
    Input("new-trip-create", "n_clicks"),
    State("new-trip-name", "value"),
    prevent_initial_call=True,
)
def create_and_redirect(n_clicks, name):
    if not n_clicks or not name or not name.strip():
        return dash.no_update
    tid = create_trip(name.strip())
    return f"/trip?id={tid}"


@callback(
    Output("trips-list", "children", allow_duplicate=True),
    Input({"type": "del-trip-btn", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_delete(n_clicks_list):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    for trigger in ctx.triggered:
        if trigger["value"]:
            tid = json.loads(trigger["prop_id"].split(".")[0])["index"]
            delete_trip(tid)
            break
    trips = fetch_trips()
    if not trips:
        return html.P("No trips yet. Create one with '+ New Trip'.", className="text-muted")
    return [_trip_card(t) for t in trips]


@callback(
    Output("trips-location", "href", allow_duplicate=True),
    Input({"type": "open-trip-btn", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_open(n_clicks_list):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    for trigger in ctx.triggered:
        if trigger["value"]:
            tid = json.loads(trigger["prop_id"].split(".")[0])["index"]
            return f"/trip?id={tid}"
    return dash.no_update
```

- [ ] **Step 2: Run full test suite — confirm no regressions**

```bash
uv run pytest tests/ -q
```

Expected: all existing tests pass.

- [ ] **Step 3: Commit**

```bash
git add pages/trips.py
git commit -m "feat: add /trips list page with create and delete"
```

---

### Task 3: `/trip` detail page

**Files:**
- Create: `pages/trip_detail.py`

**Interfaces:**
- Consumes: `fetch_trip`, `fetch_trip_expenses`, `insert_trip_expense` from `trip_db.py`; `CATEGORIES` from `tools.py`; `classify_expenses` from `categoriser.py`
- Column-detection sets copied verbatim from `import_csv.py` (do not import from that module)
- Produces: Dash page at `/trip`; reads `?id=N` from URL search string

- [ ] **Step 1: Write the page**

```python
# pages/trip_detail.py
import base64
import io
from datetime import date as _date

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dcc, html

from expense_tracker_agent.categoriser import classify_expenses
from expense_tracker_agent.tools import CATEGORIES
from expense_tracker_agent.trip_db import (
    fetch_trip, fetch_trip_expenses, insert_trip_expense,
)

dash.register_page(__name__, path="/trip", name="Trip Detail")

_KNOWN_DATE_COLS = {"date", "datum", "day"}
_KNOWN_COST_COLS = {"cost", "amount", "price", "kosten", "betrag", "preis"}
_KNOWN_MERCHANT_COLS = {"supermarket name", "supermarket", "merchant", "store", "shop", "markt", "laden"}


def _fmt(iso: str) -> str:
    try:
        y, m, d = iso.split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return iso


def _days_count(start, end) -> int:
    if not start or not end:
        return 0
    try:
        from datetime import date
        return (date.fromisoformat(end) - date.fromisoformat(start)).days + 1
    except Exception:
        return 0


def layout(**kwargs):
    return html.Div([
        dcc.Location(id="trip-location"),
        dcc.Store(id="trip-id-store"),
        html.Div(id="trip-detail-content"),
    ])


@callback(
    Output("trip-detail-content", "children"),
    Output("trip-id-store", "data"),
    Input("trip-location", "search"),
)
def render_trip(search):
    trip_id = None
    if search:
        for part in search.lstrip("?").split("&"):
            if part.startswith("id="):
                try:
                    trip_id = int(part[3:])
                except ValueError:
                    pass

    if not trip_id:
        return dbc.Alert("No trip selected.", color="warning"), None

    trip = fetch_trip(trip_id)
    if not trip:
        return dbc.Alert("Trip not found.", color="danger"), None

    days = _days_count(trip["start_date"], trip["end_date"])
    date_range = (
        f"{_fmt(trip['start_date'])} – {_fmt(trip['end_date'])}"
        if trip["start_date"] else "No expenses yet"
    )

    expenses = fetch_trip_expenses(trip_id)

    if expenses:
        df = pd.DataFrame(expenses)
        daily = df.groupby("date")["amount"].sum().reset_index().sort_values("date")
        daily["display"] = daily["date"].apply(_fmt)
        fig = px.bar(daily, x="display", y="amount",
                     labels={"display": "Date", "amount": "€ Spent"},
                     title="Daily Spending",
                     color_discrete_sequence=["#0d9488"])
        fig.update_xaxes(type="category")
        fig.update_layout(margin=dict(t=40, b=20))
    else:
        fig = go.Figure().add_annotation(text="No expenses yet", showarrow=False)

    expense_rows = [
        html.Tr([
            html.Td(_fmt(e["date"])),
            html.Td(e["merchant"] or "—"),
            html.Td(html.Span(e["category"], className="small",
                              style={"backgroundColor": "#14b8a6", "color": "#fff",
                                     "borderRadius": "4px", "padding": "2px 7px"})),
            html.Td(e["description"] or "—", className="text-muted small"),
            html.Td(f"€{e['amount']:.2f}", className="fw-semibold text-end"),
        ])
        for e in expenses
    ]

    content = [
        dbc.Button("← All Trips", href="/trips", color="link",
                   className="ps-0 mb-3 text-muted", style={"fontSize": "13px"}),

        dbc.Row([
            dbc.Col(dbc.Card(dbc.CardBody([
                html.P("Trip", className="text-muted small mb-1"),
                html.H5(trip["name"], className="mb-0"),
                html.Small(date_range, className="text-muted"),
            ]), style={"borderTop": "3px solid #0d9488", "borderRadius": "8px"}), md=4),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.P("Total Spent", className="text-muted small mb-1"),
                html.H3(f"€{trip['total']:.2f}", className="mb-0"),
            ]), style={"borderTop": "3px solid #0d9488", "borderRadius": "8px"}), md=4),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.P("Duration", className="text-muted small mb-1"),
                html.H3(f"{days} day{'s' if days != 1 else ''}", className="mb-0"),
            ]), style={"borderTop": "3px solid #0d9488", "borderRadius": "8px"}), md=4),
        ], className="mb-4 g-3"),

        dbc.Row([
            dbc.Col(dcc.Graph(figure=fig, id="trip-daily-chart"), md=12),
        ], className="mb-4"),

        dbc.Row([
            dbc.Col([
                dbc.Button("+ Add Expense", id="add-expense-trip-btn", color="primary",
                           size="sm", n_clicks=0, className="me-2"),
                dbc.Button("Import CSV", id="import-csv-trip-btn", color="outline-secondary",
                           size="sm", n_clicks=0),
            ]),
        ], className="mb-3"),

        dbc.Collapse(
            dbc.Card(dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Amount (€)", className="small"),
                        dbc.Input(id="te-amount", type="number", min=0, step=0.01, placeholder="0.00"),
                    ], md=2),
                    dbc.Col([
                        dbc.Label("Merchant", className="small"),
                        dbc.Input(id="te-merchant", type="text", placeholder="Optional"),
                    ], md=3),
                    dbc.Col([
                        dbc.Label("Category", className="small"),
                        dbc.Select(id="te-category",
                                   options=[{"label": c, "value": c} for c in CATEGORIES],
                                   value=CATEGORIES[0]),
                    ], md=3),
                    dbc.Col([
                        dbc.Label("Description", className="small"),
                        dbc.Input(id="te-description", type="text", placeholder="Optional"),
                    ], md=2),
                    dbc.Col([
                        dbc.Label("Date", className="small"),
                        dcc.DatePickerSingle(id="te-date", date=_date.today().isoformat(),
                                             display_format="DD MMM YYYY",
                                             style={"width": "100%"}),
                    ], md=2),
                ], className="mb-2"),
                dbc.Button("Save Expense", id="te-save-btn", color="primary", size="sm", n_clicks=0),
                html.Div(id="te-feedback", className="mt-2"),
            ])),
            id="add-expense-collapse",
            is_open=False,
        ),

        dbc.Collapse(
            dbc.Card(dbc.CardBody([
                dcc.Upload(
                    id="trip-csv-upload",
                    children=html.Div(["Drag & drop a CSV, or ", html.A("select file")]),
                    style={"borderWidth": "1px", "borderStyle": "dashed",
                           "borderRadius": "5px", "textAlign": "center", "padding": "20px"},
                    multiple=False,
                    accept=".csv",
                ),
                html.Div(id="trip-csv-feedback", className="mt-2"),
            ])),
            id="import-csv-collapse",
            is_open=False,
        ),

        html.H6(f"{trip['count']} expense{'s' if trip['count'] != 1 else ''}",
                className="fw-semibold mt-4 mb-2"),
        dbc.Table(
            [
                html.Thead(html.Tr([
                    html.Th("Date"), html.Th("Merchant"), html.Th("Category"),
                    html.Th("Description"), html.Th("Amount", className="text-end"),
                ])),
                html.Tbody(expense_rows if expense_rows else [
                    html.Tr([html.Td("No expenses yet", colSpan=5,
                                     className="text-muted text-center")])
                ]),
            ],
            hover=True, responsive=True, size="sm",
        ),
    ]
    return content, trip_id


@callback(
    Output("add-expense-collapse", "is_open"),
    Input("add-expense-trip-btn", "n_clicks"),
    State("add-expense-collapse", "is_open"),
    prevent_initial_call=True,
)
def toggle_add_expense(n, is_open):
    return not is_open


@callback(
    Output("import-csv-collapse", "is_open"),
    Input("import-csv-trip-btn", "n_clicks"),
    State("import-csv-collapse", "is_open"),
    prevent_initial_call=True,
)
def toggle_import_csv(n, is_open):
    return not is_open


@callback(
    Output("te-feedback", "children"),
    Output("trip-detail-content", "children", allow_duplicate=True),
    Output("trip-id-store", "data", allow_duplicate=True),
    Input("te-save-btn", "n_clicks"),
    State("te-amount", "value"),
    State("te-merchant", "value"),
    State("te-category", "value"),
    State("te-description", "value"),
    State("te-date", "date"),
    State("trip-id-store", "data"),
    State("trip-location", "search"),
    prevent_initial_call=True,
)
def save_expense(n_clicks, amount, merchant, category, description, date_val, trip_id, search):
    if not n_clicks:
        return dash.no_update, dash.no_update, dash.no_update
    if not amount or float(amount) <= 0:
        return dbc.Alert("Amount must be greater than 0.", color="danger", dismissable=True), dash.no_update, dash.no_update
    if not category:
        return dbc.Alert("Category is required.", color="danger", dismissable=True), dash.no_update, dash.no_update
    if not trip_id:
        return dbc.Alert("Trip not found.", color="danger", dismissable=True), dash.no_update, dash.no_update

    insert_trip_expense(
        trip_id=trip_id,
        amount=float(amount),
        merchant=merchant.strip() if merchant and merchant.strip() else None,
        category=category,
        description=description.strip() if description and description.strip() else None,
        date=date_val[:10] if date_val else _date.today().isoformat(),
    )
    content, new_tid = render_trip(search)
    return dbc.Alert("Expense saved.", color="success", dismissable=True, duration=3000), content, new_tid


@callback(
    Output("trip-csv-feedback", "children"),
    Output("trip-detail-content", "children", allow_duplicate=True),
    Output("trip-id-store", "data", allow_duplicate=True),
    Input("trip-csv-upload", "contents"),
    State("trip-csv-upload", "filename"),
    State("trip-id-store", "data"),
    State("trip-location", "search"),
    prevent_initial_call=True,
)
def import_csv(contents, filename, trip_id, search):
    if not contents or not trip_id:
        return dash.no_update, dash.no_update, dash.no_update

    _, content_string = contents.split(",")
    decoded = base64.b64decode(content_string)
    try:
        df = pd.read_csv(io.StringIO(decoded.decode("utf-8")))
    except Exception as exc:
        return dbc.Alert(f"Could not parse CSV: {exc}", color="danger"), dash.no_update, dash.no_update

    cols_lower = {c.lower(): c for c in df.columns}
    date_col = next((cols_lower[k] for k in _KNOWN_DATE_COLS if k in cols_lower), None)
    cost_col = next((cols_lower[k] for k in _KNOWN_COST_COLS if k in cols_lower), None)
    merchant_col = next((cols_lower[k] for k in _KNOWN_MERCHANT_COLS if k in cols_lower), None)

    if not date_col or not cost_col:
        return dbc.Alert(
            f"Could not detect date or amount columns. Found: {list(df.columns)}",
            color="warning",
        ), dash.no_update, dash.no_update

    items = []
    for _, row in df.iterrows():
        try:
            amount = float(str(row[cost_col]).replace(",", "."))
            merchant = str(row[merchant_col]).strip() if merchant_col else None
            if merchant in ("", "nan", "None"):
                merchant = None
            norm_date = pd.to_datetime(str(row[date_col]), dayfirst=True).strftime("%Y-%m-%d")
            items.append({"description": merchant or "import", "merchant": merchant,
                          "amount": amount, "date": norm_date})
        except Exception:
            continue

    if not items:
        return dbc.Alert("No valid rows found in CSV.", color="warning"), dash.no_update, dash.no_update

    try:
        categorised = classify_expenses(items)
    except Exception:
        categorised = [{"category": "Miscellaneous"} for _ in items]

    for item, cat_result in zip(items, categorised):
        insert_trip_expense(
            trip_id=trip_id,
            amount=item["amount"],
            merchant=item["merchant"],
            category=cat_result.get("category", "Miscellaneous"),
            description=None,
            date=item["date"],
        )

    content, new_tid = render_trip(search)
    return dbc.Alert(f"Imported {len(items)} expenses.", color="success", dismissable=True), content, new_tid
```

- [ ] **Step 2: Run full test suite — confirm no regressions**

```bash
uv run pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add pages/trip_detail.py
git commit -m "feat: add /trip detail page with manual add and CSV import"
```

---

### Task 4: Wire Trips into `app.py`

**Files:**
- Modify: `app.py`

**Interfaces:**
- Adds `init_trip_db()` call at startup (after existing `init_db()`)
- Adds "Trips" as the first NavLink in the `dbc.Offcanvas` drawer

- [ ] **Step 1: Add import**

In `app.py`, add to the existing imports block:

```python
from expense_tracker_agent.trip_db import init_trip_db
```

- [ ] **Step 2: Call `init_trip_db()` at startup**

After the existing startup lines:
```python
init_db()
migrate_from_csv(Path("expenses.csv"))
```

Add:
```python
init_trip_db()
```

- [ ] **Step 3: Add "Trips" to off-canvas drawer**

In the `dbc.Offcanvas` `dbc.Nav` list, add as the **first** item (before "Set Budgets"):

```python
dbc.NavLink("Trips", href="/trips", active="exact", className="mb-2",
            style={"fontWeight": "500"}),
```

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest tests/ -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add app.py
git commit -m "feat: initialise trips DB and add Trips link to off-canvas drawer"
```

---

## Verification

1. `git checkout -b feat/trips` from `main` before starting Task 1.
2. Start app: `uv run python app.py`
3. Open ☰ drawer → "Trips" appears first in the list
4. Navigate to `/trips` → empty state message with "+ New Trip" button
5. Click "+ New Trip", type "Barcelona May 2026", click "Create" → redirected to `/trip?id=1`
6. Header shows trip name, €0.00, 0 days; chart shows "No expenses yet"
7. Click "+ Add Expense", fill in amount €25, category "Food & Dining", save → row appears in table, chart updates
8. Click "Import CSV", upload a CSV → expenses imported, table and chart refresh
9. Click "← All Trips" → trip card shows name, date range, total, count
10. Click "✕" on a trip card → trip removed
11. Navigate to `/` (Dashboard) → unchanged, no trip data visible
12. Full suite: `uv run pytest tests/ -q` → all pass
13. Create PR from `feat/trips` into `main`
