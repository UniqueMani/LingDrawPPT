import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path(os.getenv("APP_DB_PATH", "backend/app.db"))


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                is_admin INTEGER NOT NULL DEFAULT 0,
                full_name TEXT DEFAULT '',
                email TEXT DEFAULT '',
                organization TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "full_name" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN full_name TEXT DEFAULT ''")
        if "email" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''")
        if "organization" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN organization TEXT DEFAULT ''")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def record_event(user_id: int, event_type: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO usage_logs (user_id, event_type, created_at) VALUES (?, ?, ?)",
            (user_id, event_type, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()


def get_user_stats(user_id: int, days: int = 30) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT event_type, COUNT(*) as cnt
            FROM usage_logs
            WHERE user_id = ? AND created_at >= datetime('now', ? || ' days')
            GROUP BY event_type
            """,
            (user_id, f"-{days}"),
        ).fetchall()
    return {row["event_type"]: row["cnt"] for row in rows}
