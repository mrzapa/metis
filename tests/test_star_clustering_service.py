"""Tests for the M24 star clustering service.

See ADR 0019 (Constellation IA — content-first projects) and the M24
implementation plan at
``docs/plans/2026-05-03-constellation-ia-reset-m24-implementation.md``.
"""

from __future__ import annotations

import numpy as np

from metis_app.services.star_clustering_service import (
    StarClusterAssignment,
    StarClusteringService,
)


def test_compute_clusters_groups_similar_embeddings():
    """Five embeddings, two natural clusters -> service returns two cluster IDs."""
    # Two tight clusters in 4-dim space.
    embeddings = {
        "star_a": np.array([1.0, 1.0, 0.0, 0.0]),
        "star_b": np.array([0.95, 1.05, 0.0, 0.0]),
        "star_c": np.array([1.05, 0.95, 0.0, 0.0]),
        "star_d": np.array([0.0, 0.0, 1.0, 1.0]),
        "star_e": np.array([0.0, 0.0, 0.95, 1.05]),
    }
    service = StarClusteringService()
    assignments = service.compute_clusters(embeddings)

    # Five assignments returned.
    assert len(assignments) == 5
    assert all(isinstance(a, StarClusterAssignment) for a in assignments)

    # star_a, star_b, star_c are in the same cluster.
    cluster_a = next(a.cluster_id for a in assignments if a.star_id == "star_a")
    cluster_b = next(a.cluster_id for a in assignments if a.star_id == "star_b")
    cluster_c = next(a.cluster_id for a in assignments if a.star_id == "star_c")
    assert cluster_a == cluster_b == cluster_c

    # star_d, star_e are in a different cluster.
    cluster_d = next(a.cluster_id for a in assignments if a.star_id == "star_d")
    cluster_e = next(a.cluster_id for a in assignments if a.star_id == "star_e")
    assert cluster_d == cluster_e
    assert cluster_a != cluster_d


def test_compute_clusters_returns_2d_coordinates():
    """Each assignment has finite (x, y) screen-space coordinates in [-1, 1]."""
    rng = np.random.default_rng(seed=0)
    embeddings = {f"star_{i}": rng.random(8) for i in range(10)}
    service = StarClusteringService()
    assignments = service.compute_clusters(embeddings)

    assert len(assignments) == 10
    for a in assignments:
        assert isinstance(a.x, float)
        assert isinstance(a.y, float)
        assert np.isfinite(a.x)
        assert np.isfinite(a.y)
        assert -1.0 <= a.x <= 1.0
        assert -1.0 <= a.y <= 1.0


def test_compute_clusters_handles_empty_input():
    service = StarClusteringService()
    assignments = service.compute_clusters({})
    assert assignments == []


def test_compute_clusters_single_star():
    """One star -> one assignment at the origin with cluster_id = 0."""
    embeddings = {"only_star": np.array([0.5, 0.5, 0.5, 0.5])}
    service = StarClusteringService()
    assignments = service.compute_clusters(embeddings)

    assert len(assignments) == 1
    assert assignments[0].star_id == "only_star"
    assert assignments[0].cluster_id == 0
    assert assignments[0].x == 0.0
    assert assignments[0].y == 0.0
