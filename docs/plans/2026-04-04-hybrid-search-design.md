# Hybrid Search (BM25 + Vector) — Design

**Date:** 2026-04-04
**Inspired by:** Onyx's alpha-blended hybrid retrieval
**Status:** Approved for implementation

---

## Problem

METIS currently uses pure cosine similarity (vector-only) for all retrieval. This works well for conceptual/semantic queries but misses:

- **Exact phrases** — e.g. "Section 4.2", "RFC 2119", a person's name
- **Technical terms** — abbreviations, product codes, model numbers
- **Proper nouns** — company names, place names

Onyx solves this with a normalised alpha-blend of BM25 keyword scores + vector similarity scores, outperforming both pure-vector and rank-fusion (RRF) approaches.

---

## Design

### Architecture

```
Query
  │
  ├─► adapter.query()  →  hit_indices + vector_scores  (existing)
  │
  └─► HybridScorer     →  bm25_scores over candidate window  (new)

Both → min-max normalise → alpha * vec + (1-α) * bm25 → re-rank
```

### New file: `metis_app/services/hybrid_scorer.py`

```python
from rank_bm25 import BM25Okapi

def _minmax(values):
    lo, hi = min(values, default=0.0), max(values, default=1.0)
    if hi == lo:
        return [1.0] * len(values)
    return [(v - lo) / (hi - lo) for v in values]

def hybrid_rerank(
    chunks: list[dict],
    hit_indices: list[int],
    vector_scores: dict[int, float],
    question: str,
    alpha: float,
) -> list[int]:
    """Re-rank hit_indices using alpha-blended BM25 + vector scores.

    alpha=1.0 → pure vector (no-op, current behaviour)
    alpha=0.0 → pure BM25
    alpha=0.5 → equal blend (recommended default)
    """
    if alpha >= 1.0 or not hit_indices:
        return hit_indices

    candidates = [chunks[i] for i in hit_indices]
    tokenized = [c.get("text", "").lower().split() for c in candidates]
    bm25 = BM25Okapi(tokenized)
    bm25_raw = bm25.get_scores(question.lower().split())

    vec_vals = [vector_scores.get(i, 0.0) for i in hit_indices]
    bm25_norm = _minmax(list(bm25_raw))
    vec_norm  = _minmax(vec_vals)

    blended = {
        idx: alpha * vec_norm[k] + (1 - alpha) * bm25_norm[k]
        for k, idx in enumerate(hit_indices)
    }
    return sorted(blended, key=blended.__getitem__, reverse=True)
```

### Modified: `metis_app/services/retrieval_pipeline.py`

In `execute_retrieval_plan()`, after the primary `adapter.query()` call:

```python
from metis_app.services.hybrid_scorer import hybrid_rerank

alpha = float(settings.get("hybrid_alpha", 1.0))
primary_result = adapter.query(bundle, question, settings)

if alpha < 1.0 and bundle.chunks:
    reranked_indices = hybrid_rerank(
        bundle.chunks,
        list(primary_result.hit_indices),
        primary_result.scores,   # dict[int, float]
        question,
        alpha,
    )
    primary_result = build_query_result(
        bundle, question, reranked_indices,
        primary_result.scores, settings=settings
    )
```

Same pattern applied to each sub-query result inside the query expansion block.

### Modified: `metis_app/services/vector_store.py` — Weaviate adapter

When `hybrid_alpha < 1.0`, use Weaviate's native hybrid query instead of `near_vector`:

```python
if alpha < 1.0:
    response = collection.query.hybrid(
        query=question,
        alpha=alpha,           # Weaviate uses same convention
        limit=limit,
        return_metadata=MetadataQuery(score=True),
    )
else:
    response = collection.query.near_vector(...)
```

### Modified: `metis_app/default_settings.json`

```json
"hybrid_alpha": 0.5
```

Place after `"search_type"` key.

---

## Settings

| Key | Default | Description |
|-----|---------|-------------|
| `hybrid_alpha` | `0.5` | `1.0` = pure vector, `0.0` = pure BM25, `0.5` = balanced |

Skills can override this in their `SKILL.md` `runtime_overrides`:
- **Evidence Pack**: `hybrid_alpha: 0.3` (keyword-biased for precise claim matching)
- **Knowledge Search**: `hybrid_alpha: 0.4`
- **Research**: `hybrid_alpha: 0.5` (default)
- **Q&A**: `hybrid_alpha: 0.6` (slightly vector-biased for conceptual questions)

---

## Dependency

Add to `pyproject.toml`:
```
rank-bm25>=0.2.2
```

Pure Python, no native extensions, <5ms for 1000 chunks.

---

## Backward Compatibility

- `hybrid_alpha = 1.0` → BM25 code never runs → identical to current behaviour
- No index rebuild required — BM25 scores computed at query time from existing chunks
- JSON, Chroma backends: use `rank_bm25` in Python
- Weaviate backend: delegate to Weaviate's built-in hybrid (no `rank_bm25` needed)

---

## Files Changed

| File | Change |
|------|--------|
| `metis_app/services/hybrid_scorer.py` | **New** — BM25 scoring + normalisation + blending |
| `metis_app/services/retrieval_pipeline.py` | Apply hybrid rerank after primary query and each sub-query |
| `metis_app/services/vector_store.py` | Weaviate: swap `near_vector` → `hybrid` when `alpha < 1.0` |
| `metis_app/default_settings.json` | Add `"hybrid_alpha": 0.5` |
| `pyproject.toml` | Add `rank-bm25>=0.2.2` |

---

## Verification

1. Build an index with METIS (JSON backend)
2. Query with a technical term that appears verbatim in a document (e.g. an exact section title)
3. With `hybrid_alpha=1.0`: check if top result contains the exact phrase
4. With `hybrid_alpha=0.5`: should surface the chunk containing the exact phrase higher
5. Run existing test suite — pure-vector tests should still pass (`hybrid_alpha=1.0` in test settings)
6. Check Weaviate adapter: set `vector_db_type=weaviate`, confirm `query.hybrid()` is called when alpha < 1.0
