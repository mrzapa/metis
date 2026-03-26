from __future__ import annotations

import json
import threading
import pytest

from metis_app.services.stream_replay import ReplayableRunStreamManager, StreamReplayStore


def test_replayable_run_stream_manager_replays_subsequent_active_events(tmp_path) -> None:
    manager = ReplayableRunStreamManager(StreamReplayStore(tmp_path))
    first_event_emitted = threading.Event()
    release_tail = threading.Event()

    def _fake_stream():
        yield {"type": "run_started", "run_id": "run-1"}
        first_event_emitted.set()
        assert release_tail.wait(timeout=2)
        yield {"type": "token", "run_id": "run-1", "text": "hello"}
        yield {"type": "final", "run_id": "run-1", "answer_text": "hello", "sources": []}

    manager.ensure_run("run-1", _fake_stream)
    assert first_event_emitted.wait(timeout=2)

    replayed_events: list[tuple[int, str]] = []

    def _collect_replay() -> None:
        for event in manager.subscribe("run-1", after_event_id=1):
            replayed_events.append((event.event_id, event.event_type))

    replay_thread = threading.Thread(target=_collect_replay, daemon=True)
    replay_thread.start()
    release_tail.set()
    replay_thread.join(timeout=2)

    assert replayed_events == [(2, "token"), (3, "final")]


def test_replayable_run_stream_manager_returns_partial_persisted_history_without_hanging(tmp_path) -> None:
    store = StreamReplayStore(tmp_path)
    store.append("run-2", 1, {"type": "run_started", "run_id": "run-2"})
    store.append("run-2", 2, {"type": "token", "run_id": "run-2", "text": "partial"})

    manager = ReplayableRunStreamManager(store)

    replayed = list(manager.subscribe("run-2", after_event_id=0))

    assert [(event.event_id, event.event_type) for event in replayed] == [
        (1, "run_started"),
        (2, "token"),
    ]


def test_stream_replay_adds_normalized_envelope_fields(tmp_path) -> None:
    store = StreamReplayStore(tmp_path)
    event = store.append("run-3", 1, {"type": "run_started", "run_id": "run-3"})

    assert event.payload["type"] == "run_started"
    assert event.payload["event_type"] == "run_started"
    assert event.payload["event_id"] == "run-3:1"
    assert event.payload["status"] == "started"
    assert event.payload["lifecycle"] == "run"
    assert event.payload["timestamp"]
    assert event.payload["context"]["run_id"] == "run-3"
    assert event.payload["payload"] == {}


def test_stream_replay_store_rejects_unknown_custom_event_type_on_append(tmp_path) -> None:
    store = StreamReplayStore(tmp_path)

    with pytest.raises(ValueError, match="unsupported stream event type: custom_event"):
        store.append("run-4", 1, {"type": "custom_event", "run_id": "run-4"})


def test_replayable_run_stream_manager_converts_unknown_custom_event_to_error(tmp_path) -> None:
    manager = ReplayableRunStreamManager(StreamReplayStore(tmp_path))

    def _fake_stream():
        yield {"type": "run_started", "run_id": "run-5"}
        yield {"type": "custom_event", "run_id": "run-5", "details": "unexpected"}

    manager.ensure_run("run-5", _fake_stream)
    replayed = list(manager.subscribe("run-5", after_event_id=0))

    assert [event.event_type for event in replayed] == ["run_started", "error"]
    assert replayed[-1].payload["run_id"] == "run-5"
    assert "unsupported stream event type: custom_event" in replayed[-1].payload["message"]


def test_stream_replay_persists_artifacts_as_metadata_only(tmp_path) -> None:
    store = StreamReplayStore(tmp_path)
    event = store.append(
        "run-6",
        1,
        {
            "type": "final",
            "run_id": "run-6",
            "answer_text": "ok",
            "sources": [],
            "artifacts": [
                {
                    "id": "a1",
                    "type": "table",
                    "summary": "artifact",
                    "payload": "x" * 20_000,
                }
            ],
        },
    )

    artifacts = list(event.payload.get("artifacts") or [])
    assert len(artifacts) == 1
    assert artifacts[0]["id"] == "a1"
    assert artifacts[0]["payload_truncated"] is False
    assert "payload" not in artifacts[0]

    rows = store.read_run("run-6")
    assert len(rows) == 1
    persisted_size = len(json.dumps(rows[0].to_payload(), ensure_ascii=False).encode("utf-8"))
    assert persisted_size < 12_000
