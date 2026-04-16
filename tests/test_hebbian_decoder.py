"""tests/test_hebbian_decoder.py — Unit tests for HebbianAssociations."""

from __future__ import annotations

import json
import pathlib

import pytest

from metis_app.utils.hebbian_decoder import HebbianAssociations


class TestConstruction:
    def test_invalid_decay_rejected(self):
        with pytest.raises(ValueError):
            HebbianAssociations(decay=0.0)
        with pytest.raises(ValueError):
            HebbianAssociations(decay=1.5)

    def test_invalid_max_weight_rejected(self):
        with pytest.raises(ValueError):
            HebbianAssociations(max_weight=0)


class TestUpdate:
    def test_noop_without_channels(self):
        store = HebbianAssociations(decay=1.0)
        store.update([], "node_a")
        assert len(store) == 0

    def test_noop_without_node(self):
        store = HebbianAssociations(decay=1.0)
        store.update([1, 2, 3], "")
        assert len(store) == 0

    def test_reinforcement_increases_score(self):
        store = HebbianAssociations(decay=1.0, max_weight=5.0)
        store.update([1, 2, 3], "node_a", reward=1.0)
        store.update([1, 2, 3], "node_a", reward=1.0)
        # Score is summed across the three channels.
        assert store.score([1, 2, 3], "node_a") == pytest.approx(6.0)

    def test_saturation_cap(self):
        store = HebbianAssociations(decay=1.0, max_weight=2.0)
        for _ in range(10):
            store.update([5], "node_a", reward=1.0)
        # Per-channel weight clipped at 2.0.
        assert store.score([5], "node_a") == pytest.approx(2.0)

    def test_negative_reward_decreases(self):
        store = HebbianAssociations(decay=1.0, max_weight=5.0)
        store.update([1], "node_a", reward=2.0)
        store.update([1], "node_a", reward=-1.0)
        assert store.score([1], "node_a") == pytest.approx(1.0)

    def test_decay_erodes_unused_entries(self):
        store = HebbianAssociations(decay=0.5, max_weight=5.0)
        store.update([1], "node_a", reward=1.0)
        # A different channel update decays node_a's own weight because we
        # decay on every touched bucket — but node_a is on channel 1, not 2,
        # so reinforce channel 1 again and then decay via repeated updates
        # to trigger the decay branch.
        for _ in range(20):
            store.update([1], "node_b", reward=0.01)
        # node_a weight on channel 1 has been multiplicatively decayed.
        assert store.score([1], "node_a") < 1.0


class TestBoost:
    def test_empty_candidates_unchanged(self):
        store = HebbianAssociations(decay=1.0)
        assert store.boost([1, 2], []) == []

    def test_no_channels_unchanged(self):
        store = HebbianAssociations(decay=1.0)
        candidates = [("a", 0.5), ("b", 0.3)]
        assert store.boost([], candidates) == candidates

    def test_cold_state_preserves_order(self):
        store = HebbianAssociations(decay=1.0)
        candidates = [("a", 0.9), ("b", 0.5), ("c", 0.1)]
        assert store.boost([1, 2, 3], candidates) == candidates

    def test_warm_state_reranks(self):
        store = HebbianAssociations(decay=1.0, max_weight=10.0)
        for _ in range(5):
            store.update([1, 2, 3], "b", reward=1.0)
        candidates = [("a", 0.9), ("b", 0.5), ("c", 0.1)]
        ranked = store.boost([1, 2, 3], candidates, weight=1.0)
        ids = [nid for nid, _ in ranked]
        # With a huge boost weight, b should leapfrog a.
        assert ids.index("b") < ids.index("a")


class TestPersistence:
    def test_roundtrip_to_disk(self, tmp_path: pathlib.Path):
        path = tmp_path / "hebbian.json"
        store = HebbianAssociations(storage_path=path, decay=1.0)
        store.update([1, 2], "node_a", reward=1.5)
        store.save()
        assert path.exists()
        raw = json.loads(path.read_text())
        assert "1" in raw and "node_a" in raw["1"]

        loaded = HebbianAssociations(storage_path=path, decay=1.0)
        assert loaded.score([1, 2], "node_a") == pytest.approx(3.0)

    def test_corrupt_file_is_ignored(self, tmp_path: pathlib.Path):
        path = tmp_path / "hebbian.json"
        path.write_text("{not json")
        store = HebbianAssociations(storage_path=path, decay=1.0)
        assert len(store) == 0


class TestStats:
    def test_empty_stats(self):
        store = HebbianAssociations(decay=1.0)
        stats = store.stats()
        assert stats["associations"] == 0.0
        assert stats["mean_weight"] == 0.0

    def test_stats_after_updates(self):
        store = HebbianAssociations(decay=1.0, max_weight=5.0)
        store.update([1, 2], "node_a", reward=1.0)
        store.update([3], "node_b", reward=1.0)
        stats = store.stats()
        assert stats["associations"] == 3.0
        assert stats["positive_associations"] == 3.0
