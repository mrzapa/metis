"""Async worker loop for the Seedling lifecycle shell."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
import logging
from typing import Any, cast

from .scheduler import SeedlingSchedule
from .status import SeedlingStatus, SeedlingStatusCache, isoformat_utc, utc_now

log = logging.getLogger(__name__)

Clock = Callable[[], datetime]
ProgressCallback = Callable[[dict[str, object]], None]
TickWorkFn = Callable[[], dict[str, Any] | None]


class SeedlingWorker:
    """Owns the always-on schedule.

    Phase 2 (PR #541) shipped this as a tickless heartbeat. Phase 3
    extends each tick with a feed-ingestion + cleanup pass when
    ``news_comets_enabled`` is set in settings, via an injectable
    ``tick_work`` callable. Per ADR 0013, no model loading happens
    here — the tick stays plumbing, decisioning, and storage only.
    """

    def __init__(
        self,
        *,
        schedule: SeedlingSchedule | None = None,
        status_cache: SeedlingStatusCache | None = None,
        clock: Clock | None = None,
        progress_cb: ProgressCallback | None = None,
        tick_work: TickWorkFn | None = None,
    ) -> None:
        self._schedule = schedule or SeedlingSchedule()
        self._status_cache = status_cache or SeedlingStatusCache()
        self._clock = clock or utc_now
        self._progress_cb = progress_cb
        self._tick_work = tick_work
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
            model_status=self._status.model_status,
            last_overnight_reflection_at=self._status.last_overnight_reflection_at,
        )
        self._status_cache.write(self._status)
        self._emit("completed", "Seedling lifecycle stopped")
        return self._status

    def tick(self) -> SeedlingStatus:
        """Publish a no-op heartbeat for Phase 2 liveness.

        Preserves ``model_status`` and ``last_overnight_reflection_at``
        across ticks so Phase 4b's overnight scheduler decisions are
        stable. The lifecycle hook updates those fields explicitly via
        :meth:`set_overnight_status` after each scheduling decision.
        """
        now = self._clock()
        next_action_at = self._schedule.next_action_at(now)
        self._status = SeedlingStatus(
            running=True,
            last_tick_at=isoformat_utc(now),
            current_stage="seedling",
            next_action_at=isoformat_utc(next_action_at),
            queue_depth=0,
            model_status=self._status.model_status,
            last_overnight_reflection_at=self._status.last_overnight_reflection_at,
        )
        self._status_cache.write(self._status)
        self._emit("running", "Seedling heartbeat")
        return self._status

    def set_overnight_status(
        self,
        *,
        model_status: str | None = None,
        last_overnight_reflection_at: str | None = None,
    ) -> SeedlingStatus:
        """Update the Phase 4b status fields without triggering a tick.

        Called by :func:`metis_app.seedling.lifecycle._default_tick_work`
        after the overnight scheduler decides whether to recompute
        ``model_status`` (every tick) or bump
        ``last_overnight_reflection_at`` (only on success). Cache write
        happens synchronously so the next ``GET /v1/seedling/status``
        sees the fresh values.
        """
        from .status import SeedlingModelStatus  # local import for forward-ref

        next_model_status = self._status.model_status
        if model_status is not None and model_status != self._status.model_status:
            # Validate against the literal — fall back to existing rather
            # than persist a typo.
            allowed = {"frontend_only", "backend_configured", "backend_disabled", "backend_unavailable"}
            if model_status in allowed:
                next_model_status = cast(SeedlingModelStatus, model_status)

        next_last_overnight = self._status.last_overnight_reflection_at
        if last_overnight_reflection_at is not None:
            text = (last_overnight_reflection_at or "").strip()
            next_last_overnight = text or None

        if (
            next_model_status == self._status.model_status
            and next_last_overnight == self._status.last_overnight_reflection_at
        ):
            return self._status

        self._status = SeedlingStatus(
            running=self._status.running,
            last_tick_at=self._status.last_tick_at,
            current_stage=self._status.current_stage,
            next_action_at=self._status.next_action_at,
            queue_depth=self._status.queue_depth,
            model_status=next_model_status,
            last_overnight_reflection_at=next_last_overnight,
        )
        self._status_cache.write(self._status)
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
                    await self._run_tick_work()
        except asyncio.CancelledError:
            log.debug("Seedling worker task cancelled")
            raise

    async def _run_tick_work(self) -> None:
        """Drive Phase 3 ingestion + cleanup off the main event loop.

        Wrapped in ``asyncio.to_thread`` because the underlying
        ``run_poll_cycle`` issues blocking HTTP fetches via
        ``audited_urlopen`` and SQLite writes via the feed repository.
        Exceptions are logged and swallowed so a single bad tick does
        not kill the worker.
        """
        if self._tick_work is None:
            return
        try:
            await asyncio.to_thread(self._tick_work)
        except Exception:  # noqa: BLE001
            log.warning("Seedling tick work failed", exc_info=True)
            self._emit("error", "Seedling tick work failed")

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
