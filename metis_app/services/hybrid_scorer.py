"""Hybrid BM25 + dense-vector reranking (Onyx-style alpha blending).

The alpha parameter controls the blend between the two signal types:
  alpha = 1.0  → pure dense/vector ranking  (no change from default behaviour)
  alpha = 0.0  → pure BM25/keyword ranking
  alpha = 0.5  → equal weight (recommended starting point for hybrid search)

Both score lists are independently min-max normalised to [0, 1] before blending
so that scale differences between BM25 and cosine-similarity scores do not skew
the final ranking.
"""

from __future__ import annotations

import re
from typing import Any


def _tokenize(text: str) -> list[str]:
    """Very lightweight whitespace + punctuation tokenizer (no extra deps)."""
    return re.findall(r"\w+", text.lower())


def _idf(term: str, corpus: list[list[str]], df_cache: dict[str, int]) -> float:
    import math

    if term not in df_cache:
        df_cache[term] = sum(1 for doc in corpus if term in doc)
    df = df_cache[term]
    n = len(corpus)
    return math.log((n - df + 0.5) / (df + 0.5) + 1.0)


def bm25_scores(
    query: str,
    texts: list[str],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    """Return per-document BM25 scores for *query* against *texts*.

    Falls back to the ``rank_bm25`` package when available; otherwise uses a
    pure-Python implementation so the scorer works with no optional deps.
    """
    if not texts:
        return []

    # ── Try rank_bm25 first ──────────────────────────────────────────────────
    try:
        from rank_bm25 import BM25Okapi  # type: ignore[import]

        tokenized = [_tokenize(t) for t in texts]
        bm = BM25Okapi(tokenized, k1=k1, b=b)
        scores = bm.get_scores(_tokenize(query))
        return [float(s) for s in scores]
    except ImportError:
        pass

    # ── Pure-Python fallback ─────────────────────────────────────────────────
    tokenized = [_tokenize(t) for t in texts]
    avg_dl = sum(len(d) for d in tokenized) / max(len(tokenized), 1)
    df_cache: dict[str, int] = {}
    query_terms = _tokenize(query)
    scores: list[float] = []
    for doc in tokenized:
        tf_map: dict[str, int] = {}
        for token in doc:
            tf_map[token] = tf_map.get(token, 0) + 1
        score = 0.0
        dl = len(doc)
        for term in query_terms:
            tf = tf_map.get(term, 0)
            idf = _idf(term, tokenized, df_cache)
            score += idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * dl / avg_dl))
        scores.append(score)
    return scores


def _min_max_normalise(values: list[float]) -> list[float]:
    if not values:
        return values
    lo, hi = min(values), max(values)
    span = hi - lo
    if span == 0.0:
        return [0.0] * len(values)
    return [(v - lo) / span for v in values]


def hybrid_rerank(
    hit_indices: list[int],
    dense_scores: dict[int, float],
    texts: list[str],
    query: str,
    *,
    alpha: float = 1.0,
    top_k: int | None = None,
) -> list[int]:
    """Reorder *hit_indices* using an alpha-blended hybrid score.

    Parameters
    ----------
    hit_indices:
        Ordered list of chunk indices from the dense retrieval pass.
    dense_scores:
        Mapping of chunk-index → raw dense similarity score.
    texts:
        Full corpus of chunk texts (indexed by chunk position, not hit_indices).
    query:
        Original user query used for BM25 scoring.
    alpha:
        Blend weight. 1.0 = pure dense, 0.0 = pure BM25.
    top_k:
        If provided, truncate the result list to this many entries.
    """
    if not hit_indices or alpha >= 1.0:
        # Short-circuit: no BM25 work needed.
        return hit_indices[:top_k] if top_k is not None else list(hit_indices)

    # ── Dense scores for candidate set ──────────────────────────────────────
    dense_raw = [float(dense_scores.get(idx, 0.0)) for idx in hit_indices]
    dense_norm = _min_max_normalise(dense_raw)

    # ── BM25 scores for the candidate texts ─────────────────────────────────
    candidate_texts = [texts[idx] if idx < len(texts) else "" for idx in hit_indices]
    bm25_raw = bm25_scores(query, candidate_texts)
    bm25_norm = _min_max_normalise(bm25_raw)

    # ── Blend ────────────────────────────────────────────────────────────────
    blended: list[tuple[float, int]] = []
    for rank, idx in enumerate(hit_indices):
        score = alpha * dense_norm[rank] + (1.0 - alpha) * bm25_norm[rank]
        blended.append((score, idx))

    blended.sort(key=lambda x: x[0], reverse=True)
    result = [idx for _, idx in blended]
    return result[:top_k] if top_k is not None else result


def hybrid_alpha(settings: dict[str, Any]) -> float:
    """Extract and clamp hybrid_alpha from *settings*."""
    try:
        value = float(settings.get("hybrid_alpha", 1.0) or 1.0)
    except (TypeError, ValueError):
        return 1.0
    return max(0.0, min(1.0, value))


__all__ = [
    "bm25_scores",
    "hybrid_alpha",
    "hybrid_rerank",
]
