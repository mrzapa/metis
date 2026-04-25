---
Milestone: Seedling + Feed (M13)
Status: In progress
Claim: claude/m13-adr-0013-runtime-pivot
Last updated: 2026-04-25 by Claude
Vision pillar: Companion
---

> **Coordinates with M17 (Network audit).** Every new stdlib outbound
> must go through `audited_urlopen` with a `trigger_feature` tag and
> `user_initiated=False`; new vendors register in `KNOWN_PROVIDERS`.
> Full contract: [`plans/network-audit/plan.md` → Coordination hooks (Phase 7)](../network-audit/plan.md#coordination-hooks-phase-7).

## Progress

*(milestone not started as a cohesive unit — this doc is the first real
plan pass. Significant adjacent scaffolding already exists in the repo
and should be harvested, not rebuilt. See the harvest list in *Notes
for the next agent*.)*

What's in place today that M13 will lean on:

- **Comet pipeline (news-comet v0)** — `metis_app/services/news_ingest_service.py`,
  `metis_app/services/comet_decision_engine.py`, `metis_app/models/comet_event.py`,
  `metis_app/api_litestar/routes/comets.py`. RSS / HackerNews / Reddit
  fetchers with size caps, failure backoff, a drift/approach/absorb
  decision engine, and six live HTTP routes under `/v1/comets/*`. Settings
  keys already shipped in `metis_app/default_settings.json`:
  `news_comets_enabled`, `news_comet_sources`, `news_comet_poll_interval_seconds`,
  `news_comet_max_active`, `news_comet_auto_absorb_threshold`,
  `news_comet_rss_feeds`, `news_comet_reddit_subs`. Feature is off by
  default; there is **no always-on background worker** driving it.
- **Companion service** — `metis_app/services/assistant_companion.py`
  (`AssistantCompanionService`) already owns identity bootstrap, a
  reflection loop with cooldown + dedup (`reflect()` at line 175),
  memory/playbook/brain-link repositories, and a nourishment model
  (`metis_app/models/star_nourishment.py`). This is the place the
  growth-stage machine hooks in.
- **Autonomous research pipeline (M09 landed)** —
  `metis_app/services/autonomous_research_service.py` already scans
  faculty gaps, does web research, synthesizes a document, and
  auto-indexes it as a new star. M09 wired `progress_cb` through to SSE
  and to `CompanionActivityEvent` on the frontend. M13 **extends** this,
  it does not duplicate it.
- **Companion dock UI** —
  `apps/metis-web/components/shell/metis-companion-dock.tsx` already
  renders a ring-buffer thought log fed by `subscribeCompanionActivity`.
  Growth-stage surfacing should land in this dock, not a new one.
- **Local GGUF runtime** — `metis_app/utils/llm_backends.py`
  (`LocalGGUFBackend`), `metis_app/services/local_model_registry.py`,
  `metis_app/services/local_llm_recommender.py`, and the web page at
  `apps/metis-web/app/gguf/`. The quantized-model *runtime* already
  exists; M13 has to pick the model, size the budget, and run it as a
  persistent background process — not re-implement `llama.cpp`
  integration.
- **Skill candidate capture (M06 scaffolding, M06 itself still Ready)** —
  `metis_app/services/skill_repository.py` has `save_candidate`,
  `list_candidates`, `mark_candidate_promoted` on a `skill_candidates.db`
  SQLite store (lines 326–381). The reflection cycle in M13 is the
  source that writes to this table.
- **2026-04-24 — Phase 1 complete.** ADR 0007
  (`docs/adr/0007-seedling-model-and-runtime.md`) selects
  Llama-3.2-1B-Instruct Q4_K_M as the default Seedling model, Qwen2.5-0.5B
  Q4_K_M as the low-memory fallback, and the existing in-process
  llama-cpp/GGUF path under Litestar lifecycle as the runtime. It rejects
  Phi-3.5-mini as the always-on default because it misses the <=2 GB resident
  target.
- **2026-04-24 — Phase 2 complete.** `metis_app/seedling/` now contains the
  lifecycle shell: a fixed-interval worker, status cache, startup/shutdown
  hooks, and a small in-process activity bridge. Litestar starts the worker
  on app startup, stops it on shutdown, and exposes `GET /v1/seedling/status`
  for liveness. The companion dock polls that heartbeat, shows the subtle
  Seedling indicator, and reuses the existing companion activity bus for
  Seedling lifecycle events. This phase is deliberately a no-op heartbeat:
  it does not load the GGUF model, ingest feeds, schedule research, or advance
  growth stages yet.
- **2026-04-25 — Phase 3 prep complete (ADR 0008).** ADR 0008
  (`docs/adr/0008-feed-storage-format.md`) locks the durable storage
  shape Phase 3 needs: a per-feature SQLite file at
  `<repo_root>/news_items.db` accessed through a new
  `metis_app/services/news_feed_repository.py`, with three tables
  (`news_items`, `comet_events`, `feed_cursors`), a 14-day rolling
  retention window over fetched items, terminal-comet eviction at 7
  days, persistent dedup keyed by the existing
  `NewsIngestService._item_hash`, and an OPML-import endpoint
  (`POST /v1/comets/opml/import`) that appends to the existing
  `news_comet_rss_feeds` setting. The ADR rejects extending
  `rag_sessions.db` or the Atlas store, and notes the shared lock /
  WAL posture so Phase 3 implementation does not re-litigate it.
- **2026-04-25 — Runtime pivot (ADR 0013, supersedes ADR 0007).** A
  re-audit found the in-browser **Bonsai-1.7B WebGPU** runtime
  (`apps/metis-web/lib/webgpu-companion/`) was already shipping as
  the de facto always-on companion model and missed by the original
  Phase 1 audit. ADR 0013
  (`docs/adr/0013-seedling-runtime-frontend-default.md`) inverts
  ADR 0007: Bonsai becomes the default Seedling reflection runtime,
  the in-process backend GGUF path becomes opt-in via the existing
  GGUF import flow, and METIS ships no default backend-model
  catalog entry as part of M13. Overnight reflection becomes an
  opt-in stretch tied to the backend toggle; the default Phase 4
  experience is *while-you-work* reflection driven by Bonsai. The
  Phase 2 lifecycle shell stays untouched.

## Next up

The next concrete actions:

1. **Phase 3 continuous ingestion (now unblocked).** Build
   `metis_app/services/news_feed_repository.py` against the schema in
   ADR 0008, then refactor `routes/comets.py` so `_active_comets` /
   `_last_poll` / `_gc_terminal_comets` become thin wrappers over the
   repository. Wire the existing `NewsIngestService` so its
   `_seen_hashes` is a read-through LRU on top of the repo. Drive
   the loop from the Phase 2 Seedling worker tick (no second
   scheduler). Add the OPML-import endpoint as part of the same PR
   so feed onboarding lands with the storage. Continue avoiding
   double-indexing with `AutonomousResearchService`. **No model
   loading in this phase** — ADR 0013 keeps reflection out of
   Phase 3 entirely.
2. **Extend `/v1/seedling/status` with `model_status`.** Add the
   four-value enum from ADR 0013 §2 (`frontend_only` /
   `backend_configured` / `backend_disabled` / `backend_unavailable`)
   to `SeedlingStatus` and the matching frontend type. Either
   alongside Phase 3 or as a tiny standalone PR before Phase 4.

## Blockers

- **M01 (Preserve & productise, Rolling)** must be far enough along
  that there's a clean attachment surface for a long-running worker —
  specifically that the Litestar app is the single entrypoint
  (ADR 0004) with no lingering Qt/controller state, and that the
  legacy `heretic_service.py`/`app_controller.py` cleanup (§4.6 of
  `docs/preserve-and-productize-plan.md`) has happened or been
  explicitly deferred. Block is **soft** — M13 can start before M01
  finishes as long as the worker only touches services that
  preserve-and-productise has already frozen (§1 of that doc).
- **VISION.md honest tradeoff — continual learning is brittle.** This
  isn't a blocker for starting M13, but it **is** a blocker for
  promising weight-level learning inside this milestone. The
  deliverable of M13 is *system-level* growth: skills accumulate,
  memory densifies, retrieval sharpens, traces become skill
  candidates. LoRA fine-tuning is M18 stretch; do not scope-creep it
  into M13.
- **Growth stages need a real signal.** If Seedling → Sapling → Bloom →
  Elder is decorative, it cheapens the whole pitch (product principle
  #1). The transition metrics (see Phase 5 below) must be concrete and
  visibly tied to user activity before this milestone can be called
  Landed.

## Notes for the next agent

### Web UI new-user audit finding (2026-04-25)

Filed from a live new-user click-through (full entry: [`plans/IDEAS.md`](../IDEAS.md) — *Web UI new-user walkthrough*). One item is M13:

- **Companion overlay's *Recent Activity* surfaces "Seedling heartbeat" × 6** as the visible activity log to a brand-new user. To anyone outside the codebase this reads like an opaque developer log, not a "watch your companion grow" moment. Translate the heartbeat event into something a first-time user actually understands — e.g. "Background research tick", "Companion checked the feed", or whatever maps to the actual signal — and consider showing only the *latest* event by default with the full list behind a disclosure. The metaphor (heartbeat) is fine internally; the user-facing label is what needs to land the *intelligence grown, not bought* promise that this milestone owns.

### Original notes

This milestone is the centre of the vision (*"Next — the Seedling and
the Feed"* in `VISION.md`). Everything in the pitch — "intelligence
grown, not bought", "watch it grow", the morning-after reflection — is
M13. Under-deliver here and the product's emotional moat collapses;
over-promise (LoRA, weight-level continual learning) and users churn
when the promise doesn't land.

### Harvest list — do not rebuild these

Before writing a single line of new code, read each of these in the
existing repo. Roughly 50% of "build the Seedling" is wiring them
together behind one background process:

| Area | File | What to harvest |
|---|---|---|
| News fetchers | `metis_app/services/news_ingest_service.py` | RSS / HN / Reddit fetchers, SSRF-safe HTTP, per-source backoff |
| Comet decisioning | `metis_app/services/comet_decision_engine.py` | `drift` / `approach` / `absorb` scoring against faculty gaps |
| Comet model | `metis_app/models/comet_event.py` | `CometEvent`, `NewsItem`, `CometPhase` lifecycle |
| Comet HTTP | `metis_app/api_litestar/routes/comets.py` | `/v1/comets/*` handlers; poll endpoint already drives the pipeline |
| Companion state | `metis_app/services/assistant_companion.py` | `reflect()` with cooldown, identity bootstrap, status machine |
| Companion model | `metis_app/models/assistant_types.py` + `models/star_nourishment.py` | `AssistantStatus`, `AssistantPolicy`, `NourishmentState` — stages likely live on `AssistantStatus` |
| Auto-research | `metis_app/services/autonomous_research_service.py` | faculty-gap scan, web search → synthesize → index |
| Orchestration seam | `metis_app/services/workspace_orchestrator.py` | where to thread the worker `progress_cb` through |
| Skill candidate store | `metis_app/services/skill_repository.py` (lines 326–381) | `save_candidate` / `list_candidates` — reflection writes here |
| Companion pub/sub | `apps/metis-web/lib/api.ts` (`CompanionActivityEvent`, `subscribeCompanionActivity`) | **the** event bus; M13 emits through it |
| Dock UI | `apps/metis-web/components/shell/metis-companion-dock.tsx` | growth-stage badge lives here, not a new surface |

### Proposed phase breakdown

A first cut. The claimant is free to restructure, but every phase
should have an explicit *what NOT to do* boundary.

#### Phase 1 — Model selection + runtime (ADR 0007 → ADR 0013)

**Goal:** pick the Seedling reflection runtime and defend the choice
in writing.

ADR 0007 (2026-04-24) initially picked Llama-3.2-1B-Instruct Q4_K_M
GGUF served in-process via the existing llama-cpp stack. ADR 0013
(2026-04-25) **supersedes that decision** after a re-audit found the
in-browser Bonsai-1.7B WebGPU runtime
(`apps/metis-web/lib/webgpu-companion/`) was already shipping and
running as the de facto always-on companion. The accepted Phase 1
decision is now:

- Default Seedling reflection runtime: **in-browser Bonsai-1.7B
  (WebGPU)** via the existing `useWebGPUCompanion()` hook. No
  required backend model download. Phase 4 wires this pipeline into
  reflection events.
- Optional backend runtime: **user-uploaded GGUF** through the existing
  `apps/metis-web/app/gguf/` flow, gated on a new
  `seedling_backend_reflection_enabled` setting (default `false`).
  When enabled, the existing `LocalGGUFBackend`/llama-cpp path runs
  reflection from the Seedling worker tick.
- METIS ships **no default backend-model catalog entry** as part of
  M13. The catalog already has Phi-3.5 / Qwen2.5-0.5B for users who
  want backend reflection.
- Browsers without WebGPU surface the existing
  `caniuse.com/webgpu` link plus a one-line *"Configure a local GGUF
  in Settings → Models for backend reflection"* fallback.

**Not this phase:** streaming-token UI polish, model-swap UI, LoRA
integration, model-loading inside the worker (Phase 4 owns that on
the opt-in backend path).

#### Phase 2 — Background worker lifecycle

**Goal:** a persistent process that wakes, does work, and signals
liveness, without stepping on existing services.

- New package: `metis_app/seedling/` (sibling to
  `metis_app/services/`). Entrypoint: `metis_app.seedling.worker:run`.
  Internal modules: `worker.py` (loop), `scheduler.py` (cadence),
  `lifecycle.py` (startup / shutdown hooks), `status.py`
  (`SeedlingStatus` dataclass + on-disk cache).
- Start/stop: hook into Litestar's `on_startup` / `on_shutdown`
  (`metis_app/api_litestar/app.py`) rather than a separate daemon
  unless ADR 0007 mandates otherwise. Benefit: one install, one
  process tree, no cross-process IPC.
- Liveness: expose `GET /v1/seedling/status` returning
  `{running: bool, last_tick_at: iso, current_stage: str,
  next_action_at: iso, queue_depth: int}`. Surface in the companion
  dock as a subtle "breathing" indicator.
- Coordination with M09's `AutonomousResearchService`: the Seedling
  worker **owns the schedule**. It decides when to call
  `run_autonomous_research()`, when to call
  `AssistantCompanionService.reflect()`, and when to poll
  `/v1/comets/poll`. No more separate cron-style triggers scattered
  through the UI. Keep the explicit user-triggered endpoints for
  manual "reflect now" / "research now" but gate the periodic calls
  through the worker.
- Events: every worker action emits through
  `workspace_orchestrator`'s existing `progress_cb` hook so the
  frontend's `CompanionActivityEvent` bus lights up uniformly. **Do
  not invent a new event channel.**

**Not this phase:** the reflection content itself; growth-stage math;
any LLM work. This phase is purely lifecycle and plumbing.

#### Phase 3 — Continuous ingestion (news-comet v1)

**Goal:** the Seedling eats continuously, not on-demand.

ADR 0013 explicitly keeps any reflection / model-loading work out of
this phase. Phase 3 is feed-storage + ingestion + OPML; reflection
wiring lives in Phase 4.

- Driver loop: every `news_comet_poll_interval_seconds`, the worker
  calls `NewsIngestService.fetch_all()` (wrap the existing
  `/v1/comets/poll` body into a plain-Python function so the worker
  doesn't go over HTTP to itself).
- Persistence: move `_active_comets` out of in-memory module state in
  `routes/comets.py` into the new `news_feed_repository.py` per
  ADR 0008. Per-source cursors are stored in `feed_cursors`; the
  cleaner contract from ADR 0008 §4 is the only deleter.
- Dedup: already has a hash-based dedupe in `NewsIngestService`; extend
  with a persistent seen-URLs set on restart.
- OPML import: new endpoint `POST /v1/comets/opml/import` that parses
  OPML and appends feeds to the `news_comet_rss_feeds` setting.
- Offline: when `_safe_get` returns `None` for every source, the
  worker should still tick — it just skips the fetch phase and
  proceeds to reflection/research. Log it, don't crash. The existing
  `_SourceHealth` backoff already covers per-source failure.
- Comet landing in the constellation: **coordinate with M09**. Every
  absorb decision already emits nothing today; extend
  `comet_decision_engine.decide()` callers (in `routes/comets.py`)
  to publish a `CompanionActivityEvent` with
  `source: "news_comet"` and `state: "running" | "completed"`. Then
  `apps/metis-web/app/page.tsx` (around the existing
  `subscribeCompanionActivity` in `useEffect`) can animate the comet
  landing on the canvas without new plumbing. Add `"news_comet"` to
  the `CompanionActivityEvent.source` union in
  `apps/metis-web/lib/api.ts`.

**Not this phase:** email, Twitter/X, podcast feeds (separate follow-up
— record in `plans/IDEAS.md` if proposed).

#### Phase 4 — Reflection (split per ADR 0013)

**Goal:** the Seedling reflects in a structured way and feeds M06's
candidate store.

ADR 0013 splits this phase into a default *while-you-work* path
(Bonsai, in-browser) and an opt-in *overnight* path (backend GGUF).
The Phase 4 PR ships **both seams**, but the overnight surface ships
behind a feature toggle so first-run users do not see broken UX
when no backend GGUF is configured.

**4a — While-you-work reflection (default, Bonsai).**

- Wire the existing `useWebGPUCompanion()` pipeline into the new
  reflection writer. The `metis:bonsai-always-on` toggle continues
  to gate event-driven reflection, but its callsite now also writes
  into a structured reflection record (via a new Litestar route the
  worker can call internally) instead of only updating the in-dock
  thought log.
- Cadence: event-driven (one reflection per completed
  `CompanionActivityEvent`) with a measurement-driven rate-limit
  (target ≥30 s between reflections; tune in retro). No time-of-day
  dependency.
- Output: extend `AssistantCompanionService.reflect()` with a thin
  Bonsai-token-stream consumer that (a) writes a short-form
  `latest_summary` / `latest_why` on `AssistantStatus`, (b) inspects
  high-convergence traces and writes candidates via
  `SkillRepository.save_candidate()` — this is the **feed into M06's
  skill self-evolution**; do not let M06 duplicate this writer,
  (c) emits a `"reflection"` `CompanionActivityEvent` with
  `kind: "while_you_work"`. The `kind` field is an **additive type
  extension** to `CompanionActivityEvent` in `apps/metis-web/lib/api.ts`
  (`kind?: "while_you_work" | "overnight"` on top of the existing
  `source | state | trigger | summary | timestamp | payload?` shape);
  existing fields keep their meaning. This is the same posture as
  Phase 3's planned `'news_comet'` addition to the `source` union —
  extend, do not duplicate.
- WebGPU-unavailable browsers: no reflection happens. The dock shows
  the existing `caniuse.com/webgpu` link plus the ADR 0013 fallback
  copy. Phase 4 does not silently degrade to a placeholder.

**4b — Overnight reflection (opt-in, backend GGUF).**

- Cadence: default 1× per 24 h via `seedling_reflection_cadence_hours`,
  with a quiet window of `seedling_reflection_quiet_window_minutes`
  (default 30) so user activity does not trip the cycle. Worker only
  schedules this when `seedling_backend_reflection_enabled = true`
  AND `model_status == "backend_configured"`.
- Input: session traces since the last reflection, newly absorbed
  comets, newly-indexed stars from the autonomous research pipeline.
- Output: extend `AssistantCompanionService.reflect()` with an
  `overnight=True` mode driven by the backend GGUF that writes a
  longer-form `latest_summary` / `latest_why`, captures candidates
  the same way as 4a, and emits the same event kind with
  `kind: "overnight"` so the dock can show a "here's what I learned
  overnight" card in the morning.
- **Distinguish from M09's research loop.** Autonomous research =
  targeted faculty-gap filler, triggered by schedule or by the user.
  Reflection (either path) = broad self-inspection over all session +
  comet activity. One can cause the other (reflection finds a gap,
  schedules research) but they are not the same call.

**Not this phase:** a full agentic loop, skill auto-promotion, or
marketplace surfacing. Candidates land in `skill_candidates.db`; M06
owns the promote-to-skill step. Marketing copy still avoids
"reflects while you sleep" without the qualifier from ADR 0013 §3.

#### Phase 5 — Growth stages UI

**Goal:** Seedling → Sapling → Bloom → Elder is visible and driven by
a real signal.

- Stage machine: add `growth_stage: Literal["seedling","sapling","bloom","elder"]`
  to `AssistantStatus` (in `metis_app/models/assistant_types.py`).
  Pure function `compute_growth_stage(status, indexes, memory,
  skills, reflections) -> stage` so it's testable without the full
  service.
- Proposed transition metrics (first cut — tune during
  implementation):
  - **Seedling → Sapling**: ≥10 user-indexed stars *and* ≥1
    completed overnight reflection.
  - **Sapling → Bloom**: ≥50 stars spanning ≥6 faculties *and* ≥5
    captured skill candidates *and* ≥7 overnight reflections.
  - **Bloom → Elder**: ≥200 stars *and* ≥3 promoted skills (via
    M06) *and* ≥30 reflections *and* brain-graph density
    (coord with M10) crossing a threshold.
  - These must feel *earned*. Nothing auto-advances on time alone —
    product principle #1.
- Surface: badge + 1-line status in
  `apps/metis-web/components/shell/metis-companion-dock.tsx`
  (top of the expanded panel, above the thought log). Optional
  second surface: the home page (`apps/metis-web/app/page.tsx`)
  empty-state hero when the user has no sessions — "Your companion
  is a Seedling. Feed it."
- Transition moment: when the stage advances, emit a distinguished
  `CompanionActivityEvent` kind (`"stage_transition"`) so the dock
  can fire a one-time confetti/pulse and optionally drop a note
  into `latest_summary`. This is the "magic moment" rep that
  VISION.md calls out as a churn defence.
- Per-stage unlocks (tentative): Sapling unlocks the overnight
  reflection morning summary, Bloom unlocks the Forge (M14) by
  default, Elder unlocks the skill marketplace (M15/dreams phase).
  These are *wiring*, not gates — the functionality exists from
  day one if the user flips a setting.

**Not this phase:** user-facing stage explanations copy (that's
copywriting + onboarding work, track separately).

#### Phase 6 — Brain-graph densification (deferred, coordinates with M10)

**Goal:** the brain graph should visibly fatten as the Seedling grows.

- **Deferred unless M10 (TriveV2 homological scaffold) has landed or
  is in progress.** M10 is Draft; if still Draft when M13 is
  claimed, mark this phase **Deferred — fold into M10's Step 6** and
  move on.
- If M10 is further along: feed Seedling-produced
  `AssistantBrainLink` records into `BrainGraph.compute_edge_weights()`
  so scaffold edges carry the companion's recent activity.
- Visual: pulse the edge when the Seedling creates it
  (coord with M02 / `brain-graph-3d.tsx`).

**Not this phase:** re-implementing persistent homology. That's M10.

#### Phase 7 (stretch) — LoRA on-deck

**Goal:** produce the training-data shape that M18 will eventually
consume, without shipping fine-tuning in M13.

- The overnight reflection cycle already sees every session
  + retrieved context + user feedback. Capture that as a JSONL
  record (`seedling_training_log.jsonl`) with fields: prompt,
  retrieved context, model output, user feedback
  (thumbs-up/down/notes from `session_repository`), trace id.
- Do *not* call any training code in M13. Do *not* surface "fine-tune
  now" in the UI. The deliverable is the log, nothing else.
- This is the *only* place M13 touches LoRA. Anything more is M18.

**Not this phase:** any weight modification, any GPU training, any
"fine-tune" button.

### Open decisions requiring ADRs

1. **ADR 0007 — Seedling model + runtime** (Phase 1 above).
   Completed 2026-04-24, **superseded** 2026-04-25 by ADR 0013 after
   a re-audit found the in-browser Bonsai-1.7B WebGPU runtime was
   already shipping. See `docs/adr/0007-seedling-model-and-runtime.md`
   for the historical decision.
2. **ADR 0008 — Feed-storage format** (new table vs Atlas extension,
   per-source cursors, OPML serialisation). Completed 2026-04-25; see
   `docs/adr/0008-feed-storage-format.md`.
3. **ADR 0013 — Seedling runtime: frontend default, backend optional**
   (which runtime carries the Phase 4 reflection content). Completed
   2026-04-25; see
   `docs/adr/0013-seedling-runtime-frontend-default.md`. Supersedes
   ADR 0007.
4. **ADR 0009 — Growth-stage signal** (exact thresholds, whether
   stages can regress, manual override for testing). Blocker for
   Phase 5. Arguably record as a plan-doc decision section rather
   than a full ADR if the thresholds will tune rapidly during
   development.

### Coordination risks

- **M09 (Landed) already owns the `CompanionActivityEvent` pub/sub
  and the dock thought log.** M13 emits through it; M13 does **not**
  introduce a second event bus, a second dock, or a second subscribe
  hook. Any temptation to add "Seedling-specific" streaming is a
  smell — add a new `source` value and a new `kind`, nothing else.
- **M06 (Ready) owns skill promotion from high-convergence traces.**
  The Seedling's overnight reflection is the **writer** to
  `skill_candidates.db`. M06 is the **reader/promoter**. Scope the
  boundary explicitly in PR descriptions so nobody implements both
  ends of the pipe twice.
- **M10 (Draft) owns brain-graph topology.** Phase 6 above is
  deferred unless M10 is live.
- **M01 (Rolling) is still cleaning up the legacy controller layer.**
  Do not attach the Seedling worker to anything in
  `metis_app/controllers/`. Use Litestar lifecycle hooks directly.
- **M15 (Pro tier launch)** blocks on M13 being real enough that a
  "what METIS learned this week" newsletter has genuine content. Do
  not build marketing surfaces into M13 itself — that's M15's
  concern.
- **M16 (Personal evals)** blocks on M13 producing measurable
  per-user improvement signal. Phase 7's training-log capture
  doubles as M16 raw material; make the schema stable enough that
  M16 can read it without rewrites.

### What NOT to do in M13

- **No LoRA fine-tuning.** That's M18 (stretch). Phase 7 caps out at
  "produce a training log". Anything beyond that violates
  VISION.md's *"LoRA fine-tuning is a stretch goal"*.
- **No mobile / PWA.** M19 is the mobile stretch. The Seedling runs
  on the desktop; the constellation surfaces the stage. No second
  client.
- **No weight-level continual learning claims.** The pitch we can
  honestly make is *system-level* growth — skills, memory,
  retrieval, traces-to-skills. VISION.md's *Risks and honest
  tradeoffs* section is explicit: the system grows, not the weights.
  Reflect that in UI copy.
- **No new event bus, no new dock, no new thought-log UI.** Emit
  through `CompanionActivityEvent`. Surface in
  `metis-companion-dock.tsx`.
- **No Forge / technique-gallery work.** That's M14. The Seedling
  consumes capabilities; the Forge produces them.
- **No paywall gating.** Pro-tier limits are M15's concern. Build
  M13 as if every user has everything.
- **No "the companion is sentient" copy.** The growth-stage names
  are poetic; the prose around them should still be grounded and
  specific ("you've fed it 50 stars across 6 faculties").

### Key files the next agent will touch

Backend:
- `metis_app/seedling/` *(new package)*
- `metis_app/api_litestar/app.py` *(startup/shutdown hooks)*
- `metis_app/api_litestar/routes/` *(new `seedling.py`; extend `comets.py`)*
- `metis_app/services/assistant_companion.py` *(add `overnight` reflection)*
- `metis_app/services/news_ingest_service.py` *(extract the poll driver)*
- `metis_app/services/comet_decision_engine.py` *(emit CompanionActivityEvent)*
- `metis_app/services/workspace_orchestrator.py` *(thread worker progress_cb)*
- `metis_app/services/skill_repository.py` *(candidate store — reader existed already)*
- `metis_app/models/assistant_types.py` *(add `growth_stage`)*
- `metis_app/models/comet_event.py` *(no changes expected)*
- `metis_app/default_settings.json` *(add `seedling_*` keys)*

Frontend:
- `apps/metis-web/components/shell/metis-companion-dock.tsx` *(stage badge)*
- `apps/metis-web/lib/api.ts` *(extend `CompanionActivityEvent.source`)*
- `apps/metis-web/app/page.tsx` *(stage-aware empty state, comet landing)*
- `apps/metis-web/lib/comet-types.ts` *(no changes expected)*

ADRs (new):
- `docs/adr/0007-seedling-model-and-runtime.md`
- `docs/adr/0008-feed-storage-format.md`
- optionally `docs/adr/0009-growth-stage-signal.md`

### Prior art to read before starting

- `VISION.md` — especially *How an AI grows in METIS* and *Risks and
  honest tradeoffs*.
- `plans/companion-realtime-visibility/plan.md` — M09's landed plan.
  The pub/sub wiring is the template.
- `docs/adr/0005-product-vision-living-ai-workspace.md` — the vision
  ADR; any decision in M13 must be consistent with it.
- `docs/adr/0004-one-interface-next-plus-litestar.md` — why the
  Seedling attaches to Litestar, not a separate daemon.
- `docs/adr/0006-star-archetype-visual-language.md` — for how comet
  absorption becomes a star archetype in the constellation.
- `docs/preserve-and-productize-plan.md` §1 (Preserve exactly) — the
  list of subsystems the Seedling must NOT perturb.
