"""Litestar routes for agent-native app-state KV store (Surface 1 & Surface 2 poll)."""

from __future__ import annotations

import os

from litestar import Router, delete, get, post
from litestar.exceptions import HTTPException as LitestarHTTPException
from litestar.params import Parameter
from pydantic import BaseModel

from metis_app.services.app_state_service import AppStateService

# ---------------------------------------------------------------------------
# Pydantic models (mirrored from FastAPI variant)
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
# Service singleton
# ---------------------------------------------------------------------------

_service: AppStateService | None = None


def _get_service() -> AppStateService:
    global _service  # noqa: PLW0603
    if _service is None:
        db_path = os.getenv("METIS_APP_STATE_DB_PATH") or None
        _service = AppStateService(db_path=db_path)
    return _service


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@get("/v1/app-state/{session_id:str}")
def list_app_state(session_id: str) -> list[dict]:
    """Return all KV entries for a session."""
    svc = _get_service()
    entries = svc.list(session_id)
    return [
        AppStateEntry(session_id=session_id, **entry).model_dump()
        for entry in entries
    ]


@get("/v1/app-state/{session_id:str}/{key:str}")
def read_app_state(session_id: str, key: str) -> dict:
    """Return a single KV entry, or 404 if absent."""
    svc = _get_service()
    entry = svc.read_entry(session_id, key)
    if entry is None:
        raise LitestarHTTPException(status_code=404, detail="Key not found")
    return AppStateEntry(session_id=session_id, **entry).model_dump()


@post("/v1/app-state/{session_id:str}/{key:str}", status_code=200)
def write_app_state(session_id: str, key: str, data: AppStateSetRequest) -> dict:
    """Upsert a KV entry and return the new global version."""
    svc = _get_service()
    new_version = svc.write(session_id, key, data.value)
    return AppStateSetResponse(version=new_version).model_dump()


@delete("/v1/app-state/{session_id:str}/{key:str}", status_code=200)
def delete_app_state(session_id: str, key: str) -> dict:
    """Delete a KV entry. Returns {ok: true} regardless of prior existence."""
    svc = _get_service()
    svc.delete(session_id, key)
    return {"ok": True}


@get("/v1/poll")
def poll(since: int) -> dict:
    """Return current version and whether it has advanced beyond *since*."""
    svc = _get_service()
    current = svc.get_version()
    return PollResponse(version=current, changed=current > since).model_dump()


router = Router(
    path="",
    route_handlers=[
        list_app_state,
        read_app_state,
        write_app_state,
        delete_app_state,
        poll,
    ],
    tags=["app-state"],
)
