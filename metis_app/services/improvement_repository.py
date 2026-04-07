"""SQLite-backed persistence and markdown materialization for improvement artifacts."""

from __future__ import annotations

from contextlib import contextmanager
import json
import pathlib
import sqlite3
from typing import Any, Iterator

from metis_app.models.improvement_types import (
    IMPROVEMENT_ARTIFACT_TYPES,
    IMPROVEMENT_STATUSES,
    ImprovementEntry,
    improvement_now_iso,
)

_HERE = pathlib.Path(__file__).resolve().parent
_PACKAGE_ROOT = _HERE.parent
_REPO_ROOT = _PACKAGE_ROOT.parent
_DEFAULT_DB_PATH = _REPO_ROOT / "rag_sessions.db"
_DEFAULT_IMPROVEMENT_ROOT = _REPO_ROOT / ".metis_cache" / "improvements"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _write_text_atomic(path: pathlib.Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    temp_path.replace(path)


class ImprovementRepository:
    """Persist Ladder-style improvement artifacts in the shared session database."""

    def __init__(
        self,
        db_path: str | pathlib.Path | None = None,
        improvements_root: str | pathlib.Path | None = None,
    ) -> None:
        configured_target = db_path or _DEFAULT_DB_PATH
        self.db_path = pathlib.Path(configured_target) if configured_target != ":memory:" else ":memory:"
        self._db_target = ":memory:" if configured_target == ":memory:" else str(pathlib.Path(configured_target))
        self._shared_conn: sqlite3.Connection | None = None
        if self._db_target == ":memory:":
            self._shared_conn = sqlite3.connect(
                self._db_target,
                check_same_thread=False,
            )
            self._shared_conn.row_factory = sqlite3.Row

        self.improvements_root = pathlib.Path(improvements_root or _DEFAULT_IMPROVEMENT_ROOT)
        self._schema_ready = False

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

    def init_db(self) -> None:
        if self._schema_ready:
            return
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS improvement_entries(
                    entry_id TEXT PRIMARY KEY,
                    artifact_key TEXT NOT NULL UNIQUE,
                    artifact_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    body_md TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    upstream_ids_json TEXT NOT NULL,
                    metadata_json TEXT NOT NULL,
                    slug TEXT NOT NULL,
                    saved_at TEXT NOT NULL,
                    markdown_path TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_improvement_entries_type_updated "
                "ON improvement_entries(artifact_type, updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_improvement_entries_status_updated "
                "ON improvement_entries(status, updated_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_improvement_entries_session_run "
                "ON improvement_entries(session_id, run_id)"
            )
        self._schema_ready = True

    def get_entry(self, entry_id: str) -> ImprovementEntry | None:
        self.init_db()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM improvement_entries WHERE entry_id = ?",
                (str(entry_id or "").strip(),),
            ).fetchone()
        return ImprovementEntry.from_row(dict(row)) if row is not None else None

    def get_entry_by_key(self, artifact_key: str) -> ImprovementEntry | None:
        self.init_db()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM improvement_entries WHERE artifact_key = ?",
                (str(artifact_key or "").strip(),),
            ).fetchone()
        return ImprovementEntry.from_row(dict(row)) if row is not None else None

    def upsert_entry(self, entry: ImprovementEntry) -> ImprovementEntry:
        self.init_db()
        existing = self.get_entry_by_key(entry.artifact_key)
        if existing is not None:
            entry.entry_id = existing.entry_id
            entry.created_at = existing.created_at

        now = improvement_now_iso()
        entry.updated_at = now
        entry.saved_at = now
        markdown_path = self._write_markdown_entry(entry)
        entry.markdown_path = str(markdown_path)

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO improvement_entries(
                    entry_id, artifact_key, artifact_type, created_at, updated_at,
                    title, summary, body_md, session_id, run_id, status,
                    tags_json, upstream_ids_json, metadata_json, slug, saved_at, markdown_path
                )
                VALUES (
                    :entry_id, :artifact_key, :artifact_type, :created_at, :updated_at,
                    :title, :summary, :body_md, :session_id, :run_id, :status,
                    :tags_json, :upstream_ids_json, :metadata_json, :slug, :saved_at, :markdown_path
                )
                ON CONFLICT(artifact_key) DO UPDATE SET
                    artifact_type = excluded.artifact_type,
                    updated_at = excluded.updated_at,
                    title = excluded.title,
                    summary = excluded.summary,
                    body_md = excluded.body_md,
                    session_id = excluded.session_id,
                    run_id = excluded.run_id,
                    status = excluded.status,
                    tags_json = excluded.tags_json,
                    upstream_ids_json = excluded.upstream_ids_json,
                    metadata_json = excluded.metadata_json,
                    slug = excluded.slug,
                    saved_at = excluded.saved_at,
                    markdown_path = excluded.markdown_path
                """,
                self._entry_row(entry),
            )
        return entry

    def list_entries(
        self,
        *,
        artifact_type: str = "",
        status: str = "",
        limit: int | None = 20,
    ) -> list[ImprovementEntry]:
        self.init_db()
        where: list[str] = []
        params: list[Any] = []
        normalized_type = str(artifact_type or "").strip().lower()
        if normalized_type:
            if normalized_type not in IMPROVEMENT_ARTIFACT_TYPES:
                raise ValueError(
                    f"artifact_type must be one of {', '.join(IMPROVEMENT_ARTIFACT_TYPES)}"
                )
            where.append("artifact_type = ?")
            params.append(normalized_type)
        normalized_status = str(status or "").strip().lower()
        if normalized_status:
            if normalized_status not in IMPROVEMENT_STATUSES:
                raise ValueError(
                    f"status must be one of {', '.join(IMPROVEMENT_STATUSES)}"
                )
            where.append("status = ?")
            params.append(normalized_status)

        query = "SELECT * FROM improvement_entries"
        if where:
            query += " WHERE " + " AND ".join(where)
        query += " ORDER BY updated_at DESC"
        if limit is not None:
            normalized_limit = max(int(limit), 0)
            if normalized_limit == 0:
                return []
            query += " LIMIT ?"
            params.append(normalized_limit)

        with self._connect() as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
        return [ImprovementEntry.from_row(dict(row)) for row in rows]

    def _entry_row(self, entry: ImprovementEntry) -> dict[str, Any]:
        return {
            "entry_id": entry.entry_id,
            "artifact_key": entry.artifact_key,
            "artifact_type": entry.artifact_type,
            "created_at": entry.created_at,
            "updated_at": entry.updated_at,
            "title": entry.title,
            "summary": entry.summary,
            "body_md": entry.body_md,
            "session_id": entry.session_id,
            "run_id": entry.run_id,
            "status": entry.status,
            "tags_json": _json_dumps(entry.tags),
            "upstream_ids_json": _json_dumps(entry.upstream_ids),
            "metadata_json": _json_dumps(entry.metadata),
            "slug": entry.slug,
            "saved_at": entry.saved_at,
            "markdown_path": entry.markdown_path,
        }

    def _write_markdown_entry(self, entry: ImprovementEntry) -> pathlib.Path:
        target_dir = self.improvements_root / f"{entry.artifact_type}s"
        target_path = target_dir / f"{entry.slug}.md"
        upstream = ", ".join(entry.upstream_ids)
        tags = ", ".join(entry.tags)
        metadata_block = json.dumps(entry.metadata, ensure_ascii=False, indent=2)
        content = (
            "---\n"
            f"entry_id: {entry.entry_id}\n"
            f"artifact_key: {entry.artifact_key}\n"
            f"artifact_type: {entry.artifact_type}\n"
            f"status: {entry.status}\n"
            f"created_at: {entry.created_at}\n"
            f"updated_at: {entry.updated_at}\n"
            f"session_id: {entry.session_id}\n"
            f"run_id: {entry.run_id}\n"
            f"tags: [{tags}]\n"
            f"upstream_ids: [{upstream}]\n"
            "---\n\n"
            f"# {entry.title}\n\n"
            "## Summary\n\n"
            f"{entry.summary}\n\n"
            "## Body\n\n"
            f"{entry.body_md}\n\n"
            "## Metadata\n\n"
            "```json\n"
            f"{metadata_block}\n"
            "```\n"
        )
        _write_text_atomic(target_path, content)
        return target_path
