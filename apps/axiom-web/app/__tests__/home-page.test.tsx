import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("motion/react", () => ({
  motion: {
    div: ({ children, ...props }: React.HTMLAttributes<HTMLDivElement>) => (
      <div {...props}>{children}</div>
    ),
    section: ({ children, ...props }: React.HTMLAttributes<HTMLElement>) => (
      <section {...props}>{children}</section>
    ),
  },
}));

vi.mock("@/components/home/home-visual-system", () => ({
  AxiomHomeLogo: () => <div data-testid="home-logo" />,
  HomeLaunchIcon: ({ kind }: { kind: string }) => (
    <div data-testid={`launch-icon-${kind}`} />
  ),
}));

vi.mock("@/components/home/space-atmosphere", () => ({
  SpaceAtmosphere: () => <div data-testid="space-atmosphere" />,
}));

vi.mock("@/components/shell/axiom-companion-dock", () => ({
  AxiomCompanionDock: () => <div data-testid="companion-dock" />,
}));

vi.mock("@/components/home/home-hero-animated-copy", () => ({
  HomeHeroAnimatedCopy: () => <div data-testid="home-hero-animated-copy" />,
}));

vi.mock("@/lib/api", () => ({
  fetchSettings: vi.fn(),
}));

const { fetchSettings } = await import("@/lib/api");
const { default: HomePage } = await import("../page");

describe("Home page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders animated hero copy and redirects launch actions to setup when setup is incomplete", async () => {
    vi.mocked(fetchSettings).mockResolvedValue({
      basic_wizard_completed: false,
    });

    render(<HomePage />);

    await waitFor(() => {
      expect(fetchSettings).toHaveBeenCalledTimes(1);
    });

    expect(screen.getByTestId("space-atmosphere")).toBeInTheDocument();
    expect(screen.getByTestId("home-hero-animated-copy")).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Chat" })[0]).toHaveAttribute(
      "href",
      "/setup",
    );
    expect(
      screen.getByRole("link", { name: "Build a Neuron" }),
    ).toHaveAttribute("href", "/setup");
    expect(screen.getByRole("link", { name: "Explore Brain" })).toHaveAttribute(
      "href",
      "/setup",
    );
  });

  it("keeps normal launch links when setup is complete", async () => {
    vi.mocked(fetchSettings).mockResolvedValue({
      basic_wizard_completed: true,
    });

    render(<HomePage />);

    await waitFor(() => {
      expect(fetchSettings).toHaveBeenCalledTimes(1);
    });

    expect(screen.getAllByRole("link", { name: "Chat" })[0]).toHaveAttribute(
      "href",
      "/chat",
    );
    expect(
      screen.getByRole("link", { name: "Build a Neuron" }),
    ).toHaveAttribute("href", "/library");
    expect(screen.getByRole("link", { name: "Explore Brain" })).toHaveAttribute(
      "href",
      "/brain",
    );
  });

  it("falls back to default launch links when settings fetch fails", async () => {
    vi.mocked(fetchSettings).mockRejectedValue(new Error("network down"));

    render(<HomePage />);

    await waitFor(() => {
      expect(fetchSettings).toHaveBeenCalledTimes(1);
    });

    expect(screen.getAllByRole("link", { name: "Chat" })[0]).toHaveAttribute(
      "href",
      "/chat",
    );
  });
});
