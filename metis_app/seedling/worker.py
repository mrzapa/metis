"""Async worker loop for the Seedling lifecycle shell."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
import logging

from .scheduler import SeedlingSchedule
from .status import SeedlingStatus, SeedlingStatusCache, isoformat_utc, utc_now

log = logging.getLogger(__name__)

Clock = Callable[[], datetime]
ProgressCallback = Callable[[dict[str, object]], None]


class SeedlingWorker:
    """Owns the future companion schedule without doing Phase 3+ work yet."""

    def __init__(
        self,
        *,
        schedule: SeedlingSchedule | None = None,
        status_cache: SeedlingStatusCache | None = None,
        clock: Clock | None = None,
        progress_cb: ProgressCallback | None = None,
    ) -> None:
        self._schedule = schedule or SeedlingSchedule()
        self._status_cache = status_cache or SeedlingStatusCache()
        self._clock = clock or utc_now
        self._progress_cb = progress_cb
        self._status = self._status_cache.read()
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None

    @property
    def status(self) -> SeedlingStatus:
        return self._status

    async def start(self) -> SeedlingStatus:
        """Start the background task and publish an immediate heartbeat."""
        if self._task is not None and not self._task.done():
            return self._status

        self._stop_event = asyncio.Event()
        status = self.tick()
        self._task = asyncio.create_task(self._run(), name="metis-seedling-worker")
        self._emit("running", "Seedling lifecycle started")
        return status

    async def stop(self) -> SeedlingStatus:
        """Signal the background task and publish a stopped status."""
        stop_event = self._stop_event
        task = self._task
        if stop_event is not None:
            stop_event.set()
        if task is not None and task is not asyncio.current_task():
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except asyncio.TimeoutError:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._task = None
        self._stop_event = None
        self._status = SeedlingStatus(
            running=False,
            last_tick_at=self._status.last_tick_at,
            current_stage=self._status.current_stage,
            next_action_at=None,
            queue_depth=0,
        )
        self._status_cache.write(self._status)
        self._emit("completed", "Seedling lifecycle stopped")
        return self._status

    def tick(self) -> SeedlingStatus:
        """Publish a no-op heartbeat for Phase 2 liveness."""
        now = self._clock()
        next_action_at = self._schedule.next_action_at(now)
        self._status = SeedlingStatus(
            running=True,
            last_tick_at=isoformat_utc(now),
            current_stage="seedling",
            next_action_at=isoformat_utc(next_action_at),
            queue_depth=0,
        )
        self._status_cache.write(self._status)
        self._emit("running", "Seedling heartbeat")
        return self._status

    async def _run(self) -> None:
        stop_event = self._stop_event
        if stop_event is None:
            return
        try:
            while not stop_event.is_set():
                try:
                    await asyncio.wait_for(
                        stop_event.wait(),
                        timeout=self._schedule.tick_interval_seconds,
                    )
                except asyncio.TimeoutError:
                    self.tick()
        except asyncio.CancelledError:
            log.debug("Seedling worker task cancelled")
            raise

    def _emit(self, state: str, summary: str) -> None:
        if self._progress_cb is None:
            return
        try:
            self._progress_cb(
                {
                    "source": "seedling",
                    "state": state,
                    "summary": summary,
                    "status": self._status.to_dict(),
                }
            )
        except Exception:  # noqa: BLE001
            log.debug("Seedling progress callback failed", exc_info=True)


async def run(worker: SeedlingWorker | None = None) -> None:
    """Entrypoint for future direct worker execution."""
    active_worker = worker or SeedlingWorker()
    await active_worker.start()
    try:
        while active_worker.status.running:
            await asyncio.sleep(1.0)
    finally:
        if active_worker.status.running:
            await active_worker.stop()
