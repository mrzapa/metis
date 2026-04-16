"""Assistant companion endpoints."""

from __future__ import annotations

from litestar import Router, delete, get, post
from pydantic import BaseModel

from metis_app.api_litestar.models import (
    AssistantBootstrapRequestModel,
    AssistantReflectRequestModel,
    AssistantUpdateRequestModel,
)
from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator


@get("/v1/assistant")
def get_assistant() -> dict:
    return WorkspaceOrchestrator().get_assistant_snapshot()


@post("/v1/assistant", status_code=200)
def update_assistant(data: AssistantUpdateRequestModel) -> dict:
    return WorkspaceOrchestrator().update_assistant(
        identity=data.identity,
        runtime=data.runtime,
        policy=data.policy,
        status=data.status,
    )


@get("/v1/assistant/status")
def get_assistant_status() -> dict:
    snapshot = WorkspaceOrchestrator().get_assistant_snapshot()
    return dict(snapshot.get("status") or {})


@post("/v1/assistant/reflect", status_code=200)
def reflect_assistant(data: AssistantReflectRequestModel) -> dict:
    kwargs = {
        "trigger": data.trigger,
        "session_id": data.session_id,
        "run_id": data.run_id,
        "force": data.force,
    }
    if data.context_id:
        kwargs["context_id"] = data.context_id
    return WorkspaceOrchestrator().reflect_assistant(**kwargs)


@post("/v1/assistant/bootstrap", status_code=200)
def bootstrap_assistant(data: AssistantBootstrapRequestModel) -> dict:
    return WorkspaceOrchestrator().bootstrap_assistant(
        install_local_model=data.install_local_model,
    )


@get("/v1/assistant/memory")
def list_assistant_memory(limit: int = 20) -> list[dict]:
    return WorkspaceOrchestrator().list_assistant_memory(limit=limit)


@delete("/v1/assistant/memory", status_code=200)
def clear_assistant_memory(limit: int = 10) -> dict:
    return WorkspaceOrchestrator().clear_assistant_memory(limit=limit)


# ---------------------------------------------------------------------------
# Star nourishment events
# ---------------------------------------------------------------------------

class _StarEventBody(BaseModel):
    event_type: str
    star_id: str = ""
    faculty_id: str = ""
    detail: str = ""
    model_id: str = ""


@post("/v1/assistant/nourishment/event", status_code=200)
def report_star_event(data: _StarEventBody) -> dict:
    """Report a star event to the companion nourishment system."""
    from metis_app.models.star_nourishment import (  # noqa: PLC0415
        NourishmentState,
        PersonalityEvolution,
        StarEvent,
        assistant_now_iso,
        compute_nourishment,
    )
    from metis_app.services.star_nourishment_gen import (  # noqa: PLC0415
        generate_star_event_reaction,
    )
    import metis_app.settings_store as _store  # noqa: PLC0415

    event = StarEvent(
        event_type=data.event_type,
        star_id=data.star_id,
        faculty_id=data.faculty_id,
        timestamp=assistant_now_iso(),
        detail=data.detail,
    )

    orch = WorkspaceOrchestrator()
    settings = _store.load_settings()
    stars = list(settings.get("landing_constellation_user_stars") or [])
    faculties = list(settings.get("constellation_faculties") or [])

    previous_raw = settings.get("_nourishment_state")
    previous = (
        NourishmentState.from_payload(previous_raw)
        if isinstance(previous_raw, dict) else None
    )

    personality = previous.personality if previous else PersonalityEvolution()

    if data.event_type == "personality_baked" and data.model_id:
        faculty_ids = [f["id"] for f in faculties if isinstance(f, dict)]
        personality.record_abliteration(
            model_id=data.model_id,
            star_count=len(stars),
            hunger_level=previous.hunger_level if previous else 0.5,
            faculty_ids=faculty_ids,
        )

    state = compute_nourishment(
        stars=stars, faculties=faculties, previous=previous,
        events=[event], personality=personality,
    )

    _store.save_settings({"_nourishment_state": state.to_payload()})
    reaction = generate_star_event_reaction(state)

    reflection_result = None
    if data.event_type == "star_removed":
        try:
            reflection_result = orch.reflect_assistant(trigger="star_removed", force=True)
        except Exception:  # noqa: BLE001
            pass

    return {
        "ok": True,
        "nourishment": state.to_payload(),
        "reaction": reaction,
        "reflection": reflection_result,
    }


@get("/v1/assistant/nourishment")
def get_nourishment() -> dict:
    """Get current nourishment state."""
    snapshot = WorkspaceOrchestrator().get_assistant_snapshot()
    return dict(snapshot.get("nourishment") or {})


@get("/v1/assistant/nourishment/personality")
def get_personality_evolution() -> dict:
    """Get the companion's personality evolution state."""
    import metis_app.settings_store as _store  # noqa: PLC0415
    from metis_app.models.star_nourishment import (  # noqa: PLC0415
        NourishmentState,
        PersonalityEvolution,
    )

    raw = _store.load_settings().get("_nourishment_state")
    if not isinstance(raw, dict):
        return PersonalityEvolution().to_payload()
    state = NourishmentState.from_payload(raw)
    return state.personality.to_payload()


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
        report_star_event,
        get_nourishment,
        get_personality_evolution,
    ],
    tags=["assistant"],
)