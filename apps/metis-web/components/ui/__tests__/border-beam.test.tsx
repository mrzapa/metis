import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const borderBeamSpy = vi.fn();
const useReducedMotionSpy = vi.fn();

vi.mock("border-beam", () => ({
  BorderBeam: (props: { children: React.ReactNode } & Record<string, unknown>) => {
    borderBeamSpy(props);
    const { children, ...rest } = props;
    return (
      <div data-testid="upstream-border-beam" data-active={String(rest.active)}>
        {children}
      </div>
    );
  },
}));

vi.mock("motion/react", async () => {
  const actual = await vi.importActual<typeof import("motion/react")>("motion/react");
  return {
    ...actual,
    useReducedMotion: () => useReducedMotionSpy(),
  };
});

import { BorderBeam } from "../border-beam";

describe("BorderBeam", () => {
  beforeEach(() => {
    borderBeamSpy.mockClear();
    useReducedMotionSpy.mockReset();
  });

  it("renders children and forwards METIS defaults", () => {
    useReducedMotionSpy.mockReturnValue(false);

    render(
      <BorderBeam>
        <span data-testid="beam-child">hello</span>
      </BorderBeam>,
    );

    expect(screen.getByTestId("beam-child")).toHaveTextContent("hello");

    const props = borderBeamSpy.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(props.colorVariant).toBe("mono");
    expect(props.theme).toBe("dark");
    expect(props.size).toBe("md");
    expect(props.active).toBe(true);
  });

  it("pauses animation when the user prefers reduced motion", () => {
    useReducedMotionSpy.mockReturnValue(true);

    render(
      <BorderBeam>
        <span>content</span>
      </BorderBeam>,
    );

    const props = borderBeamSpy.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(props.active).toBe(false);
  });

  it("allows an explicit active override regardless of reduced motion", () => {
    useReducedMotionSpy.mockReturnValue(true);

    render(
      <BorderBeam active={true}>
        <span>content</span>
      </BorderBeam>,
    );

    const props = borderBeamSpy.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    expect(props.active).toBe(true);
  });
});
