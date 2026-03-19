"""Session and feedback routes for the Axiom v1 API."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from axiom_app.services.session_repository import SessionRepository

from .models import (
    CreateSessionRequestModel,
    FeedbackRequestModel,
    FeedbackResponseModel,
    SessionDetailModel,
    SessionSummaryModel,
)

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])


def get_session_repo() -> SessionRepository:
    """FastAPI dependency — returns a SessionRepository for the configured DB path.

    Override via env AXIOM_SESSION_DB_PATH; otherwise uses the default repo-root
    rag_sessions.db (matching the desktop app's convention).
    """
    db_path = os.getenv("AXIOM_SESSION_DB_PATH") or None
    repo = SessionRepository(db_path=db_path)
    repo.init_db()
    return repo


_RepoDep = Annotated[SessionRepository, Depends(get_session_repo)]


@router.get("", response_model=list[SessionSummaryModel])
def list_sessions(
    search: str = "",
    skill: str = "",
    repo: _RepoDep = ...,
) -> list[SessionSummaryModel]:
    """List session summaries with optional full-text search and skill filter."""
    summaries = repo.list_sessions(search=search, skill=skill)
    return [SessionSummaryModel.from_dataclass(s) for s in summaries]


@router.post("", response_model=SessionSummaryModel, status_code=201)
def create_session(
    payload: CreateSessionRequestModel,
    repo: _RepoDep = ...,
) -> SessionSummaryModel:
    """Create a new session with the given title."""
    summary = repo.create_session(title=payload.title or "New Chat")
    return SessionSummaryModel.from_dataclass(summary)


@router.get("/{session_id}", response_model=SessionDetailModel)
def get_session(session_id: str, repo: _RepoDep = ...) -> SessionDetailModel:
    """Return full session detail: messages, metadata, feedback, and traces if available."""
    detail = repo.get_session(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionDetailModel.from_dataclass(detail)


@router.post("/{session_id}/feedback", response_model=FeedbackResponseModel)
def submit_feedback(
    session_id: str,
    payload: FeedbackRequestModel,
    repo: _RepoDep = ...,
) -> FeedbackResponseModel:
    """Submit thumbs-up/down feedback for a specific run within a session."""
    repo.save_feedback(
        session_id,
        run_id=payload.run_id,
        vote=payload.vote,
        note=payload.note,
    )
    return FeedbackResponseModel(ok=True)
