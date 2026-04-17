import { describe, expect, it } from "vitest";
import {
  CORE_CENTER_X,
  CORE_CENTER_Y,
  CORE_EXCLUSION_RADIUS,
  CONSTELLATION_FACULTIES,
  buildOutwardPlacement,
  clampBackgroundZoomFactor,
  findHoveredAddCandidate,
  getBackgroundCameraScale,
  getBackgroundViewportWorldBounds,
  getConstellationBridgeSuggestion,
  getConstellationCameraScale,
  getFacultyColor,
  getInfluenceColors,
  getPreviewConnectionNodes,
  inferConstellationFaculty,
  isAddableBackgroundStar,
  mixConstellationColors,
  projectConstellationPoint,
  screenToConstellationPoint,
  screenToWorldPoint,
  type ConstellationFieldStar,
  type ConstellationNodePoint,
  type Point,
  worldToScreenPoint,
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

  it("rejects stars when user has no content and hasUserContent is false", () => {
    const star = makeStar({ nx: 0.9, ny: 0.15 });
    const nodes: ConstellationNodePoint[] = [{ x: 560, y: 430 }];

    expect(isAddableBackgroundStar(star, nodes, [], WIDTH, HEIGHT, false)).toBe(false);
  });

  it("allows stars when user has created stars even if hasUserContent is false", () => {
    const star = makeStar({ nx: 0.9, ny: 0.15 });
    const nodes: ConstellationNodePoint[] = [{ x: 560, y: 430 }];
    const userStars = [makeUserStar({ x: 0.2, y: 0.2 })];

    // Should still pass because there are existing user stars
    expect(isAddableBackgroundStar(star, nodes, userStars, WIDTH, HEIGHT, false)).toBe(true);
  });

  it("rejects star within exclusion buffer of a secondary constellation star", () => {
    const star = makeStar({ nx: 0.93, ny: 0.15 });
    // Secondary constellation star at pixel (907, 120) → normalized (0.907, 0.120)
    // Distance ≈ 0.038 < ADDABLE_NODE_BUFFER (0.04) → should reject
    const nodes: ConstellationNodePoint[] = [{ x: 907, y: 120 }];

    expect(isAddableBackgroundStar(star, nodes, [], WIDTH, HEIGHT)).toBe(false);
  });

  it("accepts star just outside exclusion buffer of every constellation star", () => {
    const star = makeStar({ nx: 0.92, ny: 0.12 });
    // Secondary constellation star at pixel (867, 65) → normalized (0.867, 0.065)
    // Distance ≈ 0.076 > ADDABLE_NODE_BUFFER (0.04) → should accept
    const nodes: ConstellationNodePoint[] = [{ x: 867, y: 65 }];
    const userStars = [makeUserStar({ x: 0.2, y: 0.2 })];

    expect(isAddableBackgroundStar(star, nodes, userStars, WIDTH, HEIGHT)).toBe(true);
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

  it("round-trips connectedUserStarIds while filtering self-links", () => {
    const normalized = normalizeUserStar({
      id: "self",
      x: 0.2,
      y: 0.3,
      size: 1,
      createdAt: 2,
      connectedUserStarIds: [" self ", "peer", "peer", " peer-2 "],
    });

    expect(normalized.connectedUserStarIds).toEqual(["peer", "peer-2"]);

    const parsed = parseUserStars([normalized]);

    expect(parsed).toHaveLength(1);
    expect(parsed[0].connectedUserStarIds).toEqual(["peer", "peer-2"]);
  });

  it("leaves explicit ids untouched", () => {
    const stars = parseUserStars([
      {
        id: "  explicit-star  ",
        label: "Explicit",
        x: 0.4,
        y: 0.7,
      },
    ]);

    expect(stars).toHaveLength(1);
    expect(stars[0].id).toBe("  explicit-star  ");
  });

  it("treats blank ids as absent when meaningful star content exists", () => {
    const [blankIdStar] = parseUserStars([
      {
        id: "   ",
        label: "Bridge",
        primaryDomainId: "knowledge",
        relatedDomainIds: ["memory", "strategy"],
        x: 0.28,
      },
    ]);
    const [idlessStar] = parseUserStars([
      {
        label: "Bridge",
        primaryDomainId: "knowledge",
        relatedDomainIds: ["memory", "strategy"],
        x: 0.28,
      },
    ]);

    expect(blankIdStar.id).toBe(idlessStar.id);
    expect(blankIdStar.id).toMatch(/^default-star-/);
    expect(blankIdStar.label).toBe("Bridge");
    expect(blankIdStar.primaryDomainId).toBe("knowledge");
    expect(blankIdStar.relatedDomainIds).toEqual(["memory", "strategy"]);
  });

  it("filters sparse payloads with blank explicit ids", () => {
    const stars = parseUserStars([
      {
        id: "",
        x: 0.4,
      },
      {
        id: "   ",
        label: "   ",
        y: 0.7,
      },
      {
        id: "\n\t",
        size: 1.2,
      },
    ]);

    expect(stars).toHaveLength(0);
  });

  it("filters sparse payloads but keeps meaningful default-star seeds", () => {
    const stars = parseUserStars([
      {
        x: 0.4,
      },
      {
        y: 0.7,
        size: 1.2,
      },
      {
        label: "   ",
        x: 0.45,
        y: 0.55,
      },
      {
        label: "Bridge",
        primaryDomainId: "knowledge",
        relatedDomainIds: ["memory", "strategy"],
        x: 0.28,
      },
    ]);

    expect(stars).toHaveLength(1);
    expect(stars[0].id).toMatch(/^default-star-/);
    expect(stars[0].label).toBe("Bridge");
    expect(stars[0].primaryDomainId).toBe("knowledge");
    expect(stars[0].relatedDomainIds).toEqual(["memory", "strategy"]);
    expect(stars[0].x).toBe(0.28);
    expect(stars[0].y).toBe(0.5);
  });

  it("canonicalizes legacy and multi-link manifest metadata into the same fallback id", () => {
    const [legacyStar] = parseUserStars([
      {
        label: "Manifest bridge",
        primaryDomainId: "knowledge",
        linkedManifestPath: "/indexes/atlas.json",
        x: 0.42,
        y: 0.66,
      },
    ]);
    const [multiLinkStar] = parseUserStars([
      {
        label: "Manifest bridge",
        primaryDomainId: "knowledge",
        linkedManifestPaths: ["/indexes/atlas.json"],
        activeManifestPath: "/indexes/atlas.json",
        x: 0.42,
        y: 0.66,
      },
    ]);

    expect(legacyStar.id).toBe(multiLinkStar.id);
  });

  it("treats related domains and connected stars as order-insensitive for fallback ids", () => {
    const [left] = parseUserStars([
      {
        label: "Bridge",
        primaryDomainId: "knowledge",
        relatedDomainIds: ["memory", "strategy", "memory"],
        connectedUserStarIds: ["star-b", "star-a", "star-b"],
        x: 0.28,
        y: 0.58,
      },
    ]);
    const [right] = parseUserStars([
      {
        label: "Bridge",
        primaryDomainId: "knowledge",
        relatedDomainIds: ["strategy", "memory"],
        connectedUserStarIds: ["star-a", "star-b"],
        x: 0.28,
        y: 0.58,
      },
    ]);

    expect(left.id).toBe(right.id);
  });

  it("ignores secondary manifest attachment order when the resolved primary manifest is the same", () => {
    const [left] = parseUserStars([
      {
        label: "Atlas cluster",
        activeManifestPath: "/indexes/primary.json",
        linkedManifestPaths: [
          "/indexes/primary.json",
          "/indexes/support-b.json",
          "/indexes/support-a.json",
        ],
        x: 0.36,
        y: 0.52,
      },
    ]);
    const [right] = parseUserStars([
      {
        label: "Atlas cluster",
        activeManifestPath: "/indexes/primary.json",
        linkedManifestPaths: [
          "/indexes/support-a.json",
          "/indexes/support-b.json",
          "/indexes/primary.json",
        ],
        x: 0.36,
        y: 0.52,
      },
    ]);

    expect(left.id).toBe(right.id);
  });

  it("keeps different resolved primary manifests distinct", () => {
    const [left] = parseUserStars([
      {
        label: "Atlas cluster",
        activeManifestPath: "/indexes/primary-a.json",
        linkedManifestPaths: ["/indexes/primary-a.json", "/indexes/support.json"],
        x: 0.36,
        y: 0.52,
      },
    ]);
    const [right] = parseUserStars([
      {
        label: "Atlas cluster",
        activeManifestPath: "/indexes/primary-b.json",
        linkedManifestPaths: ["/indexes/primary-a.json", "/indexes/support.json"],
        x: 0.36,
        y: 0.52,
      },
    ]);

    expect(left.id).not.toBe(right.id);
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

  it("keeps hover targets anchored to the rendered star position", () => {
    const mouse: Point = { x: 640, y: 420 };
    const pointer: Point = { x: 900, y: 150 };
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

describe("constellation projection helpers", () => {
  it("softens constellation scaling so faculties stay legible at deep zoom", () => {
    expect(getConstellationCameraScale(1)).toBeCloseTo(1, 6);
    expect(getConstellationCameraScale(200)).toBeLessThan(getBackgroundCameraScale(200));
    expect(getConstellationCameraScale(200)).toBeCloseTo(0.08 + Math.sqrt(200) * 0.92, 3);
  });

  it("round-trips constellation points through screen projection", () => {
    const camera = { x: 180, y: -120, zoomFactor: 32 };
    const point = { x: 0.82, y: 0.23 };
    const parallax = { x: 12, y: -8 };
    const projected = projectConstellationPoint(point, WIDTH, HEIGHT, camera, parallax);
    const restored = screenToConstellationPoint(projected, WIDTH, HEIGHT, camera, parallax);

    expect(restored.x).toBeCloseTo(point.x, 6);
    expect(restored.y).toBeCloseTo(point.y, 6);
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

describe("background zoom helpers", () => {
  it("clamps the zoom factor to the supported orbit window", () => {
    expect(clampBackgroundZoomFactor(0.001)).toBe(0.002);
    expect(clampBackgroundZoomFactor(2500)).toBe(2000);
    expect(clampBackgroundZoomFactor(24)).toBe(24);
  });

  it("uses a square-root scale so a 200x zoom factor grows the viewport without blowing up span", () => {
    expect(getBackgroundCameraScale(1)).toBeCloseTo(1, 6);
    expect(getBackgroundCameraScale(200)).toBeCloseTo(Math.sqrt(200), 6);
  });

  it("round-trips world coordinates through screen projection", () => {
    const camera = {
      x: 240,
      y: -120,
      zoomFactor: 16,
    };
    const worldPoint = { x: 560, y: 80 };

    const screenPoint = worldToScreenPoint(worldPoint, WIDTH, HEIGHT, camera);
    const roundTripped = screenToWorldPoint(screenPoint, WIDTH, HEIGHT, camera);

    expect(roundTripped.x).toBeCloseTo(worldPoint.x, 6);
    expect(roundTripped.y).toBeCloseTo(worldPoint.y, 6);
  });

  it("shrinks the visible world bounds as the zoom factor grows (zoom in = closer)", () => {
    const wideBounds = getBackgroundViewportWorldBounds(WIDTH, HEIGHT, { x: 0, y: 0, zoomFactor: 1 });
    const tightBounds = getBackgroundViewportWorldBounds(WIDTH, HEIGHT, { x: 0, y: 0, zoomFactor: 64 });

    expect(tightBounds.right - tightBounds.left).toBeLessThan(wideBounds.right - wideBounds.left);
    expect(tightBounds.bottom - tightBounds.top).toBeLessThan(wideBounds.bottom - wideBounds.top);
  });
});

describe("influence colors", () => {
  it("returns a stable fallback color when no faculty ids are present", () => {
    expect(getInfluenceColors()).toEqual([[208, 216, 232]]);
  });

  it("keeps primary and bridge colors distinct for mixed stars", () => {
    expect(getInfluenceColors("autonomy", ["emergence", "autonomy"])).toEqual([
      getFacultyColor("autonomy"),
      getFacultyColor("emergence"),
    ]);
  });

  it("mixes multiple faculty colors into a blended constellation tint", () => {
    expect(
      mixConstellationColors([
        [199, 218, 121],
        [148, 153, 239],
      ]),
    ).toEqual([174, 186, 180]);
  });
});
