# pages/import_csv.py
import base64
import io

import dash
import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, State, callback, dash_table, dcc, html

from expense_tracker_agent.tools import import_csv_row

dash.register_page(__name__, path="/import", name="Import CSV")

_KNOWN_DATE_COLS = {"date", "datum", "day"}
_KNOWN_COST_COLS = {"cost", "amount", "price", "kosten", "betrag", "preis"}
_KNOWN_MERCHANT_COLS = {"supermarket name", "supermarket", "merchant", "store",
                        "shop", "markt", "laden"}

layout = html.Div([
    html.H5("Import CSV", className="mb-3"),
    html.P(
        "Upload a CSV with columns for date, cost, and supermarket name. "
        "Column names are detected automatically. Categories are assigned by Gemini AI.",
        className="text-muted mb-4",
    ),
    dcc.Upload(
        id="csv-upload",
        children=html.Div([
            "Drag & drop or ", html.A("browse"),
        ]),
        style={
            "width": "100%", "height": "80px", "lineHeight": "80px",
            "borderWidth": "1px", "borderStyle": "dashed",
            "borderRadius": "8px", "textAlign": "center",
            "color": "#6c757d",
        },
        accept=".csv",
    ),
    dcc.Loading(html.Div(id="csv-preview-section", className="mt-4")),
    dcc.Loading(html.Div(id="csv-import-result", className="mt-3")),
    html.Hr(className="mt-5"),
    html.H6("Re-categorise Existing Expenses", className="mb-1"),
    html.P(
        "Run Gemini AI over all expenses already in the database and update their categories.",
        className="text-muted small mb-3",
    ),
    dbc.Button("Re-categorise All with AI", id="recategorise-btn", color="secondary", outline=True),
    dcc.Loading(html.Div(id="recategorise-result", className="mt-3")),
])


def _detect_columns(columns: list[str]) -> dict:
    mapping = {}
    lower = {c.lower(): c for c in columns}
    for key in lower:
        if key in _KNOWN_DATE_COLS:
            mapping["date"] = lower[key]
        elif key in _KNOWN_COST_COLS:
            mapping["cost"] = lower[key]
        elif key in _KNOWN_MERCHANT_COLS:
            mapping["merchant"] = lower[key]
    return mapping


@callback(
    Output("csv-preview-section", "children"),
    Input("csv-upload", "contents"),
    State("csv-upload", "filename"),
    prevent_initial_call=True,
)
def show_preview(contents, filename):
    if contents is None:
        return dash.no_update
    _, b64 = contents.split(",", 1)
    decoded = base64.b64decode(b64).decode("utf-8")
    try:
        df = pd.read_csv(io.StringIO(decoded), dtype=str)
    except Exception as e:
        return dbc.Alert(f"Could not parse CSV: {e}", color="danger")

    mapping = _detect_columns(list(df.columns))

    col_selectors = []
    for role in ("date", "cost", "merchant"):
        col_selectors.append(
            dbc.Col([
                html.Label(role.capitalize(), className="small fw-semibold"),
                dbc.Select(
                    id=f"col-{role}",
                    options=[{"label": c, "value": c} for c in df.columns],
                    value=mapping.get(role),
                ),
            ], md=4)
        )

    preview_table = dash_table.DataTable(
        data=df.head(10).to_dict("records"),
        columns=[{"name": c, "id": c} for c in df.columns],
        style_table={"overflowX": "auto"},
        style_cell={"fontSize": "13px", "padding": "6px"},
        page_size=10,
    )

    return html.Div([
        html.H6(f"Preview: {filename}", className="mb-2"),
        preview_table,
        html.Hr(),
        html.P("Map columns (auto-detected, adjust if needed):", className="mb-2 fw-semibold"),
        dbc.Row(col_selectors, className="mb-3"),
        dbc.Button(
            f"Import {len(df)} rows",
            id="import-confirm-btn",
            color="primary",
            n_clicks=0,
        ),
        dcc.Store(id="csv-data-store", data=df.to_json(orient="records")),
    ])


@callback(
    Output("csv-import-result", "children"),
    Input("import-confirm-btn", "n_clicks"),
    State("csv-data-store", "data"),
    State("col-date", "value"),
    State("col-cost", "value"),
    State("col-merchant", "value"),
    prevent_initial_call=True,
)
def run_import(n_clicks, json_data, date_col, cost_col, merchant_col):
    if not n_clicks or not json_data:
        return dash.no_update
    if not all([date_col, cost_col]):
        return dbc.Alert("Please map at least Date and Cost columns before importing.", color="warning")

    from expense_tracker_agent.categoriser import classify_expenses

    df = pd.read_json(io.StringIO(json_data), orient="records", convert_dates=False, dtype=str)

    # Batch-classify all rows with Gemini before inserting
    classify_items = [
        {
            "description": str(row[merchant_col]).strip() if merchant_col else "",
            "merchant": str(row[merchant_col]).strip() if merchant_col else "",
        }
        for _, row in df.iterrows()
    ]
    categories = classify_expenses(classify_items)

    imported, skipped = 0, 0
    failed_rows = []
    for idx, (i, row) in enumerate(df.iterrows()):
        try:
            merchant = str(row[merchant_col]).strip() if merchant_col else ""
            raw_date = str(row[date_col]).strip()
            normalized_date = pd.to_datetime(raw_date, dayfirst=True).strftime("%Y-%m-%d")
            result = import_csv_row(
                date=normalized_date,
                amount=float(str(row[cost_col]).replace(",", ".")),
                merchant=merchant,
                category=categories[idx],
            )
            if "skipped" in result.lower():
                skipped += 1
            else:
                imported += 1
        except Exception as exc:
            failed_rows.append({
                "row": i + 1,
                date_col: row.get(date_col, "?"),
                cost_col: row.get(cost_col, "?"),
                **({"merchant": row.get(merchant_col, "?")} if merchant_col else {}),
                "error": str(exc),
            })

    alerts = []
    if imported > 0:
        alerts.append(dbc.Alert(
            f"{imported} row{'s' if imported != 1 else ''} imported successfully.",
            color="success", dismissable=True, className="mb-2",
        ))
    if skipped > 0:
        alerts.append(dbc.Alert(
            f"{skipped} duplicate{'s' if skipped != 1 else ''} skipped — "
            "same date, amount, and merchant already exists in the database.",
            color="warning", dismissable=True, className="mb-2",
        ))
    if failed_rows:
        n = len(failed_rows)
        failed_table = dbc.Table(
            [
                html.Thead(html.Tr(
                    [html.Th("CSV Row"), html.Th(date_col), html.Th(cost_col)]
                    + ([html.Th("Merchant")] if merchant_col else [])
                    + [html.Th("Error")]
                )),
                html.Tbody([
                    html.Tr(
                        [html.Td(r["row"]), html.Td(str(r[date_col])), html.Td(str(r[cost_col]))]
                        + ([html.Td(str(r.get("merchant", "")))] if merchant_col else [])
                        + [html.Td(r["error"], className="text-danger small")]
                    )
                    for r in failed_rows
                ]),
            ],
            bordered=True, size="sm", responsive=True, className="mb-0 mt-2",
        )
        alerts.append(dbc.Alert(
            [
                html.Strong(f"{n} row{'s' if n != 1 else ''} failed to import:"),
                failed_table,
            ],
            color="danger", dismissable=True, className="mb-2",
        ))
    if not alerts:
        alerts.append(dbc.Alert("Nothing was imported.", color="info", dismissable=True))
    return html.Div(alerts)


@callback(
    Output("recategorise-result", "children"),
    Input("recategorise-btn", "n_clicks"),
    prevent_initial_call=True,
)
def recategorise_all(n_clicks):
    if not n_clicks:
        return dash.no_update
    from expense_tracker_agent.categoriser import classify_expenses
    from expense_tracker_agent.db import (
        fetch_expense_items_by_parent_ids,
        fetch_expenses,
        update_expense_category,
    )

    rows = fetch_expenses()
    if not rows:
        return dbc.Alert("No expenses in the database yet.", color="info", dismissable=True)

    items_by_parent_id = fetch_expense_items_by_parent_ids([r["id"] for r in rows])
    items = []
    for r in rows:
        sub_items = items_by_parent_id.get(r["id"], [])
        sub_desc = ", ".join((i.get("description") or "").strip() for i in sub_items if (i.get("description") or "").strip())
        base_desc = (r.get("description") or "").strip()
        full_desc = "; ".join([p for p in (base_desc, sub_desc) if p])
        items.append({"description": full_desc, "merchant": r.get("merchant") or ""})
    categories = classify_expenses(items)

    for row, cat in zip(rows, categories):
        update_expense_category(row["id"], cat)

    return dbc.Alert(
        f"Done — re-categorised {len(rows)} expense{'s' if len(rows) != 1 else ''} with AI.",
        color="success", dismissable=True,
    )
