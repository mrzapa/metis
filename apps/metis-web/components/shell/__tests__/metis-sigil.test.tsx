import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetisSigil } from "../metis-sigil";

describe("MetisSigil", () => {
  it("renders with default seedling stage", () => {
    render(<MetisSigil ariaLabel="METIS sigil" />);
    const svg = screen.getByLabelText("METIS sigil");
    expect(svg).toHaveAttribute("data-stage", "seedling");
    expect(svg).toHaveAttribute("data-active", "false");
  });

  it("exposes the stage as a data attribute for each growth stage", () => {
    const stages = ["seedling", "sapling", "bloom", "elder"] as const;
    for (const stage of stages) {
      const { unmount } = render(
        <MetisSigil stage={stage} ariaLabel={`sigil-${stage}`} />,
      );
      expect(screen.getByLabelText(`sigil-${stage}`)).toHaveAttribute(
        "data-stage",
        stage,
      );
      unmount();
    }
  });

  it("renders one ring per stage tier", () => {
    const expected: Record<string, number> = {
      seedling: 1,
      sapling: 2,
      bloom: 3,
      elder: 4,
    };
    for (const stage of Object.keys(expected) as Array<keyof typeof expected>) {
      const { container, unmount } = render(
        <MetisSigil stage={stage} ariaLabel={`sigil-${stage}`} />,
      );
      // Rings are circles with stroke="currentColor" + fill="none".
      const rings = container.querySelectorAll(
        'circle[stroke="currentColor"][fill="none"]',
      );
      expect(rings.length).toBe(expected[stage]);
      unmount();
    }
  });

  it("flags active state via data-active for visual targeting", () => {
    render(<MetisSigil active ariaLabel="active-sigil" />);
    expect(screen.getByLabelText("active-sigil")).toHaveAttribute(
      "data-active",
      "true",
    );
  });

  it("respects the size prop", () => {
    render(<MetisSigil size={64} ariaLabel="big-sigil" />);
    const svg = screen.getByLabelText("big-sigil");
    expect(svg).toHaveAttribute("width", "64");
    expect(svg).toHaveAttribute("height", "64");
  });

  it("uses presentation role when no aria-label is provided", () => {
    const { container } = render(<MetisSigil />);
    const svg = container.querySelector("svg");
    expect(svg).toHaveAttribute("role", "presentation");
    expect(svg).toHaveAttribute("aria-hidden", "true");
  });
});
