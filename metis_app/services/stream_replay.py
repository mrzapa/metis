"""Canonical SSE event persistence and best-effort replay helpers."""

from __future__ import annotations

import json
import pathlib
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from metis_app.engine.querying import extract_arrow_artifacts
from metis_app.services.stream_events import normalize_stream_event

_HERE = pathlib.Path(__file__).resolve().parent
_PACKAGE_ROOT = _HERE.parent
_REPO_ROOT = _PACKAGE_ROOT.parent
_DEFAULT_TRACE_DIR = _REPO_ROOT / "traces"

_CANONICAL_STREAM_TYPES = {
    "run_started",
    "retrieval_complete",
    "retrieval_augmented",
    "subqueries",
    "iteration_start",
    "gaps_identified",
    "refinement_retrieval",
    "fallback_decision",
    "token",
    "final",
    "error",
    "action_required",
}
_TERMINAL_STREAM_TYPES = {"final", "error", "action_required"}


def _normalize_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_json_value(item) for item in value]
    return str(value)


def _artifact_metadata_only(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    raw_artifacts = normalized.get("artifacts")
    if raw_artifacts is None:
        return normalized
    sanitized = extract_arrow_artifacts(
        {
            "enable_arrow_artifacts": True,
            "artifacts": raw_artifacts,
        },
        metadata_only=True,
    )
    if sanitized:
        normalized["artifacts"] = sanitized
    else:
        normalized.pop("artifacts", None)
    return normalized


def _normalize_stream_payload(run_id: str, payload: dict[str, Any], event_id: int) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("stream payload must be a dict")
    raw_event_type = str(payload.get("event_type") or payload.get("type") or "").strip()
    event_type = raw_event_type
    if event_type not in _CANONICAL_STREAM_TYPES:
        raise ValueError(f"unsupported stream event type: {event_type or '<missing>'}")
    safe_payload = _artifact_metadata_only(payload)
    normalized = {str(key): _normalize_json_value(value) for key, value in safe_payload.items()}
    normalized["type"] = event_type
    normalized["event_type"] = event_type
    normalized["run_id"] = str(run_id or "")
    return normalize_stream_event(
        normalized,
        sequence=event_id,
        source="rag_stream_replay",
    )


@dataclass(slots=True, frozen=True)
class StreamReplayEvent:
    run_id: str
    event_id: int
    payload: dict[str, Any]

    def __post_init__(self) -> None:
        normalized_run_id = str(self.run_id or "").strip()
        normalized_event_id = int(self.event_id or 0)
        if normalized_event_id <= 0:
            raise ValueError("event_id must be a positive integer")
        normalized_payload = _normalize_stream_payload(
            normalized_run_id,
            dict(self.payload or {}),
            normalized_event_id,
        )
        object.__setattr__(self, "run_id", normalized_run_id)
        object.__setattr__(self, "event_id", normalized_event_id)
        object.__setattr__(self, "payload", normalized_payload)

    @property
    def event_type(self) -> str:
        return str(self.payload.get("type") or "")

    @property
    def is_terminal(self) -> bool:
        return self.event_type in _TERMINAL_STREAM_TYPES

    def to_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "event_id": self.event_id,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any], fallback_run_id: str = "") -> "StreamReplayEvent":
        normalized_run_id = str(payload.get("run_id") or fallback_run_id or "").strip()
        return cls(
            run_id=normalized_run_id,
            event_id=int(payload.get("event_id") or 0),
            payload=dict(payload.get("payload") or {}),
        )


class StreamReplayStore:
    """Persist canonical SSE events in per-run JSONL files."""

    def __init__(self, base_dir: str | pathlib.Path | None = None) -> None:
        self.base_dir = pathlib.Path(base_dir or _DEFAULT_TRACE_DIR)
        self.streams_dir = self.base_dir / "streams"
        self.streams_dir.mkdir(parents=True, exist_ok=True)

    def _run_path(self, run_id: str) -> pathlib.Path:
        return self.streams_dir / f"{run_id}.jsonl"

    def append(
        self,
        run_id: str,
        event_id: int,
        payload: dict[str, Any],
    ) -> StreamReplayEvent:
        event = StreamReplayEvent(run_id=run_id, event_id=event_id, payload=payload)
        with self._run_path(event.run_id).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_payload(), ensure_ascii=False, sort_keys=True) + "\n")
        return event

    def read_run(self, run_id: str) -> list[StreamReplayEvent]:
        normalized_run_id = str(run_id or "").strip()
        path = self._run_path(normalized_run_id)
        if not normalized_run_id or not path.exists():
            return []
        events: list[StreamReplayEvent] = []
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            try:
                events.append(StreamReplayEvent.from_payload(payload, fallback_run_id=normalized_run_id))
            except ValueError:
                continue
        return events

    def read_after(self, run_id: str, last_event_id: int) -> list[StreamReplayEvent]:
        threshold = max(int(last_event_id or 0), 0)
        return [event for event in self.read_run(run_id) if event.event_id > threshold]


@dataclass(slots=True)
class _RunState:
    run_id: str
    events: list[StreamReplayEvent] = field(default_factory=list)
    producer_started: bool = False
    finished: bool = False
    condition: threading.Condition = field(default_factory=threading.Condition)

    @property
    def next_event_id(self) -> int:
        if not self.events:
            return 1
        return self.events[-1].event_id + 1


class ReplayableRunStreamManager:
    """Coordinate live canonical SSE production with disk-backed replay."""

    def __init__(self, store: StreamReplayStore | None = None) -> None:
        self.store = store or StreamReplayStore()
        self._states: dict[str, _RunState] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _loaded_state(run_id: str, events: list[StreamReplayEvent]) -> _RunState:
        return _RunState(
            run_id=run_id,
            events=list(events),
            producer_started=False,
            finished=True,
        )

    def ensure_run(
        self,
        run_id: str,
        event_iter_factory: Callable[[], Iterator[dict[str, Any]]],
    ) -> None:
        normalized_run_id = str(run_id or "").strip()
        if not normalized_run_id:
            raise ValueError("run_id must not be empty")
        with self._lock:
            state = self._states.get(normalized_run_id)
            if state is None:
                persisted = self.store.read_run(normalized_run_id)
                if persisted:
                    state = self._loaded_state(normalized_run_id, persisted)
                else:
                    state = _RunState(run_id=normalized_run_id)
                self._states[normalized_run_id] = state
            if state.producer_started or state.events:
                return
            state.producer_started = True
            state.finished = False
        thread = threading.Thread(
            target=self._produce,
            args=(state, event_iter_factory),
            daemon=True,
            name=f"rag-stream-{normalized_run_id[:8]}",
        )
        thread.start()

    def subscribe(self, run_id: str, after_event_id: int = 0) -> Iterator[StreamReplayEvent]:
        normalized_run_id = str(run_id or "").strip()
        threshold = max(int(after_event_id or 0), 0)
        state = self._state_for_subscription(normalized_run_id)
        if state is None:
            return
        next_index = 0
        with state.condition:
            if threshold > 0:
                next_index = sum(1 for event in state.events if event.event_id <= threshold)
        while True:
            with state.condition:
                while next_index >= len(state.events) and not state.finished:
                    state.condition.wait(timeout=0.25)
                if next_index < len(state.events):
                    event = state.events[next_index]
                    next_index += 1
                elif state.finished:
                    return
                else:
                    continue
            yield event

    def _state_for_subscription(self, run_id: str) -> _RunState | None:
        if not run_id:
            return None
        with self._lock:
            state = self._states.get(run_id)
            if state is not None:
                return state
            persisted = self.store.read_run(run_id)
            if not persisted:
                return None
            state = self._loaded_state(run_id, persisted)
            self._states[run_id] = state
            return state

    def _produce(
        self,
        state: _RunState,
        event_iter_factory: Callable[[], Iterator[dict[str, Any]]],
    ) -> None:
        try:
            for payload in event_iter_factory():
                event = self._append(state, payload)
                if event.is_terminal:
                    break
        except Exception as exc:  # noqa: BLE001
            self._append(
                state,
                {
                    "type": "error",
                    "run_id": state.run_id,
                    "message": str(exc),
                },
            )
        finally:
            with state.condition:
                state.producer_started = False
                state.finished = True
                state.condition.notify_all()

    def _append(self, state: _RunState, payload: dict[str, Any]) -> StreamReplayEvent:
        with state.condition:
            event_id = state.next_event_id
        event = self.store.append(state.run_id, event_id, payload)
        with state.condition:
            state.events.append(event)
            if event.is_terminal:
                state.finished = True
            state.condition.notify_all()
        return event


__all__ = ["ReplayableRunStreamManager", "StreamReplayEvent", "StreamReplayStore"]
