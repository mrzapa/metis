import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";

import { MetisGlow } from "../metis-glow";
import { MetisMark } from "../metis-mark";

// NOTE: motion/react is globally mocked by vitest.setup.ts (passes children
// through, returns useReducedMotion=false). That is fine for our coverage —
// rings always render in tests when `animated !== "static"`. The reduced-
// motion code path is exercised via the `animated="static"` prop test below
// instead of by re-mocking useReducedMotion (which would force us to re-
// implement the full motion.* surface). The runtime reduced-motion contract
// is verified manually in the Phase 1 gate.

describe("<MetisGlow>", () => {
  it("renders the wrapped child", () => {
    const { getByTestId } = render(
      <MetisGlow>
        <div data-testid="child" />
      </MetisGlow>,
    );
    expect(getByTestId("child")).not.toBeNull();
  });

  it("applies the .metis-glow class so the CSS drop-shadow stack kicks in", () => {
    const { container } = render(
      <MetisGlow>
        <MetisMark />
      </MetisGlow>,
    );
    const wrapper = container.querySelector(".metis-glow");
    expect(wrapper).not.toBeNull();
  });

  it("renders 5 ripple ring filters via feMorphology when animated", () => {
    const { container } = render(
      <MetisGlow animated="on-mount">
        <MetisMark />
      </MetisGlow>,
    );
    const morphologyFilters = container.querySelectorAll("feMorphology");
    expect(morphologyFilters.length).toBe(5);
  });

  it("renders 5 ripple ring filters in loop mode too", () => {
    const { container } = render(
      <MetisGlow animated="loop">
        <MetisMark />
      </MetisGlow>,
    );
    const morphologyFilters = container.querySelectorAll("feMorphology");
    expect(morphologyFilters.length).toBe(5);
  });

  it('renders zero ripple rings when animated="static" (also the reduced-motion path)', () => {
    const { container } = render(
      <MetisGlow animated="static">
        <MetisMark />
      </MetisGlow>,
    );
    const morphologyFilters = container.querySelectorAll("feMorphology");
    expect(morphologyFilters.length).toBe(0);
  });

  it("respects the intensity prop by setting CSS opacity on the wrapper", () => {
    const { container } = render(
      <MetisGlow intensity={0.5}>
        <MetisMark />
      </MetisGlow>,
    );
    const wrapper = container.querySelector(".metis-glow") as HTMLElement;
    expect(wrapper.style.opacity).toBe("0.5");
  });

  it("sizes the wrapper to the size prop (default 280)", () => {
    const { container } = render(
      <MetisGlow size={120}>
        <MetisMark />
      </MetisGlow>,
    );
    const wrapper = container.querySelector(".metis-glow") as HTMLElement;
    expect(wrapper.style.width).toBe("120px");
    expect(wrapper.style.height).toBe("120px");
  });
});
