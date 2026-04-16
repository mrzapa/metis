"""Pydantic API models that mirror engine request/response dataclasses."""

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from metis_app.engine import (
    DirectQueryRequest,
    DirectQueryResult,
    ForecastQueryRequest,
    ForecastSchemaRequest,
    IndexBuildRequest,
    IndexBuildResult,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    RagQueryRequest,
    RagQueryResult,
    SwarmQueryRequest,
    SwarmQueryResult,
)
from metis_app.services.forecast_service import (
    ForecastMapping,
    ForecastPreflightResult,
    ForecastQueryResult,
    ForecastSchemaColumn,
    ForecastSchemaResult,
    ForecastValidationResult,
)
from metis_app.models.session_types import (
    EvidenceSource,
    SessionDetail,
    SessionFeedback as _SessionFeedback,
    SessionMessage,
    SessionSummary,
)
from metis_app.services.nyx_catalog import (
    NYX_INSTALL_TARGET_POLICY_NAME,
    NYX_REVIEW_STATUS_INSTALLABLE,
    NyxCatalogComponentDetail,
    NyxCatalogComponentSummary,
    NyxCatalogFileSummary,
    NyxCatalogSearchResult,
)


class SuggestArchetypesRequestModel(BaseModel):
    file_paths: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


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
    brain_pass: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_engine(cls, result: IndexBuildResult) -> "IndexBuildResultModel":
        return cls(
            manifest_path=str(result.manifest_path),
            index_id=result.index_id,
            document_count=result.document_count,
            chunk_count=result.chunk_count,
            embedding_signature=result.embedding_signature,
            vector_backend=result.vector_backend,
            brain_pass=dict(result.brain_pass or {}),
        )


class IndexDeleteResultModel(BaseModel):
    deleted: bool
    manifest_path: str
    index_id: str


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
    artifacts: list["QueryArtifactModel"] | None = None
    actions: list["NyxInstallActionModel"] | None = None

    @classmethod
    def from_engine(cls, result: RagQueryResult) -> "RagQueryResultModel":
        raw_artifacts = getattr(result, "artifacts", None)
        raw_actions = getattr(result, "actions", None)
        return cls(
            run_id=result.run_id,
            answer_text=result.answer_text,
            sources=result.sources,
            context_block=result.context_block,
            top_score=result.top_score,
            selected_mode=result.selected_mode,
            retrieval_plan=dict(result.retrieval_plan or {}),
            fallback=dict(result.fallback or {}),
            artifacts=[QueryArtifactModel(**item) for item in list(raw_artifacts or [])] or None,
            actions=[NyxInstallActionModel(**item) for item in list(raw_actions or [])] or None,
        )


class QueryArtifactModel(BaseModel):
    id: str = ""
    type: str
    summary: str = ""
    path: str = ""
    mime_type: str = ""
    payload: Any | None = None
    payload_bytes: int = 0
    payload_truncated: bool = False


class SwarmQueryRequestModel(BaseModel):
    manifest_path: str
    question: str
    settings: dict[str, Any]
    run_id: str | None = None
    session_id: str = ""
    n_personas: int = 8
    n_rounds: int = 4
    topics: list[str] | None = None

    model_config = ConfigDict(extra="forbid")

    def to_engine(self) -> SwarmQueryRequest:
        return SwarmQueryRequest(
            manifest_path=Path(self.manifest_path),
            question=self.question,
            settings=dict(self.settings),
            run_id=self.run_id,
            n_personas=self.n_personas,
            n_rounds=self.n_rounds,
            topics=list(self.topics) if self.topics is not None else None,
        )


class SwarmQueryResultModel(BaseModel):
    run_id: str
    answer_text: str
    report: dict[str, Any]
    sources: list[dict[str, Any]]
    selected_mode: str = "Simulation"

    @classmethod
    def from_engine(cls, result: SwarmQueryResult) -> "SwarmQueryResultModel":
        return cls(
            run_id=result.run_id,
            answer_text=result.answer_text,
            report=dict(result.report or {}),
            sources=list(result.sources or []),
            selected_mode=result.selected_mode,
        )


class ForecastMappingModel(BaseModel):
    timestamp_column: str
    target_column: str
    dynamic_covariates: list[str] = Field(default_factory=list)
    static_covariates: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    def to_service(self) -> ForecastMapping:
        return ForecastMapping(
            timestamp_column=self.timestamp_column,
            target_column=self.target_column,
            dynamic_covariates=list(self.dynamic_covariates),
            static_covariates=list(self.static_covariates),
        )


class ForecastSchemaColumnModel(BaseModel):
    name: str
    detected_type: str
    non_null_count: int
    unique_count: int
    numeric_ratio: float
    timestamp_ratio: float
    sample_values: list[str] = Field(default_factory=list)

    @classmethod
    def from_service(cls, value: ForecastSchemaColumn) -> "ForecastSchemaColumnModel":
        return cls(**value.to_dict())


class ForecastValidationResultModel(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    history_row_count: int = 0
    future_row_count: int = 0
    inferred_horizon: int = 0
    resolved_horizon: int = 0
    inferred_frequency: str = ""

    @classmethod
    def from_service(cls, value: ForecastValidationResult) -> "ForecastValidationResultModel":
        return cls(**value.to_dict())


class ForecastPreflightResultModel(BaseModel):
    ready: bool
    timesfm_available: bool
    covariates_available: bool
    model_id: str
    max_context: int
    max_horizon: int
    xreg_mode: str
    force_xreg_cpu: bool
    warnings: list[str] = Field(default_factory=list)
    install_guidance: list[str] = Field(default_factory=list)

    @classmethod
    def from_service(cls, value: ForecastPreflightResult) -> "ForecastPreflightResultModel":
        return cls(**value.to_dict())


class ForecastSchemaRequestModel(BaseModel):
    file_path: str
    mapping: ForecastMappingModel | None = None
    horizon: int | None = None

    model_config = ConfigDict(extra="forbid")

    def to_engine(self) -> ForecastSchemaRequest:
        return ForecastSchemaRequest(
            file_path=self.file_path,
            mapping=self.mapping.to_service() if self.mapping else None,
            horizon=self.horizon,
        )


class ForecastSchemaResultModel(BaseModel):
    file_path: str
    file_name: str
    delimiter: str
    row_count: int
    column_count: int
    columns: list[ForecastSchemaColumnModel]
    timestamp_candidates: list[str] = Field(default_factory=list)
    numeric_target_candidates: list[str] = Field(default_factory=list)
    suggested_mapping: ForecastMappingModel | None = None
    validation: ForecastValidationResultModel

    @classmethod
    def from_service(cls, value: ForecastSchemaResult) -> "ForecastSchemaResultModel":
        suggested_mapping = value.suggested_mapping.to_dict() if value.suggested_mapping else None
        return cls(
            file_path=value.file_path,
            file_name=value.file_name,
            delimiter=value.delimiter,
            row_count=value.row_count,
            column_count=value.column_count,
            columns=[ForecastSchemaColumnModel.from_service(item) for item in value.columns],
            timestamp_candidates=list(value.timestamp_candidates),
            numeric_target_candidates=list(value.numeric_target_candidates),
            suggested_mapping=ForecastMappingModel(**suggested_mapping) if suggested_mapping else None,
            validation=ForecastValidationResultModel.from_service(value.validation),
        )


class ForecastQueryRequestModel(BaseModel):
    file_path: str
    prompt: str = ""
    mapping: ForecastMappingModel
    settings: dict[str, Any]
    run_id: str | None = None
    session_id: str = ""
    horizon: int | None = None

    model_config = ConfigDict(extra="forbid")

    def to_engine(self) -> ForecastQueryRequest:
        return ForecastQueryRequest(
            file_path=self.file_path,
            prompt=self.prompt,
            mapping=self.mapping.to_service(),
            settings=dict(self.settings),
            horizon=self.horizon,
            run_id=self.run_id,
        )


class ForecastQueryResultModel(BaseModel):
    run_id: str
    answer_text: str
    selected_mode: str
    query_mode: str
    model_backend: str
    model_id: str
    horizon: int
    context_used: int
    warnings: list[str] = Field(default_factory=list)
    artifacts: list["QueryArtifactModel"] | None = None

    @classmethod
    def from_engine(cls, result: ForecastQueryResult) -> "ForecastQueryResultModel":
        return cls(
            run_id=result.run_id,
            answer_text=result.answer_text,
            selected_mode=result.selected_mode,
            query_mode=result.query_mode,
            model_backend=result.model_backend,
            model_id=result.model_id,
            horizon=result.horizon,
            context_used=result.context_used,
            warnings=list(result.warnings),
            artifacts=[QueryArtifactModel(**item) for item in list(result.artifacts or [])] or None,
        )


class NyxInstallProposalComponentModel(BaseModel):
    component_name: str
    title: str
    description: str = ""
    curated_description: str = ""
    component_type: str = ""
    install_target: str = ""
    registry_url: str = ""
    source_repo: str = ""
    required_dependencies: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    dev_dependencies: list[str] = Field(default_factory=list)
    registry_dependencies: list[str] = Field(default_factory=list)
    file_count: int = 0
    targets: list[str] = Field(default_factory=list)
    review_status: str = NYX_REVIEW_STATUS_INSTALLABLE
    previewable: bool = True
    installable: bool = True
    install_path_policy: str = NYX_INSTALL_TARGET_POLICY_NAME
    install_path_safe: bool = True
    install_path_issues: list[str] = Field(default_factory=list)
    audit_issues: list[str] = Field(default_factory=list)


class NyxInstallProposalModel(BaseModel):
    schema_version: str
    proposal_token: str
    source: str = "nyx_runtime"
    run_id: str = ""
    query: str = ""
    intent_type: str = ""
    matched_signals: list[str] = Field(default_factory=list)
    component_names: list[str] = Field(default_factory=list)
    component_count: int = 0
    components: list[NyxInstallProposalComponentModel] = Field(default_factory=list)


class NyxInstallActionPayloadModel(BaseModel):
    action_id: str
    action_type: Literal["nyx_install"]
    proposal_token: str
    component_count: int = 0
    component_names: list[str] = Field(default_factory=list)


class NyxInstallActionModel(BaseModel):
    action_id: str
    action_type: Literal["nyx_install"]
    label: str
    summary: str = ""
    requires_approval: bool = True
    run_action_endpoint: str = ""
    payload: NyxInstallActionPayloadModel
    proposal: NyxInstallProposalModel


class NyxInstallActionInstallerModel(BaseModel):
    command: list[str] = Field(default_factory=list)
    cwd: str = ""
    package_script: str = ""
    returncode: int = 0
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""


class NyxInstallActionResultModel(BaseModel):
    run_id: str
    approved: bool
    status: str
    action_id: str
    action_type: Literal["nyx_install"]
    proposal_token: str
    component_names: list[str] = Field(default_factory=list)
    component_count: int = 0
    execution_status: str = ""
    proposal: NyxInstallProposalModel | None = None
    installer: NyxInstallActionInstallerModel | None = None
    failure_code: str = ""

    model_config = ConfigDict(extra="allow")


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


class LearningRouteStarSnapshotModel(BaseModel):
    id: str
    label: str = ""
    intent: str = ""
    notes: str = ""
    active_manifest_path: str = ""
    linked_manifest_paths: list[str] = Field(default_factory=list)
    connected_user_star_ids: list[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class LearningRouteIndexSummaryModel(BaseModel):
    index_id: str
    manifest_path: str
    document_count: int = 0
    chunk_count: int = 0
    created_at: str = ""
    embedding_signature: str = ""
    brain_pass: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class LearningRoutePreviewRequestModel(BaseModel):
    origin_star: LearningRouteStarSnapshotModel
    connected_stars: list[LearningRouteStarSnapshotModel] = Field(default_factory=list)
    indexes: list[LearningRouteIndexSummaryModel] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class LearningRoutePreviewStepModel(BaseModel):
    id: str
    kind: Literal["orient", "foundations", "synthesis", "apply"]
    title: str
    objective: str
    rationale: str
    manifest_path: str
    source_star_id: str | None = None
    tutor_prompt: str
    estimated_minutes: int


class LearningRoutePreviewModel(BaseModel):
    route_id: str
    title: str
    origin_star_id: str
    created_at: str
    updated_at: str
    steps: list[LearningRoutePreviewStepModel] = Field(min_length=4, max_length=4)


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
    artifacts: list["QueryArtifactModel"] | None = None
    actions: list["NyxInstallActionModel"] | None = None

    @classmethod
    def from_engine(cls, result: DirectQueryResult) -> "DirectQueryResultModel":
        raw_artifacts = getattr(result, "artifacts", None)
        raw_actions = getattr(result, "actions", None)
        return cls(
            run_id=result.run_id,
            answer_text=result.answer_text,
            selected_mode=result.selected_mode,
            llm_provider=result.llm_provider,
            llm_model=result.llm_model,
            artifacts=[QueryArtifactModel(**item) for item in list(raw_artifacts or [])] or None,
            actions=[NyxInstallActionModel(**item) for item in list(raw_actions or [])] or None,
        )


class NyxCatalogFileSummaryModel(BaseModel):
    path: str = ""
    file_type: str = ""
    target: str = ""
    content_bytes: int = 0

    @classmethod
    def from_service(cls, file_summary: NyxCatalogFileSummary) -> "NyxCatalogFileSummaryModel":
        return cls(
            path=file_summary.path,
            file_type=file_summary.file_type,
            target=file_summary.target,
            content_bytes=file_summary.content_bytes,
        )


class NyxCatalogComponentSummaryModel(BaseModel):
    component_name: str = Field(description="Curated NyxUI component slug")
    title: str
    description: str
    curated_description: str
    component_type: str
    install_target: str
    registry_url: str
    schema_url: str = ""
    source: str = "nyx_registry"
    source_repo: str
    required_dependencies: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    dev_dependencies: list[str] = Field(default_factory=list)
    registry_dependencies: list[str] = Field(default_factory=list)
    file_count: int = 0
    targets: list[str] = Field(default_factory=list)
    review_status: str = NYX_REVIEW_STATUS_INSTALLABLE
    previewable: bool = True
    installable: bool = True
    install_path_policy: str = NYX_INSTALL_TARGET_POLICY_NAME
    install_path_safe: bool = True
    install_path_issues: list[str] = Field(default_factory=list)
    audit_issues: list[str] = Field(default_factory=list)

    @classmethod
    def from_service(
        cls,
        component: NyxCatalogComponentSummary,
    ) -> "NyxCatalogComponentSummaryModel":
        return cls(
            component_name=component.component_name,
            title=component.title,
            description=component.description,
            curated_description=component.curated_description,
            component_type=component.component_type,
            install_target=component.install_target,
            registry_url=component.registry_url,
            schema_url=component.schema_url,
            source=component.source,
            source_repo=component.source_repo,
            required_dependencies=list(component.required_dependencies),
            dependencies=list(component.dependencies),
            dev_dependencies=list(component.dev_dependencies),
            registry_dependencies=list(component.registry_dependencies),
            file_count=component.file_count,
            targets=list(component.targets),
            review_status=component.review_status,
            previewable=component.previewable,
            installable=component.installable,
            install_path_policy=component.install_path_policy,
            install_path_safe=component.install_path_safe,
            install_path_issues=list(component.install_path_issues),
            audit_issues=list(component.audit_issues),
        )


class NyxCatalogComponentDetailModel(NyxCatalogComponentSummaryModel):
    files: list[NyxCatalogFileSummaryModel] = Field(default_factory=list)

    @classmethod
    def from_service(
        cls,
        component: NyxCatalogComponentDetail,
    ) -> "NyxCatalogComponentDetailModel":
        return cls(
            component_name=component.component_name,
            title=component.title,
            description=component.description,
            curated_description=component.curated_description,
            component_type=component.component_type,
            install_target=component.install_target,
            registry_url=component.registry_url,
            schema_url=component.schema_url,
            source=component.source,
            source_repo=component.source_repo,
            required_dependencies=list(component.required_dependencies),
            dependencies=list(component.dependencies),
            dev_dependencies=list(component.dev_dependencies),
            registry_dependencies=list(component.registry_dependencies),
            file_count=component.file_count,
            targets=list(component.targets),
            review_status=component.review_status,
            previewable=component.previewable,
            installable=component.installable,
            install_path_policy=component.install_path_policy,
            install_path_safe=component.install_path_safe,
            install_path_issues=list(component.install_path_issues),
            audit_issues=list(component.audit_issues),
            files=[
                NyxCatalogFileSummaryModel.from_service(file_summary)
                for file_summary in component.files
            ],
        )


class NyxCatalogSearchResponseModel(BaseModel):
    query: str = ""
    total: int
    matched: int
    curated_only: bool = True
    source: str = "nyx_registry"
    items: list[NyxCatalogComponentSummaryModel] = Field(default_factory=list)

    @classmethod
    def from_service(
        cls,
        result: NyxCatalogSearchResult,
    ) -> "NyxCatalogSearchResponseModel":
        return cls(
            query=result.query,
            total=result.total,
            matched=result.matched,
            curated_only=result.curated_only,
            source=result.source,
            items=[
                NyxCatalogComponentSummaryModel.from_service(component)
                for component in result.items
            ],
        )


TelemetryId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
TelemetryLabel = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


# ---------------------------------------------------------------------------
# Web Graph build models
# ---------------------------------------------------------------------------

class WebGraphNodeModel(BaseModel):
    """A single node in the built knowledge graph."""

    filename: str
    node_type: str  # "moc" | "concept" | "pattern" | "gotcha"
    title: str


class WebGraphBuildRequestModel(BaseModel):
    """Request body for POST /v1/index/build/web-graph."""

    topic: str
    settings: dict[str, Any]
    index_id: str | None = None

    model_config = ConfigDict(extra="forbid")


class WebGraphBuildResultModel(BaseModel):
    """Response for a successfully built web-graph index."""

    index_id: str
    manifest_path: str
    topic: str
    nodes: list[WebGraphNodeModel]
    sources: list[str]
    document_count: int
    chunk_count: int


class ArtifactTelemetryBasePayloadModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArtifactTelemetrySummaryPayloadModel(ArtifactTelemetryBasePayloadModel):
    artifact_count: int = Field(ge=0, le=5)
    artifact_types: list[TelemetryLabel] = Field(default_factory=list, max_length=5)
    artifact_ids: list[TelemetryId] = Field(default_factory=list, max_length=5)


class ArtifactPayloadDetectedPayloadModel(ArtifactTelemetrySummaryPayloadModel):
    has_valid_artifacts: bool
    detected_count: int = Field(ge=0, le=5)
    normalized_count: int = Field(ge=0, le=5)
    invalid_reason: Literal["invalid_payload"] | None = None


class ArtifactRenderAttemptPayloadModel(ArtifactTelemetrySummaryPayloadModel):
    renderer: Literal["default", "custom"]


class ArtifactRenderSuccessPayloadModel(ArtifactTelemetrySummaryPayloadModel):
    renderer: Literal["default", "custom"]


class ArtifactRenderFailurePayloadModel(ArtifactTelemetrySummaryPayloadModel):
    renderer: Literal["default", "custom"]
    error_name: TelemetryLabel


class ArtifactRenderFallbackMarkdownPayloadModel(ArtifactTelemetryBasePayloadModel):
    reason: Literal["feature_disabled", "no_artifacts", "invalid_payload", "render_error"]


class ArtifactInteractionPayloadModel(ArtifactTelemetryBasePayloadModel):
    interaction_type: Literal["card_click"]
    artifact_index: int = Field(ge=0, le=4)
    artifact_id: TelemetryId | None = None
    artifact_type: TelemetryLabel | None = None


class ArtifactBoundaryFlagStatePayloadModel(ArtifactTelemetryBasePayloadModel):
    state: Literal["enabled", "disabled", "unset"]


class ArtifactRuntimeAttemptPayloadModel(ArtifactTelemetryBasePayloadModel):
    artifact_index: int = Field(ge=0, le=4)
    artifact_id: TelemetryId | None = None
    artifact_type: TelemetryLabel


class ArtifactRuntimeSuccessPayloadModel(ArtifactTelemetryBasePayloadModel):
    artifact_index: int = Field(ge=0, le=4)
    artifact_id: TelemetryId | None = None
    artifact_type: TelemetryLabel


class ArtifactRuntimeFailurePayloadModel(ArtifactTelemetryBasePayloadModel):
    artifact_index: int = Field(ge=0, le=4)
    artifact_id: TelemetryId | None = None
    artifact_type: TelemetryLabel
    error_name: TelemetryLabel


class ArtifactRuntimeSkippedPayloadModel(ArtifactTelemetryBasePayloadModel):
    artifact_index: int = Field(ge=0, le=4)
    artifact_id: TelemetryId | None = None
    artifact_type: TelemetryLabel
    reason: Literal[
        "runtime_disabled",
        "unsupported_type",
        "payload_truncated",
        "invalid_payload",
    ]


class ArtifactTelemetryEventBaseModel(BaseModel):
    source: Literal["chat_artifact_boundary"]
    occurred_at: datetime
    run_id: TelemetryId
    session_id: TelemetryId | None = None
    message_id: TelemetryId | None = None
    is_streaming: bool = False

    model_config = ConfigDict(extra="forbid")


class ArtifactPayloadDetectedEventModel(ArtifactTelemetryEventBaseModel):
    event_name: Literal["artifact_payload_detected"]
    payload: ArtifactPayloadDetectedPayloadModel


class ArtifactRenderAttemptEventModel(ArtifactTelemetryEventBaseModel):
    event_name: Literal["artifact_render_attempt"]
    payload: ArtifactRenderAttemptPayloadModel


class ArtifactRenderSuccessEventModel(ArtifactTelemetryEventBaseModel):
    event_name: Literal["artifact_render_success"]
    payload: ArtifactRenderSuccessPayloadModel


class ArtifactRenderFailureEventModel(ArtifactTelemetryEventBaseModel):
    event_name: Literal["artifact_render_failure"]
    payload: ArtifactRenderFailurePayloadModel


class ArtifactRenderFallbackMarkdownEventModel(ArtifactTelemetryEventBaseModel):
    event_name: Literal["artifact_render_fallback_markdown"]
    payload: ArtifactRenderFallbackMarkdownPayloadModel


class ArtifactInteractionEventModel(ArtifactTelemetryEventBaseModel):
    event_name: Literal["artifact_interaction"]
    payload: ArtifactInteractionPayloadModel


class ArtifactBoundaryFlagStateEventModel(ArtifactTelemetryEventBaseModel):
    event_name: Literal["artifact_boundary_flag_state"]
    payload: ArtifactBoundaryFlagStatePayloadModel


class ArtifactRuntimeAttemptEventModel(ArtifactTelemetryEventBaseModel):
    event_name: Literal["artifact_runtime_attempt"]
    payload: ArtifactRuntimeAttemptPayloadModel


class ArtifactRuntimeSuccessEventModel(ArtifactTelemetryEventBaseModel):
    event_name: Literal["artifact_runtime_success"]
    payload: ArtifactRuntimeSuccessPayloadModel


class ArtifactRuntimeFailureEventModel(ArtifactTelemetryEventBaseModel):
    event_name: Literal["artifact_runtime_failure"]
    payload: ArtifactRuntimeFailurePayloadModel


class ArtifactRuntimeSkippedEventModel(ArtifactTelemetryEventBaseModel):
    event_name: Literal["artifact_runtime_skipped"]
    payload: ArtifactRuntimeSkippedPayloadModel


UiTelemetryEventModel = Annotated[
    ArtifactPayloadDetectedEventModel
    | ArtifactRenderAttemptEventModel
    | ArtifactRenderSuccessEventModel
    | ArtifactRenderFailureEventModel
    | ArtifactRenderFallbackMarkdownEventModel
    | ArtifactInteractionEventModel
    | ArtifactBoundaryFlagStateEventModel
    | ArtifactRuntimeAttemptEventModel
    | ArtifactRuntimeSuccessEventModel
    | ArtifactRuntimeFailureEventModel
    | ArtifactRuntimeSkippedEventModel,
    Field(discriminator="event_name"),
]


class UiTelemetryIngestRequestModel(BaseModel):
    events: list[UiTelemetryEventModel] = Field(min_length=1, max_length=10)

    model_config = ConfigDict(extra="forbid")


class UiTelemetryDataQualityModel(BaseModel):
    events_with_run_id_pct: float | None = None
    events_with_source_boundary_pct: float | None = None
    events_with_client_timestamp_pct: float | None = None


class UiTelemetrySummaryMetricsModel(BaseModel):
    exposure_count: int = Field(ge=0)
    render_attempt_count: int = Field(ge=0)
    render_success_rate: float | None = None
    render_failure_rate: float | None = None
    fallback_rate_by_reason: dict[str, float | None] = Field(default_factory=dict)
    interaction_rate: float | None = None
    runtime_attempt_rate: float | None = None
    runtime_success_rate: float | None = None
    runtime_failure_rate: float | None = None
    runtime_skip_mix: dict[str, float | None] = Field(default_factory=dict)
    data_quality: UiTelemetryDataQualityModel


class UiTelemetryMetricEvaluationModel(BaseModel):
    metric: str
    status: Literal["pass", "warn", "fail"]
    observed: float | None = None
    sample_count: int = Field(ge=0)
    comparator: Literal["min", "max"]
    go_threshold: float
    rollback_threshold: float | None = None
    reason: str


class UiTelemetryThresholdSampleModel(BaseModel):
    exposure_count: int = Field(ge=0)
    payload_detected_count: int = Field(ge=0)
    render_attempt_count: int = Field(ge=0)
    runtime_attempt_count: int = Field(ge=0)
    minimum_exposure_count_for_go: int = Field(ge=1)


class UiTelemetryThresholdEvaluationModel(BaseModel):
    per_metric: dict[str, UiTelemetryMetricEvaluationModel] = Field(default_factory=dict)
    overall_recommendation: Literal["go", "hold", "rollback_runtime", "rollback_artifacts"]
    failed_conditions: list[str] = Field(default_factory=list)
    sample: UiTelemetryThresholdSampleModel


class UiTelemetrySummaryResponseModel(BaseModel):
    window_hours: int = Field(ge=1)
    generated_at: datetime
    sampled_event_count: int = Field(ge=0)
    metrics: UiTelemetrySummaryMetricsModel
    thresholds: UiTelemetryThresholdEvaluationModel


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
    file_path: str = Field(default="", exclude=True)
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
    artifacts: list[QueryArtifactModel] | None = None
    actions: list[NyxInstallActionModel] | None = None
    action_result: NyxInstallActionResultModel | None = None

    @classmethod
    def from_dataclass(cls, m: SessionMessage) -> "SessionMessageModel":
        return cls(
            role=m.role,
            content=m.content,
            ts=m.ts,
            run_id=m.run_id,
            sources=[EvidenceSourceModel.from_dataclass(s) for s in m.sources],
            artifacts=[QueryArtifactModel.model_validate(item) for item in m.artifacts] or None,
            actions=[NyxInstallActionModel.model_validate(item) for item in m.actions] or None,
            action_result=(
                NyxInstallActionResultModel.model_validate(m.action_result)
                if isinstance(m.action_result, dict)
                else None
            ),
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
    action_id: str = ""
    action_type: str = ""
    proposal_token: str = ""
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


class AbliterateStreamRequest(BaseModel):
    """Body for ``POST /v1/heretic/abliterate/stream``."""

    model_id: str
    """HuggingFace model identifier (e.g. ``meta-llama/Llama-3.1-8B-Instruct``)."""

    bnb_4bit: bool = False
    """Enable bitsandbytes 4-bit quantization to reduce VRAM usage."""

    outtype: str = "f16"
    """Output quantization type for the GGUF file (e.g. ``"f16"``, ``"q4_k_m"``)."""

    model_config = ConfigDict(extra="forbid")
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
    autonomous_research_enabled: bool
    autonomous_research_provider: str


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


class AtlasEntryModel(BaseModel):
    entry_id: str
    created_at: str
    updated_at: str
    session_id: str
    run_id: str
    title: str
    summary: str
    body_md: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    mode: str = ""
    index_id: str = ""
    top_score: float = 0.0
    source_count: int = 0
    confidence: float = 0.0
    rationale: str = ""
    slug: str = ""
    status: str = "candidate"
    saved_at: str = ""
    markdown_path: str = ""

    model_config = ConfigDict(extra="forbid")


class AtlasSaveRequestModel(BaseModel):
    session_id: str
    run_id: str
    title: str = ""
    summary: str = ""

    model_config = ConfigDict(extra="forbid")


class AtlasDecisionRequestModel(BaseModel):
    session_id: str
    run_id: str
    decision: str

    model_config = ConfigDict(extra="forbid")


class ImprovementEntryModel(BaseModel):
    entry_id: str
    artifact_key: str
    artifact_type: str
    created_at: str
    updated_at: str
    title: str
    summary: str
    body_md: str
    session_id: str = ""
    run_id: str = ""
    status: str = "draft"
    tags: list[str] = Field(default_factory=list)
    upstream_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    slug: str = ""
    saved_at: str = ""
    markdown_path: str = ""

    model_config = ConfigDict(extra="forbid")


class ImprovementCreateRequest(BaseModel):
    """Request body for POST /v1/improvements."""

    artifact_type: str
    title: str
    summary: str = ""
    body_md: str = ""
    session_id: str = ""
    run_id: str = ""
    status: str = "draft"
    tags: list[str] = Field(default_factory=list)
    upstream_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    artifact_key: str = ""

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
    score: float
    recommendation_summary: str
    notes: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    score_components: dict[str, float] = Field(default_factory=dict)
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


# ---------------------------------------------------------------------------
# OpenAI Chat Completions compatibility models (Phase 1A)
# Gated by feature flag `api_compat_openai` — off by default.
# Only non-streaming is supported in this slice.
# ---------------------------------------------------------------------------


class OpenAIChatMessageModel(BaseModel):
    """Single message in an OpenAI-style chat completions request."""

    role: Literal["system", "user", "assistant"]
    content: str

    # OpenAI clients may send extra fields (e.g. name); accept and ignore them.
    model_config = ConfigDict(extra="ignore")


class OpenAIChatCompletionRequestModel(BaseModel):
    """Minimal OpenAI /v1/chat/completions request shape.

    Extra fields sent by standard OpenAI clients (temperature, max_tokens,
    top_p, etc.) are accepted and silently ignored — this endpoint is a
    compatibility facade backed by METIS's existing pipeline.
    """

    model: str = "metis"
    messages: list[OpenAIChatMessageModel] = Field(min_length=1)
    # stream=True is not supported in this slice; clients that set it get 501.
    stream: bool | None = None

    model_config = ConfigDict(extra="ignore")


class OpenAIChatCompletionMessageOutputModel(BaseModel):
    role: Literal["assistant"] = "assistant"
    content: str

    model_config = ConfigDict(extra="forbid")


class OpenAIChatCompletionChoiceModel(BaseModel):
    index: int
    message: OpenAIChatCompletionMessageOutputModel
    finish_reason: str

    model_config = ConfigDict(extra="forbid")


class OpenAIChatCompletionUsageModel(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    model_config = ConfigDict(extra="forbid")


class OpenAIChatCompletionResponseModel(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[OpenAIChatCompletionChoiceModel]
    usage: OpenAIChatCompletionUsageModel

    model_config = ConfigDict(extra="forbid")
