# 0006 - Constellation Design: 2D Primary, Knowledge-First Dive

- **Status:** Accepted (M02 landed 2026-04-19)
- **Date:** 2026-04-18

## Context

The landing page currently renders stars in two completely separate systems:

1. A **2D WebGL shader** for the zoomed-out starfield. Hundreds of stars as
   layered point primitives — core, halo, accent, diffraction spikes,
   twinkle. Lives in `apps/metis-web/components/home/landing-starfield-
   webgl.tsx` with shader/LOD code in `apps/metis-web/lib/landing-stars/`.
2. A **3D procedural fragment shader** for the "dive" into a star. A
   hand-written GLSL simulation of a stellar surface: granulation,
   prominences, sunspots, faculae, chromosphere, corona. Lives in
   `apps/metis-web/components/home/star-dive-overlay.tsx` with shader code
   in `apps/metis-web/lib/landing-stars/star-surface-shader.ts`.

The two systems share no renderer, no coordinate system, and no colour
pipeline. The transition is a hard swap — the 2D point fades to zero and
the 3D canvas fades in — not an LOD crossfade.

This produces three user-visible problems:

- **Felt disconnection.** The 2D star and the 3D model look like different
  objects. The architecture makes this unfixable without a renderer merge.
- **"Monstrous" 3D models.** `u_stage` is hardcoded to max detail, so
  sunspots, prominences, and faculae render at all zoom levels. Palettes
  tuned for glowing 2D points look sickly wrapped around a sphere. Real
  stars at web resolution appear as points even through telescopes — a
  realistic 3D stellar surface feels out of scale and cartoonish by nature.
- **Cryptic naming.** Background decorative stars receive real astronomical
  catalogue names (Bayer / Flamsteed / Henry Draper) applied indiscriminately.
  Users see "HD 359083" under otherwise meaningless background stars and
  read them as code.

A secondary concern: the procedural `StellarProfile` system — stellar types,
spectral classes, palettes, visual profiles — was built to give each star a
unique character so different star *types* could map to different content
*types* (a deliberate design intent: "this kind of star is good for storing
this kind of content"). That intent is worth preserving even as the 3D
sphere is retired.

## Decision

The constellation goes **2D-only, knowledge-first**.

When a user dives into a star:

- Camera performs a cinematic 2D zoom and pan toward the selected star.
- Ambient stars dim and blur with depth-of-field falloff.
- The selected star grows and intensifies using the existing 2D shader
  family (enhanced bloom, archetype-specific effects, animated corona
  swirls, increased diffraction, pulsation).
- The **Star Observatory panel animates in around the star** — docked,
  orbital, or radial layout (see Open Questions). Existing panels
  (`star-archetype-picker`, `faculty-glyph-panel`, `learning-route-panel`)
  reposition into the new composition.
- The "dive" is into *meaning* — the document, the companion's notes, the
  trace, the linked sources — not into simulated stellar physics.

The procedural-differentiation design intent is preserved by redistributing
it across three surfaces instead of three renderers:

1. **Silhouette (2D archetype).** Each content type maps to a dramatically
   distinct 2D star archetype, all rendered in the existing shader family:

   | Content type | Archetype | Visual signature |
   |---|---|---|
   | Document / paper | Main sequence | Layered star, diffraction spikes, steady |
   | Podcast / audio | Pulsar | Tight core, sharp rays, fast pulsation |
   | Video | Quasar | Radiating jets, high luminosity |
   | Note / thought | Brown dwarf | Dim, rust-coloured, small halo |
   | Summary | Red giant | Large warm bloom, slow pulse |
   | Evidence pack | Binary system | Two linked stars (claim + citations) |
   | Topic cluster | Nebula | Diffuse cloud, no sharp core |
   | Archive / cold | Black hole | Dark core, luminous accretion ring |
   | Live feed (news) | Comet | Moving, trailing tail |
   | Learning route | Named constellation | Multi-star pattern with links |
   | Session | Variable star | Oscillating brightness |
   | Skill / technique | Wolf-Rayet | Rare, energetic, distinct spectrum |

   Archetype mapping is tunable and a deliberate design exercise. Selected
   mappings above are proposed, not final.

2. **Annotations.** Optional 2D accoutrements encode additional metadata
   without requiring 3D geometry: rings (document series), orbiting
   satellites (sub-nodes), dust trails (evolution over time), binary
   companions (relationships), comet tails (activity), halos (recency).

3. **Observatory as character sheet.** Spectral class, stellar type,
   temperature, luminosity, palette, archetype — surface in the Star
   Observatory as the star's *identity*. The procedural richness is
   experienced informationally when the user is engaging with the content,
   not as fake physics when they are just browsing.

**Naming becomes tiered.** The current undifferentiated Bayer/Flamsteed/HD
policy is replaced:

- **Background field stars:** no visible name. Atmosphere only. Hovering
  shows nothing.
- **Faculty constellation stars (the 8 canonical landmarks — Perseus,
  Auriga, Draco, Hercules, Gemini, Big Dipper, Lyra, Boötes):** keep
  classical names (Alpha Cygni, Omega Draconis) with a tooltip explaining
  Bayer/Flamsteed convention. These are the cosmos's named mountains —
  worth keeping for flavour and landmark navigation.
- **User-content stars:** the user's own name. Document title, session
  subject, topic label, or archetype. Bold, legible, the primary way the
  user recognises their own content.

## Because

- The 2D/3D architectural disconnect cannot be fixed without merging
  renderers; deletion is cheaper than merge.
- 3D stellar surfaces at web resolution look wrong by physical analogy —
  real stars appear as points, and a realistic sphere reads as a toy sun.
- The 2D layered shader family is already beautiful and well-invested.
  Extending it to cover archetypes is an additive change, not a pivot.
- "Stars are knowledge, not astronomy" is the right metaphor for METIS.
  Diving into a star should reveal the content and the companion's
  engagement with it — not simulate plasma.
- The `StellarProfile` procedural system is valuable metadata. Retiring
  the 3D sphere does not retire the profile system; the data feeds both
  2D archetype selection and Observatory character-sheet content.
- The Star Observatory is already well-built and the natural dive
  destination. It deserves to be the thing that appears — not a detour
  panel after a detour sphere.
- Tiered naming resolves the code-name problem without losing the
  classical-astronomy flavour on constellation landmarks.

## Constraints

- Must preserve `StellarProfile` generation, palette system, and the 2D
  rendering infrastructure.
- Must preserve the Star Observatory dialog and its existing
  archetype/faculty/learning-route features.
- Must work on mobile. Single WebGL context preferred.
- Must not regress performance of the 2D starfield (currently handling
  hundreds of stars at 60 FPS).
- Any archetype-specific effects (accretion ring, jets, pulsation,
  comet tail) must fit within the existing shader family or a small,
  bounded extension to it.
- Must coexist with ADR 0004 (one interface: Next.js + Tauri + Litestar).

## Alternatives Considered

- **Option 1: Go full 2D flat (no archetypes).** Rejected. Loses the
  differentiation-by-content-type design intent. The procedural system
  becomes genuinely wasted.
- **Option 2: Go full 3D from the start.** Rejected. Bigger refactor,
  still fights the out-of-scale sphere problem, hit detection becomes
  3D raycast, mobile performance cost.
- **Keep the 2D/3D split, polish the 3D sphere.** Rejected. The
  disconnect is architectural (two renderers, two contexts); polishing
  the sphere does not merge the renderers and does not address the
  "realistic sphere looks wrong" problem.
- **True 2.5D (shared canvas, LOD crossfade).** Rejected. Would
  require unifying two WebGL contexts that were never designed to share.
  High refactor cost. A previous 2.5D attempt was reported to feel
  "weird."

## Consequences

**Accepted:**

- `apps/metis-web/components/home/star-dive-overlay.tsx` is retired.
- `apps/metis-web/lib/landing-stars/star-surface-shader.ts` is retired.
- The 2D shader family gains a **closeup tier** that encodes
  archetype-specific effects — accretion rings, pulsation, jets, corona
  swirls, dust trails, binary separation, comet tails.
- The camera system gains smooth 2D zoom/pan easing for the dive.
- The Star Observatory dialog is reworked from modal to **docked/orbital
  entrance** — it animates in around the selected star rather than
  appearing over it.
- `StellarProfile` gains an `archetype` enum field (or equivalent) that
  maps content-type → visual template.
- `star-name-generator.ts` gains a tiered policy: field stars unnamed,
  constellation landmarks keep classical names with tooltip, user-content
  stars use user-provided names.
- `StarDiveOverlay`'s CSS, animation, and positioning code are removed.
  Existing focus-strength driven animations are re-homed on the 2D
  camera and shader.
- The `faculty-glyph-panel` and `learning-route-panel` reposition as part
  of the orbital Observatory layout.

**Preserved:**

- `StellarProfile`, `stellar-profile.ts`, palette system, visual profiles
  — all survive and drive richer 2D rendering plus Observatory content.
- All of `lib/landing-stars/` except `star-surface-shader.ts`.
- `landing-star-lod.ts` gains an archetype-aware closeup tier.
- The constellation home (8 faculty constellations) and their classical
  naming survive.
- Star Observatory's existing controls and data model.

## Open Questions

- **Exact archetype → content-type mapping.** The table above is
  proposed, not final. Needs playtest and founder taste. Some mappings
  are strong (comet for live feed, nebula for cluster); others are
  debatable (Wolf-Rayet for skill, pulsar for podcast).
- **Orbital panel layout for the Observatory.** Radial cards? Docked
  rings? Magazine-style spread? Needs design iteration before
  implementation. May warrant its own ADR.
- **Camera animation easing and duration.** Current 0.55s ease applies
  to the 3D overlay fade; the new 2D zoom needs its own curve.
- **Shader architecture for archetypes.** Whether one uber-shader with
  archetype branches is simpler than multiple specialised programs.
  Bounded by the constraint that the existing shader family stays
  extensible.
- **Mobile performance ceiling.** How many distinct archetypes can
  render simultaneously on low-end mobile GPUs.
- **Migration of existing user content.** Do existing user stars get
  retroactively assigned archetypes based on content type, or is the
  new archetype system opt-in for new content only?
  - **Resolved 2026-04-19 (M02 Phase 8.5):** *Yes, retro-assigned — and
    it already happens implicitly.* Archetypes are not persisted on
    `UserStar`; they are derived at render time. Both user-star call
    sites in `apps/metis-web/app/page.tsx`
    (`rebuildProjectedUserStarRenderState` ~line 2783 and the Star Dive
    focus acquisition path ~line 3841) call
    `deriveUserStarContentType(star)` →
    `getCachedStellarProfile(star.id, contentType)` →
    `generateStellarProfile(...)` →
    `selectStarVisualArchetype(options?.contentType)`. Every existing
    user star therefore picks up its archetype the first time it
    renders after the M02 code ships — no DB migration, no one-time
    refresh action, no opt-in toggle required. If the ADR 0006 content-
    type → archetype table is revised post-launch, existing stars will
    automatically reflect the new mapping on next render because the
    cache is keyed by `${starId}|${contentType}` (not by archetype).
- **Accessibility.** Animated pulsation, variable brightness, rotating
  corona — need a reduced-motion fallback (already partly implemented
  in the current 3D overlay; must carry across).

## Addendum — 2026-05-01 (M21 Phase 5)

The original ADR mandated three things that user critique on 2026-05-01
asked us to revisit, and two of them are amended here. Recording the
delta so future readers see what the ADR currently *enforces* rather
than what it originally proposed.

**Amended:**

1. **Faculty constellation labels are no longer painted on the
   canvas.** The original ADR didn't explicitly require visible text
   labels under each anchor — that was an implementation choice in
   `apps/metis-web/app/page.tsx`. The user reported the rendered
   "Memory" / "Perception" / "Knowledge" titles read as confusing
   "function" declarations and wanted them gone. The text-paint at
   `drawNodes` (`fillText(n.concept.title, …)`) is removed. The hit-zone
   bookkeeping (`syncNodeLabelLayout`) still runs because semantic-search
   and drag-to-reassign depend on it. Reinstate by un-commenting the
   `fillText` line if a future iteration decides labels should return.
2. **The hover surface for `classical`-tier names is gone.** The ADR's
   *tiered naming* policy is preserved at the **data layer** —
   `generateStarName({ tier: "landmark" })` still produces deterministic
   Bayer/Flamsteed designations, the catalogue inspector and Star
   Observatory still surface them on click. What was removed is the
   *hover tooltip* that put a generated classical name plus the footer
   `Classical star name (Bayer/Flamsteed convention)` under the cursor on
   every landmark / catalogue mouse-over. The combination read as
   AI slop. Click-to-inspect is now the only path to a name; hover is
   silent for every tier (matching the field-tier behaviour the ADR
   already mandated). The `<div ref={catalogueTooltipRef} …>` element
   stays in the JSX as a no-op surface in case a different hover
   mechanism is reintroduced later, but `showCatalogueTooltip` and
   `getHoveredLandmarkStar` were deleted.

**Also touched (separately, but in the same change set):**

3. **The rotating orbit ring + 8-point diffraction spike pattern +
   orbiting motes around the central METIS star (the
   "drawPolarisMetis" composition in `app/page.tsx`) were removed.**
   Not directly mandated by this ADR — the lens-flare-y motion was an
   M02 implementation choice — but listed here because it changes the
   reader's mental picture of "what the constellation home actually
   looks like in 2026-05-01+". M10's H₁ topology data used to amplify
   the orbit-ring alpha and spike length; that signal currently has no
   visual surface and will need a new one if it ever becomes
   load-bearing.

**Why the contract weakens here:** the original ADR over-specified the
*surfacing* of tiered names (mandating tooltips with explanatory
footers) when the load-bearing decision was the *naming policy itself*
(tiered, deterministic, classical-only on landmarks). The amendment
keeps the policy and lets the surface evolve.

**Reinstating any of (1), (2), (3):** every removed primitive is
recoverable from git history at the commits that landed M21 Phase 5 —
no information was destroyed.

## Addendum — 2026-05-03 (M24 / ADR 0019)

The **faculty-anchor placement decision** in this ADR is superseded by
[ADR 0019 — Constellation IA: content-first, drawable Projects](0019-constellation-ia-content-first-projects.md).
Specifically:

- **Faculty as a placement principle is removed.** Stars are no longer
  positioned around the 8 (or 11, depending on which file) named-faculty
  anchors. Placement is by content-embedding clusters with Project-pull
  override.
- **Faculty as a curriculum signal is removed end-to-end in M26.** The
  M04 reverse-curriculum logic is preserved, but the signal it operates
  on changes from faculty-gap-scoring to cluster-gap-scoring after M16
  evals validate parity.
- **The 8 faculty constellation landmarks (Perseus, Auriga, Draco,
  Hercules, Gemini, Big Dipper, Lyra, Boötes) are slated for retirement
  in M24 Phase 6 cleanup**, including their classical-naming surface in
  `star-name-generator.ts`.

**Preserved from this ADR (not superseded):**

- The `StellarProfile` archetype system (content-type → 2D archetype
  mapping). This survives and continues to drive star rendering.
- The tiered-naming policy: field stars unnamed, user-content stars by
  user name. Landmarks-classical-on-click changes shape — there are no
  more named landmark constellations after M24 Phase 6 — but the *user-
  content naming* portion of the tier continues unchanged.
- The Star Observatory dialog architecture (orbital panels around the
  selected star). The faculty-glyph-panel inside it goes away; archetype
  picker and learning-route panel survive.
- The 2D-only "knowledge-first dive" framing. M24+ does not reintroduce
  the 3D sphere.

**Why the contract weakens here:** the original ADR built the placement
principle, the curriculum signal, and the visual landmark system on the
same faculty taxonomy — and that taxonomy turned out to drift between
files (8-faculty in this ADR vs. 11-faculty in
`autonomous_research_service.py`) and to lack user-visible value. ADR
0019 separates the three concerns: placement (now content-cluster),
curriculum (still gap-scoring, just on cluster IDs after M26), and
visual landmarks (retired). The archetype system and naming-tier policy
were never tied to faculty and survive intact.

**Reinstating faculty-anchor placement:** every removed primitive is
recoverable from git history at the commits that landed M24+. Faculty
IDs persist in the data layer through M25 as invisible internals; M26
removes them. Reverting is possible up to the M26 cutover, expensive
after.
