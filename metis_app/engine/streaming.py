"""SSE-ready streaming generator for RAG queries."""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

from metis_app.engine.querying import (
    RagQueryRequest,
    _normalize_run_id,
    _prepare_rag_settings,
    _response_text,
    _system_instructions,
    extract_arrow_artifacts,
)
from metis_app.services.retrieval_pipeline import execute_retrieval_plan, generate_sub_queries
from metis_app.services.stream_events import normalize_stream_event
from metis_app.services.vector_store import resolve_vector_store
from metis_app.services.index_service import cosine_similarity as _cosine_similarity
from metis_app.utils.embedding_providers import create_embeddings
from metis_app.utils.llm_providers import create_llm, create_smart_llm
from metis_app.utils.mock_embeddings import MockEmbeddings

log = logging.getLogger(__name__)

# Guard against runaway context growth during agentic refinement iterations.
_MAX_CONTEXT_CHARS = 12_000




def _embed_text(text: str, settings: dict) -> list[float]:
    """Embed a text string for convergence comparison. Falls back to MockEmbeddings."""
    try:
        emb = create_embeddings(settings)
    except (ValueError, ImportError):
        emb = MockEmbeddings(dimensions=32)
    return emb.embed_query(text)


def _generate_sub_queries(question: str, llm: Any) -> list[str]:
    """Proxy kept local so tests can patch the stream-layer expander."""
    return generate_sub_queries(question, {}, llm)


def _identify_gaps(
    question: str,
    current_answer: str,
    context_block: str,
    llm: Any,
) -> list[str]:
    """Critique the current answer and return targeted retrieval queries for gaps.

    Inspired by AIlice's self-critique loop (``AProcessor.__call__``) where the
    agent iteratively evaluates its own outputs to identify what additional
    information is needed before producing a confident final response.

    Returns an empty list on any failure or when the answer is already complete,
    so callers always treat the result as optional.
    """

    system = (
        "You are a research quality critic. "
        "Given a question, a draft answer, and the retrieved context used to "
        "generate it, identify specific knowledge gaps: places where the answer "
        "is incomplete, vague, contradictory, or unsupported by the context. "
        "For each gap, produce a precise retrieval query that would help fill it. "
        "Return ONLY a compact JSON array of query strings (1-3 items). "
        "If the answer is complete and well-supported, return []."
    )
    # Truncate context preview to avoid consuming too many tokens.
    context_preview = context_block[:2000] if len(context_block) > 2000 else context_block
    try:
        raw = _response_text(
            llm.invoke([
                {"type": "system", "content": system},
                {
                    "type": "human",
                    "content": (
                        f"QUESTION:\n{question}\n\n"
                        f"DRAFT ANSWER:\n{current_answer}\n\n"
                        f"CONTEXT USED (excerpt):\n{context_preview}"
                    ),
                },
            ])
        )
        start, end = raw.find("["), raw.rfind("]") + 1
        if start == -1 or end == 0:
            return []
        candidates = json.loads(raw[start:end])
        if not isinstance(candidates, list):
            return []
        seen: set[str] = set()
        result: list[str] = []
        for c in candidates:
            s = str(c).strip()
            if not s or s.lower() in seen:
                continue
            seen.add(s.lower())
            result.append(s)
        return result[:3]
    except Exception:  # noqa: BLE001
        return []


def _classify_source_tiers(
    question: str,
    sources: list[dict[str, Any]],
    llm: Any,
) -> list[str]:
    """Classify each source as Supporting, Contested, or Refuting (Evidence Pack).

    Issues a single batched LLM call. Falls back to "Supporting" for all on
    any failure.
    """
    if not sources:
        return []
    snippets = []
    for i, src in enumerate(sources):
        snippet = str(src.get("snippet") or src.get("text") or src.get("content") or "")[:400]
        snippets.append(f"[{i + 1}] {snippet}")

    system_prompt = (
        "You are an evidence-tier classifier. "
        "For each numbered passage, classify it relative to the claim or question below "
        "as exactly one of: Supporting, Contested, or Refuting. "
        "Supporting: the passage directly confirms or supports the claim. "
        "Contested: the passage is mixed, nuanced, or only partially relevant. "
        "Refuting: the passage contradicts or argues against the claim. "
        'Return ONLY a JSON array of tier labels in order, e.g. ["Supporting", "Contested"].'
    )
    user_prompt = (
        f"Question/Claim: {question}\n\nPassages:\n"
        + "\n\n".join(snippets)
        + "\n\nClassify each passage:"
    )
    try:
        raw = _response_text(
            llm.invoke([
                {"type": "system", "content": system_prompt},
                {"type": "human", "content": user_prompt},
            ])
        )
        start, end = raw.find("["), raw.rfind("]") + 1
        if start >= 0 and end > start:
            tiers = json.loads(raw[start:end])
            valid = {"Supporting", "Contested", "Refuting"}
            if isinstance(tiers, list) and len(tiers) == len(sources):
                return [t if t in valid else "Contested" for t in tiers]
    except Exception:  # noqa: BLE001
        pass
    return ["Supporting"] * len(sources)


def _format_swarm_report(report: dict[str, Any]) -> str:
    """Format a SimulationReport dict into a readable markdown answer string."""
    lines: list[str] = []

    summary = str(report.get("document_summary") or "")
    if summary:
        lines.append(f"**Document Overview**\n{summary}\n")

    topics = list(report.get("topics") or [])
    if topics:
        lines.append(f"**Topics Simulated:** {', '.join(topics)}\n")

    agents = list(report.get("agents") or [])
    if agents:
        lines.append(f"**{len(agents)} Personas Generated:**")
        for a in agents:
            name = str(a.get("name") or "Agent")
            stance = str(a.get("stance_summary") or "")
            lines.append(f"• **{name}**: {stance}")
        lines.append("")

    consensus = list(report.get("consensus_topics") or [])
    contested = list(report.get("contested_topics") or [])
    if consensus:
        lines.append(f"**Consensus Topics** (strong agreement): {', '.join(consensus)}")
    if contested:
        lines.append(f"**Contested Topics** (significant disagreement): {', '.join(contested)}")
    if consensus or contested:
        lines.append("")

    rounds = list(report.get("rounds") or [])
    if rounds:
        last_round = rounds[-1]
        posts = list(last_round.get("posts") or [])
        if posts:
            lines.append(
                f"**Final Round ({last_round.get('round_num', len(rounds))}) Highlights:**"
            )
            for post in posts[:4]:
                agent_name = str(post.get("agent_name") or "Agent")
                text = str(post.get("text") or "")
                lines.append(f"\n*{agent_name}*: {text}")

    return "\n".join(lines).strip()


def _compress_context(
    context: str,
    question: str,
    llm: Any,
    iteration: int,
) -> str:
    """Compress *context* using a structured summary template.

    Ported from Hermes Agent v0.7.0 context_compressor.py.
    Template: Goal / Key Findings / Remaining Gaps / Next Steps.
    Falls back to hard truncation on LLM failure.
    """
    system = (
        "You are a concise research summariser. Compress the following retrieved "
        "context into a structured summary. Return ONLY:\n\n"
        f"## Compression Summary (pass {iteration})\n"
        "**Goal:** {one sentence restating the original question}\n"
        "**Key Findings:**\n- (bullet points of the most important facts)\n"
        "**Remaining Gaps:** (what is still unknown or unresolved)\n"
        "**Next Steps:** (what additional retrieval would help)\n\n"
        "Preserve all entity names, dates, numbers, and key claims. "
        "Be dense — every sentence should carry information."
    )
    try:
        from metis_app.engine.querying import _response_text as _rt  # noqa: PLC0415
        return _rt(
            llm.invoke([
                {"type": "system", "content": system},
                {
                    "type": "human",
                    "content": f"ORIGINAL QUESTION:\n{question}\n\nCONTEXT TO COMPRESS:\n{context[:6000]}",
                },
            ])
        )
    except Exception:  # noqa: BLE001
        return context[:_MAX_CONTEXT_CHARS]


def _dedup_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return *sources* with duplicates removed, preserving insertion order.

    Deduplication key is ``chunk_id`` when available, falling back to ``sid``
    and then the raw snippet text.
    """
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for src in sources:
        key = str(src.get("chunk_id") or src.get("sid") or src.get("snippet") or "")
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        result.append(src)
    return result


def stream_rag_answer(
    req: RagQueryRequest,
    cancel_token: Any = None,  # reserved for future cancellation support
) -> Iterator[dict[str, Any]]:
    """Yield structured dict events for a RAG query.

    Event shapes (all JSON-serialisable):
      {"type": "run_started",          "run_id": str}
      {"type": "retrieval_complete",   "run_id": str, "sources": [...],
                                        "context_block": str, "top_score": float}
      {"type": "subqueries",           "run_id": str, "queries": [str, ...]}  # Research mode only
      {"type": "iteration_start",      "run_id": str, "iteration": int,
                                        "total_iterations": int}               # agentic_mode only
      {"type": "gaps_identified",      "run_id": str, "gaps": [str, ...],
                                        "iteration": int}                      # agentic_mode only
      {"type": "refinement_retrieval", "run_id": str, "iteration": int,
                                        "sources": [...], "context_block": str,
                                        "top_score": float}                    # agentic_mode only
      {"type": "iteration_complete",   "run_id": str, "iterations_used": int,
                                        "convergence_score": float,
                                        "query_text": str}                    # agentic_mode only
      {"type": "token",                "run_id": str, "text": str}  # 1..N
      {"type": "final",                "run_id": str, "answer_text": str, "sources": [...]}
      {"type": "error",                "run_id": str, "message": str}

    The ``cancel_token`` parameter is accepted for forward-compatibility but not
    yet acted upon.  Callers may pass any truthy sentinel and check it between
    yields once support is wired up.
    """
    run_id = _normalize_run_id(req.run_id)
    event_sequence = 0

    def _emit(event: dict[str, Any]) -> dict[str, Any]:
        nonlocal event_sequence
        event_sequence += 1
        return normalize_stream_event(event, sequence=event_sequence, source="rag_stream")

    try:
        question = str(req.question or "").strip()
        if not question:
            yield _emit({"type": "error", "run_id": run_id, "message": "question must not be empty."})
            return

        yield _emit({"type": "run_started", "run_id": run_id})

        manifest_path, settings = _prepare_rag_settings(req)
        adapter = resolve_vector_store(settings)
        available, reason = adapter.is_available(settings)
        if not available:
            yield _emit({
                "type": "error",
                "run_id": run_id,
                "message": f"Vector backend unavailable: {reason}",
            })
            return

        llm = create_llm(settings)

        bundle = adapter.load(manifest_path)
        retrieval_plan = execute_retrieval_plan(
            bundle=bundle,
            adapter=adapter,
            question=question,
            settings=settings,
            llm=llm,
            subquery_generator=_generate_sub_queries,
        )
        query_result = retrieval_plan.result
        sources = [s.to_dict() for s in query_result.sources]

        for stage in retrieval_plan.stages:
            payload = dict(stage.payload or {})
            if stage.stage_type == "retrieval_complete":
                # For Evidence Pack mode, classify each source into belief tiers.
                _ret_sources = list(payload.get("sources") or [])
                _ep_mode = str(settings.get("selected_mode", "") or "")
                if _ep_mode in {"Evidence Pack", "Research"} and _ret_sources:
                    try:
                        _tiers = _classify_source_tiers(question, _ret_sources, llm)
                        for _i, _src in enumerate(_ret_sources):
                            _src["belief_tier"] = _tiers[_i] if _i < len(_tiers) else "Contested"
                    except Exception:  # noqa: BLE001
                        pass
                yield _emit({
                    "type": "retrieval_complete",
                    "run_id": run_id,
                    "sources": _ret_sources,
                    "context_block": str(payload.get("context_block") or ""),
                    "top_score": float(payload.get("top_score", 0.0) or 0.0),
                })
            elif stage.stage_type == "query_expansion":
                yield _emit({
                    "type": "subqueries",
                    "run_id": run_id,
                    "queries": list(payload.get("queries") or []),
                })
            elif stage.stage_type == "retrieval_augmented":
                yield _emit({
                    "type": "retrieval_augmented",
                    "run_id": run_id,
                    "sources": list(payload.get("sources") or []),
                    "context_block": str(payload.get("context_block") or ""),
                    "top_score": float(payload.get("top_score", 0.0) or 0.0),
                })
            elif stage.stage_type == "fallback_decision":
                yield _emit({
                    "type": "fallback_decision",
                    "run_id": run_id,
                    "fallback": payload,
                })

        if retrieval_plan.fallback.triggered and retrieval_plan.fallback.strategy == "no_answer":
            final_artifacts = extract_arrow_artifacts(settings)
            yield _emit({
                "type": "final",
                "run_id": run_id,
                "answer_text": retrieval_plan.fallback.message,
                "sources": sources,
                "fallback": retrieval_plan.fallback.to_dict(),
                **({"artifacts": final_artifacts} if final_artifacts else {}),
            })
            return

        if req.require_action:
            yield _emit({
                "type": "action_required",
                "run_id": run_id,
                "action": {
                    "kind": "confirm_settings",
                    "summary": (
                        f"Ready to synthesize an answer from {len(sources)} source(s). "
                        "Approve to continue."
                    ),
                    "payload": {
                        "source_count": len(sources),
                        "top_score": float(query_result.top_score),
                    },
                },
            })
            return

        # ------------------------------------------------------------------
        # Agentic iterative refinement loop — inspired by AIlice's
        # self-critique architecture (AProcessor.__call__).
        #
        # When agentic_mode is enabled the engine:
        #   1. Generates a non-streaming draft answer for self-critique.
        #   2. Asks the LLM to identify knowledge gaps in that draft.
        #   3. Issues targeted additional retrievals to fill those gaps.
        #   4. Repeats up to agentic_max_iterations times.
        #   5. Streams the final answer synthesised from all accumulated context.
        # ------------------------------------------------------------------
        agentic_mode = bool(settings.get("agentic_mode", False))
        agentic_max_iterations = max(
            1, int(settings.get("agentic_max_iterations", 2) or 2)
        )
        agentic_iteration_budget = max(
            1, int(settings.get("agentic_iteration_budget", agentic_max_iterations) or agentic_max_iterations)
        )
        agentic_convergence_threshold = float(
            settings.get("agentic_convergence_threshold", 0.95) or 0.95
        )

        # ------------------------------------------------------------------
        # Agent Lightning gate — star-gated fast-path execution.
        # When agent_lightning_enabled is True AND the constellation has
        # enough stars (>= LIGHTNING_STAR_THRESHOLD), the iteration budget
        # is boosted. When lightning is enabled but stars are insufficient,
        # we cap iterations to 1 (earn it by feeding the constellation).
        # ------------------------------------------------------------------
        _lightning_enabled = bool(settings.get("agent_lightning_enabled", False))
        if _lightning_enabled:
            try:
                from metis_app.models.star_nourishment import (  # noqa: PLC0415
                    LIGHTNING_STAR_THRESHOLD,
                )
                _stars = list(settings.get("landing_constellation_user_stars") or [])
                _lightning_eligible = len(_stars) >= LIGHTNING_STAR_THRESHOLD
                if _lightning_eligible:
                    # Lightning active: boost iteration budget by 50%
                    agentic_iteration_budget = max(
                        agentic_iteration_budget,
                        int(agentic_iteration_budget * 1.5),
                    )
                else:
                    # Lightning enabled but not enough stars: restrict to 1 iteration
                    agentic_iteration_budget = min(agentic_iteration_budget, 1)
            except Exception:  # noqa: BLE001
                pass  # Nourishment module unavailable — no gate applied

        accumulated_context = query_result.context_block
        accumulated_sources = list(sources)

        # ------------------------------------------------------------------
        # Simulation mode – run swarm persona simulation instead of the
        # standard agentic RAG loop.
        # Emits swarm_* events that the frontend simulation stage handles.
        # ------------------------------------------------------------------
        _mode = str(settings.get("selected_mode", "Q&A") or "Q&A")
        if _mode == "Simulation":
            from metis_app.services.swarm_service import stream_swarm_simulation  # noqa: PLC0415

            # Wave 3: swarm persona count scales with star nourishment.
            # If companion is enabled, derive n_personas from star count +
            # personality depth.  Falls back to the static setting otherwise.
            _static_personas = max(1, int(settings.get("swarm_n_personas", 8) or 8))
            try:
                from metis_app.models.star_nourishment import (  # noqa: PLC0415
                    PersonalityEvolution,
                    swarm_persona_count,
                )
                _stars = list(settings.get("landing_constellation_user_stars") or [])
                _evo_data = settings.get("personality_evolution")
                _evo = PersonalityEvolution.from_payload(_evo_data) if _evo_data else PersonalityEvolution()
                n_personas = swarm_persona_count(len(_stars), _evo.personality_depth)
            except Exception:  # noqa: BLE001
                n_personas = _static_personas
            n_rounds = max(1, int(settings.get("swarm_n_rounds", 4) or 4))
            _round_deltas: list[float] = []

            for swarm_event in stream_swarm_simulation(
                context_text=accumulated_context,
                settings=settings,
                n_personas=n_personas,
                n_rounds=n_rounds,
            ):
                etype = swarm_event.get("event", "")
                if etype == "topics_extracted":
                    yield _emit({
                        "type": "swarm_start",
                        "run_id": run_id,
                        "n_personas": n_personas,
                        "n_rounds": n_rounds,
                        "topics": list(swarm_event.get("topics") or []),
                    })
                elif etype == "persona_created":
                    _agent = dict(swarm_event.get("agent") or {})
                    yield _emit({
                        "type": "swarm_persona_vote",
                        "run_id": run_id,
                        "persona": str(_agent.get("name", "")),
                        "stance": str(_agent.get("stance_summary", "")),
                        "summary": str(_agent.get("background", "")),
                    })
                elif etype == "simulation_round_start":
                    _round_deltas = []
                    yield _emit({
                        "type": "swarm_round_start",
                        "run_id": run_id,
                        "round": int(swarm_event.get("round", 0)),
                        "n_rounds": int(swarm_event.get("total", n_rounds)),
                    })
                elif etype == "belief_shift":
                    _delta = float(swarm_event.get("delta", 0.0) or 0.0)
                    _round_deltas.append(abs(_delta))
                    yield _emit({
                        "type": "swarm_persona_vote",
                        "run_id": run_id,
                        "persona": str(swarm_event.get("agent_name", "")),
                        "stance": (
                            f"{float(swarm_event.get('prev_stance', 0.0)):+.2f}"
                            f" → {float(swarm_event.get('new_stance', 0.0)):+.2f}"
                        ),
                        "summary": (
                            f"Shifted on '{swarm_event.get('topic', '')}'"
                            f" by {_delta:+.2f}"
                        ),
                    })
                elif etype == "simulation_round":
                    _round_dict = dict(swarm_event.get("round") or {})
                    _consensus_delta = (
                        sum(_round_deltas) / len(_round_deltas) if _round_deltas else 0.0
                    )
                    yield _emit({
                        "type": "swarm_round_end",
                        "run_id": run_id,
                        "round": int(_round_dict.get("round_num", 0)),
                        "consensus_delta": round(_consensus_delta, 4),
                    })
                elif etype == "simulation_complete":
                    report_dict = dict(swarm_event.get("report") or {})
                    answer_text = _format_swarm_report(report_dict)
                    yield _emit({
                        "type": "swarm_synthesis",
                        "run_id": run_id,
                        "method": "swarm_consensus",
                    })
                    yield _emit({
                        "type": "swarm_complete",
                        "run_id": run_id,
                        "answer_text": answer_text,
                        "sources": sources,
                    })
                    final_artifacts = extract_arrow_artifacts(settings)
                    # Also emit `final` so orchestrator session-save triggers.
                    yield _emit({
                        "type": "final",
                        "run_id": run_id,
                        "answer_text": answer_text,
                        "sources": sources,
                        "fallback": retrieval_plan.fallback.to_dict(),
                        "strategy_fingerprint": "swarm_simulation",
                        **({"artifacts": final_artifacts} if final_artifacts else {}),
                    })
            return

        if agentic_mode:
            _prev_draft_embedding: list[float] = []
            _iterations_used: int = 0
            _last_convergence_score: float = 0.0
            _total_gap_count: int = 0
            _all_cited_sources: set[str] = set()
            _per_iter_cited_sources: list[set[str]] = []

            # Generate an initial non-streaming draft used only for self-critique.
            _draft_prompt = (
                f"{_system_instructions(settings)}\n\n"
                "Answer the user's question using ONLY the CONTEXT below. "
                "Cite passages as [S1], [S2], etc. If the context is insufficient, say so.\n\n"
                f"CONTEXT:\n{accumulated_context}"
            )
            current_draft = _response_text(
                llm.invoke([
                    {"type": "system", "content": _draft_prompt},
                    {"type": "human", "content": question},
                ])
            )

            for iteration in range(1, agentic_iteration_budget + 1):
                yield _emit({
                    "type": "iteration_start",
                    "run_id": run_id,
                    "iteration": iteration,
                    "total_iterations": agentic_iteration_budget,
                    "detail": {
                        "tool_name": "agentic_loop",
                        "task_summary": f"Refinement iteration {iteration}/{agentic_iteration_budget}",
                    },
                })

                gap_queries = _identify_gaps(question, current_draft, accumulated_context, llm)
                if not gap_queries:
                    break  # Answer is sufficiently complete — stop early.

                _total_gap_count += len(gap_queries)
                _prior_source_count = len(accumulated_sources)

                yield _emit({
                    "type": "gaps_identified",
                    "run_id": run_id,
                    "gaps": gap_queries,
                    "iteration": iteration,
                    "strategy_fingerprint": "gap_fill",
                    "detail": {
                        "tool_name": "gap_analyzer",
                        "task_summary": f"Identified {len(gap_queries)} gap(s)",
                    },
                    "ancestry": [run_id],
                })

                # Retrieve additional context for each identified gap.
                iteration_new_sources: list[dict[str, Any]] = []
                new_context_parts: list[str] = []
                for gap_query in gap_queries:
                    try:
                        gap_result = execute_retrieval_plan(
                            bundle=bundle,
                            adapter=adapter,
                            question=gap_query,
                            settings=settings,
                            llm=llm,
                            allow_query_expansion=False,
                            query_expander=_generate_sub_queries,
                        ).result
                        iteration_new_sources.extend(
                            s.to_dict() for s in gap_result.sources
                        )
                        new_context_parts.append(gap_result.context_block)
                    except Exception as gap_exc:  # noqa: BLE001
                        log.debug(
                            "Gap retrieval failed for query %r (iteration %d): %s",
                            gap_query,
                            iteration,
                            gap_exc,
                        )

                if not new_context_parts:
                    break  # No new evidence found — stop the loop.

                new_context_block = "\n\n".join(new_context_parts)
                candidate = accumulated_context + "\n\n" + new_context_block
                _compress_enabled = bool(settings.get("agentic_context_compress_enabled", True))
                _compress_threshold = int(
                    settings.get("agentic_context_compress_threshold_chars", _MAX_CONTEXT_CHARS)
                    or _MAX_CONTEXT_CHARS
                )
                if _compress_enabled and iteration >= 3 and len(candidate) > _compress_threshold:
                    try:
                        _compact = _compress_context(
                            accumulated_context, question, llm, iteration
                        )
                        accumulated_context = _compact + "\n\n" + new_context_block
                        yield _emit({
                            "type": "context_compressed",
                            "run_id": run_id,
                            "iteration": iteration,
                            "chars_before": len(candidate),
                            "chars_after": len(accumulated_context),
                        })
                    except Exception:  # noqa: BLE001
                        accumulated_context = candidate[:_compress_threshold]
                else:
                    accumulated_context = candidate[:_compress_threshold]
                accumulated_sources = _dedup_sources(
                    accumulated_sources + iteration_new_sources
                )
                _new_source_count = len(accumulated_sources) - _prior_source_count

                top_iter_score = max(
                    (float(s.get("score") or 0.0) for s in iteration_new_sources),
                    default=0.0,
                )
                yield _emit({
                    "type": "refinement_retrieval",
                    "run_id": run_id,
                    "iteration": iteration,
                    "sources": iteration_new_sources,
                    "context_block": new_context_block,
                    "top_score": top_iter_score,
                    "retrieval_delta": _new_source_count,
                    "strategy_fingerprint": "gap_fill",
                    "detail": {
                        "tool_name": "gap_retrieval",
                        "task_summary": f"Retrieved context for {len(gap_queries)} gap(s)",
                    },
                    "ancestry": [run_id],
                })

                # Re-synthesise a draft for the next gap-analysis cycle
                # (only needed when further iterations remain).
                if iteration < agentic_iteration_budget:
                    _refined_prompt = (
                        f"{_system_instructions(settings)}\n\n"
                        "Answer the user's question using ONLY the CONTEXT below. "
                        "Cite passages as [S1], [S2], etc. "
                        "If the context is insufficient, say so.\n\n"
                        f"CONTEXT:\n{accumulated_context}"
                    )
                    current_draft = _response_text(
                        llm.invoke([
                            {"type": "system", "content": _refined_prompt},
                            {"type": "human", "content": question},
                        ])
                    )
                    # Track per-iteration cited sources for diversity calculation
                    import re as _re
                    _iter_cited = set(_re.findall(r"\[S\d+\]", current_draft))
                    _per_iter_cited_sources.append(_iter_cited)
                    _all_cited_sources.update(_iter_cited)

                    # --- Sotaku-inspired convergence detection ---
                    _current_emb = _embed_text(current_draft, settings)
                    if _prev_draft_embedding:
                        _last_convergence_score = _cosine_similarity(
                            _prev_draft_embedding, _current_emb
                        )
                        if _last_convergence_score >= agentic_convergence_threshold:
                            _iterations_used = iteration
                            yield _emit({
                                "type": "iteration_converged",
                                "run_id": run_id,
                                "iteration": iteration,
                                "convergence_score": round(_last_convergence_score, 4),
                            })
                            break
                    _prev_draft_embedding = _current_emb
                _iterations_used = iteration

            # Compute citation diversity: fraction of total citations that appeared in >1 iteration
            _total_cited = len(_all_cited_sources)
            _shared_cited = (
                len(
                    _all_cited_sources.intersection(*_per_iter_cited_sources)
                    if len(_per_iter_cited_sources) > 1
                    else set()
                )
            )
            _citation_diversity = (
                round(1.0 - _shared_cited / _total_cited, 4) if _total_cited > 0 else 1.0
            )

            # Determine strategy fingerprint for the whole run
            _strategy = (
                "convergence"
                if _last_convergence_score >= agentic_convergence_threshold
                else ("gap_fill" if _iterations_used > 1 else "direct_synthesis")
            )

            # Emit trace event for skill candidate capture
            yield _emit({
                "type": "iteration_complete",
                "run_id": run_id,
                "iterations_used": _iterations_used,
                "convergence_score": round(_last_convergence_score, 4),
                "query_text": question,
                "strategy_fingerprint": _strategy,
                "citation_count": _total_cited,
                "citation_diversity_score": _citation_diversity,
                "gap_count_total": _total_gap_count,
            })

            # After all iterations, expose accumulated sources for the final answer.
            sources = accumulated_sources

        # Use smart model for final synthesis when configured (Research/Evidence Pack)
        _smart_modes = {"Research", "Evidence Pack"}
        _mode = str(settings.get("selected_mode", "Q&A") or "Q&A")
        synthesis_llm = create_smart_llm(settings) if _mode in _smart_modes else llm

        # ------------------------------------------------------------------
        # Final streaming synthesis using all accumulated context.
        # ------------------------------------------------------------------
        fallback_notice = ""
        if retrieval_plan.fallback.triggered:
            fallback_notice = (
                "\n\nRetrieval quality is low. Be explicit about uncertainty and do not "
                "invent support that is missing from the context."
            )
        system_prompt = (
            f"{_system_instructions(settings)}\n\n"
            "Answer the user's question using ONLY the CONTEXT below. "
            "Cite passages as [S1], [S2], etc. If the context is insufficient, say so."
            f"{fallback_notice}\n\n"
            f"CONTEXT:\n{accumulated_context}"
        )
        messages = [
            {"type": "system", "content": system_prompt},
            {"type": "human", "content": question},
        ]

        answer_parts: list[str] = []
        if hasattr(synthesis_llm, "stream"):
            # LangChain streaming path — yields chunk objects with partial content
            for chunk in synthesis_llm.stream(messages):
                text = _response_text(chunk)
                if text:
                    answer_parts.append(text)
                    yield _emit({"type": "token", "run_id": run_id, "text": text})
        else:
            # Non-streaming fallback — emit a single token event with the full answer
            answer = _response_text(synthesis_llm.invoke(messages))
            answer_parts.append(answer)
            yield _emit({"type": "token", "run_id": run_id, "text": answer})

        final_artifacts = extract_arrow_artifacts(settings)
        _final_strategy = (
            locals().get("_strategy") or
            ("sub_query_expansion" if len(retrieval_plan.stages) > 1 else "direct_synthesis")
        )
        yield _emit({
            "type": "final",
            "run_id": run_id,
            "answer_text": "".join(answer_parts),
            "sources": sources,
            "fallback": retrieval_plan.fallback.to_dict(),
            "strategy_fingerprint": _final_strategy,
            **({"artifacts": final_artifacts} if final_artifacts else {}),
        })

    except Exception as exc:  # noqa: BLE001
        yield _emit({"type": "error", "run_id": run_id, "message": str(exc)})


__all__ = ["stream_rag_answer", "_identify_gaps", "_dedup_sources", "_compress_context"]
