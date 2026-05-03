"""Cluster stars by content embedding into 2D screen-space positions.

Replaces the M02 / ADR 0006 faculty-anchor placement system with
content-embedding clusters projected to 2D for canvas rendering.

Per ADR 0019 (*Constellation IA: content-first projects*), this service
is the M24 placement engine. M25 layers Project pull-strength on top of
cluster centroids; M26 retires the backend faculty signal once eval
gates pass.

The service is deliberately stateless and dependency-free of the rest
of the engine: callers (the orchestrator + the Litestar route) supply a
``dict[str, np.ndarray | list[float]]`` of star embeddings and receive
a flat list of :class:`StarClusterAssignment` records back. Caching,
freshness, and embedding extraction live in the orchestrator wiring
(Task 1.3).

HDBSCAN is the default clusterer for two reasons: it doesn't require a
``k`` parameter (the constellation grows organically and we don't want
an a-priori cluster count), and it labels low-density points as noise
(``cluster_id = -1``) instead of forcing them into a misleading
neighbour. PCA is the default 2D projection for speed + interpretability;
swap for UMAP if a future eval shows clusters reading as muddy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
from sklearn.cluster import HDBSCAN
from sklearn.decomposition import PCA

EmbeddingLike = np.ndarray | Sequence[float]


@dataclass(slots=True)
class StarClusterAssignment:
    """One star's cluster identity + 2D canvas position.

    Coordinates are normalised to the closed interval ``[-1, 1]`` on
    both axes so the frontend can scale them to whatever canvas size it
    has without the service knowing viewport details.
    """

    #: Stable identifier supplied by the caller (typically `index_id`).
    star_id: str
    #: HDBSCAN label. ``-1`` is the noise label; ``>=0`` is a real cluster.
    cluster_id: int
    #: Normalised x in ``[-1, 1]``.
    x: float
    #: Normalised y in ``[-1, 1]``.
    y: float
    #: Filled later by a label generator (TF-IDF + LLM, M24 Phase 1.x). Empty until then.
    cluster_label: str = ""


class StarClusteringService:
    """Compute cluster assignments + 2D layout for a set of star embeddings.

    Parameters
    ----------
    min_cluster_size:
        Forwarded to :class:`sklearn.cluster.HDBSCAN`. Two is the
        smallest cluster HDBSCAN will accept; matches the design's
        "small constellation" use case where pinning a 5-cluster
        minimum would force everything into noise.
    pca_components:
        Output dimensionality of the projection. Always 2 for the M24
        canvas; exposed so future visualisations (3D BrainGraph
        overlay, tile map) can reuse the service.
    """

    def __init__(
        self,
        *,
        min_cluster_size: int = 2,
        pca_components: int = 2,
    ) -> None:
        if min_cluster_size < 2:
            raise ValueError("min_cluster_size must be >= 2 for HDBSCAN")
        if pca_components < 1:
            raise ValueError("pca_components must be >= 1")
        self._min_cluster_size = min_cluster_size
        self._pca_components = pca_components

    def compute_clusters(
        self,
        embeddings: Mapping[str, EmbeddingLike],
    ) -> list[StarClusterAssignment]:
        """Cluster + project. Returns one assignment per input star.

        Edge cases:
        - Empty input → empty output.
        - Single star → ``cluster_id = 0`` at the origin (HDBSCAN
          requires at least two points).
        - Embedding dim below ``pca_components`` → pad missing axes
          with zeros so PCA doesn't crash on a degenerate matrix.
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

        # Stack into a homogeneous float64 matrix. ``np.asarray`` accepts
        # ndarrays unchanged and converts list[float] / tuple[float, …]
        # callers supply.
        matrix = np.asarray(
            [np.asarray(embeddings[sid], dtype=np.float64) for sid in star_ids]
        )

        # Cluster. HDBSCAN labels low-density points as -1; we surface
        # that as ``cluster_id = -1`` so the frontend can render them as
        # untethered "drift" stars rather than forcing them into a
        # misleading group.
        clusterer = HDBSCAN(min_cluster_size=self._min_cluster_size)
        cluster_labels = clusterer.fit_predict(matrix)

        # Project to 2D. PCA's components must not exceed the input
        # dimensionality, so pad shorter embeddings with zero-axes.
        if matrix.shape[1] >= self._pca_components:
            pca = PCA(n_components=self._pca_components)
            coords = pca.fit_transform(matrix)
        else:
            padded = np.zeros((len(star_ids), self._pca_components))
            padded[:, : matrix.shape[1]] = matrix
            coords = padded

        # Normalise to the closed interval [-1, 1] on whichever axis has
        # the largest absolute value. The 1e-9 floor prevents a divide-
        # by-zero when every coordinate is exactly zero (e.g. a tiny
        # cluster of identical embeddings).
        max_abs = max(abs(coords.min()), abs(coords.max()), 1e-9)
        coords = coords / max_abs

        # Pad coords to width ``pca_components`` if PCA returned fewer
        # axes (degenerate matrices can collapse to 1D).
        if coords.shape[1] < self._pca_components:
            padded = np.zeros((coords.shape[0], self._pca_components))
            padded[:, : coords.shape[1]] = coords
            coords = padded

        return [
            StarClusterAssignment(
                star_id=sid,
                cluster_id=int(label),
                x=float(coords[i, 0]),
                y=float(coords[i, 1]),
            )
            for i, (sid, label) in enumerate(zip(star_ids, cluster_labels))
        ]
