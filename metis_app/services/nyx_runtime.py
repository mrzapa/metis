"""NyxUI intent detection and runtime artifact assembly for assistant queries."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

from metis_app.services.nyx_catalog import (
    CuratedNyxComponent,
    NyxCatalogBroker,
    NyxCatalogComponentDetail,
)

_NYX_SCHEMA_VERSION = "1.0"
_NYX_ARTIFACT_MIME_TYPE = "application/vnd.metis.nyx+json"
NYX_INSTALL_ACTION_TYPE = "nyx_install"
_MAX_CANDIDATES = 3
_MIN_COMPONENT_MATCH_SCORE = 14

_LOW_SIGNAL_COMPONENT_TERMS = {
    "background",
    "card",
    "component",
    "effect",
}

_STOPWORDS = {
    "a",
    "an",
    "and",
    "app",
    "build",
    "create",
    "design",
    "for",
    "from",
    "help",
    "i",
    "in",
    "interface",
    "into",
    "is",
    "it",
    "make",
    "me",
    "my",
    "of",
    "on",
    "or",
    "page",
    "screen",
    "show",
    "something",
    "that",
    "the",
    "this",
    "to",
    "ui",
    "use",
    "want",
    "with",
}

_UI_ACTION_TERMS = {
    "add",
    "build",
    "create",
    "craft",
    "design",
    "generate",
    "implement",
    "make",
    "need",
    "redesign",
    "use",
    "want",
}

_UI_SURFACE_TERMS = {
    "component",
    "dashboard",
    "hero",
    "interface",
    "landing",
    "layout",
    "page",
    "screen",
    "section",
    "ui",
}

_UI_LAYOUT_TERMS = {
    "dashboard",
    "hero",
    "landing",
    "layout",
    "page",
    "screen",
    "section",
}

_UI_PATTERN_TERMS = {
    "badge",
    "banner",
    "button",
    "card",
    "carousel",
    "cursor",
    "drawer",
    "form",
    "glass",
    "grid",
    "keyboard",
    "modal",
    "navbar",
    "navigation",
    "panel",
    "player",
    "pricing",
    "repo",
    "repository",
    "ripple",
    "scanner",
    "sidebar",
    "tabs",
}

_UI_INTERACTION_TERMS = {
    "animate",
    "animated",
    "animation",
    "cursor",
    "frosted",
    "glassmorphism",
    "glow",
    "hover",
    "immersive",
    "interactive",
    "motion",
    "reveal",
    "scanline",
    "shader",
    "three",
    "translucent",
}

_COMPONENT_HINT_PHRASES: dict[str, tuple[str, ...]] = {
    "animated-grainy-bg": ("grain", "grainy", "backdrop", "background", "hero background"),
    "animated-text": ("animated text", "headline", "title animation", "text reveal"),
    "apple-glass-effect": ("glass", "frosted", "glassmorphism", "translucent", "apple glass"),
    "custom-cursor": ("cursor", "custom cursor", "pointer trail", "follow cursor"),
    "github-repo-card": ("github", "repo", "repository", "repository card"),
    "glow-card": ("glow", "glowing", "feature card", "hover card", "pricing card"),
    "image-scanner": ("scanner", "scanline", "image scan", "media scan"),
    "keyboard": ("keyboard", "hotkey", "shortcut", "keycap"),
    "music-player": ("music", "audio player", "playlist", "player"),
    "reveal-card": ("reveal", "gallery card", "media card", "showcase card"),
    "water-ripple-effect": ("water", "ripple", "liquid", "shader", "canvas effect"),
}


def _tokenize(text: str) -> tuple[str, ...]:
    return tuple(token for token in re.findall(r"[a-z0-9]+", str(text or "").lower()) if token)


def _unique_strings(values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        unique.append(normalized)
    return tuple(unique)


def append_system_instruction(base_instructions: str, extra_instructions: str) -> str:
    base_text = str(base_instructions or "").strip()
    extra_text = str(extra_instructions or "").strip()
    if not extra_text:
        return base_text
    if not base_text:
        return extra_text
    if extra_text in base_text:
        return base_text
    return f"{base_text}\n\n{extra_text}".strip()


def merge_arrow_artifacts(existing: Any, additions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized_existing: list[dict[str, Any]] = []
    if isinstance(existing, dict):
        normalized_existing.append(dict(existing))
    elif isinstance(existing, list):
        normalized_existing.extend(dict(item) for item in existing if isinstance(item, dict))

    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for artifact in list(additions or []) + normalized_existing:
        artifact_type = str(artifact.get("type") or "").strip()
        artifact_id = str(artifact.get("id") or artifact_type).strip()
        key = (artifact_type, artifact_id)
        if artifact_type and key in seen:
            continue
        if artifact_type:
            seen.add(key)
        merged.append(dict(artifact))
    return merged


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _component_names_from_selection_artifacts(artifacts: Any) -> tuple[str, ...]:
    names: list[str] = []
    candidates: list[dict[str, Any]] = []
    if isinstance(artifacts, dict):
        candidates = [artifacts]
    elif isinstance(artifacts, list):
        candidates = [artifact for artifact in artifacts if isinstance(artifact, dict)]

    for artifact in candidates:
        if str(artifact.get("type") or "").strip() != "nyx_component_selection":
            continue
        payload = artifact.get("payload")
        if not isinstance(payload, dict):
            continue
        for component in list(payload.get("selected_components") or []):
            if not isinstance(component, dict):
                continue
            component_name = str(component.get("component_name") or "").strip().lower()
            if component_name:
                names.append(component_name)
    return _unique_strings(names)


def _component_names_from_runtime_payload(settings: dict[str, Any]) -> tuple[str, ...]:
    runtime_payload = settings.get("nyx_runtime")
    if not isinstance(runtime_payload, dict):
        return ()

    names: list[str] = []
    for component in list(runtime_payload.get("selected_components") or []):
        if not isinstance(component, dict):
            continue
        component_name = str(component.get("component_name") or "").strip().lower()
        if component_name:
            names.append(component_name)
    return _unique_strings(names)


def _proposal_component_payload(detail: NyxCatalogComponentDetail) -> dict[str, Any]:
    return {
        "component_name": detail.component_name,
        "title": detail.title,
        "description": detail.description,
        "curated_description": detail.curated_description,
        "component_type": detail.component_type,
        "install_target": detail.install_target,
        "registry_url": detail.registry_url,
        "source_repo": detail.source_repo,
        "required_dependencies": list(detail.required_dependencies),
        "dependencies": list(detail.dependencies),
        "dev_dependencies": list(detail.dev_dependencies),
        "registry_dependencies": list(detail.registry_dependencies),
        "file_count": int(detail.file_count),
        "targets": list(detail.targets),
        "review_status": detail.review_status,
        "previewable": bool(detail.previewable),
        "installable": bool(detail.installable),
        "install_path_policy": detail.install_path_policy,
        "install_path_safe": bool(detail.install_path_safe),
        "install_path_issues": list(detail.install_path_issues),
        "audit_issues": list(detail.audit_issues),
    }


def build_nyx_install_actions(
    *,
    run_id: str,
    settings: dict[str, Any],
    broker: NyxCatalogBroker,
    artifacts: Any = None,
) -> list[dict[str, Any]]:
    runtime_payload = settings.get("nyx_runtime")
    if not isinstance(runtime_payload, dict):
        return []

    component_names = _component_names_from_selection_artifacts(artifacts)
    if not component_names:
        component_names = _component_names_from_runtime_payload(settings)
    if not component_names:
        return []

    installable_components: list[NyxCatalogComponentDetail] = []
    for component_name in component_names:
        try:
            detail = broker.get_component_detail(component_name)
        except (RuntimeError, ValueError):
            continue
        if not detail.installable:
            continue
        if detail.review_status != "installable":
            continue
        if not detail.install_path_safe:
            continue
        installable_components.append(detail)

    if not installable_components:
        return []

    proposal_components = [
        _proposal_component_payload(detail)
        for detail in installable_components
    ]
    proposal_seed = {
        "schema_version": _NYX_SCHEMA_VERSION,
        "source": "nyx_runtime",
        "run_id": str(run_id or "").strip(),
        "query": str(runtime_payload.get("query") or "").strip(),
        "intent_type": str(runtime_payload.get("intent_type") or "").strip(),
        "matched_signals": list(_unique_strings(list(runtime_payload.get("matched_signals") or []))),
        "component_names": [component["component_name"] for component in proposal_components],
        "components": proposal_components,
    }
    digest = hashlib.sha256(_canonical_json(proposal_seed).encode("utf-8")).hexdigest()[:24]
    action_id = f"nyx-install:{digest}"
    proposal_token = f"nyx-proposal:{digest}"
    proposal = {
        **proposal_seed,
        "proposal_token": proposal_token,
        "component_count": len(proposal_components),
    }

    component_titles = [component.get("title") or component["component_name"] for component in proposal_components]
    summary_tail = ", ".join(component_titles[:3])
    if len(component_titles) > 3:
        summary_tail += ", ..."

    return [
        {
            "action_id": action_id,
            "action_type": NYX_INSTALL_ACTION_TYPE,
            "label": "Approve Nyx install proposal",
            "summary": (
                f"Approve installing {len(proposal_components)} reviewed Nyx component(s): {summary_tail}."
            ),
            "requires_approval": True,
            "run_action_endpoint": f"/v1/runs/{str(run_id or '').strip()}/actions",
            "payload": {
                "action_id": action_id,
                "action_type": NYX_INSTALL_ACTION_TYPE,
                "proposal_token": proposal_token,
                "component_count": len(proposal_components),
                "component_names": list(proposal.get("component_names") or []),
            },
            "proposal": proposal,
        }
    ]


def find_persisted_nyx_install_action(
    *,
    run_id: str,
    trace_store: Any,
    action_id: str = "",
    proposal_token: str = "",
    allow_latest: bool = False,
) -> dict[str, Any] | None:
    normalized_run_id = str(run_id or "").strip()
    normalized_action_id = str(action_id or "").strip()
    normalized_token = str(proposal_token or "").strip()
    if not normalized_run_id or (
        not allow_latest and not normalized_action_id and not normalized_token
    ):
        return None

    for row in reversed(list(trace_store.read_run_events(normalized_run_id) or [])):
        payload = row.get("payload") if isinstance(row, dict) else {}
        if not isinstance(payload, dict):
            continue
        raw_actions = payload.get("actions")
        if not isinstance(raw_actions, list):
            continue
        for action in raw_actions:
            if not isinstance(action, dict):
                continue
            if str(action.get("action_type") or "").strip() != NYX_INSTALL_ACTION_TYPE:
                continue
            if allow_latest and not normalized_action_id and not normalized_token:
                return dict(action)
            candidate_action_id = str(action.get("action_id") or "").strip()
            candidate_payload = action.get("payload") if isinstance(action.get("payload"), dict) else {}
            candidate_proposal = action.get("proposal") if isinstance(action.get("proposal"), dict) else {}
            candidate_token = str(
                candidate_payload.get("proposal_token")
                or candidate_proposal.get("proposal_token")
                or ""
            ).strip()
            if normalized_action_id and candidate_action_id != normalized_action_id:
                continue
            if normalized_token and candidate_token != normalized_token:
                continue
            return dict(action)
    return None


@dataclass(frozen=True)
class NyxIntentAnalysis:
    intent_type: str
    confidence: float
    matched_signals: tuple[str, ...]


@dataclass(frozen=True)
class NyxComponentCandidate:
    detail: NyxCatalogComponentDetail
    match_score: int
    reasons: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "component_name": self.detail.component_name,
            "title": self.detail.title,
            "description": self.detail.description,
            "curated_description": self.detail.curated_description,
            "component_type": self.detail.component_type,
            "install_target": self.detail.install_target,
            "registry_url": self.detail.registry_url,
            "source_repo": self.detail.source_repo,
            "match_score": int(self.match_score),
            "match_reason": "; ".join(self.reasons),
            "match_reasons": list(self.reasons),
            "preview_targets": list(self.detail.targets),
            "targets": list(self.detail.targets),
            "file_count": int(self.detail.file_count),
            "required_dependencies": list(self.detail.required_dependencies),
            "dependencies": list(self.detail.dependencies),
            "dev_dependencies": list(self.detail.dev_dependencies),
            "registry_dependencies": list(self.detail.registry_dependencies),
        }


@dataclass(frozen=True)
class NyxRuntimeContext:
    query: str
    intent: NyxIntentAnalysis
    selected_components: tuple[NyxComponentCandidate, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": _NYX_SCHEMA_VERSION,
            "query": self.query,
            "intent_type": self.intent.intent_type,
            "confidence": float(self.intent.confidence),
            "matched_signals": list(self.intent.matched_signals),
            "selected_components": [candidate.to_payload() for candidate in self.selected_components],
        }

    def system_instruction_append(self) -> str:
        lines = [
            "Nyx UI integration is active for this request.",
            "Prefer the resolved NyxUI components below when you recommend UI building blocks.",
            "Use concrete component names, install targets, and fit-based reasoning.",
            "Do not invent NyxUI components that are not in this resolved set.",
            f"Resolved intent: {self.intent.intent_type} (confidence {self.intent.confidence:.2f}).",
            "Resolved NyxUI candidates:",
        ]
        for candidate in self.selected_components:
            detail = candidate.detail
            dependencies = _unique_strings(list(detail.required_dependencies) + list(detail.dependencies))
            dependency_text = ", ".join(dependencies) if dependencies else "none"
            reason_text = "; ".join(candidate.reasons) if candidate.reasons else detail.curated_description
            lines.append(
                f"- {detail.title} ({detail.component_name}, {detail.install_target}) - "
                f"{detail.description or detail.curated_description}. "
                f"Reason: {reason_text}. Dependencies: {dependency_text}. Registry: {detail.registry_url}"
            )
        return "\n".join(lines)

    def to_artifacts(self) -> list[dict[str, Any]]:
        return [
            self._selection_artifact(),
            self._install_plan_artifact(),
            self._dependency_report_artifact(),
        ]

    def _selection_artifact(self) -> dict[str, Any]:
        payload = self.to_payload()
        payload["selection_reason"] = (
            "NyxUI candidates were resolved from the live prompt using the local curated catalog."
        )
        return {
            "id": "nyx_component_selection",
            "type": "nyx_component_selection",
            "summary": f"Nyx matched {len(self.selected_components)} component candidate(s) for this UI request.",
            "path": "nyx/component-selection",
            "mime_type": _NYX_ARTIFACT_MIME_TYPE,
            "payload": payload,
        }

    def _install_plan_artifact(self) -> dict[str, Any]:
        payload = {
            "schema_version": _NYX_SCHEMA_VERSION,
            "query": self.query,
            "intent_type": self.intent.intent_type,
            "components": [
                {
                    "component_name": candidate.detail.component_name,
                    "title": candidate.detail.title,
                    "install_target": candidate.detail.install_target,
                    "registry_url": candidate.detail.registry_url,
                    "targets": list(candidate.detail.targets),
                    "file_count": int(candidate.detail.file_count),
                    "dependency_packages": list(
                        _unique_strings(
                            list(candidate.detail.required_dependencies) + list(candidate.detail.dependencies)
                        )
                    ),
                    "steps": [
                        {
                            "step_type": "registry_add",
                            "label": f"Add {candidate.detail.title} from the NyxUI registry.",
                            "command": f"npx shadcn@latest add {candidate.detail.registry_url}",
                        }
                    ],
                }
                for candidate in self.selected_components
            ],
            "package_manager_note": (
                "Install the dependency packages with the workspace package manager in use."
            ),
        }
        return {
            "id": "nyx_install_plan",
            "type": "nyx_install_plan",
            "summary": "Nyx install targets, registry URLs, and file targets for the resolved components.",
            "path": "nyx/install-plan",
            "mime_type": _NYX_ARTIFACT_MIME_TYPE,
            "payload": payload,
        }

    def _dependency_report_artifact(self) -> dict[str, Any]:
        required_packages = _package_entries(self.selected_components, "required", lambda detail: detail.required_dependencies)
        runtime_packages = _package_entries(self.selected_components, "runtime", lambda detail: detail.dependencies)
        dev_packages = _package_entries(self.selected_components, "dev", lambda detail: detail.dev_dependencies)
        registry_packages = _package_entries(
            self.selected_components,
            "registry",
            lambda detail: detail.registry_dependencies,
        )
        payload = {
            "schema_version": _NYX_SCHEMA_VERSION,
            "query": self.query,
            "component_count": len(self.selected_components),
            "packages": required_packages + runtime_packages + dev_packages + registry_packages,
            "groups": {
                "required": required_packages,
                "runtime": runtime_packages,
                "dev": dev_packages,
                "registry": registry_packages,
            },
        }
        return {
            "id": "nyx_dependency_report",
            "type": "nyx_dependency_report",
            "summary": "Nyx dependency rollup across the resolved components.",
            "path": "nyx/dependencies",
            "mime_type": _NYX_ARTIFACT_MIME_TYPE,
            "payload": payload,
        }


def detect_nyx_intent(query: str) -> NyxIntentAnalysis | None:
    prompt = str(query or "").strip()
    if not prompt:
        return None

    prompt_lower = prompt.lower()
    query_tokens = set(_tokenize(prompt_lower))
    action_hits = sorted(query_tokens & _UI_ACTION_TERMS)
    surface_hits = sorted(query_tokens & _UI_SURFACE_TERMS)
    layout_hits = sorted(query_tokens & _UI_LAYOUT_TERMS)
    pattern_hits = sorted(query_tokens & _UI_PATTERN_TERMS)
    interaction_hits = sorted(query_tokens & _UI_INTERACTION_TERMS)
    explicit_nyx = any(token in prompt_lower for token in ("nyxui", "@nyx/", "nyxui.com/r/", " nyx "))
    alias_hits = sorted(
        phrase
        for phrases in _COMPONENT_HINT_PHRASES.values()
        for phrase in phrases
        if phrase in prompt_lower
    )

    score = 0
    signals: list[str] = []
    if explicit_nyx:
        score += 8
        signals.append("explicit_nyx")
    if action_hits:
        score += 2 * min(len(action_hits), 2)
        signals.extend(f"action:{item}" for item in action_hits[:2])
    if surface_hits:
        score += 2 * min(len(surface_hits), 3)
        signals.extend(f"surface:{item}" for item in surface_hits[:3])
    if pattern_hits:
        score += 2 * min(len(pattern_hits), 3)
        signals.extend(f"pattern:{item}" for item in pattern_hits[:3])
    if interaction_hits:
        score += min(len(interaction_hits), 4)
        signals.extend(f"interaction:{item}" for item in interaction_hits[:4])
    if alias_hits:
        score += 2 * min(len(alias_hits), 3)
        signals.extend(f"hint:{item}" for item in alias_hits[:3])

    if score < 5:
        return None
    if not (explicit_nyx or surface_hits or pattern_hits or interaction_hits or alias_hits):
        return None

    if layout_hits:
        intent_type = "ui_layout_request"
    elif interaction_hits:
        intent_type = "interaction_heavy_ui"
    elif pattern_hits:
        intent_type = "interface_pattern_selection"
    else:
        intent_type = "component_generation"

    confidence = round(min(0.98, 0.35 + 0.05 * min(score, 12)), 2)
    return NyxIntentAnalysis(
        intent_type=intent_type,
        confidence=confidence,
        matched_signals=_unique_strings(signals),
    )


def build_nyx_runtime_context(
    query: str,
    broker: NyxCatalogBroker,
    *,
    limit: int = _MAX_CANDIDATES,
) -> NyxRuntimeContext | None:
    analysis = detect_nyx_intent(query)
    if analysis is None:
        return None

    candidates = _resolve_component_candidates(query, broker, limit=max(1, min(limit, _MAX_CANDIDATES)))
    if not candidates:
        return None

    return NyxRuntimeContext(
        query=str(query or "").strip(),
        intent=analysis,
        selected_components=candidates,
    )


def augment_settings_with_nyx(
    settings: dict[str, Any],
    *,
    query: str,
    broker: NyxCatalogBroker,
) -> dict[str, Any]:
    next_settings = dict(settings or {})
    context = build_nyx_runtime_context(query, broker)
    if context is None:
        return next_settings

    next_settings["system_instructions"] = append_system_instruction(
        str(next_settings.get("system_instructions") or ""),
        context.system_instruction_append(),
    )
    existing_artifacts = next_settings.get("artifacts")
    if existing_artifacts is None and "arrow_artifacts" in next_settings:
        existing_artifacts = next_settings.get("arrow_artifacts")
    next_settings["artifacts"] = merge_arrow_artifacts(existing_artifacts, context.to_artifacts())
    next_settings["nyx_runtime"] = context.to_payload()
    return next_settings


def _resolve_component_candidates(
    query: str,
    broker: NyxCatalogBroker,
    *,
    limit: int,
) -> tuple[NyxComponentCandidate, ...]:
    prompt_lower = str(query or "").strip().lower()
    query_tokens = {token for token in _tokenize(prompt_lower) if token not in _STOPWORDS}
    ranked: list[tuple[int, str, tuple[str, ...]]] = []

    for component_name, curated in broker.iter_curated_components():
        score, reasons = _score_component_match(prompt_lower, query_tokens, component_name, curated)
        if score <= 0:
            continue
        ranked.append((score, component_name, reasons))

    ranked.sort(key=lambda item: (-item[0], item[1]))
    selected: list[NyxComponentCandidate] = []
    for score, component_name, reasons in ranked:
        if len(selected) >= limit:
            break
        explicit_match = any(reason.startswith("explicit") for reason in reasons)
        if score < _MIN_COMPONENT_MATCH_SCORE and not explicit_match:
            continue
        try:
            detail = broker.get_component_detail(component_name)
        except RuntimeError:
            continue
        selected.append(
            NyxComponentCandidate(
                detail=detail,
                match_score=score,
                reasons=reasons,
            )
        )

    return tuple(selected)


def _score_component_match(
    prompt_lower: str,
    query_tokens: set[str],
    component_name: str,
    curated: CuratedNyxComponent,
) -> tuple[int, tuple[str, ...]]:
    score = 0
    reasons: list[str] = []
    component_refs = {
        component_name,
        component_name.replace("-", " "),
        f"@nyx/{component_name}",
    }
    if any(reference in prompt_lower for reference in component_refs):
        score += 80
        reasons.append(f"explicit component reference: {component_name}")

    name_tokens = set(_tokenize(component_name.replace("-", " ")))
    description_tokens = {token for token in _tokenize(curated.description) if token not in _STOPWORDS}
    matched_name_terms = sorted(
        token for token in (query_tokens & name_tokens) if token not in _LOW_SIGNAL_COMPONENT_TERMS
    )
    matched_description_terms = sorted(
        token
        for token in (query_tokens & description_tokens)
        if token not in _LOW_SIGNAL_COMPONENT_TERMS
    )
    if matched_name_terms:
        score += 18 * len(matched_name_terms)
        reasons.append("name terms: " + ", ".join(matched_name_terms[:3]))
    if matched_description_terms:
        score += 10 * len(matched_description_terms[:4])
        reasons.append("description terms: " + ", ".join(matched_description_terms[:4]))

    for phrase in _COMPONENT_HINT_PHRASES.get(component_name, ()): 
        if phrase in prompt_lower:
            score += 14 if " " in phrase else 10
            reasons.append(f"query hint: {phrase}")

    if "background" in query_tokens and ("bg" in name_tokens or "background" in description_tokens):
        score += 8
        reasons.append("background treatment requested")
    if "card" in query_tokens and "card" in name_tokens:
        score += 6
        reasons.append("card pattern requested")
    if {"animated", "animation", "motion"} & query_tokens and "motion" in curated.required_dependencies:
        score += 6
        reasons.append("motion dependency fit")
    if {"interactive", "hover"} & query_tokens and {"interactive", "effects"} & description_tokens:
        score += 6
        reasons.append("interaction-heavy fit")

    return score, _unique_strings(reasons)


def _package_entries(
    candidates: tuple[NyxComponentCandidate, ...],
    dependency_type: str,
    dependency_getter: Any,
) -> list[dict[str, Any]]:
    packages: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        detail = candidate.detail
        for package_name in dependency_getter(detail):
            normalized = str(package_name or "").strip()
            if not normalized:
                continue
            entry = packages.setdefault(
                normalized,
                {
                    "package_name": normalized,
                    "dependency_type": dependency_type,
                    "required_by": [],
                    "install_targets": [],
                    "registry_urls": [],
                },
            )
            entry["required_by"].append(detail.component_name)
            entry["install_targets"].append(detail.install_target)
            entry["registry_urls"].append(detail.registry_url)

    normalized_entries: list[dict[str, Any]] = []
    for package_name in sorted(packages):
        entry = packages[package_name]
        normalized_entries.append(
            {
                "package_name": entry["package_name"],
                "dependency_type": dependency_type,
                "required_by": sorted(set(entry["required_by"])),
                "install_targets": sorted(set(entry["install_targets"])),
                "registry_urls": sorted(set(entry["registry_urls"])),
            }
        )
    return normalized_entries