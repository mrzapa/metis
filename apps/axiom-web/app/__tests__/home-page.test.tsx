import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { default: HomePage } = await import("../page");

describe("Home page", () => {
  let getContextSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    // JSDOM does not implement canvas rendering APIs; return null to skip draw logic.
    getContextSpy = vi
      .spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockReturnValue(null);

    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe = vi.fn();
        unobserve = vi.fn();
        disconnect = vi.fn();
        takeRecords = vi.fn(() => []);
        root = null;
        rootMargin = "0px";
        thresholds: number[] = [];
      },
    );
  });

  afterEach(() => {
    getContextSpy.mockRestore();
    vi.unstubAllGlobals();
  });

  it("renders primary navigation links", () => {
    render(<HomePage />);

    expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute(
      "href",
      "/chat",
    );
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute(
      "href",
      "/settings",
    );
  });

  it("routes the landing CTA to chat", () => {
    render(<HomePage />);

    expect(
      screen.getByRole("link", { name: "Explore the constellation" }),
    ).toHaveAttribute("href", "/chat");
  });

  it("keeps the floating chat entry point", () => {
    render(<HomePage />);

    expect(screen.getByRole("link", { name: "Open chat" })).toHaveAttribute(
      "href",
      "/chat",
    );
  });
});