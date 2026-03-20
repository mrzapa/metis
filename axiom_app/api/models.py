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
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
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
    session_id: str = ""
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
    retrieval_plan: dict[str, Any] = Field(default_factory=dict)
    fallback: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_engine(cls, result: RagQueryResult) -> "RagQueryResultModel":
        return cls(
            run_id=result.run_id,
            answer_text=result.answer_text,
            sources=result.sources,
            context_block=result.context_block,
            top_score=result.top_score,
            selected_mode=result.selected_mode,
            retrieval_plan=dict(result.retrieval_plan or {}),
            fallback=dict(result.fallback or {}),
        )


class KnowledgeSearchRequestModel(BaseModel):
    manifest_path: str
    question: str
    settings: dict[str, Any]
    run_id: str | None = None
    session_id: str = ""

    model_config = ConfigDict(extra="forbid")

    def to_engine(self) -> KnowledgeSearchRequest:
        return KnowledgeSearchRequest(
            manifest_path=Path(self.manifest_path),
            question=self.question,
            settings=dict(self.settings),
            run_id=self.run_id,
        )


class KnowledgeSearchResultModel(BaseModel):
    run_id: str
    summary_text: str
    sources: list[dict[str, Any]]
    context_block: str
    top_score: float
    selected_mode: str
    retrieval_plan: dict[str, Any] = Field(default_factory=dict)
    fallback: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_engine(cls, result: KnowledgeSearchResult) -> "KnowledgeSearchResultModel":
        return cls(
            run_id=result.run_id,
            summary_text=result.summary_text,
            sources=result.sources,
            context_block=result.context_block,
            top_score=result.top_score,
            selected_mode=result.selected_mode,
            retrieval_plan=dict(result.retrieval_plan or {}),
            fallback=dict(result.fallback or {}),
        )


class DirectQueryRequestModel(BaseModel):
    prompt: str
    settings: dict[str, Any]
    run_id: str | None = None
    session_id: str = ""

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
    label: str = ""
    breadcrumb: str = ""
    section_hint: str = ""
    locator: str = ""
    anchor: str = ""
    header_path: str = ""
    excerpt: str = ""
    file_path: str = ""
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
            label=src.label,
            breadcrumb=src.breadcrumb,
            section_hint=src.section_hint,
            locator=src.locator,
            anchor=src.anchor,
            header_path=src.header_path,
            excerpt=src.excerpt,
            file_path=src.file_path,
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


class CreateSessionRequestModel(BaseModel):
    title: str = "New Chat"

    model_config = ConfigDict(extra="forbid")


class FeedbackRequestModel(BaseModel):
    run_id: str
    vote: int  # -1 or 1; repo accepts any int
    note: str = ""

    model_config = ConfigDict(extra="forbid")


class FeedbackResponseModel(BaseModel):
    ok: bool


class AssistantIdentityModel(BaseModel):
    assistant_id: str
    name: str
    archetype: str
    companion_enabled: bool
    greeting: str
    prompt_seed: str
    docked: bool
    minimized: bool


class AssistantRuntimeModel(BaseModel):
    provider: str
    model: str
    local_gguf_model_path: str
    local_gguf_context_length: int
    local_gguf_gpu_layers: int
    local_gguf_threads: int
    fallback_to_primary: bool
    auto_bootstrap: bool
    auto_install: bool
    bootstrap_state: str
    recommended_model_name: str
    recommended_quant: str
    recommended_use_case: str


class AssistantPolicyModel(BaseModel):
    reflection_enabled: bool
    reflection_backend: str
    reflection_cooldown_seconds: int
    max_memory_entries: int
    max_playbooks: int
    max_brain_links: int
    trigger_on_onboarding: bool
    trigger_on_index_build: bool
    trigger_on_completed_run: bool
    allow_automatic_writes: bool


class AssistantStatusModel(BaseModel):
    state: str
    paused: bool
    runtime_ready: bool
    runtime_source: str
    runtime_provider: str
    runtime_model: str
    bootstrap_state: str
    bootstrap_message: str
    recommended_model_name: str
    recommended_quant: str
    recommended_use_case: str
    last_reflection_at: str
    last_reflection_trigger: str
    latest_summary: str
    latest_why: str


class AssistantMemoryEntryModel(BaseModel):
    entry_id: str
    created_at: str
    kind: str
    title: str
    summary: str
    details: str = ""
    why: str = ""
    provenance: str = ""
    confidence: float = 0.0
    trigger: str = ""
    context_id: str = ""
    session_id: str = ""
    run_id: str = ""
    tags: list[str] = Field(default_factory=list)
    related_node_ids: list[str] = Field(default_factory=list)


class AssistantPlaybookModel(BaseModel):
    playbook_id: str
    created_at: str
    title: str
    bullets: list[str] = Field(default_factory=list)
    source_session_id: str = ""
    source_run_id: str = ""
    provenance: str = ""
    confidence: float = 0.0
    active: bool = True


class AssistantBrainLinkModel(BaseModel):
    link_id: str
    created_at: str
    source_node_id: str
    target_node_id: str
    relation: str
    label: str
    provenance: str = ""
    summary: str = ""
    confidence: float = 0.0
    session_id: str = ""
    run_id: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssistantSnapshotModel(BaseModel):
    identity: AssistantIdentityModel
    runtime: AssistantRuntimeModel
    policy: AssistantPolicyModel
    status: AssistantStatusModel
    memory: list[AssistantMemoryEntryModel] = Field(default_factory=list)
    playbooks: list[AssistantPlaybookModel] = Field(default_factory=list)
    brain_links: list[AssistantBrainLinkModel] = Field(default_factory=list)


class AssistantUpdateRequestModel(BaseModel):
    identity: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    policy: dict[str, Any] | None = None
    status: dict[str, Any] | None = None

    model_config = ConfigDict(extra="forbid")


class AssistantReflectRequestModel(BaseModel):
    trigger: str = "manual"
    context_id: str = ""
    session_id: str = ""
    run_id: str = ""
    force: bool = False

    model_config = ConfigDict(extra="forbid")


class AssistantBootstrapRequestModel(BaseModel):
    install_local_model: bool = False

    model_config = ConfigDict(extra="forbid")


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
