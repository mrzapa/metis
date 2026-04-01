"""Assistant companion endpoints."""

from __future__ import annotations

from litestar import Router, delete, get, post

from metis_app.api.models import (
    AssistantBootstrapRequestModel,
    AssistantReflectRequestModel,
    AssistantUpdateRequestModel,
)
from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator


@get("/v1/assistant")
def get_assistant() -> dict:
    return WorkspaceOrchestrator().get_assistant_snapshot()


@post("/v1/assistant")
def update_assistant(payload: AssistantUpdateRequestModel) -> dict:
    return WorkspaceOrchestrator().update_assistant(
        identity=payload.identity,
        runtime=payload.runtime,
        policy=payload.policy,
        status=payload.status,
    )


@get("/v1/assistant/status")
def get_assistant_status() -> dict:
    snapshot = WorkspaceOrchestrator().get_assistant_snapshot()
    return dict(snapshot.get("status") or {})


@post("/v1/assistant/reflect")
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


@post("/v1/assistant/bootstrap")
def bootstrap_assistant(payload: AssistantBootstrapRequestModel) -> dict:
    return WorkspaceOrchestrator().bootstrap_assistant(
        install_local_model=payload.install_local_model,
    )


@get("/v1/assistant/memory")
def list_assistant_memory(limit: int = 20) -> list[dict]:
    return WorkspaceOrchestrator().list_assistant_memory(limit=limit)


@delete("/v1/assistant/memory", status_code=200)
def clear_assistant_memory(limit: int = 10) -> dict:
    return WorkspaceOrchestrator().clear_assistant_memory(limit=limit)


router = Router(
    path="",
    route_handlers=[
        get_assistant,
        update_assistant,
        get_assistant_status,
        reflect_assistant,
        bootstrap_assistant,
        list_assistant_memory,
        clear_assistant_memory,
    ],
    tags=["assistant"],
)