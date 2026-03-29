"""Autonomous research API endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

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
