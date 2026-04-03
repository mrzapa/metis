import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { ArrowArtifactBoundary } from "@/components/chat/artifacts/arrow-artifact-boundary";

vi.mock("@/lib/telemetry/ui-telemetry", async () => {
  const actual = await vi.importActual<typeof import("@/lib/telemetry/ui-telemetry")>(
    "@/lib/telemetry/ui-telemetry",
  );

  return {
    ...actual,
    emitArtifactTelemetry: vi.fn(),
  };
});

describe("ArrowArtifactBoundary Nyx rendering", () => {
  it("renders dedicated Nyx artifact cards from raw backend payloads", async () => {
    render(
      <ArrowArtifactBoundary
        content="Should not be shown"
        artifacts={[
          {
            id: "nyx_component_selection",
            type: "nyx_component_selection",
            summary: "Nyx selection",
            path: "nyx/component-selection",
            mime_type: "application/vnd.metis.nyx+json",
            payload: {
              query: "Use Glow Card in a dashboard",
              intent_type: "ui_layout_request",
              confidence: 0.88,
              selection_reason: "Nyx matched the strongest fitting components.",
              matched_signals: ["explicit_nyx", "pattern:card"],
              selected_components: [
                {
                  component_name: "glow-card",
                  title: "Glow Card",
                  description: "Interactive card with glow effects.",
                  curated_description: "Accent-heavy card chrome for feature blocks.",
                  component_type: "registry:ui",
                  install_target: "@nyx/glow-card",
                  registry_url: "https://nyxui.com/r/glow-card.json",
                  source_repo: "https://github.com/MihirJaiswal/nyxui",
                  match_score: 39,
                  match_reason: "query hint: glow",
                  match_reasons: ["query hint: glow"],
                  preview_targets: ["components/ui/glow-card.tsx"],
                  targets: ["components/ui/glow-card.tsx"],
                  file_count: 1,
                  required_dependencies: ["clsx"],
                  dependencies: ["tailwind-merge"],
                  dev_dependencies: [],
                  registry_dependencies: [],
                },
              ],
            },
          },
          {
            id: "nyx_install_plan",
            type: "nyx_install_plan",
            summary: "Nyx install plan",
            path: "nyx/install-plan",
            mime_type: "application/vnd.metis.nyx+json",
            payload: {
              query: "Use Glow Card in a dashboard",
              intent_type: "ui_layout_request",
              package_manager_note: "Install dependency packages with the workspace package manager.",
              components: [
                {
                  component_name: "glow-card",
                  title: "Glow Card",
                  install_target: "@nyx/glow-card",
                  registry_url: "https://nyxui.com/r/glow-card.json",
                  targets: ["components/ui/glow-card.tsx"],
                  file_count: 1,
                  dependency_packages: ["clsx", "tailwind-merge"],
                  steps: [
                    {
                      step_type: "registry_add",
                      label: "Add Glow Card from the NyxUI registry.",
                      command: "npx shadcn@latest add https://nyxui.com/r/glow-card.json",
                    },
                  ],
                },
              ],
            },
          },
          {
            id: "nyx_dependency_report",
            type: "nyx_dependency_report",
            summary: "Nyx dependency report",
            path: "nyx/dependencies",
            mime_type: "application/vnd.metis.nyx+json",
            payload: {
              query: "Use Glow Card in a dashboard",
              component_count: 1,
              packages: [
                {
                  package_name: "clsx",
                  dependency_type: "required",
                  required_by: ["glow-card"],
                  install_targets: ["@nyx/glow-card"],
                  registry_urls: ["https://nyxui.com/r/glow-card.json"],
                },
              ],
              groups: {
                required: [
                  {
                    package_name: "clsx",
                    dependency_type: "required",
                    required_by: ["glow-card"],
                    install_targets: ["@nyx/glow-card"],
                    registry_urls: ["https://nyxui.com/r/glow-card.json"],
                  },
                ],
                runtime: [
                  {
                    package_name: "tailwind-merge",
                    dependency_type: "runtime",
                    required_by: ["glow-card"],
                    install_targets: ["@nyx/glow-card"],
                    registry_urls: ["https://nyxui.com/r/glow-card.json"],
                  },
                ],
                dev: [],
                registry: [],
              },
            },
          },
        ]}
        runId="run-nyx-render"
      />,
    );

    expect(screen.getByTestId("nyx-component-selection-artifact")).toBeInTheDocument();
    expect(screen.getByText("Glow Card")).toBeInTheDocument();
    expect(screen.queryByText("Should not be shown")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Select artifact 2:/i }));

    await waitFor(() => {
      expect(screen.getByTestId("nyx-install-plan-artifact")).toBeInTheDocument();
      expect(screen.getByText("npx shadcn@latest add https://nyxui.com/r/glow-card.json")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole("button", { name: /Select artifact 3:/i }));

    await waitFor(() => {
      expect(screen.getByTestId("nyx-dependency-report-artifact")).toBeInTheDocument();
      expect(screen.getByText("clsx")).toBeInTheDocument();
      const detailLinks = screen.getAllByRole("link", { name: "glow-card" });
      expect(detailLinks.length).toBeGreaterThan(0);
      expect(
        detailLinks.some((link) => link.getAttribute("href") === "/library/glow-card"),
      ).toBe(true);
    });
  });
});