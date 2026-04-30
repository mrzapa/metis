"""Forge gallery endpoints (M14 Phases 1 & 2a).

Phase 1 returned a static, hard-coded inventory so the frontend shell
could render. Phase 2a replaces that with the typed registry at
``metis_app.services.forge_registry`` and resolves each technique's
``enabled`` field against the live ``settings_store``.

ADR 0014 (`docs/adr/0014-forge-route-and-toggle-state.md`) is the
architectural baseline this route is built against. Slug stability,
the ``setting_keys`` shape, and the pillar enum are all fixed there.

Settings are read once per request and shared across descriptors so a
single GET cannot stutter on multiple JSON loads.
"""

from __future__ import annotations

from typing import Any

from litestar import Router, get

from metis_app.services.forge_registry import (
    TechniqueDescriptor,
    get_registry,
)
from metis_app.settings_store import load_settings


def _serialise(descriptor: TechniqueDescriptor, settings: dict[str, Any]) -> dict[str, Any]:
    readiness = descriptor.readiness(settings)
    return {
        "id": descriptor.id,
        "name": descriptor.name,
        "description": descriptor.description,
        "pillar": descriptor.pillar,
        "enabled": descriptor.is_enabled(settings),
        "setting_keys": list(descriptor.setting_keys),
        "engine_symbols": list(descriptor.engine_symbols),
        "recent_uses": [],
        # Phase 3 — interactive toggle wiring. ``toggleable`` is a
        # convenience for the frontend; the actual override payloads
        # ride on the same object so the toggle button can call
        # ``POST /v1/settings`` directly with the right keys.
        "toggleable": descriptor.toggleable,
        "enable_overrides": descriptor.enable_overrides,
        "disable_overrides": descriptor.disable_overrides,
        # Phase 3b — runtime readiness. ``runtime_status`` is "ready"
        # or "blocked"; ``runtime_blockers`` is the list of human-
        # readable reasons a blocked technique can't be flipped.
        # ``runtime_cta_kind`` and ``runtime_cta_target`` parameterise
        # the gallery's "Get ready" affordance (install dialog vs.
        # deep-link).
        "runtime_status": readiness.status,
        "runtime_blockers": list(readiness.blockers),
        "runtime_cta_kind": readiness.cta_kind,
        "runtime_cta_target": readiness.cta_target,
    }


@get("/v1/forge/techniques", sync_to_thread=False)
def list_techniques() -> dict[str, Any]:
    """Return the live technique inventory.

    Each entry's ``enabled`` field is computed from the live
    ``settings_store`` snapshot, so user overrides surface in the
    gallery without a reload.
    """
    settings = load_settings()
    return {
        "techniques": [_serialise(descriptor, settings) for descriptor in get_registry()],
        "phase": 2,
    }


router = Router(
    path="",
    route_handlers=[list_techniques],
    tags=["forge"],
)
