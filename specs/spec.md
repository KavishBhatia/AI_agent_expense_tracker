# Feature Spec: Expense Tracker Agent — Persistence, Auto-categorization & NL Input

**Branch**: `001-expense-tracker` | **Date**: 2026-06-03

## Overview

Improve the existing local expense tracker AI agent by adding three capabilities:
1. **Persistence** — save expenses to a CSV file so data survives app restarts
2. **Auto-categorization** — infer expense category from natural descriptions like "grocery market" without requiring explicit user input
3. **Natural language input** — parse free-form input like "spent $45 at Whole Foods yesterday" into structured expense fields

## Current State

The working prototype (`expense_tracker_agent/`) uses Google ADK + Gemini 2.5 Flash with four tools:
- `add_expense(amount, category, description)` — adds to an in-memory list
- `calculate_total_spending()` — sums all expenses
- `get_spending_by_category()` — groups by category
- `list_recent_expenses(count=5)` — shows recent entries

**What works well:**
- Clean agent/tool separation
- Pydantic data validation
- Good unittest coverage pattern
- Tool docstrings guide Gemini accurately

**Known gaps:**
- All data is lost on restart (in-memory only)
- Category must be provided explicitly by the user
- No timestamp on expenses (no date-based filtering possible)
- No merchant/location field

## Requirements

### R1 — CSV Persistence
- Expenses saved to `./expenses.csv` in project root on every `add_expense` call
- File loaded on agent startup if it exists
- CSV columns: `id, amount, category, description, merchant, date, timestamp`
- `id` is auto-generated (UUID or sequential integer)

### R2 — Auto-categorization
- Predefined category list: Food, Groceries, Transport, Entertainment, Bills, Healthcare, Shopping, Other
- Agent infers category from description/merchant when user doesn't specify
- User can override with explicit category
- Category inference done via updated Gemini system prompt (no separate API call)

### R3 — Natural Language Parsing
- Agent parses free-form input → structured fields
- Examples:
  - "spent $45 at Whole Foods" → amount=45, merchant="Whole Foods", category="Groceries"
  - "lunch at McDonald's 12.50" → amount=12.50, merchant="McDonald's", category="Food"
  - "electricity bill 80" → amount=80, category="Bills", description="electricity bill"
- Date parsing: "yesterday", "last Monday", "today" resolved to ISO date (default: today)

### R4 — Enhanced Expense Model
- Add `merchant` (optional), `date` (ISO YYYY-MM-DD), `timestamp` (ISO datetime), `id` fields to `Expense`
- `add_expense` tool signature becomes: `add_expense(amount, description, category=None, merchant=None, date=None)`
- Category optional — inferred if not provided

### R5 — Backward Compatibility
- Existing tests must continue to pass (or be updated minimally)
- Agent instruction updated to guide Gemini on NL parsing and category inference
