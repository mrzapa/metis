"""Session and feedback endpoints."""

from __future__ import annotations

from litestar import Router, delete, get, post
from litestar.di import Provide
from litestar.exceptions import HTTPException as LitestarHTTPException

from metis_app.api_litestar.common import get_session_repo
from metis_app.api_litestar.models import (
    CreateSessionRequestModel,
    FeedbackRequestModel,
    FeedbackResponseModel,
    SessionDetailModel,
    SessionSummaryModel,
)
from metis_app.services.session_actions import hydrate_session_actions
from metis_app.services.session_repository import SessionRepository
from metis_app.services.trace_store import TraceStore


def _make_trace_store() -> TraceStore:
    return TraceStore()


@get("/v1/sessions")
def list_sessions(
    session_repo: SessionRepository,
    search: str = "",
    skill: str = "",
) -> list[dict[str, object]]:
    """List session summaries with optional search and skill filtering."""
    summaries = session_repo.list_sessions(search=search, skill=skill)
    return [SessionSummaryModel.from_dataclass(item).model_dump() for item in summaries]


@post("/v1/sessions", status_code=201)
def create_session(
    session_repo: SessionRepository,
    data: CreateSessionRequestModel,
) -> dict[str, object]:
    """Create a new session."""
    summary = session_repo.create_session(title=data.title or "New Chat")
    return SessionSummaryModel.from_dataclass(summary).model_dump()


@get("/v1/sessions/{session_id:str}")
def get_session(
    session_repo: SessionRepository,
    trace_store: TraceStore,
    session_id: str,
) -> dict[str, object]:
    """Return session detail, including hydrated action results."""
    detail = session_repo.get_session(session_id)
    if detail is None:
        raise LitestarHTTPException(status_code=404, detail="Session not found")
    detail = hydrate_session_actions(detail, trace_store=trace_store)
    return SessionDetailModel.from_dataclass(detail).model_dump()


@post("/v1/sessions/{session_id:str}/feedback", status_code=200)
def submit_feedback(
    session_repo: SessionRepository,
    session_id: str,
    data: FeedbackRequestModel,
) -> dict[str, bool]:
    """Persist feedback for a run in a session."""
    session_repo.save_feedback(
        session_id,
        run_id=data.run_id,
        vote=data.vote,
        note=data.note,
    )
    return FeedbackResponseModel(ok=True).model_dump()


@delete("/v1/sessions/{session_id:str}", status_code=200)
def delete_session(session_repo: SessionRepository, session_id: str) -> dict[str, object]:
    """Delete a session and all associated messages and feedback."""
    detail = session_repo.get_session(session_id)
    if detail is None:
        raise LitestarHTTPException(status_code=404, detail="Session not found")
    session_repo.delete_session(session_id)
    return {"ok": True, "session_id": session_id}


router = Router(
    path="",
    dependencies={
        # Both providers do blocking I/O on every request:
        # `get_session_repo()` opens the SQLite connection and runs
        # schema migrations; `_make_trace_store()` creates the runs
        # directory. Run them on the threadpool, not the event loop.
        "session_repo": Provide(get_session_repo, sync_to_thread=True),
        "trace_store": Provide(_make_trace_store, sync_to_thread=True),
    },
    route_handlers=[
        list_sessions,
        create_session,
        get_session,
        submit_feedback,
        delete_session,
    ],
    tags=["sessions"],
)
