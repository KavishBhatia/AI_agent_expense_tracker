# Tasks: Expense Tracker — Persistence, Auto-categorization & NL Input

**Input**: Design documents from `/specs/001-expense-tracker/`

**Branch**: `001-expense-tracker` | **Generated**: 2026-06-03

**Status key**: `[x]` = complete, `[ ]` = remaining

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project structure and gitignore — no new dependencies required (stdlib `csv` only).

- [x] T001 Add `expenses.csv` to `.gitignore` to prevent personal data from being committed

**Checkpoint**: Project ready — all runtime data stays local.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data model and CSV infrastructure. Must be complete before any user story can function.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T002 Extend `Expense` Pydantic model with `id`, `merchant`, `date`, `timestamp` fields in `expense_tracker_agent/tools.py`
- [x] T003 [P] Add `CATEGORIES` constant list (8 values) in `expense_tracker_agent/tools.py`
- [x] T004 [P] Add `CSV_FILE = Path("expenses.csv")` constant in `expense_tracker_agent/tools.py`
- [x] T005 Implement `_load_expenses()` — reads all rows from `expenses.csv` into list on module import in `expense_tracker_agent/tools.py`
- [x] T006 Implement `_save_expense(expense)` — appends single row to `expenses.csv`, creates header on first write in `expense_tracker_agent/tools.py`
- [x] T007 Implement `_filter_by_date(expense_list, start_date, end_date)` helper in `expense_tracker_agent/tools.py`
- [x] T008 Replace `expenses = []` with `expenses = _load_expenses()` in `expense_tracker_agent/tools.py`

**Checkpoint**: Foundation ready — data model is persistent and loadable.

---

## Phase 3: User Story 1 — Persistent Storage (Priority: P1) 🎯 MVP

**Goal**: Every expense logged survives an app restart. User never loses their history.

**Independent Test**: Add an expense, stop the agent, restart it, and call `list_recent_expenses` — the previously added expense must appear.

### Implementation for US1

- [x] T009 [US1] Update `add_expense` signature to `(amount, description, category, merchant=None, date=None)` in `expense_tracker_agent/tools.py`
- [x] T010 [US1] Update `add_expense` body: assign auto-increment `id`, ISO `timestamp`, resolve `date` to today if None, call `_save_expense` in `expense_tracker_agent/tools.py`
- [x] T011 [P] [US1] Add `start_date`/`end_date` optional params to `calculate_total_spending` in `expense_tracker_agent/tools.py`
- [x] T012 [P] [US1] Add `start_date`/`end_date` optional params to `get_spending_by_category` in `expense_tracker_agent/tools.py`
- [x] T013 [P] [US1] Add `category` optional filter (case-insensitive) to `list_recent_expenses` in `expense_tracker_agent/tools.py`

### Tests for US1

- [x] T014 [P] [US1] Write `TestExpenseModel` tests (5 tests) in `test_tools.py`
- [x] T015 [P] [US1] Write `TestCsvPersistence` tests (7 tests: create file, header row, contains data, multiple appends, round-trip load, empty load, field preservation) in `test_tools.py`
- [x] T016 [P] [US1] Write `TestAddExpense` tests (8 tests: merchant kwarg, date kwarg, today default, auto-id, timestamp, return message format) in `test_tools.py`

**Checkpoint**: Expense data persists across restarts. All 20 persistence-related tests pass.

---

## Phase 4: User Story 2 — Auto-categorization & Natural Language Input (Priority: P2)

**Goal**: User can say "spent $45 at Whole Foods" and the agent correctly infers Groceries without being asked.

**Independent Test**: Send "lunch at McDonald's 12.50" to the agent — it must call `add_expense` with `category="Food"` and `merchant="McDonald's"` without asking the user for the category.

### Implementation for US2

- [x] T017 [US2] Implement `_build_instruction(today: str) -> str` in `expense_tracker_agent/agent.py` with:
  - Today's date injected as `f"Today's date is {today}"`
  - Category inference rules for all 8 categories
  - Merchant extraction guidance
  - Relative date resolution guidance ("yesterday", "last Monday")
  - Rule: never ask user for category or merchant — infer from context
- [x] T018 [US2] Update `root_agent` to call `_build_instruction(today=date.today().isoformat())` in `expense_tracker_agent/agent.py`

### Tests for US2

- [x] T019 [P] [US2] Write `TestAgentInstruction` tests (6 tests: today's date present, all 8 categories present, infer keyword, merchant keyword, yesterday keyword, root_agent uses today) in `test_agent.py`
- [x] T020 [P] [US2] Write `TestAgentConfiguration` tests (4 tests: all 4 tools registered) in `test_agent.py`
- [x] T021 [P] [US2] Write `TestAgentRunner` integration tests (2 tests: add_expense called, list_recent_expenses called) with ADK 1.21.0-compatible mock in `test_agent.py`

**Checkpoint**: Agent auto-infers category from natural descriptions. 12 agent tests pass. ADK mock uses `role="model"` on function call content to pass the `_contains_empty_content` filter.

---

## Phase 5: User Story 3 — Date Filtering & Category Querying (Priority: P3)

**Goal**: User can ask "how much did I spend this week?" or "show me only Food expenses".

**Independent Test**: Add 3 expenses on different dates; call `calculate_total_spending(start_date="2026-06-01")` and verify only expenses from June 1st onwards are summed.

### Implementation for US3

*(Already delivered as part of Phase 3 tools.py changes — date filters and category filter on all query tools)*

- [x] T022 [P] [US3] Write `TestCalculateTotalSpending` tests (4 tests: no filter, start_date, end_date, date range) in `test_tools.py`
- [x] T023 [P] [US3] Write `TestGetSpendingByCategory` tests (3 tests: no filter, start_date, end_date) in `test_tools.py`
- [x] T024 [P] [US3] Write `TestListRecentExpenses` tests (4 tests: no filter, category filter, case-insensitive, empty result) in `test_tools.py`
- [x] T025 [P] [US3] Write `TestCategories` tests (3 tests: is list, 8 items, correct values) in `test_tools.py`

**Checkpoint**: All query tools support date and category filtering. All 46 tests pass.

---

## Phase 6: Polish & Validation

**Purpose**: End-to-end validation, documentation, and shipping.

- [ ] T026 Run end-to-end validation per `specs/001-expense-tracker/quickstart.md` — set `GEMINI_API_KEY` and test the 5 example interactions with `adk run expense_tracker_agent`
- [ ] T027 Update `README.md` — add new features section covering persistence, auto-categorization, and natural language examples
- [ ] T028 Commit all changes on branch `001-expense-tracker` with message summarising the feature

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories
- **Phase 3 (US1 — Persistence)**: Depends on Phase 2
- **Phase 4 (US2 — Auto-categorization)**: Depends on Phase 2; independent of US1
- **Phase 5 (US3 — Filtering)**: Depends on Phase 2; tests cover Phase 3 tool changes
- **Phase 6 (Polish)**: Depends on all user story phases complete

### User Story Dependencies

- **US1 (P1)**: Independent after Foundational — no cross-story deps
- **US2 (P2)**: Independent after Foundational — only touches `agent.py`
- **US3 (P3)**: Delivered by US1 tool changes; tested independently

### Within Each Phase

- `_load_expenses` before `expenses = _load_expenses()` (T005 before T008)
- Expense model before `add_expense` update (T002 before T009)
- `_build_instruction` before `root_agent` update (T017 before T018)

---

## Parallel Execution Examples

### Phase 2 (can run in parallel after T002/T005/T006 complete)

```
Task T003: Add CATEGORIES constant in tools.py
Task T004: Add CSV_FILE constant in tools.py
```

### Phase 3 (models and tests within US1 are independent)

```
Task T011: calculate_total_spending date params in tools.py
Task T012: get_spending_by_category date params in tools.py
Task T013: list_recent_expenses category filter in tools.py
```

### Phase 4 (US2 tests are independent)

```
Task T019: TestAgentInstruction tests in test_agent.py
Task T020: TestAgentConfiguration tests in test_agent.py
Task T021: TestAgentRunner tests in test_agent.py
```

---

## Implementation Strategy

### MVP (Already Delivered — Phases 1–5)

All core features are implemented and tested:
1. ✅ Expenses saved to `expenses.csv` on every `add_expense` call
2. ✅ Agent auto-infers category from natural language
3. ✅ Merchant and date extracted from free-form input
4. ✅ Date-range and category filters on all query tools
5. ✅ 46 automated tests (34 tools, 12 agent)

### Remaining to Ship (Phase 6)

1. Run `adk run expense_tracker_agent` with a real API key — T026
2. Update `README.md` — T027
3. Commit — T028

---

## Notes

- `[P]` tasks touch different files — no conflicts when run in parallel
- `[USn]` label maps each task to its user story for traceability
- The ADK 1.21.0 runner mock requires `role="model"` on `Content` with function calls — otherwise the event is filtered as "empty content" in `_contains_empty_content()` at `contents.py:241`
- `expenses.csv` is gitignored; test suites patch `CSV_FILE` to a tempfile to avoid interference
