# Preserve and Productize Plan

**METIS codebase audit — preservation-first**

This document is a working audit of the METIS codebase written with a single guiding rule: assume everything is valuable until proven otherwise. The goal is not to propose a rewrite, invent a new vocabulary, or simplify the product into something smaller. The goal is to surface what already works, route it to the right part of the product surface, and call out only what is genuinely dead or duplicative.

Four sections follow:

1. [Features and subsystems to preserve exactly](#1-features-and-subsystems-to-preserve-exactly)
2. [Features to expose as part of the default user journey](#2-features-to-expose-as-part-of-the-default-user-journey)
3. [Advanced capabilities to keep but move behind expert controls](#3-advanced-capabilities-to-keep-but-move-behind-expert-controls)
4. [Genuine cleanup candidates](#4-genuine-cleanup-candidates)

---

## 1. Features and subsystems to preserve exactly

These are working, tested subsystems that must not be touched unless there is a specific bug to fix. They form the backbone of METIS's product value.

### 1.1 Core RAG pipeline

`metis_app/engine/querying.py` · `metis_app/engine/streaming.py` · `metis_app/services/vector_store.py`

The retrieval-augmented generation loop—load index bundle, embed the query, score against stored chunks, rank, build a context block, inject into an LLM prompt, and return a cited answer—is the central product primitive. The implementation is clean: `query_rag()` is a pure function with typed inputs and outputs. The streaming variant in `stream_rag_answer()` emits a well-defined sequence of SSE events (`run_started`, `retrieval_complete`, `subqueries`, `token*`, `final`, `error`) that the web UI already consumes correctly.

Preserve: the event schema, the `manifest_path`-based index contract, and the citation marker convention (`[S1]`, `[S2]`, …). These are load-bearing product details that every downstream component depends on.

### 1.2 All five RAG modes

`metis_app/services/response_pipeline.py` · `metis_app/engine/streaming.py`

- **Q&A** — grounded answer with inline citations. The default, and the simplest entry point.
- **Summary** — condensed key-ideas format (also triggered by "Blinkist-style summary" output style). `is_blinkist_summary_mode()` handles the detection cleanly.
- **Tutor** — Socratic teaching mode with flashcards, quiz questions, and guided follow-ups. `run_tutor_pipeline()` produces structured output including rendered flashcards and an answer key. One-shot detection (`is_one_shot_learning_request()`) correctly suppresses the Socratic follow-up when the user asks to be taught once.
- **Research** — deep-dive with sub-query expansion and knowledge-graph traversal. Only mode that triggers the `subqueries` SSE event.
- **Evidence Pack** — claim-level grounding, structured timeline output, suitable for dossiers and incident reports.

Each mode has a matching skill in `skills/` with independently tuned retrieval parameters (`retrieval_k`, `top_k`, `mmr_lambda`, `retrieval_mode`). The skill system is the right place for those defaults; nothing needs to move.

### 1.3 Sub-query expansion

`metis_app/engine/streaming.py` → `_generate_sub_queries()`

When Research mode is active and `use_sub_queries` is enabled, the engine makes a second LLM call to produce 3–5 additional search queries before synthesis. The implementation is safe: it returns an empty list on any failure, duplicate queries are deduplicated, and the original question is excluded from the sub-query list. The `subqueries` event is emitted before synthesis so the web UI can display the expansion in real time.

Preserve this subsystem as-is. It is one of the most visible differentiators of Research mode.

### 1.4 Reranking (top_k filtering)

`metis_app/services/vector_store.py` · `metis_app/services/index_service.py`

The pipeline retrieves `retrieval_k` candidates (default 25) and then reduces them to a `top_k` window (default 5) that becomes the context block. This two-stage approach—broad recall followed by precision-focused selection—is a standard production RAG pattern. The separation of `retrieval_k` from `top_k` in every skill definition is intentional and correct.

Preserve both parameters and the distinction between them. Conflating them into one "number of results" control would silently degrade quality.

### 1.5 MMR retrieval (diversity-aware ranking)

`metis_app/services/vector_store.py`

Max Marginal Relevance ensures the context window contains diverse passages rather than near-duplicate extracts from the same section. The `mmr_lambda` parameter (0 = maximum diversity, 1 = pure similarity) is already tuned differently per skill: `qa-core` omits explicit tuning (pure similarity default), while `evidence-pack-timeline` uses `0.5`, and `research-claims` uses `0.4`.

Preserve: `retrieval_mode` enum (`flat`, `mmr`, `hierarchical`), the `mmr_lambda` parameter, and the per-skill defaults.

### 1.6 Knowledge graph building

`metis_app/utils/knowledge_graph.py`

The `KnowledgeGraph` class builds a lightweight directed entity–relationship graph during ingestion. It supports two extraction strategies: a stdlib-only rule-based extractor that works offline, and an optional spaCy-backed NER path for higher-quality entity labels. The graph feeds entity-aware retrieval in Research mode by expanding the set of candidate chunks via graph traversal.

Preserve: the dual-strategy architecture (rule-based default + optional spaCy), the `build_knowledge_graph()` / `collect_graph_chunk_candidates()` public API, and the `to_dict()` / `from_dict()` serialization contract.

### 1.7 Session persistence

`metis_app/services/session_repository.py`

`SessionRepository` is a SQLite-backed store for multi-turn conversations. It covers the full lifecycle: create, load, append message, save feedback, rename, duplicate, export, and delete. The rich `EvidenceSource` type (with `sid`, `snippet`, `header_path`, `breadcrumb`, `score`, `locator`, `anchor`, and more) is preserved verbatim in each message's citation list.

Preserve: the schema, the feedback (thumbs-up/down + notes) capability, the export path, and the `rag_sessions.db` default location.

### 1.8 Run trace and event logging

`metis_app/services/trace_store.py` · `metis_app/services/stream_replay.py`

Every run emits structured events that are appended to both a per-run JSONL file (`traces/<run_id>.jsonl`) and the global runs log. The stream replay service uses these records to reconnect interrupted SSE streams from a `last_event_id`, deduplicating events so the client does not re-process tokens it already received.

Preserve: the append-only JSONL format, the per-run file layout, and the replay/deduplication logic.

### 1.9 Vector store abstraction

`metis_app/services/vector_store.py`

`VectorStoreAdapter` is a clean ABC with `build()`, `save()`, `load()`, `query()`, and `is_available()`. The default `JsonVectorStore` works with zero external dependencies. The `WeaviateAdapter` provides a production vector-DB path. The `resolve_vector_store()` router is settings-driven.

Preserve: the ABC contract (any future adapter must implement it), atomic writes via temp-staging in the JSON path, and the manifest-based index identity.

### 1.10 Skill system

`metis_app/services/skill_repository.py` · `metis_app/services/runtime_resolution.py` · `skills/`

Skills are YAML-frontmatter + Markdown body files in `skills/`. Each skill carries triggers (keywords, modes, file types, output styles) and `runtime_overrides` that are merged into the active settings at query time. `select_skills()` scores and ranks candidates; `build_system_prompt()` assembles the merged instructions; `resolve_runtime_settings()` applies parameter overrides with conflict resolution.

The six shipping skills (`qa-core`, `summary-blinkist`, `tutor-socratic`, `research-claims`, `evidence-pack-timeline`, and `symphony-setup`) are the canonical examples of how skills work.

Preserve: the SKILL.md format, the trigger schema, `runtime_overrides`, and the runtime resolution pipeline. This is the primary extension point for the product.

### 1.11 Brain graph model and visualization

`metis_app/models/brain_graph.py` · `apps/metis-web/app/brain/` · `metis_app/api/app.py` → `/v1/brain/graph`

The brain graph connects indexes, sessions, skills, and agent profiles as typed nodes (`BrainNode`) and edges (`BrainEdge`). The web UI renders it as an interactive SVG at `/brain`. This is a unique product surface that visualizes the relationships between a user's knowledge base and their conversation history.

Preserve: the node-type taxonomy (index, session, skill, agent), the `GET /v1/brain/graph` endpoint, and the web UI page.

### 1.12 Multi-provider LLM and embedding support

`metis_app/utils/llm_providers.py` · `metis_app/utils/embedding_providers.py` · `metis_app/utils/llm_backends.py`

The LLM factory (`create_llm()`) supports Anthropic, OpenAI, Google, xAI, LM Studio, and local GGUF without any provider-specific branching at call sites. The embedding factory (`create_embeddings()`) supports OpenAI, Google, Voyage, HuggingFace, and local sentence-transformers. Both factories degrade gracefully to a mock when the provider is unavailable (useful for tests and offline use).

Preserve: the factory pattern, the mock providers, and the `model_caps.py` context-window lookup table (100+ models covered with no network calls).

### 1.13 Local GGUF support

`metis_app/utils/llm_backends.py` · `metis_app/services/local_model_registry.py` · `metis_app/services/local_llm_recommender.py` · `apps/metis-web/app/gguf/`

`LocalGGUFBackend` wraps `llama_cpp.Llama` with lazy import and GPU-layer offloading. The model registry tracks named GGUF and sentence-transformer models. The recommender selects the best-fit model for available hardware (RAM, VRAM). The web UI at `/gguf` exposes download and model management.

Preserve: the lazy-import guard, GPU layer configuration, and the model registry format. This subsystem is the primary offline path.

### 1.14 Structure-Header Tree (SHT) parser

`metis_app/models/sht.py`

`build_sht_tree()` is a pure-Python, dependency-free document section parser. It takes header annotations and content spans and produces a tree of `SHTNode` records with stable deterministic IDs, header paths, page spans, and character offsets. It feeds the structure-aware ingestion path when `structure_aware_ingestion` is enabled.

Preserve: the pure-Python implementation (zero external deps), the deterministic node ID scheme, and the `build_sht_tree()` / `SHTNode.to_dict()` public API.

### 1.15 Feedback and run-action approvals

`metis_app/api/sessions.py` → `POST /v1/sessions/{id}/feedback` · `metis_app/api/app.py` → `POST /v1/runs/{run_id}/actions`

Users can vote thumbs-up or thumbs-down on any response with an optional text note. The agentic run-action endpoint supports approval or denial of mid-run actions (currently used for `confirm_settings` when `require_action` is set on a request).

Preserve both endpoints and the `action_required` SSE event shape. The run-action gate is the trust boundary for agentic behavior.

### 1.16 API security layer

`metis_app/api/app.py`

`METIS_API_TOKEN` enables Bearer token authentication on all protected endpoints. `METIS_API_CORS_ORIGINS` controls allowed origins. `api_key_*` fields are rejected by default at write time (require `METIS_ALLOW_API_KEY_WRITE=1`). Error mapping (`ValueError` → 400, `RuntimeError` → 503) is consistent across all routes.

Preserve: the environment-variable-driven security model, the api_key write guard, and the CORS default (localhost only).

---

## 2. Features to expose as part of the default user journey

These capabilities are already implemented but not all of them are fully surfaced in the current default experience. They are well-understood, safe to show to any user, and would improve the product's legibility if placed on the main path.

### 2.1 Q&A as the starting mode

**Rationale:** Q&A is the lowest-friction entry point. It produces a direct answer with inline citations (`[S1]`, `[S2]`) and a populated evidence panel. Every new session should default to Q&A unless the user or a skill explicitly requests another mode.

**Current state:** `selected_mode` defaults to `"Q&A"` in `querying.py`. The chat UI already shows the mode label. No change needed to the backend; the web UI settings page could pre-select Q&A more explicitly during first use.

### 2.2 Index building with streaming progress

**Rationale:** Users need confidence that their documents were processed correctly. The streaming build endpoint (`POST /v1/index/build/stream`) already emits progress events (Reading → Embedding → Saving). The library page already renders a progress bar.

**Surface action:** Make streaming the only build path in the web UI (no silent batch build). Show the three-stage progress bar by default on every build, including document count and chunk count in the completion summary.

### 2.3 Mode selector in the chat UI

**Rationale:** The five modes are the primary product differentiator. A user who discovers Summary mode or Evidence Pack for the first time gains immediate value. The mode selector should be persistently visible in the chat input row, not buried in settings.

**Current state:** Mode is set via the settings page. A persistent dropdown in the chat input area would remove the round-trip to settings.

### 2.4 Evidence panel with expandable sources

**Rationale:** The evidence panel (`components/chat/evidence-panel.tsx`) shows retrieved sources with snippet, score, file path, and header breadcrumb. This is the most direct proof that the answer is grounded. It should be open by default for new users rather than collapsed.

**Current state:** The panel is implemented. Whether it defaults open or closed is a presentational choice; no backend work is needed.

### 2.5 Session management (create, rename, duplicate, delete)

**Rationale:** Sessions are how users return to previous research. The session repository supports all four operations; the web UI sidebar already implements them. The default experience should present session management as first-class, not a sidebar afterthought.

**Surface action:** On first use, create a session automatically with a title derived from the first question. Show the session list prominently so users understand they can return to prior work.

### 2.6 Feedback (thumbs-up/down) on every response

**Rationale:** Response-level feedback is the simplest improvement signal. The endpoint exists; the web UI has the `assistant-copy-actions.tsx` component. Ensure feedback buttons are present on every assistant turn, not only on selected turns.

### 2.7 LLM provider and model selection

**Rationale:** Provider choice is a first-class concern for local-first users. The settings page already has provider and model dropdowns. These should appear in the setup wizard and on the initial empty-index state so users configure their LLM before frustrating with a failed query.

### 2.8 Setup wizard as the canonical onboarding path

**Rationale:** `apps/metis-web/app/setup/` contains a wizard that walks through provider selection, embedding selection, and first index building. This is the correct default entry point for new installations. The home page (`page.tsx`) health-check logic should route to the wizard when no index or provider is configured.

### 2.9 Skill auto-selection (passive, always on)

**Rationale:** The skill system is already passive: `select_skills()` fires on every query and applies the matching skill's `runtime_overrides`. Users do not need to know skills exist for the system to benefit from them. The appropriate surface is not a "skill picker" but a subtle indicator that shows which skill was matched (e.g., "Q&A Core" displayed next to the mode label).

---

## 3. Advanced capabilities to keep but move behind expert controls

These capabilities are production-ready and genuinely valuable for power users. They should not be removed or hidden from the settings system, but they should not appear in the primary chat or library flows. An "Advanced" or "Expert" panel in settings—collapsed by default—is the right home.

### 3.1 Agentic mode and iteration control

**Settings:** `agentic_mode` (bool), `agentic_max_iterations` (int, default 2)

The recursive refinement loop (initial synthesis → self-critique → sub-query generation → re-synthesis) can substantially improve Research mode output on complex questions. It is also slower, more expensive, and confusing when it appears uninvited. Gate it behind an explicit toggle labeled "Agentic refinement" in an Advanced panel, not in the main chat header.

The `agentic_max_iterations` parameter is meaningful only when `agentic_mode` is on; show it as a dependent control.

### 3.2 Sub-query expansion parameters

**Settings:** `use_sub_queries` (bool), `subquery_max_docs` (int)

Sub-query expansion (`_generate_sub_queries()`) adds a second LLM call that generates 3–5 search variants. The default in `research-claims` skill is already `agentic_mode: true`, which implies sub-query behavior. Expose `use_sub_queries` as a standalone toggle for users who want sub-query expansion in Q&A mode without the full agentic loop.

### 3.3 Retrieval depth and reranking controls

**Settings:** `retrieval_k` (int, default 25), `top_k` (int, default 5), `use_reranker` (bool)

The two-stage retrieval pipeline is powerful but the parameters are only meaningful if the user understands what they do. Place them in an "Retrieval depth" section within Advanced: describe `retrieval_k` as "candidates to recall" and `top_k` as "passages to use in the answer."

### 3.4 MMR lambda and retrieval mode

**Settings:** `retrieval_mode` (`flat` | `mmr` | `hierarchical`), `search_type` (`similarity` | `mmr`), `mmr_lambda` (float 0–1)

MMR diversity control is one of the subtler but more impactful settings for corpus-heavy queries. Surfacing it in the Advanced panel with a slider (0 = maximum diversity, 1 = maximum relevance) and a brief explanation would serve researchers and analysts well without cluttering the main flow.

### 3.5 Structure-aware and semantic-layout ingestion

**Settings:** `structure_aware_ingestion` (bool), `semantic_layout_ingestion` (bool), `document_loader` (str)

Structure-aware ingestion uses the SHT parser to build header-path metadata for each chunk, which improves hierarchical retrieval. Semantic layout ingestion (backed by the optional `kreuzberg` library) extracts richer layout signals from PDFs and DOCX files. Both settings are off by default and require no UI explanation in the primary flow. Add them to an "Ingestion" subsection in Advanced with a note that they apply at index-build time.

### 3.6 DeepRead mode and LangExtract grounding

**Settings:** `deepread_mode` (bool), `enable_langextract` (bool)

DeepRead performs a multi-pass reading strategy at index time. LangExtract generates citation-grounding HTML in the `PipelineResult.grounding_html` field (implemented in `response_pipeline.py`). Both produce richer output at higher latency cost. Keep them in Advanced under "Answer quality" with accurate latency warnings.

### 3.7 Custom system instructions

**Settings:** `system_instructions` (str)

The default system prompt (`"You are METIS, a grounded AI assistant. Use citations when retrieved context is available."`) in `querying.py` is good enough for most users. Power users who need domain-specific personas or output constraints should be able to override it. Surface this as a multi-line text area in an "Prompt" section in Advanced.

### 3.8 Chunk size and overlap

**Settings:** `chunk_size` (int), `chunk_overlap` (int)

Chunking strategy affects both retrieval recall and answer coherence. Larger chunks preserve more context per passage; smaller chunks improve precision. These are index-time parameters (they only apply when building a new index), which makes them confusing if exposed at query time. Surface them in the Library / Index Build flow under an "Advanced options" expander.

### 3.9 LLM tuning parameters

**Settings:** `llm_temperature` (float), `llm_max_tokens` (int), `llm_provider` / `llm_model`

Temperature and token limits are meaningful for users who know what they are. The provider and model pickers already appear in settings; temperature and token limit should appear below them in an "LLM tuning" section. The `model_caps.py` lookup can pre-fill sensible defaults for each model's context window.

### 3.10 Local GGUF configuration

`apps/metis-web/app/gguf/` · `metis_app/utils/llm_backends.py`

GPU layer count, context window length, and thread count (`gpu_layers`, `context_length`, `threads` in `LocalGGUFBackend`) are hardware-specific parameters that require understanding of the local system. The GGUF page already exists; keep it accessible from settings rather than from the main navigation.

### 3.11 Agent profiles

`metis_app/services/profile_repository.py` · `metis_app/models/parity_types.py` → `AgentProfile`

Agent profiles encapsulate a full set of persona + retrieval + iteration settings (system instructions, citation policy, `retrieval_strategy`, `iteration_strategy`, `frontier_toggles`, etc.). They are the right abstraction for teams that need repeatable research configurations. Surface profile management under an "Agent profiles" section in Advanced settings, not on the main path.

### 3.12 Agent lightning mode

**Settings:** `agent_lightning_enabled` (bool)

Lightning mode reduces latency by skipping slower agentic substeps. It is useful only when `agentic_mode` is on. Show it as a dependent control inside the agentic refinement section.

### 3.13 Direct LLM query (no retrieval)

`metis_app/engine/querying.py` → `query_direct()` · `POST /v1/query/direct`

The direct query path sends a prompt straight to the LLM without any retrieval. It is useful for testing provider connectivity and for conversational tasks that do not require document context. Accessible via `chat_path: direct` in settings. Keep this setting but surface it in Advanced as "Bypass retrieval (direct LLM query)" with a clear warning.

### 3.14 Run trace viewer

`apps/metis-web/app/diagnostics/` · `GET /v1/traces/{run_id}`

The diagnostics page and trace endpoint give full visibility into the SSE event stream for any completed run. This is invaluable for debugging retrieval quality. Keep it accessible from a "Debug" section or a help menu, not from the main navigation.

### 3.15 Verbose mode and show_retrieved_context

**Settings:** `verbose_mode` (bool), `show_retrieved_context` (bool)

`verbose_mode` expands logging output; `show_retrieved_context` appends the full context block to the answer for inspection. Both are debugging aids. Surface them under Advanced / Debug alongside the trace viewer.

### 3.16 Output style selector

**Settings:** `output_style` (str: `Default answer`, `Detailed answer`, `Brief / exec summary`, `Blinkist-style summary`, `Structured report`, `Script / talk track`)

Output styles fine-tune formatting within a mode. They are most useful when paired with the Tutor or Evidence Pack modes. Surface them in the chat interface as a secondary selector that appears after the user picks a mode, or in Advanced settings as a "Response format" control.

---

## 4. Genuine cleanup candidates

These items are either dead code, redundant with something else, inconsistent with the current product direction (ADR 0004: one interface), or impossible to explain to a user as a product feature. None of them are load-bearing for the RAG pipeline.

### 4.1 `skills/symphony-setup/` — wrong product context

`skills/symphony-setup/SKILL.md` describes how to set up Symphony (OpenAI's Codex orchestrator for Linear tickets). It has no triggers relevant to RAG document queries (`symphony setup`, `configure symphony for my repo`). It belongs in the agent-coding-assistant context (`.agents/skills/`), not in the product skill library that fires during document Q&A sessions.

**Action:** Move to `.agents/skills/symphony-setup/` (or remove from `skills/` entirely). Do not rename or rewrite; just relocate.

### 4.2 `apps/metis-reflex/` — superseded proof-of-concept

The Reflex Python UI was a proof-of-concept evaluated as an alternative to Next.js. ADR 0004 settled on Next.js + Tauri as the single interface. The Reflex app is not shipped, not tested in CI, and is mentioned as a deprecated alternative in ADR 0003.

**Action:** Archive to a `_archive/` directory or delete. If kept for reference, add a prominent `DEPRECATED` header to its `README.md`.

### 4.3 `/design` page — not user-facing

`apps/metis-web/app/design/page.tsx` is a design-system component playground. It is useful for contributors but should not be reachable via the main navigation in production builds.

**Action:** Exclude from production builds via a `process.env.NODE_ENV === 'development'` guard, or move to `__dev__/design/` convention. No behavior change for end users.

### 4.4 Stale Qt/PySide6 documentation references

`docs/cleanup/interface-confusion-inventory.md` already catalogues 28 files with Qt/PySide6 references inconsistent with ADR 0004. The cleanup actions (REWRITE, DELETE, MOVE TO DEPRECATED) are well-scoped.

**Action:** Execute the inventory. The highest-priority items (README.md rewrites, `docs/migration/qt_to_web_container.md` deletion) should be done as a single documentation pass. No code changes are implied.

### 4.5 `apps/metis-web-lite/` (Astro) — unclear product role

The Astro app has a minimal presence in the repository. ADR 0003 mentions it as an optional frontend that "consumes React natively." It is not referenced in ADR 0004. If it is not a product surface and not being actively developed, it is a maintenance liability.

**Action:** Evaluate whether `metis-web-lite` serves a specific purpose (e.g., an embedded docs site or a lightweight demo). If there is no active use case, archive or remove. If it is retained, add a `README.md` that explains its scope relative to the main `metis-web`.

### 4.6 `metis_app/services/heretic_service.py` — legacy controller dependency, no API route

`heretic_service.py` wraps the `heretic-llm` CLI (a HuggingFace model abliteration tool) via subprocess calls to avoid importing its AGPL-licensed code. It is imported in `metis_app/controllers/app_controller.py`, which is the legacy Qt MVC controller layer. No FastAPI route calls it, no web UI page surfaces it, and no skill or settings key references it. The controller itself is only exercised by legacy tests and is being deprecated as part of the one-interface transition (ADR 0004).

**Action:** Move to a `scripts/` or `tools/` directory to signal it is a developer utility, not a product feature. Alternatively, gate it behind an explicit `METIS_ENABLE_HERETIC=1` environment flag. Either way, address it as part of the broader `app_controller.py` legacy cleanup rather than in isolation.

### 4.7 `engine/runs.py` `RunEvent` vs `models/parity_types.py` `TraceEvent` — near-duplicate types

`runs.py` defines `RunEvent` (run_id, timestamp, stage, event_type, payload, citations_chosen). `parity_types.py` defines `TraceEvent` with the same fields. `trace_store.py` imports `TraceEvent` from `parity_types.py` and also accepts raw dicts via the `append()` method. `RunEvent` is imported only in `tests/test_trace_store.py`; no production code path uses it directly.

**Action:** Consolidate: re-export `RunEvent` from `parity_types.py` as an alias for `TraceEvent`, or replace the one test import with `TraceEvent` and remove `RunEvent`. Either way, eliminating the duplicate definition removes a silent source of confusion for contributors who might implement a new trace path against the wrong type.

### 4.8 `apps/metis-reflex/metis_reflex.py` reference to `python main.py`

Even if the Reflex app is kept as an archive, `metis_reflex.py` contains a comment referencing `python main.py` as the Qt desktop entry point. This contradicts ADR 0004. Any archived copy should have the comment corrected or removed so it does not re-surface as documentation.

**Action:** Address as part of the Reflex app archival in §4.2 above.

---

## Summary table

| Item | Section | Action word |
|---|---|---|
| Core RAG pipeline (retrieval → reranking → cited synthesis) | Preserve | Freeze |
| All five RAG modes (Q&A, Summary, Tutor, Research, Evidence Pack) | Preserve | Freeze |
| Sub-query expansion (`_generate_sub_queries`) | Preserve | Freeze |
| Two-stage reranking (retrieval_k → top_k) | Preserve | Freeze |
| MMR retrieval | Preserve | Freeze |
| Knowledge graph building (rule-based + spaCy) | Preserve | Freeze |
| Session persistence (SQLite + EvidenceSource rich type) | Preserve | Freeze |
| Run trace + stream replay / resume | Preserve | Freeze |
| Vector store abstraction (JSON default + Weaviate) | Preserve | Freeze |
| Skill system (SKILL.md + runtime overrides) | Preserve | Freeze |
| Brain graph model + `/v1/brain/graph` | Preserve | Freeze |
| Multi-provider LLM + embedding factories | Preserve | Freeze |
| Local GGUF support | Preserve | Freeze |
| Structure-Header Tree (SHT) parser | Preserve | Freeze |
| Feedback + run-action approvals | Preserve | Freeze |
| API security (token, CORS, api_key write guard) | Preserve | Freeze |
| Q&A as default mode | Default journey | Surface |
| Streaming index build progress | Default journey | Surface |
| Mode selector in chat input row | Default journey | Surface |
| Evidence panel open by default | Default journey | Surface |
| Session auto-create + persistent session list | Default journey | Surface |
| Feedback buttons on every response | Default journey | Surface |
| LLM provider + model picker in setup wizard | Default journey | Surface |
| Setup wizard as canonical onboarding | Default journey | Surface |
| Skill auto-selection indicator (passive) | Default journey | Surface |
| Agentic mode + iteration count | Expert | Gate |
| Sub-query toggle + max-docs | Expert | Gate |
| retrieval_k / top_k / use_reranker | Expert | Gate |
| MMR lambda + retrieval mode | Expert | Gate |
| Structure-aware + semantic-layout ingestion | Expert | Gate |
| DeepRead + LangExtract | Expert | Gate |
| Custom system instructions | Expert | Gate |
| Chunk size + overlap | Expert | Gate |
| LLM temperature + token limit | Expert | Gate |
| Local GGUF GPU/context/threads config | Expert | Gate |
| Agent profiles | Expert | Gate |
| Agent lightning mode | Expert | Gate |
| Direct LLM query (bypass retrieval) | Expert | Gate |
| Run trace viewer | Expert | Gate |
| Verbose mode + show_retrieved_context | Expert | Gate |
| Output style selector | Expert | Gate |
| `skills/symphony-setup/` | Cleanup | Relocate |
| `apps/metis-reflex/` | Cleanup | Archive |
| `/design` page | Cleanup | Dev-only guard |
| Stale Qt/PySide6 documentation | Cleanup | Execute inventory |
| `apps/metis-web-lite/` (Astro) | Cleanup | Evaluate + README |
| `heretic_service.py` | Cleanup | Move to scripts/ or flag-gate |
| `engine/runs.py` `RunEvent` duplicate | Cleanup | Remove or consolidate |
