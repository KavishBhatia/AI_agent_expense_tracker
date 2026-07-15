# Trips Feature Design

**Goal:** Add a self-contained Trips section to the expense tracker, where users can group expenses by trip (e.g. "Barcelona May 2026"), import CSVs into a trip, add expenses manually, and view trip analytics.

**Prompted by:** User has multiple per-trip CSVs and wants a dedicated view separate from the main expense dashboard.

---

## Data Model

**Separate SQLite file:** `trips.db` (next to `expenses.db`). The main `expenses.db` is never read or written by the trips feature.

### `trips` table

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `name` | TEXT | NOT NULL |
| `created_at` | TEXT | NOT NULL (ISO datetime) |

### `trip_expenses` table

| Column | Type | Constraints |
|--------|------|-------------|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT |
| `trip_id` | INTEGER | NOT NULL, FK → trips(id) ON DELETE CASCADE |
| `amount` | REAL | NOT NULL |
| `merchant` | TEXT | nullable |
| `category` | TEXT | NOT NULL |
| `description` | TEXT | nullable |
| `date` | TEXT | NOT NULL (YYYY-MM-DD) |

**Trip start/end dates** are computed on-the-fly from `MIN(date)` / `MAX(date)` in `trip_expenses` — not stored.

---

## Pages

### `/trips` — Trip list

- Header row: "Trips" title + "+ New Trip" button
- Each trip rendered as a card showing: name, date range, total spent, expense count, Open / ✕ buttons
- Cards sorted by most recent expense date (newest first); trips with no expenses fall to the bottom
- "+ New Trip" opens a modal with a single name field → on create, redirect to `/trip?id=N`
- "✕" hard-deletes the trip and all its expenses

### `/trip?id=N` — Trip detail

- "← All Trips" back link
- Three KPI cards: trip name + date range, total spent, duration in days
- Daily spending bar chart (Plotly, same teal colour scheme as main app)
- "+ Add Expense" button → collapsible inline form: amount (required), merchant (optional), category (dropdown from `CATEGORIES`), description (optional), date picker
- "Import CSV" button → collapsible file upload, same auto-detection logic as existing import page
- Expense table: date, merchant, category, description, amount

---

## Navigation

"Trips" is added as the first item in the existing ☰ off-canvas drawer in `app.py`.

---

## New Module: `expense_tracker_agent/trip_db.py`

Mirrors the structure of `db.py` but for `trips.db` only. Public interface:

```python
TRIP_DB_PATH: Path
init_trip_db() -> None
create_trip(name: str) -> int
fetch_trips() -> list[dict]
fetch_trip(trip_id: int) -> dict | None
fetch_trip_expenses(trip_id: int) -> list[dict]
insert_trip_expense(trip_id, amount, merchant, category, description, date) -> int
delete_trip(trip_id: int) -> None
```

---

## CSV Import

Reuses the column-detection sets from `import_csv.py` (copied, not imported):
- Date columns: `date`, `datum`, `day`
- Amount columns: `cost`, `amount`, `price`, `kosten`, `betrag`, `preis`
- Merchant columns: `supermarket name`, `supermarket`, `merchant`, `store`, `shop`, `markt`, `laden`

Categories assigned via `classify_expenses()` from `categoriser.py` (same Gemini batch call as main import). Falls back to "Miscellaneous" if the API is unavailable.

---

## Isolation

- `trips.db` is fully separate from `expenses.db`
- The main Dashboard, History, Add Expense, and Budgets pages never read trip data
- Budget alerts and KPI cards on the main dashboard are unaffected

---

## Testing

`tests/test_trip_db.py` covers all `trip_db.py` functions using a temporary DB file patched via `unittest.mock.patch.object(trip_db_module, "TRIP_DB_PATH", tmp_path)` — matching the pattern in `tests/test_db.py`.

No tests for the Dash page callbacks (UI-only, consistent with existing pages).
