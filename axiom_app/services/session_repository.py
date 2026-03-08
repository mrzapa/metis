"""SQLite-backed session repository compatible with the legacy monolith schema."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime, timezone
import json
import pathlib
import re
import sqlite3
import uuid
from typing import Any, Iterator

from axiom_app.models.session_types import (
    EvidenceSource,
    SessionDetail,
    SessionFeedback,
    SessionMessage,
    SessionSummary,
)

_HERE = pathlib.Path(__file__).resolve().parent
_PACKAGE_ROOT = _HERE.parent
_REPO_ROOT = _PACKAGE_ROOT.parent
_DEFAULT_DB_PATH = _REPO_ROOT / "rag_sessions.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionRepository:
    """Store and retrieve chat sessions using the monolith's SQLite schema."""

    def __init__(self, db_path: str | pathlib.Path | None = None) -> None:
        self.db_path = pathlib.Path(db_path) if db_path not in (None, ":memory:") else db_path
        self._db_target = (
            ":memory:" if db_path == ":memory:" else str(self.db_path or _DEFAULT_DB_PATH)
        )
        self._shared_conn: sqlite3.Connection | None = None
        self._uri = self._db_target.startswith("file:")
        if self._db_target == ":memory:" or self._uri:
            self._shared_conn = sqlite3.connect(
                self._db_target,
                uri=self._uri,
                check_same_thread=False,
            )
            self._shared_conn.row_factory = sqlite3.Row

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self._shared_conn is not None:
            yield self._shared_conn
            self._shared_conn.commit()
            return

        target = pathlib.Path(self._db_target)
        target.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(target))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions(
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT,
                    updated_at TEXT,
                    title TEXT,
                    summary TEXT,
                    active_profile TEXT,
                    mode TEXT,
                    index_id TEXT,
                    vector_backend TEXT,
                    llm_provider TEXT,
                    llm_model TEXT,
                    embed_model TEXT,
                    retrieve_k INT,
                    final_k INT,
                    mmr_lambda REAL,
                    agentic_iterations INT,
                    extra_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages(
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    ts TEXT,
                    role TEXT,
                    content TEXT,
                    run_id TEXT,
                    sources_json TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_session_ts ON messages(session_id, ts)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS message_feedback(
                    feedback_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    run_id TEXT,
                    vote INTEGER,
                    note TEXT,
                    ts TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_feedback_session ON message_feedback(session_id, ts)"
            )

    def create_session(
        self,
        *,
        title: str = "New Chat",
        summary: str = "",
        active_profile: str = "",
        mode: str = "",
        index_id: str = "",
        vector_backend: str = "json",
        llm_provider: str = "",
        llm_model: str = "",
        embed_model: str = "",
        retrieve_k: int = 0,
        final_k: int = 0,
        mmr_lambda: float = 0.0,
        agentic_iterations: int = 0,
        extra_json: str = "{}",
        session_id: str | None = None,
    ) -> SessionSummary:
        session_id = session_id or str(uuid.uuid4())
        created_at = _now_iso()
        payload = {
            "session_id": session_id,
            "created_at": created_at,
            "updated_at": created_at,
            "title": title or "New Chat",
            "summary": summary or "",
            "active_profile": active_profile or "",
            "mode": mode or "",
            "index_id": index_id or "",
            "vector_backend": vector_backend or "",
            "llm_provider": llm_provider or "",
            "llm_model": llm_model or "",
            "embed_model": embed_model or "",
            "retrieve_k": int(retrieve_k or 0),
            "final_k": int(final_k or 0),
            "mmr_lambda": float(mmr_lambda or 0.0),
            "agentic_iterations": int(agentic_iterations or 0),
            "extra_json": extra_json or "{}",
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO sessions(
                    session_id, created_at, updated_at, title, summary,
                    active_profile, mode, index_id, vector_backend, llm_provider,
                    llm_model, embed_model, retrieve_k, final_k, mmr_lambda,
                    agentic_iterations, extra_json
                )
                VALUES (
                    :session_id, :created_at, :updated_at, :title, :summary,
                    :active_profile, :mode, :index_id, :vector_backend, :llm_provider,
                    :llm_model, :embed_model, :retrieve_k, :final_k, :mmr_lambda,
                    :agentic_iterations, :extra_json
                )
                """,
                payload,
            )
        return self.get_session(session_id).summary  # type: ignore[union-attr]

    def upsert_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
        summary: str | None = None,
        active_profile: str | None = None,
        mode: str | None = None,
        index_id: str | None = None,
        vector_backend: str | None = None,
        llm_provider: str | None = None,
        llm_model: str | None = None,
        embed_model: str | None = None,
        retrieve_k: int | None = None,
        final_k: int | None = None,
        mmr_lambda: float | None = None,
        agentic_iterations: int | None = None,
        extra_json: str | None = None,
    ) -> SessionSummary:
        detail = self.get_session(session_id)
        if detail is None:
            return self.create_session(
                title=title or "New Chat",
                summary=summary or "",
                active_profile=active_profile or "",
                mode=mode or "",
                index_id=index_id or "",
                vector_backend=vector_backend or "json",
                llm_provider=llm_provider or "",
                llm_model=llm_model or "",
                embed_model=embed_model or "",
                retrieve_k=retrieve_k or 0,
                final_k=final_k or 0,
                mmr_lambda=mmr_lambda or 0.0,
                agentic_iterations=agentic_iterations or 0,
                extra_json=extra_json or "{}",
                session_id=session_id,
            )

        current = detail.summary
        payload = {
            "session_id": session_id,
            "updated_at": _now_iso(),
            "title": title if title is not None else current.title,
            "summary": summary if summary is not None else current.summary,
            "active_profile": active_profile if active_profile is not None else current.active_profile,
            "mode": mode if mode is not None else current.mode,
            "index_id": index_id if index_id is not None else current.index_id,
            "vector_backend": (
                vector_backend if vector_backend is not None else current.vector_backend
            ),
            "llm_provider": llm_provider if llm_provider is not None else current.llm_provider,
            "llm_model": llm_model if llm_model is not None else current.llm_model,
            "embed_model": embed_model if embed_model is not None else current.embed_model,
            "retrieve_k": current.retrieve_k if retrieve_k is None else int(retrieve_k),
            "final_k": current.final_k if final_k is None else int(final_k),
            "mmr_lambda": current.mmr_lambda if mmr_lambda is None else float(mmr_lambda),
            "agentic_iterations": (
                current.agentic_iterations
                if agentic_iterations is None
                else int(agentic_iterations)
            ),
            "extra_json": extra_json if extra_json is not None else current.extra_json,
        }
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE sessions
                SET updated_at = :updated_at,
                    title = :title,
                    summary = :summary,
                    active_profile = :active_profile,
                    mode = :mode,
                    index_id = :index_id,
                    vector_backend = :vector_backend,
                    llm_provider = :llm_provider,
                    llm_model = :llm_model,
                    embed_model = :embed_model,
                    retrieve_k = :retrieve_k,
                    final_k = :final_k,
                    mmr_lambda = :mmr_lambda,
                    agentic_iterations = :agentic_iterations,
                    extra_json = :extra_json
                WHERE session_id = :session_id
                """,
                payload,
            )
        return self.get_session(session_id).summary  # type: ignore[union-attr]

    def list_sessions(
        self,
        *,
        search: str = "",
        profile: str = "",
        skill: str = "",
    ) -> list[SessionSummary]:
        sql = [
            """
            SELECT session_id, created_at, updated_at, title, summary, active_profile,
                   mode, index_id, vector_backend, llm_provider, llm_model, embed_model,
                   retrieve_k, final_k, mmr_lambda, agentic_iterations, extra_json
            FROM sessions
            """
        ]
        clauses: list[str] = []
        params: list[Any] = []
        query = (search or "").strip().lower()
        if query:
            wildcard = f"%{query}%"
            clauses.append(
                "(lower(title) LIKE ? OR lower(summary) LIKE ? OR lower(session_id) LIKE ?)"
            )
            params.extend([wildcard, wildcard, wildcard])

        profile_norm = (profile or "").strip()
        if profile_norm and profile_norm.lower() not in {"all", "all profiles"}:
            clauses.append("active_profile = ?")
            params.append(profile_norm)

        if clauses:
            sql.append("WHERE " + " AND ".join(clauses))
        sql.append("ORDER BY updated_at DESC, created_at DESC")

        with self._connect() as conn:
            rows = conn.execute("\n".join(sql), params).fetchall()
        summaries = [self._row_to_summary(row) for row in rows]
        skill_norm = (skill or "").strip()
        if not skill_norm or skill_norm.lower() in {"all", "all skills"}:
            return summaries
        return [summary for summary in summaries if skill_norm in summary.skill_ids]

    def get_session(self, session_id: str) -> SessionDetail | None:
        with self._connect() as conn:
            session = conn.execute(
                """
                SELECT session_id, created_at, updated_at, title, summary, active_profile,
                       mode, index_id, vector_backend, llm_provider, llm_model, embed_model,
                       retrieve_k, final_k, mmr_lambda, agentic_iterations, extra_json
                FROM sessions WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
            if session is None:
                return None

            messages = conn.execute(
                """
                SELECT role, content, ts, run_id, sources_json
                FROM messages
                WHERE session_id = ?
                ORDER BY ts ASC
                """,
                (session_id,),
            ).fetchall()
            feedback = conn.execute(
                """
                SELECT feedback_id, session_id, run_id, vote, note, ts
                FROM message_feedback
                WHERE session_id = ?
                ORDER BY ts ASC
                """,
                (session_id,),
            ).fetchall()

        return SessionDetail(
            summary=self._row_to_summary(session),
            messages=[self._row_to_message(row) for row in messages],
            feedback=[self._row_to_feedback(row) for row in feedback],
            traces={},
        )

    def append_message(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        run_id: str | None = None,
        sources: list[EvidenceSource] | list[dict[str, Any]] | None = None,
    ) -> None:
        serialized_sources = []
        for item in sources or []:
            if isinstance(item, EvidenceSource):
                serialized_sources.append(item.to_dict())
            elif isinstance(item, dict):
                serialized_sources.append(EvidenceSource.from_dict(item).to_dict())

        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO messages(message_id, session_id, ts, role, content, run_id, sources_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    session_id,
                    _now_iso(),
                    str(role or ""),
                    str(content or ""),
                    str(run_id or ""),
                    json.dumps(serialized_sources, ensure_ascii=False),
                ),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (_now_iso(), session_id),
            )

    def save_feedback(self, session_id: str, *, run_id: str, vote: int, note: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO message_feedback(feedback_id, session_id, run_id, vote, note, ts)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    session_id,
                    str(run_id or ""),
                    int(vote),
                    str(note or ""),
                    _now_iso(),
                ),
            )

    def delete_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM message_feedback WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    def rename_session(self, session_id: str, title: str) -> SessionSummary:
        normalized = str(title or "").strip() or "Untitled"
        with self._connect() as conn:
            conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE session_id = ?",
                (normalized, _now_iso(), session_id),
            )
        return self.get_session(session_id).summary  # type: ignore[union-attr]

    def duplicate_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
    ) -> SessionSummary:
        detail = self.get_session(session_id)
        if detail is None:
            raise FileNotFoundError(f"Session not found: {session_id}")
        summary = detail.summary
        clone = self.create_session(
            title=str(title or f"{summary.title} Copy").strip(),
            summary=summary.summary,
            active_profile=summary.active_profile,
            mode=summary.mode,
            index_id=summary.index_id,
            vector_backend=summary.vector_backend,
            llm_provider=summary.llm_provider,
            llm_model=summary.llm_model,
            embed_model=summary.embed_model,
            retrieve_k=summary.retrieve_k,
            final_k=summary.final_k,
            mmr_lambda=summary.mmr_lambda,
            agentic_iterations=summary.agentic_iterations,
            extra_json=summary.extra_json,
        )
        for message in detail.messages:
            self.append_message(
                clone.session_id,
                role=message.role,
                content=message.content,
                run_id=message.run_id,
                sources=message.sources,
            )
        return self.get_session(clone.session_id).summary  # type: ignore[union-attr]

    def export_session(self, session_id: str, save_dir: str | pathlib.Path) -> tuple[pathlib.Path, pathlib.Path]:
        detail = self.get_session(session_id)
        if detail is None:
            raise FileNotFoundError(f"Session not found: {session_id}")

        save_dir = pathlib.Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)

        title = (detail.summary.title or "Untitled").strip() or "Untitled"
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", title).strip("_") or "session"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        md_path = save_dir / f"{slug}_{stamp}.md"
        json_path = save_dir / f"{slug}_{stamp}.json"

        payload = self._session_export_payload(detail)
        lines = [
            f"# Session Export: {title}",
            "",
            f"- Session ID: `{detail.summary.session_id}`",
            f"- Updated: `{detail.summary.updated_at or ''}`",
            f"- Skills: `{', '.join(detail.summary.skill_ids) or '-'}`",
            f"- Primary Skill: `{detail.summary.primary_skill_id or '-'}`",
            f"- Mode: `{detail.summary.mode or '-'}`",
            f"- Index: `{detail.summary.index_id or '(default)'}`",
            f"- Model: `{detail.summary.llm_model or '-'}`",
            "",
            "## Summary",
            detail.summary.summary or "(none)",
            "",
            "## Transcript + Sources",
            "",
        ]
        for idx, msg in enumerate(detail.messages, start=1):
            role = (msg.role or "unknown").capitalize()
            lines.append(f"### {idx}. {role} ({msg.ts or ''})")
            lines.append(msg.content or "")
            if msg.sources:
                lines.append("")
                self._append_sources_markdown(lines, msg.sources)
            lines.append("")

        if detail.feedback:
            lines.extend(["## Feedback", ""])
            for item in detail.feedback:
                vote = "👍" if int(item.vote or 0) > 0 else "👎"
                lines.append(
                    f"- {vote} run_id={item.run_id or '-'} @ {item.ts or ''}: {item.note or ''}"
                )
            lines.append("")

        md_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return md_path, json_path

    def _session_export_payload(self, detail: SessionDetail) -> dict[str, Any]:
        payload = asdict(detail.summary)
        payload["messages"] = []
        for msg in detail.messages:
            payload["messages"].append(
                {
                    "role": msg.role,
                    "content": msg.content,
                    "ts": msg.ts,
                    "run_id": msg.run_id,
                    "sources": [source.to_dict() for source in msg.sources],
                }
            )
        payload["feedback"] = [asdict(item) for item in detail.feedback]
        payload["traces"] = detail.traces or {}
        return payload

    @staticmethod
    def _header_path_label(header_path: str) -> str:
        value = str(header_path or "").strip()
        return value or "(No header path)"

    def _append_sources_markdown(
        self,
        lines: list[str],
        sources: list[EvidenceSource],
    ) -> None:
        normalized = [self._normalize_export_source_item(source) for source in sources]
        if not normalized:
            return
        has_header_groups = any(item.get("header_path") for item in normalized)
        lines.append("Sources:")
        if not has_header_groups:
            for source in normalized:
                lines.append(
                    f"- source={source.get('source') or '-'} | "
                    f"chunk_id={source.get('chunk_id') or '-'} | "
                    f"score={source.get('score') if source.get('score') is not None else '-'}"
                )
            return

        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in normalized:
            grouped.setdefault(self._header_path_label(str(item.get("header_path") or "")), []).append(item)
        for header_label, items in grouped.items():
            lines.append(f"- {header_label}")
            for source in items:
                evidence_id = source.get("chunk_id") or source.get("node_id") or "-"
                lines.append(
                    f"  - source={source.get('source') or '-'} | "
                    f"evidence={evidence_id} | "
                    f"score={source.get('score') if source.get('score') is not None else '-'}"
                )

    @staticmethod
    def _normalize_export_source_item(source: EvidenceSource) -> dict[str, Any]:
        item = source.to_dict()
        item["header_path"] = str(item.get("header_path") or "").strip()
        breadcrumb = str(item.get("breadcrumb") or item.get("header_path") or "").strip()
        item["breadcrumb"] = breadcrumb
        item["breadcrumb_tokens"] = [token.strip() for token in breadcrumb.split(">") if token.strip()]
        return item

    @staticmethod
    def _row_to_summary(row: sqlite3.Row) -> SessionSummary:
        return SessionSummary(
            session_id=str(row["session_id"] or ""),
            created_at=str(row["created_at"] or ""),
            updated_at=str(row["updated_at"] or ""),
            title=str(row["title"] or ""),
            summary=str(row["summary"] or ""),
            active_profile=str(row["active_profile"] or ""),
            mode=str(row["mode"] or ""),
            index_id=str(row["index_id"] or ""),
            vector_backend=str(row["vector_backend"] or ""),
            llm_provider=str(row["llm_provider"] or ""),
            llm_model=str(row["llm_model"] or ""),
            embed_model=str(row["embed_model"] or ""),
            retrieve_k=int(row["retrieve_k"] or 0),
            final_k=int(row["final_k"] or 0),
            mmr_lambda=float(row["mmr_lambda"] or 0.0),
            agentic_iterations=int(row["agentic_iterations"] or 0),
            extra_json=str(row["extra_json"] or "{}"),
        )

    @staticmethod
    def _row_to_message(row: sqlite3.Row) -> SessionMessage:
        parsed_sources: list[EvidenceSource] = []
        try:
            raw_sources = json.loads(row["sources_json"] or "[]")
        except json.JSONDecodeError:
            raw_sources = []
        if isinstance(raw_sources, list):
            parsed_sources = [
                EvidenceSource.from_dict(item)
                for item in raw_sources
                if isinstance(item, dict)
            ]
        return SessionMessage(
            role=str(row["role"] or ""),
            content=str(row["content"] or ""),
            ts=str(row["ts"] or ""),
            run_id=str(row["run_id"] or ""),
            sources=parsed_sources,
        )

    @staticmethod
    def _row_to_feedback(row: sqlite3.Row) -> SessionFeedback:
        return SessionFeedback(
            feedback_id=str(row["feedback_id"] or ""),
            session_id=str(row["session_id"] or ""),
            run_id=str(row["run_id"] or ""),
            vote=int(row["vote"] or 0),
            note=str(row["note"] or ""),
            ts=str(row["ts"] or ""),
        )
