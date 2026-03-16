"""Pydantic API models that mirror engine request/response dataclasses."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from axiom_app.engine import (
    DirectQueryRequest,
    DirectQueryResult,
    IndexBuildRequest,
    IndexBuildResult,
    RagQueryRequest,
    RagQueryResult,
)
from axiom_app.models.session_types import (
    EvidenceSource,
    SessionDetail,
    SessionFeedback as _SessionFeedback,
    SessionMessage,
    SessionSummary,
)


class IndexBuildRequestModel(BaseModel):
    document_paths: list[str] = Field(min_length=1)
    settings: dict[str, Any]
    index_id: str | None = None

    model_config = ConfigDict(extra="forbid")

    def to_engine(self) -> IndexBuildRequest:
        return IndexBuildRequest(
            document_paths=self.document_paths,
            settings=dict(self.settings),
            index_id=self.index_id,
        )


class IndexBuildResultModel(BaseModel):
    manifest_path: str
    index_id: str
    document_count: int
    chunk_count: int
    embedding_signature: str
    vector_backend: str

    @classmethod
    def from_engine(cls, result: IndexBuildResult) -> "IndexBuildResultModel":
        return cls(
            manifest_path=str(result.manifest_path),
            index_id=result.index_id,
            document_count=result.document_count,
            chunk_count=result.chunk_count,
            embedding_signature=result.embedding_signature,
            vector_backend=result.vector_backend,
        )


class RagQueryRequestModel(BaseModel):
    manifest_path: str
    question: str
    settings: dict[str, Any]
    run_id: str | None = None
    require_action: bool = False

    model_config = ConfigDict(extra="forbid")

    def to_engine(self) -> RagQueryRequest:
        return RagQueryRequest(
            manifest_path=Path(self.manifest_path),
            question=self.question,
            settings=dict(self.settings),
            run_id=self.run_id,
            require_action=self.require_action,
        )


class RagQueryResultModel(BaseModel):
    run_id: str
    answer_text: str
    sources: list[dict[str, Any]]
    context_block: str
    top_score: float
    selected_mode: str

    @classmethod
    def from_engine(cls, result: RagQueryResult) -> "RagQueryResultModel":
        return cls(
            run_id=result.run_id,
            answer_text=result.answer_text,
            sources=result.sources,
            context_block=result.context_block,
            top_score=result.top_score,
            selected_mode=result.selected_mode,
        )


class DirectQueryRequestModel(BaseModel):
    prompt: str
    settings: dict[str, Any]
    run_id: str | None = None

    model_config = ConfigDict(extra="forbid")

    def to_engine(self) -> DirectQueryRequest:
        return DirectQueryRequest(
            prompt=self.prompt,
            settings=dict(self.settings),
            run_id=self.run_id,
        )


class DirectQueryResultModel(BaseModel):
    run_id: str
    answer_text: str
    selected_mode: str
    llm_provider: str = ""
    llm_model: str = ""

    @classmethod
    def from_engine(cls, result: DirectQueryResult) -> "DirectQueryResultModel":
        return cls(
            run_id=result.run_id,
            answer_text=result.answer_text,
            selected_mode=result.selected_mode,
            llm_provider=result.llm_provider,
            llm_model=result.llm_model,
        )


# ---------------------------------------------------------------------------
# Session & feedback models
# ---------------------------------------------------------------------------


class EvidenceSourceModel(BaseModel):
    """Evidence source — file_path omitted; use sid as stable ID."""

    sid: str
    source: str
    snippet: str
    chunk_id: str = ""
    chunk_idx: int | None = None
    score: float | None = None
    title: str = ""
    breadcrumb: str = ""
    section_hint: str = ""
    anchor: str = ""
    date: str = ""
    timestamp: str = ""
    speaker: str = ""
    actor: str = ""
    entry_type: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_dataclass(cls, src: EvidenceSource) -> "EvidenceSourceModel":
        return cls(
            sid=src.sid,
            source=src.source,
            snippet=src.snippet,
            chunk_id=src.chunk_id,
            chunk_idx=src.chunk_idx,
            score=src.score,
            title=src.title,
            breadcrumb=src.breadcrumb,
            section_hint=src.section_hint,
            anchor=src.anchor,
            date=src.date,
            timestamp=src.timestamp,
            speaker=src.speaker,
            actor=src.actor,
            entry_type=src.entry_type,
            metadata=dict(src.metadata or {}),
        )


class SessionSummaryModel(BaseModel):
    session_id: str
    created_at: str
    updated_at: str
    title: str
    summary: str
    active_profile: str
    mode: str
    index_id: str
    vector_backend: str
    llm_provider: str
    llm_model: str
    embed_model: str
    retrieve_k: int
    final_k: int
    mmr_lambda: float
    agentic_iterations: int
    extra: dict[str, Any]  # parsed extra_json; raw JSON string not exposed

    @classmethod
    def from_dataclass(cls, s: SessionSummary) -> "SessionSummaryModel":
        return cls(
            session_id=s.session_id,
            created_at=s.created_at,
            updated_at=s.updated_at,
            title=s.title,
            summary=s.summary,
            active_profile=s.active_profile,
            mode=s.mode,
            index_id=s.index_id,
            vector_backend=s.vector_backend,
            llm_provider=s.llm_provider,
            llm_model=s.llm_model,
            embed_model=s.embed_model,
            retrieve_k=s.retrieve_k,
            final_k=s.final_k,
            mmr_lambda=s.mmr_lambda,
            agentic_iterations=s.agentic_iterations,
            extra=s.extra,
        )


class SessionMessageModel(BaseModel):
    role: str
    content: str
    ts: str
    run_id: str = ""
    sources: list[EvidenceSourceModel] = Field(default_factory=list)

    @classmethod
    def from_dataclass(cls, m: SessionMessage) -> "SessionMessageModel":
        return cls(
            role=m.role,
            content=m.content,
            ts=m.ts,
            run_id=m.run_id,
            sources=[EvidenceSourceModel.from_dataclass(s) for s in m.sources],
        )


class SessionFeedbackModel(BaseModel):
    feedback_id: str
    session_id: str
    run_id: str
    vote: int
    note: str
    ts: str

    @classmethod
    def from_dataclass(cls, f: _SessionFeedback) -> "SessionFeedbackModel":
        return cls(
            feedback_id=f.feedback_id,
            session_id=f.session_id,
            run_id=f.run_id,
            vote=f.vote,
            note=f.note,
            ts=f.ts,
        )


class SessionDetailModel(BaseModel):
    summary: SessionSummaryModel
    messages: list[SessionMessageModel] = Field(default_factory=list)
    feedback: list[SessionFeedbackModel] = Field(default_factory=list)
    traces: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_dataclass(cls, d: SessionDetail) -> "SessionDetailModel":
        return cls(
            summary=SessionSummaryModel.from_dataclass(d.summary),
            messages=[SessionMessageModel.from_dataclass(m) for m in d.messages],
            feedback=[SessionFeedbackModel.from_dataclass(f) for f in d.feedback],
            traces=dict(d.traces or {}),
        )


class RunActionRequestModel(BaseModel):
    approved: bool
    payload: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class FeedbackRequestModel(BaseModel):
    run_id: str
    vote: int  # -1 or 1; repo accepts any int
    note: str = ""

    model_config = ConfigDict(extra="forbid")


class FeedbackResponseModel(BaseModel):
    ok: bool


class GgufCatalogEntryModel(BaseModel):
    model_name: str
    provider: str
    parameter_count: str
    architecture: str
    use_case: str
    fit_level: str
    run_mode: str
    best_quant: str
    estimated_tps: float
    memory_required_gb: float
    memory_available_gb: float
    recommended_context_length: int
    source_repo: str
    source_provider: str

    model_config = ConfigDict(extra="forbid")


class GgufInstalledEntryModel(BaseModel):
    id: str
    name: str
    path: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class GgufValidateRequestModel(BaseModel):
    model_path: str

    model_config = ConfigDict(extra="forbid")


class GgufRegisterRequestModel(BaseModel):
    name: str
    path: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")
