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

---

## Web UI new-user audit (2026-04-25)

Filed from a live new-user click-through of `apps/metis-web` at localhost:3000 (Claude-in-Chrome MCP + DOM/network instrumentation). Full original entry with verification details: [`plans/IDEAS.md`](../plans/IDEAS.md) — *Web UI new-user walkthrough — P0–P3 punch list*. Items 5/18/19 are parked there; 10/11/12/13 went to M12; 31 went to M13. Everything below is M01 work.

Attack in the order **P0 → P1 visual → P1 perf → P2 IA → P2 copy → P3**. Each numbered item is intended to be a self-contained PR.

### Status snapshot (2026-04-26)

The audit is **mostly closed**. Remaining items are flagged below per phase. Closed items have a ✅ and a PR reference; parked items live in [`plans/IDEAS.md`](../plans/IDEAS.md) → *Iced*; nothing-to-do items have a 🟢.

**PR map** — every closed item lands via one of these merged PRs:

| PR | Merged | Scope |
|---|---|---|
| [#543](https://github.com/mrzapa/metis/pull/543) | 2026-04-25 | Initial audit doc filing + triage; reduced-motion sweep on PageChrome + OnboardingStep + 15 component reveals (audit Phase 1 item 1) |
| [#547](https://github.com/mrzapa/metis/pull/547) | 2026-04-25 | Most audit Phase 1–6 items + Settings deep-dive items 47–53 + skill-pass refinements 35–46. **Excludes** the unified-FAB sweep (commit `8177535`) which was pushed AFTER this PR closed and is recovered as #553. |
| [#549](https://github.com/mrzapa/metis/pull/549) | (open) | GSAP ambient seedling-pulse widget — replaces the M13 "Seedling heartbeat" text rows with a 6-layer SVG widget driven by real `/v1/seedling/status` data. |
| [#553](https://github.com/mrzapa/metis/pull/553) | (open) | Unified gold FAB radial menu (audit item 8) + lens-flare follow-up (item 5) + minor tooltip follow-ups (forecast covariate `Ignore`/`Dynamic`/`Static`, RAG banner buttons, × Close in catalogue inspector). Cherry-pick recovery of orphaned `8177535`. |

**Remaining open items**:
- Item 18 (blocked-URL/PII signal) — **parked in IDEAS.md *Iced***, awaiting reproduction
- Item 5 (UI-editable API keys) — **parked**, posture decision tied to M17 Phase 8
- Item 19 (home FCP ~696ms) — **parked**, not user-blocking
- Catalogue-search-by-name affordance is dropped from the home page in PR #553 (sweep 6 cherry-pick) when consolidating the three-sparkle-icon problem into the unified gold FAB. The component file (`apps/metis-web/components/constellation/catalogue-search-overlay.tsx`) and its tests still exist but are no longer mounted on `/`. **Open question**: fold it into the unified FAB's Threads-search satellite, or delete the dead code. Flag for future polish PR.

**Phase 1 (P0 first-run blockers)** — all ✅ closed:
- 1 ✅ PR #543 (PageChrome) + #547 (15 components)
- 2 ✅ PR #547 (`first-run-banner.tsx` mounted on `/`)
- 3 ✅ PR #547 (badge gated on `directChatReadiness` memo)
- 4 ✅ PR #547 (structured 422 with config-error card)

**Phase 2 (P1 visual / sprite)** — all ✅ closed:
- 5 ✅ PR #547 first attempt + PR #553 follow-up cleanup (lens-flare → soft warm-gold gradient)
- 6 ✅ PR #547 (sprite anchor — defensive half-pixel rounding)
- 7 ✅ PR #547 (canvas DPR via `setTransform(dpr,...)` capped at 2)
- 8 ✅ PR #553 (unified gold FAB with 3-satellite radial menu — orphaned from #547, recovered)
- 9 🟢 PR #547 — investigated, could not reproduce at any common viewport width

**Phase 3 (P1 perf / network)**:
- 10 🟢 *Investigated 2026-04-26.* The observed multiplier (`/v1/assistant` ×3, `/v1/seedling/status` ×3, `/v1/settings` ×4) traces to React 19 StrictMode dev-mode double-invocation of `useEffect` (Next.js defaults `reactStrictMode: true`) plus intentional fresh-state fetches before user-triggered actions in `apps/metis-web/app/chat/page.tsx` (6 `fetchSettings` callsites: 1 mount, 5 pre-action). In production builds StrictMode is off and effects run once. **Not a real prod perf bug.** Worth a follow-up only if production telemetry shows the same fan-out.
- 11 🟢 *Investigated 2026-04-26.* The two `/v1/comets/active` calls and the `/v1/comets/events?poll_seconds=10` long-poll trace to a single consumer (`apps/metis-web/hooks/use-news-comets.ts`) using a hydrate-then-stream SSE pattern (`streamCometEvents` calls `fetchActiveComets` first then opens the SSE). The duplicate `/v1/comets/active` call is StrictMode dev-mode mount-effect-running-twice; the 31.5s SSE connection is the *intended* keepalive duration (long-poll → push). **Not a real prod perf bug.** SSE is the right choice for live comet updates.
- 12 (audit's "blocked URL with query-string data") = item 18 in IDEAS.md, parked

**Phase 4 (P2 IA)** — all ✅ closed:
- 13 ✅ PR #547 (Pipeline → Research log; nav unified)
- 14 ✅ PR #547 (Diagnostics out of nav, behind Cmd/Ctrl+Shift+D)
- 15 ⚠️ Forecast feature still implicit — Settings has Forecast (TimesFM) defaults but Chat path toggle is `Direct / RAG` only. Not addressed.
- 16 ✅ PR #547 (`assistant_identity.minimized` defaults `true`; companion overlay starts collapsed)

**Phase 5 (P2 onboarding / copy)** — mostly ✅ closed:
- 17 ✅ PR #547 (step labels un-truncated to 1 word; WHAT THIS UNLOCKS sidebar dropped; duplicate STEP n OF 5 removed). Plus follow-up provider/embedding subtext + Credential posture removal in same PR.
- 18 ✅ PR #547 (step tabs are 1-word now: Provider · API key · Embeddings · Index · Launch)
- 19 ✅ PR #547 (heading voice neutralized — "Choose how I should embed" → "Choose your embedding provider"; "Add credentials only if I need them" → "Add an API key (optional)")
- 20 ✅ PR #547 (auto-pair embedding default with chosen LLM provider until user touches it)
- 21 ✅ PR #547 (chat toolbar tooltips on Agentic, Heretic, Direct, RAG, Change, model pill)
- 22 ✅ PR #547 (astronomy glossary tooltips on Faculty Sigil, Stellar Identity, Spectral Class, Magnitude, palette swatches across 4 files)
- 23 ✅ PR #547 (chat empty-state procedural prompt chips replace filler)

**Phase 6 (P3 minor)** — all ✅ closed:
- 24 ✅ PR #547 (Export PPTX hidden when no sources)

**Skill-pass refinements (items 35–46)** — all ✅ closed:
- 35 ✅ PR #547 (anthropic/mock pill clickable)
- 36 ✅ PR #547 (Provider dropdown with 8 supported providers; Model placeholder per provider)
- 37 ✅ PR #547 (WebGPU plug-and-play wizard fork — single-click to /chat)
- 38 ✅ PR #547 ("Heretic" chat-toolbar pill — kept visible, tooltip explains it now)
- 39 🟡 Star-creation on canvas-click — flagged but not yet refactored to a dedicated mode
- 40 🟡 CSV-only attach icon — title attr added in PR #553 (sweep 6) but icon itself unchanged
- 41 🟢 Investigated — already correctly OFF at schema level; was a local override
- 42 🟡 Outline tab still empty placeholder
- 43 🟡 Trace tab still surfaces dev events to non-dev users
- 44 ✅ PR #547 (third-person Companion overlay voice)
- 45 🟡 Chat toolbar progressive disclosure not implemented (the `⋯` menu wrap)
- 46 ✅ PR #547 (Heretic href `[BLOCKED]` issue resolved alongside the structured 422 work)

**Settings deep-dive (items 47–53)** — all ✅ closed:
- 47 ✅ PR #547 (`enable_recursive_memory` defaults ON)
- 48 ✅ PR #547 (archetype renamed to "Local-first research companion")
- 49 🟡 Privacy & network audit still 3 clicks deep — promotion to header pill not implemented
- 50 ✅ PR #547 (raw setting-key references → friendly Link with deep-link)
- 51 ✅ PR #547 (`?tab=` deep-link works)
- 52 🟢 Investigated — already sticky-bottom from earlier commit; audit was stale
- 53 ✅ PR #547 (companion overlay default-collapsed via server-side flip; cross-page coverage resolved)

**Items still 🟡 open and worth a future polish PR**:
- Item 15 (expose Forecast in chat path or remove orphan settings)
- Item 39 (star-creation as explicit mode)
- Item 40 (CSV attach icon — replace generic icon with sparkline glyph)
- Item 42 (Outline tab — implement or hide)
- Item 43 (Trace tab — gate behind Developer mode)
- Item 45 (Chat toolbar `⋯` progressive disclosure)
- Item 49 (Promote Privacy & network audit to a header pill)
- Catalogue-search-by-name affordance — fold into FAB or delete

These are net-new follow-up items, not regressions. Keep this snapshot up to date as future PRs close items.

### Phase 1 — P0 first-run blockers (1–2 days)

1. **Reduced-motion reveal bug.** Elements get `style="opacity: 0; transform: translateY(…)"` as the initial state; under `prefers-reduced-motion: reduce` the reveal animation never fires (transition is `1e-06s` but the trigger is gated). Verified on Pipeline (`<h3>No entries yet</h3>` + empty-state copy at computed opacity 0) and on Chat right after the wizard's *Finish and open chat*. Fix: audit every `whileInView` / motion-style reveal in `apps/metis-web` and ensure the final state is unconditionally applied when `useReducedMotion()` is true (no opacity-0 starting state). This is the dominant source of "lag in many places" the user reported.
2. **First-run banner on `/`.** A fresh user with `basic_wizard_completed=false` lands on the constellation home with no hint setup is needed — `/` is exempted in [`components/setup-guard.tsx`](../apps/metis-web/components/setup-guard.tsx) (see `allowedBeforeSetup`). Add a dismissible banner on `app/page.tsx` when `basic_wizard_completed` is false, linking to `/setup`. Don't drop `/` from the guard — that would trap the user from exploring.
3. **"DIRECT CHAT READY" badge.** The wizard Step 5 launch summary shows the green badge even when no API key was provided. Gate the badge on (provider has a credential) AND (provider !== `mock`).
4. **Mock fallback masquerades as a real reply.** `[Mock/Test Backend] / Short answer: Local mock backend executed successfully…` is rendered styled like an answer in the chat bubble. Either (a) when provider is `mock` or no key configured, return a structured client-side error card ("No model provider is configured — set one up in Settings") instead of a mock-answer, or (b) keep mock for dev but gate it behind a dev flag so production never hits it. Likely touches `metis_app/api_litestar/routes/query.py` and the chat client renderer.

### Phase 2 — P1 visual / sprite (~1 day)

5. **Lens-flare ring on the gold "+" New Chat button** (bottom-right of `/`). Hard blue-white circular halo around a warm-gold star — clashes with everything else. Replace with a soft glow.
6. **METIS sprite anchor misalignment.** At max in-app zoom (2000×) the inner core dot is offset down-and-right of the outer halo ring; rays emanate from yet a third center. Make all three layers share one anchor in the renderer.
7. **Canvas DPR mismatch.** 1920×855 internal canvas CSS-stretched larger → aliased rays/connector lines at every zoom. `canvas.width = clientWidth * devicePixelRatio` with proper `ctx.scale`.
8. **Three sparkle/star icons on home** with totally different actions (purple "+" = thread search, gold "+" bottom-right = New Chat, gold sparkle top-right = spectral filter toggle). Different shapes (magnifier / plus-bubble / sliders) + `aria-label` + tooltip on each.
9. **Magnitude slider overflow.** Bounding rect reported at x=1591 in a 1568-wide viewport (default Chrome window). Fix the panel flex/overflow so it stays inside the viewport.

### Phase 3 — P1 perf / network (~1 day)

10. **Per-mount API fan-out dedupe.** A single chat send fires `/v1/assistant` x3, `/v1/seedling/status` x3, `/v1/settings` x4, `/v1/sessions` x2 within seconds. Almost certainly multiple React effects / hooks racing on mount. Coalesce at the hook layer.
11. **31.5-second long-poll connections** held open by `/v1/comets/active` (two parallel) and `/v1/comets/events?poll_seconds=10`. Verify intentional; if so, debounce/coalesce so we don't have two parallel poll loops; if not, kill.
12. **Blocked URL with query-string data.** A 404 was blocked by Chrome with `[BLOCKED: Cookie/query string data]` during a chat send — possible PII in URL params. Reproduce, identify the call, move data to body / scrub. If confirmed PII-in-URL: also flag in the M17 plan doc as a network-audit item.

### Phase 4 — P2 information architecture (~half-day)

13. **Nav inconsistency.** Home renders `Chat / Settings`; every other page renders `Home / Chat / Settings / Diagnostics / Pipeline`. Unify: same items on every page.
14. **Diagnostics in primary nav.** It's a dev/ops surface; move into a footer or a Settings sub-section.
15. **Forecast feature is implicit.** Settings has `Forecast (TimesFM)` defaults but Chat's path toggle only shows `Direct / RAG`. Either expose Forecast in the path toggle or remove the orphan settings.
16. **Companion overlay default state.** Currently opens by default on every page and covers the right pane on Chat (Sources panel). Default to collapsed pill; user opens on demand.

### Phase 5 — P2 onboarding / copy (multi-day)

17. **Setup wizard copy compression.** Each step has hero card + eyebrow + H1 + body + step tabs + step number + step heading + step subhead + body + card descriptions + `WHAT THIS UNLOCKS` sidebar that often duplicates the body. Cut to: one short paragraph per step. Drop the `WHAT THIS UNLOCKS` sidebar (or move into a per-step tooltip).
18. **Step tabs truncated** ("1. Choose the primary model …", "2. Add credentials only if l…"). Either give each step a 2–3 word label or expand the tab strip's width.
19. **Wizard heading voice.** "Choose how I should embed documents", "Add credentials only if I need them" — first-person from the AI. Neutralize: "Choose your embedding provider", "Provide an API key (optional)".
20. **Default selections in the wizard cause silent mismatches.** Anthropic preselected at step 1, OpenAI preselected at step 3 for embeddings — combo requires both keys but neither is required to proceed. Either pre-select once consistently (Anthropic LLM + Voyage/local embeddings, or OpenAI both) or surface the mismatch at Step 5 with a warning.
21. **Chat toolbar jargon.** `Agentic off`, `Heretic`, `mock / mock`, `Evidence Pack`, `local_gguf` need `title=` tooltips at minimum. Optional small "?" glossary popover.
22. **Astronomy metaphor untranslated.** Faculty Sigil, Stellar Identity, Spectral Class M7 V, Magnitude ≤ 6.5, halo/rim/core/accent palette, "Main sequence" — add tooltip + glossary. The metaphor is a vision pillar (Cosmos), not optional, but it needs translation for non-astronomers.
23. **"Discover everything"** hero copy currently only paints after a click. Make it visible on first paint.

### Phase 6 — P3 minor (patch)

24. **"Export PPTX"** button is visible on Chat → Sources panel even when "No sources yet." Gate the button on `sources.length > 0`.

### How to attack this

- One agent claims the M01 row when starting the audit work; otherwise it stays Rolling.
- Land Phase 1 as 4 small PRs (one per item) — these unblock first-time users and should ship before anything else.
- Phase 2 / 3 / 4 / 6 are visual / perf / IA / patch and can land in parallel small PRs.
- Phase 5 is the largest by line-count; consider landing 17–22 (copy/wizard) in one PR and 23 in a separate PR.

### What's *not* in this audit

- Item 5 from the IDEAS entry (UI-editable API keys) is **parked** — it's a posture decision (settings.json-only credentials) that should be made alongside the parked telemetry posture decision (2026-04-18) and M17 Phase 8.
- Item 19 from the IDEAS entry (home FCP 696ms) is **parked** — not user-blocking.
- Item 18 from the IDEAS entry (the blocked URL with query-string data) is in this list as Phase 3 item 12, but is **also flagged for M17** if a real PII leak is confirmed.

---

## 2026-04-25 — UI/UX skill-pass refinements

A second walkthrough was run with the `ui-ux-pro-max` skill applied and the user's design constraints (noob-friendly plug-and-play, no whitespace expansion — the cosmos backdrop *is* the negative space, retain functional toggles but reorganize/hide for default users, simplify the three home-page sparkle icons preferring the gold bottom-right styling, de-emphasize Diagnostics, replace text-heavy "Seedling heartbeat" with GSAP-driven visual signal, clarify or remove Pipeline, kill filler copy, restore procedurally-generated prompt suggestions). The recommendations below either **refine** existing audit items or **add net-new** ones.

Recommended design system (from `ui-ux-pro-max --design-system`): **Minimal Single Column / Single CTA focus** pattern, **Exaggerated Minimalism** style (bold contrast, oversized type, negative space supplied by the cosmos backdrop — *not* literal padding). Adopt `#22C55E` as the active/CTA accent (replacing the cyan/teal currently used) for "go / ready" semantics. Typography stays compatible with current Fira-family pairing.

### Refinement of audit item 8 (three-sparkle disambiguation) → unified gold FAB

Subsume the purple "+" (semantic search), gold "+" bottom-right (new chat), and gold sparkle top-right (filter panel toggle) into **one gold FAB** styled like the current bottom-right button (user feedback: "looks the best") with the lens-flare ring removed (already audit item 5). On click, GSAP `stagger`-animates 3 satellite buttons outward in a short arc (~200ms total): magnifier (search), sliders (filters), paper-plane (new chat). Outside-click `reverse`-animates the collapse. Satellites overlay the canvas — no layout shift. This subsumes audit items 5 (lens flare) and 8 (three icons) into a single PR.

### Refinement of audit item 23 (chat empty state) → procedural prompt chips + restored generator

`STARTER_PROMPTS_DIRECT` / `STARTER_PROMPTS_WITH_INDEX` in [`apps/metis-web/app/setup/page.tsx:133`](../apps/metis-web/app/setup/page.tsx) are hardcoded. The chat empty state at [`apps/metis-web/components/chat/chat-panel.tsx:681`](../apps/metis-web/components/chat/chat-panel.tsx) shows a static H3 + paragraph. Replace both with **procedurally-generated prompt chips** (4–6) that float just above the composer when message list is empty. Generator inputs in priority order:

1. Indexed-doc titles (if any) — e.g. "Summarize the key claims in $title".
2. Recent comet topics from `/v1/comets/active`.
3. Time-of-day / first-session vs returning-user templated openers.
4. Fallback to the current 3 static prompts if nothing else available.

Click chip → stages prompt in composer (no auto-send). The chip strip *is* the empty state — no separate H3 needed. Kills the filler copy "Start with a question that feels specific" entirely.

### Refinement of audit item 14 (Diagnostics) + new Pipeline decision

- **Diagnostics**: out of primary nav. Reachable via `Settings → Diagnostics & logs` or `Cmd+Shift+D` shortcut. Redesign even the advanced view to a single status card with progressive disclosure:
  ```
  🟢 All systems healthy · 3 versions matched · 0 errors in last 100 lines
  [ Show details ▾ ]
  ```
  Don't open as the version cards + JSON dump + log tail it currently is.
- **Pipeline**: user noted purpose is unclear. Two options:
  1. **Recommended:** rename to `Research log` and tie content to seedling/comet activity ("watch what your companion has been working on") — gives clear value prop tied to a vision pillar.
  2. Remove from primary nav; surface inside Settings → "Improvement log" only.

### Refinement of M13 jargon item → ambient seedling widget (GSAP)

`/v1/seedling/status` returns `{ running, last_tick_at, next_action_at, current_stage, queue_depth, activity_events[] }` — currently the UI throws all of this away as 6× repeated text "Seedling heartbeat". Replace with a small (~80×80px) ambient widget anchored top-right of home (or as a faint orbiting satellite around the central METIS sprite):

- **Pulse ring**: `gsap.to(ring, { scale: 1.2, opacity: 0, duration: tickPeriod, repeat: -1, yoyo: true })` synced to `next_action_at - last_tick_at`. The user *sees* the heartbeat instead of reading the word.
- **Stage indicator**: outer arc fills as `seedling → sapling → bloom → elder`. Single visual conveys lifecycle.
- **Queue depth**: 1 small orbiting dot per queued item; empty when idle.
- **Activity event**: brief comet-streak GSAP tween from off-screen edge → seedling, ending in a flash on absorption.
- **Hover**: tooltip "Last check 2 min ago · Next in 58s · 0 in queue".
- **Click**: opens the existing detailed Companion overlay (advanced surface preserved for power users).

The 6 unlabeled action buttons (Pause / Reflect Now / Clear Recent / Refresh / Research Now / Auto-research) move into a `⋯` more-menu inside the expanded overlay. **Auto-research defaults OFF** (currently silently ON without consent — privacy/expectation issue).

This subsumes the M13 plan's jargon-translation item; refine the M13 plan note to reference this design.

### NEW — Net-new findings from this pass

35. **`anthropic / mock` toolbar pill is a non-clickable label** disguised as a button (no `onclick`/`href`, identical styling to clickable pills around it). Either make it open the Change-Model modal or restyle as plain text so it stops looking interactive.
36. **Change-Model modal: Provider and Model are free-text inputs**, no curated dropdown, no validation. Replace with a select/combobox of supported providers; model dropdown should be filtered by selected provider.
37. **`Use Browser (WebGPU) — Runs Bonsai 1.7B entirely in your browser — no API key needed`** is buried inside the "Change Model" modal. This is the literal **plug-and-play** path. Promote it to the wizard's **Step 1 first option** as a binary fork:
    ```
    Welcome to METIS

    ┌────────────────────────┐  ┌────────────────────────┐
    │  ✨ Try it instantly   │  │  ⚙  Use my own model   │
    │  Browser-only model    │  │  Anthropic / OpenAI    │
    │  No setup, no key      │  │  or local GGUF         │
    │  [ Get started ]       │  │  [ Configure ]         │
    └────────────────────────┘  └────────────────────────┘
    ```
    Left card → straight into chat with WebGPU/Bonsai loaded. **Zero further wizard steps for the default user**. Right card → the existing 5-step flow (which still gets the copy compression + voice neutralization from Phase 5). This is the single highest-leverage change for "noob friendly" — most users land in chat in one click with a working model.
38. **Heretic = "Uncensored mode"** (user clarification: it *is* a key feature, don't bury it). Don't move to deep settings; instead **rename in chat-toolbar UI** from `Heretic` (implementation/CLI tool name) to a user-facing label like **Uncensored mode** or icon + tooltip. Keep visible since it's a core differentiator.
39. **Clicking empty space on the constellation canvas silently creates a new star** (toast: *"Star added and linked into the selected constellation branch"*). Irreversible content modification from a casual click — surprise factor for any new user clicking around to explore. Wire star-creation to its own dedicated mode: the SELECT/HAND bottom toolbar already exists; add a third "+ Add star" mode and only allow canvas-click creation when that mode is active.
40. **File-attachment icon is misleading.** Generic-looking icon next to send button only accepts `.csv,.tsv` for forecasting (`accept=".csv,.tsv"`, aria-label *"Attach time series data"*, title *"Attach CSV/TSV to forecast"*). New users will assume general document upload. Either: (a) change the icon to a chart-line/sparkline glyph, (b) replace the placeholder hint to be more specific than "Ask anything, or attach a CSV/TSV to forecast", (c) split into two affordances if document upload becomes a feature.
41. **Auto-research defaults ON** in Companion overlay. METIS does background research without explicit user consent on first run. Privacy/expectation issue. Default OFF and prompt user post-onboarding ("Want METIS to keep researching topics it sees in your activity?").
42. **Outline tab is empty placeholder** ("Outline will show the structure of the current conversation."). Either implement or hide until ready.
43. **Trace tab shows raw dev events** (`Synthesis / final / artifact_boundary_flag_state / artifact_render_fallback_markdown`). Hide for first-run; reveal only after `Developer mode` toggle in Settings.
44. **Companion overlay copy uses third-person voice** ("METIS welcomed the user and prepared a lightweight local companion flow"). Switch to first-person ("I've prepared a lightweight local flow — you can chat as soon as you're ready") or fully neutral.
45. **Toolbar progressive disclosure**. Default chat toolbar collapses to: `[Direct▸RAG] · Bonsai 1.7B (browser) · ⋯` — behind the `⋯` menu: Change model, Agentic mode, Uncensored mode (Heretic, renamed), System instructions, Conversation settings. Power users pin items back to toolbar via menu setting if desired.
46. **The Heretic toolbar pill's `href` triggers a `[BLOCKED: Cookie/query string data]` block** in Chrome — second confirmation of the PII-in-URL issue from existing audit item 12. The pill links to `/settings/?tab=models&modelsTab=heretic` which Chrome's tracking protection flags. Move state to body / scrub.

### Phase mapping for these refinements

| New/refined | Phase in this plan |
|---|---|
| 35 (anthropic/mock label) | Phase 1 (P0 — directly visible chat affordance lying about being clickable) |
| 36 (free-text provider/model inputs) | Phase 1 (P0 — first-time-user trap) |
| 37 (WebGPU wizard fork) | Phase 1 (P0 — biggest single noob-friendly win) |
| 38 (Heretic → Uncensored rename) | Phase 2 (visual/copy) |
| 39 (canvas-click creates star) | Phase 1 (P0 — surprise content modification) |
| 40 (CSV-only attach icon) | Phase 2 |
| 41 (Auto-research defaults OFF) | Phase 1 (P0 — privacy expectation) |
| 42 (Outline tab) | Phase 4 (IA — hide until implemented) |
| 43 (Trace tab developer mode) | Phase 4 |
| 44 (overlay third-person voice) | Phase 5 (copy) |
| 45 (toolbar progressive disclosure) | Phase 4 |
| 46 (Heretic href PII block) | Phase 3 (already item 12 — same investigation) |
| Refinement of item 8 → unified FAB | Phase 2 (replaces existing item 8 spec) |
| Refinement of item 23 → procedural chips | Phase 5 (replaces existing item 23 spec) |
| Refinement of item 14 → Diagnostics tucked behind shortcut + Pipeline rename | Phase 4 (replaces existing item 14 spec, adds Pipeline decision) |
| Refinement of M13 item → GSAP seedling widget | M13 plan note (already merged; update to reference this design) |

### NEW — Settings deep-dive findings

47. **Memory tab — Recursive memory defaults OFF.** "Persist and recall prior conversation context across sessions" — this is a flagship "your AI grows with you" feature and is **directly contradicted by being off by default**. Default ON, or surface in the wizard as part of the WebGPU plug-and-play fork.
48. **Companion tab — Archetype defaults to "Clippy-style research companion".** Self-deprecating joke serialized into the assistant's prompt seed. Replace with on-brand default ("Local-first research companion" / "Companion").
49. **Privacy & network audit is buried 3 clicks deep** but is the strongest local-first selling point in the product (live outbound-call audit, airplane mode toggle, per-provider allow/block matrix, 0-call counter). Promote: small status pill in the home/chat header — `🟢 0 outbound calls · airplane off` — clickable to open the panel. Aligns with M17 Network Audit milestone work.
50. **Privacy panel cross-references settings by raw key name** ("Controlled by `autonomous_research_enabled` in other settings"). Replace with a clickable link that deep-links to that setting; never expose raw keys to the user.
51. **`?tab=retrieval` query param doesn't deep-link to the Retrieval tab** — page loads with Core selected. Tab state is local-only, not URL-synced. Breaks bookmarking and sharing of specific tabs.
52. **"Save settings" button is at the top of the form**, between the tab strip and the field grid. Users scroll through dozens of fields, modify, then have to scroll back up to save. Move to bottom (or make it sticky on a footer bar).
53. **Companion overlay covers the right pane on every page** including Privacy & network audit. Same persistence problem as Chat. Default-collapsed across the whole app would solve it. (Already implied by audit item 16 — flagging the cross-page recurrence.)

Phase mapping: items 47, 48, 49 are **Phase 1 / 2** (high-impact noob-friendly + brand-aligned). Items 50, 51, 52 are **Phase 4** (IA polish). Item 53 is already covered by audit item 16.
