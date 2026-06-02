import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.db import get_conn


AUTH_SECRET = os.getenv("AUTH_SECRET", "lingdraw-dev-secret").encode("utf-8")
TOKEN_TTL_SECONDS = int(os.getenv("TOKEN_TTL_SECONDS", "86400"))


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64url_decode(raw: str) -> bytes:
    pad = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode((raw + pad).encode("utf-8"))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return f"pbkdf2_sha256${_b64url_encode(salt)}${_b64url_encode(digest)}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algo, salt_b64, digest_b64 = encoded.split("$", 2)
        if algo != "pbkdf2_sha256":
            return False
        salt = _b64url_decode(salt_b64)
        expected = _b64url_decode(digest_b64)
        got = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
        return hmac.compare_digest(got, expected)
    except Exception:
        return False


def create_token(user_id: int, username: str, is_admin: bool) -> str:
    payload = {
        "sub": user_id,
        "username": username,
        "is_admin": bool(is_admin),
        "exp": int(time.time()) + TOKEN_TTL_SECONDS,
    }
    body = _b64url_encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    sig = hmac.new(AUTH_SECRET, body.encode("utf-8"), hashlib.sha256).digest()
    return f"{body}.{_b64url_encode(sig)}"


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        body, sig = token.split(".", 1)
        expected = hmac.new(AUTH_SECRET, body.encode("utf-8"), hashlib.sha256).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig)):
            return None
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None
        return payload
    except Exception:
        return None


def get_user_by_username(username: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, is_admin, full_name, email, organization, created_at FROM users WHERE username = ?",
            (username,),
        ).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, is_admin, full_name, email, organization, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None


def create_user(
    username: str,
    password: str,
    is_admin: bool = False,
    full_name: str = "",
    email: str = "",
    organization: str = "",
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    pwh = hash_password(password)
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, is_admin, full_name, email, organization, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (username, pwh, 1 if is_admin else 0, full_name, email, organization, now),
        )
        conn.commit()
        user_id = cur.lastrowid
    return get_user_by_id(int(user_id)) or {}


def update_user(
    user_id: int,
    *,
    username: Optional[str] = None,
    password: Optional[str] = None,
    full_name: Optional[str] = None,
    email: Optional[str] = None,
    organization: Optional[str] = None,
) -> Dict[str, Any]:
    assignments: list[str] = []
    values: list[Any] = []
    if username is not None:
        assignments.append("username = ?")
        values.append(username)
    if password is not None:
        assignments.append("password_hash = ?")
        values.append(hash_password(password))
    if full_name is not None:
        assignments.append("full_name = ?")
        values.append(full_name)
    if email is not None:
        assignments.append("email = ?")
        values.append(email)
    if organization is not None:
        assignments.append("organization = ?")
        values.append(organization)
    if assignments:
        values.append(user_id)
        with get_conn() as conn:
            conn.execute(
                f"UPDATE users SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
            conn.commit()
    return get_user_by_id(user_id) or {}


def list_users() -> list[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, username, is_admin, full_name, email, organization, created_at FROM users ORDER BY id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def ensure_admin_user(username: str, password: str) -> None:
    existing = get_user_by_username(username)
    if existing:
        return
    create_user(username=username, password=password, is_admin=True)


def ensure_normal_user(username: str, password: str) -> None:
    existing = get_user_by_username(username)
    if existing:
        return
    create_user(username=username, password=password, is_admin=False)
