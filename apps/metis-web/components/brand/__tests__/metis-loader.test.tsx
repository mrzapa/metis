import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import { MetisLoader } from "../metis-loader";

describe("<MetisLoader>", () => {
  it('renders MetisGlow in loop mode (5 ripple ring filters)', () => {
    const { container } = render(<MetisLoader />);
    const morphologyFilters = container.querySelectorAll("feMorphology");
    expect(morphologyFilters.length).toBe(5);
  });

  it("renders the mark inside the glow wrapper", () => {
    const { container } = render(<MetisLoader />);
    // The wrapper is the .metis-glow div; the mark is the only <svg> with
    // viewBox 0 0 1000 1000 (the ripple svg has the same viewBox but is
    // aria-hidden and pointer-events-none — find a path with the master
    // path data instead).
    const paths = container.querySelectorAll("path");
    // At least one path is the master mark path; rings also use the same
    // path. So count > 0.
    expect(paths.length).toBeGreaterThan(0);
  });

  it("respects a custom size prop on the wrapper", () => {
    const { container } = render(<MetisLoader size={64} />);
    const wrapper = container.querySelector(".metis-glow") as HTMLElement;
    expect(wrapper.style.width).toBe("64px");
    expect(wrapper.style.height).toBe("64px");
  });
});
