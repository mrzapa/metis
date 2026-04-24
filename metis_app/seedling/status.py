"""Seedling status payload and cache helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Literal, cast

SeedlingStage = Literal["seedling", "sapling", "bloom", "elder"]

_STAGES: set[str] = {"seedling", "sapling", "bloom", "elder"}


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(timezone.utc)


def isoformat_utc(value: datetime) -> str:
    """Serialize *value* as an ISO-8601 UTC string."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class SeedlingStatus:
    """Small public status shape for the always-on Seedling worker."""

    running: bool = False
    last_tick_at: str | None = None
    current_stage: SeedlingStage = "seedling"
    next_action_at: str | None = None
    queue_depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "last_tick_at": self.last_tick_at,
            "current_stage": self.current_stage,
            "next_action_at": self.next_action_at,
            "queue_depth": max(0, int(self.queue_depth)),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "SeedlingStatus":
        if not isinstance(payload, dict):
            return cls()
        raw_stage = str(payload.get("current_stage") or "seedling")
        stage = cast(SeedlingStage, raw_stage) if raw_stage in _STAGES else "seedling"
        try:
            queue_depth = max(0, int(payload.get("queue_depth") or 0))
        except (TypeError, ValueError):
            queue_depth = 0
        return cls(
            running=bool(payload.get("running", False)),
            last_tick_at=_optional_text(payload.get("last_tick_at")),
            current_stage=stage,
            next_action_at=_optional_text(payload.get("next_action_at")),
            queue_depth=queue_depth,
        )


class SeedlingStatusCache:
    """Tiny JSON cache so status survives app reloads without a database."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path is not None else _default_cache_path()

    def read(self) -> SeedlingStatus:
        try:
            raw = self.path.read_text(encoding="utf-8")
            payload = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            # Cache is observational; a corrupt or unreadable file must not
            # block worker startup.
            return SeedlingStatus()
        return SeedlingStatus.from_dict(payload)

    def write(self, status: SeedlingStatus) -> None:
        payload = json.dumps(status.to_dict(), indent=2, sort_keys=True)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
            tmp_path.write_text(payload + "\n", encoding="utf-8")
            tmp_path.replace(self.path)
        except OSError:
            # The cache is observational only; lifecycle must continue if the
            # runtime directory is unavailable or read-only.
            return


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _default_cache_path() -> Path:
    override = os.environ.get("METIS_SEEDLING_STATUS_PATH")
    if override:
        return Path(override)
    return Path(tempfile.gettempdir()) / "metis" / "seedling_status.json"
