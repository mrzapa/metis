import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { TechniqueCard } from "../technique-card";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { ForgeTechnique } from "@/lib/api";


function makeTechnique(overrides: Partial<ForgeTechnique> = {}): ForgeTechnique {
  return {
    id: "reranker",
    name: "Reranker",
    description: "Cross-encoder pass over retrieved passages.",
    pillar: "cortex",
    enabled: false,
    setting_keys: ["use_reranker"],
    engine_symbols: ["metis_app.services.reranker"],
    recent_uses: [],
    toggleable: true,
    enable_overrides: { use_reranker: true },
    disable_overrides: { use_reranker: false },
    runtime_status: "ready",
    runtime_blockers: [],
    runtime_cta_kind: null,
    runtime_cta_target: null,
    ...overrides,
  };
}

function renderCard(props: React.ComponentProps<typeof TechniqueCard>) {
  return render(
    <TooltipProvider delay={0}>
      <TechniqueCard {...props} />
    </TooltipProvider>,
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("<TechniqueCard /> Phase 3 toggle", () => {
  it("renders a switch when toggleable + onToggle are both supplied", () => {
    renderCard({
      technique: makeTechnique(),
      onToggle: vi.fn(async () => {}),
    });
    const sw = screen.getByRole("switch", { name: /activate reranker/i });
    expect(sw).toHaveAttribute("aria-checked", "false");
  });

  it("does not render a switch when the technique is not toggleable", () => {
    renderCard({
      technique: makeTechnique({
        toggleable: false,
        enable_overrides: null,
        disable_overrides: null,
      }),
      onToggle: vi.fn(async () => {}),
    });
    expect(screen.queryByRole("switch")).toBeNull();
  });

  it("does not render a switch when no onToggle is supplied", () => {
    renderCard({
      technique: makeTechnique(),
    });
    expect(screen.queryByRole("switch")).toBeNull();
  });

  it("calls onToggle with the next enabled state when the switch is clicked", async () => {
    const onToggle = vi.fn<(technique: ForgeTechnique, enabled: boolean) => Promise<void>>(
      async () => {},
    );
    renderCard({
      technique: makeTechnique({ enabled: false }),
      onToggle,
    });

    fireEvent.click(screen.getByRole("switch"));

    await waitFor(() => {
      expect(onToggle).toHaveBeenCalledTimes(1);
    });
    const call = onToggle.mock.calls[0];
    expect(call[1]).toBe(true);
  });

  it("disables the switch while the toggle is in flight", async () => {
    type Resolver = (() => void) | null;
    const resolverRef: { current: Resolver } = { current: null };
    const onToggle = vi.fn<(technique: ForgeTechnique, enabled: boolean) => Promise<void>>(
      () =>
        new Promise<void>((r) => {
          resolverRef.current = () => r();
        }),
    );
    renderCard({
      technique: makeTechnique(),
      onToggle,
    });

    const sw = screen.getByRole("switch");
    fireEvent.click(sw);

    await waitFor(() => {
      expect(sw).toBeDisabled();
      expect(sw).toHaveAttribute("data-pending", "true");
    });

    resolverRef.current?.();
    await waitFor(() => {
      expect(sw).not.toBeDisabled();
      expect(sw).toHaveAttribute("data-pending", "false");
    });
  });

  it("surfaces an inline error when onToggle rejects", async () => {
    const onToggle = vi.fn(async () => {
      throw new Error("forge backend exploded");
    });
    renderCard({
      technique: makeTechnique(),
      onToggle,
    });

    fireEvent.click(screen.getByRole("switch"));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/forge backend exploded/i);
  });

  it("renders a read-only badge for non-toggleable, ready techniques", () => {
    renderCard({
      technique: makeTechnique({
        id: "informational",
        name: "Informational",
        toggleable: false,
        enable_overrides: null,
        disable_overrides: null,
        runtime_status: "ready",
        runtime_blockers: [],
      }),
      onToggle: vi.fn(async () => {}),
    });
    expect(
      screen.getByLabelText(/read-only — needs runtime check/i),
    ).toBeTruthy();
  });
});

describe("<TechniqueCard /> Phase 3b runtime readiness", () => {
  it("disables the switch when a toggleable technique is blocked", () => {
    renderCard({
      technique: makeTechnique({
        id: "heretic-abliteration",
        name: "Heretic abliteration",
        toggleable: true,
        enable_overrides: { heretic_output_dir: ".metis_cache/heretic-out" },
        disable_overrides: { heretic_output_dir: "" },
        runtime_status: "blocked",
        runtime_blockers: ["Heretic CLI is not on $PATH"],
        runtime_cta_kind: "install_heretic",
      }),
      onToggle: vi.fn(async () => {}),
    });
    const sw = screen.getByRole("switch");
    expect(sw).toBeDisabled();
    expect(sw).toHaveAttribute("data-blocked", "true");
    expect(sw.getAttribute("aria-label")).toMatch(/blocked|runtime check/i);
  });

  it("does not call onToggle when a blocked switch is clicked", () => {
    const onToggle = vi.fn(async () => {});
    renderCard({
      technique: makeTechnique({
        id: "heretic-abliteration",
        name: "Heretic abliteration",
        toggleable: true,
        enable_overrides: { heretic_output_dir: "x" },
        disable_overrides: { heretic_output_dir: "" },
        runtime_status: "blocked",
        runtime_blockers: ["Heretic CLI is not on $PATH"],
        runtime_cta_kind: "install_heretic",
      }),
      onToggle,
    });
    fireEvent.click(screen.getByRole("switch"));
    expect(onToggle).not.toHaveBeenCalled();
  });

  it("surfaces the readiness row + blocker text when blocked", () => {
    renderCard({
      technique: makeTechnique({
        id: "heretic-abliteration",
        name: "Heretic abliteration",
        toggleable: true,
        enable_overrides: { heretic_output_dir: "x" },
        disable_overrides: { heretic_output_dir: "" },
        runtime_status: "blocked",
        runtime_blockers: ["Heretic CLI is not on $PATH"],
        runtime_cta_kind: "install_heretic",
      }),
      onToggle: vi.fn(async () => {}),
    });
    const row = screen.getByTestId("forge-readiness-row");
    expect(row).toHaveTextContent(/heretic cli is not on \$PATH/i);
    expect(screen.getByTestId("forge-readiness-cta")).toHaveTextContent(/get ready/i);
  });

  it("renders a chat-link CTA for switch_chat_path techniques", () => {
    renderCard({
      technique: makeTechnique({
        id: "timesfm-forecasting",
        name: "TimesFM forecasting",
        toggleable: false,
        enable_overrides: null,
        disable_overrides: null,
        runtime_status: "blocked",
        runtime_blockers: ["Forecast mode is activated by switching the chat to Forecast."],
        runtime_cta_kind: "switch_chat_path",
        runtime_cta_target: "/chat",
      }),
      onToggle: vi.fn(async () => {}),
    });
    // No switch + no read-only lock badge — only the readiness row
    // with the deep-link CTA.
    expect(screen.queryByRole("switch")).toBeNull();
    expect(screen.queryByLabelText(/read-only/i)).toBeNull();
    const cta = screen.getByTestId("forge-readiness-cta");
    expect(cta).toHaveAttribute("href", "/chat");
    expect(cta).toHaveTextContent(/open chat/i);
  });

  it("opens the install-Heretic dialog when the Get-ready CTA is clicked", async () => {
    renderCard({
      technique: makeTechnique({
        id: "heretic-abliteration",
        name: "Heretic abliteration",
        toggleable: true,
        enable_overrides: { heretic_output_dir: "x" },
        disable_overrides: { heretic_output_dir: "" },
        runtime_status: "blocked",
        runtime_blockers: ["Heretic CLI is not on $PATH"],
        runtime_cta_kind: "install_heretic",
      }),
      onToggle: vi.fn(async () => {}),
    });
    fireEvent.click(screen.getByTestId("forge-readiness-cta"));
    const dialogTitle = await screen.findByRole("heading", { name: /install heretic cli/i });
    expect(dialogTitle).toBeTruthy();
    // Install command is rendered verbatim so the user can copy it.
    expect(screen.getByText(/pipx install heretic-cli/i)).toBeTruthy();
  });
});
