"""Assistant companion routes."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

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


# ---------------------------------------------------------------------------
# Star nourishment events — the punishment/reward loop
# ---------------------------------------------------------------------------

class StarEventBody(BaseModel):
    event_type: str       # "star_added" | "star_removed" | "star_evolved"
    star_id: str = ""
    faculty_id: str = ""
    detail: str = ""


@router.post("/nourishment/event")
def report_star_event(payload: StarEventBody) -> dict:
    """Report a star event to the companion.

    This triggers the nourishment state update and, for star_removed events,
    the punishment feedback loop that makes the companion aware of loss.
    """
    from metis_app.models.star_nourishment import (  # noqa: PLC0415
        NourishmentState,
        StarEvent,
        assistant_now_iso,
        compute_nourishment,
    )
    from metis_app.services.star_nourishment_gen import (  # noqa: PLC0415
        generate_star_event_reaction,
    )
    import metis_app.settings_store as _store  # noqa: PLC0415

    event = StarEvent(
        event_type=payload.event_type,
        star_id=payload.star_id,
        faculty_id=payload.faculty_id,
        timestamp=assistant_now_iso(),
        detail=payload.detail,
    )

    orch = WorkspaceOrchestrator()
    settings = _store.load_settings()
    stars = list(settings.get("landing_constellation_user_stars") or [])
    faculties = list(
        settings.get("constellation_faculties")
        or [
            {"id": "mathematics", "name": "Mathematics"},
            {"id": "physics", "name": "Physics"},
            {"id": "literature", "name": "Literature"},
            {"id": "history", "name": "History"},
            {"id": "biology", "name": "Biology"},
            {"id": "philosophy", "name": "Philosophy"},
            {"id": "computer-science", "name": "Computer Science"},
            {"id": "economics", "name": "Economics"},
            {"id": "chemistry", "name": "Chemistry"},
            {"id": "engineering", "name": "Engineering"},
            {"id": "arts", "name": "Arts"},
        ]
    )

    previous_raw = settings.get("_nourishment_state")
    previous = (
        NourishmentState.from_payload(previous_raw)
        if isinstance(previous_raw, dict) else None
    )

    state = compute_nourishment(
        stars=stars,
        faculties=faculties,
        previous=previous,
        events=[event],
    )

    # Persist nourishment state for temporal tracking
    _store.save_settings({"_nourishment_state": state.to_payload()})

    reaction = generate_star_event_reaction(state)

    # For star_removed events, trigger companion reflection (punishment loop)
    reflection_result = None
    if payload.event_type == "star_removed":
        try:
            reflection_result = orch.reflect_assistant(
                trigger="star_removed",
                force=True,
            )
        except Exception:  # noqa: BLE001
            pass

    return {
        "ok": True,
        "nourishment": state.to_payload(),
        "reaction": reaction,
        "reflection": reflection_result,
    }


@router.get("/nourishment")
def get_nourishment() -> dict:
    """Get current nourishment state."""
    orch = WorkspaceOrchestrator()
    snapshot = orch.get_assistant_snapshot()
    return dict(snapshot.get("nourishment") or {})
