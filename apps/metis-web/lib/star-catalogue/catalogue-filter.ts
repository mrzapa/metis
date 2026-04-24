/**
 * M12 Phase 3 — Catalogue filter state, predicate, and URL-hash codec.
 *
 * Pure helpers consumed by the `CatalogueFilterPanel` component, the render
 * loop in `app/page.tsx`, and the URL persistence layer. State is transient
 * view state — kept in URL hash only, never written to settings.
 */

export const CATALOGUE_SPECTRAL_FAMILIES = [
  "O",
  "B",
  "A",
  "F",
  "G",
  "K",
  "M",
] as const;

export type CatalogueSpectralFamily = (typeof CATALOGUE_SPECTRAL_FAMILIES)[number];

const SPECTRAL_FAMILY_SET = new Set<string>(CATALOGUE_SPECTRAL_FAMILIES);

/**
 * Apparent-magnitude ceiling exposed by the slider. Aligned with the
 * generation cap in `StarCatalogue.generateSector` (clamps mag to 6.5).
 */
export const CATALOGUE_FILTER_MAX_MAGNITUDE = 6.5;

/**
 * Brightness multiplier applied to stars that fail the active filter.
 * Phase 3 dims rather than hides — galactic structure stays visible per
 * the plan doc's "dim, not hide" contract.
 */
export const CATALOGUE_FILTER_DIM_BRIGHTNESS = 0.2;

export interface CatalogueFilterState {
  families: Set<CatalogueSpectralFamily>;
  maxMagnitude: number;
}

export const CATALOGUE_FILTER_DEFAULT: CatalogueFilterState = {
  families: new Set(),
  maxMagnitude: CATALOGUE_FILTER_MAX_MAGNITUDE,
};

export function isCatalogueFilterActive(state: CatalogueFilterState): boolean {
  if (state.families.size > 0) return true;
  if (state.maxMagnitude < CATALOGUE_FILTER_MAX_MAGNITUDE) return true;
  return false;
}

export interface FilterableStar {
  profile: { spectralFamily: string };
  apparentMagnitude: number;
}

export function matchesCatalogueFilter(
  star: FilterableStar,
  state: CatalogueFilterState,
): boolean {
  if (state.families.size > 0) {
    const family = star.profile.spectralFamily;
    if (!family) return false;
    if (!state.families.has(family as CatalogueSpectralFamily)) return false;
  }
  if (star.apparentMagnitude > state.maxMagnitude) return false;
  return true;
}

function stripHashPrefix(raw: string): string {
  let s = raw;
  if (s.startsWith("#")) s = s.slice(1);
  if (s.startsWith("!")) s = s.slice(1);
  return s;
}

function clampMagnitude(value: number): number {
  if (!Number.isFinite(value)) return CATALOGUE_FILTER_MAX_MAGNITUDE;
  if (value < 0) return 0;
  if (value > CATALOGUE_FILTER_MAX_MAGNITUDE) return CATALOGUE_FILTER_MAX_MAGNITUDE;
  return value;
}

function formatMagnitude(value: number): string {
  // Trim trailing zeros — `3` is friendlier than `3.0` in a URL.
  return Number.parseFloat(value.toFixed(2)).toString();
}

export function encodeFilterToHash(state: CatalogueFilterState): string {
  const parts: string[] = [];

  if (state.families.size > 0) {
    const ordered = CATALOGUE_SPECTRAL_FAMILIES.filter((f) => state.families.has(f));
    parts.push(`fams=${ordered.join(",")}`);
  }

  if (state.maxMagnitude < CATALOGUE_FILTER_MAX_MAGNITUDE) {
    parts.push(`mag=${formatMagnitude(state.maxMagnitude)}`);
  }

  return parts.join("&");
}

export function decodeFilterFromHash(rawHash: string): CatalogueFilterState {
  const stripped = stripHashPrefix(rawHash);
  if (stripped.length === 0) {
    return {
      families: new Set(),
      maxMagnitude: CATALOGUE_FILTER_MAX_MAGNITUDE,
    };
  }

  const params = new URLSearchParams(stripped);
  const families = new Set<CatalogueSpectralFamily>();
  const famsRaw = params.get("fams");
  if (famsRaw) {
    for (const candidate of famsRaw.split(",")) {
      const trimmed = candidate.trim().toUpperCase();
      if (SPECTRAL_FAMILY_SET.has(trimmed)) {
        families.add(trimmed as CatalogueSpectralFamily);
      }
    }
  }

  let maxMagnitude = CATALOGUE_FILTER_MAX_MAGNITUDE;
  const magRaw = params.get("mag");
  if (magRaw !== null) {
    const parsed = Number.parseFloat(magRaw);
    maxMagnitude = clampMagnitude(parsed);
  }

  return { families, maxMagnitude };
}
