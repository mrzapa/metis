# METIS

The Living AI Workspace — a local-first workspace where a small always-on
companion grows from what the user feeds it. Three product pillars
(**Cosmos**, **Companion**, **Cortex**) are the canonical decomposition;
everything in this glossary belongs to one of them or to the cross-cutting
infrastructure that joins them.

> **Sources.** Every term below is grounded in `VISION.md` and the
> `docs/adr/` series. When one ADR contradicts another, the more recent
> ADR wins (e.g. ADR 0013 supersedes ADR 0007 on Seedling runtime).

## Language

### Pillars

**Cosmos**:
The pillar where knowledge is a navigable universe — every source becomes a Star placed by Faculty.
_Avoid_: "starfield" (renderer-level), "knowledge graph" (too generic).

**Companion**:
The pillar describing the persistent local AI that lives, remembers, reflects, and grows with visible stages. The companion is a first-class product object, not a dock widget.
_Avoid_: "assistant" (overloaded), "agent" (too generic), "chatbot".

**Cortex**:
The pillar where every frontier AI technique is plug-and-play. Techniques become Skills the Companion can graft on.
_Avoid_: "platform", "engine".

### Cosmos

**Star**:
A unit of user content placed in the constellation — document, podcast, video, note, summary, evidence pack, topic cluster, archive, live feed, learning route, session, or skill. Every shipped surface has a star or it does not ship.
_Avoid_: "node", "card", "tile".

**Constellation**:
The 2D WebGL spatial home where stars live. Single canvas, single coordinate system. After ADR 0006 there is no 3D star surface.
_Avoid_: "starfield" (renderer-level term for the background-only shader).

**Archetype**:
The 2D visual template that maps a star's content type to its silhouette and behaviour (main sequence, pulsar, quasar, brown dwarf, red giant, binary system, nebula, black hole, comet, named constellation, variable star, Wolf-Rayet). Derived at render time from `selectStarVisualArchetype(contentType)`; not persisted on `UserStar`.
_Avoid_: "shape", "kind", "icon".

**StellarProfile**:
Procedural metadata — spectral class, stellar type, temperature, luminosity, palette — that drives the 2D rendering and the Star Observatory's character-sheet content. Cache key is `${starId}|${contentType}`.
_Avoid_: "star metadata", "style".

**Star Observatory**:
The docked / orbital panel that animates in around a selected star on dive. The destination of a dive — meaning, not simulated stellar physics.
_Avoid_: "star modal", "detail panel".

**Faculty**:
One of the eight canonical archetypes that organise the cosmos: Perseus, Auriga, Draco, Hercules, Gemini, Big Dipper, Lyra, Boötes. The named landmarks. A `faculty_id` on a comet routes it toward the matching constellation.
_Avoid_: "category", "tag", "topic".

**Brain graph**:
The Three.js force-directed graph that subscribes to live retrieval activity. Distinct from the constellation — the constellation places stars by faculty; the brain graph traces what a query touched.
_Avoid_: "knowledge graph", "memory graph".

**Comet**:
A live-feed item moving through phases (`entering` → `drifting` → `approaching` → `absorbing` → `absorbed` | `dismissed` | `fading`). Visually rendered with a tail. Lifecycle is owned by the Seedling worker; absorbed comets become Atlas entries.
_Avoid_: "feed item" alone — a `NewsItem` becomes a Comet only once it gets a `CometEvent` row.

**Dive**:
The cinematic 2D zoom and pan from constellation overview into a single star. Camera zooms toward the star, ambient stars dim with depth-of-field, the Observatory animates in around it.
_Avoid_: "open star", "click into".

### Companion

**Seedling**:
The always-on small local LLM that ingests, classifies, and reflects in the background. Conceptually one thing; runtime location is set by ADR 0013 (in-browser Bonsai by default; opt-in in-process GGUF backend).
_Avoid_: "background worker" (the worker is one part of the Seedling), "small model" (ambiguous).

**Bonsai**:
The default in-browser WebGPU runtime model (Bonsai-1.7B) that powers the Seedling's reflection pass without a backend dependency. Lives in `apps/metis-web/lib/webgpu-companion/`.
_Avoid_: confusing with "the Seedling" — Bonsai is one runtime; the Seedling is the role.

**Growth stages**:
The visible Companion progression: Seedling → Sapling → Bloom → Elder. The pitch collapses if growth is not visible, so this is a product surface, not a metric.
_Avoid_: "level", "tier", "rank".

**Reflection**:
The Seedling's overnight synthesis pass over recent activity, producing the morning "here's what I learned" report. Triggered by the worker tick, not by user action.
_Avoid_: "summary" (too generic), "digest".

**Hermes**:
The persistent HUD / companion dock — the always-visible surface where the Companion is reachable. Distinct from a chat tab.
_Avoid_: "dock" alone, "HUD" alone.

**Atlas**:
The episodic memory store. Persists Atlas entries (the durable provenance artefacts that absorbed comets become). Lives in `rag_sessions.db`.
_Avoid_: "memory" (too broad — Atlas is specifically episodic), "history".

**Atlas entry**:
A persisted provenance artefact in `atlas_entries` (in `rag_sessions.db`). The end-state of an absorbed comet; what stays after the comet itself ages out.
_Avoid_: "memory record", "note" — Atlas entries are specifically the provenance shape.

**Forge**:
The one-click technique gallery where Cortex modules become togglable. The arbiter of which experiments survive — techniques that earn a Forge slot stay; others get flag-gated or removed.
_Avoid_: "marketplace" (governance is undecided; see VISION.md open questions), "plugin store".

### Cortex

**Skill**:
A togglable Cortex module — a technique the Companion can graft on via the Forge. Persisted as a candidate in `skill_candidates.db`.
_Avoid_: "plugin", "module" (in glossary terms, "module" means anything with an interface and an implementation; see [docs/LANGUAGE.md](docs/LANGUAGE.md)).

**IterRAG**:
The convergence retrieval mode — one of the five tuned RAG modes.

**Tribev2**:
The multimodal faculty classification system that decides which Faculty a piece of content belongs to.

**Heretic**:
The model abliteration capability. ADR 0005 keeps Heretic as a first-class Cortex module — "use abliterated open-weight models if you want to."

**TimesFM**:
The forecasting capability (TimesFM 2.5).

**Swarm**:
The persona simulation capability.

**Trace timeline**:
The provenance / observability surface that shows what a query touched.

### Cross-cutting infrastructure

**Network audit**:
The outbound-fetch logging system (ADR 0010 / 0011). Every outbound call goes through `audited_urlopen` with a `trigger_feature` tag. Stores in `network_audit.db`. Privacy posture: never persists the full URL of an *audited* fetch — distinct from `news_items.db`, which persists user-curated reading material by design.

**News feed repository**:
The persistence layer for news-comet state — `news_items`, `comet_events`, `feed_cursors`. Lives in `news_items.db` (NOT extending `rag_sessions.db`). Owns serialization; the comet decision engine continues to own scoring.
_Avoid_: "feed store" (ambiguous with `feed_cursors` only).

**ADR (Architecture Decision Record)**:
A numbered decision document under `docs/adr/`. Records context, decision, because, constraints, alternatives, consequences, open questions. Status: Draft / Accepted / Superseded. Never re-litigated by the `improve-codebase-architecture` skill.

**Plan doc**:
A milestone-level work document under `plans/<slug>/plan.md`. Has standard frontmatter (Milestone / Status / Claim / Last updated / Vision pillar). The operational layer between VISION.md and code.

**Milestone**:
A row in `plans/IMPLEMENTATION.md`. Backed by a plan doc. Status: Draft / Ready / In progress / Rolling / Blocked / Landed / Superseded. Identified by `M01`, `M13`, etc.

**Local-first**:
A non-negotiable product constraint, not a marketing word. METIS works offline after model files are present. Cloud features are opt-in and end-to-end encrypted. Routing background work through a remote provider violates the product promise.
_Avoid_: "offline-capable" (too weak), "privacy-first" (too vague).

## Relationships

- A **Star** has one **Archetype** (derived from its content type at render).
- A **Star** has one **StellarProfile** (cached by `starId|contentType`).
- A **Faculty** owns many **Stars** within the **Constellation**.
- A **Comet** is a **Star** in motion — once absorbed, it leaves an **Atlas entry** behind.
- The **Seedling** owns the **Comet** lifecycle; user actions (`/absorb`, `/dismiss`) trigger phase changes through the **News feed repository**, never around it.
- An **Atlas entry** outlives its **Comet**; the cleaner protects active comets from `news_items` eviction by phase guard.
- A **Cortex** module becomes a **Skill** by earning a **Forge** slot.
- An **ADR** governs many **Plan docs**; a **Plan doc** governs many commits.
- **Bonsai** runs the **Seedling**'s **Reflection** pass by default (ADR 0013); a backend GGUF runtime is opt-in (ADR 0007 superseded posture).

## Flagged ambiguities

- **"star" was used for both content units and rendered points** — resolved: a *Star* (capitalised, in the glossary) is a unit of user content with a faculty and a stellar profile. A *star* in shader/lib code may refer to a rendered point primitive, including background field stars that have no Star-with-capital-S identity.
- **"module" is overloaded** — within METIS product language a *module* can mean a Cortex technique. Within the architecture-improvement skill (`docs/LANGUAGE.md`) "Module" means anything with an interface and an implementation. Both meanings coexist; pick by context.
- **"agent"** — METIS rarely uses the word internally; see *Companion*. Reserve "agent" for the LLM-driven session worker concept (e.g. an external Codex agent picking up a milestone), not for the Companion.
- **"feed"** — multiple meanings: an RSS / HN / Reddit *source* (a row in `feed_cursors`), the live stream of *items* it produces (`NewsItem`), and the user-facing *comet stream* (CometEvents in flight). Use the specific term where possible.

## Example dialogue

> **User:** "When the Companion absorbs a Comet, does it become a Star?"
>
> **Agent:** "An absorbed Comet writes an Atlas entry — that's the durable
> provenance. Whether the absorbed comet *also* gets a Star in the
> Constellation depends on the user-content lifecycle, not the absorb
> path itself. The phase transition (`absorbing` → `absorbed`) goes through
> `update_phase` on the News feed repository. The Atlas entry is what
> survives after retention evicts the original `news_items` row."

---

_Note for future agents:_ this CONTEXT.md was bootstrapped from ADRs 0005, 0006, 0007, 0008, 0010, 0011, 0013 and `plans/README.md`. Terms here are documented; sharpen further by running through the `domain-model` skill in an interactive session, which will grill you on edge cases and update this file inline as decisions crystallise.
