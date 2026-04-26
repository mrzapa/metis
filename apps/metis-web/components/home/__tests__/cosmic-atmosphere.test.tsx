import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CosmicAtmosphere } from "../cosmic-atmosphere";

describe("CosmicAtmosphere", () => {
  it("renders a fixed full-viewport overlay", () => {
    render(<CosmicAtmosphere zoomFactor={1} />);
    const layer = screen.getByTestId("cosmic-atmosphere");
    expect(layer.className).toMatch(/fixed/);
    expect(layer.className).toMatch(/inset-0/);
    expect(layer.className).toMatch(/pointer-events-none/);
  });

  it("is hidden from the accessibility tree", () => {
    render(<CosmicAtmosphere zoomFactor={1} />);
    expect(screen.getByTestId("cosmic-atmosphere")).toHaveAttribute(
      "aria-hidden",
      "true",
    );
  });

  it("scales intensity with zoom — zero at zoom 1", () => {
    render(<CosmicAtmosphere zoomFactor={1} />);
    const layer = screen.getByTestId("cosmic-atmosphere");
    expect(parseFloat(layer.dataset.intensity ?? "0")).toBe(0);
  });

  it("intensity climbs sub-linearly into the mid-zoom range", () => {
    const { rerender } = render(<CosmicAtmosphere zoomFactor={2} />);
    const at2 = parseFloat(
      screen.getByTestId("cosmic-atmosphere").dataset.intensity ?? "0",
    );
    rerender(<CosmicAtmosphere zoomFactor={20} />);
    const at20 = parseFloat(
      screen.getByTestId("cosmic-atmosphere").dataset.intensity ?? "0",
    );
    rerender(<CosmicAtmosphere zoomFactor={60} />);
    const at60 = parseFloat(
      screen.getByTestId("cosmic-atmosphere").dataset.intensity ?? "0",
    );
    expect(at2).toBeGreaterThan(0);
    expect(at20).toBeGreaterThan(at2);
    expect(at60).toBeGreaterThan(at20);
    expect(at60).toBeLessThanOrEqual(1);
  });

  it("clamps to 1 at extreme zoom", () => {
    render(<CosmicAtmosphere zoomFactor={1000} />);
    const layer = screen.getByTestId("cosmic-atmosphere");
    expect(parseFloat(layer.dataset.intensity ?? "0")).toBe(1);
  });
});
