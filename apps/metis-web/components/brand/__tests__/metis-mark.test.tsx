import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { MetisMark } from "../metis-mark";

describe("<MetisMark>", () => {
  it("renders an SVG with the master 0 0 1000 1000 viewBox", () => {
    const { container } = render(<MetisMark />);
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
    expect(svg?.getAttribute("viewBox")).toBe("0 0 1000 1000");
  });

  it("uses currentColor on the path so it inherits color from CSS", () => {
    const { container } = render(<MetisMark />);
    const path = container.querySelector("path");
    expect(path?.getAttribute("fill")).toBe("currentColor");
  });

  it("renders the path with fill-rule=evenodd (M-shape negative space)", () => {
    const { container } = render(<MetisMark />);
    const path = container.querySelector("path");
    expect(path?.getAttribute("fill-rule")).toBe("evenodd");
  });

  it("respects the size prop on width and height", () => {
    const { container } = render(<MetisMark size={64} />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("width")).toBe("64");
    expect(svg?.getAttribute("height")).toBe("64");
  });

  it("defaults to size 32 when no size prop is given", () => {
    const { container } = render(<MetisMark />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("width")).toBe("32");
    expect(svg?.getAttribute("height")).toBe("32");
  });

  it("becomes a named role=img when title prop is set", () => {
    render(<MetisMark title="Metis home" />);
    // RTL's getByRole understands SVG <title> as the accessible name.
    const svg = screen.getByRole("img", { name: /metis home/i });
    expect(svg).not.toBeNull();
  });

  it("is aria-hidden when no title prop is set (decorative)", () => {
    const { container } = render(<MetisMark />);
    const svg = container.querySelector("svg");
    expect(svg?.getAttribute("aria-hidden")).toBe("true");
  });

  it("merges className without losing the default brand color class", () => {
    const { container } = render(<MetisMark className="custom-class" />);
    const svg = container.querySelector("svg");
    const cls = svg?.getAttribute("class") ?? "";
    expect(cls).toContain("custom-class");
    // The default class places the mark at var(--brand-mark) so the
    // surrounding text color isn't accidentally inherited.
    expect(cls).toContain("brand-mark");
  });
});
