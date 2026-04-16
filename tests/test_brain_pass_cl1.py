"""tests/test_brain_pass_cl1.py — CL1-encoder integration in brain_pass.

Covers the non-Tribev2 pieces we wired in:

* Aggregation of coherence / fingerprint across multiple native results
* Heuristic fingerprint fallback when native Tribev2 did not run
* Passthrough of coherence/fingerprint into the brain_graph node metadata
"""

from __future__ import annotations

import pathlib

from metis_app.models.brain_graph import BrainGraph
from metis_app.services import brain_pass


class TestAggregateNativeAnalyses:
    def test_coherence_is_averaged(self):
        results = [
            {
                "native_input_mode": "audio",
                "top_rois": ["roi_a"],
                "timesteps": 10,
                "vertex_count": 32,
                "coherence": {"c_score": 0.4, "closure": 0.6},
                "fingerprint": {1: 1.0, 2: 0.5},
            },
            {
                "native_input_mode": "audio",
                "top_rois": ["roi_b"],
                "timesteps": 15,
                "vertex_count": 32,
                "coherence": {"c_score": 0.6, "closure": 0.2},
                "fingerprint": {1: 2.0, 3: 0.8},
            },
        ]
        agg = brain_pass._aggregate_native_analyses(results)
        assert agg["coherence"]["c_score"] == 0.5
        assert agg["coherence"]["closure"] == 0.4
        # Channel 1 appears in both: avg(1.0, 2.0) = 1.5
        assert agg["fingerprint"][1] == 1.5
        # Channel 2 only in first
        assert agg["fingerprint"][2] == 0.5
        # Channel 3 only in second
        assert agg["fingerprint"][3] == 0.8

    def test_handles_missing_coherence(self):
        results = [
            {"native_input_mode": "text", "top_rois": [], "timesteps": 5, "vertex_count": 8},
            {"native_input_mode": "text", "top_rois": [], "timesteps": 5, "vertex_count": 8,
             "coherence": {"c_score": 0.9}, "fingerprint": {1: 1.0}},
        ]
        agg = brain_pass._aggregate_native_analyses(results)
        assert agg["coherence"]["c_score"] == 0.9
        assert agg["fingerprint"] == {1: 1.0}

    def test_empty_results(self):
        agg = brain_pass._aggregate_native_analyses([])
        assert agg == {"native_input_mode": "", "top_rois": []}


class TestHeuristicFallback:
    def test_run_brain_pass_attaches_fingerprint_on_fallback(self, tmp_path: pathlib.Path):
        # Create one trivial text source; Tribev2 native won't be installed in
        # the test env, so we should fall through the heuristic path.
        src = tmp_path / "note.txt"
        src.write_text("A simple note about research and reasoning.", encoding="utf-8")

        result = brain_pass.run_brain_pass(
            [str(src)],
            settings={
                "enable_brain_pass": True,
                "brain_pass_native_enabled": False,  # force fallback
                "brain_pass_allow_fallback": True,
            },
        )

        assert result.provider == "fallback"
        fingerprint = result.analysis.get("fingerprint")
        assert isinstance(fingerprint, dict)
        assert len(fingerprint) > 0
        # Coherence is not available without native run, but the key exists
        # so downstream code can safely read it.
        assert "coherence" in result.analysis


class TestBrainGraphPassthrough:
    def test_node_metadata_surfaces_coherence_and_fingerprint(self):
        graph = BrainGraph()
        indexes = [
            {
                "index_id": "idx-1",
                "collection_name": "c1",
                "brain_pass": {
                    "placement": {
                        "faculty_id": "knowledge",
                        "secondary_faculty_id": "reasoning",
                    },
                    "analysis": {
                        "coherence": {"c_score": 0.42, "closure": 0.7},
                        "fingerprint": {"5": 1.2, "9": 0.6},
                    },
                },
            }
        ]
        graph.build_from_indexes_and_sessions(indexes=indexes, sessions=[], skip_layout=True)
        node = graph.nodes["index:idx-1"]
        assert node.metadata["coherence"] == {"c_score": 0.42, "closure": 0.7}
        # Keys are coerced back to ints for downstream Hebbian lookups.
        assert node.metadata["fingerprint"] == {5: 1.2, 9: 0.6}
        assert node.metadata["faculty_id"] == "knowledge"

    def test_node_metadata_tolerates_missing_analysis(self):
        graph = BrainGraph()
        indexes = [
            {
                "index_id": "idx-2",
                "collection_name": "c2",
                "brain_pass": {
                    "placement": {"faculty_id": "memory"},
                },
            }
        ]
        graph.build_from_indexes_and_sessions(indexes=indexes, sessions=[], skip_layout=True)
        node = graph.nodes["index:idx-2"]
        assert node.metadata["coherence"] is None
        assert node.metadata["fingerprint"] == {}
