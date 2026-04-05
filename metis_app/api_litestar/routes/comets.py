"""Litestar routes for comet-news feature."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from litestar import Router, get, post
from litestar.exceptions import HTTPException as LitestarHTTPException
from litestar.response import Stream
from pydantic import BaseModel

import metis_app.settings_store as _settings_store
from metis_app.engine import list_indexes
from metis_app.models.comet_event import CometEvent
from metis_app.services.comet_decision_engine import CometDecisionEngine
from metis_app.services.news_ingest_service import NewsIngestService

log = logging.getLogger(__name__)

# Terminal phases that should be garbage-collected after a retention period.
_TERMINAL_PHASES = frozenset({"absorbed", "dismissed", "fading"})
_GC_RETAIN_SECONDS = 120  # keep terminal comets for 2 min (for UI fade animations)
_SSE_MAX_DURATION = 25 * 60  # 25 minutes max per SSE connection

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


def _gc_terminal_comets() -> None:
    """Remove terminal comets older than *_GC_RETAIN_SECONDS*."""
    now = time.time()
    _active_comets[:] = [
        c for c in _active_comets
        if c.phase not in _TERMINAL_PHASES
        or (now - (c.absorbed_at or c.decided_at or c.created_at)) < _GC_RETAIN_SECONDS
    ]


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CometAbsorbRequest(BaseModel):
    notes: str = ""


class CometDismissRequest(BaseModel):
    reason: str = ""


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@get("/v1/comets/sources")
def list_comet_sources() -> dict:
    """Return currently configured news sources."""
    settings = _settings_store.load_settings()
    return {
        "enabled": settings.get("news_comets_enabled", False),
        "sources": settings.get("news_comet_sources", ["rss"]),
        "available_sources": ["rss", "hackernews", "reddit"],
        "rss_feeds": settings.get("news_comet_rss_feeds", []),
        "reddit_subs": settings.get("news_comet_reddit_subs", []),
        "poll_interval_seconds": settings.get("news_comet_poll_interval_seconds", 300),
        "max_active": settings.get("news_comet_max_active", 5),
    }


@get("/v1/comets/active")
def list_active_comets() -> list[dict]:
    """Return currently active comet events."""
    _gc_terminal_comets()
    return [c.to_dict() for c in _active_comets if c.phase not in _TERMINAL_PHASES]


@post("/v1/comets/poll", status_code=200)
def poll_comets() -> dict:
    """Manually trigger a news poll cycle."""
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

    max_active = min(100, max(1, int(settings.get("news_comet_max_active", 5))))
    _gc_terminal_comets()
    active_non_terminal = [c for c in _active_comets if c.phase not in _TERMINAL_PHASES]
    slots = max(0, max_active - len(active_non_terminal))
    new_comets = decided[:slots]
    _active_comets.extend(new_comets)
    _last_poll = time.time()

    return {
        "comets": [c.to_dict() for c in new_comets],
        "total_active": len([c for c in _active_comets if c.phase not in _TERMINAL_PHASES]),
    }


@get("/v1/comets/events")
async def comet_events_sse(poll_seconds: float = 10.0) -> Stream:
    """SSE stream of comet lifecycle events."""
    poll_seconds = max(1.0, min(poll_seconds, 120.0))

    async def _generate() -> AsyncGenerator[bytes, None]:
        started_at = time.monotonic()
        last_hash: str | None = None
        try:
            while True:
                if time.monotonic() - started_at > _SSE_MAX_DURATION:
                    break
                try:
                    active = [c.to_dict() for c in _active_comets if c.phase not in _TERMINAL_PHASES]
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
                        yield f"data: {event_data}\n\n".encode()
                except Exception as exc:
                    log.debug("comet events SSE error: %s", exc)
                await asyncio.sleep(poll_seconds)
        except asyncio.CancelledError:
            pass

    return Stream(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@post("/v1/comets/{comet_id:str}/absorb", status_code=200)
def absorb_comet(comet_id: str, data: CometAbsorbRequest | None = None) -> dict:
    """Mark a comet as absorbed."""
    for comet in _active_comets:
        if comet.comet_id == comet_id:
            comet.phase = "absorbing"
            comet.absorbed_at = time.time()
            return {"ok": True, "comet": comet.to_dict()}
    raise LitestarHTTPException(status_code=404, detail="Comet not found")


@post("/v1/comets/{comet_id:str}/dismiss", status_code=200)
def dismiss_comet(comet_id: str, data: CometDismissRequest | None = None) -> dict:
    """Dismiss a comet."""
    for comet in _active_comets:
        if comet.comet_id == comet_id:
            comet.phase = "dismissed"
            return {"ok": True, "comet": comet.to_dict()}
    raise LitestarHTTPException(status_code=404, detail="Comet not found")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = Router(
    path="",
    route_handlers=[
        list_comet_sources,
        list_active_comets,
        poll_comets,
        comet_events_sse,
        absorb_comet,
        dismiss_comet,
    ],
    tags=["comets"],
)
