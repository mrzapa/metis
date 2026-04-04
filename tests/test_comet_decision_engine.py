"""Tests for CometDecisionEngine — gap scoring, relevance, and decisions."""

from __future__ import annotations

from metis_app.models.comet_event import CometEvent, NewsItem
from metis_app.services.comet_decision_engine import CometDecisionEngine


def _make_event(faculty_id: str = "knowledge", score: float = 0.7) -> CometEvent:
    item = NewsItem(
        item_id="test-1",
        title="Test Article",
        summary="Summary",
        url="https://example.com",
        source_channel="rss",
    )
    return CometEvent(
        comet_id="comet-test-1",
        news_item=item,
        faculty_id=faculty_id,
        classification_score=score,
    )


# ---------------------------------------------------------------------------
# Gap scoring
# ---------------------------------------------------------------------------


def test_gap_scores_empty_indexes():
    engine = CometDecisionEngine()
    gaps = engine.compute_gap_scores([])
    # All faculties should have max gap (1.0) with no indexes
    assert all(v == 1.0 for v in gaps.values())
    assert "knowledge" in gaps


def test_gap_scores_with_indexes():
    engine = CometDecisionEngine()
    indexes = [
        {"index_id": "auto_knowledge_1", "document_count": 3},
        {"index_id": "auto_knowledge_2", "document_count": 2},
        {"index_id": "auto_knowledge_3", "document_count": 1},
        {"index_id": "auto_reasoning_1", "document_count": 1},
    ]
    gaps = engine.compute_gap_scores(indexes)
    # knowledge has 3 auto_ stars, reasoning has 1
    assert gaps["knowledge"] < gaps["reasoning"]
    # faculties with zero indexes should be highest gap
    assert gaps["perception"] == 1.0


# ---------------------------------------------------------------------------
# Relevance scoring
# ---------------------------------------------------------------------------


def test_relevance_combines_classification_and_gap():
    engine = CometDecisionEngine()
    event = _make_event(faculty_id="knowledge", score=0.9)
    gaps = {"knowledge": 0.8, "reasoning": 0.2}
    relevance = engine.score_relevance(event, gaps)
    # 0.4 * 0.9 (classification) + 0.6 * 0.8 (gap) = 0.36 + 0.48 = 0.84
    assert abs(relevance - 0.84) < 0.01


def test_relevance_zero_gap_lowers_score():
    engine = CometDecisionEngine()
    event = _make_event(faculty_id="knowledge", score=0.5)
    gaps = {"knowledge": 0.0}
    relevance = engine.score_relevance(event, gaps)
    # 0.4 * 0.5 + 0.6 * 0.0 = 0.20
    assert abs(relevance - 0.20) < 0.01


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------


def test_decide_absorb_above_threshold():
    engine = CometDecisionEngine()
    event = _make_event(score=0.9)
    gaps = {"knowledge": 1.0}
    result = engine.decide(event, gaps, absorb_threshold=0.75)
    assert result.decision == "absorb"


def test_decide_approach_between_thresholds():
    engine = CometDecisionEngine()
    event = _make_event(score=0.5)
    gaps = {"knowledge": 0.5}
    result = engine.decide(event, gaps, absorb_threshold=0.75)
    assert result.decision == "approach"


def test_decide_drift_below_lower_threshold():
    engine = CometDecisionEngine()
    event = _make_event(score=0.1)
    gaps = {"knowledge": 0.1}
    result = engine.decide(event, gaps, absorb_threshold=0.75)
    assert result.decision == "drift"


# ---------------------------------------------------------------------------
# Batch evaluation
# ---------------------------------------------------------------------------


def test_evaluate_batch_respects_max_active():
    engine = CometDecisionEngine()
    events: list[CometEvent] = []
    for i in range(10):
        item = NewsItem(
            item_id=f"batch-{i}", title=f"Article {i}", summary="",
            url=f"https://example.com/{i}", source_channel="rss",
        )
        events.append(CometEvent(
            comet_id=f"c-batch-{i}",
            news_item=item,
            faculty_id="knowledge",
            classification_score=0.8,
        ))

    settings = {"news_comet_max_active": 3, "news_comet_auto_absorb_threshold": 0.75}
    indexes: list[dict] = []
    result = engine.evaluate_batch(events, indexes, settings)
    assert len(result) <= 3


def test_evaluate_batch_assigns_decisions():
    engine = CometDecisionEngine()
    item = NewsItem(
        item_id="ev-1", title="Important", summary="Very relevant",
        url="https://example.com/1", source_channel="rss",
    )
    event = CometEvent(
        comet_id="c-ev-1",
        news_item=item,
        faculty_id="perception",
        classification_score=0.95,
    )
    settings = {"news_comet_max_active": 5, "news_comet_auto_absorb_threshold": 0.75}
    result = engine.evaluate_batch([event], [], settings)
    assert len(result) == 1
    assert result[0].decision in ("drift", "approach", "absorb")
    assert result[0].comet_id
