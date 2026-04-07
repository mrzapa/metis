"""Improvement-pipeline routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator

from .models import ImprovementEntryModel

router = APIRouter(prefix="/v1/improvements", tags=["improvements"])


@router.get("", response_model=list[ImprovementEntryModel])
def list_improvement_entries(
    artifact_type: str = "",
    status: str = "",
    limit: int = 20,
) -> list[dict]:
    return WorkspaceOrchestrator().list_improvement_entries(
        artifact_type=artifact_type,
        status=status,
        limit=limit,
    )


@router.get("/{entry_id}", response_model=ImprovementEntryModel)
def get_improvement_entry(entry_id: str) -> dict:
    entry = WorkspaceOrchestrator().get_improvement_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Improvement entry not found")
    return entry
