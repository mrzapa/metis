from __future__ import annotations

from metis_app.engine.streaming import _cosine_similarity, _embed_text


def test_cosine_similarity_identical_vectors():
    v = [1.0, 0.0, 0.0]
    assert abs(_cosine_similarity(v, v) - 1.0) < 1e-6


def test_cosine_similarity_orthogonal_vectors():
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert abs(_cosine_similarity(a, b)) < 1e-6


def test_cosine_similarity_zero_vector_returns_zero():
    assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_embed_text_returns_list_of_floats():
    result = _embed_text("hello world", {"embeddings_backend": "mock"})
    assert isinstance(result, list)
    assert all(isinstance(x, float) for x in result)
