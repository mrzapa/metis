"""Phase 3 wiring tests — Seedling worker drives the comet pipeline."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from metis_app.models.comet_event import CometEvent, NewsItem
from metis_app.seedling.lifecycle import _default_tick_work
from metis_app.seedling.scheduler import SeedlingSchedule
from metis_app.seedling.status import SeedlingStatusCache
from metis_app.seedling.worker import SeedlingWorker
from metis_app.services.comet_pipeline import (
    reset_default_engine,
    reset_default_ingest_service,
    run_poll_cycle,
)
from metis_app.services.news_feed_repository import (
    NewsFeedRepository,
    reset_default_repository,
)


@pytest.fixture(autouse=True)
def isolated_pipeline_singletons():
    reset_default_repository(NewsFeedRepository(":memory:"))
    reset_default_ingest_service(None)
    reset_default_engine(None)
    yield
    reset_default_repository(None)
    reset_default_ingest_service(None)
    reset_default_engine(None)


# ---------------------------------------------------------------------------
# News-ingest LRU on top of repo
# ---------------------------------------------------------------------------


def test_news_ingest_dedup_persists_across_service_instances() -> None:
    """A new service instance must inherit the persisted dedup state.

    This is the load-bearing claim of ADR 0008 §2 — a process restart
    no longer re-emits the entire RSS window as new comets.
    """
    from metis_app.services.news_ingest_service import NewsIngestService

    repo = NewsFeedRepository(":memory:")
    item = NewsItem(
        title="Already seen",
        url="https://example.com/seen",
        source_channel="rss",
        published_at=1.0,
        fetched_at=2.0,
    )

    first = NewsIngestService(repository=repo)
    inserted = first._dedup([item])  # noqa: SLF001 — internal seam intentionally tested
    assert len(inserted) == 1

    # New service instance, same repo. Simulates a process restart.
    second = NewsIngestService(repository=repo)
    inserted_again = second._dedup([item])  # noqa: SLF001
    assert inserted_again == []


def test_news_ingest_dedup_falls_back_to_in_memory_without_repo() -> None:
    from metis_app.services.news_ingest_service import NewsIngestService

    item = NewsItem(
        title="alone",
        url="https://example.com/alone",
        source_channel="rss",
        published_at=1.0,
        fetched_at=2.0,
    )
    svc = NewsIngestService()
    assert svc._dedup([item]) == [item]  # noqa: SLF001
    assert svc._dedup([item]) == []  # noqa: SLF001


# ---------------------------------------------------------------------------
# run_poll_cycle persists into the default repo
# ---------------------------------------------------------------------------


def test_run_poll_cycle_returns_disabled_when_news_comets_off() -> None:
    result = run_poll_cycle({"news_comets_enabled": False})
    assert result["comets"] == []
    assert result["message"] == "News comets disabled"


def test_run_poll_cycle_short_circuits_when_no_items(monkeypatch) -> None:
    from metis_app.services.news_ingest_service import NewsIngestService

    class DummyIngest(NewsIngestService):
        def ingest(self, settings, *, brain_pass_fn=None):  # type: ignore[override]
            return []

    result = run_poll_cycle(
        {"news_comets_enabled": True},
        ingest=DummyIngest(),
        engine=None,
        indexes=[],
    )
    assert result == {"comets": [], "message": "No new items"}


def test_run_poll_cycle_persists_decided_comets_up_to_max_active() -> None:
    """Slot-overflow events are dropped (matches legacy behaviour)."""
    from metis_app.services.comet_decision_engine import CometDecisionEngine
    from metis_app.services.news_ingest_service import NewsIngestService

    fixed_events = [
        CometEvent(
            comet_id=f"c-{i}",
            news_item=NewsItem(
                title=f"News {i}",
                url=f"https://example.com/{i}",
                source_channel="rss",
                fetched_at=100.0 + i,
            ),
            decision="approach",
            phase="drifting",
            relevance_score=0.7,
            classification_score=0.6,
            gap_score=0.5,
        )
        for i in range(4)
    ]

    class DummyIngest(NewsIngestService):
        def ingest(self, settings, *, brain_pass_fn=None):  # type: ignore[override]
            return fixed_events

    class DummyEngine(CometDecisionEngine):
        def evaluate_batch(self, events, indexes, settings):  # type: ignore[override]
            return list(events)

    settings = {
        "news_comets_enabled": True,
        "news_comet_max_active": 2,
    }

    result = run_poll_cycle(
        settings, ingest=DummyIngest(), engine=DummyEngine(), indexes=[]
    )
    assert len(result["comets"]) == 2
    assert result["total_active"] == 2


# ---------------------------------------------------------------------------
# Default tick-work hook
# ---------------------------------------------------------------------------


def test_default_tick_work_returns_overnight_skip_when_disabled() -> None:
    """With news comets off and no backend reflection configured, the tick
    work returns the overnight runner's skip payload (Phase 4b)."""
    fake_settings = {"news_comets_enabled": False}
    with patch("metis_app.settings_store.load_settings", return_value=fake_settings):
        result = _default_tick_work()
    # With nothing configured the overnight runner reports a skipped
    # cycle rather than ``None`` so the dock can show a status pill.
    assert isinstance(result, dict)
    assert result.get("ran") is False
    assert "model_status" in (result.get("reason") or "")


def test_default_tick_work_runs_pipeline_and_cleanup_when_enabled() -> None:
    fake_settings = {
        "news_comets_enabled": True,
        "news_comet_max_active": 3,
        "news_comet_sources": [],
        "seedling_feed_retention_days": 5,
        "seedling_feed_max_rows": 10,
        "seedling_feed_terminal_retention_days": 1,
    }

    with patch("metis_app.settings_store.load_settings", return_value=fake_settings):
        result = _default_tick_work()

    # No sources are configured, so the pipeline returns either the
    # disabled marker (no comets enabled / no items) — but news_comets_enabled
    # is true so the relevant message is "No new items".
    assert isinstance(result, dict)
    assert result["comets"] == []
    assert "message" in result


def test_seedling_worker_invokes_tick_work_hook() -> None:
    """Verify the worker actually awaits tick_work after each heartbeat."""
    invocations: list[None] = []

    def tick_work() -> dict[str, object] | None:
        invocations.append(None)
        return {"comets": [], "message": "stub"}

    cache = SeedlingStatusCache(":memory:")
    schedule = SeedlingSchedule(tick_interval_seconds=0.05)
    worker = SeedlingWorker(
        schedule=schedule,
        status_cache=cache,
        tick_work=tick_work,
    )

    async def scenario() -> None:
        await worker.start()
        await asyncio.sleep(0.18)
        await worker.stop()

    asyncio.run(scenario())

    # Two ticks expected over ~180 ms with a 50 ms interval.
    assert len(invocations) >= 1


def test_seedling_worker_swallows_tick_work_exceptions() -> None:
    """A failing tick_work must not stop the worker."""
    calls: list[int] = []

    def tick_work() -> dict[str, object] | None:
        calls.append(len(calls))
        if len(calls) < 2:
            raise RuntimeError("boom")
        return None

    cache = SeedlingStatusCache(":memory:")
    schedule = SeedlingSchedule(tick_interval_seconds=0.05)
    worker = SeedlingWorker(
        schedule=schedule,
        status_cache=cache,
        tick_work=tick_work,
    )

    async def scenario() -> None:
        await worker.start()
        await asyncio.sleep(0.25)
        await worker.stop()

    asyncio.run(scenario())

    # Worker survived the first failure and called tick_work again.
    assert len(calls) >= 2


def test_seedling_worker_offloads_blocking_tick_work_via_to_thread() -> None:
    """Blocking sync work in tick_work must not stall the asyncio loop.

    Architect review I-2: this test demonstrates that
    ``await asyncio.to_thread(self._tick_work)`` is actually wrapping
    the call. If a future change replaces it with a direct sync call,
    a parallel asyncio task that fires before tick_work returns proves
    the loop wasn't blocked.
    """
    import time as _time

    blocked_for = 0.5  # seconds — long enough to dwarf the parallel sleep
    parallel_returned_at: list[float] = []
    tick_returned_at: list[float] = []

    def tick_work() -> dict[str, object] | None:
        _time.sleep(blocked_for)
        tick_returned_at.append(_time.monotonic())
        return None

    cache = SeedlingStatusCache(":memory:")
    schedule = SeedlingSchedule(tick_interval_seconds=0.01)
    worker = SeedlingWorker(
        schedule=schedule,
        status_cache=cache,
        tick_work=tick_work,
    )

    async def scenario() -> None:
        await worker.start()

        async def parallel() -> None:
            # Race against the long tick_work — if to_thread is used,
            # this returns within ~50 ms even though tick_work blocks
            # for 500 ms.
            await asyncio.sleep(0.05)
            parallel_returned_at.append(_time.monotonic())

        # Wait long enough to fire at least one tick + parallel.
        parallel_task = asyncio.create_task(parallel())
        await asyncio.sleep(0.6)
        await parallel_task
        await worker.stop()

    asyncio.run(scenario())

    assert parallel_returned_at, "parallel asyncio task never ran"
    assert tick_returned_at, "tick_work never returned"
    # The parallel coroutine must have finished BEFORE the blocking
    # tick_work returned — proves the event loop wasn't stalled.
    assert parallel_returned_at[0] < tick_returned_at[0], (
        "Event loop was blocked by tick_work; "
        "asyncio.to_thread must be in place around the call"
    )


# ---------------------------------------------------------------------------
# Settings overrides honored end-to-end (architect review I-1)
# ---------------------------------------------------------------------------


def test_default_tick_work_honors_seedling_feed_db_path(tmp_path, monkeypatch) -> None:
    """The configured ``seedling_feed_db_path`` must reach the repo singleton.

    Architect review I-1 — without this the override at install time is
    silently lost.
    """
    from metis_app.services.news_feed_repository import (
        NewsFeedRepository,
        get_default_repository,
        reset_default_repository,
    )

    reset_default_repository(None)
    db_path = tmp_path / "configured_feed.db"

    fake_settings = {
        "news_comets_enabled": True,
        "news_comet_sources": [],
        "seedling_feed_db_path": str(db_path),
        "seedling_feed_retention_days": 1,
        "seedling_feed_max_rows": 1,
        "seedling_feed_terminal_retention_days": 1,
    }
    monkeypatch.setattr(
        "metis_app.settings_store.load_settings", lambda: dict(fake_settings)
    )

    try:
        _default_tick_work()
        # The singleton resolved through _resolve_feed_repository must
        # use the configured path so the cleanup pass writes there
        # (and not at the default <repo_root>/news_items.db).
        repo = get_default_repository()
        assert isinstance(repo, NewsFeedRepository)
        assert str(repo.db_path).replace("\\", "/") == str(db_path).replace("\\", "/")
        assert db_path.exists() or repo.db_path == ":memory:"
    finally:
        reset_default_repository(None)


# ---------------------------------------------------------------------------
# LRU drift on repo failure (architect review I-3 + I-4)
# ---------------------------------------------------------------------------


def test_news_ingest_does_not_lose_items_when_repo_write_fails() -> None:
    """A repo write failure must NOT mark items as seen.

    Otherwise the items get classified once but never persisted, and
    the next tick silently skips them via the in-memory LRU. ADR 0008
    §2 promises the persistent set is the source of truth.
    """
    from metis_app.services.news_feed_repository import NewsFeedRepository
    from metis_app.services.news_ingest_service import NewsIngestService

    class FlakeyRepo(NewsFeedRepository):
        def __init__(self) -> None:
            super().__init__(":memory:")
            self.fail_next = True

        def add_news_items(self, items, *, source_url=""):  # type: ignore[override]
            if self.fail_next:
                self.fail_next = False
                raise RuntimeError("simulated SQLite hiccup")
            return super().add_news_items(items, source_url=source_url)

    repo = FlakeyRepo()
    svc = NewsIngestService(repository=repo)
    item = NewsItem(
        title="Important",
        url="https://example.com/important",
        source_channel="rss",
        published_at=1.0,
        fetched_at=2.0,
    )

    # First tick: repo throws. Items must NOT enter the LRU.
    first = svc._dedup([item])  # noqa: SLF001
    assert first == [item]  # the failure is logged, items still flow downstream

    # Second tick: repo succeeds. Items must reach the persistent set.
    second = svc._dedup([item])  # noqa: SLF001
    assert second == [item]

    # Third tick: now they're really persisted; should dedupe.
    third = svc._dedup([item])  # noqa: SLF001
    assert third == []


def test_news_ingest_lru_warm_failure_retries_on_next_call() -> None:
    """Warm failure must not permanently disable the read-through cache.

    Architect review I-4: a transient repo error during the first
    poll previously set ``_lru_warmed=True`` and never retried.
    """
    from metis_app.services.news_feed_repository import NewsFeedRepository
    from metis_app.services.news_ingest_service import NewsIngestService

    class FlakeyWarmRepo(NewsFeedRepository):
        def __init__(self) -> None:
            super().__init__(":memory:")
            self.calls: list[int] = []
            self.fail_warm = True

        def list_known_hashes(self, *, limit: int = 2000):  # type: ignore[override]
            self.calls.append(len(self.calls))
            if self.fail_warm:
                self.fail_warm = False
                raise RuntimeError("transient warm failure")
            return super().list_known_hashes(limit=limit)

    repo = FlakeyWarmRepo()
    svc = NewsIngestService(repository=repo)

    # First call triggers warm failure.
    svc._dedup([])  # noqa: SLF001 — internal warm path
    assert svc._lru_warmed is False  # noqa: SLF001 — must allow retry

    # Second call retries the warm and succeeds.
    svc._dedup([])  # noqa: SLF001
    assert svc._lru_warmed is True  # noqa: SLF001
    assert len(repo.calls) >= 2
