"""Tests for the star clustering service (M24 Phase 1, Task 1.2).

The service replaces the faculty-anchor placement system from M02 / ADR
0006 with content-embedding clusters projected to 2D canvas space. See
``docs/adr/0019-constellation-ia-content-first-projects.md``.
"""

from __future__ import annotations

import numpy as np

from metis_app.services.star_clustering_service import (
    StarClusterAssignment,
    StarClusteringService,
)


def test_compute_clusters_groups_similar_embeddings() -> None:
    """Five embeddings, two natural clusters → service returns two cluster IDs."""
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

    # One assignment per input star.
    assert len(assignments) == 5
    assert {a.star_id for a in assignments} == set(embeddings.keys())

    # star_a, star_b, star_c are in the same cluster.
    by_id = {a.star_id: a for a in assignments}
    assert by_id["star_a"].cluster_id == by_id["star_b"].cluster_id
    assert by_id["star_b"].cluster_id == by_id["star_c"].cluster_id

    # star_d, star_e are in a different cluster from the first three.
    assert by_id["star_d"].cluster_id == by_id["star_e"].cluster_id
    assert by_id["star_a"].cluster_id != by_id["star_d"].cluster_id


def test_compute_clusters_returns_2d_coordinates() -> None:
    """Each assignment has finite (x, y) screen-space coordinates in [-1, 1]."""
    rng = np.random.default_rng(seed=42)
    embeddings = {f"star_{i}": rng.random(8) for i in range(10)}
    service = StarClusteringService()
    assignments = service.compute_clusters(embeddings)

    assert len(assignments) == 10
    for a in assignments:
        assert isinstance(a.x, float)
        assert isinstance(a.y, float)
        assert -1.0 <= a.x <= 1.0
        assert -1.0 <= a.y <= 1.0


def test_compute_clusters_handles_empty_input() -> None:
    """Empty input → empty output, no errors."""
    service = StarClusteringService()
    assignments = service.compute_clusters({})
    assert assignments == []


def test_compute_clusters_single_star() -> None:
    """One star → one assignment at cluster_id=0, centred at the origin."""
    embeddings = {"only_star": np.array([0.5, 0.5, 0.5, 0.5])}
    service = StarClusteringService()
    assignments = service.compute_clusters(embeddings)

    assert len(assignments) == 1
    assert assignments[0] == StarClusterAssignment(
        star_id="only_star",
        cluster_id=0,
        x=0.0,
        y=0.0,
    )


def test_compute_clusters_accepts_list_of_floats_for_embedding() -> None:
    """Embeddings supplied as plain `list[float]` are normalised to ndarray."""
    embeddings = {
        "star_a": [1.0, 1.0, 0.0, 0.0],
        "star_b": [0.95, 1.05, 0.0, 0.0],
        "star_c": [0.0, 0.0, 1.0, 1.0],
    }
    service = StarClusteringService()
    assignments = service.compute_clusters(embeddings)
    assert len(assignments) == 3
    by_id = {a.star_id: a for a in assignments}
    # Coords are valid floats.
    for a in assignments:
        assert -1.0 <= a.x <= 1.0
        assert -1.0 <= a.y <= 1.0
    # The two close embeddings should land in the same cluster.
    assert by_id["star_a"].cluster_id == by_id["star_b"].cluster_id


def test_compute_clusters_pads_when_embedding_dim_below_pca_components() -> None:
    """Inputs with fewer dims than `pca_components` shouldn't crash PCA."""
    embeddings = {
        "star_a": np.array([1.0]),
        "star_b": np.array([2.0]),
        "star_c": np.array([3.0]),
    }
    service = StarClusteringService(pca_components=2)
    assignments = service.compute_clusters(embeddings)
    assert len(assignments) == 3
    # All assignments have valid (x, y) — the second axis was padded with zeros.
    for a in assignments:
        assert -1.0 <= a.x <= 1.0
        assert -1.0 <= a.y <= 1.0
