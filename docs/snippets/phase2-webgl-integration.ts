// ═══════════════════════════════════════════════════════════════════════════════
// PHASE 2: Wire StarCatalogue into the existing LandingStarfieldWebgl renderer
// ═══════════════════════════════════════════════════════════════════════════════
//
// The existing renderer already handles WebGL instanced points beautifully.
// We just need to replace the data source (WorldStarData tiles → CatalogueStar).
//
// STRATEGY: The existing pipeline is:
//   getWorldTileStars() → WorldStarData[] → project to screen → LandingWorldStarRenderState[]
//   → buildLandingStarRenderPlan() → LandingWebglStar[] → landingStarfieldFrameRef → WebGL
//
// We replace the first stage: instead of WorldStarData from tiles, we use CatalogueStar
// from the StarCatalogue, then feed them through the same projection + LOD pipeline.

// ──────────────────────────────────────────────────────────────────────────────
// STEP 2.1: Add imports and initialise the catalogue (top of page.tsx)
// ──────────────────────────────────────────────────────────────────────────────

// ADD these imports near the top of page.tsx (around line 93):
/*
import { StarCatalogue, DEFAULT_CATALOGUE_CONFIG } from "@/lib/star-catalogue";
import type { CatalogueStar } from "@/lib/star-catalogue";
*/

// ADD this inside the Home() component body (around line 905, near other refs):
/*
const starCatalogueRef = useRef<StarCatalogue | null>(null);

// Lazy-init the catalogue (only once)
if (!starCatalogueRef.current) {
  starCatalogueRef.current = new StarCatalogue(
    DEFAULT_CATALOGUE_CONFIG,
    generateStellarProfile,
  );
}
*/

// ──────────────────────────────────────────────────────────────────────────────
// STEP 2.2: Replace refreshVisibleStars to use StarCatalogue
// ──────────────────────────────────────────────────────────────────────────────

// REPLACE the function `refreshVisibleStars` (around line 2500-2540) with:
/*
function refreshVisibleStars(backgroundCamera: BackgroundCameraState) {
  const catalogue = starCatalogueRef.current;
  if (!catalogue) return;

  const worldBounds = getBackgroundViewportWorldBounds(
    W, H, backgroundCamera, BACKGROUND_TILE_PADDING_PX,
  );

  // Get catalogue stars in viewport
  const catalogueStars = catalogue.getVisibleStars(
    worldBounds.left,
    worldBounds.right,
    worldBounds.top,
    worldBounds.bottom,
    1, // buffer factor: 1 extra sector ring
  );

  // Convert CatalogueStar[] → WorldStarData[] for the existing projection pipeline
  const nextVisibleWorldStars: WorldStarData[] = [];
  for (const cat of catalogueStars) {
    // Map apparent magnitude (0=bright, 6.5=dim) → brightness (0-1) and baseSize
    const brightnessNorm = 1 - cat.apparentMagnitude / 6.5;
    const brightness = 0.12 + brightnessNorm * 0.72;
    const baseSize = 0.3 + brightnessNorm * 2.2;

    // Determine LOD reveal zoom: dimmer stars only appear at higher zoom
    const revealZoom = cat.apparentMagnitude < 2
      ? 1
      : cat.apparentMagnitude < 4
        ? WORLD_STAR_REVEAL_STEPS[Math.min(6, Math.floor(cat.apparentMagnitude * 2))] ?? 1
        : WORLD_STAR_REVEAL_STEPS[Math.min(WORLD_STAR_REVEAL_STEPS.length - 1, Math.floor(cat.apparentMagnitude * 3))] ?? 200;

    if (backgroundCamera.zoomFactor + 1e-6 < revealZoom) continue;

    // Use profile visual properties for twinkle/diffraction
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

  visibleWorldStars = nextVisibleWorldStars;

  // Evict distant sectors periodically (every ~60 frames)
  if (Math.random() < 0.016) {
    const centerSector = catalogue.worldToSector(backgroundCamera.x, backgroundCamera.y);
    catalogue.evictDistantSectors(centerSector.sx, centerSector.sy, 6);
  }

  // ... rest of the existing refreshVisibleStars continues from here:
  // the projection loop (visibleWorldStars.forEach...) remains UNCHANGED
}
*/

// ──────────────────────────────────────────────────────────────────────────────
// STEP 2.3: Keep the stellar profile cache fed from CatalogueStar
// ──────────────────────────────────────────────────────────────────────────────

// MODIFY getCachedStellarProfile to also check CatalogueStar.profile directly.
// This avoids regenerating profiles for catalogue stars (they already have them):
/*
// Add a map to cache CatalogueStar profiles by id
const catalogueStarProfileCache = new Map<string, StellarProfile>();

function getCachedStellarProfile(starId: string): StellarProfile {
  // Check catalogue cache first (pre-computed)
  const catProfile = catalogueStarProfileCache.get(starId);
  if (catProfile) return catProfile;

  // Fall back to existing generation
  const cachedProfile = landingStarProfileCacheRef.current.get(starId);
  if (cachedProfile) return cachedProfile;

  const nextProfile = generateStellarProfile(starId);
  landingStarProfileCacheRef.current.set(starId, nextProfile);
  return nextProfile;
}

// In refreshVisibleStars, after creating each WorldStarData, cache the profile:
// catalogueStarProfileCache.set(cat.id, cat.profile);
*/

// ──────────────────────────────────────────────────────────────────────────────
// STEP 2.4: Remove the old tile-based field star system
// ──────────────────────────────────────────────────────────────────────────────

// DELETE or comment out:
// - The `getWorldTileStars()` function (lines ~325-390)
// - The `createTileSeed()` function (lines ~283-297)
// - The `nextDeterministicSeed()` and `sampleDeterministicRatio()` functions
// - The `tileCache` ref and `MAX_CACHED_WORLD_TILES` constant
// - The `WORLD_STAR_COUNT_BY_LAYER` constant
//
// KEEP: WORLD_STAR_REVEAL_STEPS (still used for zoom gating)
// KEEP: BACKGROUND_TILE_SIZE (still used for world bounds calculation)
// KEEP: BACKGROUND_TILE_PADDING_PX (still used for viewport padding)

export {};
