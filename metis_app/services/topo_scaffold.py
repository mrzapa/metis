"""Topological scaffold utilities for weighted BrainGraph structures.

This module computes lightweight, graph-based approximations of homological
signals used by the METIS brain visualization and companion context.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from metis_app.models.brain_graph import BrainGraph


@dataclass(slots=True)
class PersistencePair:
    birth: float
    death: float
    dimension: int
    node_ids: list[str]


@dataclass(slots=True)
class ScaffoldResult:
    betti_0: int
    betti_1: int
    h0_pairs: list[PersistencePair]
    h1_pairs: list[PersistencePair]
    scaffold_edges: list[tuple[str, str, float, int]]
    summary: str


class _UnionFind:
    def __init__(self, node_ids: list[str]) -> None:
        self.parent = {node_id: node_id for node_id in node_ids}
        self.rank = {node_id: 0 for node_id in node_ids}

    def find(self, node_id: str) -> str:
        parent = self.parent[node_id]
        if parent != node_id:
            self.parent[node_id] = self.find(parent)
        return self.parent[node_id]

    def union(self, left: str, right: str) -> bool:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return False

        left_rank = self.rank[left_root]
        right_rank = self.rank[right_root]
        if left_rank < right_rank:
            self.parent[left_root] = right_root
        elif left_rank > right_rank:
            self.parent[right_root] = left_root
        else:
            self.parent[right_root] = left_root
            self.rank[left_root] += 1
        return True


def _norm_edge(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


def _build_weight_lookup(graph: BrainGraph) -> dict[tuple[str, str], float]:
    lookup: dict[tuple[str, str], float] = {}
    for edge in graph.edges:
        key = _norm_edge(edge.source_id, edge.target_id)
        lookup[key] = max(lookup.get(key, 0.0), float(edge.weight or 0.0))
    return lookup


def _build_tree_adjacency(tree_edges: list[tuple[str, str]]) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = {}
    for left, right in tree_edges:
        adjacency.setdefault(left, set()).add(right)
        adjacency.setdefault(right, set()).add(left)
    return adjacency


def _find_tree_path(adjacency: dict[str, set[str]], start: str, goal: str) -> list[str]:
    if start == goal:
        return [start]

    queue: list[tuple[str, list[str]]] = [(start, [start])]
    visited: set[str] = {start}
    while queue:
        node_id, path = queue.pop(0)
        for neighbor in adjacency.get(node_id, set()):
            if neighbor in visited:
                continue
            next_path = [*path, neighbor]
            if neighbor == goal:
                return next_path
            visited.add(neighbor)
            queue.append((neighbor, next_path))
    return []


def compute_scaffold(graph: BrainGraph) -> ScaffoldResult:
    """Compute graph-topology scaffold metrics for a BrainGraph."""
    node_ids = sorted(graph.nodes.keys())
    if not node_ids:
        return ScaffoldResult(
            betti_0=0,
            betti_1=0,
            h0_pairs=[],
            h1_pairs=[],
            scaffold_edges=[],
            summary="No graph nodes available for scaffold analysis.",
        )

    weighted_edges = sorted(
        graph.edges,
        key=lambda edge: float(edge.weight or 0.0),
        reverse=True,
    )

    # H0 proxy via descending-weight Kruskal merges.
    h0_pairs: list[PersistencePair] = []
    uf_h0 = _UnionFind(node_ids)
    max_weight = float(weighted_edges[0].weight) if weighted_edges else 1.0
    for edge in weighted_edges:
        if uf_h0.union(edge.source_id, edge.target_id):
            h0_pairs.append(
                PersistencePair(
                    birth=max_weight,
                    death=float(edge.weight or 0.0),
                    dimension=0,
                    node_ids=[edge.source_id, edge.target_id],
                )
            )

    betti_0 = len({uf_h0.find(node_id) for node_id in node_ids})

    # Fundamental cycle basis from non-tree edges.
    tree_uf = _UnionFind(node_ids)
    tree_edges: list[tuple[str, str]] = []
    non_tree_edges: list[tuple[str, str, float]] = []
    for edge in weighted_edges:
        left = str(edge.source_id)
        right = str(edge.target_id)
        weight = float(edge.weight or 0.0)
        if tree_uf.union(left, right):
            tree_edges.append(_norm_edge(left, right))
        else:
            non_tree_edges.append((_norm_edge(left, right)[0], _norm_edge(left, right)[1], weight))

    tree_adjacency = _build_tree_adjacency(tree_edges)
    weight_lookup = _build_weight_lookup(graph)

    h1_pairs: list[PersistencePair] = []
    persistence_scores: dict[tuple[str, str], float] = {}
    frequency_scores: dict[tuple[str, str], int] = {}

    for left, right, closing_weight in non_tree_edges:
        path = _find_tree_path(tree_adjacency, left, right)
        if len(path) < 2:
            continue

        cycle_nodes = path
        cycle_edges = [_norm_edge(path[index], path[index + 1]) for index in range(len(path) - 1)]
        cycle_edges.append(_norm_edge(left, right))

        # Use smallest edge weight in the cycle as a persistence proxy.
        cycle_weight = min(weight_lookup.get(edge_key, closing_weight) for edge_key in cycle_edges)
        persistence_value = max(0.05, cycle_weight)

        h1_pairs.append(
            PersistencePair(
                birth=closing_weight,
                death=0.0,
                dimension=1,
                node_ids=cycle_nodes,
            )
        )

        for edge_key in cycle_edges:
            persistence_scores[edge_key] = persistence_scores.get(edge_key, 0.0) + persistence_value
            frequency_scores[edge_key] = frequency_scores.get(edge_key, 0) + 1

    scaffold_edges = sorted(
        [
            (left, right, round(persistence_scores[(left, right)], 6), frequency_scores[(left, right)])
            for left, right in persistence_scores
        ],
        key=lambda item: (item[2], item[3]),
        reverse=True,
    )

    betti_1 = len(h1_pairs)
    strongest = scaffold_edges[0][2] if scaffold_edges else 0.0
    summary = (
        f"Topology snapshot: {betti_0} connected region(s), {betti_1} integration loop(s), "
        f"strongest scaffold edge score {strongest:.2f}."
    )

    return ScaffoldResult(
        betti_0=betti_0,
        betti_1=betti_1,
        h0_pairs=h0_pairs,
        h1_pairs=h1_pairs,
        scaffold_edges=scaffold_edges,
        summary=summary,
    )


def scaffold_to_payload(result: ScaffoldResult) -> dict[str, Any]:
    return {
        "betti_0": result.betti_0,
        "betti_1": result.betti_1,
        "h0_pairs": [
            {
                "birth": item.birth,
                "death": item.death,
                "dimension": item.dimension,
                "node_ids": item.node_ids,
            }
            for item in result.h0_pairs
        ],
        "h1_pairs": [
            {
                "birth": item.birth,
                "death": item.death,
                "dimension": item.dimension,
                "node_ids": item.node_ids,
            }
            for item in result.h1_pairs
        ],
        "scaffold_edges": [
            {
                "source_id": left,
                "target_id": right,
                "persistence_weight": persistence,
                "frequency_weight": frequency,
            }
            for left, right, persistence, frequency in result.scaffold_edges
        ],
        "summary": result.summary,
    }
