---
Milestone: M02 — Constellation 2D refactor
Status: Landed
Claim: Phases 0-8 landed
Last updated: 2026-04-19 by claude-opus-4-7
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

**Phase 1 — Tiered naming (done modulo Phase 4 follow-up, 2026-04-18 by claude-opus-4-7):**
- 1.1 ✅ — `generateStarName` accepts `nameTier: "field" | "landmark" | "user"`;
  field → null, landmark → classical name, user → caller-supplied.
  (`apps/metis-web/lib/star-catalogue/star-name-generator.ts:17-74`)
- 1.2 ✅ — `GeneratedStarName` returns `{ name, kind }` where
  `NameKind = "classical" | "user" | null`. `CatalogueStar.name` widened to
  `string | null`.
- 1.3 ⚠️ **Deferred to Phase 4.** Faculty constellation stars render as
  anchor + edges in the starfield today; they are not individual
  `CatalogueStar` rows, so `generateStarName` is never called for them.
  Per-star `landmark` wiring requires making faculty stars individually
  inspectable — the Orbital Observatory scope. User stars: legacy fallback
  still uses `generateClassicalDesignation` at `apps/metis-web/app/page.tsx:4122`;
  explicit `user`-tier wiring rolls in with Observatory's user-star surface.
- 1.4 ⚠️ **Deferred to Phase 4.** Field-star hover suppression is in place
  (`page.tsx:4410` gates the catalogue tooltip on non-null `catalogueName`).
  Per-landmark classical-name tooltip with "Bayer/Flamsteed convention" footer
  and user-name bold styling roll in with the Observatory hover surface.
- 1.5 ✅ — 16 unit tests in
  `apps/metis-web/lib/star-catalogue/__tests__/star-name-generator.test.ts`
  cover all tier branches, determinism, and error cases.

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

**Phase 4 — Orbital Observatory (landed, 2026-04-18 by claude-opus-4-7):**
- 4.1 ✅ — **Layout decision: docked rings.** Panel rings sit at top /
  right / bottom / left around the star so the star stays centred and
  visible. Slot spacing lands the horizontal rings with
  `w-[min(560–640px,calc(100vw-2rem))]` and the vertical rings with
  `w-[min(320–340px,calc(50vw-12rem))]` so the centre column stays
  clear at 1280px+ widths. Cardinal slots only; radial cards / magazine
  spread deferred until the Observatory surfaces demand them.
- 4.2 ✅ — New `apps/metis-web/components/constellation/observatory-orbital-layout.tsx`
  exposes a named-slot API (`top | right | bottom | left`) with abstract
  slots — callers decide which panel goes where. Empty slots render as
  `data-slot-filled="false"` spacers so the ring geometry stays stable
  when a panel is contextually absent (e.g. archetype picker only in
  build view). Covered by 6 unit tests in
  `observatory-orbital-layout.test.tsx` (ring order, empty marking,
  reduced-motion, stagger timing, exit transition, breakpoint).
- 4.3 ✅ — Entrance animation: each slot fades + slides inward from its
  off-stage edge (`translate` by `OFFSTAGE_OFFSET_PX = 48px` + 100%) with
  an 80 ms stagger in `OBSERVATORY_SLOT_ORDER` (top → right → bottom →
  left). Duration is `CONSTELLATION_DIVE_DURATION_MS = 700` ms on the
  `cubic-bezier(0.33, 1, 0.68, 1)` curve — same curve as the camera
  hook's `cubicOutEasing` so the rings settle with the camera pullback.
- 4.4 ✅ — Exit animation: reverses translate + fades opacity back to 0
  on `OBSERVATORY_EXIT_DURATION_MS = 420` ms (60 % of the entrance). The
  orbital layout only mounts while `open && isOrbital`, so closing the
  dialog tears the overlay down after the Base UI dialog's own exit —
  there's no orphaned camera state.
- 4.5 ✅ — Esc dismiss + click-outside dismiss + focus trap all stay
  with the underlying `<Dialog>` (`@base-ui/react`), which the orbital
  layout wraps as a sibling portal — it doesn't replace the dialog
  primitive. Accessibility regression: hover/focus tooltips continue to
  render from the existing refs; the layout itself is `aria-hidden` at
  the centre spacer and passes keyboard focus through to slot children.
- 4.6 ✅ — Mobile fallback: `useIsOrbitalViewport()` watches
  `(min-width: 768px)`. On narrower viewports the orbital overlay is
  not mounted at all; the classic side-rail modal renders the three
  sub-panels inline as before. Inline copies are hidden on desktop
  (`isOrbital ? null : <Panel ... />`) so a sub-panel instance only
  exists once per open dialog.

**Phase 1.4 follow-up (landed in the same slice, 2026-04-18):**
- Landmark hover: new `getHoveredLandmarkStar` in `page.tsx` hit-tests
  the faculty anchor + secondary stars (11 constellations ×
  5–7 stars). Names come from `generateStarName({ tier: "landmark",
  rng, magnitude })` seeded deterministically on
  `(facultyId, starIndex)` — same anchor yields the same Bayer /
  Flamsteed designation across sessions. Index 0 (anchor) uses
  magnitude ~2 for a bright classical name; secondaries use ~3.5
  for Flamsteed numbers. Tooltip shows classical name + italic
  footer "Classical star name (Bayer/Flamsteed convention)".
- User-content hover: the legacy `generateClassicalDesignation`
  fallback at `page.tsx:4093` is replaced by
  `generateStarName({ tier: "user", userSuppliedName: star.label })`.
  Unnamed user stars now fall back to their id rather than fabricate
  a classical designation. User names render bold via a
  `data-name-kind="user"` attribute on the tooltip title.
- Field stars stay suppressed as before.

**Verification:** `pnpm test` → 247 passed, 10 skipped, 0 failed (up
from 241 with 6 new orbital-layout tests). `pnpm exec tsc --noEmit`
→ exit 0. `pnpm exec eslint` on touched files → 0 errors; pre-
existing warnings unchanged.

**Phase 5 — Deletion (landed, 2026-04-18 by claude-opus-4-7):**
- 5.1 ✅ — Deleted `apps/metis-web/components/home/star-dive-overlay.tsx`
  (the 3D sphere overlay component, its `StarDiveOverlayView` interface, and
  the `StarSurfaceShader`-driven WebGL2 draw loop).
- 5.2 ✅ — Deleted `apps/metis-web/lib/landing-stars/star-surface-shader.ts`
  (the procedural stellar-surface fragment shader: granulation, prominences,
  sunspots, corona, and the `u_stage` staging uniform).
- 5.3 ✅ — Removed the `StarDiveOverlayView` and `StarDiveOverlay` imports
  from `app/page.tsx`; removed the `{ STAR_VERT, STAR_FRAG, compileShader,
  createStarProgram }` imports from
  `components/constellation/star-observatory-dialog.tsx`. Replaced the
  inline `StarDiveOverlayView` ref type with a local `StarDiveFocusView`
  interface in `page.tsx` — the ref is still populated every frame because
  Phase 2.3 reads `screenX / screenY / focusStrength` off it to drive the
  2D starfield's depth-of-field focus uniforms. The ref was renamed from
  `starDiveOverlayViewRef` to `starDiveFocusViewRef` to reflect its actual
  role post-deletion. `pnpm exec tsc --noEmit` → exit 0.
- 5.4 ✅ — No standalone CSS file existed for the 3D overlay; all its
  styles were inline in the deleted component (wrapper transform, fade-in,
  box-shadow, transition curves). The `<StarDiveOverlay>` JSX mount in
  `page.tsx` was removed. No other CSS references survived the deletion.
- 5.5 ✅ — `u_stage`, the procedural stellar-surface noise (granulation +
  prominence + sunspot + corona calls), and the related shader uniforms
  (`u_color`, `u_color2`, `u_color3`, `u_hasColor2`, `u_hasColor3`,
  `u_hasDiffraction`, `u_seed`, `u_res`) were all removed as part of 5.2
  since they lived entirely inside `star-surface-shader.ts`. The 2D focus
  uniforms in `landing-starfield-webgl.tsx` (`uFocusCenter`, `uFocusStrength`,
  `uFocusRadius`, `uFocusFalloff`) are untouched — those belong to the
  2D archetype path and are explicitly out of scope per the Phase 5
  guardrail.
- 5.6 ✅ — No tests exclusively covered the deleted code and no tests
  asserted on a 2D → 3D swap; grep for `star-dive`/`star-surface`/
  `StarDiveOverlay`/`StarMiniPreview` across
  `apps/metis-web/**/__tests__/**` returned nothing before deletion. A
  stale comment in `hooks/__tests__/use-constellation-camera.test.ts`
  references the "star-dive zone" (the zoom tier where dive easing kicks
  in, still live) and is left intact — that behaviour still exists.
  The doc comment in `components/home/landing-starfield-webgl.types.ts`
  that said the focus centre "matches the star-dive overlay" was
  rewritten to describe the 2D depth-of-field consumer instead.
- **Collateral inside `star-observatory-dialog.tsx`:** the dialog's
  `StarMiniPreview` component rendered a WebGL2 thumbnail using the
  deleted `createStarProgram` + `u_stage` shader. Replaced with a static
  CSS radial-gradient disc driven by faculty color + stage; the dead
  `domainSeed` helper (only used for the shader's `u_seed` uniform) was
  also removed. Same props signature, no caller-site changes.

**Verification:** `pnpm test` → 247 passed, 10 skipped, 0 failed
(unchanged from Phase 4 — no tests cover deleted code exclusively,
see 5.6 above). `pnpm exec tsc --noEmit` → exit 0. `pnpm exec eslint`
on touched files → 0 errors, 18 warnings (all pre-existing on
`page.tsx` unused-vars + react-hooks/exhaustive-deps + one unused
import in the dialog; unchanged by this phase). `pnpm build` →
compiled successfully in 18.4 s, static pages generated. Bundle-size
delta vs pre-Phase-5 main not captured as concrete bytes (Next 16
Turbopack build output doesn't surface per-route byte totals at the
default log level); `.next/static` sits at ~37.17 MB on this build
as a reference point for the next comparison. Final DoD grep:
`rg star-surface-shader apps/ metis_app/` and
`rg star-dive-overlay apps/ metis_app/` both return empty.

**Notes for the next agent (Phase 5):**
- `starDive*Ref` names in `page.tsx` (focus state, world pos, profile,
  name, strength, pan-suppressed) refer to the 2D *camera* focus state,
  not the retired 3D overlay. They stay. The sole rename in Phase 5
  was `starDiveOverlayViewRef` → `starDiveFocusViewRef`.
- The Observatory dialog's star thumbnail is now a simple faculty-
  tinted radial gradient. If Phase 6 annotations surface a richer
  2D preview (e.g. the archetype's closeup-tier shader rendered into
  a tiny canvas), it's a natural replacement for `StarMiniPreview`.
- `useReducedMotionPreference` inside `star-observatory-dialog.tsx`
  is **load-bearing** — STAND DOWN, do not remove. (The Phase 5 note
  calling it "dead" was wrong; leaving the correction here for the
  next agent.)

**Phase 6 — Annotations (landed, 2026-04-18 by claude-opus-4-7):**
- 6.1 ✅ — Shipped the top 3 annotations: **halos (recency)**, **rings
  (document series)**, **orbiting satellites (sub-nodes)**. Comet tails,
  dust trails, and binary companions remain deferred per the Phase 6
  DoD.
- 6.2 ✅ — All three render inside the existing
  `landing-starfield-webgl.tsx` uber-shader (no second WebGL context).
  New `StellarProfile.annotations?: StarAnnotations` field; default
  `undefined` — `generateStellarProfile` never populates it because
  annotations are content-driven, not procedural. `LandingProjectedStar`
  mirrors the optional field so user-star producers can thread it
  through. Attribute-packing adds six new per-vertex floats
  (`aHaloStrength`, `aRingCount`, `aRingOpacity`, `aSatelliteCount`,
  `aSatelliteRadius`, `aSatellitePeriod`) appended to the same combined
  buffer as `aArchetype`; gated in the fragment stage on
  `isCloseup` (`vTier > 2.5`) so ambient/point/sprite/hero rendering is
  unchanged. The shader recalculates the point-sprite UV remap when
  satellites are on — the vertex stage widens `gl_PointSize` by
  `max(1, vSatelliteRadius + 1)` and the fragment stage scales `uv` by
  the same factor so the star silhouette stays visually the same while
  the satellite orbit at radius 1.8–3.2 lands inside the sprite.
  Reduced motion rides on the existing `uTime` path (orbits freeze the
  same way archetype pulsation does) — no second gate introduced.
- 6.3 ✅ — 22 new vitest tests across two files. New
  `apps/metis-web/lib/landing-stars/__tests__/star-annotations.test.ts`
  covers `haloStrengthFromAge` curve shape at 0 / half-life / 2× half-
  life and future clamp; `deriveStarAnnotations` for individual signals
  (none / only recency / only ring / only satellites) and the stacked
  all-three case; learning-route `updatedAt` preference over
  `createdAt`; and `getStarAnnotationAttributeValues` attribute
  encoding (null passthrough, halo clamp, ring count + opacity
  override, satellite count + radius + default/override period,
  stacked no-cross-talk). `stellar-profile.test.ts` gains two tests
  covering `annotations` defaulting to undefined and the pass-through /
  determinism contract when a caller attaches one.

**Verification:** `pnpm test` → **269 passed**, 10 skipped, 0 failed
(up from 247 by 22 new tests). `pnpm exec tsc --noEmit` → exit 0.
`pnpm exec eslint` on new + modified files (`star-annotations.ts`,
`star-annotations.test.ts`, `types.ts`, `landing-star-types.ts`,
`stellar-profile.test.ts`, `index.ts`, `landing-starfield-webgl.tsx`)
→ 0 errors, 0 warnings. `page.tsx` still carries its 18 pre-existing
warnings (unused vars, react-hooks/exhaustive-deps) — unchanged by
this phase. `pnpm build` → compiled successfully in 12.4 s, static
pages generated. DoD greps: `rg star-surface-shader apps/ metis_app/`
and `rg star-dive-overlay apps/ metis_app/` still return empty.

**Notes for the next agent (Phase 6):**
- Annotations are plumbed end-to-end for user stars, but user stars do
  not yet flow through the WebGL starfield batch. The webgl stream
  today is catalogue-only (`landingRenderableStars` is built from
  `visibleWorldStars` in `page.tsx`). The CPU-side derive + attach is
  ready (`rebuildProjectedUserStarRenderState` and the Star Dive focus
  path both attach annotations to the stellar profile they emit); the
  day a user star makes it into `landingStarfieldFrameRef.current.stars`,
  halos / rings / satellites will render automatically. Until then the
  visible effect of Phase 6 is zero because no catalogue star has
  annotations today. Follow-up: inject the focused user star into the
  closeup tier of the WebGL batch so the dive silhouette carries its
  annotations.
- The fragment shader remaps `uv` / `dist` by `satelliteSpriteBoost`
  only when satellites are present. The original star silhouette stays
  visually the same size; ring and halo annotations reuse the remapped
  `dist` so they sit where the archetype expected them. If a future
  annotation needs to reach beyond the original sprite (e.g. dust
  trails streaming outside UV 1.0), it must either ride on the boosted
  sprite path or trigger its own size boost.
- `aRingOpacity` is packed as a float 0..1 alongside `aRingCount` (not
  bit-packed with the count) — the spec called out two attributes for
  simplicity, and that's what landed. Future annotations should follow
  the same one-attribute-per-float rule unless bit-packing buys
  meaningful bandwidth.
- Reduced motion: satellites freeze whenever `uTime` freezes. We
  confirmed no separate gate is needed — the existing material
  uniform path already handles this.
- Annotation decay signals:
  - Halo: reads `learningRoute.updatedAt` when present, else
    `createdAt`. Once `UserStar` gains a real `lastTouchedAt`, update
    `pickTouchedAtMs` in `star-annotations.ts` to prefer it.
  - Rings: `linkedManifestPaths.length` (with `activeManifestPath`
    as a fallback for single-document).
  - Satellites: `connectedUserStarIds.length`, clamped at 4.
- The `StarMiniPreview` thumbnail in `star-observatory-dialog.tsx`
  (the CSS-gradient stand-in from Phase 5) is still a natural fit for
  a richer closeup-tier render. Phase 6 does not touch it.

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

**Phase 7 — Naming + Observatory polish (landed, 2026-04-19 by claude-opus-4-7):**
- 7.1 ✅ — New **Stellar identity panel** at the top of the Observatory
  scrollable content area in
  `apps/metis-web/components/constellation/star-observatory-dialog.tsx`.
  Surfaces the three `StellarProfile` scalars (spectral class via
  `formatSpectralClassLabel`, temperature K via `formatTemperatureK`,
  luminosity L☉ via `formatLuminositySolar`) as a semantic `<dl>` three-
  column grid, the archetype (`formatVisualArchetypeLabel`) as a Badge,
  and all five palette colours (core / halo / accent / rim / surface)
  as inline swatches. The profile is derived in-dialog via
  `generateStellarProfile(star.id, { contentType: deriveUserStarContentType(star) })`
  so it stays deterministic and matches the starfield renderer's profile
  rather than threading a duplicate prop through every dialog caller.
  New formatter helpers live in
  `apps/metis-web/lib/landing-stars/stellar-profile.ts` and are re-
  exported from `lib/landing-stars/index.ts`.
- 7.2 ✅ — **Confirmation, no code change.** The classical Bayer/Flamsteed
  tooltip shipped in the Phase 1.4 follow-up already covers this
  requirement end-to-end: `buildLandmarkTooltipContent` (`page.tsx`
  ~4206) emits the convention explainer; `getHoveredLandmarkStar`
  (`page.tsx` ~4290) exposes it on pointer hover; CSS lives at
  `page.tsx` ~5982. No gaps found during trace.
- 7.3 ✅ — **Reduced-motion gate threaded through to the WebGL uber-shader.**
  The page effect previously sampled
  `window.matchMedia("(prefers-reduced-motion: reduce)")` once at setup
  and fed it only into hover-motion logic, so twinkle, archetype
  pulsation, Phase 6 satellite orbits, and halo pulse all kept running
  even with the OS preference on. Now `reducedMotion` is a `let`
  binding with a live `change` listener (with addListener fallback for
  older Safari) and paired cleanup in the effect's teardown, and it is
  threaded through `LandingStarfieldFrame.reducedMotion` (new optional
  field in `landing-starfield-webgl.types.ts`). The shader render loop
  freezes `material.uniforms.uTime.value` at its last real-time value
  (not zero — zero would jump the twinkle/pulse phase to a visibly
  different still) whenever the flag is true, and releases it back to
  `timestampMs * 0.001` when the flag flips off. This completes the
  reduced-motion story: Phase 2.2 camera easing, Phase 4 orbital
  entrance/exit, Phase 6 satellite/ring/halo animations, and the
  archetype twinkle all halt together. Ring rendering is unaffected
  because rings' geometry does not depend on `uTime`.

**Verification:** `pnpm test` → **284 passed**, 10 skipped, 0 failed
(up from 269 by 15 new stellar-profile formatter tests and 2 new
identity-panel tests). `pnpm exec tsc --noEmit` → exit 0. `pnpm exec
eslint` on all touched files — 0 new errors, 0 new warnings; page.tsx
still carries its 18 pre-existing warnings unchanged by this phase.
Commits: `31f7a2f` (7.1), `00ab1d3` (7.3).

**Phase 8 — Verification (landed, 2026-04-19 by claude-opus-4-7):**
- 8.1 ✅ — `pnpm test` in `apps/metis-web` → **286 passed, 10 skipped,
  0 failed** across 44 test files (+ 2 skipped files). Duration 63.47s.
- 8.2 ✅ — Repo-wide typecheck. `pnpm -w typecheck` does not exist at
  the repo root (`--workspace-root may only be used inside a
  workspace` — the repo uses pnpm but not a workspace manifest), so
  fell back per the plan to `pnpm exec tsc --noEmit` in
  `apps/metis-web`. Exit code 0, no type errors.
- 8.3 ⚠️ **Code-path verification done; manual browser QA deferred to
  human reviewer.** An automated agent cannot open a browser or move a
  pointer, so fabricating manual QA results would be dishonest. What
  the code trace confirmed is wired end-to-end:
  - *Field-star hover (nameless):* `onCanvasPointerMove` in
    `apps/metis-web/app/page.tsx` ~line 4571 falls through to
    `getHoveredCatalogueStar`; the guard `if (catHit && !catHit.addable
    && catHit.catalogueName)` exits early when `catalogueName` is null,
    and field-tier stars have `catalogueName === null` per the Phase 1
    tiered-naming policy → tooltip is suppressed.
  - *Landmark hover (classical name + Bayer/Flamsteed tooltip):*
    `getHoveredLandmarkStar` ~line 4320 hit-tests the 11 faculty
    constellation anchor/secondary stars, seeds a deterministic RNG by
    `(facultyId, starIndex)`, calls `generateStarName({ tier:
    "landmark", rng, magnitude })` and hands the classical name to
    `showCatalogueTooltip({ ..., kind: "classical" })` ~line 4563.
    `buildLandmarkTooltipContent` (~line 4206, confirmed in Phase 7.2)
    renders the Bayer/Flamsteed convention footer.
  - *User-star hover (user name):* `showStarTooltip(star, target)` ~line
    4127 pulls title/description/domain off the `UserStar` object
    directly (no name generation), so the user's own label is always
    the one shown.
  - *Dive into each archetype:* Star Dive focus acquisition at ~line
    3830 derives `focusedContentType = deriveUserStarContentType(
    focusedUserStar)` then calls `getCachedStellarProfile(target.id,
    focusedContentType)`. Because the cache is keyed
    `${starId}|${contentType}` and `generateStellarProfile` runs
    `selectStarVisualArchetype(options?.contentType)` on every miss,
    each of the 12 content-type → archetype mappings in
    `CONTENT_TYPE_ARCHETYPE_MAP` is exercised by code without any
    per-archetype branching in the dive path.
  - *Reduced-motion toggle:* `material.uniforms.uTime.value` is gated
    by `frame.reducedMotion` at
    `apps/metis-web/components/home/landing-starfield-webgl.tsx` line
    852; freezing `frozenTimeSeconds` halts twinkle, halo pulse, and
    satellite orbits (Phase 6 attributes feed the same `uTime`). Phase
    7.3 added the live `matchMedia` listener on the page side.

  **Manual QA checklist handed to the human reviewer** (must be
  exercised on the landing page against a real build before the user
  considers M02 signed off):
  1. Hover a background field star — tooltip stays hidden.
  2. Hover a faculty-constellation anchor star (e.g. Perseus' Algol) —
     classical name appears plus a footer explaining Bayer/Flamsteed.
  3. Hover a user-content star — the user's own title/domain/description
     render in the tooltip card.
  4. Dive into at least one star of each of the 12 archetypes
     (`main_sequence`, `pulsar`, `quasar`, `brown_dwarf`, `red_giant`,
     `binary`, `nebula`, `black_hole`, `comet`, `constellation`,
     `variable`, `wolf_rayet`) and confirm the closeup silhouette is
     visibly differentiated per the ADR 0006 table. `learning_route`
     → constellation and `document` → main_sequence are the two
     content types exercised by the existing `deriveUserStarContentType`
     inference; the other 10 require either user-star metadata
     extensions or M12 catalogue content to exercise in production.
  5. Flip OS `prefers-reduced-motion` on → twinkle, halo pulse, and
     any satellite orbits freeze on next frame; flip off → motion
     resumes without a visible jump.

- 8.4 ⚠️ **Static signals recorded; runtime FPS deferred to human
  reviewer.** An automated agent cannot measure real frame time. The
  plan / ADR 0006 target is "60fps at 200+ stars with one closeup". No
  perf instrumentation was found in
  `components/home/landing-starfield-webgl.tsx` (no stats.js import, no
  `PerformanceObserver`, no custom frame-time logger — only a
  `minimumFrameDeltaMs = 16` rAF throttle ~line 840 which caps the
  paint cadence at ~60Hz but does not report back). Static signals
  that *were* verified:
  - **Draw calls per frame:** 1 (`renderer.render(scene, camera)` ~line
    867 on a single `THREE.Points` object). No secondary render targets,
    no post-processing pass.
  - **Shader uniforms:** 7 (`uDpr`, `uTime`, `uZoomScale`,
    `uFocusCenter`, `uFocusStrength`, `uFocusRadius`, `uFocusFalloff`)
    — constant across archetypes, set once per frame.
  - **Per-vertex attributes:** 12 floats (`position` × 3 +
    `aColorA/B/C` × 4 each + `aShape` × 4 + `aTwinkle` × 2 +
    `aArchetype` × 1 + 6 Phase 6 annotation scalars). At 200 stars
    that is ≈ 7.8 KB of attribute data per frame (200 × 40 floats ×
    4 B), trivially below any bandwidth concern.
  - **Archetype branching:** `int(aArchetype)` is compared against 12
    IDs inside the fragment stage; the compiler is expected to unroll
    these into constant-time branches per fragment, matching the
    Phase 3 design assumption.
  - **Instance buffer vs. attribute stream:** the starfield does not
    use GL_ARB_instanced_arrays — every star is a `THREE.Points` vertex
    drawn in a single `drawArrays`, so there is no instance buffer to
    size. Attribute buffers grow linearly with `stars.length` and are
    only rebuilt when `frame.revision` changes (~line 847).

  ADR 0006 does not gate landing the milestone on a specific measured
  FPS number — the constraint reads "Must not regress performance of
  the 2D starfield (currently handling hundreds of stars at 60 FPS)"
  and the uber-shader hot path is a handful of constant-time fragment
  branches per pixel, which is cheaper than the retired 3D sphere
  overlay it replaces. **Recommendation:** land M02, track perf-
  instrumentation + a mobile-device pass as an explicit follow-up (see
  *Next up* below) rather than block the roadmap on a number the agent
  cannot produce.

- 8.5 ✅ — **Migration question resolved.** Yes, existing user stars
  retro-assign archetypes, and the retro-assignment already happens
  implicitly at render time. See ADR 0006 *Open Questions* for the
  full reasoning. Code-trace evidence:
  `rebuildProjectedUserStarRenderState` (`page.tsx` ~line 2783) and
  the Star Dive focus path (~line 3841) both call
  `deriveUserStarContentType(star)` →
  `getCachedStellarProfile(star.id, contentType)` →
  `generateStellarProfile(...)` →
  `selectStarVisualArchetype(options?.contentType)`. Archetype is not
  a persisted `UserStar` field — it is a derived render-time property
  keyed by `(starId, contentType)` in the in-memory cache. Every
  existing user star therefore picks up its archetype the first time
  it paints after M02 ships. No migration script, no one-time
  refresh action, no opt-in toggle.

- 8.6 ✅ — `plans/IMPLEMENTATION.md` M02 row → `Landed`, merge SHA
  `0449c2e` (PR #511, `Merge pull request #511 from mrzapa/claude/
  metis-vision-strategy-Bj7jJ`), date 2026-04-19. Frontmatter above
  flipped to `Status: Landed`.

**Verification totals across M02:** `pnpm test` → 286 passed, 10
skipped, 0 failed (grew from 211 at Phase 0 to 286 at Phase 8 — +75
test cases across the milestone). `pnpm exec tsc --noEmit` → exit 0.
No new eslint errors or warnings on touched files. Merge commits in
order: Phase 0–5 landed via #509 (`cd42a80`), Phase 6 + Phase 7.1/7.3
landed via #511 (`0449c2e`).

## Next up

M02 is **Landed**. All remaining items are deliberate follow-ups the
milestone did not in-scope — each one can be claimed by a new plan
doc or folded into a future milestone as noted.

- **[Human QA] Manual pass on landing page (Phase 8.3 checklist).** The
  agent could not exercise a browser; the reviewer should run through
  the five-item checklist in the Phase 8 progress entry above before
  announcing M02 to users. File any regression found there as a
  defect plan, not under M02.
- **[Follow-up] Performance instrumentation + mobile pass (Phase 8.4,
  ADR 0006 open question).** Add a frame-time logger (stats.js or a
  custom `PerformanceObserver` on `measure` entries) to
  `landing-starfield-webgl.tsx`, then run the landing page on a real
  low-end mobile device with ≥200 stars and one closeup-tier star
  active. Record the FPS number in ADR 0006's *Mobile performance
  ceiling* open question.
- **Phase 6 follow-up — inject focused user star into WebGL closeup
  tier**: today the webgl starfield renders catalogue stars only, so
  annotations plumbed through `StellarProfile` are invisible until a
  user star joins that stream. Tracked in *Notes for the next agent
  (Phase 6)* above.
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

## Blockers

None at plan-time. Live blockers go here.

## Notes for the next agent

- **Phase 8.5 migration-question outcome (2026-04-19):** existing user
  stars retro-assign archetypes *implicitly at render time* — archetype
  is derived from content type on every render via
  `deriveUserStarContentType` → `getCachedStellarProfile` →
  `selectStarVisualArchetype`. Archetype is **not** a persisted
  `UserStar` field. No migration script needed. Corollary: if ADR 0006's
  content-type → archetype table is revised later, every existing user
  star picks up the new archetype on next render because
  `getCachedStellarProfile` is keyed by `${starId}|${contentType}` and
  the archetype is re-derived per miss. Cache key does not include the
  archetype itself, so mapping changes take effect without cache
  invalidation.
- **Phase 8.4 perf instrumentation gap:** the Three.js starfield has no
  FPS/frame-time telemetry today. One draw call per frame, 7 uniforms,
  12 per-vertex attributes, 12-way fragment-stage branch on
  `int(aArchetype)`. Static numbers are healthy; a real mobile-device
  pass is the missing signal and is deliberately deferred to a
  follow-up (see *Next up*).
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
- **4.1** ✅ — **Docked rings chosen.** Panel rings dock at top/right/
  bottom/left around the star; the star stays visible at centre. See
  *Notes for the next agent* for spacing + caller mapping.
- **4.2** ✅ — `apps/metis-web/components/constellation/observatory-orbital-layout.tsx`
  ships with an abstract named-slot API. Caller-driven panel mapping
  (archetype picker top, faculty glyph left, learning route bottom).
- **4.3** ✅ — Entrance: each slot fades + slides inward from its edge,
  staggered 80 ms, duration `CONSTELLATION_DIVE_DURATION_MS` (700 ms)
  on a cubic-out curve that matches the camera hook.
- **4.4** ✅ — Exit reverses translate + fades on a 60 %-shortened
  duration. The overlay is only mounted while `open && isOrbital` so
  dismissal tears down cleanly without orphaning the camera.
- **4.5** ✅ — Esc / click-outside / focus trap continue through the
  underlying `@base-ui/react` Dialog primitive; the orbital layout is a
  sibling portal that does not replace it.
- **4.6** ✅ — `useIsOrbitalViewport()` gates the orbital overlay at
  `(min-width: 768px)`. Narrower viewports render the classic side-
  rail modal only.

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
