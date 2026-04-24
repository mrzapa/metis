"""Cadence helpers for the Seedling worker."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

DEFAULT_TICK_INTERVAL_SECONDS = 60.0


@dataclass(frozen=True)
class SeedlingSchedule:
    """Simple fixed-interval schedule for the Phase 2 lifecycle shell."""

    tick_interval_seconds: float = DEFAULT_TICK_INTERVAL_SECONDS

    def __post_init__(self) -> None:
        if self.tick_interval_seconds <= 0:
            raise ValueError("tick_interval_seconds must be greater than zero")

    def next_action_at(self, now: datetime) -> datetime:
        return now + timedelta(seconds=self.tick_interval_seconds)
