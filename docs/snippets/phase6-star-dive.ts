// ═══════════════════════════════════════════════════════════════════════════════
// PHASE 6: Star Dive Integration — Any star can be dived into
// ═══════════════════════════════════════════════════════════════════════════════
//
// The existing StarDiveOverlay already accepts a StellarProfile and renders
// a photorealistic star surface. We just need to allow catalogue stars to
// trigger it, not just user stars.

// ──────────────────────────────────────────────────────────────────────────────
// STEP 6.1: Modify findStarDiveFocusTarget to include catalogue stars
// ──────────────────────────────────────────────────────────────────────────────

// The existing findStarDiveFocusTarget in constellation-home.ts finds the
// closest projected star to screen centre. MODIFY it to also search
// LandingWorldStarRenderState (which now contains catalogue stars):

/*
// In the star dive focus calculation (around line 3780-3810 in page.tsx):
// After the existing user star focus check:

// Check catalogue stars for dive target
if (!focusedStarId && starDiveFocusStrength > 0) {
  // Find the closest catalogue star to screen centre
  if (landingStarSpatialHash) {
    const centreStar = findClosestLandingStarHitTarget(
      landingStarSpatialHash,
      W / 2,
      H / 2,
      { queryPaddingPx: 100 },
    );
    if (centreStar) {
      focusedStarId = centreStar.id;
      const catStar = catalogueStarLookup.get(centreStar.id);
      if (catStar) {
        starDiveFocusProfileRef.current = catStar.profile;
      }
    }
  }
}
*/

// ──────────────────────────────────────────────────────────────────────────────
// STEP 6.2: Update the StarDiveOverlay view ref with catalogue star data
// ──────────────────────────────────────────────────────────────────────────────

// The existing code around line 3790-3830 sets starDiveOverlayViewRef.current
// based on the focused user star. Extend to handle catalogue stars:

/*
// In the render loop, after computing starDiveFocusStrength:
const focusStrength = getStarDiveFocusStrength(backgroundZoomRef.current);
starDiveFocusStrengthRef.current = focusStrength;

if (focusStrength > 0.01) {
  let focusProfile: StellarProfile | null = null;
  let focusScreenX = W / 2;
  let focusScreenY = H / 2;

  // Check user stars first
  const focusedUserStar = /* existing user star focus logic */;
  if (focusedUserStar) {
    focusProfile = getCachedStellarProfile(focusedUserStar.id);
    focusScreenX = focusedUserStar.target.x;
    focusScreenY = focusedUserStar.target.y;
  } else if (landingStarSpatialHash) {
    // Fall back to nearest catalogue star
    const nearest = findClosestLandingStarHitTarget(
      landingStarSpatialHash, W / 2, H / 2, { queryPaddingPx: 120 },
    );
    if (nearest) {
      const catStar = catalogueStarLookup.get(nearest.id);
      focusProfile = catStar?.profile ?? getCachedStellarProfile(nearest.id);
      focusScreenX = nearest.x;
      focusScreenY = nearest.y;
    }
  }

  if (focusProfile) {
    starDiveOverlayViewRef.current = {
      screenX: focusScreenX,
      screenY: focusScreenY,
      focusStrength,
      profile: focusProfile,
    };
    starDiveFocusProfileRef.current = focusProfile;
  }
} else {
  starDiveOverlayViewRef.current = null;
}
*/

// ──────────────────────────────────────────────────────────────────────────────
// STEP 6.3: Show the star HUD with catalogue star info during dive
// ──────────────────────────────────────────────────────────────────────────────

// The existing HUD (around line 4690) shows spectral class, temperature, etc.
// Extend it to also show the star's name:

/*
{starDiveFocusStrength > 0.5 && starDiveFocusProfileRef.current && (
  <div
    className="metis-star-dive-hud"
    style={{
      position: "fixed",
      bottom: 80,
      left: "50%",
      transform: "translateX(-50%)",
      zIndex: 20,
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      gap: 4,
      color: "rgba(255,255,255,0.9)",
      fontFamily: '"Space Grotesk", sans-serif',
      fontSize: 13,
      fontWeight: 400,
      letterSpacing: "0.02em",
      textShadow: "0 1px 8px rgba(0,0,0,0.7)",
      opacity: Math.min(1, (starDiveFocusStrength - 0.5) * 4),
      transition: "opacity 0.3s",
      pointerEvents: "none",
    }}
    aria-live="polite"
  >
    {/* NEW: Show catalogue star name if available */}
    {starDiveFocusedStarIdRef.current && catalogueStarLookup.get(starDiveFocusedStarIdRef.current) && (
      <div style={{ fontSize: 18, fontWeight: 500, letterSpacing: "-0.01em" }}>
        {catalogueStarLookup.get(starDiveFocusedStarIdRef.current)!.name}
      </div>
    )}
    <div style={{ fontSize: 15, fontWeight: 500 }}>
      {starDiveFocusProfileRef.current.spectralClass} — {starDiveFocusProfileRef.current.stellarType.replace(/_/g, " ")}
    </div>
    <div style={{ opacity: 0.7, fontSize: 11 }}>
      {Math.round(starDiveFocusProfileRef.current.temperatureK).toLocaleString()} K
      {" · "}
      {starDiveFocusProfileRef.current.luminositySolar.toFixed(1)} L☉
      {" · "}
      {starDiveFocusProfileRef.current.radiusSolar.toFixed(2)} R☉
    </div>
    {/* NEW: "Add to Constellation" quick action during dive */}
    {starDiveFocusedStarIdRef.current?.startsWith("cat-") && (
      <button
        type="button"
        className="metis-star-btn"
        style={{
          marginTop: 8,
          pointerEvents: "auto",
          fontSize: 10,
          padding: "6px 14px",
        }}
        onClick={() => {
          const catStar = catalogueStarLookup.get(starDiveFocusedStarIdRef.current!);
          if (catStar) promoteCatalogueStarToUser(catStar);
        }}
      >
        Add to Constellation
      </button>
    )}
    <div style={{ opacity: 0.45, fontSize: 10, marginTop: 2 }}>
      Press Esc to exit
    </div>
  </div>
)}
*/

export {};
