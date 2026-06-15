# pages/scan_receipt.py
import base64
from collections import Counter

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dash_table, dcc, html

from expense_tracker_agent.db import fetch_expenses, insert_expense, insert_expense_item
from expense_tracker_agent.receipt_scanner import parse_receipt
from expense_tracker_agent.tools import CATEGORIES

dash.register_page(__name__, path="/scan", name="Scan Receipt")

layout = html.Div([
    html.H5("Scan a Receipt", className="mb-3"),
    html.P(
        "Upload a photo of your receipt. Gemini will extract the items automatically.",
        className="text-muted mb-4",
    ),
    # Loading wraps the upload + parse-trigger so spinner shows during Gemini call
    dcc.Loading(
        [
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
            html.Div(id="receipt-parse-trigger", style={"display": "none"}),
        ],
        type="circle",
        color="#0f766e",
    ),
    dcc.Store(id="receipt-parsed-store"),   # original parsed data
    dcc.Store(id="receipt-edit-store"),     # tracks user edits to the form
    # Dynamic review form (table + editable fields rendered here)
    html.Div(id="receipt-review-section", className="mt-4"),
    # Static action buttons — shown/hidden via show_actions callback
    html.Div(
        id="receipt-actions",
        className="mt-3 d-flex gap-2",
        style={"display": "none"},
        children=[
            dbc.Button("Confirm & Save", id="receipt-confirm-btn", color="success", n_clicks=0),
            dbc.Button("Cancel", id="receipt-cancel-btn", color="secondary", outline=True, n_clicks=0),
        ],
    ),
    html.Div(id="receipt-save-result", className="mt-3"),
    html.Hr(className="mt-4"),
    html.H6("Recently saved receipts", className="mb-2 text-muted"),
    html.Div(id="receipt-recent-list"),
])


@callback(
    Output("receipt-parsed-store", "data"),
    Output("receipt-parse-trigger", "children"),
    Input("receipt-upload", "contents"),
    State("receipt-upload", "filename"),
    prevent_initial_call=True,
)
def process_receipt(contents, filename):
    """Parse receipt image with Gemini; write result to store."""
    if not contents:
        return dash.no_update, dash.no_update
    _, b64 = contents.split(",", 1)
    image_bytes = base64.b64decode(b64)
    mime = "image/png" if filename and filename.lower().endswith(".png") else "image/jpeg"
    receipt = parse_receipt(image_bytes, mime_type=mime)
    if receipt is None:
        return {"error": "Could not parse this receipt. Try a clearer photo."}, html.Div()
    return {
        "merchant": receipt.merchant,
        "date": receipt.date,
        "total": receipt.total,
        "items": [
            {"description": it.description, "amount": it.amount, "category": it.category}
            for it in receipt.items
        ],
    }, html.Div()


@callback(
    Output("receipt-review-section", "children"),
    Output("receipt-edit-store", "data"),          # initialise edit store from parsed data
    Input("receipt-parsed-store", "data"),
)
def render_review(store_data):
    """Sole owner of receipt-review-section. Also seeds the edit store."""
    if not store_data:
        return html.Div(), None
    if "error" in store_data:
        return dbc.Alert(store_data["error"], color="danger"), None

    items_table = dash_table.DataTable(
        id="receipt-items-table",
        data=store_data["items"],
        columns=[
            {"name": "Description", "id": "description", "editable": True},
            {"name": "Amount (€)", "id": "amount", "editable": True, "type": "numeric"},
            {"name": "Category", "id": "category", "editable": True, "presentation": "dropdown"},
        ],
        dropdown={
            "category": {
                "options": [{"label": c, "value": c} for c in CATEGORIES],
                "clearable": False,
            }
        },
        editable=True,
        row_deletable=True,
        style_cell={"fontSize": "13px", "padding": "6px"},
        style_table={"overflowX": "auto"},
        style_data_conditional=[
            {"if": {"state": "active"}, "backgroundColor": "#f0fdfa", "border": "1px solid #14b8a6"},
        ],
    )

    return (
        html.Div([
            dbc.Row([
                dbc.Col([html.Label("Store", className="small fw-semibold"),
                         dbc.Input(id="receipt-merchant", value=store_data["merchant"])], md=4),
                dbc.Col([html.Label("Date", className="small fw-semibold"),
                         dbc.Input(id="receipt-date", value=store_data["date"])], md=4),
                dbc.Col([html.Label("Total (€)", className="small fw-semibold"),
                         dbc.Input(id="receipt-total", value=str(store_data["total"]), type="number")], md=4),
            ], className="mb-3"),
            html.H6("Line items", className="mb-2"),
            html.P("Edit cells · pick category from dropdown · × to remove a row",
                   className="text-muted small mb-2"),
            items_table,
        ]),
        # Seed edit store with the parsed data
        {
            "merchant": store_data["merchant"],
            "date": store_data["date"],
            "total": store_data["total"],
            "items": store_data["items"],
        },
    )


@callback(
    Output("receipt-edit-store", "data", allow_duplicate=True),
    Input("receipt-items-table", "data"),
    Input("receipt-merchant", "value"),
    Input("receipt-date", "value"),
    Input("receipt-total", "value"),
    State("receipt-edit-store", "data"),
    prevent_initial_call=True,
)
def sync_edits(items, merchant, date, total, current_edit):
    """Keep edit store in sync with whatever the user changes in the form."""
    if current_edit is None:
        return dash.no_update
    return {
        **current_edit,
        "items": items if items is not None else current_edit.get("items", []),
        "merchant": merchant or current_edit.get("merchant", ""),
        "date": date or current_edit.get("date", ""),
        "total": total if total is not None else current_edit.get("total", 0),
    }


@callback(
    Output("receipt-actions", "style"),
    Input("receipt-parsed-store", "data"),
)
def show_actions(data):
    """Show static action buttons only when a parsed receipt is available."""
    if data and "error" not in data:
        return {}
    return {"display": "none"}


@callback(
    Output("receipt-save-result", "children"),
    Output("receipt-recent-list", "children"),
    Output("receipt-parsed-store", "data", allow_duplicate=True),
    Input("receipt-confirm-btn", "n_clicks"),
    State("receipt-edit-store", "data"),
    State("receipt-parsed-store", "data"),   # fallback if edit store not yet populated
    prevent_initial_call=True,
)
def save_receipt(n_clicks, edit_data, parsed_data):
    """Save using data from the edit store (no dynamic States needed)."""
    if not n_clicks:
        return dash.no_update, dash.no_update, dash.no_update

    data = edit_data or parsed_data
    if not data or "error" in data:
        return (
            dbc.Alert("No receipt data to save.", color="warning", dismissable=True),
            dash.no_update,
            dash.no_update,
        )

    try:
        merchant = (str(data.get("merchant") or "Unknown")).strip()
        date = (str(data.get("date") or "")).strip()
        total_val = float(data.get("total") or 0)
        items = data.get("items") or []

        item_cats = [str(item.get("category") or "Miscellaneous") for item in items]
        parent_category = Counter(item_cats).most_common(1)[0][0] if item_cats else "Miscellaneous"

        parent_id = insert_expense(
            amount=total_val,
            category=parent_category,
            description=f"Receipt: {merchant}",
            merchant=merchant,
            date=date,
            source="receipt_scan",
        )
        for item in items:
            insert_expense_item(
                parent_id=parent_id,
                amount=float(item.get("amount") or 0),
                description=str(item.get("description") or ""),
                category=str(item.get("category") or "Miscellaneous"),
            )

        recent = _recent_saves()
        return (
            dbc.Alert(
                f"Saved — #{parent_id} · {merchant} · €{total_val:.2f} · {len(items)} items · {date}",
                color="success", dismissable=True,
            ),
            recent,
            None,   # clear store → render_review hides form + show_actions hides buttons
        )
    except Exception as exc:
        return (
            dbc.Alert(f"Save failed: {exc}", color="danger", dismissable=True),
            dash.no_update,
            dash.no_update,
        )


@callback(
    Output("receipt-parsed-store", "data", allow_duplicate=True),
    Input("receipt-cancel-btn", "n_clicks"),
    prevent_initial_call=True,
)
def cancel_receipt(n_clicks):
    if not n_clicks:
        return dash.no_update
    return None


def _recent_saves():
    rows = [r for r in fetch_expenses() if r.get("source") == "receipt_scan"][-5:][::-1]
    if not rows:
        return html.P("No saved receipts yet.", className="text-muted small")

    def _fmt(iso):
        try:
            y, m, d = iso.split("-")
            return f"{d}/{m}/{y}"
        except Exception:
            return iso

    return dbc.Table(
        [
            html.Thead(html.Tr([html.Th("Date"), html.Th("Store"), html.Th("Amount"), html.Th("Items")])),
            html.Tbody([
                html.Tr([
                    html.Td(_fmt(r["date"]), className="text-muted small"),
                    html.Td(r.get("merchant") or "—"),
                    html.Td(f"€{r['amount']:.2f}", className="fw-semibold"),
                    html.Td(r["description"]),
                ])
                for r in rows
            ]),
        ],
        hover=True, responsive=True, size="sm",
    )
