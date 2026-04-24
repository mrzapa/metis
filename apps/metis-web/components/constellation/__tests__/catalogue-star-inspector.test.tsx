import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CatalogueStarInspector } from "../catalogue-star-inspector";
import type { CatalogueStarInspectorStar } from "../catalogue-star-inspector";
import { generateStellarProfile } from "@/lib/landing-stars";

function makeCatalogueStar(
  overrides: Partial<CatalogueStarInspectorStar> = {},
): CatalogueStarInspectorStar {
  return {
    id: "metis-prime-s0-s0-17",
    name: null,
    profile: generateStellarProfile("metis-prime-s0-s0-17"),
    apparentMagnitude: 3.8,
    worldX: 0.12,
    worldY: -0.45,
    ...overrides,
  };
}

describe("CatalogueStarInspector", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <CatalogueStarInspector
        open={false}
        star={makeCatalogueStar()}
        addable
        onClose={vi.fn()}
        onPromote={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when star is null", () => {
    const { container } = render(
      <CatalogueStarInspector
        open
        star={null}
        addable
        onClose={vi.fn()}
        onPromote={vi.fn()}
      />,
    );
    expect(container.firstChild).toBeNull();
  });

  it("shows the catalogue name when provided", () => {
    render(
      <CatalogueStarInspector
        open
        star={makeCatalogueStar({ name: "Vega" })}
        addable
        onClose={vi.fn()}
        onPromote={vi.fn()}
      />,
    );
    expect(screen.getByText("Vega")).toBeTruthy();
  });

  it("falls back to 'Field star' with id suffix when name is null", () => {
    render(
      <CatalogueStarInspector
        open
        star={makeCatalogueStar({
          id: "metis-prime-s0-s0-17",
          name: null,
        })}
        addable
        onClose={vi.fn()}
        onPromote={vi.fn()}
      />,
    );
    const title = screen.getByTestId("catalogue-star-inspector-title");
    expect(title.textContent).toContain("Field star");
    expect(title.textContent).toContain("s0-17");
  });

  it("renders spectral class, temperature, luminosity, magnitude, archetype, coordinates", () => {
    const star = makeCatalogueStar({
      apparentMagnitude: 2.1,
      worldX: 1.234,
      worldY: -0.567,
    });
    render(
      <CatalogueStarInspector
        open
        star={star}
        addable
        onClose={vi.fn()}
        onPromote={vi.fn()}
      />,
    );
    expect(screen.getByText(/Spectral class/i)).toBeTruthy();
    expect(screen.getByText(/Temperature/i)).toBeTruthy();
    expect(screen.getByText(/Luminosity/i)).toBeTruthy();
    expect(screen.getByText(/Apparent magnitude/i)).toBeTruthy();
    expect(screen.getByText(/Archetype/i)).toBeTruthy();
    expect(screen.getByText(/Coordinates/i)).toBeTruthy();
    expect(screen.getByText(/2\.10/)).toBeTruthy();
    expect(screen.getByText(/1\.234.*−0\.567|1\.234.*-0\.567/)).toBeTruthy();
  });

  it("enables the promote button when addable is true and calls onPromote on click", () => {
    const onPromote = vi.fn();
    render(
      <CatalogueStarInspector
        open
        star={makeCatalogueStar()}
        addable
        onClose={vi.fn()}
        onPromote={onPromote}
      />,
    );
    const promote = screen.getByRole("button", { name: /promote/i });
    expect((promote as HTMLButtonElement).disabled).toBe(false);
    fireEvent.click(promote);
    expect(onPromote).toHaveBeenCalledTimes(1);
  });

  it("disables the promote button when not addable and shows a reason", () => {
    render(
      <CatalogueStarInspector
        open
        star={makeCatalogueStar()}
        addable={false}
        promoteDisabledReason="Too far from your constellation."
        onClose={vi.fn()}
        onPromote={vi.fn()}
      />,
    );
    const promote = screen.getByRole("button", { name: /promote/i });
    expect((promote as HTMLButtonElement).disabled).toBe(true);
    expect(promote.getAttribute("title")).toBe("Too far from your constellation.");
  });

  it("clicking the close button calls onClose", () => {
    const onClose = vi.fn();
    render(
      <CatalogueStarInspector
        open
        star={makeCatalogueStar()}
        addable
        onClose={onClose}
        onPromote={vi.fn()}
      />,
    );
    const close = screen.getByRole("button", { name: /close/i });
    fireEvent.click(close);
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("pressing Escape calls onClose", () => {
    const onClose = vi.fn();
    render(
      <CatalogueStarInspector
        open
        star={makeCatalogueStar()}
        addable
        onClose={onClose}
        onPromote={vi.fn()}
      />,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("does not react to Escape when closed", () => {
    const onClose = vi.fn();
    render(
      <CatalogueStarInspector
        open={false}
        star={makeCatalogueStar()}
        addable
        onClose={onClose}
        onPromote={vi.fn()}
      />,
    );
    fireEvent.keyDown(window, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
  });
});
