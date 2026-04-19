---
Milestone: The Forge (M14)
Status: Draft
Claim: unclaimed
Last updated: 2026-04-19 by claude/plans-m14-m16-m17
Vision pillar: Companion + Cortex
---

## Progress

*(milestone not started as a cohesive unit — this doc is the first real
plan pass. The Forge is a thin new UI surface over a lot of
already-shipped technique infrastructure. Crucially, **every named
frontier technique the Forge will list already exists as working code
in the repo**; what's missing is the gallery surface that elevates
them from "settings checkbox" to "capability the companion just
absorbed". See the harvest inventory in *Notes for the next agent*.)*

What's in place today that M14 will lean on:

- **Every frontier technique named in VISION.md is already implemented.**
  IterRAG convergence (`agentic_mode` + `agentic_convergence_threshold`
  in `metis_app/default_settings.json:148–158`, driven through
  `metis_app/engine/querying.py`), Swarm persona simulation
  (`metis_app/services/swarm_service.py`, `SwarmSimulator` at line 314),
  Heretic abliteration
  (`metis_app/services/heretic_service.py`, CLI-wrapped, with a
  live route at `metis_app/api_litestar/routes/heretic.py`),
  Tribev2 multimodal faculty extraction
  (`metis_app/services/brain_pass.py` — the `brain_pass_*` settings
  at `default_settings.json:167–178`), TimesFM forecasting
  (`metis_app/services/forecast_service.py` + `metis_app/engine/forecasting.py`,
  `forecast_*` settings at `default_settings.json:142–147`),
  sub-query expansion (`use_sub_queries` at `default_settings.json:134`,
  `subquery_max_docs` at line 137), hybrid BM25+vector retrieval
  (`metis_app/services/hybrid_scorer.py`, `hybrid_alpha` at
  `default_settings.json:131`), MMR diversification (`mmr_lambda` at
  line 132, `retrieval_mode: "mmr"` at line 128), reranking
  (`metis_app/services/reranker.py`, `use_reranker` at line 133).
  The Forge does not build techniques; it *surfaces* them.
- **Skill infrastructure — half of a marketplace.**
  `metis_app/services/skill_repository.py` already loads YAML-frontmatter
  skills from `skills/` (nine shipped: `agent-native-bridge`,
  `evidence-pack-timeline`, `pptx-export`, `qa-core`, `research-claims`,
  `summary-blinkist`, `swarm-critique`, `symphony-setup`,
  `tutor-socratic`), gates them via `settings["skills"]["enabled"]`
  (per-skill booleans), and has a `skill_candidates.db` pipeline
  (`save_candidate` / `list_candidates` / `mark_candidate_promoted`
  at `skill_repository.py:326–381`). The Forge is the front-end
  for candidate review that M06 currently lacks.
- **Settings page pattern to copy (and diverge from).**
  `apps/metis-web/app/settings/page.tsx` already renders one
  of the largest per-feature toggle surfaces in the app
  (hybrid_alpha sliders, reranker toggles, swarm_n_personas
  steppers, agentic-mode checkboxes). This is the *anti-pattern*
  the Forge must avoid (VISION principle #4 — "Skills over
  settings"). But the shape of `updateSettings()` calls in
  `apps/metis-web/lib/api.ts` and the shadcn form pattern are the
  right mechanics.
- **M02 (Landed 2026-04-19) design-system primitives.**
  `apps/metis-web/components/ui/` now carries the 2D constellation
  design system — `animated-lucide-icon`, `border-beam`,
  `tooltip`, `tabs`, `separator`. The Forge's technique cards
  should lean on these rather than re-invent.
- **Companion dock as the "here's what I just learned" surface.**
  `apps/metis-web/components/shell/metis-companion-dock.tsx` —
  the M09-landed pub/sub bus — already displays
  `CompanionActivityEvent`s. When a user enables a technique via
  the Forge, the dock should fire a "the companion has absorbed
  <technique>" event; no new event channel needed.
- **Page chrome pattern.** `components/shell/page-chrome.tsx` +
  the `app/settings/`, `app/gguf/`, `app/brain/`, `app/library/`
  route set is the template for adding a new top-level route.
  A new `app/forge/` slot fits the existing shell without layout
  surgery.

## Next up

The first concrete actions for whoever claims M14:

1. **Write ADR 0010 — Forge route and toggle-state architecture.**
   Decide three things in one doc: (a) route shape —
   single-page `/forge` with anchored sections vs.
   `/forge` index + `/forge/<technique-id>` detail pages; (b)
   toggle-state storage — reuse existing `settings_store.py` keys
   (already-in-place but scattered), promote to a typed
   `forge_state` module sitting on top of M11's agent-native KV
   store, or introduce a new `forge_state.db`; (c) what
   constitutes a "technique" in Forge terms — is it any
   settings-gated capability, a `skills/` entry, or a new
   first-class registry object? Recommend (a) single-page with
   deep-link anchors for v1, (b) reuse `settings_store.py` behind
   a thin `forge_registry.py` facade, (c) introduce a
   `TechniqueDescriptor` dataclass — lightweight, registry-driven,
   non-dynamic. This is the biggest design choice in M14 and
   should be argued in writing before any UI code.
2. **Build the technique inventory — read-only first.** Ship
   `apps/metis-web/app/forge/page.tsx` rendering a static list
   of every technique from the harvest inventory below, with
   description, pillar, current enable state pulled from
   `fetchSettings()`. No toggles yet. The goal is to make the
   data surface real before adding interaction. Parallel
   backend work: a new `metis_app/api_litestar/routes/forge.py`
   exposing `GET /v1/forge/techniques` returning
   `[{id, name, description, pillar, enabled, setting_keys,
   recent_uses}]`.
3. **Spike a single toggle end-to-end.** Pick one technique
   with a clear on/off — suggest `use_reranker`. Wire the
   Forge card's toggle to `updateSettings({use_reranker: true})`,
   verify it propagates to the retrieval pipeline, and fire a
   `CompanionActivityEvent` with
   `source: "forge", kind: "technique_toggled",
   payload: {technique_id: "reranker", enabled: true}`. If this
   round-trips cleanly — settings write, pipeline uses new value
   on next query, dock reflects the change — the mechanism
   scales to every other card.

## Blockers

- **M06 (Skill self-evolution, Ready)** must be far enough along
  that skill-candidate promotion is real. The Forge's
  *"Accept this candidate skill"* pane is the front-end for
  M06's data pipeline (`skill_repository.save_candidate()` →
  Forge review UI → `mark_candidate_promoted()` →
  `skills["enabled"][<id>] = true`). M06 is **Ready**, not
  landed; if the Forge ships before M06's writer side, the
  candidate review pane will be inert. Options: (1) block
  Phase 5 until M06 lands, (2) ship the reader-only review
  pane with a "no candidates yet — your companion hasn't
  reflected long enough" empty state, which also buys us the
  VISION.md copy win of "watch it grow". Recommend option (2)
  so the Forge can ship its first four phases without M06 in
  the critical path.
- **M02 (Constellation 2D refactor, Landed 2026-04-19)** —
  design-system primitives are in place, but the *home
  page* (`apps/metis-web/app/page.tsx`) is still the hotspot
  of all hotspots (99.8th %ile churn per Repowise). Adding a
  "Open the Forge" entry point to the home page will collide
  with any concurrent M02-adjacent work. Coordinate in PR
  descriptions; prefer reaching the Forge from the page
  chrome nav, not from the constellation canvas itself.
- **VISION.md principle #4 ("Skills over settings") is a
  design tension, not a code blocker.** If the Forge is built
  as a second settings page with prettier icons, the milestone
  fails its own pitch. The guard is: every Forge card must
  frame the toggle as *"accepting a capability"*, not
  *"enabling a feature"*. Copy, animation, and the companion's
  reaction (dock event) matter as much as the mechanic.
- **VISION.md principle #9 ("No capability without a star")
  applies awkwardly to the Forge.** Techniques are not
  documents; they don't naturally live as stars in the
  constellation. Resolve this explicitly in ADR 0010 — either
  (a) each *active* technique gets a star (think "companion
  skills" as a dedicated constellation sector), (b) the Forge
  itself gets a star that unfolds into the gallery, or (c)
  we declare the Forge a legitimate exception to principle #9
  and document that in the ADR. Recommend (a) — techniques
  are exactly the *capabilities* that principle is protecting.
  Coordinate with M12's star-catalogue work.

## Notes for the next agent

The Forge is a **thin** milestone over **thick** existing
infrastructure. Every time you think "we need to build X", check
the harvest inventory below first — the probability is very high
X already exists as a settings key, a service, or a route. The
M13 lesson applies squared to M14: the emotional moat is
*exposure*, not *creation*.

The Forge is also where the VISION's maximalism pays off. Heretic
abliteration, Swarm simulation, Tribev2 multimodal extraction —
these are each arguably over-scoped for an indie product on their
own. Shipped as one togglable gallery, they stop looking like
loose experiments and start looking like *the gallery the pitch
promised*. The Forge is the feature that makes the rest of the
codebase make sense.

### Harvest inventory — what the Forge actually lists on day one

**Every row below is already implemented code.** The Forge's job
is to give each a card, a description, a toggle, and a home.

| Technique | Pillar | Current toggle | Engine surface | User-facing today? |
|---|---|---|---|---|
| **IterRAG convergence** | 🧠 | `agentic_mode: bool`, `agentic_max_iterations: int`, `agentic_convergence_threshold: float`, `agentic_iteration_budget: int`, `agentic_context_compress_*` (`default_settings.json:148–159`) | `metis_app/engine/querying.py` agentic loop; `metis_app/engine/streaming.py` for SSE | Hidden in Advanced Retrieval tab of settings page |
| **Sub-query expansion** | 🧠 | `use_sub_queries: bool` (line 134), `subquery_max_docs: int` (line 137) | `metis_app/services/retrieval_pipeline.py` | Settings toggle, no explanation |
| **Hybrid search (BM25 + vector, M08 Landed)** | 🧠 | `hybrid_alpha: float` (line 131 — 1.0 = vector-only, 0.0 = BM25-only) | `metis_app/services/hybrid_scorer.py`; `metis_app/services/vector_store.py` | Slider in settings, unexplained |
| **MMR diversification** | 🧠 | `mmr_lambda: float` (line 132), `retrieval_mode: "mmr" \| "flat" \| "hybrid" \| "hierarchical"` (line 128) | `metis_app/services/retrieval_pipeline.py` | Slider + dropdown in settings |
| **Reranker** | 🧠 | `use_reranker: bool` (line 133) | `metis_app/services/reranker.py` (`rerank_hits` at line 143) | Settings toggle |
| **Swarm persona simulation** | 🧠 | `swarm_n_personas: int` (line 154), `swarm_n_rounds: int` (line 155) | `metis_app/services/swarm_service.py` (`SwarmSimulator` at line 314); `metis_app/api_litestar/routes/query.py` (SwarmQueryRequest at `engine/querying.py:96`) | Has its own skill (`skills/swarm-critique/`) but no discovery surface |
| **TimesFM forecasting** | 🧠 | `forecast_model_id`, `forecast_max_context`, `forecast_max_horizon`, `forecast_use_quantiles`, `forecast_xreg_mode`, `forecast_force_xreg_cpu` (lines 142–147); activated via `chat_path: "Forecast"` | `metis_app/services/forecast_service.py`; `metis_app/engine/forecasting.py` | Only reachable via Forecast chat path — no gallery entry |
| **Tribev2 multimodal faculty extraction** | 🌱🌌 | `brain_pass_native_enabled`, `brain_pass_native_text_enabled`, `brain_pass_model_id`, `brain_pass_device`, `enable_brain_pass` (lines 167–178) | `metis_app/services/brain_pass.py` (tribev2 runtime resolver at line 189) | Runs during index build; invisible to user |
| **Heretic abliteration** | 🧠 | `heretic_output_dir` (line 196); no boolean, subprocess-gated by CLI availability (`is_heretic_available()` at `heretic_service.py:48`) | `metis_app/services/heretic_service.py`; `metis_app/api_litestar/routes/heretic.py` | Standalone page/dialog exists; not in a gallery |
| **News-comet ingestion (M13)** | 🌱 | `news_comets_enabled`, `news_comet_sources`, `news_comet_poll_interval_seconds`, `news_comet_max_active`, `news_comet_auto_absorb_threshold`, `news_comet_rss_feeds`, `news_comet_reddit_subs` (lines 201–207) | `metis_app/services/news_ingest_service.py`; `metis_app/services/comet_decision_engine.py` | Off by default; M13 is making it always-on |
| **Hebbian edge updates** | 🌱 | `enable_hebbian: bool` (line 179), `hebbian_boost`, `hebbian_decay` (180–181) | `metis_app/utils/hebbian_decoder.py` | No user surface |
| **Autonomous research (M09 Landed)** | 🌱 | `assistant_policy.autonomous_research_enabled` (line 65) | `metis_app/services/autonomous_research_service.py` | Companion dock; the Forge would list the *technique*, the dock still owns the live feed |
| **Recursive retrieval / memory** | 🧠🌱 | `enable_recursive_retrieval`, `enable_recursive_memory` (lines 186–187) | pipelines referenced in settings but implementation status varies | **Audit before listing** — may be dead code from M01 |
| **Citation v2 / claim-level grounding** | 🧠 | `enable_citation_v2`, `enable_claim_level_grounding_citefix_lite` (188–189) | `metis_app/services/response_pipeline.py` | Hidden in settings |
| **Knowledge graph extraction (langextract / structured)** | 🧠 | `enable_langextract`, `enable_structured_extraction`, `build_llm_knowledge_graph`, `kg_query_mode` | response/indexing pipeline | Hidden in settings |
| **Arrow artifact runtime** | 🔧 | `enable_arrow_artifacts`, `enable_arrow_artifact_runtime` (lines 184–185) | `metis_app/services/artifact_converter.py` | Hidden in settings |
| **Agent Lightning** | 🧠 | `agent_lightning_enabled` (line 190) | `metis_app/services/runtime_resolution.py` | **Audit** — may be stub |
| **Semantic chunking** | 🧠 | `structure_aware_ingestion`, `semantic_layout_ingestion`, `chunk_strategy: "fixed" \| "semantic"` | `metis_app/services/semantic_chunker.py` | Hidden in settings |
| **Skill library (9 shipped skills)** | 🌱🧠 | `settings["skills"]["enabled"][<id>]` bool | `metis_app/services/skill_repository.py`; YAML frontmatter in `skills/<id>/SKILL.md` | No surface — silently activated by query modes |
| **User-submitted technique (post-v1)** | 🌱 | — (new) | — (new; may tie to M13 ingestion) | Phase 4 below |

**The inventory is also a harvest audit.** Before shipping, walk
each row and answer: (a) does the toggle actually do anything on
an end-to-end query? (b) is the description writable in one
honest sentence, or is the technique too vague to promote? (c)
does the setting-key layout match what the Forge UI will need, or
should we normalise to a consistent `{technique_id}_enabled`
pattern in a follow-up? Any row that fails (a) or (b) gets either
fixed or filed to `plans/IDEAS.md` as a harvest debt; it does not
ship in the Forge until it can earn its slot.

### Proposed phase breakdown

A first cut. Each phase has an explicit *what NOT to do* boundary.

#### Phase 1 — Forge route + shell (ADR 0010)

**Goal:** a new top-level route with page chrome, empty content,
navigable from the existing settings/home nav.

- New route: `apps/metis-web/app/forge/page.tsx` +
  `apps/metis-web/app/forge/loading.tsx`. Page chrome via
  `components/shell/page-chrome.tsx` (the same wrapper
  `/settings` uses).
- Nav entry: add a "Forge" link to wherever the existing
  nav lives (audit `components/shell/hud/` and
  `components/shell/page-chrome.tsx`). Do **not** add an
  entry to the constellation canvas itself in this phase —
  principle #9 resolution happens in Phase 2.
- ADR 0010 resolves route shape (single-page vs per-technique)
  before the shell is implemented. Default recommendation:
  single page with anchored sections + in-page search/filter;
  per-technique detail pages deferred to post-v1 unless a
  technique has enough content (trace history, config sliders,
  changelog) to warrant its own page.
- Backend: stub `routes/forge.py` with a `GET /v1/forge/techniques`
  returning a static hard-coded list (mirror of the harvest
  inventory). No dynamic registry yet.

**Not this phase:** technique toggles, any card interaction,
marketplace, candidate review, trace integration.

#### Phase 2 — Technique cards (read-only) + star home

**Goal:** every technique in the harvest inventory has a card,
with description, pillar badge, current enabled state (read-only),
and — resolving principle #9 — a star in the constellation that
opens the Forge card.

- Card component: new `apps/metis-web/components/forge/technique-card.tsx`.
  Leans on M02 primitives (`border-beam`, `tooltip`,
  `animated-lucide-icon`). Variants by pillar colour.
- Data source: `GET /v1/forge/techniques` now returns real data
  — a server-side registry in `metis_app/services/forge_registry.py`
  that maps `TechniqueDescriptor` entries (id, name, description,
  pillar, enabled, setting_keys, docs_url, engine_symbols) to
  the live settings store. One entry per harvest row.
- Constellation integration: each **active** technique lives
  as a distinct star under a new "Skills" faculty in the
  constellation. The star's observatory dialog
  (`star-observatory-dialog.tsx`) deep-links to
  `/forge#<technique-id>`. This is how principle #9 is
  satisfied for the Forge. Techniques that are *off* do not
  appear in the constellation — turning one on *in the Forge*
  lights up its star, which is exactly the "capability
  absorbed" feel VISION.md wants.
- The settings page stays — the Forge is not a replacement for
  advanced retrieval parameter tuning. But every card links to
  the relevant settings deep-link for power users.

**Not this phase:** writable toggles, arXiv paste, candidate
review, trace history.

#### Phase 3 — Per-technique toggles (the ignition moment)

**Goal:** flipping a card from off to on actually activates the
capability — and feels like the companion just absorbed it.

- Toggle wiring: each card calls `updateSettings()` (or the new
  assistant-policy sub-path where applicable — see harvest
  inventory for per-technique key layout). The settings-keys
  list lives on the `TechniqueDescriptor`.
- Event emission: on success, emit a
  `CompanionActivityEvent` with
  `source: "forge", kind: "technique_toggled",
  payload: {technique_id, enabled}` through the existing M09
  pub/sub. The dock shows a one-line acknowledgement; if
  `enabled`, the card animates (use M02's `border-beam` for
  30 seconds, then settle), and the constellation star fades
  in.
- Pre-flight checks: some techniques have runtime
  prerequisites — Heretic needs the CLI on PATH
  (`is_heretic_available()` at `heretic_service.py:48`),
  TimesFM needs the model downloaded, Tribev2 needs the
  Python dep, GGUF techniques need a chosen model. Each card
  reports its readiness; an un-ready card offers a
  "Get ready" action (link to `/gguf`, install Heretic, etc.)
  rather than a raw toggle.
- Validation: at least three techniques must round-trip
  toggle → engine behaviour change → observable output before
  calling the phase done. Suggested: reranker, sub-queries,
  swarm.
- State KV question: recommend *not* introducing a new
  `forge_state.db` in this phase. The live settings store
  (`settings_store.py` — read/write via `GET/POST /v1/settings`)
  is sufficient. If we discover we need ephemeral UI state
  (card expansion, "what's new" badges), route it through
  M11's agent-native KV store (`/v1/app_state`), not a new
  table.

**Not this phase:** paste-arXiv, candidate review, trace
integration, marketplace.

#### Phase 4 — "Absorb a technique" — arXiv paste flow

**Goal:** user pastes an arXiv (or GitHub / blog) URL; METIS
processes it into a candidate technique description; user
reviews before activation. This is the *growth moment* the
VISION paragraph explicitly promises.

- UI: a prominent "Absorb a technique" input at the top of the
  Forge page. Accepts arXiv links, GitHub READMEs, blog URLs.
  Spinner + progress log while the companion reads and
  extracts.
- Backend: new `POST /v1/forge/absorb` that:
  1. Fetches the source (respect SSRF safety — reuse
     `news_ingest_service._safe_get`).
  2. Summarises into a structured `TechniqueProposal`
     (name, claim, pillar guess, does-METIS-already-have-it,
     rough implementation sketch). **LLM-driven; uses the
     assistant's configured model.**
  3. Cross-references against the existing harvest inventory
     — "you asked to add IterRAG; METIS already has it, here's
     where it lives." This is as important as the creation
     path; it prevents the companion from pretending to absorb
     what's already absorbed.
  4. For genuinely new techniques, writes a
     `TechniqueProposal` to a new `forge_proposals.db`
     (or an extension of `skill_candidates.db` — decide in
     ADR 0010). **Does not activate.** Proposal sits in a
     review pane.
- Tie-in with M13 news-comet pipeline: the comet
  decision-engine may flag an arXiv comet as
  "absorb" with high score. When it does, a
  `TechniqueProposal` lands in the Forge review pane
  automatically. This is the "paste an arXiv link → watch
  the companion absorb it" moment VISION.md is describing.
- **Reject as a source of code.** The Forge does not write
  new engine code from arXiv links. What it does: (a)
  identify which existing technique most closely matches,
  (b) propose settings changes that activate adjacent
  techniques in a new combination, (c) produce a
  `skills/<id>/SKILL.md` draft (YAML frontmatter + body)
  with `runtime_overrides` that the user reviews and
  activates. This is a conservative scope that delivers the
  *feel* without the impossible scope of "arbitrary code
  generation from a paper". Document this boundary in
  ADR 0010.

**Not this phase:** marketplace, revenue share, cross-user
skill sharing, running untrusted code from papers.

#### Phase 5 — Skill-marketplace hooks (local-only v1)

**Goal:** candidate skills from M06 appear in the Forge with
accept/reject UI. Cross-user sharing scoped *out*.

- Producer side (M06, Ready): the Seedling's overnight
  reflection already writes to
  `skill_candidates.db` via
  `skill_repository.save_candidate()`. Nothing for the Forge
  to do here — just consume.
- Reader UI: a new "Candidate skills" section on the Forge
  page (second-class to the main technique gallery).
  Each candidate shows: the originating query, convergence
  score, trace excerpt, proposed runtime overrides.
  Accept → writes a `skills/<id>/SKILL.md` file + flips
  `settings["skills"]["enabled"][id] = true` + calls
  `mark_candidate_promoted(id)`. Reject → just marks
  promoted=1 with a `rejected=1` side column (new column).
- Backend: `GET /v1/forge/candidates`,
  `POST /v1/forge/candidates/<id>/accept`,
  `POST /v1/forge/candidates/<id>/reject`. Accept handler
  writes the YAML file; small bespoke writer (do not
  generalise until we have more than one use case).
- **Marketplace revenue share (VISION.md 80/20) is
  explicitly out of scope for M14.** That's in
  post-M15 territory — after Pro tier launches, once we have
  paying users, when "upload a skill" has a plausible audience.
  Do not wire Stripe. Do not add "publish to marketplace" UI.
  Leave a single greyed-out "Share this skill" button with
  tooltip "Coming with Lifetime tier" if the aesthetic
  demands it, or omit entirely.

**Not this phase:** any remote endpoint; any upload; any
payments; any cross-user trust / signature model.

#### Phase 6 — Trace integration

**Goal:** each technique card shows recent usage from the
existing trace timeline (principle #5 — "Trace everything").

- Backend: `GET /v1/forge/techniques/<id>/recent-uses`
  returning the last N trace events where this technique
  contributed (retrieval step mentions reranker, query
  result used agentic loop, etc). Source:
  `metis_app/services/trace_store.py`.
- UI: card expansion shows a mini-timeline (reuse
  `apps/metis-web/components/chat/trace-timeline.tsx`
  styling, if it generalises cheaply). Each entry links
  into the full trace view.
- "Technique was used N times this week" micro-counter on
  the card face — this is the *honest growth metric* that
  turns a toggle from a checkbox into evidence of use.
  VISION.md's "intelligence grown, not bought" works better
  when the user can see that a technique they enabled two
  weeks ago has been earning its keep.

**Not this phase:** aggregated analytics dashboards,
cross-technique correlation, "your companion uses reranker
47% more than average" — that's M16's territory.

#### Phase 7 (stretch) — Export / share a technique bundle

**Goal:** produce the *file format* for sharing a skill bundle,
without shipping any network surface. A later milestone
(post-M15) can wire the marketplace.

- Format: `.metis-skill` — a tarball of the `skills/<id>/`
  directory plus a manifest (id, author, version, dependency
  list of other skills, minimum METIS version). Signed by a
  local keypair *if* we can add `pyca/cryptography` without
  weight; otherwise unsigned in v1.
- UI: "Export this skill" button on accepted candidate
  cards. Produces a file in a user-chosen directory.
  Explicitly does **not** upload.
- "Import a .metis-skill" flow: drag and drop onto the
  Forge page → preview → accept.
- This phase exists to make M15+ launch copy honest:
  "you can already share skills between METIS installs,
  the marketplace just makes it one click." Do not over-invest
  before M15's readership is proven.

**Not this phase:** hosted marketplace, signature-of-trust PKI,
discoverability search, any remote component.

### Open decisions requiring ADRs

1. **ADR 0010 — Forge route + toggle-state architecture**
   (Phase 1). Covers: single-page vs per-technique route
   shape; toggle-state storage (reuse settings vs M11 KV vs
   new `forge_state`); what a "technique" *is* (registry
   object vs settings-synthesised); arXiv-paste scope
   boundary (no code generation, only proposal + skill
   draft); star-per-technique as principle #9 resolution.
   **Biggest design call in the milestone.**
2. **ADR 0011 — Candidate skill acceptance mechanics**
   (Phase 5). Covers: file-writer format, YAML schema
   migration policy if the skill schema changes, rejection
   bookkeeping (new column vs separate table), whether an
   auto-accept threshold should exist.
3. **ADR 0012 — Skill bundle format** (Phase 7, optional
   until Phase 7 claimed). Covers: `.metis-skill` on-disk
   layout, version + dependency resolution, signing posture.

### Coordination risks

- **M15 (Pro tier + launch, Draft needed)** depends on the
  Forge being live before launch. `plans/pro-tier-launch/plan.md`
  mentions "the Forge" directly as part of what Pro earns.
  Scope M14 tight — six phases of "technique gallery +
  toggles + candidate review + trace + export" is already
  the right scope for v1. If M15 slips on M14 because we
  scope-creep a marketplace into M14, we lose a quarter. The
  Pro-tier plan doc calls out that a "what METIS learned
  this week" newsletter needs M13 + M16 as content — the Forge
  doesn't need to source that content, just exhibit it.
- **M06 (Skill self-evolution, Ready)** is the writer of
  skill candidates. Phase 5 is the reader. Specify the
  `SkillCandidate` → `skills/<id>/SKILL.md` translator as a
  single module (`metis_app/services/skill_promoter.py`?)
  and reference it from both M06's promoter and the Forge's
  accept handler so neither side re-implements the logic.
- **M02 (Landed)** — reuse the design system. Do not introduce
  a separate visual language for the Forge. The
  `border-beam` + `tooltip` + `animated-lucide-icon` primitives
  are the house style now.
- **M12 (Interactive star catalogue, Ready)** — Phase 2
  proposes each active technique gets a star in the
  constellation. Coordinate with M12's star-catalogue data
  model so techniques appear under a "Skills" faculty sector
  cleanly. Share the `StarCatalogue` + `name-gen` modules
  M12 Phase 1 landed on 2026-04-19.
- **M11 (Agent-native state, Landed)** — the KV store is
  available for ephemeral UI state (card expansion, "what's
  new" badges). Do not abuse it for what belongs in the
  settings store (global technique on/off lives in
  settings; per-view UI state lives in KV).
- **M13 (Seedling + Feed, Draft)** — the overnight reflection
  writes skill candidates (Phase 4 of M13's plan). The Forge
  reads them (Phase 5 here). If M13's writer lands before
  this milestone's reader, candidates accumulate unread —
  that's fine, they'll be there when the Forge ships. If the
  Forge ships first, the candidate pane shows an empty state
  until the Seedling is live, which is also fine.
- **M01 (Preserve & productise, Rolling)** — the harvest
  audit in this plan (see *Harvest inventory* above)
  contributes to M01's "cut dead paths" goal. Any
  technique row that fails the honest-description test is
  either fixed or cut. The Forge is a forcing function for
  the preserve-and-productise pass; claim the overlap.
- **VISION.md principle #4 conflict.** "Skills over settings"
  means every new capability arrives as a skill, and the
  settings page does not grow. The Forge is the *opposite
  of* the settings page in UX intent — it's the surface
  where capabilities arrive ceremonially. But if we build it
  lazily, it looks like settings-with-icons. The guard:
  every Forge card must frame its toggle as *"accepting a
  capability"*, not *"enabling a feature"*. The companion
  dock event after a toggle matters as much as the toggle
  itself.

### What NOT to do in M14

- **Don't build a cross-user marketplace.** Revenue share
  (VISION.md's "creators earn 80%") is post-M15, probably
  post-Lifetime-tier. Leaving a greyed-out share button with
  a roadmap tooltip is the most this phase ships.
- **Don't promise SDK-level extensibility.** VISION.md is
  explicit: "Not a platform before it is a product. Any SDK
  is years out." (*What we are explicitly not doing*.) The
  Forge does not expose a technique-registration API to
  third-party code. Skills are YAML-frontmatter files with
  config overrides, nothing more.
- **Don't run untrusted code from arXiv links.** Phase 4
  produces a proposal *document* and optionally a skill
  draft, not executable anything.
- **Don't gate basic techniques behind Pro.** VISION.md's
  Free tier gets "full local features". Every technique in
  the harvest inventory is a local feature. What *is* Pro-
  only: unlimited constellations, autonomous research cron,
  forecast mode, PPTX export, **the Forge's skill-marketplace
  tab** (once that's a thing), priority presets. The Forge
  *itself* — gallery + toggles + candidate review + trace —
  is free. The marketplace is Pro. Say this in ADR 0010 so
  M15 doesn't have to re-litigate it.
- **Don't become a second settings page.** If the Forge's
  toggles have identical affordance to settings page
  toggles, the milestone fails its own pitch. The Forge
  is a *gallery* — cards, pillars, pre-flight readiness,
  dock event on activation, star in the constellation on
  enable. Settings is a *form* — dense sliders, small type,
  advanced users only. Different surfaces, different jobs.
- **Don't crowd the home page.** The Forge is reached via
  nav or via a star in the constellation's "Skills" sector.
  It is not a panel on `app/page.tsx`.
- **Don't duplicate skill infrastructure.** `skills/` +
  `settings["skills"]["enabled"]` + `skill_repository.py`
  is the existing skill layer. The Forge consumes it; it
  does not fork it.

### Key files the next agent will touch

Backend:
- `metis_app/services/forge_registry.py` *(new — `TechniqueDescriptor` dataclass, static registry)*
- `metis_app/services/skill_promoter.py` *(new — candidate → skill file writer; shared with M06)*
- `metis_app/api_litestar/routes/forge.py` *(new — `/v1/forge/*` routes)*
- `metis_app/api_litestar/app.py` *(mount the new routes)*
- `metis_app/services/skill_repository.py` *(add rejection bookkeeping; do not duplicate candidate logic)*
- `metis_app/services/trace_store.py` *(extend with technique-filtered query for Phase 6)*
- `metis_app/default_settings.json` *(no new keys in Phase 1–2; possibly `forge_*` keys in Phase 4)*

Frontend:
- `apps/metis-web/app/forge/page.tsx` *(new)*
- `apps/metis-web/app/forge/loading.tsx` *(new)*
- `apps/metis-web/app/forge/[technique]/page.tsx` *(new; only if ADR 0010 picks per-technique routes)*
- `apps/metis-web/components/forge/technique-card.tsx` *(new)*
- `apps/metis-web/components/forge/technique-gallery.tsx` *(new)*
- `apps/metis-web/components/forge/absorb-arxiv.tsx` *(new, Phase 4)*
- `apps/metis-web/components/forge/candidate-review.tsx` *(new, Phase 5)*
- `apps/metis-web/components/shell/page-chrome.tsx` *(nav entry)*
- `apps/metis-web/components/shell/metis-companion-dock.tsx` *(consume `technique_toggled` events — no change if pub/sub is generic)*
- `apps/metis-web/lib/api.ts` *(add `TechniqueDescriptor`, `fetchForgeTechniques`, `absorbArxivUrl`, `listSkillCandidates`, `acceptSkillCandidate`; extend `CompanionActivityEvent.source` with `"forge"`)*
- `apps/metis-web/components/constellation/star-observatory-dialog.tsx` *(Phase 2 — recognise technique stars, deep-link to `/forge#<id>`)*

ADRs (new):
- `docs/adr/0010-forge-route-and-toggle-state.md`
- `docs/adr/0011-skill-candidate-acceptance.md`
- optionally `docs/adr/0012-metis-skill-bundle-format.md`

### Prior art to read before starting

- `VISION.md` — especially the *Cortex* pillar section, *Product
  principles* 3 and 4, *Business model* (Pro tier row), *Next —
  the Forge* paragraph, and *What we are explicitly not doing*.
- `plans/seedling-and-feed/plan.md` — the companion-side of
  the same growth story; the Forge shows the user what the
  Seedling has absorbed.
- `plans/pro-tier-launch/plan.md` — the Forge is one of the
  named Pro deliverables; stay in sync.
- `plans/companion-realtime-visibility/plan.md` — the
  `CompanionActivityEvent` pub/sub template.
- `docs/adr/0005-product-vision-living-ai-workspace.md` —
  the vision ADR. Any Forge decision must pass its smell test.
- `docs/adr/0006-constellation-design-2d-primary.md` — for
  how Phase 2's technique stars fit the 2D archetype language.
- `skills/qa-core/SKILL.md` and `skills/swarm-critique/SKILL.md`
  — two of the nine shipped skills. The Forge must not break
  them; its accept-a-candidate writer must produce the same
  YAML shape.
- `metis_app/default_settings.json` top to bottom — this file
  *is* the technique inventory, pre-Forge.
- `metis_app/services/skill_repository.py` — read end to end.
  The Forge is mostly a UI over what's already here.
