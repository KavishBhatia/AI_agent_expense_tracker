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
            dbc.NavbarBrand("ExpenseAI", href="/", className="fw-bold"),
            dbc.Nav(
                [
                    dbc.NavLink("Dashboard", href="/", active="exact"),
                    dbc.NavLink("Add Expense", href="/add", active="exact"),
                    dbc.NavLink("Import CSV", href="/import", active="exact"),
                    dbc.NavLink("Scan Receipt", href="/scan", active="exact"),
                ],
                navbar=True,
                className="ms-auto",
            ),
        ],
        fluid=True,
    ),
    color="white",
    className="border-bottom mb-4 shadow-sm",
)

app.layout = html.Div(
    [
        navbar,
        dbc.Container(dash.page_container, fluid=False, className="pb-5"),
    ]
)

if __name__ == "__main__":
    app.run(debug=True, port=8050)
