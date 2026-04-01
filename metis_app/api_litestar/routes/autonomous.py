"""Autonomous research endpoints."""

from __future__ import annotations

import logging
from typing import Any

from litestar import Router, get, post
from litestar.exceptions import HTTPException as LitestarHTTPException

import metis_app.settings_store as _settings_store
from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator

_log = logging.getLogger(__name__)


@get("/v1/autonomous/status")
async def get_autonomous_status() -> dict[str, Any]:
    settings = _settings_store.load_settings()
    policy = settings.get("assistant_policy") or {}
    return {
        "enabled": bool(policy.get("autonomous_research_enabled", False)),
        "provider": str(policy.get("autonomous_research_provider") or "tavily"),
        "web_search_api_key_set": bool(
            str(settings.get("web_search_api_key") or "").strip()
        ),
    }


@post("/v1/autonomous/trigger")
async def trigger_autonomous_research() -> dict[str, Any]:
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


router = Router(
    path="",
    route_handlers=[get_autonomous_status, trigger_autonomous_research],
    tags=["autonomous"],
)