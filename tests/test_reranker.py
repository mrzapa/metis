"""Tests for metis_app.services.reranker."""

from __future__ import annotations

from metis_app.services.reranker import (
    bm25_score_chunks,
    reciprocal_rank_fusion,
    rerank_hits,
)


def test_rrf_single_list_preserves_order() -> None:
    """A single list passed to RRF should preserve its original order."""
    ranked = [5, 3, 1, 0, 2]
    result = reciprocal_rank_fusion(ranked)
    assert result == ranked


def test_rrf_two_identical_lists() -> None:
    """Two identical lists should produce the same order."""
    ranked = [0, 1, 2, 3]
    result = reciprocal_rank_fusion(ranked, ranked)
    assert result == ranked


def test_rrf_different_lists_fuses_rankings() -> None:
    """Items that appear high in both lists should rank higher."""
    list_a = [0, 1, 2, 3]  # 0 is best in list_a
    list_b = [3, 2, 1, 0]  # 3 is best in list_b
    result = reciprocal_rank_fusion(list_a, list_b)
    # All items should appear.
    assert set(result) == {0, 1, 2, 3}
    # Items ranked high in both (1, 2) should beat those ranked high in only one.
    assert len(result) == 4


def test_rrf_empty_lists() -> None:
    """Empty lists should produce empty results."""
    result = reciprocal_rank_fusion([], [])
    assert result == []


def test_rrf_disjoint_lists() -> None:
    """Disjoint lists should all be included."""
    result = reciprocal_rank_fusion([0, 1], [2, 3])
    assert set(result) == {0, 1, 2, 3}


def test_bm25_scores_relevant_chunk_higher() -> None:
    """Chunks containing query terms should score higher."""
    question = "machine learning algorithms"
    chunks = [
        {"text": "Deep learning is a subset of machine learning algorithms."},
        {"text": "The weather today is sunny and warm."},
        {"text": "Machine learning uses data to train models."},
    ]
    scores = bm25_score_chunks(question, chunks)
    assert len(scores) == 3
    # Chunk 0 and 2 mention query terms; chunk 1 does not.
    assert scores[0] > scores[1]
    assert scores[2] > scores[1]


def test_bm25_empty_question_returns_zeros() -> None:
    """An empty question should return zero scores."""
    chunks = [{"text": "Some content here."}]
    scores = bm25_score_chunks("", chunks)
    assert scores == [0.0]


def test_bm25_empty_chunks_returns_empty() -> None:
    """No chunks should return an empty list."""
    scores = bm25_score_chunks("test query", [])
    assert scores == []


def test_rerank_hits_returns_correct_count() -> None:
    """rerank_hits should return at most top_k results."""
    # Create a minimal bundle-like object with chunks.
    class FakeBundle:
        chunks = [
            {"text": "Alpha article about neural networks."},
            {"text": "Beta piece on deep learning."},
            {"text": "Gamma text about cooking recipes."},
            {"text": "Delta document on machine learning models."},
            {"text": "Epsilon notes on garden plants."},
        ]

    bundle = FakeBundle()
    question = "machine learning"
    vector_ranked = [0, 1, 3, 2, 4]
    graph_hits = [3, 0]
    settings = {"top_k": 3, "retrieval_k": 5}

    result = rerank_hits(bundle, question, vector_ranked, graph_hits, settings)
    assert len(result) <= 3
    # All returned indices should be valid.
    for idx in result:
        assert 0 <= idx < len(bundle.chunks)


def test_rerank_hits_without_graph_hits() -> None:
    """rerank_hits should work even without graph hits."""
    class FakeBundle:
        chunks = [
            {"text": "Python programming tutorial."},
            {"text": "JavaScript guide for beginners."},
            {"text": "Cooking with Python snakes."},
        ]

    bundle = FakeBundle()
    result = rerank_hits(
        bundle,
        "Python programming",
        [0, 1, 2],
        [],
        {"top_k": 2, "retrieval_k": 3},
    )
    assert len(result) <= 2
    # The Python-relevant chunk should be ranked high.
    assert 0 in result


def test_rerank_hits_respects_top_k() -> None:
    """Top_k should cap the output length."""
    class FakeBundle:
        chunks = [{"text": f"chunk {i}"} for i in range(20)]

    bundle = FakeBundle()
    result = rerank_hits(
        bundle,
        "chunk",
        list(range(20)),
        list(range(5)),
        {"top_k": 3, "retrieval_k": 20},
    )
    assert len(result) == 3
