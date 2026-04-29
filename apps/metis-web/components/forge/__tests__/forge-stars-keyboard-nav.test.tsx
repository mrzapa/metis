import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { ForgeStarsKeyboardNav } from "../forge-stars-keyboard-nav";
import type { ForgeStar } from "@/lib/forge-stars";

const router = {
  push: vi.fn(),
  replace: vi.fn(),
  back: vi.fn(),
  forward: vi.fn(),
  refresh: vi.fn(),
  prefetch: vi.fn(),
};

vi.mock("next/navigation", () => ({
  useRouter: () => router,
}));

afterEach(() => {
  router.push.mockReset();
});

function makeStar(overrides: Partial<ForgeStar>): ForgeStar {
  return {
    id: "reranker",
    x: 0.79,
    y: 0.66,
    size: 1,
    name: "Reranker",
    pillar: "cortex",
    paletteRgb: [129, 220, 198],
    ...overrides,
  };
}

describe("<ForgeStarsKeyboardNav />", () => {
  it("renders nothing when there are no stars", () => {
    const { container } = render(<ForgeStarsKeyboardNav stars={[]} />);
    expect(container.firstChild).toBeNull();
  });

  it("exposes one focusable button per active technique under a nav landmark", () => {
    render(
      <ForgeStarsKeyboardNav
        stars={[
          makeStar({ id: "reranker", name: "Reranker" }),
          makeStar({
            id: "swarm-personas",
            name: "Swarm persona simulation",
            pillar: "cortex",
          }),
        ]}
      />,
    );

    const nav = screen.getByRole("navigation", { name: /active forge techniques/i });
    expect(nav).toBeTruthy();

    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(2);
    expect(buttons[0]).toHaveTextContent(/open reranker in the forge/i);
    expect(buttons[1]).toHaveTextContent(/open swarm persona simulation in the forge/i);
  });

  it("uses the visually-hidden Tailwind class so the canvas owns the visible layer", () => {
    render(<ForgeStarsKeyboardNav stars={[makeStar({ id: "reranker" })]} />);
    const nav = screen.getByTestId("forge-stars-keyboard-nav");
    // `sr-only` is the standard ""visually hidden but accessible to AT""
    // primitive in the project's Tailwind setup. The class gates the
    // reveal-on-focus reveal style underneath.
    expect(nav.className).toMatch(/\bsr-only\b/);
    expect(nav.className).toMatch(/\bfocus-within:not-sr-only\b/);
  });

  it("routes to /forge#<id> when a button is activated", () => {
    render(
      <ForgeStarsKeyboardNav
        stars={[makeStar({ id: "hebbian-edges", name: "Hebbian edge updates" })]}
      />,
    );
    const button = screen.getByRole("button", {
      name: /open hebbian edge updates in the forge/i,
    });
    fireEvent.click(button);
    expect(router.push).toHaveBeenCalledWith("/forge#hebbian-edges");
  });
});
