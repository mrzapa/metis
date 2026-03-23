import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const particlesSpy = vi.fn();
const useReducedMotionSpy = vi.fn();

vi.mock("@tsparticles/react", () => ({
  default: (props: unknown) => {
    particlesSpy(props);
    return <div data-testid="home-space-particles" />;
  },
  initParticlesEngine: vi.fn(async () => {}),
}));

vi.mock("@tsparticles/slim", () => ({
  loadSlim: vi.fn(async () => {}),
}));

vi.mock("motion/react", async () => {
  const actual = await vi.importActual<typeof import("motion/react")>("motion/react");
  return {
    ...actual,
    useReducedMotion: () => useReducedMotionSpy(),
  };
});

import { SpaceAtmosphere } from "../space-atmosphere";

describe("SpaceAtmosphere", () => {
  beforeEach(() => {
    particlesSpy.mockClear();
    useReducedMotionSpy.mockReset();
  });

  it("renders a non-interactive tsParticles background layer", async () => {
    useReducedMotionSpy.mockReturnValue(false);

    render(<SpaceAtmosphere />);

    await waitFor(() => {
      expect(screen.getByTestId("home-space-particles")).toBeInTheDocument();
    });

    const latestCall = particlesSpy.mock.calls.at(-1)?.[0] as {
      options: {
        fullScreen: { enable: boolean };
        interactivity: {
          events: {
            onHover: { enable: boolean };
            onClick: { enable: boolean };
          };
        };
        particles: {
          move: { enable: boolean };
        };
      };
    };

    expect(latestCall).toBeDefined();
    expect(latestCall.options.fullScreen.enable).toBe(false);
    expect(latestCall.options.interactivity.events.onHover.enable).toBe(false);
    expect(latestCall.options.interactivity.events.onClick.enable).toBe(false);
    expect(latestCall.options.particles.move.enable).toBe(true);
    expect(screen.getByTestId("shooting-stars-layer")).toBeInTheDocument();
  });

  it("disables particle motion when reduced motion is requested", async () => {
    useReducedMotionSpy.mockReturnValue(true);

    render(<SpaceAtmosphere />);

    await waitFor(() => {
      expect(screen.getByTestId("home-space-particles")).toBeInTheDocument();
    });

    const latestCall = particlesSpy.mock.calls.at(-1)?.[0] as {
      options: {
        fpsLimit: number;
        particles: {
          number: { value: number };
          move: { enable: boolean };
          opacity: { animation: { enable: boolean } };
          twinkle: { particles: { enable: boolean } };
        };
      };
    };

    expect(latestCall.options.fpsLimit).toBe(30);
    expect(latestCall.options.particles.number.value).toBe(48);
    expect(latestCall.options.particles.move.enable).toBe(false);
    expect(latestCall.options.particles.opacity.animation.enable).toBe(false);
    expect(latestCall.options.particles.twinkle.particles.enable).toBe(false);
    expect(screen.queryByTestId("shooting-stars-layer")).not.toBeInTheDocument();
  });
});
