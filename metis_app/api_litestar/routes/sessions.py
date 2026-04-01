"""Session and feedback endpoints."""

from __future__ import annotations

from litestar import Router, delete, get, post
from litestar.exceptions import HTTPException as LitestarHTTPException

from metis_app.api.models import (
    CreateSessionRequestModel,
    FeedbackRequestModel,
    FeedbackResponseModel,
    SessionDetailModel,
    SessionSummaryModel,
)
from metis_app.api.sessions import _hydrate_session_actions
from metis_app.api_litestar.common import get_session_repo


@get("/v1/sessions")
async def list_sessions(search: str = "", skill: str = "") -> list[dict[str, object]]:
    """List session summaries with optional search and skill filtering."""
    repo = get_session_repo()
    summaries = repo.list_sessions(search=search, skill=skill)
    return [SessionSummaryModel.from_dataclass(item).model_dump() for item in summaries]


@post("/v1/sessions", status_code=201)
async def create_session(payload: CreateSessionRequestModel) -> dict[str, object]:
    """Create a new session."""
    repo = get_session_repo()
    summary = repo.create_session(title=payload.title or "New Chat")
    return SessionSummaryModel.from_dataclass(summary).model_dump()


@get("/v1/sessions/{session_id:str}")
async def get_session(session_id: str) -> dict[str, object]:
    """Return session detail, including hydrated action results."""
    repo = get_session_repo()
    detail = repo.get_session(session_id)
    if detail is None:
        raise LitestarHTTPException(status_code=404, detail="Session not found")
    detail = _hydrate_session_actions(detail)
    return SessionDetailModel.from_dataclass(detail).model_dump()


@post("/v1/sessions/{session_id:str}/feedback")
async def submit_feedback(session_id: str, payload: FeedbackRequestModel) -> dict[str, bool]:
    """Persist feedback for a run in a session."""
    repo = get_session_repo()
    repo.save_feedback(
        session_id,
        run_id=payload.run_id,
        vote=payload.vote,
        note=payload.note,
    )
    return FeedbackResponseModel(ok=True).model_dump()


@delete("/v1/sessions/{session_id:str}", status_code=200)
async def delete_session(session_id: str) -> dict[str, object]:
    """Delete a session and all associated messages and feedback."""
    repo = get_session_repo()
    detail = repo.get_session(session_id)
    if detail is None:
        raise LitestarHTTPException(status_code=404, detail="Session not found")
    repo.delete_session(session_id)
    return {"ok": True, "session_id": session_id}


router = Router(
    path="",
    route_handlers=[
        list_sessions,
        create_session,
        get_session,
        submit_feedback,
        delete_session,
    ],
    tags=["sessions"],
)