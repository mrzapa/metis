"""SQLite-backed key-value store for agent-native application state (Surface 1)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import pathlib
import sqlite3
from typing import Iterator

_HERE = pathlib.Path(__file__).resolve().parent
_PACKAGE_ROOT = _HERE.parent
_REPO_ROOT = _PACKAGE_ROOT.parent
_DEFAULT_DB_PATH = _REPO_ROOT / "app_state.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class AppStateService:
    """SQLite-backed KV store for per-session agent state.

    Values are stored as TEXT; callers are responsible for JSON serialization.
    A global version counter is atomically incremented on every write so that
    readers can detect stale caches without row-level change tracking.
    """

    def __init__(self, db_path: str | pathlib.Path | None = None) -> None:
        if db_path is None:
            self._db_target = str(_DEFAULT_DB_PATH)
        elif str(db_path) == ":memory:":
            self._db_target = ":memory:"
        else:
            self._db_target = str(pathlib.Path(db_path))

        self._shared_conn: sqlite3.Connection | None = None

        if self._db_target == ":memory:":
            self._shared_conn = sqlite3.connect(
                ":memory:",
                check_same_thread=False,
            )
            self._shared_conn.row_factory = sqlite3.Row

        self.init_db()

    # ------------------------------------------------------------------
    # Internal connection helpers
    # ------------------------------------------------------------------

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self._shared_conn is not None:
            yield self._shared_conn
            self._shared_conn.commit()
            return

        target = pathlib.Path(self._db_target)
        target.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(target), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """Explicit transaction context for multi-statement atomic operations."""
        if self._shared_conn is not None:
            self._shared_conn.execute("BEGIN")
            try:
                yield self._shared_conn
                self._shared_conn.commit()
            except Exception:
                self._shared_conn.rollback()
                raise
            return

        target = pathlib.Path(self._db_target)
        target.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(target), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("BEGIN")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Schema initialisation
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        """Create tables and seed version_counter row if not present."""
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS app_state (
                    session_id TEXT NOT NULL,
                    key        TEXT NOT NULL,
                    value      TEXT NOT NULL,
                    version    INTEGER NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, key)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS version_counter (
                    id      INTEGER PRIMARY KEY,
                    version INTEGER DEFAULT 0,
                    CHECK (id = 1)
                )
                """
            )
            conn.execute(
                "INSERT OR IGNORE INTO version_counter (id, version) VALUES (1, 0)"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def read(self, session_id: str, key: str) -> str | None:
        """Return the stored value for (session_id, key), or None if absent."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_state WHERE session_id = ? AND key = ?",
                (session_id, key),
            ).fetchone()
        return row["value"] if row else None

    def read_entry(self, session_id: str, key: str) -> dict | None:
        """Return the full row for (session_id, key) as a dict, or None if absent.

        Dict keys: key, value, version, updated_at.
        """
        with self._connect() as conn:
            row = conn.execute(
                "SELECT key, value, version, updated_at FROM app_state"
                " WHERE session_id = ? AND key = ?",
                (session_id, key),
            ).fetchone()
        return dict(row) if row else None

    def write(self, session_id: str, key: str, value: str) -> int:
        """Upsert (session_id, key) → value and atomically increment the global version.

        Returns the new global version integer.
        """
        with self._transaction() as conn:
            conn.execute(
                "UPDATE version_counter SET version = version + 1 WHERE id = 1"
            )
            row = conn.execute(
                "SELECT version FROM version_counter WHERE id = 1"
            ).fetchone()
            new_version: int = row["version"]
            conn.execute(
                """
                INSERT OR REPLACE INTO app_state
                    (session_id, key, value, version, updated_at)
                VALUES
                    (?, ?, ?, ?, ?)
                """,
                (session_id, key, value, new_version, _now_iso()),
            )
        return new_version

    def delete(self, session_id: str, key: str) -> None:
        """Remove the (session_id, key) row if it exists."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM app_state WHERE session_id = ? AND key = ?",
                (session_id, key),
            )

    def list(self, session_id: str) -> list[dict]:
        """Return all KV entries for session_id as a list of dicts.

        Each dict contains: key, value, version, updated_at.
        """
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT key, value, version, updated_at
                FROM app_state
                WHERE session_id = ?
                ORDER BY key
                """,
                (session_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_version(self) -> int:
        """Return the current global version counter value."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT version FROM version_counter WHERE id = 1"
            ).fetchone()
        return row["version"] if row else 0
