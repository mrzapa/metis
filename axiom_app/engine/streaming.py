"""SSE-ready streaming generator for RAG queries."""

from __future__ import annotations

from typing import Any, Iterator

from axiom_app.engine.querying import (
    RagQueryRequest,
    _normalize_run_id,
    _prepare_rag_settings,
    _response_text,
    _system_instructions,
)
from axiom_app.services.vector_store import resolve_vector_store
from axiom_app.utils.llm_providers import create_llm


def stream_rag_answer(
    req: RagQueryRequest,
    cancel_token: Any = None,  # reserved for future cancellation support
) -> Iterator[dict[str, Any]]:
    """Yield structured dict events for a RAG query.

    Event shapes (all JSON-serialisable):
      {"type": "run_started",        "run_id": str}
      {"type": "retrieval_complete", "run_id": str, "sources": [...],
                                     "context_block": str, "top_score": float}
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
        llm = create_llm(settings)

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
