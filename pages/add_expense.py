# pages/add_expense.py
import re
from datetime import date as _date

import dash
import dash_bootstrap_components as dbc
from dash import Input, Output, State, callback, dcc, html

from expense_tracker_agent import agent_bridge
from expense_tracker_agent.db import fetch_expenses
from expense_tracker_agent.tools import CATEGORIES, add_expense

dash.register_page(__name__, path="/add", name="Add Expense")


_GROCERY_KW = {"edeka", "rewe", "lidl", "aldi", "kaufland", "netto", "penny", "norma",
               "supermarkt", "grocery", "supermarket", "bäckerei", "bakery"}
_DINING_KW  = {"restaurant", "cafe", "kaffee", "coffee", "pizza", "burger", "kebab",
               "mcdonald", "mensa", "bistro", "bäcker", "imbiss", "diner", "sushi"}
_TRANSPORT_KW = {"uber", "taxi", "bus", "bahn", "train", "metro", "tram", "mvv", "hvv",
                 "fuel", "tanken", "petrol", "parking", "bvg", "db"}
_ENTERTAINMENT_KW = {"cinema", "kino", "movie", "concert", "theatre", "museum",
                     "netflix", "spotify", "gaming", "steam"}
_ALCOHOL_KW = {"beer", "bier", "wine", "wein", "spirits", "bar", "pub", "cocktail", "gin", "vodka"}


def _infer_category(text: str) -> str:
    t = text.lower()
    if any(k in t for k in _ALCOHOL_KW):
        return "Alcohol"
    if any(k in t for k in _GROCERY_KW):
        return "Groceries"
    if any(k in t for k in _DINING_KW):
        return "Food & Dining"
    if any(k in t for k in _TRANSPORT_KW):
        return "Transport"
    if any(k in t for k in _ENTERTAINMENT_KW):
        return "Entertainment"
    return "Miscellaneous"


def _try_fallback_parse(raw_text: str, selected_date: str | None) -> str | None:
    """Regex-based expense parser used when the AI API is unavailable."""
    # Amount: €12.50 / 12,50 / 12.5
    amt_m = re.search(r"€?\s*(\d+[.,]\d{1,2}|\d+(?=\s*€)|\d+)", raw_text, re.IGNORECASE)
    if not amt_m:
        return None
    amount = float(amt_m.group(1).replace(",", "."))

    # Merchant: "at Edeka" / "from Rewe" / "bei Lidl"
    merch_m = re.search(r"\b(?:at|from|bei|@)\s+([A-Za-zÄÖÜäöüß][A-Za-zÄÖÜäöüß0-9\s&-]{0,30}?)(?:\s+on\b|\s*$|,)", raw_text, re.IGNORECASE)
    merchant = merch_m.group(1).strip() if merch_m else None

    # Date resolution: prefer date picker, then parse "on DD/MM(/YYYY)"
    expense_date = selected_date[:10] if selected_date else None
    if not expense_date:
        date_m = re.search(r"\bon\s+(\d{1,2}[/.\-]\d{1,2}(?:[/.\-]\d{2,4})?)", raw_text, re.IGNORECASE)
        if date_m:
            parts = re.split(r"[/.\-]", date_m.group(1))
            try:
                day, month = int(parts[0]), int(parts[1])
                year = int(parts[2]) if len(parts) > 2 else _date.today().year
                if year < 100:
                    year += 2000
                expense_date = f"{year:04d}-{month:02d}-{day:02d}"
            except (ValueError, IndexError):
                pass
    if not expense_date:
        expense_date = _date.today().isoformat()

    context = f"{raw_text} {merchant or ''}"
    category = _infer_category(context)
    description = (merchant or raw_text[:40]).strip()

    result = add_expense(
        amount=amount,
        description=description,
        category=category,
        merchant=merchant,
        date=expense_date,
    )
    return f"⚠️ AI unavailable (rate limit hit). Added directly:\n{result}"

layout = dbc.Row([
    # Left: chat panel
    dbc.Col([
        html.H5("Chat with your expense agent", className="mb-3"),
        html.Div(id="chat-history", style={
            "height": "380px", "overflowY": "auto",
            "border": "1px solid #e9ecef", "borderRadius": "8px",
            "padding": "12px", "background": "#fafafa",
            "marginBottom": "12px",
        }),
        dbc.Row([
            dbc.Col([
                html.Label("Date", className="small text-muted mb-1"),
                dcc.DatePickerSingle(
                    id="expense-date-picker",
                    display_format="DD MMM YYYY",
                    placeholder="Today",
                    clearable=True,
                    style={"width": "100%"},
                ),
            ], md=4),
            dbc.Col([
                html.Label("Message", className="small text-muted mb-1"),
                dbc.InputGroup([
                    dbc.Input(
                        id="chat-input",
                        placeholder='e.g. "€10 at Edeka" or "€3 beer, part of Edeka shop"',
                        type="text",
                        debounce=False,
                    ),
                    dbc.Button("Send", id="chat-send", color="primary", n_clicks=0),
                ]),
            ], md=8),
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
    State("expense-date-picker", "date"),
    prevent_initial_call=True,
)
def handle_chat(n_clicks, n_submit, user_input, messages, selected_date):
    if not user_input or not user_input.strip():
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    text = user_input.strip()
    if selected_date:
        text = f"On {selected_date[:10]}: {text}"

    count_before = len(fetch_expenses())
    try:
        response = agent_bridge.chat(text)
    except Exception:
        # Guard: if the agent tool already saved the expense before the API error,
        # skip the fallback to avoid a double-add.
        if len(fetch_expenses()) > count_before:
            last = fetch_expenses()[-1]
            response = (
                f"⚠️ AI hit an error but your expense was saved: "
                f"{last['description']} €{last['amount']:.2f} [{last['category']}]"
            )
        else:
            fallback = _try_fallback_parse(user_input.strip(), selected_date)
            response = fallback if fallback else (
                "⚠️ AI unavailable (rate limit hit). Could not auto-parse — "
                "try a clearer format like '€12.50 at Edeka' or '€5 beer'."
            )

    messages = messages + [
        {"role": "user", "text": user_input.strip() + (f"  [{selected_date[:10]}]" if selected_date else "")},
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

    def _fmt(iso):
        try:
            y, m, d = iso.split("-")
            return f"{d}/{m}/{y}"
        except Exception:
            return iso

    recent = fetch_expenses()[-8:][::-1]
    recent_items = [
        dbc.ListGroupItem([
            html.Span(r["description"], className="fw-semibold"),
            html.Span(f" — €{r['amount']:.2f}", className="text-muted"),
            html.Br(),
            html.Small(f"{_fmt(r['date'])} · {r['category']}", className="text-muted"),
        ])
        for r in recent
    ]
    recent_list = dbc.ListGroup(recent_items) if recent_items else html.P("No expenses yet.", className="text-muted")

    return bubbles, messages, "", recent_list
