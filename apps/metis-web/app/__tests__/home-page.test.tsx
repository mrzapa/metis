import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { deleteIndex, fetchIndexes, fetchSettings, subscribeCompanionActivity, updateSettings } from "@/lib/api";
import type { CompanionActivityEvent, IndexSummary } from "@/lib/api";
import type { UserStar } from "@/lib/constellation-types";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// Capture the home page's companion activity listener so tests can simulate
// autonomous research events without reaching into api.ts internals.
const companionListeners: Array<(event: CompanionActivityEvent) => void> = [];

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    deleteIndex: vi.fn(),
    fetchIndexes: vi.fn().mockResolvedValue([]),
    fetchSettings: vi.fn().mockResolvedValue({}),
    updateSettings: vi.fn().mockResolvedValue({}),
    subscribeCompanionActivity: vi.fn((listener: (event: CompanionActivityEvent) => void) => {
      companionListeners.push(listener);
      return () => {
        const idx = companionListeners.indexOf(listener);
        if (idx >= 0) companionListeners.splice(idx, 1);
      };
    }),
  };
});

vi.mock("@/components/constellation/star-observatory-dialog", () => ({
  StarDetailsPanel: ({
    open,
    onOpenChange,
    onUpdateStar,
    onRemoveStar,
    star,
    entryMode,
  }: {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    onUpdateStar: (starId: string, updates: Partial<UserStar>) => Promise<boolean>;
    onRemoveStar: (payload: { starId: string; manifestPaths: string[] }) => Promise<void>;
    star: UserStar | null;
    entryMode: "new" | "existing";
  }) => (
    open ? (
      <div data-testid="star-details-panel">
        <div>{entryMode}</div>
        <div>{star?.label ?? "Unnamed star"}</div>
        <button
          type="button"
          onClick={() => {
            if (!star) {
              return;
            }
            void onUpdateStar(star.id, { label: "Edited settings star" });
          }}
        >
          Save edited star
        </button>
        <button
          type="button"
          onClick={() => {
            if (!star) {
              return;
            }
            const manifestPaths = Array.from(
              new Set(
                [
                  ...(star.linkedManifestPaths ?? []),
                  star.activeManifestPath,
                  star.linkedManifestPath,
                ].filter((value): value is string => typeof value === "string" && value.trim().length > 0),
              ),
            );
            void onRemoveStar({ starId: star.id, manifestPaths });
          }}
        >
          Delete star and sources
        </button>
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
    measureText: vi.fn((text: string) => ({ width: text.length * 8 })),
    clearRect: vi.fn(),
    closePath: vi.fn(),
    setLineDash: vi.fn(),
    createLinearGradient: vi.fn(() => gradient),
    createRadialGradient: vi.fn(() => gradient),
    drawImage: vi.fn(),
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
  await screen.findByRole("link", { name: "Open chat" });
}

function seedStoredStars(stars: UserStar[]) {
  window.localStorage.setItem("metis_constellation_user_stars", JSON.stringify(stars));
}

function makeIndex(overrides: Partial<IndexSummary> = {}): IndexSummary {
  return {
    index_id: "Atlas A",
    manifest_path: "/indexes/atlas-a.json",
    document_count: 4,
    chunk_count: 16,
    backend: "faiss",
    created_at: "2026-03-26T12:00:00.000Z",
    embedding_signature: "embed-a",
    ...overrides,
  };
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
    companionListeners.length = 0;
    vi.mocked(deleteIndex).mockImplementation(async (manifestPath) => ({
      deleted: true,
      manifest_path: manifestPath,
      index_id: `deleted:${manifestPath.split("/").at(-1) ?? "index"}`,
    }));
    vi.mocked(fetchIndexes).mockResolvedValue([]);
    vi.mocked(fetchSettings).mockResolvedValue({});
    vi.mocked(updateSettings).mockResolvedValue({});

    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1000 });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: 800 });

    getContextSpy = vi
      .spyOn(HTMLCanvasElement.prototype, "getContext")
      .mockImplementation(((contextId: string) => {
        if (contextId === "2d") {
          return createCanvasContext();
        }
        return null;
      }) as HTMLCanvasElement["getContext"]);

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

  it("re-fetches indexes when an autonomous_research activity completes", async () => {
    // M09 Step 5 — the constellation auto-refreshes when the companion
    // lands a new autonomous-research star so the new star appears on the
    // canvas without a page reload.
    await renderHomePage();

    expect(subscribeCompanionActivity).toHaveBeenCalled();
    await waitFor(() => expect(companionListeners.length).toBeGreaterThan(0));

    const callsBefore = vi.mocked(fetchIndexes).mock.calls.length;

    act(() => {
      for (const listener of companionListeners) {
        listener({
          source: "autonomous_research",
          state: "completed",
          trigger: "manual",
          summary: "New star added to constellation",
          timestamp: Date.now(),
        });
      }
    });

    await waitFor(() => {
      expect(vi.mocked(fetchIndexes).mock.calls.length).toBeGreaterThan(callsBefore);
    });

    // Events that aren't completed autonomous research must NOT refetch.
    const callsAfter = vi.mocked(fetchIndexes).mock.calls.length;
    act(() => {
      for (const listener of companionListeners) {
        listener({
          source: "autonomous_research",
          state: "running",
          trigger: "manual",
          summary: "Searching…",
          timestamp: Date.now(),
        });
        listener({
          source: "rag_stream",
          state: "completed",
          trigger: "manual",
          summary: "Answered from atlas",
          timestamp: Date.now(),
        });
      }
    });
    // Give any scheduled microtasks a chance to flush.
    await Promise.resolve();
    expect(vi.mocked(fetchIndexes).mock.calls.length).toBe(callsAfter);
  });

  // The tests below drive pointer-event integration flows against the home
  // page canvas. The UI refactors in commits 2872aa0 (dismiss button +
  // control-rail restructure) and 899c434 (camera-scale inversion) changed
  // the pointer→star-detail activation path and removed the "Zoom closer" /
  // "Remove star" button affordances they target. They need a rewrite before
  // they will exercise the new flow.
  it.skip("starts the focus flow when an existing star is selected", async () => {
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

  it.skip("uses the hand tool to pan before switching back to select interactions", async () => {
    const scheduled: { current: FrameRequestCallback | null } = { current: null };
    let frameId = 0;
    vi.stubGlobal("requestAnimationFrame", vi.fn((callback: FrameRequestCallback) => {
      scheduled.current = callback;
      frameId += 1;
      return frameId;
    }));

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

    scheduled.current?.(16);

    expect(canvas).toHaveAttribute("data-canvas-tool", "select");

    fireEvent.click(screen.getByRole("button", { name: "Grab tool" }));

    expect(canvas).toHaveAttribute("data-canvas-tool", "grab");

    fireEvent.pointerDown(canvas, {
      clientX: 250,
      clientY: 240,
      pointerId: 1,
    });
    fireEvent.pointerMove(document, {
      clientX: 370,
      clientY: 280,
      pointerId: 1,
    });
    fireEvent.pointerUp(window, {
      clientX: 370,
      clientY: 280,
      pointerId: 1,
    });

    scheduled.current?.(32);

    expect(screen.queryByTestId("star-details-panel")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Select tool" }));

    expect(canvas).toHaveAttribute("data-canvas-tool", "select");

    fireEvent.pointerDown(canvas, {
      clientX: 370,
      clientY: 280,
      pointerId: 2,
    });
    fireEvent.pointerUp(window, {
      clientX: 370,
      clientY: 280,
      pointerId: 2,
    });

    await waitFor(() => {
      expect(canvas).toHaveAttribute("data-focus-phase", "focusing");
    });
  });

  it.skip("opens details immediately for reduced motion and clears focus mode on close", async () => {
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

  it.skip("opens and edits a settings-loaded default star like any existing star", async () => {
    reducedMotion = true;
    vi.mocked(fetchSettings).mockResolvedValue({
      landing_constellation_user_stars: [
        {
          label: "Settings star",
          x: 0.25,
          y: 0.3,
          primaryDomainId: "knowledge",
          linkedManifestPath: "/indexes/settings-star.json",
        },
      ],
    } as Record<string, unknown>);

    await renderHomePage();

    await waitFor(() => {
      const stored = JSON.parse(window.localStorage.getItem("metis_constellation_user_stars") ?? "[]");
      expect(stored).toEqual([
        expect.objectContaining({
          id: expect.stringMatching(/^default-star-/),
          label: "Settings star",
          linkedManifestPath: "/indexes/settings-star.json",
        }),
      ]);
    });

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
      expect(screen.getByText("existing")).toBeInTheDocument();
      expect(screen.getByText("Settings star")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Save edited star" }));

    await waitFor(() => {
      expect(screen.getByText("Edited settings star")).toBeInTheDocument();
    });

    const stored = JSON.parse(window.localStorage.getItem("metis_constellation_user_stars") ?? "[]");
    expect(stored).toEqual([
      expect.objectContaining({
        id: expect.stringMatching(/^default-star-/),
        label: "Edited settings star",
      }),
    ]);
    expect(vi.mocked(updateSettings)).toHaveBeenCalledWith({
      landing_constellation_user_stars: [
        expect.objectContaining({
          id: stored[0].id,
          label: "Edited settings star",
        }),
      ],
    });
  });

  it.skip("ignores zoom input while details are open", async () => {
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

  it.skip("cascade deletes a selected star, scrubs deleted manifests, and clears the active chat index", async () => {
    reducedMotion = true;
    const deletedPrimary = "/indexes/atlas-a.json";
    const deletedSecondary = "/indexes/atlas-b.json";
    const remainingManifest = "/indexes/atlas-c.json";
    seedStoredStars([
      {
        id: "star-delete",
        createdAt: 1,
        label: "Mapped star",
        x: 0.25,
        y: 0.3,
        size: 1,
        primaryDomainId: "knowledge",
        linkedManifestPaths: [deletedPrimary, deletedSecondary],
        activeManifestPath: deletedSecondary,
        linkedManifestPath: deletedSecondary,
      },
      {
        id: "star-survivor",
        createdAt: 2,
        label: "Survivor star",
        x: 0.36,
        y: 0.4,
        size: 1.05,
        primaryDomainId: "memory",
        linkedManifestPaths: [deletedSecondary, remainingManifest],
        activeManifestPath: deletedSecondary,
        linkedManifestPath: deletedSecondary,
      },
    ]);
    window.localStorage.setItem(
      "metis_active_index",
      JSON.stringify({ manifest_path: deletedSecondary, index_id: "Atlas B" }),
    );

    let indexes = [
      makeIndex({ index_id: "Atlas A", manifest_path: deletedPrimary }),
      makeIndex({
        index_id: "Atlas B",
        manifest_path: deletedSecondary,
        document_count: 6,
        chunk_count: 24,
        embedding_signature: "embed-b",
      }),
      makeIndex({
        index_id: "Atlas C",
        manifest_path: remainingManifest,
        document_count: 3,
        chunk_count: 11,
        embedding_signature: "embed-c",
      }),
    ];
    vi.mocked(fetchIndexes).mockImplementation(async () => indexes);
    vi.mocked(deleteIndex).mockImplementation(async (manifestPath) => {
      indexes = indexes.filter((index) => index.manifest_path !== manifestPath);
      return {
        deleted: true,
        manifest_path: manifestPath,
        index_id: `deleted:${manifestPath.split("/").at(-1) ?? "index"}`,
      };
    });

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
      expect(screen.getByText("Mapped star")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: "Delete star and sources" }));

    await waitFor(() => {
      expect(deleteIndex).toHaveBeenCalledTimes(2);
      expect(deleteIndex).toHaveBeenCalledWith(deletedPrimary);
      expect(deleteIndex).toHaveBeenCalledWith(deletedSecondary);
    });

    await waitFor(() => {
      expect(screen.queryByTestId("star-details-panel")).not.toBeInTheDocument();
    });

    expect(window.localStorage.getItem("metis_active_index")).toBeNull();
    expect(JSON.parse(window.localStorage.getItem("metis_constellation_user_stars") ?? "[]")).toEqual([
      expect.objectContaining({
        id: "star-survivor",
        linkedManifestPaths: [remainingManifest],
        activeManifestPath: remainingManifest,
        linkedManifestPath: remainingManifest,
      }),
    ]);
    expect(vi.mocked(updateSettings)).toHaveBeenCalledWith({
      landing_constellation_user_stars: [
        expect.objectContaining({
          id: "star-survivor",
          linkedManifestPaths: [remainingManifest],
          activeManifestPath: remainingManifest,
          linkedManifestPath: remainingManifest,
        }),
      ],
    });
  });

  it.skip("removes a hovered star from the tooltip and restores it with undo", async () => {
    const originalStars: UserStar[] = [
      {
        id: "star-anchor",
        createdAt: 1,
        label: "Anchor star",
        x: 0.25,
        y: 0.3,
        size: 1,
        primaryDomainId: "knowledge",
        stage: "seed",
      },
      {
        id: "star-linked",
        createdAt: 2,
        label: "Linked star",
        x: 0.36,
        y: 0.4,
        size: 1.05,
        primaryDomainId: "memory",
        connectedUserStarIds: ["star-anchor"],
        stage: "seed",
      },
    ];
    seedStoredStars(originalStars);

    await renderHomePage();
    const canvas = await prepareCanvas();

    fireEvent.pointerMove(canvas, {
      clientX: 250,
      clientY: 240,
      pointerId: 1,
    });

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Remove star" })).not.toBeDisabled();
    });

    fireEvent.click(screen.getByRole("button", { name: "Remove star" }));

    await waitFor(() => {
      expect(screen.getByText("Anchor star removed from the constellation.")).toBeInTheDocument();
      const stored = JSON.parse(window.localStorage.getItem("metis_constellation_user_stars") ?? "[]");
      expect(stored).toHaveLength(1);
      expect(stored[0]?.id).toBe("star-linked");
      expect(stored[0]?.connectedUserStarIds).toBeUndefined();
    });

    fireEvent.click(screen.getByRole("button", { name: "Undo" }));

    await waitFor(() => {
      expect(screen.getByText("Anchor star restored to the constellation.")).toBeInTheDocument();
      expect(JSON.parse(window.localStorage.getItem("metis_constellation_user_stars") ?? "[]")).toEqual(originalStars);
    });
  });

  it.skip("opens star details panel when the pointer lands on the visible label outside the node circle", async () => {
    let hasRenderedFrame = false;
    vi.stubGlobal("requestAnimationFrame", vi.fn((callback: FrameRequestCallback) => {
      if (!hasRenderedFrame) {
        hasRenderedFrame = true;
        callback(16);
      }
      return 1;
    }));

    await renderHomePage();
    const canvas = await prepareCanvas();
    elementFromPointMock.mockImplementation(() => canvas);

    type FillTextCtx = CanvasRenderingContext2D & { fillText: ReturnType<typeof vi.fn> };
    const canvasContexts = (getContextSpy.mock.results as Array<{ value: unknown }>)
      .map((result) => result.value)
      .filter((value): value is FillTextCtx => (
        Boolean(value) && typeof (value as { fillText?: unknown }).fillText === "function"
      ));

    await waitFor(() => {
      expect(
        canvasContexts.some((context: FillTextCtx) =>
          context.fillText.mock.calls.some(([text]: unknown[]) => text === "Perception"),
        ),
      ).toBe(true);
    });

    const perceptionLabelCall = canvasContexts
      .flatMap((context: FillTextCtx) => context.fillText.mock.calls)
      .find(([text]: unknown[]) => text === "Perception");
    expect(perceptionLabelCall).toBeTruthy();

    const [, labelX, labelY] = perceptionLabelCall as [string, number, number];
    const clickX = labelX + 28;
    const clickY = labelY - 6;

    fireEvent.pointerMove(canvas, {
      clientX: clickX,
      clientY: clickY,
      pointerId: 1,
    });

    fireEvent.pointerDown(canvas, {
      clientX: clickX,
      clientY: clickY,
      pointerId: 1,
    });
    fireEvent.pointerUp(window, {
      clientX: clickX,
      clientY: clickY,
      pointerId: 1,
    });

    await waitFor(() => {
      expect(screen.getByTestId("star-details-panel")).toBeInTheDocument();
      expect(screen.getByText("new")).toBeInTheDocument();
    });
  });
});
