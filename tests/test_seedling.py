"""Tests for the Seedling lifecycle shell."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from metis_app.seedling.activity import (
    clear_seedling_activity_events,
    get_seedling_activity_boot_id,
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
            "model_status": "ridiculous-status",  # invalid → falls back to default
        }
    )

    assert status.to_dict() == {
        "running": True,
        "last_tick_at": "2026-04-24T20:00:00+00:00",
        "current_stage": "seedling",
        "next_action_at": None,
        "queue_depth": 0,
        "model_status": "frontend_only",
        "last_overnight_reflection_at": None,
        "last_overnight_attempt_at": None,
    }


def test_status_payload_round_trips_phase4b_fields() -> None:
    payload = {
        "running": True,
        "last_tick_at": "2026-04-25T08:00:00+00:00",
        "current_stage": "seedling",
        "next_action_at": None,
        "queue_depth": 0,
        "model_status": "backend_configured",
        "last_overnight_reflection_at": "2026-04-25T06:00:00+00:00",
        "last_overnight_attempt_at": "2026-04-25T06:00:30+00:00",
    }
    status = SeedlingStatus.from_dict(payload)
    assert status.model_status == "backend_configured"
    assert status.last_overnight_reflection_at == "2026-04-25T06:00:00+00:00"
    assert status.last_overnight_attempt_at == "2026-04-25T06:00:30+00:00"
    assert status.to_dict() == payload


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


def test_status_cache_falls_back_when_file_is_not_utf8(tmp_path) -> None:
    path = tmp_path / "seedling_status.json"
    path.write_bytes(b"\xff\xfe\xfdnot valid utf-8")

    assert SeedlingStatusCache(path).read() == SeedlingStatus()


def test_activity_bridge_records_companion_activity_payload() -> None:
    clear_seedling_activity_events()
    boot_id = get_seedling_activity_boot_id()

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
    assert events[0]["payload"]["event_id"] == f"seedling-{boot_id}-1"
    assert events[0]["payload"]["boot_id"] == boot_id
    assert events[0]["payload"]["status"] == {"running": False}


def test_activity_bridge_propagates_brain_link_created_kind() -> None:
    """Phase 6 follow-up: ``kind="brain_link_created"`` is now in the
    bridge's allow-list. Events with that kind survive the filter
    (older Phase 4 / 5 kinds also keep working)."""
    clear_seedling_activity_events()
    record_seedling_activity(
        {
            "state": "completed",
            "kind": "brain_link_created",
            "summary": "Linked memory:abc → assistant:metis",
            "status": {
                "links": [
                    {
                        "source_node_id": "memory:abc",
                        "target_node_id": "assistant:metis",
                        "relation": "learned_from_session",
                    }
                ],
            },
        }
    )

    events = list_seedling_activity_events()
    assert len(events) == 1
    assert events[0]["kind"] == "brain_link_created"
    assert events[0]["state"] == "completed"
    assert events[0]["payload"]["status"]["links"][0]["relation"] == "learned_from_session"


def test_activity_bridge_drops_unknown_kind_silently() -> None:
    """Forward-compat guard: unknown ``kind`` values are dropped from
    the event (the rest of the payload still flows through). Catches
    a regression where adding a new kind to the allow-list breaks the
    drop-unknown-kind contract."""
    clear_seedling_activity_events()
    record_seedling_activity(
        {
            "state": "completed",
            "kind": "this_kind_does_not_exist",
            "summary": "Future event",
        }
    )

    events = list_seedling_activity_events()
    assert len(events) == 1
    assert "kind" not in events[0]
    assert events[0]["summary"] == "Future event"


def test_activity_bridge_rotates_boot_id_after_clear() -> None:
    clear_seedling_activity_events()
    boot_a = get_seedling_activity_boot_id()
    record_seedling_activity({"summary": "tick a"})

    clear_seedling_activity_events()
    boot_b = get_seedling_activity_boot_id()
    record_seedling_activity({"summary": "tick b"})

    assert boot_a != boot_b
    events = list_seedling_activity_events()
    assert events[0]["payload"]["event_id"] == f"seedling-{boot_b}-1"
    assert events[0]["payload"]["boot_id"] == boot_b


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
