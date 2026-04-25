"""SQLite-backed persistence for news-comet feeds (ADR 0008).

This is the only writer to ``<repo_root>/news_items.db``. It owns:

- ``news_items`` — fetched items keyed by a stable 16-char SHA-256
  prefix of ``(title, url)`` (the same hash :class:`NewsIngestService`
  uses in-process). Raw payload is preserved in ``raw_metadata_json``.
- ``comet_events`` — the lifecycle row attached to a ``news_items`` row.
  ``ON DELETE CASCADE`` is intentionally **not** declared; the cleaner
  in :meth:`cleanup` runs a phase-guarded ``DELETE`` so an aged-out
  parent cannot silently drop a live ``drifting``/``approaching``/
  ``absorbing`` comet (ADR 0008 §4).
- ``feed_cursors`` — per-source incremental polling state (last polled
  at, last item hash, failure count, paused-until). Migrating
  ``_SourceHealth`` backoff into the DB so a restart does not lose the
  signal.

All writes go through a single :class:`threading.Lock` per repository
instance. WAL journal mode is enabled on connect so the existing
``/v1/comets/events`` SSE stream can read concurrently with the
worker. ``:memory:`` mode reuses one ``check_same_thread=False``
connection so the schema and rows survive across transactions during
tests.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import logging
import pathlib
import sqlite3
import threading
import time
from typing import Any, Iterator

from metis_app.models.comet_event import CometEvent, NewsItem

log = logging.getLogger(__name__)

_HERE = pathlib.Path(__file__).resolve().parent
_PACKAGE_ROOT = _HERE.parent
_REPO_ROOT = _PACKAGE_ROOT.parent
_DEFAULT_DB_PATH = _REPO_ROOT / "news_items.db"

_ACTIVE_PHASES: frozenset[str] = frozenset(
    {"entering", "drifting", "approaching", "absorbing"}
)
_TERMINAL_PHASES: frozenset[str] = frozenset({"dismissed", "fading"})


@dataclass(frozen=True, slots=True)
class FeedCursor:
    """Per-source polling cursor."""

    source_channel: str
    source_url: str
    last_polled_at: float = 0.0
    last_success_at: float = 0.0
    last_item_hash: str = ""
    failure_count: int = 0
    paused_until: float = 0.0


@dataclass(frozen=True, slots=True)
class CleanupReport:
    """Counts of rows removed during a single cleanup pass."""

    news_items_evicted: int = 0
    comet_events_evicted: int = 0


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_load(value: str | bytes | None, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


class NewsFeedRepository:
    """Durable home for news-comet items, comets, and per-source cursors."""

    def __init__(self, db_path: str | pathlib.Path | None = None) -> None:
        configured_target = db_path or _DEFAULT_DB_PATH
        self._db_target = (
            ":memory:"
            if configured_target == ":memory:"
            else str(pathlib.Path(configured_target))
        )
        self.db_path = (
            ":memory:"
            if self._db_target == ":memory:"
            else pathlib.Path(self._db_target)
        )
        self._shared_conn: sqlite3.Connection | None = None
        if self._db_target == ":memory:":
            self._shared_conn = sqlite3.connect(
                self._db_target, check_same_thread=False
            )
            self._shared_conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._schema_ready = False

    # ------------------------------------------------------------------
    # Connection management (mirrors AtlasRepository's posture)
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
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        self._ensure_ready()
        conn: sqlite3.Connection | None = None
        with self._lock:
            try:
                if self._shared_conn is not None:
                    conn = self._shared_conn
                else:
                    conn = sqlite3.connect(str(self._db_target), timeout=30.0)
                    conn.row_factory = sqlite3.Row
                    conn.execute("PRAGMA journal_mode=WAL")
                    conn.execute("PRAGMA busy_timeout=30000")
                    conn.execute("PRAGMA foreign_keys=ON")
                conn.execute("BEGIN IMMEDIATE")
                yield conn
                conn.commit()
            except Exception:
                if conn is not None:
                    conn.rollback()
                raise
            finally:
                if conn is not None and conn is not self._shared_conn:
                    conn.close()

    # ------------------------------------------------------------------
    # Schema (lazy, idempotent — ADR 0008 §1)
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        if self._schema_ready:
            return
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS news_items (
                    item_hash         TEXT PRIMARY KEY,
                    item_id           TEXT NOT NULL,
                    title             TEXT NOT NULL,
                    summary           TEXT NOT NULL,
                    url               TEXT NOT NULL,
                    source_channel    TEXT NOT NULL,
                    source_url        TEXT NOT NULL DEFAULT '',
                    published_at      REAL NOT NULL DEFAULT 0.0,
                    fetched_at        REAL NOT NULL,
                    raw_metadata_json TEXT NOT NULL DEFAULT '{}'
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_news_items_fetched "
                "ON news_items (fetched_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_news_items_source "
                "ON news_items (source_channel, source_url, fetched_at DESC)"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS comet_events (
                    comet_id              TEXT PRIMARY KEY,
                    item_hash             TEXT NOT NULL REFERENCES news_items(item_hash),
                    faculty_id            TEXT NOT NULL DEFAULT '',
                    secondary_faculty_id  TEXT NOT NULL DEFAULT '',
                    classification_score  REAL NOT NULL DEFAULT 0.0,
                    decision              TEXT NOT NULL,
                    relevance_score       REAL NOT NULL DEFAULT 0.0,
                    gap_score             REAL NOT NULL DEFAULT 0.0,
                    phase                 TEXT NOT NULL,
                    created_at            REAL NOT NULL,
                    decided_at            REAL NOT NULL DEFAULT 0.0,
                    absorbed_at           REAL NOT NULL DEFAULT 0.0,
                    phase_changed_at      REAL NOT NULL DEFAULT 0.0,
                    atlas_entry_id        TEXT NOT NULL DEFAULT '',
                    notes                 TEXT NOT NULL DEFAULT ''
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_comet_events_phase_changed "
                "ON comet_events (phase, phase_changed_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_comet_events_phase "
                "ON comet_events (phase, created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_comet_events_active "
                "ON comet_events (created_at DESC) "
                "WHERE phase NOT IN ('absorbed','dismissed','fading')"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_comet_events_atlas "
                "ON comet_events (atlas_entry_id) "
                "WHERE atlas_entry_id != ''"
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS feed_cursors (
                    source_channel    TEXT NOT NULL,
                    source_url        TEXT NOT NULL,
                    last_polled_at    REAL NOT NULL DEFAULT 0.0,
                    last_success_at   REAL NOT NULL DEFAULT 0.0,
                    last_item_hash    TEXT NOT NULL DEFAULT '',
                    failure_count     INTEGER NOT NULL DEFAULT 0,
                    paused_until      REAL NOT NULL DEFAULT 0.0,
                    PRIMARY KEY (source_channel, source_url)
                )
                """
            )
        self._schema_ready = True

    def _ensure_ready(self) -> None:
        if not self._schema_ready:
            self.init_db()

    # ------------------------------------------------------------------
    # Hash helper (ADR 0008 §2 — same algorithm as NewsIngestService)
    # ------------------------------------------------------------------

    @staticmethod
    def compute_item_hash(title: str, url: str) -> str:
        raw = f"{title.strip().lower()}|{url.strip().lower()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # news_items
    # ------------------------------------------------------------------

    def add_news_items(
        self, items: list[NewsItem], *, source_url: str = ""
    ) -> list[NewsItem]:
        """Insert *items*. Return the subset that was newly inserted.

        Items already present (by ``item_hash``) are silently skipped —
        the same posture as the in-memory ``_seen_hashes`` cache that
        :meth:`NewsIngestService._dedup` previously owned.
        """
        if not items:
            return []
        new_items: list[NewsItem] = []
        with self._transaction() as conn:
            for item in items:
                if not item.title or not item.url:
                    continue
                item_hash = self.compute_item_hash(item.title, item.url)
                cursor = conn.execute(
                    """
                    INSERT INTO news_items (
                        item_hash, item_id, title, summary, url,
                        source_channel, source_url, published_at,
                        fetched_at, raw_metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(item_hash) DO NOTHING
                    """,
                    (
                        item_hash,
                        item.item_id,
                        item.title,
                        item.summary,
                        item.url,
                        item.source_channel,
                        source_url,
                        float(item.published_at),
                        float(item.fetched_at or time.time()),
                        _json_dumps(item.raw_metadata or {}),
                    ),
                )
                if cursor.rowcount > 0:
                    new_items.append(item)
        return new_items

    def list_known_hashes(self, *, limit: int = 2000) -> list[str]:
        """Return the most recent ``item_hash`` values, newest first.

        Used to warm the in-memory LRU on top of the repo so the
        fast-path dedup check in :class:`NewsIngestService` does not
        round-trip the DB on every poll.
        """
        if limit <= 0:
            return []
        self._ensure_ready()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT item_hash FROM news_items "
                "ORDER BY fetched_at DESC LIMIT ?",
                (int(limit),),
            ).fetchall()
        return [row["item_hash"] for row in rows]

    # ------------------------------------------------------------------
    # comet_events
    # ------------------------------------------------------------------

    def record_comet(
        self, event: CometEvent, *, source_url: str = ""
    ) -> bool:
        """Persist *event* and its parent ``news_items`` row.

        Returns ``True`` if a new comet row was inserted; ``False`` if
        a comet for that ``comet_id`` already existed.
        """
        item = event.news_item
        item_hash = self.compute_item_hash(item.title, item.url)
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO news_items (
                    item_hash, item_id, title, summary, url,
                    source_channel, source_url, published_at,
                    fetched_at, raw_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_hash) DO NOTHING
                """,
                (
                    item_hash,
                    item.item_id,
                    item.title,
                    item.summary,
                    item.url,
                    item.source_channel,
                    source_url,
                    float(item.published_at),
                    float(item.fetched_at or time.time()),
                    _json_dumps(item.raw_metadata or {}),
                ),
            )
            # ``phase_changed_at`` defaults to ``created_at`` so a comet
            # inserted directly into a non-default phase (e.g. tests
            # building "dismissed_old" fixtures) still pivots terminal
            # retention off when the comet entered that phase, not off
            # when it was originally fetched. ``update_phase`` later
            # bumps this on every transition.
            cursor = conn.execute(
                """
                INSERT INTO comet_events (
                    comet_id, item_hash, faculty_id, secondary_faculty_id,
                    classification_score, decision, relevance_score, gap_score,
                    phase, created_at, decided_at, absorbed_at,
                    phase_changed_at, atlas_entry_id, notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', '')
                ON CONFLICT(comet_id) DO NOTHING
                """,
                (
                    event.comet_id,
                    item_hash,
                    event.faculty_id,
                    event.secondary_faculty_id,
                    float(event.classification_score),
                    event.decision,
                    float(event.relevance_score),
                    float(event.gap_score),
                    event.phase,
                    float(event.created_at),
                    float(event.decided_at),
                    float(event.absorbed_at),
                    float(event.created_at),
                ),
            )
            return cursor.rowcount > 0

    def update_phase(
        self,
        comet_id: str,
        phase: str,
        *,
        notes: str | None = None,
        absorbed_at: float | None = None,
        atlas_entry_id: str | None = None,
        phase_changed_at: float | None = None,
    ) -> CometEvent | None:
        """Mutate ``phase`` (and optionally ``notes`` / ``absorbed_at``
        / ``atlas_entry_id``) for *comet_id*.

        ``phase_changed_at`` is bumped on every call (defaults to
        ``time.time()``). Terminal retention in :meth:`cleanup` pivots
        on this column, not ``created_at`` — Codex P2 from PR #545.
        Without it, a comet that drifted for 14 days then got dismissed
        yesterday would be evicted on the next cleanup pass even though
        the dismissal happened well inside the retention window.

        All ``phase`` mutations from route handlers and the worker tick
        funnel through this method (ADR 0008 §Consequences) so the
        cleaner only has one source of truth to guard against.
        """
        sets = ["phase = ?", "phase_changed_at = ?"]
        params: list[Any] = [
            phase,
            float(phase_changed_at if phase_changed_at is not None else time.time()),
        ]
        if notes is not None:
            sets.append("notes = ?")
            params.append(notes)
        if absorbed_at is not None:
            sets.append("absorbed_at = ?")
            params.append(float(absorbed_at))
        if atlas_entry_id is not None:
            sets.append("atlas_entry_id = ?")
            params.append(atlas_entry_id)
        params.append(comet_id)
        with self._transaction() as conn:
            conn.execute(
                f"UPDATE comet_events SET {', '.join(sets)} WHERE comet_id = ?",
                params,
            )
        return self.get_comet(comet_id)

    def get_comet(self, comet_id: str) -> CometEvent | None:
        self._ensure_ready()
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT c.*, n.item_id, n.title, n.summary, n.url,
                       n.source_channel, n.published_at, n.fetched_at,
                       n.raw_metadata_json
                  FROM comet_events c
                  JOIN news_items n ON n.item_hash = c.item_hash
                 WHERE c.comet_id = ?
                """,
                (comet_id,),
            ).fetchone()
        return _row_to_comet(row)

    def list_active(self, *, limit: int | None = None) -> list[CometEvent]:
        """Return non-terminal comets, newest-first."""
        self._ensure_ready()
        sql = """
            SELECT c.*, n.item_id, n.title, n.summary, n.url,
                   n.source_channel, n.published_at, n.fetched_at,
                   n.raw_metadata_json
              FROM comet_events c
              JOIN news_items n ON n.item_hash = c.item_hash
             WHERE c.phase NOT IN ('absorbed','dismissed','fading')
             ORDER BY c.created_at DESC
        """
        params: list[Any] = []
        if limit is not None and limit > 0:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [c for c in (_row_to_comet(r) for r in rows) if c is not None]

    def list_active_count(self) -> int:
        """Cheap counter used by ``poll_comets`` for max-active enforcement."""
        self._ensure_ready()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM comet_events "
                "WHERE phase NOT IN ('absorbed','dismissed','fading')"
            ).fetchone()
        return int(row["n"]) if row else 0

    # ------------------------------------------------------------------
    # feed_cursors
    # ------------------------------------------------------------------

    def get_cursor(
        self, source_channel: str, source_url: str
    ) -> FeedCursor | None:
        self._ensure_ready()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM feed_cursors "
                "WHERE source_channel = ? AND source_url = ?",
                (source_channel, source_url),
            ).fetchone()
        if row is None:
            return None
        return FeedCursor(
            source_channel=row["source_channel"],
            source_url=row["source_url"],
            last_polled_at=float(row["last_polled_at"]),
            last_success_at=float(row["last_success_at"]),
            last_item_hash=row["last_item_hash"] or "",
            failure_count=int(row["failure_count"]),
            paused_until=float(row["paused_until"]),
        )

    def update_cursor(
        self,
        source_channel: str,
        source_url: str,
        *,
        last_polled_at: float | None = None,
        last_success_at: float | None = None,
        last_item_hash: str | None = None,
        failure_count: int | None = None,
        paused_until: float | None = None,
    ) -> FeedCursor:
        """Insert or update a cursor row, returning the fresh state."""
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT INTO feed_cursors (
                    source_channel, source_url, last_polled_at,
                    last_success_at, last_item_hash, failure_count,
                    paused_until
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_channel, source_url) DO UPDATE SET
                    last_polled_at  = COALESCE(?, feed_cursors.last_polled_at),
                    last_success_at = COALESCE(?, feed_cursors.last_success_at),
                    last_item_hash  = COALESCE(?, feed_cursors.last_item_hash),
                    failure_count   = COALESCE(?, feed_cursors.failure_count),
                    paused_until    = COALESCE(?, feed_cursors.paused_until)
                """,
                (
                    source_channel,
                    source_url,
                    float(last_polled_at or 0.0),
                    float(last_success_at or 0.0),
                    last_item_hash or "",
                    int(failure_count or 0),
                    float(paused_until or 0.0),
                    last_polled_at,
                    last_success_at,
                    last_item_hash,
                    failure_count,
                    paused_until,
                ),
            )
        existing = self.get_cursor(source_channel, source_url)
        # The INSERT path always populates a row; this should never be None.
        assert existing is not None  # noqa: S101
        return existing

    # ------------------------------------------------------------------
    # Retention (ADR 0008 §4)
    # ------------------------------------------------------------------

    def cleanup(
        self,
        *,
        now: float | None = None,
        retention_days: int = 14,
        max_rows: int = 50_000,
        terminal_retention_days: int = 7,
        live_atlas_entry_ids: set[str] | None = None,
    ) -> CleanupReport:
        """Apply ADR 0008's retention policy.

        - ``news_items`` evict ``fetched_at < now - retention_days`` AND not
          referenced by an active comet (or by a still-linked absorbed
          comet whose ``atlas_entry_id`` is still in
          *live_atlas_entry_ids*).
        - Same exclusion gates the 50k-row cap.
        - ``comet_events`` evict dismissed/fading older than 7 days,
          plus absorbed-but-unlinked ditto. Linked absorbed comets
          whose ``atlas_entry_id`` no longer exists in
          *live_atlas_entry_ids* are also evicted.

        ``live_atlas_entry_ids`` is caller-supplied so this repository
        does not reach across SQLite files (a Codex P2 fix-forward
        from PR #542). When ``None``, the cleaner treats every linked
        absorbed comet as still-valid (i.e. cannot evict by atlas).
        """
        cutoff_now = float(now if now is not None else time.time())
        items_cutoff = cutoff_now - max(0, retention_days) * 86_400.0
        terminal_cutoff = cutoff_now - max(0, terminal_retention_days) * 86_400.0
        atlas_known = live_atlas_entry_ids if live_atlas_entry_ids is not None else None

        items_removed = 0
        comets_removed = 0
        with self._transaction() as conn:
            # 1) Sweep terminal comets first so the news_items guard
            #    sees the latest set of "still alive" rows.
            #
            # Both queries pivot on ``phase_changed_at`` (set on every
            # ``update_phase`` call) so retention measures time-in-
            # terminal-phase, not time-since-creation. Without this,
            # an old drifting comet that got dismissed yesterday would
            # be evicted today.
            cursor = conn.execute(
                """
                DELETE FROM comet_events
                 WHERE phase IN ('dismissed','fading')
                   AND phase_changed_at < ?
                """,
                (terminal_cutoff,),
            )
            comets_removed += cursor.rowcount or 0

            cursor = conn.execute(
                """
                DELETE FROM comet_events
                 WHERE phase = 'absorbed'
                   AND atlas_entry_id = ''
                   AND phase_changed_at < ?
                """,
                (terminal_cutoff,),
            )
            comets_removed += cursor.rowcount or 0

            if atlas_known is not None:
                # Evict linked absorbed comets whose target atlas entry
                # no longer exists. Do the filter in Python so we do
                # not reach across SQLite files.
                rows = conn.execute(
                    """
                    SELECT comet_id, atlas_entry_id FROM comet_events
                     WHERE phase = 'absorbed' AND atlas_entry_id != ''
                    """
                ).fetchall()
                stale = [
                    row["comet_id"]
                    for row in rows
                    if row["atlas_entry_id"] not in atlas_known
                ]
                for comet_id in stale:
                    conn.execute(
                        "DELETE FROM comet_events WHERE comet_id = ?",
                        (comet_id,),
                    )
                comets_removed += len(stale)

            # 2) Sweep aged-out news_items, guarded by the active /
            #    linked-absorbed exclusion.
            cursor = conn.execute(
                """
                DELETE FROM news_items
                 WHERE fetched_at < ?
                   AND item_hash NOT IN (
                       SELECT item_hash FROM comet_events
                        WHERE phase IN ('entering','drifting','approaching','absorbing')
                           OR (phase = 'absorbed' AND atlas_entry_id != '')
                   )
                """,
                (items_cutoff,),
            )
            items_removed += cursor.rowcount or 0

            # 3) Hard row cap. Same exclusion as above; no orphaning.
            if max_rows > 0:
                rows_above_cap = conn.execute(
                    "SELECT COUNT(*) AS n FROM news_items"
                ).fetchone()
                total = int(rows_above_cap["n"]) if rows_above_cap else 0
                excess = max(0, total - int(max_rows))
                if excess > 0:
                    cursor = conn.execute(
                        """
                        DELETE FROM news_items
                         WHERE item_hash IN (
                             SELECT item_hash FROM news_items
                              WHERE item_hash NOT IN (
                                  SELECT item_hash FROM comet_events
                                   WHERE phase IN ('entering','drifting','approaching','absorbing')
                                      OR (phase = 'absorbed' AND atlas_entry_id != '')
                              )
                              ORDER BY fetched_at ASC
                              LIMIT ?
                         )
                        """,
                        (excess,),
                    )
                    items_removed += cursor.rowcount or 0

        return CleanupReport(
            news_items_evicted=items_removed,
            comet_events_evicted=comets_removed,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_comet(row: sqlite3.Row | None) -> CometEvent | None:
    if row is None:
        return None
    raw_metadata = _json_load(row["raw_metadata_json"], {})
    if not isinstance(raw_metadata, dict):
        raw_metadata = {}
    item = NewsItem(
        item_id=row["item_id"],
        title=row["title"],
        summary=row["summary"],
        url=row["url"],
        source_channel=row["source_channel"],
        published_at=float(row["published_at"]),
        fetched_at=float(row["fetched_at"]),
        raw_metadata=raw_metadata,
    )
    return CometEvent(
        comet_id=row["comet_id"],
        news_item=item,
        faculty_id=row["faculty_id"],
        secondary_faculty_id=row["secondary_faculty_id"],
        classification_score=float(row["classification_score"]),
        decision=row["decision"],
        relevance_score=float(row["relevance_score"]),
        gap_score=float(row["gap_score"]),
        phase=row["phase"],
        created_at=float(row["created_at"]),
        decided_at=float(row["decided_at"]),
        absorbed_at=float(row["absorbed_at"]),
    )


# ---------------------------------------------------------------------------
# Module-level default singleton (lazy)
# ---------------------------------------------------------------------------


_default_repo: NewsFeedRepository | None = None
_default_repo_lock = threading.Lock()


def get_default_repository(
    db_path: str | pathlib.Path | None = None,
) -> NewsFeedRepository:
    """Return a process-wide default repository instance.

    *db_path* is honoured only on first call; subsequent calls return
    the existing singleton. Tests that need an isolated DB should
    construct their own ``NewsFeedRepository(":memory:")`` instead.
    """
    global _default_repo
    with _default_repo_lock:
        if _default_repo is None:
            _default_repo = NewsFeedRepository(db_path)
        return _default_repo


def reset_default_repository(repo: NewsFeedRepository | None = None) -> None:
    """Replace the module-level singleton (test affordance)."""
    global _default_repo
    with _default_repo_lock:
        _default_repo = repo
