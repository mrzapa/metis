"""Star Nourishment state model — tracks METIS companion hunger/satiation.

Inspired by GuppyLM's personality-through-structure pattern:
personality isn't prompted, it's built from state awareness.

The NourishmentState gives the companion a *felt sense* of its constellation:
- **hunger_level**: 0.0 (satiated) → 1.0 (starving). Rises over time
  without new stars, drops when stars are added.
- **faculty_gaps**: faculties with < threshold stars (knowledge blind spots).
- **star_events**: recent star additions/removals the companion perceives.
- **lightning_eligible**: whether the constellation has enough mass to
  unlock agent lightning (fast-path agentic execution).

Anti-sandbagging constraint: hunger NEVER degrades output quality.
It shapes desire/expression, not capability. The quality floor is
independent of nourishment state.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from .assistant_types import _coerce_float, _coerce_int, assistant_now_iso


# ---------------------------------------------------------------------------
# Star event — atomic perception of a constellation change
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class StarEvent:
    event_type: str          # "star_added" | "star_removed" | "star_evolved"
    star_id: str
    faculty_id: str
    timestamp: str
    detail: str = ""         # e.g. "Scroll star added to Physics faculty"

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> "StarEvent":
        return cls(
            event_type=str(data.get("event_type") or "star_added"),
            star_id=str(data.get("star_id") or ""),
            faculty_id=str(data.get("faculty_id") or ""),
            timestamp=str(data.get("timestamp") or assistant_now_iso()),
            detail=str(data.get("detail") or ""),
        )


# ---------------------------------------------------------------------------
# Faculty nourishment snapshot
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class FacultyNourishment:
    faculty_id: str
    faculty_name: str
    star_count: int
    satiation: float         # 0.0–1.0; per-faculty fullness
    is_gap: bool             # star_count < gap_threshold

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


# ---------------------------------------------------------------------------
# Nourishment thresholds
# ---------------------------------------------------------------------------

# Stars required per faculty before it's considered "nourished"
FACULTY_GAP_THRESHOLD = 3

# Total stars needed to unlock agent lightning
LIGHTNING_STAR_THRESHOLD = 10

# Hunger decay rate (hunger rises by this per hour without new stars)
HUNGER_DECAY_RATE_PER_HOUR = 0.04

# Maximum recent events the companion tracks
MAX_RECENT_EVENTS = 20

# Hunger response levels
HUNGER_LEVELS = {
    "satiated":  (0.0, 0.15),
    "content":   (0.15, 0.35),
    "curious":   (0.35, 0.55),
    "hungry":    (0.55, 0.75),
    "ravenous":  (0.75, 0.90),
    "starving":  (0.90, 1.01),
}


def hunger_label(level: float) -> str:
    """Map a 0.0–1.0 hunger value to a named state."""
    for name, (lo, hi) in HUNGER_LEVELS.items():
        if lo <= level < hi:
            return name
    return "starving"


# ---------------------------------------------------------------------------
# NourishmentState — the companion's felt sense of its constellation
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class NourishmentState:
    hunger_level: float = 0.5               # 0.0 satiated → 1.0 starving
    total_stars: int = 0
    integrated_stars: int = 0               # stars at "integrated" stage
    faculty_nourishment: list[FacultyNourishment] = field(default_factory=list)
    faculty_gaps: list[str] = field(default_factory=list)   # faculty_ids with gaps
    recent_events: list[StarEvent] = field(default_factory=list)
    lightning_eligible: bool = False
    last_fed_at: str = ""                   # ISO timestamp of last star_added
    last_starved_at: str = ""               # ISO timestamp when hunger hit > 0.90
    computed_at: str = ""

    @property
    def hunger_name(self) -> str:
        return hunger_label(self.hunger_level)

    @property
    def gap_count(self) -> int:
        return len(self.faculty_gaps)

    @property
    def is_starving(self) -> bool:
        return self.hunger_level >= 0.90

    @property
    def has_recent_loss(self) -> bool:
        return any(e.event_type == "star_removed" for e in self.recent_events[-5:])

    def to_payload(self) -> dict[str, Any]:
        d = asdict(self)
        d["hunger_name"] = self.hunger_name
        d["gap_count"] = self.gap_count
        d["is_starving"] = self.is_starving
        d["has_recent_loss"] = self.has_recent_loss
        return d

    @classmethod
    def from_payload(cls, data: dict[str, Any] | None) -> "NourishmentState":
        if not data:
            return cls(computed_at=assistant_now_iso())
        return cls(
            hunger_level=max(0.0, min(1.0, _coerce_float(data.get("hunger_level"), 0.5))),
            total_stars=max(0, _coerce_int(data.get("total_stars"), 0)),
            integrated_stars=max(0, _coerce_int(data.get("integrated_stars"), 0)),
            faculty_nourishment=[
                FacultyNourishment(**fn) if isinstance(fn, dict) else fn
                for fn in (data.get("faculty_nourishment") or [])
            ],
            faculty_gaps=list(data.get("faculty_gaps") or []),
            recent_events=[
                StarEvent.from_payload(e) if isinstance(e, dict) else e
                for e in (data.get("recent_events") or [])
            ],
            lightning_eligible=bool(data.get("lightning_eligible", False)),
            last_fed_at=str(data.get("last_fed_at") or ""),
            last_starved_at=str(data.get("last_starved_at") or ""),
            computed_at=str(data.get("computed_at") or assistant_now_iso()),
        )


# ---------------------------------------------------------------------------
# Compute nourishment from raw star data
# ---------------------------------------------------------------------------

def compute_nourishment(
    stars: list[dict[str, Any]],
    faculties: list[dict[str, str]],
    previous: NourishmentState | None = None,
    events: list[StarEvent] | None = None,
) -> NourishmentState:
    """Derive a NourishmentState from the current constellation.

    Parameters
    ----------
    stars : list of star dicts (from settings["landing_constellation_user_stars"])
    faculties : list of {id, name} dicts (the 11 constellation faculties)
    previous : optional prior state for temporal hunger computation
    events : optional new star events to append
    """
    now = assistant_now_iso()
    total = len(stars)
    integrated = sum(1 for s in stars if (s.get("stage") or "seed") == "integrated")

    # Per-faculty nourishment
    faculty_star_counts: dict[str, int] = {}
    for star in stars:
        fid = star.get("primaryDomainId") or star.get("faculty_id") or ""
        if fid:
            faculty_star_counts[fid] = faculty_star_counts.get(fid, 0) + 1

    faculty_nourishment: list[FacultyNourishment] = []
    faculty_gaps: list[str] = []
    for fac in faculties:
        fid = fac["id"]
        fname = fac["name"]
        count = faculty_star_counts.get(fid, 0)
        sat = min(1.0, count / max(1, FACULTY_GAP_THRESHOLD * 2))
        is_gap = count < FACULTY_GAP_THRESHOLD
        faculty_nourishment.append(FacultyNourishment(
            faculty_id=fid,
            faculty_name=fname,
            star_count=count,
            satiation=sat,
            is_gap=is_gap,
        ))
        if is_gap:
            faculty_gaps.append(fid)

    # Hunger computation — based on star density + temporal decay
    if total == 0:
        hunger = 1.0
    else:
        # Base hunger from star density (more stars → less hungry)
        density_hunger = max(0.0, 1.0 - (total / 30.0))
        # Gap pressure: each gap faculty adds hunger
        gap_pressure = min(0.3, len(faculty_gaps) * 0.05)
        # Temporal decay since last feeding
        time_hunger = 0.0
        if previous and previous.last_fed_at:
            try:
                last_fed = datetime.fromisoformat(previous.last_fed_at)
                hours_since = (datetime.now(timezone.utc) - last_fed).total_seconds() / 3600
                time_hunger = min(0.3, hours_since * HUNGER_DECAY_RATE_PER_HOUR)
            except (ValueError, TypeError):
                pass
        hunger = min(1.0, density_hunger + gap_pressure + time_hunger)

    # Merge events
    recent = list((previous.recent_events if previous else []))
    if events:
        recent.extend(events)
    recent = recent[-MAX_RECENT_EVENTS:]

    # Determine last_fed_at
    last_fed = (previous.last_fed_at if previous else "") or ""
    for evt in (events or []):
        if evt.event_type == "star_added":
            last_fed = evt.timestamp

    lightning = total >= LIGHTNING_STAR_THRESHOLD

    last_starved = (previous.last_starved_at if previous else "") or ""
    if hunger >= 0.90 and not last_starved:
        last_starved = now

    return NourishmentState(
        hunger_level=round(hunger, 3),
        total_stars=total,
        integrated_stars=integrated,
        faculty_nourishment=faculty_nourishment,
        faculty_gaps=faculty_gaps,
        recent_events=recent,
        lightning_eligible=lightning,
        last_fed_at=last_fed,
        last_starved_at=last_starved,
        computed_at=now,
    )
