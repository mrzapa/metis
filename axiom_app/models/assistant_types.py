"""Typed records for the persistent Axiom companion."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
import uuid


def assistant_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


@dataclass(slots=True)
class AssistantIdentity:
    assistant_id: str = "axiom-companion"
    name: str = "Axiom"
    archetype: str = "Clippy-style research companion"
    companion_enabled: bool = True
    greeting: str = (
        "I can help you get started, reflect on completed work, and map what I learn in the Brain tab."
    )
    prompt_seed: str = (
        "You are Axiom, a local-first companion who helps the user get oriented, suggests next steps, "
        "and records concise reflections without taking over the main chat."
    )
    docked: bool = True
    minimized: bool = False

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "AssistantIdentity":
        data = dict(payload or {})
        return cls(
            assistant_id=str(data.get("assistant_id") or "axiom-companion"),
            name=str(data.get("name") or "Axiom"),
            archetype=str(data.get("archetype") or "Clippy-style research companion"),
            companion_enabled=bool(data.get("companion_enabled", True)),
            greeting=str(data.get("greeting") or cls().greeting),
            prompt_seed=str(data.get("prompt_seed") or cls().prompt_seed),
            docked=bool(data.get("docked", True)),
            minimized=bool(data.get("minimized", False)),
        )


@dataclass(slots=True)
class AssistantRuntime:
    provider: str = ""
    model: str = ""
    local_gguf_model_path: str = ""
    local_gguf_context_length: int = 2048
    local_gguf_gpu_layers: int = 0
    local_gguf_threads: int = 0
    fallback_to_primary: bool = True
    auto_bootstrap: bool = True
    auto_install: bool = False
    bootstrap_state: str = "pending"
    recommended_model_name: str = ""
    recommended_quant: str = ""
    recommended_use_case: str = "chat"

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "AssistantRuntime":
        data = dict(payload or {})
        return cls(
            provider=str(data.get("provider") or ""),
            model=str(data.get("model") or ""),
            local_gguf_model_path=str(data.get("local_gguf_model_path") or ""),
            local_gguf_context_length=max(_coerce_int(data.get("local_gguf_context_length"), 2048), 512),
            local_gguf_gpu_layers=max(_coerce_int(data.get("local_gguf_gpu_layers"), 0), 0),
            local_gguf_threads=max(_coerce_int(data.get("local_gguf_threads"), 0), 0),
            fallback_to_primary=bool(data.get("fallback_to_primary", True)),
            auto_bootstrap=bool(data.get("auto_bootstrap", True)),
            auto_install=bool(data.get("auto_install", False)),
            bootstrap_state=str(data.get("bootstrap_state") or "pending"),
            recommended_model_name=str(data.get("recommended_model_name") or ""),
            recommended_quant=str(data.get("recommended_quant") or ""),
            recommended_use_case=str(data.get("recommended_use_case") or "chat"),
        )


@dataclass(slots=True)
class AssistantPolicy:
    reflection_enabled: bool = True
    reflection_backend: str = "hybrid"
    reflection_cooldown_seconds: int = 180
    max_memory_entries: int = 200
    max_playbooks: int = 64
    max_brain_links: int = 400
    trigger_on_onboarding: bool = True
    trigger_on_index_build: bool = True
    trigger_on_completed_run: bool = True
    allow_automatic_writes: bool = True

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "AssistantPolicy":
        data = dict(payload or {})
        return cls(
            reflection_enabled=bool(data.get("reflection_enabled", True)),
            reflection_backend=str(data.get("reflection_backend") or "hybrid"),
            reflection_cooldown_seconds=max(_coerce_int(data.get("reflection_cooldown_seconds"), 180), 0),
            max_memory_entries=max(_coerce_int(data.get("max_memory_entries"), 200), 1),
            max_playbooks=max(_coerce_int(data.get("max_playbooks"), 64), 1),
            max_brain_links=max(_coerce_int(data.get("max_brain_links"), 400), 1),
            trigger_on_onboarding=bool(data.get("trigger_on_onboarding", True)),
            trigger_on_index_build=bool(data.get("trigger_on_index_build", True)),
            trigger_on_completed_run=bool(data.get("trigger_on_completed_run", True)),
            allow_automatic_writes=bool(data.get("allow_automatic_writes", True)),
        )


@dataclass(slots=True)
class AssistantStatus:
    state: str = "idle"
    paused: bool = False
    runtime_ready: bool = False
    runtime_source: str = ""
    runtime_provider: str = ""
    runtime_model: str = ""
    bootstrap_state: str = "pending"
    bootstrap_message: str = ""
    recommended_model_name: str = ""
    recommended_quant: str = ""
    recommended_use_case: str = "chat"
    last_reflection_at: str = ""
    last_reflection_trigger: str = ""
    latest_summary: str = ""
    latest_why: str = ""

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "AssistantStatus":
        data = dict(payload or {})
        return cls(
            state=str(data.get("state") or "idle"),
            paused=bool(data.get("paused", False)),
            runtime_ready=bool(data.get("runtime_ready", False)),
            runtime_source=str(data.get("runtime_source") or ""),
            runtime_provider=str(data.get("runtime_provider") or ""),
            runtime_model=str(data.get("runtime_model") or ""),
            bootstrap_state=str(data.get("bootstrap_state") or "pending"),
            bootstrap_message=str(data.get("bootstrap_message") or ""),
            recommended_model_name=str(data.get("recommended_model_name") or ""),
            recommended_quant=str(data.get("recommended_quant") or ""),
            recommended_use_case=str(data.get("recommended_use_case") or "chat"),
            last_reflection_at=str(data.get("last_reflection_at") or ""),
            last_reflection_trigger=str(data.get("last_reflection_trigger") or ""),
            latest_summary=str(data.get("latest_summary") or ""),
            latest_why=str(data.get("latest_why") or ""),
        )


@dataclass(slots=True)
class AssistantMemoryEntry:
    entry_id: str
    created_at: str
    kind: str
    title: str
    summary: str
    details: str = ""
    why: str = ""
    provenance: str = "assistant_local"
    confidence: float = 0.5
    trigger: str = ""
    context_id: str = ""
    session_id: str = ""
    run_id: str = ""
    tags: list[str] = field(default_factory=list)
    related_node_ids: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def create(
        cls,
        *,
        kind: str,
        title: str,
        summary: str,
        details: str = "",
        why: str = "",
        provenance: str = "assistant_local",
        confidence: float = 0.5,
        trigger: str = "",
        context_id: str = "",
        session_id: str = "",
        run_id: str = "",
        tags: list[str] | None = None,
        related_node_ids: list[str] | None = None,
    ) -> "AssistantMemoryEntry":
        return cls(
            entry_id=str(uuid.uuid4()),
            created_at=assistant_now_iso(),
            kind=str(kind or "reflection"),
            title=str(title or "Companion Reflection"),
            summary=str(summary or "").strip(),
            details=str(details or "").strip(),
            why=str(why or "").strip(),
            provenance=str(provenance or "assistant_local"),
            confidence=max(0.0, min(1.0, _coerce_float(confidence, 0.5))),
            trigger=str(trigger or "").strip(),
            context_id=str(context_id or "").strip(),
            session_id=str(session_id or "").strip(),
            run_id=str(run_id or "").strip(),
            tags=[str(item) for item in (tags or []) if str(item).strip()],
            related_node_ids=[str(item) for item in (related_node_ids or []) if str(item).strip()],
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "AssistantMemoryEntry":
        data = dict(payload or {})
        return cls(
            entry_id=str(data.get("entry_id") or uuid.uuid4()),
            created_at=str(data.get("created_at") or assistant_now_iso()),
            kind=str(data.get("kind") or "reflection"),
            title=str(data.get("title") or "Companion Reflection"),
            summary=str(data.get("summary") or ""),
            details=str(data.get("details") or ""),
            why=str(data.get("why") or ""),
            provenance=str(data.get("provenance") or "assistant_local"),
            confidence=max(0.0, min(1.0, _coerce_float(data.get("confidence"), 0.5))),
            trigger=str(data.get("trigger") or ""),
            context_id=str(data.get("context_id") or ""),
            session_id=str(data.get("session_id") or ""),
            run_id=str(data.get("run_id") or ""),
            tags=[str(item) for item in (data.get("tags") or []) if str(item).strip()],
            related_node_ids=[str(item) for item in (data.get("related_node_ids") or []) if str(item).strip()],
        )


@dataclass(slots=True)
class AssistantPlaybook:
    playbook_id: str
    created_at: str
    title: str
    bullets: list[str] = field(default_factory=list)
    source_session_id: str = ""
    source_run_id: str = ""
    provenance: str = "assistant_local"
    confidence: float = 0.5
    active: bool = True

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def create(
        cls,
        *,
        title: str,
        bullets: list[str],
        source_session_id: str = "",
        source_run_id: str = "",
        provenance: str = "assistant_local",
        confidence: float = 0.5,
    ) -> "AssistantPlaybook":
        return cls(
            playbook_id=str(uuid.uuid4()),
            created_at=assistant_now_iso(),
            title=str(title or "Companion Playbook"),
            bullets=[str(item).strip() for item in bullets if str(item).strip()],
            source_session_id=str(source_session_id or "").strip(),
            source_run_id=str(source_run_id or "").strip(),
            provenance=str(provenance or "assistant_local"),
            confidence=max(0.0, min(1.0, _coerce_float(confidence, 0.5))),
            active=True,
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "AssistantPlaybook":
        data = dict(payload or {})
        return cls(
            playbook_id=str(data.get("playbook_id") or uuid.uuid4()),
            created_at=str(data.get("created_at") or assistant_now_iso()),
            title=str(data.get("title") or "Companion Playbook"),
            bullets=[str(item).strip() for item in (data.get("bullets") or []) if str(item).strip()],
            source_session_id=str(data.get("source_session_id") or ""),
            source_run_id=str(data.get("source_run_id") or ""),
            provenance=str(data.get("provenance") or "assistant_local"),
            confidence=max(0.0, min(1.0, _coerce_float(data.get("confidence"), 0.5))),
            active=bool(data.get("active", True)),
        )


@dataclass(slots=True)
class AssistantBrainLink:
    link_id: str
    created_at: str
    source_node_id: str
    target_node_id: str
    relation: str
    label: str
    provenance: str = "assistant_local"
    summary: str = ""
    confidence: float = 0.5
    session_id: str = ""
    run_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def create(
        cls,
        *,
        source_node_id: str,
        target_node_id: str,
        relation: str,
        label: str,
        provenance: str = "assistant_local",
        summary: str = "",
        confidence: float = 0.5,
        session_id: str = "",
        run_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> "AssistantBrainLink":
        return cls(
            link_id=str(uuid.uuid4()),
            created_at=assistant_now_iso(),
            source_node_id=str(source_node_id or "").strip(),
            target_node_id=str(target_node_id or "").strip(),
            relation=str(relation or "neural_link").strip(),
            label=str(label or relation or "Neural Link").strip(),
            provenance=str(provenance or "assistant_local"),
            summary=str(summary or "").strip(),
            confidence=max(0.0, min(1.0, _coerce_float(confidence, 0.5))),
            session_id=str(session_id or "").strip(),
            run_id=str(run_id or "").strip(),
            metadata=dict(metadata or {}),
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "AssistantBrainLink":
        data = dict(payload or {})
        return cls(
            link_id=str(data.get("link_id") or uuid.uuid4()),
            created_at=str(data.get("created_at") or assistant_now_iso()),
            source_node_id=str(data.get("source_node_id") or ""),
            target_node_id=str(data.get("target_node_id") or ""),
            relation=str(data.get("relation") or "neural_link"),
            label=str(data.get("label") or data.get("relation") or "Neural Link"),
            provenance=str(data.get("provenance") or "assistant_local"),
            summary=str(data.get("summary") or ""),
            confidence=max(0.0, min(1.0, _coerce_float(data.get("confidence"), 0.5))),
            session_id=str(data.get("session_id") or ""),
            run_id=str(data.get("run_id") or ""),
            metadata=dict(data.get("metadata") or {}),
        )
