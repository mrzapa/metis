"""FastAPI routes for agent-native app-state KV store (Surface 1 & Surface 2 poll)."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from metis_app.services.app_state_service import AppStateService

router = APIRouter(prefix="/v1", tags=["app-state"])


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AppStateEntry(BaseModel):
    session_id: str
    key: str
    value: str
    version: int
    updated_at: str


class AppStateSetRequest(BaseModel):
    value: str


class AppStateSetResponse(BaseModel):
    version: int


class PollResponse(BaseModel):
    version: int
    changed: bool


# ---------------------------------------------------------------------------
# Dependency — module-level singleton
# ---------------------------------------------------------------------------

_service: AppStateService | None = None


def get_app_state_service() -> AppStateService:
    """Return shared AppStateService instance (created on first call).

    Override the database path via the METIS_APP_STATE_DB_PATH environment
    variable; falls back to the service's built-in default (repo-root
    app_state.db).
    """
    global _service  # noqa: PLW0603
    if _service is None:
        db_path = os.getenv("METIS_APP_STATE_DB_PATH") or None
        _service = AppStateService(db_path=db_path)
    return _service


_SvcDep = Annotated[AppStateService, Depends(get_app_state_service)]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/app-state/{session_id}", response_model=list[AppStateEntry])
def list_app_state(session_id: str, svc: _SvcDep) -> list[AppStateEntry]:
    """Return all KV entries for a session."""
    entries = svc.list(session_id)
    return [AppStateEntry(session_id=session_id, **entry) for entry in entries]


@router.get("/app-state/{session_id}/{key}", response_model=AppStateEntry)
def read_app_state(session_id: str, key: str, svc: _SvcDep) -> AppStateEntry:
    """Return a single KV entry for (session_id, key), or 404 if absent."""
    entry = svc.read_entry(session_id, key)
    if entry is None:
        raise HTTPException(status_code=404, detail="Key not found")
    return AppStateEntry(session_id=session_id, **entry)


@router.post(
    "/app-state/{session_id}/{key}",
    response_model=AppStateSetResponse,
    status_code=200,
)
def write_app_state(
    session_id: str,
    key: str,
    body: AppStateSetRequest,
    svc: _SvcDep,
) -> AppStateSetResponse:
    """Upsert a KV entry and return the new global version."""
    new_version = svc.write(session_id, key, body.value)
    return AppStateSetResponse(version=new_version)


@router.delete("/app-state/{session_id}/{key}")
def delete_app_state(
    session_id: str,
    key: str,
    svc: _SvcDep,
) -> dict[str, bool]:
    """Delete a KV entry. Returns {ok: true} regardless of prior existence."""
    svc.delete(session_id, key)
    return {"ok": True}


@router.get("/poll", response_model=PollResponse)
def poll(
    since: int = Query(..., description="Version counter value known to the caller"),
    svc: AppStateService = Depends(get_app_state_service),
) -> PollResponse:
    """Return current version and whether it has advanced beyond *since*."""
    current = svc.get_version()
    return PollResponse(version=current, changed=current > since)
