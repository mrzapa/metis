# 0005 - Product Vision: The Living AI Workspace

- **Status:** Draft
- **Date:** 2026-04-18

## Context

METIS has accumulated substantial capability across years of iteration: a
WebGL constellation home with 8-faculty archetypes, a Three.js brain graph
that subscribes to live retrieval activity, a persistent Hermes HUD /
companion dock with Atlas episodic memory and autonomous research, five
tuned RAG modes, hybrid retrieval with MMR and reranking, IterRAG convergence
on the roadmap, skill self-evolution on the roadmap, Tribev2 multimodal
faculty classification, TimesFM 2.5 forecasting, swarm persona simulation,
Heretic model abliteration, news-comet ingest, a trace timeline, and more.

The problem has never been capability. The problem is that without a clear
product vision, the maximalist codebase reads as incoherent rather than
differentiated. "Local-first RAG workspace" undersells what exists and puts
METIS in direct commodity competition with Jan, LM Studio, AnythingLLM,
Notion AI, and Obsidian plugins.

The founder's stated values additionally shape the positioning: this is a
lifestyle business, not a venture-scale bet; user freedom is a core value;
the maximalism is intentional; the goal is an accessible playground for
frontier AI techniques — not a corporate research platform.

## Proposed Direction

METIS is positioned as **The Living AI Workspace** — a workspace where a
small, always-on local AI companion takes root, grows from what the user
feeds it, and blooms into something no cloud chatbot can match.

Tagline: **Grow an AI that actually knows you.**
Theme: **Intelligence grown, not bought.**

The product is expressed through three pillars, each mapped to existing
capability:

| Pillar | Product meaning | Existing substrate |
|--------|------------------|---------------------|
| 🌌 **Cosmos** | Knowledge as a navigable universe; every source becomes a star placed by faculty | Landing starfield, constellation home, brain graph, star observatory, comets |
| 🌱 **Companion** | Persistent local AI that lives, remembers, reflects, and grows with visible stages | Hermes HUD, Atlas, assistant repository, reflection loop, autonomous research stream |
| 🧠 **Cortex** | Every frontier AI technique, plug-and-play | Skill system, IterRAG, swarm, Tribev2, Heretic, TimesFM, trace timeline |

The pivotal new surface is the **Seedling** — a small, quantized local LLM
running as a background worker, continuously ingesting news/RSS/user
documents (leveraging the existing news-comet infrastructure), reflecting
overnight, and visibly growing through stages (Seedling → Sapling → Bloom →
Elder). Accompanied by the **Forge**: a one-click technique gallery where
every frontier method in the codebase becomes a togglable module a user can
graft into their companion.

Audience: AI-curious users broadly — indie writers, hobbyist researchers,
autodidacts, tinkerers, the r/LocalLLaMA crowd, privacy-minded professionals.
Not regulated industries, not enterprise.

Monetisation: lifestyle-business ladder (Free → Pro $29/mo → Lifetime $499 →
optional Supporter $10/mo). No team tier. No enterprise. No venture capital.
Revenue target: $200–400k/yr solo.

Full narrative in [VISION.md](../../VISION.md).

## Because

- **Capability fusion is the moat, not capability addition.** Cosmos,
  Companion, and Cortex, fused in a beautiful local workspace, is a slot
  nobody else is in. Jan/LM Studio/AnythingLLM are stateless. Notion/Mem/
  ChatGPT are remote. None grow.
- **The "companion that grows" hook is emotionally sticky.** The switching
  cost becomes the AI itself. Months of compounded memory, skills, and
  personalisation cannot be replicated by a competitor.
- **The Forge turns every weird experiment into a feature.** Heretic, Swarm,
  Tribev2, TimesFM stop being loose side projects and become nutrients for
  companion growth. Maximalism becomes the product.
- **The democratic angle is real.** A curious user with a laptop can end up
  with a companion nobody else has. That story travels.
- **The constellation UI cannot be cloned quickly.** WebGL spatial indexing,
  Three.js force-directed brain graph, Star Observatory — years of work
  constitute a genuine brand and UX moat.
- **Freedom without ideology.** "Local by default, every layer swappable,
  every call inspectable" is a concrete promise users care about. The word
  "sovereign" was considered and rejected as too grievance-coded; freedom
  to experiment reads as permission rather than protest.
- **Lifestyle-business shape matches founder intent.** No team tier, no
  enterprise, no VC, no employees until the founder decides. Pricing and
  scope are designed for a solo operator making a very good living.

## Constraints

- Must not break ADR 0004 (one interface: Next.js + Tauri + Litestar).
- Must preserve local-first and offline capability as non-negotiable. Cloud
  features (sync, marketplace) are opt-in and end-to-end encrypted.
- Must preserve existing load-bearing surfaces identified in
  `preserve-and-productize-plan.md` (five modes, session persistence,
  citation tracking, multi-provider factories, skill runtime, local GGUF).
- Must not introduce user-identity infrastructure for the core product.
  Everything is local and single-user.
- Every new capability must be reachable from the constellation. If it has
  no star, it does not ship.
- No quarterly delivery targets — development is sprint-paced. Priorities
  are ordered, not calendared.

## Alternatives Considered

- **"The Cognitive Cosmos" / analyst wedge (earlier draft of this ADR).**
  Rejected. Too enterprise-coded, too narrow, incompatible with the
  Heretic/abliteration values and lifestyle-business shape.
- **"The Sovereign Second Brain" / sovereignty framing.** Rejected on tone.
  "Sovereign" reads as grievance; "freedom to experiment" reads as permission.
  Core values preserved, language softened.
- **"Advanced RAG workspace" / generic framing.** Rejected. Commoditised,
  undersells the constellation and companion work, puts METIS in direct
  competition with Glean / Notion AI where it cannot win.
- **"The Grimoire" / game-mechanic framing.** Considered. Taglines like "AI
  techniques are spells your companion learns" have flavour, but risk
  being read as unserious unless fully committed to game mechanics. Light
  game-feel (growth stages, milestones) is adopted; heavy grimoire
  aesthetics are not.
- **Vertical-only pivot (e.g. "METIS for Analysts" as the whole product).**
  Rejected. Incompatible with the maximalist playground positioning. A
  specific persona launch may still be useful as a marketing wedge later.
- **Platform-first (open Skills SDK + Atlas API early).** Rejected.
  Platform without a proven product is a developer tool with no users.

## Consequences

**Accepted:**

- `VISION.md` becomes the canonical pitch. Top-level README is rewritten
  over time to align.
- Preserve-and-productize plan gains a clear north star: preserve what
  serves Cosmos / Companion / Cortex; retire or flag-gate what does not.
- Dead or orphaned surfaces are scheduled for removal or opt-in gating:
  Qt references, `apps/metis-reflex/`, `apps/metis-web-lite/`.
- Heretic is **not** deprecated. It becomes a first-class Cortex module
  in the Forge — "use abliterated open-weight models if you want to."
- Two major new surfaces enter the roadmap: **the Seedling** (small
  always-on local LLM with visible growth) and **the Forge** (one-click
  technique gallery).
- Development is sprint-paced. Work is prioritised in order, not by
  quarter. VISION.md and this ADR therefore describe sequence, not
  calendar.
- The companion becomes a first-class product object, not a dock widget.
  Memory quality, identity persistence, and "does it actually know me"
  feel are invested in disproportionately.
- Growth-feel becomes a visible product surface (stages, personal evals,
  morning "here's what I learned overnight" report). If the companion
  doesn't visibly grow, the pitch collapses.
- LoRA fine-tuning on user data is an explicit **stretch goal**, not a
  shipped promise. The default growth story is system-level (skills,
  memory, retrieval), not weight-level.

**Open tradeoffs:**

- The small-LLM-that-lives is the most technically ambitious claim in the
  pitch. Mitigation: the *system* learns by default (skills, memory,
  traces → skills); weight-level learning is a stretch goal clearly
  labelled as such.
- Ten partially-finished sophisticated systems exist; cutting three of
  them is higher-leverage than adding new ones. The Forge becomes the
  arbiter — techniques that earn a slot survive, others are flag-gated
  or removed.
- Solo-founder capacity is finite. Sprinting works but is cuttable; any
  item above the explicit stretch line can slip without breaking the
  pitch, as long as preserve-and-productise holds.

## Open Questions

- **Which small local LLM powers the Seedling by default.** Phi-class,
  Llama-3.2-1B-Instruct, Qwen-2.5-1.5B, or a dynamic choice based on
  available hardware. Decision required before Seedling implementation.
- **How the Forge exposes techniques.** Grid of cards? Archetype tags?
  Paste-an-arXiv-link workflow? UX exploration required. Possibly a
  separate ADR once the design is closer.
- **What "visible growth" looks like concretely.** Companion stages
  (Seedling/Sapling/Bloom/Elder) vs. skill count vs. brain-graph density
  vs. all of the above. Needs design iteration.
- **Skill marketplace governance.** Community-submitted skills could ingest
  untrusted runtime overrides. Trust, review, and signing model needs its
  own ADR before the marketplace opens.
- **Which existing experiments to retire.** Swarm, Heretic, news-comet,
  Nyx runtime, forecasting — each needs an explicit survive / flag-gate /
  retire call via the Forge lens. Decision required in the preserve-and-
  productise cycle.
- **Pricing validation.** $29 / $499 / $10 is the proposed ladder.
  Requires at least 20 design-partner conversations before the Pro tier
  public launch to confirm.
- **Whether LoRA fine-tuning on user data is attemptable solo.** GPU
  requirements, eval harness, catastrophic-forgetting mitigation all
  nontrivial. May need to remain a stretch goal indefinitely.
- **Relationship to existing plans** (`docs/plan/2026-04-01-hermes-sotaku-
  roadmap-design.md`, `preserve-and-productize-plan.md`, `docs/plans/`).
  Compatible with this ADR but should be re-titled or cross-linked so the
  narrative threads are discoverable.
