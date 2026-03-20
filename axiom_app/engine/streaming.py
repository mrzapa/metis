"""SSE-ready streaming generator for RAG queries."""

from __future__ import annotations

from typing import Any, Iterator

from axiom_app.engine.querying import (
    RagQueryRequest,
    _normalize_run_id,
    _prepare_rag_settings,
    _response_text,
    _selected_mode,
    _system_instructions,
)
from axiom_app.services.reranker import reciprocal_rank_fusion
from axiom_app.services.vector_store import resolve_vector_store
from axiom_app.utils.llm_providers import create_llm


def _generate_sub_queries(question: str, llm: Any) -> list[str]:
    """Call the LLM to produce 3-5 search sub-queries for *question*.

    Returns an empty list on any failure so callers always treat the result
    as optional.
    """
    import json as _json

    system = (
        "You generate search sub-queries for retrieval. "
        "Return 3-5 concise sub-queries as a JSON array of strings. "
        "Do not include any extra text."
    )
    try:
        raw = _response_text(
            llm.invoke([
                {"type": "system", "content": system},
                {"type": "human", "content": question},
            ])
        )
        start, end = raw.find("["), raw.rfind("]") + 1
        if start == -1 or end == 0:
            return []
        candidates = _json.loads(raw[start:end])
        if not isinstance(candidates, list):
            return []
        seen: set[str] = set()
        result: list[str] = []
        q_lower = question.strip().lower()
        for c in candidates:
            s = str(c).strip()
            if not s or s.lower() == q_lower or s.lower() in seen:
                continue
            seen.add(s.lower())
            result.append(s)
        return result[:5]
    except Exception:  # noqa: BLE001
        return []


def stream_rag_answer(
    req: RagQueryRequest,
    cancel_token: Any = None,  # reserved for future cancellation support
) -> Iterator[dict[str, Any]]:
    """Yield structured dict events for a RAG query.

    Event shapes (all JSON-serialisable):
      {"type": "run_started",        "run_id": str}
      {"type": "retrieval_complete", "run_id": str, "sources": [...],
                                     "context_block": str, "top_score": float}
      {"type": "subqueries",        "run_id": str, "queries": [str, ...]}  # Research mode only
      {"type": "token",              "run_id": str, "text": str}  # 1..N
      {"type": "final",              "run_id": str, "answer_text": str, "sources": [...]}
      {"type": "error",              "run_id": str, "message": str}

    The ``cancel_token`` parameter is accepted for forward-compatibility but not
    yet acted upon.  Callers may pass any truthy sentinel and check it between
    yields once support is wired up.
    """
    run_id = _normalize_run_id(req.run_id)
    try:
        question = str(req.question or "").strip()
        if not question:
            yield {"type": "error", "run_id": run_id, "message": "question must not be empty."}
            return

        yield {"type": "run_started", "run_id": run_id}

        manifest_path, settings = _prepare_rag_settings(req)
        adapter = resolve_vector_store(settings)
        available, reason = adapter.is_available(settings)
        if not available:
            yield {
                "type": "error",
                "run_id": run_id,
                "message": f"Vector backend unavailable: {reason}",
            }
            return

        llm = create_llm(settings)

        bundle = adapter.load(manifest_path)
        query_result = adapter.query(bundle, question, settings)
        sources = [s.to_dict() for s in query_result.sources]

        yield {
            "type": "retrieval_complete",
            "run_id": run_id,
            "sources": sources,
            "context_block": query_result.context_block,
            "top_score": float(query_result.top_score),
        }

        mode = _selected_mode(settings)
        sub_sources: list[dict[str, Any]] = []
        if mode == "Research" and settings.get("use_sub_queries", False):
            sub_queries = _generate_sub_queries(question, llm)
            if sub_queries:
                yield {"type": "subqueries", "run_id": run_id, "queries": sub_queries}

                # ── Sub-query retrieval ───────────────────────────────
                # Run each sub-query through the same retrieval pipeline
                # and fuse their hit indices with the primary results.
                primary_hits = query_result.hit_indices
                all_ranked_lists: list[list[int]] = [primary_hits]
                for sq in sub_queries:
                    try:
                        sq_result = adapter.query(bundle, sq, settings)
                        all_ranked_lists.append(sq_result.hit_indices)
                        sub_sources.extend(
                            s.to_dict() for s in sq_result.sources
                        )
                    except Exception as exc:  # noqa: BLE001
                        import logging as _logging

                        _logging.getLogger(__name__).debug(
                            "Sub-query retrieval failed for %r: %s", sq, exc
                        )

                if len(all_ranked_lists) > 1:
                    from axiom_app.services.index_service import build_query_result
                    fused = reciprocal_rank_fusion(*all_ranked_lists)
                    top_k = int(settings.get("top_k", 5))
                    fused = fused[:top_k]
                    # Re-compute scores from the primary result.
                    scores = [0.0] * len(bundle.chunks) if not hasattr(bundle, "embeddings") else []
                    if hasattr(bundle, "embeddings") and bundle.embeddings:
                        from axiom_app.services.index_service import cosine_similarity
                        from axiom_app.utils.embedding_providers import create_embeddings
                        from axiom_app.utils.mock_embeddings import MockEmbeddings

                        try:
                            emb = create_embeddings(settings)
                        except (ValueError, ImportError):
                            emb = MockEmbeddings(dimensions=32)
                        q_vec = emb.embed_query(question)
                        scores = [cosine_similarity(q_vec, vec) for vec in bundle.embeddings]
                    query_result = build_query_result(bundle, question, fused, scores)
                    sources = [s.to_dict() for s in query_result.sources]
                    yield {
                        "type": "retrieval_augmented",
                        "run_id": run_id,
                        "sources": sources,
                        "context_block": query_result.context_block,
                        "top_score": float(query_result.top_score),
                    }

        if req.require_action:
            yield {
                "type": "action_required",
                "run_id": run_id,
                "action": {
                    "kind": "confirm_settings",
                    "summary": (
                        f"Ready to synthesize an answer from {len(sources)} source(s). "
                        "Approve to continue."
                    ),
                    "payload": {
                        "source_count": len(sources),
                        "top_score": float(query_result.top_score),
                    },
                },
            }
            return

        system_prompt = (
            f"{_system_instructions(settings)}\n\n"
            "Answer the user's question using ONLY the CONTEXT below. "
            "Cite passages as [S1], [S2], etc. If the context is insufficient, say so.\n\n"
            f"CONTEXT:\n{query_result.context_block}"
        )
        messages = [
            {"type": "system", "content": system_prompt},
            {"type": "human", "content": question},
        ]

        answer_parts: list[str] = []
        if hasattr(llm, "stream"):
            # LangChain streaming path — yields chunk objects with partial content
            for chunk in llm.stream(messages):
                text = _response_text(chunk)
                if text:
                    answer_parts.append(text)
                    yield {"type": "token", "run_id": run_id, "text": text}
        else:
            # Non-streaming fallback — emit a single token event with the full answer
            answer = _response_text(llm.invoke(messages))
            answer_parts.append(answer)
            yield {"type": "token", "run_id": run_id, "text": answer}

        yield {
            "type": "final",
            "run_id": run_id,
            "answer_text": "".join(answer_parts),
            "sources": sources,
        }

    except Exception as exc:  # noqa: BLE001
        yield {"type": "error", "run_id": run_id, "message": str(exc)}


__all__ = ["stream_rag_answer"]
