"""Litestar startup/shutdown hooks for the Seedling worker."""

from __future__ import annotations

from .activity import record_seedling_activity
from .status import SeedlingStatus
from .worker import SeedlingWorker

_worker: SeedlingWorker | None = None


def get_seedling_worker() -> SeedlingWorker:
    global _worker
    if _worker is None:
        _worker = SeedlingWorker(progress_cb=record_seedling_activity)
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
