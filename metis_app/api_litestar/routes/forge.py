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
import pathlib
from typing import Any

from litestar import Router, get, post
from litestar.exceptions import HTTPException

from metis_app.services import forge_proposals
from metis_app.services.forge_absorb import absorb
from metis_app.services.forge_registry import (
    TechniqueDescriptor,
    get_registry,
)
from metis_app.settings_store import load_settings

log = logging.getLogger(__name__)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]


def _proposal_db_path() -> pathlib.Path:
    """Resolve the on-disk path for ``forge_proposals.db``.

    Wrapped in a thin function so tests can patch the path to a
    pytest tmp_path without leaking writes to the repo root. Falls
    through to ``forge_proposals.DEFAULT_DB_PATH`` in production.
    """
    return forge_proposals.DEFAULT_DB_PATH


def _skills_root_for_drafts() -> pathlib.Path:
    """Resolve the directory new skill drafts get written to.

    Defaults to ``<repo>/skills`` (the same place the existing nine
    YAML-frontmatter skills live). Tests patch this to a tmp path.
    """
    return _REPO_ROOT / "skills"


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
    result = absorb(url.strip(), llm=llm)

    # Phase 4b — persist successful proposals so the review pane
    # survives a reload. We only save when the absorb pipeline
    # actually produced a proposal; matches-only or error responses
    # don't pollute the db.
    proposal_id: int | None = None
    proposal = result.get("proposal")
    if proposal:
        try:
            proposal_id = forge_proposals.save_proposal(
                db_path=_proposal_db_path(),
                source_url=str(result.get("source_url") or url),
                arxiv_id=str(result.get("arxiv_id") or "") or None,
                title=str(result.get("title") or ""),
                summary=str(result.get("summary") or "") or None,
                proposal_name=str(proposal.get("name") or ""),
                proposal_claim=str(proposal.get("claim") or ""),
                proposal_pillar=str(proposal.get("pillar_guess") or "cross-cutting"),
                proposal_sketch=str(proposal.get("implementation_sketch") or ""),
            )
        except Exception as exc:  # noqa: BLE001
            # Persistence is a best-effort enhancement — if the db is
            # unwritable (read-only filesystem, packaging issue), the
            # absorb result still ships; the user just loses the
            # review-pane survival behaviour.
            log.warning("Forge proposal persistence failed: %s", exc)
    result["proposal_id"] = proposal_id
    return result


@get("/v1/forge/proposals", sync_to_thread=False)
def list_proposals_route(status: str | None = None) -> dict[str, Any]:
    """Return persisted proposals newest-first.

    Defaults to ``status="pending"`` so the review pane only renders
    rows that still need a decision. Pass ``?status=accepted`` (or
    ``rejected``) to fetch the audit history.
    """
    rows = forge_proposals.list_proposals(
        db_path=_proposal_db_path(),
        status=status if status else "pending",
    )
    return {"proposals": rows}


@post("/v1/forge/proposals/{proposal_id:int}/accept", status_code=200, sync_to_thread=False)
def accept_proposal_route(proposal_id: int) -> dict[str, Any]:
    """Draft a ``skills/<slug>/SKILL.md`` from the proposal and mark
    the row accepted. Returns ``{status, skill_path}`` so the
    frontend can deep-link the user to the file they should edit.

    A 409 is returned when the slug already has a SKILL.md (the
    user has accepted twice; we don't silently clobber). A 404
    means the id doesn't exist.
    """
    db_path = _proposal_db_path()
    proposal = forge_proposals.get_proposal(db_path=db_path, proposal_id=proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")

    skills_root = _skills_root_for_drafts()
    try:
        skill_path = forge_proposals.write_skill_draft(
            db_path=db_path,
            proposal_id=proposal_id,
            skills_root=skills_root,
        )
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    relative = str(skill_path.relative_to(skills_root.parent)) if skill_path.is_absolute() else str(skill_path)
    forge_proposals.mark_accepted(
        db_path=db_path,
        proposal_id=proposal_id,
        skill_path=relative,
    )
    return {
        "status": "accepted",
        "skill_path": relative,
        "proposal_id": proposal_id,
    }


@post("/v1/forge/proposals/{proposal_id:int}/reject", status_code=200, sync_to_thread=False)
def reject_proposal_route(proposal_id: int) -> dict[str, Any]:
    """Mark the proposal rejected without writing any skill draft."""
    db_path = _proposal_db_path()
    proposal = forge_proposals.get_proposal(db_path=db_path, proposal_id=proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"proposal {proposal_id} not found")
    forge_proposals.mark_rejected(db_path=db_path, proposal_id=proposal_id)
    return {"status": "rejected", "proposal_id": proposal_id}


router = Router(
    path="",
    route_handlers=[
        list_techniques,
        absorb_technique,
        list_proposals_route,
        accept_proposal_route,
        reject_proposal_route,
    ],
    tags=["forge"],
)
