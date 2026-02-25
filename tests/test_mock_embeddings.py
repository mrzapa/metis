"""tests/test_mock_embeddings.py — Unit tests for MockEmbeddings.

No Tk, no ML libraries required.  All assertions are pure arithmetic on
the deterministic SHA-256-based vectors.
"""

from __future__ import annotations

import pytest

from axiom_app.utils.mock_embeddings import MockEmbeddings

# ---------------------------------------------------------------------------
# Dimension
# ---------------------------------------------------------------------------


def test_default_dimension_is_32():
    emb = MockEmbeddings()
    vec = emb.embed_query("hello")
    assert len(vec) == 32


def test_custom_dimension_is_respected():
    for dim in (8, 16, 64, 128, 256):
        emb = MockEmbeddings(dimensions=dim)
        vec = emb.embed_query("test")
        assert len(vec) == dim, f"expected {dim} dimensions, got {len(vec)}"


def test_minimum_dimension_is_8():
    """Dimensions below 8 are clamped to 8."""
    emb = MockEmbeddings(dimensions=1)
    assert emb.dimensions == 8
    vec = emb.embed_query("x")
    assert len(vec) == 8


# ---------------------------------------------------------------------------
# Value range
# ---------------------------------------------------------------------------


def test_values_in_minus_one_to_one():
    emb = MockEmbeddings(dimensions=256)
    for text in ("", "hello world", "the quick brown fox", "日本語テスト"):
        vec = emb.embed_query(text)
        for v in vec:
            assert -1.0 <= v <= 1.0, f"value {v} out of range for text {text!r}"


def test_values_are_floats():
    emb = MockEmbeddings()
    vec = emb.embed_query("hello")
    assert all(isinstance(v, float) for v in vec)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_same_text_same_vector():
    emb = MockEmbeddings()
    v1 = emb.embed_query("reproducible")
    v2 = emb.embed_query("reproducible")
    assert v1 == v2


def test_different_texts_different_vectors():
    emb = MockEmbeddings()
    v1 = emb.embed_query("apple")
    v2 = emb.embed_query("orange")
    assert v1 != v2


def test_separate_instances_produce_same_vector():
    """Two independent MockEmbeddings objects with the same dim are equivalent."""
    text = "determinism check"
    v1 = MockEmbeddings(dimensions=32).embed_query(text)
    v2 = MockEmbeddings(dimensions=32).embed_query(text)
    assert v1 == v2


def test_empty_string_has_stable_vector():
    emb = MockEmbeddings()
    v1 = emb.embed_query("")
    v2 = emb.embed_query("")
    assert v1 == v2


# ---------------------------------------------------------------------------
# embed_documents
# ---------------------------------------------------------------------------


def test_embed_documents_returns_one_vector_per_text():
    emb = MockEmbeddings()
    texts = ["alpha", "beta", "gamma"]
    result = emb.embed_documents(texts)
    assert len(result) == len(texts)


def test_embed_documents_each_vector_has_correct_dimension():
    emb = MockEmbeddings(dimensions=64)
    result = emb.embed_documents(["a", "b", "c"])
    for vec in result:
        assert len(vec) == 64


def test_embed_documents_matches_embed_query_per_text():
    """embed_documents[i] must equal embed_query(texts[i])."""
    emb = MockEmbeddings(dimensions=32)
    texts = ["first", "second", "third"]
    batch = emb.embed_documents(texts)
    for i, text in enumerate(texts):
        single = emb.embed_query(text)
        assert batch[i] == single, f"mismatch for text index {i}: {text!r}"


def test_embed_documents_empty_list():
    emb = MockEmbeddings()
    assert emb.embed_documents([]) == []


def test_embed_documents_single_item():
    emb = MockEmbeddings()
    result = emb.embed_documents(["only"])
    assert len(result) == 1
    assert result[0] == emb.embed_query("only")


# ---------------------------------------------------------------------------
# embed_query
# ---------------------------------------------------------------------------


def test_embed_query_returns_flat_list():
    emb = MockEmbeddings()
    vec = emb.embed_query("flat list check")
    assert isinstance(vec, list)
    # Must be a flat list, not a list of lists.
    assert all(not isinstance(v, list) for v in vec)


def test_embed_query_none_equivalent_to_empty_string():
    """The implementation treats None as empty via ``(text or '')``."""
    emb = MockEmbeddings()
    v_none  = emb._embed(None)   # type: ignore[arg-type]
    v_empty = emb._embed("")
    assert v_none == v_empty


# ---------------------------------------------------------------------------
# Dimension independence
# ---------------------------------------------------------------------------


def test_vectors_of_different_dimensions_share_prefix_values():
    """
    Larger dimensions are built by cycling the digest, so the first N
    values of a 64-dim vector match the 32-dim vector for the same text.
    (Documents the algorithm; regression guard against accidental changes.)
    """
    text = "prefix test"
    v32 = MockEmbeddings(dimensions=32).embed_query(text)
    v64 = MockEmbeddings(dimensions=64).embed_query(text)
    assert v64[:32] == v32
