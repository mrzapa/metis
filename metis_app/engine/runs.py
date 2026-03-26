"""UI-neutral run event primitives."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid
from typing import Any


def now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_run_id() -> str:
    return str(uuid.uuid4())


def _normalize_json_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_normalize_json_value(item) for item in value]
    return str(value)


def _normalize_payload(payload: dict[str, Any] | Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    return {str(key): _normalize_json_value(value) for key, value in payload.items()}


@dataclass(slots=True)
class RunEvent:
    run_id: str
    timestamp: str
    stage: str
    event_type: str
    payload: dict[str, Any]
    citations_chosen: list[str] | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "run_id", str(self.run_id or ""))
        object.__setattr__(self, "timestamp", str(self.timestamp or ""))
        object.__setattr__(self, "stage", str(self.stage or ""))
        object.__setattr__(self, "event_type", str(self.event_type or ""))
        object.__setattr__(self, "payload", _normalize_payload(self.payload))
        object.__setattr__(
            self,
            "citations_chosen",
            None if self.citations_chosen is None else [str(item) for item in self.citations_chosen],
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "stage": self.stage,
            "event_type": self.event_type,
            "payload": dict(self.payload),
            "citations_chosen": None if self.citations_chosen is None else list(self.citations_chosen),
        }


__all__ = ["RunEvent", "make_run_id", "now_iso_utc"]
