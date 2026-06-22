# pages/history.py
from datetime import date, timedelta

import json

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, dcc, html

from expense_tracker_agent.db import fetch_expenses, update_expense_category
from expense_tracker_agent.tools import CATEGORIES

dash.register_page(__name__, path="/history", name="History")


# ── Pure stat helpers ─────────────────────────────────────────────────────────

def compute_weekly_avg(rows: list[dict], category: str) -> float:
    """Average Mon–Sun weekly spend for `category` across all complete weeks with data."""
    filtered = [r for r in rows if r["category"] == category]
    if not filtered:
        return 0.0
    today = date.today()
    current_monday = today - timedelta(days=today.weekday())
    weekly: dict[tuple, float] = {}
    for r in filtered:
        d = date.fromisoformat(r["date"])
        if d >= current_monday:  # exclude current incomplete week
            continue
        week_key = d.isocalendar()[:2]  # (year, ISO-week) — ISO weeks are Mon–Sun
        weekly[week_key] = weekly.get(week_key, 0.0) + r["amount"]
    if not weekly:
        return 0.0
    return sum(weekly.values()) / len(weekly)


def compute_monthly_avg(rows: list[dict], category: str) -> float:
    """Average 1st–last-day monthly spend for `category` across all complete months with data."""
    filtered = [r for r in rows if r["category"] == category]
    if not filtered:
        return 0.0
    today = date.today()
    current_month_start = today.replace(day=1)
    monthly: dict[tuple, float] = {}
    for r in filtered:
        d = date.fromisoformat(r["date"])
        if d >= current_month_start:  # exclude current incomplete month
            continue
        key = (d.year, d.month)
        monthly[key] = monthly.get(key, 0.0) + r["amount"]
    if not monthly:
        return 0.0
    return sum(monthly.values()) / len(monthly)


def last_purchase_info(rows: list[dict], category: str) -> dict | None:
    """Return the most recent row for `category`, or None."""
    filtered = [r for r in rows if r["category"] == category]
    if not filtered:
        return None
    return max(filtered, key=lambda r: r["date"])


# ── Layout helpers ────────────────────────────────────────────────────────────

_CAT_OPTIONS = [{"label": "All Categories", "value": ""}] + [
    {"label": c, "value": c} for c in CATEGORIES
]

_CARD_STYLE = {"borderTop": "3px solid #14b8a6", "borderRadius": "8px"}


def _stat_card(label: str, value: str, sub: str = ""):
    body_children = [
        html.P(label, className="text-muted small mb-1"),
        html.H4(value, className="mb-0"),
    ]
    if sub:
        body_children.append(html.Small(sub, className="text-muted"))
    return dbc.Col(dbc.Card(dbc.CardBody(body_children), style=_CARD_STYLE), md=4)


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


layout = html.Div([
    dcc.Store(id="history-cat-updated-store"),
    dcc.Store(id="history-page-num", data=1),
    html.H5("History", className="mb-1"),
    html.P("Browse past transactions and track spending by category.",
           className="text-muted mb-4"),

    # ── Category insights ──────────────────────────────────────────────────
    dbc.Card(dbc.CardBody([
        html.H6("Category Insights", className="fw-semibold mb-3"),
        dbc.Row([
            dbc.Col([
                html.Label("Category", className="small text-muted mb-1"),
                dbc.Select(
                    id="history-cat-select",
                    options=_CAT_OPTIONS,
                    value="Groceries",
                ),
            ], md=4),
        ], className="mb-3"),
        html.Div(id="history-stat-cards"),
    ]), className="mb-4"),

    # ── Transaction browser ────────────────────────────────────────────────
    dbc.Card(dbc.CardBody([
        html.H6("Transactions", className="fw-semibold mb-3"),
        dbc.Row([
            dbc.Col([
                html.Label("Category", className="small text-muted mb-1"),
                dbc.Select(id="history-filter-cat", options=_CAT_OPTIONS, value="Groceries"),
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
        dbc.Row([
            dbc.Col(
                dbc.Button("← Prev", id="history-prev-btn", color="outline-secondary",
                           size="sm", disabled=True),
                width="auto",
            ),
            dbc.Col(
                html.Span(id="history-page-info", className="text-muted small"),
                width="auto", className="d-flex align-items-center",
            ),
            dbc.Col(
                dbc.Button("Next →", id="history-next-btn", color="outline-secondary",
                           size="sm", disabled=True),
                width="auto",
            ),
        ], className="mt-3 justify-content-center g-2", align="center"),
    ])),
])


# ── Callbacks ─────────────────────────────────────────────────────────────────

@callback(
    Output("history-stat-cards", "children"),
    Output("history-filter-cat", "value"),
    Input("history-cat-select", "value"),
)
def update_stat_cards(category: str):
    """Update the three stat cards when a category is selected."""
    if not category:
        return html.P("Select a category above to see averages.", className="text-muted small"), ""
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
        _stat_card("Avg / Week", f"€{avg_week:.2f}", "Mon–Sun, all time"),
        _stat_card("Avg / Month", f"€{avg_month:.2f}", "1st–last day, all time"),
        _stat_card("Last Purchase", last_text, last_sub),
    ])
    return cards, category


_PAGE_SIZE = 10


@callback(
    Output("history-results-count", "children"),
    Output("history-table", "children"),
    Output("history-page-info", "children"),
    Output("history-prev-btn", "disabled"),
    Output("history-next-btn", "disabled"),
    Input("history-filter-cat", "value"),
    Input("history-search", "value"),
    Input("expense-deleted-store", "data"),
    Input("history-cat-updated-store", "data"),
    Input("history-page-num", "data"),
)
def update_table(category: str, keyword: str, _deleted, _cat_updated, page_num):
    """Filter and render the transaction table with pagination."""
    rows = fetch_expenses()
    kw = (keyword or "").strip().lower()
    filtered = [
        r for r in rows
        if (not category or r["category"] == category)
        and (not kw or kw in (r.get("merchant") or "").lower()
             or kw in r.get("description", "").lower())
    ]
    filtered.sort(key=lambda r: r["date"], reverse=True)

    total = len(filtered)
    total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
    page = max(1, min(page_num or 1, total_pages))
    page_rows = filtered[(page - 1) * _PAGE_SIZE : page * _PAGE_SIZE]

    if not page_rows:
        return (
            "0 transactions found",
            html.P("No transactions match your search.", className="text-muted small mt-2"),
            "",
            True,
            True,
        )

    count_text = f"{total} transaction{'s' if total != 1 else ''} found"
    page_info = f"Page {page} of {total_pages}"
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
                    html.Td(
                        dbc.Select(
                            id={"type": "hist-cat-select", "index": r["id"]},
                            options=[{"label": c, "value": c} for c in CATEGORIES],
                            value=r["category"],
                            size="sm",
                            style={"fontSize": "12px", "minWidth": "150px"},
                        )
                    ),
                    html.Td(f"€{r['amount']:.2f}", className="fw-semibold text-end"),
                    html.Td(r["description"], className="text-muted small"),
                    html.Td(
                        dbc.Button("×", id={"type": "del-expense", "index": r["id"]},
                                   size="sm", color="link",
                                   style={"color": "#dc3545", "padding": "0 4px", "lineHeight": "1"}),
                        className="text-center",
                    ),
                ])
                for r in page_rows
            ]),
        ],
        hover=True, responsive=True, size="sm", className="mb-0",
    )
    return count_text, table, page_info, page <= 1, page >= total_pages


@callback(
    Output("history-page-num", "data"),
    Input("history-prev-btn", "n_clicks"),
    State("history-page-num", "data"),
    prevent_initial_call=True,
)
def go_prev(n_clicks, current_page):
    return max(1, (current_page or 1) - 1)


@callback(
    Output("history-page-num", "data", allow_duplicate=True),
    Input("history-next-btn", "n_clicks"),
    State("history-page-num", "data"),
    prevent_initial_call=True,
)
def go_next(n_clicks, current_page):
    return (current_page or 1) + 1


@callback(
    Output("history-page-num", "data", allow_duplicate=True),
    Input("history-filter-cat", "value"),
    Input("history-search", "value"),
    prevent_initial_call=True,
)
def reset_page_on_filter_change(_cat, _kw):
    return 1


@callback(
    Output("history-cat-updated-store", "data"),
    Input({"type": "hist-cat-select", "index": ALL}, "value"),
    prevent_initial_call=True,
)
def update_category_inline(values):
    """Persist an inline category change to the database."""
    ctx = dash.callback_context
    for trigger in ctx.triggered:
        if trigger["value"]:
            expense_id = json.loads(trigger["prop_id"].split(".")[0])["index"]
            update_expense_category(expense_id, trigger["value"])
    return ctx.triggered_id
