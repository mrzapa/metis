import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const pushMock = vi.fn();

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock("@/components/shell/page-chrome", () => ({
  PageChrome: ({
    actions,
    children,
    heroAside,
    title,
  }: React.PropsWithChildren<{
    actions?: React.ReactNode;
    heroAside?: React.ReactNode;
    title: string;
  }>) => (
    <div>
      <h1>{title}</h1>
      {actions}
      {heroAside}
      {children}
    </div>
  ),
}));

vi.mock("@/lib/api", () => ({
  fetchNyxComponentDetail: vi.fn(),
}));

const { fetchNyxComponentDetail } = await import("@/lib/api");
const { NyxComponentDetailPage } = await import("../nyx-component-detail-page");

describe("NyxComponentDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    vi.mocked(fetchNyxComponentDetail).mockResolvedValue({
      component_name: "glow-card",
      title: "Glow Card",
      description: "A glow card.",
      curated_description: "Interactive card with glow-based accent effects.",
      component_type: "registry:ui",
      install_target: "@nyx/glow-card",
      registry_url: "https://nyxui.com/r/glow-card.json",
      schema_url: "https://ui.shadcn.com/schema/registry-item.json",
      source: "nyx_registry",
      source_repo: "https://github.com/MihirJaiswal/nyxui",
      required_dependencies: ["clsx", "tailwind-merge"],
      dependencies: ["clsx", "tailwind-merge"],
      dev_dependencies: [],
      registry_dependencies: ["button"],
      file_count: 1,
      targets: ["components/ui/glow-card.tsx"],
      files: [
        {
          path: "registry/ui/glow-card.tsx",
          file_type: "registry:ui",
          target: "components/ui/glow-card.tsx",
          content_bytes: 128,
        },
      ],
    });
  });

  it("renders install and dependency context from the local Nyx detail API", async () => {
    render(<NyxComponentDetailPage componentName="glow-card" />);

    expect(await screen.findByText("Install footprint")).toBeInTheDocument();
    expect(screen.getByText("@nyx/glow-card")).toBeInTheDocument();
    expect(screen.getByText("components/ui/glow-card.tsx")).toBeInTheDocument();
    expect(screen.getAllByText("tailwind-merge").length).toBeGreaterThan(0);
  });

  it("can seed chat from the preview surface", async () => {
    render(<NyxComponentDetailPage componentName="glow-card" />);

    expect(await screen.findByText("Prompt-ready handoff")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: /Use in chat/i })[0]);

    expect(window.localStorage.getItem("metis_chat_seed_prompt")).toContain(
      "@nyx/glow-card",
    );
    expect(pushMock).toHaveBeenCalledWith("/chat");
  });
});