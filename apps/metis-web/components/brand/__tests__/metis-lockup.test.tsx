import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import { MetisLockup } from "../metis-lockup";

describe("<MetisLockup>", () => {
  it("renders the mark and the lowercase 'metis' wordmark", () => {
    const { container } = render(<MetisLockup />);
    expect(container.querySelector("svg")).not.toBeNull();
    expect(screen.getByText("metis")).not.toBeNull();
  });

  it("places the wordmark to the right by default (flex-row)", () => {
    const { container } = render(<MetisLockup />);
    const root = container.firstChild as HTMLElement;
    expect(root.className).toMatch(/flex-row/);
  });

  it('places the wordmark below when wordmarkPosition="below" (flex-col)', () => {
    const { container } = render(<MetisLockup wordmarkPosition="below" />);
    const root = container.firstChild as HTMLElement;
    expect(root.className).toMatch(/flex-col/);
  });

  it('renders a larger mark when size="lg"', () => {
    const { container } = render(<MetisLockup size="lg" />);
    const svg = container.querySelector("svg");
    // size="lg" should produce a 128 px mark (size="md" is 64).
    expect(svg?.getAttribute("width")).toBe("128");
  });
});
