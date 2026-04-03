import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchIndexes, fetchSettings, updateSettings } from "@/lib/api";
import type { UserStar } from "@/lib/constellation-types";

const SETTINGS_KEY = "landing_constellation_user_stars";
const STORAGE_KEY = "metis_constellation_user_stars";

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
    font: "",
    textAlign: "center",
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 1,
    lineDashOffset: 0,
  } as unknown as CanvasRenderingContext2D;
}

function readStoredStars(): UserStar[] {
  return JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "[]") as UserStar[];
}

async function renderHomePage() {
  render(<HomePage />);
  await screen.findByRole("button", { name: "Seed indexed sources" });
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

describe("Home page real dialog flow", () => {
  let getContextSpy: ReturnType<typeof vi.spyOn>;
  let elementFromPointMock: ReturnType<typeof vi.fn>;
  let reducedMotion = false;

  beforeEach(() => {
    reducedMotion = false;
    window.localStorage.clear();
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

  it("opens and edits a settings-loaded default star through the real dialog flow", async () => {
    reducedMotion = true;
    vi.mocked(fetchSettings).mockResolvedValue({
      [SETTINGS_KEY]: [
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
      expect(readStoredStars()).toEqual([
        expect.objectContaining({
          id: expect.stringMatching(/^default-star-/),
          label: "Settings star",
          linkedManifestPath: "/indexes/settings-star.json",
        }),
      ]);
    });

    const [loadedStar] = readStoredStars();
    expect(loadedStar).toEqual(
      expect.objectContaining({
        id: expect.stringMatching(/^default-star-/),
        createdAt: expect.any(Number),
        linkedManifestPaths: ["/indexes/settings-star.json"],
      }),
    );

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

    const labelInput = await screen.findByDisplayValue("Settings star");
    const notesInput = screen.getByPlaceholderText(/Extra reminders, caveats, or context/i);

    fireEvent.change(labelInput, {
      target: { value: "Edited settings star" },
    });
    fireEvent.change(notesInput, {
      target: { value: "Now editable through the page dialog." },
    });

    fireEvent.click(screen.getByRole("button", { name: "Save meaning" }));

    await waitFor(() => {
      expect(screen.getByText(/Star details updated/i)).toBeInTheDocument();
      expect(screen.getByDisplayValue("Edited settings star")).toBeInTheDocument();
      expect(screen.getByDisplayValue("Now editable through the page dialog.")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(readStoredStars()).toEqual([
        expect.objectContaining({
          id: loadedStar.id,
          createdAt: loadedStar.createdAt,
          label: "Edited settings star",
          notes: "Now editable through the page dialog.",
          linkedManifestPath: "/indexes/settings-star.json",
          linkedManifestPaths: ["/indexes/settings-star.json"],
        }),
      ]);
    });

    expect(vi.mocked(updateSettings)).toHaveBeenCalledTimes(1);
    expect(vi.mocked(updateSettings)).toHaveBeenLastCalledWith({
      [SETTINGS_KEY]: [
        expect.objectContaining({
          id: loadedStar.id,
          createdAt: loadedStar.createdAt,
          label: "Edited settings star",
          notes: "Now editable through the page dialog.",
          linkedManifestPath: "/indexes/settings-star.json",
          linkedManifestPaths: ["/indexes/settings-star.json"],
        }),
      ],
    });
  });
});