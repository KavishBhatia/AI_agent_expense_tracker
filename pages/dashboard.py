# pages/dashboard.py
from datetime import date, timedelta

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, dcc, html

from expense_tracker_agent import charts
from expense_tracker_agent.db import delete_expense, fetch_expenses, restore_expense


def _fmt(iso: str) -> str:
    """Convert YYYY-MM-DD → DD/MM/YYYY for display."""
    try:
        y, m, d = iso.split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return iso

dash.register_page(__name__, path="/", name="Dashboard")

_PERIODS = {
    "last_14_days": "Last 14 Days",
    "this_month": "This Month",
    "last_month": "Last Month",
    "last_3_months": "Last 3 Months",
    "all_time": "All Time",
}


def _date_range(period: str) -> tuple:
    today = date.today()
    if period == "last_14_days":
        return (today - timedelta(days=13)).isoformat(), today.isoformat()
    if period == "this_month":
        return today.replace(day=1).isoformat(), today.isoformat()
    if period == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        return last_prev.replace(day=1).isoformat(), last_prev.isoformat()
    if period == "last_3_months":
        return (today - timedelta(days=90)).replace(day=1).isoformat(), today.isoformat()
    return None, None  # all_time


_TOAST_HIDDEN = {"position": "fixed", "bottom": "20px", "right": "20px",
                 "zIndex": 9999, "display": "none"}
_TOAST_VISIBLE = {**_TOAST_HIDDEN, "display": "block"}

# Note: expense-deleted-store, last-deleted-store, and undo-toast-container
# are defined in app.py so they persist across page navigation.

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

    # Link to History page
    dbc.Row([
        dbc.Col(
            dbc.Button("→ View History", href="/history", color="link", size="sm",
                       className="ps-0 text-muted", style={"fontSize": "13px"}),
        ),
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


@callback(
    Output("day-drilldown", "children"),
    Input("chart-trend", "clickData"),
    prevent_initial_call=True,
)
def show_day_detail(click_data):
    if not click_data:
        return dash.no_update
    raw = click_data["points"][0]["x"]          # DD/MM/YYYY from chart
    try:
        import pandas as _pd
        db_date = _pd.to_datetime(raw, dayfirst=True).strftime("%Y-%m-%d")
    except Exception:
        db_date = raw
    display_date = _fmt(db_date)
    rows = fetch_expenses(start_date=db_date, end_date=db_date)
    if not rows:
        return dbc.Alert(f"No transactions found for {display_date}.", color="info", dismissable=True)
    total = sum(r["amount"] for r in rows)
    table_rows = [
        html.Tr([
            html.Td(r.get("merchant") or "—"),
            html.Td(html.Span(r["category"], className="small", style={"backgroundColor": "#14b8a6", "color": "#fff", "borderRadius": "4px", "padding": "2px 7px"})),
            html.Td(f"€{r['amount']:.2f}", className="fw-semibold text-end"),
            html.Td(r["description"], className="text-muted small"),
        ])
        for r in rows
    ]
    return dbc.Card(dbc.CardBody([
        html.Div([
            html.Span(f"Breakdown for {display_date}", className="fw-semibold"),
            html.Span(f"  {len(rows)} transactions · €{total:.2f} total",
                      className="text-muted small ms-2"),
        ], className="mb-2"),
        dbc.Table(
            [
                html.Thead(html.Tr([
                    html.Th("Store"), html.Th("Category"),
                    html.Th("Amount", className="text-end"), html.Th("Description"),
                ])),
                html.Tbody(table_rows),
                html.Tfoot(html.Tr([
                    html.Th("Total", colSpan=2, className="text-muted"),
                    html.Th(f"€{total:.2f}", className="text-end"),
                    html.Th(""),
                ])),
            ],
            hover=True, responsive=True, size="sm", className="mb-0",
        ),
    ]), style={"borderLeft": "3px solid #14b8a6", "borderRadius": "8px"})


@callback(
    Output("expense-deleted-store", "data"),
    Output("last-deleted-store", "data"),
    Output("undo-toast-container", "style"),
    Output("undo-toast-text", "children"),
    Input({"type": "del-expense", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_delete(n_clicks_list):
    import json
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update
    for trigger in ctx.triggered:
        if trigger["value"]:
            expense_id = json.loads(trigger["prop_id"].split(".")[0])["index"]
            # Fetch the row before soft-deleting so we can show it in the toast
            rows = fetch_expenses()
            row = next((r for r in rows if r["id"] == expense_id), None)
            delete_expense(expense_id)
            label = f"{row['merchant'] or row['description']} €{row['amount']:.2f}" if row else f"#{expense_id}"
            return (
                {"action": "delete", "id": expense_id},
                {"id": expense_id, "label": label},
                _TOAST_VISIBLE,
                f"Deleted: {label}",
            )
    return dash.no_update, dash.no_update, dash.no_update, dash.no_update


@callback(
    Output("expense-deleted-store", "data", allow_duplicate=True),
    Output("last-deleted-store", "data", allow_duplicate=True),
    Output("undo-toast-container", "style", allow_duplicate=True),
    Input("undo-expense-btn", "n_clicks"),
    State("last-deleted-store", "data"),
    prevent_initial_call=True,
)
def handle_restore(n_clicks, last_deleted):
    if not n_clicks or not last_deleted:
        return dash.no_update, dash.no_update, dash.no_update
    restore_expense(last_deleted["id"])
    return {"action": "restore", "id": last_deleted["id"]}, None, _TOAST_HIDDEN
