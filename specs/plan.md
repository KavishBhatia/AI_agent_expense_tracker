# Implementation Plan: Expense Tracker Improvements

**Branch**: `001-expense-tracker` | **Date**: 2026-06-03 | **Spec**: [spec.md](spec.md)

**Input**: [specs/001-expense-tracker/spec.md](spec.md)

## Summary

Extend the existing Google ADK expense tracker agent with CSV persistence, auto-categorization via improved Gemini prompting, and natural language parsing for merchant/date extraction. The agent architecture (ADK + tools pattern) stays unchanged; all changes are in `tools.py` and `agent.py`.

## Technical Context

**Language/Version**: Python 3.11

**Primary Dependencies**: google-adk, gemini-2.5-flash, pydantic (all existing); `csv` module (stdlib, no new installs)

**Storage**: CSV file (`./expenses.csv`) — user-confirmed; Python stdlib `csv` module

**Testing**: unittest (existing pattern in `test_agent.py`)

**Target Platform**: Local machine (macOS/Linux), CLI via `adk run`

**Project Type**: AI agent CLI tool

**Performance Goals**: Interactive sub-2s response (unchanged — Gemini API latency dominates)

**Constraints**: Local-only, no cloud storage, single-user, no new pip dependencies

**Scale/Scope**: Personal use (~100–500 expenses total)

## Constitution Check

*Constitution is a placeholder template — no gates defined. No violations.*

## Project Structure

### Documentation (this feature)

```text
specs/001-expense-tracker/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── tools.md         # Tool interface contracts
└── tasks.md             # Phase 2 output (not yet created)
```

### Source Code

```text
expense_tracker_agent/
├── agent.py             # Update: new instruction with categories + date injection
└── tools.py             # Update: Expense model, add_expense signature, CSV persistence

expenses.csv             # Generated at runtime (gitignored)
test_agent.py            # Update: new Expense fields, add_expense parameters
```

## Implementation Phases

### Phase 1 — Extend `Expense` model and `add_expense` tool (tools.py)

1. Add `id`, `merchant`, `date`, `timestamp` fields to `Expense` Pydantic model
2. Add `CATEGORIES` constant list
3. Add `_load_expenses()` helper — reads `expenses.csv` into list on module load
4. Add `_save_expense(expense)` helper — appends row to `expenses.csv`
5. Replace `expenses = []` with `expenses = _load_expenses()`
6. Update `add_expense` signature: `(amount, description, category, merchant=None, date=None)`
7. Update `add_expense` body: assign id/timestamp, call `_save_expense`
8. Update `calculate_total_spending` to accept `start_date`/`end_date` (optional)
9. Update `get_spending_by_category` to accept `start_date`/`end_date` (optional)
10. Update `list_recent_expenses` to accept `category` filter (optional)

### Phase 2 — Update agent instruction (agent.py)

1. Import `date` from `datetime`
2. Inject `date.today().isoformat()` into agent `instruction` at construction time
3. Add category inference rules to instruction
4. Add merchant extraction guidance to instruction
5. Add date resolution guidance (today/yesterday/relative dates)

### Phase 3 — Update tests (test_agent.py)

1. Update `test_add_expense_tool_call` mock args to include `date` parameter
2. Update assertions for new `Expense` fields (id, date, timestamp)
3. Ensure `tools.expenses.clear()` in `setUp` still works

## Complexity Tracking

No constitution violations. Architecture unchanged from existing ADK pattern.
