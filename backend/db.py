import os
import sqlite3
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
        conn.commit()
