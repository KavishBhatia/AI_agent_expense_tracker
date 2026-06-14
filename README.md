# ExpenseAI

A personal expense tracker with a conversational AI agent and a web dashboard. Log expenses by chatting naturally, import CSV history, scan receipts with Gemini Vision, and explore your spending through interactive charts.

## Features

| Page | What it does |
|------|-------------|
| **Dashboard** | KPI cards, daily/monthly trend, category donut, top merchants, heatmap. Click any bar to drill down into that day's transactions. |
| **Add Expense** | Chat with a Gemini-powered agent — "€9.49 at Edeka on 10/06" just works. Pick a date from the date picker or leave it blank for today. |
| **Import CSV** | Upload a CSV, auto-detect date/cost/merchant columns (DD/MM/YYYY aware), preview before committing, get per-row error detail on failures. |
| **Scan Receipt** | Upload a receipt photo — Gemini Vision extracts the merchant, total, and individual line items into an editable table before saving. |

## Tech stack

- **AI** — Google Gemini 2.5 Flash via [Google ADK](https://google.github.io/adk-docs/)
- **Frontend** — [Plotly Dash](https://dash.plotly.com/) + Dash Bootstrap Components
- **Charts** — Plotly
- **Database** — SQLite (auto-created on first run, no setup needed)
- **Data** — pandas

## Setup

```bash
# 1. Clone
git clone https://github.com/kavishbhatia/AI_agent_expense_tracker.git
cd AI_agent_expense_tracker

# 2. Virtual environment
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# 3. Install
pip install -e .

# 4. API key
cp .env.example .env
# Open .env and set GOOGLE_API_KEY=your_key_here
```

Get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com/).

## Run

```bash
python app.py
```

Open [http://localhost:8050](http://localhost:8050). The SQLite database is created automatically on first launch.

## Project structure

```
AI_agent_expense_tracker/
├── app.py                          # Dash entry point
├── pyproject.toml
├── .env.example
├── pages/                          # Dash multi-page UI
│   ├── dashboard.py
│   ├── add_expense.py
│   ├── import_csv.py
│   └── scan_receipt.py
├── expense_tracker_agent/          # Backend package
│   ├── agent.py                    # ADK root agent
│   ├── tools.py                    # Agent tools (add, list, calculate…)
│   ├── db.py                       # SQLite layer
│   ├── receipt_scanner.py          # Gemini Vision receipt parsing
│   ├── charts.py                   # Plotly figure builders
│   └── agent_bridge.py             # Sync bridge from Dash → async ADK
└── tests/
    ├── test_db.py
    ├── test_charts.py
    ├── test_tools.py
    ├── test_agent.py
    └── test_receipt_scanner.py
```

## Running tests

```bash
.venv/bin/python -m pytest tests/ -v
```
