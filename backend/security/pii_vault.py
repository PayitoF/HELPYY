"""PII Vault — stores and retrieves token↔value mappings with TTL.

SQLite for local development, DynamoDB for production.
Controlled by DATABASE_TYPE env var.
"""

import json
import os
import sqlite3
import time
import threading
from pathlib import Path

_TTL_HOURS = int(os.getenv("PII_VAULT_TTL_HOURS", "24"))
_DB_PATH = os.getenv("SQLITE_DB_PATH", "data/helpyy.db")


class PIIVault:
    """Store and retrieve PII token mappings per session with automatic expiry."""

    def __init__(self, db_path: str | None = None, ttl_hours: int | None = None):
        self._db_path = db_path or _DB_PATH
        self._ttl_seconds = (ttl_hours if ttl_hours is not None else _TTL_HOURS) * 3600
        self._local = threading.local()
        self._ensure_table()

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    def store(self, session_id: str, mapping: dict[str, str]) -> None:
        """Store or merge a token mapping for a session.

        Args:
            session_id: Chat session identifier.
            mapping: {token: original_value} pairs to store.
        """
        conn = self._conn()
        existing = self._load_raw(conn, session_id)
        if existing is not None:
            existing.update(mapping)
            mapping = existing

        expires_at = time.time() + self._ttl_seconds
        conn.execute(
            "INSERT OR REPLACE INTO pii_vault (session_id, mapping, expires_at) VALUES (?, ?, ?)",
            (session_id, json.dumps(mapping, ensure_ascii=False), expires_at),
        )
        conn.commit()

    def retrieve(self, session_id: str) -> dict[str, str] | None:
        """Retrieve the token mapping for a session (returns None if expired)."""
        conn = self._conn()
        self._purge_expired(conn)
        return self._load_raw(conn, session_id)

    def delete(self, session_id: str) -> None:
        """Delete all PII data for a session."""
        conn = self._conn()
        conn.execute("DELETE FROM pii_vault WHERE session_id = ?", (session_id,))
        conn.commit()

    # ------------------------------------------------------------------
    # internal
    # ------------------------------------------------------------------

    def _conn(self) -> sqlite3.Connection:
        """Thread-local SQLite connection."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn = conn
        return conn

    def _ensure_table(self) -> None:
        conn = self._conn()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pii_vault (
                session_id TEXT PRIMARY KEY,
                mapping    TEXT NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )
        conn.commit()

    def _load_raw(self, conn: sqlite3.Connection, session_id: str) -> dict[str, str] | None:
        row = conn.execute(
            "SELECT mapping, expires_at FROM pii_vault WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        mapping_json, expires_at = row
        if time.time() > expires_at:
            conn.execute("DELETE FROM pii_vault WHERE session_id = ?", (session_id,))
            conn.commit()
            return None
        return json.loads(mapping_json)

    def _purge_expired(self, conn: sqlite3.Connection) -> None:
        conn.execute("DELETE FROM pii_vault WHERE expires_at < ?", (time.time(),))
        conn.commit()
