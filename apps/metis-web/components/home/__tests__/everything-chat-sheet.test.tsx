import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { fetchSettings, queryRag } from "@/lib/api";

import { ALL_STARS_MARKER, EverythingChatSheet } from "../everything-chat-sheet";

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
});
