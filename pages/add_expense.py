# pages/add_expense.py
import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html

import agent_bridge
from expense_tracker_agent.db import fetch_expenses

dash.register_page(__name__, path="/add", name="Add Expense")

layout = dbc.Row([
    # Left: chat panel
    dbc.Col([
        html.H5("Chat with your expense agent", className="mb-3"),
        html.Div(id="chat-history", style={
            "height": "420px", "overflowY": "auto",
            "border": "1px solid #e9ecef", "borderRadius": "8px",
            "padding": "12px", "background": "#fafafa",
            "marginBottom": "12px",
        }),
        dbc.InputGroup([
            dbc.Input(
                id="chat-input",
                placeholder='e.g. "10 euro at Edeka today" or "3 euro beer, part of Edeka shop"',
                type="text",
                debounce=False,
            ),
            dbc.Button("Send", id="chat-send", color="primary", n_clicks=0),
        ]),
        dcc.Store(id="chat-messages", data=[]),
    ], md=7),

    # Right: recent expenses
    dbc.Col([
        html.H5("Recent expenses", className="mb-3"),
        html.Div(id="recent-expenses-list"),
    ], md=5),
])


@callback(
    Output("chat-history", "children"),
    Output("chat-messages", "data"),
    Output("chat-input", "value"),
    Output("recent-expenses-list", "children"),
    Input("chat-send", "n_clicks"),
    Input("chat-input", "n_submit"),
    State("chat-input", "value"),
    State("chat-messages", "data"),
    prevent_initial_call=True,
)
def handle_chat(n_clicks, n_submit, user_input, messages):
    if not user_input or not user_input.strip():
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    response = agent_bridge.chat(user_input.strip())
    messages = messages + [
        {"role": "user", "text": user_input.strip()},
        {"role": "agent", "text": response},
    ]

    bubbles = []
    for msg in messages:
        is_user = msg["role"] == "user"
        bubbles.append(
            html.Div(msg["text"], style={
                "background": "#0d6efd" if is_user else "#e9ecef",
                "color": "white" if is_user else "#333",
                "padding": "8px 12px",
                "borderRadius": "12px",
                "marginBottom": "8px",
                "maxWidth": "85%",
                "marginLeft": "auto" if is_user else "0",
                "fontSize": "14px",
            })
        )

    recent = fetch_expenses()[-8:][::-1]
    recent_items = [
        dbc.ListGroupItem(
            [
                html.Span(r["description"], className="fw-semibold"),
                html.Span(f" — €{r['amount']:.2f}", className="text-muted"),
                html.Br(),
                html.Small(f"{r['date']} · {r['category']}", className="text-muted"),
            ]
        )
        for r in recent
    ]
    recent_list = dbc.ListGroup(recent_items) if recent_items else html.P("No expenses yet.", className="text-muted")

    return bubbles, messages, "", recent_list
