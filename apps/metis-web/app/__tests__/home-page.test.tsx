import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchIndexes } from "@/lib/api";
import type { UserStar } from "@/lib/constellation-types";

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
  StarDetailsPanel: ({
    open,
    onOpenChange,
    star,
    entryMode,
  }: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    star: UserStar | null;
    entryMode: "new" | "existing";
  }) => (
    open ? (
      <div data-testid="star-details-panel">
        <div>{entryMode}</div>
        <div>{star?.label ?? "Unnamed star"}</div>
        <button type="button" onClick={() => onOpenChange(false)}>
          Close details
        </button>
      </div>
    ) : null
  ),
}));

const { default: HomePage } = await import("../page");

function createCanvasContext(): CanvasRenderingContext2D {
  const gradient = { addColorStop: vi.fn() };

  return {
    beginPath: vi.fn(),
    arc: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    fillRect: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    translate: vi.fn(),
    rotate: vi.fn(),
    scale: vi.fn(),
    fillText: vi.fn(),
    clearRect: vi.fn(),
    closePath: vi.fn(),
    setLineDash: vi.fn(),
    createLinearGradient: vi.fn(() => gradient),
    createRadialGradient: vi.fn(() => gradient),
    font: "",
    textAlign: "center",
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 1,
    lineDashOffset: 0,
  } as unknown as CanvasRenderingContext2D;
}

async function renderHomePage() {
  render(<HomePage />);
  await screen.findByRole("button", { name: "Seed indexed sources" });
}

function seedStoredStars(stars: UserStar[]) {
  window.localStorage.setItem("metis_constellation_user_stars", JSON.stringify(stars));
}

async function prepareCanvas() {
  const canvas = document.querySelector("canvas") as HTMLCanvasElement;
  expect(canvas).toBeTruthy();

  Object.defineProperty(canvas, "getBoundingClientRect", {
    configurable: true,
    value: () => ({
      x: 0,
      y: 0,
      left: 0,
      top: 0,
      width: 1000,
      height: 800,
      right: 1000,
      bottom: 800,
      toJSON: () => ({}),
    }),
  });
  canvas.setPointerCapture = vi.fn();

  return canvas;
}

describe("Home page", () => {
  let getContextSpy: ReturnType<typeof vi.spyOn>;
  let elementFromPointMock: ReturnType<typeof vi.fn>;
  let reducedMotion = false;

  beforeEach(() => {
    reducedMotion = false;
    window.localStorage.clear();
    vi.mocked(fetchIndexes).mockResolvedValue([]);

    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1000 });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 800 });

    getContextSpy = vi
      .spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockReturnValue(createCanvasContext());

    vi.stubGlobal("requestAnimationFrame", vi.fn(() => 1));
    vi.stubGlobal("cancelAnimationFrame", vi.fn());
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

    vi.stubGlobal(
      "matchMedia",
      vi.fn((query: string) => ({
        matches: query.includes("prefers-reduced-motion") ? reducedMotion : false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );

    elementFromPointMock = vi.fn(() => null);
    Object.defineProperty(document, "elementFromPoint", {
      configurable: true,
      value: elementFromPointMock,
    });
  });

  afterEach(() => {
    getContextSpy.mockRestore();
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("renders navigation and the floating chat link", async () => {
    await renderHomePage();

    expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute("href", "/chat");
    expect(screen.getByRole("link", { name: "Settings" })).toHaveAttribute("href", "/settings");
    expect(screen.getByRole("link", { name: "Open chat" })).toHaveAttribute("href", "/chat");
  });

  it("maps detected indexes into orbit from the home controls", async () => {
    vi.mocked(fetchIndexes).mockResolvedValue([
      {
        index_id: "Orbit dossier",
        manifest_path: "/tmp/orbit-dossier.json",
        document_count: 3,
        chunk_count: 12,
        backend: "faiss",
        embedding_signature: "embed-orbit",
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

  it("starts the focus flow when an existing star is selected", async () => {
    seedStoredStars([
      {
        id: "star-existing",
        createdAt: 1,
        label: "Existing star",
        x: 0.25,
        y: 0.3,
        size: 1,
        primaryDomainId: "knowledge",
      },
    ]);

    await renderHomePage();
    const canvas = await prepareCanvas();
    elementFromPointMock.mockImplementation(() => canvas);

    fireEvent.pointerDown(canvas, {
      clientX: 250,
      clientY: 240,
      pointerId: 1,
    });
    fireEvent.pointerUp(window, {
      clientX: 250,
      clientY: 240,
      pointerId: 1,
    });

    await waitFor(() => {
      expect(canvas).toHaveAttribute("data-focus-phase", "focusing");
    });

    expect(screen.queryByTestId("star-details-panel")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zoom closer" })).toBeDisabled();
  });

  it("opens details immediately for reduced motion and clears focus mode on close", async () => {
    reducedMotion = true;
    seedStoredStars([
      {
        id: "star-existing",
        createdAt: 1,
        label: "Existing star",
        x: 0.25,
        y: 0.3,
        size: 1,
        primaryDomainId: "knowledge",
      },
    ]);

    await renderHomePage();
    const canvas = await prepareCanvas();
    elementFromPointMock.mockImplementation(() => canvas);

    fireEvent.pointerDown(canvas, {
      clientX: 250,
      clientY: 240,
      pointerId: 1,
    });
    fireEvent.pointerUp(window, {
      clientX: 250,
      clientY: 240,
      pointerId: 1,
    });

    await waitFor(() => {
      expect(screen.getByTestId("star-details-panel")).toBeInTheDocument();
      expect(canvas).toHaveAttribute("data-focus-phase", "details-open");
    });

    fireEvent.click(screen.getByRole("button", { name: "Close details" }));

    await waitFor(() => {
      expect(screen.queryByTestId("star-details-panel")).not.toBeInTheDocument();
      expect(canvas).toHaveAttribute("data-focus-phase", "idle");
    });

    expect(screen.getByRole("button", { name: "Zoom closer" })).not.toBeDisabled();
  });

  it("ignores zoom input while details are open", async () => {
    reducedMotion = true;
    seedStoredStars([
      {
        id: "star-existing",
        createdAt: 1,
        label: "Existing star",
        x: 0.25,
        y: 0.3,
        size: 1,
        primaryDomainId: "knowledge",
      },
    ]);

    await renderHomePage();
    const canvas = await prepareCanvas();
    elementFromPointMock.mockImplementation(() => canvas);

    fireEvent.pointerDown(canvas, {
      clientX: 250,
      clientY: 240,
      pointerId: 1,
    });
    fireEvent.pointerUp(window, {
      clientX: 250,
      clientY: 240,
      pointerId: 1,
    });

    await waitFor(() => {
      expect(screen.getByTestId("star-details-panel")).toBeInTheDocument();
      expect(canvas).toHaveAttribute("data-focus-phase", "details-open");
    });

    const zoomValue = document.querySelector(".metis-zoom-pill-value")?.textContent;
    fireEvent.wheel(canvas, {
      clientX: 250,
      clientY: 240,
      deltaY: 120,
    });

    expect(document.querySelector(".metis-zoom-pill-value")?.textContent).toBe(zoomValue);
    expect(canvas).toHaveAttribute("data-focus-phase", "details-open");
  });
});
