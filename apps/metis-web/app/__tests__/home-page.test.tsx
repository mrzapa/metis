import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchIndexes } from "@/lib/api";

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

vi.mock("@/components/constellation/star-observatory-dialog", () => ({
  StarObservatoryDialog: () => null,
}));

const { default: HomePage } = await import("../page");

async function renderHomePage() {
  render(<HomePage />);
  await screen.findByRole("button", { name: "Seed indexed sources" });
}

describe("Home page", () => {
  let getContextSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    window.localStorage.clear();
    vi.mocked(fetchIndexes).mockResolvedValue([]);

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
    window.localStorage.clear();
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

  it("routes the landing CTA to the build section", async () => {
    await renderHomePage();

    expect(
      screen.getByRole("link", { name: "Build the constellation" }),
    ).toHaveAttribute("href", "#build-map");
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

    expect(screen.queryByRole("button", { name: "Add star" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Seed indexed sources" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Remove selected" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reset orbit" })).toBeDisabled();
    expect(screen.getByText("0 added stars")).toBeInTheDocument();
    expect(screen.getByText("0 indexed sources detected")).toBeInTheDocument();
    expect(screen.getByText("0 sources ready to map")).toBeInTheDocument();
    expect(screen.getByText("0 attachments in orbit")).toBeInTheDocument();
    expect(screen.getAllByText(/Follow the faculty ring/i).length).toBeGreaterThan(0);
    expect(
      screen.getByText(/Each star opens its own observatory/i),
    ).toBeInTheDocument();
  });

  it("maps detected indexes into orbit from the home controls", async () => {
    vi.mocked(fetchIndexes).mockResolvedValue([
      {
        index_id: "Orbit dossier",
        manifest_path: "/tmp/orbit-dossier.json",
        document_count: 3,
        chunk_count: 12,
        backend: "faiss",
        created_at: "2026-03-26T12:00:00.000Z",
      },
    ]);

    await renderHomePage();

    await waitFor(() => {
      expect(screen.getByText("1 indexed source detected")).toBeInTheDocument();
      expect(screen.getByText("1 source ready to map")).toBeInTheDocument();
      expect(screen.getByRole("button", { name: "Seed indexed sources" })).not.toBeDisabled();
    });

    fireEvent.click(screen.getByRole("button", { name: "Seed indexed sources" }));

    await waitFor(() => {
      expect(screen.getByText(/1(\/\d+)? added stars/)).toBeInTheDocument();
      expect(screen.getByText("0 sources ready to map")).toBeInTheDocument();
      expect(screen.getByText("1 attachment in orbit")).toBeInTheDocument();
    });

    await waitFor(() => {
      const stored = window.localStorage.getItem("metis_constellation_user_stars");
      expect(stored).not.toBeNull();
      expect(JSON.parse(stored ?? "[]")).toEqual(
        expect.arrayContaining([
          expect.objectContaining({
            label: "Orbit dossier",
            primaryDomainId: "knowledge",
            stage: "seed",
            linkedManifestPath: "/tmp/orbit-dossier.json",
          }),
        ]),
      );
    });
  });
});
