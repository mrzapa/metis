"""Comet decision engine — scores news comets against faculty gaps and decides drift/approach/absorb."""

from __future__ import annotations

import logging
import time
from typing import Any

from metis_app.models.comet_event import CometEvent

log = logging.getLogger(__name__)

# Faculty order (same as autonomous research service)
FACULTY_ORDER = [
    "perception", "knowledge", "memory", "reasoning", "skills",
    "strategy", "personality", "values", "synthesis", "autonomy", "emergence",
]


class CometDecisionEngine:
    """Score comet events and decide whether METIS should engage.

    Decision thresholds:
      - relevance < 0.3  → drift  (comet floats past)
      - 0.3 ≤ relevance < threshold → approach  (METIS shows interest)
      - relevance ≥ threshold → absorb  (METIS absorbs into faculty)

    Where ``threshold`` is ``news_comet_auto_absorb_threshold`` from settings
    (default: 0.75).
    """

    def compute_gap_scores(self, indexes: list[dict[str, Any]]) -> dict[str, float]:
        """Return a 0-1 gap score per faculty.  Faculties with fewer indexed
        stars have higher gaps (more need for new knowledge).
        """
        counts: dict[str, int] = {f: 0 for f in FACULTY_ORDER}
        for idx in indexes:
            idx_id: str = idx.get("index_id", "")
            for fac in FACULTY_ORDER:
                if fac in idx_id.lower():
                    counts[fac] += 1
                    break

        max_count = max(counts.values()) if counts else 1
        if max_count == 0:
            max_count = 1

        return {
            fac: 1.0 - (count / max_count)
            for fac, count in counts.items()
        }

    def score_relevance(
        self,
        event: CometEvent,
        gap_scores: dict[str, float],
    ) -> float:
        """Compute a composite relevance score [0, 1] for a comet event.

        Combines classification confidence with faculty gap demand.
        """
        classification = event.classification_score
        gap = gap_scores.get(event.faculty_id, 0.5)

        # Weighted blend: 40% classification confidence + 60% faculty gap
        relevance = 0.4 * classification + 0.6 * gap
        return max(0.0, min(1.0, relevance))

    def decide(
        self,
        event: CometEvent,
        gap_scores: dict[str, float],
        *,
        absorb_threshold: float = 0.75,
    ) -> CometEvent:
        """Score and decide the outcome for a single comet event (in-place mutation)."""
        relevance = self.score_relevance(event, gap_scores)
        event.relevance_score = relevance
        event.gap_score = gap_scores.get(event.faculty_id, 0.0)
        event.decided_at = time.time()

        if relevance >= absorb_threshold:
            event.decision = "absorb"
            event.phase = "approaching"
        elif relevance >= 0.3:
            event.decision = "approach"
            event.phase = "approaching"
        else:
            event.decision = "drift"
            event.phase = "drifting"

        return event

    def evaluate_batch(
        self,
        events: list[CometEvent],
        indexes: list[dict[str, Any]],
        settings: dict[str, Any],
    ) -> list[CometEvent]:
        """Evaluate a batch of comet events and return them with decisions filled in."""
        gap_scores = self.compute_gap_scores(indexes)
        absorb_threshold = float(settings.get("news_comet_auto_absorb_threshold", 0.75))
        max_active = int(settings.get("news_comet_max_active", 5))

        decided: list[CometEvent] = []
        for event in events[:max_active]:
            self.decide(event, gap_scores, absorb_threshold=absorb_threshold)
            decided.append(event)

        return decided
