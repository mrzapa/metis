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
    SessionDetail,
    SessionSummary,
)
from axiom_app.services.session_repository import SessionRepository
from axiom_app.services.skill_repository import SkillRepository
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
    ) -> None:
        self._session_repo: SessionRepository = session_repo or _make_session_repo()
        self._skill_repo: SkillRepository = skill_repo or SkillRepository()
        self._index_dir: pathlib.Path | str | None = index_dir

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
        """Build a new index from *document_paths* using the engine pipeline.

        Delegates to :func:`axiom_app.engine.build_index` without duplicating
        any ingestion logic.
        """
        req = IndexBuildRequest(
            document_paths=document_paths,
            settings=settings,
            index_id=index_id,
        )
        return build_index(req, progress_cb=progress_cb)

    def list_indexes(self) -> list[dict[str, Any]]:
        """Return metadata for all persisted indexes."""
        return list_indexes(self._index_dir)

    def get_index(self, index_id: str) -> dict[str, Any] | None:
        """Return metadata for a single index, or ``None`` if not found."""
        return get_index(index_id, self._index_dir)

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def run_rag_query(self, req: RagQueryRequest) -> RagQueryResult:
        """Execute a batch RAG query via the engine."""
        return query_rag(req)

    def run_direct_query(self, req: DirectQueryRequest) -> DirectQueryResult:
        """Execute a direct (no-retrieval) LLM query via the engine."""
        return query_direct(req)

    def stream_rag_query(
        self,
        req: RagQueryRequest,
        cancel_token: Any = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield SSE-ready event dicts for a streaming RAG query.

        Delegates to :func:`axiom_app.engine.stream_rag_answer`.
        """
        return stream_rag_answer(req, cancel_token=cancel_token)

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
        return BrainGraph().build_from_indexes_and_sessions(indexes, sessions)

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
