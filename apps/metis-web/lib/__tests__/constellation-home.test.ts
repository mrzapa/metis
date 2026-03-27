import { describe, expect, it } from "vitest";
import {
  CORE_CENTER_X,
  CORE_CENTER_Y,
  CORE_EXCLUSION_RADIUS,
  CONSTELLATION_FACULTIES,
  buildOutwardPlacement,
  findHoveredAddCandidate,
  getConstellationBridgeSuggestion,
  getPreviewConnectionNodes,
  inferConstellationFaculty,
  isAddableBackgroundStar,
  type ConstellationFieldStar,
  type ConstellationNodePoint,
  type Point,
} from "@/lib/constellation-home";
import { normalizeUserStar, parseUserStars, type UserStar } from "@/lib/constellation-types";

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

describe("normalizeUserStar", () => {
  it("migrates the legacy manifest path into the new multi-link shape", () => {
    const star = normalizeUserStar({
      id: "legacy",
      x: 0.24,
      y: 0.61,
      size: 1.1,
      createdAt: 42,
      linkedManifestPath: "/indexes/legacy.json",
    });

    expect(star.linkedManifestPath).toBe("/indexes/legacy.json");
    expect(star.linkedManifestPaths).toEqual(["/indexes/legacy.json"]);
    expect(star.activeManifestPath).toBe("/indexes/legacy.json");
    expect(star.stage).toBe("growing");
  });

  it("keeps explicit stage overrides while normalizing manifest metadata", () => {
    const star = normalizeUserStar({
      id: "multi",
      x: 0.3,
      y: 0.55,
      size: 1,
      createdAt: 7,
      stage: "seed",
      notes: "  stitched across domains  ",
      linkedManifestPaths: ["/indexes/a.json", "/indexes/b.json", "/indexes/a.json"],
      activeManifestPath: "/indexes/b.json",
      relatedDomainIds: ["memory", "strategy", "memory"],
      primaryDomainId: "knowledge",
    });

    expect(star.stage).toBe("seed");
    expect(star.notes).toBe("stitched across domains");
    expect(star.linkedManifestPaths).toEqual(["/indexes/b.json", "/indexes/a.json"]);
    expect(star.activeManifestPath).toBe("/indexes/b.json");
    expect(star.linkedManifestPath).toBe("/indexes/b.json");
    expect(star.relatedDomainIds).toEqual(["memory", "strategy"]);
  });

  it("defaults to integrated when multiple attached indexes are present", () => {
    const star = normalizeUserStar({
      id: "integrated",
      x: 0.6,
      y: 0.4,
      size: 1,
      createdAt: 9,
      linkedManifestPaths: ["/indexes/one.json", "/indexes/two.json"],
    });

    expect(star.stage).toBe("integrated");
  });
});

describe("parseUserStars", () => {
  it("filters invalid entries and preserves migrated stars", () => {
    const stars = parseUserStars([
      {
        id: "valid",
        x: 0.1,
        y: 0.2,
        size: 1,
        createdAt: 1,
        linkedManifestPath: "/indexes/source.json",
      },
      {
        id: "broken",
        x: "oops",
      },
    ]);

    expect(stars).toHaveLength(1);
    expect(stars[0].linkedManifestPaths).toEqual(["/indexes/source.json"]);
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

  it("moves later shells farther from the core", () => {
    const near = buildOutwardPlacement(CORE_CENTER_X + 0.02, CORE_CENTER_Y, 0);
    const far = buildOutwardPlacement(CORE_CENTER_X + 0.02, CORE_CENTER_Y, 16);

    expect(Math.hypot(far[0] - CORE_CENTER_X, far[1] - CORE_CENTER_Y)).toBeGreaterThan(
      Math.hypot(near[0] - CORE_CENTER_X, near[1] - CORE_CENTER_Y),
    );
  });
});

describe("faculty inference", () => {
  it("returns the nearest faculty without a bridge suggestion for a direct hit", () => {
    const faculty = CONSTELLATION_FACULTIES[0];

    const inference = inferConstellationFaculty({ x: faculty.x, y: faculty.y });

    expect(inference.primary.faculty.id).toBe(faculty.id);
    expect(inference.bridgeSuggestion).toBeNull();
    expect(getConstellationBridgeSuggestion({ x: faculty.x, y: faculty.y })).toBeNull();
  });

  it("suggests a bridge faculty when the second nearest facet is close enough", () => {
    const primaryFaculty = CONSTELLATION_FACULTIES[0];
    const secondaryFaculty = CONSTELLATION_FACULTIES[1];
    const point: Point = {
      x: primaryFaculty.x * 0.52 + secondaryFaculty.x * 0.48,
      y: primaryFaculty.y * 0.52 + secondaryFaculty.y * 0.48,
    };

    const inference = inferConstellationFaculty(point);

    expect(inference.primary.faculty.id).toBe(primaryFaculty.id);
    expect(inference.secondary?.faculty.id).toBe(secondaryFaculty.id);
    expect(inference.bridgeSuggestion?.faculty.id).toBe(secondaryFaculty.id);
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
