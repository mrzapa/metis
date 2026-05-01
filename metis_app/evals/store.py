"""SQLite-backed persistence for personal evals (M16).

ADR 0017 picks a dedicated ``evals.db`` over reusing
``rag_sessions.db`` so eval evolution is decoupled from chat/session
persistence. The store owns three tables:

- ``tasks``       — corpus rows derived from reinforce-labeled traces.
- ``runs``        — per-execution records keyed by ``generation_id``.
- ``generations`` — content-addressed companion fingerprints (ADR 0017
  §4) so week-over-week comparisons stay honest across model swaps,
  skill promotions, and (eventually) LoRA adapters.

The Phase 3 runner, the grading lanes, and the report surface layer on
top of this module. Phase 2 only delivers the schema, dataclasses, and
CRUD primitives plus a default-store singleton with an env override.
"""

from __future__ import annotations

import os
import pathlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator

DEFAULT_DB_ENV_VAR = "METIS_EVALS_DB_PATH"

_HERE = pathlib.Path(__file__).resolve().parent
_PACKAGE_ROOT = _HERE.parent
_REPO_ROOT = _PACKAGE_ROOT.parent
_DEFAULT_DB_PATH = _REPO_ROOT / "evals.db"


@dataclass(frozen=True)
class EvalTaskRow:
    """Storage shape for ``tasks`` rows.

    The logical task model lives in ``corpus.EvalTask``; this row
    flattens it into the JSON-blob shape ADR 0017 chose so the corpus
    schema can evolve without further SQLite migrations.
    """

    task_id: str
    created_at: str
    task_type: str
    source_run_id: str | None
    payload_json: str
    tags_json: str


@dataclass(frozen=True)
class EvalRun:
    """Storage shape for ``runs`` rows."""

    run_id: str
    task_id: str
    generation_id: str
    created_at: str
    trace_run_id: str
    signals_json: str
    aggregate_score: float | None
    output_text: str
    review_required: bool


@dataclass(frozen=True)
class EvalGeneration:
    """Storage shape for ``generations`` rows."""

    generation_id: str
    first_seen_at: str
    runtime_spec_json: str
    lora_adapter_id: str | None
    skill_set_hash: str
    settings_hash: str
    notes: str


def _resolve_db_path(db_path: str | pathlib.Path | None) -> str:
    if db_path is not None:
        if db_path == ":memory:":
            return ":memory:"
        return str(db_path)
    env_path = os.environ.get(DEFAULT_DB_ENV_VAR, "").strip()
    if env_path:
        return env_path
    return str(_DEFAULT_DB_PATH)


class EvalStore:
    """SQLite-backed eval persistence.

    The constructor accepts an explicit ``db_path``. When ``None`` (the
    default for the module-level singleton) the store consults
    ``METIS_EVALS_DB_PATH`` and falls back to ``<repo>/evals.db`` so
    tests can isolate via env-var override without monkeypatching the
    constructor.
    """

    def __init__(self, db_path: str | pathlib.Path | None = None) -> None:
        target = _resolve_db_path(db_path)
        self.db_path = pathlib.Path(target) if target != ":memory:" else None
        self._db_target = target
        self._shared_conn: sqlite3.Connection | None = None
        if target == ":memory:":
            self._shared_conn = sqlite3.connect(target, check_same_thread=False)
            self._shared_conn.row_factory = sqlite3.Row

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self._shared_conn is not None:
            yield self._shared_conn
            self._shared_conn.commit()
            return
        assert self.db_path is not None
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks(
                    task_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    task_type TEXT NOT NULL,
                    source_run_id TEXT,
                    payload_json TEXT NOT NULL,
                    tags_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_tasks_type ON tasks(task_type)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs(
                    run_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    generation_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    trace_run_id TEXT,
                    signals_json TEXT NOT NULL,
                    aggregate_score REAL,
                    output_text TEXT,
                    review_required INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_task ON runs(task_id, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_runs_generation ON runs(generation_id)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS generations(
                    generation_id TEXT PRIMARY KEY,
                    first_seen_at TEXT NOT NULL,
                    runtime_spec_json TEXT NOT NULL,
                    lora_adapter_id TEXT,
                    skill_set_hash TEXT NOT NULL,
                    settings_hash TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT ''
                )
                """
            )

    # ------------------------------------------------------------------
    # tasks
    # ------------------------------------------------------------------

    def upsert_task(self, row: EvalTaskRow) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tasks(task_id, created_at, task_type, source_run_id,
                                  payload_json, tags_json)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    task_type=excluded.task_type,
                    source_run_id=excluded.source_run_id,
                    payload_json=excluded.payload_json,
                    tags_json=excluded.tags_json
                """,
                (
                    row.task_id,
                    row.created_at,
                    row.task_type,
                    row.source_run_id,
                    row.payload_json,
                    row.tags_json,
                ),
            )

    def get_task(self, task_id: str) -> EvalTaskRow | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM tasks WHERE task_id=?", (task_id,)
            ).fetchone()
        return _row_to_task(row) if row else None

    def list_tasks(
        self, *, task_type: str | None = None, limit: int | None = None
    ) -> list[EvalTaskRow]:
        sql = "SELECT * FROM tasks"
        params: list[object] = []
        if task_type is not None:
            sql += " WHERE task_type=?"
            params.append(task_type)
        sql += " ORDER BY created_at, task_id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_row_to_task(r) for r in rows]

    # ------------------------------------------------------------------
    # runs
    # ------------------------------------------------------------------

    def insert_run(self, run: EvalRun) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs(run_id, task_id, generation_id, created_at,
                                 trace_run_id, signals_json, aggregate_score,
                                 output_text, review_required)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.task_id,
                    run.generation_id,
                    run.created_at,
                    run.trace_run_id,
                    run.signals_json,
                    run.aggregate_score,
                    run.output_text,
                    1 if run.review_required else 0,
                ),
            )

    def list_runs(
        self,
        *,
        task_id: str | None = None,
        generation_id: str | None = None,
        since: str | None = None,
        limit: int | None = None,
    ) -> list[EvalRun]:
        clauses: list[str] = []
        params: list[object] = []
        if task_id is not None:
            clauses.append("task_id=?")
            params.append(task_id)
        if generation_id is not None:
            clauses.append("generation_id=?")
            params.append(generation_id)
        if since is not None:
            clauses.append("created_at>=?")
            params.append(since)
        sql = "SELECT * FROM runs"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at, run_id"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(int(limit))
        with self._connect() as conn:
            rows = conn.execute(sql, tuple(params)).fetchall()
        return [_row_to_run(r) for r in rows]

    # ------------------------------------------------------------------
    # generations
    # ------------------------------------------------------------------

    def upsert_generation(self, gen: EvalGeneration) -> None:
        # ADR 0017 §4 — first_seen_at must remain stable so comparison
        # windows do not silently drift on repeat upserts. The ON
        # CONFLICT clause therefore preserves first_seen_at and notes
        # while leaving the derived spec/hash fields available for
        # backfill if material settings ever needed re-canonicalising.
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO generations(generation_id, first_seen_at,
                                        runtime_spec_json, lora_adapter_id,
                                        skill_set_hash, settings_hash, notes)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(generation_id) DO NOTHING
                """,
                (
                    gen.generation_id,
                    gen.first_seen_at,
                    gen.runtime_spec_json,
                    gen.lora_adapter_id,
                    gen.skill_set_hash,
                    gen.settings_hash,
                    gen.notes,
                ),
            )

    def get_generation(self, generation_id: str) -> EvalGeneration | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM generations WHERE generation_id=?",
                (generation_id,),
            ).fetchone()
        return _row_to_generation(row) if row else None

    def latest_generation(self) -> EvalGeneration | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM generations ORDER BY first_seen_at DESC LIMIT 1"
            ).fetchone()
        return _row_to_generation(row) if row else None


def _row_to_task(row: sqlite3.Row) -> EvalTaskRow:
    return EvalTaskRow(
        task_id=row["task_id"],
        created_at=row["created_at"],
        task_type=row["task_type"],
        source_run_id=row["source_run_id"],
        payload_json=row["payload_json"],
        tags_json=row["tags_json"],
    )


def _row_to_run(row: sqlite3.Row) -> EvalRun:
    return EvalRun(
        run_id=row["run_id"],
        task_id=row["task_id"],
        generation_id=row["generation_id"],
        created_at=row["created_at"],
        trace_run_id=row["trace_run_id"] or "",
        signals_json=row["signals_json"],
        aggregate_score=row["aggregate_score"],
        output_text=row["output_text"] or "",
        review_required=bool(row["review_required"]),
    )


def _row_to_generation(row: sqlite3.Row) -> EvalGeneration:
    return EvalGeneration(
        generation_id=row["generation_id"],
        first_seen_at=row["first_seen_at"],
        runtime_spec_json=row["runtime_spec_json"],
        lora_adapter_id=row["lora_adapter_id"],
        skill_set_hash=row["skill_set_hash"],
        settings_hash=row["settings_hash"],
        notes=row["notes"],
    )


# ----------------------------------------------------------------------
# Module-level default store — env-overridable, test-resettable. Mirrors
# the network_audit pattern so callers do not need to thread a store
# through every call site.
# ----------------------------------------------------------------------

_default_store: EvalStore | None = None


def get_default_store() -> EvalStore:
    global _default_store
    if _default_store is None:
        _default_store = EvalStore()
        _default_store.init_db()
    return _default_store


def reset_default_store_for_tests() -> None:
    global _default_store
    _default_store = None
