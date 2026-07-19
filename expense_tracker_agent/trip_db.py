# expense_tracker_agent/trip_db.py
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

TRIP_DB_PATH = Path("trips.db")


@contextmanager
def _conn():
    conn = sqlite3.connect(TRIP_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_trip_db() -> None:
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS trips (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL,
                created_at TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS trip_expenses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id     INTEGER NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
                amount      REAL    NOT NULL,
                merchant    TEXT,
                category    TEXT    NOT NULL,
                description TEXT,
                date        TEXT    NOT NULL
            );
        """)


def create_trip(name: str) -> int:
    ts = datetime.now().isoformat()
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO trips (name, created_at) VALUES (?, ?)", (name, ts)
        )
        return cur.lastrowid


def _row_to_trip(row) -> dict:
    return {
        "id": row[0], "name": row[1], "created_at": row[2],
        "start_date": row[3], "end_date": row[4],
        "total": row[5] or 0.0, "count": row[6] or 0,
    }


def fetch_trips() -> list[dict]:
    sql = """
        SELECT t.id, t.name, t.created_at,
               MIN(e.date) AS start_date, MAX(e.date) AS end_date,
               COALESCE(SUM(e.amount), 0.0) AS total,
               COUNT(e.id) AS count
        FROM trips t
        LEFT JOIN trip_expenses e ON e.trip_id = t.id
        GROUP BY t.id
        ORDER BY (MAX(e.date) IS NULL) ASC, MAX(e.date) DESC, t.created_at DESC
    """
    with _conn() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(sql).fetchall()
    return [_row_to_trip(r) for r in rows]


def fetch_trip(trip_id: int) -> dict | None:
    sql = """
        SELECT t.id, t.name, t.created_at,
               MIN(e.date) AS start_date, MAX(e.date) AS end_date,
               COALESCE(SUM(e.amount), 0.0) AS total,
               COUNT(e.id) AS count
        FROM trips t
        LEFT JOIN trip_expenses e ON e.trip_id = t.id
        WHERE t.id = ?
        GROUP BY t.id
    """
    with _conn() as con:
        con.row_factory = sqlite3.Row
        row = con.execute(sql, (trip_id,)).fetchone()
    return _row_to_trip(row) if row else None


def fetch_trip_expenses(trip_id: int) -> list[dict]:
    sql = """
        SELECT id, trip_id, amount, merchant, category, description, date
        FROM trip_expenses
        WHERE trip_id = ?
        ORDER BY date ASC
    """
    with _conn() as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(sql, (trip_id,)).fetchall()
    return [dict(r) for r in rows]


def insert_trip_expense(
    trip_id: int,
    amount: float,
    merchant: str | None,
    category: str,
    description: str | None,
    date: str,
) -> int:
    with _conn() as con:
        con.execute("PRAGMA foreign_keys = ON")
        cur = con.execute(
            """INSERT INTO trip_expenses
               (trip_id, amount, merchant, category, description, date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (trip_id, amount, merchant, category, description, date),
        )
        return cur.lastrowid


def trip_expense_exists(trip_id: int, date: str, merchant: str | None, amount: float) -> bool:
    if not merchant:
        return False
    with _conn() as con:
        row = con.execute(
            "SELECT 1 FROM trip_expenses WHERE trip_id=? AND date=? AND merchant=? AND amount=? LIMIT 1",
            (trip_id, date, merchant, amount),
        ).fetchone()
    return row is not None


def delete_trip(trip_id: int) -> None:
    with _conn() as con:
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("DELETE FROM trips WHERE id = ?", (trip_id,))


def delete_trip_expense(expense_id: int) -> None:
    with _conn() as con:
        con.execute("DELETE FROM trip_expenses WHERE id = ?", (expense_id,))


def fetch_trip_expense(expense_id: int) -> dict | None:
    sql = """SELECT id, trip_id, amount, merchant, category, description, date
             FROM trip_expenses WHERE id = ?"""
    with _conn() as con:
        con.row_factory = sqlite3.Row
        row = con.execute(sql, (expense_id,)).fetchone()
    return dict(row) if row else None


def update_trip_expense(
    expense_id: int,
    amount: float,
    merchant: str | None,
    category: str,
    description: str | None,
    date: str,
) -> None:
    with _conn() as con:
        con.execute(
            """UPDATE trip_expenses
               SET amount=?, merchant=?, category=?, description=?, date=?
               WHERE id=?""",
            (amount, merchant, category, description, date, expense_id),
        )
