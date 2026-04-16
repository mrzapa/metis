"""tests/test_spatial_encoder.py — Unit tests for SpatialFingerprint."""

from __future__ import annotations

import numpy as np
import pytest

from metis_app.utils.spatial_encoder import SpatialFingerprint


class TestConstruction:
    def test_rejects_tiny_channel_count(self):
        with pytest.raises(ValueError):
            SpatialFingerprint(n_channels=1)

    def test_rejects_oversize_top_k(self):
        with pytest.raises(ValueError):
            SpatialFingerprint(n_channels=32, active_k=64)

    def test_rejects_inverted_amp_range(self):
        with pytest.raises(ValueError):
            SpatialFingerprint(amp_range=(2.0, 1.0))


class TestDeterminism:
    def test_same_id_same_fingerprint(self):
        a = SpatialFingerprint(seed=42).encode_id(7)
        b = SpatialFingerprint(seed=42).encode_id(7)
        assert a == b

    def test_same_vector_same_fingerprint(self):
        vec = np.arange(16, dtype=np.float32)
        a = SpatialFingerprint(seed=42).encode_vector(vec)
        b = SpatialFingerprint(seed=42).encode_vector(vec)
        assert a == b

    def test_different_seed_different_fingerprint(self):
        vec = np.linspace(-1, 1, 32)
        a = SpatialFingerprint(seed=1).encode_vector(vec)
        b = SpatialFingerprint(seed=2).encode_vector(vec)
        assert a != b


class TestTopK:
    def test_active_k_respected(self):
        enc = SpatialFingerprint(n_channels=62, active_k=8)
        fp = enc.encode_vector(np.random.default_rng(0).standard_normal(32))
        assert len(fp) == 8

    def test_amplitudes_within_range(self):
        enc = SpatialFingerprint(amp_range=(0.5, 2.0))
        fp = enc.encode_vector(np.arange(24, dtype=np.float32))
        for amp in fp.values():
            assert 0.5 <= amp <= 2.0


class TestSimilarity:
    def test_similar_vectors_overlap(self):
        enc = SpatialFingerprint(n_channels=32, active_k=12, seed=7)
        rng = np.random.default_rng(7)
        base = rng.standard_normal(64)
        near = base + 0.01 * rng.standard_normal(64)
        a = enc.encode_vector(base)
        b = enc.encode_vector(near)
        assert SpatialFingerprint.similarity(a, b) > 0.5

    def test_empty_fingerprint_similarity_zero(self):
        enc = SpatialFingerprint()
        a = enc.encode_vector(np.zeros(16))
        assert SpatialFingerprint.similarity(a, {}) == 0.0
        assert SpatialFingerprint.similarity({}, a) == 0.0

    def test_identical_fingerprint_similarity_one(self):
        enc = SpatialFingerprint()
        a = enc.encode_vector(np.arange(16))
        assert SpatialFingerprint.similarity(a, a) == pytest.approx(1.0)

    def test_overlap_count(self):
        enc = SpatialFingerprint(n_channels=16, active_k=4, seed=11)
        a = enc.encode_id(1)
        b = enc.encode_id(1)
        assert SpatialFingerprint.overlap(a, b) == 4


class TestEdgeCases:
    def test_empty_vector_returns_empty(self):
        assert SpatialFingerprint().encode_vector([]) == {}

    def test_string_id_encodes(self):
        fp = SpatialFingerprint().encode_id("hello world")
        assert len(fp) > 0
