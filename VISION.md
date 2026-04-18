# METIS — Vision

> **Grow an AI that actually knows you.**
>
> A living workspace where a small AI companion takes root, learns from your life, and blooms into something no cloud chatbot can match.

---

## What METIS is

METIS is a **living AI workspace**. Not a chat app. Not a notes app. Not a RAG tool. A workspace where an AI companion lives inside your machine, grows from what you feed it, and becomes — slowly, compoundingly, unmistakably — *yours*.

You drop in documents, papers, podcasts, videos. They take root as stars in a navigable cosmos. A small, always-on local model watches, reads, reflects, and remembers. When a new technique from the AI frontier catches your eye — IterRAG, Swarm, Heretic, multimodal faculty extraction, time-series forecasting — you graft it in. The companion learns to use it. Over weeks and months, what started as a blank workspace becomes an intelligence grown on your life.

Every layer is swappable. Every capability is inspectable. Everything runs locally. METIS works on an airplane.

## The pitch in one line

**Every other AI product rents you a stranger's mind. METIS grows one with you.**

## The three pillars

Every capability in the codebase lives under one of three:

### 🌌 Cosmos — your knowledge as a universe
Every document, paper, podcast, video, tweet, and note becomes a *star*. Stars are placed by faculty (Perception, Knowledge, Memory, Reasoning, Skills, Strategy, Personality, Values). Indexes become constellations. Live activity renders as comets. Individual stars open into a Star Observatory where you assign archetypes, plan learning routes, and link sources. The constellation is the primary navigation — not decoration.

### 🌱 Companion — an AI that grows
The beating heart of METIS. A persistent local AI entity that bootstraps an identity on first run, keeps an Atlas of episodic memories, runs reflection loops in the background, and follows its own curiosity when you're away. It ingests news feeds, RSS, podcasts, and your documents as continuous nutrients. It has visible growth stages. Over months, its brain graph densifies and its skills accumulate until it knows your thinking better than any cloud assistant ever could.

### 🧠 Cortex — every frontier technique, plug and play
Five tuned modes (Q&A, Summary, Tutor, Research, Evidence Pack). Hybrid retrieval with MMR and reranking. Sub-query decomposition. IterRAG convergence for agentic refinement. Swarm persona simulation. Tribev2 multimodal faculty classification for audio, video, images. TimesFM 2.5 forecasting. Heretic abliteration for uncensored open-weight models. A trace timeline that makes every retrieval, reflection, and agentic iteration inspectable. Any LLM, any embedder, any vector store.

Most AI products have one of these done well. METIS has all three, fused, local, beautiful.

## How an AI grows in METIS

The promise is simple: every day, your companion gets smarter — about you, not about everyone.

- **Feed it.** Drop documents, paste URLs, subscribe to RSS, point it at a podcast feed. The news-comet service streams fresh signal continuously.
- **Graft in techniques.** Browse the Forge — a gallery of frontier AI techniques as togglable modules. IterRAG convergence, swarm simulation, multimodal ingestion, abliterated models, sub-query expansion. Paste an arXiv link, get a new skill.
- **Let it dream.** Overnight, the companion reflects. Candidate skills emerge from high-convergence traces. Memory consolidates. In the morning, it proposes what it learned.
- **Watch it grow.** Companion stages (Seedling → Sapling → Bloom → Elder) track knowledge density, skill count, reflection depth. The brain graph densifies visibly. Personal evals track how the companion is getting better at *your* specific tasks.
- **Keep it yours.** Nothing phones home. Every call is inspectable. The weights, the memory, the graph — all portable, all on your machine.

The stretch goal: overnight LoRA fine-tuning on your data. Not promised on day one, because real continual learning is hard. But it's a goal — the moment the companion's *weights* adapt to you, not just its behaviour, METIS becomes genuinely uncloneable.

## Why this wins

- **Nobody else does this.** Jan, LM Studio, Open WebUI, AnythingLLM are stateless per-session. Notion AI, ChatGPT, Perplexity are stateless and off-premise. None grow. None live. None compound.
- **The constellation UI.** WebGL starfield with LOD and spatial indexing, Three.js brain graph subscribing to live retrieval, Star Observatory, comets. No competitor has anything close. Brand and product simultaneously.
- **Emotionally sticky.** You don't leave an AI you grew. The switching cost is the AI itself.
- **Democratic.** No PhD needed. No fine-tuning knowledge. Plug in, feed it, watch. A curious dad with a laptop can end up with a companion nobody else has.
- **Every weird capability pays off.** Heretic, Swarm, Tribev2, TimesFM — these stop being loose experiments and start being *nutrients* for the companion's growth. Maximalism becomes the feature.

## Who it is for

Anyone who has ever thought *I wish I could just try that* about an AI paper, trick, or technique. Anyone who wants an AI that feels like *theirs* rather than rented by the month. Concretely:

- AI-curious professionals who don't code
- Indie writers, fiction authors, creators
- Hobbyist researchers, autodidacts, students
- Homelabbers, tinkerers, r/LocalLLaMA regulars
- Privacy people — already paying for Obsidian, Kagi, Mullvad, Proton, Framework
- Anyone whose knowledge is their work product and doesn't want it on someone else's servers

**Not a target:** Regulated-industry compliance buyers, enterprise procurement, anyone who needs SOC 2 on day one. Those pitches are incompatible with Heretic and the living-companion ethos. We don't chase them.

## Product principles

1. **Intelligence grown, not bought.** Every session leaves the companion smarter about you. Growth is the product.
2. **Beauty is a feature.** The constellation is not decoration. If a surface is not beautiful, it is not finished.
3. **Every technique, plug and play.** If it's in the codebase, it's one click away. The Forge is how new capabilities arrive.
4. **Skills over settings.** New capabilities arrive as skills that auto-activate. The settings page does not grow.
5. **Trace everything.** Every retrieval, reflection, and iteration is inspectable. Transparency is the antidote to hallucination.
6. **Local by default. Always.** Nothing phones home without explicit consent. Cloud features are opt-in and end-to-end encrypted.
7. **Preserve and productise.** The codebase is an asset. Surface what exists before building what doesn't.
8. **One interface.** Next.js in Tauri, backed by a local Litestar API (per ADR 0004).
9. **No capability without a star.** If a feature has no home in the constellation, it doesn't ship.

## Business model

A lifestyle business. No team tier. No enterprise. No employees unless the founder decides otherwise. No venture capital.

| Tier | Price | What you get |
|------|-------|--------------|
| **Free** | $0 | Full local features, one active constellation, community models. Free forever. |
| **Pro** | $29/mo · $290/yr | Unlimited constellations, companion autonomous research, forecast mode, PPTX export, the Forge, skill marketplace, priority presets |
| **Lifetime** | $499 one-time | Everything in Pro, forever. No subscription. The price of never being held hostage. |
| **Supporter** | $10/mo (optional) | Same as Free, plus a supporter badge and direct access to the maintainer |

Revenue target: $200–400k/yr solo. Example mix: 500 Pro × $29/mo ($174k/yr) + 200 Lifetime × $499 ($100k, replenishing) + Supporter and incidental revenue. Achievable from r/LocalLLaMA, HN, AI Twitter, and indie-creator communities.

Optional once Pro base is meaningful: skill marketplace revenue share (creators earn 80%, METIS 20%). No rush on this.

## What we're building, in order

We're sprinting — no quarter targets. What matters is the order, not the calendar.

**Now — preserve and productise.**
Finish the preserve-and-productize plan. Ship IterRAG convergence. Wire the companion visibly into evidence and trace surfaces. Kill or flag-gate dead paths (Qt refs, `metis-reflex`, `metis-web-lite`). Tighten onboarding so a new user hits a magic moment within minutes.

**Next — the Seedling and the Feed.**
The small-LLM-that-lives. A persistent quantized local model (Phi-class or Llama-3.2-1B) running as a background worker. Continuous ingestion of news, RSS, and user documents. Visible growth stages. Overnight reflection cycle. This is the feature the whole pitch rests on.

**Next — the Forge.**
Technique gallery UI. Every frontier method in the codebase (IterRAG, Swarm, Heretic, Tribev2, TimesFM, sub-query expansion) becomes a togglable module. Paste an arXiv link, browse curated techniques, watch the companion absorb them.

**Next — Pro tier and public launch.**
Pro tier ships. Launch announcement to r/LocalLLaMA, HN, indie AI Twitter. First skill pack shipped. Public roadmap published.

**Next — Dreams and self-evolution.**
Phase 3 of the existing roadmap: skills auto-generated from high-convergence traces. Companion proposes new skills each morning. Skill marketplace opens. Lifetime tier launches.

**Next — Personal Evals and Network Audit.**
Track how the companion is getting better at the user's specific tasks over time. Network audit panel — show every outbound call, block per provider, prove offline.

**Stretch — LoRA fine-tuning on user data.**
The moment the companion's *weights* adapt to the user, not just its behaviour. Genuinely uncloneable. Hard problem (catastrophic forgetting, eval hell, GPU demands) — not promised on the tin, but worth aiming at.

**Stretch — mobile read-only companion.**
Tauri Mobile or a thin PWA that reads from your desktop METIS. Companion in your pocket, knowledge on your laptop.

## What we are explicitly not doing

- Not a general-purpose chat assistant. ChatGPT owns that.
- Not a Notion competitor. Docs-as-pages is not the metaphor.
- Not a cloud-first product with a local fallback. Local is the product.
- Not a team/enterprise tier. No SSO, no SOC 2, no compliance pitch.
- Not raising venture capital. Not building a company with employees unless the founder chooses to.
- Not a platform before it is a product. Any SDK is years out.
- Not shipping any capability that cannot be reached from the constellation.
- Not promising things we don't ship — LoRA fine-tuning, continual learning, and mobile are stretch goals, not guarantees.

## Risks and honest tradeoffs

- **The small-LLM-that-lives is the hardest technical claim.** Real continual learning is brittle. The honest default is that the *system* grows (skills accumulate, memory densifies, retrieval sharpens, traces become skills) — not the model weights. That's still differentiated enough to win. LoRA fine-tuning is a stretch goal.
- **Ten partially-finished sophisticated systems in the codebase.** Cutting three of them is higher-leverage than adding new ones. The Forge is the mechanism — if a technique doesn't earn a slot in the gallery, it doesn't survive.
- **The companion is the biggest emotional moat and the biggest execution risk.** If it feels dumb or forgetful, the whole pitch collapses. Memory quality, identity persistence, and "does it actually know me" feel must be invested in disproportionately.
- **Solo-founder capacity.** Scope is cuttable. Any item above the stretch line can slip without breaking the pitch, as long as preserve-and-productise holds.
- **"Intelligence grown, not bought" is a promise. If the companion doesn't visibly grow, users will churn.** Growth rings, personal evals, and the morning "here's what I learned overnight" surface aren't nice-to-have — they're the product.

## One-line summary

**METIS is a living AI workspace where a small local companion takes root, learns from your life, and grows into something no cloud chatbot can match. Intelligence grown, not bought.**
