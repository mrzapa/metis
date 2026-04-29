"use client";

import { useEffect, useState } from "react";
import {
  CONSTELLATION_FACULTIES,
  FACULTY_PALETTE,
  type ConstellationFacultyMetadata,
} from "@/lib/constellation-home";
import { fetchForgeTechniques, type ForgePillar, type ForgeTechnique } from "@/lib/api";

// M14 Phase 2b — canvas-integrated technique stars.
//
// Each enabled Forge technique becomes a real star in the home-page
// constellation, positioned in the Skills faculty sector. The star
// flows through the same projection/camera pipeline as user stars so
// it pans, zooms, and parallaxes alongside the rest of the
// constellation. Clicks deep-link to `/forge#<technique-id>` (handled
// in `app/page.tsx`); the existing star-observatory dialog is not
// hijacked.
//
// Layout: a small ring around the Skills anchor, with a phase offset
// chosen so the first star does not collide with the leading shape
// star of the Skills constellation glyph.

const SKILLS_FACULTY: ConstellationFacultyMetadata | undefined =
  CONSTELLATION_FACULTIES.find((f) => f.id === "skills");

// Ring radius (in normalised constellation coords) around the Skills
// anchor. 0.075 keeps the cluster tucked near the faculty without
// overlapping the constellation glyph.
export const FORGE_STAR_RING_RADIUS = 0.075;
// Twist the ring so the first star sits at ~"8 o'clock" relative to
// the Skills anchor, leaving the constellation glyph undisturbed.
export const FORGE_STAR_RING_PHASE = -Math.PI / 3;
// Each technique star's `size` value flows through
// `buildProjectedUserStarHitTarget` (hit radius ≈ size × 10 + 8) and
// `drawForgeStars` (visual halo). 1.0 matches typical user-star size
// without being so big that the cluster reads as user content.
export const FORGE_STAR_SIZE = 1.0;

export interface ForgeStar {
  id: string;
  // Normalised constellation coords, [0, 1] in both axes.
  x: number;
  y: number;
  size: number;
  name: string;
  pillar: ForgePillar;
  paletteRgb: [number, number, number];
}

/** Map a pillar onto a constellation palette tone. Companion stars
 *  inherit the Skills faculty colour (emerald) so the cluster reads
 *  as ""skills"". Cortex stars borrow the reasoning palette so the
 *  cluster has a visible pillar contrast. Cosmos / cross-cutting
 *  fall back to the perception sky / a neutral tone. */
export function pillarStarPalette(pillar: ForgePillar): [number, number, number] {
  switch (pillar) {
    case "companion":
      return FACULTY_PALETTE.skills;
    case "cortex":
      return FACULTY_PALETTE.reasoning;
    case "cosmos":
      return FACULTY_PALETTE.perception;
    case "cross-cutting":
    default:
      return [208, 216, 232];
  }
}

/** Return one positioned ForgeStar per enabled technique, fanned
 *  evenly around the Skills faculty anchor. Order is the registry
 *  order (the API preserves it), so the first enabled technique
 *  always lands at the same ring slot — no surprise reshuffles when
 *  a single toggle flips. */
export function forgeStarPositions(active: ForgeTechnique[]): ForgeStar[] {
  if (!SKILLS_FACULTY || active.length === 0) return [];
  const anchorX = SKILLS_FACULTY.x;
  const anchorY = SKILLS_FACULTY.y;
  return active.map((technique, index) => {
    const theta = FORGE_STAR_RING_PHASE + (index / active.length) * Math.PI * 2;
    const x = anchorX + Math.cos(theta) * FORGE_STAR_RING_RADIUS;
    const y = anchorY + Math.sin(theta) * FORGE_STAR_RING_RADIUS;
    return {
      id: technique.id,
      x,
      y,
      size: FORGE_STAR_SIZE,
      name: technique.name,
      pillar: technique.pillar,
      paletteRgb: pillarStarPalette(technique.pillar),
    };
  });
}

interface UseForgeStarsOptions {
  // Test seam — when set, the hook uses this list directly instead of
  // calling the API. Production callers leave it undefined.
  override?: ForgeTechnique[];
}

/** Subscribe to the active-Forge-techniques stream as positioned
 *  constellation stars. Re-fetches on visibility change so the home
 *  page reflects toggles made elsewhere in the app (e.g. /settings
 *  or the Forge gallery itself). On error, returns an empty array
 *  rather than crashing the constellation render. */
export function useForgeStars(options: UseForgeStarsOptions = {}): ForgeStar[] {
  const [stars, setStars] = useState<ForgeStar[]>([]);

  useEffect(() => {
    if (options.override !== undefined) {
      const active = options.override.filter((t) => t.enabled);
      setStars(forgeStarPositions(active));
      return;
    }

    let cancelled = false;
    async function refresh() {
      try {
        const payload = await fetchForgeTechniques();
        if (cancelled) return;
        const active = payload.techniques.filter((t) => t.enabled);
        setStars(forgeStarPositions(active));
      } catch {
        if (cancelled) return;
        // Forge stars are decorative on the home page — failing the
        // fetch should not blow up the constellation. Drop to empty
        // state and let the next visibility-change retry.
        setStars([]);
      }
    }

    void refresh();

    const onVisibilityChange = () => {
      if (typeof document !== "undefined" && document.visibilityState === "visible") {
        void refresh();
      }
    };
    if (typeof document !== "undefined") {
      document.addEventListener("visibilitychange", onVisibilityChange);
    }

    return () => {
      cancelled = true;
      if (typeof document !== "undefined") {
        document.removeEventListener("visibilitychange", onVisibilityChange);
      }
    };
  }, [options.override]);

  return stars;
}
