"""Assistant companion routes."""

from __future__ import annotations

from fastapi import APIRouter

from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator

from .models import (
    AssistantBootstrapRequestModel,
    AssistantMemoryEntryModel,
    AssistantReflectRequestModel,
    AssistantSnapshotModel,
    AssistantStatusModel,
    AssistantUpdateRequestModel,
)

router = APIRouter(prefix="/v1/assistant", tags=["assistant"])


@router.get("", response_model=AssistantSnapshotModel)
def get_assistant() -> dict:
    return WorkspaceOrchestrator().get_assistant_snapshot()


@router.post("", response_model=AssistantSnapshotModel)
def update_assistant(payload: AssistantUpdateRequestModel) -> dict:
    return WorkspaceOrchestrator().update_assistant(
        identity=payload.identity,
        runtime=payload.runtime,
        policy=payload.policy,
        status=payload.status,
    )


@router.get("/status", response_model=AssistantStatusModel)
def get_assistant_status() -> dict:
    snapshot = WorkspaceOrchestrator().get_assistant_snapshot()
    return dict(snapshot.get("status") or {})


@router.post("/reflect")
def reflect_assistant(payload: AssistantReflectRequestModel) -> dict:
    kwargs = {
        "trigger": payload.trigger,
        "session_id": payload.session_id,
        "run_id": payload.run_id,
        "force": payload.force,
    }
    if payload.context_id:
        kwargs["context_id"] = payload.context_id
    return WorkspaceOrchestrator().reflect_assistant(**kwargs)


@router.post("/bootstrap", response_model=AssistantSnapshotModel)
def bootstrap_assistant(payload: AssistantBootstrapRequestModel) -> dict:
    return WorkspaceOrchestrator().bootstrap_assistant(
        install_local_model=payload.install_local_model
    )


@router.get("/memory", response_model=list[AssistantMemoryEntryModel])
def list_assistant_memory(limit: int = 20) -> list[dict]:
    return WorkspaceOrchestrator().list_assistant_memory(limit=limit)


@router.delete("/memory")
def clear_assistant_memory(limit: int = 10) -> dict:
    return WorkspaceOrchestrator().clear_assistant_memory(limit=limit)
