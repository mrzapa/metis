"""SSE-ready streaming generator for RAG queries."""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

from axiom_app.engine.querying import (
    RagQueryRequest,
    _normalize_run_id,
    _prepare_rag_settings,
    _response_text,
    _system_instructions,
)
from axiom_app.services.retrieval_pipeline import execute_retrieval_plan, generate_sub_queries
from axiom_app.services.stream_events import normalize_stream_event
from axiom_app.services.vector_store import resolve_vector_store
from axiom_app.utils.llm_providers import create_llm

log = logging.getLogger(__name__)

# Guard against runaway context growth during agentic refinement iterations.
_MAX_CONTEXT_CHARS = 12_000


def _generate_sub_queries(question: str, llm: Any) -> list[str]:
    """Proxy kept local so tests can patch the stream-layer expander."""
    return generate_sub_queries(question, {}, llm)


def _identify_gaps(
    question: str,
    current_answer: str,
    context_block: str,
    llm: Any,
) -> list[str]:
    """Critique the current answer and return targeted retrieval queries for gaps.

    Inspired by AIlice's self-critique loop (``AProcessor.__call__``) where the
    agent iteratively evaluates its own outputs to identify what additional
    information is needed before producing a confident final response.

    Returns an empty list on any failure or when the answer is already complete,
    so callers always treat the result as optional.
    """

    system = (
        "You are a research quality critic. "
        "Given a question, a draft answer, and the retrieved context used to "
        "generate it, identify specific knowledge gaps: places where the answer "
        "is incomplete, vague, contradictory, or unsupported by the context. "
        "For each gap, produce a precise retrieval query that would help fill it. "
        "Return ONLY a compact JSON array of query strings (1-3 items). "
        "If the answer is complete and well-supported, return []."
    )
    # Truncate context preview to avoid consuming too many tokens.
    context_preview = context_block[:2000] if len(context_block) > 2000 else context_block
    try:
        raw = _response_text(
            llm.invoke([
                {"type": "system", "content": system},
                {
                    "type": "human",
                    "content": (
                        f"QUESTION:\n{question}\n\n"
                        f"DRAFT ANSWER:\n{current_answer}\n\n"
                        f"CONTEXT USED (excerpt):\n{context_preview}"
                    ),
                },
            ])
        )
        start, end = raw.find("["), raw.rfind("]") + 1
        if start == -1 or end == 0:
            return []
        candidates = json.loads(raw[start:end])
        if not isinstance(candidates, list):
            return []
        seen: set[str] = set()
        result: list[str] = []
        for c in candidates:
            s = str(c).strip()
            if not s or s.lower() in seen:
                continue
            seen.add(s.lower())
            result.append(s)
        return result[:3]
    except Exception:  # noqa: BLE001
        return []


def _dedup_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return *sources* with duplicates removed, preserving insertion order.

    Deduplication key is ``chunk_id`` when available, falling back to ``sid``
    and then the raw snippet text.
    """
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for src in sources:
        key = str(src.get("chunk_id") or src.get("sid") or src.get("snippet") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result.append(src)
    return result


def stream_rag_answer(
    req: RagQueryRequest,
    cancel_token: Any = None,  # reserved for future cancellation support
) -> Iterator[dict[str, Any]]:
    """Yield structured dict events for a RAG query.

    Event shapes (all JSON-serialisable):
      {"type": "run_started",          "run_id": str}
      {"type": "retrieval_complete",   "run_id": str, "sources": [...],
                                        "context_block": str, "top_score": float}
      {"type": "subqueries",           "run_id": str, "queries": [str, ...]}  # Research mode only
      {"type": "iteration_start",      "run_id": str, "iteration": int,
                                        "total_iterations": int}               # agentic_mode only
      {"type": "gaps_identified",      "run_id": str, "gaps": [str, ...],
                                        "iteration": int}                      # agentic_mode only
      {"type": "refinement_retrieval", "run_id": str, "iteration": int,
                                        "sources": [...], "context_block": str,
                                        "top_score": float}                    # agentic_mode only
      {"type": "token",                "run_id": str, "text": str}  # 1..N
      {"type": "final",                "run_id": str, "answer_text": str, "sources": [...]}
      {"type": "error",                "run_id": str, "message": str}

    The ``cancel_token`` parameter is accepted for forward-compatibility but not
    yet acted upon.  Callers may pass any truthy sentinel and check it between
    yields once support is wired up.
    """
    run_id = _normalize_run_id(req.run_id)
    event_sequence = 0

    def _emit(event: dict[str, Any]) -> dict[str, Any]:
        nonlocal event_sequence
        event_sequence += 1
        return normalize_stream_event(event, sequence=event_sequence, source="rag_stream")

    try:
        question = str(req.question or "").strip()
        if not question:
            yield _emit({"type": "error", "run_id": run_id, "message": "question must not be empty."})
            return

        yield _emit({"type": "run_started", "run_id": run_id})

        manifest_path, settings = _prepare_rag_settings(req)
        adapter = resolve_vector_store(settings)
        available, reason = adapter.is_available(settings)
        if not available:
            yield _emit({
                "type": "error",
                "run_id": run_id,
                "message": f"Vector backend unavailable: {reason}",
            })
            return

        llm = create_llm(settings)

        bundle = adapter.load(manifest_path)
        retrieval_plan = execute_retrieval_plan(
            bundle=bundle,
            adapter=adapter,
            question=question,
            settings=settings,
            llm=llm,
            subquery_generator=_generate_sub_queries,
        )
        query_result = retrieval_plan.result
        sources = [s.to_dict() for s in query_result.sources]

        for stage in retrieval_plan.stages:
            payload = dict(stage.payload or {})
            if stage.stage_type == "retrieval_complete":
                yield _emit({
                    "type": "retrieval_complete",
                    "run_id": run_id,
                    "sources": list(payload.get("sources") or []),
                    "context_block": str(payload.get("context_block") or ""),
                    "top_score": float(payload.get("top_score", 0.0) or 0.0),
                })
            elif stage.stage_type == "query_expansion":
                yield _emit({
                    "type": "subqueries",
                    "run_id": run_id,
                    "queries": list(payload.get("queries") or []),
                })
            elif stage.stage_type == "retrieval_augmented":
                yield _emit({
                    "type": "retrieval_augmented",
                    "run_id": run_id,
                    "sources": list(payload.get("sources") or []),
                    "context_block": str(payload.get("context_block") or ""),
                    "top_score": float(payload.get("top_score", 0.0) or 0.0),
                })
            elif stage.stage_type == "fallback_decision":
                yield _emit({
                    "type": "fallback_decision",
                    "run_id": run_id,
                    "fallback": payload,
                })

        if retrieval_plan.fallback.triggered and retrieval_plan.fallback.strategy == "no_answer":
            yield _emit({
                "type": "final",
                "run_id": run_id,
                "answer_text": retrieval_plan.fallback.message,
                "sources": sources,
                "fallback": retrieval_plan.fallback.to_dict(),
            })
            return

        if req.require_action:
            yield _emit({
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
            })
            return

        # ------------------------------------------------------------------
        # Agentic iterative refinement loop — inspired by AIlice's
        # self-critique architecture (AProcessor.__call__).
        #
        # When agentic_mode is enabled the engine:
        #   1. Generates a non-streaming draft answer for self-critique.
        #   2. Asks the LLM to identify knowledge gaps in that draft.
        #   3. Issues targeted additional retrievals to fill those gaps.
        #   4. Repeats up to agentic_max_iterations times.
        #   5. Streams the final answer synthesised from all accumulated context.
        # ------------------------------------------------------------------
        agentic_mode = bool(settings.get("agentic_mode", False))
        agentic_max_iterations = max(
            1, int(settings.get("agentic_max_iterations", 2) or 2)
        )

        accumulated_context = query_result.context_block
        accumulated_sources = list(sources)

        if agentic_mode:
            # Generate an initial non-streaming draft used only for self-critique.
            _draft_prompt = (
                f"{_system_instructions(settings)}\n\n"
                "Answer the user's question using ONLY the CONTEXT below. "
                "Cite passages as [S1], [S2], etc. If the context is insufficient, say so.\n\n"
                f"CONTEXT:\n{accumulated_context}"
            )
            current_draft = _response_text(
                llm.invoke([
                    {"type": "system", "content": _draft_prompt},
                    {"type": "human", "content": question},
                ])
            )

            for iteration in range(1, agentic_max_iterations + 1):
                yield _emit({
                    "type": "iteration_start",
                    "run_id": run_id,
                    "iteration": iteration,
                    "total_iterations": agentic_max_iterations,
                })

                gap_queries = _identify_gaps(question, current_draft, accumulated_context, llm)
                if not gap_queries:
                    break  # Answer is sufficiently complete — stop early.

                yield _emit({
                    "type": "gaps_identified",
                    "run_id": run_id,
                    "gaps": gap_queries,
                    "iteration": iteration,
                })

                # Retrieve additional context for each identified gap.
                iteration_new_sources: list[dict[str, Any]] = []
                new_context_parts: list[str] = []
                for gap_query in gap_queries:
                    try:
                        gap_result = execute_retrieval_plan(
                            bundle=bundle,
                            adapter=adapter,
                            question=gap_query,
                            settings=settings,
                            llm=llm,
                            allow_query_expansion=False,
                            query_expander=_generate_sub_queries,
                        ).result
                        iteration_new_sources.extend(
                            s.to_dict() for s in gap_result.sources
                        )
                        new_context_parts.append(gap_result.context_block)
                    except Exception as gap_exc:  # noqa: BLE001
                        log.debug(
                            "Gap retrieval failed for query %r (iteration %d): %s",
                            gap_query,
                            iteration,
                            gap_exc,
                        )

                if not new_context_parts:
                    break  # No new evidence found — stop the loop.

                new_context_block = "\n\n".join(new_context_parts)
                # Guard against runaway context growth.
                candidate = accumulated_context + "\n\n" + new_context_block
                accumulated_context = candidate[:_MAX_CONTEXT_CHARS]
                accumulated_sources = _dedup_sources(
                    accumulated_sources + iteration_new_sources
                )

                top_iter_score = max(
                    (float(s.get("score") or 0.0) for s in iteration_new_sources),
                    default=0.0,
                )
                yield _emit({
                    "type": "refinement_retrieval",
                    "run_id": run_id,
                    "iteration": iteration,
                    "sources": iteration_new_sources,
                    "context_block": new_context_block,
                    "top_score": top_iter_score,
                })

                # Re-synthesise a draft for the next gap-analysis cycle
                # (only needed when further iterations remain).
                if iteration < agentic_max_iterations:
                    _refined_prompt = (
                        f"{_system_instructions(settings)}\n\n"
                        "Answer the user's question using ONLY the CONTEXT below. "
                        "Cite passages as [S1], [S2], etc. "
                        "If the context is insufficient, say so.\n\n"
                        f"CONTEXT:\n{accumulated_context}"
                    )
                    current_draft = _response_text(
                        llm.invoke([
                            {"type": "system", "content": _refined_prompt},
                            {"type": "human", "content": question},
                        ])
                    )

            # After all iterations, expose accumulated sources for the final answer.
            sources = accumulated_sources

        # ------------------------------------------------------------------
        # Final streaming synthesis using all accumulated context.
        # ------------------------------------------------------------------
        fallback_notice = ""
        if retrieval_plan.fallback.triggered:
            fallback_notice = (
                "\n\nRetrieval quality is low. Be explicit about uncertainty and do not "
                "invent support that is missing from the context."
            )
        system_prompt = (
            f"{_system_instructions(settings)}\n\n"
            "Answer the user's question using ONLY the CONTEXT below. "
            "Cite passages as [S1], [S2], etc. If the context is insufficient, say so."
            f"{fallback_notice}\n\n"
            f"CONTEXT:\n{accumulated_context}"
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
                    yield _emit({"type": "token", "run_id": run_id, "text": text})
        else:
            # Non-streaming fallback — emit a single token event with the full answer
            answer = _response_text(llm.invoke(messages))
            answer_parts.append(answer)
            yield _emit({"type": "token", "run_id": run_id, "text": answer})

        yield _emit({
            "type": "final",
            "run_id": run_id,
            "answer_text": "".join(answer_parts),
            "sources": sources,
            "fallback": retrieval_plan.fallback.to_dict(),
        })

    except Exception as exc:  # noqa: BLE001
        yield _emit({"type": "error", "run_id": run_id, "message": str(exc)})


__all__ = ["stream_rag_answer", "_identify_gaps", "_dedup_sources"]
