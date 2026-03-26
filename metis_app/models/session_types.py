"""Typed session and evidence records for MVC parity features."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from typing import Any


@dataclass(slots=True)
class EvidenceSource:
    """Structured retrieved evidence attached to an assistant response."""

    sid: str
    source: str
    snippet: str
    chunk_id: str = ""
    chunk_idx: int | None = None
    score: float | None = None
    header_path: str = ""
    breadcrumb: str = ""
    title: str = ""
    label: str = ""
    section_hint: str = ""
    locator: str = ""
    date: str = ""
    timestamp: str = ""
    speaker: str = ""
    actor: str = ""
    entry_type: str = ""
    file_path: str = ""
    anchor: str = ""
    excerpt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sid": self.sid,
            "source": self.source,
            "snippet": self.snippet,
            "chunk_id": self.chunk_id,
            "chunk_idx": self.chunk_idx,
            "score": self.score,
            "header_path": self.header_path,
            "breadcrumb": self.breadcrumb or self.header_path,
            "title": self.title or self.source,
            "label": self.label or self.title or self.source,
            "section_hint": self.section_hint,
            "locator": self.locator,
            "date": self.date,
            "timestamp": self.timestamp,
            "speaker": self.speaker,
            "actor": self.actor,
            "type": self.entry_type,
            "file_path": self.file_path,
            "anchor": self.anchor,
            "excerpt": self.excerpt or self.snippet,
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EvidenceSource":
        data = dict(payload or {})
        snippet = str(
            data.get("snippet")
            or data.get("excerpt")
            or data.get("text")
            or ""
        )
        source = str(
            data.get("source")
            or data.get("title")
            or data.get("source_title")
            or "unknown"
        )
        score = data.get("score")
        try:
            score = float(score) if score is not None else None
        except (TypeError, ValueError):
            score = None

        chunk_idx = data.get("chunk_idx")
        try:
            chunk_idx = int(chunk_idx) if chunk_idx is not None else None
        except (TypeError, ValueError):
            chunk_idx = None

        header_path = str(data.get("header_path") or "").strip()
        breadcrumb = str(
            data.get("breadcrumb")
            or " > ".join(data.get("breadcrumb_tokens") or [])
            or header_path
        ).strip()

        return cls(
            sid=str(data.get("sid") or ""),
            source=source,
            snippet=snippet,
            chunk_id=str(data.get("chunk_id") or data.get("node_id") or ""),
            chunk_idx=chunk_idx,
            score=score,
            header_path=header_path,
            breadcrumb=breadcrumb,
            title=str(data.get("title") or data.get("source_title") or source),
            label=str(data.get("label") or data.get("title") or data.get("source_title") or source),
            section_hint=str(
                data.get("section_hint")
                or data.get("section")
                or data.get("chapter")
                or ""
            ),
            locator=str(data.get("locator") or data.get("position_hint") or ""),
            date=str(data.get("date") or data.get("month_bucket") or ""),
            timestamp=str(data.get("timestamp") or ""),
            speaker=str(data.get("speaker") or ""),
            actor=str(data.get("actor") or ""),
            entry_type=str(data.get("type") or ""),
            file_path=str(
                data.get("file_path")
                or ((data.get("metadata") or {}).get("source_path"))
                or ""
            ),
            anchor=str(data.get("anchor") or ""),
            excerpt=str(data.get("excerpt") or snippet),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass(slots=True)
class SessionSummary:
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
    extra_json: str

    @property
    def extra(self) -> dict[str, Any]:
        try:
            parsed = json.loads(self.extra_json or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @property
    def skill_ids(self) -> list[str]:
        extra = self.extra
        skills = dict(extra.get("skills") or {})
        return [str(item) for item in (skills.get("selected") or []) if str(item).strip()]

    @property
    def primary_skill_id(self) -> str:
        extra = self.extra
        skills = dict(extra.get("skills") or {})
        return str(skills.get("primary") or "").strip()

    @property
    def skill_reasons(self) -> dict[str, str]:
        extra = self.extra
        skills = dict(extra.get("skills") or {})
        return {
            str(key): str(value)
            for key, value in dict(skills.get("reasons") or {}).items()
            if str(key).strip()
        }


@dataclass(slots=True)
class SessionMessage:
    role: str
    content: str
    ts: str
    run_id: str = ""
    sources: list[EvidenceSource] = field(default_factory=list)


@dataclass(slots=True)
class SessionFeedback:
    feedback_id: str
    session_id: str
    run_id: str
    vote: int
    note: str
    ts: str


@dataclass(slots=True)
class SessionDetail:
    summary: SessionSummary
    messages: list[SessionMessage] = field(default_factory=list)
    feedback: list[SessionFeedback] = field(default_factory=list)
    traces: dict[str, Any] = field(default_factory=dict)
