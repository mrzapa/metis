# Star Dive Sphere — Design Document

**Date:** 2026-04-04

## Goal

Replace the fullscreen `StarCloseupWebgl` overlay with a proper 3D sphere rendered directly inside the existing `LandingStarfieldWebgl` Three.js scene. The sphere uses the high-quality shader already proven in the add-star observatory dialog (Worley granulation, plasma turbulence, sunspot penumbrae, chromosphere, coronal streamers). Scroll direction is fixed so scrolling UP zooms IN.

## Problems Being Solved

1. **Potato shape** — fullscreen overlay rendered a 2D disk that appeared oval on landscape screens (partially fixed by aspect ratio PR, but the fundamental design was wrong)
2. **Wrong zoom direction** — `Math.exp(deltaY * 0.0014)` meant scroll-down = zoom in; users expect scroll-up = zoom in
3. **Low-quality shader** — `star-closeup-webgl.tsx` used 2-octave fBm simplex noise for granulation; the observatory dialog has multi-scale Worley cells, domain-warped plasma, spicules, and coronal loops
4. **Visual incoherence** — the zoom-in close-up looked nothing like the star preview shown in the add-star pane
5. **Extra DOM layer** — a fixed fullscreen transparent canvas sitting above everything even when invisible

## Architecture

### Removed
- `apps/metis-web/components/home/star-closeup-webgl.tsx` — deleted entirely
- `<StarCloseupWebgl>` from `page.tsx`
- `metis-star-closeup-webgl` CSS class

### Added
- `apps/metis-web/lib/landing-stars/star-surface-shader.ts` — shared GLSL shader source extracted from `star-observatory-dialog.tsx`, consumed by both the dialog renderer and the new sphere mesh
- Sphere mesh (two `THREE.SphereGeometry` objects) inside `LandingStarfieldWebgl`'s existing Three.js scene

### Modified
- `apps/metis-web/components/home/landing-starfield-webgl.types.ts` — add `sphere` field to `LandingStarfieldFrame`
- `apps/metis-web/components/home/landing-starfield-webgl.tsx` — add sphere mesh setup + per-frame update
- `apps/metis-web/app/page.tsx` — populate `frame.sphere`, fix scroll direction, remove `StarCloseupWebgl`

## Data Flow

```
page.tsx animation loop
  → reads starDiveFocusWorldPosRef, starDiveFocusStrengthRef, starDiveFocusProfileRef
  → projects world position to screen coords
  → writes frame.sphere = { x, y, radius, focusStrength, profile }

LandingStarfieldWebgl render loop (already runs every frame)
  → reads frameRef.current.sphere
  → updates sphere mesh position, scale, uniforms
  → renders: corona sphere (BackSide) → star surface sphere → points
```

No new React state, no new animation loop, no extra DOM elements.

## LandingStarfieldFrame Extension

```ts
export interface StarDiveSphereFrame {
  x: number;            // star screen-space X (pixels, matches camera space)
  y: number;            // star screen-space Y
  radius: number;       // sphere radius in pixels (grows with zoom)
  focusStrength: number; // 0→1 for fade-in/out
  profile: StellarProfile;
}

// Added to LandingStarfieldFrame:
sphere: StarDiveSphereFrame | null;
```

## Sphere Sizing

```ts
const radius = focusStrength * 0.30 * frame.height;
// At full focus (strength=1): 30% of viewport height = 324px on 1080p
// Corona sphere scale: radius * 1.6
```

## Sphere Meshes

### Star surface sphere
- `SphereGeometry(1, 64, 32)` — 64 horizontal, 32 vertical segments; smooth enough for close-up
- `ShaderMaterial` with ported observatory shader
- `depthTest: false`, `transparent: false`
- Scale = `radius`, position = `(x, y, 0.5)` (slightly in front of star points at z=0)

### Corona sphere
- `SphereGeometry(1, 32, 16)`
- `ShaderMaterial` — simple rim glow: `pow(1.0 - max(0.0, dot(vNormal, vViewDir)), 3.0) * uCoronaIntensity`
- `side: THREE.BackSide`, `transparent: true`, `blending: THREE.AdditiveBlending`, `depthTest: false`
- Scale = `radius * 1.6`

## Shader Strategy

**Source:** `STAR_FRAG` in `star-observatory-dialog.tsx` is the canonical shader.

**Extract to:** `lib/landing-stars/star-surface-shader.ts` exports:
```ts
export const STAR_SURFACE_FRAG_GLSL: string;  // Three.js compatible (no #version header, varying, gl_FragColor)
export const STAR_SURFACE_VERT_GLSL: string;  // passes vNormal, vViewDir, vSphereUv
```

**Observatory dialog** updated to import and use `STAR_SURFACE_FRAG_GLSL` (wrapped in `#version 300 es` adapter) — same visual result, single source.

**Adaptations for Three.js sphere mesh:**
- Remove `#version 300 es` header (Three.js handles it)
- Replace `in/out` with `varying`
- Replace `fragColor` with `gl_FragColor`
- Replace `v_uv` + disk projection with mesh normals: vertex shader passes `vNormal = normalize(normalMatrix * normal)` and `vViewDir = normalize(-mvPosition.xyz)`
- `vSphereUv` computed from `position.xyz` (unit sphere): `vec2(rx, rz) * 2.0 + starOff` (same rotation logic as dialog)
- `u_res` becomes `uResolution` (vec2 of pixel size)

**Uniforms (per StellarProfile):**
```glsl
uniform float uTime;
uniform float uSeed;          // profile.seedHash % 1000 / 1000
uniform float uFocusStrength; // 0→1 fade
uniform float uStage;         // always 2.0 (show full detail)
uniform vec3  uColor;         // profile.palette.core (RGB 0-255)
uniform vec3  uColor2;        // profile.palette.halo
uniform vec3  uColor3;        // profile.palette.accent
uniform float uHasColor2;     // 1.0
uniform float uHasColor3;     // 1.0
uniform float uHasDiffraction; // 1.0 for hero/closeup stars
uniform vec2  uResolution;
```

## Scroll Direction Fix

`page.tsx` ~line 4040:
```ts
// Before
const zoomMultiplier = Math.exp(e.deltaY * 0.0014);
// After — scroll UP (negative deltaY) = zoom IN
const zoomMultiplier = Math.exp(-e.deltaY * 0.0014);
```

## Performance Notes

- Two sphere meshes are always in the scene but scaled to 0 when `focusStrength === 0` — no fragment shader invocations for invisible pixels
- `SphereGeometry(64, 32)` = ~4000 triangles, trivial for a GPU
- The observatory shader uses `u_stage >= 1.0` / `>= 2.0` guards for sunspots/faculae — these always run at `uStage = 2.0` for max quality; cost is bounded by sphere pixel count (much less than a fullscreen pass)
- No new animation loop — reuses the existing 60fps starfield RAF
