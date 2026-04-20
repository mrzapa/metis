"""Litestar routes for the M17 Network Audit panel (Phase 5a).

Exposes four read-only GET endpoints under ``/v1/network-audit/``:

- ``/events`` — paginated tail of recorded audit events (newest-first).
- ``/providers`` — per-provider status rows for the privacy panel's
  provider matrix (kill-switch state, 7-day call counts, last-call
  timestamps).
- ``/recent-count`` — count of events in a time window (powers the
  "N outbound calls in last 5 minutes" indicator at the top of the
  panel).
- ``/stream`` — SSE stream of new events for the live feed.

The synthetic-pass POST endpoint and CSV export are Phase 5c — not
in this module yet.

Design notes:

- Every route degrades cleanly when :func:`get_default_store` returns
  ``None`` (the store singleton failed to initialise — see
  ``metis_app/network_audit/runtime.py``). The panel is a privacy
  surface; a broken audit store must not 500 the whole page.
- Pydantic response models mirror the 14-field
  :class:`NetworkAuditEvent` dataclass. Datetimes are serialised as
  ISO-8601 strings (the standard Pydantic behaviour).
- The SSE route's polling cadence and hard cap (500 ms / 25 min)
  match the comets SSE route so the two streams behave consistently
  under the Litestar ASGI worker pool.

See ``plans/network-audit/plan.md`` (Phase 5) and
``docs/adr/0010-network-audit-interception.md``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from litestar import Router, get
from litestar.response import Stream
from pydantic import BaseModel

from metis_app.network_audit.kill_switches import is_provider_blocked
from metis_app.network_audit.providers import KNOWN_PROVIDERS
from metis_app.network_audit.runtime import (
    get_default_settings,
    get_default_store,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tunables
# ---------------------------------------------------------------------------

_EVENTS_DEFAULT_LIMIT = 100
_EVENTS_MAX_LIMIT = 500
_RECENT_COUNT_DEFAULT_WINDOW = 300  # 5 minutes
_RECENT_COUNT_MIN_WINDOW = 60  # 1 minute
_RECENT_COUNT_MAX_WINDOW = 7 * 24 * 60 * 60  # 7 days
_PROVIDER_WINDOW_7D_SECONDS = 7 * 24 * 60 * 60
_SSE_POLL_INTERVAL_SECONDS = 0.5
_SSE_MAX_DURATION_SECONDS = 25 * 60
# Max rows drained per SELECT. If a burst produces more than this
# between two polls, the loop immediately re-queries (no sleep) to
# keep draining. So this is a memory/throughput knob, not a lossy cap.
_SSE_DRAIN_LIMIT = 500


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class NetworkAuditEventResponse(BaseModel):
    """Wire shape for one :class:`NetworkAuditEvent` row."""

    id: str
    timestamp: datetime
    method: str
    url_host: str
    url_path_prefix: str
    query_params_stored: bool  # always False — schema invariant
    provider_key: str
    trigger_feature: str
    size_bytes_in: int | None
    size_bytes_out: int | None
    latency_ms: int | None
    status_code: int | None
    user_initiated: bool
    blocked: bool
    source: str


class ProviderStatusResponse(BaseModel):
    """Wire shape for one row of the panel's provider matrix."""

    key: str
    display_name: str
    category: str
    kill_switch_setting_key: str | None
    blocked: bool
    events_7d: int
    last_call_at: datetime | None


class RecentCountResponse(BaseModel):
    """Wire shape for the ``/recent-count`` endpoint."""

    count: int
    window_seconds: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event_to_response(event: Any) -> NetworkAuditEventResponse:
    """Project a :class:`NetworkAuditEvent` into the wire model."""
    return NetworkAuditEventResponse(
        id=event.id,
        timestamp=event.timestamp,
        method=event.method,
        url_host=event.url_host,
        url_path_prefix=event.url_path_prefix,
        query_params_stored=bool(event.query_params_stored),
        provider_key=event.provider_key,
        trigger_feature=event.trigger_feature,
        size_bytes_in=event.size_bytes_in,
        size_bytes_out=event.size_bytes_out,
        latency_ms=event.latency_ms,
        status_code=event.status_code,
        user_initiated=event.user_initiated,
        blocked=event.blocked,
        source=event.source,
    )


def _clamp(value: int, lo: int, hi: int) -> int:
    """Clamp ``value`` into the inclusive range ``[lo, hi]``."""
    if value < lo:
        return lo
    if value > hi:
        return hi
    return value


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------


@get("/v1/network-audit/events", sync_to_thread=False)
def list_events(
    limit: int = _EVENTS_DEFAULT_LIMIT,
    provider: str | None = None,
) -> list[dict]:
    """Return the last ``limit`` audit events, newest-first.

    Query params:
      - ``limit``: clamped to ``[1, 500]``. Default 100.
      - ``provider``: optional provider key; when present, filters
        to events from that provider only.

    Returns ``[]`` with 200 when the audit store is unavailable — the
    panel should still render an empty state rather than error out.
    """
    effective_limit = _clamp(int(limit), 1, _EVENTS_MAX_LIMIT)
    store = get_default_store()
    if store is None:
        return []
    # "Privacy panel never 500s" — degrade to empty list on mid-request
    # SQLite failures (corruption, concurrent VACUUM, etc.) rather than
    # surfacing the error. The warning is logged so ops can still see
    # something is wrong.
    try:
        if provider:
            events = store.recent_by_provider(str(provider), effective_limit)
        else:
            events = store.recent(effective_limit)
    except Exception as exc:  # noqa: BLE001
        log.warning("network_audit /events read failed: %s", exc, exc_info=True)
        return []
    return [_event_to_response(ev).model_dump(mode="json") for ev in events]


@get("/v1/network-audit/providers", sync_to_thread=False)
def list_providers() -> list[dict]:
    """Return one status row per known provider (excluding ``unclassified``).

    Each row carries the provider's declarative spec plus three
    live-computed fields: ``blocked`` (current kill-switch state),
    ``events_7d`` (count in the last 7 days), and ``last_call_at``
    (newest event timestamp, or ``None`` if never called).

    The ``unclassified`` fallback entry is filtered out — it exists
    in :data:`KNOWN_PROVIDERS` as a classification catch-all, not as
    a real destination the user can enable or disable.
    """
    store = get_default_store()
    settings = get_default_settings()

    responses: list[dict] = []
    for key, spec in KNOWN_PROVIDERS.items():
        if key == "unclassified":
            continue

        blocked = is_provider_blocked(key, settings)

        # "Privacy panel never 500s" — degrade each provider's
        # live-computed fields to zero/None on SQLite read failure.
        # The provider row still renders with blocked state + spec
        # metadata so the user isn't blocked from flipping a kill
        # switch just because a count query errored.
        if store is None:
            events_7d = 0
            last_call_at: datetime | None = None
        else:
            try:
                events_7d = store.count_recent_by_provider(
                    key, _PROVIDER_WINDOW_7D_SECONDS
                )
                # Fetch just the newest event for this provider to populate
                # last_call_at. Cheap (indexed by provider_key+timestamp).
                latest = store.recent_by_provider(key, limit=1)
                last_call_at = latest[0].timestamp if latest else None
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "network_audit /providers read failed for %s: %s",
                    key,
                    exc,
                    exc_info=True,
                )
                events_7d = 0
                last_call_at = None

        responses.append(
            ProviderStatusResponse(
                key=spec.key,
                display_name=spec.display_name,
                category=spec.category,
                kill_switch_setting_key=spec.kill_switch_setting_key,
                blocked=blocked,
                events_7d=events_7d,
                last_call_at=last_call_at,
            ).model_dump(mode="json")
        )

    return responses


@get("/v1/network-audit/recent-count", sync_to_thread=False)
def recent_count(window: int = _RECENT_COUNT_DEFAULT_WINDOW) -> dict:
    """Return the count of audit events in the last ``window`` seconds.

    Query params:
      - ``window``: clamped to ``[60, 604800]`` (1 min to 7 days).
        Default 300 (matches the panel's "N outbound calls in last 5
        minutes" indicator).

    Shape: ``{"count": int, "window_seconds": int}``. The echoed
    ``window_seconds`` reflects the *clamped* value so the caller can
    re-render the indicator label accurately even if they passed an
    out-of-range input.
    """
    effective_window = _clamp(
        int(window), _RECENT_COUNT_MIN_WINDOW, _RECENT_COUNT_MAX_WINDOW
    )
    store = get_default_store()
    if store is None:
        count = 0
    else:
        # "Privacy panel never 500s" — degrade to zero on read failure.
        try:
            count = store.count_recent(window_seconds=effective_window)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "network_audit /recent-count read failed: %s", exc, exc_info=True
            )
            count = 0
    return RecentCountResponse(
        count=count, window_seconds=effective_window
    ).model_dump(mode="json")


@get("/v1/network-audit/stream")
async def stream_events() -> Stream:
    """SSE stream of new audit events.

    Emits events in chronological order (oldest-first within each
    batch) so the frontend can append them to a scrolling log without
    reordering. Uses SQLite's monotonic ``rowid`` as the stream
    cursor (see :meth:`NetworkAuditStore.events_after`). Polls every
    500 ms; if a poll returns a full batch of ``_SSE_DRAIN_LIMIT``
    rows, immediately polls again without sleeping to drain any
    remaining backlog — so a burst of >limit events between two polls
    cannot silently drop any. Hard cap of 25 minutes per connection
    — clients are expected to reconnect.

    When the store is unavailable, emits a single
    ``{"type": "no_store"}`` frame and closes so the panel can show
    an "audit store unavailable" banner instead of a silent dead
    connection.
    """

    async def _generate() -> AsyncGenerator[bytes, None]:
        started_at = time.monotonic()
        store = get_default_store()
        if store is None:
            yield (
                "data: "
                + json.dumps({"type": "no_store"})
                + "\n\n"
            ).encode()
            return

        # Watermark = last emitted rowid. SQLite's implicit rowid
        # strictly increments on every INSERT, so this is immune to
        # ULID tie-ordering within a single millisecond (the 80-bit
        # random suffix on new_ulid() is not monotonic).
        last_rowid: int = 0
        # Prime to the current max so we only emit events observed
        # AFTER connect. Clients that want historical events hit
        # /events first.
        try:
            last_rowid = store.max_rowid()
        except Exception as exc:  # noqa: BLE001 — audit infra must not crash
            log.debug("network_audit stream prime failed: %s", exc)

        try:
            while True:
                if (
                    time.monotonic() - started_at
                    > _SSE_MAX_DURATION_SECONDS
                ):
                    break
                try:
                    batch = store.events_after(last_rowid, _SSE_DRAIN_LIMIT)
                except RuntimeError:
                    # Store was closed mid-stream (e.g. shutdown during
                    # long-lived connection). Exit rather than burn CPU
                    # hitting the same RuntimeError at 2 Hz for up to
                    # 25 minutes.
                    log.debug("network_audit stream: store closed, exiting")
                    break
                except Exception as exc:  # noqa: BLE001
                    log.debug("network_audit stream tick error: %s", exc)
                    await asyncio.sleep(_SSE_POLL_INTERVAL_SECONDS)
                    continue

                # Batch is chronological (oldest-first) per
                # events_after's contract — emit in order, advancing
                # the watermark per-event so a partial cancel doesn't
                # replay already-delivered events on reconnect.
                for rowid, event in batch:
                    payload = _event_to_response(event).model_dump(
                        mode="json"
                    )
                    payload["type"] = "audit_event"
                    yield (
                        "data: "
                        + json.dumps(payload, default=str)
                        + "\n\n"
                    ).encode()
                    last_rowid = rowid

                # If we drained a full batch, more events may still be
                # queued — loop without sleeping to continue draining.
                # This is what prevents silent drops when a burst of
                # >_SSE_DRAIN_LIMIT events arrives between two polls.
                if len(batch) >= _SSE_DRAIN_LIMIT:
                    continue
                await asyncio.sleep(_SSE_POLL_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            # Litestar cancels the generator on client disconnect.
            # Swallow quietly — there is nothing to flush.
            pass

    return Stream(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = Router(
    path="",
    route_handlers=[
        list_events,
        list_providers,
        recent_count,
        stream_events,
    ],
    tags=["network-audit"],
)
