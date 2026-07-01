from datetime import datetime

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, dcc, html

from expense_tracker_agent.db import get_all_budgets, set_budget
from expense_tracker_agent.tools import CATEGORIES

dash.register_page(__name__, path="/budgets", name="Budgets")

_CARD_STYLE = {"borderTop": "3px solid #14b8a6", "borderRadius": "8px"}
_SLIDER_MARKS = {0: "€0", 500: "€500", 1000: "€1000", 1500: "€1500", 2000: "€2000"}


def layout():
    budgets = get_all_budgets()
    rows = []
    for i in range(0, len(CATEGORIES), 2):
        cols = []
        for cat in CATEGORIES[i : i + 2]:
            cols.append(dbc.Col([
                html.Label(cat, className="small fw-semibold mb-1"),
                dcc.Slider(
                    id={"type": "budget-slider", "index": cat},
                    min=0,
                    max=2000,
                    step=50,
                    value=budgets.get(cat, 0),
                    marks=_SLIDER_MARKS,
                    tooltip={"placement": "top", "always_visible": True},
                    className="mb-2",
                ),
                html.Small("Drag to 0 to remove limit", className="text-muted"),
            ], md=6, className="mb-4"))
        rows.append(dbc.Row(cols))

    return html.Div([
        html.H5("Monthly Budgets", className="mb-1"),
        html.P(
            "Set a monthly spending limit per category. Slide to 0 to remove the limit.",
            className="text-muted mb-4",
        ),
        dbc.Card(dbc.CardBody([
            *rows,
            dbc.Row(dbc.Col(
                dbc.Button("Save Budgets", id="budget-save-btn", color="primary", n_clicks=0),
                className="mt-2",
            )),
            html.Div(id="budget-save-feedback", className="mt-3"),
        ]), style=_CARD_STYLE),
    ])


@callback(
    Output("budget-save-feedback", "children"),
    Output("budget-updated-store", "data"),
    Input("budget-save-btn", "n_clicks"),
    State({"type": "budget-slider", "index": ALL}, "value"),
    State({"type": "budget-slider", "index": ALL}, "id"),
    prevent_initial_call=True,
)
def save_budgets(n_clicks, values, ids):
    for val, id_dict in zip(values, ids):
        cat = id_dict["index"]
        limit = float(val) if val and val > 0 else None
        set_budget(cat, limit)
    return (
        dbc.Alert("Budgets saved.", color="success", duration=3000, dismissable=True),
        {"saved_at": datetime.now().isoformat()},
    )
