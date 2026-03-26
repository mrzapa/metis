import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const blurTextSpy = vi.fn();
const shinyTextSpy = vi.fn();

vi.mock("@/components/vendor/react-bits/text/blur-text", () => ({
  BlurText: (props: { text: string }) => {
    blurTextSpy(props);
    return <p data-testid="blur-text-mock">{props.text}</p>;
  },
}));

vi.mock("@/components/vendor/react-bits/text/shiny-text", () => ({
  ShinyText: (props: { text: string }) => {
    shinyTextSpy(props);
    return <p data-testid="shiny-text-mock">{props.text}</p>;
  },
}));

const { HomeHeroAnimatedCopy } = await import("../home-hero-animated-copy");

describe("HomeHeroAnimatedCopy", () => {
  beforeEach(() => {
    blurTextSpy.mockClear();
    shinyTextSpy.mockClear();
  });

  it("renders blurred headline and shiny subline copy", () => {
    render(<HomeHeroAnimatedCopy />);

    expect(screen.getByTestId("home-hero-animated-copy")).toBeInTheDocument();
    expect(screen.getByTestId("blur-text-mock")).toHaveTextContent(
      "Local-first intelligence for every document orbit.",
    );
    expect(screen.getByTestId("shiny-text-mock")).toHaveTextContent(
      "Grounded retrieval. Quietly animated clarity.",
    );
  });

  it("passes subtle animation tuning props to vendored components", () => {
    render(<HomeHeroAnimatedCopy />);

    expect(blurTextSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "Local-first intelligence for every document orbit.",
        animateBy: "words",
        delay: 90,
        stepDuration: 0.3,
      }),
    );

    expect(shinyTextSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        text: "Grounded retrieval. Quietly animated clarity.",
        speed: 2.6,
        delay: 0.4,
        shineColor: "#f5f9ff",
      }),
    );
  });
});
