import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CatalogueFilterPanel } from "../catalogue-filter-panel";
import {
  CATALOGUE_FILTER_DEFAULT,
  CATALOGUE_FILTER_MAX_MAGNITUDE,
  type CatalogueFilterState,
} from "@/lib/star-catalogue";

function makeState(overrides: Partial<CatalogueFilterState> = {}): CatalogueFilterState {
  return {
    families: overrides.families ?? new Set(),
    maxMagnitude: overrides.maxMagnitude ?? CATALOGUE_FILTER_MAX_MAGNITUDE,
  };
}

describe("CatalogueFilterPanel", () => {
  it("renders one chip per spectral family plus an All chip", () => {
    render(
      <CatalogueFilterPanel
        state={CATALOGUE_FILTER_DEFAULT}
        onStateChange={vi.fn()}
      />,
    );
    for (const family of ["O", "B", "A", "F", "G", "K", "M"]) {
      expect(screen.getByRole("button", { name: family })).toBeTruthy();
    }
    expect(screen.getByRole("button", { name: /all/i })).toBeTruthy();
  });

  it("All chip is pressed when no families are selected", () => {
    render(
      <CatalogueFilterPanel
        state={CATALOGUE_FILTER_DEFAULT}
        onStateChange={vi.fn()}
      />,
    );
    expect(
      screen
        .getByRole("button", { name: /all/i })
        .getAttribute("aria-pressed"),
    ).toBe("true");
  });

  it("a family chip is pressed when that family is in state", () => {
    render(
      <CatalogueFilterPanel
        state={makeState({ families: new Set(["G"]) })}
        onStateChange={vi.fn()}
      />,
    );
    expect(
      screen.getByRole("button", { name: "G" }).getAttribute("aria-pressed"),
    ).toBe("true");
    expect(
      screen.getByRole("button", { name: "M" }).getAttribute("aria-pressed"),
    ).toBe("false");
    expect(
      screen.getByRole("button", { name: /all/i }).getAttribute("aria-pressed"),
    ).toBe("false");
  });

  it("clicking a family chip adds it to state", () => {
    const onStateChange = vi.fn();
    render(
      <CatalogueFilterPanel state={CATALOGUE_FILTER_DEFAULT} onStateChange={onStateChange} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "G" }));
    expect(onStateChange).toHaveBeenCalledTimes(1);
    const next = onStateChange.mock.calls[0][0] as CatalogueFilterState;
    expect([...next.families]).toEqual(["G"]);
  });

  it("clicking a selected family chip removes it (toggle)", () => {
    const onStateChange = vi.fn();
    render(
      <CatalogueFilterPanel
        state={makeState({ families: new Set(["G", "K"]) })}
        onStateChange={onStateChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "K" }));
    const next = onStateChange.mock.calls[0][0] as CatalogueFilterState;
    expect([...next.families].sort()).toEqual(["G"]);
  });

  it("clicking All clears the family selection", () => {
    const onStateChange = vi.fn();
    render(
      <CatalogueFilterPanel
        state={makeState({ families: new Set(["G", "K"]) })}
        onStateChange={onStateChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /all/i }));
    const next = onStateChange.mock.calls[0][0] as CatalogueFilterState;
    expect(next.families.size).toBe(0);
  });

  it("renders the magnitude slider with the current value", () => {
    render(
      <CatalogueFilterPanel
        state={makeState({ maxMagnitude: 4.5 })}
        onStateChange={vi.fn()}
      />,
    );
    const slider = screen.getByRole("slider", { name: /magnitude/i });
    expect((slider as HTMLInputElement).valueAsNumber).toBe(4.5);
  });

  it("changing the slider fires onStateChange with new max magnitude", () => {
    const onStateChange = vi.fn();
    render(
      <CatalogueFilterPanel
        state={CATALOGUE_FILTER_DEFAULT}
        onStateChange={onStateChange}
      />,
    );
    const slider = screen.getByRole("slider", { name: /magnitude/i });
    fireEvent.change(slider, { target: { value: "3.5" } });
    const next = onStateChange.mock.calls[0][0] as CatalogueFilterState;
    expect(next.maxMagnitude).toBe(3.5);
  });

  it("Reset button restores the default state when filter is active", () => {
    const onStateChange = vi.fn();
    render(
      <CatalogueFilterPanel
        state={makeState({ families: new Set(["G"]), maxMagnitude: 3.0 })}
        onStateChange={onStateChange}
      />,
    );
    const reset = screen.getByRole("button", { name: /reset/i });
    fireEvent.click(reset);
    const next = onStateChange.mock.calls[0][0] as CatalogueFilterState;
    expect(next.families.size).toBe(0);
    expect(next.maxMagnitude).toBe(CATALOGUE_FILTER_MAX_MAGNITUDE);
  });

  it("Reset button is hidden when filter is at the default state", () => {
    render(
      <CatalogueFilterPanel
        state={CATALOGUE_FILTER_DEFAULT}
        onStateChange={vi.fn()}
      />,
    );
    expect(screen.queryByRole("button", { name: /reset/i })).toBeNull();
  });
});
