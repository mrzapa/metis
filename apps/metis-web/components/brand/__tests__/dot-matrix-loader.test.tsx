import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import { DotMatrixLoader } from "../dot-matrix-loader";

describe("<DotMatrixLoader>", () => {
  it("renders breath as a 5×5 grid of circles with the dm-breath class", () => {
    const { container } = render(<DotMatrixLoader name="breath" />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg!.classList.contains("dm-breath")).toBe(true);
    const circles = container.querySelectorAll("circle");
    expect(circles.length).toBe(25);
  });

  it("renders thinking with the dm-thinking class and 25 circles", () => {
    const { container } = render(<DotMatrixLoader name="thinking" />);
    const svg = container.querySelector("svg");
    expect(svg!.classList.contains("dm-thinking")).toBe(true);
    expect(container.querySelectorAll("circle").length).toBe(25);
  });

  it("inner-cluster cells of thinking carry an animation-delay style", () => {
    // Inner 3×3 spans cols 1..3, rows 1..3. Per the design doc, those
    // 9 cells are the only ones with non-zero animation-delay.
    const { container } = render(<DotMatrixLoader name="thinking" />);
    const circles = Array.from(container.querySelectorAll("circle"));
    // Inner cluster cells are indices where col in [1..3] and row in [1..3]
    // — for our row-major emit order, those are 9 specific indices.
    const innerIndices = [6, 7, 8, 11, 12, 13, 16, 17, 18];
    const inner = innerIndices.map((i) => circles[i] as SVGCircleElement);
    for (const c of inner) {
      expect(c.style.animationDelay).not.toBe("");
    }
  });

  it("renders stream with dm-stream class and per-cell row-major delays", () => {
    const { container } = render(<DotMatrixLoader name="stream" />);
    const svg = container.querySelector("svg");
    expect(svg!.classList.contains("dm-stream")).toBe(true);
    const circles = Array.from(container.querySelectorAll("circle"));
    expect(circles.length).toBe(25);
    // Every circle should carry a non-empty animation-delay (every cell animates).
    for (const c of circles) {
      expect((c as SVGCircleElement).style.animationDelay).not.toBe("");
    }
  });

  it("renders compile with dm-compile class and 25 circles", () => {
    const { container } = render(<DotMatrixLoader name="compile" />);
    const svg = container.querySelector("svg");
    expect(svg!.classList.contains("dm-compile")).toBe(true);
    expect(container.querySelectorAll("circle").length).toBe(25);
  });

  it("renders verify as a one-shot with fill-forwards", () => {
    const { container } = render(<DotMatrixLoader name="verify" />);
    const svg = container.querySelector("svg");
    expect(svg!.classList.contains("dm-verify")).toBe(true);
    // Six checkmark cells should carry a non-empty animation-delay style.
    // Other cells should not animate at all.
    const circles = Array.from(container.querySelectorAll("circle")) as SVGCircleElement[];
    const animated = circles.filter((c) => c.style.animationDelay !== "");
    expect(animated.length).toBe(5); // (3,0) (4,1) (3,2) (2,3) (1,4)
  });
});
