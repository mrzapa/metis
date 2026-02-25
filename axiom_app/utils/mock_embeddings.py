"""axiom_app.utils.mock_embeddings — Deterministic embeddings for testing.

``MockEmbeddings`` produces fixed-length vectors from SHA-256 digests so
tests and offline smoke-runs are completely reproducible without any
ML model on disk.

The class exposes the same ``embed_documents`` / ``embed_query`` interface
used by the LangChain embedding adapters, so it is a drop-in replacement
during development.

Migrated from the top of ``agentic_rag_gui.py``; that module now imports
from here so the single source of truth lives in the testable package.
"""

from __future__ import annotations

import hashlib


class MockEmbeddings:
    """Small deterministic embeddings backend for local/test use.

    Parameters
    ----------
    dimensions:
        Length of each embedding vector.  Clamped to a minimum of 8.
        Defaults to 32.

    Notes
    -----
    Each text is hashed with SHA-256; the 32-byte digest is sampled
    cyclically to fill the requested number of dimensions.  Each raw
    byte ``b`` maps to ``(b / 255) * 2 - 1``, giving values in [-1, 1].
    The result is therefore:

    * **Deterministic** — identical text always produces identical vectors.
    * **Fast** — no model loading, no network calls.
    * **Reasonably spread** — SHA-256 avalanche effect means similar texts
      produce dissimilar vectors, which is good enough for functional tests.
    """

    def __init__(self, dimensions: int = 32) -> None:
        self.dimensions = max(8, int(dimensions))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _embed(self, text: str) -> list[float]:
        payload = (text or "").encode("utf-8", errors="ignore")
        digest = hashlib.sha256(payload).digest()
        return [
            (digest[idx % len(digest)] / 255.0) * 2.0 - 1.0
            for idx in range(self.dimensions)
        ]

    # ------------------------------------------------------------------
    # Public interface (mirrors LangChain Embeddings protocol)
    # ------------------------------------------------------------------

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per document in *texts*."""
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        """Return a single embedding vector for a query string."""
        return self._embed(text)
