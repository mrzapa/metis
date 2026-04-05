"""Tests for NewsIngestService — RSS parsing, dedup, and classification."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from metis_app.models.comet_event import NewsItem
from metis_app.services.news_ingest_service import (
    NewsIngestService,
    _fetch_hackernews,
    _fetch_reddit,
    _parse_rss_feed,
    _SourceHealth,
)


# ---------------------------------------------------------------------------
# Dedup
# ---------------------------------------------------------------------------


def test_dedup_prevents_duplicate_items():
    svc = NewsIngestService()
    item = NewsItem(
        item_id="dup-1",
        title="Test Article",
        summary="Summary text",
        url="https://example.com/article",
        source_channel="rss",
    )
    result1 = svc._dedup([item])
    result2 = svc._dedup([item])
    assert len(result1) == 1
    assert len(result2) == 0


def test_dedup_allows_different_items():
    svc = NewsIngestService()
    a = NewsItem(item_id="a", title="First", summary="", url="https://a.com", source_channel="rss")
    b = NewsItem(item_id="b", title="Second", summary="", url="https://b.com", source_channel="rss")
    result = svc._dedup([a, b])
    assert len(result) == 2


def test_dedup_caps_seen_set():
    svc = NewsIngestService()
    svc._max_seen = 5
    items = [
        NewsItem(item_id=f"i-{i}", title=f"Title {i}", summary="", url=f"https://e.com/{i}", source_channel="rss")
        for i in range(10)
    ]
    svc._dedup(items)
    # After trimming, seen-set should not exceed max_seen
    assert len(svc._seen_hashes) <= 5


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def test_classify_item_uses_brain_pass_result():
    svc = NewsIngestService()
    item = NewsItem(item_id="c-1", title="Neural plasticity", summary="Brain study", url="https://a.com", source_channel="rss")
    brain_result = MagicMock()
    brain_result.placement = {"faculty_id": "reasoning", "secondary_faculty_id": "", "score": 0.88}
    brain_fn = MagicMock(return_value=brain_result)
    event = svc.classify_item(item, brain_pass_fn=brain_fn)
    assert event.faculty_id == "reasoning"
    assert event.classification_score == 0.88
    brain_fn.assert_called_once()


def test_classify_item_fallback_when_no_brain_pass():
    svc = NewsIngestService()
    item = NewsItem(item_id="c-2", title="Some news", summary="", url="https://b.com", source_channel="rss")
    event = svc.classify_item(item, brain_pass_fn=None)
    assert event.faculty_id == "knowledge"
    assert event.classification_score == 0.1


def test_classify_item_fallback_on_brain_pass_error():
    svc = NewsIngestService()
    item = NewsItem(item_id="c-3", title="Error case", summary="", url="https://c.com", source_channel="rss")
    brain_fn = MagicMock(side_effect=RuntimeError("LLM unavailable"))
    event = svc.classify_item(item, brain_pass_fn=brain_fn)
    assert event.faculty_id == "knowledge"


# ---------------------------------------------------------------------------
# RSS parsing
# ---------------------------------------------------------------------------


def test_parse_rss_feed_handles_empty_response():
    with patch("metis_app.services.news_ingest_service.feedparser") as mock_fp:
        mock_fp.parse.return_value = MagicMock(entries=[])
        items = _parse_rss_feed("https://example.com/rss")
    assert items == []


def test_parse_rss_feed_returns_items():
    mock_entry = MagicMock()
    mock_entry.title = "New Discovery"
    mock_entry.summary = "Scientists discover..."
    mock_entry.link = "https://example.com/1"
    mock_entry.published_parsed = None

    with patch("metis_app.services.news_ingest_service.feedparser") as mock_fp:
        mock_fp.parse.return_value = MagicMock(entries=[mock_entry])
        items = _parse_rss_feed("https://example.com/rss")

    assert len(items) == 1
    assert items[0]["title"] == "New Discovery"


def test_parse_rss_feed_returns_empty_on_missing_feedparser():
    with patch("metis_app.services.news_ingest_service.feedparser", None):
        items = _parse_rss_feed("https://example.com/rss")
    assert items == []


# ---------------------------------------------------------------------------
# Ingest pipeline
# ---------------------------------------------------------------------------


def test_ingest_returns_classified_items():
    svc = NewsIngestService()
    fake_item = NewsItem(
        item_id="ing-1", title="AI Breakthrough", summary="Major advance",
        url="https://news.com/1", source_channel="rss",
    )
    settings = {
        "news_comet_sources": ["rss"],
        "news_comet_rss_feeds": ["https://feed.example.com/rss"],
    }

    with patch.object(svc, "fetch_rss", return_value=[fake_item]):
        results = svc.ingest(settings, brain_pass_fn=None)

    assert len(results) == 1
    assert results[0].news_item.item_id == "ing-1"
    assert results[0].faculty_id == "knowledge"


# ---------------------------------------------------------------------------
# HackerNews fetcher
# ---------------------------------------------------------------------------


def test_fetch_hackernews_returns_stories():
    with patch("metis_app.services.news_ingest_service._safe_get_json") as mock_get:
        mock_get.side_effect = [
            [101, 102],  # top story IDs
            {"type": "story", "title": "Show HN: Cool Tool", "url": "https://cool.dev", "time": 1700000000},
            {"type": "story", "title": "Ask HN: Career advice?", "url": "", "time": 1700000100},
        ]
        items = _fetch_hackernews(limit=2)

    assert len(items) == 2
    assert items[0]["title"] == "Show HN: Cool Tool"
    assert items[0]["url"] == "https://cool.dev"
    # Self-post with no URL should link to HN discussion
    assert "news.ycombinator.com" in items[1]["url"]


def test_fetch_hackernews_handles_api_failure():
    with patch("metis_app.services.news_ingest_service._safe_get_json", return_value=None):
        items = _fetch_hackernews()
    assert items == []


def test_fetch_hackernews_skips_non_stories():
    with patch("metis_app.services.news_ingest_service._safe_get_json") as mock_get:
        mock_get.side_effect = [
            [201, 202],
            {"type": "comment", "text": "Nice!"},
            {"type": "story", "title": "Real Story", "url": "https://real.com", "time": 0},
        ]
        items = _fetch_hackernews(limit=2)
    assert len(items) == 1
    assert items[0]["title"] == "Real Story"


# ---------------------------------------------------------------------------
# Reddit fetcher
# ---------------------------------------------------------------------------


def test_fetch_reddit_returns_posts():
    reddit_resp = {
        "data": {
            "children": [
                {"data": {"title": "TIL something", "url": "https://r.com/1", "selftext": "wow", "created_utc": 1700000000, "stickied": False}},
                {"data": {"title": "Stickied mod post", "url": "https://r.com/2", "selftext": "", "created_utc": 0, "stickied": True}},
            ]
        }
    }
    with patch("metis_app.services.news_ingest_service._safe_get_json", return_value=reddit_resp):
        items = _fetch_reddit(["machinelearning"])
    # Only non-stickied posts
    assert len(items) == 1
    assert items[0]["title"] == "TIL something"


def test_fetch_reddit_handles_api_failure():
    with patch("metis_app.services.news_ingest_service._safe_get_json", return_value=None):
        items = _fetch_reddit(["python"])
    assert items == []


def test_fetch_reddit_sanitises_subreddit_name():
    """Subreddit prefixes like 'r/' and trailing slashes should be stripped."""
    reddit_resp = {"data": {"children": [
        {"data": {"title": "Post", "url": "https://x.com", "selftext": "", "created_utc": 0, "stickied": False}},
    ]}}
    with patch("metis_app.services.news_ingest_service._safe_get_json", return_value=reddit_resp) as mock_get:
        _fetch_reddit(["r/python/"])
    # Should request cleaned-up subreddit name
    call_url = mock_get.call_args[0][0]
    assert "/r/python/" in call_url
    assert "/r/r/" not in call_url


# ---------------------------------------------------------------------------
# Per-source error tracking
# ---------------------------------------------------------------------------


def test_source_health_pauses_after_repeated_failures():
    h = _SourceHealth()
    for _ in range(5):
        h.record_failure()
    assert h.is_paused is True


def test_source_health_resets_on_success():
    h = _SourceHealth()
    for _ in range(4):
        h.record_failure()
    h.record_success()
    assert h.failures == 0
    assert h.is_paused is False


def test_source_health_pause_expires():
    h = _SourceHealth()
    for _ in range(5):
        h.record_failure()
    # Manually expire the pause
    h.paused_until = 0.0
    assert h.is_paused is False


# ---------------------------------------------------------------------------
# Multi-source fetch_all
# ---------------------------------------------------------------------------


def test_fetch_all_includes_hackernews():
    svc = NewsIngestService()
    settings = {"news_comet_sources": ["hackernews"]}
    fake_item = NewsItem(item_id="hn-1", title="HN Story", summary="", url="https://hn.com", source_channel="hackernews")
    with patch.object(svc, "fetch_hackernews", return_value=[fake_item]):
        items = svc.fetch_all(settings)
    assert len(items) == 1
    assert items[0].source_channel == "hackernews"


def test_fetch_all_includes_reddit():
    svc = NewsIngestService()
    settings = {"news_comet_sources": ["reddit"], "news_comet_reddit_subs": ["python"]}
    fake_item = NewsItem(item_id="rd-1", title="Reddit Post", summary="", url="https://reddit.com/1", source_channel="reddit")
    with patch.object(svc, "fetch_reddit", return_value=[fake_item]):
        items = svc.fetch_all(settings)
    assert len(items) == 1
    assert items[0].source_channel == "reddit"


def test_fetch_all_skips_reddit_without_subs():
    svc = NewsIngestService()
    settings = {"news_comet_sources": ["reddit"]}  # no reddit_subs
    with patch.object(svc, "fetch_reddit") as mock_fetch:
        svc.fetch_all(settings)
    mock_fetch.assert_not_called()
