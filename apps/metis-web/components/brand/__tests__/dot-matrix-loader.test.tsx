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
});
