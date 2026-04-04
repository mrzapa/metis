"""Shared retrieval planning for batch and streaming RAG flows.

This module ports the most transferable WeKnora pattern into METIS:
retrieval is treated as a staged plan rather than a single opaque call.
The plan can be reused by batch answers, streaming runs, and retrieval-only
knowledge search.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any

from metis_app.services.hybrid_scorer import hybrid_rerank
from metis_app.services.index_service import IndexBundle, QueryResult, build_query_result
from metis_app.services.reranker import reciprocal_rank_fusion
from metis_app.utils.embedding_providers import create_embeddings
from metis_app.utils.llm_providers import create_llm
from metis_app.utils.mock_embeddings import MockEmbeddings

_EMB_DIM = 32
_DEFAULT_MIN_SCORE = 0.15
_DEFAULT_FALLBACK_MESSAGE = (
    "I couldn't find enough grounded evidence in the selected index to answer "
    "confidently. Try Knowledge Search, increase retrieval depth, or rephrase "
    "the question."
)


@dataclass(slots=True)
class FallbackDecision:
    triggered: bool = False
    strategy: str = "synthesize_anyway"
    reason: str = ""
    min_score: float = _DEFAULT_MIN_SCORE
    observed_score: float = 0.0
    message: str = _DEFAULT_FALLBACK_MESSAGE

    def to_dict(self) -> dict[str, Any]:
        return {
            "triggered": bool(self.triggered),
            "strategy": str(self.strategy or "synthesize_anyway"),
            "reason": str(self.reason or ""),
            "min_score": float(self.min_score),
            "observed_score": float(self.observed_score),
            "message": str(self.message or _DEFAULT_FALLBACK_MESSAGE),
        }


@dataclass(slots=True)
class RetrievalStage:
    stage_type: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage_type": self.stage_type,
            "payload": dict(self.payload or {}),
        }


@dataclass(slots=True)
class RetrievalPlan:
    question: str
    selected_mode: str
    result: QueryResult
    effective_queries: list[str] = field(default_factory=list)
    stages: list[RetrievalStage] = field(default_factory=list)
    fallback: FallbackDecision = field(default_factory=FallbackDecision)

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "selected_mode": self.selected_mode,
            "effective_queries": list(self.effective_queries),
            "stages": [stage.to_dict() for stage in self.stages],
            "fallback": self.fallback.to_dict(),
            "top_score": float(self.result.top_score),
            "source_count": len(self.result.sources),
        }


def _selected_mode(settings: dict[str, Any]) -> str:
    return str(settings.get("selected_mode", "Q&A") or "Q&A")


def _response_text(result: Any) -> str:
    return str(getattr(result, "content", result) or "")


def _fallback_strategy(settings: dict[str, Any]) -> str:
    raw = str(settings.get("fallback_strategy", "synthesize_anyway") or "synthesize_anyway")
    value = raw.strip().lower()
    if value in {"no_answer", "synthesize_anyway"}:
        return value
    return "synthesize_anyway"


def _fallback_message(settings: dict[str, Any]) -> str:
    return str(settings.get("fallback_message") or _DEFAULT_FALLBACK_MESSAGE).strip() or _DEFAULT_FALLBACK_MESSAGE


def _min_score(settings: dict[str, Any]) -> float:
    try:
        return max(0.0, float(settings.get("retrieval_min_score", _DEFAULT_MIN_SCORE) or _DEFAULT_MIN_SCORE))
    except (TypeError, ValueError):
        return _DEFAULT_MIN_SCORE


def _should_expand_queries(settings: dict[str, Any], *, allow_query_expansion: bool) -> bool:
    if not allow_query_expansion:
        return False
    if not bool(settings.get("use_sub_queries", False)):
        return False
    return _selected_mode(settings) in {"Research", "Knowledge Search"}


def _load_query_embeddings(settings: dict[str, Any]) -> Any:
    try:
        return create_embeddings(settings)
    except (ValueError, ImportError):
        return MockEmbeddings(dimensions=_EMB_DIM)


def _score_bundle_against_question(
    bundle: IndexBundle,
    question: str,
    settings: dict[str, Any],
) -> list[float]:
    embeddings = _load_query_embeddings(settings)
    query_vector = embeddings.embed_query(question)
    scores: list[float] = []
    for vector in bundle.embeddings:
        dot = sum(a * b for a, b in zip(query_vector, vector))
        q_norm = sum(a * a for a in query_vector) ** 0.5
        v_norm = sum(b * b for b in vector) ** 0.5
        scores.append(dot / (q_norm * v_norm) if q_norm > 0 and v_norm > 0 else 0.0)
    return scores


def generate_sub_queries(question: str, llm: Any) -> list[str]:
    system = (
        "You generate search sub-queries for retrieval. "
        "Return 3-5 concise sub-queries as a JSON array of strings. "
        "Do not include any extra text."
    )
    try:
        raw = _response_text(
            llm.invoke(
                [
                    {"type": "system", "content": system},
                    {"type": "human", "content": question},
                ]
            )
        )
        start, end = raw.find("["), raw.rfind("]") + 1
        if start == -1 or end <= start:
            return []
        payload = json.loads(raw[start:end])
        if not isinstance(payload, list):
            return []
        seen: set[str] = set()
        result: list[str] = []
        normalized_question = question.strip().lower()
        for item in payload:
            candidate = str(item).strip()
            normalized = candidate.lower()
            if not candidate or normalized == normalized_question or normalized in seen:
                continue
            seen.add(normalized)
            result.append(candidate)
        return result[:5]
    except Exception:  # noqa: BLE001
        return []


def _generate_sub_queries(question: str, settings: dict[str, Any], llm: Any | None = None) -> list[str]:
    if llm is None:
        try:
            llm = create_llm(settings)
        except Exception:  # noqa: BLE001
            return []
    return generate_sub_queries(question, llm)


def _fallback_for_result(result: QueryResult, settings: dict[str, Any]) -> FallbackDecision:
    minimum = _min_score(settings)
    strategy = _fallback_strategy(settings)
    message = _fallback_message(settings)
    if not result.sources:
        return FallbackDecision(
            triggered=True,
            strategy=strategy,
            reason="no_sources",
            min_score=minimum,
            observed_score=float(result.top_score or 0.0),
            message=message,
        )
    if float(result.top_score or 0.0) < minimum:
        return FallbackDecision(
            triggered=True,
            strategy=strategy,
            reason="score_below_threshold",
            min_score=minimum,
            observed_score=float(result.top_score or 0.0),
            message=message,
        )
    return FallbackDecision(
        triggered=False,
        strategy=strategy,
        reason="",
        min_score=minimum,
        observed_score=float(result.top_score or 0.0),
        message=message,
    )


def execute_retrieval_plan(
    bundle: IndexBundle,
    question: str,
    settings: dict[str, Any],
    *,
    adapter: Any,
    llm: Any | None = None,
    allow_query_expansion: bool = True,
    subquery_generator: Any | None = None,
    query_expander: Any | None = None,
) -> RetrievalPlan:
    """Run the retrieval pipeline and return a serialisable plan."""

    selected_mode = _selected_mode(settings)

    # --- Knowledge cache look-aside (disabled by default) ---
    _cache = None
    if settings.get("enable_knowledge_cache"):
        try:
            from metis_app.services.knowledge_cache import QueryResultCache  # noqa: PLC0415
            _cache = QueryResultCache.build(settings, index_id=bundle.index_id)
            _cached_payload = _cache.get(question)
            if _cached_payload is not None:
                from metis_app.models.session_types import EvidenceSource as _ES  # noqa: PLC0415
                _cached_sources = [
                    _ES.from_dict(s) for s in _cached_payload.get("sources") or []
                ]
                _cached_result = QueryResult(
                    prompt=str(_cached_payload.get("prompt") or ""),
                    context_block=str(_cached_payload.get("context_block") or ""),
                    sources=_cached_sources,
                    hit_indices=list(_cached_payload.get("hit_indices") or []),
                    top_score=float(_cached_payload.get("top_score") or 0.0),
                )
                return RetrievalPlan(
                    question=question,
                    selected_mode=selected_mode,
                    result=_cached_result,
                    effective_queries=[question],
                    stages=[RetrievalStage("cache_hit", {"index_id": bundle.index_id})],
                    fallback=_fallback_for_result(_cached_result, settings),
                )
        except Exception:  # noqa: BLE001
            _cache = None  # degrade gracefully; proceed with live retrieval

    primary_result = adapter.query(bundle, question, settings)

    # Hybrid rerank: blend BM25 keyword scores with vector scores (Onyx-style alpha blending).
    # alpha=1.0 (default) is a no-op — pure vector, identical to previous behaviour.
    _hybrid_alpha = float(settings.get("hybrid_alpha", 1.0) or 1.0)
    if _hybrid_alpha < 1.0 and bundle.chunks:
        _vec_scores = {
            s.chunk_idx: float(s.score)
            for s in primary_result.sources
            if s.chunk_idx is not None
        }
        _reranked = hybrid_rerank(
            bundle.chunks, list(primary_result.hit_indices),
            _vec_scores, question, _hybrid_alpha,
        )
        if _reranked != list(primary_result.hit_indices):
            primary_result = build_query_result(
                bundle, question, _reranked, _vec_scores, settings=settings,
            )

    effective_queries = [question]

    # ── Hybrid rerank primary result ─────────────────────────────────────────
    if alpha < 1.0 and primary_result.hit_indices:
        chunk_texts = [str(c.get("text") or "") for c in bundle.chunks]
        top_k = int(settings.get("top_k", 5) or 5)
        reranked_indices = hybrid_rerank(
            list(primary_result.hit_indices),
            {idx: float(s) for idx, s in zip(primary_result.hit_indices, [primary_result.top_score] * len(primary_result.hit_indices))},
            chunk_texts,
            question,
            alpha=alpha,
            top_k=top_k,
        )
        dense_scores = _score_bundle_against_question(bundle, question, settings)
        primary_result = build_query_result(bundle, question, reranked_indices, dense_scores, settings=settings)

    stages: list[RetrievalStage] = [
        RetrievalStage(
            stage_type="retrieval_complete",
            payload={
                "sources": [source.to_dict() for source in primary_result.sources],
                "context_block": primary_result.context_block,
                "top_score": float(primary_result.top_score),
            },
        )
    ]

    final_result = primary_result

    if _should_expand_queries(settings, allow_query_expansion=allow_query_expansion):
        generator = query_expander if callable(query_expander) else subquery_generator
        if callable(generator):
            try:
                sub_queries = list(generator(question, llm))
            except Exception:  # noqa: BLE001
                sub_queries = []
        else:
            sub_queries = _generate_sub_queries(question, settings, llm=llm)
        if sub_queries:
            effective_queries.extend(sub_queries)
            stages.append(
                RetrievalStage(
                    stage_type="query_expansion",
                    payload={"queries": list(sub_queries)},
                )
            )
            ranked_lists: list[list[int]] = [list(primary_result.hit_indices)]
            for sub_query in sub_queries:
                try:
                    ranked_lists.append(list(adapter.query(bundle, sub_query, settings).hit_indices))
                except Exception:  # noqa: BLE001
                    continue
            if len(ranked_lists) > 1:
                fused_indices = reciprocal_rank_fusion(*ranked_lists)
                top_k = int(settings.get("top_k", 5) or 5)
                dense_scores = _score_bundle_against_question(bundle, question, settings)
                if _hybrid_alpha < 1.0 and bundle.chunks:
                    _dense_dict = {i: float(s) for i, s in enumerate(dense_scores)}
                    # Rerank a wider candidate window before slicing to top_k
                    _candidate_pool = fused_indices[: max(top_k * 3, top_k)]
                    fused_indices = hybrid_rerank(
                        bundle.chunks, _candidate_pool, _dense_dict, question, _hybrid_alpha,
                    )
                final_result = build_query_result(
                    bundle,
                    question,
                    fused_indices[:top_k],
                    dense_scores,
                    settings=settings,
                )
                stages.append(
                    RetrievalStage(
                        stage_type="retrieval_augmented",
                        payload={
                            "sources": [source.to_dict() for source in final_result.sources],
                            "context_block": final_result.context_block,
                            "top_score": float(final_result.top_score),
                        },
                    )
                )

    # --- Monte Carlo Evidence Sampling (MCES) ---
    # Expands retrieved chunks by re-reading each source file and returning
    # the best context window around the hit (controlled by enable_mces).
    if settings.get("enable_mces") and final_result.sources:
        try:
            from metis_app.services.monte_carlo_sampler import apply_mces  # noqa: PLC0415
            _mces_snippets, _expanded_count = apply_mces(
                final_result.sources, question, settings
            )
            if _mces_snippets:
                # Patch each source's snippet with the expanded context window
                # so the LLM actually receives fuller text.
                _expanded_map = {
                    s["file_path"]: s["expanded_text"] for s in _mces_snippets
                }
                for _src in final_result.sources:
                    _fp = _src.file_path or ""
                    if _fp and _fp in _expanded_map:
                        _src.snippet = _expanded_map[_fp]
                # Rebuild context_block from updated source snippets
                final_result.context_block = "\n\n".join(
                    _src.snippet
                    for _src in final_result.sources
                    if _src.snippet
                )
                stages.append(
                    RetrievalStage(
                        stage_type="mces_context_expansion",
                        payload={
                            "snippets": _mces_snippets,
                            "expanded_count": _expanded_count,
                        },
                    )
                )
        except Exception:  # noqa: BLE001
            pass  # MCES is best-effort; never block a query

    fallback = _fallback_for_result(final_result, settings)
    stages.append(
        RetrievalStage(
            stage_type="fallback_decision",
            payload=fallback.to_dict(),
        )
    )

    if selected_mode == "Research" and final_result.sources:
        final_result.sources.sort(
            key=lambda s: (s.chunk_idx if s.chunk_idx is not None else 0)
        )

    # --- Cache put (store result for future hits) ---
    if _cache is not None:
        try:
            _cache.put(question, {
                "prompt": final_result.prompt,
                "context_block": final_result.context_block,
                "sources": [s.to_dict() for s in final_result.sources],
                "hit_indices": list(final_result.hit_indices),
                "top_score": float(final_result.top_score),
            })
        except Exception:  # noqa: BLE001
            pass

    return RetrievalPlan(
        question=question,
        selected_mode=selected_mode,
        result=final_result,
        effective_queries=effective_queries,
        stages=stages,
        fallback=fallback,
    )


__all__ = [
    "FallbackDecision",
    "RetrievalPlan",
    "RetrievalStage",
    "execute_retrieval_plan",
    "generate_sub_queries",
]
