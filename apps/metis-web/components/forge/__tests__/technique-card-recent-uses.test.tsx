import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { TechniqueCard } from "../technique-card";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { ForgeTechnique } from "@/lib/api";

const mocks = vi.hoisted(() => ({
  fetchRecentUses: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchForgeRecentUses: (...args: unknown[]) => mocks.fetchRecentUses(...args),
  };
});

function makeTechnique(overrides: Partial<ForgeTechnique> = {}): ForgeTechnique {
  return {
    id: "iterrag-convergence",
    name: "IterRAG convergence",
    description: "Agentic retrieval loop.",
    pillar: "cortex",
    enabled: true,
    setting_keys: ["agentic_mode"],
    engine_symbols: ["metis_app.engine.querying"],
    recent_uses: [],
    weekly_use_count: 0,
    toggleable: true,
    enable_overrides: { agentic_mode: true },
    disable_overrides: { agentic_mode: false },
    runtime_status: "ready",
    runtime_blockers: [],
    runtime_cta_kind: null,
    runtime_cta_target: null,
    ...overrides,
  };
}

function renderCard(technique: ForgeTechnique) {
  return render(
    <TooltipProvider delay={0}>
      <TechniqueCard technique={technique} />
    </TooltipProvider>,
  );
}

afterEach(() => {
  mocks.fetchRecentUses.mockReset();
});

describe("<TechniqueCard /> Phase 6 — recent uses", () => {
  it("renders the weekly-use pill when the count is positive", () => {
    renderCard(makeTechnique({ weekly_use_count: 7 }));
    const pill = screen.getByTestId("forge-weekly-use-pill");
    expect(pill).toHaveTextContent(/7 uses this week/i);
  });

  it("hides the pill when the count is zero", () => {
    renderCard(makeTechnique({ weekly_use_count: 0 }));
    expect(screen.queryByTestId("forge-weekly-use-pill")).toBeNull();
  });

  it("singularises the pill copy when the count is exactly one", () => {
    renderCard(makeTechnique({ weekly_use_count: 1 }));
    const pill = screen.getByTestId("forge-weekly-use-pill");
    expect(pill).toHaveTextContent(/1 use this week/i);
  });

  it("expands and lazy-loads recent uses when the user clicks the pill", async () => {
    mocks.fetchRecentUses.mockResolvedValue({
      events: [
        {
          run_id: "run-A",
          timestamp: "2026-04-30T10:00:00+00:00",
          stage: "reflection",
          event_type: "iteration_complete",
          preview: "converged after 3 iterations",
        },
        {
          run_id: "run-B",
          timestamp: "2026-04-30T09:00:00+00:00",
          stage: "reflection",
          event_type: "iteration_start",
          preview: "starting iteration 1",
        },
      ],
      weekly_count: 2,
    });

    renderCard(makeTechnique({ weekly_use_count: 2 }));
    const trigger = screen.getByTestId("forge-recent-uses-trigger");
    fireEvent.click(trigger);

    await waitFor(() => {
      expect(mocks.fetchRecentUses).toHaveBeenCalledWith("iterrag-convergence");
    });
    const rows = await screen.findAllByTestId("forge-recent-uses-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent(/converged after 3 iterations/);
    expect(rows[1]).toHaveTextContent(/starting iteration 1/);
  });

  it("renders an empty-state message when the API returns no events", async () => {
    mocks.fetchRecentUses.mockResolvedValue({ events: [], weekly_count: 0 });

    renderCard(makeTechnique({ weekly_use_count: 3 }));
    fireEvent.click(screen.getByTestId("forge-recent-uses-trigger"));

    await waitFor(() => expect(mocks.fetchRecentUses).toHaveBeenCalled());
    const empty = await screen.findByTestId("forge-recent-uses-empty");
    expect(empty).toHaveTextContent(/no recent uses/i);
  });

  it("surfaces an inline error when the recent-uses fetch fails", async () => {
    mocks.fetchRecentUses.mockRejectedValue(new Error("server down"));

    renderCard(makeTechnique({ weekly_use_count: 5 }));
    fireEvent.click(screen.getByTestId("forge-recent-uses-trigger"));

    const error = await screen.findByTestId("forge-recent-uses-error");
    expect(error).toHaveTextContent(/server down/);
  });

  it("does not refetch on a second open within the same card lifetime", async () => {
    mocks.fetchRecentUses.mockResolvedValue({
      events: [
        {
          run_id: "run-A",
          timestamp: "2026-04-30T10:00:00+00:00",
          stage: "reflection",
          event_type: "iteration_complete",
          preview: "converged",
        },
      ],
      weekly_count: 1,
    });

    renderCard(makeTechnique({ weekly_use_count: 1 }));
    const trigger = screen.getByTestId("forge-recent-uses-trigger");
    fireEvent.click(trigger); // open
    await waitFor(() => expect(mocks.fetchRecentUses).toHaveBeenCalledTimes(1));
    fireEvent.click(trigger); // collapse
    fireEvent.click(trigger); // re-open — should reuse cached data
    expect(mocks.fetchRecentUses).toHaveBeenCalledTimes(1);
  });

  it("renders nothing for the recent-uses control when no markers are wired", () => {
    // weekly_use_count is the proxy: an unwired technique has no counts
    // and the card should hide the pill AND the expand trigger so the
    // user isn't promised a timeline that won't arrive.
    renderCard(makeTechnique({ weekly_use_count: 0 }));
    expect(screen.queryByTestId("forge-recent-uses-trigger")).toBeNull();
  });
});
