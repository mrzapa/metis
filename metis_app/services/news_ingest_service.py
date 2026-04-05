"""News ingestion service — fetches news from configured sources, deduplicates, and classifies via brain pass.

Supported source types:
  - rss       — RSS/Atom feeds (requires ``feedparser``)
  - hackernews — HackerNews top stories via Firebase API
  - reddit    — Reddit subreddit hot posts via JSON API
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from metis_app.models.comet_event import CometEvent, NewsItem

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_HTTP_TIMEOUT = 10.0  # seconds for all HTTP fetches
_MAX_BODY_BYTES = 512 * 1024  # 512 KB response cap (SSRF / memory safety)
_MAX_FAILURES_BEFORE_PAUSE = 5  # per-source error threshold
_PAUSE_SECONDS = 600  # 10 min backoff after repeated failures

# ---------------------------------------------------------------------------
# RSS parser (optional dependency)
# ---------------------------------------------------------------------------

try:
    import feedparser  # type: ignore[import-untyped]
except ImportError:
    feedparser = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Safe HTTP helper (ClawFeed-inspired: timeout + size cap + error handling)
# ---------------------------------------------------------------------------

def _safe_get(url: str, *, timeout: float = _HTTP_TIMEOUT) -> bytes | None:
    """Fetch *url* with timeout and response-size cap.  Returns None on error."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "METIS/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.read(_MAX_BODY_BYTES)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log.warning("HTTP fetch failed for %s: %s", url, exc)
        return None


def _safe_get_json(url: str, *, timeout: float = _HTTP_TIMEOUT) -> Any | None:
    """Fetch *url* and parse as JSON.  Returns None on any error."""
    body = _safe_get(url, timeout=timeout)
    if body is None:
        return None
    try:
        return json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning("JSON decode failed for %s: %s", url, exc)
        return None


# ---------------------------------------------------------------------------
# Per-source error tracker (ClawFeed-inspired)
# ---------------------------------------------------------------------------

@dataclass
class _SourceHealth:
    """Track consecutive failures per source channel."""
    failures: int = 0
    paused_until: float = 0.0

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= _MAX_FAILURES_BEFORE_PAUSE:
            self.paused_until = time.time() + _PAUSE_SECONDS
            log.warning("Source paused for %ds after %d consecutive failures", _PAUSE_SECONDS, self.failures)

    def record_success(self) -> None:
        self.failures = 0
        self.paused_until = 0.0

    @property
    def is_paused(self) -> bool:
        if self.paused_until <= 0:
            return False
        if time.time() >= self.paused_until:
            # Pause expired — reset
            self.failures = 0
            self.paused_until = 0.0
            return False
        return True


def _parse_rss_feed(url: str, *, timeout: float = _HTTP_TIMEOUT) -> list[dict[str, Any]]:
    """Fetch and parse an RSS/Atom feed, returning a list of entry dicts.

    Requires ``feedparser`` — returns an empty list if not installed.
    """
    if feedparser is None:
        log.warning("feedparser not installed — RSS source disabled (pip install feedparser)")
        return []

    try:
        feed = feedparser.parse(url)
    except Exception as exc:
        log.warning("Failed to parse RSS feed %s: %s", url, exc)
        return []

    items: list[dict[str, Any]] = []
    for entry in feed.entries[:20]:  # cap per feed
        published = 0.0
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published = time.mktime(entry.published_parsed)
        items.append({
            "title": getattr(entry, "title", ""),
            "summary": getattr(entry, "summary", "")[:500],
            "url": getattr(entry, "link", ""),
            "published_at": published,
        })
    return items


# ---------------------------------------------------------------------------
# HackerNews fetcher (Firebase API — no auth required)
# ---------------------------------------------------------------------------

_HN_TOP_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
_HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"


def _fetch_hackernews(*, limit: int = 15) -> list[dict[str, Any]]:
    """Fetch top HackerNews stories via the public Firebase API."""
    story_ids = _safe_get_json(_HN_TOP_URL)
    if not isinstance(story_ids, list):
        return []

    items: list[dict[str, Any]] = []
    for sid in story_ids[:limit]:
        story = _safe_get_json(_HN_ITEM_URL.format(sid))
        if not isinstance(story, dict) or story.get("type") != "story":
            continue
        title = story.get("title", "")
        url = story.get("url", "")
        if not title:
            continue
        # HN self-posts have no URL — link to HN discussion
        if not url:
            url = f"https://news.ycombinator.com/item?id={sid}"
        items.append({
            "title": title,
            "summary": "",  # HN stories have no summary
            "url": url,
            "published_at": float(story.get("time", 0)),
        })
    return items


# ---------------------------------------------------------------------------
# Reddit fetcher (public JSON API — no auth required)
# ---------------------------------------------------------------------------

_REDDIT_HOT_URL = "https://www.reddit.com/r/{}/hot.json?limit={}&raw_json=1"


def _fetch_reddit(subreddits: list[str], *, limit_per_sub: int = 10) -> list[dict[str, Any]]:
    """Fetch hot posts from configured subreddits via Reddit's public JSON API."""
    items: list[dict[str, Any]] = []
    for sub in subreddits:
        # Sanitise subreddit name
        sub = sub.strip().strip("/").removeprefix("r/")
        if not sub:
            continue
        url = _REDDIT_HOT_URL.format(sub, limit_per_sub)
        data = _safe_get_json(url)
        if not isinstance(data, dict):
            continue
        children = data.get("data", {}).get("children", [])
        for child in children:
            post = child.get("data", {})
            if post.get("stickied"):
                continue
            title = post.get("title", "")
            link = post.get("url", "")
            if not title:
                continue
            summary = (post.get("selftext") or "")[:500]
            items.append({
                "title": title,
                "summary": summary,
                "url": link,
                "published_at": float(post.get("created_utc", 0)),
            })
    return items


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class NewsIngestService:
    """Poll configured news sources and produce deduplicated NewsItem objects."""

    def __init__(self) -> None:
        self._seen_hashes: OrderedDict[str, None] = OrderedDict()
        self._max_seen: int = 2000
        self._source_health: dict[str, _SourceHealth] = {}

    def _health(self, channel: str) -> _SourceHealth:
        """Get or create per-source health tracker."""
        if channel not in self._source_health:
            self._source_health[channel] = _SourceHealth()
        return self._source_health[channel]

    @staticmethod
    def _item_hash(title: str, url: str) -> str:
        raw = f"{title.strip().lower()}|{url.strip().lower()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _dedup(self, items: list[NewsItem]) -> list[NewsItem]:
        unique: list[NewsItem] = []
        for item in items:
            h = self._item_hash(item.title, item.url)
            if h not in self._seen_hashes:
                self._seen_hashes[h] = None
                unique.append(item)
        # Evict oldest hashes (FIFO) if cache grows too large
        while len(self._seen_hashes) > self._max_seen:
            self._seen_hashes.popitem(last=False)
        return unique

    def fetch_rss(self, feed_urls: list[str]) -> list[NewsItem]:
        """Fetch news items from a list of RSS feed URLs."""
        health = self._health("rss")
        if health.is_paused:
            log.debug("RSS source paused due to repeated failures")
            return []
        items: list[NewsItem] = []
        try:
            for url in feed_urls:
                raw = _parse_rss_feed(url)
                for entry in raw:
                    items.append(NewsItem(
                        title=entry.get("title", ""),
                        summary=entry.get("summary", ""),
                        url=entry.get("url", ""),
                        source_channel="rss",
                        published_at=entry.get("published_at", 0.0),
                    ))
            if items:
                health.record_success()
            elif feed_urls:
                health.record_failure()
        except Exception as exc:
            log.warning("RSS fetch error: %s", exc)
            health.record_failure()
        return self._dedup(items)

    def fetch_hackernews(self, *, limit: int = 15) -> list[NewsItem]:
        """Fetch top HackerNews stories."""
        health = self._health("hackernews")
        if health.is_paused:
            log.debug("HackerNews source paused due to repeated failures")
            return []
        try:
            raw = _fetch_hackernews(limit=limit)
            items = [
                NewsItem(
                    title=entry["title"],
                    summary=entry.get("summary", ""),
                    url=entry["url"],
                    source_channel="hackernews",
                    published_at=entry.get("published_at", 0.0),
                )
                for entry in raw
            ]
            if items:
                health.record_success()
            else:
                health.record_failure()
            return self._dedup(items)
        except Exception as exc:
            log.warning("HackerNews fetch error: %s", exc)
            health.record_failure()
            return []

    def fetch_reddit(self, subreddits: list[str]) -> list[NewsItem]:
        """Fetch hot posts from configured subreddits."""
        health = self._health("reddit")
        if health.is_paused:
            log.debug("Reddit source paused due to repeated failures")
            return []
        try:
            raw = _fetch_reddit(subreddits)
            items = [
                NewsItem(
                    title=entry["title"],
                    summary=entry.get("summary", ""),
                    url=entry["url"],
                    source_channel="reddit",
                    published_at=entry.get("published_at", 0.0),
                )
                for entry in raw
            ]
            if items:
                health.record_success()
            else:
                health.record_failure()
            return self._dedup(items)
        except Exception as exc:
            log.warning("Reddit fetch error: %s", exc)
            health.record_failure()
            return []

    def fetch_all(self, settings: dict[str, Any]) -> list[NewsItem]:
        """Fetch news from all enabled sources per settings."""
        sources: list[str] = settings.get("news_comet_sources", ["rss"])
        items: list[NewsItem] = []

        if "rss" in sources:
            feeds: list[str] = settings.get("news_comet_rss_feeds", [])
            if feeds:
                items.extend(self.fetch_rss(feeds))

        if "hackernews" in sources:
            items.extend(self.fetch_hackernews())

        if "reddit" in sources:
            subs: list[str] = settings.get("news_comet_reddit_subs", [])
            if subs:
                items.extend(self.fetch_reddit(subs))

        return self._dedup(items)

    def classify_item(
        self,
        item: NewsItem,
        *,
        brain_pass_fn: Callable[..., Any] | None = None,
    ) -> CometEvent:
        """Run brain pass classification on a news item and wrap it in a CometEvent."""
        event = CometEvent(news_item=item)

        if brain_pass_fn is not None:
            try:
                result = brain_pass_fn(
                    title=item.title,
                    summary=item.summary,
                    content=item.summary,
                )
                placement = getattr(result, "placement", None) or {}
                if isinstance(placement, dict):
                    event.faculty_id = placement.get("faculty_id", "")
                    event.secondary_faculty_id = placement.get("secondary_faculty_id", "")
                    event.classification_score = float(placement.get("score", 0.0))
                elif hasattr(placement, "faculty_id"):
                    event.faculty_id = getattr(placement, "faculty_id", "")
                    event.secondary_faculty_id = getattr(placement, "secondary_faculty_id", "")
                    event.classification_score = float(getattr(placement, "score", 0.0))
            except Exception as exc:
                log.warning("Brain pass classification failed for %r: %s", item.title, exc)

        # Fallback: assign to 'knowledge' if unclassified
        if not event.faculty_id:
            event.faculty_id = "knowledge"
            event.classification_score = 0.1

        return event

    def ingest(
        self,
        settings: dict[str, Any],
        *,
        brain_pass_fn: Callable[..., Any] | None = None,
    ) -> list[CometEvent]:
        """Full pipeline: fetch → dedup → classify → return comet events."""
        items = self.fetch_all(settings)
        events: list[CometEvent] = []
        for item in items:
            event = self.classify_item(item, brain_pass_fn=brain_pass_fn)
            events.append(event)
        return events
