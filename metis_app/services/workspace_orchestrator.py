"""Single orchestration layer that composes all METIS subsystems for the UI.

``WorkspaceOrchestrator`` is the **one** entry point that the API (and any
future UI surface) should call.  It delegates every operation to the existing
engine and service modules — it never duplicates their logic.

Subsystems composed here
------------------------
* **Ingestion / Organisation** — :mod:`metis_app.engine.indexing` and
  :mod:`metis_app.engine.index_registry`
* **Retrieval** — :mod:`metis_app.engine.querying` and
  :mod:`metis_app.engine.streaming`
* **Graph** — :mod:`metis_app.models.brain_graph`
* **Sessions / Memory** — :class:`~metis_app.services.session_repository.SessionRepository`
* **Skills** — :class:`~metis_app.services.skill_repository.SkillRepository`
* **Settings** — :mod:`metis_app.settings_store`
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
import re
import threading
from collections.abc import Callable, Iterator
from typing import Any

import metis_app.settings_store as _settings_store
from metis_app.engine import (
    build_index,
    delete_index,
    forecast_preflight,
    get_index,
    inspect_forecast_schema,
    knowledge_search,
    list_indexes,
    query_forecast,
    query_direct,
    query_rag,
    query_swarm,
    stream_forecast,
    stream_rag_answer,
)
from metis_app.engine.indexing import IndexBuildRequest, IndexBuildResult
from metis_app.engine.querying import (
    DirectQueryRequest,
    DirectQueryResult,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    RagQueryRequest,
    RagQueryResult,
    SwarmQueryRequest,
    SwarmQueryResult,
    extract_arrow_artifacts,
)
from metis_app.engine.forecasting import ForecastQueryRequest, ForecastSchemaRequest
from metis_app.models.atlas_types import AtlasEntry
from metis_app.models.brain_graph import BrainGraph
from metis_app.models.improvement_types import ImprovementEntry
from metis_app.models.session_types import (
    EvidenceSource,
    SessionDetail,
    SessionSummary,
)
from metis_app.services.atlas_repository import AtlasRepository
from metis_app.services.assistant_companion import AssistantCompanionService
from metis_app.services.improvement_repository import ImprovementRepository
from metis_app.services.learning_route_service import (
    LearningRouteIndexSummary,
    LearningRoutePreviewRequest,
    LearningRouteStarSnapshot,
    plan_learning_route_preview,
)
from metis_app.services.nyx_catalog import (
    NyxCatalogBroker,
    NyxCatalogComponentDetail,
    NyxCatalogSearchResult,
    get_default_nyx_catalog_broker,
)
from metis_app.services.nyx_runtime import augment_settings_with_nyx, build_nyx_install_actions
from metis_app.services.session_repository import SessionRepository
from metis_app.services.skill_repository import SkillRepository, _DEFAULT_CANDIDATES_DB_PATH
from metis_app.services.trace_store import TraceStore
from metis_app.models.parity_types import SkillDefinition

log = logging.getLogger(__name__)

# Module-level in-process flag: True while any autonomous research run is
# executing. Used by GET /v1/autonomous/status so the UI can dim the
# "Research Now" button or reflect an in-flight run. Guarded by a lock
# because run_autonomous_research may be invoked concurrently from the SSE
# endpoint and the fire-and-forget trigger endpoint.
_autonomous_running_lock = threading.Lock()
_autonomous_running_count = 0


def is_autonomous_research_running() -> bool:
    """Return True if any autonomous research run is currently in flight."""
    with _autonomous_running_lock:
        return _autonomous_running_count > 0


class WorkspaceOrchestrator:
    """Unified orchestration facade over all METIS subsystems.

    All parameters are optional; the orchestrator resolves sensible defaults
    from environment variables and on-disk configuration when they are omitted.

    Parameters
    ----------
    session_repo:
        An initialised :class:`~metis_app.services.session_repository.SessionRepository`.
        When ``None`` the orchestrator creates one from the environment variable
        ``METIS_SESSION_DB_PATH`` (or the default on-disk path).
    skill_repo:
        An initialised :class:`~metis_app.services.skill_repository.SkillRepository`.
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
        nyx_catalog: NyxCatalogBroker | None = None,
        atlas_repo: AtlasRepository | None = None,
        improvement_repo: ImprovementRepository | None = None,
    ) -> None:
        self._session_repo: SessionRepository = session_repo or _make_session_repo()
        self._skill_repo: SkillRepository = skill_repo or SkillRepository()
        self._index_dir: pathlib.Path | str | None = index_dir
        self._trace_store = TraceStore()
        self._atlas_repo = atlas_repo or AtlasRepository()
        self._improvement_repo = improvement_repo or ImprovementRepository()
        self._assistant_service = assistant_service or AssistantCompanionService(
            session_repo=self._session_repo,
            trace_store=self._trace_store,
        )
        self._nyx_catalog = nyx_catalog or get_default_nyx_catalog_broker()

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

        Delegates to :func:`metis_app.engine.build_index` without duplicating
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
            _orchestrator=self,
        )
        return result

    def list_indexes(self) -> list[dict[str, Any]]:
        """Return metadata for all persisted indexes."""
        return list_indexes(self._index_dir)

    def get_index(self, index_id: str) -> dict[str, Any] | None:
        """Return metadata for a single index, or ``None`` if not found."""
        return get_index(index_id, self._index_dir)

    def delete_index(self, manifest_path: str | pathlib.Path) -> dict[str, Any]:
        """Delete a persisted index by manifest or legacy bundle path."""
        return delete_index(manifest_path)

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
        resolved_settings = self._resolve_query_settings(req.settings, query=req.question)
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
        result.actions = self._resolve_nyx_install_actions(
            result.run_id,
            resolved_settings,
            getattr(result, "artifacts", None),
        ) or None
        result_artifacts = list(getattr(result, "artifacts", None) or []) if isinstance(getattr(result, "artifacts", None), list) else []
        result_actions = list(getattr(result, "actions", None) or []) if isinstance(getattr(result, "actions", None), list) else []
        for stage in list(result.retrieval_plan.get("stages") or []):
            stage_type = str(stage.get("stage_type") or "").strip()
            payload = dict(stage.get("payload") or {})
            if not stage_type:
                continue
            self._record_trace_event(
                result.run_id,
                {
                    "type": (
                        "subqueries"
                        if stage_type == "query_expansion"
                        else stage_type
                    ),
                    "run_id": result.run_id,
                    **(
                        {"fallback": payload}
                        if stage_type == "fallback_decision"
                        else payload
                    ),
                },
            )
        self._record_trace_event(
            result.run_id,
            {
                "type": "final",
                "run_id": result.run_id,
                "answer_text": result.answer_text,
                "sources": result.sources,
                "fallback": result.fallback,
                **({"artifacts": result_artifacts} if result_artifacts else {}),
                **({"actions": result_actions} if result_actions else {}),
            },
        )
        if session_id:
            self.append_message(
                session_id,
                role="assistant",
                content=result.answer_text,
                run_id=result.run_id,
                sources=[EvidenceSource.from_dict(item) for item in result.sources],
                artifacts=result_artifacts,
                actions=result_actions,
            )
            self._maybe_create_atlas_candidate(
                session_id=session_id,
                question=req.question,
                run_id=result.run_id,
                answer_text=result.answer_text,
                sources=result.sources,
                selected_mode=result.selected_mode,
                top_score=result.top_score,
                fallback=result.fallback,
            )
            self._assistant_service.reflect(
                trigger="completed_run",
                settings=resolved_settings,
                session_id=session_id,
                run_id=result.run_id,
                _orchestrator=self,
            )
        return result

    def run_direct_query(
        self,
        req: DirectQueryRequest,
        *,
        session_id: str = "",
    ) -> DirectQueryResult:
        """Execute a direct (no-retrieval) LLM query via the engine."""
        resolved_settings = self._resolve_query_settings(req.settings, query=req.prompt)
        normalized = DirectQueryRequest(
            prompt=req.prompt,
            settings=resolved_settings,
            run_id=req.run_id,
        )
        if session_id:
            self._prepare_session_for_query(session_id, req.prompt, resolved_settings)
            self.append_message(session_id, role="user", content=req.prompt, run_id="")
        result = query_direct(normalized)
        result.actions = self._resolve_nyx_install_actions(
            result.run_id,
            resolved_settings,
            getattr(result, "artifacts", None),
        ) or None
        result_artifacts = list(getattr(result, "artifacts", None) or []) if isinstance(getattr(result, "artifacts", None), list) else []
        result_actions = list(getattr(result, "actions", None) or []) if isinstance(getattr(result, "actions", None), list) else []
        self._record_trace_event(
            result.run_id,
            {
                "type": "final",
                "run_id": result.run_id,
                "answer_text": result.answer_text,
                "sources": [],
                **({"artifacts": result_artifacts} if result_artifacts else {}),
                **({"actions": result_actions} if result_actions else {}),
            },
        )
        if session_id:
            self.append_message(
                session_id,
                role="assistant",
                content=result.answer_text,
                run_id=result.run_id,
                sources=[],
                artifacts=result_artifacts,
                actions=result_actions,
            )
            self._assistant_service.reflect(
                trigger="completed_run",
                settings=resolved_settings,
                session_id=session_id,
                run_id=result.run_id,
                _orchestrator=self,
            )
        return result

    def run_knowledge_search(
        self,
        req: KnowledgeSearchRequest,
        *,
        session_id: str = "",
    ) -> KnowledgeSearchResult:
        """Execute retrieval-only knowledge search via the engine."""
        resolved_settings = self._resolve_query_settings(req.settings)
        normalized = KnowledgeSearchRequest(
            manifest_path=req.manifest_path,
            question=req.question,
            settings=resolved_settings,
            run_id=req.run_id,
        )
        if session_id:
            self._prepare_session_for_query(session_id, req.question, resolved_settings, manifest_path=req.manifest_path)
            self.append_message(session_id, role="user", content=req.question, run_id="")
        result = knowledge_search(normalized)
        for stage in list(result.retrieval_plan.get("stages") or []):
            stage_type = str(stage.get("stage_type") or "").strip()
            payload = dict(stage.get("payload") or {})
            if not stage_type:
                continue
            self._record_trace_event(
                result.run_id,
                {
                    "type": (
                        "subqueries"
                        if stage_type == "query_expansion"
                        else stage_type
                    ),
                    "run_id": result.run_id,
                    **(
                        {"fallback": payload}
                        if stage_type == "fallback_decision"
                        else payload
                    ),
                },
            )
        self._record_trace_event(
            result.run_id,
            {
                "type": "knowledge_search_complete",
                "run_id": result.run_id,
                "sources": result.sources,
                "context_block": result.context_block,
                "top_score": result.top_score,
                "fallback": result.fallback,
            },
        )
        if session_id:
            self.append_message(
                session_id,
                role="assistant",
                content=result.summary_text,
                run_id=result.run_id,
                sources=[EvidenceSource.from_dict(item) for item in result.sources],
            )
            self._assistant_service.reflect(
                trigger="completed_run",
                settings=resolved_settings,
                session_id=session_id,
                run_id=result.run_id,
                _orchestrator=self,
            )
        return result

    def run_swarm_query(
        self,
        req: SwarmQueryRequest,
        *,
        session_id: str = "",
    ) -> SwarmQueryResult:
        """Execute a swarm simulation query via the engine."""
        resolved_settings = self._resolve_query_settings(req.settings, query=req.question)
        normalized = SwarmQueryRequest(
            manifest_path=req.manifest_path,
            question=req.question,
            settings=resolved_settings,
            run_id=req.run_id,
            n_personas=req.n_personas,
            n_rounds=req.n_rounds,
            topics=req.topics,
        )
        if session_id:
            self._prepare_session_for_query(session_id, req.question, resolved_settings, manifest_path=req.manifest_path)
            self.append_message(session_id, role="user", content=req.question, run_id="")
        result = query_swarm(normalized)
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
                _orchestrator=self,
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

        Delegates to :func:`metis_app.engine.stream_rag_answer`.
        """
        resolved_settings = self._resolve_query_settings(req.settings, query=req.question)
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
            pending_top_score = 0.0
            final_run_id = str(normalized.run_id or "")
            for raw_event in stream_rag_answer(normalized, cancel_token=cancel_token):
                event = dict(raw_event)
                event_run_id = str(event.get("run_id") or final_run_id or "").strip()
                if event_run_id:
                    final_run_id = event_run_id
                if event.get("type") == "final":
                    nyx_actions = self._resolve_nyx_install_actions(
                        final_run_id,
                        resolved_settings,
                        event.get("artifacts"),
                    )
                    if nyx_actions:
                        event["actions"] = nyx_actions
                self._record_trace_event(final_run_id, event)
                if event.get("type") in {"retrieval_complete", "retrieval_augmented"}:
                    pending_sources = [
                        item if isinstance(item, EvidenceSource) else EvidenceSource.from_dict(item)
                        for item in list(event.get("sources") or [])
                    ]
                    try:
                        pending_top_score = float(event.get("top_score") or 0.0)
                    except (TypeError, ValueError):
                        pending_top_score = 0.0
                elif (
                    event.get("type") == "iteration_complete"
                    and int(event.get("iterations_used", 0)) >= 2
                ):
                    self._assistant_service.capture_skill_candidate(
                        db_path=_DEFAULT_CANDIDATES_DB_PATH,
                        query_text=str(event.get("query_text") or normalized.question),
                        trace_json=json.dumps(event),
                        convergence_score=float(event.get("convergence_score") or 0.0),
                        trace_iterations=int(event.get("iterations_used") or 0),
                    )
                elif event.get("type") == "final" and session_id:
                    final_sources = [
                        item if isinstance(item, EvidenceSource) else EvidenceSource.from_dict(item)
                        for item in list(event.get("sources") or pending_sources)
                    ]
                    final_artifacts = [
                        dict(item)
                        for item in list(event.get("artifacts") or [])
                        if isinstance(item, dict)
                    ]
                    final_actions = [
                        dict(item)
                        for item in list(event.get("actions") or [])
                        if isinstance(item, dict)
                    ]
                    self.append_message(
                        session_id,
                        role="assistant",
                        content=str(event.get("answer_text") or ""),
                        run_id=final_run_id,
                        sources=final_sources,
                        artifacts=final_artifacts,
                        actions=final_actions,
                    )
                    self._maybe_create_atlas_candidate(
                        session_id=session_id,
                        question=req.question,
                        run_id=final_run_id,
                        answer_text=str(event.get("answer_text") or ""),
                        sources=[
                            item.to_dict() if isinstance(item, EvidenceSource) else dict(item)
                            for item in final_sources
                        ],
                        selected_mode=str(resolved_settings.get("selected_mode") or ""),
                        top_score=pending_top_score,
                        fallback=dict(event.get("fallback") or {}),
                    )
                    self._assistant_service.reflect(
                        trigger="completed_run",
                        settings=resolved_settings,
                        session_id=session_id,
                        run_id=final_run_id,
                        _orchestrator=self,
                    )
                yield event

        return _wrapped()

    def get_forecast_preflight(self, settings: dict[str, Any] | None = None) -> dict[str, Any]:
        resolved_settings = self._resolve_query_settings(settings or {})
        resolved_settings["selected_mode"] = "Forecast"
        return forecast_preflight(resolved_settings).to_dict()

    def inspect_forecast_schema(self, req: ForecastSchemaRequest) -> dict[str, Any]:
        return inspect_forecast_schema(req).to_dict()

    def run_forecast_query(
        self,
        req: ForecastQueryRequest,
        *,
        session_id: str = "",
    ) -> Any:
        resolved_settings = self._resolve_query_settings(req.settings, query=req.prompt)
        resolved_settings["selected_mode"] = "Forecast"
        normalized = ForecastQueryRequest(
            file_path=req.file_path,
            prompt=req.prompt,
            mapping=req.mapping,
            settings=resolved_settings,
            horizon=req.horizon,
            run_id=req.run_id,
        )
        user_prompt = str(req.prompt or "").strip() or f"Forecast {pathlib.Path(req.file_path).name}"
        if session_id:
            self._prepare_session_for_query(session_id, user_prompt, resolved_settings)
            self.append_message(session_id, role="user", content=user_prompt, run_id="")

        result = query_forecast(normalized)
        result_artifacts = list(getattr(result, "artifacts", None) or [])
        self._record_trace_event(
            result.run_id,
            {
                "type": "final",
                "run_id": result.run_id,
                "answer_text": result.answer_text,
                "sources": [],
                "artifacts": result_artifacts,
                "selected_mode": result.selected_mode,
                "model_backend": result.model_backend,
                "model_id": result.model_id,
                "horizon": result.horizon,
                "context_used": result.context_used,
                "warnings": list(getattr(result, "warnings", []) or []),
            },
        )
        if session_id:
            self.append_message(
                session_id,
                role="assistant",
                content=result.answer_text,
                run_id=result.run_id,
                sources=[],
                artifacts=result_artifacts,
                actions=[],
            )
            self._assistant_service.reflect(
                trigger="completed_run",
                settings=resolved_settings,
                session_id=session_id,
                run_id=result.run_id,
                _orchestrator=self,
            )
        return result

    def stream_forecast_query(
        self,
        req: ForecastQueryRequest,
        *,
        session_id: str = "",
    ) -> Iterator[dict[str, Any]]:
        resolved_settings = self._resolve_query_settings(req.settings, query=req.prompt)
        resolved_settings["selected_mode"] = "Forecast"
        normalized = ForecastQueryRequest(
            file_path=req.file_path,
            prompt=req.prompt,
            mapping=req.mapping,
            settings=resolved_settings,
            horizon=req.horizon,
            run_id=req.run_id,
        )
        user_prompt = str(req.prompt or "").strip() or f"Forecast {pathlib.Path(req.file_path).name}"
        if session_id:
            self._prepare_session_for_query(session_id, user_prompt, resolved_settings)
            self.append_message(session_id, role="user", content=user_prompt, run_id="")

        def _wrapped() -> Iterator[dict[str, Any]]:
            final_run_id = str(normalized.run_id or "")
            for event in stream_forecast(normalized):
                final_run_id = str(event.get("run_id") or final_run_id or "").strip()
                self._record_trace_event(final_run_id, event)
                if event.get("type") == "final" and session_id:
                    final_artifacts = [
                        dict(item)
                        for item in list(event.get("artifacts") or [])
                        if isinstance(item, dict)
                    ]
                    self.append_message(
                        session_id,
                        role="assistant",
                        content=str(event.get("answer_text") or ""),
                        run_id=final_run_id,
                        sources=[],
                        artifacts=final_artifacts,
                        actions=[],
                    )
                    self._assistant_service.reflect(
                        trigger="completed_run",
                        settings=resolved_settings,
                        session_id=session_id,
                        run_id=final_run_id,
                        _orchestrator=self,
                    )
                yield event

        return _wrapped()

    # ------------------------------------------------------------------
    # Graph / Brain canvas
    # ------------------------------------------------------------------

    def get_workspace_graph(self, *, skip_layout: bool = False) -> BrainGraph:
        """Build and return the :class:`~metis_app.models.brain_graph.BrainGraph`.

        Fetches indexes from the engine registry and sessions from the
        session repository, then delegates graph construction to
        :meth:`BrainGraph.build_from_indexes_and_sessions`.
        """
        indexes = self.list_indexes()
        sessions = self._session_repo.list_sessions()
        assistant_snapshot = self._assistant_service.get_snapshot(_settings_store.load_settings())
        return BrainGraph().build_from_indexes_and_sessions(indexes, sessions, assistant_snapshot, skip_layout=skip_layout)

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
        artifacts: list[dict[str, Any]] | None = None,
        actions: list[dict[str, Any]] | None = None,
    ) -> None:
        """Append a message to *session_id*."""
        self._session_repo.append_message(
            session_id,
            role=role,
            content=content,
            run_id=run_id,
            sources=sources or [],
            artifacts=artifacts or [],
            actions=actions or [],
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

    def get_atlas_candidate(
        self,
        *,
        session_id: str,
        run_id: str,
    ) -> dict[str, Any] | None:
        """Return a pending Atlas candidate for one session/run pair."""
        entry = self._atlas_repo.get_candidate(session_id=session_id, run_id=run_id)
        return entry.to_payload() if entry is not None else None

    def save_atlas_entry(
        self,
        *,
        session_id: str,
        run_id: str,
        title: str | None = None,
        summary: str | None = None,
    ) -> dict[str, Any]:
        """Promote a candidate into a saved Atlas entry and materialize markdown."""
        entry = self._atlas_repo.save(
            session_id=session_id,
            run_id=run_id,
            title=title,
            summary=summary,
        )
        return entry.to_payload()

    def decide_atlas_candidate(
        self,
        *,
        session_id: str,
        run_id: str,
        decision: str,
    ) -> dict[str, Any]:
        """Persist a non-save decision for a candidate."""
        entry = self._atlas_repo.decide(
            session_id=session_id,
            run_id=run_id,
            decision=str(decision or "").strip().lower(),
        )
        return entry.to_payload()

    def list_atlas_entries(self, *, limit: int = 20) -> list[dict[str, Any]]:
        """List recently saved Atlas entries."""
        return [
            entry.to_payload()
            for entry in self._atlas_repo.list_entries(limit=limit)
        ]

    def get_atlas_entry(self, entry_id: str) -> dict[str, Any] | None:
        entry = self._atlas_repo.get_entry(entry_id)
        return entry.to_payload() if entry is not None else None

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
    # Nyx catalog
    # ------------------------------------------------------------------

    def search_nyx_catalog(
        self,
        *,
        query: str = "",
        limit: int | None = None,
    ) -> NyxCatalogSearchResult:
        """Return the curated Nyx catalog with optional local search filtering."""
        return self._nyx_catalog.search_catalog(query=query, limit=limit)

    def get_nyx_component_detail(self, component_name: str) -> NyxCatalogComponentDetail:
        """Return normalized detail for one allowlisted Nyx component."""
        return self._nyx_catalog.get_component_detail(component_name)

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
        result = self._assistant_service.reflect(
            **kwargs,
            _orchestrator=self,
        )
        self._capture_improvement_idea_from_reflection(result)
        return result

    def record_companion_reflection(
        self,
        *,
        summary: str,
        why: str = "",
        trigger: str = "while_you_work",
        kind: str = "while_you_work",
        confidence: float = 0.55,
        source_event: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist a Bonsai (Phase 4a) or backend (Phase 4b) reflection.

        Thin wrapper around
        :meth:`AssistantCompanionService.record_external_reflection`
        so HTTP routes do not have to know the assistant-service API
        directly. Settings resolution mirrors :meth:`reflect_assistant`.
        """
        resolved_settings = self._resolve_query_settings(settings or {})
        return self._assistant_service.record_external_reflection(
            summary=summary,
            why=why,
            trigger=trigger,
            kind=kind,
            confidence=confidence,
            source_event=source_event,
            tags=tags,
            settings=resolved_settings,
        )

    def recompute_growth_stage(
        self,
        *,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Phase 5: gather counters + recompute the growth stage.

        Idempotent: when the stage is unchanged, no events fire and
        nothing is persisted. On a transition, ``AssistantStatus.growth_stage``
        is bumped, ``growth_stage_changed_at`` is stamped, and a
        ``CompanionActivityEvent`` with ``source="seedling"``,
        ``state="completed"``, ``kind="stage_transition"`` is recorded
        on the activity bridge so the dock can fire its one-time pulse.

        Returns ``{stage, advanced_from, signals, transition_event?}``.
        """
        from datetime import datetime, timezone  # local for clarity

        from metis_app.seedling.activity import record_seedling_activity
        from metis_app.seedling.growth import (
            DEFAULT_THRESHOLDS,
            compute_growth_stage,
            signals_from_counts,
        )

        active_settings = self._resolve_query_settings(settings or {})
        counts = self._collect_growth_counts()
        signals = signals_from_counts(counts)

        identity = self._assistant_service.repository.get_status()
        current_stage = identity.growth_stage

        override_raw = str(
            active_settings.get("seedling_growth_stage_override") or ""
        ).strip().lower()
        override = override_raw if override_raw in {
            "seedling", "sapling", "bloom", "elder",
        } else None

        decision = compute_growth_stage(
            signals=signals,
            current_stage=current_stage,
            thresholds=DEFAULT_THRESHOLDS,
            override=override,  # type: ignore[arg-type]
        )

        result: dict[str, Any] = {
            "stage": decision.stage,
            "advanced_from": decision.advanced_from,
            "reason": decision.reason,
            "signals": {
                "indexed_stars": signals.indexed_stars,
                "indexed_faculties": signals.indexed_faculties,
                "reflections_total": signals.reflections_total,
                "overnight_reflections": signals.overnight_reflections,
                "skill_candidates": signals.skill_candidates,
                "promoted_skills": signals.promoted_skills,
                "brain_graph_density": signals.brain_graph_density,
            },
        }

        if decision.advanced_from is None and decision.stage == current_stage:
            return result

        now_iso = datetime.now(timezone.utc).isoformat()
        identity.growth_stage = decision.stage
        identity.growth_stage_changed_at = now_iso
        self._assistant_service.repository.update_status(identity)

        if decision.advanced_from is not None:
            try:
                record_seedling_activity(
                    {
                        "state": "completed",
                        "kind": "stage_transition",
                        "trigger": "growth_stage",
                        "summary": (
                            f"Companion advanced to {decision.stage.title()}"
                        ),
                        "status": {
                            "growth_stage": decision.stage,
                            "advanced_from": decision.advanced_from,
                        },
                    }
                )
                result["transition_event"] = {
                    "source": "seedling",
                    "kind": "stage_transition",
                    "advanced_from": decision.advanced_from,
                    "stage": decision.stage,
                }
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "Failed to emit stage_transition activity event: %s",
                    exc,
                    exc_info=True,
                )
        return result

    def _collect_growth_counts(self) -> dict[str, Any]:
        """Gather the structural counters used by ``recompute_growth_stage``.

        Failures here are non-fatal — each counter falls back to zero
        so the recompute always yields a deterministic stage even if
        one of the underlying repos is mid-init.
        """
        counts: dict[str, Any] = {}

        # Indexes / faculties (stars).
        try:
            indexes = self.list_indexes()
        except Exception:
            indexes = []
        counts["indexed_stars"] = len(indexes)
        faculties: set[str] = set()
        for ix in indexes:
            faculty = str(ix.get("faculty_id") or ix.get("faculty") or "").strip()
            if faculty:
                faculties.add(faculty)
        counts["indexed_faculties"] = len(faculties)

        # Reflections — any kind counts (Phase 4a Bonsai, Phase 4b
        # overnight, Phase 4 manual). The plan doc decision section
        # documents this — see ADR 0013 §Open Questions resolution.
        try:
            recent = self._assistant_service.repository.list_memory(limit=1000)
        except Exception:
            recent = []
        reflection_kinds = {
            "reflection",
            "bonsai_reflection",
            "overnight_reflection",
        }
        reflections_total = 0
        overnight_reflections = 0
        for entry in recent:
            kind = str(getattr(entry, "kind", "") or "")
            if kind in reflection_kinds:
                reflections_total += 1
            if kind == "overnight_reflection":
                overnight_reflections += 1
        counts["reflections_total"] = reflections_total
        counts["overnight_reflections"] = overnight_reflections

        # Skill candidates / promoted skills.
        try:
            skill_counts = self._skill_repo.count_candidates(
                db_path=_DEFAULT_CANDIDATES_DB_PATH,
            )
        except Exception:
            skill_counts = {"unpromoted": 0, "promoted": 0}
        counts["skill_candidates"] = int(skill_counts.get("unpromoted", 0))
        counts["promoted_skills"] = int(skill_counts.get("promoted", 0))

        # Phase 6 — brain-graph density. Pulls a dedicated, uncapped
        # density graph (NOT the UI ``get_workspace_graph`` snapshot,
        # which caps memory at 8 / playbooks at 6 for display reasons).
        # Long-running companions need their Elder advance gated on
        # accumulated history, not a recent window.
        counts["brain_graph_density"] = 0.0
        try:
            counts["brain_graph_density"] = float(
                self._compute_assistant_density()
            )
        except Exception:
            # Defensive: a half-initialised session repo or empty
            # workspace shouldn't crash the tick — Phase 5 already
            # treats missing counters as zero.
            counts["brain_graph_density"] = 0.0
        return counts

    def _compute_assistant_density(self) -> float:
        """Phase 6 P1 fix — assistant-scope density over full history.

        The UI ``get_workspace_graph`` builds its assistant subgraph
        from ``AssistantCompanionService.get_snapshot``, which caps
        ``memory`` at 8 entries and ``playbooks`` at 6 — sane for the
        Brain canvas but wrong for an Elder gate that needs to see
        accumulated learning. We pull *uncapped* memory / playbook /
        brain_link rows directly from the repository, hydrate a
        density-only ``BrainGraph``, and ask it for the ratio.

        ``indexes`` and ``sessions`` are still pulled (so cross-edges
        emitted by ``reflect()`` resolve their ``index:*`` / ``session:*``
        target nodes) but we tolerate failures — a half-initialised
        session repo just means the index / session targets are
        missing and the ``_add_assistant_subgraph`` existence guard
        drops those edges, which is the correct conservative answer.
        """
        repo = self._assistant_service.repository
        try:
            indexes = self.list_indexes()
        except Exception:
            indexes = []
        try:
            sessions = self._session_repo.list_sessions()
        except Exception:
            sessions = []
        assistant_payload = {
            "identity": {"companion_enabled": True},
            "memory": [item.to_payload() for item in repo.list_memory()],
            "playbooks": [item.to_payload() for item in repo.list_playbooks()],
            "brain_links": [
                item.to_payload() for item in repo.list_brain_links()
            ],
        }
        graph = BrainGraph().build_from_indexes_and_sessions(
            indexes,
            sessions,
            assistant_payload,
            skip_layout=True,
        )
        return float(graph.compute_assistant_density())

    def run_autonomous_research(
        self,
        settings: dict[str, Any],
        progress_cb: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any] | None:
        """Run one autonomous research cycle: find sparse faculty → web search → synthesize → index.

        Returns result dict with {faculty_id, index_id, title, sources} or None if skipped.
        Called from the companion reflection loop when autonomous_research_enabled is True.

        progress_cb is optional; receives phase dicts: {"phase", "faculty_id", "detail"}.
        """
        from metis_app.models.assistant_types import AssistantPolicy
        from metis_app.services.autonomous_research_service import AutonomousResearchService
        from metis_app.utils.web_search import create_web_search

        # Read policy from the incoming settings directly (not from resolved/disk settings)
        # _resolve_query_settings clobbers assistant_policy with on-disk values
        raw_policy = (settings or {}).get("assistant_policy") or {}
        policy = AssistantPolicy.from_payload(raw_policy)
        if not policy.autonomous_research_enabled:
            return None

        global _autonomous_running_count
        with _autonomous_running_lock:
            _autonomous_running_count += 1
        try:
            # Resolve LLM/embedding settings for the research service
            resolved = self._resolve_query_settings(settings)

            index_dicts = self.list_indexes()
            index_list = [
                {"index_id": idx.get("index_id", ""), "document_count": idx.get("document_count", 0)}
                for idx in index_dicts
            ]
            concurrency = max(1, int(raw_policy.get("autonomous_research_concurrency", 1) or 1))
            delay_ms = max(0, int(raw_policy.get("autonomous_research_request_delay_ms", 500) or 500))

            svc = AutonomousResearchService(web_search=create_web_search(resolved))

            if concurrency <= 1:
                # Original single-gap behaviour — backwards compatible
                result = svc.run(
                    settings=resolved,
                    indexes=index_list,
                    orchestrator=self,
                    progress_cb=progress_cb,
                )
                self._capture_improvement_sources_from_autonomous_result(result)
                return result

            # Collect all sparse faculty gaps
            import asyncio
            faculty_ids: list[str] = []
            temp_indexes = list(index_list)
            for _ in range(concurrency * 2):  # cap scan to avoid infinite loop
                fid = svc.scan_faculty_gaps(temp_indexes)
                if fid is None or fid in faculty_ids:
                    break
                faculty_ids.append(fid)
                # Temporarily mark as covered so scan finds the next gap
                temp_indexes = temp_indexes + [{"index_id": f"auto_{fid}_placeholder"}]

            if not faculty_ids:
                return None

            results = asyncio.run(
                svc.run_batch(
                    faculty_ids=faculty_ids,
                    settings=resolved,
                    orchestrator=self,
                    concurrency=concurrency,
                    request_delay_ms=delay_ms,
                    progress_cb=progress_cb,
                )
            )
            self._capture_improvement_sources_from_autonomous_result(results)
            return results[0] if results else None
        finally:
            with _autonomous_running_lock:
                _autonomous_running_count -= 1

    def list_improvement_entries(
        self,
        *,
        artifact_type: str = "",
        status: str = "",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return [
            entry.to_payload()
            for entry in self._improvement_repo.list_entries(
                artifact_type=artifact_type,
                status=status,
                limit=limit,
            )
        ]

    def get_improvement_entry(self, entry_id: str) -> dict[str, Any] | None:
        entry = self._improvement_repo.get_entry(entry_id)
        return entry.to_payload() if entry is not None else None

    def upsert_improvement_entry(self, payload: dict[str, Any]) -> dict[str, Any]:
        entry = ImprovementEntry.from_payload(payload)
        saved = self._improvement_repo.upsert_entry(entry)
        return saved.to_payload()

    def preview_learning_route(
        self,
        *,
        origin_star: LearningRouteStarSnapshot,
        connected_stars: list[LearningRouteStarSnapshot],
        indexes: list[LearningRouteIndexSummary],
    ) -> dict[str, Any]:
        resolved_settings = self._resolve_query_settings({})
        preview = plan_learning_route_preview(
            LearningRoutePreviewRequest(
                origin_star=origin_star,
                connected_stars=list(connected_stars),
                indexes=list(indexes),
            ),
            settings=resolved_settings,
        )
        return preview.to_dict()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_query_settings(self, incoming: dict[str, Any], *, query: str = "") -> dict[str, Any]:
        base = _settings_store.load_settings()
        merged = dict(base)
        merged.update(dict(incoming or {}))
        merged["assistant_identity"] = base.get("assistant_identity", {})
        merged["assistant_runtime"] = base.get("assistant_runtime", {})
        merged["assistant_policy"] = base.get("assistant_policy", {})
        if str(query or "").strip():
            try:
                merged = augment_settings_with_nyx(
                    merged,
                    query=query,
                    broker=self._nyx_catalog,
                )
            except RuntimeError:
                pass
        return merged

    def _resolve_nyx_install_actions(
        self,
        run_id: str,
        settings: dict[str, Any],
        artifacts: Any = None,
    ) -> list[dict[str, Any]]:
        try:
            return build_nyx_install_actions(
                run_id=run_id,
                settings=settings,
                broker=self._nyx_catalog,
                artifacts=artifacts,
            )
        except (RuntimeError, ValueError):
            return []

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
        if "artifacts" in payload:
            payload_artifacts = extract_arrow_artifacts(
                {
                    "enable_arrow_artifacts": True,
                    "artifacts": payload.get("artifacts"),
                },
                metadata_only=True,
            )
            if payload_artifacts:
                payload["artifacts"] = payload_artifacts
            else:
                payload.pop("artifacts", None)
        stage_map = {
            "run_started": "retrieval",
            "retrieval_complete": "retrieval",
            "retrieval_augmented": "retrieval",
            "knowledge_search_complete": "retrieval",
            "subqueries": "retrieval",
            "iteration_start": "reflection",
            "gaps_identified": "reflection",
            "refinement_retrieval": "retrieval",
            "iteration_converged": "reflection",
            "iteration_complete": "reflection",
            "fallback_decision": "fallback",
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

    def _maybe_create_atlas_candidate(
        self,
        *,
        session_id: str,
        question: str,
        run_id: str,
        answer_text: str,
        sources: list[dict[str, Any]] | list[EvidenceSource],
        selected_mode: str,
        top_score: float,
        fallback: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        normalized_run_id = str(run_id or "").strip()
        normalized_session_id = str(session_id or "").strip()
        normalized_answer = str(answer_text or "").strip()
        normalized_mode = str(selected_mode or "").strip() or "Q&A"
        fallback_payload = dict(fallback or {})

        if not normalized_run_id or not normalized_session_id or not normalized_answer:
            return None
        if normalized_mode in {"Knowledge Search", "Forecast", "Simulation"}:
            return None
        if bool(fallback_payload.get("triggered")):
            return None

        normalized_sources: list[dict[str, Any]] = []
        for item in sources:
            if isinstance(item, EvidenceSource):
                normalized_sources.append(item.to_dict())
            elif isinstance(item, dict):
                normalized_sources.append(dict(item))

        source_count = len(normalized_sources)
        if source_count < 2 or len(normalized_answer) < 120:
            return None

        try:
            normalized_top_score = float(top_score or 0.0)
        except (TypeError, ValueError):
            normalized_top_score = 0.0

        confidence = self._atlas_candidate_confidence(
            answer_text=normalized_answer,
            source_count=source_count,
            top_score=normalized_top_score,
            selected_mode=normalized_mode,
        )
        if confidence < 0.62:
            return None

        title = self._atlas_title_from_question(question)
        summary = self._atlas_summary(normalized_answer)
        session_detail = self.get_session(normalized_session_id)
        index_id = session_detail.summary.index_id if session_detail is not None else ""
        rationale = (
            f"{source_count} grounded sources, top score {normalized_top_score:.2f}, "
            f"mode {normalized_mode}."
        )
        entry = AtlasEntry.create_candidate(
            session_id=normalized_session_id,
            run_id=normalized_run_id,
            title=title,
            summary=summary,
            body_md=normalized_answer,
            sources=normalized_sources,
            mode=normalized_mode,
            index_id=index_id,
            top_score=normalized_top_score,
            source_count=source_count,
            confidence=confidence,
            rationale=rationale,
        )
        stored = self._atlas_repo.upsert_candidate(entry)
        return stored.to_payload()

    @staticmethod
    def _atlas_title_from_question(question: str) -> str:
        raw = str(question or "").strip()
        if raw.startswith("[AGENT ACTION:"):
            parts = raw.split("\n\n", 1)
            raw = parts[-1].strip() if parts else raw
        raw = raw or "Untitled Atlas Entry"
        if len(raw) <= 120:
            return raw
        return raw[:117].rstrip() + "..."

    @staticmethod
    def _atlas_summary(answer_text: str) -> str:
        lines = [line.strip() for line in str(answer_text or "").splitlines() if line.strip()]
        if not lines:
            return ""
        first_line = lines[0]
        summary = re.split(r"(?<=[.!?])\s+", first_line, maxsplit=1)[0]
        summary = summary.strip()
        if len(summary) <= 160:
            return summary
        return summary[:157].rstrip() + "..."

    def _capture_improvement_sources_from_autonomous_result(
        self,
        result: dict[str, Any] | list[dict[str, Any]] | None,
    ) -> None:
        rows = result if isinstance(result, list) else ([result] if isinstance(result, dict) else [])
        for item in rows:
            faculty_id = str(item.get("faculty_id") or "").strip()
            index_id = str(item.get("index_id") or "").strip()
            title = str(item.get("title") or "").strip()
            if not title:
                continue
            sources = [
                str(source).strip()
                for source in (item.get("sources") or [])
                if str(source).strip()
            ]
            artifact = ImprovementEntry.create(
                artifact_key=f"source:autonomous_research:{index_id or title.lower()}",
                artifact_type="source",
                title=title,
                summary=(
                    f"Autonomous research filled the '{faculty_id or 'unknown'}' faculty gap "
                    f"and created index '{index_id or 'unknown'}'."
                ),
                body_md=(
                    f"METIS autonomous research generated a new research star titled '{title}'.\n\n"
                    f"Faculty: {faculty_id or 'unknown'}\n"
                    f"Index: {index_id or 'unknown'}\n"
                    f"Sources: {', '.join(sources) if sources else 'none'}"
                ),
                status="active",
                tags=["autonomous_research", *([faculty_id] if faculty_id else [])],
                metadata={
                    "origin": "autonomous_research",
                    "faculty_id": faculty_id,
                    "index_id": index_id,
                    "sources": sources,
                },
            )
            self._improvement_repo.upsert_entry(artifact)

    def _capture_improvement_idea_from_reflection(self, result: dict[str, Any] | None) -> None:
        if not isinstance(result, dict) or not result.get("ok"):
            return
        memory_entry = result.get("memory_entry")
        if not isinstance(memory_entry, dict):
            return
        trigger = str(memory_entry.get("trigger") or "").strip()
        session_id = str(memory_entry.get("session_id") or "").strip()
        run_id = str(memory_entry.get("run_id") or "").strip()
        title = str(memory_entry.get("title") or "").strip()
        summary = str(memory_entry.get("summary") or "").strip()
        details = str(memory_entry.get("details") or "").strip()
        entry_id = str(memory_entry.get("entry_id") or "").strip()
        if not title:
            return
        artifact = ImprovementEntry.create(
            artifact_key=f"idea:reflection:{trigger}:{session_id}:{run_id}:{entry_id}",
            artifact_type="idea",
            title=title,
            summary=summary,
            body_md=details,
            session_id=session_id,
            run_id=run_id,
            status="draft",
            tags=["assistant_reflection", *([trigger] if trigger else [])],
            metadata={
                "origin": "assistant_reflection",
                "why": str(memory_entry.get("why") or "").strip(),
                "confidence": memory_entry.get("confidence"),
                "related_node_ids": list(memory_entry.get("related_node_ids") or []),
            },
        )
        self._improvement_repo.upsert_entry(artifact)

    @staticmethod
    def _atlas_candidate_confidence(
        *,
        answer_text: str,
        source_count: int,
        top_score: float,
        selected_mode: str,
    ) -> float:
        confidence = 0.18
        confidence += min(max(source_count, 0), 5) * 0.08
        confidence += max(0.0, min(top_score, 1.0)) * 0.34
        if len(answer_text) >= 420:
            confidence += 0.08
        if len(answer_text) >= 900:
            confidence += 0.05
        if selected_mode in {"Research", "Evidence Pack", "Summary"}:
            confidence += 0.14
        elif selected_mode in {"Q&A", "Tutor"}:
            confidence += 0.08
        return max(0.0, min(confidence, 0.95))

    def enabled_skills(self, settings: dict[str, Any]) -> list[SkillDefinition]:
        """Return skills that are enabled for the given *settings* snapshot."""
        return self._skill_repo.enabled_skills(settings)

    def ingest_ui_telemetry_events(self, events: list[dict[str, Any]]) -> int:
        """Persist validated frontend UI telemetry through the existing trace path."""
        accepted = 0
        for event in events:
            event_name = str(event.get("event_name") or "").strip()
            run_id = str(event.get("run_id") or "").strip()
            if not event_name or not run_id:
                continue

            payload = event.get("payload")
            self._trace_store.append_event(
                run_id=run_id,
                stage="ui_artifact",
                event_type=event_name,
                payload={
                    "source": str(event.get("source") or "chat_artifact_boundary"),
                    "session_id": str(event.get("session_id") or ""),
                    "message_id": str(event.get("message_id") or ""),
                    "client_timestamp": str(event.get("occurred_at") or ""),
                    "is_streaming": bool(event.get("is_streaming", False)),
                    "telemetry": dict(payload) if isinstance(payload, dict) else {},
                },
            )
            accepted += 1

        return accepted

    def get_ui_telemetry_summary(
        self,
        *,
        window_hours: int = 24,
        limit: int = 50_000,
    ) -> dict[str, Any]:
        """Return aggregated UI artifact telemetry and threshold evaluation."""
        try:
            normalized_window = int(window_hours)
        except (TypeError, ValueError):
            normalized_window = 24
        if normalized_window <= 0:
            normalized_window = 24
        try:
            normalized_limit = int(limit)
        except (TypeError, ValueError):
            normalized_limit = 50_000
        if normalized_limit <= 0:
            normalized_limit = 50_000
        return self._trace_store.aggregate_ui_artifact_summary(
            window_hours=normalized_window,
            limit=normalized_limit,
        )

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
    db_path = os.getenv("METIS_SESSION_DB_PATH") or None
    repo = SessionRepository(db_path=db_path)
    repo.init_db()
    return repo
