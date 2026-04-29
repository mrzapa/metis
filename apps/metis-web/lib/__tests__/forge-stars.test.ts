import { afterEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

import {
  FORGE_STAR_RING_PHASE,
  FORGE_STAR_RING_RADIUS,
  FORGE_STAR_SIZE,
  forgeStarPositions,
  pillarStarPalette,
  useForgeStars,
} from "../forge-stars";
import { CONSTELLATION_FACULTIES, FACULTY_PALETTE } from "../constellation-home";
import type { ForgeTechnique, ForgeTechniquesResponse } from "../api";

const SKILLS = CONSTELLATION_FACULTIES.find((f) => f.id === "skills");
if (!SKILLS) throw new Error("Skills faculty missing from CONSTELLATION_FACULTIES");

// Hoisted mock state — setting `mockState.fetcher` rebinds what
// `fetchForgeTechniques` does for the next call. `vi.mock` runs at
// module load before this top-level code, so the factory cannot
// close over a non-hoisted variable directly.
const mockState = vi.hoisted(() => ({
  fetcher: null as
    | (() => Promise<ForgeTechniquesResponse>)
    | null,
}));

vi.mock("../api", async () => {
  const actual = await vi.importActual<typeof import("../api")>("../api");
  return {
    ...actual,
    fetchForgeTechniques: () => {
      if (mockState.fetcher === null) {
        return Promise.resolve({ techniques: [], phase: 2 });
      }
      return mockState.fetcher();
    },
  };
});

afterEach(() => {
  mockState.fetcher = null;
});

function makeTechnique(id: string, overrides: Partial<ForgeTechnique> = {}): ForgeTechnique {
  return {
    id,
    name: id,
    description: `${id} description`,
    pillar: "cortex",
    enabled: true,
    setting_keys: [],
    engine_symbols: [],
    recent_uses: [],
    ...overrides,
  };
}

describe("forgeStarPositions", () => {
  it("returns nothing when there are no enabled techniques", () => {
    expect(forgeStarPositions([])).toEqual([]);
  });

  it("places one star at the seeded angle around the Skills anchor", () => {
    const [star] = forgeStarPositions([makeTechnique("reranker")]);
    expect(star).toBeDefined();
    expect(star.id).toBe("reranker");
    expect(star.size).toBe(FORGE_STAR_SIZE);
    const expectedX = SKILLS.x + Math.cos(FORGE_STAR_RING_PHASE) * FORGE_STAR_RING_RADIUS;
    const expectedY = SKILLS.y + Math.sin(FORGE_STAR_RING_PHASE) * FORGE_STAR_RING_RADIUS;
    expect(star.x).toBeCloseTo(expectedX, 6);
    expect(star.y).toBeCloseTo(expectedY, 6);
  });

  it("fans multiple stars evenly around the anchor with stable per-id slots", () => {
    const techniques = [
      makeTechnique("a"),
      makeTechnique("b"),
      makeTechnique("c"),
      makeTechnique("d"),
    ];
    const stars = forgeStarPositions(techniques);
    expect(stars).toHaveLength(4);
    const angles = stars.map((star) => Math.atan2(star.y - SKILLS.y, star.x - SKILLS.x));
    const diffs = angles.slice(1).map((angle, i) => normaliseAngle(angle - angles[i]));
    diffs.forEach((diff) => expect(diff).toBeCloseTo(Math.PI / 2, 5));
  });

  it("propagates each technique's pillar onto its star palette", () => {
    const stars = forgeStarPositions([
      makeTechnique("c", { pillar: "cortex" }),
      makeTechnique("p", { pillar: "companion" }),
    ]);
    expect(stars[0].paletteRgb).toEqual(FACULTY_PALETTE.reasoning);
    expect(stars[1].paletteRgb).toEqual(FACULTY_PALETTE.skills);
  });
});

describe("pillarStarPalette", () => {
  it("returns the skills tone for companion techniques", () => {
    expect(pillarStarPalette("companion")).toEqual(FACULTY_PALETTE.skills);
  });

  it("returns the reasoning tone for cortex techniques", () => {
    expect(pillarStarPalette("cortex")).toEqual(FACULTY_PALETTE.reasoning);
  });

  it("returns a neutral palette for cross-cutting techniques", () => {
    expect(pillarStarPalette("cross-cutting")).toEqual([208, 216, 232]);
  });
});

describe("useForgeStars stale-response guard", () => {
  it("ignores an older fetch that resolves after a newer one", async () => {
    // Two pending promises: the FIRST one resolves *late* with
    // ""old"" data, the SECOND one resolves *first* with ""new"" data.
    // The hook must end with the new data because the old payload's
    // request token is stale by the time it lands.
    let resolveFirst: ((value: ForgeTechniquesResponse) => void) | null = null;
    let resolveSecond: ((value: ForgeTechniquesResponse) => void) | null = null;
    const oldPayload: ForgeTechniquesResponse = {
      phase: 2,
      techniques: [makeTechnique("stale-only", { pillar: "cortex" })],
    };
    const newPayload: ForgeTechniquesResponse = {
      phase: 2,
      techniques: [
        makeTechnique("fresh-a", { pillar: "cortex" }),
        makeTechnique("fresh-b", { pillar: "companion" }),
      ],
    };

    let callIndex = 0;
    mockState.fetcher = () => {
      callIndex += 1;
      if (callIndex === 1) {
        return new Promise<ForgeTechniquesResponse>((r) => {
          resolveFirst = r;
        });
      }
      return new Promise<ForgeTechniquesResponse>((r) => {
        resolveSecond = r;
      });
    };

    const { result } = renderHook(() => useForgeStars());
    expect(result.current).toEqual([]);

    // Trigger a second request (mimicking a `visibilitychange`).
    await act(async () => {
      document.dispatchEvent(new Event("visibilitychange"));
    });

    // Resolve the SECOND fetch first — this is the ""newer"" request
    // and its result should land.
    await act(async () => {
      resolveSecond?.(newPayload);
    });

    await waitFor(() => {
      expect(result.current.map((s) => s.id)).toEqual(["fresh-a", "fresh-b"]);
    });

    // Now resolve the FIRST (older) fetch. Its result is stale and
    // must be discarded by the request-token guard.
    await act(async () => {
      resolveFirst?.(oldPayload);
    });

    // Give the microtask queue a tick; assert the state did not
    // regress to the stale payload.
    await Promise.resolve();
    expect(result.current.map((s) => s.id)).toEqual(["fresh-a", "fresh-b"]);
  });

  it("falls silent when the fetch rejects", async () => {
    mockState.fetcher = () => Promise.reject(new Error("network down"));
    const { result } = renderHook(() => useForgeStars());
    await waitFor(() => {
      // Hook handles the rejection gracefully; we land on an empty
      // star list rather than throwing through the React tree.
      expect(result.current).toEqual([]);
    });
  });
});

function normaliseAngle(theta: number): number {
  let normalised = theta;
  while (normalised <= -Math.PI) normalised += Math.PI * 2;
  while (normalised > Math.PI) normalised -= Math.PI * 2;
  return Math.abs(normalised);
}
