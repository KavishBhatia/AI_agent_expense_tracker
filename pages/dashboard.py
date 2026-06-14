# pages/dashboard.py
from datetime import date, timedelta

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, callback, dcc, html

import charts

dash.register_page(__name__, path="/", name="Dashboard")

_PERIODS = {
    "this_month": "This Month",
    "last_month": "Last Month",
    "last_3_months": "Last 3 Months",
}


def _date_range(period: str) -> tuple[str, str]:
    today = date.today()
    if period == "this_month":
        start = today.replace(day=1)
        return start.isoformat(), today.isoformat()
    if period == "last_month":
        first_this = today.replace(day=1)
        last_prev = first_this - timedelta(days=1)
        start = last_prev.replace(day=1)
        return start.isoformat(), last_prev.isoformat()
    # last_3_months
    start = (today - timedelta(days=90)).replace(day=1)
    return start.isoformat(), today.isoformat()


layout = html.Div([
    dbc.Row([
        dbc.Col(
            dbc.Select(
                id="period-select",
                options=[{"label": v, "value": k} for k, v in _PERIODS.items()],
                value="this_month",
                style={"maxWidth": "200px"},
            ),
            width="auto",
        ),
    ], className="mb-4"),

    # KPI cards
    dbc.Row(id="kpi-cards", className="mb-4 g-3"),

    # Charts row 1
    dbc.Row([
        dbc.Col(dcc.Graph(id="chart-trend"), md=8),
        dbc.Col(dcc.Graph(id="chart-donut"), md=4),
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

    return (
        kpi_cards,
        charts.fig_monthly_trend(),
        charts.fig_category_donut(start, end),
        charts.fig_weekly_bar(start, end),
        charts.fig_top_merchants(start, end),
        charts.fig_sub_expense_breakdown(start, end),
        charts.fig_heatmap(start, end),
    )
