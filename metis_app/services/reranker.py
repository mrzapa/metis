"""Re-ranking utilities for fusing multiple retrieval signals.

Provides:

* **Reciprocal Rank Fusion (RRF)** – merges ranked lists from different
  retrieval strategies (vector similarity, knowledge-graph, keyword/BM25)
  into a single ranking.  This is the same algorithm used in production RAG
  systems like ApeRAG and Elasticsearch.

* **Keyword (BM25-lite) scoring** – a lightweight keyword-match scorer that
  requires no external dependencies.  Provides a complementary signal to
  dense-vector similarity.

The public entry point is :func:`rerank_hits`, called from
``select_hit_indices`` when ``use_reranker`` is ``True``.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any


# ---------------------------------------------------------------------------
# Reciprocal Rank Fusion
# ---------------------------------------------------------------------------

def reciprocal_rank_fusion(
    *ranked_lists: list[int],
    k: int = 60,
) -> list[int]:
    """Fuse several ranked index lists using Reciprocal Rank Fusion.

    Parameters
    ----------
    *ranked_lists:
        Each argument is a list of chunk indices ordered best-first.
    k:
        RRF constant (default 60, as in the original paper).

    Returns
    -------
    list[int]
        Chunk indices sorted by fused score (highest first).
    """
    scores: dict[int, float] = {}
    for ranked in ranked_lists:
        for rank, idx in enumerate(ranked, start=1):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda idx: scores[idx], reverse=True)


# ---------------------------------------------------------------------------
# Lightweight keyword (BM25-lite) scorer
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"\w+", re.UNICODE)

# Common English stop-words to exclude from scoring.
_STOP_WORDS = frozenset(
    "a an the is was are were be been being have has had do does did "
    "will would shall should may might can could must need to of in for "
    "on at by from with as into about up out over between through after "
    "and or but not no nor so yet if then else when how what which who "
    "whom where why all each both few many much some any its it he she "
    "they them their his her this that these those i my me we our you your".split()
)


def _tokenise(text: str) -> list[str]:
    """Lowercase word tokenisation with stop-word removal."""
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOP_WORDS]


def bm25_score_chunks(
    question: str,
    chunks: list[dict[str, Any]],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    """Score each chunk against *question* using a simplified BM25 formula.

    This is a self-contained BM25 implementation that requires only the
    question and the chunk texts — no pre-computed index is needed.

    Parameters
    ----------
    question:
        User query string.
    chunks:
        List of chunk dicts (must contain ``"text"`` key).
    k1, b:
        Standard BM25 tuning parameters.

    Returns
    -------
    list[float]
        One score per chunk, higher is better.
    """
    q_terms = _tokenise(question)
    if not q_terms or not chunks:
        return [0.0] * len(chunks)

    # Pre-tokenise all chunks.
    chunk_tokens = [_tokenise(str(c.get("text", ""))) for c in chunks]
    doc_lens = [len(tokens) for tokens in chunk_tokens]
    avg_dl = sum(doc_lens) / max(len(doc_lens), 1)
    n = len(chunks)

    # Document frequency of each query term.
    df: dict[str, int] = Counter()
    for tokens in chunk_tokens:
        unique = set(tokens)
        for qt in q_terms:
            if qt in unique:
                df[qt] += 1

    # Compute BM25 score per chunk.
    scores: list[float] = []
    for i, tokens in enumerate(chunk_tokens):
        tf_map = Counter(tokens)
        score = 0.0
        dl = doc_lens[i]
        for qt in q_terms:
            tf = tf_map.get(qt, 0)
            if tf == 0:
                continue
            idf = math.log((n - df[qt] + 0.5) / (df[qt] + 0.5) + 1.0)
            numerator = tf * (k1 + 1)
            denominator = tf + k1 * (1 - b + b * dl / max(avg_dl, 1))
            score += idf * numerator / denominator
        scores.append(score)
    return scores


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def rerank_hits(
    bundle: Any,
    question: str,
    vector_ranked: list[int],
    graph_hits: list[int],
    settings: dict[str, Any],
) -> list[int]:
    """Re-rank chunk indices by fusing vector, keyword, and KG signals.

    Parameters
    ----------
    bundle:
        An ``IndexBundle`` (must have ``.chunks`` attribute).
    question:
        The user query.
    vector_ranked:
        Chunk indices ordered by vector similarity (best first).
    graph_hits:
        Chunk indices returned by knowledge graph traversal.
    settings:
        App settings dict (uses ``top_k`` and ``retrieval_k``).

    Returns
    -------
    list[int]
        Final ranked chunk indices, length capped to ``top_k``.
    """
    top_k = int(settings.get("top_k", 5))
    retrieval_k = int(settings.get("retrieval_k", 25))

    # Compute keyword-based ranking for the retrieval pool.
    pool_indices = vector_ranked[:retrieval_k]
    if not pool_indices or not hasattr(bundle, "chunks"):
        return vector_ranked[:top_k]

    bm25_scores = bm25_score_chunks(question, bundle.chunks)
    keyword_ranked = sorted(pool_indices, key=lambda idx: bm25_scores[idx], reverse=True)

    # Build the ranked lists to fuse.
    lists_to_fuse: list[list[int]] = [vector_ranked[:retrieval_k]]

    if keyword_ranked:
        lists_to_fuse.append(keyword_ranked)

    if graph_hits:
        lists_to_fuse.append(graph_hits)

    fused = reciprocal_rank_fusion(*lists_to_fuse)
    return fused[:top_k]


__all__ = [
    "bm25_score_chunks",
    "reciprocal_rank_fusion",
    "rerank_hits",
]
