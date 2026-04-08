# Interactive Star Catalogue — Coding Agent Prompts

> Execute these prompts in order. Each prompt is self-contained with exact file paths, line numbers, and code. Do not skip phases. Run `npx tsc --noEmit` after each prompt to verify compilation.

---

## Prompt 1 of 6 — Wire the Star Catalogue into page.tsx (Phase 2)

```
You are working on the Metis project at apps/metis-web.

GOAL: Replace the tile-based field star system with the new StarCatalogue from lib/star-catalogue/.
The star-catalogue module is already committed at apps/metis-web/lib/star-catalogue/ with these files:
  types.ts, rng.ts, star-name-generator.ts, galaxy-distribution.ts, star-catalogue.ts, index.ts

IMPORTANT RULES:
- Do NOT change any file in lib/star-catalogue/ — it is already correct.
- Do NOT remove anything not explicitly listed below.
- Run `npx tsc --noEmit` after each file change.

STEP 1 — Add imports to apps/metis-web/app/page.tsx

At line 93, after the existing landing-stars imports, add:

```ts
import { StarCatalogue, DEFAULT_CATALOGUE_CONFIG } from "@/lib/star-catalogue";
import type { CatalogueStar } from "@/lib/star-catalogue";
```

STEP 2 — Add the catalogue ref inside the Home() component

At line ~920 (near `const starDiveOverlayViewRef = useRef(...)`), add:

```ts
const starCatalogueRef = useRef<StarCatalogue | null>(null);
if (!starCatalogueRef.current) {
  starCatalogueRef.current = new StarCatalogue(
    DEFAULT_CATALOGUE_CONFIG,
    generateStellarProfile,
  );
}
```

Also add a Map ref to cache catalogue star profiles and a lookup Map:

```ts
const catalogueStarProfileCacheRef = useRef(new Map<string, StellarProfile>());
```

STEP 3 — Add a catalogue star lookup inside the render effect

Inside the useEffect that contains the render loop (the one starting around line 1983 with `const canvas = canvasRef.current`), add a mutable variable alongside the existing `let visibleWorldStars`:

```ts
let catalogueStarLookup = new Map<string, CatalogueStar>();
```

STEP 4 — Replace refreshVisibleStars (lines 2498–2537)

Replace ONLY the tile-fetching loop (lines 2518-2537) inside the `if (shouldRebuildVisibleWorldStars)` block. Keep everything BELOW the `visibleWorldStars = nextVisibleWorldStars;` line unchanged. Here is the replacement for lines 2518-2537:

```ts
      if (shouldRebuildVisibleWorldStars) {
        const nextVisibleWorldStars: WorldStarData[] = [];
        const catalogue = starCatalogueRef.current;
        const nextLookup = new Map<string, CatalogueStar>();

        if (catalogue) {
          const catalogueStars = catalogue.getVisibleStars(
            worldBounds.left,
            worldBounds.right,
            worldBounds.top,
            worldBounds.bottom,
            1,
          );

          for (const cat of catalogueStars) {
            nextLookup.set(cat.id, cat);
            catalogueStarProfileCacheRef.current.set(cat.id, cat.profile);

            const brightnessNorm = 1 - cat.apparentMagnitude / 6.5;
            const brightness = 0.12 + brightnessNorm * 0.72;
            const baseSize = 0.3 + brightnessNorm * 2.2;

            const revealIdx = Math.min(
              WORLD_STAR_REVEAL_STEPS.length - 1,
              cat.apparentMagnitude < 2
                ? 0
                : cat.apparentMagnitude < 4
                  ? Math.floor(cat.apparentMagnitude * 2)
                  : Math.floor(cat.apparentMagnitude * 3),
            );
            const revealZoom = WORLD_STAR_REVEAL_STEPS[revealIdx] ?? 1;

            if (backgroundCamera.zoomFactor + 1e-6 < revealZoom) continue;

            const v = cat.profile.visual;
            nextVisibleWorldStars.push({
              id: cat.id,
              worldX: cat.wx,
              worldY: cat.wy,
              layer: cat.depthLayer < 0.4 ? 0 : cat.depthLayer < 0.7 ? 1 : 2,
              baseSize,
              brightness,
              twinkle: v.twinkleSpeed > 0.003,
              twinkleSpeed: v.twinkleSpeed,
              twinklePhase: v.twinklePhase,
              parallaxFactor: cat.depthLayer < 0.4 ? 0.026 : cat.depthLayer < 0.7 ? 0.013 : 0.006,
              hasDiffraction: v.diffractionStrength > 0.1 && baseSize > 1.2,
              revealZoomFactor: revealZoom,
            });
          }
        }

        catalogueStarLookup = nextLookup;
        visibleWorldStars = nextVisibleWorldStars;
```

STEP 5 — Update getCachedStellarProfile to check catalogue cache first

Find `function getCachedStellarProfile` (around line ~2680) and add this at the top of the function body:

```ts
const catProfile = catalogueStarProfileCacheRef.current.get(starId);
if (catProfile) return catProfile;
```

STEP 6 — Periodic sector eviction

At the end of the refreshVisibleStars function, just before the closing brace, add:

```ts
// Evict distant sectors every ~60 frames
if (Math.random() < 0.016 && starCatalogueRef.current) {
  const cam = readBackgroundCamera();
  const centerSector = starCatalogueRef.current.worldToSector(cam.x, cam.y);
  starCatalogueRef.current.evictDistantSectors(centerSector.sx, centerSector.sy, 6);
}
```

DO NOT delete the old getWorldTileStars function or tileCache yet — they will be removed in a later phase. The catalogue now feeds the same pipeline, so the tile functions become dead code.

VERIFICATION:
- `npx tsc --noEmit` passes
- Run the app: stars should appear from the catalogue (they are spiral-arm distributed)
- Zoom in/out: stars should reveal progressively (dim stars appear at higher zoom)
- Pan: new sectors should lazily generate as you move
```

---

## Prompt 2 of 6 — Star Interaction System (Phase 3)

```
You are working on apps/metis-web/app/page.tsx in the Metis project.

GOAL: Make every catalogue star hoverable and clickable. Show a tooltip on hover, open a detail dialog on click.

PREREQUISITE: Phase 2 (Prompt 1) must be applied first.

IMPORTANT RULES:
- Do NOT modify lib/star-catalogue/ or lib/landing-stars/ files.
- Keep all existing user star interaction code intact.
- Run `npx tsc --noEmit` after changes.

STEP 1 — Hash ALL visible stars, not just addable ones

At line ~2727, find:
```ts
const addableTargets = landingRenderableStars.filter((star) => star.addable);

landingStarSpatialHash = addableTargets.length > 0
  ? buildLandingStarSpatialHash(addableTargets)
  : null;
```

Replace with:
```ts
const addableTargets = landingRenderableStars.filter((star) => star.addable);

// Hash ALL visible stars for catalogue star interaction (not just addable)
landingStarSpatialHash = landingRenderableStars.length > 0
  ? buildLandingStarSpatialHash(landingRenderableStars)
  : null;
// Keep the addable-only hash for the add-star flow
landingAddableSpatialHash = addableTargets.length > 0
  ? buildLandingStarSpatialHash(addableTargets)
  : null;
```

Add a new mutable variable near the existing `let landingStarSpatialHash` (around line ~2060):
```ts
let landingAddableSpatialHash: LandingStarSpatialHash | null = null;
```

Then update ALL existing references to `landingStarSpatialHash` that are specifically about finding addable candidates (in the click handler and hover handler around lines 4069 and 4075) to use `landingAddableSpatialHash` instead. The landingStarSpatialHash should be used for the new catalogue star hover/click below.

STEP 2 — Add state for hovered catalogue star

Near the existing `const [hoveredAddCandidateId, setHoveredAddCandidateId]` at line ~848, add:

```ts
const [hoveredCatalogueStarId, setHoveredCatalogueStarId] = useState<string | null>(null);
const hoveredCatalogueStarRef = useRef<CatalogueStar | null>(null);
const [selectedCatalogueStar, setSelectedCatalogueStar] = useState<CatalogueStar | null>(null);
```

STEP 3 — Add catalogue star hover detection

In the mousemove handler (around line 4050-4090), AFTER the existing addable candidate hover check, add a fallback check for any catalogue star:

```ts
// Catalogue star hover (only if no addable candidate is hovered)
if (!hoveredAddCandidateRef.current && landingStarSpatialHash) {
  const closest = findClosestLandingStarHitTarget(landingStarSpatialHash, e.clientX, e.clientY);
  if (closest) {
    const catStar = catalogueStarLookup.get(closest.id);
    if (catStar && hoveredCatalogueStarRef.current?.id !== catStar.id) {
      hoveredCatalogueStarRef.current = catStar;
      setHoveredCatalogueStarId(catStar.id);
    }
  } else if (hoveredCatalogueStarRef.current) {
    hoveredCatalogueStarRef.current = null;
    setHoveredCatalogueStarId(null);
  }
}
```

STEP 4 — Add catalogue star click handler

In the click/pointerup handler (around line 4400-4470), AFTER the existing addable candidate check and BEFORE the final `armedAddCandidateIdRef.current = null;` fallback, add:

```ts
// Catalogue star click (open observatory dialog)
if (landingStarSpatialHash) {
  const closest = findClosestLandingStarHitTarget(landingStarSpatialHash, e.clientX, e.clientY);
  if (closest) {
    const catStar = catalogueStarLookup.get(closest.id);
    if (catStar) {
      setSelectedCatalogueStar(catStar);
      closeConcept();
      return;
    }
  }
}
```

STEP 5 — Add the promoteCatalogueStarToUser function

Add this near the other star-adding functions (around line 2280):

```ts
async function promoteCatalogueStarToUser(catStar: CatalogueStar) {
  const backgroundCamera = readBackgroundCamera();
  const scale = getBackgroundCameraScale(backgroundCamera.zoomFactor);
  const screenX = (catStar.wx - backgroundCamera.x) * scale + W / 2;
  const screenY = (catStar.wy - backgroundCamera.y) * scale + H / 2;
  const constellationPoint = screenToConstellationPoint(
    { x: screenX, y: screenY }, W, H, backgroundCamera,
  );

  const inference = inferConstellationFaculty(constellationPoint);
  const createdStar = await addUserStar({
    x: constellationPoint.x,
    y: constellationPoint.y,
    size: 0.82 + Math.min(catStar.profile.luminositySolar, 3) * 0.18,
    label: catStar.name,
    primaryDomainId: inference.primary.faculty.id,
    stage: "seed",
  });

  if (createdStar) {
    setSelectedCatalogueStar(null);
    openStarDetails(createdStar, "new");
    showToast({ dismissMs: 2400, message: `${catStar.name} added to your constellation`, tone: "default" });
  }
}
```

STEP 6 — Add the tooltip JSX

In the JSX return block (around line 4640, after the existing hover tooltip), add:

```tsx
{/* Catalogue star tooltip */}
{hoveredCatalogueStarId && hoveredCatalogueStarRef.current && !selectedCatalogueStar && (() => {
  const cat = hoveredCatalogueStarRef.current;
  const renderState = visibleStarsRef.current.find(s => s.id === cat.id);
  if (!renderState) return null;
  return (
    <div
      style={{
        position: "fixed",
        left: Math.min(renderState.screenX + 16, (typeof window !== "undefined" ? window.innerWidth : 1920) - 260),
        top: renderState.screenY - 40,
        zIndex: 210,
        pointerEvents: "none",
        background: "rgba(6, 10, 20, 0.92)",
        border: "1px solid rgba(200, 210, 225, 0.12)",
        borderRadius: 10,
        padding: "10px 14px",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        boxShadow: "0 12px 32px rgba(0, 0, 0, 0.4)",
        maxWidth: 240,
        animation: "metis-tooltipIn 180ms cubic-bezier(0.16, 1, 0.3, 1)",
      }}
    >
      <div style={{ fontFamily: '"Space Grotesk", sans-serif', fontSize: 14, fontWeight: 500, color: "rgba(240, 244, 255, 0.96)", letterSpacing: "-0.01em" }}>
        {cat.name}
      </div>
      <div style={{ marginTop: 4, fontSize: 11, color: "rgba(232, 184, 74, 0.82)", letterSpacing: "0.06em", textTransform: "uppercase" as const }}>
        {cat.profile.spectralClass} · {cat.profile.stellarType.replace(/_/g, " ")}
      </div>
      <div style={{ marginTop: 3, fontSize: 10, color: "rgba(180, 190, 210, 0.55)", letterSpacing: "0.02em" }}>
        {Math.round(cat.profile.temperatureK).toLocaleString()} K · {cat.profile.luminositySolar.toFixed(1)} L☉
      </div>
    </div>
  );
})()}
```

STEP 7 — Add the Star Observatory dialog JSX

After the tooltip, add:

```tsx
{/* Star Observatory — catalogue star detail dialog */}
{selectedCatalogueStar && (() => {
  const cat = selectedCatalogueStar;
  const p = cat.profile.palette;
  return (
    <div
      style={{
        position: "fixed",
        left: "50%",
        top: "50%",
        transform: "translate(-50%, -50%)",
        zIndex: 200,
        width: "min(380px, calc(100vw - 32px))",
        background: "rgba(6, 10, 20, 0.94)",
        border: "1px solid rgba(200, 210, 225, 0.09)",
        borderRadius: 18,
        overflow: "hidden",
        boxShadow: "0 24px 80px rgba(0, 0, 0, 0.5)",
        backdropFilter: "blur(24px)",
        WebkitBackdropFilter: "blur(24px)",
        animation: "metis-tooltipIn 300ms cubic-bezier(0.16, 1, 0.3, 1)",
      }}
    >
      {/* Colour strip from star palette */}
      <div style={{
        height: 3,
        background: `linear-gradient(90deg, rgb(${p.halo[0]},${p.halo[1]},${p.halo[2]}), rgb(${p.core[0]},${p.core[1]},${p.core[2]}), rgb(${p.accent[0]},${p.accent[1]},${p.accent[2]}))`,
      }} />
      <div style={{ padding: "22px 24px 20px" }}>
        <div style={{ fontSize: 10, letterSpacing: "0.24em", textTransform: "uppercase" as const, color: "rgba(232, 184, 74, 0.72)", fontFamily: '"Space Grotesk", sans-serif' }}>
          {cat.profile.stellarType.replace(/_/g, " ")}
        </div>
        <div style={{ marginTop: 8, fontFamily: '"Outfit", sans-serif', fontWeight: 300, fontSize: 26, color: "rgba(240, 244, 255, 0.96)", letterSpacing: "-0.02em" }}>
          {cat.name}
        </div>
        <div style={{ marginTop: 6, fontFamily: '"Space Grotesk", sans-serif', fontSize: 13, fontWeight: 500, color: "rgba(200, 210, 225, 0.7)" }}>
          {cat.profile.spectralClass}{cat.profile.luminosityClass ? ` ${cat.profile.luminosityClass}` : ""}
        </div>

        {/* Stats grid */}
        <div style={{ marginTop: 16, display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 8 }}>
          {[
            ["Temperature", `${Math.round(cat.profile.temperatureK).toLocaleString()} K`],
            ["Luminosity", `${cat.profile.luminositySolar.toFixed(1)} L☉`],
            ["Mass", `${cat.profile.massSolar.toFixed(2)} M☉`],
            ["Radius", `${cat.profile.radiusSolar.toFixed(2)} R☉`],
          ].map(([label, value]) => (
            <div key={label} style={{ padding: "10px 12px", borderRadius: 10, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(200,210,225,0.05)" }}>
              <div style={{ fontSize: 9, letterSpacing: "0.16em", textTransform: "uppercase" as const, color: "rgba(180,190,210,0.4)" }}>{label}</div>
              <div style={{ fontFamily: '"Outfit", sans-serif', fontSize: 16, fontWeight: 400, color: "rgba(240,244,255,0.9)", letterSpacing: "-0.01em" }}>{value}</div>
            </div>
          ))}
        </div>

        {/* Actions */}
        <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid rgba(200,210,225,0.06)", display: "flex", gap: 10 }}>
          <button
            type="button"
            onClick={() => promoteCatalogueStarToUser(cat)}
            style={{
              flex: 1,
              border: "1px solid rgba(232,184,74,0.22)",
              background: "rgba(28,40,72,0.56)",
              color: "rgba(255,245,221,0.94)",
              borderRadius: 999,
              padding: "10px 16px",
              fontSize: 11,
              letterSpacing: "0.1em",
              textTransform: "uppercase" as const,
              cursor: "pointer",
              fontFamily: '"Inter", sans-serif',
              transition: "all 0.25s ease",
            }}
          >
            Add to Constellation
          </button>
          <button
            type="button"
            onClick={() => setSelectedCatalogueStar(null)}
            style={{
              width: 38, height: 38,
              display: "flex", alignItems: "center", justifyContent: "center",
              border: "1px solid rgba(200,210,225,0.1)",
              background: "rgba(15,22,40,0.56)",
              color: "rgba(200,210,225,0.5)",
              borderRadius: 999,
              cursor: "pointer",
              fontSize: 16,
            }}
          >
            ✕
          </button>
        </div>
      </div>
    </div>
  );
})()}
```

STEP 8 — Add the tooltip animation keyframes to metisStyles

In the `const metisStyles` template literal (around line 5001), add this if the `metis-tooltipIn` keyframe doesn't already exist:

```css
@keyframes metis-tooltipIn {
  from { opacity: 0; transform: translateY(6px) scale(0.96); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
```

STEP 9 — Close the observatory on Escape

In the existing keydown handler, add:
```ts
if (e.key === "Escape" && selectedCatalogueStar) {
  setSelectedCatalogueStar(null);
  e.preventDefault();
  return;
}
```

VERIFICATION:
- `npx tsc --noEmit` passes
- Hover over any star: tooltip shows with name, spectral class, temperature
- Click a star: observatory dialog opens with full stats and palette colour strip
- "Add to Constellation" button creates a UserStar and opens star details
- Escape closes the observatory
- Existing user star interaction still works identically
```

---

## Prompt 3 of 6 — Galaxy Integration (Phase 4)

```
You are working on apps/metis-web/app/page.tsx and apps/metis-web/components/home/landing-starfield-webgl.tsx.

GOAL: At extreme zoom-out, catalogue stars naturally form the galaxy shape. Remove the painted galaxy overlay. Add a zoom-responsive star size uniform to the WebGL shader.

PREREQUISITE: Phases 2+3 (Prompts 1+2) must be applied first.

IMPORTANT RULES:
- Run `npx tsc --noEmit` after changes.
- Keep the existing nebulae/dust rendering — only remove the galaxy canvas.

STEP 1 — Add zoomScale to the frame interface

In apps/metis-web/components/home/landing-starfield-webgl.types.ts, add to LandingStarfieldFrame:
```ts
zoomScale: number;
```

STEP 2 — Add uZoomScale uniform to the vertex shader

In apps/metis-web/components/home/landing-starfield-webgl.tsx, find the vertexShader string.
Add this uniform declaration alongside the existing `uDpr` and `uTime`:
```glsl
uniform float uZoomScale;
```

Add this scaling logic just before the `gl_PointSize = ...` line:
```glsl
float zoomSizeScale = mix(0.15, 1.0, smoothstep(0.0, 0.4, uZoomScale));
```

Then multiply the existing gl_PointSize calculation by `zoomSizeScale`:
```glsl
gl_PointSize = max(0.5, <existing_expression> * zoomSizeScale);
```

STEP 3 — Add the uZoomScale uniform to the Three.js material

In the same file, find the `uniforms` object in the ShaderMaterial (it has `uDpr` and `uTime`). Add:
```ts
uZoomScale: { value: 1.0 },
```

In the render loop where `uTime` is updated, add:
```ts
material.uniforms.uZoomScale.value = frame.zoomScale ?? 1.0;
```

STEP 4 — Feed zoomScale from page.tsx

In page.tsx, find `landingStarfieldFrameRef.current = {` (around line ~2730). Add the `zoomScale` property:
```ts
landingStarfieldFrameRef.current = {
  height: H,
  revision: landingStarfieldFrameRef.current.revision + 1,
  stars: nextWebglStars,
  width: W,
  zoomScale: Math.min(1, Math.max(0,
    (Math.log(backgroundCamera.zoomFactor) - Math.log(0.002)) /
    (Math.log(2000) - Math.log(0.002))
  )),
};
```

STEP 5 — Remove the painted galaxy overlay

In page.tsx:
1. Find `function drawGalaxy()` (line ~2213). Delete the entire function (lines 2213-2221).
2. Find the `galaxyCanvas` creation (search for `const galaxyCanvas = document.createElement("canvas")`). Delete the entire block that creates and paints the galaxy canvas (the 3-layer painting: radial core glow, fBm cloud arms, star field). This is a substantial block — delete everything from the `galaxyCanvas` creation to where it finishes painting (approximately 40-60 lines).
3. Find the `drawGalaxy()` call in the render function (line ~3866). Delete it.

STEP 6 — Add a subtle galactic core glow as replacement

After the `drawGalaxy()` removal, add a lightweight replacement in the render function at the same location:
```ts
// Galactic core glow (replaces painted galaxy)
{
  const glowAlpha = 1 - smoothstep(0.002, 0.12, backgroundCamera.zoomFactor);
  if (glowAlpha > 0) {
    const scale = getBackgroundCameraScale(backgroundCamera.zoomFactor);
    const cx = (0 - backgroundCamera.x) * scale + W / 2;
    const cy = (0 - backgroundCamera.y) * scale + H / 2;
    const radius = Math.max(W, H) * 0.35 * Math.sqrt(scale);
    ctx!.save();
    ctx!.globalAlpha = ctx!.globalAlpha * glowAlpha * 0.16;
    const glow = ctx!.createRadialGradient(cx, cy, 0, cx, cy, radius);
    glow.addColorStop(0, "rgba(200, 170, 120, 0.3)");
    glow.addColorStop(0.3, "rgba(140, 150, 180, 0.12)");
    glow.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx!.fillStyle = glow;
    ctx!.fillRect(0, 0, W, H);
    ctx!.restore();
  }
}
```

VERIFICATION:
- `npx tsc --noEmit` passes
- At default zoom (1x): stars look the same as before
- Zoom out (toward 0.002): stars shrink to tiny points, naturally forming spiral arm galaxy structure
- The old painted galaxy overlay is gone — the stars ARE the galaxy
- Subtle warm core glow visible at extreme zoom-out
- Zoom in (toward 2000): stars grow, eventually triggering star dive
```

---

## Prompt 4 of 6 — Unified Star Identity (Phase 5)

```
You are working on apps/metis-web/app/page.tsx.

GOAL: User stars and catalogue stars render through the same WebGL pipeline. The 2D canvas drawUserStars() becomes an overlay-only renderer (faculty rings, selection, labels, RAG pulse) — the star body is rendered in WebGL.

PREREQUISITE: Phases 2-4 (Prompts 1-3) must be applied first.

STEP 1 — Include user star positions in the WebGL frame

Find the section that builds `nextWebglStars` from `flattenedRenderPlan` (around line ~2718-2724).
After building nextWebglStars, add user stars into the same array:

```ts
// Append user stars to the WebGL frame (unified rendering)
const userStarScale = Math.max(0.58, 0.36 + Math.pow(getConstellationCameraScale(backgroundCamera.zoomFactor), 0.72) * 0.64);
projectedUserStarRenderState.forEach((projState) => {
  const { star, target, stellarProfile } = projState;
  nextWebglStars.push({
    addable: false,
    apparentSize: star.size * 3.5 * userStarScale,
    brightness: Math.min(0.98, 0.6 + (star.size - 0.5) * 0.3),
    id: star.id,
    profile: stellarProfile,
    renderTier: "hero" as const,
    x: target.x,
    y: target.y,
  });
});
```

NOTE: `projectedUserStarRenderState` must already be built by this point. If the call to `rebuildProjectedUserStarRenderState` happens AFTER refreshVisibleStars in the render function, move the rebuild call to happen BEFORE refreshVisibleStars. Check the render function (around line 3850-3855) to confirm order.

STEP 2 — Strip the core fill from drawUserStars

In `function drawUserStars(t: number)` (line ~2962), remove the radial gradient fills that draw the star body:
- Remove the halo gradient fill (ctx.createRadialGradient for the halo)
- Remove the aura gradient fill
- Remove the core fill
- Remove diffraction spike rendering from 2D canvas (the WebGL shader handles this now)

KEEP ONLY these overlay elements:
- Faculty colour ring (`ctx.arc` with `strokeStyle` using faculty colour)
- RAG pulse ring
- Selection ring (dashed gold arc)
- Orbiting satellite dots
- Drag ghost

This means the 2D canvas only draws rings and decorations around user stars, while the actual star body is rendered in WebGL at the same position. This creates a unified look.

STEP 3 — Consistent parallax

Find any place where user star parallax is hardcoded (e.g., `parallax: 0.015` in the nodes array around line 2315). Leave node parallax alone, but ensure user stars in the WebGL frame are projected with the same parallax factors as their corresponding constellation position.

VERIFICATION:
- `npx tsc --noEmit` passes
- User stars now have the same visual style as catalogue stars (WebGL-rendered body)
- Faculty colour rings and selection indicators still appear around user stars
- RAG pulse still works on user stars
- Orbiting satellites still visible
- The star body should look identical between user and catalogue stars
```

---

## Prompt 5 of 6 — Star Dive for Catalogue Stars (Phase 6)

```
You are working on apps/metis-web/app/page.tsx.

GOAL: Any catalogue star (not just user stars) can be dived into at high zoom. The star dive overlay shows the photorealistic shader surface for ANY star.

PREREQUISITE: Phases 2-5 (Prompts 1-4) must be applied first.

STEP 1 — Extend the star dive focus target to include catalogue stars

Find the star dive focus acquisition block in the render function (around line ~3742-3758). Currently it only searches user stars:

```ts
const userStarTargets = userStarsRef.current.flatMap((star) => {
  const proj = projectedUserStarRenderState.get(star.id);
  if (!proj) return [];
  return [{ id: star.id, screenX: proj.target.x, screenY: proj.target.y, brightness: star.size }];
});
const target = findStarDiveFocusTarget(userStarTargets, W, H);
```

AFTER this user star search, add a fallback to catalogue stars if no user star was found:

```ts
if (!target && landingStarSpatialHash) {
  const nearest = findClosestLandingStarHitTarget(landingStarSpatialHash, W / 2, H / 2);
  if (nearest) {
    const catStar = catalogueStarLookup.get(nearest.id);
    if (catStar) {
      const scale = getBackgroundCameraScale(backgroundCamera.zoomFactor);
      starDiveFocusedStarIdRef.current = nearest.id;
      starDiveFocusWorldPosRef.current = {
        x: backgroundCamera.x + (nearest.x - W / 2) / scale,
        y: backgroundCamera.y + (nearest.y - H / 2) / scale,
      };
      starDiveFocusProfileRef.current = catStar.profile;
    }
  }
}
```

Wrap the original target acquisition in an `if (target) { ... }` block so the catalogue fallback only runs when no user star is found.

STEP 2 — Show star name in the dive HUD

Find the star dive HUD JSX (around line 4690, the div that shows spectral class and temperature during dive). Add the star name at the top:

```tsx
{starDiveFocusedStarIdRef.current && (() => {
  const catStar = catalogueStarLookup.get(starDiveFocusedStarIdRef.current ?? "");
  if (!catStar) return null;
  return (
    <div style={{ fontSize: 18, fontWeight: 500, letterSpacing: "-0.01em", marginBottom: 4 }}>
      {catStar.name}
    </div>
  );
})()}
```

STEP 3 — Add "Add to Constellation" button in the dive HUD

Below the existing HUD stats, add a quick-add button for catalogue stars:

```tsx
{starDiveFocusedStarIdRef.current?.startsWith("cat-") && (
  <button
    type="button"
    className="metis-star-btn"
    style={{ marginTop: 8, pointerEvents: "auto", fontSize: 10, padding: "6px 14px" }}
    onClick={() => {
      const catStar = catalogueStarLookup.get(starDiveFocusedStarIdRef.current ?? "");
      if (catStar) promoteCatalogueStarToUser(catStar);
    }}
  >
    Add to Constellation
  </button>
)}
```

VERIFICATION:
- `npx tsc --noEmit` passes
- Zoom in past 200x on ANY star (user or catalogue): star dive activates, photorealistic surface appears
- Catalogue star dives show the star's name in the HUD
- "Add to Constellation" button visible during catalogue star dives
- User star dives still work exactly the same
```

---

## Prompt 6 of 6 — Visual Polish + Dead Code Cleanup

```
You are working on the Metis project at apps/metis-web.

GOAL: Improve the WebGL fragment shader for richer star visuals, and clean up dead code from the old tile system.

PREREQUISITE: All previous phases (Prompts 1-5) must be applied first.

STEP 1 — Replace the fragment shader

In apps/metis-web/components/home/landing-starfield-webgl.tsx, replace the entire fragmentShader string with:

```glsl
varying float vAddable;
varying float vBloom;
varying float vBrightness;
varying float vCoreRadius;
varying float vDiffraction;
varying float vTier;
varying float vTwinkle;
varying vec3 vAccentColor;
varying vec3 vCoreColor;
varying vec3 vHaloColor;

float safeSmoothstep(float edge0, float edge1, float x) {
  if (edge0 == edge1) return x < edge0 ? 0.0 : 1.0;
  return smoothstep(edge0, edge1, x);
}

void main() {
  vec2 uv = gl_PointCoord * 2.0 - 1.0;
  float dist = length(uv);
  if (dist > 1.0) discard;

  float tierBlend = vTier > 1.5 ? 1.0 : (vTier > 0.5 ? 0.6 : 0.0);

  // Softer halo with exponential decay
  float haloMask = exp(-dist * dist * (2.0 + (1.0 - tierBlend) * 1.5));

  // Gaussian core profile
  float coreWidth = max(0.08, vCoreRadius * 0.5);
  float coreMask = exp(-dist * dist / (2.0 * coreWidth * coreWidth));

  // Surface transition
  float surfaceMask = safeSmoothstep(0.82, max(0.08, vCoreRadius * 1.8), dist);

  // Chromatic aberration ring at the limb
  float chromaRing = safeSmoothstep(0.92, 0.72, dist) * safeSmoothstep(0.42, 0.62, dist);

  // Colour mixing
  vec3 surfaceColor = mix(vHaloColor, vCoreColor, 0.42);
  vec3 color = mix(vHaloColor, surfaceColor, surfaceMask);
  color = mix(color, vCoreColor, coreMask * 0.85);

  // Chromatic corona
  color += vAccentColor * chromaRing * (0.06 + tierBlend * 0.1);

  // Hot white core for bright stars
  float whiteCore = coreMask * coreMask * vBrightness * 0.35;
  color = mix(color, vec3(1.0), whiteCore);

  // Hero tier: swirl detail + limb darkening
  if (vTier > 1.5) {
    float angle = atan(uv.y, uv.x);
    float swirl = sin(angle * 3.0 + dist * 12.0) * 0.5 + 0.5;
    float swirlMask = safeSmoothstep(0.88, 0.14, dist) * swirl * 0.08 * vBloom;
    color += vAccentColor * swirlMask;
    float limb = 1.0 - pow(1.0 - dist * dist, 0.5);
    color *= 1.0 - limb * 0.15;
  }

  // 6-spike diffraction
  if (vDiffraction > 0.02) {
    float crossX = exp(-abs(uv.x) * 16.0);
    float crossY = exp(-abs(uv.y) * 16.0);
    float spike45a = exp(-(abs(uv.x - uv.y) * 0.707) * 22.0);
    float spike45b = exp(-(abs(uv.x + uv.y) * 0.707) * 22.0);
    float primarySpike = max(crossX, crossY);
    float secondarySpike = max(spike45a, spike45b) * 0.35;
    float spikeMask = (primarySpike + secondarySpike) * (1.0 - dist * 0.6);
    float spikeStrength = vDiffraction * (0.16 + tierBlend * 0.22);
    color += vAccentColor * spikeMask * spikeStrength;
  }

  // Addable tint
  if (vAddable > 0.5) {
    color = mix(color, vec3(0.95, 0.82, 0.55), 0.10);
  }

  // Alpha
  float alphaBase = (0.16 + vBrightness * 0.52) * vTwinkle;
  float alpha = haloMask * alphaBase + coreMask * 0.32 + chromaRing * 0.05;
  alpha = clamp(alpha * (0.88 + vBloom * 0.14), 0.0, 1.0);

  gl_FragColor = vec4(color * (0.84 + vBrightness * 0.36), alpha);
}
```

STEP 2 — Remove dead tile code from page.tsx

These are now dead code since the StarCatalogue replaced them. Remove:

1. `function nextDeterministicSeed(seed: number)` (line ~266)
2. `function createTileSeed(tileX, tileY, layer, index)` (line ~283)
3. `function sampleDeterministicRatio(seed: number)` (line ~308)
4. `function getWorldTileStars(tileCache, layer, tileX, tileY)` (lines ~325-388)
5. `const MAX_CACHED_WORLD_TILES = 4096;` (line ~135)
6. `const WORLD_STAR_COUNT_BY_LAYER = [4, 7, 10] as const;` (line ~136)
7. The `tileCache` variable inside the render effect: `const tileCache = new Map<string, WorldStarData[]>();` (line ~2056)

KEEP: BACKGROUND_TILE_SIZE, BACKGROUND_TILE_PADDING_PX, WORLD_STAR_REVEAL_STEPS (still used).

STEP 3 — Remove any now-unused imports

If any imports become unused after the dead code removal (e.g., specific tile-related types), remove them.

VERIFICATION:
- `npx tsc --noEmit` passes
- Stars look richer: chromatic corona ring visible on bright stars, sharper 6-spike diffraction, Gaussian core glow
- Hero-tier stars show subtle swirl detail and limb darkening
- No console errors
- The app builds cleanly with `npm run build`
```

---

## Quick Reference — Execution Checklist

| Prompt | Phase | Files Modified | Key Outcome |
|--------|-------|----------------|-------------|
| 1 | 2 | page.tsx | Catalogue stars feed the WebGL renderer |
| 2 | 3 | page.tsx | Every star is hoverable + clickable with observatory dialog |
| 3 | 4 | page.tsx, landing-starfield-webgl.tsx, landing-starfield-webgl.types.ts | Galaxy IS the stars at zoom-out |
| 4 | 5 | page.tsx | User stars + catalogue stars unified in WebGL |
| 5 | 6 | page.tsx | Star dive works on any catalogue star |
| 6 | Polish | page.tsx, landing-starfield-webgl.tsx | Richer shader + dead code removal |
