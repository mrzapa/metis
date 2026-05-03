# Constellation IA Reset — Design (M24 + M25 + M26)

**Date:** 2026-05-03
**Author:** claude/constellation-ia-intake
**Vision pillars:** Cosmos (🌌), Cortex (🧠), Companion (🌱) — cross-cutting
**Source intake:** [`plans/IDEAS.md` → *Constellation IA reset*](../../plans/IDEAS.md). Direct user critique 2026-05-03.

## Why this exists

VISION's Cosmos pillar opens with: *"Stars are placed by faculty (Perception, Knowledge, Memory, Reasoning, Skills, Strategy, Personality, Values)."* That sentence is **false on multiple counts**, and the user's critique on 2026-05-03 surfaces why:

1. **The taxonomy is unstable.** VISION lists 8 faculties; `metis_app/services/autonomous_research_service.py:24` ships **11** (`synthesis`, `autonomy`, `emergence` added). The reverse-curriculum signal (M04) and the companion's poetic copy (`star_nourishment_gen.py:112-138`) reference faculty by name with these 11 — but the canvas (`app/page.tsx:176`) is anchored on the original 8. The user's mental model and the runtime model disagree about what faculty even *is*.
2. **The user can't reason about the AI's curriculum.** When METIS researches autonomously, it picks "the sparsest faculty" — but `personality` vs `synthesis` vs `emergence` don't map to how anyone organises their knowledge. The user explicitly said they "struggled to see the use case." When the user can't see why their constellation is shaped a certain way, the constellation is decorative — not a navigation primitive.
3. **M21 Phase 5 already half-removed it.** Faculty title text was removed from the canvas, the central-star lens flare was removed, the classical-name hover was silenced. The user is saying that wasn't enough — go further on the underlying anchor concept, not just the surface paint.
4. **Competitor parity demands a Project primitive.** ChatGPT Projects and Claude Projects are now the dominant vocabulary for "scoped chat workspace." Metis has no equivalent. The constellation has the *visual* shape ("draw a line between stars to scope a chat") but no plumbing.

The user's request is best read as: replace the faculty-as-organising-metaphor with a content-first IA, add a Project primitive, give the central METIS star a job (Everything chat), and stop pretending the constellation is shaped by abstract cognitive architecture.

## What this is not

- **Not** ripping the constellation. The starfield, the M-star brand, the comets, the archetype system from ADR 0006, the Star Observatory dialog — all survive. What changes is *how stars are placed* and *what the ring labels say*.
- **Not** killing the companion dock. The dock remains the canonical companion-chat surface. The new central-star Everything chat is *RAG over all stars* — different surface, different job.
- **Not** a single milestone. Three milestones (M24, M25, M26) land the trajectory in stages.
- **Not** an immediate backend purge. The faculty taxonomy stays as an *invisible internal* signal until M26 replaces it with a content-cluster signal that's been validated against M16 evals.
- **Not** a competitor clone. Projects in Metis are *saved selections over stars*, not a separate file workspace (per Q4a decision). Lighter than ChatGPT/Claude Projects; fits Metis's star-as-content model.

## Decisions and rationale

| # | Decision | Rationale |
|---|---|---|
| 1 | **B-trajectory, staged across M24/M25/M26.** Faculty is gone end-to-end at the destination, but staged so each milestone is independently shippable and the backend curriculum signal isn't replaced before its replacement is validated against evals. | M04 reverse curriculum is real engineering and works. Replacing the signal it operates on without eval validation risks regression. M16 builds the eval harness; M26 uses it as the validation gate. |
| 2 | **Star placement = embedding clusters with Project pull (Q2 option D).** Day-1 = AI-clustered embedding-projection layout. As Projects accumulate, force-directed layout pulls Project members together. Both signals feed the curriculum (cluster gaps + Project gaps). | A alone has no user-controlled organisation; B alone has a cold-start problem (new users have no Projects). D is the combo: works on day 1, honours user intent as it accumulates. |
| 3 | **Add flow = file-picker → AI-suggested top-5 stars + "Create new" (Q3 D+1).** AI ranks suggestions by content fingerprint similarity, with same-Project stars boosted, with content-type as a soft tiebreak. "Create new star" is always offered side-by-side. | Threshold-gated approaches hide one of the two correct answers when the AI's similarity score is uncertain — and on small datasets, similarity scores are *often* uncertain. Side-by-side keeps the user in control. |
| 4 | **Project = saved selection over star IDs (Q4a A).** Lightweight: name + member-star-IDs + per-project instructions + per-project chat history. No content duplication. Chat inside a Project filters retrieval to those stars' indexes only. | Stars already own indexes and content. A Project that *also* owns content creates the "where did I upload this — to the star or the project?" cognitive cost. Saved-selection-over-stars preserves the star-as-knowledge metaphor. |
| 5 | **Project UX = click-to-select with pulse + Confirm (Q4b user clarification).** Click star A → glows + pulses. Click star B → also selected. Hit Confirm → Project created. Glowing line/rope renders connecting members **after** confirm — the line is the *result*, not the gesture. | User explicitly asked for click-then-click-then-confirm rather than drag-to-draw. Drag-a-line scales badly past 2 stars; click-to-select handles N stars naturally. |
| 6 | **Central METIS star = Everything chat only (Q5a 1).** Click central star → chat scoped to all stars' content (RAG over the union of all attached indexes). The companion-chat surface stays in the dock. No mode toggle inside the chat. | The dock already has companion chat (WebGPU local model). Adding a Companion-mode toggle to the central star duplicates the surface. Each surface gets one job: dock = pure companion conversation; central star = everything-RAG; Projects = scoped RAG. |
| 7 | **Per-Project Forge config (Q5b B).** Each Project owns its Forge state — which techniques are enabled, which model, which mode. Projects inherit globals at create time; can override per-Project after. | Projects-as-scopes is meaningless if technique config is global. The whole point of "this Project is for my thesis" is that the Project gets its own *behaviour* — closer to Claude Projects' per-project system prompts. |
| 8 | **Faculty stays as internal-only backend signal until M26.** M24 + M25 ship without touching `comet_decision_engine`, `autonomous_research_service`, Tribev2 classifier, or `star_nourishment_gen`. Faculty IDs continue flowing through those pipelines invisibly. | Decoupling the visible-purge from the backend-purge protects two things: M04 reverse curriculum keeps working (no eval regression), and the M24+M25 ship can be scoped to ~6 weeks instead of ~10. |
| 9 | **ADR 0019 written before M24 starts.** Documents the IA pivot, marks ADR 0006 partially superseded (faculty-anchor decision specifically; archetype + tiered-naming policy survive). | Without an ADR, future agents will rebuild what's removed. The faculty system has been recreated twice already (8→11 faculties between VISION and runtime); explicit deprecation is required. |
| 10 | **VISION.md amended.** Cosmos pillar paragraph rewritten ("stars are placed by *content*"); "How an AI grows" gets the Projects loop added. | The pillar narrative is the agent onboarding signal. Leaving "stars are placed by faculty" in VISION.md while M24 ships is a contradiction every new agent will trip over. |

## Cross-milestone architecture

Three milestones, sequenced. Each is independently shippable.

```
                  ┌────────────────────────────────────────────────┐
                  │  M24 — Faculty UI purge + content-first IA     │
                  │  (~2 weeks)                                    │
                  ├────────────────────────────────────────────────┤
                  │  • Drop FACULTY_CONCEPTS / faculty ring on     │
                  │    canvas                                       │
                  │  • New embedding-cluster placement engine      │
                  │  • New Add flow (file picker → AI suggests)    │
                  │  • Central-star = Everything chat              │
                  │  • Faculty backend stays — invisible internal  │
                  └────────────────────────────────────────────────┘
                                       │
                                       ▼
                  ┌────────────────────────────────────────────────┐
                  │  M25 — Projects + Forge integration            │
                  │  (~2–4 weeks)                                  │
                  ├────────────────────────────────────────────────┤
                  │  • Project data model (saved selection)        │
                  │  • Click-to-select-then-confirm UX             │
                  │  • Glowing-line rendering for member links     │
                  │  • Per-Project Forge config                    │
                  │  • Project chat (filtered RAG)                 │
                  │  • Force-directed pull on cluster placement    │
                  └────────────────────────────────────────────────┘
                                       │
                                       ▼
                  ┌────────────────────────────────────────────────┐
                  │  M26 — Backend faculty taxonomy removal        │
                  │  (~3–4 weeks)                                  │
                  ├────────────────────────────────────────────────┤
                  │  • comet_decision_engine: faculty → cluster    │
                  │  • autonomous_research: faculty → cluster      │
                  │  • Tribev2 classifier output: faculty → cluster│
                  │  • star_nourishment: faculty → cluster         │
                  │  • M04 reverse curriculum re-validated         │
                  │  • M16 evals as gating harness                 │
                  └────────────────────────────────────────────────┘
```

**Cross-cutting deliverables (write before M24 starts):**

- **ADR 0019 — Constellation IA: content-first, drawable Projects.** Marks ADR 0006's faculty-anchor decision partially superseded.
- **VISION.md amendment.** Cosmos pillar paragraph rewritten; "How an AI grows" gets Projects.
- **`plans/IMPLEMENTATION.md` rows for M24, M25, M26.** With Status: Ready (M24), Draft (M25), Draft (M26).

---

## M24 — Faculty UI purge + content-first IA + Add flow + Everything chat

### Goal

Replace the faculty-anchored canvas with embedding-cluster placement; replace the Star-Observatory-as-Add-flow with a file-picker → AI-suggested-stars flow; give the central METIS star a real job (Everything chat). Backend faculty signal untouched.

### Architecture

Five surfaces:

1. **Canvas placement (`apps/metis-web/app/page.tsx`)** — `FACULTY_CONCEPTS` / faculty-ring rendering replaced with cluster-projection rendering. Stars positioned by their (precomputed) cluster centroid + within-cluster offset.
2. **Star Observatory dialog (`components/constellation/star-observatory-dialog.tsx`)** — `faculty-glyph-panel` removed. Stellar Identity / archetype / spectral class survive (per ADR 0006). Tier 1 / 2 of the dialog cleaned up.
3. **Add flow (`apps/metis-web/components/home/add-star-dialog.tsx`, new)** — replaces the existing `+ ADD` button's current behaviour. New file-picker dialog → embedding → top-5 ranked existing stars + "Create new" → confirm.
4. **Central METIS star (`apps/metis-web/app/page.tsx` — `drawPolarisMetis` and click-handling)** — currently visually decorative post-M21. Now becomes a clickable surface that opens an "Everything chat" sheet.
5. **Everything chat surface (`apps/metis-web/components/home/everything-chat-sheet.tsx`, new)** — reuses chat panel components from `apps/metis-web/components/chat/`, scoped to a virtual all-stars-union index.

### Components (new)

Under `apps/metis-web/components/home/`:

- `add-star-dialog.tsx` — file picker + paste-text + AI-ranked suggestion list + Create-new option.
- `everything-chat-sheet.tsx` — slide-over sheet that hosts the existing `ChatPanel` against a virtual all-stars index.

Under `apps/metis-web/lib/`:

- `star-clustering.ts` — pure utility for k-means / HDBSCAN clustering over star content embeddings, with 2D projection (UMAP-lite or t-SNE-lite implementation, or wrapper around an existing browser-friendly library).
- `star-add-recommender.ts` — embeds incoming content, ranks existing stars by cosine similarity, applies Project boost (post-M25) and content-type tiebreak.

### Backend additions (minimal)

`metis_app/services/star_clustering_service.py` (new) — server-side clustering job that runs on demand and stores cluster IDs + 2D projection coordinates per star. Triggered:

- On first run after M24 deploys (full clustering pass over existing stars).
- On Add-star (incremental: place new star into nearest existing cluster, re-cluster if drift exceeds threshold).
- On user-triggered "Re-layout" action.

`GET /v1/stars/clusters` — returns the cluster assignment + 2D coords for every star.

`POST /v1/stars/:id/embedding` (new, internal) — generate or refresh a star's content embedding. Used by the Add recommender. (May reuse existing index-building embedding pipeline rather than a new endpoint — confirm during impl.)

### Data flow

**Canvas placement (on render):**

```
Page mounts → fetchStarClusters() → GET /v1/stars/clusters
  → returns [{star_id, cluster_id, x, y}]
  → drawNodes() places each star at its (x, y)
  → cluster-coloured halo by cluster_id (optional, for visual grouping)
```

**Add flow (on `+ ADD` click):**

```
User clicks +ADD → AddStarDialog opens
  → user selects file(s) / pastes text
  → frontend embeds content (via existing index-build flow OR a lightweight embedding endpoint)
  → POST /v1/stars/recommend with {content_embedding, content_type}
  → backend runs cosine similarity against existing star embeddings
  → backend boosts same-Project stars (post-M25; no-op for M24)
  → returns top-5 ranked candidates + a default "create new" suggestion
  → AddStarDialog displays candidates as a card-grid; user picks one
  → if existing: POST /v1/stars/:id/attach with the file/text content
  → if new:      POST /v1/stars with {content, suggested_name, suggested_archetype}
  → on success: refresh canvas (re-fetch clusters; new star animates into its cluster)
```

**Central-star Everything chat:**

```
User clicks central METIS star
  → EverythingChatSheet opens (slide-over)
  → ChatPanel mounts with virtual_index_id = "_all_stars"
  → on user message: backend dispatches RAG against the union of all star indexes
  → response streams back as usual
```

The "_all_stars" virtual index is **not** a new persisted index — it's a runtime concept. The retrieval pipeline takes a query and runs it against every attached index, then merges + re-ranks. New backend method `WorkspaceOrchestrator.run_everything_chat(...)` wraps this.

### Migration of existing user data

Existing user stars are placed by faculty in the current schema. M24 needs to migrate them to cluster-projected positions.

**Approach: derive on render, à la M02 Phase 8.5.** Cluster IDs and 2D coordinates are *not* persisted on `UserStar` — they're computed on-demand by the clustering service and cached. First render after M24 deploys triggers a one-time clustering pass; subsequent renders use the cache. New stars added thereafter trigger incremental updates.

**Cache invalidation:** if the user adds N stars (N to be tuned, ~5 candidate) since the last full pass, trigger a re-layout in the background. User-visible rationale: "Re-layout your constellation to reflect new content?" — surfaced as an optional notification, not a forced action.

**Faculty IDs on existing stars are preserved** in the persistence layer. They become invisible internals from the user's perspective.

### Error handling

- **Cluster service failure** — fall back to a deterministic "scattered grid" layout (each star gets a stable hash-based position). Toast: "Couldn't compute layout; showing default placement."
- **Add-recommender failure** — degrade to "Create new star" only; surface toast "Couldn't suggest matches; you can add to an existing star manually after."
- **Everything chat backend error** — same surface as existing `/chat` errors (already-mature in the chat panel).
- **Migration race** — if a star is added during an in-flight clustering pass, the new star gets a tentative position (nearest-neighbour to its embedding's closest existing star) and is corrected when the pass completes.

### Testing

**TDD mode: pragmatic** (matches M21 / M23 conventions).

**Backend pytest:**
- `tests/test_star_clustering_service.py` (new) — golden-data clustering test (5 sample embeddings → 2 clusters), incremental-add test, cache-staleness test.
- `tests/test_star_recommender.py` (new) — cosine ranking test, content-type tiebreak test.
- `tests/test_everything_chat.py` (new) — end-to-end virtual-all-stars retrieval test.

**Frontend vitest:**
- `add-star-dialog.test.tsx` — file-picker + paste-text + recommendation-display + create-new-fallback.
- `everything-chat-sheet.test.tsx` — sheet open/close + chat panel mount.
- `star-clustering.test.ts` — pure-utility unit tests for the projection helper.

**Browser preview verification (Phase 6 of M24):**
1. Load `/`; canvas renders cluster-grouped layout (no 8-faculty ring).
2. Click `+ ADD`; dialog opens; pick a file; see top-5 suggestions + Create-new; pick one; see the star animate into place.
3. Click central METIS star; Everything chat sheet opens; send a message; see RAG response.
4. Reload; layout persists.
5. With reduced-motion enabled, no regressions.

### Phasing (M24)

Six phases, ~2 weeks total.

| # | Phase | Scope | Est. |
|---|---|---|---|
| 1 | Backend: clustering service | `star_clustering_service.py` + `GET /v1/stars/clusters` + tests | ~2 days |
| 2 | Backend: Add recommender | `POST /v1/stars/recommend` + cosine ranking + tests | ~1 day |
| 3 | Frontend: cluster placement | Replace `FACULTY_CONCEPTS` rendering with cluster-projection rendering in `app/page.tsx` | ~3 days |
| 4 | Frontend: Add flow | `AddStarDialog` + file picker + recommendation display + create-new fallback | ~3 days |
| 5 | Frontend: Everything chat | `EverythingChatSheet` + central-star click handler + virtual-all-stars retrieval wiring | ~2 days |
| 6 | Verify + observatory cleanup | Browser-preview QA; remove `faculty-glyph-panel`; clean up faculty references in copy across `/setup`, observatory dialog | ~2 days |

Phasing rationale: backend phases (1–2) ship without UI behind unchanged frontend — no risk to running users (faculty-anchored layout still renders until Phase 3). Frontend phases gate on backend landing. Phase 6 closes the user-visible cleanup.

### What survives M24 (do not touch)

- `StellarProfile` archetype system from ADR 0006.
- Tier 1 / Tier 2 / Tier 3 star naming policy from ADR 0006 (field stars unnamed, landmarks via classical names *kept on click only* per M21 Phase 5, user-content stars by user name).
- Star Observatory dialog's archetype picker, learning-route panel, attached-indexes management.
- Companion dock and all its existing companion-chat surfaces.
- Comet pipeline and news-comet visual rendering (M22 headline labels).
- Faculty IDs as invisible backend internals.

---

## M25 — Projects + Forge integration

### Goal

Add a Project primitive: user selects N stars by clicking, hits Confirm, gets a named scoped workspace with its own chat history, instructions, and Forge config. Projects are visualised as glowing connection lines on the canvas.

### Architecture

Three new surfaces:

1. **Project data model** — new `metis_app/models/project_types.py` (`Project` dataclass) + `metis_app/services/project_repository.py` (SQLite table + CRUD).
2. **Click-to-select UX** — selection-mode state in `app/page.tsx` + visual pulse on selected stars + floating Confirm button.
3. **Project chat surface** — extension of the existing `ChatPanel` that filters RAG retrieval to the Project's member stars.

Plus per-Project Forge config (lives on the Project record).

### Data model

```python
@dataclass(slots=True)
class Project:
    project_id: str
    created_at: str
    updated_at: str
    name: str
    member_star_ids: list[str]
    instructions: str = ""               # per-project system prompt
    forge_config: dict[str, Any] = ...   # per-project technique enablement
    color: str = ""                      # for line/halo rendering
```

SQLite schema:

```sql
CREATE TABLE projects (
  project_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  name TEXT NOT NULL,
  member_star_ids_json TEXT NOT NULL,
  instructions TEXT DEFAULT '',
  forge_config_json TEXT DEFAULT '{}',
  color TEXT DEFAULT ''
);
CREATE INDEX idx_projects_updated_at ON projects(updated_at DESC);
```

`ProjectRepository` methods:
- `list_projects() -> list[Project]`
- `get_project(project_id) -> Project | None`
- `create_project(name, member_star_ids, ...) -> Project`
- `update_project(project_id, **fields) -> Project`
- `delete_project(project_id) -> bool`
- `find_projects_for_star(star_id) -> list[Project]` — for Q3's same-Project boost in the recommender.

### HTTP routes

```
GET    /v1/projects                      → list
POST   /v1/projects                      → create
GET    /v1/projects/{id}                 → detail
PATCH  /v1/projects/{id}                 → update (name, instructions, forge_config, member_star_ids)
DELETE /v1/projects/{id}                 → delete
GET    /v1/projects/{id}/chat            → chat scoped to project
POST   /v1/projects/{id}/chat/messages   → message scoped to project
```

### UX flow

**Creating a Project:**

1. User clicks star A → `selectedStars` state adds A → A renders with pulsing halo (~1.5s loop).
2. User clicks star B → A and B both pulsing.
3. (User can click more stars or click an already-selected star to deselect.)
4. Once `selectedStars.length >= 1`, a floating action button appears bottom-centre: "Create Project from N stars".
5. User clicks the button → name dialog opens ("What's this Project for?" + optional instructions textarea).
6. On confirm → `POST /v1/projects` → backend creates row → frontend renders glowing line/rope connecting members.

**Editing a Project (post-create):**

- Click a Project's line → opens the Project's detail panel (or sheet) with member list + instructions + Forge config.
- "Add stars" button → enters selection mode again, scoped to this Project.
- "Remove star" → click an X next to the star in the member list.
- Force-directed layout updates: the cluster placement engine pulls members of the same Project together.

**Project chat:**

- From the Project detail panel: "Open chat" button → routes to `/chat?project=<id>` (or in-place sheet).
- Chat composer is the same surface as the existing `/chat`, but the retrieval filter is locked to the Project's member stars.
- Project's `instructions` are injected as the system prompt.
- Project's `forge_config` overrides the global Forge state for this chat.

### Visual rendering

**Project lines:**

- Cubic Bezier connecting member stars in a closed loop (or open polyline if only 2 members).
- Default colour: project's `color` field (auto-generated from project name hash for consistency).
- Stroke: ~1.5px, glow filter (~3px blur).
- On hover: thicker stroke + brighter halo.
- On click: opens project detail.

**Force-directed pull:**

- Each Project applies attractive force between member stars (k=0.05 per shared Project).
- Cluster placement engine (from M24) blends cluster-centroid pull with Project pull.
- Re-layout runs in background after Project create/edit.

### Per-Project Forge config

A Project's `forge_config` is a dict mirroring the global Forge state shape. Fields:

```ts
interface ProjectForgeConfig {
  iterrag_enabled?: boolean;
  iterrag_max_iterations?: number;
  swarm_enabled?: boolean;
  heretic_enabled?: boolean;
  // ... mirrors global Forge fields
}
```

Resolution rule (mirrors the M23 `tone_preset` resolver pattern):
- If a Project's `forge_config` has a key set, that value wins for chats inside the Project.
- If a key is absent, fall back to global Forge state.
- Empty dict = full inheritance from global.

UI for editing:
- Project detail panel has a "Forge" section that mirrors the global Forge surface (per-technique toggle + parameters).
- Each toggle has a tri-state: Inherit (global) / On / Off.
- Settings page shows global; Project detail shows per-Project overrides.

### Phasing (M25)

| # | Phase | Scope | Est. |
|---|---|---|---|
| 1 | Backend: Project schema + repo | `project_types.py` + `project_repository.py` + tests | ~2 days |
| 2 | Backend: Project routes + chat | `routes/projects.py` + project-scoped retrieval + tests | ~3 days |
| 3 | Frontend: select + confirm UX | Selection-mode state + pulse rendering + floating Confirm + create dialog | ~3 days |
| 4 | Frontend: line rendering + force pull | Cubic Bezier line drawing + force-directed pull integration with M24's cluster layout | ~3 days |
| 5 | Frontend: Project detail + chat | Detail panel + member management + Project-scoped chat sheet | ~3 days |
| 6 | Per-Project Forge | Project Forge UI section + resolution-rule wiring + tests | ~2 days |
| 7 | Recommender boost + verify | Wire same-Project boost into M24's `recommend` endpoint; browser-preview QA | ~1 day |

~2.5 weeks. Phase 7 retroactively connects M25 back to M24 — the recommender finally gets its Project boost (no-op until now).

### What survives M25

- M24's cluster-placement engine (Projects layer on top, don't replace).
- Global Forge surface (still authoritative for app-wide defaults).
- Existing `/chat` page and its session model (Project chat is a *scoped* variant, not a replacement).

---

## M26 — Backend faculty taxonomy removal

### Goal

Replace faculty-gap-scoring with content-cluster-gap-scoring across every backend pipeline that currently uses faculty IDs as a curriculum / decision signal. Validate with M16 evals before flipping.

### Pipelines affected

| File | Current behaviour | After M26 |
|---|---|---|
| `metis_app/services/autonomous_research_service.py` | Iterates `FACULTY_ORDER` (11 faculties), picks sparsest, formulates research query for that faculty | Iterates cluster IDs, picks sparsest cluster, formulates research query for that cluster's content theme (cluster's centroid keywords as the topic seed) |
| `metis_app/services/comet_decision_engine.py` | Scores news comets against per-faculty gap scores | Scores news comets against per-cluster gap scores; new comets are tagged with their nearest-cluster ID instead of faculty ID |
| `metis_app/models/star_nourishment.py` | `FacultyNourishment` per-faculty satiation; companion mood references faculty by name | `ClusterNourishment` per-cluster satiation; companion mood references cluster keywords ("the *Python performance* region is sparse, almost bare") |
| `metis_app/services/star_nourishment_gen.py` | Poetic copy templated with `{faculty}` substitution | Copy templated with `{cluster_label}` (auto-extracted from cluster centroid) |
| `metis_app/services/news_ingest_service.py` | Tags ingested news with classified `faculty_id` | Tags with classified nearest-`cluster_id` |
| `metis_app/services/news_feed_repository.py` | Schema includes `faculty_id` per news entry | Schema migrates to `cluster_id` (data migration: backfill from existing `faculty_id` via embedding-distance) |
| `metis_app/models/comet_event.py` | `CometEvent.faculty_id` field | Replaced with `cluster_id` (or both during transition) |
| `metis_app/services/brain_pass.py` | Per-faculty reflection passes | Per-cluster reflection passes |
| Tribev2 classifier (`metis_app/services/topo_scaffold.py` and friends) | Outputs faculty IDs from multimodal content | Outputs cluster assignments; classifier becomes "find nearest cluster centroid" |

### Eval validation strategy

M26 cannot ship blind — replacing the curriculum signal that M04 was tuned for risks regression in research quality.

**Gate:** before M26 lands, M16 evals must show the cluster-gap signal produces research quality at parity or better than faculty-gap signal on the same eval corpus.

**Eval shape (to be designed in M26 Phase 1):**
- Run autonomous research with both signals (A/B) on a fixed eval task corpus.
- Compare: relevance of researched docs to user's actual interests; coverage of user's content domains; companion-mood quality (poetic copy still readable, not jargony cluster IDs).
- If parity + readability holds, flip the signal. If not, iterate on the cluster signal (different clustering algorithm, different cluster-label generator) until parity.

### Phasing (M26)

| # | Phase | Scope | Est. |
|---|---|---|---|
| 1 | Eval design + harness | Define M26-specific eval tasks for curriculum signal comparison; wire into M16 store | ~3 days |
| 2 | Cluster-gap-scoring service | New `cluster_gap_service.py` + tests (parallel to existing faculty-gap path) | ~3 days |
| 3 | A/B run + validation | Run autonomous research with both signals; compare evals; iterate cluster signal until parity | ~5 days (variable) |
| 4 | Pipeline rewrites (per-table above) | One file at a time; each commit pairs the rewrite with a regression test | ~5 days |
| 5 | Schema migration | News-feed schema rename + backfill + tests | ~2 days |
| 6 | Tribev2 classifier rewire | Rewrite classifier output to cluster IDs; preserve existing model weights if possible | ~3 days |
| 7 | Companion copy migration | `star_nourishment_gen` template rewrite + cluster-label generator + tests | ~2 days |
| 8 | Final flip + cleanup | Delete `FACULTY_ORDER`, `FACULTY_DESCRIPTIONS`, faculty fields on data classes; pytest still green | ~1 day |

~3.5 weeks. Variable because Phase 3 may surface eval regressions that need iteration.

### What survives M26

Nothing in the faculty taxonomy. After M26, the codebase has *zero* references to faculty as a runtime concept.

But — `M02 plan doc`, `ADR 0006 addendum (M21 Phase 5)`, and the eventually-superseded `ADR 0006` itself remain as historical record. The git log preserves every renamed identifier; future archaeology is supported.

---

## Cross-cutting

### ADR 0019 — Constellation IA: content-first, drawable Projects

Drafted before M24 starts. Documents:

- Faculty-anchor decision (from ADR 0006 / M02) reversed.
- Archetype + tiered-naming policy from ADR 0006 preserved (specific carve-out).
- Cluster-projection placement is the new placement principle.
- Project = saved selection over star IDs (lightweight; not a separate workspace).
- Click-to-select-then-confirm is the canonical Project-creation UX.
- Per-Project Forge config is the per-Project behavioural override.
- Backend faculty signal staged for removal in M26 (not M24/M25).

ADR 0006 gets a new addendum: *"Faculty-anchor placement decision superseded by ADR 0019 (M24+). Archetype + naming-tier policy preserved."*

### VISION.md amendments

**Cosmos pillar paragraph** (line 26):

> Every document, paper, podcast, video, tweet, and note becomes a *star*. Stars are placed by **content** — clustered by what they're about, with intentional connections drawn by the user as **Projects**. Indexes become constellations. Live activity renders as comets. Individual stars open into a Star Observatory where you assign archetypes, plan learning routes, and link sources. The constellation is the primary navigation — not decoration.

**"How an AI grows" loop** (line 36) — add a new bullet:

> - **Group it.** Draw constellation lines between stars to create *Projects* — scoped workspaces with their own chat history, instructions, and technique config. Project chat sees only the Project's stars; Everything chat sees them all.

**Drop the faculty enumeration entirely** from the VISION pillar paragraph. The 8-faculty list ("Perception, Knowledge, Memory, Reasoning, Skills, Strategy, Personality, Values") is removed without replacement; the placement principle is "by content."

### Supersession status

- **M02 — Constellation 2D refactor (Landed):** the *faculty-anchor* sub-decision is superseded by M24+; the *archetype system* and *tiered-naming policy* survive.
- **ADR 0006 — Constellation Design (Accepted):** addendum added pointing to ADR 0019; faculty-anchor section marked Superseded.
- **M21 Phase 5 (Landed):** retroactively absorbed — its faculty-text-paint removal becomes a step on the path to M24's full purge.
- **M04 — Reverse curriculum (Landed):** logic preserved; signal source replaced in M26 (faculty IDs → cluster IDs).
- **M14 — Forge (Landed):** unchanged. Per-Project Forge in M25 layers *on top* of the global Forge; doesn't modify it.

---

## Out of scope, recorded

These are explicitly **not** in M24/M25/M26. Future agents: don't add them, even if they look small.

- **Multi-Project membership for chats.** A chat lives in zero or one Project (or the Everything chat). No "this chat references Projects A + B."
- **Project hierarchies / sub-Projects.** Projects are flat. No nesting.
- **Project sharing between users.** Local-first. No multi-user shared Projects.
- **Project templates / pre-set instructions.** Each Project is created blank; no template catalogue.
- **"Suggested Projects."** The AI doesn't propose new Projects. The user creates them by intent.
- **Cluster-naming UI.** Clusters get auto-generated labels (centroid keywords); no user-rename for cluster names. (Projects have user-given names; clusters don't.)
- **Faculty resurfacing under any other name.** If someone proposes "let's bring back the 11-faculty taxonomy as 'cognitive zones'" — no. Content-first is the trajectory.
- **The drag-to-draw line gesture.** User explicitly chose click-to-select-then-confirm. Drag-to-draw is rejected.
- **Companion-chat surface in the central star.** Stays in the dock. Don't add a Companion-mode toggle to Everything chat.

---

## Open questions for impl

Non-blocking; flag for the impl agent. Some get resolved in the impl plan; some surface during build.

1. **Clustering algorithm choice.** k-means is simple but requires a fixed `k`; HDBSCAN auto-discovers `k` but has more parameters to tune. Default for first ship: **HDBSCAN** with sensible parameters; revisit after Phase 1 eval data.

2. **2D projection algorithm.** UMAP is the gold standard but heavy. t-SNE is similar. **PCA** is cheap and good enough for 2D scatter; default to **PCA** for first ship, upgrade if cluster boundaries look bad.

3. **Cluster label generator.** "Centroid keywords" is hand-wavy. Concrete options: (a) extract top-10 TF-IDF terms from member content, (b) ask an LLM to summarize the cluster, (c) use the most-common content title bigram. Default: **a + b combined** — TF-IDF terms cheap-fast for fallback, LLM summary when available.

4. **Re-layout trigger threshold.** N stars added since last full pass before suggesting re-layout. Default: **5**. Tune based on observed user behaviour.

5. **Project chat retrieval scoping.** Filter at retrieval time (vector store filter by member-star-IDs) vs. build a virtual index. Default: **filter at retrieval time** — simpler, matches the "saved selection" data model.

6. **Force-directed layout convergence.** When does the layout stop iterating? Risk: thrashing as the user adds Projects rapidly. Default: **n=200 iterations** with early-stop if delta < threshold.

7. **Per-Project Forge inheritance UX.** Tri-state checkbox (Inherit / On / Off) is ugly. Alternatives: a "Reset to global default" link per technique; a settings-style "Override global" toggle that reveals the per-Project knob. Default: **Reset link** for first ship.

8. **What happens to the 8 named landmark constellations** (Perseus, Auriga, Draco, etc. with their classical Bayer names)? They're a leftover from the faculty era. M24 removes their classical naming surface from copy but the data layer keeps generating them — they're still referenced in `star-name-generator.ts`. Recommendation: **kill them in M24 Phase 6 cleanup**. They're decorative and the user critique cited them as "AI slop". Verify with the user before pulling the trigger.

9. **Migration for existing user data — opt-in or forced?** Cluster placement re-positions all existing user stars. Some users may have built mental geography around current faculty-anchored positions. Recommendation: **forced re-layout on first M24 visit** with a one-time "Your constellation has been re-laid-out by content. [Undo for this session]" toast. Undo restores faculty-anchored layout for the session only; the new layout becomes permanent on next visit. Discuss with user before locking.
