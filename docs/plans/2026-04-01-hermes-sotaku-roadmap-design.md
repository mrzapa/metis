# Design: Hermes Agent + Sotaku Inspirations for Metis

**Date:** 2026-04-01
**Constraints:** Local-first (GGUF + cloud APIs), no new infrastructure (SQLite + JSON vector store)

---

## Context

Two external repos were analyzed for ideas to improve Metis:

**[NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)** — Self-improving agent framework. Key patterns: self-registering tool registry, autonomous skill creation from experience traces, subagent delegation (parallel workers), batch trajectory generation for RL training data.

**[chenglou/sotaku](https://github.com/chenglou/sotaku)** — Looped transformer for sudoku (constraint satisfaction). Key insight: run the same weights N times at inference; convergence emerges naturally without explicit fixed-point losses. Train at 16 iterations, scale to 1024 at test time with better accuracy. Reverse curriculum (hard→easy) beats forward curriculum. Core thesis: *replace if/else heuristics with tiny neural nets that search through the idea space.*

Metis already has: `agentic_mode` loop, SKILL.md skills system, autonomous research (11 constellation faculties), companion AI, retrieval pipeline with sub-queries + reranking, web graph service.

---

## Roadmap: 4 Independent Phases

### Phase 1: IterRAG — Convergence-Based Retrieval Loop

**Inspired by:** Sotaku's looped transformer with test-time compute scaling

**Problem:** `agentic_mode` runs a fixed `agentic_max_iterations` loop with no convergence detection. The answer may stabilize after 2 iterations but the loop continues to the max, wasting tokens.

**Design:**
1. After each iteration, embed the synthesized answer using the existing embeddings provider
2. Compute cosine similarity between the current and previous answer embeddings
3. If similarity > `agentic_convergence_threshold` (default: 0.95), stop early
4. The synthesized answer is appended to the next iteration's retrieval context (feeding output back as enriched input — the Sotaku analog: same pipeline weights, richer context each pass)
5. Response trace gains `iterations_used: N` and `convergence_score: 0.97` for UI display

**New settings:**
```json
"agentic_iteration_budget": 4,
"agentic_convergence_threshold": 0.95
```

**Files to change:**
- `metis_app/services/retrieval_pipeline.py` — main loop change + convergence check
- `metis_app/engine/querying.py` — context enrichment between iterations
- `metis_app/default_settings.json` — new settings
- `metis_app/api/models.py` — add `iterations_used`, `convergence_score` to response model

---

### Phase 2: Reverse-Curriculum Autonomous Research

**Inspired by:** Sotaku's finding that hard→easy training consistently beats easy→hard

**Problem:** Autonomous research iterates through faculties in a fixed sequential order, treating all gaps equally regardless of their importance or interconnectedness.

**Design:**
- Define a hardness score per faculty gap:
  ```
  hardness = demand_score / max(current_index_count, 1)
  demand_score = number of other faculties referencing this one in BrainGraph
  ```
- Sort faculties by hardness descending before each research cycle
- Rationale: high-demand + low-coverage faculties (e.g., "reasoning" referenced by 6 others but 0 auto-indexes) benefit most from fresh research; easy/low-demand gaps fill naturally over time

**Files to change:**
- `metis_app/services/autonomous_research_service.py` — sort order + hardness calculation
- BrainGraph model (wherever `constellation_faculties` adjacency is stored) — read connection counts

---

### Phase 3: Skill Self-Evolution from Traces

**Inspired by:** Hermes Agent's built-in learning loop (autonomous skill creation from experience)

**Problem:** Skills are static SKILL.md files. Successful multi-step reasoning patterns are lost when a session ends.

**Design:**
1. When `iterations_used >= 2` on a successful agentic run, save a `skill_candidate` to SQLite:
   - Fields: `query_text`, `trace_json` (chain of retrievals + syntheses), `convergence_score`, `created_at`, `promoted: bool`
2. Score candidates: convergence speed (fewer iterations = higher score) + user feedback signals if available
3. Companion AI's existing periodic reflection (on `reflection_cooldown_seconds` timer) gains a new step: review top-5 unreviewed candidates
4. Companion calls LLM to judge generalizability; if yes, generates a new SKILL.md
5. New skill written to `skills/auto-generated/<slug>.md` and registered on next skill scan
6. Safety: auto-generated skills tagged `source: auto`, bulk-deletable via API

**Files to change:**
- `metis_app/services/skill_repository.py` — `save_candidate()`, `review_candidates()`, `promote_to_skill()`
- `metis_app/services/assistant_companion.py` — skill review trigger in reflection cycle
- Run trace finalization site (wherever agentic runs resolve) — call `save_candidate()`

---

### Phase 4: Parallel Research Subagents

**Inspired by:** Hermes Agent's subagent delegation for parallel workstreams

**Problem:** Autonomous research researches faculties sequentially, making full constellation coverage slow — each faculty cycle blocks the next.

**Design:**
1. New setting: `autonomous_research_concurrency: 3` (default `1` preserves current behavior)
2. `asyncio.Semaphore(concurrency)` gates concurrent faculty research tasks
3. `asyncio.gather()` over all qualifying faculties bounded by semaphore
4. Index writes protected by existing SQLite transactions; add `asyncio.Lock` for JSON vector file writes if needed
5. Per-provider request delay: `autonomous_research_request_delay_ms` (default: `500`) throttles web search API calls within concurrent tasks

**Files to change:**
- `metis_app/services/autonomous_research_service.py` — async gather + semaphore pattern
- `metis_app/default_settings.json` — `autonomous_research_concurrency`, `autonomous_research_request_delay_ms`

---

## Implementation Order

| Order | Phase | Reason |
|-------|-------|--------|
| 1 | Phase 1 (IterRAG) | Highest user-visible impact; touches only existing code paths |
| 2 | Phase 2 (Reverse Curriculum) | Small behavioral change, single file |
| 3 | Phase 4 (Parallel Research) | Independent async refactor |
| 4 | Phase 3 (Skill Evolution) | Most complex; depends on Phase 1 for trace data |

---

## Verification

- **Phase 1:** Run an agentic query; assert `iterations_used < agentic_iteration_budget` when answer stabilizes; confirm trace contains `convergence_score`
- **Phase 2:** Inspect research order in logs — high-demand faculties should appear first in each cycle
- **Phase 3:** Run 3+ successful agentic queries, trigger companion reflection, verify `skills/auto-generated/` gets populated
- **Phase 4:** Set `concurrency: 3`; watch autonomous research complete ~3x faster in logs; verify no duplicate or corrupted index writes
