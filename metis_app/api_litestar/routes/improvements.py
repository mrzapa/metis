"""Improvement-pipeline endpoints."""

from __future__ import annotations

from litestar import Router, get
from litestar.exceptions import HTTPException as LitestarHTTPException

from metis_app.api.models import ImprovementEntryModel
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


router = Router(
    path="",
    route_handlers=[
        list_improvement_entries,
        get_improvement_entry,
    ],
    tags=["improvements"],
)
