"""Single orchestration layer that composes all Axiom subsystems for the UI.

``WorkspaceOrchestrator`` is the **one** entry point that the API (and any
future UI surface) should call.  It delegates every operation to the existing
engine and service modules — it never duplicates their logic.

Subsystems composed here
------------------------
* **Ingestion / Organisation** — :mod:`axiom_app.engine.indexing` and
  :mod:`axiom_app.engine.index_registry`
* **Retrieval** — :mod:`axiom_app.engine.querying` and
  :mod:`axiom_app.engine.streaming`
* **Graph** — :mod:`axiom_app.models.brain_graph`
* **Sessions / Memory** — :class:`~axiom_app.services.session_repository.SessionRepository`
* **Skills** — :class:`~axiom_app.services.skill_repository.SkillRepository`
* **Settings** — :mod:`axiom_app.settings_store`
"""

from __future__ import annotations

import json
import os
import pathlib
from collections.abc import Callable, Iterator
from typing import Any

import axiom_app.settings_store as _settings_store
from axiom_app.engine import (
    build_index,
    get_index,
    list_indexes,
    query_direct,
    query_rag,
    stream_rag_answer,
)
from axiom_app.engine.indexing import IndexBuildRequest, IndexBuildResult
from axiom_app.engine.querying import (
    DirectQueryRequest,
    DirectQueryResult,
    RagQueryRequest,
    RagQueryResult,
)
from axiom_app.models.brain_graph import BrainGraph
from axiom_app.models.session_types import (
    EvidenceSource,
    SessionDetail,
    SessionSummary,
)
from axiom_app.services.assistant_companion import AssistantCompanionService
from axiom_app.services.session_repository import SessionRepository
from axiom_app.services.skill_repository import SkillRepository
from axiom_app.services.trace_store import TraceStore
from axiom_app.models.parity_types import SkillDefinition


class WorkspaceOrchestrator:
    """Unified orchestration facade over all Axiom subsystems.

    All parameters are optional; the orchestrator resolves sensible defaults
    from environment variables and on-disk configuration when they are omitted.

    Parameters
    ----------
    session_repo:
        An initialised :class:`~axiom_app.services.session_repository.SessionRepository`.
        When ``None`` the orchestrator creates one from the environment variable
        ``AXIOM_SESSION_DB_PATH`` (or the default on-disk path).
    skill_repo:
        An initialised :class:`~axiom_app.services.skill_repository.SkillRepository`.
        When ``None`` the orchestrator creates one pointing at the default
        ``skills/`` directory in the repository root.
    index_dir:
        Directory that contains persisted index bundles.  ``None`` defers to
        the engine default.
    """

    def __init__(
        self,
        session_repo: SessionRepository | None = None,
        skill_repo: SkillRepository | None = None,
        index_dir: pathlib.Path | str | None = None,
        assistant_service: AssistantCompanionService | None = None,
    ) -> None:
        self._session_repo: SessionRepository = session_repo or _make_session_repo()
        self._skill_repo: SkillRepository = skill_repo or SkillRepository()
        self._index_dir: pathlib.Path | str | None = index_dir
        self._trace_store = TraceStore()
        self._assistant_service = assistant_service or AssistantCompanionService(
            session_repo=self._session_repo,
            trace_store=self._trace_store,
        )

    # ------------------------------------------------------------------
    # Ingestion / Organisation
    # ------------------------------------------------------------------

    def ingest_documents(
        self,
        document_paths: list[str],
        settings: dict[str, Any],
        *,
        index_id: str | None = None,
        progress_cb: Callable[[dict[str, Any]], None] | None = None,
    ) -> IndexBuildResult:
        return self.build_index(
            document_paths,
            settings,
            index_id=index_id,
            progress_cb=progress_cb,
        )

    def build_index(
        self,
        document_paths: list[str],
        settings: dict[str, Any],
        *,
        index_id: str | None = None,
        progress_cb: Callable[[dict[str, Any]], None] | None = None,
    ) -> IndexBuildResult:
        """Build a new index from *document_paths* using the engine pipeline.

        Delegates to :func:`axiom_app.engine.build_index` without duplicating
        any ingestion logic.
        """
        resolved_settings = self._resolve_query_settings(settings)
        req = IndexBuildRequest(
            document_paths=document_paths,
            settings=resolved_settings,
            index_id=index_id,
        )
        result = build_index(req, progress_cb=progress_cb)
        self._assistant_service.reflect(
            trigger="index_build",
            settings=resolved_settings,
            context_id=f"index:{result.index_id}",
        )
        return result

    def list_indexes(self) -> list[dict[str, Any]]:
        """Return metadata for all persisted indexes."""
        return list_indexes(self._index_dir)

    def get_index(self, index_id: str) -> dict[str, Any] | None:
        """Return metadata for a single index, or ``None`` if not found."""
        return get_index(index_id, self._index_dir)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def run_rag_query(
        self,
        req: RagQueryRequest,
        *,
        session_id: str = "",
    ) -> RagQueryResult:
        """Execute a batch RAG query via the engine."""
        resolved_settings = self._resolve_query_settings(req.settings)
        normalized = RagQueryRequest(
            manifest_path=req.manifest_path,
            question=req.question,
            settings=resolved_settings,
            run_id=req.run_id,
            require_action=req.require_action,
        )
        if session_id:
            self._prepare_session_for_query(session_id, req.question, resolved_settings, manifest_path=req.manifest_path)
            self.append_message(session_id, role="user", content=req.question, run_id="")
        result = query_rag(normalized)
        self._record_trace_event(
            result.run_id,
            {
                "type": "retrieval_complete",
                "run_id": result.run_id,
                "sources": result.sources,
                "context_block": result.context_block,
                "top_score": result.top_score,
            },
        )
        self._record_trace_event(
            result.run_id,
            {
                "type": "final",
                "run_id": result.run_id,
                "answer_text": result.answer_text,
                "sources": result.sources,
            },
        )
        if session_id:
            self.append_message(
                session_id,
                role="assistant",
                content=result.answer_text,
                run_id=result.run_id,
                sources=[EvidenceSource.from_dict(item) for item in result.sources],
            )
            self._assistant_service.reflect(
                trigger="completed_run",
                settings=resolved_settings,
                session_id=session_id,
                run_id=result.run_id,
            )
        return result

    def run_direct_query(
        self,
        req: DirectQueryRequest,
        *,
        session_id: str = "",
    ) -> DirectQueryResult:
        """Execute a direct (no-retrieval) LLM query via the engine."""
        resolved_settings = self._resolve_query_settings(req.settings)
        normalized = DirectQueryRequest(
            prompt=req.prompt,
            settings=resolved_settings,
            run_id=req.run_id,
        )
        if session_id:
            self._prepare_session_for_query(session_id, req.prompt, resolved_settings)
            self.append_message(session_id, role="user", content=req.prompt, run_id="")
        result = query_direct(normalized)
        self._record_trace_event(
            result.run_id,
            {
                "type": "final",
                "run_id": result.run_id,
                "answer_text": result.answer_text,
                "sources": [],
            },
        )
        if session_id:
            self.append_message(
                session_id,
                role="assistant",
                content=result.answer_text,
                run_id=result.run_id,
                sources=[],
            )
            self._assistant_service.reflect(
                trigger="completed_run",
                settings=resolved_settings,
                session_id=session_id,
                run_id=result.run_id,
            )
        return result

    def stream_rag_query(
        self,
        req: RagQueryRequest,
        cancel_token: Any = None,
        *,
        session_id: str = "",
    ) -> Iterator[dict[str, Any]]:
        """Yield SSE-ready event dicts for a streaming RAG query.

        Delegates to :func:`axiom_app.engine.stream_rag_answer`.
        """
        resolved_settings = self._resolve_query_settings(req.settings)
        normalized = RagQueryRequest(
            manifest_path=req.manifest_path,
            question=req.question,
            settings=resolved_settings,
            run_id=req.run_id,
            require_action=req.require_action,
        )
        if session_id:
            self._prepare_session_for_query(
                session_id,
                req.question,
                resolved_settings,
                manifest_path=req.manifest_path,
            )
            self.append_message(session_id, role="user", content=req.question, run_id="")

        def _wrapped() -> Iterator[dict[str, Any]]:
            pending_sources: list[EvidenceSource] = []
            final_run_id = str(normalized.run_id or "")
            for event in stream_rag_answer(normalized, cancel_token=cancel_token):
                event_run_id = str(event.get("run_id") or final_run_id or "").strip()
                if event_run_id:
                    final_run_id = event_run_id
                self._record_trace_event(final_run_id, event)
                if event.get("type") == "retrieval_complete":
                    pending_sources = [
                        item if isinstance(item, EvidenceSource) else EvidenceSource.from_dict(item)
                        for item in list(event.get("sources") or [])
                    ]
                elif event.get("type") == "final" and session_id:
                    final_sources = [
                        item if isinstance(item, EvidenceSource) else EvidenceSource.from_dict(item)
                        for item in list(event.get("sources") or pending_sources)
                    ]
                    self.append_message(
                        session_id,
                        role="assistant",
                        content=str(event.get("answer_text") or ""),
                        run_id=final_run_id,
                        sources=final_sources,
                    )
                    self._assistant_service.reflect(
                        trigger="completed_run",
                        settings=resolved_settings,
                        session_id=session_id,
                        run_id=final_run_id,
                    )
                yield event

        return _wrapped()

    # ------------------------------------------------------------------
    # Graph / Brain canvas
    # ------------------------------------------------------------------

    def get_workspace_graph(self) -> BrainGraph:
        """Build and return the :class:`~axiom_app.models.brain_graph.BrainGraph`.

        Fetches indexes from the engine registry and sessions from the
        session repository, then delegates graph construction to
        :meth:`BrainGraph.build_from_indexes_and_sessions`.
        """
        indexes = self.list_indexes()
        sessions = self._session_repo.list_sessions()
        assistant_snapshot = self._assistant_service.get_snapshot(_settings_store.load_settings())
        return BrainGraph().build_from_indexes_and_sessions(indexes, sessions, assistant_snapshot)

    # ------------------------------------------------------------------
    # Sessions / Memory
    # ------------------------------------------------------------------

    def list_sessions(
        self,
        *,
        search: str = "",
        skill: str = "",
    ) -> list[SessionSummary]:
        """Return session summaries with optional filtering."""
        return self._session_repo.list_sessions(search=search, skill=skill)

    def get_session(self, session_id: str) -> SessionDetail | None:
        """Return the full session detail, or ``None`` if not found."""
        return self._session_repo.get_session(session_id)

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
        """Create a new chat session and return its summary."""
        return self._session_repo.create_session(
            title=title,
            summary=summary,
            active_profile=active_profile,
            mode=mode,
            index_id=index_id,
            vector_backend=vector_backend,
            llm_provider=llm_provider,
            llm_model=llm_model,
            embed_model=embed_model,
            retrieve_k=retrieve_k,
            final_k=final_k,
            mmr_lambda=mmr_lambda,
            agentic_iterations=agentic_iterations,
            extra_json=extra_json,
            session_id=session_id,
        )

    def upsert_session(self, session_id: str, **kwargs: Any) -> SessionSummary:
        """Create-or-update a session by *session_id*."""
        return self._session_repo.upsert_session(session_id, **kwargs)

    def append_message(
        self,
        session_id: str,
        *,
        role: str,
        content: str,
        run_id: str = "",
        sources: list[dict[str, Any]] | None = None,
    ) -> None:
        """Append a message to *session_id*."""
        self._session_repo.append_message(
            session_id,
            role=role,
            content=content,
            run_id=run_id,
            sources=sources or [],
        )

    def save_feedback(
        self,
        session_id: str,
        *,
        run_id: str,
        vote: int,
        note: str = "",
    ) -> None:
        """Persist thumbs-up/down feedback for a run."""
        self._session_repo.save_feedback(
            session_id,
            run_id=run_id,
            vote=vote,
            note=note,
        )

    def delete_session(self, session_id: str) -> None:
        """Permanently delete a session and all its messages."""
        self._session_repo.delete_session(session_id)

    # ------------------------------------------------------------------
    # Skills
    # ------------------------------------------------------------------

    def list_skills(self) -> list[SkillDefinition]:
        """Return all valid skill definitions from the skills directory."""
        return self._skill_repo.list_valid_skills()

    def get_skill(self, skill_id: str) -> SkillDefinition | None:
        """Return a single skill definition by *skill_id*, or ``None``."""
        return self._skill_repo.get_skill(skill_id)

    # ------------------------------------------------------------------
    # Assistant / companion
    # ------------------------------------------------------------------

    def get_assistant_snapshot(self, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        resolved_settings = self._resolve_query_settings(settings or {})
        return self._assistant_service.get_snapshot(resolved_settings)

    def update_assistant(
        self,
        *,
        identity: dict[str, Any] | None = None,
        runtime: dict[str, Any] | None = None,
        policy: dict[str, Any] | None = None,
        status: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._assistant_service.update_config(
            identity=identity,
            runtime=runtime,
            policy=policy,
            status=status,
        )

    def bootstrap_assistant(self, *, install_local_model: bool = False) -> dict[str, Any]:
        return self._assistant_service.bootstrap_runtime(install_local_model=install_local_model)

    def list_assistant_memory(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return [
            item.to_payload()
            for item in self._assistant_service.repository.list_memory(limit=limit)
        ]

    def clear_assistant_memory(self, *, limit: int = 10) -> dict[str, Any]:
        return self._assistant_service.clear_recent_memory(limit=limit)

    def reflect_assistant(
        self,
        *,
        trigger: str,
        context_id: str = "",
        session_id: str = "",
        run_id: str = "",
        force: bool = False,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_settings = self._resolve_query_settings(settings or {})
        kwargs: dict[str, Any] = {
            "trigger": trigger,
            "settings": resolved_settings,
            "session_id": session_id,
            "run_id": run_id,
            "force": force,
        }
        if context_id:
            kwargs["context_id"] = context_id
        return self._assistant_service.reflect(
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_query_settings(self, incoming: dict[str, Any]) -> dict[str, Any]:
        base = _settings_store.load_settings()
        merged = dict(base)
        merged.update(dict(incoming or {}))
        merged["assistant_identity"] = base.get("assistant_identity", {})
        merged["assistant_runtime"] = base.get("assistant_runtime", {})
        merged["assistant_policy"] = base.get("assistant_policy", {})
        return merged

    def _prepare_session_for_query(
        self,
        session_id: str,
        title_seed: str,
        settings: dict[str, Any],
        *,
        manifest_path: str | pathlib.Path | None = None,
    ) -> None:
        summary = self.get_session(session_id)
        title = summary.summary.title if summary is not None else (title_seed[:60] or "New Chat")
        llm_model = str(settings.get("llm_model_custom") or settings.get("llm_model") or "")
        embed_model = str(
            settings.get("embedding_model_custom")
            or settings.get("embedding_model")
            or settings.get("sentence_transformers_model")
            or ""
        )
        index_id = self._resolve_index_id_from_manifest(manifest_path)
        extra = {
            "assistant": self.get_assistant_snapshot(settings),
        }
        self.upsert_session(
            session_id,
            title=title,
            active_profile=str(settings.get("selected_mode") or ""),
            mode=str(settings.get("selected_mode") or ""),
            index_id=index_id,
            vector_backend=str(settings.get("vector_db_type") or "json"),
            llm_provider=str(settings.get("llm_provider") or ""),
            llm_model=llm_model,
            embed_model=embed_model,
            retrieve_k=int(settings.get("retrieval_k") or settings.get("top_k") or 0),
            final_k=int(settings.get("top_k") or 0),
            mmr_lambda=float(settings.get("mmr_lambda") or 0.0),
            agentic_iterations=int(settings.get("agentic_max_iterations") or 0),
            extra_json=json.dumps(extra, ensure_ascii=False),
        )

    def _resolve_index_id_from_manifest(self, manifest_path: str | pathlib.Path | None) -> str:
        candidate = str(manifest_path or "").strip()
        if not candidate:
            return ""
        for row in self.list_indexes():
            if str(row.get("manifest_path") or "").strip() == candidate:
                return str(row.get("index_id") or row.get("collection_name") or "")
        return ""

    def _record_trace_event(self, run_id: str, event: dict[str, Any]) -> None:
        normalized_run_id = str(run_id or event.get("run_id") or "").strip()
        event_type = str(event.get("type") or "").strip()
        if not normalized_run_id or not event_type or event_type == "token":
            return
        payload = {
            key: value
            for key, value in dict(event or {}).items()
            if key not in {"type", "run_id"}
        }
        stage_map = {
            "run_started": "retrieval",
            "retrieval_complete": "retrieval",
            "retrieval_augmented": "retrieval",
            "subqueries": "retrieval",
            "iteration_start": "reflection",
            "gaps_identified": "reflection",
            "refinement_retrieval": "retrieval",
            "final": "synthesis",
            "error": "error",
            "action_required": "action_required",
        }
        self._trace_store.append_event(
            run_id=normalized_run_id,
            stage=stage_map.get(event_type, "event"),
            event_type=event_type,
            payload=payload,
        )

    def enabled_skills(self, settings: dict[str, Any]) -> list[SkillDefinition]:
        """Return skills that are enabled for the given *settings* snapshot."""
        return self._skill_repo.enabled_skills(settings)

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def load_settings(self) -> dict[str, Any]:
        """Return the active settings, merged from defaults and user overrides."""
        return _settings_store.load_settings()

    def save_settings(self, updates: dict[str, Any]) -> dict[str, Any]:
        """Persist *updates* to settings.json and return the merged result."""
        return _settings_store.save_settings(updates)

    def safe_settings(self, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return settings with ``api_key_*`` fields redacted."""
        payload = settings if settings is not None else self.load_settings()
        return _settings_store.safe_settings(payload)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _make_session_repo() -> SessionRepository:
    db_path = os.getenv("AXIOM_SESSION_DB_PATH") or None
    repo = SessionRepository(db_path=db_path)
    repo.init_db()
    return repo
