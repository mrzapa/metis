---
Milestone: Interactive star catalogue (M12)
Status: Ready
Claim: claude/m12-plan-and-claim
Last updated: 2026-04-24 by claude/m12-plan-and-claim
Vision pillar: Cosmos
Supersedes: docs/plans/2026-04-05-interactive-star-catalogue.md
---

# M12 — Interactive Star Catalogue

Turn the already-landed procedural catalogue + WebGL renderer into a
**searchable, filterable, click-to-inspect star explorer** — the
interactive layer that the old superseded Phase 2 design doc promised
but never reached.

This plan is grounded in the post-M02 reality: the rendering path, the
spatial hash, the hover tooltip, the "addable" promotion target, and
the seeded `CatalogueStar` data model are all live on `main`. M12 is a
**thin new interactive surface** over that infrastructure, not a new
renderer.

## Why this matters

From `VISION.md` pillar #1 (*Cosmos — your knowledge as a universe*):
*"The constellation is the primary navigation — not decoration. Every
document, paper, podcast, video, tweet, and note becomes a star…
Individual stars open into a Star Observatory where you assign
archetypes, plan learning routes, and link sources."*

Today the galaxy is beautiful but mostly a backdrop. Thousands of
procedurally-generated stars exist; none are addressable without
scrolling to one by eye. The user cannot search for "Vega", cannot
filter by spectral class, cannot click a nameless field star and ask
"what would this become if I attached my paper PDF to it?". M12 closes
that gap.

Principle #9 — *"No capability without a star"* — is already honoured
by the catalogue layer. M12 makes principle #10 — *"Stars are
knowledge, not astronomy"* — practically reachable: a user can reach
any star in the catalogue in two clicks and turn it into a knowledge
anchor.

---

## Progress

*(Plan drafted 2026-04-24 — no implementation phases have landed yet.
Phase 0 below is this plan-and-claim pass itself.)*

### What's already in place (harvest inventory)

| Surface | Location | Notes |
|---|---|---|
| `CatalogueStar` + `CatalogueSector` data model | `apps/metis-web/lib/star-catalogue/types.ts` | Frozen shape, seeded IDs, `apparentMagnitude`, `depthLayer`, full `StellarProfile`. `name: string \| null` (ADR 0006 field/landmark/user tiers). |
| `StarCatalogue` generator | `apps/metis-web/lib/star-catalogue/star-catalogue.ts` | Lazy per-sector generation with `getVisibleStars(viewport)`, `evictDistantSectors`, memoised profiles. |
| `DEFAULT_CATALOGUE_CONFIG` | `apps/metis-web/lib/star-catalogue/types.ts` | `galaxySeed: "metis-prime"`, 350 stars per 960-unit sector, 4-arm spiral. Already consumed at `app/page.tsx:2096`. |
| `generateStarName` (tiered) | `apps/metis-web/lib/star-catalogue/star-name-generator.ts` | M02 Phase 1 — `"field" \| "landmark" \| "user"`. Field stars return `null`. |
| WebGL2 instanced renderer | `apps/metis-web/lib/landing-stars/landing-starfield-webgl.ts` (`LandingStarfieldWebgl`) | Landed via M02. Point / sprite / hero / closeup LOD. |
| Spatial hash + hit-testing | `apps/metis-web/lib/landing-stars/landing-star-spatial-index.ts` | `buildLandingStarSpatialHash`, `findClosestLandingStarHitTarget`. Used today for both addable and catalogue hover paths. |
| Catalogue hover tooltip | `app/page.tsx` — `showCatalogueTooltip` / `catalogueTooltipRef` / `getHoveredCatalogueStar` | Already shows name + spectral class for landmark-tier stars on hover; field stars hover silently per ADR 0006. |
| `isAddableBackgroundStar` promotion gate | `apps/metis-web/lib/landing-stars/landing-star-interaction.ts` | Already decides whether a catalogue star is adjacency-eligible for promotion; the click-to-add path is live. |
| Camera fly-to mechanics | `apps/metis-web/lib/constellation-home.ts` + `backgroundCameraTargetOriginRef` in `app/page.tsx` | Pan-and-zoom animator already exists; Star Dive uses it for focus transitions. |
| Semantic search surface (user stars only) | `app/page.tsx` (`semantic-star-search`) + `apps/metis-web/lib/semantic-constellation.ts` | The anti-pattern for scope: this searches user stars by meaning — M12 must search the *catalogue*, which is a different index. |
| `CatalogueUserStar` interface | `apps/metis-web/lib/star-catalogue/types.ts:57` | Placeholder for the eventual "user stars are CatalogueStars with extra metadata" migration. Noted as "Phase 5 of the Interactive Star Catalogue plan" in the type comment — that migration is **still open** and folds into this milestone. |
| Star Observatory / `StarDetailsPanel` | `apps/metis-web/components/constellation/star-observatory-dialog.tsx:384` | Rich detail surface for *user* stars. M12 adds a lighter parallel surface for *catalogue* stars that can ramp into full promotion. |

### Previously-landed work referenced by this plan

| Phase | Commit / PR | What landed |
|---|---|---|
| Phase 1 (superseded plan) — procedural data layer | PR #513, commits `c65c9ad` → `6772e18` → `4b34d67` (2026-04-05) | `types.ts`, `rng.ts`, `galaxy-distribution.ts`, `star-name-generator.ts`, `star-catalogue.ts`, `index.ts` + tests. |
| Phase 2 (superseded plan) — dedicated WebGL2 renderer | PR #514 → `faae7c0` (2026-04-06) then reverted via `c1b683a` | `StarCatalogueRenderer` class was written, then removed as redundant with the M02 `LandingStarfieldWebgl`. |
| M02 — 2D constellation refactor | Merge `0449c2e` (2026-04-19) | Ship-quality WebGL2 renderer with LOD tiers, DOF, Star Dive, archetype silhouettes — handles *all* star rendering (catalogue + user). |
| Superseded design doc flip | `70b0d05` (2026-04-19) | Old design doc marked `Superseded`, M12 row flipped to `Draft needed`. |

### Verified genuinely open (2026-04-24)

Grep of `apps/metis-web/` for the key M12 deliverables confirms none
are present on `main`:

- No catalogue-search overlay component (`star-explorer`, `catalogue-search`, etc. — not in tree).
- No catalogue-star detail pane — only the hover tooltip at `app/page.tsx:4222` (`showCatalogueTooltip`).
- No spectral-class / magnitude filter UI anywhere.
- No "promote a non-addable catalogue star to the user's constellation" flow. Today only stars that pass `isAddableBackgroundStar` (adjacency gate) are clickable into `handleAddStar`; named landmark stars and far-off field stars are inspectable by hover only.
- `CatalogueUserStar` is declared (`types.ts:57`) but **no code path instantiates it yet** — the existing user-star shape is still the legacy `UserStar` from `lib/constellation-types.ts`. The unification migration is part of M12 Phase 4 below.

## Next up

The first concrete actions for whoever picks up Phase 1:

1. **Read this plan end-to-end**, then read `docs/adr/0006-constellation-design-2d-primary.md` (ADR 0006 — the "stars are knowledge, not astronomy" contract that the inspector surface must honour) and scan `app/page.tsx:4200–4580` (the current catalogue hover + addable-click code paths).
2. **Phase 1 — Catalogue Star Inspector (lightweight detail pane).** A new React component that opens on click of *any* catalogue star (addable or not), showing name (or "unnamed field star"), spectral class + subclass, apparent magnitude, world coordinates, and the same `StellarProfile` mini-preview already used inside `StarDetailsPanel`. Two CTAs: "Close" and "Promote to my constellation…" (the latter hands off to the existing user-star creation flow with the catalogue star's position + profile pre-filled, but sits behind the adjacency gate unless Phase 4 relaxes it).
3. **Push the Phase 1 PR and stop.** Do not roll Phase 2 into the same PR. Let the human review the inspector surface — its shape shapes the rest.

## Blockers

- **None.** All dependencies (M02 renderer, catalogue data layer, spatial hash, camera fly-to, Star Observatory pattern) are landed on `main`.

## Notes for the next agent

### Phased plan (each phase = one PR)

**Phase 0 — Plan doc + claim (this PR).** Plan written, row flipped
`Draft needed → Ready`, branch claimed.

**Phase 1 — Catalogue Star Inspector.** New component
`apps/metis-web/components/constellation/catalogue-star-inspector.tsx`
(a non-modal side panel, not a full-screen dialog — `StarDetailsPanel`
is the dialog; the inspector is lighter and dismissible on outside
click). Wired into `app/page.tsx` via a new `inspectedCatalogueStar`
state that's set by a click handler on any rendered catalogue star
(both addable and non-addable paths). Hover tooltip remains; click now
opens the inspector. Minimum fields: name (or `"Field star · ${id}"`),
spectral class + visual archetype, apparent magnitude, world position,
24×24 `StarMiniPreview` from `star-observatory-dialog.tsx`. Secondary
CTA: "Promote to my constellation…" — disabled with tooltip
explaining adjacency if the star is out of reach; enabled otherwise
and reusing `handleAddStar`. Add unit tests for the inspector
rendering logic (name-tier branching, disabled-CTA reason) and an
integration test that simulates a catalogue-star click and asserts
the inspector opens. **Scope: a few hundred lines + tests. ~1 day.**

**Phase 2 — Catalogue Search Overlay.** A search input that lives in
the existing top-right HUD alongside the semantic star search,
collapsible behind a ✧ trigger (mirror the `metis-semantic-search`
pattern, do not rebuild it). Typing queries the *catalogue* index —
**this requires a tiny new index**: `StarCatalogue` already lazy-
generates per-sector; a naive implementation iterates currently-loaded
sectors and scores by substring (acceptable for landmark-tier names,
which are the only named stars). Results list (up to 8) with spectral
class chip + magnitude. Click a result → call
`backgroundCameraTargetOriginRef.current = { x: star.wx, y: star.wy }`
and open the Phase 1 inspector on arrival. **Scope: new search
component + catalogue-index helper + tests. ~1 day.**

**Phase 3 — Spectral / magnitude filter.** Filter chip row under the
search overlay (O/B/A/F/G/K/M/L/T + "All"), plus a magnitude slider
("show stars brighter than m=X"). When active, the render plan
receives a `filterPredicate` and dims (not hides — keep the galactic
structure visible) stars that fail the predicate to 20% brightness.
Filter state is URL-hash-persisted (so a shared link opens with the
same filter active) but not saved to settings (transient view state).
**Scope: filter component + render-plan predicate threading + tests.
~1 day.**

**Phase 4 — Catalogue/User star unification + promote flow.** Migrate
`UserStar` (legacy, `lib/constellation-types.ts`) onto the
`CatalogueUserStar extends CatalogueStar` shape declared in
`star-catalogue/types.ts:57` (a migration already earmarked in the
type comment). Relax the adjacency gate on "Promote to my
constellation" when triggered from the inspector — a user should be
able to attach a document to any catalogue star, even a distant field
star, and watch it become a named landmark. Add a "first star
anywhere" onboarding flow that uses this path. **Scope: type
migration + promote handler + onboarding hook + tests. ~2–3 days — the
biggest phase, split further if it feels too large at the time.**

### Design contract — what the inspector is *not*

- **Not a `StarDetailsPanel`.** `StarDetailsPanel` is the authoring
  surface for user stars (upload manifests, pick archetypes, run a
  learning route). The catalogue inspector is for read-only
  inspection and a single "promote" entry point. If the inspector
  ever grows upload UI, it has drifted — fold into `StarDetailsPanel`
  instead.
- **Not a modal.** Modal dims the constellation and breaks "stars are
  the primary navigation". Inspector is an edge-anchored side pane
  (prefer right edge at desktop widths) with the constellation still
  pannable behind it.
- **Not a search of arbitrary repo content.** The search box searches
  the star catalogue by name / spectral class. Semantic search over
  user documents already exists as `metis-semantic-search` — do not
  conflate.
- **Not a capability without a star.** Principle #9 holds: every
  feature in M12 hangs off an existing or newly-inspected
  `CatalogueStar`. No new top-level route. No new settings tab.

### Touchpoints & collision watch

- **`apps/metis-web/app/page.tsx`** is a hotspot (99.8th percentile
  churn — see Repowise). Every M12 phase touches it at the
  state-wiring level. Keep inspector/search components *outside*
  `page.tsx` — import them in, don't inline.
- **M02 is Landed** but the renderer (`LandingStarfieldWebgl`) is
  still the same code. If M12 needs a render-time flag (e.g. filter
  dim), plumb it via the existing render-plan shape
  (`buildLandingStarRenderPlan`), not via new renderer flags.
- **M14 (The Forge)** depends on M12 per the IMPLEMENTATION.md
  depends-on column. The dependency is "the Forge's technique cards
  promote to user-constellation stars" — so Phase 4's unified
  `CatalogueUserStar` shape is the contract M14 consumes. If Phase 4
  slips, M14 can still start against the legacy `UserStar`; the
  unified shape is a refactor, not a block.
- **M13 (Seedling + Feed)** independently reaches for the catalogue
  to place incoming news comets. Coordinate: if both land in the same
  window, share a design review so promoted-from-news stars and
  promoted-from-inspector stars take the same code path.

### Out of scope for M12

- Cross-galaxy travel (multiple galaxy seeds). One galaxy; deterministic.
- A backend-side catalogue index (e.g. SQLite). Not needed — the
  galaxy is deterministic and already fits in memory sector-by-sector.
- Audio / sound on inspector open. The constellation today is silent;
  keep it that way until a global audio policy exists.
- Mobile-specific layout. Handle later with M19.

### Verification — what "done" means for each phase

Every phase PR must pass the three commands from the onboarding prompt:

```
# Backend
python -m pytest tests/ --ignore=tests/_litestar_helpers --ignore=tests/test_api_app.py

# Frontend type + unit
cd apps/metis-web && npx tsc --noEmit && npx vitest run

# Lint (touched files only)
ruff check <touched .py files>
```

Plus for phases that touch `page.tsx` or add a rendered component,
capture a screenshot of the before/after into the PR body — the
constellation is a visual feature and review benefits from the image.

### Reminders from the onboarding prompt

- Conventional-commit style: `feat(m12): …`, `fix(m12): …`,
  `docs(m12): …`, `test(m12): …`. `Co-Authored-By` trailer on every
  commit (copy from a recent `git log` entry).
- CI guard `tests/test_network_audit_no_raw_urlopen.py` applies: if
  M12 ever needs to hit a URL from Python (it shouldn't — this is a
  frontend-only milestone), route through `audited_urlopen`.
- Branch naming: `claude/m12-<short-descriptor>` per phase.
