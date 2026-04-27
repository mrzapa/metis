import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useRef } from "react";
import {
  CosmicAtmosphere,
  type CosmicAtmosphereFocusFrame,
} from "../cosmic-atmosphere";

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

  it("does not render the focus-bloom layer when no ref is provided", () => {
    render(<CosmicAtmosphere zoomFactor={1} />);
    expect(
      screen.queryByTestId("cosmic-atmosphere-focus-bloom"),
    ).not.toBeInTheDocument();
  });

  it("renders the focus-bloom layer when a focusFrameRef is provided", () => {
    function Wrapper() {
      const ref = useRef<CosmicAtmosphereFocusFrame>({
        centerX: 100,
        centerY: 80,
        strength: 0.5,
      });
      return <CosmicAtmosphere zoomFactor={20} focusFrameRef={ref} />;
    }
    render(<Wrapper />);
    expect(
      screen.getByTestId("cosmic-atmosphere-focus-bloom"),
    ).toBeInTheDocument();
  });

  it("renders the pulse-ring layer when a focusFrameRef is provided", () => {
    function Wrapper() {
      const ref = useRef<CosmicAtmosphereFocusFrame>({
        centerX: 100,
        centerY: 80,
        strength: 0.5,
      });
      return <CosmicAtmosphere zoomFactor={20} focusFrameRef={ref} />;
    }
    render(<Wrapper />);
    expect(
      screen.getByTestId("cosmic-atmosphere-pulse-ring"),
    ).toBeInTheDocument();
  });

  it("does not render the pulse-ring layer without a focusFrameRef", () => {
    render(<CosmicAtmosphere zoomFactor={1} />);
    expect(
      screen.queryByTestId("cosmic-atmosphere-pulse-ring"),
    ).not.toBeInTheDocument();
  });
});
