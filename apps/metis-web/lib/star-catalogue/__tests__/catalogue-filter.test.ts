import { describe, expect, it } from "vitest";

import {
  CATALOGUE_FILTER_DEFAULT,
  CATALOGUE_FILTER_DIM_BRIGHTNESS,
  CATALOGUE_FILTER_MAX_MAGNITUDE,
  CATALOGUE_SPECTRAL_FAMILIES,
  decodeFilterFromHash,
  encodeFilterToHash,
  isCatalogueFilterActive,
  matchesCatalogueFilter,
  mergeFilterIntoHash,
} from "../catalogue-filter";
import type { CatalogueFilterState } from "../catalogue-filter";

function star(family: string, magnitude: number) {
  return {
    profile: { spectralFamily: family },
    apparentMagnitude: magnitude,
  };
}

describe("catalogue-filter", () => {
  describe("CATALOGUE_FILTER_DEFAULT", () => {
    it("is empty families + max magnitude (everything passes)", () => {
      expect(CATALOGUE_FILTER_DEFAULT.families.size).toBe(0);
      expect(CATALOGUE_FILTER_DEFAULT.maxMagnitude).toBe(CATALOGUE_FILTER_MAX_MAGNITUDE);
    });
  });

  describe("isCatalogueFilterActive", () => {
    it("returns false for the default state", () => {
      expect(isCatalogueFilterActive(CATALOGUE_FILTER_DEFAULT)).toBe(false);
    });

    it("returns true when any family is selected", () => {
      const state: CatalogueFilterState = {
        families: new Set(["G"]),
        maxMagnitude: CATALOGUE_FILTER_MAX_MAGNITUDE,
      };
      expect(isCatalogueFilterActive(state)).toBe(true);
    });

    it("returns true when magnitude is restricted below the max", () => {
      const state: CatalogueFilterState = {
        families: new Set(),
        maxMagnitude: 4.0,
      };
      expect(isCatalogueFilterActive(state)).toBe(true);
    });
  });

  describe("matchesCatalogueFilter", () => {
    it("default state matches everything", () => {
      expect(matchesCatalogueFilter(star("M", 6.0), CATALOGUE_FILTER_DEFAULT)).toBe(true);
      expect(matchesCatalogueFilter(star("O", 0.5), CATALOGUE_FILTER_DEFAULT)).toBe(true);
    });

    it("family filter matches only stars in the selected family set", () => {
      const state: CatalogueFilterState = {
        families: new Set(["G", "K"]),
        maxMagnitude: CATALOGUE_FILTER_MAX_MAGNITUDE,
      };
      expect(matchesCatalogueFilter(star("G", 5), state)).toBe(true);
      expect(matchesCatalogueFilter(star("K", 5), state)).toBe(true);
      expect(matchesCatalogueFilter(star("M", 5), state)).toBe(false);
      expect(matchesCatalogueFilter(star("O", 5), state)).toBe(false);
    });

    it("magnitude filter passes stars BRIGHTER than (numerically less than or equal to) max", () => {
      const state: CatalogueFilterState = {
        families: new Set(),
        maxMagnitude: 3.0,
      };
      expect(matchesCatalogueFilter(star("G", 2.5), state)).toBe(true);
      expect(matchesCatalogueFilter(star("G", 3.0), state)).toBe(true);
      expect(matchesCatalogueFilter(star("G", 3.5), state)).toBe(false);
    });

    it("combines family + magnitude as AND (both must pass)", () => {
      const state: CatalogueFilterState = {
        families: new Set(["G"]),
        maxMagnitude: 3.0,
      };
      expect(matchesCatalogueFilter(star("G", 2.5), state)).toBe(true);
      expect(matchesCatalogueFilter(star("G", 4.0), state)).toBe(false);
      expect(matchesCatalogueFilter(star("M", 2.5), state)).toBe(false);
    });

    it("treats empty spectralFamily strictly (does not pass family filter)", () => {
      const state: CatalogueFilterState = {
        families: new Set(["G"]),
        maxMagnitude: CATALOGUE_FILTER_MAX_MAGNITUDE,
      };
      expect(matchesCatalogueFilter(star("", 2.5), state)).toBe(false);
    });
  });

  describe("CATALOGUE_FILTER_DIM_BRIGHTNESS", () => {
    it("is a small constant strictly between 0 and 1", () => {
      expect(CATALOGUE_FILTER_DIM_BRIGHTNESS).toBeGreaterThan(0);
      expect(CATALOGUE_FILTER_DIM_BRIGHTNESS).toBeLessThan(1);
    });
  });

  describe("encodeFilterToHash / decodeFilterFromHash", () => {
    it("default state encodes to empty string", () => {
      expect(encodeFilterToHash(CATALOGUE_FILTER_DEFAULT)).toBe("");
    });

    it("encodes families as comma-joined uppercase letters", () => {
      const state: CatalogueFilterState = {
        families: new Set(["G", "B", "A"]),
        maxMagnitude: CATALOGUE_FILTER_MAX_MAGNITUDE,
      };
      const encoded = encodeFilterToHash(state);
      // Order is canonical (per CATALOGUE_SPECTRAL_FAMILIES order), so result is deterministic.
      expect(encoded).toBe("fams=B,A,G");
    });

    it("encodes a magnitude restriction", () => {
      const state: CatalogueFilterState = {
        families: new Set(),
        maxMagnitude: 4.5,
      };
      expect(encodeFilterToHash(state)).toBe("mag=4.5");
    });

    it("encodes both family + magnitude restrictions joined with &", () => {
      const state: CatalogueFilterState = {
        families: new Set(["G"]),
        maxMagnitude: 4.0,
      };
      expect(encodeFilterToHash(state)).toBe("fams=G&mag=4");
    });

    it("decodes empty/null hash to default state", () => {
      expect(decodeFilterFromHash("")).toEqual(CATALOGUE_FILTER_DEFAULT);
      expect(decodeFilterFromHash("#")).toEqual(CATALOGUE_FILTER_DEFAULT);
    });

    it("decodes families and magnitude", () => {
      const state = decodeFilterFromHash("fams=G,K&mag=4.5");
      expect([...state.families].sort()).toEqual(["G", "K"]);
      expect(state.maxMagnitude).toBe(4.5);
    });

    it("tolerates leading hash and #!", () => {
      const a = decodeFilterFromHash("#fams=G");
      const b = decodeFilterFromHash("#!fams=G");
      expect([...a.families]).toEqual(["G"]);
      expect([...b.families]).toEqual(["G"]);
    });

    it("ignores unknown spectral families silently", () => {
      const state = decodeFilterFromHash("fams=G,Z,XX,K");
      expect([...state.families].sort()).toEqual(["G", "K"]);
    });

    it("clamps malformed magnitude to default and ignores instead of throwing", () => {
      const state = decodeFilterFromHash("mag=banana");
      expect(state.maxMagnitude).toBe(CATALOGUE_FILTER_MAX_MAGNITUDE);
    });

    it("clamps out-of-range magnitudes to [0, max]", () => {
      const tooHigh = decodeFilterFromHash("mag=99");
      expect(tooHigh.maxMagnitude).toBe(CATALOGUE_FILTER_MAX_MAGNITUDE);
      const negative = decodeFilterFromHash("mag=-3");
      expect(negative.maxMagnitude).toBe(0);
    });

    it("encode-then-decode is a round trip for non-default states", () => {
      const state: CatalogueFilterState = {
        families: new Set(["O", "B", "M"]),
        maxMagnitude: 5.5,
      };
      const decoded = decodeFilterFromHash(encodeFilterToHash(state));
      expect([...decoded.families].sort()).toEqual(["B", "M", "O"]);
      expect(decoded.maxMagnitude).toBe(5.5);
    });
  });

  describe("CATALOGUE_SPECTRAL_FAMILIES", () => {
    it("is exactly O B A F G K M in classical hot-to-cool order", () => {
      expect(CATALOGUE_SPECTRAL_FAMILIES).toEqual(["O", "B", "A", "F", "G", "K", "M"]);
    });
  });

  describe("mergeFilterIntoHash", () => {
    it("returns empty string for empty hash + default state", () => {
      expect(mergeFilterIntoHash("", CATALOGUE_FILTER_DEFAULT)).toBe("");
      expect(mergeFilterIntoHash("#", CATALOGUE_FILTER_DEFAULT)).toBe("");
    });

    it("encodes filter into empty hash when state is active", () => {
      const state: CatalogueFilterState = {
        families: new Set(["G"]),
        maxMagnitude: 4.5,
      };
      expect(mergeFilterIntoHash("", state)).toBe("fams=G&mag=4.5");
    });

    it("preserves an unrelated anchor when filter is at default state", () => {
      expect(mergeFilterIntoHash("#build-map", CATALOGUE_FILTER_DEFAULT)).toBe("build-map");
    });

    it("preserves an unrelated anchor when filter is active", () => {
      const state: CatalogueFilterState = {
        families: new Set(["G"]),
        maxMagnitude: CATALOGUE_FILTER_MAX_MAGNITUDE,
      };
      expect(mergeFilterIntoHash("#build-map", state)).toBe("build-map&fams=G");
    });

    it("replaces existing fams= without duplicating it", () => {
      const state: CatalogueFilterState = {
        families: new Set(["K"]),
        maxMagnitude: CATALOGUE_FILTER_MAX_MAGNITUDE,
      };
      expect(mergeFilterIntoHash("fams=G", state)).toBe("fams=K");
    });

    it("replaces existing mag= without duplicating it", () => {
      const state: CatalogueFilterState = {
        families: new Set(),
        maxMagnitude: 2.5,
      };
      expect(mergeFilterIntoHash("mag=5.0", state)).toBe("mag=2.5");
    });

    it("preserves anchor + replaces existing filter when active state changes", () => {
      const state: CatalogueFilterState = {
        families: new Set(["K"]),
        maxMagnitude: 3.0,
      };
      expect(mergeFilterIntoHash("#build-map&fams=G&mag=5.0", state)).toBe(
        "build-map&fams=K&mag=3",
      );
    });

    it("strips the filter portion when state returns to default, keeps anchor", () => {
      expect(
        mergeFilterIntoHash("#build-map&fams=G&mag=5.0", CATALOGUE_FILTER_DEFAULT),
      ).toBe("build-map");
    });

    it("returns just the encoded filter when there are no other segments", () => {
      const state: CatalogueFilterState = {
        families: new Set(["G", "K"]),
        maxMagnitude: 4,
      };
      expect(mergeFilterIntoHash("fams=O&mag=2", state)).toBe("fams=G,K&mag=4");
    });

    it("tolerates leading # and #!", () => {
      const state: CatalogueFilterState = {
        families: new Set(["G"]),
        maxMagnitude: CATALOGUE_FILTER_MAX_MAGNITUDE,
      };
      expect(mergeFilterIntoHash("#!build-map", state)).toBe("build-map&fams=G");
    });

    it("preserves multiple unrelated segments", () => {
      const state: CatalogueFilterState = {
        families: new Set(["G"]),
        maxMagnitude: CATALOGUE_FILTER_MAX_MAGNITUDE,
      };
      expect(mergeFilterIntoHash("ref=hn&campaign=launch", state)).toBe(
        "ref=hn&campaign=launch&fams=G",
      );
    });

    it("does not strip anchor-only fragment when default state replaces no-op", () => {
      // No prior filter, default state, anchor preserved as-is.
      expect(mergeFilterIntoHash("#section", CATALOGUE_FILTER_DEFAULT)).toBe("section");
    });
  });
});
