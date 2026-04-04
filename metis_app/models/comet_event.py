"""Data models for the comet-news feature."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal


CometDecision = Literal["drift", "approach", "absorb"]
CometPhase = Literal["entering", "drifting", "approaching", "absorbing", "fading", "absorbed", "dismissed"]


@dataclass(slots=True)
class NewsItem:
    """A single news item fetched from an external source."""

    item_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    title: str = ""
    summary: str = ""
    url: str = ""
    source_channel: str = ""  # e.g. "rss", "exa", "arxiv"
    published_at: float = 0.0  # epoch seconds
    fetched_at: float = field(default_factory=time.time)
    raw_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CometEvent:
    """A comet event representing a news item's lifecycle in the constellation."""

    comet_id: str = field(default_factory=lambda: f"comet_{uuid.uuid4().hex[:10]}")
    news_item: NewsItem = field(default_factory=NewsItem)

    # Brain pass classification
    faculty_id: str = ""
    secondary_faculty_id: str = ""
    classification_score: float = 0.0

    # Decision engine output
    decision: CometDecision = "drift"
    relevance_score: float = 0.0
    gap_score: float = 0.0

    # Lifecycle
    phase: CometPhase = "entering"
    created_at: float = field(default_factory=time.time)
    decided_at: float = 0.0
    absorbed_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "comet_id": self.comet_id,
            "news_item": {
                "item_id": self.news_item.item_id,
                "title": self.news_item.title,
                "summary": self.news_item.summary,
                "url": self.news_item.url,
                "source_channel": self.news_item.source_channel,
                "published_at": self.news_item.published_at,
            },
            "faculty_id": self.faculty_id,
            "secondary_faculty_id": self.secondary_faculty_id,
            "classification_score": self.classification_score,
            "decision": self.decision,
            "relevance_score": self.relevance_score,
            "gap_score": self.gap_score,
            "phase": self.phase,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
            "absorbed_at": self.absorbed_at,
        }
