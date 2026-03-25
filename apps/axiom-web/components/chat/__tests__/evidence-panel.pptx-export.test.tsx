import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { EvidenceSource } from "@/lib/chat-types";

vi.mock("lucide-react", async (importOriginal) => {
  const actual = await importOriginal<typeof import("lucide-react")>();
  const Icon = () => null;
  return {
    ...actual,
    FileDown: Icon,
  };
});

vi.mock("@/lib/export/pptx", () => ({
  exportChatAnswerAsPptx: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchTraceEvents: vi.fn().mockResolvedValue([]),
  };
});

const { EvidencePanel } = await import("@/components/chat/evidence-panel");
const { exportChatAnswerAsPptx } = await import("@/lib/export/pptx");

function buildSource(overrides: Partial<EvidenceSource> = {}): EvidenceSource {
  return {
    sid: "S-1",
    source: "notes.md",
    snippet: "Evidence snippet",
    title: "Meeting Notes",
    score: 0.9,
    breadcrumb: "Team > Notes",
    section_hint: "Summary",
    ...overrides,
  };
}

function renderPanel(props: Partial<React.ComponentProps<typeof EvidencePanel>> = {}) {
  return render(
    <EvidencePanel
      sources={props.sources ?? []}
      runIds={props.runIds ?? []}
      latestRunId={props.latestRunId ?? null}
      selectedMode={props.selectedMode}
      latestAnswer={props.latestAnswer}
      fallback={props.fallback ?? null}
      liveTraceEvents={props.liveTraceEvents}
      isStreaming={props.isStreaming}
      preferredTab={props.preferredTab}
      postureToken={props.postureToken}
    />,
  );
}

describe("EvidencePanel PPTX export", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(exportChatAnswerAsPptx).mockResolvedValue(undefined);
  });

  it("renders Export PPTX and invokes exporter with expected payload", async () => {
    const sources = [buildSource()];

    renderPanel({
      sources,
      selectedMode: "Evidence Pack",
      latestAnswer: "Grounded response",
    });

    const button = screen.getByRole("button", { name: /export pptx/i });
    expect(button).toBeEnabled();

    fireEvent.click(button);

    await waitFor(() => {
      expect(exportChatAnswerAsPptx).toHaveBeenCalledTimes(1);
    });

    expect(exportChatAnswerAsPptx).toHaveBeenCalledWith(
      expect.objectContaining({
        answer: "Grounded response",
        sources,
        mode: "Evidence Pack",
        title: "Axiom Evidence Pack Export",
        fileName: "axiom-Evidence Pack",
      }),
    );
  });

  it("disables export when there is no answer and no sources", () => {
    renderPanel({
      sources: [],
      latestAnswer: "",
      selectedMode: "Evidence Pack",
    });

    expect(screen.getByRole("button", { name: /export pptx/i })).toBeDisabled();
  });

  it("shows exporting state and prevents duplicate clicks while export is pending", async () => {
    let resolveExport: (() => void) | undefined;
    const pending = new Promise<void>((resolve) => {
      resolveExport = resolve;
    });
    vi.mocked(exportChatAnswerAsPptx).mockReturnValue(pending);

    renderPanel({
      sources: [buildSource()],
      latestAnswer: "Answer",
      selectedMode: "Research",
    });

    const button = screen.getByRole("button", { name: /export pptx/i });
    fireEvent.click(button);

    await screen.findByRole("button", { name: /exporting/i });
    expect(screen.getByRole("button", { name: /exporting/i })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: /exporting/i }));
    expect(exportChatAnswerAsPptx).toHaveBeenCalledTimes(1);

    resolveExport?.();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /export pptx/i })).toBeEnabled();
    });
  });
});