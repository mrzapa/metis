import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchIndexes, fetchSettings, fetchStarClusters, updateSettings } from "@/lib/api";
import type { StarClusterAssignment } from "@/lib/api";

const SETTINGS_KEY = "landing_constellation_user_stars";
const MIGRATED_KEY = "m24_layout_migrated_v1";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchIndexes: vi.fn().mockResolvedValue([]),
    fetchSettings: vi.fn().mockResolvedValue({}),
    fetchStarClusters: vi.fn().mockResolvedValue([]),
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
    drawImage: vi.fn(),
    font: "",
    textAlign: "center",
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 1,
    lineDashOffset: 0,
  } as unknown as CanvasRenderingContext2D;
}

function makeClusterAssignment(starId: string): StarClusterAssignment {
  return {
    star_id: starId,
    cluster_id: 0,
    x: 0.1,
    y: 0.2,
    cluster_label: "test cluster",
  };
}

describe("Home page migration toast", () => {
  let getContextSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    window.localStorage.clear();

    // Seed a single user star via the settings payload — the home-page
    // hydrates `userStars` from `fetchSettings` on mount, so this gives
    // us a non-empty `userStars.length` for the toast effect.
    vi.mocked(fetchSettings).mockResolvedValue({
      [SETTINGS_KEY]: [
        {
          id: "toast-star",
          x: 0.25,
          y: 0.3,
          size: 1,
          createdAt: 1,
          label: "Toast star",
          primaryDomainId: "knowledge",
        },
      ],
    } as Record<string, unknown>);
    vi.mocked(fetchIndexes).mockResolvedValue([]);
    vi.mocked(updateSettings).mockResolvedValue({});

    // Default: clusters returns at least one assignment so the toast
    // gating predicate (`clusters.length > 0`) is satisfied.
    vi.mocked(fetchStarClusters).mockResolvedValue([
      makeClusterAssignment("toast-star"),
    ]);

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
        matches: query.includes("prefers-reduced-motion"),
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );
  });

  afterEach(() => {
    getContextSpy.mockRestore();
    window.localStorage.clear();
    vi.unstubAllGlobals();
  });

  it("fires toast on first mount when localStorage key is absent and clusters/stars exist", async () => {
    // localStorage starts empty → migration key is absent → toast fires.
    render(<HomePage />);
    await screen.findByRole("link", { name: "Open chat" });

    // Toast renders the "Undo for this session" action button alongside
    // the migration message.
    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Undo for this session" }),
      ).toBeInTheDocument();
    });
    expect(
      screen.getByText("Your constellation has been re-laid out by content."),
    ).toBeInTheDocument();

    // Side-effect: the migration flag is now persisted.
    expect(window.localStorage.getItem(MIGRATED_KEY)).not.toBeNull();
  });

  it("does NOT fire toast on subsequent mount when localStorage key is present", async () => {
    // Pre-seed the migration flag — the toast effect must short-circuit.
    window.localStorage.setItem(MIGRATED_KEY, "1234567890");

    render(<HomePage />);
    await screen.findByRole("link", { name: "Open chat" });

    // Give the cluster fetch + state effects time to settle, then assert
    // the toast did NOT render.
    await waitFor(() => {
      expect(vi.mocked(fetchStarClusters)).toHaveBeenCalled();
    });
    // A microtask flush gives the dependent useEffect a chance to run.
    await Promise.resolve();
    await Promise.resolve();

    expect(
      screen.queryByRole("button", { name: "Undo for this session" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Your constellation has been re-laid out by content."),
    ).not.toBeInTheDocument();

    // The flag must remain at the value we seeded (the effect must not
    // overwrite it).
    expect(window.localStorage.getItem(MIGRATED_KEY)).toBe("1234567890");
  });
});
