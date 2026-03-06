"""Resolve mode/profile-aware runtime settings and prompt composition."""

from __future__ import annotations

from typing import Any

from axiom_app.models.parity_types import AgentProfile, ResolvedRuntimeSettings

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


def resolve_runtime_settings(
    settings: dict[str, Any],
    profile: AgentProfile,
    *,
    profile_label: str,
    query: str = "",
) -> ResolvedRuntimeSettings:
    mode = normalize_mode_name(settings.get("selected_mode", profile.mode_default or "Q&A"))
    mode_defaults = MODE_DEFAULTS.get(mode, MODE_DEFAULTS["Q&A"])
    retrieval = dict(profile.retrieval_strategy or {})
    iteration = dict(profile.iteration_strategy or {})

    llm_model = (
        str(profile.model or "").strip()
        or str(settings.get("llm_model", "") or "").strip()
        or str(settings.get("llm_model_custom", "") or "").strip()
    )
    embedding_model = (
        str(settings.get("embedding_model", "") or "").strip()
        or str(settings.get("embedding_model_custom", "") or "").strip()
        or str(settings.get("sentence_transformers_model", "") or "").strip()
    )
    resolved_mode = (
        "Evidence Pack"
        if mode == "Q&A" and is_evidence_pack_query(query, str(settings.get("output_style", "") or ""))
        else mode
    )
    mode_prompt = MODE_PROMPT_PACKS.get(resolved_mode, MODE_PROMPT_PACKS["Q&A"])

    retrieve_k = max(1, int(retrieval.get("retrieve_k", settings.get("retrieval_k", mode_defaults["retrieve_k"])) or mode_defaults["retrieve_k"]))
    final_k = max(1, int(retrieval.get("final_k", settings.get("top_k", mode_defaults["final_k"])) or mode_defaults["final_k"]))
    mmr_lambda = float(retrieval.get("mmr_lambda", settings.get("mmr_lambda", mode_defaults["mmr_lambda"])) or mode_defaults["mmr_lambda"])
    retrieval_mode = str(retrieval.get("retrieval_mode", profile.retrieval_mode or settings.get("retrieval_mode", mode_defaults["retrieval_mode"])) or mode_defaults["retrieval_mode"])
    agentic_mode = bool(iteration.get("agentic_mode", settings.get("agentic_mode", mode_defaults["agentic_mode"])))
    agentic_max_iterations = max(1, int(iteration.get("max_iterations", settings.get("agentic_max_iterations", mode_defaults["max_iterations"])) or mode_defaults["max_iterations"]))
    system_prompt = build_system_prompt(
        settings,
        profile,
        resolved_mode,
        mode_prompt,
        retrieve_k,
        final_k,
        mmr_lambda,
        retrieval_mode,
        agentic_mode,
        agentic_max_iterations,
    )

    return ResolvedRuntimeSettings(
        mode=resolved_mode,
        profile_label=str(profile_label or "Built-in: Default"),
        profile=profile,
        retrieve_k=retrieve_k,
        final_k=final_k,
        mmr_lambda=mmr_lambda,
        search_type=str(retrieval.get("search_type", settings.get("search_type", "similarity")) or "similarity"),
        retrieval_mode=retrieval_mode,
        agentic_mode=agentic_mode,
        agentic_max_iterations=agentic_max_iterations,
        llm_provider=str(profile.provider or settings.get("llm_provider", "") or ""),
        llm_model=llm_model,
        embedding_provider=str(settings.get("embedding_provider", "") or ""),
        embedding_model=embedding_model,
        output_style=str(settings.get("output_style", "") or ""),
        mode_prompt_pack=mode_prompt,
        prompt_pack_id=resolved_mode,
        system_prompt=system_prompt,
        evidence_pack_mode=resolved_mode == "Evidence Pack",
        resolution_payload={
            "mode": resolved_mode,
            "profile_label": str(profile_label or "Built-in: Default"),
            "retrieve_k": retrieve_k,
            "final_k": final_k,
            "mmr_lambda": mmr_lambda,
            "search_type": str(retrieval.get("search_type", settings.get("search_type", "similarity")) or "similarity"),
            "retrieval_mode": retrieval_mode,
            "agentic_mode": agentic_mode,
            "agentic_max_iterations": agentic_max_iterations,
            "llm_provider": str(profile.provider or settings.get("llm_provider", "") or ""),
            "llm_model": llm_model,
            "embedding_provider": str(settings.get("embedding_provider", "") or ""),
            "embedding_model": embedding_model,
            "output_style": str(settings.get("output_style", "") or ""),
            "prompt_pack_id": resolved_mode,
            "mode_prompt_pack": mode_prompt,
        },
    )


def build_system_prompt(
    settings: dict[str, Any],
    profile: AgentProfile,
    mode: str,
    mode_prompt: str,
    retrieve_k: int,
    final_k: int,
    mmr_lambda: float,
    retrieval_mode: str,
    agentic_mode: bool,
    agentic_max_iterations: int,
) -> str:
    base_instructions = str(
        settings.get("system_instructions")
        or "You are Axiom, a grounded AI assistant. Use citations when retrieved context is available."
    ).strip()
    segments = [
        f"Active mode: {mode}",
        base_instructions,
        (
            "Retrieval strategy: "
            f"mode={retrieval_mode}, retrieve_k={retrieve_k}, final_k={final_k}, mmr_lambda={mmr_lambda}."
        ),
    ]
    if profile.system_instructions:
        segments.append(f"Profile overlay:\n{profile.system_instructions}")
    if profile.style_template:
        segments.append(f"Profile style template:\n{profile.style_template}")
    if profile.citation_policy:
        segments.append(f"Profile citation policy:\n{profile.citation_policy}")
    if mode_prompt:
        segments.append(mode_prompt)
    segments.append(
        f"Agentic: enabled={int(agentic_mode)}, max_iterations={agentic_max_iterations}."
    )
    output_style = str(settings.get("output_style", "") or "").strip()
    if output_style:
        segments.append(f"Output style: {output_style}")
    return "\n\n".join(segment for segment in segments if segment.strip())
