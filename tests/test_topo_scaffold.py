from __future__ import annotations

from metis_app.models.brain_graph import BrainEdge, BrainGraph, BrainNode
from metis_app.services.topo_scaffold import compute_scaffold


def _square_graph() -> BrainGraph:
    graph = BrainGraph()
    for node_id in ("a", "b", "c", "d"):
        graph.add_node(BrainNode(node_id=node_id, node_type="index", label=node_id))

    graph.add_edge(BrainEdge("a", "b", "link", weight=3.0))
    graph.add_edge(BrainEdge("b", "c", "link", weight=3.0))
    graph.add_edge(BrainEdge("c", "d", "link", weight=3.0))
    graph.add_edge(BrainEdge("d", "a", "link", weight=3.0))
    return graph


def test_compute_scaffold_detects_single_h1_loop_for_square() -> None:
    result = compute_scaffold(_square_graph())

    assert result.betti_0 == 1
    assert result.betti_1 == 1
    assert len(result.h1_pairs) == 1
    assert result.h1_pairs[0].birth == 3.0
    assert result.h1_pairs[0].death == 0.0
    assert result.scaffold_edges
    assert "integration loop" in result.summary
