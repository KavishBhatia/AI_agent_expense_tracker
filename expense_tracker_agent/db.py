# expense_tracker_agent/db.py
import csv as _csv
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path("expenses.db")


@contextmanager
def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                amount    REAL    NOT NULL,
                merchant  TEXT,
                category  TEXT    NOT NULL,
                description TEXT  NOT NULL,
                date      TEXT    NOT NULL,
                timestamp TEXT    NOT NULL,
                source    TEXT    NOT NULL DEFAULT 'manual',
                deleted   INTEGER NOT NULL DEFAULT 0
            )
        """)
        # Migration: add deleted column to pre-existing databases
        existing_cols = [r[1] for r in conn.execute("PRAGMA table_info(expenses)").fetchall()]
        if "deleted" not in existing_cols:
            conn.execute("ALTER TABLE expenses ADD COLUMN deleted INTEGER NOT NULL DEFAULT 0")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS expense_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id   INTEGER NOT NULL REFERENCES expenses(id),
                amount      REAL    NOT NULL,
                description TEXT    NOT NULL,
                category    TEXT    NOT NULL,
                timestamp   TEXT    NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS budgets (
                category      TEXT PRIMARY KEY,
                monthly_limit REAL NOT NULL
            )
        """)
        # Migration: rename Transport → Commute
        conn.execute("UPDATE expenses SET category = 'Commute' WHERE category = 'Transport'")
        conn.execute("UPDATE expense_items SET category = 'Commute' WHERE category = 'Transport'")
        conn.execute("UPDATE budgets SET category = 'Commute' WHERE category = 'Transport'")


def insert_expense(
    amount: float,
    category: str,
    description: str,
    merchant: Optional[str] = None,
    date: Optional[str] = None,
    source: str = "manual",
) -> int:
    ts = datetime.now().isoformat(timespec="seconds")
    d = date or datetime.now().date().isoformat()
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO expenses (amount, merchant, category, description, date, timestamp, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (amount, merchant, category, description, d, ts, source),
        )
        return cur.lastrowid


def insert_expense_item(parent_id: int, amount: float, description: str, category: str) -> int:
    ts = datetime.now().isoformat(timespec="seconds")
    with _conn() as conn:
        cur = conn.execute(
            "INSERT INTO expense_items (parent_id, amount, description, category, timestamp) "
            "VALUES (?, ?, ?, ?, ?)",
            (parent_id, amount, description, category, ts),
        )
        return cur.lastrowid


def fetch_expenses(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> list[dict]:
    sql = "SELECT * FROM expenses WHERE deleted = 0"
    params: list = []
    if start_date:
        sql += " AND date >= ?"
        params.append(start_date)
    if end_date:
        sql += " AND date <= ?"
        params.append(end_date)
    sql += " ORDER BY date ASC, id ASC"
    with _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def fetch_expense_items(parent_id: int) -> list[dict]:
    with _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM expense_items WHERE parent_id = ? ORDER BY id",
            (parent_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def fetch_expense_items_by_parent_ids(parent_ids: list[int]) -> dict[int, list[dict]]:
    if not parent_ids:
        return {}
    placeholders = ",".join("?" for _ in parent_ids)
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM expense_items WHERE parent_id IN ({placeholders}) ORDER BY parent_id, id",
            parent_ids,
        ).fetchall()
    grouped: dict[int, list[dict]] = {pid: [] for pid in parent_ids}
    for row in rows:
        item = dict(row)
        grouped[item["parent_id"]].append(item)
    return grouped


def expense_exists(date: str, merchant: str, amount: float) -> bool:
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM expenses WHERE date=? AND merchant=? AND amount=?",
            (date, merchant, amount),
        ).fetchone()
    return row is not None


def find_parent_expense(merchant: str, date: str) -> Optional[int]:
    with _conn() as conn:
        row = conn.execute(
            "SELECT id FROM expenses WHERE merchant=? AND date=? ORDER BY id DESC LIMIT 1",
            (merchant, date),
        ).fetchone()
    return row["id"] if row else None


def delete_expense(expense_id: int) -> None:
    with _conn() as conn:
        conn.execute("UPDATE expenses SET deleted = 1 WHERE id = ?", (expense_id,))


def restore_expense(expense_id: int) -> None:
    with _conn() as conn:
        conn.execute("UPDATE expenses SET deleted = 0 WHERE id = ?", (expense_id,))


def update_expense_category(expense_id: int, category: str) -> None:
    with _conn() as conn:
        conn.execute(
            "UPDATE expenses SET category = ? WHERE id = ?",
            (category, expense_id),
        )


def get_all_budgets() -> dict[str, float]:
    with _conn() as conn:
        rows = conn.execute("SELECT category, monthly_limit FROM budgets").fetchall()
    return {r["category"]: r["monthly_limit"] for r in rows}


def set_budget(category: str, monthly_limit: float | None) -> None:
    with _conn() as conn:
        if monthly_limit is None or monthly_limit <= 0:
            conn.execute("DELETE FROM budgets WHERE category = ?", (category,))
        else:
            conn.execute(
                "INSERT INTO budgets (category, monthly_limit) VALUES (?, ?) "
                "ON CONFLICT(category) DO UPDATE SET monthly_limit=excluded.monthly_limit",
                (category, monthly_limit),
            )


def migrate_from_csv(csv_path: Path) -> int:
    if not csv_path.exists():
        return 0
    count = 0
    with open(csv_path, newline="") as f:
        for row in _csv.DictReader(f):
            merchant = row.get("merchant") or None
            if not expense_exists(row["date"], merchant or "", float(row["amount"])):
                insert_expense(
                    amount=float(row["amount"]),
                    category=row["category"],
                    description=row["description"],
                    merchant=merchant,
                    date=row["date"],
                    source="csv_import",
                )
                count += 1
    return count
