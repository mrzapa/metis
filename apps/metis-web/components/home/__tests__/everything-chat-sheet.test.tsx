import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchSettings, queryRag } from "@/lib/api";

import { ALL_STARS_MARKER, EverythingChatSheet } from "../everything-chat-sheet";

function mockRagResult(answerText: string) {
  return {
    run_id: "run-x",
    answer_text: answerText,
    sources: [],
    context_block: "",
    top_score: 0.5,
    selected_mode: "Q&A",
    retrieval_plan: { stages: [] },
    fallback: {},
  } as never;
}

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    fetchSettings: vi.fn(),
    queryRag: vi.fn(),
  };
});

const mockedFetchSettings = vi.mocked(fetchSettings);
const mockedQueryRag = vi.mocked(queryRag);

afterEach(() => {
  mockedFetchSettings.mockReset();
  mockedQueryRag.mockReset();
});

describe("EverythingChatSheet", () => {
  it("renders the composer and empty-state hint when open", () => {
    render(
      <EverythingChatSheet open onOpenChange={() => {}} />,
    );

    expect(screen.getByTestId("everything-chat-sheet")).toBeInTheDocument();
    expect(screen.getByTestId("everything-chat-input")).toBeInTheDocument();
    expect(screen.getByTestId("everything-chat-send")).toBeDisabled();
    expect(
      screen.getByText(/spans your entire constellation/i),
    ).toBeInTheDocument();
  });

  it("does not render sheet content when closed", () => {
    render(
      <EverythingChatSheet open={false} onOpenChange={() => {}} />,
    );

    expect(screen.queryByTestId("everything-chat-sheet")).not.toBeInTheDocument();
  });

  it("sends with manifest_path equal to the _all_stars sentinel", async () => {
    mockedFetchSettings.mockResolvedValueOnce({} as never);
    mockedQueryRag.mockResolvedValueOnce({
      run_id: "run-1",
      answer_text: "Aggregated answer.",
      sources: [],
      context_block: "",
      top_score: 0.5,
      selected_mode: "Q&A",
      retrieval_plan: { stages: [] } as never,
      fallback: {},
    });

    render(
      <EverythingChatSheet open onOpenChange={() => {}} />,
    );

    fireEvent.change(screen.getByTestId("everything-chat-input"), {
      target: { value: "summarise everything" },
    });
    fireEvent.click(screen.getByTestId("everything-chat-send"));

    await waitFor(() => {
      expect(mockedQueryRag).toHaveBeenCalledTimes(1);
    });

    const [manifestPath, question] = mockedQueryRag.mock.calls[0];
    expect(manifestPath).toBe(ALL_STARS_MARKER);
    expect(question).toBe("summarise everything");

    await waitFor(() => {
      expect(screen.getByText("Aggregated answer.")).toBeInTheDocument();
    });
  });

  it("clears the transcript when the sheet is closed and reopened", async () => {
    mockedFetchSettings.mockResolvedValueOnce({} as never);
    mockedQueryRag.mockResolvedValueOnce(mockRagResult("first answer"));

    const { rerender } = render(
      <EverythingChatSheet open onOpenChange={() => {}} />,
    );

    fireEvent.change(screen.getByTestId("everything-chat-input"), {
      target: { value: "first question" },
    });
    fireEvent.click(screen.getByTestId("everything-chat-send"));

    await waitFor(() => {
      expect(screen.getByText("first answer")).toBeInTheDocument();
    });

    // Close and reopen — transcript should be empty.
    rerender(<EverythingChatSheet open={false} onOpenChange={() => {}} />);
    rerender(<EverythingChatSheet open onOpenChange={() => {}} />);

    expect(screen.queryByText("first answer")).not.toBeInTheDocument();
    expect(screen.queryByText("first question")).not.toBeInTheDocument();
    expect(
      screen.getByText(/spans your entire constellation/i),
    ).toBeInTheDocument();
  });

  it("renders an error bubble when queryRag throws", async () => {
    mockedFetchSettings.mockResolvedValueOnce({} as never);
    mockedQueryRag.mockRejectedValueOnce(new Error("boom"));

    render(
      <EverythingChatSheet open onOpenChange={() => {}} />,
    );

    fireEvent.change(screen.getByTestId("everything-chat-input"), {
      target: { value: "explode please" },
    });
    fireEvent.click(screen.getByTestId("everything-chat-send"));

    await waitFor(() => {
      expect(screen.getByTestId("everything-chat-msg-error")).toBeInTheDocument();
    });

    expect(screen.getByText("boom")).toBeInTheDocument();
  });

  it("does not append assistant message when sheet closes before queryRag resolves", async () => {
    // Simulate a queryRag that resolves only after we explicitly let it.
    let resolveQuery: ((value: ReturnType<typeof mockRagResult>) => void) | null = null;
    const inFlight = new Promise<ReturnType<typeof mockRagResult>>((res) => {
      resolveQuery = res;
    });
    mockedFetchSettings.mockResolvedValueOnce({} as never);
    mockedQueryRag.mockReturnValueOnce(inFlight as never);

    const { rerender } = render(
      <EverythingChatSheet open onOpenChange={() => {}} />,
    );

    fireEvent.change(screen.getByTestId("everything-chat-input"), {
      target: { value: "race against close" },
    });
    fireEvent.click(screen.getByTestId("everything-chat-send"));

    // Close the sheet before queryRag resolves — this is the race the
    // fix targets. The reset effect bumps `handleSendActiveRef`, which
    // the in-flight handler must check against before calling setState.
    rerender(<EverythingChatSheet open={false} onOpenChange={() => {}} />);

    // Now let the query resolve. Without the abort guard the handler
    // would race and re-append an assistant bubble that would reappear
    // on next open.
    resolveQuery!(mockRagResult("orphaned answer"));

    // Reopen and wait for any pending microtasks to flush.
    rerender(<EverythingChatSheet open onOpenChange={() => {}} />);
    await new Promise((resolve) => setTimeout(resolve, 0));

    // Transcript must be empty — the orphaned reply was abandoned.
    expect(screen.queryByText("orphaned answer")).not.toBeInTheDocument();
    expect(screen.queryByText("race against close")).not.toBeInTheDocument();
    expect(
      screen.getByText(/spans your entire constellation/i),
    ).toBeInTheDocument();
  });
});
