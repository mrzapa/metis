"""Forge trace-integration service (M14 Phase 6).

Each ``TechniqueDescriptor`` declares the ``event_type`` strings the
engine emits when the technique fires. The Forge gallery uses this to
surface two things on each card:

* a card-face **weekly use counter** ("Used 12 times this week"), and
* an expandable **mini-timeline** of the most-recent N events with a
  short preview pulled from the event payload.

Read-only with respect to the trace store: this module never appends,
mutates, or moves trace events. It scans ``runs.jsonl`` (the global
trace log) once per request, filters by event-type membership, and
projects each match into a tiny ``{run_id, timestamp, stage,
event_type, preview}`` shape. Heavy fields (``payload`` blobs,
``retrieval_results``, ``prompt`` dumps) are dropped before they cross
the API boundary so a single noisy run can't blow up the gallery
response size.

Phase 6 explicitly leaves *aggregated analytics* — cross-technique
correlation, "your companion uses reranker 47% more than average" — to
a later milestone. The honest per-technique counter is the win this
phase ships.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from metis_app.services.forge_registry import TechniqueDescriptor
from metis_app.services.trace_store import TraceStore

log = logging.getLogger(__name__)

# Card-face counter window. Seven days mirrors VISION's "this week"
# rhythm and keeps the counter honest — a technique active in the
# last week is a real "earning its keep" signal; a technique only
# active months ago should not stay decorated as "in use".
_WEEKLY_WINDOW = timedelta(days=7)

# Hard upper bound on how many recent events we project per detail
# call. A run can emit dozens of events of the same type (one per
# iteration, per chunk, etc.); without a cap we'd ship the entire run
# back. The default UI surface only renders ~10 entries anyway.
_DEFAULT_LIMIT = 20

# Event payload preview cap. The frontend wants a one-liner, not a
# dump; trim aggressively but leave enough room for "converged after
# 3 iterations" or "rerank lifted top-1 from 0.42 → 0.81".
_PREVIEW_MAX_CHARS = 160


def _parse_iso(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp into a UTC ``datetime``.

    Mirrors the helper in ``trace_store._parse_iso_timestamp``; we
    don't import that one because it's underscore-prefixed — copying
    the four-line normaliser is cleaner than reaching across the seam.
    """
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _payload_preview(payload: Any) -> str:
    """Render a one-line preview of a TraceEvent payload.

    Strategy:
    1. Prefer ``summary`` / ``message`` / ``status`` keys when present
       — these are the human-readable strings the engine already
       writes for lifecycle events.
    2. Fall back to a comma-separated ``key=value`` rendering for the
       first few entries.
    3. Truncate to ``_PREVIEW_MAX_CHARS``.
    """
    if not isinstance(payload, dict):
        return ""
    for key in ("summary", "message", "status_text", "status"):
        candidate = payload.get(key)
        if isinstance(candidate, str) and candidate.strip():
            text = candidate.strip()
            return text[:_PREVIEW_MAX_CHARS - 1] + "…" if len(text) > _PREVIEW_MAX_CHARS else text
    bits: list[str] = []
    for key, value in list(payload.items())[:3]:
        # Skip noisy fields that would explode the preview without
        # adding signal; the frontend has the run_id link if the user
        # wants the full payload.
        if key in {
            "prompt",
            "retrieval_results",
            "tool_calls",
            "validator",
            "artifacts",
            "citations_chosen",
        }:
            continue
        try:
            rendered = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            rendered = str(value)
        if len(rendered) > 60:
            rendered = rendered[:59] + "…"
        bits.append(f"{key}={rendered}")
    text = ", ".join(bits)
    return text[:_PREVIEW_MAX_CHARS - 1] + "…" if len(text) > _PREVIEW_MAX_CHARS else text


def _iter_runs_jsonl(store: TraceStore) -> Iterable[dict[str, Any]]:
    """Yield rows from ``runs.jsonl`` skipping corrupt lines.

    Mirrors ``TraceStore.read_run`` defensiveness — a single torn
    line shouldn't 500 the gallery.
    """
    if not store.runs_jsonl.exists():
        return []
    rows: list[dict[str, Any]] = []
    raw = store.runs_jsonl.read_text(encoding="utf-8", errors="replace")
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def recent_uses_for_technique(
    *,
    descriptor: TechniqueDescriptor,
    store: TraceStore,
    limit: int = _DEFAULT_LIMIT,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the most-recent trace events that match the descriptor's
    declared markers, plus a 7-day weekly count.

    Returns ``{"events": [...], "weekly_count": int}``. ``events`` is
    capped at *limit* entries and ordered newest-first. Each event is
    projected into a minimal shape the frontend can render directly:
    ``{run_id, timestamp, stage, event_type, preview}``.
    """
    markers = set(descriptor.trace_event_types)
    if not markers:
        return {"events": [], "weekly_count": 0}

    cutoff: datetime
    if now is None:
        cutoff = datetime.now(timezone.utc) - _WEEKLY_WINDOW
    else:
        cutoff = (
            now.astimezone(timezone.utc)
            if now.tzinfo is not None
            else now.replace(tzinfo=timezone.utc)
        ) - _WEEKLY_WINDOW

    weekly_count = 0
    matched: list[tuple[datetime | None, dict[str, Any]]] = []
    for row in _iter_runs_jsonl(store):
        event_type = str(row.get("event_type") or "")
        if event_type not in markers:
            continue
        ts = _parse_iso(row.get("timestamp"))
        if ts is not None and ts >= cutoff:
            weekly_count += 1
        matched.append((ts, row))

    # Newest-first; rows without timestamps sort to the bottom so a
    # malformed timestamp doesn't masquerade as the most-recent event.
    matched.sort(
        key=lambda pair: pair[0] or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    capped_limit = max(0, int(limit))
    events: list[dict[str, Any]] = []
    for _ts, row in matched[:capped_limit]:
        events.append(
            {
                "run_id": str(row.get("run_id") or ""),
                "timestamp": str(row.get("timestamp") or ""),
                "stage": str(row.get("stage") or ""),
                "event_type": str(row.get("event_type") or ""),
                "preview": _payload_preview(row.get("payload")),
            }
        )

    return {"events": events, "weekly_count": weekly_count}


def weekly_use_counts(
    *,
    descriptors: tuple[TechniqueDescriptor, ...],
    store: TraceStore,
    now: datetime | None = None,
) -> dict[str, int]:
    """Return ``{descriptor.id: weekly_count}`` for every descriptor.

    Single-pass scan over ``runs.jsonl`` rather than calling
    :func:`recent_uses_for_technique` once per descriptor — the list
    endpoint renders all 13 cards and we don't want 13× the I/O on a
    single page load.
    """
    cutoff: datetime
    if now is None:
        cutoff = datetime.now(timezone.utc) - _WEEKLY_WINDOW
    else:
        cutoff = (
            now.astimezone(timezone.utc)
            if now.tzinfo is not None
            else now.replace(tzinfo=timezone.utc)
        ) - _WEEKLY_WINDOW

    # event_type -> count over the last 7 days
    per_event: dict[str, int] = {}
    for row in _iter_runs_jsonl(store):
        ts = _parse_iso(row.get("timestamp"))
        if ts is None or ts < cutoff:
            continue
        event_type = str(row.get("event_type") or "")
        if not event_type:
            continue
        per_event[event_type] = per_event.get(event_type, 0) + 1

    out: dict[str, int] = {}
    for descriptor in descriptors:
        total = 0
        for marker in descriptor.trace_event_types:
            total += per_event.get(marker, 0)
        out[descriptor.id] = total
    return out
