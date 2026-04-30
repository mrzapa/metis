"""Forge gallery endpoints (M14 Phases 1, 2a, 3, 4a).

Phase 1 returned a static, hard-coded inventory so the frontend shell
could render. Phase 2a replaced that with the typed registry at
``metis_app.services.forge_registry`` and resolves each technique's
``enabled`` field against the live ``settings_store``. Phase 3
exposed the ``enable_overrides`` payloads so the frontend can flip
toggles through ``POST /v1/settings``. Phase 3b grew the runtime
readiness probe shape. Phase 4a adds ``POST /v1/forge/absorb`` —
the arxiv-paste pipeline that fetches a paper, cross-references it
against the registry, and (via the configured assistant LLM) returns
a structured ``TechniqueProposal`` for the user to review.

ADR 0014 (`docs/adr/0014-forge-route-and-toggle-state.md`) is the
architectural baseline this route is built against. Slug stability,
the ``setting_keys`` shape, and the pillar enum are all fixed there.

Settings are read once per request and shared across descriptors so a
single GET cannot stutter on multiple JSON loads.
"""

from __future__ import annotations

import logging
from typing import Any

from litestar import Router, get, post
from litestar.exceptions import HTTPException

from metis_app.services.forge_absorb import absorb
from metis_app.services.forge_registry import (
    TechniqueDescriptor,
    get_registry,
)
from metis_app.settings_store import load_settings

log = logging.getLogger(__name__)


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


def _build_llm_for_absorb(settings: dict[str, Any]) -> Any | None:
    """Resolve the assistant's configured LLM for the absorb prompt.

    Wrapped in a thin function so tests can patch it without touching
    ``llm_providers``. ``create_llm`` raises if no provider is
    available — we collapse that to ``None`` so the route returns a
    proposal=null payload instead of a 500.
    """
    try:
        from metis_app.utils.llm_providers import create_llm
    except Exception as exc:  # noqa: BLE001
        log.warning("Forge absorb: cannot import llm_providers: %s", exc)
        return None
    try:
        return create_llm(settings)
    except Exception as exc:  # noqa: BLE001
        log.warning("Forge absorb: create_llm failed: %s", exc)
        return None


@post("/v1/forge/absorb", status_code=200, sync_to_thread=False)
def absorb_technique(data: dict[str, Any]) -> dict[str, Any]:
    """Fetch + cross-reference + summarise the URL into a proposal.

    Returns the absorb pipeline's result envelope so the frontend can
    render either the matches-against-existing branch or the
    proposal-from-LLM branch in one component. Errors come back as a
    200 with ``source_kind="error"`` and a human-readable ``error``
    string — actual exceptions stay as 4xx/5xx (e.g. missing ``url``).
    """
    url = (data or {}).get("url")
    if not isinstance(url, str) or not url.strip():
        raise HTTPException(status_code=400, detail="`url` is required")

    settings = load_settings()
    llm = _build_llm_for_absorb(settings)
    return absorb(url.strip(), llm=llm)


router = Router(
    path="",
    route_handlers=[list_techniques, absorb_technique],
    tags=["forge"],
)
