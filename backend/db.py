import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Optional


DB_PATH = Path(os.getenv("APP_DB_PATH", "backend/app.db"))


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


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
        if "is_active" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        if "disabled_at" not in cols:
            conn.execute("ALTER TABLE users ADD COLUMN disabled_at TEXT")

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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS uploaded_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                mime_type TEXT DEFAULT '',
                file_size INTEGER NOT NULL DEFAULT 0,
                pages INTEGER NOT NULL DEFAULT 0,
                parse_status TEXT NOT NULL DEFAULT 'processing',
                error_message TEXT DEFAULT '',
                extracted_text TEXT DEFAULT '',
                pages_detail TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT,
                deleted_at TEXT
            )
            """
        )
        file_cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(uploaded_files)").fetchall()
        }
        if "extracted_text" not in file_cols:
            conn.execute("ALTER TABLE uploaded_files ADD COLUMN extracted_text TEXT DEFAULT ''")
        if "pages_detail" not in file_cols:
            conn.execute("ALTER TABLE uploaded_files ADD COLUMN pages_detail TEXT DEFAULT '[]'")
        if "updated_at" not in file_cols:
            conn.execute("ALTER TABLE uploaded_files ADD COLUMN updated_at TEXT")
            conn.execute("UPDATE uploaded_files SET updated_at = created_at WHERE updated_at IS NULL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS admin_audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_user_id INTEGER NOT NULL,
                action_type TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                detail TEXT DEFAULT '',
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


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_uploaded_file(
    user_id: int,
    original_filename: str,
    stored_filename: str,
    file_path: str,
    mime_type: str,
    file_size: int,
) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO uploaded_files
                (user_id, original_filename, stored_filename, file_path, mime_type, file_size, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, original_filename, stored_filename, file_path, mime_type, file_size, utc_now()),
        )
        conn.commit()
        return int(cur.lastrowid)


def update_uploaded_file(file_id: int, *, parse_status: str, pages: int = 0, error_message: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE uploaded_files SET parse_status = ?, pages = ?, error_message = ?, updated_at = ? WHERE id = ?",
            (parse_status, pages, error_message[:1000], utc_now(), file_id),
        )
        conn.commit()


def update_uploaded_file_result(
    file_id: int,
    *,
    parse_status: str,
    pages: int = 0,
    error_message: str = "",
    extracted_text: str = "",
    pages_detail: str = "[]",
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE uploaded_files
            SET parse_status = ?, pages = ?, error_message = ?, extracted_text = ?, pages_detail = ?, updated_at = ?
            WHERE id = ?
            """,
            (parse_status, pages, error_message[:1000], extracted_text, pages_detail, utc_now(), file_id),
        )
        conn.commit()


def get_uploaded_file(file_id: int) -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT f.*, u.username
            FROM uploaded_files f JOIN users u ON u.id = f.user_id
            WHERE f.id = ?
            """,
            (file_id,),
        ).fetchone()
        return dict(row) if row else None


def list_user_uploaded_files(user_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, original_filename, stored_filename, file_path, mime_type,
                   file_size, pages, parse_status, error_message, created_at,
                   COALESCE(updated_at, created_at) AS updated_at
            FROM uploaded_files
            WHERE user_id = ? AND deleted_at IS NULL
            ORDER BY id DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_user_uploaded_file(file_id: int, user_id: int) -> Optional[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, user_id, original_filename, stored_filename, file_path, mime_type,
                   file_size, pages, parse_status, error_message, extracted_text,
                   pages_detail, created_at, COALESCE(updated_at, created_at) AS updated_at
            FROM uploaded_files
            WHERE id = ? AND user_id = ? AND deleted_at IS NULL
            """,
            (file_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def record_admin_audit(
    admin_user_id: int,
    action_type: str,
    target_type: str,
    target_id: str | int,
    detail: str = "",
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO admin_audit_logs
                (admin_user_id, action_type, target_type, target_id, detail, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (admin_user_id, action_type, target_type, str(target_id), detail[:1000], utc_now()),
        )
        conn.commit()


def _page_args(page: int, page_size: int) -> tuple[int, int]:
    size = max(1, min(100, page_size))
    return size, (max(1, page) - 1) * size


def list_admin_users(page: int, page_size: int, keyword: str = "", active: Optional[bool] = None) -> dict[str, Any]:
    where: list[str] = []
    args: list[Any] = []
    if keyword:
        where.append("(username LIKE ? OR full_name LIKE ? OR email LIKE ? OR organization LIKE ?)")
        token = f"%{keyword}%"
        args.extend([token, token, token, token])
    if active is not None:
        where.append("is_active = ?")
        args.append(1 if active else 0)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    size, offset = _page_args(page, page_size)
    with get_conn() as conn:
        total = int(conn.execute(f"SELECT COUNT(*) FROM users {clause}", args).fetchone()[0])
        rows = conn.execute(
            f"""
            SELECT id, username, is_admin, is_active, disabled_at, full_name, email, organization, created_at
            FROM users {clause} ORDER BY id DESC LIMIT ? OFFSET ?
            """,
            [*args, size, offset],
        ).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": size}


def list_uploaded_files(
    page: int,
    page_size: int,
    keyword: str = "",
    user_id: Optional[int] = None,
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    include_deleted: bool = False,
) -> dict[str, Any]:
    where = [] if include_deleted else ["f.deleted_at IS NULL"]
    args: list[Any] = []
    if keyword:
        where.append("f.original_filename LIKE ?")
        args.append(f"%{keyword}%")
    if user_id is not None:
        where.append("f.user_id = ?")
        args.append(user_id)
    if status:
        where.append("f.parse_status = ?")
        args.append(status)
    if date_from:
        where.append("f.created_at >= ?")
        args.append(date_from)
    if date_to:
        where.append("f.created_at <= ?")
        args.append(date_to)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    size, offset = _page_args(page, page_size)
    select = """
        SELECT f.id, f.user_id, u.username, f.original_filename, f.mime_type, f.file_size,
               f.pages, f.parse_status, f.error_message, f.created_at, f.deleted_at
        FROM uploaded_files f JOIN users u ON u.id = f.user_id
    """
    with get_conn() as conn:
        total = int(conn.execute(f"SELECT COUNT(*) FROM uploaded_files f {clause}", args).fetchone()[0])
        rows = conn.execute(f"{select} {clause} ORDER BY f.id DESC LIMIT ? OFFSET ?", [*args, size, offset]).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": size}


def soft_delete_uploaded_file(file_id: int) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE uploaded_files SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL",
            (utc_now(), file_id),
        )
        conn.commit()
        return cur.rowcount > 0


def list_usage_logs(
    page: int,
    page_size: int,
    user_id: Optional[int] = None,
    event_type: str = "",
    date_from: str = "",
    date_to: str = "",
) -> dict[str, Any]:
    where: list[str] = []
    args: list[Any] = []
    if user_id is not None:
        where.append("l.user_id = ?")
        args.append(user_id)
    if event_type:
        where.append("l.event_type = ?")
        args.append(event_type)
    if date_from:
        where.append("l.created_at >= ?")
        args.append(date_from)
    if date_to:
        where.append("l.created_at <= ?")
        args.append(date_to)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    size, offset = _page_args(page, page_size)
    select = "SELECT l.id, l.user_id, u.username, l.event_type, l.created_at FROM usage_logs l JOIN users u ON u.id = l.user_id"
    with get_conn() as conn:
        total = int(conn.execute(f"SELECT COUNT(*) FROM usage_logs l {clause}", args).fetchone()[0])
        rows = conn.execute(f"{select} {clause} ORDER BY l.id DESC LIMIT ? OFFSET ?", [*args, size, offset]).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": size}


def clear_usage_logs(before: str) -> int:
    with get_conn() as conn:
        cur = conn.execute("DELETE FROM usage_logs WHERE created_at < ?", (before,))
        conn.commit()
        return int(cur.rowcount)


def list_audit_logs(page: int, page_size: int) -> dict[str, Any]:
    size, offset = _page_args(page, page_size)
    with get_conn() as conn:
        total = int(conn.execute("SELECT COUNT(*) FROM admin_audit_logs").fetchone()[0])
        rows = conn.execute(
            """
            SELECT l.id, l.admin_user_id, u.username AS admin_username, l.action_type,
                   l.target_type, l.target_id, l.detail, l.created_at
            FROM admin_audit_logs l JOIN users u ON u.id = l.admin_user_id
            ORDER BY l.id DESC LIMIT ? OFFSET ?
            """,
            (size, offset),
        ).fetchall()
    return {"items": [dict(row) for row in rows], "total": total, "page": page, "page_size": size}


def get_admin_overview() -> dict[str, Any]:
    with get_conn() as conn:
        total_users = int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])
        active_users = int(conn.execute("SELECT COUNT(*) FROM users WHERE is_active = 1").fetchone()[0])
        total_files = int(conn.execute("SELECT COUNT(*) FROM uploaded_files WHERE deleted_at IS NULL").fetchone()[0])
        failed_files = int(conn.execute("SELECT COUNT(*) FROM uploaded_files WHERE deleted_at IS NULL AND parse_status = 'failed'").fetchone()[0])
        recent_events = int(conn.execute("SELECT COUNT(*) FROM usage_logs WHERE created_at >= datetime('now', '-30 days')").fetchone()[0])
        counts = conn.execute(
            "SELECT event_type, COUNT(*) AS cnt FROM usage_logs WHERE created_at >= datetime('now', '-30 days') GROUP BY event_type"
        ).fetchall()
    failed = list_uploaded_files(1, 5, status="failed")["items"]
    audits = list_audit_logs(1, 5)["items"]
    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_files": total_files,
        "failed_files": failed_files,
        "recent_events": recent_events,
        "event_counts": {row["event_type"]: row["cnt"] for row in counts},
        "recent_failed_files": failed,
        "recent_audit_logs": audits,
    }
