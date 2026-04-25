"""Tests for ``NewsFeedRepository`` — ADR 0008 schema + retention contract."""

from __future__ import annotations

import time

import pytest

from metis_app.models.comet_event import CometEvent, NewsItem
from metis_app.services.news_feed_repository import (
    CleanupReport,
    NewsFeedRepository,
    get_default_repository,
    reset_default_repository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(
    *,
    title: str = "A title",
    url: str = "https://example.com/a",
    summary: str = "summary",
    channel: str = "rss",
    published_at: float = 1_700_000_000.0,
    fetched_at: float = 1_700_000_100.0,
    raw_metadata: dict[str, object] | None = None,
) -> NewsItem:
    return NewsItem(
        title=title,
        url=url,
        summary=summary,
        source_channel=channel,
        published_at=published_at,
        fetched_at=fetched_at,
        raw_metadata=raw_metadata or {"author": "alice"},
    )


def _make_event(
    item: NewsItem,
    *,
    comet_id: str = "comet_test_001",
    phase: str = "drifting",
    decision: str = "drift",
    classification_score: float = 0.7,
    relevance_score: float = 0.6,
    gap_score: float = 0.4,
    created_at: float = 1_700_000_200.0,
) -> CometEvent:
    return CometEvent(
        comet_id=comet_id,
        news_item=item,
        faculty_id="ml",
        secondary_faculty_id="systems",
        classification_score=classification_score,
        decision=decision,
        relevance_score=relevance_score,
        gap_score=gap_score,
        phase=phase,
        created_at=created_at,
        decided_at=created_at + 5,
    )


# ---------------------------------------------------------------------------
# Schema + idempotent init
# ---------------------------------------------------------------------------


def test_init_db_is_idempotent_and_lazy() -> None:
    repo = NewsFeedRepository(":memory:")
    repo.init_db()
    repo.init_db()  # second call is a no-op

    # Triggering a transaction also initialises lazily on a fresh repo.
    fresh = NewsFeedRepository(":memory:")
    fresh.add_news_items([])  # vacuous insert
    assert fresh.list_known_hashes() == []


def test_compute_item_hash_matches_news_ingest_algorithm() -> None:
    # The repository must use the same algorithm
    # NewsIngestService._item_hash uses so the in-memory LRU cache and
    # the persisted dedup agree.
    h = NewsFeedRepository.compute_item_hash("Hello WORLD", "https://Example.com/A")
    assert len(h) == 16
    assert h == NewsFeedRepository.compute_item_hash("hello world", "https://example.com/a")
    assert h != NewsFeedRepository.compute_item_hash("hello world", "https://example.com/b")


# ---------------------------------------------------------------------------
# news_items insert + dedup
# ---------------------------------------------------------------------------


def test_add_news_items_dedups_on_conflict() -> None:
    repo = NewsFeedRepository(":memory:")
    item = _make_item()

    inserted = repo.add_news_items([item])
    assert len(inserted) == 1
    assert inserted[0].url == item.url

    # Re-inserting the same hash is silent.
    again = repo.add_news_items([item])
    assert again == []
    assert len(repo.list_known_hashes()) == 1


def test_add_news_items_skips_blank_title_or_url() -> None:
    repo = NewsFeedRepository(":memory:")
    inserted = repo.add_news_items(
        [
            _make_item(title="", url="https://example.com/a"),
            _make_item(title="ok", url=""),
            _make_item(title="ok", url="https://example.com/b"),
        ]
    )
    assert len(inserted) == 1
    assert inserted[0].url == "https://example.com/b"


def test_list_known_hashes_returns_newest_first() -> None:
    repo = NewsFeedRepository(":memory:")
    older = _make_item(title="Older", url="https://example.com/older", fetched_at=100.0)
    newer = _make_item(title="Newer", url="https://example.com/newer", fetched_at=200.0)
    repo.add_news_items([older, newer])

    hashes = repo.list_known_hashes()
    assert len(hashes) == 2
    expected_first = NewsFeedRepository.compute_item_hash("Newer", "https://example.com/newer")
    assert hashes[0] == expected_first


# ---------------------------------------------------------------------------
# comet_events
# ---------------------------------------------------------------------------


def test_record_comet_round_trips_news_item_and_metadata() -> None:
    repo = NewsFeedRepository(":memory:")
    item = _make_item(raw_metadata={"upvotes": 42, "section": "science"})
    event = _make_event(item)

    inserted = repo.record_comet(event)
    assert inserted is True

    # Recording the same comet_id again is a no-op.
    again = repo.record_comet(event)
    assert again is False

    fetched = repo.get_comet(event.comet_id)
    assert fetched is not None
    assert fetched.comet_id == event.comet_id
    assert fetched.faculty_id == event.faculty_id
    assert fetched.classification_score == pytest.approx(event.classification_score)
    assert fetched.news_item.title == item.title
    assert fetched.news_item.summary == item.summary
    assert fetched.news_item.raw_metadata == {"upvotes": 42, "section": "science"}


def test_list_active_excludes_terminal_phases() -> None:
    repo = NewsFeedRepository(":memory:")
    drifting = _make_event(
        _make_item(title="A", url="https://example.com/a"),
        comet_id="c_drifting",
        phase="drifting",
        created_at=200.0,
    )
    absorbed = _make_event(
        _make_item(title="B", url="https://example.com/b"),
        comet_id="c_absorbed",
        phase="absorbed",
        created_at=100.0,
    )
    dismissed = _make_event(
        _make_item(title="C", url="https://example.com/c"),
        comet_id="c_dismissed",
        phase="dismissed",
        created_at=50.0,
    )
    for ev in (drifting, absorbed, dismissed):
        repo.record_comet(ev)

    active = repo.list_active()
    assert [c.comet_id for c in active] == ["c_drifting"]
    assert repo.list_active_count() == 1


def test_update_phase_persists_notes_and_atlas_link() -> None:
    repo = NewsFeedRepository(":memory:")
    event = _make_event(_make_item(), comet_id="c_to_absorb", phase="drifting")
    repo.record_comet(event)

    updated = repo.update_phase(
        "c_to_absorb",
        "absorbed",
        notes="user marked as relevant",
        absorbed_at=1_700_000_900.0,
        atlas_entry_id="atlas_xyz",
    )
    assert updated is not None
    assert updated.phase == "absorbed"
    assert updated.absorbed_at == pytest.approx(1_700_000_900.0)

    refetched = repo.get_comet("c_to_absorb")
    assert refetched is not None
    assert refetched.phase == "absorbed"


def test_update_phase_unknown_comet_returns_none() -> None:
    repo = NewsFeedRepository(":memory:")
    assert repo.update_phase("c_missing", "fading") is None


# ---------------------------------------------------------------------------
# feed_cursors
# ---------------------------------------------------------------------------


def test_get_cursor_returns_none_for_unknown_source() -> None:
    repo = NewsFeedRepository(":memory:")
    assert repo.get_cursor("rss", "https://example.com/feed.xml") is None


def test_update_cursor_round_trips_and_partial_updates_preserve_other_fields() -> None:
    repo = NewsFeedRepository(":memory:")
    repo.update_cursor(
        "rss",
        "https://example.com/feed.xml",
        last_polled_at=100.0,
        last_success_at=99.0,
        last_item_hash="aaaaaaaaaaaaaaaa",
        failure_count=0,
        paused_until=0.0,
    )

    repo.update_cursor(
        "rss",
        "https://example.com/feed.xml",
        last_polled_at=200.0,
        # Other fields omitted; should not clobber.
    )

    cur = repo.get_cursor("rss", "https://example.com/feed.xml")
    assert cur is not None
    assert cur.last_polled_at == pytest.approx(200.0)
    assert cur.last_success_at == pytest.approx(99.0)
    assert cur.last_item_hash == "aaaaaaaaaaaaaaaa"


# ---------------------------------------------------------------------------
# Cleanup contract (ADR 0008 §4)
# ---------------------------------------------------------------------------


def test_cleanup_does_not_evict_active_news_items() -> None:
    repo = NewsFeedRepository(":memory:")
    # An old (40-day-old) item that an active comet still references.
    old_active_item = _make_item(
        title="Stale-but-live",
        url="https://example.com/live",
        fetched_at=time.time() - 40 * 86_400,
    )
    repo.record_comet(
        _make_event(old_active_item, comet_id="c_active", phase="approaching"),
    )

    report = repo.cleanup(retention_days=14, max_rows=50_000)
    assert isinstance(report, CleanupReport)
    assert report.news_items_evicted == 0
    assert report.comet_events_evicted == 0

    # The live comet survives — phase guard worked.
    assert repo.list_active_count() == 1
    assert len(repo.list_known_hashes()) == 1


def test_cleanup_evicts_aged_news_items_without_active_comet() -> None:
    repo = NewsFeedRepository(":memory:")
    old_item = _make_item(
        title="Old",
        url="https://example.com/old",
        fetched_at=time.time() - 30 * 86_400,
    )
    fresh_item = _make_item(
        title="Fresh",
        url="https://example.com/fresh",
        fetched_at=time.time(),
    )
    repo.add_news_items([old_item, fresh_item])

    report = repo.cleanup(retention_days=14)
    assert report.news_items_evicted == 1

    remaining = repo.list_known_hashes()
    assert len(remaining) == 1
    assert remaining[0] == NewsFeedRepository.compute_item_hash(
        fresh_item.title, fresh_item.url
    )


def test_cleanup_evicts_dismissed_and_fading_comets_after_terminal_window() -> None:
    repo = NewsFeedRepository(":memory:")
    now = time.time()
    # Use fetched_at = now so the parent news_items row survives the
    # 14-day window and the test isolates the terminal-comet sweep.
    repo.record_comet(
        _make_event(
            _make_item(
                title="dismissed_old",
                url="https://example.com/x",
                fetched_at=now,
            ),
            comet_id="c_dismissed_old",
            phase="dismissed",
            created_at=now - 10 * 86_400,
        )
    )
    repo.record_comet(
        _make_event(
            _make_item(
                title="fading_old",
                url="https://example.com/y",
                fetched_at=now,
            ),
            comet_id="c_fading_old",
            phase="fading",
            created_at=now - 10 * 86_400,
        )
    )
    repo.record_comet(
        _make_event(
            _make_item(
                title="dismissed_recent",
                url="https://example.com/z",
                fetched_at=now,
            ),
            comet_id="c_dismissed_recent",
            phase="dismissed",
            created_at=now - 1 * 86_400,
        )
    )

    report = repo.cleanup(now=now, terminal_retention_days=7)
    assert report.comet_events_evicted >= 2
    assert repo.get_comet("c_dismissed_old") is None
    assert repo.get_comet("c_fading_old") is None
    assert repo.get_comet("c_dismissed_recent") is not None


def test_cleanup_keeps_linked_absorbed_comets_with_live_atlas_entry() -> None:
    repo = NewsFeedRepository(":memory:")
    now = time.time()
    repo.record_comet(
        _make_event(
            _make_item(title="linked_old", url="https://example.com/lx"),
            comet_id="c_linked",
            phase="absorbed",
            created_at=now - 30 * 86_400,
        )
    )
    repo.update_phase(
        "c_linked",
        "absorbed",
        atlas_entry_id="atlas_alive",
        absorbed_at=now - 29 * 86_400,
    )

    report = repo.cleanup(
        now=now,
        terminal_retention_days=7,
        live_atlas_entry_ids={"atlas_alive"},
    )
    # Linked + still-alive atlas entry: comet survives.
    assert report.comet_events_evicted == 0
    assert repo.get_comet("c_linked") is not None


def test_cleanup_evicts_absorbed_comets_whose_atlas_entry_is_gone() -> None:
    repo = NewsFeedRepository(":memory:")
    now = time.time()
    repo.record_comet(
        _make_event(
            _make_item(title="orphan_old", url="https://example.com/ox"),
            comet_id="c_orphan",
            phase="absorbed",
            created_at=now - 30 * 86_400,
        )
    )
    repo.update_phase(
        "c_orphan",
        "absorbed",
        atlas_entry_id="atlas_gone",
        absorbed_at=now - 29 * 86_400,
    )

    report = repo.cleanup(
        now=now,
        terminal_retention_days=7,
        live_atlas_entry_ids=set(),
    )
    assert report.comet_events_evicted == 1
    assert repo.get_comet("c_orphan") is None


def test_cleanup_terminal_retention_pivots_on_phase_changed_at() -> None:
    """Recently-dismissed comets must survive even if they were
    originally created long ago — Codex P2 from PR #545.

    Previously the cleaner used ``created_at < cutoff`` which would
    evict a long-lived comet the moment it transitioned to terminal,
    because its ``created_at`` was already well past the retention
    window.
    """
    repo = NewsFeedRepository(":memory:")
    now = time.time()

    # An old comet that drifted for 14 days, then dismissed yesterday.
    repo.record_comet(
        _make_event(
            _make_item(
                title="long_drifter",
                url="https://example.com/long",
                fetched_at=now,
            ),
            comet_id="c_long_drifter",
            phase="drifting",
            created_at=now - 14 * 86_400,
        )
    )
    yesterday = now - 1 * 86_400
    repo.update_phase(
        "c_long_drifter",
        "dismissed",
        notes="user dismissed",
        phase_changed_at=yesterday,
    )

    report = repo.cleanup(now=now, terminal_retention_days=7)
    assert report.comet_events_evicted == 0
    assert repo.get_comet("c_long_drifter") is not None

    # Re-dismiss with an old phase_changed_at — should now evict.
    repo.update_phase(
        "c_long_drifter",
        "dismissed",
        phase_changed_at=now - 30 * 86_400,
    )
    report = repo.cleanup(now=now, terminal_retention_days=7)
    assert report.comet_events_evicted == 1
    assert repo.get_comet("c_long_drifter") is None


def test_cleanup_evicts_unlinked_absorbed_comet_after_terminal_window() -> None:
    repo = NewsFeedRepository(":memory:")
    now = time.time()
    repo.record_comet(
        _make_event(
            _make_item(title="absorbed_unlinked", url="https://example.com/au"),
            comet_id="c_unlinked",
            phase="absorbed",
            created_at=now - 30 * 86_400,
        )
    )
    # Bump phase_changed_at to 29 days ago so the orphan-absorbed
    # sweep sees a comet outside the 7-day terminal window.
    repo.update_phase(
        "c_unlinked",
        "absorbed",
        absorbed_at=now - 29 * 86_400,
        phase_changed_at=now - 29 * 86_400,
    )

    report = repo.cleanup(now=now, terminal_retention_days=7)
    assert report.comet_events_evicted == 1
    assert repo.get_comet("c_unlinked") is None


def test_cleanup_max_rows_evicts_oldest_excluding_active() -> None:
    repo = NewsFeedRepository(":memory:")
    now = time.time()
    # 5 items: 3 of them attached to active comets, 2 plain rows.
    for i in range(3):
        item = _make_item(
            title=f"active-{i}",
            url=f"https://example.com/active/{i}",
            fetched_at=now - i,
        )
        repo.record_comet(
            _make_event(item, comet_id=f"c_active_{i}", phase="drifting"),
        )
    for i in range(2):
        repo.add_news_items(
            [
                _make_item(
                    title=f"plain-{i}",
                    url=f"https://example.com/plain/{i}",
                    fetched_at=now - 100 - i,
                )
            ]
        )

    assert len(repo.list_known_hashes()) == 5

    report = repo.cleanup(now=now, retention_days=10_000, max_rows=4)
    # Only the plain rows (no active comet) are eligible for the
    # max-rows sweep. The cap is 4, so 1 plain row goes.
    assert report.news_items_evicted == 1
    assert repo.list_active_count() == 3


# ---------------------------------------------------------------------------
# Default singleton helpers
# ---------------------------------------------------------------------------


def test_get_default_repository_singleton_and_reset() -> None:
    reset_default_repository(NewsFeedRepository(":memory:"))
    a = get_default_repository()
    b = get_default_repository()
    assert a is b

    reset_default_repository(None)
    c = get_default_repository(":memory:")
    assert c is not a
    reset_default_repository(None)
