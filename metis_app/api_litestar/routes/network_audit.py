"""Litestar routes for the M17 Network Audit panel (Phases 5a + 6 + 7).

Exposes five read-only GET endpoints and one write endpoint under
``/v1/network-audit/``:

- ``/events`` — paginated tail of recorded audit events (newest-first).
- ``/providers`` — per-provider status rows for the privacy panel's
  provider matrix (kill-switch state, 7-day call counts, last-call
  timestamps).
- ``/recent-count`` — count of events in a time window (powers the
  "N outbound calls in last 5 minutes" indicator at the top of the
  panel).
- ``/stream`` — SSE stream of new events for the live feed.
- ``/export`` — Phase 7 CSV export of the last ``days`` (default 30,
  clamped 1..90) of audit events. Streamed row-by-row; served
  locally; never uploads anywhere.
- ``POST /synthetic-pass`` — Phase 6 "prove offline" litmus test.
  Exercises each registered provider once (synthetically — no real
  network) and returns per-provider call counts. With airplane mode
  on every count is zero.

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
import csv
import io
import json
import logging
import time
from collections.abc import AsyncGenerator, Iterator
from datetime import datetime, timezone
from typing import Any

from litestar import Router, get, post
from litestar.response import Stream
from pydantic import BaseModel

from metis_app.network_audit.events import NetworkAuditEvent
from metis_app.network_audit.kill_switches import (
    AIRPLANE_MODE_KEY,
    is_provider_blocked,
)
from metis_app.network_audit.providers import KNOWN_PROVIDERS
from metis_app.network_audit.runtime import (
    get_default_settings,
    get_default_store,
)
from metis_app.network_audit.store import new_ulid

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

# Phase 7 /export — inclusive day range. The store's rolling retention
# caps physical history at 30 days by default, so ``days > 30`` returns
# whatever survives (usually 30). The upper bound is still 90 so a
# future retention-policy bump doesn't silently cap exports, and it
# bounds the cutoff-ms math without a surprise overflow.
_EXPORT_DAYS_DEFAULT = 30
_EXPORT_DAYS_MIN = 1
_EXPORT_DAYS_MAX = 90
# CSV column order — mirrors the store columns, skipping ``id`` and the
# hard-coded ``query_params_stored`` invariant (always ``False``;
# carrying it into the export would add noise without information).
# Keep this list in sync with ``_csv_row_for_event`` below if either
# changes.
_EXPORT_COLUMNS: tuple[str, ...] = (
    "timestamp",
    "method",
    "url_host",
    "url_path_prefix",
    "provider_key",
    "trigger_feature",
    "size_bytes_in",
    "size_bytes_out",
    "latency_ms",
    "status_code",
    "user_initiated",
    "blocked",
    "source",
)


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


class SyntheticProviderResult(BaseModel):
    """One provider's result row in the synthetic-pass response."""

    provider_key: str
    display_name: str
    category: str
    attempted: bool
    """``True`` iff the probe tried to emit a synthetic event for this
    provider. ``False`` when the kill switch blocked it — the point of
    the litmus test is that airplane mode prevents emission entirely.
    """
    blocked: bool
    """``True`` iff the kill switch is currently blocking this provider."""
    actual_calls: int
    """Count of audit events recorded under ``provider_key`` during
    the probe window (``rowid > start_rowid``). With airplane mode
    on this MUST be ``0`` for every provider — the "prove offline"
    invariant the panel is built to advertise.
    """
    error: str | None
    """Short human-readable error message if anything went wrong for
    this provider, otherwise ``None``."""


class SyntheticPassResponse(BaseModel):
    """Wire shape for the ``POST /synthetic-pass`` endpoint."""

    duration_ms: int
    airplane_mode: bool
    providers: list[SyntheticProviderResult]


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
# CSV export (Phase 7 — disclosure / portability)
# ---------------------------------------------------------------------------


def _csv_row_for_event(event: Any) -> tuple[Any, ...]:
    """Project a :class:`NetworkAuditEvent` into a CSV row tuple.

    Column order matches :data:`_EXPORT_COLUMNS`. Timestamps are
    emitted as ISO-8601 with timezone (UTC) so the CSV is
    round-trippable back through ``datetime.fromisoformat``. Booleans
    are serialised as ``"true"``/``"false"`` for readability in
    spreadsheets (Python's default ``True``/``False`` also works but
    is inconsistent with most vendor CSV exports).

    Keep in sync with :data:`_EXPORT_COLUMNS` — any reorder or addition
    must touch both.
    """
    return (
        event.timestamp.isoformat(),
        event.method,
        event.url_host,
        event.url_path_prefix,
        event.provider_key,
        event.trigger_feature,
        "" if event.size_bytes_in is None else event.size_bytes_in,
        "" if event.size_bytes_out is None else event.size_bytes_out,
        "" if event.latency_ms is None else event.latency_ms,
        "" if event.status_code is None else event.status_code,
        "true" if event.user_initiated else "false",
        "true" if event.blocked else "false",
        event.source,
    )


def _iter_csv_rows(store: Any, cutoff_ms: int) -> Iterator[bytes]:
    """Yield CSV-encoded bytes chunks for every event since ``cutoff_ms``.

    Writes the header row first, then streams event rows out of the
    store's chunked generator. Encoding is UTF-8; row separator is
    ``\\r\\n`` (CSV standard — Excel and Google Sheets both prefer it
    and LibreOffice accepts it). No BOM — modern tools handle UTF-8
    without one, and emitting a BOM confuses some Unix pipelines.

    Each yield flushes one CSV row, so the HTTP response streams
    incrementally even for the worst-case ~50k-row retention cap.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(_EXPORT_COLUMNS)
    yield buffer.getvalue().encode("utf-8")
    buffer.seek(0)
    buffer.truncate(0)

    # ``iter_events_since`` raises RuntimeError if the store is closed
    # mid-iteration; we let that propagate — the Litestar Stream will
    # terminate and the client sees a truncated CSV, which is the
    # honest signal that something went wrong. Partial CSV is better
    # than a silent zero-byte download.
    for event in store.iter_events_since(cutoff_ms):
        writer.writerow(_csv_row_for_event(event))
        yield buffer.getvalue().encode("utf-8")
        buffer.seek(0)
        buffer.truncate(0)


@get("/v1/network-audit/export", sync_to_thread=True)
def export_csv(days: int = _EXPORT_DAYS_DEFAULT) -> Stream:
    """Stream the last ``days`` days of audit events as CSV.

    Query params:
      - ``days``: clamped to ``[1, 90]``. Default 30. Values outside
        the range are clamped silently (no 400 — the privacy panel
        has a "never error" posture and the user just gets a sensible
        export).

    Response headers set ``Content-Type: text/csv; charset=utf-8``
    and a ``Content-Disposition`` attachment so the browser triggers a
    download. The filename embeds the effective day count and a UTC
    timestamp so repeated exports don't overwrite each other in the
    Downloads folder.

    Graceful degradation: if the audit store is unavailable the
    endpoint still returns 200 OK with a header-only CSV (single row
    of column names, no data). A 500 would break the panel's "never
    errors" contract.

    This endpoint intentionally streams row-by-row rather than
    buffering — the store's 30-day / 50k-event rolling cap is small
    enough to fit in memory, but streaming costs nothing extra and
    keeps peak RSS flat if the cap is ever raised.
    """
    effective_days = _clamp(int(days), _EXPORT_DAYS_MIN, _EXPORT_DAYS_MAX)
    cutoff_ms = int(
        (time.time() - float(effective_days) * 86400.0) * 1000
    )

    store = get_default_store()
    generated_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"metis-network-audit-{effective_days}d-{generated_at}.csv"
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        # Cache-busting: the export is a live query result, never
        # suitable for a stale cache hit.
        "Cache-Control": "no-store",
    }

    if store is None:
        # Header-only CSV — gives the browser a valid download that
        # documents the columns even when the audit store isn't
        # available. The panel never 500s.
        header_buffer = io.StringIO()
        csv.writer(header_buffer, lineterminator="\r\n").writerow(
            _EXPORT_COLUMNS
        )

        def _header_only() -> Iterator[bytes]:
            yield header_buffer.getvalue().encode("utf-8")

        return Stream(
            _header_only(),
            media_type="text/csv; charset=utf-8",
            headers=headers,
        )

    return Stream(
        _iter_csv_rows(store, cutoff_ms),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )


# ---------------------------------------------------------------------------
# Synthetic-pass probe (Phase 6 — prove offline)
# ---------------------------------------------------------------------------

# Declared ``url_host`` / ``url_path_prefix`` pairs for each provider
# key the synthetic-pass probe exercises. These match the vendor-SDK
# "intent-level" labels the Phase 4 wrappers use (see
# ``metis_app.network_audit.sdk_events``) so a synthetic event sits
# alongside real events in the feed without looking out of place. The
# path prefix is a coarse label, not a real endpoint — the probe never
# touches the wire.
_SYNTHETIC_PROBE_HOSTS: dict[str, tuple[str, str, str]] = {
    # key: (url_host, url_path_prefix, source)
    # LLM providers — mirror the Phase 4 sdk_events defaults.
    "openai": ("api.openai.com", "/chat", "sdk_invocation"),
    "anthropic": ("api.anthropic.com", "/messages", "sdk_invocation"),
    "google": ("generativelanguage.googleapis.com", "/v1beta", "sdk_invocation"),
    "xai": ("api.x.ai", "/v1", "sdk_invocation"),
    "local_lm_studio": ("localhost", "/v1", "sdk_invocation"),
    # Embedding providers.
    "openai_embeddings": ("api.openai.com", "/embeddings", "sdk_invocation"),
    "google_embeddings": (
        "generativelanguage.googleapis.com",
        "/v1beta",
        "sdk_invocation",
    ),
    "voyage": ("api.voyageai.com", "/v1", "sdk_invocation"),
    "huggingface_local": ("localhost", "/", "sdk_invocation"),
    # Search providers.
    "duckduckgo": ("api.duckduckgo.com", "/", "stdlib_urlopen"),
    "jina_reader": ("r.jina.ai", "/", "stdlib_urlopen"),
    "tavily": ("api.tavily.com", "/search", "sdk_invocation"),
    # Ingestion providers (stdlib path).
    "rss_feed": ("example.com", "/feed", "stdlib_urlopen"),
    "hackernews_api": (
        "hacker-news.firebaseio.com",
        "/v0",
        "stdlib_urlopen",
    ),
    "reddit_api": ("www.reddit.com", "/r", "stdlib_urlopen"),
    # Model hub.
    "huggingface_hub": ("huggingface.co", "/api", "stdlib_urlopen"),
    # Vector DB — weaviate_url may be any host; use the declared pattern.
    "weaviate": ("weaviate.local", "/v1", "stdlib_urlopen"),
    # Other / stdlib.
    "nyx_registry": ("nyxui.com", "/", "stdlib_urlopen"),
    # Fonts CDN.
    "google_fonts": ("fonts.googleapis.com", "/css2", "stdlib_urlopen"),
}

# Cross-module contract: the frontend audit-panel filters events out of
# the "real traffic" feed by ``trigger_feature == "synthetic_pass"``.
# Synthetic events are visible in ``/v1/network-audit/events`` and the
# SSE stream by design (so the user can inspect them after a probe),
# but they must not pollute the default live-feed view. If this literal
# changes, the web client's filter at
# ``apps/metis-web/app/settings/privacy/page.tsx`` must change in lockstep.
_SYNTHETIC_TRIGGER_FEATURE = "synthetic_pass"


def _emit_synthetic_event(
    store: Any, provider_key: str, source: str, url_host: str, url_path_prefix: str
) -> None:
    """Synthesise a single ``trigger_feature="synthetic_pass"`` event.

    Goes directly through ``store.append`` rather than
    :func:`audited_urlopen` or :func:`audit_sdk_call` — both of those
    would (a) perform a real kill-switch check (we have already made
    that decision at the caller) and (b) for the stdlib path, actually
    attempt to open the URL. The probe's job is to exercise the
    audit-emission path, not the wire.
    """
    store.append(
        NetworkAuditEvent(
            id=new_ulid(),
            timestamp=datetime.now(timezone.utc),
            method="GET",
            url_host=url_host,
            url_path_prefix=url_path_prefix,
            query_params_stored=False,
            provider_key=provider_key,
            trigger_feature=_SYNTHETIC_TRIGGER_FEATURE,
            size_bytes_in=None,
            size_bytes_out=None,
            latency_ms=0,
            status_code=None,
            user_initiated=False,
            blocked=False,
            source=source,  # type: ignore[arg-type]
        )
    )


@post("/v1/network-audit/synthetic-pass", status_code=200, sync_to_thread=False)
def synthetic_pass() -> dict:
    """Run a scripted probe over every known provider and return the counts.

    Phase 6 "prove offline" litmus test. For each provider in
    :data:`KNOWN_PROVIDERS` (skipping ``unclassified``):

    1. Consult :func:`is_provider_blocked`. If blocked: mark
       ``attempted=False, blocked=True, actual_calls=0`` and move on —
       crucially, do NOT synthesise an event. The whole point is that
       a blocked provider generates zero audit rows.
    2. Otherwise: synthesise one ``trigger_feature="synthetic_pass"``
       event directly via ``store.append`` (never via the real wrapper
       — that would attempt the network) and mark ``attempted=True,
       blocked=False``.

    After the loop, re-query the store for events with
    ``rowid > start_rowid`` grouped by ``provider_key`` — that's the
    authoritative ``actual_calls`` count. Using the rowid delta means
    the count reflects what SQLite actually wrote, not what we think
    we wrote, so a disk-full store with the same provider listed as
    ``attempted=True, actual_calls=0`` honestly signals silent drop.

    The plan's 30-second budget is a MAXIMUM, not a target. Synthetic
    probes are near-instant; ``duration_ms`` is real wall-clock.

    Graceful degradation: if the audit store is unavailable the route
    returns ``providers: []``, ``duration_ms: 0``, and the current
    airplane-mode flag with 200 OK. Privacy panel must not 500.
    """
    started_at = time.perf_counter()
    settings = get_default_settings()
    airplane_mode = settings.get(AIRPLANE_MODE_KEY) is True

    store = get_default_store()
    if store is None:
        return SyntheticPassResponse(
            duration_ms=0,
            airplane_mode=airplane_mode,
            providers=[],
        ).model_dump(mode="json")

    # Record the watermark BEFORE any probe writes so events_after()
    # returns exactly the rows produced by this pass.
    try:
        start_rowid = store.max_rowid()
    except Exception as exc:  # noqa: BLE001 — audit infra must not 500
        log.warning(
            "network_audit /synthetic-pass max_rowid failed: %s", exc, exc_info=True
        )
        return SyntheticPassResponse(
            duration_ms=int((time.perf_counter() - started_at) * 1000),
            airplane_mode=airplane_mode,
            providers=[],
        ).model_dump(mode="json")

    # Per-provider bookkeeping. Ordered dict preserves KNOWN_PROVIDERS
    # iteration order so the response is deterministic.
    results: list[dict[str, Any]] = []
    for key, spec in KNOWN_PROVIDERS.items():
        if key == "unclassified":
            continue

        blocked = is_provider_blocked(key, settings)
        error: str | None = None
        attempted = False

        if not blocked:
            probe = _SYNTHETIC_PROBE_HOSTS.get(key)
            if probe is None:
                # Provider is registered but has no declared synthetic
                # host. Skip emission, flag the result with an error so
                # the panel can prompt us to add the entry above.
                error = "no synthetic probe host registered"
            else:
                url_host, url_path_prefix, source = probe
                try:
                    _emit_synthetic_event(
                        store,
                        provider_key=key,
                        source=source,
                        url_host=url_host,
                        url_path_prefix=url_path_prefix,
                    )
                    attempted = True
                except Exception as exc:  # noqa: BLE001 — degrade per-provider
                    log.warning(
                        "network_audit /synthetic-pass emit failed for %s: %s",
                        key,
                        exc,
                        exc_info=True,
                    )
                    error = f"synthetic emit failed: {exc}"

        results.append(
            {
                "provider_key": spec.key,
                "display_name": spec.display_name,
                "category": spec.category,
                "attempted": attempted,
                "blocked": blocked,
                "actual_calls": 0,  # filled in below from the rowid delta
                "error": error,
            }
        )

    # Count events emitted during the probe window, grouped by
    # provider_key. This is the authoritative source for
    # ``actual_calls`` — if a write silently dropped we want to show
    # the zero honestly.
    provider_counts: dict[str, int] = {}
    try:
        # Drain in chunks until a partial batch, matching the SSE
        # drain pattern. We use a generous per-chunk cap; synthetic
        # passes produce at most one event per registered provider so
        # a single round-trip is the expected shape.
        cursor_rowid = start_rowid
        chunk_limit = max(len(_SYNTHETIC_PROBE_HOSTS) * 2, 64)
        while True:
            batch = store.events_after(cursor_rowid, chunk_limit)
            if not batch:
                break
            for rowid, event in batch:
                if event.trigger_feature == _SYNTHETIC_TRIGGER_FEATURE:
                    provider_counts[event.provider_key] = (
                        provider_counts.get(event.provider_key, 0) + 1
                    )
                cursor_rowid = rowid
            if len(batch) < chunk_limit:
                break
    except Exception as exc:  # noqa: BLE001 — degrade to zero counts
        log.warning(
            "network_audit /synthetic-pass count query failed: %s",
            exc,
            exc_info=True,
        )

    for row in results:
        row["actual_calls"] = provider_counts.get(row["provider_key"], 0)

    duration_ms = int((time.perf_counter() - started_at) * 1000)
    return SyntheticPassResponse(
        duration_ms=duration_ms,
        airplane_mode=airplane_mode,
        providers=[SyntheticProviderResult(**row) for row in results],
    ).model_dump(mode="json")


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
        export_csv,
        synthetic_pass,
    ],
    tags=["network-audit"],
)
