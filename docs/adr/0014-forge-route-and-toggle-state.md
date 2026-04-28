# 0014 - The Forge: Route Shape, Toggle State, and Principle #9 Resolution

- **Status:** Accepted (M14 Phase 1 architectural baseline)
- **Date:** 2026-04-28

## Context

M14 (*The Forge*) ships a thin new UI surface — a technique gallery —
on top of already-shipped engine infrastructure. Every named frontier
technique in `VISION.md` (IterRAG convergence, Swarm persona simulation,
Heretic abliteration, Tribev2 multimodal extraction, TimesFM
forecasting, sub-query expansion, hybrid retrieval, MMR, reranker,
news-comet ingestion, the nine shipped skills under `skills/`) already
exists as runnable code. The Forge does not build techniques. It
*surfaces* them.

`plans/the-forge/plan.md` (Phase 1 *Next up*) calls for an ADR before
any UI code lands, resolving four architectural questions that cut
across every later phase:

1. **Route shape** — single-page `/forge` with anchored sections, or
   `/forge` index plus per-technique `/forge/<id>` detail pages?
2. **Toggle-state storage** — reuse `metis_app/settings_store.py` (the
   live KV the engine already reads on every query), promote to a
   typed module on top of M11's agent-native KV, or introduce a new
   `forge_state.db`?
3. **What counts as a "technique"** — any settings-gated capability,
   a `skills/` entry, or a new first-class registry object?
4. **`VISION.md` principle #9 conflict** — the principle says "no
   capability without a star". Techniques are not documents; they
   don't naturally live in the constellation. Resolve.

A fifth question — how the arXiv-paste flow scopes itself — is
deferred to Phase 4 but the safety boundary is set here so M15 launch
copy stays honest.

## Decision

### 1. Route shape — single-page `/forge` with deep-link anchors (v1)

`apps/metis-web/app/forge/page.tsx` is one page. Each technique gets
an in-page section with `id="{technique_id}"` so deep-links like
`/forge#reranker` work for both the constellation's *Skills* sector
(Phase 2) and the companion dock's "absorbed *X*" event copy
(Phase 3).

Per-technique routes (`/forge/<technique-id>/page.tsx`) are deferred
to **post-v1**. They earn their place only when a single technique
accumulates enough first-class content (full trace history, dedicated
config sliders, changelog, paper backlinks) to warrant its own page.
None do today; adding the routing structure pre-emptively would
violate the project's "no premature abstraction" stance.

### 2. Toggle-state storage — reuse `settings_store.py` behind a thin
   `forge_registry.py` facade

Every Forge toggle delegates to the live settings KV (`GET/POST
/v1/settings`) via the existing `updateSettings()` path. The engine
already reads these keys on every query — adding a new storage layer
would either duplicate the read path (bug surface) or require the
engine to learn a second source of truth (architectural debt).

The new module `metis_app/services/forge_registry.py` (Phase 2) wraps
the underlying settings keys behind a `TechniqueDescriptor` dataclass:

```python
@dataclass(frozen=True)
class TechniqueDescriptor:
    id: str                              # stable slug, e.g. "reranker"
    name: str                            # display name
    description: str                     # one honest sentence
    pillar: Literal["cosmos", "companion", "cortex", "cross-cutting"]
    setting_keys: tuple[str, ...]        # which settings_store keys gate this
    enabled_predicate: Callable[[Settings], bool]
    docs_url: str | None = None
    engine_symbols: tuple[str, ...] = ()  # for traceability
```

The registry is a **module-level static list**, not a database table
or a dynamic plugin loader. Adding a technique means appending one
descriptor to a Python list and shipping it. If a future requirement
demands dynamic registration, that becomes its own ADR.

**Per-view UI state** (card expansion, "what's new" badges,
last-viewed-at) lives in M11's agent-native KV store
(`/v1/app_state`), keyed under `forge.*`. Global on/off lives in
settings; ephemeral UI state lives in KV. The boundary is clean
because the engine never reads UI state.

**A new `forge_state.db` is explicitly rejected.** The plan doc's
*Next up* lists it as an option; this ADR closes that door. There is
no Forge-specific persistence requirement in Phases 1–7 that
settings + KV together cannot meet.

### 3. What is a "technique"

A `TechniqueDescriptor` covers exactly **three** kinds of things:

1. A **settings-gated engine capability** with at least one boolean
   or scalar key in `metis_app/default_settings.json` that the
   query/index/reflection pipeline reads on every run. Example:
   `use_reranker`, `agentic_mode`, `hybrid_alpha`,
   `news_comets_enabled`.
2. A **shipped skill** under `skills/<id>/` whose enable state is
   stored at `settings["skills"]["enabled"][<id>]`. Example: the
   nine skills already shipped (`agent-native-bridge`,
   `evidence-pack-timeline`, `pptx-export`, `qa-core`,
   `research-claims`, `summary-blinkist`, `swarm-critique`,
   `symphony-setup`, `tutor-socratic`).
3. A **runtime-prereq capability** whose enable state is computed
   from environment plus settings, not a single boolean. Example:
   Heretic abliteration (`heretic_output_dir` plus
   `heretic_service.is_heretic_available()`), TimesFM (`forecast_*`
   plus model-download status). The descriptor's
   `enabled_predicate` resolves these.

A technique that is none of the above does not appear in the Forge.
This is the *honest-description test* the plan doc demands: every
row in the harvest inventory must trace to live engine code through
its `setting_keys` and `engine_symbols` fields, or it does not ship.

The Forge's static registry deliberately does **not** synthesise
techniques from `default_settings.json` keys. Hand-curated
descriptors are how each technique earns a one-sentence
description, a pillar, and the right pre-flight check. Settings-key
churn does not silently change the gallery.

### 4. Principle #9 — each *active* technique gets a star

`VISION.md` principle #9 ("no capability without a star") is a
real product constraint, not stylistic. The Forge resolves it as
follows (Phase 2 implements; Phase 1 declares intent):

- Each **enabled** technique is a star in a new "Skills" faculty
  sector of the 2D constellation. Its archetype is determined by
  pillar (Cortex techniques use the existing knowledge archetype;
  Companion techniques use the seedling archetype; cross-cutting
  techniques use a neutral utility archetype).
- The star's observatory dialog
  (`apps/metis-web/components/constellation/star-observatory-dialog.tsx`)
  deep-links to `/forge#<technique-id>` rather than rendering the
  technique inline. The Forge stays the single source of UI truth
  for technique state.
- Techniques that are **off** do not appear in the constellation.
  Toggling on in the Forge lights up the star — that *is* the
  "capability absorbed" feel the VISION paragraph describes.

This does mean the constellation gains ~10–15 stars when the user
turns on the harvest inventory's defaults. ADR 0006 (constellation
2D primary) does not cap star count; the renderer scales to several
hundred without grief. The star catalogue's M12 work has the data
plumbing in place.

The Forge **itself** does not get a meta-star in the constellation.
Reaching the Forge is a nav action (page chrome link) or
deep-link (from a Skills-sector star); the constellation's job is
*knowledge*, not *navigation*.

### 5. arXiv-paste boundary (deferred phase, declared early)

`POST /v1/forge/absorb` (Phase 4) produces a `TechniqueProposal`
document, optionally a `skills/<id>/SKILL.md` draft, and **never**
new engine code. The proposal is reviewed before any setting flips.
"Absorb a technique" in the Forge means *recognise where this
technique fits in METIS* — which existing capability it most
resembles, which adjacent settings combine to approximate it, and
which one-page skill description captures it. The Forge does not
run untrusted code from papers.

This boundary lives here, not in a Phase 4 ADR, so M15 launch copy
written before Phase 4 ships can stay honest.

## Constraints

- **Preserve principle #4** ("Skills over settings"). The Forge is
  not a second settings page. Cards present *capability*, not
  *configuration*. The dock event after a toggle and the
  constellation star fade-in matter as much as the mechanic.
  Reviewers can reject Forge cards that read like settings rows.
- **Preserve principle #5** ("Trace everything"). Every toggle
  emits a `CompanionActivityEvent` (`source: "forge"`,
  `kind: "technique_toggled"`) through the M09 pub/sub. Phase 6
  surfaces per-technique trace history.
- **Preserve principle #6** ("Local by default"). The Forge ships
  no remote endpoints in v1. Phase 7's stretch export is
  file-only; no upload, no signature server.
- **Preserve principle #7** ("Preserve and productise"). Every
  technique listed must trace to existing engine code. The
  inventory audit (`plans/the-forge/plan.md` *Harvest inventory*
  table) is the M01 hand-off.
- **Preserve ADR 0004** (one Litestar interface). All Forge
  backend lives in `metis_app/api_litestar/routes/forge.py`. No
  new daemon, no IPC.
- **Free tier gets the Forge.** Per `VISION.md` business model,
  every technique in the harvest inventory is a local feature and
  ships free. Pro-only is the (future) skill marketplace tab and
  the autonomous research cron — the *gallery and toggles
  themselves* are free. Restating this here so M15 doesn't
  re-litigate it.

## Alternatives Considered

- **Per-technique routes from day one (`/forge/<id>` for every
  technique).** Rejected. ~15 sub-routes for thin content
  duplicates the page-chrome pattern unnecessarily. Anchored
  sections on a single page handle deep-linking and let the user
  scan the whole gallery. If one technique grows enough to need
  its own page, promote it then.
- **New `forge_state.db`.** Rejected. The toggle state already
  lives in `settings_store.py` and is read on every engine call.
  A second store would either duplicate the read path or force
  the engine to consult two sources. Either is worse than
  reusing what works.
- **Synthesise the registry from `default_settings.json`.**
  Rejected. The harvest inventory's *honest-description test*
  requires per-technique editorial: a one-sentence description,
  a pillar, the right pre-flight check. Free-form synthesis from
  setting keys produces "enable_recursive_memory: bool — toggles
  recursive memory" which is exactly the principle-#4 anti-pattern.
- **Forge meta-star in the constellation.** Rejected. A single
  star labelled "The Forge" doesn't satisfy principle #9 — it
  hides the *individual* capabilities behind a UI shell. The
  star-per-active-technique model exposes growth visibly: turn
  on reranker, see a star appear in the Skills sector. That's
  the feel the VISION paragraph promises.
- **Declare the Forge an explicit exception to principle #9.**
  Rejected with prejudice. The principle is a guard against
  exactly this: features that ship without a constellation home
  end up unfindable. The star-per-technique resolution honours
  the principle and adds product value (visible growth).
- **Treat each `skills/<id>/` entry as the canonical technique
  unit.** Rejected. ~15 of the harvest inventory rows have no
  `skills/` entry (they're settings-gated engine capabilities,
  not skill files). Forcing every technique through the skill
  shape would require writing 15 SKILL.md stubs first — work
  that should not block the Forge shipping.

## Consequences

- **Phase 1 (this ADR + shell):** ships
  `apps/metis-web/app/forge/page.tsx`,
  `apps/metis-web/app/forge/loading.tsx`,
  `metis_app/api_litestar/routes/forge.py` with
  `GET /v1/forge/techniques` returning a static hardcoded list,
  and a "Forge" link in `page-chrome.tsx` nav. No interactive
  cards yet; the page renders an empty-state preview that
  confirms the round-trip.
- **Phase 2:** introduces `metis_app/services/forge_registry.py`
  (the typed `TechniqueDescriptor` dataclass + the live-settings
  predicates), real card rendering, and the Skills-sector
  constellation integration.
- **Phase 3:** wires writable toggles + `CompanionActivityEvent`
  emission. No new storage; everything routes through
  `settings_store.py` and the M09 pub/sub.
- **Phase 4:** the arXiv-paste boundary above governs the
  `POST /v1/forge/absorb` contract.
- **No new top-level dependency.** The registry is plain Python
  dataclasses; the page reuses M02 design-system primitives.
- **Per-technique URL anchors are permanent.** Deep-link
  `#technique-id` slugs are now part of the URL surface; renaming
  a slug requires either a redirect or a deprecation pass. Slug
  list is curated in `forge_registry.py`; reviewers should treat
  slug changes the same way they treat `default_settings.json`
  key renames.
- **Skill-mention parity.** The nine shipped skills under `skills/`
  appear in the Forge under their YAML-frontmatter `id`. The Forge
  reader does not invent slugs; if a skill folder is renamed, the
  registry entry must move with it.

## Open Questions

- **Star archetype assignment.** Phase 2 chooses concrete archetypes
  per technique. The mapping (Cortex → knowledge archetype,
  Companion → seedling archetype, cross-cutting → utility) is the
  default; specific techniques may want bespoke archetypes (Heretic
  feels more "tool" than "knowledge"). Resolve in Phase 2 review.
- **Rejection bookkeeping for skill candidates** (Phase 5). ADR
  0011 territory — separate ADR when Phase 5 is claimed.
- **`.metis-skill` bundle format** (Phase 7 stretch). ADR 0012
  territory if and when Phase 7 is claimed. This ADR does not
  pre-empt that decision.
- **Pro-only marketplace tab placement.** When the Forge gains a
  marketplace tab post-M15, the tab lives at the top of the same
  Forge page (a `Tabs` from `components/ui/tabs.tsx`), not a
  separate route. Confirm in M15's launch ADR.
- **Searching/filtering at scale.** With ~20 techniques today, the
  page renders fine without filters. If the registry grows past
  ~40, a filter-bar component lifted from the Improvements page
  is the cheapest answer. Track in Phase 2 retro.
