"""Typed records used by the MVC parity layer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import uuid
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class AgentProfile:
    """Profile definition compatible with monolith JSON profile files."""

    name: str
    system_instructions: str = ""
    style_template: str = ""
    citation_policy: str = ""
    retrieval_strategy: dict[str, Any] = field(default_factory=dict)
    iteration_strategy: dict[str, Any] = field(default_factory=dict)
    comprehension_pipeline_on_ingest: dict[str, Any] | None = None
    mode_default: str = "Q&A"
    provider: str = ""
    model: str = ""
    retrieval_mode: str = ""
    llm_max_tokens: int | None = None
    frontier_toggles: dict[str, Any] = field(default_factory=dict)
    digest_usage: bool | None = None

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "AgentProfile":
        data = dict(payload or {})
        llm_max_tokens = data.get("llm_max_tokens")
        try:
            llm_max_tokens = int(llm_max_tokens) if llm_max_tokens is not None else None
        except (TypeError, ValueError):
            llm_max_tokens = None
        digest_usage = data.get("digest_usage")
        if digest_usage is not None:
            digest_usage = bool(digest_usage)
        return cls(
            name=str(data.get("name") or "Default"),
            system_instructions=str(data.get("system_instructions") or ""),
            style_template=str(data.get("style_template") or ""),
            citation_policy=str(data.get("citation_policy") or ""),
            retrieval_strategy=dict(data.get("retrieval_strategy") or {}),
            iteration_strategy=dict(data.get("iteration_strategy") or {}),
            comprehension_pipeline_on_ingest=(
                dict(data.get("comprehension_pipeline_on_ingest") or {})
                if isinstance(data.get("comprehension_pipeline_on_ingest"), dict)
                else data.get("comprehension_pipeline_on_ingest")
            ),
            mode_default=str(data.get("mode_default") or "Q&A"),
            provider=str(data.get("provider") or ""),
            model=str(data.get("model") or ""),
            retrieval_mode=str(data.get("retrieval_mode") or ""),
            llm_max_tokens=llm_max_tokens,
            frontier_toggles=dict(data.get("frontier_toggles") or {}),
            digest_usage=digest_usage,
        )


@dataclass(slots=True)
class LocalModelEntry:
    """Normalized local-model registry row."""

    entry_id: str
    model_type: str
    name: str
    value: str
    path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.entry_id,
            "type": self.model_type,
            "name": self.name,
            "value": self.value,
            "path": self.path,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def new(
        cls,
        model_type: str,
        name: str,
        value: str,
        *,
        path: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "LocalModelEntry":
        return cls(
            entry_id=str(uuid.uuid4()),
            model_type=str(model_type or "").strip(),
            name=str(name or "").strip(),
            value=str(value or "").strip(),
            path=str(path or "").strip(),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any], *, fallback_type: str) -> "LocalModelEntry | None":
        data = dict(payload or {})
        name = str(data.get("name") or "").strip()
        value = str(data.get("value") or data.get("path") or "").strip()
        path = str(data.get("path") or value).strip()
        model_type = str(data.get("type") or fallback_type or "").strip()
        if not name or not value or model_type not in {"gguf", "sentence_transformers"}:
            return None
        return cls(
            entry_id=str(data.get("id") or uuid.uuid4()),
            model_type=model_type,
            name=name,
            value=value,
            path=path if model_type == "gguf" else "",
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass(slots=True)
class IndexManifest:
    """Canonical persisted index contract for all vector backends."""

    index_id: str
    backend: str
    created_at: str
    embedding_signature: str = ""
    source_files: list[str] = field(default_factory=list)
    manifest_path: str = ""
    bundle_path: str = "bundle.json"
    vector_store_path: str = ""
    collection_name: str = ""
    document_count: int = 0
    chunk_count: int = 0
    outline_path: str = "artifacts/document_outline.json"
    semantic_regions_path: str = "artifacts/semantic_regions.json"
    events_path: str = "artifacts/events.json"
    grounding_artifact_path: str = ""
    restore_requirements: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    legacy_compat: bool = False

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "IndexManifest":
        data = dict(payload or {})
        return cls(
            index_id=str(data.get("index_id") or ""),
            backend=str(data.get("backend") or "json"),
            created_at=str(data.get("created_at") or utc_now_iso()),
            embedding_signature=str(data.get("embedding_signature") or ""),
            source_files=[str(item) for item in (data.get("source_files") or [])],
            manifest_path=str(data.get("manifest_path") or ""),
            bundle_path=str(data.get("bundle_path") or "bundle.json"),
            vector_store_path=str(data.get("vector_store_path") or ""),
            collection_name=str(data.get("collection_name") or ""),
            document_count=int(data.get("document_count") or 0),
            chunk_count=int(data.get("chunk_count") or 0),
            outline_path=str(data.get("outline_path") or "artifacts/document_outline.json"),
            semantic_regions_path=str(data.get("semantic_regions_path") or "artifacts/semantic_regions.json"),
            events_path=str(data.get("events_path") or "artifacts/events.json"),
            grounding_artifact_path=str(data.get("grounding_artifact_path") or ""),
            restore_requirements=dict(data.get("restore_requirements") or {}),
            metadata=dict(data.get("metadata") or {}),
            legacy_compat=bool(data.get("legacy_compat", False)),
        )


@dataclass(slots=True)
class TraceEvent:
    """Monolith-compatible trace event persisted as JSON lines."""

    run_id: str
    event_id: str
    stage: str
    event_type: str
    timestamp: str
    iteration: int = 0
    latency_ms: int | None = None
    prompt: dict[str, Any] | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    retrieval_results: dict[str, Any] | None = None
    citations_chosen: list[str] = field(default_factory=list)
    validator: dict[str, Any] | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        stage: str,
        event_type: str,
        iteration: int = 0,
        latency_ms: int | None = None,
        prompt: dict[str, Any] | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
        retrieval_results: dict[str, Any] | None = None,
        citations_chosen: list[str] | None = None,
        validator: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> "TraceEvent":
        return cls(
            run_id=str(run_id or ""),
            event_id=str(uuid.uuid4()),
            stage=str(stage or ""),
            event_type=str(event_type or ""),
            timestamp=utc_now_iso(),
            iteration=int(iteration or 0),
            latency_ms=latency_ms,
            prompt=dict(prompt or {}) if prompt is not None else None,
            tool_calls=[dict(item) for item in (tool_calls or [])],
            retrieval_results=dict(retrieval_results or {}) if retrieval_results is not None else None,
            citations_chosen=[str(item) for item in (citations_chosen or [])],
            validator=dict(validator or {}) if validator is not None else None,
            payload=dict(payload or {}),
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TraceEvent":
        data = dict(payload or {})
        latency_ms = data.get("latency_ms")
        try:
            latency_ms = int(latency_ms) if latency_ms is not None else None
        except (TypeError, ValueError):
            latency_ms = None
        return cls(
            run_id=str(data.get("run_id") or ""),
            event_id=str(data.get("event_id") or uuid.uuid4()),
            stage=str(data.get("stage") or ""),
            event_type=str(data.get("event_type") or ""),
            timestamp=str(data.get("timestamp") or utc_now_iso()),
            iteration=int(data.get("iteration") or 0),
            latency_ms=latency_ms,
            prompt=dict(data.get("prompt") or {}) if data.get("prompt") is not None else None,
            tool_calls=[dict(item) for item in (data.get("tool_calls") or []) if isinstance(item, dict)],
            retrieval_results=(
                dict(data.get("retrieval_results") or {})
                if data.get("retrieval_results") is not None
                else None
            ),
            citations_chosen=[str(item) for item in (data.get("citations_chosen") or [])],
            validator=dict(data.get("validator") or {}) if data.get("validator") is not None else None,
            payload=dict(data.get("payload") or {}),
        )


@dataclass(slots=True)
class ResolvedRuntimeSettings:
    """Effective runtime settings after profile + mode resolution."""

    mode: str
    profile_label: str
    profile: AgentProfile
    retrieve_k: int
    final_k: int
    mmr_lambda: float
    search_type: str
    retrieval_mode: str
    agentic_mode: bool
    agentic_max_iterations: int
    llm_provider: str
    llm_model: str
    embedding_provider: str
    embedding_model: str
    output_style: str
    mode_prompt_pack: str
    prompt_pack_id: str
    system_prompt: str
    evidence_pack_mode: bool = False
    resolution_payload: dict[str, Any] = field(default_factory=dict)
