# 0005 - Product Vision: The Cognitive Cosmos

- **Status:** Draft
- **Date:** 2026-04-18

## Context

METIS has accumulated substantial capability across four years of iteration: a
WebGL constellation home with 8-faculty archetypes, a Three.js brain graph
that subscribes to live retrieval activity, a persistent Hermes HUD / companion
dock with Atlas episodic memory and autonomous research, five tuned RAG modes,
hybrid retrieval with MMR and reranking, IterRAG convergence on the roadmap,
skill self-evolution on the roadmap, Tribev2 multimodal faculty classification,
TimesFM 2.5 forecasting, swarm persona simulation, and a trace timeline with
stage-colored JSON payload inspection.

The problem is not capability. The problem is that no single product story
binds these capabilities together, so the pitch has defaulted to "local-first
RAG workspace" — which undersells what has been built and puts METIS in direct
commodity competition with Glean, Mem, Notion AI, and Obsidian+LLM.

Without a clear product vision, three risks compound:

1. New features are built against an implicit positioning that is not shared,
   producing surfaces that do not reinforce each other (Nyx catalog, Heretic
   abliteration, news comet ingest, swarm service).
2. The preserve-and-productize plan has no north star against which to decide
   what to preserve, what to surface, and what to retire.
3. The codebase cannot be monetised without a defensible positioning that
   justifies paid tiers against free cloud alternatives.

## Proposed Direction

METIS is positioned as **The Cognitive Cosmos**: a private, local-first AI
companion that turns everything a user reads, watches, and thinks into a
navigable universe — and grows alongside them.

The product is expressed through three pillars, each mapped to existing
capability:

| Pillar | Product meaning | Existing substrate |
|--------|------------------|---------------------|
| **Cosmos** | Every source becomes a star, placed by faculty, navigable in 3D | Landing starfield, constellation home, brain graph, star observatory, comets |
| **Companion** | A persistent AI entity with identity, memory, and reflection that lives with the user for years | Hermes HUD, Atlas, assistant repository, reflection loop, autonomous research stream |
| **Cortex** | Research-grade RAG with 5 modes, agentic convergence, and skills that evolve from the user's own traces | Skill system, IterRAG roadmap, swarm service, Tribev2, trace timeline |

Primary wedge for the first 12 months: **independent analysts and boutique
research firms.** Forecast mode, Research mode, and Evidence Pack → PPTX match
their actual deliverables and justify a paid tier against cloud alternatives.

Secondary expansions (12–24 months): academic researchers, legal and
compliance teams, regulated enterprise (defense, finance, healthcare, gov).

Monetisation is a freemium ladder (Solo Free → Solo Pro → Team → Enterprise)
with the business-model unlock being **end-to-end encrypted constellation sync
for teams**. Optional long-tail: a Skills SDK and Atlas memory platform
(18–24 months).

Full narrative in [VISION.md](../../VISION.md).

## Because

- **Capability fusion, not capability addition, is the differentiated move.**
  Individual pillars are catchable; all three fused and running locally is not.
- **Local-first is a durable wedge in regulated verticals.** Cloud AI is a
  lock-out for legal, medical, defense, finance, and IP-sensitive work. No
  other AI workspace competes seriously here.
- **The constellation UI is a brand asset that cannot be cloned quickly.**
  Years of WebGL, Three.js, faculty-archetype design, and force-directed
  graph work constitute a real moat.
- **The companion is already architecturally persistent.** Atlas, reflection,
  autonomous research, and WebGPU-backed local embedding infrastructure exist.
  Competitors are raising rounds to build this.
- **The skill system plus IterRAG plus self-evolution is a unique personalisation
  path.** It replaces settings sprawl with declarative behaviour that tunes to
  the user over time.
- **A single positioning lets the preserve-and-productize plan prune
  confidently.** Anything that does not serve Cosmos, Companion, or Cortex is a
  candidate for flag-gating or removal.

## Constraints

- Must not break ADR 0004 (one interface: Next.js + Tauri + Litestar).
- Must preserve local-first and offline capability as non-negotiable. Cloud
  services (sync, marketplace) are opt-in and end-to-end encrypted.
- Must preserve existing paid and load-bearing product surfaces identified in
  `preserve-and-productize-plan.md` (five modes, session persistence,
  citation tracking, multi-provider factories, skill runtime, local GGUF).
- Must not introduce user-identity infrastructure on the solo tier. Identity
  arrives with the Team tier and only for sync scope.
- Every new capability must be reachable from the constellation. If it has no
  star, it does not ship.

## Alternatives Considered

- **"Advanced RAG workspace."** Rejected. Generic, commoditised, and
  undersells the constellation and companion work. Puts METIS in direct
  commodity competition with Glean and Notion AI.
- **"AI-native knowledge graph / second brain."** Rejected. Too close to
  Obsidian + LLM and Mem; does not explain why local-first and the companion
  matter.
- **"Private ChatGPT alternative."** Rejected. Competes on commodity chat
  where ChatGPT, Claude, and Perplexity are vastly better resourced.
- **Platform-first (open Skills SDK + Atlas API in year one).** Rejected.
  Platform without an opinionated product is a developer-tool with no users.
  Platform arrives in year two, built on a proven product.
- **Vertical-only pivot (e.g. "METIS for Law" as the whole product).**
  Rejected as a starting constraint but embraced as a *sequencing* tactic.
  Vertical showcases are how the horizontal product gets sold.

## Consequences

**Accepted:**

- `VISION.md` becomes the canonical pitch document. Top-level README is
  rewritten over time to align.
- Preserve-and-productize plan gains a north star: preserve what serves
  Cosmos / Companion / Cortex; retire or flag-gate what does not.
- Dead or orphaned surfaces are scheduled for removal or opt-in gating:
  Qt references, `apps/metis-reflex/`, `apps/metis-web-lite/`, Heretic
  abliteration (to `scripts/` or `METIS_ENABLE_HERETIC` flag), `RunEvent`
  duplicate (consolidate with `TraceEvent`).
- Sequencing decisions are made by quarter (see VISION.md "Roadmap").
  IterRAG convergence ships in Q1, "METIS for Analysts" showcase in Q2,
  skill marketplace and self-evolution in Q3, encrypted team sync in Q4.
- The companion becomes a first-class object, not a dock widget. Identity,
  memory quality, and reflection feel are invested in disproportionately.

**Open tradeoffs:**

- Privacy + local + beauty may be a niche rather than a mass market. The
  hedge is to own the lucrative niche (regulated professions) rather than
  compete for general knowledge work.
- Ten partially-finished sophisticated systems exist; the highest-leverage
  next act is *cutting* three of them, not adding new ones. This will
  generate friction with contributors attached to specific experiments.
- "Preserve and productise" slows net-new feature velocity for ~1 quarter.

## Open Questions

- **Vertical showcase selection.** Analysts is the proposed Q2 showcase, but
  legal/academic/regulated each have plausible cases. Decision due before
  Q2 kickoff.
- **Sync architecture.** CRDT-based end-to-end encrypted sync is the stated
  direction. Specific CRDT library, key-management model, and conflict-
  resolution surface (UI) remain open. Separate ADR required before Q4.
- **Skill marketplace governance.** Community-submitted skills could ingest
  untrusted runtime overrides. Trust, review, and signing model needs its
  own ADR before Q3.
- **Which of swarm, Heretic, news comets, Nyx runtime to retire.** At most
  one should survive into the shipped product pitch. Decision due before
  end of Q1.
- **Pricing validation.** $29 / $79 / custom is the proposed ladder.
  Requires at least 20 design-partner conversations before the Q2 launch
  to confirm.
- **Relationship to existing `docs/plan/2026-04-01-hermes-sotaku-roadmap-design.md`
  and `docs/plans/` documents.** These are compatible with this ADR but
  should be re-titled or cross-linked so the narrative threads are
  discoverable.
