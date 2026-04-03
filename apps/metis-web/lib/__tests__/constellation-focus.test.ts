import { describe, expect, it } from "vitest";
import { MAX_BACKGROUND_ZOOM_FACTOR, MIN_BACKGROUND_ZOOM_FACTOR } from "@/lib/constellation-home";
import {
  buildProjectedCandidateHitTarget,
  buildProjectedUserStarHitTarget,
  buildCameraForConstellationPoint,
  buildStarFocusCamera,
  cloneCameraSnapshot,
  createUserStarVisualProfile,
  DESKTOP_STAR_FOCUS_LAYOUT,
  findClosestProjectedTarget,
  getStarFocusLayout,
  isCameraSettled,
  MOBILE_STAR_FOCUS_LAYOUT,
  projectUserStarScreenPoint,
  projectFocusedStar,
} from "@/lib/constellation-focus";

describe("constellation focus helpers", () => {
  it("projects a focused desktop star into the safe zone", () => {
    const camera = buildStarFocusCamera(
      { x: 0.72, y: 0.38, size: 1 },
      1440,
      900,
    );

    const projected = projectFocusedStar(
      { x: 0.72, y: 0.38 },
      1440,
      900,
      camera,
    );

    expect(projected.x).toBeCloseTo(1440 * DESKTOP_STAR_FOCUS_LAYOUT.viewportX, 1);
    expect(projected.y).toBeCloseTo(900 * DESKTOP_STAR_FOCUS_LAYOUT.viewportY, 1);
  });

  it("switches to the mobile focus layout below the panel breakpoint", () => {
    expect(getStarFocusLayout(390, 844)).toEqual(MOBILE_STAR_FOCUS_LAYOUT);
    expect(getStarFocusLayout(1440, 900)).toEqual(DESKTOP_STAR_FOCUS_LAYOUT);
  });

  it("clamps the focus zoom when a camera target requests an extreme value", () => {
    expect(
      buildCameraForConstellationPoint(
        { x: 0.5, y: 0.5 },
        1440,
        900,
        999,
        DESKTOP_STAR_FOCUS_LAYOUT,
      ).zoomFactor,
    ).toBe(MAX_BACKGROUND_ZOOM_FACTOR);

    expect(
      buildCameraForConstellationPoint(
        { x: 0.5, y: 0.5 },
        1440,
        900,
        0.01,
        MOBILE_STAR_FOCUS_LAYOUT,
      ).zoomFactor,
    ).toBe(MIN_BACKGROUND_ZOOM_FACTOR);
  });

  it("clones and settles back to a saved camera snapshot", () => {
    const original = {
      x: -120,
      y: 64,
      zoomFactor: 1.8,
    };
    const snapshot = cloneCameraSnapshot(original);

    expect(snapshot).toEqual({
      x: -120,
      y: 64,
      zoomFactor: 1.8,
    });
    expect(snapshot).not.toBe(original);
    expect(isCameraSettled(snapshot, snapshot)).toBe(true);
  });

  it("updates projected user-star hit targets when the camera changes", () => {
    const nearTarget = buildProjectedUserStarHitTarget(
      { id: "star-a", x: 0.62, y: 0.4, size: 1 },
      1200,
      800,
      { x: 0, y: 0, zoomFactor: 1 },
    );
    const shiftedTarget = buildProjectedUserStarHitTarget(
      { id: "star-a", x: 0.62, y: 0.4, size: 1 },
      1200,
      800,
      { x: 120, y: -40, zoomFactor: 1.8 },
    );

    expect(nearTarget.x).not.toBeCloseTo(shiftedTarget.x, 4);
    expect(nearTarget.y).not.toBeCloseTo(shiftedTarget.y, 4);
  });

  it("applies parallax offset to user-star positions when mouse is provided", () => {
    const camera = { x: 0, y: 0, zoomFactor: 1 };
    const star = { id: "star-a", x: 0.62, y: 0.4, size: 1 };
    const noMouseTarget = buildProjectedUserStarHitTarget(star, 1200, 800, camera);
    const withMouseTarget = buildProjectedUserStarHitTarget(
      star,
      1200,
      800,
      camera,
      0,
      { x: 700, y: 500 }, // Mouse offset from center (600, 400)
    );

    // With mouse positioned right of center, x should shift right
    // With mouse positioned below center, y should shift down
    expect(withMouseTarget.x).toBeGreaterThan(noMouseTarget.x);
    expect(withMouseTarget.y).toBeGreaterThan(noMouseTarget.y);
  });

  it("creates deterministic visual profiles for seeded user stars", () => {
    const firstProfile = createUserStarVisualProfile("star-seeded");
    const secondProfile = createUserStarVisualProfile("star-seeded");
    const differentProfile = createUserStarVisualProfile("star-other");

    expect(secondProfile).toEqual(firstProfile);
    expect(differentProfile).not.toEqual(firstProfile);
    expect(firstProfile.coreIntensity).toBeGreaterThan(0.88);
    expect(firstProfile.coreIntensity).toBeLessThan(1.22);
  });

  it("projects screen-space user-star positions through the shared helper used by hit targets", () => {
    const camera = { x: 120, y: -40, zoomFactor: 1.8 };
    const mouse = { x: 700, y: 500 };
    const star = { id: "star-a", x: 0.62, y: 0.4, size: 1 };
    const projectedPoint = projectUserStarScreenPoint(star, 1200, 800, camera, mouse);
    const projectedTarget = buildProjectedUserStarHitTarget(star, 1200, 800, camera, 0, mouse);

    expect(projectedTarget.x).toBeCloseTo(projectedPoint.x, 6);
    expect(projectedTarget.y).toBeCloseTo(projectedPoint.y, 6);
  });

  it("finds the closest cached hit target from screen-space projections", () => {
    const candidateTarget = buildProjectedCandidateHitTarget(
      { id: "candidate-a", nx: 0.5, ny: 0.5, parallaxFactor: 0.02 },
      1000,
      800,
      { x: 500, y: 400 },
      24,
    );
    const fartherTarget = {
      id: "candidate-b",
      x: candidateTarget.x + 120,
      y: candidateTarget.y + 120,
      hitRadius: 24,
    };

    expect(
      findClosestProjectedTarget(
        [candidateTarget, fartherTarget],
        { x: candidateTarget.x + 4, y: candidateTarget.y + 3 },
      )?.id,
    ).toBe("candidate-a");
  });

  it("keeps background candidate hit targets anchored to the rendered screen position", () => {
    const star = { id: "candidate-a", nx: 0.5, ny: 0.5, parallaxFactor: 0.02 };
    const centeredTarget = buildProjectedCandidateHitTarget(
      star,
      1000,
      800,
      { x: 500, y: 400 },
      24,
    );
    const offsetTarget = buildProjectedCandidateHitTarget(
      star,
      1000,
      800,
      { x: 740, y: 180 },
      24,
    );

    expect(offsetTarget.x).toBeCloseTo(centeredTarget.x, 6);
    expect(offsetTarget.y).toBeCloseTo(centeredTarget.y, 6);
  });
});
