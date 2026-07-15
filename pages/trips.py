# pages/trips.py
import json

import dash
import dash_bootstrap_components as dbc
from dash import ALL, Input, Output, State, callback, dcc, html

from expense_tracker_agent.trip_db import create_trip, delete_trip, fetch_trips

dash.register_page(__name__, path="/trips", name="Trips")


def _fmt_range(start, end):
    if not start:
        return "No expenses yet"
    if start == end:
        return start
    return f"{start}  →  {end}"


def _trip_card(trip: dict):
    date_range = _fmt_range(trip["start_date"], trip["end_date"])
    return dbc.Card(
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.H6(trip["name"], className="mb-1 fw-semibold"),
                    html.Small(date_range, className="text-muted"),
                ], md=7),
                dbc.Col([
                    html.Div(f"€{trip['total']:.2f}", className="fw-semibold text-end"),
                    html.Small(f"{trip['count']} expense{'s' if trip['count'] != 1 else ''}",
                               className="text-muted d-block text-end"),
                ], md=3),
                dbc.Col([
                    dbc.Button("Open", id={"type": "open-trip-btn", "index": trip["id"]},
                               color="outline-primary", size="sm", className="me-1"),
                    dbc.Button("✕", id={"type": "del-trip-btn", "index": trip["id"]},
                               color="outline-danger", size="sm"),
                ], md=2, className="d-flex align-items-center justify-content-end"),
            ], align="center"),
        ]),
        className="mb-3",
        style={"borderLeft": "3px solid #0d9488", "borderRadius": "8px"},
    )


layout = html.Div([
    dcc.Location(id="trips-location", refresh=True),
    dbc.Row([
        dbc.Col(html.H4("Trips", className="mb-0"), width="auto"),
        dbc.Col(
            dbc.Button("+ New Trip", id="new-trip-btn", color="primary", size="sm", n_clicks=0),
            width="auto", className="ms-auto",
        ),
    ], align="center", className="mb-4"),

    html.Div(id="trips-list"),

    dbc.Modal([
        dbc.ModalHeader(dbc.ModalTitle("New Trip")),
        dbc.ModalBody([
            dbc.Label("Trip name"),
            dbc.Input(id="new-trip-name", placeholder='e.g. "Barcelona May 2026"', type="text"),
            html.Div(id="new-trip-name-error", className="text-danger small mt-1"),
        ]),
        dbc.ModalFooter([
            dbc.Button("Cancel", id="new-trip-cancel", color="secondary", n_clicks=0),
            dbc.Button("Create", id="new-trip-create", color="primary", n_clicks=0),
        ]),
    ], id="new-trip-modal", is_open=False),
])


@callback(
    Output("trips-list", "children"),
    Input("trips-location", "pathname"),
)
def refresh_trips(_):
    trips = fetch_trips()
    if not trips:
        return html.P("No trips yet. Create one with '+ New Trip'.", className="text-muted")
    return [_trip_card(t) for t in trips]


@callback(
    Output("new-trip-modal", "is_open"),
    Output("new-trip-name", "value"),
    Output("new-trip-name-error", "children", allow_duplicate=True),
    Input("new-trip-btn", "n_clicks"),
    Input("new-trip-cancel", "n_clicks"),
    State("new-trip-modal", "is_open"),
    prevent_initial_call=True,
)
def toggle_modal(open_clicks, cancel_clicks, is_open):
    ctx = dash.callback_context
    if not ctx.triggered:
        return is_open, dash.no_update, dash.no_update
    if ctx.triggered_id == "new-trip-btn":
        return True, "", ""
    return False, "", ""

@callback(
    Output("new-trip-modal", "is_open", allow_duplicate=True),
    Output("new-trip-name-error", "children", allow_duplicate=True),
    Input("new-trip-create", "n_clicks"),
    State("new-trip-name", "value"),
    prevent_initial_call=True,
)
def validate_and_close(n_clicks, name):
    if not name or not name.strip():
        return True, "Trip name cannot be empty."
    return False, ""


@callback(
    Output("trips-location", "href"),
    Input("new-trip-create", "n_clicks"),
    State("new-trip-name", "value"),
    prevent_initial_call=True,
)
def create_and_redirect(n_clicks, name):
    if not n_clicks or not name or not name.strip():
        return dash.no_update
    tid = create_trip(name.strip())
    return f"/trip?id={tid}"


@callback(
    Output("trips-list", "children", allow_duplicate=True),
    Input({"type": "del-trip-btn", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_delete(n_clicks_list):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    for trigger in ctx.triggered:
        if trigger["value"]:
            tid = json.loads(trigger["prop_id"].split(".")[0])["index"]
            delete_trip(tid)
            break
    trips = fetch_trips()
    if not trips:
        return html.P("No trips yet. Create one with '+ New Trip'.", className="text-muted")
    return [_trip_card(t) for t in trips]


@callback(
    Output("trips-location", "href", allow_duplicate=True),
    Input({"type": "open-trip-btn", "index": ALL}, "n_clicks"),
    prevent_initial_call=True,
)
def handle_open(n_clicks_list):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update
    for trigger in ctx.triggered:
        if trigger["value"]:
            tid = json.loads(trigger["prop_id"].split(".")[0])["index"]
            return f"/trip?id={tid}"
    return dash.no_update
