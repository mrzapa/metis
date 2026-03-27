import { describe, expect, it } from "vitest";
import {
  CORE_CENTER_X,
  CORE_CENTER_Y,
  CORE_EXCLUSION_RADIUS,
  buildOutwardPlacement,
  findHoveredAddCandidate,
  getPreviewConnectionNodes,
  isAddableBackgroundStar,
  type ConstellationFieldStar,
  type ConstellationNodePoint,
  type Point,
} from "@/lib/constellation-home";
import type { UserStar } from "@/lib/constellation-types";

const WIDTH = 1000;
const HEIGHT = 1000;

function makeStar(overrides: Partial<ConstellationFieldStar> = {}): ConstellationFieldStar {
  return {
    id: "field-star",
    nx: 0.82,
    ny: 0.18,
    layer: 0,
    baseSize: 0.92,
    brightness: 0.4,
    twinkle: false,
    twinkleSpeed: 0.01,
    twinklePhase: 0,
    parallaxFactor: 0,
    hasDiffraction: false,
    ...overrides,
  };
}

function makeUserStar(overrides: Partial<UserStar> = {}): UserStar {
  return {
    id: "user-star",
    x: 0.2,
    y: 0.2,
    size: 0.9,
    createdAt: 1,
    ...overrides,
  };
}

describe("isAddableBackgroundStar", () => {
  it("rejects stars inside the core exclusion radius", () => {
    const star = makeStar({ nx: 0.58, ny: 0.44 });

    expect(isAddableBackgroundStar(star, [], [], WIDTH, HEIGHT)).toBe(false);
  });

  it("rejects stars near an existing user star", () => {
    const star = makeStar({ nx: 0.82, ny: 0.18 });
    const userStars = [makeUserStar({ x: 0.84, y: 0.2 })];

    expect(isAddableBackgroundStar(star, [], userStars, WIDTH, HEIGHT)).toBe(false);
  });

  it("rejects stars near a core node", () => {
    const star = makeStar({ nx: 0.82, ny: 0.18 });
    const nodes: ConstellationNodePoint[] = [{ x: 830, y: 190 }];

    expect(isAddableBackgroundStar(star, nodes, [], WIDTH, HEIGHT)).toBe(false);
  });

  it("accepts a bright outer star with clear space around it", () => {
    const star = makeStar({ nx: 0.9, ny: 0.15 });
    const nodes: ConstellationNodePoint[] = [{ x: 560, y: 430 }];
    const userStars = [makeUserStar({ x: 0.2, y: 0.2 })];

    expect(isAddableBackgroundStar(star, nodes, userStars, WIDTH, HEIGHT)).toBe(true);
  });

  it("accepts a readable far-field star so users get more add opportunities", () => {
    const star = makeStar({ layer: 2, baseSize: 0.52, nx: 0.86, ny: 0.16 });
    const nodes: ConstellationNodePoint[] = [{ x: 560, y: 430 }];

    expect(isAddableBackgroundStar(star, nodes, [], WIDTH, HEIGHT)).toBe(true);
  });
});

describe("findHoveredAddCandidate", () => {
  it("returns the nearest eligible star within the hit radius", () => {
    const pointer: Point = { x: 904, y: 154 };
    const stars = [
      makeStar({ id: "nearest", nx: 0.9, ny: 0.15 }),
      makeStar({ id: "second", nx: 0.92, ny: 0.17 }),
      makeStar({ id: "blocked", nx: 0.56, ny: 0.44 }),
    ];
    const candidate = findHoveredAddCandidate(
      stars,
      [{ x: 560, y: 430 }],
      [],
      pointer,
      pointer,
      WIDTH,
      HEIGHT,
      30,
    );

    expect(candidate?.id).toBe("nearest");
  });

  it("uses projected star coordinates when parallax shifts the hover target", () => {
    const mouse: Point = { x: 640, y: 420 };
    const pointer: Point = { x: 902.8, y: 148.4 };
    const stars = [makeStar({ id: "projected", nx: 0.9, ny: 0.15, parallaxFactor: 0.02 })];

    const candidate = findHoveredAddCandidate(
      stars,
      [{ x: 560, y: 430 }],
      [],
      pointer,
      mouse,
      WIDTH,
      HEIGHT,
      8,
    );

    expect(candidate?.id).toBe("projected");
  });

  it("returns null when no eligible star is close enough", () => {
    const pointer: Point = { x: 200, y: 200 };
    const stars = [makeStar({ id: "far", nx: 0.9, ny: 0.15 })];

    expect(
      findHoveredAddCandidate(stars, [{ x: 560, y: 430 }], [], pointer, pointer, WIDTH, HEIGHT, 20),
    ).toBeNull();
  });
});

describe("buildOutwardPlacement", () => {
  it("pushes mapped stars beyond the core exclusion ring", () => {
    const [x, y] = buildOutwardPlacement(CORE_CENTER_X + 0.01, CORE_CENTER_Y + 0.01, 0);

    expect(Math.hypot(x - CORE_CENTER_X, y - CORE_CENTER_Y)).toBeGreaterThanOrEqual(
      CORE_EXCLUSION_RADIUS + 0.055 - 1e-6,
    );
  });
});

describe("getPreviewConnectionNodes", () => {
  it("returns the two closest nodes in distance order", () => {
    const nodes: Array<ConstellationNodePoint & { id: string }> = [
      { id: "closest", x: 880, y: 180 },
      { id: "second", x: 760, y: 260 },
      { id: "far", x: 560, y: 430 },
    ];

    const result = getPreviewConnectionNodes({ nx: 0.9, ny: 0.18 }, nodes, WIDTH, HEIGHT);

    expect(result.map((node) => node.id)).toEqual(["closest", "second"]);
  });
});
