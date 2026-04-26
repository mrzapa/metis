"""Litestar startup/shutdown hooks for the Seedling worker."""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

from .activity import record_seedling_activity
from .status import SeedlingStatus
from .worker import SeedlingWorker

log = logging.getLogger(__name__)

_worker: SeedlingWorker | None = None


def _default_tick_work() -> dict[str, Any] | None:
    """Phase 3 ingestion + retention + Phase 4b overnight reflection.

    Imports happen lazily so test fixtures can construct a Seedling
    worker without paying the comet/feed/companion import surface.

    The function always recomputes ``model_status`` (cheap, pure
    function over settings) so the dock's status pill flips quickly
    when the user toggles the backend reflection setting on or off.
    The overnight reflection cycle itself is gated on
    ``model_status == "backend_configured"`` plus the cadence and
    quiet-window checks in :mod:`metis_app.seedling.overnight`.
    """
    try:
        import metis_app.settings_store as _settings_store  # noqa: WPS433
        from metis_app.services.comet_pipeline import (  # noqa: WPS433
            resolve_feed_repository,
            run_poll_cycle,
        )
        from .overnight import compute_model_status  # noqa: WPS433
    except Exception:  # noqa: BLE001
        log.debug("Seedling tick work imports failed", exc_info=True)
        return None

    settings = _settings_store.load_settings()

    # Recompute model_status every tick — cheap and means the dock
    # surfaces the user's setting changes within one tick.
    worker = _worker
    if worker is not None:
        try:
            worker.set_overnight_status(model_status=compute_model_status(settings))
        except Exception:  # noqa: BLE001
            log.debug("Worker model_status update failed", exc_info=True)

    # Build the orchestrator once per tick so Phases 4b and 5 share
    # the instance (each construction wires several repos together —
    # not expensive individually but doubling was wasteful). Lazy
    # import keeps the rest of the tick decoupled from the orchestrator
    # import chain.
    orchestrator = _build_orchestrator()

    # Phase 4b — overnight reflection. Independent of news ingestion;
    # a user might run the backend reflection without any news comets
    # configured.
    overnight_payload = _maybe_run_overnight(settings, orchestrator=orchestrator)

    # Phase 5 — recompute the growth stage every tick. Idempotent
    # (returns the same stage when nothing changed); fires a
    # stage_transition CompanionActivityEvent only on actual
    # advance. Failures don't kill the rest of the tick.
    if orchestrator is not None:
        try:
            orchestrator.recompute_growth_stage(settings=settings)
        except Exception:  # noqa: BLE001
            log.debug("Growth stage recompute raised", exc_info=True)

    if not settings.get("news_comets_enabled", False):
        return overnight_payload

    repo = resolve_feed_repository()
    try:
        result = run_poll_cycle(settings, repository=repo)
    except Exception:  # noqa: BLE001
        log.warning("Seedling poll cycle raised", exc_info=True)
        result = None

    try:
        retention_days = int(settings.get("seedling_feed_retention_days", 14))
        max_rows = int(settings.get("seedling_feed_max_rows", 50_000))
        terminal_days = int(settings.get("seedling_feed_terminal_retention_days", 7))
        repo.cleanup(
            retention_days=retention_days,
            max_rows=max_rows,
            terminal_retention_days=terminal_days,
        )
    except Exception:  # noqa: BLE001
        log.warning("Seedling cleanup pass raised", exc_info=True)

    if overnight_payload is not None and isinstance(result, dict):
        result["overnight"] = overnight_payload
    return result


def _build_orchestrator() -> "Any":
    """Construct the WorkspaceOrchestrator once per tick (architect nit).

    Returns ``None`` on import failure so callers can short-circuit
    without crashing the tick.
    """
    try:
        from metis_app.services.workspace_orchestrator import (  # noqa: WPS433
            WorkspaceOrchestrator,
        )
    except Exception:  # noqa: BLE001
        log.debug("WorkspaceOrchestrator import failed", exc_info=True)
        return None
    return WorkspaceOrchestrator()


def _maybe_run_overnight(
    settings: dict[str, Any], *, orchestrator: "Any" = None
) -> dict[str, Any] | None:
    """Run the Phase 4b overnight cycle if the gates allow.

    *orchestrator* is supplied by the tick caller so this helper does
    not pay a duplicate construction cost per tick (architect nit).
    """
    try:
        from .overnight import (  # noqa: WPS433
            compute_model_status,
            maybe_run_overnight_reflection,
        )
    except Exception:  # noqa: BLE001
        log.debug("Overnight reflection imports failed", exc_info=True)
        return None

    model_status = compute_model_status(settings)
    if model_status != "backend_configured":
        return {"ran": False, "reason": f"model_status={model_status}"}

    if orchestrator is None:
        orchestrator = _build_orchestrator()
        if orchestrator is None:
            return {"ran": False, "reason": "orchestrator_unavailable"}

    worker = _worker
    # Cadence pivots on the *attempt* anchor (success OR failure) so a
    # failing GGUF doesn't enter a tight retry loop — Codex P1 from
    # PR #550 review.
    last_attempt: datetime | None = None
    if worker is not None and worker.status.last_overnight_attempt_at:
        try:
            last_attempt = datetime.fromisoformat(
                worker.status.last_overnight_attempt_at.replace("Z", "+00:00")
            )
        except ValueError:
            last_attempt = None

    activity = _collect_overnight_activity(orchestrator)
    last_user_activity_at = _resolve_last_user_activity(orchestrator)

    payload = maybe_run_overnight_reflection(
        settings=settings,
        record_external_reflection=orchestrator.record_companion_reflection,
        last_overnight_attempt_at=last_attempt,
        last_user_activity_at=last_user_activity_at,
        activity=activity,
    )
    if worker is not None:
        try:
            _record_overnight_outcome(worker=worker, payload=payload)
        except Exception:  # noqa: BLE001
            log.debug("Failed to record overnight outcome", exc_info=True)
    return payload


def _record_overnight_outcome(*, worker: SeedlingWorker, payload: dict[str, Any]) -> None:
    """Translate the runner's outcome into worker-status updates.

    Three branches:

    - **Success** (``ran=True``) — bump *both* anchors: cadence resets
      via ``last_overnight_attempt_at`` and the success timestamp
      ``last_overnight_reflection_at`` powers the morning-after card.
      Also clear any prior ``backend_unavailable`` since the model
      just demonstrated it can load.
    - **Generator error** (``reason="generator_error"``) — the model
      is configured but cannot run. Bump the attempt anchor (back-off)
      and flip ``model_status`` to ``backend_unavailable`` so the dock
      stops claiming the backend is healthy. Codex P1 fix.
    - **Other skip reasons** (cadence not due, user active, model
      status disabled, persist skipped) — no state change. The next
      tick will re-evaluate cleanly.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    reason = (payload.get("reason") or "")

    if payload.get("ran"):
        worker.set_overnight_status(
            last_overnight_reflection_at=now_iso,
            last_overnight_attempt_at=now_iso,
            model_status="backend_configured",
        )
        return

    if reason == "generator_error":
        worker.set_overnight_status(
            last_overnight_attempt_at=now_iso,
            model_status="backend_unavailable",
        )
        return

    # All other skip reasons mean we never tried generation. Don't
    # touch the anchors — the cadence gate will let us through next
    # cycle on its own terms.


def _collect_overnight_activity(orchestrator: Any) -> dict[str, Any]:
    """Gather the prior day's reflections / comets / stars for the prompt.

    Failures here are non-fatal — the prompt builder happily handles an
    empty activity dict ("no recorded activity in the prior day").
    """
    activity: dict[str, Any] = {}
    try:
        memory = orchestrator.list_assistant_memory(limit=6)
        if isinstance(memory, list):
            activity["recent_reflections"] = memory
    except Exception:  # noqa: BLE001
        log.debug("Could not list recent reflections for overnight prompt", exc_info=True)

    try:
        from metis_app.services.comet_pipeline import (  # noqa: WPS433
            resolve_feed_repository,
        )

        repo = resolve_feed_repository()
        active = repo.list_active(limit=8)
        if active:
            activity["recent_comets"] = [c.to_dict() for c in active]
    except Exception:  # noqa: BLE001
        log.debug(
            "Could not list active comets for overnight prompt", exc_info=True
        )

    return activity


def _resolve_last_user_activity(orchestrator: Any) -> datetime | None:
    """Look up the most recent user activity timestamp.

    For Phase 4b v0 we rely on the assistant snapshot's
    ``last_reflection_at`` as a proxy — every manual chat reflection
    bumps it, and so does the automatic reflection on completed runs.
    Phase 4b retro can refine this with a dedicated
    ``last_user_input_at`` field if the proxy proves too coarse.
    """
    try:
        snapshot = orchestrator.get_assistant_snapshot()
    except Exception:  # noqa: BLE001
        return None
    status = (snapshot or {}).get("status") or {}
    raw = status.get("last_reflection_at")
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def get_seedling_worker() -> SeedlingWorker:
    global _worker
    if _worker is None:
        _worker = SeedlingWorker(
            progress_cb=record_seedling_activity,
            tick_work=_default_tick_work,
        )
    return _worker


def get_seedling_status() -> SeedlingStatus:
    return get_seedling_worker().status


async def start_seedling_worker() -> None:
    await get_seedling_worker().start()


async def stop_seedling_worker() -> None:
    await get_seedling_worker().stop()


def reset_seedling_worker(worker: SeedlingWorker | None = None) -> None:
    """Replace the singleton in tests after it has been stopped."""
    global _worker
    _worker = worker
