# pages/trip_detail.py
import base64
import io
from datetime import date as _date

import dash
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, callback, dcc, html

from expense_tracker_agent.categoriser import classify_expenses
from expense_tracker_agent.tools import CATEGORIES
from expense_tracker_agent.trip_db import (
    delete_trip_expense, fetch_trip, fetch_trip_expense, fetch_trip_expenses,
    insert_trip_expense, trip_expense_exists, update_trip_expense,
)

dash.register_page(__name__, path="/trip", name="Trip Detail")

_KNOWN_DATE_COLS = ["date", "datum", "day"]
_KNOWN_COST_COLS = ["cost", "amount", "price", "spent", "kosten", "betrag", "preis"]
_KNOWN_NAME_COLS = [
    # most specific first — typical trip export column names
    "item",
    # merchant / shop specific
    "merchant", "store", "shop", "supermarket", "supermarket name",
    # generic description columns
    "description", "details", "name", "label", "title",
    # loose fallbacks — common spreadsheet extras (checked last to avoid false matches)
    "note", "notes", "what",
    # german
    "beschreibung", "bezeichnung", "markt", "laden", "zweck",
]


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
        return (_date.fromisoformat(end) - _date.fromisoformat(start)).days + 1
    except Exception:
        return 0


def layout(**kwargs):
    return html.Div([
        dcc.Location(id="trip-location"),
        dcc.Store(id="trip-id-store"),
        dcc.Store(id="pending-delete-trip-expense-id"),
        dcc.Store(id="editing-trip-expense-id"),
        dcc.Store(id="te-pending-force-data"),
        html.Div(id="te-feedback"),
        dcc.Loading(
            html.Div(id="trip-csv-feedback"),
            type="circle",
            color="#e11d48",
        ),
        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Delete expense?")),
            dbc.ModalBody(html.Div(id="del-trip-expense-modal-body",
                                   children="This will permanently delete the expense.")),
            dbc.ModalFooter([
                dbc.Button("Cancel", id="confirm-del-trip-expense-cancel",
                           color="secondary", n_clicks=0),
                dbc.Button("Delete", id="confirm-del-trip-expense-btn",
                           color="danger", n_clicks=0),
            ]),
        ], id="confirm-delete-trip-expense-modal", is_open=False),

        dbc.Modal([
            dbc.ModalHeader(dbc.ModalTitle("Edit Expense")),
            dbc.ModalBody([
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Amount (€)", className="small"),
                        dbc.Input(id="edit-te-amount", type="number", min=0, step=0.01),
                    ], md=3),
                    dbc.Col([
                        dbc.Label("Merchant / Description", className="small"),
                        dbc.Input(id="edit-te-merchant", type="text", placeholder="Optional"),
                    ], md=4),
                    dbc.Col([
                        dbc.Label("Category", className="small"),
                        dbc.Select(id="edit-te-category",
                                   options=[{"label": c, "value": c} for c in CATEGORIES]),
                    ], md=5),
                ], className="mb-2 g-2"),
                dbc.Row([
                    dbc.Col([
                        dbc.Label("Notes", className="small"),
                        dbc.Input(id="edit-te-description", type="text", placeholder="Optional"),
                    ], md=8),
                    dbc.Col([
                        dbc.Label("Date", className="small"),
                        dcc.DatePickerSingle(id="edit-te-date",
                                             display_format="DD MMM YYYY",
                                             style={"width": "100%"}),
                    ], md=4),
                ], className="g-2"),
                html.Div(id="edit-te-feedback", className="mt-2"),
            ]),
            dbc.ModalFooter([
                dbc.Button("Cancel", id="edit-te-cancel", color="secondary", n_clicks=0),
                dbc.Button("Save", id="edit-te-save", n_clicks=0,
                           style={"backgroundColor": "#e11d48", "borderColor": "#e11d48",
                                  "color": "#fff"}),
            ]),
        ], id="edit-trip-expense-modal", is_open=False, size="lg"),

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
        n_bars = len(daily)
        chart_md = 4 if n_bars <= 3 else (6 if n_bars <= 6 else 12)
        fig = px.bar(daily, x="display", y="amount",
                     labels={"display": "Date", "amount": "€ Spent"},
                     title="Daily Spending",
                     color_discrete_sequence=["#e11d48"])
        fig.update_xaxes(type="category")
        fig.update_layout(height=300, margin=dict(t=30, b=10, l=40, r=10))
    else:
        chart_md = 4
        fig = go.Figure().add_annotation(text="No expenses yet", showarrow=False)

    expense_rows = [
        html.Tr([
            html.Td(_fmt(e["date"])),
            html.Td(e["merchant"] or "—"),
            html.Td(html.Span(e["category"], className="small",
                              style={"backgroundColor": "#f43f5e", "color": "#fff",
                                     "borderRadius": "4px", "padding": "2px 7px"})),
            html.Td(e["description"] or "—", className="text-muted small"),
            html.Td(f"€{e['amount']:.2f}", className="fw-semibold text-end"),
            html.Td([
                dbc.Button("✎", id={"type": "edit-trip-expense", "index": e["id"]},
                           size="sm", color="link", title="Edit expense",
                           style={"color": "#6c757d", "padding": "0 4px", "lineHeight": "1"},
                           **{"aria-label": "Edit expense"}),
                dbc.Button("×", id={"type": "del-trip-expense", "index": e["id"]},
                           size="sm", color="link", title="Delete expense",
                           style={"color": "#dc3545", "padding": "0 4px", "lineHeight": "1"},
                           **{"aria-label": "Delete expense"}),
            ], className="text-center text-nowrap"),
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
            ]), style={"borderTop": "3px solid #e11d48", "borderRadius": "8px"}), md=4),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.P("Total Spent", className="text-muted small mb-1"),
                html.H3(f"€{trip['total']:.2f}", className="mb-0"),
            ]), style={"borderTop": "3px solid #e11d48", "borderRadius": "8px"}), md=4),
            dbc.Col(dbc.Card(dbc.CardBody([
                html.P("Duration", className="text-muted small mb-1"),
                html.H3(f"{days} day{'s' if days != 1 else ''}", className="mb-0"),
            ]), style={"borderTop": "3px solid #e11d48", "borderRadius": "8px"}), md=4),
        ], className="mb-4 g-3"),

        dbc.Row([
            dbc.Col([
                dbc.Button("▼ Daily Spending", id="chart-toggle-btn", color="link",
                           size="sm", n_clicks=0, className="ps-0 mb-1",
                           style={"color": "#e11d48", "textDecoration": "none"}),
                dbc.Collapse(
                    dcc.Graph(figure=fig, id="trip-daily-chart",
                              style={"height": "300px"}),
                    id="chart-collapse",
                    is_open=False,
                ),
            ], md=chart_md),
        ], className="mb-2"),

        dbc.Row([
            dbc.Col([
                dbc.Button("+ Add Expense", id="add-expense-trip-btn", size="sm",
                           n_clicks=0, className="me-2",
                           style={"backgroundColor": "#e11d48", "borderColor": "#e11d48", "color": "#fff"}),
                dbc.Button("Import CSV", id="import-csv-trip-btn", size="sm", n_clicks=0,
                           style={"color": "#e11d48", "borderColor": "#e11d48",
                                  "backgroundColor": "transparent"}),
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
                dbc.Button("Save Expense", id="te-save-btn", size="sm", n_clicks=0,
                           style={"backgroundColor": "#e11d48", "borderColor": "#e11d48", "color": "#fff"}),
                dbc.Button("Save anyway", id="te-force-save-btn", size="sm", n_clicks=0,
                           color="warning", className="ms-2",
                           style={"display": "none"}),
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
                    html.Th("Description"), html.Th("Amount", className="text-end"), html.Th(""),
                ])),
                html.Tbody(expense_rows if expense_rows else [
                    html.Tr([html.Td("No expenses yet", colSpan=6,
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


_FORCE_BTN_SHOW = {"display": "inline-block"}
_FORCE_BTN_HIDE = {"display": "none"}


@callback(
    Output("te-feedback", "children"),
    Output("trip-detail-content", "children", allow_duplicate=True),
    Output("trip-id-store", "data", allow_duplicate=True),
    Output("te-pending-force-data", "data"),
    Output("te-force-save-btn", "style"),
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
    _no = dash.no_update
    if not n_clicks:
        return _no, _no, _no, _no, _no
    if not amount or float(amount) <= 0:
        return dbc.Alert("Amount must be greater than 0.", color="danger", dismissable=True), _no, _no, None, _FORCE_BTN_HIDE
    if not category:
        return dbc.Alert("Category is required.", color="danger", dismissable=True), _no, _no, None, _FORCE_BTN_HIDE
    if not trip_id:
        return dbc.Alert("Trip not found.", color="danger", dismissable=True), _no, _no, None, _FORCE_BTN_HIDE

    canonical_merchant = merchant.strip() if merchant and merchant.strip() else None
    canonical_date = date_val[:10] if date_val else _date.today().isoformat()

    if trip_expense_exists(trip_id, canonical_date, canonical_merchant, float(amount)):
        pending = {
            "trip_id": trip_id, "amount": float(amount),
            "merchant": canonical_merchant, "category": category,
            "description": description.strip() if description and description.strip() else None,
            "date": canonical_date,
        }
        warning = dbc.Alert(
            [f"⚠️ A {canonical_merchant or 'matching'} expense of €{float(amount):.2f} "
             f"on {canonical_date} already exists. Not saved — click 'Save anyway' to override."],
            color="warning", dismissable=True,
        )
        return warning, _no, _no, pending, _FORCE_BTN_SHOW

    insert_trip_expense(
        trip_id=trip_id,
        amount=float(amount),
        merchant=canonical_merchant,
        category=category,
        description=description.strip() if description and description.strip() else None,
        date=canonical_date,
    )
    content, new_tid = render_trip(search)
    return dbc.Alert("Expense saved.", color="success", dismissable=True, duration=3000), content, new_tid, None, _FORCE_BTN_HIDE


@callback(
    Output("te-feedback", "children", allow_duplicate=True),
    Output("trip-detail-content", "children", allow_duplicate=True),
    Output("trip-id-store", "data", allow_duplicate=True),
    Output("te-pending-force-data", "data", allow_duplicate=True),
    Output("te-force-save-btn", "style", allow_duplicate=True),
    Input("te-force-save-btn", "n_clicks"),
    State("te-pending-force-data", "data"),
    State("trip-location", "search"),
    prevent_initial_call=True,
)
def force_save_expense(n_clicks, pending, search):
    _no = dash.no_update
    if not n_clicks or not pending:
        return _no, _no, _no, _no, _no
    insert_trip_expense(
        trip_id=pending["trip_id"],
        amount=pending["amount"],
        merchant=pending["merchant"],
        category=pending["category"],
        description=pending["description"],
        date=pending["date"],
    )
    content, new_tid = render_trip(search)
    return dbc.Alert("Expense saved.", color="success", dismissable=True, duration=3000), content, new_tid, None, _FORCE_BTN_HIDE


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
    if not contents:
        return dash.no_update, dash.no_update, dash.no_update
    if not trip_id:
        return dbc.Alert("Trip ID missing — try refreshing the page.", color="danger"), dash.no_update, dash.no_update

    _, content_string = contents.split(",", 1)
    decoded = base64.b64decode(content_string)
    try:
        decoded_text = decoded.decode("utf-8")
    except UnicodeDecodeError:
        try:
            decoded_text = decoded.decode("latin-1")
        except Exception as exc:
            return dbc.Alert(f"Could not parse CSV: {exc}", color="danger"), dash.no_update, dash.no_update

    try:
        df = pd.read_csv(io.StringIO(decoded_text), sep=None, engine="python")
    except Exception:
        try:
            df = pd.read_csv(io.StringIO(decoded_text))
        except Exception as exc:
            return dbc.Alert(f"Could not parse CSV: {exc}", color="danger"), dash.no_update, dash.no_update

    print(f"[trip import] columns in '{filename}': {list(df.columns)}")

    cols_lower = {c.strip().lower(): c for c in df.columns}
    date_col = next((cols_lower[k] for k in _KNOWN_DATE_COLS if k in cols_lower), None)
    cost_col = next((cols_lower[k] for k in _KNOWN_COST_COLS if k in cols_lower), None)
    name_col = next((cols_lower[k] for k in _KNOWN_NAME_COLS if k in cols_lower), None)

    # prefix fallback: handles "Cost for 2", "Cost per person", etc.
    if not cost_col:
        cost_prefixes = tuple(_KNOWN_COST_COLS)
        cost_col = next(
            (orig for lower, orig in cols_lower.items() if lower.startswith(cost_prefixes)),
            None,
        )

    print(f"[trip import] detected → date={date_col!r} cost={cost_col!r} name={name_col!r}")

    if not date_col or not cost_col:
        return dbc.Alert(
            f"Could not detect date or amount columns. "
            f"Columns found: {list(df.columns)}. "
            f"Expected one of {sorted(_KNOWN_DATE_COLS)} for date and {sorted(_KNOWN_COST_COLS)} for amount.",
            color="warning",
        ), dash.no_update, dash.no_update

    items = []
    skipped = 0
    for _, row in df.iterrows():
        try:
            raw_amount = str(row[cost_col]).replace(",", ".").strip()
            # strip any currency symbols
            raw_amount = "".join(c for c in raw_amount if c.isdigit() or c in ".+-")
            amount = float(raw_amount)
            if pd.isna(amount) or amount == 0:
                skipped += 1
                continue
            merchant = str(row[name_col]).strip() if name_col else None
            if merchant in ("", "nan", "None", "NaN"):
                merchant = None
            norm_date = pd.to_datetime(str(row[date_col]), dayfirst=True).strftime("%Y-%m-%d")
            items.append({"description": merchant or "import", "merchant": merchant,
                          "amount": amount, "date": norm_date})
        except Exception as exc:
            print(f"[trip import] skipped row: {exc}")
            skipped += 1
            continue

    print(f"[trip import] parsed {len(items)} valid rows, skipped {skipped}")

    if not items:
        return dbc.Alert(
            f"No valid rows found in CSV (skipped {skipped} rows). "
            f"Check that the amount column contains numbers.",
            color="warning",
        ), dash.no_update, dash.no_update

    try:
        categorised = classify_expenses(items)
        # guard against API returning fewer items than expected
        if not categorised or len(categorised) != len(items):
            print(f"[trip import] classify_expenses returned {len(categorised) if categorised else 0} items for {len(items)} — falling back")
            categorised = ["Miscellaneous"] * len(items)
    except Exception as exc:
        print(f"[trip import] classify_expenses failed: {exc} — falling back to Miscellaneous")
        categorised = ["Miscellaneous"] * len(items)

    inserted = 0
    for item, category in zip(items, categorised):
        insert_trip_expense(
            trip_id=trip_id,
            amount=item["amount"],
            merchant=item["merchant"],
            category=category,
            description=None,
            date=item["date"],
        )
        inserted += 1

    print(f"[trip import] inserted {inserted} expenses into trip {trip_id}")

    extra = f" ({skipped} rows skipped)" if skipped else ""
    content, new_tid = render_trip(search)
    return dbc.Alert(f"Imported {inserted} expenses{extra}.", color="success", dismissable=True), content, new_tid


@callback(
    Output("pending-delete-trip-expense-id", "data"),
    Output("confirm-delete-trip-expense-modal", "is_open"),
    Output("del-trip-expense-modal-body", "children"),
    Input({"type": "del-trip-expense", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def open_del_trip_expense_modal(n_clicks_list):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update, dash.no_update
    import json
    for trigger in ctx.triggered:
        if trigger["value"]:
            expense_id = json.loads(trigger["prop_id"].split(".")[0])["index"]
            body = ["Permanently delete this expense?"]
            return expense_id, True, body
    return dash.no_update, dash.no_update, dash.no_update


@callback(
    Output("confirm-delete-trip-expense-modal", "is_open", allow_duplicate=True),
    Output("trip-detail-content", "children", allow_duplicate=True),
    Output("trip-id-store", "data", allow_duplicate=True),
    Input("confirm-del-trip-expense-btn", "n_clicks"),
    Input("confirm-del-trip-expense-cancel", "n_clicks"),
    State("pending-delete-trip-expense-id", "data"),
    State("trip-location", "search"),
    prevent_initial_call=True,
)
def handle_del_trip_expense_confirm(confirm_clicks, cancel_clicks, expense_id, search):
    ctx = dash.callback_context
    if ctx.triggered_id == "confirm-del-trip-expense-btn" and confirm_clicks and expense_id:
        delete_trip_expense(expense_id)
        content, new_tid = render_trip(search)
        return False, content, new_tid
    return False, dash.no_update, dash.no_update


@callback(
    Output("editing-trip-expense-id", "data"),
    Output("edit-trip-expense-modal", "is_open"),
    Output("edit-te-amount", "value"),
    Output("edit-te-merchant", "value"),
    Output("edit-te-category", "value"),
    Output("edit-te-description", "value"),
    Output("edit-te-date", "date"),
    Input({"type": "edit-trip-expense", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def open_edit_expense_modal(n_clicks_list):
    import json
    ctx = dash.callback_context
    if not ctx.triggered:
        return (dash.no_update,) * 7
    for trigger in ctx.triggered:
        if trigger["value"]:
            expense_id = json.loads(trigger["prop_id"].split(".")[0])["index"]
            expense = fetch_trip_expense(expense_id)
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
    Output("edit-trip-expense-modal", "is_open", allow_duplicate=True),
    Output("trip-detail-content", "children", allow_duplicate=True),
    Output("trip-id-store", "data", allow_duplicate=True),
    Output("edit-te-feedback", "children"),
    Input("edit-te-save", "n_clicks"),
    Input("edit-te-cancel", "n_clicks"),
    State("editing-trip-expense-id", "data"),
    State("edit-te-amount", "value"),
    State("edit-te-merchant", "value"),
    State("edit-te-category", "value"),
    State("edit-te-description", "value"),
    State("edit-te-date", "date"),
    State("trip-location", "search"),
    prevent_initial_call=True,
)
def save_edit_expense(save_clicks, cancel_clicks, expense_id,
                      amount, merchant, category, description, date_val, search):
    ctx = dash.callback_context
    if ctx.triggered_id == "edit-te-cancel":
        return False, dash.no_update, dash.no_update, ""
    if not save_clicks or not expense_id:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    if not amount or float(amount) <= 0:
        return (
            True, dash.no_update, dash.no_update,
            dbc.Alert("Amount must be greater than 0.", color="danger", className="py-1 small"),
        )
    if not category:
        return (
            True, dash.no_update, dash.no_update,
            dbc.Alert("Category is required.", color="danger", className="py-1 small"),
        )
    if not date_val:
        return (
            True, dash.no_update, dash.no_update,
            dbc.Alert("Date is required.", color="danger", className="py-1 small"),
        )
    update_trip_expense(
        expense_id,
        float(amount),
        merchant or None,
        category,
        description or None,
        date_val,
    )
    content, new_tid = render_trip(search)
    return False, content, new_tid, ""


@callback(
    Output("chart-collapse", "is_open"),
    Output("chart-toggle-btn", "children"),
    Input("chart-toggle-btn", "n_clicks"),
    State("chart-collapse", "is_open"),
    prevent_initial_call=True,
)
def toggle_chart(n_clicks, is_open):
    if is_open:
        return False, "▼ Daily Spending"
    return True, "▲ Hide Chart"
