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


def test_init_db_idempotent_on_repeat_calls(tmp_path) -> None:
    """The migration uses ``ALTER TABLE ADD COLUMN`` which raises
    ``OperationalError: duplicate column name`` when the column
    exists. The Codex P2 fix gates the catch to that specific
    message — but the happy path (repeat ``init_db`` on an
    already-migrated DB) must still succeed silently. Lock that."""
    from metis_app.services.assistant_repository import AssistantRepository

    repo = AssistantRepository(tmp_path / "assistant.json")
    # First call creates the table with all columns + runs the
    # ALTER TABLEs (which will raise duplicate-column for each, since
    # the CREATE TABLE already declared them).
    repo.init_db()
    # Second call must not raise — the duplicate-column errors are
    # still safely swallowed.
    repo._schema_ready = False  # force re-run of init_db's ensure path
    repo.init_db()
    # And a third — proves the migration is genuinely idempotent
    # rather than accidentally relying on a one-shot side-effect.
    repo._schema_ready = False
    repo.init_db()


def test_init_db_reraises_non_duplicate_operational_errors(tmp_path, monkeypatch) -> None:
    """Codex P2 regression (PR #572): the migration loop must NOT
    swallow ``OperationalError`` causes other than the
    duplicate-column case. Errors like ``database is locked``,
    disk-full, or schema corruption MUST propagate so startup fails
    loudly rather than entering a broken-schema state.

    Simulate a non-duplicate error by wrapping the connection in a
    proxy so any ALTER TABLE raises ``database is locked``."""
    import contextlib
    import sqlite3
    from metis_app.services.assistant_repository import AssistantRepository

    repo = AssistantRepository(tmp_path / "assistant.json")

    class _ConnProxy:
        """Connection proxy that injects a fault into ALTER TABLE
        but lets every other call through.

        ``sqlite3.Connection.execute`` is a read-only attribute, so
        we can't monkeypatch it directly — wrap the whole connection
        in a delegate-everything-except-execute proxy instead."""

        def __init__(self, real: sqlite3.Connection) -> None:
            self._real = real

        def execute(self, sql, *args, **kwargs):
            if "ALTER TABLE" in str(sql).upper():
                raise sqlite3.OperationalError("database is locked")
            return self._real.execute(sql, *args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._real, name)

    real_connect = repo._connect

    @contextlib.contextmanager
    def _faulty_connect():
        with real_connect() as conn:
            yield _ConnProxy(conn)

    monkeypatch.setattr(repo, "_connect", _faulty_connect)

    # init_db should raise — the lock error is NOT a
    # duplicate-column case and must propagate.
    with pytest.raises(sqlite3.OperationalError, match="database is locked"):
        repo.init_db()


def test_assistant_status_round_trips_growth_and_user_input_fields(tmp_path) -> None:
    """M13 retro fix: ``AssistantStatus.growth_stage``,
    ``growth_stage_changed_at``, and ``last_user_input_at`` MUST
    survive ``update_status`` → ``get_status`` round-trip on disk.

    Phase 5 added ``growth_stage`` to the dataclass but never
    extended the SQL schema — the field silently dropped on every
    persist (latent bug; in-memory tests passed because they used a
    fake repo). This test catches the regression on the real
    ``AssistantRepository`` and locks the M13 retro schema migration."""
    from metis_app.models.assistant_types import AssistantStatus
    from metis_app.services.assistant_repository import AssistantRepository

    repo = AssistantRepository(tmp_path / "assistant.json")
    status = AssistantStatus()
    status.growth_stage = "sapling"
    status.growth_stage_changed_at = "2026-04-26T05:00:00+00:00"
    status.last_user_input_at = "2026-04-26T05:30:00+00:00"
    repo.update_status(status)

    # Reconstruct from disk via a fresh repo instance to prove the
    # values genuinely persisted (not just held in process memory).
    repo2 = AssistantRepository(tmp_path / "assistant.json")
    after = repo2.get_status()
    assert after.growth_stage == "sapling"
    assert after.growth_stage_changed_at == "2026-04-26T05:00:00+00:00"
    assert after.last_user_input_at == "2026-04-26T05:30:00+00:00"


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
