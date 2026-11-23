# Quickstart

## Prerequisites

```bash
uv sync --dev
cp .env.example .env        # then set GOOGLE_API_KEY in .env
```

A free key is available at https://aistudio.google.com/.

## Run the app

```bash
uv run python app.py
```

Open http://localhost:8050. `expenses.db` and `trips.db` are created on first launch. Stop the foreground server with Ctrl+C. On macOS, double-click `expense_start.command` to start the app in the background and `expense_stop.command` to stop it (both use `.expense_tracker.pid` in the project root). The stop script also closes the Terminal windows used to start and stop the app (Terminal.app only); the first time, macOS may ask to let Terminal control Terminal, so allow it.

## Pages

| Path | Page |
|------|------|
| `/` | Dashboard |
| `/add` | Add Expense (chat) |
| `/history` | History |
| `/trips`, `/trip` | Trips |
| `/budgets` | Budgets |
| `/import` | Import CSV |
| `/scan` | Scan Receipt |
| `/backup` | Backup |

## Example chat (Add Expense)

```
You:   €9.49 at Edeka on 10/06
Agent: Added expense #... Edeka €9.49 [Groceries] on 2026-06-10

You:   Lunch at McDonald's was 12.50 yesterday
Agent: Added expense #... McDonald's €12.50 [Food & Dining] on <yesterday>

You:   How much have I spent total?
Agent: Total spending: €...

You:   Show spending by category
You:   List my last 3 expenses
```

Adding the same date + merchant + amount again returns a duplicate warning; reply "add anyway" to save it.

## Backups

```bash
uv run python scripts/backup_db.py --auth    # one-time Google Drive OAuth
uv run python scripts/backup_db.py --local   # local backup only
scripts/install_backup_schedule.sh           # install the daily schedule (macOS)
```

## Run tests

```bash
uv run pytest tests/ -v
```
