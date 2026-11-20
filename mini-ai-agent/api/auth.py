import base64
import hashlib
import hmac
import json
import os
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterator

from fastapi import HTTPException

DB_PATH = os.getenv("AUTH_DB_PATH", os.path.join("data", "auth.db"))
SECRET = os.getenv("AUTH_SECRET", "mini-agent-local-secret-change-me")
TOKEN_TTL = int(os.getenv("AUTH_TOKEN_TTL", "86400"))


def _connect() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def _db() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                username TEXT PRIMARY KEY,
                salt TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )


def _hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000
    ).hex()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(payload: str) -> str:
    return _b64(hmac.new(SECRET.encode(), payload.encode(), hashlib.sha256).digest())


def register(username: str, password: str) -> dict[str, Any]:
    username = (username or "").strip().lower()
    if not username or len(username) > 64:
        raise HTTPException(status_code=400, detail="Invalid username.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 chars.")
    salt = os.urandom(16).hex()
    with _db() as conn:
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        if exists:
            raise HTTPException(status_code=409, detail="Username already exists.")
        from datetime import datetime, timezone

        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute(
            "INSERT INTO users (username, salt, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (username, salt, _hash_password(password, salt), created),
        )
    return {"username": username, "created_at": created}


def login(username: str, password: str) -> dict[str, Any]:
    username = (username or "").strip().lower()
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
    if not row or not hmac.compare_digest(
        row["password_hash"], _hash_password(password, row["salt"])
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials.")
    return {
        "access_token": create_token(username),
        "token_type": "bearer",
        "username": username,
    }


def create_token(username: str) -> str:
    payload = _b64(
        json.dumps(
            {"sub": username, "iat": int(time.time()), "exp": int(time.time()) + TOKEN_TTL},
            separators=(",", ":"),
        ).encode()
    )
    return f"{payload}.{_sign(payload)}"


def decode_token(token: str) -> str:
    try:
        payload, signature = token.split(".", 1)
        if not hmac.compare_digest(signature, _sign(payload)):
            raise ValueError("bad signature")
        data = json.loads(_unb64(payload))
        if int(data.get("exp", 0)) < int(time.time()):
            raise ValueError("expired")
        username = str(data.get("sub", ""))
        if not username:
            raise ValueError("missing subject")
        return username
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token.") from exc
