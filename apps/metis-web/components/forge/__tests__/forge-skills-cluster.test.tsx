import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ForgeSkillsCluster,
  __test as clusterInternals,
} from "../forge-skills-cluster";
import { CONSTELLATION_FACULTIES, FACULTY_PALETTE } from "@/lib/constellation-home";
import type { ForgeTechnique } from "@/lib/api";

const router = {
  push: vi.fn(),
  replace: vi.fn(),
  back: vi.fn(),
  forward: vi.fn(),
  refresh: vi.fn(),
  prefetch: vi.fn(),
};

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

function makeTechnique(
  id: string,
  overrides: Partial<ForgeTechnique> = {},
): ForgeTechnique {
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

afterEach(() => {
  router.push.mockReset();
});

describe("clusterDots position math", () => {
  const skills = CONSTELLATION_FACULTIES.find((f) => f.id === "skills")!;

  it("returns no dots when no techniques are enabled", () => {
    const dots = clusterInternals.clusterDots([]);
    expect(dots).toEqual([]);
  });

  it("places one dot at the seeded angle around the Skills anchor", () => {
    const dots = clusterInternals.clusterDots([makeTechnique("reranker")]);
    expect(dots).toHaveLength(1);
    const [dot] = dots;
    const expectedX =
      skills.x + Math.cos(clusterInternals.CLUSTER_RING_PHASE) * clusterInternals.CLUSTER_RING_RADIUS;
    const expectedY =
      skills.y + Math.sin(clusterInternals.CLUSTER_RING_PHASE) * clusterInternals.CLUSTER_RING_RADIUS;
    expect(dot.nx).toBeCloseTo(expectedX, 6);
    expect(dot.ny).toBeCloseTo(expectedY, 6);
  });

  it("fans multiple dots evenly around the anchor", () => {
    const techniques = [
      makeTechnique("a"),
      makeTechnique("b"),
      makeTechnique("c"),
      makeTechnique("d"),
    ];
    const dots = clusterInternals.clusterDots(techniques);
    expect(dots).toHaveLength(4);
    // Each pair of adjacent dots should be the same arc-distance from
    // the anchor; reading dx/dy and computing the polar angle confirms
    // a uniform spread of TAU / 4 between consecutive dots.
    const angles = dots.map((dot) => Math.atan2(dot.ny - skills.y, dot.nx - skills.x));
    const diffs = angles
      .slice(1)
      .map((angle, idx) => normaliseAngle(angle - angles[idx]));
    diffs.forEach((diff) => expect(diff).toBeCloseTo(Math.PI / 2, 5));
  });
});

describe("pillarPalette", () => {
  it("returns the skills tone for companion techniques", () => {
    expect(clusterInternals.pillarPalette("companion")).toEqual(FACULTY_PALETTE.skills);
  });

  it("returns the reasoning tone for cortex techniques", () => {
    expect(clusterInternals.pillarPalette("cortex")).toEqual(FACULTY_PALETTE.reasoning);
  });

  it("returns a neutral palette for cross-cutting techniques", () => {
    const tone = clusterInternals.pillarPalette("cross-cutting");
    expect(tone).toEqual([208, 216, 232]);
  });
});

describe("<ForgeSkillsCluster /> rendering", () => {
  it("renders nothing when no active techniques", () => {
    const { container } = render(
      <ForgeSkillsCluster
        techniquesOverride={[
          makeTechnique("a", { enabled: false }),
          makeTechnique("b", { enabled: false }),
        ]}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders one dot per active technique", async () => {
    const techniques = [
      makeTechnique("reranker"),
      makeTechnique("hebbian-edges", { pillar: "companion" }),
      makeTechnique("inactive", { enabled: false }),
    ];
    render(<ForgeSkillsCluster techniquesOverride={techniques} />);

    const buttons = await screen.findAllByRole("button");
    expect(buttons).toHaveLength(2);
    expect(buttons.map((btn) => btn.getAttribute("data-technique-id"))).toEqual([
      "reranker",
      "hebbian-edges",
    ]);
  });

  it("hides itself when `hidden` prop is set", () => {
    const { container } = render(
      <ForgeSkillsCluster
        hidden
        techniquesOverride={[makeTechnique("reranker")]}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("routes to /forge#<id> when a dot is clicked", async () => {
    render(
      <ForgeSkillsCluster techniquesOverride={[makeTechnique("reranker")]} />,
    );
    const button = await screen.findByRole("button", {
      name: /open reranker in the forge/i,
    });
    act(() => {
      fireEvent.click(button);
    });
    await waitFor(() => {
      expect(router.push).toHaveBeenCalledWith("/forge#reranker");
    });
  });
});

function normaliseAngle(theta: number): number {
  let normalised = theta;
  while (normalised <= -Math.PI) normalised += Math.PI * 2;
  while (normalised > Math.PI) normalised -= Math.PI * 2;
  return Math.abs(normalised);
}
