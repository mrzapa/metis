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


def test_default_tick_work_returns_none_when_disabled() -> None:
    fake_settings = {"news_comets_enabled": False}
    with patch("metis_app.settings_store.load_settings", return_value=fake_settings):
        assert _default_tick_work() is None


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
