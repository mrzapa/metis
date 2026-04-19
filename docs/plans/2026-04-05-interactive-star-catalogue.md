# Interactive Star Catalogue — Implementation Plan

> **⚠️ SUPERSEDED — 2026-04-19.** This doc predates the M02 Constellation
> 2D refactor (landed 2026-04-15, PR #511/#512). M02 already shipped the
> WebGL2 instanced star rendering path via `LandingStarfieldWebgl` with
> LOD tiers, DOF, Star Dive integration, and interaction targets —
> features the Phase 2 renderer described here did not plan for. The
> `ConstellationFieldStar` removal, painted galaxy overlay cleanup, and
> `StarCatalogue` wiring have also already landed.
>
> **What's still real about M12:** the *interactive* layer — click-to-inspect
> catalogue stars, search by name, filter by spectral class / magnitude,
> promote-to-user-constellation flow. That scope needs a fresh plan
> grounded in the post-M02 reality. See the M12 row in
> [`plans/IMPLEMENTATION.md`](../../plans/IMPLEMENTATION.md) (status:
> `Draft needed`).
>
> Kept on disk for reference per `plans/README.md` ("Superseded plans
> stay on disk with Status: Superseded and a pointer to what replaced
> them"). Do not implement against this document.

---

**Project:** Metis (`mrzapa/metis`) · `apps/metis-web`  
**Date:** 2026-04-05  
**Status:** Superseded (2026-04-19) — renderer path landed via M02; interactive layer needs new plan
**Audience:** Developer (mrzapa) + coding agents (Claude Code / similar)

---

## 1. Executive Summary

The goal is to replace the decorative `ConstellationFieldStar` background-dot system with a **Procedural Star Catalogue** — a deterministic, lazily-generated database of thousands of real stars, each with a unique identity, spectral class, name, world-space position, and full interactivity. The result is a unified star universe where:

- Every visible dot is a genuine star with a seeded `StellarProfile`
- Any star can be clicked, inspected, and added to the user's constellation
- User constellation stars are _the same kind of object_ as catalogue stars — just with additional metadata (label, faculty, connections)
- The galaxy view at extreme zoom-out is composed of these actual stars, not a painted overlay
- All stars share the same parallax behaviour and rendering pipeline
- The existing `star-surface-shader.ts` WebGL2 shader surface can be dived into from _any_ star

**Performance target:** 10,000 rendered stars at ≥60 fps on mid-range hardware (2020-era laptop GPU).

---

## 2. Current State Analysis

### 2.1 What exists and works well

| Component | Location | Status |
|---|---|---|
| `generateStellarProfile(seed)` | `lib/landing-stars/stellar-profile.ts` | ✅ Complete — spectral class, mass, radius, palette, visual profile |
| WebGL2 star surface shader | `lib/landing-stars/star-surface-shader.ts` | ✅ Complete — Worley granulation, plasma, sunspots, corona, diffraction |
| LOD tier system | `lib/landing-stars/landing-star-lod.ts` | ✅ Complete — point/sprite/hero/closeup thresholds |
| Spatial hash | `lib/landing-stars/landing-star-spatial-index.ts` | ✅ Complete — `buildLandingStarSpatialHash`, `findClosestLandingStarHitTarget` |
| Interaction helpers | `lib/landing-stars/landing-star-interaction.ts` | ✅ Complete — hit radius, selectable size per LOD |
| Star dive zoom overlay | `app/page.tsx` (`StarDiveOverlay`) | ✅ Complete — triggered at zoom ≥ 200, full shader surface |
| Camera / zoom / pan | `lib/constellation-home.ts` | ✅ Complete — `getBackgroundCameraScale`, parallax, projection |
| Faculty / user star data model | `lib/constellation-types.ts` | ✅ Complete — `UserStar` interface |

### 2.2 What is broken / missing

| Problem | Root cause |
|---|---|
| Background stars are non-interactive | `ConstellationFieldStar` has no `StellarProfile`, no name, no click handler |
| Two-tier rendering feels disconnected | User stars and background stars use separate draw paths |
| Background stars have no parallax | `parallaxFactor` field exists but galaxy layer parallax is identity |
| Galaxy overlay is a painted blur | `drawGalaxyBackground()` uses radial gradients and fBm noise — not real stars |
| Canvas 2D perf cap at ~500 stars | `ctx.arc()` per star is CPU-bound; WebGL instancing handles 100,000+ |
| Star dive only works on `UserStar` | `StarDiveOverlay` reads `UserStar.stellarProfile` — no catalogue equivalent |

---

## 3. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  Browser Frame (requestAnimationFrame)                              │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  WebGL2 Canvas (bottom layer)                                │  │
│  │                                                              │  │
│  │  StarCatalogueRenderer (instanced GL_POINTS)                 │  │
│  │  ├── VAO: position(xy) + color(rgb) + size(f) + brightness   │  │
│  │  ├── One drawArraysInstanced() per frame                     │  │
│  │  ├── Vertex shader: world→screen, LOD point size             │  │
│  │  └── Fragment shader: soft disc + twinkle + diffraction      │  │
│  │                                                              │  │
│  │  StarDiveOverlay (existing WebGL2 shader, unchanged)         │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  2D Canvas (top layer, transparent background)               │  │
│  │                                                              │  │
│  │  ├── Galaxy core glow (radial gradient bloom — kept)         │  │
│  │  ├── Constellation edges (line between UserStars)            │  │
│  │  ├── UserStar label overlays (name, faculty colour ring)     │  │
│  │  ├── Hover tooltip (star name + spectral class)              │  │
│  │  └── Selection ring / click ripple                           │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  React UI Layer                                              │  │
│  │  ├── StarDetailPane (inspect catalogue star or user star)    │  │
│  │  ├── ConstellationPanel (existing)                           │  │
│  │  └── ZoomControls / minimap (existing)                       │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Data Layer (no rendering)                                   │  │
│  │                                                              │  │
│  │  StarCatalogue                                               │  │
│  │  ├── generateSector(sx, sy) → CatalogueStar[]               │  │
│  │  ├── getVisibleStars(viewport) → CatalogueStar[]            │  │
│  │  └── cache: Map<sectorKey, CatalogueStar[]>                  │  │
│  │                                                              │  │
│  │  SpatialIndex<CatalogueStar>  (existing hash, generalised)   │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### Layer stacking

```
z-index  canvas/element            purpose
────────────────────────────────────────────────────────
  1      WebGL canvas              instanced star field + star dive
  2      2D overlay canvas         labels, edges, tooltips, glow
  3      React portals             detail pane, panels, HUD
```

Both canvases are `position: absolute; top: 0; left: 0; width: 100%; height: 100%`. The 2D canvas has `pointer-events: none` so mouse events pass through to the WebGL canvas hit-test layer.

---

## 4. Data Model Specifications

### 4.1 `CatalogueStar`

```typescript
// lib/star-catalogue/types.ts

import type { StellarProfile } from '../landing-stars/types';

/** A deterministically generated star from the galaxy catalogue. */
export interface CatalogueStar {
  /** Stable unique ID: `${galaxySeed}-${sectorKey}-${indexInSector}` */
  id: string;

  /**
   * World-space position in normalised galaxy coordinates [-1, 1].
   * x=0, y=0 is galactic centre.
   */
  wx: number;
  wy: number;

  /** Full procedural profile (spectral class, temperature, palette, etc.) */
  profile: StellarProfile;

  /** Human-readable name generated from seed */
  name: string;

  /**
   * Visual apparent magnitude [0–6]. Derived from profile.luminosity and
   * a distance factor baked in at generation time.
   * Lower = brighter. Used for LOD and rendering brightness.
   */
  apparentMagnitude: number;

  /**
   * Parallax depth layer [0–1]. Stars near 0 are in the far background
   * (slow parallax), near 1 are in the foreground (fast parallax).
   * Deterministically derived from seed.
   */
  depthLayer: number;
}

/** A CatalogueStar that has been promoted to the user's constellation. */
export interface UserStar extends CatalogueStar {
  label: string;
  primaryDomainId: string | null;
  relatedDomainIds: string[];
  stage: 'seed' | 'sprout' | 'bloom' | 'nova';
  notes: string;
  connectedUserStarIds: string[];
  learningRoute: string | null;
}

/** Sector coordinates in galaxy space. */
export interface SectorKey {
  sx: number; // integer
  sy: number; // integer
}

/** All CatalogueStars for one sector (deterministic). */
export interface CatalogueSector {
  key: SectorKey;
  stars: CatalogueStar[];
}
```

### 4.2 `StarCatalogue`

```typescript
// lib/star-catalogue/star-catalogue.ts

export interface StarCatalogueConfig {
  /**
   * Master galaxy seed string. All star positions/profiles derive from this.
   * Changing it produces an entirely different galaxy.
   */
  galaxySeed: string;

  /**
   * Stars per sector. Higher = denser galaxy, more memory.
   * Recommended: 200–500 for 5,000–10,000 visible at typical zoom.
   */
  starsPerSector: number;

  /**
   * Size of each sector in world units. Sectors partition the [-1,1] galaxy
   * space. sectorSize = 0.1 gives 400 sectors total (20×20).
   */
  sectorSize: number;

  /** Number of spiral arms (2 or 4 look best). */
  numArms: number;

  /** Tightness of arm wind (radians per unit distance from centre). */
  armWindingRate: number;
}
```

### 4.3 GPU instance buffer layout

Each visible star is one row in a tightly packed `Float32Array`. Layout (8 floats = 32 bytes per star):

```
offset 0:  screen_x        (float32) — projected screen position x
offset 1:  screen_y        (float32) — projected screen position y
offset 2:  point_size      (float32) — GL_POINTS point size in pixels
offset 4:  color_r         (float32) — 0..1 linear
offset 5:  color_g         (float32)
offset 6:  color_b         (float32)
offset 7:  brightness      (float32) — 0..1, controls alpha/intensity
```

One `Float32Array` of `maxVisibleStars * 8` floats, updated each frame via `gl.bufferSubData`.

---

## 5. Phase Breakdown

---

### Phase 1: Procedural Star Catalogue Data Layer

**Goal:** Create the deterministic star generation system. No rendering changes yet.  
**Estimated effort:** ~4 hours  
**Dependencies:** None

---

#### Task 1.1 — Create `lib/star-catalogue/` directory and type definitions

**Files to create:**
- `apps/metis-web/lib/star-catalogue/types.ts`
- `apps/metis-web/lib/star-catalogue/index.ts` (barrel export)

**Action:** Create the `CatalogueStar`, `UserStar`, `SectorKey`, `CatalogueSector`, and `StarCatalogueConfig` interfaces as specified in §4.1 and §4.2 above. The `UserStar` interface in this file _replaces_ the one in `lib/constellation-types.ts` (migration in Phase 5).

**Verification:** `tsc --noEmit` passes.

---

#### Task 1.2 — Implement seeded RNG helpers

**File to modify:** `apps/metis-web/lib/star-catalogue/rng.ts` (new file)

The existing `hashSeed` in `stellar-profile.ts` uses FNV-1a. Extract it into a shared utility and add a `SeededRNG` class:

```typescript
// apps/metis-web/lib/star-catalogue/rng.ts

/**
 * FNV-1a 32-bit hash. Deterministic, fast, good distribution.
 * Already used in stellar-profile.ts — centralise it here.
 */
export function fnv1a32(str: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0; // unsigned 32-bit
}

/**
 * Mulberry32 — fast, high-quality 32-bit PRNG.
 * Initialised from a seed integer (e.g. FNV-1a hash of a string).
 */
export class SeededRNG {
  private s: number;

  constructor(seed: number) {
    this.s = seed >>> 0;
  }

  /** Returns float in [0, 1) */
  next(): number {
    this.s |= 0;
    this.s = (this.s + 0x6d2b79f5) | 0;
    let t = Math.imul(this.s ^ (this.s >>> 15), 1 | this.s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  /** Returns float in [min, max) */
  range(min: number, max: number): number {
    return min + this.next() * (max - min);
  }

  /** Returns integer in [0, n) */
  int(n: number): number {
    return Math.floor(this.next() * n);
  }

  /** Picks a random element from an array */
  pick<T>(arr: T[]): T {
    return arr[this.int(arr.length)];
  }
}
```

**Verification:** Write a quick test: `new SeededRNG(fnv1a32('test')).next()` should return the same float on every call with the same seed. A simple `console.assert` in a `__tests__/rng.test.ts` suffices.

---

#### Task 1.3 — Implement star name generator

**File to create:** `apps/metis-web/lib/star-catalogue/star-name-generator.ts`

Generate Bayer-style names (Greek letter + constellation genitive) for brighter stars and catalogue-style designations (HD/HIP number) for dimmer ones:

```typescript
import { SeededRNG } from './rng';

const GREEK = [
  'Alpha','Beta','Gamma','Delta','Epsilon','Zeta','Eta','Theta',
  'Iota','Kappa','Lambda','Mu','Nu','Xi','Omicron','Pi','Rho',
  'Sigma','Tau','Upsilon','Phi','Chi','Psi','Omega',
];

const CONSTELLATIONS_GENITIVE = [
  'Orionis','Cygni','Leonis','Tauri','Scorpii','Aquilae','Herculis',
  'Persei','Cassiopeiae','Ursae Majoris','Ursae Minoris','Draconis',
  'Lyrae','Carinae','Centauri','Crucis','Virginis','Piscium',
  'Sagittarii','Capricorni','Aquarii','Geminorum','Cancri','Arietis',
  'Librae','Ophiuchi','Serpentis','Aurigae','Bootis','Coronae Borealis',
];

/**
 * Generate a star name from a SeededRNG instance and apparent magnitude.
 * Brighter stars (lower magnitude) get Bayer designations.
 * Dimmer stars get catalogue-style HD numbers.
 */
export function generateStarName(rng: SeededRNG, magnitude: number): string {
  if (magnitude < 3.0) {
    // Bayer designation: "Alpha Orionis"
    const greek = rng.pick(GREEK);
    const constellation = rng.pick(CONSTELLATIONS_GENITIVE);
    return `${greek} ${constellation}`;
  } else if (magnitude < 5.0) {
    // Flamsteed-style: "47 Tauri"
    const num = rng.int(99) + 1;
    const constellation = rng.pick(CONSTELLATIONS_GENITIVE).split(' ')[0]; // short form
    return `${num} ${constellation}`;
  } else {
    // Henry Draper catalogue number
    const hd = rng.int(359083) + 1;
    return `HD ${hd}`;
  }
}
```

**Verification:** Call `generateStarName` with a fixed RNG seed a dozen times and confirm no crashes; output should look like real star names.

---

#### Task 1.4 — Implement galaxy position distribution

**File to create:** `apps/metis-web/lib/star-catalogue/galaxy-distribution.ts`

This controls the spatial structure. Use density-wave-inspired elliptical arm distribution (as described by [beltoforion.de](https://beltoforion.de/en/spiral_galaxy_renderer)):

```typescript
import { SeededRNG } from './rng';

export interface GalaxyDistributionConfig {
  numArms: number;         // 2 or 4
  armWindingRate: number;  // e.g. 3.5 rad per unit radius
  coreRadius: number;      // fraction of galaxy radius that is "core" [0..1]
  diskFalloff: number;     // exponential falloff rate
}

/**
 * Generate a world-space position (wx, wy) for a star within a sector.
 *
 * Returns a position biased toward spiral arms and the galactic core.
 * All stars are in [-1, 1] world space.
 */
export function sampleGalaxyPosition(
  rng: SeededRNG,
  cfg: GalaxyDistributionConfig,
): { wx: number; wy: number; depthLayer: number } {
  // Determine whether this star is: core, arm, or halo
  const roll = rng.next();
  let wx: number, wy: number;

  if (roll < 0.15) {
    // Galactic core: tight Gaussian blob
    const r = Math.abs(gaussianApprox(rng)) * cfg.coreRadius;
    const theta = rng.next() * Math.PI * 2;
    wx = Math.cos(theta) * r;
    wy = Math.sin(theta) * r;
  } else if (roll < 0.85) {
    // Spiral arm: pick an arm, sample along it with scatter
    const armIndex = rng.int(cfg.numArms);
    const armOffset = (armIndex / cfg.numArms) * Math.PI * 2;

    // Exponentially distributed distance from centre
    const rawRadius = -Math.log(1 - rng.next() * 0.9999) / cfg.diskFalloff;
    const r = Math.min(rawRadius, 1.0);

    // Arm angle at this radius (logarithmic spiral)
    const armAngle = armOffset + r * cfg.armWindingRate;

    // Scatter perpendicular to arm (tighter near centre, wider at edge)
    const scatter = rng.range(-0.04, 0.04) * (0.5 + r);

    const theta = armAngle + scatter;
    wx = Math.cos(theta) * r;
    wy = Math.sin(theta) * r;
  } else {
    // Halo: uniform disk, low density
    const r = rng.next() * 0.9 + 0.05;
    const theta = rng.next() * Math.PI * 2;
    wx = Math.cos(theta) * r;
    wy = Math.sin(theta) * r;
  }

  // Depth layer: loosely correlated with radius (near-centre stars slightly closer)
  const depthLayer = 0.3 + rng.next() * 0.7;

  return { wx, wy, depthLayer };
}

/**
 * Box-Muller approximation using two uniform samples.
 * Returns ~N(0,1).
 */
function gaussianApprox(rng: SeededRNG): number {
  let s = 0;
  for (let i = 0; i < 6; i++) s += rng.next();
  return (s - 3) / Math.sqrt(3);
}
```

**Verification:** Render 5,000 points from `sampleGalaxyPosition` on a debug canvas (HTML `<canvas>` without camera transform). The output should visually show 2–4 spiral arms and a bright core blob.

---

#### Task 1.5 — Implement `StarCatalogue` class

**File to create:** `apps/metis-web/lib/star-catalogue/star-catalogue.ts`

```typescript
import { fnv1a32, SeededRNG } from './rng';
import { sampleGalaxyPosition, GalaxyDistributionConfig } from './galaxy-distribution';
import { generateStarName } from './star-name-generator';
import { generateStellarProfile } from '../landing-stars/stellar-profile';
import type { CatalogueStar, CatalogueSector, SectorKey, StarCatalogueConfig } from './types';

export class StarCatalogue {
  private readonly cfg: StarCatalogueConfig;
  private readonly distCfg: GalaxyDistributionConfig;
  private readonly sectorCache = new Map<string, CatalogueSector>();

  constructor(cfg: StarCatalogueConfig) {
    this.cfg = cfg;
    this.distCfg = {
      numArms: cfg.numArms,
      armWindingRate: cfg.armWindingRate,
      coreRadius: 0.15,
      diskFalloff: 3.0,
    };
  }

  /** Canonical string key for a sector. */
  private sectorKey(sx: number, sy: number): string {
    return `${sx},${sy}`;
  }

  /** World coordinate to sector index. */
  worldToSector(wx: number, wy: number): SectorKey {
    return {
      sx: Math.floor(wx / this.cfg.sectorSize),
      sy: Math.floor(wy / this.cfg.sectorSize),
    };
  }

  /**
   * Generate all stars for a sector. Pure/deterministic.
   * Calling this twice with the same sx/sy always returns identical results.
   */
  generateSector(sx: number, sy: number): CatalogueSector {
    const key = this.sectorKey(sx, sy);
    const cached = this.sectorCache.get(key);
    if (cached) return cached;

    const sectorSeed = fnv1a32(`${this.cfg.galaxySeed}:${key}`);
    const rng = new SeededRNG(sectorSeed);
    const stars: CatalogueStar[] = [];

    for (let i = 0; i < this.cfg.starsPerSector; i++) {
      const starSeedStr = `${this.cfg.galaxySeed}:${key}:${i}`;
      const starSeed = fnv1a32(starSeedStr);
      const starRng = new SeededRNG(starSeed);

      const { wx, wy, depthLayer } = sampleGalaxyPosition(starRng, this.distCfg);

      // Clamp to sector bounds with slight overlap for clustering continuity
      const sectorWx = sx * this.cfg.sectorSize + (wx + 1) * 0.5 * this.cfg.sectorSize;
      const sectorWy = sy * this.cfg.sectorSize + (wy + 1) * 0.5 * this.cfg.sectorSize;

      const profile = generateStellarProfile(starSeedStr);

      // Apparent magnitude: brighter for high luminosity, fainter for dim types
      // Map luminosity (solar luminosities) to magnitude scale
      const luminosity = profile.luminosity ?? 1.0;
      const baseMag = 5.0 - 2.5 * Math.log10(Math.max(luminosity, 0.0001));
      const apparentMagnitude = Math.max(0, Math.min(6.5, baseMag + starRng.range(-0.5, 0.5)));

      const name = generateStarName(new SeededRNG(starSeed + 1), apparentMagnitude);

      stars.push({
        id: `${this.cfg.galaxySeed}-${key}-${i}`,
        wx: sectorWx,
        wy: sectorWy,
        profile,
        name,
        apparentMagnitude,
        depthLayer,
      });
    }

    const sector: CatalogueSector = { key: { sx, sy }, stars };
    this.sectorCache.set(key, sector);
    return sector;
  }

  /**
   * Return all visible stars for the given world-space viewport rectangle.
   * Generates sectors on demand, caches them.
   *
   * @param wxMin  left edge in world space
   * @param wxMax  right edge in world space
   * @param wyMin  top edge in world space
   * @param wyMax  bottom edge in world space
   * @param bufferFactor  how many extra sectors to generate beyond viewport (default 1)
   */
  getVisibleStars(
    wxMin: number,
    wxMax: number,
    wyMin: number,
    wyMax: number,
    bufferFactor = 1,
  ): CatalogueStar[] {
    const s = this.cfg.sectorSize;
    const sxMin = Math.floor(wxMin / s) - bufferFactor;
    const sxMax = Math.floor(wxMax / s) + bufferFactor;
    const syMin = Math.floor(wyMin / s) - bufferFactor;
    const syMax = Math.floor(wyMax / s) + bufferFactor;

    const result: CatalogueStar[] = [];
    for (let sx = sxMin; sx <= sxMax; sx++) {
      for (let sy = syMin; sy <= syMax; sy++) {
        const sector = this.generateSector(sx, sy);
        result.push(...sector.stars);
      }
    }
    return result;
  }

  /**
   * Evict sectors far from the current viewport to prevent unbounded memory growth.
   * Call once per second (not per frame).
   */
  evictDistantSectors(
    currentSx: number,
    currentSy: number,
    maxManhattanDistance: number,
  ): void {
    for (const [key, sector] of this.sectorCache.entries()) {
      const dx = Math.abs(sector.key.sx - currentSx);
      const dy = Math.abs(sector.key.sy - currentSy);
      if (dx + dy > maxManhattanDistance) {
        this.sectorCache.delete(key);
      }
    }
  }
}
```

**Verification:**
1. Instantiate `StarCatalogue` in a unit test and call `getVisibleStars(-1, 1, -1, 1)`.
2. Assert: returns > 1,000 stars, no two stars share the same `id`, calling it twice returns structurally identical arrays.

---

### Phase 2: WebGL2 Instanced Star Renderer

**Goal:** Replace the canvas 2D `ConstellationFieldStar` drawing loop with a WebGL2 instanced renderer. 10,000 stars, one draw call per frame.  
**Estimated effort:** ~6 hours  
**Dependencies:** Phase 1 (CatalogueStar type, StarCatalogue)

---

#### Task 2.1 — Create WebGL canvas element alongside existing 2D canvas

**File to modify:** `apps/metis-web/app/page.tsx`

Currently there is one `<canvas ref={canvasRef}>`. Add a second canvas `<canvas ref={glCanvasRef}>` positioned identically underneath it:

```tsx
// In the JSX return:
<div style={{ position: 'relative', width: '100%', height: '100%' }}>
  {/* WebGL layer: stars, star dive */}
  <canvas
    ref={glCanvasRef}
    style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', zIndex: 1 }}
  />
  {/* 2D overlay layer: labels, edges, tooltips, HUD */}
  <canvas
    ref={canvasRef}
    style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', zIndex: 2 }}
    onMouseMove={handleMouseMove}
    onMouseDown={handleMouseDown}
    onWheel={handleWheel}
  />
  {/* React UI portals */}
  {/* ... existing panels ... */}
</div>
```

The `canvasRef` 2D canvas keeps all pointer events. Hit-testing is done in JS (spatial hash), not via WebGL picking.

**Verification:** Both canvases are present in the DOM. Take a screenshot — the page should look identical to before (2D canvas still draws everything).

---

#### Task 2.2 — Create `StarCatalogueRenderer`

**File to create:** `apps/metis-web/lib/star-catalogue/star-catalogue-renderer.ts`

This class owns the WebGL2 context, shaders, buffers, and the `draw()` method called each frame.

```typescript
// apps/metis-web/lib/star-catalogue/star-catalogue-renderer.ts

import type { CatalogueStar } from './types';

const VERT_SRC = /* glsl */`#version 300 es
precision highp float;

// Per-instance attributes (divisor = 1)
in vec2  a_screenPos;    // projected screen position [0, width] x [0, height]
in float a_pointSize;    // point size in pixels
in vec3  a_color;        // linear RGB
in float a_brightness;   // 0..1

uniform vec2 u_resolution;  // canvas width, height

out vec3  v_color;
out float v_brightness;

void main() {
  // Convert screen px to clip space
  vec2 clip = (a_screenPos / u_resolution) * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
  gl_PointSize = clamp(a_pointSize, 1.0, 64.0);
  v_color = a_color;
  v_brightness = a_brightness;
}
`;

const FRAG_SRC = /* glsl */`#version 300 es
precision mediump float;

in vec3  v_color;
in float v_brightness;

out vec4 fragColor;

void main() {
  // Soft circular disc
  vec2 uv = gl_PointCoord * 2.0 - 1.0;
  float r = dot(uv, uv);
  if (r > 1.0) discard;

  // Gaussian core + faint halo
  float core = exp(-r * 4.0);
  float halo = exp(-r * 1.5) * 0.3;
  float intensity = (core + halo) * v_brightness;

  fragColor = vec4(v_color * intensity, intensity);
}
`;

// Instance buffer stride: 8 floats = screen_x, screen_y, point_size, pad, r, g, b, brightness
const FLOATS_PER_STAR = 8;
const MAX_VISIBLE_STARS = 15_000;

export class StarCatalogueRenderer {
  private gl: WebGL2RenderingContext;
  private program: WebGLProgram;
  private vao: WebGLVertexArrayObject;
  private instanceBuffer: WebGLBuffer;
  private instanceData: Float32Array;

  // Attribute locations
  private aScreenPos: number;
  private aPointSize: number;
  private aColor: number;
  private aBrightness: number;
  private uResolution: WebGLUniformLocation;

  constructor(canvas: HTMLCanvasElement) {
    const gl = canvas.getContext('webgl2', {
      alpha: true,
      premultipliedAlpha: true,
      antialias: false,
    });
    if (!gl) throw new Error('WebGL2 not supported');
    this.gl = gl;

    this.program = this.compileProgram(VERT_SRC, FRAG_SRC);
    gl.useProgram(this.program);

    this.aScreenPos = gl.getAttribLocation(this.program, 'a_screenPos');
    this.aPointSize = gl.getAttribLocation(this.program, 'a_pointSize');
    this.aColor = gl.getAttribLocation(this.program, 'a_color');
    this.aBrightness = gl.getAttribLocation(this.program, 'a_brightness');
    this.uResolution = gl.getUniformLocation(this.program, 'u_resolution')!;

    // Allocate instance buffer (pre-allocated, updated each frame)
    this.instanceData = new Float32Array(MAX_VISIBLE_STARS * FLOATS_PER_STAR);
    this.instanceBuffer = gl.createBuffer()!;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instanceBuffer);
    gl.bufferData(gl.ARRAY_BUFFER, this.instanceData.byteLength, gl.DYNAMIC_DRAW);

    this.vao = gl.createVertexArray()!;
    gl.bindVertexArray(this.vao);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instanceBuffer);

    const STRIDE = FLOATS_PER_STAR * 4; // bytes

    // a_screenPos: offset 0, 2 floats
    gl.enableVertexAttribArray(this.aScreenPos);
    gl.vertexAttribPointer(this.aScreenPos, 2, gl.FLOAT, false, STRIDE, 0);
    gl.vertexAttribDivisor(this.aScreenPos, 1);

    // a_pointSize: offset 8 (2 floats * 4 bytes), 1 float
    gl.enableVertexAttribArray(this.aPointSize);
    gl.vertexAttribPointer(this.aPointSize, 1, gl.FLOAT, false, STRIDE, 8);
    gl.vertexAttribDivisor(this.aPointSize, 1);

    // pad float at offset 12 (unused, maintains 4-float alignment)

    // a_color: offset 16 (4 floats * 4 bytes), 3 floats
    gl.enableVertexAttribArray(this.aColor);
    gl.vertexAttribPointer(this.aColor, 3, gl.FLOAT, false, STRIDE, 16);
    gl.vertexAttribDivisor(this.aColor, 1);

    // a_brightness: offset 28 (7 floats * 4 bytes), 1 float
    gl.enableVertexAttribArray(this.aBrightness);
    gl.vertexAttribPointer(this.aBrightness, 1, gl.FLOAT, false, STRIDE, 28);
    gl.vertexAttribDivisor(this.aBrightness, 1);

    gl.bindVertexArray(null);

    // Enable blending for transparent point sprites
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA); // premultiplied alpha
  }

  /**
   * Draw all visible catalogue stars for the current frame.
   *
   * @param visibleStars  Stars returned by StarCatalogue.getVisibleStars()
   * @param projectFn     Converts (wx, wy) world coords → (sx, sy) screen px
   * @param zoomFactor    Current camera zoom for LOD point-size calculation
   * @param canvasW       Canvas pixel width
   * @param canvasH       Canvas pixel height
   */
  draw(
    visibleStars: CatalogueStar[],
    projectFn: (wx: number, wy: number) => { sx: number; sy: number },
    zoomFactor: number,
    canvasW: number,
    canvasH: number,
  ): void {
    const { gl, instanceData } = this;

    gl.viewport(0, 0, canvasW, canvasH);
    gl.clearColor(0, 0, 0, 0); // transparent — the page background shows through
    gl.clear(gl.COLOR_BUFFER_BIT);

    gl.useProgram(this.program);
    gl.uniform2f(this.uResolution, canvasW, canvasH);

    let count = 0;
    const maxStars = Math.min(visibleStars.length, MAX_VISIBLE_STARS);

    for (let i = 0; i < maxStars; i++) {
      const star = visibleStars[i];
      const { sx, sy } = projectFn(star.wx, star.wy);

      // Frustum cull: skip if off-screen
      if (sx < -64 || sx > canvasW + 64 || sy < -64 || sy > canvasH + 64) continue;

      // LOD point size: apparent magnitude + zoom
      // At zoom 1, a magnitude-0 star is 6px; mag-6 is 1px
      const basePx = Math.pow(10, (-star.apparentMagnitude + 6) / 2.5) * 2.5;
      const zoomScale = Math.sqrt(zoomFactor);
      const pointSize = Math.max(1.0, Math.min(basePx * zoomScale, 32.0));

      // Brightness: map magnitude to 0..1 intensity
      const brightness = Math.pow(10, (-star.apparentMagnitude) / 2.5) * 0.8 + 0.2;

      const palette = star.profile.palette;
      const base = count * FLOATS_PER_STAR;
      instanceData[base + 0] = sx;
      instanceData[base + 1] = sy;
      instanceData[base + 2] = pointSize;
      instanceData[base + 3] = 0; // pad
      instanceData[base + 4] = palette.core[0] / 255;
      instanceData[base + 5] = palette.core[1] / 255;
      instanceData[base + 6] = palette.core[2] / 255;
      instanceData[base + 7] = brightness;

      count++;
    }

    if (count === 0) return;

    gl.bindBuffer(gl.ARRAY_BUFFER, this.instanceBuffer);
    gl.bufferSubData(gl.ARRAY_BUFFER, 0, instanceData, 0, count * FLOATS_PER_STAR);

    gl.bindVertexArray(this.vao);
    gl.drawArraysInstanced(gl.POINTS, 0, 1, count);
    gl.bindVertexArray(null);
  }

  resize(width: number, height: number): void {
    this.gl.canvas.width = width;
    (this.gl.canvas as HTMLCanvasElement).height = height;
  }

  dispose(): void {
    const { gl } = this;
    gl.deleteBuffer(this.instanceBuffer);
    gl.deleteVertexArray(this.vao);
    gl.deleteProgram(this.program);
  }

  private compileProgram(vert: string, frag: string): WebGLProgram {
    const gl = this.gl;
    const vs = this.compileShader(gl.VERTEX_SHADER, vert);
    const fs = this.compileShader(gl.FRAGMENT_SHADER, frag);
    const prog = gl.createProgram()!;
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      throw new Error(`Program link error: ${gl.getProgramInfoLog(prog)}`);
    }
    gl.deleteShader(vs);
    gl.deleteShader(fs);
    return prog;
  }

  private compileShader(type: number, src: string): WebGLShader {
    const gl = this.gl;
    const sh = gl.createShader(type)!;
    gl.shaderSource(sh, src);
    gl.compileShader(sh);
    if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
      throw new Error(`Shader compile error: ${gl.getShaderInfoLog(sh)}`);
    }
    return sh;
  }
}
```

**Verification:**
1. Replace the `drawFieldStars()` call in `page.tsx` with `renderer.draw(visibleStars, project, zoom, w, h)`.
2. At zoom = 1 (normal view), you should see ≥5,000 coloured star points.
3. Check Chrome DevTools Performance tab: one draw call per frame, GPU frame time < 2ms for 10,000 stars.

---

#### Task 2.3 — Wire `StarCatalogue` + `StarCatalogueRenderer` into the render loop

**File to modify:** `apps/metis-web/app/page.tsx`

```typescript
// At component mount (useEffect with []):
const catalogue = new StarCatalogue({
  galaxySeed: 'metis-galaxy-v1',
  starsPerSector: 300,
  sectorSize: 0.1,
  numArms: 4,
  armWindingRate: 3.8,
});
const renderer = new StarCatalogueRenderer(glCanvasRef.current!);

// In the render loop, replace the field-star drawing section:
const camera = cameraRef.current;
const zoomFactor = camera.zoomFactor;

// Compute world-space viewport (inverse of world→screen projection)
const { wxMin, wxMax, wyMin, wyMax } = getWorldViewport(camera, canvasW, canvasH);

const visibleStars = catalogue.getVisibleStars(wxMin, wxMax, wyMin, wyMax, 1);

renderer.draw(
  visibleStars,
  (wx, wy) => projectWorldToScreen(wx, wy, camera, canvasW, canvasH),
  zoomFactor,
  canvasW,
  canvasH,
);

// Cache visible stars for hit-testing (shared ref, updated each frame)
visibleStarsRef.current = visibleStars;
```

**Helper to add to `lib/constellation-home.ts`:**

```typescript
/** Returns the world-space bounding box of the current viewport. */
export function getWorldViewport(
  camera: CameraState,
  canvasW: number,
  canvasH: number,
): { wxMin: number; wxMax: number; wyMin: number; wyMax: number } {
  // Inverse of projectWorldToScreen
  const scale = getBackgroundCameraScale(camera.zoomFactor);
  const halfW = canvasW / 2;
  const halfH = canvasH / 2;
  const invScale = 1 / (scale * Math.min(canvasW, canvasH));

  const wxMin = camera.offsetX / canvasW - halfW * invScale;
  // ... (full implementation follows same logic as existing projection)
  // See existing projectWorldToScreen for exact formula
}
```

**Note:** The full `getWorldViewport` implementation must mirror the exact inverse of `projectWorldToScreen` in `constellation-home.ts`. This is a one-time derivation based on the existing projection formula.

**Verification:** Navigate around the galaxy view. Stars appear, move with the camera, and zoom correctly. Frame rate stays ≥60fps in Chrome DevTools.

---

#### Task 2.4 — Remove the old `ConstellationFieldStar` drawing code

**File to modify:** `apps/metis-web/app/page.tsx`

Delete:
- `generateFieldStars()` function
- `fieldStarsRef` / `ConstellationFieldStar[]` state
- `drawFieldStars(ctx, ...)` function
- All `ConstellationFieldStar`-related import references

**Verification:** `tsc --noEmit` passes. The page loads without errors. The visual result is the WebGL star field.

---

#### Task 2.5 — Remove the painted galaxy overlay

**File to modify:** `apps/metis-web/app/page.tsx`

The existing `drawGalaxyBackground()` function draws a multi-layer radial gradient + fBm noise overlay. At extreme zoom-out (zoomFactor < 0.05), the instanced star renderer already compresses thousands of points into a galaxy shape. Remove the painted overlay or reduce it to just the galactic-core radial glow (a single small soft circle at screen center).

**What to keep:** a subtle radial core bloom on the 2D canvas — 2–3 concentric `createRadialGradient()` strokes centered on the galaxy origin projection, opacity ≤ 0.3.

**What to remove:** fBm cloud arms, dust lane strokes, the outer haze layer.

**Verification:** At zoomFactor 0.002, the galaxy view is composed of visible star points with a faint central glow. The galaxy shape (arms + core density) comes naturally from the star distribution, not painted layers.

---

### Phase 3: Star Interaction System

**Goal:** Every catalogue star is hoverable and clickable. Clicking opens a detail pane; "Add to Constellation" promotes it to a `UserStar`.  
**Estimated effort:** ~5 hours  
**Dependencies:** Phase 2 (visible stars cached in `visibleStarsRef`)

---

#### Task 3.1 — Build a `CatalogueStar` spatial index for hit testing

**File to modify:** `apps/metis-web/lib/star-catalogue/star-catalogue-spatial.ts` (new file)

The existing `buildLandingStarSpatialHash` in `landing-star-spatial-index.ts` operates on `LandingProjectedStar` (screen-space). Create a catalogue-specific wrapper that wraps the same algorithm:

```typescript
import { buildLandingStarSpatialHash, findClosestLandingStarHitTarget }
  from '../landing-stars/landing-star-spatial-index';
import type { CatalogueStar } from './types';

export interface CatalogueHitTarget {
  star: CatalogueStar;
  screenX: number;
  screenY: number;
  hitRadius: number;
}

export function buildCatalogueSpatialIndex(
  targets: CatalogueHitTarget[],
  cellSize: number,
) {
  // Adapt CatalogueHitTarget to the shape expected by the existing spatial hash
  const adapted = targets.map((t) => ({
    id: t.star.id,
    screenX: t.screenX,
    screenY: t.screenY,
    hitRadius: t.hitRadius,
    // carry the original target for retrieval
    _original: t,
  }));
  return buildLandingStarSpatialHash(adapted as any, cellSize);
}

export function findClosestCatalogueStar(
  hash: ReturnType<typeof buildCatalogueSpatialIndex>,
  mouseX: number,
  mouseY: number,
): CatalogueHitTarget | null {
  const result = findClosestLandingStarHitTarget(hash as any, mouseX, mouseY);
  return result ? (result as any)._original : null;
}
```

**Alternative (simpler):** Skip the adapter and implement a 2D spatial grid directly on `CatalogueStar` screen positions. Both approaches are acceptable.

---

#### Task 3.2 — Rebuild the spatial index each frame (throttled)

**File to modify:** `apps/metis-web/app/page.tsx`

```typescript
// After renderer.draw() in the render loop:
const targets: CatalogueHitTarget[] = visibleStars.map((star) => {
  const { sx, sy } = projectWorldToScreen(star.wx, star.wy, camera, canvasW, canvasH);
  const mag = star.apparentMagnitude;
  const hitRadius = Math.max(8, 14 - mag * 1.2); // bigger hit area for bright stars
  return { star, screenX: sx, screenY: sy, hitRadius };
});

// Rebuild index at ~10fps (not every frame) to save CPU
if (frameCount % 6 === 0) {
  catalogueSpatialIndexRef.current = buildCatalogueSpatialIndex(targets, 60);
}
```

---

#### Task 3.3 — Implement hover: tooltip showing star name + spectral class

**File to modify:** `apps/metis-web/app/page.tsx`

```typescript
// In handleMouseMove:
const hit = findClosestCatalogueStar(
  catalogueSpatialIndexRef.current,
  mouseX,
  mouseY,
);

if (hit) {
  hoveredCatalogueStarRef.current = hit.star;
  document.body.style.cursor = 'pointer';
} else {
  hoveredCatalogueStarRef.current = null;
  document.body.style.cursor = 'default';
}
```

**In the 2D canvas render section**, after drawing user star labels:

```typescript
const hovered = hoveredCatalogueStarRef.current;
if (hovered) {
  const { sx, sy } = projectWorldToScreen(hovered.wx, hovered.wy, camera, canvasW, canvasH);
  drawStarTooltip(ctx, sx, sy, hovered.name, hovered.profile.spectralClass);
}
```

**`drawStarTooltip` helper** (add to `page.tsx` or extract to `lib/star-catalogue/star-tooltip.ts`):

```typescript
function drawStarTooltip(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  name: string,
  spectralClass: string,
): void {
  const PADDING = 8;
  const label = `${name}  ·  ${spectralClass}`;
  ctx.font = '12px "Inter", sans-serif';
  const textW = ctx.measureText(label).width;
  const boxW = textW + PADDING * 2;
  const boxH = 24;
  const bx = x + 14;
  const by = y - 14;

  // Background pill
  ctx.fillStyle = 'rgba(0,0,0,0.75)';
  ctx.beginPath();
  ctx.roundRect(bx, by - boxH, boxW, boxH, 4);
  ctx.fill();

  // Text
  ctx.fillStyle = '#f0f0f0';
  ctx.fillText(label, bx + PADDING, by - 7);
}
```

---

#### Task 3.4 — Implement click: open `StarDetailPane` for catalogue stars

**File to modify:** `apps/metis-web/app/page.tsx`

```typescript
// In handleMouseDown (or click handler):
const hit = findClosestCatalogueStar(
  catalogueSpatialIndexRef.current,
  mouseX,
  mouseY,
);

if (hit) {
  setSelectedCatalogueStar(hit.star); // new React state
  setSelectedUserStar(null);          // deselect user star
  e.stopPropagation();
}
```

Create a `CatalogueStarDetailPane` React component (or extend the existing `StarDetailPane`):

```tsx
// apps/metis-web/components/CatalogueStarDetailPane.tsx

interface Props {
  star: CatalogueStar;
  onClose: () => void;
  onAddToConstellation: (star: CatalogueStar) => void;
}

export function CatalogueStarDetailPane({ star, onClose, onAddToConstellation }: Props) {
  const { profile } = star;
  return (
    <div className="star-detail-pane">
      <button onClick={onClose}>×</button>
      <h2>{star.name}</h2>
      <p className="spectral">{profile.spectralClass} · {Math.round(profile.temperature).toLocaleString()} K</p>
      <dl>
        <dt>Mass</dt>         <dd>{profile.mass?.toFixed(2)} M☉</dd>
        <dt>Radius</dt>       <dd>{profile.radius?.toFixed(2)} R☉</dd>
        <dt>Luminosity</dt>   <dd>{profile.luminosity?.toFixed(3)} L☉</dd>
        <dt>Magnitude</dt>    <dd>{star.apparentMagnitude.toFixed(1)}</dd>
      </dl>
      <button
        className="add-to-constellation"
        onClick={() => onAddToConstellation(star)}
      >
        ✦ Add to My Constellation
      </button>
    </div>
  );
}
```

---

#### Task 3.5 — Implement "Add to Constellation" promotion

**File to modify:** `apps/metis-web/app/page.tsx`

```typescript
function handleAddCatalogueStarToConstellation(star: CatalogueStar): void {
  const userStar: UserStar = {
    ...star,                         // inherits id, wx, wy, profile, name, apparentMagnitude, depthLayer
    // Map world coords to the constellation coordinate system
    x: worldToConstellationX(star.wx),
    y: worldToConstellationY(star.wy),
    label: star.name,
    primaryDomainId: null,
    relatedDomainIds: [],
    stage: 'seed',
    notes: '',
    connectedUserStarIds: [],
    learningRoute: null,
  };
  setUserStars((prev) => [...prev, userStar]);
  setSelectedCatalogueStar(null);
}
```

The `worldToConstellationX/Y` helpers translate from `[-1, 1]` galaxy world coords to the existing constellation viewport coordinate space. Derive from the inverse of `constellationToWorldX/Y` if it exists, or create them.

---

### Phase 4: Galaxy Integration

**Goal:** Make the galaxy view at extreme zoom-out composed of real star catalogue points, not a painted overlay.  
**Estimated effort:** ~3 hours  
**Dependencies:** Phases 1, 2

---

#### Task 4.1 — Tune galaxy distribution for visual quality

**File to modify:** `apps/metis-web/lib/star-catalogue/galaxy-distribution.ts`

At zoom-out (zoomFactor < 0.1), all sectors are visible at once. The galaxy should look like a proper spiral galaxy. Tune the parameters:

```typescript
// Recommended StarCatalogue constructor config for visual quality:
{
  galaxySeed: 'metis-galaxy-v1',
  starsPerSector: 350,    // 400 sectors × 350 = 140,000 total catalogue stars
  sectorSize: 0.1,        // 0.1 × 0.1 world units per sector, 400 sectors total
  numArms: 4,
  armWindingRate: 3.8,
}
```

**Density calibration:**
- At zoomFactor 0.002 (maximum zoom-out), the galaxy radius in pixels ≈ `canvasHeight * 0.4`
- All 140,000 catalogue stars exist, but only ~10,000 are rendered (MAX_VISIBLE_STARS cap)
- To still show galaxy structure at extreme zoom-out, **magnitude-sort** the visible stars and prefer the brightest ones when the total exceeds MAX_VISIBLE_STARS:

```typescript
// In star-catalogue-renderer.ts, before the draw loop:
if (visibleStars.length > MAX_VISIBLE_STARS) {
  visibleStars.sort((a, b) => a.apparentMagnitude - b.apparentMagnitude);
  visibleStars = visibleStars.slice(0, MAX_VISIBLE_STARS);
}
```

---

#### Task 4.2 — Scale star point sizes with zoom (zoom-out compress, zoom-in expand)

**File to modify:** `apps/metis-web/lib/star-catalogue/star-catalogue-renderer.ts`

At extreme zoom-out, point size should be locked to 1px minimum to ensure the galaxy is visible as a structure, not a blank blur. At high zoom (star dive approach), points grow and eventually the LOD system takes over.

In the `draw()` loop, refine the size calculation:

```typescript
const scale = getBackgroundCameraScale(zoomFactor); // from constellation-home.ts
// Stars appear larger when zoomed in, pixel-capped at zoom-out
const basePx = Math.pow(10, (-star.apparentMagnitude + 6) / 2.5) * 2.5;
const zoomedPx = basePx * Math.sqrt(Math.max(zoomFactor, 0.01));
const pointSize = Math.max(1.0, Math.min(zoomedPx, 32.0));
```

**Verification:** At zoomFactor 0.002, the galaxy should be visible as ≥2,000 distinct points forming arm shapes. At zoomFactor 1, the constellation view shows well-spaced stars of varying sizes.

---

#### Task 4.3 — Parallax: all stars move with camera (consistent depth)

**File to modify:** `apps/metis-web/lib/constellation-home.ts`

Currently `ConstellationFieldStar` had a `parallaxFactor` that was inconsistently applied. With the new system, parallax is derived from each star's `depthLayer`:

```typescript
export function projectWorldToScreen(
  wx: number,
  wy: number,
  depthLayer: number,   // 0 = background, 1 = foreground
  camera: CameraState,
  canvasW: number,
  canvasH: number,
): { sx: number; sy: number } {
  const scale = getBackgroundCameraScale(camera.zoomFactor);
  // Parallax: foreground stars move slightly more with pan
  const parallax = 0.85 + depthLayer * 0.15;
  const sx = canvasW / 2 + (wx - camera.worldCenterX * parallax) * scale * canvasW;
  const sy = canvasH / 2 + (wy - camera.worldCenterY * parallax) * scale * canvasH;
  return { sx, sy };
}
```

Update all call sites of `projectWorldToScreen` to pass `star.depthLayer` (or `0.5` as a neutral default for the 2D UI elements).

---

### Phase 5: Unified Star Identity

**Goal:** User stars and catalogue stars are the same type. The rendering pipeline treats them identically except for the 2D overlay (labels, faculty rings, connection edges).  
**Estimated effort:** ~4 hours  
**Dependencies:** Phases 1–4

---

#### Task 5.1 — Migrate `UserStar` to extend `CatalogueStar`

**File to modify:** `apps/metis-web/lib/constellation-types.ts`

The current `UserStar` in `constellation-types.ts` has manually defined fields. Replace its definition with:

```typescript
// apps/metis-web/lib/constellation-types.ts

export type { UserStar } from './star-catalogue/types';
// Re-export for backwards compatibility
```

Ensure the new `UserStar` in `star-catalogue/types.ts` has all the fields the UI currently uses: `label`, `primaryDomainId`, `relatedDomainIds`, `stage`, `notes`, `connectedUserStarIds`, `learningRoute`.

**Migration note:** Existing persisted user stars (localStorage/DB) may have the old shape without `wx`/`wy`/`profile`. Write a migration function:

```typescript
export function migrateUserStar(old: OldUserStar): UserStar {
  // Generate a deterministic profile from the old star's id
  const profile = generateStellarProfile(old.id);
  const name = old.label || generateStarName(new SeededRNG(fnv1a32(old.id)), 3.0);
  return {
    id: old.id,
    wx: old.x ?? 0, // fallback; will be re-positioned if needed
    wy: old.y ?? 0,
    profile,
    name,
    apparentMagnitude: 2.5,
    depthLayer: 0.5,
    label: old.label ?? '',
    primaryDomainId: old.primaryDomainId ?? null,
    relatedDomainIds: old.relatedDomainIds ?? [],
    stage: old.stage ?? 'seed',
    notes: old.notes ?? '',
    connectedUserStarIds: old.connectedUserStarIds ?? [],
    learningRoute: old.learningRoute ?? null,
  };
}
```

---

#### Task 5.2 — Render user stars through the WebGL renderer

**File to modify:** `apps/metis-web/app/page.tsx`

Pass user stars alongside catalogue stars to the renderer:

```typescript
const allRenderStars: CatalogueStar[] = [
  ...visibleCatalogueStars,
  ...userStars, // UserStar extends CatalogueStar, so this is type-safe
];
renderer.draw(allRenderStars, projectFn, zoomFactor, canvasW, canvasH);
```

User stars get their base star point rendered by WebGL. The 2D canvas then draws _on top_:
- Faculty colour ring around the user star's position
- Label text
- Connection edges to other user stars
- Stage badge (seed/sprout/bloom/nova icon)

This is the existing `drawUserStar()` logic — keep it, but call it as an overlay pass _after_ the WebGL frame has rendered.

---

#### Task 5.3 — Unify hover/click handling

**File to modify:** `apps/metis-web/app/page.tsx`

The spatial index should include both catalogue stars _and_ user stars. Build one combined index:

```typescript
const allTargets: CatalogueHitTarget[] = allRenderStars.map((star) => {
  const { sx, sy } = projectWorldToScreen(star.wx, star.wy, star.depthLayer, camera, canvasW, canvasH);
  // User stars get a larger hit radius (they are primary interactive objects)
  const isUserStar = 'label' in star;
  const hitRadius = isUserStar ? 18 : Math.max(8, 14 - star.apparentMagnitude * 1.2);
  return { star, screenX: sx, screenY: sy, hitRadius };
});
catalogueSpatialIndexRef.current = buildCatalogueSpatialIndex(allTargets, 60);
```

On click, check whether the closest star is a `UserStar` (has `label`) or a `CatalogueStar`:

```typescript
const hit = findClosestCatalogueStar(catalogueSpatialIndexRef.current, mouseX, mouseY);
if (hit) {
  const isUserStar = 'label' in hit.star;
  if (isUserStar) {
    setSelectedUserStar(hit.star as UserStar);
  } else {
    setSelectedCatalogueStar(hit.star);
  }
}
```

---

### Phase 6: Star Dive Integration

**Goal:** Any catalogue star (not just user stars) can be dived into with the existing WebGL2 shader close-up.  
**Estimated effort:** ~2 hours  
**Dependencies:** Phases 1–5

---

#### Task 6.1 — Modify `StarDiveOverlay` to accept `CatalogueStar`

**File to modify:** `apps/metis-web/app/page.tsx` (or wherever `StarDiveOverlay` is defined)

Currently `StarDiveOverlay` reads a `UserStar.stellarProfile`. The new `CatalogueStar` has `star.profile` (same `StellarProfile` type from `stellar-profile.ts`). Update the prop type:

```typescript
interface StarDiveOverlayProps {
  // Before: star: UserStar
  // After:
  star: CatalogueStar;      // UserStar also satisfies this since it extends CatalogueStar
  zoomFactor: number;
  // ... rest of existing props
}

// Inside StarDiveOverlay, change:
// Before: const profile = star.stellarProfile;
// After:
const profile = star.profile;
```

---

#### Task 6.2 — Trigger star dive from catalogue star focus

**File to modify:** `apps/metis-web/lib/constellation-home.ts`

The existing `setStarDiveFocus` logic targets a `UserStar`. Generalise it to accept any `CatalogueStar`:

```typescript
export function setStarDiveFocus(
  camera: CameraState,
  star: CatalogueStar,  // was UserStar
): CameraState {
  return {
    ...camera,
    diveFocusWx: star.wx,
    diveFocusWy: star.wy,
    diveFocusStar: star,
  };
}
```

When the user zooms into a catalogue star (via scroll or double-click), call `setStarDiveFocus` with it. The `STAR_DIVE_ZOOM_THRESHOLD = 200` logic remains unchanged — it just activates the close-up shader when zoomFactor exceeds 200 and a focus star is set.

---

#### Task 6.3 — Select closest star as dive target when zooming past threshold

**File to modify:** `apps/metis-web/app/page.tsx`

When `zoomFactor` crosses `STAR_DIVE_ZOOM_THRESHOLD`, if no dive target is set, automatically pick the closest catalogue star to the current screen centre:

```typescript
useEffect(() => {
  if (zoomFactor >= STAR_DIVE_ZOOM_THRESHOLD && !diveFocusStar) {
    const centre = { x: canvasW / 2, y: canvasH / 2 };
    const closest = findClosestCatalogueStar(catalogueSpatialIndexRef.current, centre.x, centre.y);
    if (closest) {
      cameraRef.current = setStarDiveFocus(cameraRef.current, closest.star);
    }
  }
}, [zoomFactor]);
```

**Verification:** Zoom in on any star in the catalogue. At zoomFactor ≥ 200, the WebGL2 shader surface overlay activates showing the photorealistic star surface. The star's spectral type (from `profile.spectralClass`) drives the shader's colour parameters.

---

## 6. Performance Budget

| Concern | Target | Mitigation |
|---|---|---|
| Visible star count | ≤15,000 per frame | `MAX_VISIBLE_STARS = 15_000`; magnitude-sort + cull |
| WebGL draw calls | 1 per frame (stars) + 1 (dive overlay) | Instanced `drawArraysInstanced()` |
| GPU frame time (stars) | < 2ms | GL_POINTS are extremely cheap; no geometry per star |
| JS frame time (CPU) | < 4ms | Sector generation is cached; only `bufferSubData` on the hot path |
| Sector generation | Off hot path | Sectors are lazily generated and cached; generation happens once per sector ever |
| Spatial index rebuild | ~10 fps (every 6 frames) | `frameCount % 6 === 0` guard |
| Memory (sector cache) | < 50MB | 400 sectors × 350 stars × ~200 bytes per star ≈ 28MB; evict distant sectors |
| `visibleStarsRef` allocation | Zero per frame | Pre-allocated; `getVisibleStars` re-uses the same sector arrays |

**Canvas size:** Use `devicePixelRatio` clamped to `min(window.devicePixelRatio, 2)` for both canvases to avoid GPU overload on retina displays.

---

## 7. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| WebGL2 unavailable (old browser/device) | Low | High | Check `canvas.getContext('webgl2')` at init; fall back to canvas 2D with reduced star count (500) |
| `generateStellarProfile` doesn't expose `luminosity` | Medium | Low | Check the `StellarProfile` type; if `luminosity` is missing, derive it from `temperature` using Stefan-Boltzmann: `L ∝ R² T⁴` |
| `StellarProfile.palette.core` shape is not `[r,g,b]` | Medium | Medium | Inspect `stellar-profile.ts`; adapt colour extraction to match actual palette structure |
| Sector cache grows unbounded during pan | Low | Medium | Implement `evictDistantSectors()` on a 1-second interval |
| Two-canvas stacking breaks existing pointer events | Medium | High | Ensure `glCanvas` has `pointer-events: none`; all mouse handling stays on the 2D canvas |
| Star dive activation auto-picking wrong star | Low | Low | Only auto-pick if user is actively zooming towards a visible star; add a minimum distance threshold (50px) |
| Migrating old `UserStar` data loses constellation positions | Medium | High | Write and test `migrateUserStar()` before shipping Phase 5; keep old `x`/`y` fields in `UserStar` as nullable deprecation shim |
| Visual regression: galaxy looks worse than painted overlay | Medium | Medium | Keep the painted overlay as a debug toggle; A/B compare at zoomFactor 0.002 before shipping Phase 4 |

---

## 8. File Change Summary

| File | Action | Phase |
|---|---|---|
| `lib/star-catalogue/types.ts` | **Create** — `CatalogueStar`, `UserStar`, `SectorKey`, `StarCatalogueConfig` | 1 |
| `lib/star-catalogue/rng.ts` | **Create** — `fnv1a32`, `SeededRNG` (Mulberry32) | 1 |
| `lib/star-catalogue/star-name-generator.ts` | **Create** — `generateStarName()` | 1 |
| `lib/star-catalogue/galaxy-distribution.ts` | **Create** — `sampleGalaxyPosition()` spiral arm distribution | 1 |
| `lib/star-catalogue/star-catalogue.ts` | **Create** — `StarCatalogue` class with `getVisibleStars`, `generateSector`, `evictDistantSectors` | 1 |
| `lib/star-catalogue/index.ts` | **Create** — barrel export | 1 |
| `lib/landing-stars/stellar-profile.ts` | **Modify** — extract `hashSeed` / FNV-1a into `rng.ts`, import from there | 1 |
| `app/page.tsx` | **Modify** — add `glCanvasRef`, instantiate `StarCatalogue` + `StarCatalogueRenderer`, remove old field star code, wire render loop | 2 |
| `lib/star-catalogue/star-catalogue-renderer.ts` | **Create** — WebGL2 instanced renderer with VAO, instance buffer, GLSL shaders | 2 |
| `lib/constellation-home.ts` | **Modify** — add `getWorldViewport()`, update `projectWorldToScreen` to accept `depthLayer` | 2, 4 |
| `lib/star-catalogue/star-catalogue-spatial.ts` | **Create** — `buildCatalogueSpatialIndex`, `findClosestCatalogueStar` | 3 |
| `components/CatalogueStarDetailPane.tsx` | **Create** — React detail pane for inspecting catalogue stars | 3 |
| `lib/constellation-types.ts` | **Modify** — re-export `UserStar` from `star-catalogue/types.ts` | 5 |
| `app/page.tsx` | **Modify** — `StarDiveOverlay` prop change (`star.stellarProfile` → `star.profile`), `setStarDiveFocus` generalised | 6 |
| `lib/constellation-home.ts` | **Modify** — `setStarDiveFocus` accepts `CatalogueStar` | 6 |

---

## 9. Implementation Order & Checkpoints

```
Phase 1 ──► Phase 2 ──► Phase 3
               │              │
               ▼              ▼
            Phase 4 ──► Phase 5 ──► Phase 6
```

**Checkpoint after Phase 2:** The galaxy view works with WebGL instanced stars. Performance target met (60fps, 10K stars). No interactivity yet, but the visual result is correct.

**Checkpoint after Phase 3:** Every star is clickable. "Add to Constellation" works. The detail pane shows spectral class, temperature, mass. This is the main feature-complete milestone.

**Checkpoint after Phase 5:** User stars and catalogue stars are visually indistinguishable (same renderer), only differentiated by the 2D overlay. The system feels unified.

**Checkpoint after Phase 6:** Full star dive works from any star. The experience of zooming into a catalogue star to see its photorealistic surface closes the loop on the original vision.

---

## 10. Quick Reference: Key Constants

```typescript
// Keep these in sync with constellation-home.ts
const MIN_ZOOM = 0.002;
const MAX_ZOOM = 2000;
const STAR_DIVE_ZOOM_THRESHOLD = 200;
const STAR_DIVE_FULL_ZOOM = 800;

// New constants to add to star-catalogue/star-catalogue.ts
const MAX_VISIBLE_STARS = 15_000;
const SECTOR_SIZE = 0.1;         // world units
const STARS_PER_SECTOR = 350;
const SECTORS_TOTAL = 400;       // 20×20
const SPATIAL_INDEX_CELL = 60;   // pixels
const SPATIAL_INDEX_REBUILD_INTERVAL = 6; // frames
const SECTOR_EVICT_MANHATTAN = 8; // evict sectors > 8 tiles away
```

---

## 11. Suggested Coding Agent Prompt (Claude Code)

When handing this plan to an AI coding agent, use the following prompt preamble:

```
You are implementing the Interactive Star Catalogue for the Metis project.
Repository: mrzapa/metis — monorepo, target app: apps/metis-web (Next.js).
Full implementation plan is in: interactive-star-catalogue-plan.md

Rules:
1. Implement one Phase at a time. Do not skip ahead.
2. After each task, run `cd apps/metis-web && npx tsc --noEmit` and fix any type errors before moving on.
3. Do NOT delete any existing file without being explicitly told to. Prefer additive changes.
4. The `StellarProfile` type from `lib/landing-stars/stellar-profile.ts` is authoritative — read it before writing any code that accesses `.palette`, `.luminosity`, or `.spectralClass`.
5. The render loop is in `app/page.tsx`. It uses `requestAnimationFrame`. All rendering changes go through the existing loop — do not add a second animation loop.
6. After implementing Phase 2, take a screenshot of the galaxy view at zoomFactor 0.002 and verify spiral arm structure is visible.
```

---

*Plan authored 2026-04-05. All TypeScript interfaces, GLSL shader code, and pseudocode are ready-to-implement. Adapt palette field access paths after reading the live `stellar-profile.ts` source.*
