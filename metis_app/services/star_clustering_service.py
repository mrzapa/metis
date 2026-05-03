"""Cluster stars by content embedding into 2D screen-space positions.

Replaces the M02 / ADR 0006 faculty-anchor placement system. Stars are
grouped by content fingerprint and projected to 2D for canvas rendering.

Per ADR 0019, this service is the M24 placement engine. M25 will layer
Project-pull on top of cluster centroids; for now the projection is
purely content-driven.

See:
- ``docs/adr/0019-constellation-ia-content-first-projects.md``
- ``docs/plans/2026-05-03-constellation-ia-reset-design.md``
- ``docs/plans/2026-05-03-constellation-ia-reset-m24-implementation.md``
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import PCA


@dataclass(slots=True)
class StarClusterAssignment:
    """One star's cluster ID + 2D canvas position.

    Attributes:
        star_id: Stable identifier supplied by the caller.
        cluster_id: HDBSCAN label. ``-1`` means noise / unclustered;
            non-negative integers identify a real cluster.
        x, y: Projected 2D coordinates, normalised into ``[-1, 1]`` so
            the frontend canvas can map them directly to its viewport.
        cluster_label: Human-readable label, populated by a later stage
            (TF-IDF + LLM); empty by default.
    """

    star_id: str
    cluster_id: int
    x: float
    y: float
    cluster_label: str = ""


class StarClusteringService:
    """Compute cluster assignments and 2D layout for star embeddings."""

    def __init__(
        self,
        *,
        min_cluster_size: int = 2,
        pca_components: int = 2,
    ) -> None:
        self._min_cluster_size = min_cluster_size
        self._pca_components = pca_components

    def compute_clusters(
        self,
        embeddings: dict[str, np.ndarray | list[float]],
    ) -> list[StarClusterAssignment]:
        """Cluster + project. Returns one assignment per input star.

        Edge cases:
        - Empty input ``{}`` -> ``[]``.
        - Single star -> one assignment at the origin, ``cluster_id=0``.
        - Embedding dim < ``pca_components`` -> coordinates are padded
          with zeros along the missing axes before normalisation.

        Note: HDBSCAN with ``min_cluster_size=2`` labels all stars as
        noise (``cluster_id=-1``) until the input has roughly 5+ stars.
        Frontend code must render ``cluster_id=-1`` gracefully (treat as
        "no cluster yet").
        """
        if not embeddings:
            return []

        star_ids = list(embeddings.keys())

        if len(star_ids) == 1:
            return [
                StarClusterAssignment(
                    star_id=star_ids[0],
                    cluster_id=0,
                    x=0.0,
                    y=0.0,
                )
            ]

        # Stack into a (n_stars, n_dims) float matrix.
        matrix = np.asarray(
            [np.asarray(embeddings[sid], dtype=np.float64) for sid in star_ids]
        )

        # Cluster (HDBSCAN; noise -> cluster_id = -1).
        clusterer = HDBSCAN(min_cluster_size=self._min_cluster_size)
        cluster_labels = clusterer.fit_predict(matrix)

        # Project to 2D. Fall back to zero-padding if input dim is too small.
        if matrix.shape[1] >= self._pca_components:
            pca = PCA(n_components=self._pca_components)
            coords = pca.fit_transform(matrix)
        else:
            coords = np.zeros((len(star_ids), self._pca_components))
            coords[:, : matrix.shape[1]] = matrix

        # Normalise coords to [-1, 1] by dividing by the global max-abs.
        max_abs = max(abs(float(coords.min())), abs(float(coords.max())), 1e-9)
        coords = coords / max_abs

        return [
            StarClusterAssignment(
                star_id=sid,
                cluster_id=int(label),
                x=float(coords[i, 0]),
                y=float(coords[i, 1]),
            )
            for i, (sid, label) in enumerate(zip(star_ids, cluster_labels))
        ]
