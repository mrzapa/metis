"""FastAPI routes for comet-news feature."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import metis_app.settings_store as _settings_store
from metis_app.engine import list_indexes
from metis_app.models.comet_event import CometEvent
from metis_app.services.comet_decision_engine import CometDecisionEngine
from metis_app.services.news_ingest_service import NewsIngestService

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/comets", tags=["comets"])

# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

_ingest: NewsIngestService | None = None
_engine: CometDecisionEngine | None = None
_active_comets: list[CometEvent] = []
_last_poll: float = 0.0


def _get_ingest() -> NewsIngestService:
    global _ingest
    if _ingest is None:
        _ingest = NewsIngestService()
    return _ingest


def _get_engine() -> CometDecisionEngine:
    global _engine
    if _engine is None:
        _engine = CometDecisionEngine()
    return _engine


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CometAbsorbRequest(BaseModel):
    notes: str = ""


class CometDismissRequest(BaseModel):
    reason: str = ""


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/sources")
def list_comet_sources() -> dict[str, Any]:
    """Return currently configured news sources."""
    settings = _settings_store.load_settings()
    return {
        "enabled": settings.get("news_comets_enabled", False),
        "sources": settings.get("news_comet_sources", ["rss"]),
        "rss_feeds": settings.get("news_comet_rss_feeds", []),
        "poll_interval_seconds": settings.get("news_comet_poll_interval_seconds", 300),
        "max_active": settings.get("news_comet_max_active", 5),
    }


@router.get("/active")
def list_active_comets() -> list[dict[str, Any]]:
    """Return currently active comet events."""
    return [c.to_dict() for c in _active_comets if c.phase not in ("absorbed", "dismissed")]


@router.post("/poll")
def poll_comets() -> dict[str, Any]:
    """Manually trigger a news poll cycle. Returns new comet events."""
    global _last_poll
    settings = _settings_store.load_settings()

    if not settings.get("news_comets_enabled", False):
        return {"comets": [], "message": "News comets disabled"}

    ingest = _get_ingest()
    engine = _get_engine()

    events = ingest.ingest(settings)
    if not events:
        return {"comets": [], "message": "No new items"}

    indexes = list_indexes()
    decided = engine.evaluate_batch(events, indexes, settings)

    max_active = int(settings.get("news_comet_max_active", 5))
    active_non_terminal = [c for c in _active_comets if c.phase not in ("absorbed", "dismissed", "fading")]
    slots = max(0, max_active - len(active_non_terminal))
    new_comets = decided[:slots]
    _active_comets.extend(new_comets)
    _last_poll = time.time()

    return {
        "comets": [c.to_dict() for c in new_comets],
        "total_active": len([c for c in _active_comets if c.phase not in ("absorbed", "dismissed")]),
    }


@router.get("/events")
async def comet_events_sse(poll_seconds: float = 10.0) -> StreamingResponse:
    """SSE stream of comet lifecycle events.

    Emits ``comet_update`` events whenever the active comet list changes,
    polling every *poll_seconds* seconds.
    """
    poll_seconds = max(1.0, min(poll_seconds, 120.0))

    async def _generate() -> AsyncGenerator[str, None]:
        last_hash: str | None = None
        while True:
            try:
                active = [c.to_dict() for c in _active_comets if c.phase not in ("absorbed", "dismissed")]
                data_str = json.dumps(active, sort_keys=True, default=str)
                current_hash = hashlib.sha256(data_str.encode()).hexdigest()[:16]

                if current_hash != last_hash:
                    last_hash = current_hash
                    event_data = json.dumps({
                        "type": "comet_update",
                        "hash": current_hash,
                        "comets": active,
                        "timestamp": time.time(),
                    }, default=str)
                    yield f"data: {event_data}\n\n"
            except Exception as exc:
                log.debug("comet events SSE error: %s", exc)
            await asyncio.sleep(poll_seconds)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/{comet_id}/absorb")
def absorb_comet(comet_id: str, body: CometAbsorbRequest | None = None) -> dict[str, Any]:
    """Mark a comet as absorbed — METIS incorporates the news into the faculty."""
    for comet in _active_comets:
        if comet.comet_id == comet_id:
            comet.phase = "absorbing"
            comet.absorbed_at = time.time()
            return {"ok": True, "comet": comet.to_dict()}
    raise HTTPException(status_code=404, detail="Comet not found")


@router.post("/{comet_id}/dismiss")
def dismiss_comet(comet_id: str, body: CometDismissRequest | None = None) -> dict[str, Any]:
    """Dismiss a comet — let it drift away."""
    for comet in _active_comets:
        if comet.comet_id == comet_id:
            comet.phase = "dismissed"
            return {"ok": True, "comet": comet.to_dict()}
    raise HTTPException(status_code=404, detail="Comet not found")
