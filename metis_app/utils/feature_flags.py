"""Feature flag and kill-switch helpers.

This module centralizes feature flag names and runtime evaluation rules.
Flags are stored in ``settings.json`` under:

- ``feature_flags``: per-flag boolean overrides
- ``feature_kill_switches``: per-flag temporary disable windows

Kill switches take precedence over enabled flags.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sys
from typing import Any

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):
        """Backport of stdlib StrEnum for Python 3.10."""

        def __str__(self) -> str:
            return str(self.value)


class FeatureFlag(StrEnum):
    """Known feature flags for incremental rollout."""

    API_COMPAT_OPENAI = "api_compat_openai"
    AGENT_LOOP_HARDENING = "agent_loop_hardening"
    TOOL_RUNTIME_CORE = "tool_runtime_core"
    TOOL_APPROVAL_FLOW = "tool_approval_flow"
    SESSION_LINEAGE = "session_lineage"
    EVENT_ENVELOPE_V2 = "event_envelope_v2"
    PROVIDER_FALLBACK_ROUTING = "provider_fallback_routing"
    TENANT_RBAC_MODE = "tenant_rbac_mode"
    TOPO_SCAFFOLD_ENABLED = "topo_scaffold_enabled"


_DEFAULT_STATES: dict[FeatureFlag, bool] = {
    FeatureFlag.API_COMPAT_OPENAI: False,
    FeatureFlag.AGENT_LOOP_HARDENING: False,
    FeatureFlag.TOOL_RUNTIME_CORE: False,
    FeatureFlag.TOOL_APPROVAL_FLOW: False,
    FeatureFlag.SESSION_LINEAGE: False,
    FeatureFlag.EVENT_ENVELOPE_V2: False,
    FeatureFlag.PROVIDER_FALLBACK_ROUTING: False,
    FeatureFlag.TENANT_RBAC_MODE: False,
    FeatureFlag.TOPO_SCAFFOLD_ENABLED: True,
}


@dataclass(frozen=True, slots=True)
class FeatureStatus:
    name: str
    enabled: bool
    disabled_by_kill_switch: bool
    kill_switch_reason: str
    disabled_until: str


def _parse_iso(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_kill_switch_active(kill_switch: dict[str, Any], *, now: datetime) -> bool:
    if not bool(kill_switch.get("disabled", False)):
        return False
    until = _parse_iso(kill_switch.get("disabled_until"))
    if until is None:
        return True
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return until > now


def _flag_overrides(settings: dict[str, Any]) -> dict[str, bool]:
    raw = settings.get("feature_flags")
    if not isinstance(raw, dict):
        return {}
    return {str(k): bool(v) for k, v in raw.items()}


def _kill_switches(settings: dict[str, Any]) -> dict[str, dict[str, Any]]:
    raw = settings.get("feature_kill_switches")
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            result[str(key)] = dict(value)
    return result


def get_feature_statuses(settings: dict[str, Any], *, now: datetime | None = None) -> list[FeatureStatus]:
    """Return effective status for all known feature flags."""
    now_ts = now or datetime.now(timezone.utc)
    overrides = _flag_overrides(settings)
    kill_switches = _kill_switches(settings)

    statuses: list[FeatureStatus] = []
    for flag in FeatureFlag:
        name = str(flag)
        default_enabled = _DEFAULT_STATES[flag]
        enabled = bool(overrides.get(name, default_enabled))

        kill_switch = kill_switches.get(name, {})
        active = _is_kill_switch_active(kill_switch, now=now_ts)
        if active:
            enabled = False

        statuses.append(
            FeatureStatus(
                name=name,
                enabled=enabled,
                disabled_by_kill_switch=active,
                kill_switch_reason=str(kill_switch.get("reason") or ""),
                disabled_until=str(kill_switch.get("disabled_until") or ""),
            )
        )

    return statuses


def validate_feature_name(feature_name: str) -> str:
    """Validate and normalize a feature flag name."""
    normalized = str(feature_name or "").strip()
    if not normalized:
        raise ValueError("feature name must not be empty")
    try:
        return str(FeatureFlag(normalized))
    except ValueError as exc:
        allowed = ", ".join(str(flag) for flag in FeatureFlag)
        raise ValueError(f"Unknown feature '{normalized}'. Allowed: {allowed}") from exc


def set_feature_enabled(settings: dict[str, Any], feature_name: str, enabled: bool) -> dict[str, Any]:
    """Return updated settings with a feature enable override."""
    normalized = validate_feature_name(feature_name)
    updated = dict(settings)
    flags = _flag_overrides(updated)
    flags[normalized] = bool(enabled)
    updated["feature_flags"] = flags
    return updated


def disable_feature_for_duration(
    settings: dict[str, Any],
    feature_name: str,
    *,
    reason: str = "",
    duration_ms: int = 0,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return updated settings with an active kill switch for a feature.

    ``duration_ms`` <= 0 means disable until manually cleared.
    """
    normalized = validate_feature_name(feature_name)
    updated = dict(settings)
    kill_switches = _kill_switches(updated)

    now_ts = now or datetime.now(timezone.utc)
    until_text = ""
    if duration_ms > 0:
        until = now_ts.timestamp() + (duration_ms / 1000.0)
        until_dt = datetime.fromtimestamp(until, tz=timezone.utc)
        until_text = until_dt.isoformat()

    kill_switches[normalized] = {
        "disabled": True,
        "reason": str(reason or "").strip(),
        "disabled_until": until_text,
    }
    updated["feature_kill_switches"] = kill_switches
    return updated


def clear_kill_switch(settings: dict[str, Any], feature_name: str) -> dict[str, Any]:
    """Return updated settings with a feature kill switch removed."""
    normalized = validate_feature_name(feature_name)
    updated = dict(settings)
    kill_switches = _kill_switches(updated)
    kill_switches.pop(normalized, None)
    updated["feature_kill_switches"] = kill_switches
    return updated
