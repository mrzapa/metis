"""Improvement-pipeline endpoints."""

from __future__ import annotations

import uuid as _uuid

from litestar import Router, get, post
from litestar.exceptions import HTTPException as LitestarHTTPException

from metis_app.api_litestar.models import ImprovementCreateRequest, ImprovementEntryModel
from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator


@get("/v1/improvements")
def list_improvement_entries(
    artifact_type: str = "",
    status: str = "",
    limit: int = 20,
) -> list[dict]:
    entries = WorkspaceOrchestrator().list_improvement_entries(
        artifact_type=artifact_type,
        status=status,
        limit=limit,
    )
    return [
        ImprovementEntryModel.model_validate(entry).model_dump(mode="json")
        for entry in entries
    ]


@get("/v1/improvements/{entry_id:str}")
def get_improvement_entry(entry_id: str) -> dict:
    entry = WorkspaceOrchestrator().get_improvement_entry(entry_id)
    if entry is None:
        raise LitestarHTTPException(status_code=404, detail="Improvement entry not found")
    return ImprovementEntryModel.model_validate(entry).model_dump(mode="json")


@post("/v1/improvements", status_code=201)
def create_improvement_entry(data: ImprovementCreateRequest) -> dict:
    payload = data.model_dump()
    if not payload.get("artifact_key"):
        slug_base = str(payload.get("title") or "entry").lower().replace(" ", "-")[:48]
        payload["artifact_key"] = (
            f"{payload['artifact_type']}:manual:{slug_base}:{_uuid.uuid4().hex[:8]}"
        )
    entry = WorkspaceOrchestrator().upsert_improvement_entry(payload)
    return ImprovementEntryModel.model_validate(entry).model_dump(mode="json")


router = Router(
    path="",
    route_handlers=[
        list_improvement_entries,
        get_improvement_entry,
        create_improvement_entry,
    ],
    tags=["improvements"],
)
