import { describe, expect, it } from "vitest";
import {
  createStellarPaletteFromTemperature,
  formatLuminositySolar,
  formatSpectralClassLabel,
  formatTemperatureK,
  formatVisualArchetypeLabel,
  generateStellarProfile,
  getStellarBaseColor,
} from "../stellar-profile";
import type { StellarProfile } from "../types";

function expectRgbChannelRange(color: readonly number[]) {
  color.forEach((channel) => {
    expect(channel).toBeGreaterThanOrEqual(0);
    expect(channel).toBeLessThanOrEqual(255);
    expect(Number.isInteger(channel)).toBe(true);
  });
}

describe("generateStellarProfile", () => {
  it("is deterministic for the same numeric or string seed", () => {
    const numeric = generateStellarProfile(42);
    const stringy = generateStellarProfile("42");
    const repeated = generateStellarProfile(42);

    expect(numeric).toEqual(repeated);
    expect(numeric).toEqual(stringy);
  });

  it("produces varied but stable outputs for different seeds", () => {
    const first = generateStellarProfile("andromeda");
    const second = generateStellarProfile("pleiades");

    expect(first.seedHash).not.toBe(second.seedHash);
    expect(first).not.toEqual(second);
  });

  it("keeps profile values within sensible rendering ranges", () => {
    const seeds = [1, 7, 19, 42, 108, "m33", "vega", "rigel"];

    for (const seed of seeds) {
      const profile = generateStellarProfile(seed);

      expect(profile.seed).toBe(String(seed));
      expect(profile.temperatureK).toBeGreaterThanOrEqual(2);
      expect(profile.temperatureK).toBeLessThanOrEqual(2000000);
      expect(profile.luminositySolar).toBeGreaterThan(0);
      expect(profile.massSolar).toBeGreaterThan(0);
      expect(profile.radiusSolar).toBeGreaterThan(0);
      expect(profile.spectralClass).toBeTruthy();
      expect(profile.spectralFamily).toBeTruthy();
      expect(profile.palette.core.length).toBe(3);
      expect(profile.palette.surface.length).toBe(3);
      expect(profile.palette.halo.length).toBe(3);
      expect(profile.palette.accent.length).toBe(3);
      expect(profile.palette.rim.length).toBe(3);
      expectRgbChannelRange(profile.baseColor);
      expectRgbChannelRange(profile.palette.core);
      expectRgbChannelRange(profile.palette.surface);
      expectRgbChannelRange(profile.palette.halo);
      expectRgbChannelRange(profile.palette.accent);
      expectRgbChannelRange(profile.palette.rim);
      expect(profile.visual.coreRadiusFactor).toBeGreaterThan(0);
      expect(profile.visual.coreRadiusFactor).toBeLessThan(0.5);
      expect(profile.visual.haloRadiusFactor).toBeGreaterThan(profile.visual.coreRadiusFactor);
      expect(profile.visual.bloomFactor).toBeGreaterThan(0.4);
      expect(profile.visual.spriteHardness).toBeGreaterThan(0.3);
      expect(profile.visual.spriteHardness).toBeLessThanOrEqual(1);
      expect(profile.visual.twinkleSpeed).toBeGreaterThanOrEqual(0.00025);
      expect(profile.visual.twinkleSpeed).toBeLessThanOrEqual(0.0035);
      expect(profile.visual.twinklePhase).toBeGreaterThanOrEqual(0);
      expect(profile.visual.twinklePhase).toBeLessThanOrEqual(Math.PI * 2);
      expect(profile.visual.parallaxFactor).toBeGreaterThan(0);
      expect(profile.visual.parallaxFactor).toBeLessThan(0.03);
      expect(profile.visual.spikeCount).toBeGreaterThanOrEqual(0);
      expect(profile.visual.spikeCount).toBeLessThanOrEqual(6);
    }
  });

  it("exposes a reusable temperature-to-palette helper", () => {
    const palette = createStellarPaletteFromTemperature(5778);
    const baseColor = getStellarBaseColor(5778);

    expectRgbChannelRange(baseColor);
    expectRgbChannelRange(palette.core);
    expectRgbChannelRange(palette.surface);
    expectRgbChannelRange(palette.halo);
    expectRgbChannelRange(palette.accent);
    expectRgbChannelRange(palette.rim);
  });

  it("defaults visualArchetype to main_sequence when content type is omitted", () => {
    const profile = generateStellarProfile("atlas");
    expect(profile.visualArchetype).toBe("main_sequence");
  });

  it("sets visualArchetype from the provided content type", () => {
    expect(generateStellarProfile("atlas", { contentType: "podcast" }).visualArchetype).toBe(
      "pulsar",
    );
    expect(generateStellarProfile("atlas", { contentType: "archive" }).visualArchetype).toBe(
      "black_hole",
    );
    expect(generateStellarProfile("atlas", { contentType: "live_feed" }).visualArchetype).toBe(
      "comet",
    );
    expect(generateStellarProfile("atlas", { contentType: null }).visualArchetype).toBe(
      "main_sequence",
    );
  });

  it("keeps the rest of the profile deterministic regardless of content type", () => {
    const baseline = generateStellarProfile("atlas");
    const tagged = generateStellarProfile("atlas", { contentType: "video" });

    // Content type only affects visualArchetype; other fields come from the seed.
    expect({ ...tagged, visualArchetype: baseline.visualArchetype }).toEqual(baseline);
  });

  it("leaves annotations undefined — they are content-driven, not procedural", () => {
    const profile = generateStellarProfile("atlas");
    expect(profile.annotations).toBeUndefined();

    const tagged = generateStellarProfile("atlas", { contentType: "learning_route" });
    expect(tagged.annotations).toBeUndefined();
  });

  it("accepts an externally-supplied annotations field without mutating the seeded output", () => {
    const baseline = generateStellarProfile("atlas");
    const annotated: typeof baseline = {
      ...baseline,
      annotations: {
        halo: { strength: 0.7 },
        ring: { count: 2 },
      },
    };

    // Stripping annotations reproduces the untouched seeded profile.
    const rest = { ...annotated, annotations: undefined };
    delete (rest as { annotations?: unknown }).annotations;
    expect(rest).toEqual(baseline);
    expect(annotated.annotations?.halo?.strength).toBeCloseTo(0.7, 5);
    expect(annotated.annotations?.ring?.count).toBe(2);
  });
});

describe("Observatory identity-panel formatters (M02 Phase 7.1)", () => {
  describe("formatTemperatureK", () => {
    it("rounds to a whole Kelvin and thousands-separates", () => {
      expect(formatTemperatureK(5_778)).toBe("5,778");
      expect(formatTemperatureK(12_345.6)).toBe("12,346");
      expect(formatTemperatureK(900)).toBe("900");
    });

    it("returns an em dash for non-finite values", () => {
      expect(formatTemperatureK(Number.NaN)).toBe("—");
      expect(formatTemperatureK(Number.POSITIVE_INFINITY)).toBe("—");
    });
  });

  describe("formatLuminositySolar", () => {
    it("uses scientific notation past 10,000 L☉", () => {
      expect(formatLuminositySolar(250_000)).toMatch(/e\+/i);
      expect(formatLuminositySolar(15_000)).toMatch(/e\+/i);
    });

    it("fixes 100+ L☉ to whole numbers", () => {
      expect(formatLuminositySolar(340)).toBe("340");
      expect(formatLuminositySolar(100)).toBe("100");
    });

    it("keeps 10-99 L☉ at one decimal", () => {
      expect(formatLuminositySolar(12.345)).toBe("12.3");
      expect(formatLuminositySolar(99)).toBe("99.0");
    });

    it("keeps 0.01-9.99 L☉ at two decimals", () => {
      expect(formatLuminositySolar(1)).toBe("1.00");
      expect(formatLuminositySolar(0.04)).toBe("0.04");
    });

    it("uses scientific notation below 0.01 L☉", () => {
      expect(formatLuminositySolar(0.0001)).toMatch(/e-/i);
    });

    it("returns an em dash for non-positive or non-finite values", () => {
      expect(formatLuminositySolar(0)).toBe("—");
      expect(formatLuminositySolar(-5)).toBe("—");
      expect(formatLuminositySolar(Number.NaN)).toBe("—");
    });
  });

  describe("formatSpectralClassLabel", () => {
    it("joins family, subclass, and luminosity class into the classical compact form", () => {
      const profile = generateStellarProfile("vega");
      const label = formatSpectralClassLabel(profile);

      if (profile.spectralSubclass != null && profile.luminosityClass) {
        expect(label).toBe(`${profile.spectralFamily}${profile.spectralSubclass} ${profile.luminosityClass}`);
      } else if (profile.spectralSubclass != null) {
        expect(label).toBe(`${profile.spectralFamily}${profile.spectralSubclass}`);
      } else {
        expect(label).toContain(profile.spectralFamily);
      }
    });

    it("falls back to spectralClass when the parts are missing", () => {
      const profile: StellarProfile = {
        ...generateStellarProfile("rigel"),
        spectralFamily: "",
        spectralSubclass: null,
        luminosityClass: null,
        spectralClass: "O9Ia",
      };
      expect(formatSpectralClassLabel(profile)).toBe("O9Ia");
    });
  });

  describe("formatVisualArchetypeLabel", () => {
    it("returns pretty labels for known archetypes", () => {
      expect(formatVisualArchetypeLabel("main_sequence")).toBe("Main sequence");
      expect(formatVisualArchetypeLabel("wolf_rayet")).toBe("Wolf-Rayet");
      expect(formatVisualArchetypeLabel("black_hole")).toBe("Black hole");
      expect(formatVisualArchetypeLabel("pulsar")).toBe("Pulsar");
    });

    it("falls back to a spaced snake_case → words conversion for unknown archetypes", () => {
      expect(formatVisualArchetypeLabel("something_new")).toBe("something new");
    });

    it("returns the default label when the archetype is nullish", () => {
      expect(formatVisualArchetypeLabel(null)).toBe("Main sequence");
      expect(formatVisualArchetypeLabel(undefined)).toBe("Main sequence");
      expect(formatVisualArchetypeLabel("")).toBe("Main sequence");
    });
  });
});
