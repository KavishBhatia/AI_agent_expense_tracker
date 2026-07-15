# app.py
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html

from expense_tracker_agent.db import init_db, migrate_from_csv
from expense_tracker_agent.trip_db import init_trip_db

init_db()
migrate_from_csv(Path("expenses.csv"))
init_trip_db()

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
)

_TOAST_HIDDEN = {"position": "fixed", "bottom": "20px", "right": "20px",
                 "zIndex": 9999, "display": "none"}

navbar = dbc.Navbar(
    dbc.Container(
        [
            dbc.NavbarBrand("ExpenseAI", href="/", style={"color": "#ffffff", "fontWeight": "700", "fontSize": "18px"}),
            dbc.NavbarToggler(id="navbar-toggler"),
            dbc.Collapse(
                dbc.Nav(
                    [
                        dbc.NavLink("Dashboard",   href="/",        active="exact",
                                    style={"color": "#ccfbf1", "fontWeight": "500"}),
                        dbc.NavLink("Add Expense", href="/add",     active="exact",
                                    style={"color": "#ccfbf1", "fontWeight": "500"}),
                        dbc.NavLink("History",     href="/history", active="exact",
                                    style={"color": "#ccfbf1", "fontWeight": "500"}),
                        dbc.Button(
                            [
                                html.Span("☰"),
                                html.Span("Open tools drawer", className="visually-hidden"),
                            ],
                            id="tools-drawer-btn",
                            color="link",
                            title="Tools",
                            style={"color": "#ccfbf1", "fontSize": "1.2rem", "padding": "6px 10px"},
                            n_clicks=0,
                        ),
                    ],
                    navbar=True,
                    className="ms-auto gap-2",
                ),
                id="navbar-collapse",
                navbar=True,
            ),
        ],
        fluid=True,
    ),
    style={"backgroundColor": "#0f766e", "boxShadow": "0 2px 8px rgba(0,0,0,0.15)"},
    className="mb-4 px-3",
)

app.layout = html.Div(
    [
        # Global stores — available to callbacks on any page
        dcc.Store(id="expense-deleted-store"),
        dcc.Store(id="last-deleted-store"),
        dcc.Store(id="budget-updated-store"),
        # Undo toast — always in DOM regardless of active page
        html.Div(
            id="undo-toast-container",
            style=_TOAST_HIDDEN,
            children=dbc.Alert(
                [
                    html.Span(id="undo-toast-text", className="me-3 small"),
                    dbc.Button("Undo", id="undo-expense-btn", size="sm", n_clicks=0,
                               style={"backgroundColor": "#0d9488", "borderColor": "#0d9488",
                                      "color": "#fff"}),
                ],
                color="dark",
                className="d-flex align-items-center mb-0 py-2 shadow",
            ),
        ),
        navbar,
        dbc.Offcanvas(
            dbc.Nav(
                [
                    dbc.NavLink("Trips", href="/trips", active="exact", className="mb-2",
                                style={"fontWeight": "500"}),
                    dbc.NavLink("Set Budgets",  href="/budgets", active="exact", className="mb-2",
                                style={"fontWeight": "500"}),
                    dbc.NavLink("Import CSV",   href="/import",  active="exact", className="mb-2",
                                style={"fontWeight": "500"}),
                    dbc.NavLink("Scan Receipt", href="/scan",    active="exact", className="mb-2",
                                style={"fontWeight": "500"}),
                    dbc.NavLink("Backup",       href="/backup",  active="exact",
                                style={"fontWeight": "500"}),
                ],
                vertical=True,
            ),
            id="tools-offcanvas",
            title="Tools",
            placement="end",
            is_open=False,
        ),
        dbc.Container(dash.page_container, fluid=False, className="pb-5"),
    ]
)


@callback(
    Output("tools-offcanvas", "is_open"),
    Input("tools-drawer-btn", "n_clicks"),
    Input("_pages_location", "pathname"),
    State("tools-offcanvas", "is_open"),
    prevent_initial_call=True,
)
def toggle_tools_drawer(_n, _pathname, is_open):
    ctx = dash.callback_context
    if ctx.triggered_id == "_pages_location":
        return False
    return not is_open

server = app.server

if __name__ == "__main__":
    app.run(debug=True, port=8050)
