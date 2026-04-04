"""News ingestion service — fetches news from configured sources, deduplicates, and classifies via brain pass."""

from __future__ import annotations

import hashlib
import logging
import time
from collections.abc import Callable
from typing import Any

from metis_app.models.comet_event import CometEvent, NewsItem

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# RSS parser (optional dependency)
# ---------------------------------------------------------------------------

try:
    import feedparser  # type: ignore[import-untyped]
except ImportError:
    feedparser = None  # type: ignore[assignment]


def _parse_rss_feed(url: str, *, timeout: float = 15.0) -> list[dict[str, Any]]:
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
# Service
# ---------------------------------------------------------------------------


class NewsIngestService:
    """Poll configured news sources and produce deduplicated NewsItem objects."""

    def __init__(self) -> None:
        self._seen_hashes: set[str] = set()
        self._max_seen: int = 2000

    @staticmethod
    def _item_hash(title: str, url: str) -> str:
        raw = f"{title.strip().lower()}|{url.strip().lower()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _dedup(self, items: list[NewsItem]) -> list[NewsItem]:
        unique: list[NewsItem] = []
        for item in items:
            h = self._item_hash(item.title, item.url)
            if h not in self._seen_hashes:
                self._seen_hashes.add(h)
                unique.append(item)
        # Evict oldest hashes if cache grows too large
        if len(self._seen_hashes) > self._max_seen:
            excess = len(self._seen_hashes) - self._max_seen
            to_remove = list(self._seen_hashes)[:excess]
            self._seen_hashes -= set(to_remove)
        return unique

    def fetch_rss(self, feed_urls: list[str]) -> list[NewsItem]:
        """Fetch news items from a list of RSS feed URLs."""
        items: list[NewsItem] = []
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
        return self._dedup(items)

    def fetch_all(self, settings: dict[str, Any]) -> list[NewsItem]:
        """Fetch news from all enabled sources per settings."""
        sources: list[str] = settings.get("news_comet_sources", ["rss"])
        items: list[NewsItem] = []

        if "rss" in sources:
            feeds: list[str] = settings.get("news_comet_rss_feeds", [])
            if feeds:
                items.extend(self.fetch_rss(feeds))

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
