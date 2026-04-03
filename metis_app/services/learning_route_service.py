"""Learning-route planning for constellation stars."""

from __future__ import annotations

import json
import logging
import pathlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from metis_app.utils.llm_providers import create_llm

log = logging.getLogger(__name__)

LearningRouteStepKind = Literal["orient", "foundations", "synthesis", "apply"]
_STEP_KINDS: tuple[LearningRouteStepKind, ...] = (
    "orient",
    "foundations",
    "synthesis",
    "apply",
)
_STEP_ESTIMATED_MINUTES: dict[LearningRouteStepKind, int] = {
    "orient": 12,
    "foundations": 18,
    "synthesis": 22,
    "apply": 16,
}


@dataclass(frozen=True)
class LearningRouteStarSnapshot:
    id: str
    label: str = ""
    intent: str = ""
    notes: str = ""
    active_manifest_path: str = ""
    linked_manifest_paths: list[str] = field(default_factory=list)
    connected_user_star_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class LearningRouteIndexSummary:
    index_id: str
    manifest_path: str
    document_count: int = 0
    chunk_count: int = 0
    created_at: str = ""
    embedding_signature: str = ""
    brain_pass: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LearningRoutePreviewRequest:
    origin_star: LearningRouteStarSnapshot
    connected_stars: list[LearningRouteStarSnapshot] = field(default_factory=list)
    indexes: list[LearningRouteIndexSummary] = field(default_factory=list)


@dataclass(frozen=True)
class LearningRoutePreviewStep:
    id: str
    kind: LearningRouteStepKind
    title: str
    objective: str
    rationale: str
    manifest_path: str
    source_star_id: str | None
    tutor_prompt: str
    estimated_minutes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "estimated_minutes": self.estimated_minutes,
            "id": self.id,
            "kind": self.kind,
            "manifest_path": self.manifest_path,
            "objective": self.objective,
            "rationale": self.rationale,
            "source_star_id": self.source_star_id,
            "title": self.title,
            "tutor_prompt": self.tutor_prompt,
        }


@dataclass(frozen=True)
class LearningRoutePreview:
    route_id: str
    title: str
    origin_star_id: str
    created_at: str
    updated_at: str
    steps: list[LearningRoutePreviewStep]

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "origin_star_id": self.origin_star_id,
            "route_id": self.route_id,
            "steps": [step.to_dict() for step in self.steps],
            "title": self.title,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class _ManifestCandidate:
    manifest_path: str
    source_star_id: str
    source_star_label: str
    source_description: str
    index_summary: LearningRouteIndexSummary | None = None


def plan_learning_route_preview(
    request: LearningRoutePreviewRequest,
    *,
    settings: dict[str, Any],
) -> LearningRoutePreview:
    candidates = _build_manifest_candidates(request)
    if not candidates:
        raise ValueError("This star needs at least one attached source before METIS can plot a route.")

    fallback_preview = _build_fallback_preview(request, candidates)
    llm_preview = _build_llm_preview(
        request=request,
        fallback_preview=fallback_preview,
        settings=settings,
    )
    return llm_preview or fallback_preview


def _build_manifest_candidates(
    request: LearningRoutePreviewRequest,
) -> list[_ManifestCandidate]:
    origin = request.origin_star
    connected_by_id = {
        star.id: star
        for star in request.connected_stars
        if str(star.id or "").strip()
    }
    index_by_manifest = {
        _normalize_manifest_path(index.manifest_path): index
        for index in request.indexes
        if _normalize_manifest_path(index.manifest_path)
    }
    seen_manifest_paths: set[str] = set()
    candidates: list[_ManifestCandidate] = []

    def append_candidate(
        manifest_path: str,
        *,
        source_star: LearningRouteStarSnapshot,
        source_description: str,
    ) -> None:
        normalized_manifest_path = _normalize_manifest_path(manifest_path)
        if not normalized_manifest_path or normalized_manifest_path in seen_manifest_paths:
            return
        seen_manifest_paths.add(normalized_manifest_path)
        candidates.append(
            _ManifestCandidate(
                manifest_path=normalized_manifest_path,
                source_star_id=source_star.id,
                source_star_label=_normalize_text(source_star.label),
                source_description=source_description,
                index_summary=index_by_manifest.get(normalized_manifest_path),
            )
        )

    append_candidate(
        origin.active_manifest_path,
        source_star=origin,
        source_description="the selected star's active source",
    )

    for manifest_path in origin.linked_manifest_paths:
        if _normalize_manifest_path(manifest_path) == _normalize_manifest_path(origin.active_manifest_path):
            continue
        append_candidate(
            manifest_path,
            source_star=origin,
            source_description="another source already attached to the selected star",
        )

    for connected_star_id in origin.connected_user_star_ids:
        connected_star = connected_by_id.get(connected_star_id)
        if connected_star is None:
            continue
        append_candidate(
            connected_star.active_manifest_path,
            source_star=connected_star,
            source_description="a connected star's active source",
        )

    return candidates


def _build_fallback_preview(
    request: LearningRoutePreviewRequest,
    candidates: list[_ManifestCandidate],
) -> LearningRoutePreview:
    route_id = f"learning-route-{uuid.uuid4()}"
    timestamp = _utc_now_iso()
    topic = _resolve_route_topic(request.origin_star, candidates[0])
    title = f"Route Through the Stars: {topic}"
    steps: list[LearningRoutePreviewStep] = []

    for step_index, kind in enumerate(_STEP_KINDS):
        candidate = candidates[step_index] if step_index < len(candidates) else candidates[step_index % len(candidates)]
        source_name = _resolve_source_name(candidate)
        steps.append(
            LearningRoutePreviewStep(
                id=f"{route_id}-step-{step_index + 1}",
                kind=kind,
                title=_build_fallback_step_title(kind, topic),
                objective=_build_fallback_objective(kind, topic, source_name),
                rationale=_build_fallback_rationale(kind, topic, source_name, candidate),
                manifest_path=candidate.manifest_path,
                source_star_id=_resolve_source_star_id(request.origin_star, candidate),
                tutor_prompt=_build_fallback_tutor_prompt(kind, topic, source_name),
                estimated_minutes=_STEP_ESTIMATED_MINUTES[kind],
            )
        )

    return LearningRoutePreview(
        route_id=route_id,
        title=title,
        origin_star_id=request.origin_star.id,
        created_at=timestamp,
        updated_at=timestamp,
        steps=steps,
    )


def _build_llm_preview(
    *,
    request: LearningRoutePreviewRequest,
    fallback_preview: LearningRoutePreview,
    settings: dict[str, Any],
) -> LearningRoutePreview | None:
    try:
        llm = create_llm(settings)
    except Exception as exc:  # noqa: BLE001
        log.debug("Learning-route planner falling back to templates: %s", exc)
        return None

    index_context = {
        _normalize_manifest_path(index.manifest_path): {
            "brain_pass": dict(index.brain_pass or {}),
            "chunk_count": int(index.chunk_count or 0),
            "document_count": int(index.document_count or 0),
            "index_id": _normalize_text(index.index_id),
            "manifest_path": _normalize_manifest_path(index.manifest_path),
        }
        for index in request.indexes
        if _normalize_manifest_path(index.manifest_path)
    }
    system_prompt = (
        "You are planning a four-stop METIS learning route.\n"
        "Keep the fixed step order exactly as: orient, foundations, synthesis, apply.\n"
        "Do not add steps. Do not remove steps. Do not change each step's id, kind, manifest_path, or source_star_id.\n"
        "Return strict JSON with this exact shape:\n"
        '{"title": "string", "steps": [{"id": "string", "title": "string", "objective": "string", '
        '"rationale": "string", "tutor_prompt": "string", "estimated_minutes": 12}]}\n'
        "Make the wording vivid, course-like, and grounded in the provided star and source context."
    )
    human_payload = {
        "connected_stars": [
            {
                "active_manifest_path": _normalize_manifest_path(star.active_manifest_path),
                "id": star.id,
                "intent": _normalize_text(star.intent),
                "label": _normalize_text(star.label),
                "notes": _normalize_text(star.notes),
            }
            for star in request.connected_stars
        ],
        "index_context": index_context,
        "origin_star": {
            "id": request.origin_star.id,
            "intent": _normalize_text(request.origin_star.intent),
            "label": _normalize_text(request.origin_star.label),
            "notes": _normalize_text(request.origin_star.notes),
        },
        "route_preview": fallback_preview.to_dict(),
    }

    try:
        raw = llm.invoke(
            [
                {"type": "system", "content": system_prompt},
                {"type": "human", "content": json.dumps(human_payload, ensure_ascii=False, indent=2)},
            ]
        )
        payload = _extract_json_object(str(getattr(raw, "content", raw) or ""))
        if not isinstance(payload, dict):
            return None
        return _merge_llm_payload(fallback_preview, payload)
    except Exception as exc:  # noqa: BLE001
        log.debug("Learning-route planner JSON generation failed: %s", exc)
        return None


def _merge_llm_payload(
    fallback_preview: LearningRoutePreview,
    payload: dict[str, Any],
) -> LearningRoutePreview | None:
    raw_steps = payload.get("steps")
    if not isinstance(raw_steps, list) or len(raw_steps) != len(fallback_preview.steps):
        return None

    raw_steps_by_id: dict[str, dict[str, Any]] = {}
    for raw_step in raw_steps:
        if not isinstance(raw_step, dict):
            return None
        step_id = _normalize_text(raw_step.get("id"))
        if not step_id or step_id in raw_steps_by_id:
            return None
        raw_steps_by_id[step_id] = raw_step

    expected_ids = {step.id for step in fallback_preview.steps}
    if set(raw_steps_by_id) != expected_ids:
        return None

    merged_steps: list[LearningRoutePreviewStep] = []
    for fallback_step in fallback_preview.steps:
        raw_step = raw_steps_by_id[fallback_step.id]
        merged_steps.append(
            LearningRoutePreviewStep(
                id=fallback_step.id,
                kind=fallback_step.kind,
                title=_normalize_text(raw_step.get("title")) or fallback_step.title,
                objective=_normalize_text(raw_step.get("objective")) or fallback_step.objective,
                rationale=_normalize_text(raw_step.get("rationale")) or fallback_step.rationale,
                manifest_path=fallback_step.manifest_path,
                source_star_id=fallback_step.source_star_id,
                tutor_prompt=_normalize_text(raw_step.get("tutor_prompt")) or fallback_step.tutor_prompt,
                estimated_minutes=_normalize_estimated_minutes(
                    raw_step.get("estimated_minutes"),
                    fallback_step.estimated_minutes,
                ),
            )
        )

    return LearningRoutePreview(
        route_id=fallback_preview.route_id,
        title=_normalize_text(payload.get("title")) or fallback_preview.title,
        origin_star_id=fallback_preview.origin_star_id,
        created_at=fallback_preview.created_at,
        updated_at=fallback_preview.updated_at,
        steps=merged_steps,
    )


def _resolve_route_topic(
    origin_star: LearningRouteStarSnapshot,
    primary_candidate: _ManifestCandidate,
) -> str:
    return (
        _normalize_text(origin_star.label)
        or _normalize_text(origin_star.intent)
        or _resolve_source_name(primary_candidate)
    )


def _resolve_source_name(candidate: _ManifestCandidate) -> str:
    if candidate.index_summary is not None and _normalize_text(candidate.index_summary.index_id):
        return _normalize_text(candidate.index_summary.index_id)
    return _manifest_title(candidate.manifest_path)


def _resolve_source_star_id(
    origin_star: LearningRouteStarSnapshot,
    candidate: _ManifestCandidate,
) -> str | None:
    connected_ids = set(origin_star.connected_user_star_ids)
    if candidate.source_star_id in connected_ids:
        return candidate.source_star_id
    return None


def _build_fallback_step_title(kind: LearningRouteStepKind, topic: str) -> str:
    if kind == "orient":
        return f"Orient Around {topic}"
    if kind == "foundations":
        return f"Lay the Foundations for {topic}"
    if kind == "synthesis":
        return "Synthesize the Constellation"
    return f"Apply {topic}"


def _build_fallback_objective(
    kind: LearningRouteStepKind,
    topic: str,
    source_name: str,
) -> str:
    if kind == "orient":
        return f"Get a fast, confident overview of {topic} by using {source_name} to map the big ideas and vocabulary."
    if kind == "foundations":
        return f"Use {source_name} to build the core concepts, assumptions, and mechanics that make {topic} legible."
    if kind == "synthesis":
        return f"Connect the pieces from earlier stops with {source_name} so {topic} becomes a usable mental model."
    return f"Use {source_name} to turn {topic} into an applied move you can explain, test, or practice."


def _build_fallback_rationale(
    kind: LearningRouteStepKind,
    topic: str,
    source_name: str,
    candidate: _ManifestCandidate,
) -> str:
    if kind == "orient":
        return f"Start with {source_name} because it gives METIS a clean launch point for {topic} without overloading the learner."
    if kind == "foundations":
        return f"{source_name} is positioned here to make the underlying structure of {topic} feel steady before the route widens."
    if kind == "synthesis":
        return f"This stop uses {source_name} to weave the route together and reveal how the constellation around {topic} actually connects."
    return (
        f"{source_name} closes the route with an applied lens so {topic} leaves the page and becomes something you can use. "
        f"It is grounded in {candidate.source_description}."
    )


def _build_fallback_tutor_prompt(
    kind: LearningRouteStepKind,
    topic: str,
    source_name: str,
) -> str:
    if kind == "orient":
        return (
            f"Tutor me through an orientation to {topic} using {source_name}. "
            "Start with the big picture, define the key terms, and ask two check-in questions before moving on."
        )
    if kind == "foundations":
        return (
            f"Tutor me on the foundations of {topic} using {source_name}. "
            "Teach the core ideas step by step, use one analogy, and pause for a quick understanding check."
        )
    if kind == "synthesis":
        return (
            f"Tutor me on how the main ideas of {topic} connect by drawing on {source_name}. "
            "Help me compare concepts, surface tradeoffs, and ask me to explain the model back in my own words."
        )
    return (
        f"Tutor me on applying {topic} using {source_name}. "
        "Give me one realistic scenario, coach me through the decision process, and finish with a short practice exercise."
    )


def _extract_json_object(raw_text: str) -> dict[str, Any] | None:
    start = raw_text.find("{")
    end = raw_text.rfind("}") + 1
    if start == -1 or end <= start:
        return None
    try:
        payload = json.loads(raw_text[start:end])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _normalize_estimated_minutes(value: Any, fallback: int) -> int:
    try:
        estimated_minutes = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(5, min(90, estimated_minutes))


def _normalize_manifest_path(value: Any) -> str:
    normalized = _normalize_text(value)
    return normalized


def _normalize_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _manifest_title(manifest_path: str) -> str:
    stem = pathlib.Path(manifest_path).stem.replace("-", " ").replace("_", " ").strip()
    if not stem:
        return "this source"
    return stem.title()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "LearningRouteIndexSummary",
    "LearningRoutePreview",
    "LearningRoutePreviewRequest",
    "LearningRoutePreviewStep",
    "LearningRouteStarSnapshot",
    "plan_learning_route_preview",
]
