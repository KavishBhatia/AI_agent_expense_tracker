# pages/history.py
from datetime import date, timedelta

import json
import re

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, dcc, html

from expense_tracker_agent.db import fetch_expense, fetch_expenses, update_expense, update_expense_category
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
    dcc.Store(id="history-expense-updated-store"),
    dcc.Store(id="history-page-num", data=1),
    dcc.Store(id="editing-expense-id"),
    html.H5("History", className="mb-1"),
    html.P("Browse past transactions and track spending by category.",
           className="text-muted mb-4"),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("Edit Expense")),
        dbc.ModalBody([
            dbc.Row([
                dbc.Col([
                    dbc.Label("Amount (€)", className="small"),
                    dbc.Input(id="edit-e-amount", type="number", min=0, step=0.01),
                ], md=3),
                dbc.Col([
                    dbc.Label("Merchant", className="small"),
                    dbc.Input(id="edit-e-merchant", type="text", placeholder="Optional"),
                ], md=4),
                dbc.Col([
                    dbc.Label("Category", className="small"),
                    dbc.Select(id="edit-e-category",
                               options=[{"label": c, "value": c} for c in CATEGORIES]),
                ], md=5),
            ], className="mb-2 g-2"),
            dbc.Row([
                dbc.Col([
                    dbc.Label("Description", className="small"),
                    dbc.Input(id="edit-e-description", type="text"),
                ], md=8),
                dbc.Col([
                    dbc.Label("Date", className="small"),
                    dcc.DatePickerSingle(id="edit-e-date",
                                         display_format="DD MMM YYYY",
                                         style={"width": "100%"}),
                ], md=4),
            ], className="g-2"),
            html.Div(id="edit-e-feedback", className="mt-2"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="edit-e-cancel", color="secondary", n_clicks=0),
            dbc.Button("Save", id="edit-e-save", n_clicks=0,
                       style={"backgroundColor": "#0d9488", "borderColor": "#0d9488",
                              "color": "#fff"}),
        ]),
    ], id="edit-expense-modal", is_open=False, size="lg"),

    # ── Category insights ──────────────────────────────────────────────────
    dbc.Card(dbc.CardBody([
        html.H6("Category Insights", className="fw-semibold mb-3"),
        html.Div(id="history-stat-cards"),
    ]), className="mb-4"),

    # ── Transaction browser ────────────────────────────────────────────────
    dbc.Card(dbc.CardBody([
        html.H6("Transactions", className="fw-semibold mb-3"),
        dcc.Download(id="history-download-csv"),
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
        dbc.Row([
            dbc.Col(html.Div(id="history-results-count", className="text-muted small")),
            dbc.Col(
                dbc.Button("⬇ Export CSV", id="history-export-btn",
                           color="outline-secondary", size="sm"),
                width="auto",
            ),
        ], className="mb-2 align-items-center"),
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
    Input("history-filter-cat", "value"),
    Input("expense-deleted-store", "data"),
    Input("history-cat-updated-store", "data"),
    Input("history-expense-updated-store", "data"),
)
def update_stat_cards(category: str, _deleted, _cat_updated, _expense_updated):
    """Update the three stat cards when the transaction browser category changes."""
    if not category:
        return html.P("Select a specific category below (not \"All Categories\") to see averages.", className="text-muted small")
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
    return dbc.Row([
        _stat_card("Avg / Week", f"€{avg_week:.2f}", "Mon–Sun, all time"),
        _stat_card("Avg / Month", f"€{avg_month:.2f}", "1st–last day, all time"),
        _stat_card("Last Purchase", last_text, last_sub),
    ])


_PAGE_SIZE = 10


def _parse_page_info(page_info: str | None) -> tuple[int, int]:
    """Return current page and total pages parsed from 'Page X of Y' text."""
    match = re.search(r"Page\s+(\d+)\s+of\s+(\d+)", page_info or "")
    if not match:
        return 1, 1
    return int(match.group(1)), int(match.group(2))


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
    Input("history-expense-updated-store", "data"),
    Input("history-page-num", "data"),
)
def update_table(category: str, keyword: str, _deleted, _cat_updated, _expense_updated, page_num):
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
                    html.Td([
                        dbc.Button("✎", id={"type": "edit-expense", "index": r["id"]},
                                   size="sm", color="link", title="Edit expense",
                                   style={"color": "#6c757d", "padding": "0 4px", "lineHeight": "1"}),
                        dbc.Button("×", id={"type": "del-expense", "index": r["id"]},
                                   size="sm", color="link", title="Delete expense",
                                   style={"color": "#dc3545", "padding": "0 4px", "lineHeight": "1"}),
                    ], className="text-center text-nowrap"),
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
    State("history-page-info", "children"),
    prevent_initial_call=True,
)
def go_prev(n_clicks, page_info):
    page, _ = _parse_page_info(page_info)
    return max(1, page - 1)


@callback(
    Output("history-page-num", "data", allow_duplicate=True),
    Input("history-next-btn", "n_clicks"),
    State("history-page-info", "children"),
    prevent_initial_call=True,
)
def go_next(n_clicks, page_info):
    page, total_pages = _parse_page_info(page_info)
    return min(total_pages, page + 1)


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


@callback(
    Output("editing-expense-id", "data"),
    Output("edit-expense-modal", "is_open"),
    Output("edit-e-amount", "value"),
    Output("edit-e-merchant", "value"),
    Output("edit-e-category", "value"),
    Output("edit-e-description", "value"),
    Output("edit-e-date", "date"),
    Input({"type": "edit-expense", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def open_edit_expense_modal(n_clicks_list):
    """Pre-fill and open the edit modal for the clicked row."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return (dash.no_update,) * 7
    for trigger in ctx.triggered:
        if trigger["value"]:
            expense_id = json.loads(trigger["prop_id"].split(".")[0])["index"]
            expense = fetch_expense(expense_id)
            if not expense:
                return (dash.no_update,) * 7
            return (
                expense_id,
                True,
                expense["amount"],
                expense["merchant"],
                expense["category"],
                expense["description"],
                expense["date"],
            )
    return (dash.no_update,) * 7


@callback(
    Output("edit-expense-modal", "is_open", allow_duplicate=True),
    Output("history-expense-updated-store", "data"),
    Output("edit-e-feedback", "children"),
    Input("edit-e-save", "n_clicks"),
    Input("edit-e-cancel", "n_clicks"),
    State("editing-expense-id", "data"),
    State("edit-e-amount", "value"),
    State("edit-e-merchant", "value"),
    State("edit-e-category", "value"),
    State("edit-e-description", "value"),
    State("edit-e-date", "date"),
    prevent_initial_call=True,
)
def save_edit_expense(save_clicks, cancel_clicks, expense_id,
                      amount, merchant, category, description, date_val):
    """Validate and persist an edited expense."""
    ctx = dash.callback_context
    if ctx.triggered_id == "edit-e-cancel":
        return False, dash.no_update, ""
    if not save_clicks or not expense_id:
        return dash.no_update, dash.no_update, dash.no_update
    if not amount or float(amount) <= 0:
        return (
            True, dash.no_update,
            dbc.Alert("Amount must be greater than 0.", color="danger", className="py-1 small"),
        )
    if not category:
        return (
            True, dash.no_update,
            dbc.Alert("Category is required.", color="danger", className="py-1 small"),
        )
    if not description or not description.strip():
        return (
            True, dash.no_update,
            dbc.Alert("Description is required.", color="danger", className="py-1 small"),
        )
    if not date_val:
        return (
            True, dash.no_update,
            dbc.Alert("Date is required.", color="danger", className="py-1 small"),
        )
    update_expense(
        expense_id,
        float(amount),
        merchant or None,
        category,
        description.strip(),
        date_val[:10],
    )
    return False, expense_id, ""


@callback(
    Output("history-download-csv", "data"),
    Input("history-export-btn", "n_clicks"),
    State("history-filter-cat", "value"),
    State("history-search", "value"),
    prevent_initial_call=True,
)
def export_csv(n_clicks, category, keyword):
    """Download all rows matching the current filters as a CSV file."""
    import csv
    import io

    rows = fetch_expenses()
    kw = (keyword or "").strip().lower()
    filtered = [
        r for r in rows
        if (not category or r["category"] == category)
        and (not kw or kw in (r.get("merchant") or "").lower()
             or kw in r.get("description", "").lower())
    ]
    filtered.sort(key=lambda r: r["date"], reverse=True)

    buf = io.StringIO(newline="")
    fields = ["date", "merchant", "category", "amount", "description"]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(filtered)

    filename = f"expenses_{category or 'all'}_{date.today().isoformat()}.csv"
    return dcc.send_string(buf.getvalue(), filename)
