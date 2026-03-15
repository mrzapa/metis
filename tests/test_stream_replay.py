from __future__ import annotations

import threading

from axiom_app.services.stream_replay import ReplayableRunStreamManager, StreamReplayStore


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
