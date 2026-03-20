"""UI-free query helpers for engine consumers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import uuid

from axiom_app.services.index_service import load_index_manifest
from axiom_app.services.retrieval_pipeline import execute_retrieval_plan
from axiom_app.services.vector_store import resolve_vector_store
from axiom_app.utils.llm_providers import create_llm

_DEFAULT_SELECTED_MODE = "Q&A"
_DEFAULT_SYSTEM_INSTRUCTIONS = (
    "You are Axiom, a grounded AI assistant. Use citations when retrieved context "
    "is available."
)


@dataclass(slots=True)
class RagQueryRequest:
    manifest_path: str | Path
    question: str
    settings: dict[str, Any]
    run_id: str | None = None
    require_action: bool = False


@dataclass(slots=True)
class RagQueryResult:
    run_id: str
    answer_text: str
    sources: list[dict[str, Any]]
    context_block: str
    top_score: float
    selected_mode: str
    retrieval_plan: dict[str, Any] = field(default_factory=dict)
    fallback: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DirectQueryRequest:
    prompt: str
    settings: dict[str, Any]
    run_id: str | None = None


@dataclass(slots=True)
class DirectQueryResult:
    run_id: str
    answer_text: str
    selected_mode: str
    llm_provider: str = ""
    llm_model: str = ""


@dataclass(slots=True)
class KnowledgeSearchRequest:
    manifest_path: str | Path
    question: str
    settings: dict[str, Any]
    run_id: str | None = None


@dataclass(slots=True)
class KnowledgeSearchResult:
    run_id: str
    summary_text: str
    sources: list[dict[str, Any]]
    context_block: str
    top_score: float
    selected_mode: str
    retrieval_plan: dict[str, Any] = field(default_factory=dict)
    fallback: dict[str, Any] = field(default_factory=dict)


def _normalize_run_id(run_id: str | None) -> str:
    candidate = str(run_id or "").strip()
    return candidate or str(uuid.uuid4())


def _selected_mode(settings: dict[str, Any]) -> str:
    return str(settings.get("selected_mode", _DEFAULT_SELECTED_MODE) or _DEFAULT_SELECTED_MODE)


def _system_instructions(settings: dict[str, Any]) -> str:
    return str(settings.get("system_instructions") or _DEFAULT_SYSTEM_INSTRUCTIONS).strip()


def _response_text(result: Any) -> str:
    return str(getattr(result, "content", result) or "")


def _prepare_rag_settings(req: RagQueryRequest) -> tuple[Path, dict[str, Any]]:
    raw_manifest_path = str(req.manifest_path or "").strip()
    if not raw_manifest_path:
        raise ValueError("manifest_path must not be empty.")
    manifest_path = Path(raw_manifest_path)

    settings = dict(req.settings)
    manifest = load_index_manifest(manifest_path)
    settings["vector_db_type"] = str(
        manifest.backend or settings.get("vector_db_type", "json") or "json"
    )
    return manifest_path, settings


def query_rag(req: RagQueryRequest) -> RagQueryResult:
    """Run retrieval plus non-streaming synthesis for a persisted index."""

    question = str(req.question or "").strip()
    if not question:
        raise ValueError("question must not be empty.")

    manifest_path, settings = _prepare_rag_settings(req)
    adapter = resolve_vector_store(settings)
    available, reason = adapter.is_available(settings)
    if not available:
        raise RuntimeError(f"Vector backend unavailable: {reason}")

    bundle = adapter.load(manifest_path)
    llm = create_llm(settings)
    retrieval_plan = execute_retrieval_plan(
        bundle=bundle,
        adapter=adapter,
        question=question,
        settings=settings,
        llm=llm,
    )
    query_result = retrieval_plan.result

    if retrieval_plan.fallback.triggered and retrieval_plan.fallback.strategy == "no_answer":
        answer = retrieval_plan.fallback.message
    else:
        system_prompt = (
            f"{_system_instructions(settings)}\n\n"
            "Answer the user's question using ONLY the CONTEXT below. "
            "Cite passages as [S1], [S2], etc. If the context is insufficient, say so.\n\n"
            f"CONTEXT:\n{query_result.context_block}"
        )
        answer = _response_text(
            llm.invoke(
                [
                    {"type": "system", "content": system_prompt},
                    {"type": "human", "content": question},
                ]
            )
        )
    return RagQueryResult(
        run_id=_normalize_run_id(req.run_id),
        answer_text=answer,
        sources=[source.to_dict() for source in query_result.sources],
        context_block=query_result.context_block,
        top_score=float(query_result.top_score),
        selected_mode=_selected_mode(settings),
        retrieval_plan=retrieval_plan.to_dict(),
        fallback=retrieval_plan.fallback.to_dict(),
    )


def query_direct(req: DirectQueryRequest) -> DirectQueryResult:
    """Run a non-streaming direct prompt through the configured LLM provider."""

    prompt = str(req.prompt or "").strip()
    if not prompt:
        raise ValueError("prompt must not be empty.")

    settings = dict(req.settings)
    llm = create_llm(settings)
    answer = _response_text(
        llm.invoke(
            [
                {"type": "system", "content": _system_instructions(settings)},
                {"type": "human", "content": prompt},
            ]
        )
    )
    return DirectQueryResult(
        run_id=_normalize_run_id(req.run_id),
        answer_text=answer,
        selected_mode=_selected_mode(settings),
        llm_provider=str(settings.get("llm_provider", "") or ""),
        llm_model=str(settings.get("llm_model", "") or ""),
    )


def _knowledge_search_summary(result: KnowledgeSearchResult) -> str:
    source_count = len(result.sources)
    document_count = len(
        {
            str(source.get("source") or source.get("title") or "").strip()
            for source in result.sources
            if str(source.get("source") or source.get("title") or "").strip()
        }
    )
    if source_count == 0:
        return str(result.fallback.get("message") or "No grounded matches were found in the selected index.")
    return (
        f"Found {source_count} relevant passage(s) across "
        f"{max(document_count, 1)} document(s). Review the evidence panel to inspect the matches."
    )


def knowledge_search(req: KnowledgeSearchRequest) -> KnowledgeSearchResult:
    """Run retrieval only, without LLM synthesis."""

    question = str(req.question or "").strip()
    if not question:
        raise ValueError("question must not be empty.")

    manifest_path, settings = _prepare_rag_settings(
        RagQueryRequest(
            manifest_path=req.manifest_path,
            question=question,
            settings=req.settings,
            run_id=req.run_id,
        )
    )
    settings["selected_mode"] = "Knowledge Search"
    try:
        settings["top_k"] = int(settings.get("knowledge_search_top_k") or settings.get("top_k") or 8)
    except (TypeError, ValueError):
        settings["top_k"] = 8
    adapter = resolve_vector_store(settings)
    available, reason = adapter.is_available(settings)
    if not available:
        raise RuntimeError(f"Vector backend unavailable: {reason}")

    bundle = adapter.load(manifest_path)
    llm = None
    if bool(settings.get("use_sub_queries", False)):
        try:
            llm = create_llm(settings)
        except Exception:  # noqa: BLE001
            llm = None
    retrieval_plan = execute_retrieval_plan(
        bundle=bundle,
        adapter=adapter,
        question=question,
        settings=settings,
        llm=llm,
    )
    result = retrieval_plan.result
    result_payload = KnowledgeSearchResult(
        run_id=_normalize_run_id(req.run_id),
        summary_text="",
        sources=[source.to_dict() for source in result.sources],
        context_block=result.context_block,
        top_score=float(result.top_score),
        selected_mode=_selected_mode(settings),
        retrieval_plan=retrieval_plan.to_dict(),
        fallback=retrieval_plan.fallback.to_dict(),
    )
    result_payload.summary_text = _knowledge_search_summary(result_payload)
    return result_payload


__all__ = [
    "DirectQueryRequest",
    "DirectQueryResult",
    "KnowledgeSearchRequest",
    "KnowledgeSearchResult",
    "RagQueryRequest",
    "RagQueryResult",
    "knowledge_search",
    "query_direct",
    "query_rag",
]
