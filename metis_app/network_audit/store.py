"""SQLite-backed rolling store for :class:`NetworkAuditEvent`.

The store is bounded: at most ``max_rows`` events (default 50,000) and
at most ``max_age_seconds`` old (default 30 days), whichever is
smaller. Eviction runs opportunistically every ~100 appends and
unconditionally on :meth:`NetworkAuditStore.vacuum`.

See ``docs/adr/0011-network-audit-retention.md`` for the retention
policy rationale and schema-migration posture. See
``plans/network-audit/plan.md`` (Phase 2) for the scope constraints
(no call-site wrapping yet, no API routes yet).

The store mirrors the rolling-bounded-store pattern used by
``metis_app/services/trace_store.py`` structurally, but persists to
SQLite (not JSON-lines) so that per-provider count queries needed by
the Phase 5 panel are O(log n) rather than O(n).
"""

from __future__ import annotations

import os
import pathlib
import secrets
import sqlite3
import threading
import time
from collections.abc import Iterator
from datetime import datetime, timezone

from metis_app.network_audit.events import NetworkAuditEvent

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_HERE = pathlib.Path(__file__).resolve().parent
_PACKAGE_ROOT = _HERE.parent
_REPO_ROOT = _PACKAGE_ROOT.parent
DEFAULT_DB_PATH = _REPO_ROOT / "network_audit.db"
"""Default database location — sits next to ``skill_candidates.db``."""

DEFAULT_MAX_ROWS = 50_000
"""Rolling cap by row count."""

DEFAULT_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
"""Rolling cap by age (30 days in seconds)."""

_EVICTION_CHECK_INTERVAL = 100
"""Run opportunistic eviction every N appends to keep per-append cost low."""


# ---------------------------------------------------------------------------
# ULID generation (stdlib-only)
# ---------------------------------------------------------------------------

# Crockford base32 alphabet — 32 characters, no I/L/O/U to avoid
# visual confusion. Canonical reference: https://www.crockford.com/base32.html
_CROCKFORD_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode_crockford_base32(value: int, length: int) -> str:
    """Encode ``value`` as a ``length``-character Crockford base32 string."""
    chars: list[str] = []
    for _ in range(length):
        chars.append(_CROCKFORD_ALPHABET[value & 0x1F])
        value >>= 5
    return "".join(reversed(chars))


def new_ulid() -> str:
    """Return a 26-character ULID-compatible identifier.

    A ULID is 128 bits: 48-bit big-endian millisecond timestamp
    followed by 80 bits of randomness, encoded as 26 Crockford-base32
    characters. Matches the ULID spec closely enough that any ULID
    parser will accept our IDs; we do not pull in an external
    ``ulid-py`` dependency for one helper.

    Lexicographic sort order matches chronological order for IDs
    generated in the same millisecond bucket (the random suffix
    breaks ties non-monotonically; monotonic ULIDs are a v2 concern
    if we ever need strict ordering within a millisecond).
    """
    # 48-bit millisecond timestamp. time.time_ns() avoids the float
    # rounding that would clip the low bit on very recent systems.
    timestamp_ms = time.time_ns() // 1_000_000
    timestamp_part = _encode_crockford_base32(timestamp_ms & ((1 << 48) - 1), 10)
    # 80 bits of randomness. secrets.token_bytes is CSPRNG-backed; we
    # could use os.urandom directly but secrets is the documented
    # stdlib entry point for cryptographic randomness.
    random_int = int.from_bytes(secrets.token_bytes(10), "big")
    random_part = _encode_crockford_base32(random_int, 16)
    return timestamp_part + random_part


# ---------------------------------------------------------------------------
# Synthetic event helper (shared by tests; co-located with the store
# as the Phase 2 spec allows)
# ---------------------------------------------------------------------------


def make_synthetic_event(
    *,
    provider_key: str = "unclassified",
    trigger_feature: str = "synthetic_pass",
    method: str = "GET",
    url_host: str = "example.com",
    url_path_prefix: str = "/v1",
    timestamp: datetime | None = None,
    size_bytes_in: int | None = None,
    size_bytes_out: int | None = None,
    latency_ms: int | None = None,
    status_code: int | None = None,
    user_initiated: bool = False,
    blocked: bool = False,
    event_id: str | None = None,
    source: str = "stdlib_urlopen",
) -> NetworkAuditEvent:
    """Construct a :class:`NetworkAuditEvent` with sensible defaults.

    Useful in tests and for the Phase 6 "prove offline" synthetic
    pass. Every field is overridable; the defaults produce a valid
    event without any argument. ``source`` defaults to
    ``"stdlib_urlopen"`` to match the pre-Phase-4 semantics; pass
    ``source="sdk_invocation"`` to construct an SDK-layer event.
    """
    # The Literal-typed param is narrowed inside NetworkAuditEvent;
    # we accept a bare ``str`` here so callers can build synthetic
    # invalid events in tests without fighting mypy.
    return NetworkAuditEvent(
        id=event_id or new_ulid(),
        timestamp=timestamp or datetime.now(timezone.utc),
        method=method,
        url_host=url_host,
        url_path_prefix=url_path_prefix,
        query_params_stored=False,
        provider_key=provider_key,
        trigger_feature=trigger_feature,
        size_bytes_in=size_bytes_in,
        size_bytes_out=size_bytes_out,
        latency_ms=latency_ms,
        status_code=status_code,
        user_initiated=user_initiated,
        blocked=blocked,
        source=source,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


_SCHEMA = """
CREATE TABLE IF NOT EXISTS network_audit_events (
    id               TEXT PRIMARY KEY,
    timestamp_ms     INTEGER NOT NULL,
    method           TEXT NOT NULL,
    url_host         TEXT NOT NULL,
    url_path_prefix  TEXT NOT NULL,
    provider_key     TEXT NOT NULL,
    trigger_feature  TEXT NOT NULL,
    size_bytes_in    INTEGER,
    size_bytes_out   INTEGER,
    latency_ms       INTEGER,
    status_code      INTEGER,
    user_initiated   INTEGER NOT NULL,
    blocked          INTEGER NOT NULL,
    source           TEXT NOT NULL DEFAULT 'stdlib_urlopen'
)
"""

# Phase 4 migration: columns that may need to be added to a pre-existing
# ``network_audit_events`` table. The tuple format is
# ``(column_name, column_sql_fragment)``. ``_ensure_columns`` iterates in
# order, adding any column that is not already present via
# ``ALTER TABLE ... ADD COLUMN`` with a literal default so existing rows
# are backfilled atomically. SQLite supports this in a single DDL call.
#
# Keep this list minimal; once a field has been added and shipped for a
# release cycle, it should remain here for the benefit of rolling
# installs (the entry is a no-op on schemas that already carry the
# column). Removal requires a separate migration.
_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("source", "source TEXT NOT NULL DEFAULT 'stdlib_urlopen'"),
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON network_audit_events (timestamp_ms)",
    "CREATE INDEX IF NOT EXISTS idx_audit_provider ON network_audit_events (provider_key, timestamp_ms)",
)


def _timestamp_to_ms(ts: datetime) -> int:
    """Convert a tz-aware datetime to UNIX epoch milliseconds."""
    # NetworkAuditEvent enforces tz-awareness in __post_init__.
    return int(ts.timestamp() * 1000)


def _timestamp_from_ms(ms: int) -> datetime:
    """Inverse of :func:`_timestamp_to_ms`."""
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


class NetworkAuditStore:
    """SQLite-backed rolling store for audit events.

    Concurrency: ``sqlite3.Connection`` is opened with
    ``check_same_thread=False`` and all writes are serialised by a
    single ``threading.Lock``. Litestar is async but stdlib
    ``sqlite3`` is not asyncio-friendly; the lock is held for
    sub-millisecond inserts and is acceptable at the expected
    throughput (dozens of events per minute at peak).

    WAL journal mode is enabled on connect so concurrent reads
    from the Phase 5 API routes do not block the writer.
    """

    def __init__(
        self,
        db_path: pathlib.Path | str | None = None,
        *,
        max_rows: int = DEFAULT_MAX_ROWS,
        max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS,
    ) -> None:
        if db_path is not None:
            self.db_path = pathlib.Path(db_path)
        else:
            env_override = os.environ.get("METIS_NETWORK_AUDIT_DB_PATH")
            self.db_path = pathlib.Path(env_override) if env_override else DEFAULT_DB_PATH
        self.max_rows = int(max_rows)
        self.max_age_seconds = int(max_age_seconds)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._conn: sqlite3.Connection | None = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            isolation_level=None,  # autocommit; we wrap multi-statement in explicit tx
            timeout=30.0,
        )
        self._appends_since_eviction = 0
        self._closed = False

        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA busy_timeout=30000")
        self._conn.execute(_SCHEMA)
        for statement in _INDEXES:
            self._conn.execute(statement)
        # Apply pending column migrations. Fresh installs land on the
        # current ``_SCHEMA`` directly; this step is only meaningful for
        # DBs that pre-date a later column addition (e.g. pre-Phase-4
        # tables without ``source``). See ``_MIGRATIONS``.
        self._apply_column_migrations()

    def _apply_column_migrations(self) -> None:
        """Add any missing columns from ``_MIGRATIONS`` via ``ALTER TABLE``.

        SQLite's ``ALTER TABLE ... ADD COLUMN ... DEFAULT <value>`` fills
        all existing rows with the literal default in a single DDL call.
        That matches the Phase 4 requirement: a rolling install with a
        13-column DB gets the 14th column seamlessly and pre-existing
        rows report ``source='stdlib_urlopen'`` (the pre-Phase-4
        semantic default). Idempotent — entries whose column already
        exists are skipped.
        """
        assert self._conn is not None
        existing = {
            row[1]
            for row in self._conn.execute(
                "PRAGMA table_info(network_audit_events)"
            )
        }
        for column_name, column_sql in _MIGRATIONS:
            if column_name not in existing:
                self._conn.execute(
                    f"ALTER TABLE network_audit_events ADD COLUMN {column_sql}"
                )

    # ------------------------------------------------------------------
    # Write path
    # ------------------------------------------------------------------

    def append(self, event: NetworkAuditEvent) -> None:
        """Persist ``event``. Runs opportunistic eviction every ~100 calls."""
        conn = self._require_conn()
        row = (
            event.id,
            _timestamp_to_ms(event.timestamp),
            event.method,
            event.url_host,
            event.url_path_prefix,
            event.provider_key,
            event.trigger_feature,
            event.size_bytes_in,
            event.size_bytes_out,
            event.latency_ms,
            event.status_code,
            1 if event.user_initiated else 0,
            1 if event.blocked else 0,
            event.source,
        )
        with self._lock:
            conn.execute(
                "INSERT OR REPLACE INTO network_audit_events "
                "(id, timestamp_ms, method, url_host, url_path_prefix, "
                "provider_key, trigger_feature, size_bytes_in, size_bytes_out, "
                "latency_ms, status_code, user_initiated, blocked, source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                row,
            )
            self._appends_since_eviction += 1
            if self._appends_since_eviction >= _EVICTION_CHECK_INTERVAL:
                self._evict_locked()
                self._appends_since_eviction = 0

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------

    def recent(self, limit: int = 100) -> list[NetworkAuditEvent]:
        """Return the ``limit`` most recent events, newest-first."""
        conn = self._require_conn()
        cursor = conn.execute(
            "SELECT id, timestamp_ms, method, url_host, url_path_prefix, "
            "provider_key, trigger_feature, size_bytes_in, size_bytes_out, "
            "latency_ms, status_code, user_initiated, blocked, source "
            "FROM network_audit_events "
            "ORDER BY timestamp_ms DESC, id DESC LIMIT ?",
            (int(limit),),
        )
        return [_row_to_event(row) for row in cursor.fetchall()]

    def recent_by_provider(
        self, provider_key: str, limit: int = 100
    ) -> list[NetworkAuditEvent]:
        """Return the ``limit`` most recent events for a given provider key."""
        conn = self._require_conn()
        cursor = conn.execute(
            "SELECT id, timestamp_ms, method, url_host, url_path_prefix, "
            "provider_key, trigger_feature, size_bytes_in, size_bytes_out, "
            "latency_ms, status_code, user_initiated, blocked, source "
            "FROM network_audit_events "
            "WHERE provider_key = ? "
            "ORDER BY timestamp_ms DESC, id DESC LIMIT ?",
            (str(provider_key), int(limit)),
        )
        return [_row_to_event(row) for row in cursor.fetchall()]

    def count_recent(self, window_seconds: int = 300) -> int:
        """Return the number of events in the last ``window_seconds``."""
        conn = self._require_conn()
        cutoff_ms = int((time.time() - float(window_seconds)) * 1000)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM network_audit_events WHERE timestamp_ms >= ?",
            (cutoff_ms,),
        )
        return int(cursor.fetchone()[0])

    def count_recent_by_provider(
        self, provider_key: str, window_seconds: int
    ) -> int:
        """Return the number of events for ``provider_key`` in the last window.

        Used by the Phase 5 audit panel to populate the ``events_7d``
        column in the provider matrix. Served by the
        ``idx_audit_provider`` composite index (``provider_key,
        timestamp_ms``) so the query cost is O(log n + match_count)
        rather than a full table scan.

        Passing an unknown provider key returns ``0`` — not an error;
        the panel iterates :data:`KNOWN_PROVIDERS` and some entries
        (notably ``rss_feed``, ``weaviate``) may never have been hit.
        """
        conn = self._require_conn()
        cutoff_ms = int((time.time() - float(window_seconds)) * 1000)
        cursor = conn.execute(
            "SELECT COUNT(*) FROM network_audit_events "
            "WHERE provider_key = ? AND timestamp_ms >= ?",
            (str(provider_key), cutoff_ms),
        )
        return int(cursor.fetchone()[0])

    def max_rowid(self) -> int:
        """Return the current maximum ``rowid`` in the events table.

        Used by the SSE stream to prime its watermark so clients that
        connect to the live stream skip events that were inserted
        before the connection. A value of ``0`` is returned for an
        empty table — any subsequent insert will produce a rowid ≥ 1.

        SQLite's implicit ``rowid`` is guaranteed to strictly increase
        on every INSERT against a ROWID table (our table has a TEXT
        primary key, so it keeps the implicit rowid). This gives us a
        monotonic stream cursor that does not depend on ULID ordering
        — the 80-bit random suffix on :func:`new_ulid` is not
        monotonic within a millisecond, so an id-based watermark can
        silently skip same-ms events. See :meth:`events_after`.
        """
        conn = self._require_conn()
        cursor = conn.execute(
            "SELECT COALESCE(MAX(rowid), 0) FROM network_audit_events"
        )
        return int(cursor.fetchone()[0])

    def iter_events_since(
        self, cutoff_ms: int, *, chunk_size: int = 1000
    ) -> Iterator[NetworkAuditEvent]:
        """Yield events with ``timestamp_ms >= cutoff_ms`` in chronological order.

        Walks the table in ``chunk_size`` batches using the implicit
        ``rowid`` as the cursor. The rowid walk is stable under
        concurrent inserts (new rows get higher rowids, so they land
        after the current cursor position) and avoids buffering the
        full 30-day / 50k-row retention window in memory — the Phase 7
        CSV export streams rows directly from this generator into the
        response body.

        Ordering is by ``rowid ASC``, which for a given retention
        window is effectively ``timestamp_ms ASC`` plus per-millisecond
        insert order — good enough for a chronological CSV. Switching
        to an explicit ``ORDER BY timestamp_ms ASC`` here would force a
        temp-table sort for no practical gain at the store's size cap.

        Args:
            cutoff_ms: Lower bound (inclusive) on ``timestamp_ms``.
                Events older than this are filtered out at the SQL
                layer so we never yield them.
            chunk_size: SELECT page size. Must be >= 1. Defaults to
                1000.

        Raises:
            RuntimeError: If the store has been closed.
        """
        conn = self._require_conn()
        if chunk_size < 1:
            chunk_size = 1
        cursor_rowid = 0
        while True:
            rows = conn.execute(
                "SELECT rowid, id, timestamp_ms, method, url_host, url_path_prefix, "
                "provider_key, trigger_feature, size_bytes_in, size_bytes_out, "
                "latency_ms, status_code, user_initiated, blocked, source "
                "FROM network_audit_events "
                "WHERE rowid > ? AND timestamp_ms >= ? "
                "ORDER BY rowid ASC LIMIT ?",
                (int(cursor_rowid), int(cutoff_ms), int(chunk_size)),
            ).fetchall()
            if not rows:
                return
            for row in rows:
                cursor_rowid = int(row[0])
                yield _row_to_event(row[1:])
            if len(rows) < chunk_size:
                return

    def events_after(
        self, after_rowid: int, limit: int
    ) -> list[tuple[int, NetworkAuditEvent]]:
        """Return events with ``rowid > after_rowid``, chronological (oldest-first).

        Returns a list of ``(rowid, event)`` pairs so the caller can
        advance its watermark per-event without re-reading the row's
        metadata. Ordering is by ``rowid`` ASC, which is a monotonic
        SQLite-internal counter — immune to ULID tie-ordering issues
        within a single millisecond.

        The SSE stream uses this as its primary cursor. It polls
        periodically with ``after_rowid = last_emitted_rowid`` and
        drains in chunks of ``limit`` rows; if the returned batch
        equals ``limit``, more events may still be queued and the
        caller should loop without sleeping until the batch is
        partial. This guarantees no silent drops under bursty traffic
        (>limit events between two polls).
        """
        conn = self._require_conn()
        cursor = conn.execute(
            "SELECT rowid, id, timestamp_ms, method, url_host, url_path_prefix, "
            "provider_key, trigger_feature, size_bytes_in, size_bytes_out, "
            "latency_ms, status_code, user_initiated, blocked, source "
            "FROM network_audit_events "
            "WHERE rowid > ? ORDER BY rowid ASC LIMIT ?",
            (int(after_rowid), int(limit)),
        )
        return [(int(row[0]), _row_to_event(row[1:])) for row in cursor.fetchall()]

    # ------------------------------------------------------------------
    # Retention
    # ------------------------------------------------------------------

    def vacuum(self) -> None:
        """Evict over-age and over-count rows, then run SQLite VACUUM.

        Intended to be called on app startup before the API routes
        begin serving requests, and on-demand by the panel's manual
        compaction affordance (Phase 5+).
        """
        with self._lock:
            self._evict_locked()
            self._appends_since_eviction = 0
            # VACUUM must run outside any transaction. The connection
            # uses isolation_level=None (autocommit), so this is safe.
            assert self._conn is not None
            self._conn.execute("VACUUM")

    def _evict_locked(self) -> None:
        """Drop rows older than ``max_age_seconds`` and over the row cap.

        Caller MUST hold ``self._lock``.
        """
        conn = self._require_conn()
        # Over-age eviction.
        age_cutoff_ms = int((time.time() - float(self.max_age_seconds)) * 1000)
        conn.execute(
            "DELETE FROM network_audit_events WHERE timestamp_ms < ?",
            (age_cutoff_ms,),
        )
        # Over-count eviction: delete the oldest rows beyond the cap.
        cursor = conn.execute("SELECT COUNT(*) FROM network_audit_events")
        count = int(cursor.fetchone()[0])
        if count > self.max_rows:
            overflow = count - self.max_rows
            conn.execute(
                "DELETE FROM network_audit_events WHERE id IN ("
                "SELECT id FROM network_audit_events "
                "ORDER BY timestamp_ms ASC, id ASC LIMIT ?"
                ")",
                (overflow,),
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying connection. Idempotent."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._conn is not None:
                try:
                    self._conn.close()
                finally:
                    self._conn = None

    def _require_conn(self) -> sqlite3.Connection:
        if self._closed or self._conn is None:
            raise RuntimeError("NetworkAuditStore is closed")
        return self._conn

    # Context-manager convenience for test ergonomics.
    def __enter__(self) -> "NetworkAuditStore":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()


def _row_to_event(row: tuple) -> NetworkAuditEvent:  # pragma: no cover - trivial
    """Convert a SQLite row tuple back to a :class:`NetworkAuditEvent`."""
    (
        id_,
        timestamp_ms,
        method,
        url_host,
        url_path_prefix,
        provider_key,
        trigger_feature,
        size_bytes_in,
        size_bytes_out,
        latency_ms,
        status_code,
        user_initiated,
        blocked,
        source,
    ) = row
    # ``source`` is a Literal-typed Python field but comes back as a
    # bare string from SQLite. The Literal validator in ``__post_init__``
    # will reject an unknown value, so a corrupted row fails loudly
    # rather than propagating a garbled label into the UI.
    return NetworkAuditEvent(
        id=id_,
        timestamp=_timestamp_from_ms(int(timestamp_ms)),
        method=method,
        url_host=url_host,
        url_path_prefix=url_path_prefix,
        query_params_stored=False,
        provider_key=provider_key,
        trigger_feature=trigger_feature,
        size_bytes_in=size_bytes_in,
        size_bytes_out=size_bytes_out,
        latency_ms=latency_ms,
        status_code=status_code,
        user_initiated=bool(user_initiated),
        blocked=bool(blocked),
        source=source,
    )


__all__ = [
    "DEFAULT_DB_PATH",
    "DEFAULT_MAX_AGE_SECONDS",
    "DEFAULT_MAX_ROWS",
    "NetworkAuditStore",
    "make_synthetic_event",
    "new_ulid",
]
