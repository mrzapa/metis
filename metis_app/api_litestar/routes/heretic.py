"""Heretic abliteration endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from litestar import Router, get, post
from litestar.response import ServerSentEvent

from metis_app.api.models import AbliterateStreamRequest
from metis_app.services.heretic_service import HereticService

log = logging.getLogger(__name__)


def _fire_personality_baked(model_id: str) -> None:
    """Record a personality_baked event in the nourishment system.

    Called after a successful abliteration to connect heretic → companion
    identity via the PersonalityEvolution tracker.
    """
    from metis_app.models.star_nourishment import (  # noqa: PLC0415
        NourishmentState,
        PersonalityEvolution,
        StarEvent,
        assistant_now_iso,
        compute_nourishment,
    )
    import metis_app.settings_store as _store  # noqa: PLC0415

    settings = _store.load_settings()
    stars = list(settings.get("landing_constellation_user_stars") or [])
    faculties = list(settings.get("constellation_faculties") or [])
    faculty_ids = [f["id"] for f in faculties if isinstance(f, dict)]

    previous_raw = settings.get("_nourishment_state")
    previous = (
        NourishmentState.from_payload(previous_raw)
        if isinstance(previous_raw, dict) else None
    )

    personality = previous.personality if previous else PersonalityEvolution()
    personality.record_abliteration(
        model_id=model_id,
        star_count=len(stars),
        hunger_level=previous.hunger_level if previous else 0.5,
        faculty_ids=faculty_ids,
    )

    event = StarEvent(
        event_type="personality_baked",
        star_id="",
        faculty_id="",
        timestamp=assistant_now_iso(),
        detail=f"Abliterated {model_id}",
    )

    state = compute_nourishment(
        stars=stars, faculties=faculties, previous=previous,
        events=[event], personality=personality,
    )
    _store.save_settings({"_nourishment_state": state.to_payload()})
    log.info("personality_baked event recorded for %s (depth=%.3f)", model_id, state.personality_depth)


@get("/v1/heretic/preflight")
def preflight() -> dict[str, Any]:
    svc = HereticService()
    result = svc.preflight()
    return {
        "ready": result["ready"],
        "heretic_available": result["heretic"],
        "convert_script": result["convert_script"],
        "errors": result["errors"],
    }


@post("/v1/heretic/abliterate/stream")
async def abliterate_stream(payload: AbliterateStreamRequest) -> ServerSentEvent:
    loop = asyncio.get_running_loop()
    event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def _progress_cb(event: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(event_queue.put_nowait, event)

    svc = HereticService()
    future = loop.run_in_executor(
        None,
        lambda: svc.run_pipeline(
            payload.model_id,
            bnb_4bit=payload.bnb_4bit,
            outtype=payload.outtype,
            post_message=_progress_cb,
        ),
    )

    async def _event_generator() -> Any:
        yield {
            "event": "message",
            "data": json.dumps(
                {
                    "type": "started",
                    "message": f"Starting abliteration pipeline for {payload.model_id}",
                },
                ensure_ascii=False,
            ),
        }

        while not future.done():
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=0.05)
                if event.get("type") == "status":
                    event = {"type": "progress", "message": event.get("text", "")}
                yield {
                    "event": "message",
                    "data": json.dumps(event, ensure_ascii=False),
                }
            except asyncio.TimeoutError:
                pass

        await asyncio.sleep(0)
        while not event_queue.empty():
            event = event_queue.get_nowait()
            if event.get("type") == "status":
                event = {"type": "progress", "message": event.get("text", "")}
            yield {
                "event": "message",
                "data": json.dumps(event, ensure_ascii=False),
            }

        try:
            gguf_path = future.result()
            # Fire personality_baked event to connect heretic → nourishment
            try:
                _fire_personality_baked(payload.model_id)
            except Exception:  # noqa: BLE001
                log.warning("Failed to fire personality_baked event for %s", payload.model_id)
            yield {
                "event": "message",
                "data": json.dumps(
                    {
                        "type": "complete",
                        "message": "Abliteration pipeline complete",
                        "gguf_path": str(gguf_path),
                    },
                    ensure_ascii=False,
                ),
            }
        except Exception as exc:  # noqa: BLE001
            log.exception("Abliteration pipeline failed for %s", payload.model_id)
            yield {
                "event": "message",
                "data": json.dumps(
                    {"type": "error", "message": str(exc)},
                    ensure_ascii=False,
                ),
            }

    return ServerSentEvent(_event_generator())


router = Router(path="", route_handlers=[preflight, abliterate_stream], tags=["heretic"])