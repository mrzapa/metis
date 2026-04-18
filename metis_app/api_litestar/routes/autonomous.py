"""Autonomous research endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from litestar import Router, get, post
from litestar.exceptions import HTTPException as LitestarHTTPException
from litestar.response import ServerSentEvent

import metis_app.settings_store as _settings_store
from metis_app.services.workspace_orchestrator import (
    WorkspaceOrchestrator,
    is_autonomous_research_running,
)

_log = logging.getLogger(__name__)


@get("/v1/autonomous/status")
def get_autonomous_status() -> dict[str, Any]:
    settings = _settings_store.load_settings()
    policy = settings.get("assistant_policy") or {}
    return {
        "enabled": bool(policy.get("autonomous_research_enabled", False)),
        "provider": str(policy.get("autonomous_research_provider") or "tavily"),
        "web_search_api_key_set": bool(
            str(settings.get("web_search_api_key") or "").strip()
        ),
        "is_running": is_autonomous_research_running(),
    }


@post("/v1/autonomous/trigger", status_code=200)
def trigger_autonomous_research() -> dict[str, Any]:
    settings = _settings_store.load_settings()
    policy = dict(settings.get("assistant_policy") or {})
    policy["autonomous_research_enabled"] = True
    settings = dict(settings)
    settings["assistant_policy"] = policy

    orchestrator = WorkspaceOrchestrator()
    try:
        result = orchestrator.run_autonomous_research(settings)
        return {"ok": True, "result": result}
    except Exception as exc:  # noqa: BLE001
        _log.error("manual autonomous research trigger failed: %s", exc)
        raise LitestarHTTPException(status_code=500, detail=str(exc)) from exc


@post("/v1/autonomous/research/stream", status_code=200)
async def trigger_autonomous_research_stream() -> ServerSentEvent:
    """Trigger autonomous research and stream phase events via SSE."""
    settings = _settings_store.load_settings()
    policy = dict(settings.get("assistant_policy") or {})
    policy["autonomous_research_enabled"] = True
    settings = dict(settings)
    settings["assistant_policy"] = policy

    orchestrator = WorkspaceOrchestrator()
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    def _progress_cb(event: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(queue.put_nowait, event)

    future = loop.run_in_executor(
        None,
        lambda: orchestrator.run_autonomous_research(settings, progress_cb=_progress_cb),
    )

    async def _event_generator() -> Any:
        yield {"event": "message", "data": json.dumps({"type": "research_started"})}
        while not future.done():
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.05)
                yield {"event": "message", "data": json.dumps(event)}
            except asyncio.TimeoutError:
                pass
        await asyncio.sleep(0)
        while not queue.empty():
            yield {"event": "message", "data": json.dumps(queue.get_nowait())}
        try:
            result = future.result()
            yield {"event": "message", "data": json.dumps({"type": "research_complete", "result": result})}
        except Exception as exc:  # noqa: BLE001
            _log.error("autonomous research stream error: %s", exc)
            yield {"event": "message", "data": json.dumps({"type": "research_error", "message": str(exc)})}

    return ServerSentEvent(_event_generator())


router = Router(
    path="",
    route_handlers=[get_autonomous_status, trigger_autonomous_research, trigger_autonomous_research_stream],
    tags=["autonomous"],
)