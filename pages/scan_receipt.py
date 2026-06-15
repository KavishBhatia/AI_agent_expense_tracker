# pages/scan_receipt.py
import base64

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dash_table, dcc, html

from expense_tracker_agent.db import insert_expense, insert_expense_item
from expense_tracker_agent.receipt_scanner import parse_receipt

dash.register_page(__name__, path="/scan", name="Scan Receipt")

layout = html.Div([
    html.H5("Scan a Receipt", className="mb-3"),
    html.P(
        "Upload a photo of your receipt. Gemini will extract the items automatically.",
        className="text-muted mb-4",
    ),
    dcc.Upload(
        id="receipt-upload",
        children=html.Div(["Drag & drop or ", html.A("browse"), " (JPG / PNG)"]),
        style={
            "width": "100%", "height": "80px", "lineHeight": "80px",
            "borderWidth": "1px", "borderStyle": "dashed",
            "borderRadius": "8px", "textAlign": "center", "color": "#6c757d",
        },
        accept="image/*",
    ),
    dcc.Store(id="receipt-parsed-store"),
    html.Div(id="receipt-review-section", className="mt-4"),
    html.Div(id="receipt-save-result", className="mt-3"),
])


@callback(
    Output("receipt-review-section", "children"),
    Output("receipt-parsed-store", "data"),
    Input("receipt-upload", "contents"),
    State("receipt-upload", "filename"),
    prevent_initial_call=True,
)
def process_receipt(contents, filename):
    if not contents:
        return dash.no_update, dash.no_update

    header, b64 = contents.split(",", 1)
    image_bytes = base64.b64decode(b64)
    mime = "image/png" if filename and filename.lower().endswith(".png") else "image/jpeg"

    receipt = parse_receipt(image_bytes, mime_type=mime)
    if receipt is None:
        return dbc.Alert("Could not parse this receipt. Try a clearer photo.", color="danger"), None

    store_data = {
        "merchant": receipt.merchant,
        "date": receipt.date,
        "total": receipt.total,
        "items": [{"description": it.description, "amount": it.amount, "category": it.category}
                  for it in receipt.items],
    }

    items_table = dash_table.DataTable(
        id="receipt-items-table",
        data=store_data["items"],
        columns=[
            {"name": "Description", "id": "description", "editable": True},
            {"name": "Amount (€)", "id": "amount", "editable": True, "type": "numeric"},
            {"name": "Category", "id": "category", "editable": True,
             "presentation": "dropdown"},
        ],
        editable=True,
        style_cell={"fontSize": "13px", "padding": "6px"},
        style_table={"overflowX": "auto"},
    )

    review = html.Div([
        dbc.Row([
            dbc.Col([html.Label("Store"), dbc.Input(id="receipt-merchant", value=receipt.merchant)], md=4),
            dbc.Col([html.Label("Date"), dbc.Input(id="receipt-date", value=receipt.date)], md=4),
            dbc.Col([html.Label("Total (€)"), dbc.Input(id="receipt-total", value=str(receipt.total), type="number")], md=4),
        ], className="mb-3"),
        html.H6("Line items (editable)"),
        items_table,
        html.Div(className="mt-3 d-flex gap-2", children=[
            dbc.Button("Confirm & Save", id="receipt-confirm-btn", color="success", n_clicks=0),
            dbc.Button("Cancel", id="receipt-cancel-btn", color="secondary", outline=True, n_clicks=0),
        ]),
    ])

    return review, store_data


@callback(
    Output("receipt-save-result", "children"),
    Output("receipt-review-section", "children", allow_duplicate=True),
    Input("receipt-confirm-btn", "n_clicks"),
    State("receipt-merchant", "value"),
    State("receipt-date", "value"),
    State("receipt-total", "value"),
    State("receipt-items-table", "data"),
    prevent_initial_call=True,
)
def save_receipt(n_clicks, merchant, date, total, items):
    if not n_clicks:
        return dash.no_update, dash.no_update

    from collections import Counter
    item_cats = [item.get("category", "Miscellaneous") for item in (items or [])]
    parent_category = Counter(item_cats).most_common(1)[0][0] if item_cats else "Miscellaneous"

    parent_id = insert_expense(
        amount=float(total or 0),
        category=parent_category,
        description=f"Receipt: {merchant}",
        merchant=merchant,
        date=date,
        source="receipt_scan",
    )
    for item in (items or []):
        insert_expense_item(
            parent_id=parent_id,
            amount=float(item.get("amount", 0)),
            description=item.get("description", ""),
            category=item.get("category", "Other"),
        )

    return (
        dbc.Alert(
            f"Saved! Expense #{parent_id} ({merchant}, €{total}) with {len(items or [])} items.",
            color="success",
        ),
        html.Div(),
    )


@callback(
    Output("receipt-review-section", "children", allow_duplicate=True),
    Output("receipt-parsed-store", "data", allow_duplicate=True),
    Input("receipt-cancel-btn", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_receipt(n_clicks):
    if not n_clicks:
        return dash.no_update, dash.no_update
    return html.Div(), None
