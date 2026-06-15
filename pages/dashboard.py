# pages/dashboard.py
from datetime import date, timedelta

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html

from expense_tracker_agent import charts
from expense_tracker_agent.db import fetch_expenses


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


def _recent_table(rows, limit: int = 6):
    if not rows:
        return html.P("No transactions yet.", className="text-muted small")
    recent = rows[-limit:][::-1]
    table_rows = [
        html.Tr([
            html.Td(_fmt(r["date"]), className="text-muted small"),
            html.Td(r.get("merchant") or "—"),
            html.Td(dbc.Badge(r["category"], color="secondary", className="small")),
            html.Td(f"€{r['amount']:.2f}", className="fw-semibold text-end"),
            html.Td(r["description"], className="text-muted small"),
        ])
        for r in recent
    ]
    return dbc.Table(
        [
            html.Thead(html.Tr([
                html.Th("Date"), html.Th("Store"), html.Th("Category"),
                html.Th("Amount", className="text-end"), html.Th("Description"),
            ])),
            html.Tbody(table_rows),
        ],
        hover=True, responsive=True, size="sm", className="mb-0",
    )


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


@callback(
    Output("kpi-cards", "children"),
    Output("recent-transactions", "children"),
    Output("chart-trend", "figure"),
    Output("chart-donut", "figure"),
    Output("chart-weekly", "figure"),
    Output("chart-merchants", "figure"),
    Output("chart-sub-breakdown", "figure"),
    Output("chart-heatmap", "figure"),
    Input("period-select", "value"),
)
def update_dashboard(period: str):
    start, end = _date_range(period)
    stats = charts.kpi_stats(start, end)

    kpi_cards = [
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("Total Spent", className="text-muted small mb-1"),
            html.H3(f"€{stats['total']:.2f}", className="mb-0"),
        ])), md=4),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("Transactions", className="text-muted small mb-1"),
            html.H3(str(stats["count"]), className="mb-0"),
        ])), md=4),
        dbc.Col(dbc.Card(dbc.CardBody([
            html.P("Avg / Day", className="text-muted small mb-1"),
            html.H3(f"€{stats['avg_per_day']:.2f}", className="mb-0"),
        ])), md=4),
    ]

    def _safe(fn, *args):
        try:
            return fn(*args)
        except Exception as exc:
            import plotly.graph_objects as go
            return go.Figure().add_annotation(text=f"Chart error: {exc}", showarrow=False)

    rows = fetch_expenses(start, end)
    recent = _recent_table(rows, limit=6)

    return (
        kpi_cards,
        recent,
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
            html.Td(dbc.Badge(r["category"], color="secondary", className="small")),
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
    ]), className="border-primary border-start border-3 ps-0")
