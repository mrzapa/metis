import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchIndexes: vi.fn().mockResolvedValue([]),
    fetchSettings: vi.fn().mockResolvedValue({}),
    updateSettings: vi.fn().mockResolvedValue({}),
  };
});

const { default: HomePage } = await import("../page");

async function renderHomePage() {
  render(<HomePage />);
  await waitFor(() => {
    expect(screen.getByRole("button", { name: "Map library" })).not.toBeDisabled();
  });
}

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

  it("renders primary navigation links", async () => {
    await renderHomePage();

    expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute(
      "href",
      "/chat",
    );
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute(
      "href",
      "/settings",
    );
  });

  it("routes the landing CTA to chat", async () => {
    await renderHomePage();

    expect(
      screen.getByRole("link", { name: "Explore the constellation" }),
    ).toHaveAttribute("href", "/chat");
  });

  it("keeps the floating chat entry point", async () => {
    await renderHomePage();

    expect(screen.getByRole("link", { name: "Open chat" })).toHaveAttribute(
      "href",
      "/chat",
    );
  });

  it("renders constellation growth controls", async () => {
    await renderHomePage();

    expect(screen.getByRole("button", { name: "Add star" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Map library" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Remove selected" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reset added" })).toBeDisabled();
    expect(screen.getByText("0 added stars")).toBeInTheDocument();
  });
});