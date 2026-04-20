"""Tests for ``metis_app.network_audit.store`` (Phase 2 of M17).

Covers the SQLite-backed rolling event store: round-trip fidelity,
ordering, provider-scoped reads, the time-window count query,
retention (row-cap and age-cap), ULID uniqueness, and idempotent
close. See ``docs/adr/0011-network-audit-retention.md``.
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from metis_app.network_audit import NetworkAuditEvent, NetworkAuditStore
from metis_app.network_audit.store import make_synthetic_event, new_ulid


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Return an ephemeral DB path under pytest's ``tmp_path``."""
    return tmp_path / "audit.db"


# ---------------------------------------------------------------------------
# Round trip + ordering
# ---------------------------------------------------------------------------


def test_round_trip_single_event(tmp_db: Path) -> None:
    """Append then recent() returns the same event, all fields equal."""
    store = NetworkAuditStore(tmp_db)
    try:
        original = make_synthetic_event(
            provider_key="openai",
            trigger_feature="unit_test",
            method="POST",
            url_host="api.openai.com",
            url_path_prefix="/v1",
            size_bytes_in=1234,
            size_bytes_out=567,
            latency_ms=42,
            status_code=200,
            user_initiated=True,
            blocked=False,
        )
        store.append(original)
        events = store.recent(limit=1)
        assert len(events) == 1
        fetched = events[0]
        assert fetched.id == original.id
        assert fetched.method == "POST"
        assert fetched.url_host == "api.openai.com"
        assert fetched.url_path_prefix == "/v1"
        assert fetched.query_params_stored is False
        assert fetched.provider_key == "openai"
        assert fetched.trigger_feature == "unit_test"
        assert fetched.size_bytes_in == 1234
        assert fetched.size_bytes_out == 567
        assert fetched.latency_ms == 42
        assert fetched.status_code == 200
        assert fetched.user_initiated is True
        assert fetched.blocked is False
        # Timestamp round-trips to the millisecond.
        assert abs(
            (fetched.timestamp - original.timestamp).total_seconds()
        ) < 0.002
    finally:
        store.close()


def test_recent_limit_is_respected(tmp_db: Path) -> None:
    """``recent(limit=N)`` returns at most N rows."""
    with NetworkAuditStore(tmp_db) as store:
        for _ in range(10):
            store.append(make_synthetic_event())
        assert len(store.recent(limit=3)) == 3
        assert len(store.recent(limit=100)) == 10


def test_recent_is_newest_first(tmp_db: Path) -> None:
    """Events come back in descending timestamp order."""
    base = datetime(2026, 4, 19, 12, 0, 0, tzinfo=timezone.utc)
    with NetworkAuditStore(tmp_db) as store:
        store.append(make_synthetic_event(timestamp=base, event_id=new_ulid()))
        store.append(
            make_synthetic_event(
                timestamp=base + timedelta(seconds=10), event_id=new_ulid()
            ),
        )
        store.append(
            make_synthetic_event(
                timestamp=base + timedelta(seconds=20), event_id=new_ulid()
            ),
        )
        events = store.recent(limit=10)
        assert len(events) == 3
        timestamps = [event.timestamp for event in events]
        assert timestamps == sorted(timestamps, reverse=True)


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def test_recent_by_provider_filters_correctly(tmp_db: Path) -> None:
    """Provider-scoped read returns only matching rows."""
    with NetworkAuditStore(tmp_db) as store:
        for _ in range(3):
            store.append(make_synthetic_event(provider_key="openai"))
        for _ in range(2):
            store.append(make_synthetic_event(provider_key="anthropic"))
        for _ in range(4):
            store.append(make_synthetic_event(provider_key="hackernews_api"))

        openai_events = store.recent_by_provider("openai", limit=100)
        assert len(openai_events) == 3
        assert all(event.provider_key == "openai" for event in openai_events)

        anthropic_events = store.recent_by_provider("anthropic", limit=100)
        assert len(anthropic_events) == 2
        assert all(event.provider_key == "anthropic" for event in anthropic_events)

        # Unknown provider — empty result, not an error.
        assert store.recent_by_provider("nonexistent", limit=100) == []


# ---------------------------------------------------------------------------
# Time-window count
# ---------------------------------------------------------------------------


def test_count_recent_window(tmp_db: Path) -> None:
    """``count_recent`` respects the cutoff."""
    now = datetime.now(timezone.utc)
    with NetworkAuditStore(tmp_db) as store:
        # Five events 10 seconds ago — outside a 5-second window, inside 60.
        old_timestamp = now - timedelta(seconds=10)
        for _ in range(5):
            store.append(
                make_synthetic_event(timestamp=old_timestamp, event_id=new_ulid()),
            )
        assert store.count_recent(window_seconds=5) == 0
        assert store.count_recent(window_seconds=60) == 5

        # One event right now — inside both windows.
        store.append(make_synthetic_event(timestamp=now, event_id=new_ulid()))
        assert store.count_recent(window_seconds=5) == 1
        assert store.count_recent(window_seconds=60) == 6


def test_max_rowid_tracks_inserts(tmp_db: Path) -> None:
    """``max_rowid`` returns 0 for an empty table and rises with inserts.

    Used by the SSE stream to prime its watermark past pre-connect
    history so clients only see events inserted after the connection.
    """
    now = datetime.now(timezone.utc)
    with NetworkAuditStore(tmp_db) as store:
        assert store.max_rowid() == 0
        store.append(make_synthetic_event(timestamp=now, event_id=new_ulid()))
        r1 = store.max_rowid()
        assert r1 >= 1
        store.append(make_synthetic_event(timestamp=now, event_id=new_ulid()))
        r2 = store.max_rowid()
        assert r2 > r1


def test_events_after_drains_in_chronological_order(tmp_db: Path) -> None:
    """``events_after`` returns events with rowid > cursor, oldest-first.

    This is the stream cursor primitive. It must (a) exclude events at
    or before the cursor, (b) return strictly-monotonic rowids, (c)
    order oldest-first so the frontend sees a chronological log.
    """
    now = datetime.now(timezone.utc)
    with NetworkAuditStore(tmp_db) as store:
        # Insert 4 events; capture the rowid after the 2nd.
        for _ in range(2):
            store.append(make_synthetic_event(timestamp=now, event_id=new_ulid()))
        cursor_rowid = store.max_rowid()
        for _ in range(2):
            store.append(make_synthetic_event(timestamp=now, event_id=new_ulid()))

        drained = store.events_after(cursor_rowid, limit=100)
        assert len(drained) == 2
        # Strictly monotonic rowids, oldest first.
        assert drained[0][0] < drained[1][0]
        assert drained[0][0] > cursor_rowid


def test_events_after_never_loses_burst_events_beyond_drain_limit(
    tmp_db: Path,
) -> None:
    """Regression for PR #520 Codex P1: a burst of >limit events between
    two polls must not silently drop events beyond the limit.

    Simulates: client connects at rowid=0 (empty store). Then 120
    events arrive before the next poll. A single SELECT with
    ``limit=50`` would return the 50 oldest; if the SSE loop advanced
    its watermark to the newest of those 50 and queried with that
    cursor next tick, events 51..120 would be silently dropped. The
    fix is to loop-drain: keep querying while the batch is full. This
    test asserts that the drain-all pattern reaches every event.
    """
    now = datetime.now(timezone.utc)
    with NetworkAuditStore(tmp_db) as store:
        total = 120
        for _ in range(total):
            store.append(make_synthetic_event(timestamp=now, event_id=new_ulid()))

        # Simulate the SSE loop: start at rowid 0, drain in chunks of
        # 50 until partial.
        drain_limit = 50
        cursor = 0
        drained_ids: list[str] = []
        while True:
            batch = store.events_after(cursor, limit=drain_limit)
            if not batch:
                break
            drained_ids.extend(event.id for _rowid, event in batch)
            cursor = batch[-1][0]
            if len(batch) < drain_limit:
                break

        assert len(drained_ids) == total, (
            "Drain-all pattern must reach every event past the initial "
            "cursor, not just the first _SSE_DRAIN_LIMIT"
        )
        assert len(set(drained_ids)) == total, "No duplicates"


def test_events_after_monotonic_rowid_immune_to_ulid_tie_disorder(
    tmp_db: Path,
) -> None:
    """Regression for PR #520 Codex P2: same-millisecond events with
    lexicographically disordered IDs must still all appear in
    ``events_after`` strictly after a cursor that includes some of them.

    Constructs three events at the exact same timestamp_ms with IDs
    chosen so that the lex order is NOT the insert order. An id-based
    watermark would classify the second-inserted (lex-smallest) event
    as "already seen" when the cursor = max(ids). The rowid-based
    watermark does not have this problem because rowid is assigned
    monotonically per INSERT regardless of id lex order.
    """
    now = datetime.now(timezone.utc)
    with NetworkAuditStore(tmp_db) as store:
        # Fixed timestamp so all three share the same timestamp_ms.
        ts = now.replace(microsecond=0)
        # Insert events whose IDs are deliberately NOT monotonic:
        # the middle insert has the smallest id lex-wise.
        ids_in_insert_order = [
            "ZZZZZZZZZZZZZZZZZZZZZZZZZZ",  # largest lex
            "00000000000000000000000000",  # smallest lex, inserted 2nd
            "MMMMMMMMMMMMMMMMMMMMMMMMMM",  # middle lex
        ]
        for event_id in ids_in_insert_order:
            store.append(make_synthetic_event(timestamp=ts, event_id=event_id))

        # Cursor = after the first insert's rowid. events_after must
        # return the LAST TWO inserts in insert order, even though the
        # 2nd insert has a lex-smaller id than the cursor's id.
        first_rowid = 1  # SQLite rowid starts at 1 on empty table
        drained = store.events_after(first_rowid, limit=100)
        drained_ids = [event.id for _rowid, event in drained]
        assert drained_ids == [
            "00000000000000000000000000",
            "MMMMMMMMMMMMMMMMMMMMMMMMMM",
        ], "Must return events in INSERT order (rowid), not lex order"


def test_count_recent_by_provider_filters_correctly(tmp_db: Path) -> None:
    """``count_recent_by_provider`` sums only the named provider's events.

    Phase 5a helper. The audit panel's per-provider matrix calls this
    with ``window_seconds=7*86400`` once per row.
    """
    now = datetime.now(timezone.utc)
    with NetworkAuditStore(tmp_db) as store:
        for _ in range(3):
            store.append(
                make_synthetic_event(
                    provider_key="openai", timestamp=now, event_id=new_ulid()
                )
            )
        for _ in range(2):
            store.append(
                make_synthetic_event(
                    provider_key="anthropic",
                    timestamp=now,
                    event_id=new_ulid(),
                )
            )
        # Stale event outside the window — must not be counted.
        store.append(
            make_synthetic_event(
                provider_key="openai",
                timestamp=now - timedelta(seconds=3600),
                event_id=new_ulid(),
            )
        )
        assert store.count_recent_by_provider("openai", window_seconds=60) == 3
        assert (
            store.count_recent_by_provider("anthropic", window_seconds=60) == 2
        )
        # Wider window picks up the stale openai event.
        assert (
            store.count_recent_by_provider("openai", window_seconds=7200) == 4
        )
        # Unknown provider key returns 0, not an error.
        assert (
            store.count_recent_by_provider(
                "definitely_not_a_provider", window_seconds=60
            )
            == 0
        )


# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------


def test_retention_caps_event_count(tmp_db: Path) -> None:
    """With ``max_rows=100``, the store holds at most a handful over the cap.

    Opportunistic eviction kicks in every 100 appends, so after a
    sizeable insert batch the stored count is bounded.
    """
    with NetworkAuditStore(tmp_db, max_rows=100) as store:
        for _ in range(350):
            store.append(make_synthetic_event(event_id=new_ulid()))
        # After three opportunistic evictions, the count sits at max_rows.
        # The eviction check fires every 100 appends, so we may be at
        # max_rows + up-to-99 pending. Force a vacuum for a crisp bound.
        store.vacuum()
        assert len(store.recent(limit=1000)) == 100
        # Now append more and confirm the cap holds after a second vacuum —
        # a bug where eviction trimmed once then let the store grow unbounded
        # would be caught here.
        for _ in range(200):
            store.append(make_synthetic_event(event_id=new_ulid()))
        store.vacuum()
        assert len(store.recent(limit=1000)) == 100


def test_retention_vacuum_removes_over_age(tmp_db: Path) -> None:
    """Events older than ``max_age_seconds`` are evicted by ``vacuum()``."""
    now = datetime.now(timezone.utc)
    with NetworkAuditStore(tmp_db, max_age_seconds=30 * 24 * 3600) as store:
        # 60 days ago — outside the window.
        old = now - timedelta(days=60)
        for _ in range(5):
            store.append(make_synthetic_event(timestamp=old, event_id=new_ulid()))
        # Present.
        for _ in range(3):
            store.append(make_synthetic_event(timestamp=now, event_id=new_ulid()))

        store.vacuum()

        events = store.recent(limit=100)
        assert len(events) == 3
        for event in events:
            # Everything surviving is within the window.
            age_seconds = (now - event.timestamp).total_seconds()
            assert age_seconds < 30 * 24 * 3600


def test_retention_caps_via_explicit_vacuum(tmp_db: Path) -> None:
    """Manual ``vacuum()`` enforces the row cap regardless of append count."""
    with NetworkAuditStore(tmp_db, max_rows=5) as store:
        for _ in range(20):
            store.append(make_synthetic_event(event_id=new_ulid()))
        store.vacuum()
        assert len(store.recent(limit=100)) == 5


# ---------------------------------------------------------------------------
# ULIDs
# ---------------------------------------------------------------------------


def test_ulid_ids_are_unique() -> None:
    """1000 rapidly generated ULIDs are pairwise distinct."""
    ids = {new_ulid() for _ in range(1000)}
    assert len(ids) == 1000


def test_ulid_is_26_chars_and_crockford_alphabet() -> None:
    """Each ULID is 26 chars and drawn from the Crockford base32 alphabet."""
    alphabet = set("0123456789ABCDEFGHJKMNPQRSTVWXYZ")
    for _ in range(50):
        value = new_ulid()
        assert len(value) == 26
        assert set(value) <= alphabet


def test_ulid_timestamp_prefix_is_monotonic() -> None:
    """ULIDs generated at different times compare in creation order."""
    first = new_ulid()
    # Sleep-free: a later ULID is generated after time.time_ns() advances.
    # If the system clock has millisecond granularity we may tie; use a
    # short busy-wait to cross a millisecond boundary.
    import time

    start_ns = time.time_ns()
    while time.time_ns() - start_ns < 2_000_000:
        pass
    second = new_ulid()
    # Timestamp prefix is the first 10 chars.
    assert first[:10] <= second[:10]


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_close_is_idempotent(tmp_db: Path) -> None:
    """Calling close() twice does not raise."""
    store = NetworkAuditStore(tmp_db)
    store.close()
    store.close()  # Must not raise.


def test_appending_after_close_raises(tmp_db: Path) -> None:
    """Operations on a closed store raise cleanly."""
    store = NetworkAuditStore(tmp_db)
    store.close()
    with pytest.raises(RuntimeError, match="closed"):
        store.append(make_synthetic_event())


def test_context_manager_closes_on_exit(tmp_db: Path) -> None:
    """The store is a context manager; exit closes the connection."""
    with NetworkAuditStore(tmp_db) as store:
        store.append(make_synthetic_event())
    with pytest.raises(RuntimeError, match="closed"):
        store.append(make_synthetic_event())


# ---------------------------------------------------------------------------
# Synthetic writer helper
# ---------------------------------------------------------------------------


def test_synthetic_writer_produces_valid_event() -> None:
    """``make_synthetic_event`` returns a well-formed event with defaults."""
    event = make_synthetic_event()
    assert isinstance(event, NetworkAuditEvent)
    assert event.query_params_stored is False
    assert event.timestamp.tzinfo is not None
    assert event.provider_key == "unclassified"
    assert event.trigger_feature == "synthetic_pass"


def test_synthetic_writer_accepts_overrides() -> None:
    """Every field on ``make_synthetic_event`` is overridable."""
    event = make_synthetic_event(
        provider_key="reddit_api",
        trigger_feature="news_comet_worker",
        method="POST",
        url_host="www.reddit.com",
        url_path_prefix="/r",
        size_bytes_in=42,
        size_bytes_out=7,
        latency_ms=100,
        status_code=403,
        user_initiated=True,
        blocked=True,
    )
    assert event.provider_key == "reddit_api"
    assert event.trigger_feature == "news_comet_worker"
    assert event.method == "POST"
    assert event.url_host == "www.reddit.com"
    assert event.url_path_prefix == "/r"
    assert event.size_bytes_in == 42
    assert event.size_bytes_out == 7
    assert event.latency_ms == 100
    assert event.status_code == 403
    assert event.user_initiated is True
    assert event.blocked is True


# ---------------------------------------------------------------------------
# Blocked events are still persisted
# ---------------------------------------------------------------------------


def test_blocked_events_are_persisted(tmp_db: Path) -> None:
    """``blocked=True`` events round-trip — the panel shows what we stopped."""
    with NetworkAuditStore(tmp_db) as store:
        store.append(make_synthetic_event(blocked=True, provider_key="openai"))
        events = store.recent(limit=1)
        assert len(events) == 1
        assert events[0].blocked is True


# ---------------------------------------------------------------------------
# Default DB path fallback — tempfile-driven, no repo pollution
# ---------------------------------------------------------------------------


def test_store_accepts_string_path() -> None:
    """``db_path`` accepts both ``Path`` and ``str``."""
    with tempfile.TemporaryDirectory() as tmp:
        str_path = str(Path(tmp) / "audit.db")
        store = NetworkAuditStore(str_path)
        try:
            store.append(make_synthetic_event())
            assert len(store.recent(limit=1)) == 1
        finally:
            store.close()


# ---------------------------------------------------------------------------
# iter_events_since — Phase 7 CSV export helper
# ---------------------------------------------------------------------------


def test_iter_events_since_filters_by_cutoff(tmp_db: Path) -> None:
    """Events older than ``cutoff_ms`` are filtered out at the SQL layer."""
    now = datetime.now(timezone.utc)
    old = make_synthetic_event(
        provider_key="rss_feed",
        timestamp=now - timedelta(days=10),
    )
    recent = make_synthetic_event(
        provider_key="openai",
        timestamp=now - timedelta(hours=1),
    )
    with NetworkAuditStore(tmp_db) as store:
        store.append(old)
        store.append(recent)
        cutoff_ms = int((now - timedelta(days=5)).timestamp() * 1000)
        rows = list(store.iter_events_since(cutoff_ms))
        keys = {ev.provider_key for ev in rows}
        assert keys == {"openai"}


def test_iter_events_since_chronological_order(tmp_db: Path) -> None:
    """Yielded events come back in chronological (rowid ascending) order."""
    now = datetime.now(timezone.utc)
    events = [
        make_synthetic_event(
            provider_key=f"prov-{i}",
            timestamp=now - timedelta(minutes=10 - i),
        )
        for i in range(5)
    ]
    with NetworkAuditStore(tmp_db) as store:
        for ev in events:
            store.append(ev)
        cutoff_ms = int((now - timedelta(hours=1)).timestamp() * 1000)
        rows = list(store.iter_events_since(cutoff_ms))
        assert len(rows) == 5
        timestamps = [row.timestamp for row in rows]
        assert timestamps == sorted(timestamps)


def test_iter_events_since_chunk_boundary_has_no_gap(tmp_db: Path) -> None:
    """Walker keeps going across chunk boundaries; total count equals insert count."""
    now = datetime.now(timezone.utc)
    with NetworkAuditStore(tmp_db) as store:
        total = 25
        for i in range(total):
            store.append(
                make_synthetic_event(
                    provider_key="openai",
                    timestamp=now - timedelta(seconds=total - i),
                )
            )
        cutoff_ms = int((now - timedelta(hours=1)).timestamp() * 1000)
        # Use a tiny chunk_size to force several SELECT round-trips.
        rows = list(store.iter_events_since(cutoff_ms, chunk_size=4))
        assert len(rows) == total


def test_iter_events_since_empty_window_returns_nothing(tmp_db: Path) -> None:
    """A cutoff in the future yields zero events — the generator terminates cleanly."""
    now = datetime.now(timezone.utc)
    with NetworkAuditStore(tmp_db) as store:
        store.append(make_synthetic_event(provider_key="openai", timestamp=now))
        future_cutoff_ms = int((now + timedelta(days=1)).timestamp() * 1000)
        assert list(store.iter_events_since(future_cutoff_ms)) == []


def test_iter_events_since_rejects_zero_or_negative_chunk_size(tmp_db: Path) -> None:
    """``chunk_size`` below 1 is clamped to 1 (defensive, not a hard error)."""
    now = datetime.now(timezone.utc)
    with NetworkAuditStore(tmp_db) as store:
        store.append(make_synthetic_event(provider_key="openai", timestamp=now))
        cutoff_ms = int((now - timedelta(hours=1)).timestamp() * 1000)
        rows = list(store.iter_events_since(cutoff_ms, chunk_size=0))
        assert len(rows) == 1


def test_iter_events_since_raises_after_close(tmp_db: Path) -> None:
    """Closed store refuses to yield further events rather than hang."""
    store = NetworkAuditStore(tmp_db)
    store.append(make_synthetic_event(provider_key="openai"))
    store.close()
    with pytest.raises(RuntimeError):
        list(store.iter_events_since(0))
