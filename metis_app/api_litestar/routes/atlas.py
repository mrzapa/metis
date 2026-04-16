"""Atlas candidate and saved-entry routes."""

from __future__ import annotations

from litestar import Router, get, post
from litestar.exceptions import HTTPException as LitestarHTTPException

from metis_app.api_litestar.models import (
    AtlasDecisionRequestModel,
    AtlasEntryModel,
    AtlasSaveRequestModel,
)
from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator


@get("/v1/atlas/candidate")
def get_atlas_candidate(session_id: str, run_id: str) -> dict:
    candidate = WorkspaceOrchestrator().get_atlas_candidate(
        session_id=session_id,
        run_id=run_id,
    )
    if candidate is None:
        raise LitestarHTTPException(status_code=404, detail="Atlas candidate not found")
    return AtlasEntryModel.model_validate(candidate).model_dump(mode="json")


@post("/v1/atlas/save", status_code=200)
def save_atlas_entry(data: AtlasSaveRequestModel) -> dict:
    try:
        entry = WorkspaceOrchestrator().save_atlas_entry(
            session_id=data.session_id,
            run_id=data.run_id,
            title=data.title,
            summary=data.summary,
        )
    except FileNotFoundError as exc:
        raise LitestarHTTPException(status_code=404, detail=str(exc)) from exc
    return AtlasEntryModel.model_validate(entry).model_dump(mode="json")


@post("/v1/atlas/decision", status_code=200)
def decide_atlas_candidate(data: AtlasDecisionRequestModel) -> dict:
    try:
        entry = WorkspaceOrchestrator().decide_atlas_candidate(
            session_id=data.session_id,
            run_id=data.run_id,
            decision=data.decision,
        )
    except ValueError as exc:
        raise LitestarHTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise LitestarHTTPException(status_code=404, detail=str(exc)) from exc
    return AtlasEntryModel.model_validate(entry).model_dump(mode="json")


@get("/v1/atlas/entries")
def list_atlas_entries(limit: int = 20) -> list[dict]:
    entries = WorkspaceOrchestrator().list_atlas_entries(limit=limit)
    return [
        AtlasEntryModel.model_validate(entry).model_dump(mode="json")
        for entry in entries
    ]


@get("/v1/atlas/entries/{entry_id:str}")
def get_atlas_entry(entry_id: str) -> dict:
    entry = WorkspaceOrchestrator().get_atlas_entry(entry_id)
    if entry is None:
        raise LitestarHTTPException(status_code=404, detail="Atlas entry not found")
    return AtlasEntryModel.model_validate(entry).model_dump(mode="json")


router = Router(
    path="",
    route_handlers=[
        get_atlas_candidate,
        save_atlas_entry,
        decide_atlas_candidate,
        list_atlas_entries,
        get_atlas_entry,
    ],
    tags=["atlas"],
)
