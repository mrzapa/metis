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

    # Phase 4b — overnight reflection. Independent of news ingestion;
    # a user might run the backend reflection without any news comets
    # configured.
    overnight_payload = _maybe_run_overnight(settings)

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


def _maybe_run_overnight(settings: dict[str, Any]) -> dict[str, Any] | None:
    """Run the Phase 4b overnight cycle if the gates allow.

    Imports happen lazily so the rest of Phase 3's tick work doesn't
    depend on the assistant-companion service being importable.
    """
    try:
        from metis_app.services.workspace_orchestrator import (  # noqa: WPS433
            WorkspaceOrchestrator,
        )
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

    worker = _worker
    last_overnight: datetime | None = None
    if worker is not None and worker.status.last_overnight_reflection_at:
        try:
            last_overnight = datetime.fromisoformat(
                worker.status.last_overnight_reflection_at.replace("Z", "+00:00")
            )
        except ValueError:
            last_overnight = None

    orchestrator = WorkspaceOrchestrator()
    activity = _collect_overnight_activity(orchestrator)
    last_user_activity_at = _resolve_last_user_activity(orchestrator)

    payload = maybe_run_overnight_reflection(
        settings=settings,
        record_external_reflection=orchestrator.record_companion_reflection,
        last_overnight_reflection_at=last_overnight,
        last_user_activity_at=last_user_activity_at,
        activity=activity,
    )
    if payload.get("ran"):
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            if worker is not None:
                worker.set_overnight_status(last_overnight_reflection_at=now_iso)
        except Exception:  # noqa: BLE001
            log.debug("Failed to bump last_overnight_reflection_at", exc_info=True)
    return payload


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
