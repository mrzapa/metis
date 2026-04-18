import { describe, expect, it } from "vitest";
import {
  createStellarPaletteFromTemperature,
  generateStellarProfile,
  getStellarBaseColor,
} from "../stellar-profile";

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
});
