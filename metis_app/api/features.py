"""Feature flag and kill-switch endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

import metis_app.settings_store as _store
from metis_app.utils.feature_flags import (
    clear_kill_switch,
    disable_feature_for_duration,
    get_feature_statuses,
    set_feature_enabled,
    validate_feature_name,
)

router = APIRouter(prefix="/v1/features", tags=["features"])


class FeatureKillSwitchRequest(BaseModel):
    reason: str = ""
    duration_ms: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid")


class FeatureEnableRequest(BaseModel):
    enabled: bool = True

    model_config = ConfigDict(extra="forbid")


@router.get("")
def list_features() -> dict[str, list[dict[str, Any]]]:
    """Return effective status for all known feature flags."""
    statuses = get_feature_statuses(_store.load_settings())
    return {
        "features": [
            {
                "name": status.name,
                "enabled": status.enabled,
                "disabled_by_kill_switch": status.disabled_by_kill_switch,
                "kill_switch_reason": status.kill_switch_reason,
                "disabled_until": status.disabled_until,
            }
            for status in statuses
        ]
    }


@router.post("/{feature_name}/disable")
def disable_feature(feature_name: str, payload: FeatureKillSwitchRequest) -> dict[str, Any]:
    """Disable a feature immediately, optionally for a fixed duration."""
    try:
        normalized = validate_feature_name(feature_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    current = _store.load_settings()
    updated = disable_feature_for_duration(
        current,
        normalized,
        reason=payload.reason,
        duration_ms=int(payload.duration_ms),
    )
    try:
        _store.save_settings(updated)
    except OSError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    status = next(item for item in get_feature_statuses(_store.load_settings()) if item.name == normalized)
    return {
        "feature": normalized,
        "enabled": status.enabled,
        "disabled_by_kill_switch": status.disabled_by_kill_switch,
        "kill_switch_reason": status.kill_switch_reason,
        "disabled_until": status.disabled_until,
    }


@router.post("/{feature_name}/enable")
def enable_feature(feature_name: str, payload: FeatureEnableRequest) -> dict[str, Any]:
    """Set feature enabled state and clear active kill switch when enabling."""
    try:
        normalized = validate_feature_name(feature_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    current = _store.load_settings()
    updated = set_feature_enabled(current, normalized, payload.enabled)
    if payload.enabled:
        updated = clear_kill_switch(updated, normalized)

    try:
        _store.save_settings(updated)
    except OSError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    status = next(item for item in get_feature_statuses(_store.load_settings()) if item.name == normalized)
    return {
        "feature": normalized,
        "enabled": status.enabled,
        "disabled_by_kill_switch": status.disabled_by_kill_switch,
        "kill_switch_reason": status.kill_switch_reason,
        "disabled_until": status.disabled_until,
    }
