import { render, screen, act } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import {
  OBSERVATORY_EXIT_DURATION_MS,
  OBSERVATORY_ORBITAL_MIN_WIDTH_PX,
  OBSERVATORY_SLOT_ORDER,
  ObservatoryOrbitalLayout,
  SLOT_ENTRANCE_STAGGER_MS,
  isOrbitalViewport,
} from "../observatory-orbital-layout";
import { CONSTELLATION_DIVE_DURATION_MS } from "@/hooks/use-constellation-camera";

const FLUSH_FRAME = async () => {
  await act(async () => {
    await new Promise<void>((resolve) => {
      requestAnimationFrame(() => resolve());
    });
  });
};

describe("ObservatoryOrbitalLayout", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders all four slots in ring order", () => {
    render(
      <ObservatoryOrbitalLayout
        open
        reducedMotion
        slots={{
          top: <div data-testid="slot-top-content">Top</div>,
          right: <div data-testid="slot-right-content">Right</div>,
          bottom: <div data-testid="slot-bottom-content">Bottom</div>,
          left: <div data-testid="slot-left-content">Left</div>,
        }}
      />,
    );

    const layout = screen.getByTestId("observatory-orbital-layout");
    const rendered = Array.from(layout.querySelectorAll<HTMLElement>("[data-slot]"))
      .filter((el) => el.dataset.slot !== "center")
      .map((el) => el.dataset.slot);

    // Preserves the documented ring order so the stagger is deterministic.
    expect(rendered).toEqual([...OBSERVATORY_SLOT_ORDER]);

    expect(screen.getByTestId("slot-top-content")).toBeTruthy();
    expect(screen.getByTestId("slot-right-content")).toBeTruthy();
    expect(screen.getByTestId("slot-bottom-content")).toBeTruthy();
    expect(screen.getByTestId("slot-left-content")).toBeTruthy();
  });

  it("marks empty slots so callers can target them without hardcoding mapping", () => {
    render(
      <ObservatoryOrbitalLayout
        open
        reducedMotion
        slots={{ top: <span>Top only</span> }}
      />,
    );

    const layout = screen.getByTestId("observatory-orbital-layout");
    const filled = layout.querySelector('[data-slot="top"]');
    const empty = layout.querySelector('[data-slot="right"]');

    expect(filled?.getAttribute("data-slot-filled")).toBe("true");
    expect(empty?.getAttribute("data-slot-filled")).toBe("false");
  });

  it("reduced motion skips the offstage → onstage animation", () => {
    render(
      <ObservatoryOrbitalLayout
        open
        reducedMotion
        slots={{ top: <div>T</div> }}
      />,
    );

    const slot = screen.getByTestId("observatory-orbital-layout").querySelector<HTMLElement>('[data-slot="top"]');
    expect(slot?.style.transition).toBe("none");
    expect(slot?.style.opacity).toBe("1");
  });

  it("staggered entrance uses camera dive duration + 80ms per ring", async () => {
    render(
      <ObservatoryOrbitalLayout
        open
        slots={{
          top: <div>T</div>,
          right: <div>R</div>,
          bottom: <div>B</div>,
          left: <div>L</div>,
        }}
      />,
    );
    // Let the mount → open frame flip through.
    await FLUSH_FRAME();

    const layout = screen.getByTestId("observatory-orbital-layout");
    const slots = OBSERVATORY_SLOT_ORDER.map(
      (name) => layout.querySelector<HTMLElement>(`[data-slot="${name}"]`),
    );

    slots.forEach((slot, index) => {
      expect(slot).toBeTruthy();
      const transition = slot!.style.transition;
      expect(transition).toContain(`${CONSTELLATION_DIVE_DURATION_MS}ms`);
      expect(transition).toContain(`${index * SLOT_ENTRANCE_STAGGER_MS}ms`);
    });
  });

  it("exit animation runs a shortened duration on the same curve", async () => {
    const { rerender } = render(
      <ObservatoryOrbitalLayout open slots={{ top: <div>T</div> }} />,
    );
    await FLUSH_FRAME();

    rerender(<ObservatoryOrbitalLayout open={false} slots={{ top: <div>T</div> }} />);
    // `open` prop changes trigger a re-render but the slot style recomputes
    // synchronously because we read `visible` during the render pass.
    await FLUSH_FRAME();

    const slot = screen.getByTestId("observatory-orbital-layout").querySelector<HTMLElement>('[data-slot="top"]');
    expect(slot?.style.transition).toContain(`${OBSERVATORY_EXIT_DURATION_MS}ms`);
    expect(slot?.style.opacity).toBe("0");
  });

  it("isOrbitalViewport treats the breakpoint threshold inclusively", () => {
    expect(isOrbitalViewport(OBSERVATORY_ORBITAL_MIN_WIDTH_PX)).toBe(true);
    expect(isOrbitalViewport(OBSERVATORY_ORBITAL_MIN_WIDTH_PX - 1)).toBe(false);
  });
});
