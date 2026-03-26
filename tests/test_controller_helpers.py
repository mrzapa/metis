"""tests/test_controller_helpers.py — Unit tests for pure controller helpers.

Tests _chunk_text and _cosine which live at module level in app_controller
and contain no Tk or model dependencies.
"""

from __future__ import annotations

import math

import pytest

from metis_app.controllers.app_controller import _chunk_text, _cosine


# ---------------------------------------------------------------------------
# _chunk_text
# ---------------------------------------------------------------------------

class TestChunkText:
    def test_empty_string_returns_empty_list(self):
        # No text → no chunks (empty string has length 0, loop never starts).
        result = _chunk_text("", 100, 10)
        assert result == []

    def test_text_shorter_than_chunk_size(self):
        result = _chunk_text("hello", 100, 10)
        assert result == ["hello"]

    def test_exact_chunk_size_no_overlap(self):
        result = _chunk_text("abcdef", 3, 0)
        assert result == ["abc", "def"]

    def test_overlap_creates_shared_content(self):
        text = "0123456789"
        result = _chunk_text(text, 6, 2)
        # chunk 0: [0..6) → "012345"
        # chunk 1: [4..10) → "456789"
        assert result[0] == "012345"
        assert result[1] == "456789"
        # The last 2 chars of chunk 0 appear at the start of chunk 1
        assert result[0][-2:] == result[1][:2]

    def test_chunk_count_is_correct(self):
        # 100-char text, chunk_size=20, overlap=5 → step=15
        # positions: 0,15,30,45,60,75,90 → 7 chunks
        text = "x" * 100
        result = _chunk_text(text, 20, 5)
        assert len(result) == 7

    def test_last_chunk_never_exceeds_source(self):
        text = "a" * 97
        for chunk in _chunk_text(text, 20, 5):
            assert len(chunk) <= 20

    def test_all_chars_covered(self):
        """Reconstruct the original (no overlap) and check coverage."""
        text = "The quick brown fox jumps over the lazy dog."
        chunks = _chunk_text(text, 10, 0)
        assert "".join(chunks) == text

    def test_overlap_clamped_to_chunk_size_minus_one(self):
        # overlap >= chunk_size should not loop forever
        result = _chunk_text("abcde", 3, 10)  # overlap clamped to 2
        assert len(result) >= 1
        for c in result:
            assert len(c) <= 3

    def test_invalid_chunk_size_raises(self):
        with pytest.raises(ValueError):
            _chunk_text("hello", 0, 0)

    def test_single_char_chunks(self):
        result = _chunk_text("abc", 1, 0)
        assert result == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# _cosine
# ---------------------------------------------------------------------------

class TestCosine:
    def test_identical_vectors_return_one(self):
        v = [1.0, 0.0, 0.0]
        assert math.isclose(_cosine(v, v), 1.0)

    def test_orthogonal_vectors_return_zero(self):
        v1 = [1.0, 0.0]
        v2 = [0.0, 1.0]
        assert math.isclose(_cosine(v1, v2), 0.0)

    def test_opposite_vectors_return_minus_one(self):
        v1 = [1.0, 0.0]
        v2 = [-1.0, 0.0]
        assert math.isclose(_cosine(v1, v2), -1.0)

    def test_zero_vector_returns_zero(self):
        v1 = [0.0, 0.0]
        v2 = [1.0, 2.0]
        assert _cosine(v1, v2) == 0.0
        assert _cosine(v2, v1) == 0.0

    def test_symmetry(self):
        v1 = [1.0, 2.0, 3.0]
        v2 = [4.0, 5.0, 6.0]
        assert math.isclose(_cosine(v1, v2), _cosine(v2, v1))

    def test_result_bounded_in_minus_one_to_one(self):
        import random
        rng = random.Random(42)
        for _ in range(50):
            v1 = [rng.uniform(-1, 1) for _ in range(16)]
            v2 = [rng.uniform(-1, 1) for _ in range(16)]
            sim = _cosine(v1, v2)
            assert -1.0 - 1e-9 <= sim <= 1.0 + 1e-9

    def test_mock_embeddings_same_text_scores_1(self):
        """Sanity: embed the same string twice, cosine should be ~1."""
        from metis_app.utils.mock_embeddings import MockEmbeddings
        emb = MockEmbeddings(dimensions=32)
        v = emb.embed_query("hello world")
        assert math.isclose(_cosine(v, v), 1.0)

    def test_mock_embeddings_different_texts_score_less_than_1(self):
        from metis_app.utils.mock_embeddings import MockEmbeddings
        emb = MockEmbeddings(dimensions=32)
        v1 = emb.embed_query("hello world")
        v2 = emb.embed_query("completely different content xyz")
        assert _cosine(v1, v2) < 1.0
