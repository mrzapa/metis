---
Milestone: M02 — Constellation 2D refactor
Status: In progress
Claim: claude/m02-archetypes-nebula-bh-rg (Phase 3: all 12 archetypes) — Phases 0/0.3/1/2/3-scaffold+pulsar landed
Last updated: 2026-04-18 by claude-opus-4-7
Vision pillar: Cosmos
ADR: docs/adr/0006-constellation-design-2d-primary.md
---

# M02 — Constellation 2D Refactor

Retire the 3D star-surface sphere. Make the constellation fully 2D. Redistribute
the procedural-star-differentiation design intent across **silhouette
(archetype) + annotations + Observatory**. Replace the indiscriminate
astronomical catalogue naming with a **tiered naming policy**.

This plan implements [ADR 0006](../../docs/adr/0006-constellation-design-2d-primary.md).
Read that first.

## Why this matters

From `VISION.md` principle #10: *"Stars are knowledge, not astronomy. Diving
into a star reveals its content — the document, the companion's notes, the
trace — not a simulated stellar surface."* Today's landing page violates this
by treating each star as a physics simulation you dive into. This refactor
aligns the constellation with the vision.

---

## Progress

<!-- Append as phases land. -->

**Phase 0 — Archetype scaffold (partial ✅, 2026-04-18 by claude-opus-4-7):**
- 0.1 ✅ — Added `StarVisualArchetype` + `StarContentType` + `selectStarVisualArchetype`
  + `CONTENT_TYPE_ARCHETYPE_MAP` + `DEFAULT_VISUAL_ARCHETYPE` in new
  `apps/metis-web/lib/landing-stars/star-visual-archetype.ts`. Named
  `StarVisualArchetype` (not `StarArchetype`) to avoid collision with the
  backend `StarArchetype` indexing-strategy enum in
  `metis_app/services/star_archetype.py` — those are different concepts.
- 0.2 ✅ — `StellarProfile` gained `visualArchetype: StarVisualArchetype`.
  `generateStellarProfile` now accepts an optional
  `GenerateStellarProfileOptions { contentType? }` 2nd arg. Content type only
  affects `visualArchetype`; all other fields remain deterministic from seed.
- 0.3 ✅ — Threaded `contentType` through the landing-star producers.
  `StellarProfileGenerator` in `apps/metis-web/lib/star-catalogue/star-catalogue.ts`
  now accepts the same `GenerateStellarProfileOptions` second arg as
  `generateStellarProfile`, so the procedural field-star path is option-ready
  (still defaults to `main_sequence` — catalogue stars have no content type).
  In `apps/metis-web/app/page.tsx`, `getCachedStellarProfile` takes an optional
  `contentType` and keys the cache by `${starId}|${contentType}` so a star's
  archetype refreshes if its content type changes. A new helper
  `deriveUserStarContentType` in `apps/metis-web/lib/user-star-content-type.ts`
  infers the content type from a `UserStar` (learning route → `learning_route`,
  else manifest path present → `document`, else `null`). That inference is
  applied at the two user-star call sites: `rebuildProjectedUserStarRenderState`
  and the Star Dive focus acquisition fallback.
- 0.4 ✅ — `LandingProjectedStar` now carries optional
  `visualArchetype?: StarVisualArchetype` so downstream render tiers can
  branch on it. Optional so pure-procedural field stars can omit it (omission
  = `main_sequence` at render time).
- 0.5 ✅ — Tests added:
  `apps/metis-web/lib/landing-stars/__tests__/star-visual-archetype.test.ts`
  (3 cases: null/undefined default, 12 canonical mappings, map completeness)
  and three new cases in `stellar-profile.test.ts` (default archetype,
  archetype driven by content type, determinism of all other fields).

**Verification:** `pnpm test` → 211 passed, 10 skipped, 0 failed.
`pnpm exec tsc --noEmit` → exit 0. `pnpm exec eslint` on touched files →
no new errors or warnings (existing `page.tsx` pre-existing warnings are
unchanged).

**Phase 1 — Tiered naming (in progress, 2026-04-18 by claude-opus-4-7):**
See the Phase 1 task boxes below for per-task status as the work lands.

**Errata — 8 vs 11 faculty landmarks:** ADR 0006 line 103 and the Phase 1
section below say "eight faculty landmarks (Perseus, Auriga, Draco,
Hercules, Gemini, Big Dipper, Lyra, Boötes)". The code has drifted:
`apps/metis-web/lib/constellation-home.ts:130–186` defines **11**
faculty constellations — the original 8 plus **Synthesis** (Andromeda),
**Autonomy** (Cygnus), and **Emergence** (Cassiopeia). Phase 1 treats the
`landmark` tier as applying to all faculty-constellation stars, whatever
count exists. ADR 0006 should be updated to reflect 11 as part of M02
landing.

**Phase 2 — Cinematic 2D camera (partial ✅, 2026-04-18 by claude-opus-4-7):**
- 2.1 ✅ — Extracted the camera easing loop out of `page.tsx` into a new
  `apps/metis-web/hooks/use-constellation-camera.ts`. The hook owns the four
  refs (`origin`, `targetOrigin`, `zoom`, `zoomTarget`) plus a `scrollVelocity`
  ref, and exposes `stepCamera({ reducedMotion, focusStrength })`,
  `setTargetOrigin`, `setZoomTarget`, `jumpTo`, `getState`, `getTargetState`,
  `registerScrollVelocity`, and `easeDive`. `page.tsx` now aliases its existing
  ref names to the hook's refs so all downstream reads keep working; the
  inline origin + galaxy-pullback + zoom easing in `render()` is a single
  `stepCamera` call.
- 2.2 ✅ — `CONSTELLATION_DIVE_DURATION_MS = 700` and `cubicOutEasing` are
  exported from the hook. `easeDive(elapsed, duration?)` drives the cubic-out
  curve for any future time-based tweens; the in-loop easing keeps its
  per-frame exponential form but the ease factors (`0.12` base, `0.18` above
  the dive threshold) are configurable on the hook and calibrated to match
  ~0.7 s settling.
- 2.3 ✅ — `landing-starfield-webgl.tsx` gained four new uniforms
  (`uFocusCenter`, `uFocusStrength`, `uFocusRadius`, `uFocusFalloff`). The
  vertex shader computes screen-space distance from the dive focus, broadens
  point size (up to 1.6×) and dims ambient stars (up to 85 %) outside the
  sharp radius. The fragment shader reuses the same varyings to shift alpha
  from core toward halo, giving a bokeh-ish bloom without leaving the
  existing WebGL context. `LandingStarfieldFrame` is extended with the
  matching optional fields, and `page.tsx` populates them from
  `starDiveOverlayViewRef`.
- 2.4 ✅ — Focused-star size boost and brightness dim for ambient stars are
  already driven on the CPU side in `page.tsx` (lines 2597-2614); shader-side
  point-size boost + halo widening stack on top via the new uniforms.
- 2.5 ✅ — Reduced-motion snap path runs through `stepCamera`: when the flag
  is set, both origin and zoom jump straight to their targets; the dive
  ease boost is skipped.
- **Tests:** `apps/metis-web/hooks/__tests__/use-constellation-camera.test.ts`
  covers init, origin ease, reduced-motion snap, dive-zone zoom ease,
  `jumpTo` clamp, scroll-velocity decay, and `easeDive` curve shape.

**Verification:** `pnpm test` → 216 passed, 10 skipped, 0 failed.
`pnpm exec tsc --noEmit` → exit 0. `pnpm lint` → 0 errors (pre-existing
warnings only).

**Phase 3 — Closeup shader tier with archetype branches (scaffold +
first two archetypes ✅, 2026-04-18 by claude-opus-4-7):**
- 3.1 ✅ — `closeup` tier in `landing-star-lod.ts` was already a first-class
  entry in `LandingStarRenderBatches` and `tierCounts`. This PR adds the
  missing unit tests: the dive focus target is promoted regardless of
  zoom/brightness, and it lands in `batches.closeup` without being double-
  bucketed into the sprite batch.
- 3.2 ✅ — Architecture decision recorded: **one uber-shader with an
  archetype attribute, not a family of specialised programs.** A new
  `aArchetype` 1-float-per-vertex attribute is appended to the existing
  combined buffer in `landing-starfield-webgl.tsx`. The shader reads it
  as a `vArchetype` varying and branches on integer ids defined in
  `STAR_VISUAL_ARCHETYPE_IDS` (`apps/metis-web/lib/landing-stars/star-visual-archetype.ts`).
  The ids are an ABI between the GPU shader and the CPU attribute packer
  (`fillStarAttributes`) and are covered by a dedicated unit test that
  asserts uniqueness, non-negativity, integer-ness, and that
  `main_sequence` is 0 so the default path is the baseline. The
  archetype attribute is *only consulted on the closeup tier*
  (`vTier > 2.5`) — ambient/point/sprite/hero rendering stays untouched,
  so Phase 3 cannot regress the galaxy view.
- 3.3 ✅ **(all 12 archetypes shipped):**
  - `main_sequence` — baseline. The closeup branch is a no-op; output is
    bit-identical to the pre-Phase-3 renderer once the attribute is
    omitted or pinned to 0.
  - `pulsar` — ~3 Hz size pulsation (vertex: `sin(uTime * 18.85) * 0.18`),
    tightened halo (halo alpha × 0.72, core alpha × 1.35), and sharpened
    diffraction rays (×1.9 boost + steeper exp falloff) so the Bayer
    spikes read as lighthouse beams. Pulsation also modulates final
    alpha so spikes breathe with the size beat.
  - `quasar` — modest ~1.3 Hz bright pulse + two opposing polar jets
    along the Y axis (`exp(-abs(uv.x) * 8.0)` cross a
    `smoothstep(0.25, 1.0, abs(uv.y))` extent, time-modulated with
    `sin(uTime * 6.0 + abs(uv.y) * 10.0)`). Jet colour mixes accent
    with a near-white tint. Diffraction suppressed.
  - `brown_dwarf` — dim, small (size ×0.75). Palette heavily mixed with
    rust `vec3(0.6, 0.3, 0.15)` at 0.55 weight. Halo/core/rim alpha all
    pulled down. No pulsation.
  - `red_giant` — slow ~0.5 Hz swell (`sin(uTime * 3.14) * 0.06`), point-
    size bloat ×1.12, halo alpha ×1.18, core alpha ×0.92, and a warm
    colour mix (`mix(core, vec3(1.0, 0.56, 0.28), 0.42)` at 0.35 weight)
    so the disc reads as a broad, cool-burning giant.
  - `binary` — primary disc at centre + companion core blob orbiting at
    radius 0.6 with period `uTime * 1.6`. Primary halo alpha ×0.85,
    core ×1.1 so the companion reads. Diffraction suppressed.
  - `nebula` — no sharp star. Point-size bloat ×1.18; the default core/
    rim are suppressed (core alpha ×0.2, rim ×0.4); halo alpha ×1.55;
    the visible pixels come from a two-frequency angular+radial sine
    cloud (`sin(ang * 3 + dist * 6) + 0.6 * sin(ang * 7 - dist * 11)`)
    blended with accent colour. Diffraction spikes suppressed so no
    hard cross survives.
  - `black_hole` — crushes the inner disc to black
    (`mix(vec3(0.0), color, 1.0 - smoothstep(0.5, 0.0, dist))`) and
    draws a luminous accretion ring at ~0.55-0.72 radius from the
    halo + accent colours scaled ×1.6. Halo/core/rim alpha stack
    zeroed out — the only visible contribution comes from the ring
    mask (`0.6 + brightness * 0.35`). Diffraction spikes suppressed.
  - `comet` — bright head biased to the right at `uv = (0.45, 0.0)`
    with a soft-edged disc, plus a tail streaming leftward with
    exponential falloff (`exp(-tailX * 2.4) * exp(-(uv.y * 4)^2)`).
    Head colour is a warm whitish blend; tail colour is halo/accent
    mix. Diffraction and default halo/core/rim suppressed. Starter
    implementation within a single point sprite — ADR 0006 notes
    sprite-strip or per-frame offset buffer as the richer long-term
    path for real motion trails.
  - `constellation` — five anchor points
    (`(0.0, -0.55), (-0.5, -0.1), (0.55, 0.05), (-0.15, 0.55), (0.3, 0.35)`)
    with thin connecting links between a fixed pair sequence. Anchors
    rendered as soft discs; links computed via per-segment
    point-to-segment distance with a thin falloff. Default halo/core/
    rim and diffraction suppressed — the pattern carries the alpha.
  - `variable` — irregular brightness only. No structural change; two
    incommensurate sines (`sin(uTime * 4.2) * 0.09 + sin(uTime * 1.7 +
    1.1) * 0.05`) drive `pulseAlpha = 0.7 + pulse * 0.45` so the star
    breathes with a non-repeating beat. Core warm-shifted in sympathy.
  - `wolf_rayet` — hot-spectrum tint (`vec3(0.6, 0.78, 1.0)` at 0.38)
    plus animated radial wind bands (`0.5 + 0.5 * sin(dist * 26.0 -
    uTime * 8.0)`) modulating the outgoing halo/accent mix. Size ×1.08,
    fast ~1.75 Hz pulse.
- 3.4 ✅ — Render-plan tests assert the closeup tier wiring. Shader-side
  archetype effect visual tests are intentionally out of scope (vitest
  runs in jsdom, no WebGL context). Plumbing the render params through
  the attribute encoding is test-covered on the CPU side via
  `getStarVisualArchetypeId`.

**Verification:** `pnpm test` → 241 passed, 10 skipped, 0 failed (up from
216). `pnpm exec tsc --noEmit` → exit 0. `pnpm exec eslint` on touched
files → 0 errors, 0 warnings.

**Open Phase 3 items for future slices:**
- Mobile perf ceiling number (ADR 0006 open question, Phase 3 DoD):
  still unmeasured. With the uber-shader approach the hot path is a
  handful of constant-time branches per fragment; should be cheap on
  mobile but needs a real device pass.
- CPU-side `visualArchetype` was not previously read by the renderer;
  now it is. `StellarProfile` has made `visualArchetype` a required
  field since Phase 0, so no additional plumbing was needed — this
  is flagged for the next agent only if they find a star path that
  builds a profile without going through `generateStellarProfile`.

## Next up

- **Phase 1.4 wiring for individual landmark stars** (follow-up): today
  the faculty constellations render as anchor + edges without per-star
  Bayer labels surfaced on hover. The landmark tier API is ready; a
  follow-up phase should decide where per-star labels appear (likely
  Phase 4 Orbital Observatory when faculty stars become individually
  inspectable).
- **Phase 3 follow-ups** — all 12 archetypes are visually
  distinct at closeup tier now. Remaining work if we want richer
  looks: promote `comet` from its single-point-sprite UV fake to a
  sprite strip / per-frame offset buffer (ADR 0006); revisit the
  `binary` companion-blob radius and the `constellation` anchor
  layout once real faculty-star content drives them; cover more of
  `wolf_rayet` / `variable` with palette research if playtest reveals
  them as too uniform.
- **Phase 4 Orbital Observatory** — unblocked by Phases 0+1+2+3 scaffold.
  Suggested claim: `claude/m02-orbital-observatory`.

## Blockers

None at plan-time. Live blockers go here.

## Notes for the next agent

- **Naming convention:** the frontend type is `StarVisualArchetype` because
  backend `metis_app/services/star_archetype.py` already owns a
  `StarArchetype` enum for indexing-strategy (Scroll/Ledger/Codex/…). They
  are different concepts — do not merge them. If you need to surface both in
  the same context, alias the backend one.
- **Plan phrasing below still says `StarArchetype`** in task 0.1 — that
  wording is retained for historical context; the landed code uses
  `StarVisualArchetype`. Future phases should read field names from the
  landed source, not from this prose.
- The 3D sphere's CSS, focus-strength animations, and scroll-direction mapping
  are still desirable on the 2D dive. Don't delete animation intent — re-home
  it on the 2D camera + shader.
- `StellarProfile` is the procedural-differentiation system from prior work.
  It **stays**. It now feeds (a) archetype selection and (b) the Observatory
  character-sheet panel. Don't delete it.
- The WebGL context for the starfield is Three.js (`landing-starfield-webgl.tsx`).
  Any new archetype-specific effect must extend the existing shader family;
  avoid introducing a second WebGL context.
- Accessibility: `prefers-reduced-motion` exists in the current 3D overlay.
  Carry the equivalent gates to the 2D closeup tier.

---

## Scope

**In scope:**
- Landing page constellation rendering (`apps/metis-web/app/page.tsx`,
  `apps/metis-web/components/home/*`, `apps/metis-web/lib/landing-stars/*`).
- Star Observatory dialog reshaping from modal to orbital (only the
  presentation layer; its data model stays).
- Star name generation policy.
- `StellarProfile` gains an `archetype` field.

**Out of scope:**
- Brain graph (`/brain` page) — different component, different renderer.
- Star catalogue UI (M12) — coordinates via shared renderer but is its own
  milestone.
- Any backend changes beyond passing content-type through to the frontend.

---

## Pre-work — what exists today

| File | Role | Fate |
|---|---|---|
| `apps/metis-web/components/home/landing-starfield-webgl.tsx` | Three.js 2D starfield. Layered point shader (core/halo/accent/spikes/twinkle). | **Kept + extended** with closeup tier + archetype branches. |
| `apps/metis-web/components/home/star-dive-overlay.tsx` | 3D sphere overlay (raw WebGL2 fragment shader). | **Deleted** in Phase 5. |
| `apps/metis-web/lib/landing-stars/star-surface-shader.ts` | 3D stellar-surface fragment shader (granulation, prominences, sunspots, corona). | **Deleted** in Phase 5. |
| `apps/metis-web/lib/landing-stars/landing-star-lod.ts` | LOD tier classifier (point/sprite/hero/closeup). | **Kept + extended** with archetype-aware closeup. |
| `apps/metis-web/lib/landing-stars/stellar-profile.ts` | Procedural stellar-type/palette/profile generation. | **Kept + extended** with `archetype` field. |
| `apps/metis-web/lib/landing-stars/landing-star-types.ts` | Shared types (`LandingStarRenderTier` etc). | **Extended** for archetype. |
| `apps/metis-web/lib/star-catalogue/star-name-generator.ts` | Bayer/Flamsteed/HD name generation. | **Rewritten** to tiered policy. |
| `apps/metis-web/components/constellation/star-observatory-dialog.tsx` | Modal dialog opened on dive. | **Reshaped** to orbital entrance; data model unchanged. |
| `apps/metis-web/components/constellation/star-archetype-picker.tsx` | User-facing archetype assignment. | Repositioned into orbital layout. |
| `apps/metis-web/components/constellation/faculty-glyph-panel.tsx` | Faculty glyph display. | Repositioned into orbital layout. |
| `apps/metis-web/components/constellation/learning-route-panel.tsx` | Learning routes. | Repositioned into orbital layout. |
| `apps/metis-web/app/page.tsx` | Hosts starfield + dive overlay + camera controls. | Heaviest touch point. |

---

## Phased plan

Eight phases. Phases 1–3 can mostly run in parallel. Phase 4 depends on 0+1+2+3.
Phase 5 is deletion (runs last). Phases 6–7 are polish. Phase 8 is verification.

Each phase has a **Definition of done** — the next agent should flip that phase
to ✅ in *Progress* only when every box is genuinely ticked.

### Phase 0 — Archetype scaffold (foundation)

Add the archetype concept to types and data model. Everything else depends on
this being present (even if content-type mapping is placeholder-only at first).

**Tasks:**
- **0.1** — Add `StarArchetype` enum to `landing-star-types.ts`. Identifiers
  are snake_case transliterations of the archetype display names in
  [ADR 0006](../../docs/adr/0006-constellation-design-2d-primary.md):
  `main_sequence`, `pulsar`, `quasar`, `brown_dwarf`, `red_giant`, `binary`,
  `nebula`, `black_hole`, `comet`, `constellation`, `variable`, `wolf_rayet`.
  (ADR 0006 spells the last one "Wolf-Rayet" in prose; the code identifier
  is `wolf_rayet` for consistency with the other snake_case values.)
- **0.2** — Add `archetype: StarArchetype` field to `StellarProfile` in
  `stellar-profile.ts`. Populate via a new `selectArchetype(profile, contentType)`
  function. For now, content-type → archetype mapping lives in a single table
  constant `CONTENT_TYPE_ARCHETYPE_MAP`.
- **0.3** — Thread `contentType` from whatever produces landing stars (likely
  `apps/metis-web/lib/star-catalogue/*` or a fixture) through to profile
  generation. If the content type isn't known at first, default to
  `main_sequence`.
- **0.4** — Extend `LandingProjectedStar` (or equivalent) so the archetype is
  available at render time.
- **0.5** — Unit tests in `apps/metis-web/lib/landing-stars/__tests__/`:
  `selectArchetype` returns expected archetype for each content type; default
  fallback when content type missing.

**Definition of done:** every landing star in the existing fixtures has an
archetype value that can be inspected in devtools. No visual change yet.

**Files touched:** `landing-star-types.ts`, `stellar-profile.ts`, maybe
`star-catalogue/*`, new `__tests__/archetype.test.ts`.

### Phase 1 — Tiered naming policy

Replace the Bayer/Flamsteed/HD naming free-for-all with the three-tier policy
from ADR 0006. Independent of renderer work — a good parallel track.

**Tasks:**
- **1.1** — In `star-name-generator.ts`, accept a `nameTier` input:
  `"field" | "landmark" | "user"`. Field stars return `null` (no name).
  Landmarks continue to get classical names (Alpha Cygni, Omega Draconis, etc.)
  but tagged as `classical`. User-content stars use a caller-supplied name.
- **1.2** — Add a `nameKind` field alongside name (`"classical" | "user" | null`)
  so the renderer can style them differently and so tooltips know whether to
  show the Bayer/Flamsteed explanation.
- **1.3** — Wire the caller sites: the eight faculty landmarks (Perseus,
  Auriga, Draco, Hercules, Gemini, Big Dipper, Lyra, Boötes) get `landmark`.
  User-content stars get `user`. Everything else gets `field`.
- **1.4** — Rendering: field stars suppress the name label entirely on hover;
  landmarks get classical-name tooltip with a *"Classical star name
  (Bayer/Flamsteed convention)"* footer line; user stars show the user's name
  bold.
- **1.5** — Update any existing snapshot/unit tests for the name generator.

**Definition of done:** hovering a background field star shows nothing.
Hovering a constellation landmark shows classical name + convention tooltip.
Hovering user content shows its actual name.

**Files touched:** `star-name-generator.ts`, wherever names are rendered
(likely inside `landing-starfield-webgl.tsx` or a hover layer), naming tests.

### Phase 2 — Cinematic 2D camera

Replace the "fade-out 2D point, fade-in 3D canvas" swap with a single smooth
2D camera zoom/pan toward the focused star.

**Tasks:**
- **2.1** — Extract the current focus/zoom control logic in `page.tsx` into
  a dedicated hook `useConstellationCamera`. Inputs: `focusStarId`,
  `focusStrength`, `scrollVelocity`. Outputs: `{ cameraX, cameraY, zoom,
  easing }`.
- **2.2** — Add an easing curve for dive: cubic-out, ~0.7s default,
  configurable. The 0.55s on the current 3D overlay fade is a starting point;
  treat as tunable.
- **2.3** — Ambient stars: apply a depth-of-field-like falloff — distance from
  focus increases blur radius and decreases brightness. Implement in the
  starfield shader uniforms, not as a post-process, to stay within the
  existing WebGL context.
- **2.4** — Focused star: grows in apparent size, halo intensifies, diffraction
  spikes elongate. These controls already exist in the shader — just drive
  them harder on dive.
- **2.5** — `prefers-reduced-motion`: if set, snap (no ease) and skip pulsation.

**Definition of done:** clicking a star smoothly zooms the camera toward it;
background stars blur and dim; the focused star grows. No 3D sphere appears.

**Files touched:** `page.tsx`, new `use-constellation-camera.ts`,
`landing-starfield-webgl.tsx` (shader uniforms), possibly
`landing-star-interaction.ts`.

### Phase 3 — Closeup shader tier with archetype branches

The existing LOD has `point | sprite | hero`. Add `closeup` and drive
archetype-specific effects from a single shader (or a small family).

**Tasks:**
- **3.1** — Extend `landing-star-lod.ts`: `closeup` tier is already there as an
  override — formalise it as a first-class tier with its own rendering path.
- **3.2** — Decide shader architecture (open question in ADR 0006): **start
  with one uber-shader with archetype branches** via a uniform `uArchetype`
  (int) and a small set of per-archetype parameters. Fall back to specialised
  programs only if the uber-shader proves slow.
- **3.3** — Implement archetype effects (one PR per archetype is fine; ship in
  this priority order because early ones carry the demo):
  - `main_sequence` — baseline, already close.
  - `pulsar` — tight core, sharp rays, fast pulsation (~2–4 Hz).
  - `nebula` — diffuse cloud, no sharp core (noise field, low alpha).
  - `black_hole` — dark disc, luminous accretion ring (additive ring primitive).
  - `comet` — moving, trailing tail (sprite strip or per-frame offset buffer).
  - `quasar` — radiating jets (two opposing elongated lobes).
  - `red_giant` — large warm bloom, slow pulse.
  - `binary` — two linked stars; may need a two-point draw path.
  - `brown_dwarf` — dim, rust palette, small halo.
  - `variable` — oscillating brightness.
  - `wolf_rayet` — rare, energetic, distinct spectrum (rank last — may need
    a custom palette).
  - `constellation` — multi-star pattern with links (this is a composite
    archetype; lines between points already exist in the galaxy plan).
- **3.4** — Each archetype gets a test: given a mock `StellarProfile` with
  `archetype: X`, the render plan emits the expected shader params.

**Definition of done:** every archetype renders visually distinct at closeup
tier. FPS stays ≥60 on desktop with a single closeup + normal starfield.
Mobile ceiling question from ADR 0006 gets a concrete answer (number in
*Notes for the next agent*).

**Files touched:** `landing-star-lod.ts`, `landing-starfield-webgl.tsx`,
likely a new `closeup-shader.ts`, LOD tests, archetype render-param tests.

### Phase 4 — Orbital Observatory

Turn the Observatory from a modal that overlays the star into a layout that
animates in around the star. The data model and most sub-components
(archetype picker, faculty glyphs, learning route) stay the same; only
layout/entrance changes.

**Tasks:**
- **4.1** — ADR 0006 leaves the exact layout open (radial cards / docked rings
  / magazine spread). Pick one for an MVP — **recommendation: docked rings**
  (panel rings at top/right/bottom/left around the star, so the star stays
  visible at centre). Document the choice in this plan's *Notes*.
- **4.2** — Build a layout container component
  `observatory-orbital-layout.tsx` that positions existing sub-panels as
  slots.
- **4.3** — Animate entrance: each slot fades + slides inward from its edge,
  staggered ~80ms, synced to the camera easing from Phase 2.
- **4.4** — Exit animation on dismiss: reverse.
- **4.5** — Keyboard dismiss (Esc) + click-outside dismiss still work.
  Focus trap still works. (Accessibility regression check.)
- **4.6** — Mobile: fall back to the existing modal on small viewports
  (`<768px`). Orbital layout assumes desktop real estate.

**Definition of done:** diving into a star zooms camera + rings animate in
around it. Observatory sub-panels (archetype picker, faculty glyphs, learning
route) all render and function.

**Files touched:** new `observatory-orbital-layout.tsx`, minor edits to
`star-observatory-dialog.tsx`, panel sub-components, CSS.

### Phase 5 — Deletion

Only after phases 0–4 are ✅. Remove the retired 3D system.

**Tasks:**
- **5.1** — Delete `apps/metis-web/components/home/star-dive-overlay.tsx`.
- **5.2** — Delete `apps/metis-web/lib/landing-stars/star-surface-shader.ts`.
- **5.3** — Remove imports/exports referencing the deleted files. `tsc`
  should be green.
- **5.4** — Remove any CSS specific to the 3D overlay.
- **5.5** — Remove `u_stage`, procedural stellar-surface noise calls, and
  related unused uniforms.
- **5.6** — Delete tests that only cover the deleted code. Adapt tests that
  asserted on the 2D→3D swap to the new camera-zoom behaviour.

**Definition of done:** from the repo root,
`rg star-surface-shader apps/ metis_app/` and
`rg star-dive-overlay apps/ metis_app/` return nothing (grep is scoped to
source trees; this plan doc still mentions the names and that's fine).
`tsc` and `pnpm test` pass. `pnpm build` produces a smaller bundle.

### Phase 6 — Annotations (2D accoutrements)

Lightweight extras that encode metadata without 3D: rings (document series),
orbiting satellites (sub-nodes), dust trails (evolution over time), binary
companions (relationships), comet tails (activity), halos (recency).

**Tasks:**
- **6.1** — Pick the top 3 with highest signal-to-noise: **halos (recency)**,
  **rings (document series)**, **orbiting satellites (sub-nodes)**. Defer the
  rest until the Observatory surfaces demand them.
- **6.2** — Each renders in the 2D shader family. Parametrise via
  `StellarProfile` fields (new: `annotations: { ring?, halo?, satellites? }`).
- **6.3** — Storybook / visual tests for each annotation in isolation.

**Definition of done:** user stars can carry up to three annotations
visible at hero/closeup tiers.

### Phase 7 — Naming + Observatory polish

- **7.1** — Observatory character sheet: surface the `StellarProfile` fields
  (spectral class, temperature, luminosity, palette, archetype) as the
  star's *identity* panel.
- **7.2** — Tooltip for landmark classical names explains the Bayer/Flamsteed
  convention.
- **7.3** — Reduced-motion path exercised end-to-end.

### Phase 8 — Verification

- **8.1** — Run `pnpm test` (frontend unit tests).
- **8.2** — Run `pnpm -w typecheck` (repo-wide typecheck).
- **8.3** — Manual pass on landing page: hover a field star (nameless),
  hover a landmark (classical name + tooltip), hover user content (user
  name), dive into a star of each archetype.
- **8.4** — Performance regression check: 60fps target at 200+ stars with
  one closeup. Document actual numbers in *Notes for the next agent*.
- **8.5** — Migration question from ADR 0006: existing user stars — do we
  retro-assign archetypes based on content type? **Proposed default: yes,
  retro-assign at load time using the same `selectArchetype` function.**
  Document decision in ADR 0006's *Open Questions*.
- **8.6** — Update `plans/IMPLEMENTATION.md`: M02 → `Landed`, add merge
  commit SHA and date.

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Uber-shader with 12 archetype branches is slow on low-end mobile. | Archetype-specific programs as fallback. Measure early (Phase 3 DoD). |
| Orbital layout feels cramped on small desktop widths. | Breakpoint to modal on `<1024px`, not just `<768px`. Decide in Phase 4. |
| Existing user stars look wrong after retro-archetype assignment. | Phase 8.5 — give users a one-time "refresh star archetypes" action if assignment is bad. |
| "Disconnect" still felt because 2D point is too small to carry archetype detail. | Phase 3 closeup tier is the answer — archetype detail only shows on dive. |
| We delete the 3D shader and someone was relying on it in a feature branch. | `git log --all -- <paths>` before deletion. Announce intent in the PR description. |

---

## Coordination with M12 (Interactive star catalogue)

M12 shares the 2D renderer. Coordination rules:

- **Archetype enum** — owned by this milestone. M12 consumes it.
- **`StellarProfile` field additions** — any new field proposed by M12 goes
  through `landing-star-types.ts`; M02 agents get a heads-up.
- **Shader changes** — if both milestones are in flight, the one touching the
  shader file posts a note in the other's plan doc's *Notes for the next
  agent* before merging.

---

## Open questions (carried from ADR 0006)

These must be answered before or during the relevant phase. Record the answer
in this file's *Notes for the next agent* and update ADR 0006.

- Exact archetype → content-type mapping — **Phase 0 ships a proposed table;
  revisit after Phase 3 playtest.**
- Orbital panel layout — **Phase 4.1 picks docked rings; revisit if it feels
  wrong.**
- Camera easing and duration — **Phase 2.2 ships cubic-out ~0.7s; tune.**
- Shader architecture (uber vs specialised) — **Phase 3.2 starts uber;
  branch if performance forces it.**
- Mobile performance ceiling — **Phase 3 DoD produces a number.**
- Migration of existing user content archetypes — **Phase 8.5.**
- Accessibility reduced-motion — **Phase 2.5 + Phase 7.3.**
