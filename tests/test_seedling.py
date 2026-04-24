"""Tests for the Seedling lifecycle shell."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from metis_app.seedling.activity import (
    clear_seedling_activity_events,
    list_seedling_activity_events,
    record_seedling_activity,
)
from metis_app.seedling.scheduler import SeedlingSchedule
from metis_app.seedling.status import SeedlingStatus, SeedlingStatusCache
from metis_app.seedling.worker import SeedlingWorker


def test_status_payload_sanitizes_stage_and_queue_depth() -> None:
    status = SeedlingStatus.from_dict(
        {
            "running": True,
            "last_tick_at": "2026-04-24T20:00:00+00:00",
            "current_stage": "unknown",
            "next_action_at": "",
            "queue_depth": -4,
        }
    )

    assert status.to_dict() == {
        "running": True,
        "last_tick_at": "2026-04-24T20:00:00+00:00",
        "current_stage": "seedling",
        "next_action_at": None,
        "queue_depth": 0,
    }


def test_status_cache_round_trips(tmp_path) -> None:
    cache = SeedlingStatusCache(tmp_path / "seedling_status.json")
    expected = SeedlingStatus(
        running=True,
        last_tick_at="2026-04-24T20:00:00+00:00",
        current_stage="seedling",
        next_action_at="2026-04-24T20:01:00+00:00",
        queue_depth=2,
    )

    cache.write(expected)

    assert cache.read() == expected


def test_activity_bridge_records_companion_activity_payload() -> None:
    clear_seedling_activity_events()

    record_seedling_activity(
        {
            "state": "completed",
            "summary": "Seedling lifecycle stopped",
            "status": {"running": False},
        }
    )

    events = list_seedling_activity_events()
    assert len(events) == 1
    assert events[0]["source"] == "seedling"
    assert events[0]["state"] == "completed"
    assert events[0]["summary"] == "Seedling lifecycle stopped"
    assert events[0]["payload"]["event_id"] == "seedling-1"
    assert events[0]["payload"]["status"] == {"running": False}


def test_schedule_rejects_non_positive_interval() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        SeedlingSchedule(tick_interval_seconds=0)


def test_worker_start_tick_and_stop(tmp_path) -> None:
    timestamps = iter(
        [
            datetime(2026, 4, 24, 20, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 24, 20, 1, tzinfo=timezone.utc),
        ]
    )
    events: list[dict[str, object]] = []
    worker = SeedlingWorker(
        schedule=SeedlingSchedule(tick_interval_seconds=30),
        status_cache=SeedlingStatusCache(tmp_path / "status.json"),
        clock=lambda: next(timestamps),
        progress_cb=events.append,
    )

    async def scenario() -> None:
        started = await worker.start()
        assert started.running is True
        assert started.current_stage == "seedling"
        assert started.queue_depth == 0
        assert started.next_action_at == "2026-04-24T20:00:30+00:00"

        ticked = worker.tick()
        assert ticked.last_tick_at == "2026-04-24T20:01:00+00:00"
        assert ticked.next_action_at == "2026-04-24T20:01:30+00:00"

        stopped = await worker.stop()
        assert stopped.running is False
        assert stopped.next_action_at is None

    asyncio.run(scenario())

    assert [event["summary"] for event in events] == [
        "Seedling heartbeat",
        "Seedling lifecycle started",
        "Seedling heartbeat",
        "Seedling lifecycle stopped",
    ]
