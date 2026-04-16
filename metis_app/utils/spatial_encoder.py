"""metis_app.utils.spatial_encoder — Sparse spatial fingerprinting.

Maps an arbitrary vector (or integer id) onto a small, deterministic set of
"channels" with associated amplitudes.  The resulting sparse pattern is
cheap to store, comparable via Jaccard overlap, and stable across runs for
the same ``seed``.

Used by ``brain_pass`` to attach a per-document fingerprint to every source
and by ``retrieval_pipeline`` to compute query-to-node affinity without
another embedding round-trip.

Algorithm (derived from the spatial-encoding approach in
`4R7I5T/CL1_LLM_Encoder/spatial_encoder.py`):

1. A fixed random projection ``W`` of shape ``(n_channels, dim)`` is built
   lazily the first time a vector of a given dimensionality is encoded.
2. The input is projected and passed through a sigmoid.
3. The top ``active_k`` channels by activation are retained.
4. Activations are mapped linearly into ``amp_range``.

The matrix seed is deterministic in ``seed`` so two METIS installs with
the same settings produce identical fingerprints, which is important for
Hebbian persistence across index rebuilds.
"""

from __future__ import annotations

import hashlib
from typing import Iterable

import numpy as np


class SpatialFingerprint:
    """Deterministic sparse top-k channel encoder."""

    def __init__(
        self,
        n_channels: int = 62,
        active_k: int = 8,
        seed: int = 1337,
        amp_range: tuple[float, float] = (0.3, 2.5),
    ) -> None:
        if n_channels < 2:
            raise ValueError("n_channels must be >= 2")
        if not 1 <= active_k <= n_channels:
            raise ValueError("active_k must be in [1, n_channels]")
        lo, hi = amp_range
        if hi <= lo:
            raise ValueError("amp_range must be (lo, hi) with hi > lo")

        self.n_channels = int(n_channels)
        self.active_k = int(active_k)
        self.seed = int(seed)
        self.amp_lo = float(lo)
        self.amp_hi = float(hi)
        self._projections: dict[int, np.ndarray] = {}

    # ------------------------------------------------------------------
    # Core
    # ------------------------------------------------------------------

    def _projection(self, dim: int) -> np.ndarray:
        """Lazily build and cache a projection matrix of shape (C, dim)."""
        cached = self._projections.get(dim)
        if cached is not None:
            return cached
        rng = np.random.default_rng(self.seed ^ (dim * 2654435761 & 0xFFFFFFFF))
        matrix = rng.standard_normal((self.n_channels, dim)).astype(np.float32)
        # Row-normalise so vector magnitude doesn't dominate channel selection.
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        matrix /= norms
        self._projections[dim] = matrix
        return matrix

    def _top_k_amplitudes(self, activations: np.ndarray) -> dict[int, float]:
        if activations.size == 0:
            return {}
        k = min(self.active_k, activations.size)
        top_idx = np.argpartition(activations, -k)[-k:]
        top_vals = activations[top_idx]
        order = np.argsort(-top_vals)
        top_idx = top_idx[order]
        top_vals = top_vals[order]
        # Map activations (expected to be 0..1 via sigmoid) into amp_range.
        span = self.amp_hi - self.amp_lo
        amps = self.amp_lo + span * np.clip(top_vals, 0.0, 1.0)
        return {int(ch): float(a) for ch, a in zip(top_idx, amps)}

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def encode_vector(self, vector: Iterable[float]) -> dict[int, float]:
        """Encode a numeric vector as a sparse channel→amplitude map."""
        arr = np.asarray(list(vector), dtype=np.float32)
        if arr.ndim != 1 or arr.size == 0:
            return {}
        projected = self._projection(arr.size) @ arr
        activations = 1.0 / (1.0 + np.exp(-projected))
        return self._top_k_amplitudes(activations)

    def encode_id(self, item_id: int | str) -> dict[int, float]:
        """Encode an opaque id (int or string) via deterministic hashing."""
        if isinstance(item_id, int):
            payload = item_id.to_bytes(8, "little", signed=False)
        else:
            payload = str(item_id).encode("utf-8", errors="ignore")
        digest = hashlib.blake2b(payload, digest_size=32).digest()
        rng = np.random.default_rng(np.frombuffer(digest, dtype=np.uint32))
        vector = rng.standard_normal(self.n_channels).astype(np.float32)
        activations = 1.0 / (1.0 + np.exp(-vector))
        return self._top_k_amplitudes(activations)

    # ------------------------------------------------------------------
    # Comparison helpers
    # ------------------------------------------------------------------

    @staticmethod
    def similarity(a: dict[int, float], b: dict[int, float]) -> float:
        """Weighted Jaccard similarity between two fingerprints.

        Returns 0.0 if either fingerprint is empty.  Values closer to 1.0
        indicate stronger overlap in both channel selection and amplitude.
        """
        if not a or not b:
            return 0.0
        keys = set(a) | set(b)
        num = 0.0
        den = 0.0
        for k in keys:
            va = a.get(k, 0.0)
            vb = b.get(k, 0.0)
            num += min(va, vb)
            den += max(va, vb)
        return float(num / den) if den > 0 else 0.0

    @staticmethod
    def overlap(a: dict[int, float], b: dict[int, float]) -> int:
        """Count of channels active in both fingerprints."""
        return len(set(a) & set(b))
