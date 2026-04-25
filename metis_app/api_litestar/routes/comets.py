"""Litestar routes for comet-news feature."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from litestar import Request, Router, get, post
from litestar.datastructures import UploadFile
from litestar.exceptions import HTTPException as LitestarHTTPException
from litestar.response import Stream
from pydantic import BaseModel

import metis_app.settings_store as _settings_store
from metis_app.services.comet_pipeline import (
    get_default_engine,
    get_default_ingest_service,
    resolve_feed_repository,
    run_poll_cycle,
)
from metis_app.services.news_feed_repository import NewsFeedRepository
from metis_app.services.opml_import import (
    OpmlImportError,
    merge_feed_urls,
    parse_opml,
)

log = logging.getLogger(__name__)

# SSE longevity cap; matches the previous in-memory implementation.
_SSE_MAX_DURATION = 25 * 60  # 25 minutes max per SSE connection
_LIST_ACTIVE_LIMIT = 100  # parity with the previous in-memory module-state cap


# ---------------------------------------------------------------------------
# Repository accessor — kept thin so tests can swap in a `:memory:` repo.
# ---------------------------------------------------------------------------


def _get_repo() -> NewsFeedRepository:
    """Resolve the feed repository through the shared accessor.

    Routes share :func:`resolve_feed_repository` with the Seedling
    worker tick so the very first access (HTTP or worker) honours
    the configured ``seedling_feed_db_path`` — Codex P1 from PR #545.
    """
    return resolve_feed_repository()


# Keep the legacy accessors alive for any existing test fixtures that
# import them; they now defer to the comet_pipeline module-level
# singletons.
_get_ingest = get_default_ingest_service
_get_engine = get_default_engine


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
    """Return currently active comet events (newest first)."""
    repo = _get_repo()
    return [c.to_dict() for c in repo.list_active(limit=_LIST_ACTIVE_LIMIT)]


@post("/v1/comets/poll", status_code=200)
def poll_comets() -> dict:
    """Manually trigger a news poll cycle."""
    settings = _settings_store.load_settings()
    return run_poll_cycle(settings)


@get("/v1/comets/events")
async def comet_events_sse(poll_seconds: float = 10.0) -> Stream:
    """SSE stream of comet lifecycle events."""
    poll_seconds = max(1.0, min(poll_seconds, 120.0))

    async def _generate() -> AsyncGenerator[bytes, None]:
        repo = _get_repo()
        started_at = time.monotonic()
        last_hash: str | None = None
        try:
            while True:
                if time.monotonic() - started_at > _SSE_MAX_DURATION:
                    break
                try:
                    active = [
                        c.to_dict() for c in repo.list_active(limit=_LIST_ACTIVE_LIMIT)
                    ]
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
    notes = (data.notes if data is not None else "") or ""
    repo = _get_repo()
    updated = repo.update_phase(
        comet_id,
        "absorbing",
        notes=notes,
        absorbed_at=time.time(),
    )
    if updated is None:
        raise LitestarHTTPException(status_code=404, detail="Comet not found")
    return {"ok": True, "comet": updated.to_dict()}


@post("/v1/comets/{comet_id:str}/dismiss", status_code=200)
def dismiss_comet(comet_id: str, data: CometDismissRequest | None = None) -> dict:
    """Dismiss a comet."""
    reason = (data.reason if data is not None else "") or ""
    repo = _get_repo()
    updated = repo.update_phase(comet_id, "dismissed", notes=reason)
    if updated is None:
        raise LitestarHTTPException(status_code=404, detail="Comet not found")
    return {"ok": True, "comet": updated.to_dict()}


_OPML_DEFAULT_MAX_BYTES = 1 * 1024 * 1024  # 1 MiB


@post("/v1/comets/opml/import", status_code=200)
async def import_opml(request: Request[Any, Any, Any]) -> dict[str, object]:
    """Import an OPML file and append new feeds to ``news_comet_rss_feeds``.

    Error contract (ADR 0008 §5):

    - ``413`` when the request body or upload exceeds
      ``seedling_opml_import_max_bytes``.
    - ``400`` when the OPML XML is malformed or the document root is
      not ``<opml>``.
    - ``422`` when the document parses but contains zero ``xmlUrl``
      entries (treated as caller error).
    - ``200`` with ``{added, skipped_duplicate, skipped_invalid, errors}``
      on success.

    The endpoint never starts a poll synchronously — the next Seedling
    tick picks up the new feeds.
    """
    settings = _settings_store.load_settings()
    max_bytes = max(
        1,
        int(settings.get("seedling_opml_import_max_bytes", _OPML_DEFAULT_MAX_BYTES)),
    )

    payload: bytes | None = None
    try:
        form = await request.form()
    except Exception:  # noqa: BLE001
        form = None  # type: ignore[assignment]

    if form is not None:
        for value in form.values():
            if isinstance(value, UploadFile):
                content = await value.read()
                if len(content) > max_bytes:
                    raise LitestarHTTPException(
                        status_code=413,
                        detail=f"OPML upload exceeds {max_bytes} bytes",
                    )
                payload = content
                break

    if payload is None:
        body = await request.body()
        if len(body) > max_bytes:
            raise LitestarHTTPException(
                status_code=413, detail=f"OPML body exceeds {max_bytes} bytes"
            )
        payload = body

    if not payload:
        raise LitestarHTTPException(
            status_code=400, detail="OPML body is empty"
        )

    try:
        feed_urls = parse_opml(payload)
    except OpmlImportError as exc:
        message = str(exc)
        if "no xmlurl" in message.lower():
            raise LitestarHTTPException(status_code=422, detail=message) from exc
        raise LitestarHTTPException(status_code=400, detail=message) from exc

    existing: list[str] = list(settings.get("news_comet_rss_feeds", []) or [])
    added, skipped_duplicate, skipped_invalid = merge_feed_urls(existing, feed_urls)

    if added:
        merged = existing + added
        settings["news_comet_rss_feeds"] = merged
        try:
            _settings_store.save_settings(settings)
        except Exception as exc:  # noqa: BLE001
            log.warning("OPML settings save failed", exc_info=True)
            raise LitestarHTTPException(
                status_code=500, detail=f"Failed to save settings: {exc}"
            ) from exc

        repo = _get_repo()
        for url in added:
            try:
                repo.update_cursor(
                    source_channel="rss",
                    source_url=url,
                    last_polled_at=0.0,
                )
            except Exception:  # noqa: BLE001
                log.debug("Cursor seed for %s failed", url, exc_info=True)

    return {
        "added": len(added),
        "added_urls": added,
        "skipped_duplicate": len(skipped_duplicate),
        "skipped_invalid": len(skipped_invalid),
        "errors": [],
    }


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
        import_opml,
    ],
    tags=["comets"],
)
