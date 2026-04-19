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
        assert len(store.recent(limit=1000)) <= 100


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
