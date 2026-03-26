"""SQLite-backed persistence for the local-first METIS companion."""

from __future__ import annotations

from contextlib import contextmanager
import json
import os
import pathlib
import sqlite3
from typing import Any, Iterator

from metis_app.models.assistant_types import (
    AssistantBrainLink,
    AssistantMemoryEntry,
    AssistantPlaybook,
    AssistantStatus,
)

_HERE = pathlib.Path(__file__).resolve().parent
_PACKAGE_ROOT = _HERE.parent
_REPO_ROOT = _PACKAGE_ROOT.parent
_DEFAULT_DB_PATH = _REPO_ROOT / "rag_sessions.db"
_DEFAULT_LEGACY_STATE_PATH = _REPO_ROOT / "assistant_state.json"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _json_load(value: str | bytes | None, default: Any) -> Any:
    if value in (None, ""):
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


class AssistantRepository:
    """Persist companion state in the shared session database."""

    def __init__(
        self,
        db_path: str | pathlib.Path | None = None,
        legacy_state_path: str | pathlib.Path | None = None,
    ) -> None:
        inferred_legacy = legacy_state_path
        resolved_db_path: str | pathlib.Path | None = db_path
        if db_path not in (None, ":memory:"):
            candidate = pathlib.Path(db_path)
            if candidate.suffix.lower() == ".json" and legacy_state_path is None:
                inferred_legacy = candidate
                resolved_db_path = candidate.with_name("rag_sessions.db")

        env_db_path = os.getenv("METIS_SESSION_DB_PATH") or None
        configured_target = resolved_db_path or env_db_path or _DEFAULT_DB_PATH
        db_target: str
        if configured_target == ":memory:":
            db_target = ":memory:"
            self.db_path: pathlib.Path | str = ":memory:"
        elif isinstance(configured_target, str) and configured_target.startswith("file:"):
            db_target = configured_target
            self.db_path = configured_target
        else:
            path_target = pathlib.Path(configured_target)
            self.db_path = path_target
            db_target = str(path_target)

        self._db_target = db_target
        self._uri = db_target.startswith("file:")
        self._shared_conn: sqlite3.Connection | None = None
        if self._db_target == ":memory:" or self._uri:
            self._shared_conn = sqlite3.connect(
                self._db_target,
                uri=self._uri,
                check_same_thread=False,
            )
            self._shared_conn.row_factory = sqlite3.Row

        self.state_path = pathlib.Path(inferred_legacy or _DEFAULT_LEGACY_STATE_PATH)
        self._schema_ready = False
        self._legacy_import_checked = False

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
        conn: sqlite3.Connection | None = None
        try:
            if self._shared_conn is not None:
                conn = self._shared_conn
            else:
                conn = sqlite3.connect(str(self._db_target), timeout=30.0)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA busy_timeout=30000")
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

    def init_db(self) -> None:
        if self._schema_ready:
            return
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assistant_status(
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    state TEXT NOT NULL,
                    paused INTEGER NOT NULL,
                    runtime_ready INTEGER NOT NULL,
                    runtime_source TEXT NOT NULL,
                    runtime_provider TEXT NOT NULL,
                    runtime_model TEXT NOT NULL,
                    bootstrap_state TEXT NOT NULL,
                    bootstrap_message TEXT NOT NULL,
                    recommended_model_name TEXT NOT NULL,
                    recommended_quant TEXT NOT NULL,
                    recommended_use_case TEXT NOT NULL,
                    last_reflection_at TEXT NOT NULL,
                    last_reflection_trigger TEXT NOT NULL,
                    latest_summary TEXT NOT NULL,
                    latest_why TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assistant_memory(
                    entry_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    details TEXT NOT NULL,
                    why TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    trigger TEXT NOT NULL,
                    context_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    tags_json TEXT NOT NULL,
                    related_node_ids_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_assistant_memory_created_at ON assistant_memory(created_at DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_assistant_memory_trigger_context ON assistant_memory(trigger, context_id, session_id, run_id)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assistant_playbooks(
                    playbook_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    title TEXT NOT NULL,
                    bullets_json TEXT NOT NULL,
                    source_session_id TEXT NOT NULL,
                    source_run_id TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    active INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_assistant_playbooks_created_at ON assistant_playbooks(created_at DESC)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS assistant_brain_links(
                    link_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    source_node_id TEXT NOT NULL,
                    target_node_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    label TEXT NOT NULL,
                    provenance TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    session_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_assistant_brain_links_created_at ON assistant_brain_links(created_at DESC)"
            )
        self._schema_ready = True

    def _ensure_ready(self) -> None:
        self.init_db()
        self._maybe_import_legacy_state()

    def _maybe_import_legacy_state(self) -> None:
        if self._legacy_import_checked:
            return
        self._legacy_import_checked = True
        if not self.state_path.exists():
            return
        if self._has_persisted_rows():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError):
            return
        normalized = self._normalize_payload(payload)
        with self._transaction() as conn:
            self._replace_state(
                conn,
                status=AssistantStatus.from_payload(normalized.get("status")),
                memory=[
                    AssistantMemoryEntry.from_payload(item)
                    for item in normalized.get("memory", [])
                ],
                playbooks=[
                    AssistantPlaybook.from_payload(item)
                    for item in normalized.get("playbooks", [])
                ],
                brain_links=[
                    AssistantBrainLink.from_payload(item)
                    for item in normalized.get("brain_links", [])
                ],
            )

    def _has_persisted_rows(self) -> bool:
        with self._connect() as conn:
            tables = (
                "assistant_status",
                "assistant_memory",
                "assistant_playbooks",
                "assistant_brain_links",
            )
            for table in tables:
                row = conn.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
                if row is not None and int(row["count"] or 0) > 0:
                    return True
        return False

    def _normalize_payload(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        data = dict(payload or {})
        return {
            "status": AssistantStatus.from_payload(data.get("status")).to_payload(),
            "memory": [
                AssistantMemoryEntry.from_payload(item).to_payload()
                for item in (data.get("memory") or [])
                if isinstance(item, dict)
            ],
            "playbooks": [
                AssistantPlaybook.from_payload(item).to_payload()
                for item in (data.get("playbooks") or [])
                if isinstance(item, dict)
            ],
            "brain_links": [
                AssistantBrainLink.from_payload(item).to_payload()
                for item in (data.get("brain_links") or [])
                if isinstance(item, dict)
            ],
        }

    def _status_from_row(self, row: sqlite3.Row | None) -> AssistantStatus:
        if row is None:
            return AssistantStatus()
        return AssistantStatus.from_payload(dict(row))

    def _memory_from_row(self, row: sqlite3.Row) -> AssistantMemoryEntry:
        payload = dict(row)
        payload["tags"] = _json_load(payload.pop("tags_json", "[]"), [])
        payload["related_node_ids"] = _json_load(payload.pop("related_node_ids_json", "[]"), [])
        return AssistantMemoryEntry.from_payload(payload)

    def _playbook_from_row(self, row: sqlite3.Row) -> AssistantPlaybook:
        payload = dict(row)
        payload["bullets"] = _json_load(payload.pop("bullets_json", "[]"), [])
        return AssistantPlaybook.from_payload(payload)

    def _brain_link_from_row(self, row: sqlite3.Row) -> AssistantBrainLink:
        payload = dict(row)
        payload["metadata"] = _json_load(payload.pop("metadata_json", "{}"), {})
        return AssistantBrainLink.from_payload(payload)

    def _status_row(self, status: AssistantStatus) -> dict[str, Any]:
        payload = status.to_payload()
        payload["id"] = 1
        payload["paused"] = int(bool(payload["paused"]))
        payload["runtime_ready"] = int(bool(payload["runtime_ready"]))
        return payload

    def _memory_row(self, entry: AssistantMemoryEntry) -> dict[str, Any]:
        payload = entry.to_payload()
        return {
            "entry_id": payload["entry_id"],
            "created_at": payload["created_at"],
            "kind": payload["kind"],
            "title": payload["title"],
            "summary": payload["summary"],
            "details": payload["details"],
            "why": payload["why"],
            "provenance": payload["provenance"],
            "confidence": payload["confidence"],
            "trigger": payload["trigger"],
            "context_id": payload["context_id"],
            "session_id": payload["session_id"],
            "run_id": payload["run_id"],
            "tags_json": _json_dumps(payload["tags"]),
            "related_node_ids_json": _json_dumps(payload["related_node_ids"]),
        }

    def _playbook_row(self, playbook: AssistantPlaybook) -> dict[str, Any]:
        payload = playbook.to_payload()
        return {
            "playbook_id": payload["playbook_id"],
            "created_at": payload["created_at"],
            "title": payload["title"],
            "bullets_json": _json_dumps(payload["bullets"]),
            "source_session_id": payload["source_session_id"],
            "source_run_id": payload["source_run_id"],
            "provenance": payload["provenance"],
            "confidence": payload["confidence"],
            "active": int(bool(payload["active"])),
        }

    def _brain_link_row(self, link: AssistantBrainLink) -> dict[str, Any]:
        payload = link.to_payload()
        return {
            "link_id": payload["link_id"],
            "created_at": payload["created_at"],
            "source_node_id": payload["source_node_id"],
            "target_node_id": payload["target_node_id"],
            "relation": payload["relation"],
            "label": payload["label"],
            "provenance": payload["provenance"],
            "summary": payload["summary"],
            "confidence": payload["confidence"],
            "session_id": payload["session_id"],
            "run_id": payload["run_id"],
            "metadata_json": _json_dumps(payload["metadata"]),
        }

    def _replace_state(
        self,
        conn: sqlite3.Connection,
        *,
        status: AssistantStatus,
        memory: list[AssistantMemoryEntry],
        playbooks: list[AssistantPlaybook],
        brain_links: list[AssistantBrainLink],
    ) -> None:
        conn.execute("DELETE FROM assistant_status")
        conn.execute("DELETE FROM assistant_memory")
        conn.execute("DELETE FROM assistant_playbooks")
        conn.execute("DELETE FROM assistant_brain_links")
        conn.execute(
            """
            INSERT INTO assistant_status(
                id, state, paused, runtime_ready, runtime_source, runtime_provider,
                runtime_model, bootstrap_state, bootstrap_message,
                recommended_model_name, recommended_quant, recommended_use_case,
                last_reflection_at, last_reflection_trigger, latest_summary, latest_why
            ) VALUES (
                :id, :state, :paused, :runtime_ready, :runtime_source, :runtime_provider,
                :runtime_model, :bootstrap_state, :bootstrap_message,
                :recommended_model_name, :recommended_quant, :recommended_use_case,
                :last_reflection_at, :last_reflection_trigger, :latest_summary, :latest_why
            )
            """,
            self._status_row(status),
        )
        if memory:
            conn.executemany(
                """
                INSERT INTO assistant_memory(
                    entry_id, created_at, kind, title, summary, details, why,
                    provenance, confidence, trigger, context_id, session_id,
                    run_id, tags_json, related_node_ids_json
                ) VALUES (
                    :entry_id, :created_at, :kind, :title, :summary, :details, :why,
                    :provenance, :confidence, :trigger, :context_id, :session_id,
                    :run_id, :tags_json, :related_node_ids_json
                )
                """,
                [self._memory_row(item) for item in memory],
            )
        if playbooks:
            conn.executemany(
                """
                INSERT INTO assistant_playbooks(
                    playbook_id, created_at, title, bullets_json, source_session_id,
                    source_run_id, provenance, confidence, active
                ) VALUES (
                    :playbook_id, :created_at, :title, :bullets_json, :source_session_id,
                    :source_run_id, :provenance, :confidence, :active
                )
                """,
                [self._playbook_row(item) for item in playbooks],
            )
        if brain_links:
            conn.executemany(
                """
                INSERT INTO assistant_brain_links(
                    link_id, created_at, source_node_id, target_node_id, relation,
                    label, provenance, summary, confidence, session_id, run_id, metadata_json
                ) VALUES (
                    :link_id, :created_at, :source_node_id, :target_node_id, :relation,
                    :label, :provenance, :summary, :confidence, :session_id, :run_id, :metadata_json
                )
                """,
                [self._brain_link_row(item) for item in brain_links],
            )

    def load_state(self) -> dict[str, Any]:
        self._ensure_ready()
        return {
            "status": self.get_status().to_payload(),
            "memory": [item.to_payload() for item in self.list_memory()],
            "playbooks": [item.to_payload() for item in self.list_playbooks()],
            "brain_links": [item.to_payload() for item in self.list_brain_links()],
        }

    def save_state(self, payload: dict[str, Any]) -> dict[str, Any]:
        self._ensure_ready()
        normalized = self._normalize_payload(payload)
        with self._transaction() as conn:
            self._replace_state(
                conn,
                status=AssistantStatus.from_payload(normalized.get("status")),
                memory=[
                    AssistantMemoryEntry.from_payload(item)
                    for item in normalized.get("memory", [])
                ],
                playbooks=[
                    AssistantPlaybook.from_payload(item)
                    for item in normalized.get("playbooks", [])
                ],
                brain_links=[
                    AssistantBrainLink.from_payload(item)
                    for item in normalized.get("brain_links", [])
                ],
            )
        return normalized

    def get_status(self) -> AssistantStatus:
        self._ensure_ready()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM assistant_status WHERE id = 1").fetchone()
        return self._status_from_row(row)

    def update_status(self, status: AssistantStatus | dict[str, Any]) -> AssistantStatus:
        self._ensure_ready()
        current = self.get_status().to_payload()
        updates = status.to_payload() if isinstance(status, AssistantStatus) else dict(status or {})
        current.update(updates)
        resolved = AssistantStatus.from_payload(current)
        with self._transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO assistant_status(
                    id, state, paused, runtime_ready, runtime_source, runtime_provider,
                    runtime_model, bootstrap_state, bootstrap_message,
                    recommended_model_name, recommended_quant, recommended_use_case,
                    last_reflection_at, last_reflection_trigger, latest_summary, latest_why
                ) VALUES (
                    :id, :state, :paused, :runtime_ready, :runtime_source, :runtime_provider,
                    :runtime_model, :bootstrap_state, :bootstrap_message,
                    :recommended_model_name, :recommended_quant, :recommended_use_case,
                    :last_reflection_at, :last_reflection_trigger, :latest_summary, :latest_why
                )
                """,
                self._status_row(resolved),
            )
        return resolved

    def list_memory(self, *, limit: int | None = None) -> list[AssistantMemoryEntry]:
        self._ensure_ready()
        query = "SELECT * FROM assistant_memory ORDER BY created_at DESC"
        params: tuple[Any, ...] = ()
        if limit is not None:
            normalized_limit = max(int(limit), 0)
            if normalized_limit == 0:
                return []
            query = f"{query} LIMIT ?"
            params = (normalized_limit,)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._memory_from_row(row) for row in rows]

    def add_memory_entry(
        self,
        entry: AssistantMemoryEntry | dict[str, Any],
        *,
        max_entries: int | None = None,
    ) -> AssistantMemoryEntry:
        self._ensure_ready()
        item = entry if isinstance(entry, AssistantMemoryEntry) else AssistantMemoryEntry.from_payload(entry)
        rows = self.list_memory()
        rows = [existing for existing in rows if existing.entry_id != item.entry_id]
        rows.append(item)
        rows.sort(key=lambda existing: existing.created_at, reverse=True)
        if max_entries is not None:
            rows = rows[: max(int(max_entries), 1)]
        with self._transaction() as conn:
            conn.execute("DELETE FROM assistant_memory")
            if rows:
                conn.executemany(
                    """
                    INSERT INTO assistant_memory(
                        entry_id, created_at, kind, title, summary, details, why,
                        provenance, confidence, trigger, context_id, session_id,
                        run_id, tags_json, related_node_ids_json
                    ) VALUES (
                        :entry_id, :created_at, :kind, :title, :summary, :details, :why,
                        :provenance, :confidence, :trigger, :context_id, :session_id,
                        :run_id, :tags_json, :related_node_ids_json
                    )
                    """,
                    [self._memory_row(existing) for existing in rows],
                )
        return item

    def clear_recent_memory(self, *, limit: int = 10) -> int:
        self._ensure_ready()
        rows = self.list_memory()
        normalized_limit = max(int(limit), 0)
        removed = rows[:normalized_limit]
        kept = rows[normalized_limit:]
        with self._transaction() as conn:
            conn.execute("DELETE FROM assistant_memory")
            if kept:
                conn.executemany(
                    """
                    INSERT INTO assistant_memory(
                        entry_id, created_at, kind, title, summary, details, why,
                        provenance, confidence, trigger, context_id, session_id,
                        run_id, tags_json, related_node_ids_json
                    ) VALUES (
                        :entry_id, :created_at, :kind, :title, :summary, :details, :why,
                        :provenance, :confidence, :trigger, :context_id, :session_id,
                        :run_id, :tags_json, :related_node_ids_json
                    )
                    """,
                    [self._memory_row(existing) for existing in kept],
                )
        return len(removed)

    def list_playbooks(self, *, limit: int | None = None) -> list[AssistantPlaybook]:
        self._ensure_ready()
        query = "SELECT * FROM assistant_playbooks ORDER BY created_at DESC"
        params: tuple[Any, ...] = ()
        if limit is not None:
            normalized_limit = max(int(limit), 0)
            if normalized_limit == 0:
                return []
            query = f"{query} LIMIT ?"
            params = (normalized_limit,)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._playbook_from_row(row) for row in rows]

    def add_playbook(
        self,
        playbook: AssistantPlaybook | dict[str, Any],
        *,
        max_items: int | None = None,
    ) -> AssistantPlaybook:
        self._ensure_ready()
        item = playbook if isinstance(playbook, AssistantPlaybook) else AssistantPlaybook.from_payload(playbook)
        rows = self.list_playbooks()
        dedupe_key = (item.title.casefold(), tuple(bullet.casefold() for bullet in item.bullets))
        rows = [
            existing
            for existing in rows
            if (existing.title.casefold(), tuple(bullet.casefold() for bullet in existing.bullets)) != dedupe_key
        ]
        rows.append(item)
        rows.sort(key=lambda existing: existing.created_at, reverse=True)
        if max_items is not None:
            rows = rows[: max(int(max_items), 1)]
        with self._transaction() as conn:
            conn.execute("DELETE FROM assistant_playbooks")
            if rows:
                conn.executemany(
                    """
                    INSERT INTO assistant_playbooks(
                        playbook_id, created_at, title, bullets_json, source_session_id,
                        source_run_id, provenance, confidence, active
                    ) VALUES (
                        :playbook_id, :created_at, :title, :bullets_json, :source_session_id,
                        :source_run_id, :provenance, :confidence, :active
                    )
                    """,
                    [self._playbook_row(existing) for existing in rows],
                )
        return item

    def list_brain_links(self, *, limit: int | None = None) -> list[AssistantBrainLink]:
        self._ensure_ready()
        query = "SELECT * FROM assistant_brain_links ORDER BY created_at DESC"
        params: tuple[Any, ...] = ()
        if limit is not None:
            normalized_limit = max(int(limit), 0)
            if normalized_limit == 0:
                return []
            query = f"{query} LIMIT ?"
            params = (normalized_limit,)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._brain_link_from_row(row) for row in rows]

    def add_brain_links(
        self,
        links: list[AssistantBrainLink | dict[str, Any]],
        *,
        max_items: int | None = None,
    ) -> list[AssistantBrainLink]:
        self._ensure_ready()
        existing_rows = self.list_brain_links()
        incoming = [
            link if isinstance(link, AssistantBrainLink) else AssistantBrainLink.from_payload(link)
            for link in links
        ]
        dedupe_keys = {
            (
                item.source_node_id,
                item.target_node_id,
                item.relation,
                item.session_id,
                item.run_id,
            )
            for item in incoming
        }
        existing_rows = [
            item
            for item in existing_rows
            if (
                item.source_node_id,
                item.target_node_id,
                item.relation,
                item.session_id,
                item.run_id,
            )
            not in dedupe_keys
        ]
        existing_rows.extend(incoming)
        existing_rows.sort(key=lambda item: item.created_at, reverse=True)
        if max_items is not None:
            existing_rows = existing_rows[: max(int(max_items), 1)]
        with self._transaction() as conn:
            conn.execute("DELETE FROM assistant_brain_links")
            if existing_rows:
                conn.executemany(
                    """
                    INSERT INTO assistant_brain_links(
                        link_id, created_at, source_node_id, target_node_id, relation,
                        label, provenance, summary, confidence, session_id, run_id, metadata_json
                    ) VALUES (
                        :link_id, :created_at, :source_node_id, :target_node_id, :relation,
                        :label, :provenance, :summary, :confidence, :session_id, :run_id, :metadata_json
                    )
                    """,
                    [self._brain_link_row(item) for item in existing_rows],
                )
        return incoming
