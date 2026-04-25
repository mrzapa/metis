"""Litestar startup/shutdown hooks for the Seedling worker."""

from __future__ import annotations

import logging
from typing import Any

from .activity import record_seedling_activity
from .status import SeedlingStatus
from .worker import SeedlingWorker

log = logging.getLogger(__name__)

_worker: SeedlingWorker | None = None


def _default_tick_work() -> dict[str, Any] | None:
    """Phase 3 ingestion + retention sweep, run from inside each tick.

    Imports happen lazily so test fixtures can construct a Seedling
    worker without paying the comet/feed import surface.
    """
    try:
        import metis_app.settings_store as _settings_store  # noqa: WPS433
        from metis_app.services.comet_pipeline import (  # noqa: WPS433
            resolve_feed_repository,
            run_poll_cycle,
        )
    except Exception:  # noqa: BLE001
        log.debug("Seedling tick work imports failed", exc_info=True)
        return None

    settings = _settings_store.load_settings()
    if not settings.get("news_comets_enabled", False):
        return None

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

    return result


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
