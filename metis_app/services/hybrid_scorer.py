"""Hybrid BM25 + vector score blending for METIS retrieval.

Ported from Onyx's alpha-blending approach: normalise both score arrays to
[0, 1] within the candidate window, then take a convex combination.

    hybrid_score = alpha * vector_score + (1 - alpha) * bm25_score

alpha=1.0  → pure vector  (default, identical to current behaviour)
alpha=0.0  → pure BM25
alpha=0.5  → equal blend  (recommended for most corpora)
"""

from __future__ import annotations

from typing import Any


def _minmax(values: list[float]) -> list[float]:
    """Min-max normalise *values* to the [0, 1] range.

    If all values are equal, returns a list of 1.0s so the caller's weighted
    sum still produces a meaningful result.
    """
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    if hi == lo:
        return [1.0] * len(values)
    span = hi - lo
    return [(v - lo) / span for v in values]


def hybrid_rerank(
    chunks: list[dict[str, Any]],
    hit_indices: list[int],
    vector_scores: dict[int, float],
    question: str,
    alpha: float,
) -> list[int]:
    """Re-rank *hit_indices* using alpha-blended BM25 + vector scores.

    Parameters
    ----------
    chunks:
        All indexed chunks (``bundle.chunks``).  Only the chunks referenced by
        *hit_indices* are scored — scoring is fast regardless of total corpus
        size because BM25 is computed over the candidate window only.
    hit_indices:
        Ordered candidate indices returned by the vector adapter.
    vector_scores:
        Mapping of chunk index → cosine similarity score, reconstructed from
        ``QueryResult.sources`` as ``{s.chunk_idx: s.score for s in sources}``.
    question:
        The raw query string; tokenised by simple whitespace split.
    alpha:
        Blend weight in [0.0, 1.0].  ``alpha >= 1.0`` is a no-op (returns
        *hit_indices* unchanged, preserving exact current behaviour).

    Returns
    -------
    list[int]
        *hit_indices* re-ordered by descending hybrid score.
    """
    if alpha >= 1.0 or not hit_indices:
        return hit_indices

    try:
        from rank_bm25 import BM25Okapi  # type: ignore[import]
    except ImportError as exc:
        # Graceful degradation: if rank_bm25 is not installed fall back to
        # pure vector ordering rather than crashing.
        import logging
        logging.getLogger(__name__).warning(
            "rank_bm25 is not installed; falling back to pure vector ranking. "
            "Install it with: pip install rank-bm25  (%s)",
            exc,
        )
        return hit_indices

    # Build BM25 over the candidate window (not the entire corpus).
    candidates = [chunks[i] for i in hit_indices if 0 <= i < len(chunks)]
    if not candidates:
        return hit_indices

    tokenized = [str(c.get("text") or "").lower().split() for c in candidates]
    bm25 = BM25Okapi(tokenized)
    query_tokens = str(question).lower().split()
    bm25_raw: list[float] = list(bm25.get_scores(query_tokens))

    vec_vals: list[float] = [
        float(vector_scores.get(idx, 0.0)) for idx in hit_indices
    ]

    bm25_norm = _minmax(bm25_raw)
    vec_norm = _minmax(vec_vals)

    blended: dict[int, float] = {
        idx: alpha * vec_norm[k] + (1.0 - alpha) * bm25_norm[k]
        for k, idx in enumerate(hit_indices)
        if k < len(bm25_norm) and k < len(vec_norm)
    }
    # Any hit_indices that were out-of-range for chunks get appended at the end
    missing = [i for i in hit_indices if i not in blended]
    return sorted(blended, key=blended.__getitem__, reverse=True) + missing


__all__ = ["hybrid_rerank"]
