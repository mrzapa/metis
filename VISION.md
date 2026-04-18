# METIS — Vision

> **The Cognitive Cosmos.**
> A private, local-first AI companion that turns everything you read, watch, and think into a living universe you can navigate — and grows alongside you.

---

## Why this exists

The last three years produced two kinds of AI products:

1. **Cloud chat** — ChatGPT, Claude, Perplexity. Powerful, general, and built on the assumption that your data can leave your machine.
2. **Cloud workspaces** — Notion AI, Glean, Mem. Competent retrieval on top of documents you've already handed to a vendor.

Neither option works for people whose knowledge is the *product*: analysts, researchers, consultants, lawyers, clinicians, investigators, IP-sensitive professionals. For them, every prompt is a leak risk and every vendor is a lock-out.

METIS exists for them. The bet is simple: there is a durable market for an AI workspace that is private by default, beautiful enough to be loved, and rich enough to compete on capability — not just on "we don't train on your data."

## What METIS is

METIS is three things fused into one product:

- **Cosmos** — every document, paper, podcast, video, conversation, and note you drop into METIS becomes a *star* in a navigable 3D universe. Stars are placed by faculty (Perception, Knowledge, Memory, Reasoning, Skills, Strategy, Personality, Values). Indexes, sessions, and topics become constellations. The graph is not decoration; it is the primary navigation.

- **Companion** — a persistent AI entity that lives in the workspace shell. It has an identity that bootstraps on first run, an Atlas of episodic memories that persists across sessions, a reflection loop that runs in the background, and an autonomous-research mode that follows its own curiosity while you work. Over months, it becomes *yours*.

- **Cortex** — a research-grade RAG engine with five tuned modes (Q&A, Summary, Tutor, Research, Evidence Pack), hybrid retrieval, sub-query expansion, iterative agentic refinement with convergence-based early-stopping, skills that auto-evolve from your own traces, and a trace timeline that makes every retrieval decision inspectable.

All of it runs locally. Every layer — LLM, embeddings, vector store — is swappable. With a local GGUF model, METIS works on an airplane.

## Who it is for

**Primary wedge (first 12 months):**

- **Independent analysts and boutique researchers** — earnings prep, sector reports, competitive intelligence. Forecast mode (TimesFM 2.5) and Evidence Pack → PPTX match their actual deliverables.

**Secondary expansions (12–24 months):**

- **Academic researchers** — paper ingestion, Tutor mode, multimodal lectures, knowledge graph densification over time.
- **Legal and compliance teams** — discovery, due diligence, claim-level grounding, audit-ready citation trails.
- **Regulated enterprise** — defense, finance, healthcare, government. On-prem, local-only, SSO.

We do not try to be ChatGPT. We do not try to be Notion. We try to be the private, intelligent workspace that a professional chooses for life.

## Why METIS wins

Five moats, all already partially built:

1. **The constellation UI.** A WebGL starfield with LOD rendering, a Three.js brain graph that subscribes to live retrieval activity, a Star Observatory with ML-suggested archetypes and learning-route planning, and news/activity rendered as animated comets. No competitor in the RAG or second-brain space has anything close. It is brand and product simultaneously.
2. **The companion with identity and memory.** Persistent Hermes HUD, Atlas episodic memory, reflection cycles, autonomous research, WebGPU-backed local embeddings. The "AI that actually knows me" substrate that most startups are raising rounds to build.
3. **The skill system.** YAML-defined, triggered passively by query shape and file type, tunable per-mode, and — on the roadmap — self-evolving from high-convergence traces. A declarative personalisation layer that replaces a wall of toggles.
4. **Research-grade retrieval.** Five modes with independent tuning, hybrid BM25 + semantic retrieval, MMR, reranker, sub-query expansion, IterRAG convergence, swarm persona simulation, and Tribev2 multimodal faculty classification. Trace timeline makes every decision inspectable.
5. **Local-first with no vendor lock-in.** Tauri, SQLite, local GGUF, factory pattern for every provider. The only serious private AI workspace on the market.

Individually, any one of these is catchable. Together, they are a product nobody else is building.

## Product principles

1. **Private by default. Never by apology.** Local, encrypted, portable. Sync is opt-in and end-to-end encrypted. No telemetry without explicit consent.
2. **Beauty is a feature.** The constellation is not decoration. If a surface is not beautiful, it is not finished.
3. **The companion grows.** Every session leaves the companion smarter about you, not about everyone.
4. **Skills over settings.** New capabilities arrive as skills that auto-activate; we do not grow the settings page.
5. **Trace everything.** Every retrieval, every reflection, every agentic iteration is inspectable. Transparency is the antidote to hallucination.
6. **Preserve and productise.** The codebase is an asset. We surface what exists before we build what does not.
7. **One interface.** Next.js in Tauri, backed by a local Litestar API. No Qt, no Electron, no browser-only mode (per ADR 0004).

## Business model

A freemium ladder where the business-model unlock is encrypted sync for teams.

| Tier | Price | For | Delivers |
|------|-------|-----|----------|
| **Solo — Free** | $0 | Individual experimentation | Full local features, one active constellation, community models |
| **Solo — Pro** | $29/mo | Power users | Unlimited constellations, companion autonomous research, forecast mode, PPTX export, skill marketplace, priority presets |
| **Team** | $79/seat/mo | Research groups, boutique firms | Everything in Pro + end-to-end encrypted constellation sync, shared skills, team-scoped Atlas memory |
| **Enterprise** | Custom | Regulated industries | On-prem, SSO, audit log, managed GGUF inference, dedicated skill engineering, SLAs |

Optional long-tail (18–24 months): **METIS Platform.** Open the Skills SDK and Atlas memory API so other applications can embed persistent companions. Memory-as-a-service for the next wave of agentic apps.

## Roadmap (next 12 months)

**Q1 — Preserve and productise.**
Finish the preserve-and-productize plan. Ship IterRAG convergence. Wire the companion into evidence and trace surfaces so it visibly reflects on active work. Kill or flag-gate dead surfaces (Qt refs, metis-reflex, metis-web-lite, Heretic). Onboarding path: three minutes to first magic moment.

**Q2 — "METIS for Analysts" showcase.**
Opinionated persona onboarding. Forecast + Research + Evidence Pack → PPTX pre-tuned end-to-end. First skill pack shipped. Pro tier launch.

**Q3 — Skill marketplace and self-evolution.**
Ship roadmap Phase 3 (skills auto-generated from high-convergence traces). Public skill sharing. This creates the network effect a local-first product normally lacks.

**Q4 — Encrypted team sync.**
CRDT-based constellation sync, end-to-end encrypted. Team tier launch. The moment METIS becomes a business, not a beautiful app.

## What we are explicitly not doing

- Not a general-purpose chat assistant. ChatGPT owns that.
- Not a Notion competitor. Docs-as-pages is not the metaphor.
- Not a cloud-first product with a local fallback. Local-first is the product.
- Not a platform before it is a product. Skills SDK is year two, not year one.
- Not adding capabilities that cannot be reached from the constellation. If it has no star, it does not ship.

## Risks and honest tradeoffs

- **Privacy + local + beauty may be a niche, not a mass market.** The hedge is to own the lucrative niche (regulated professions) rather than fight ChatGPT and Perplexity for general knowledge work.
- **The codebase has ~10 partially-finished sophisticated systems.** The highest-leverage act for the next quarter is *cutting* three of them, not adding new ones.
- **The companion is the biggest emotional moat and the biggest execution risk.** If it feels dumb or forgetful, the whole pitch collapses. Memory quality, identity persistence, and the "does it actually know me" feel must be invested in disproportionately.

## One-line summary

**METIS is the private AI workspace for people whose knowledge is their product — a cognitive cosmos they navigate, inhabited by a companion that grows with them.**
