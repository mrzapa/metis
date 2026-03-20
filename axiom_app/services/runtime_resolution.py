"""Resolve skill-aware runtime settings and prompt composition."""

from __future__ import annotations

from typing import Any

from axiom_app.models.assistant_types import (
    AssistantIdentity,
    AssistantPolicy,
    AssistantRuntime,
)
from axiom_app.models.parity_types import (
    ResolvedRuntimeSettings,
    SkillDefinition,
    SkillMatch,
    SkillSessionState,
)
from axiom_app.services.skill_repository import SCALAR_OVERRIDE_KEYS

MODE_ALIASES = {
    "qa": "Q&A",
    "q&a": "Q&A",
    "book summary": "Summary",
    "blinkist": "Summary",
    "summary": "Summary",
    "tutor": "Tutor",
    "research": "Research",
    "evidence pack": "Evidence Pack",
}

MODE_DEFAULTS: dict[str, dict[str, Any]] = {
    "Q&A": {"retrieve_k": 25, "final_k": 5, "mmr_lambda": 0.5, "retrieval_mode": "flat", "agentic_mode": False, "max_iterations": 2},
    "Summary": {"retrieve_k": 20, "final_k": 4, "mmr_lambda": 0.6, "retrieval_mode": "hierarchical", "agentic_mode": False, "max_iterations": 2},
    "Tutor": {"retrieve_k": 24, "final_k": 6, "mmr_lambda": 0.55, "retrieval_mode": "hierarchical", "agentic_mode": True, "max_iterations": 2},
    "Research": {"retrieve_k": 42, "final_k": 12, "mmr_lambda": 0.4, "retrieval_mode": "hierarchical", "agentic_mode": True, "max_iterations": 3},
    "Evidence Pack": {"retrieve_k": 35, "final_k": 10, "mmr_lambda": 0.5, "retrieval_mode": "hierarchical", "agentic_mode": True, "max_iterations": 3},
}

MODE_PROMPT_PACKS = {
    "Q&A": (
        "Mode: Q&A. Provide succinct, direct answers first, then supporting details. "
        "Ground factual statements with citations and avoid unnecessary verbosity."
    ),
    "Summary": (
        "Mode: Summary (Blinkist style). Focus on key ideas and practical takeaways, avoid over-detailing, "
        "and include a concise timeline of important events where relevant."
    ),
    "Tutor": (
        "Mode: Tutor. Use an educational tone, ask clarifying Socratic questions when useful, and include "
        "practice flashcards/quiz prompts grounded in retrieved evidence."
    ),
    "Research": (
        "Mode: Research. Extract and structure claims and counterclaims with explicit argument mapping and "
        "citation-backed evidence quality notes. Prefer hierarchical retrieval synthesis."
    ),
    "Evidence Pack": (
        "Mode: Evidence Pack. Build a structured timeline and narrative with exhaustive citations, ensuring "
        "every factual statement is explicitly grounded."
    ),
}

_DEFAULT_ASSISTANT_IDENTITY = AssistantIdentity()
_DEFAULT_ASSISTANT_RUNTIME = AssistantRuntime()
_DEFAULT_ASSISTANT_POLICY = AssistantPolicy()


def normalize_mode_name(mode_name: str) -> str:
    normalized = str(mode_name or "").strip()
    if not normalized:
        return "Q&A"
    return MODE_ALIASES.get(normalized.lower(), normalized)


def is_evidence_pack_query(query: str, output_style: str = "") -> bool:
    text = f"{query or ''} {output_style or ''}".strip().lower()
    if not text:
        return False
    keywords = (
        "evidence pack",
        "timeline",
        "chronology",
        "incident",
        "packet",
        "affidavit",
        "dossier",
        "evidence table",
    )
    return any(token in text for token in keywords)


def infer_file_types(documents: list[str] | None) -> list[str]:
    file_types: list[str] = []
    for document in documents or []:
        suffix = str(document or "").strip()
        if "." in suffix:
            suffix = "." + suffix.split(".")[-1].lower()
        if suffix and suffix not in file_types:
            file_types.append(suffix)
    return file_types


def _keyword_score(query: str, keywords: list[str]) -> tuple[int, list[str]]:
    text = str(query or "").strip().casefold()
    score = 0
    matched: list[str] = []
    for keyword in keywords or []:
        normalized = str(keyword or "").strip().casefold()
        if normalized and normalized in text:
            score += 10
            matched.append(str(keyword))
    return score, matched


def _list_intersection_score(value: str, candidates: list[str], *, points: int) -> tuple[int, list[str]]:
    normalized = str(value or "").strip().casefold()
    matched = [item for item in candidates or [] if str(item or "").strip().casefold() == normalized and normalized]
    return (points if matched else 0), [str(item) for item in matched]


def _file_type_score(file_types: list[str], candidates: list[str]) -> tuple[int, list[str]]:
    normalized = {str(item or "").strip().casefold() for item in file_types or [] if str(item).strip()}
    matched = [str(item) for item in candidates or [] if str(item or "").strip().casefold() in normalized]
    return (2 * len(matched)), matched


def build_capability_index(enabled_skills: list[SkillDefinition]) -> str:
    if not enabled_skills:
        return "Enabled skills:\n- none"
    lines = ["Enabled skills:"]
    for skill in sorted(enabled_skills, key=lambda item: item.skill_id.casefold()):
        lines.append(skill.capability_line())
    return "\n".join(lines)


def select_skills(
    enabled_skills: list[SkillDefinition],
    *,
    session_state: SkillSessionState | None,
    query: str,
    mode: str,
    output_style: str,
    file_types: list[str] | None = None,
) -> list[SkillMatch]:
    normalized_state = (session_state or SkillSessionState()).normalized()
    pinned = set(normalized_state.pinned)
    muted = set(normalized_state.muted)
    matches: list[SkillMatch] = []

    for skill in enabled_skills or []:
        pinned_match = skill.skill_id in pinned
        if skill.skill_id in muted and not pinned_match:
            continue

        reasons: list[str] = []
        score = 0

        keyword_points, keyword_matches = _keyword_score(query, list(skill.triggers.get("keywords") or []))
        score += keyword_points
        if keyword_matches:
            reasons.append("keywords: " + ", ".join(keyword_matches))

        mode_points, mode_matches = _list_intersection_score(mode, list(skill.triggers.get("modes") or []), points=5)
        score += mode_points
        if mode_matches:
            reasons.append("mode: " + ", ".join(mode_matches))

        output_points, output_matches = _list_intersection_score(
            output_style,
            list(skill.triggers.get("output_styles") or []),
            points=3,
        )
        score += output_points
        if output_matches:
            reasons.append("output: " + ", ".join(output_matches))

        file_points, file_matches = _file_type_score(list(file_types or []), list(skill.triggers.get("file_types") or []))
        score += file_points
        if file_matches:
            reasons.append("file: " + ", ".join(file_matches))

        if not pinned_match and score <= 0:
            continue
        if pinned_match:
            reasons.insert(0, "pinned for session")

        matches.append(
            SkillMatch(
                skill_id=skill.skill_id,
                name=skill.name,
                reason="; ".join(reasons) if reasons else "selected by default",
                score=int(score),
                pinned=pinned_match,
                priority=int(skill.priority),
                runtime_overrides=dict(skill.runtime_overrides or {}),
                body=str(skill.body or "").strip(),
            )
        )

    matches.sort(
        key=lambda item: (
            0 if item.pinned else 1,
            -int(item.priority),
            -int(item.score),
            item.skill_id.casefold(),
        )
    )
    return matches


def _append_overrides(selected_skills: list[SkillMatch], key: str) -> list[str]:
    values: list[str] = []
    for skill in selected_skills:
        value = str(skill.runtime_overrides.get(key, "") or "").strip()
        if value:
            values.append(value)
    return values


def _scalar_conflicts(selected_skills: list[SkillMatch]) -> list[dict[str, Any]]:
    if not selected_skills:
        return []
    primary = selected_skills[0]
    conflicts: list[dict[str, Any]] = []
    for skill in selected_skills[1:]:
        for key in sorted(SCALAR_OVERRIDE_KEYS):
            if key not in skill.runtime_overrides:
                continue
            kept = primary.runtime_overrides.get(key)
            dropped = skill.runtime_overrides.get(key)
            if kept == dropped:
                continue
            conflicts.append(
                {
                    "key": key,
                    "kept_skill_id": primary.skill_id,
                    "kept_value": kept,
                    "dropped_skill_id": skill.skill_id,
                    "dropped_value": dropped,
                }
            )
    return conflicts


def _selected_skill_lines(selected_skills: list[SkillMatch]) -> list[str]:
    if not selected_skills:
        return []
    lines = ["Loaded skills:"]
    for skill in selected_skills:
        lines.append(f"- {skill.skill_id}: {skill.reason}")
    return lines


def build_system_prompt(
    settings: dict[str, Any],
    *,
    selected_skills: list[SkillMatch],
    capability_index: str,
    mode: str,
    mode_prompt: str,
    retrieve_k: int,
    final_k: int,
    mmr_lambda: float,
    retrieval_mode: str,
    agentic_mode: bool,
    agentic_max_iterations: int,
    citation_policy_append: list[str],
) -> str:
    base_instructions = str(
        settings.get("system_instructions")
        or "You are Axiom, a grounded AI assistant. Use citations when retrieved context is available."
    ).strip()
    segments = [
        f"Active mode: {mode}",
        base_instructions,
        capability_index,
        (
            "Retrieval strategy: "
            f"mode={retrieval_mode}, retrieve_k={retrieve_k}, final_k={final_k}, mmr_lambda={mmr_lambda}."
        ),
    ]
    if selected_skills:
        segments.append("\n".join(_selected_skill_lines(selected_skills)))
        skill_blocks = ["Selected skill instructions:"]
        for skill in selected_skills:
            skill_blocks.append(f"[{skill.skill_id}] {skill.name}\n{skill.body}")
        segments.append("\n\n".join(block for block in skill_blocks if block.strip()))
    if citation_policy_append:
        segments.append("Skill citation policy:\n" + "\n".join(citation_policy_append))
    if mode_prompt:
        segments.append(mode_prompt)
    segments.append(
        f"Agentic: enabled={int(agentic_mode)}, max_iterations={agentic_max_iterations}."
    )
    output_style = str(settings.get("output_style", "") or "").strip()
    if output_style:
        segments.append(f"Output style: {output_style}")
    return "\n\n".join(segment for segment in segments if str(segment).strip())


def resolve_runtime_settings(
    settings: dict[str, Any],
    *,
    enabled_skills: list[SkillDefinition],
    session_skill_state: SkillSessionState | None = None,
    query: str = "",
    file_types: list[str] | None = None,
) -> ResolvedRuntimeSettings:
    base_mode = normalize_mode_name(settings.get("selected_mode", "Q&A"))
    base_output_style = str(settings.get("output_style", "") or "").strip()
    capability_index = build_capability_index(enabled_skills)
    selected_skills = select_skills(
        enabled_skills,
        session_state=session_skill_state,
        query=query,
        mode=base_mode,
        output_style=base_output_style,
        file_types=list(file_types or []),
    )
    primary = selected_skills[0] if selected_skills else None
    primary_overrides = dict(primary.runtime_overrides or {}) if primary is not None else {}
    appended_system_instructions = _append_overrides(selected_skills, "system_instructions_append")
    citation_policy_append = _append_overrides(selected_skills, "citation_policy_append")

    resolved_mode = normalize_mode_name(primary_overrides.get("selected_mode", base_mode))
    output_style = str(primary_overrides.get("output_style", base_output_style) or base_output_style).strip()
    if resolved_mode == "Q&A" and is_evidence_pack_query(query, output_style):
        resolved_mode = "Evidence Pack"
    mode_defaults = MODE_DEFAULTS.get(resolved_mode, MODE_DEFAULTS["Q&A"])
    mode_prompt = MODE_PROMPT_PACKS.get(resolved_mode, MODE_PROMPT_PACKS["Q&A"])

    llm_model = (
        str(settings.get("llm_model", "") or "").strip()
        or str(settings.get("llm_model_custom", "") or "").strip()
    )
    embedding_model = (
        str(settings.get("embedding_model", "") or "").strip()
        or str(settings.get("embedding_model_custom", "") or "").strip()
        or str(settings.get("sentence_transformers_model", "") or "").strip()
    )

    retrieve_k = max(
        1,
        int(
            primary_overrides.get(
                "retrieval_k",
                settings.get("retrieval_k", mode_defaults["retrieve_k"]),
            )
            or mode_defaults["retrieve_k"]
        ),
    )
    final_k = max(
        1,
        int(
            primary_overrides.get(
                "top_k",
                settings.get("top_k", mode_defaults["final_k"]),
            )
            or mode_defaults["final_k"]
        ),
    )
    mmr_lambda = float(
        primary_overrides.get(
            "mmr_lambda",
            settings.get("mmr_lambda", mode_defaults["mmr_lambda"]),
        )
        or mode_defaults["mmr_lambda"]
    )
    retrieval_mode = str(
        primary_overrides.get(
            "retrieval_mode",
            settings.get("retrieval_mode", mode_defaults["retrieval_mode"]),
        )
        or mode_defaults["retrieval_mode"]
    )
    agentic_mode = bool(
        primary_overrides.get(
            "agentic_mode",
            settings.get("agentic_mode", mode_defaults["agentic_mode"]),
        )
    )
    agentic_max_iterations = max(
        1,
        int(
            primary_overrides.get(
                "agentic_max_iterations",
                settings.get("agentic_max_iterations", mode_defaults["max_iterations"]),
            )
            or mode_defaults["max_iterations"]
        ),
    )

    prompt_settings = dict(settings)
    if output_style:
        prompt_settings["output_style"] = output_style
    if appended_system_instructions:
        joined = "\n\n".join(appended_system_instructions)
        base_prompt = str(prompt_settings.get("system_instructions", "") or "").strip()
        prompt_settings["system_instructions"] = (
            base_prompt + ("\n\n" if base_prompt else "") + joined
        ).strip()
    system_prompt = build_system_prompt(
        prompt_settings,
        selected_skills=selected_skills,
        capability_index=capability_index,
        mode=resolved_mode,
        mode_prompt=mode_prompt,
        retrieve_k=retrieve_k,
        final_k=final_k,
        mmr_lambda=mmr_lambda,
        retrieval_mode=retrieval_mode,
        agentic_mode=agentic_mode,
        agentic_max_iterations=agentic_max_iterations,
        citation_policy_append=citation_policy_append,
    )
    conflicts = _scalar_conflicts(selected_skills)
    next_session_state = (session_skill_state or SkillSessionState()).normalized()
    next_session_state.selected = [skill.skill_id for skill in selected_skills]
    next_session_state.primary = primary.skill_id if primary is not None else ""
    next_session_state.reasons = {skill.skill_id: skill.reason for skill in selected_skills}

    return ResolvedRuntimeSettings(
        mode=resolved_mode,
        retrieve_k=retrieve_k,
        final_k=final_k,
        mmr_lambda=mmr_lambda,
        search_type=str(settings.get("search_type", "similarity") or "similarity"),
        retrieval_mode=retrieval_mode,
        agentic_mode=agentic_mode,
        agentic_max_iterations=agentic_max_iterations,
        llm_provider=str(settings.get("llm_provider", "") or ""),
        llm_model=llm_model,
        embedding_provider=str(settings.get("embedding_provider", "") or ""),
        embedding_model=embedding_model,
        output_style=output_style,
        mode_prompt_pack=mode_prompt,
        prompt_pack_id=resolved_mode,
        system_prompt=system_prompt,
        evidence_pack_mode=resolved_mode == "Evidence Pack",
        selected_skills=selected_skills,
        primary_skill_id=primary.skill_id if primary is not None else "",
        capability_index=capability_index,
        skill_prompt_block="\n\n".join(
            f"[{skill.skill_id}] {skill.body}" for skill in selected_skills if skill.body
        ),
        session_skill_state=next_session_state,
        runtime_override_conflicts=conflicts,
        resolution_payload={
            "mode": resolved_mode,
            "retrieve_k": retrieve_k,
            "final_k": final_k,
            "mmr_lambda": mmr_lambda,
            "search_type": str(settings.get("search_type", "similarity") or "similarity"),
            "retrieval_mode": retrieval_mode,
            "agentic_mode": agentic_mode,
            "agentic_max_iterations": agentic_max_iterations,
            "llm_provider": str(settings.get("llm_provider", "") or ""),
            "llm_model": llm_model,
            "embedding_provider": str(settings.get("embedding_provider", "") or ""),
            "embedding_model": embedding_model,
            "output_style": output_style,
            "prompt_pack_id": resolved_mode,
            "mode_prompt_pack": mode_prompt,
            "selected_skills": [skill.to_payload() for skill in selected_skills],
            "primary_skill_id": primary.skill_id if primary is not None else "",
            "runtime_override_conflicts": conflicts,
            "skills": next_session_state.to_payload(),
        },
    )


def resolve_assistant_identity(settings: dict[str, Any]) -> AssistantIdentity:
    payload = settings.get("assistant_identity")
    if isinstance(payload, dict):
        return AssistantIdentity.from_payload(payload)
    return AssistantIdentity.from_payload(_DEFAULT_ASSISTANT_IDENTITY.to_payload())


def resolve_assistant_runtime(settings: dict[str, Any]) -> AssistantRuntime:
    payload = settings.get("assistant_runtime")
    if isinstance(payload, dict):
        return AssistantRuntime.from_payload(payload)
    return AssistantRuntime.from_payload(_DEFAULT_ASSISTANT_RUNTIME.to_payload())


def resolve_assistant_policy(settings: dict[str, Any]) -> AssistantPolicy:
    payload = settings.get("assistant_policy")
    if isinstance(payload, dict):
        return AssistantPolicy.from_payload(payload)
    return AssistantPolicy.from_payload(_DEFAULT_ASSISTANT_POLICY.to_payload())


def build_assistant_reflection_prompt(
    identity: AssistantIdentity,
    *,
    context_lines: list[str],
    trace_events: list[dict[str, Any]] | None = None,
    seed_summary: str = "",
) -> str:
    trace_preview = [
        f"- {str(item.get('event_type') or item.get('stage') or 'event')}: {str((item.get('payload') or {}))[:180]}"
        for item in (trace_events or [])[:6]
    ]
    prompt_parts = [
        identity.prompt_seed.strip(),
        (
            "You are generating a compact local reflection for the persistent Axiom companion. "
            "Return JSON with keys: title, summary, details, why, playbook_title, playbook_bullets, tags, confidence."
        ),
    ]
    if seed_summary.strip():
        prompt_parts.append(f"Seed summary: {seed_summary.strip()}")
    if context_lines:
        prompt_parts.append("Context:\n" + "\n".join(f"- {line}" for line in context_lines if str(line).strip()))
    if trace_preview:
        prompt_parts.append("Trace preview:\n" + "\n".join(trace_preview))
    return "\n\n".join(part for part in prompt_parts if part.strip())
