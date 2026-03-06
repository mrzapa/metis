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

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.entry_id,
            "type": self.model_type,
            "name": self.name,
            "value": self.value,
            "path": self.path,
        }

    @classmethod
    def new(cls, model_type: str, name: str, value: str, *, path: str = "") -> "LocalModelEntry":
        return cls(
            entry_id=str(uuid.uuid4()),
            model_type=str(model_type or "").strip(),
            name=str(name or "").strip(),
            value=str(value or "").strip(),
            path=str(path or "").strip(),
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
    system_prompt: str
    evidence_pack_mode: bool = False
