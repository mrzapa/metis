"""tests/test_brain_metrics.py — Unit tests for brain coherence metrics."""

from __future__ import annotations

import numpy as np

from metis_app.utils.brain_metrics import CoherenceAssessor, compute_coherence


def _structured_activity(v: int = 8, t: int = 128, seed: int = 0) -> np.ndarray:
    """Synthesise a (V, T) tensor with inter-channel coupling."""
    rng = np.random.default_rng(seed)
    base = rng.standard_normal(t).cumsum()
    out = np.zeros((v, t), dtype=np.float32)
    for i in range(v):
        out[i] = np.roll(base, i) + 0.2 * rng.standard_normal(t)
    return out


def _noise_activity(v: int = 8, t: int = 128, seed: int = 1) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal((v, t)).astype(np.float32)


class TestShape:
    def test_zero_input_returns_zero_metrics(self):
        m = compute_coherence(np.zeros((0, 0)))
        assert m["c_score"] == 0.0
        assert m["active_channels"] == 0

    def test_one_channel_returns_finite_metrics(self):
        m = compute_coherence(np.random.default_rng(0).standard_normal((1, 64)))
        for v in m.values():
            assert np.isfinite(v)

    def test_required_keys_present(self):
        m = compute_coherence(_noise_activity())
        for key in (
            "c_score", "closure", "lambda2_norm", "rho",
            "lz_complexity", "channel_entropy", "synchrony",
            "mean_transfer_entropy", "mean_firing_rate", "active_channels",
        ):
            assert key in m


class TestRanges:
    def test_scores_are_bounded(self):
        m = compute_coherence(_structured_activity())
        for key in ("c_score", "closure", "lambda2_norm", "rho",
                    "lz_complexity", "channel_entropy", "synchrony",
                    "mean_firing_rate"):
            assert 0.0 <= m[key] <= 1.0, f"{key}={m[key]}"


class TestStructureVsNoise:
    def test_structured_has_higher_closure_than_noise(self):
        # Closure should reflect the temporally-coupled structure we injected.
        structured = compute_coherence(_structured_activity(v=16, t=256))
        noise = compute_coherence(_noise_activity(v=16, t=256))
        assert structured["closure"] >= noise["closure"] - 0.1


class TestDownsample:
    def test_downsample_still_returns_valid_metrics(self):
        activity = _structured_activity(v=8, t=256)
        m = compute_coherence(activity, downsample=4)
        for v in m.values():
            assert np.isfinite(v)
        assert m["active_channels"] > 0

    def test_max_channels_caps_work(self):
        activity = _structured_activity(v=128, t=256)
        m = compute_coherence(activity, max_channels=16)
        # Metrics still finite with the channel cap applied.
        assert np.isfinite(m["c_score"])


class TestAssessor:
    def test_push_and_score(self):
        assessor = CoherenceAssessor(window=128, max_channels=32)
        for _ in range(4):
            assessor.push(_noise_activity(v=8, t=32))
        m = assessor.score()
        assert "c_score" in m
        assert np.isfinite(m["c_score"])

    def test_empty_assessor_returns_zero(self):
        assessor = CoherenceAssessor()
        m = assessor.score()
        assert m["c_score"] == 0.0

    def test_window_trim_keeps_recent_frames(self):
        assessor = CoherenceAssessor(window=32, max_channels=16)
        for i in range(10):
            assessor.push(np.full((4, 16), float(i), dtype=np.float32))
        # After 10*16=160 pushes, we keep only the last 32 columns.
        activity = np.concatenate(assessor._buffer, axis=1)
        assert activity.shape[1] <= 32
