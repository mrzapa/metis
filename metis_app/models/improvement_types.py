"""Typed records for the Ladder-inspired improvement pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import json
import re
from typing import Any
import uuid

IMPROVEMENT_ARTIFACT_TYPES: tuple[str, ...] = (
    "source",
    "idea",
    "hypothesis",
    "experiment",
    "algorithm",
    "result",
)

IMPROVEMENT_STATUSES: tuple[str, ...] = (
    "draft",
    "active",
    "testing",
    "complete",
    "archived",
)


def improvement_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify_improvement_title(title: str, *, fallback: str = "improvement-entry") -> str:
    candidate = re.sub(r"[^a-z0-9]+", "-", str(title or "").strip().lower()).strip("-")
    return candidate[:80] or fallback


def _coerce_json_object(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _coerce_str_list(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def _normalize_artifact_type(value: Any) -> str:
    candidate = str(value or "idea").strip().lower()
    if candidate not in IMPROVEMENT_ARTIFACT_TYPES:
        raise ValueError(
            f"artifact_type must be one of {', '.join(IMPROVEMENT_ARTIFACT_TYPES)}"
        )
    return candidate


def _normalize_status(value: Any, *, default: str = "draft") -> str:
    candidate = str(value or default).strip().lower() or default
    if candidate not in IMPROVEMENT_STATUSES:
        raise ValueError(f"status must be one of {', '.join(IMPROVEMENT_STATUSES)}")
    return candidate


@dataclass(slots=True)
class ImprovementEntry:
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
    tags: list[str] = field(default_factory=list)
    upstream_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    slug: str = ""
    saved_at: str = ""
    markdown_path: str = ""

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def create(
        cls,
        *,
        artifact_key: str,
        artifact_type: str,
        title: str,
        summary: str = "",
        body_md: str = "",
        session_id: str = "",
        run_id: str = "",
        status: str = "draft",
        tags: list[str] | None = None,
        upstream_ids: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ImprovementEntry":
        now = improvement_now_iso()
        normalized_title = str(title or "").strip() or "Untitled Improvement Entry"
        normalized_key = str(artifact_key or "").strip()
        if not normalized_key:
            raise ValueError("artifact_key must not be empty")
        return cls(
            entry_id=str(uuid.uuid4()),
            artifact_key=normalized_key,
            artifact_type=_normalize_artifact_type(artifact_type),
            created_at=now,
            updated_at=now,
            title=normalized_title,
            summary=str(summary or "").strip(),
            body_md=str(body_md or "").strip(),
            session_id=str(session_id or "").strip(),
            run_id=str(run_id or "").strip(),
            status=_normalize_status(status, default="draft"),
            tags=_coerce_str_list(tags or []),
            upstream_ids=_coerce_str_list(upstream_ids or []),
            metadata=_coerce_json_object(metadata),
            slug=slugify_improvement_title(normalized_title),
            saved_at=now,
            markdown_path="",
        )

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "ImprovementEntry":
        data = dict(payload or {})
        title = str(data.get("title") or "Untitled Improvement Entry").strip()
        return cls(
            entry_id=str(data.get("entry_id") or uuid.uuid4()),
            artifact_key=str(data.get("artifact_key") or "").strip(),
            artifact_type=_normalize_artifact_type(data.get("artifact_type") or "idea"),
            created_at=str(data.get("created_at") or improvement_now_iso()),
            updated_at=str(data.get("updated_at") or data.get("created_at") or improvement_now_iso()),
            title=title,
            summary=str(data.get("summary") or "").strip(),
            body_md=str(data.get("body_md") or "").strip(),
            session_id=str(data.get("session_id") or "").strip(),
            run_id=str(data.get("run_id") or "").strip(),
            status=_normalize_status(data.get("status"), default="draft"),
            tags=_coerce_str_list(data.get("tags") or []),
            upstream_ids=_coerce_str_list(data.get("upstream_ids") or []),
            metadata=_coerce_json_object(data.get("metadata")),
            slug=str(data.get("slug") or "").strip() or slugify_improvement_title(title),
            saved_at=str(data.get("saved_at") or data.get("created_at") or improvement_now_iso()),
            markdown_path=str(data.get("markdown_path") or "").strip(),
        )

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ImprovementEntry":
        return cls.from_payload(
            {
                "entry_id": row.get("entry_id"),
                "artifact_key": row.get("artifact_key"),
                "artifact_type": row.get("artifact_type"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "title": row.get("title"),
                "summary": row.get("summary"),
                "body_md": row.get("body_md"),
                "session_id": row.get("session_id"),
                "run_id": row.get("run_id"),
                "status": row.get("status"),
                "tags": json.loads(row.get("tags_json") or "[]"),
                "upstream_ids": json.loads(row.get("upstream_ids_json") or "[]"),
                "metadata": json.loads(row.get("metadata_json") or "{}"),
                "slug": row.get("slug"),
                "saved_at": row.get("saved_at"),
                "markdown_path": row.get("markdown_path"),
            }
        )
