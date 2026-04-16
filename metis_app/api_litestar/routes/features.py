"""Feature flag endpoints."""

from __future__ import annotations

from typing import Any

from litestar import Router, get, post
from litestar.exceptions import HTTPException as LitestarHTTPException
from pydantic import BaseModel, ConfigDict, Field

import metis_app.settings_store as _store
from metis_app.utils.feature_flags import (
    clear_kill_switch,
    disable_feature_for_duration,
    get_feature_statuses,
    set_feature_enabled,
    validate_feature_name,
)


class FeatureKillSwitchRequest(BaseModel):
    reason: str = ""
    duration_ms: int = Field(default=0, ge=0)

    model_config = ConfigDict(extra="forbid")


class FeatureEnableRequest(BaseModel):
    enabled: bool = True

    model_config = ConfigDict(extra="forbid")


@get("/v1/features")
def list_features() -> dict[str, list[dict[str, Any]]]:
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


@post("/v1/features/{feature_name:str}/disable", status_code=200)
def disable_feature(
    feature_name: str,
    data: FeatureKillSwitchRequest,
) -> dict[str, Any]:
    try:
        normalized = validate_feature_name(feature_name)
    except ValueError as exc:
        raise LitestarHTTPException(status_code=422, detail=str(exc)) from exc

    current = _store.load_settings()
    updated = disable_feature_for_duration(
        current,
        normalized,
        reason=data.reason,
        duration_ms=int(data.duration_ms),
    )
    try:
        _store.save_settings(updated)
    except OSError as exc:
        raise LitestarHTTPException(status_code=503, detail=str(exc)) from exc

    status = next(item for item in get_feature_statuses(_store.load_settings()) if item.name == normalized)
    return {
        "feature": normalized,
        "enabled": status.enabled,
        "disabled_by_kill_switch": status.disabled_by_kill_switch,
        "kill_switch_reason": status.kill_switch_reason,
        "disabled_until": status.disabled_until,
    }


@post("/v1/features/{feature_name:str}/enable", status_code=200)
def enable_feature(
    feature_name: str,
    data: FeatureEnableRequest,
) -> dict[str, Any]:
    try:
        normalized = validate_feature_name(feature_name)
    except ValueError as exc:
        raise LitestarHTTPException(status_code=422, detail=str(exc)) from exc

    current = _store.load_settings()
    updated = set_feature_enabled(current, normalized, data.enabled)
    if data.enabled:
        updated = clear_kill_switch(updated, normalized)

    try:
        _store.save_settings(updated)
    except OSError as exc:
        raise LitestarHTTPException(status_code=503, detail=str(exc)) from exc

    status = next(item for item in get_feature_statuses(_store.load_settings()) if item.name == normalized)
    return {
        "feature": normalized,
        "enabled": status.enabled,
        "disabled_by_kill_switch": status.disabled_by_kill_switch,
        "kill_switch_reason": status.kill_switch_reason,
        "disabled_until": status.disabled_until,
    }


router = Router(
    path="",
    route_handlers=[list_features, disable_feature, enable_feature],
    tags=["features"],
)