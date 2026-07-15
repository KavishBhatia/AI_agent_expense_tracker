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
_KNOWN_NAME_COLS = {
    # generic
    "description", "details", "item", "name", "note", "notes", "what", "label", "title",
    # merchant / shop
    "merchant", "store", "shop", "supermarket", "supermarket name",
    # german
    "beschreibung", "bezeichnung", "markt", "laden", "zweck",
}


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
        html.Div(id="te-feedback"),
        html.Div(id="trip-csv-feedback"),
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
    name_col = next((cols_lower[k] for k in _KNOWN_NAME_COLS if k in cols_lower), None)

    if not date_col or not cost_col:
        return dbc.Alert(
            f"Could not detect date or amount columns. Found: {list(df.columns)}",
            color="warning",
        ), dash.no_update, dash.no_update

    items = []
    for _, row in df.iterrows():
        try:
            amount = float(str(row[cost_col]).replace(",", "."))
            if pd.isna(amount):
                raise ValueError("Missing amount")
            merchant = str(row[name_col]).strip() if name_col else None
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
        categorised = ["Miscellaneous"] * len(items)

    for item, category in zip(items, categorised):
        insert_trip_expense(
            trip_id=trip_id,
            amount=item["amount"],
            merchant=item["merchant"],
            category=category,
            description=None,
            date=item["date"],
        )

    content, new_tid = render_trip(search)
    return dbc.Alert(f"Imported {len(items)} expenses.", color="success", dismissable=True), content, new_tid
