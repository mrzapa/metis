"""Tests for the M24 star recommender service.

See ADR 0019 (Constellation IA - content-first projects) and the M24
implementation plan at
``docs/plans/2026-05-03-constellation-ia-reset-m24-implementation.md``.
"""

from __future__ import annotations

import numpy as np

from metis_app.services.star_recommender_service import (
    StarRecommendation,
    StarRecommenderService,
)


def test_rank_returns_top_k_by_cosine_similarity():
    """Three stars; query is closest to ``python_perf`` -> it ranks first."""
    star_embeddings = {
        "python_perf": np.array([1.0, 0.0, 0.0]),
        "python_tooling": np.array([0.95, 0.31, 0.0]),
        "cooking": np.array([0.0, 0.0, 1.0]),
    }
    star_metadata = {
        "python_perf": {"label": "Python perf", "archetype": "main_sequence"},
        "python_tooling": {"label": "Python tooling", "archetype": "main_sequence"},
        "cooking": {"label": "Cooking", "archetype": "main_sequence"},
    }
    query = np.array([1.0, 0.05, 0.0])

    service = StarRecommenderService()
    results = service.rank(
        query_embedding=query,
        star_embeddings=star_embeddings,
        star_metadata=star_metadata,
        top_k=3,
    )

    assert len(results) == 3
    assert all(isinstance(r, StarRecommendation) for r in results)
    assert results[0].star_id == "python_perf"
    assert results[-1].star_id == "cooking"
    # Strictly decreasing similarity.
    assert results[0].similarity > results[1].similarity > results[2].similarity


def test_rank_content_type_tiebreak():
    """Identical embeddings + matching archetype hint -> hint wins."""
    star_embeddings = {
        "doc_a": np.array([1.0, 0.0]),
        "doc_b": np.array([1.0, 0.0]),
    }
    star_metadata = {
        "doc_a": {"label": "Doc A", "archetype": "main_sequence"},
        "doc_b": {"label": "Doc B", "archetype": "pulsar"},
    }
    query = np.array([1.0, 0.0])

    service = StarRecommenderService()
    results = service.rank(
        query_embedding=query,
        star_embeddings=star_embeddings,
        star_metadata=star_metadata,
        top_k=2,
        content_type_hint="main_sequence",
    )

    assert len(results) == 2
    assert results[0].star_id == "doc_a"
    assert results[0].archetype == "main_sequence"
    assert results[1].star_id == "doc_b"


def test_rank_handles_empty_star_set():
    """No stars -> empty list."""
    service = StarRecommenderService()
    results = service.rank(
        query_embedding=np.array([1.0, 0.0]),
        star_embeddings={},
        star_metadata={},
        top_k=5,
    )
    assert results == []
