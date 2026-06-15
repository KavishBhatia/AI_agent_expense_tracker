# app.py
from pathlib import Path

import dash
import dash_bootstrap_components as dbc
from dash import html

from expense_tracker_agent.db import init_db, migrate_from_csv

# Ensure DB is ready and migrate any existing CSV data
init_db()
migrate_from_csv(Path("expenses.csv"))

app = dash.Dash(
    __name__,
    use_pages=True,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    suppress_callback_exceptions=True,
)

navbar = dbc.Navbar(
    dbc.Container(
        [
            dbc.NavbarBrand("ExpenseAI", href="/", style={"color": "#ffffff", "fontWeight": "700", "fontSize": "18px"}),
            dbc.NavbarToggler(id="navbar-toggler"),
            dbc.Collapse(
                dbc.Nav(
                    [
                        dbc.NavLink("Dashboard", href="/", active="exact",
                                    style={"color": "#ccfbf1", "fontWeight": "500"}),
                        dbc.NavLink("Add Expense", href="/add", active="exact",
                                    style={"color": "#ccfbf1", "fontWeight": "500"}),
                        dbc.NavLink("Import CSV", href="/import", active="exact",
                                    style={"color": "#ccfbf1", "fontWeight": "500"}),
                        dbc.NavLink("Scan Receipt", href="/scan", active="exact",
                                    style={"color": "#ccfbf1", "fontWeight": "500"}),
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
        navbar,
        dbc.Container(dash.page_container, fluid=False, className="pb-5"),
    ]
)

if __name__ == "__main__":
    app.run(debug=True, port=8050)
