# 0019 — Constellation IA: content-first, drawable Projects

- **Status:** Accepted (M24 design 2026-05-03)
- **Date:** 2026-05-03
- **Supersedes (partially):** [ADR 0006](0006-constellation-design-2d-primary.md) — two sub-decisions are reversed: (1) the *faculty-anchor* placement decision; (2) the *landmark tier* of the tiered-naming policy. ADR 0006's archetype system and the field-star + user-content tiers of the naming policy are preserved.

## Context

ADR 0006 (M02, landed 2026-04-19) established that stars on the constellation home are placed by **faculty** — eight cognitive-architecture categories (Perception, Knowledge, Memory, Reasoning, Skills, Strategy, Personality, Values) anchored as named constellations on the canvas. Faculties also became a backend signal driving:

- M04 reverse-curriculum scoring (`metis_app/services/autonomous_research_service.py`)
- News-comet absorb decisions (`metis_app/services/comet_decision_engine.py`)
- Companion mood / poetic copy (`metis_app/services/star_nourishment_gen.py`)
- Tribev2 multimodal classifier output (`metis_app/services/topo_scaffold.py`)

A year of usage exposed three problems:

1. **Taxonomy instability.** VISION.md ships 8 faculties; runtime ships **11** (`autonomous_research_service.py:24` adds `synthesis`, `autonomy`, `emergence`). The mismatch persisted across multiple iterations without resolution — sign that the eight cognitive-architecture buckets weren't actually load-bearing.
2. **No user-visible value.** Direct user feedback 2026-05-03: *"we struggled to see the use case for them going forward."* The cognitive-architecture vocabulary doesn't map to how users organise their content; users think in projects and topics, not in faculties.
3. **M21 Phase 5 already half-removed it.** Faculty title text removed from canvas; central-star lens flare removed; classical-name hover silenced. The user's critique on 2026-05-03 was that the underlying anchor concept needed to follow.

A separate driver: **competitor parity demands a Project primitive**. ChatGPT Projects and Claude Projects are now the dominant vocabulary for "scoped chat workspace." Metis has the visual shape ("draw lines between stars") but no plumbing.

## Decision

The constellation goes **content-first**, with **Projects** as the user-visible organising primitive.

### Placement

Stars are placed by **content embedding clusters with Project-pull**:

- Each star's content is embedded with the existing embedding model.
- A clustering pass (HDBSCAN by default; PCA-projected to 2D) groups stars by content similarity.
- Cluster centroids determine canvas position; within-cluster offsets disambiguate stars in the same cluster.
- When Projects exist, force-directed layout pulls Project members together — Projects override cluster placement when the user has expressed intentional organisation.

Faculty IDs survive as **invisible internal signals** through M24 + M25, then are removed end-to-end in M26.

### Add flow

Click `+ ADD` opens a **file-picker / paste-text dialog**:

1. User uploads files or pastes text.
2. AI embeds the content and ranks the top 5 fingerprint-similar existing stars (with same-Project boost when applicable, plus content-type as a soft tiebreak).
3. UI displays the top 5 candidates **alongside** a "Create new star" option. User picks one.
4. Content attaches to the chosen star (or creates a new one).

Replaces today's flow where the user manually assigns archetype + faculty in the Star Observatory.

### Projects

A **Project** is a saved selection over star IDs:

- `name` + `member_star_ids[]` + `instructions` (per-project system prompt) + `forge_config` (per-project technique enablement) + `color`.
- No content duplication. No project-owned indexes. Chat inside a Project filters retrieval to the Project's stars.
- Per-Project Forge config layers on top of the global Forge state — Projects inherit globals at create time, can override per-Project after.

**Project-creation UX:** click-to-select-then-confirm.

1. Click star A → glows + pulses (selected state).
2. Click star B → also selected.
3. Floating Confirm button appears once `selectedStars.length >= 1`.
4. Confirm → name dialog → Project created.
5. After confirm, a glowing line/rope renders connecting the member stars. **The line is the result, not the gesture** — drag-to-draw is rejected.

### Central METIS star

Click central METIS star → **Everything chat** — RAG over the union of all star indexes. The everything-counterpoint to scoped Project chat.

The companion dock continues to host pure companion conversation (the WebGPU local model). No duplication; no mode toggle on the central-star surface.

## Because

- **Cognitive-architecture taxonomy doesn't earn its keep.** Users think in projects, topics, content domains. Faculty as an organising metaphor solved a problem nobody had.
- **Content embeddings are already in the system.** Every star has indexed content with embeddings. Clustering is a small additive pass on existing data — no new model, no new pipeline.
- **Projects map to existing competitor vocabulary.** Users coming from ChatGPT or Claude already have the mental model. Metis's "drawable constellation lines" gives the same primitive a *spatial* expression that no competitor has.
- **Click-to-select scales.** Drag-to-draw is intuitive for 2 stars but breaks down at N. Click-to-select-then-confirm handles N=2 and N=20 with the same gesture.
- **Per-Project Forge config matches Claude Projects' per-project instructions.** Projects without behaviour-scoping are weaker than Projects with.
- **The trajectory is staged for safety.** Replacing the M04 curriculum signal without eval validation risks regressing autonomous-research quality. M26 gates on M16 evals; M24 + M25 ship without touching the backend signal.
- **Faculty's absence in VISION needs to be true at the doc level.** Leaving "stars are placed by faculty" in VISION while M24 ships is a contradiction every new agent will trip over.

## Constraints

- Must preserve `StellarProfile` archetype system from ADR 0006 (content-type → visual archetype mapping).
- ADR 0006's tiered-naming policy is **partially** preserved: field stars stay unnamed; user-content stars stay named by the user. The **landmark tier is retired** in M24 Phase 6 — there are no more named-landmark constellations (Perseus, Auriga, Draco, Hercules, Gemini, Big Dipper, Lyra, Boötes), and `star-name-generator.ts`'s `kind: "landmark"` branch is removed. The user-content + field-star portions of the tiered policy survive unchanged.
- Must preserve Star Observatory dialog and its existing controls (archetype picker, learning-route panel, attached-indexes management).
- Must preserve the companion dock and all its existing companion-chat surfaces.
- Must work on mobile (single WebGL context preferred; Project lines render via canvas 2D overlay).
- Must not regress 60-FPS rendering of the 2D starfield.
- Must coexist with ADR 0004 (Next.js + Tauri + Litestar).
- Backend faculty signal stays as invisible internal through M24 + M25 — M04 reverse curriculum continues working unchanged.

## Alternatives Considered

- **Keep faculty UI but quieter.** Rejected — M21 Phase 5 already tried this. The user wants the underlying concept gone, not just the surface paint.
- **End-to-end faculty removal in a single milestone.** Rejected — too risky for M04 reverse curriculum; eval validation needed first. Staged across M24/M25/M26 with M16 evals as the M26 gate.
- **Keep faculty as a hidden internal *forever*** (Q1 option C from intake brainstorm). Rejected — leaves an 11-vs-8 mismatch and a dual codepath in perpetuity. Trajectory commits to full removal.
- **Project = pre-built virtual index** (Q4a option B). Rejected — duplicates content and adds refresh logic when member stars change. Saved-selection model is lighter and matches Metis's star-as-content metaphor.
- **Project = separate workspace with own uploads** (Q4a option C, ChatGPT Projects-style). Rejected — breaks Metis's "stars are the unit of knowledge" metaphor. Users would have to decide "do I upload to the star or the project?" — a cost the saved-selection model avoids.
- **Drag-to-draw line UX** (Q4b option 2). Rejected by user — click-to-select-then-confirm scales better past 2 stars and matches the user's stated preference.
- **Companion mode toggle on central-star chat** (Q5a option 3). Rejected — duplicates the companion dock, which is already the canonical companion-chat surface.

## Consequences

**Accepted:**

- M24 ships UI-only faculty purge: `FACULTY_CONCEPTS` and faculty-ring rendering removed from `app/page.tsx`; `faculty-glyph-panel` removed from Star Observatory; faculty references in copy purged across `/setup` and the observatory dialog.
- M24 ships content-embedding-cluster placement: new `star_clustering_service.py` backend + `GET /v1/stars/clusters` route + frontend cluster-projection rendering.
- M24 ships the new Add flow: new `AddStarDialog` + `POST /v1/stars/recommend` + create-new fallback.
- M24 ships central-star Everything chat: new `EverythingChatSheet` + virtual-all-stars-union retrieval.
- M25 ships Projects: new `Project` data model + `ProjectRepository` + 7 HTTP routes + click-to-select UX + glowing-line rendering + per-Project Forge config + Project chat surface.
- M26 ships backend faculty taxonomy removal: `comet_decision_engine`, `autonomous_research_service`, `star_nourishment_gen`, `news_ingest_service`, `news_feed_repository`, `comet_event` model, `brain_pass`, Tribev2 classifier — all rewired from faculty IDs to cluster IDs.
- M26 gates on M16 evals: cluster-gap-scoring must achieve research-quality parity with faculty-gap-scoring before the flip.
- VISION.md Cosmos pillar paragraph rewritten; "How an AI grows" gets the Projects loop.
- ADR 0006 receives an addendum pointing here; faculty-anchor section marked Superseded.
- M02 row in `IMPLEMENTATION.md` retains `Status: Landed` but its scope statement gains a "faculty-anchor decision superseded by ADR 0019" footnote.
- M21 Phase 5 retroactively absorbed as a step on the path to M24's full purge.

**Preserved:**

- `StellarProfile` archetype system, palette system, visual profiles, 2D shader family.
- The field-star and user-content tiers of ADR 0006's naming policy (field stars unnamed; user-content stars named by the user). The landmark tier is retired in M24 Phase 6 — see *Constraints*.
- Star Observatory dialog and controls.
- Companion dock and companion-chat surface.
- Comet pipeline and news-comet visual rendering (M22 headline labels).
- Forge global surface (still authoritative for app-wide defaults; per-Project layers on top).
- M04 reverse-curriculum logic (signal source replaced in M26; logic itself unchanged).

**Risks accepted:**

- Eval gate on M26 may surface signal regressions requiring iteration. Phasing accommodates this with variable Phase 3 length.
- Existing user stars get repositioned by the cluster engine on first M24 visit. Toast offers session-scoped undo; permanent layout is the new cluster-projected one.
- Companion poetic copy migration in M26 changes user-facing language. Keyword-extracted cluster labels may read more dryly than `personality` / `synthesis` / `emergence`. M26 Phase 7 invests specifically in copy quality.

## Open Questions

(See [`docs/plans/2026-05-03-constellation-ia-reset-design.md` → *Open questions for impl*](../plans/2026-05-03-constellation-ia-reset-design.md) for the full list. Highlights:)

- HDBSCAN vs k-means default; PCA vs UMAP for 2D projection.
- Cluster label generator algorithm (TF-IDF + LLM combined as a default).
- Re-layout trigger threshold (N stars added).
- Force-directed layout convergence criteria.
- Per-Project Forge inheritance UX (Reset-to-default vs tri-state).
- Existing user-data migration — forced vs opt-in (default: forced with session-scoped undo).
- ~~Whether to also retire the 8 named landmark constellations (Perseus, Auriga, etc.) in M24 Phase 6 cleanup.~~ **Resolved:** yes, retired. User confirmed during the 2026-05-03 brainstorm that landmarks read as decorative AI slop. The Constraints section above and the M24 Phase 6 plan-doc step both reflect this decision.
