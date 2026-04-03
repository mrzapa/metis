"""Autonomous research API endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

import metis_app.settings_store as _settings_store
from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/autonomous", tags=["autonomous"])


@router.get("/status")
def get_autonomous_status() -> dict[str, Any]:
    """Return current autonomous research configuration."""
    settings = _settings_store.load_settings()
    policy = settings.get("assistant_policy") or {}
    return {
        "enabled": bool(policy.get("autonomous_research_enabled", False)),
        "provider": str(policy.get("autonomous_research_provider") or "tavily"),
        "web_search_api_key_set": bool(
            str(settings.get("web_search_api_key") or "").strip()
        ),
    }


@router.post("/trigger")
def trigger_autonomous_research() -> dict[str, Any]:
    """Manually trigger one autonomous research cycle (dev/test use)."""
    settings = _settings_store.load_settings()
    # Override policy to enable for this one call
    policy = dict(settings.get("assistant_policy") or {})
    policy["autonomous_research_enabled"] = True
    settings = dict(settings)
    settings["assistant_policy"] = policy

    orc = WorkspaceOrchestrator()
    try:
        result = orc.run_autonomous_research(settings)
        return {"ok": True, "result": result}
    except Exception as exc:
        _log.error("manual autonomous research trigger failed: %s", exc)
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/research/stream")
async def trigger_autonomous_research_stream() -> StreamingResponse:
    """Trigger autonomous research and stream phase events via SSE."""
    settings = _settings_store.load_settings()
    policy = dict(settings.get("assistant_policy") or {})
    policy["autonomous_research_enabled"] = True
    settings = dict(settings)
    settings["assistant_policy"] = policy

    orc = WorkspaceOrchestrator()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def _progress_cb(event: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    future = loop.run_in_executor(
        None,
        lambda: orc.run_autonomous_research(settings, progress_cb=_progress_cb),
    )

    async def _event_gen() -> AsyncGenerator[str, None]:
        yield f"event: message\ndata: {json.dumps({'type': 'research_started'})}\n\n"
        while not future.done():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.05)
                yield f"event: message\ndata: {json.dumps(event)}\n\n"
            except asyncio.TimeoutError:
                pass
        await asyncio.sleep(0)
        while not queue.empty():
            event = queue.get_nowait()
            yield f"event: message\ndata: {json.dumps(event)}\n\n"
        try:
            result = future.result()
            yield f"event: message\ndata: {json.dumps({'type': 'research_complete', 'result': result})}\n\n"
        except Exception as exc:  # noqa: BLE001
            _log.error("autonomous research stream error: %s", exc)
            yield f"event: message\ndata: {json.dumps({'type': 'research_error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        _event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
