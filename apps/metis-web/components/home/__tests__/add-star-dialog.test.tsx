import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { recommendStarsForContent } from "@/lib/api";
import type { RecommendResponse } from "@/lib/api";

import { AddStarDialog, type AddDecision } from "../add-star-dialog";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    recommendStarsForContent: vi.fn(),
  };
});

const mockedRecommend = vi.mocked(recommendStarsForContent);

function makeRecommendResponse(
  overrides: Partial<RecommendResponse> = {},
): RecommendResponse {
  return {
    recommendations: [
      {
        star_id: "star-aa",
        similarity: 0.91,
        label: "Python performance",
        archetype: "main_sequence",
      },
      {
        star_id: "star-bb",
        similarity: 0.74,
        label: "Python tooling",
        archetype: "main_sequence",
      },
    ],
    create_new_suggested: false,
    ...overrides,
  };
}

afterEach(() => {
  mockedRecommend.mockReset();
});

describe("AddStarDialog", () => {
  it("renders the input step with file trigger, textarea, and Next disabled while empty", () => {
    render(
      <AddStarDialog open onOpenChange={() => {}} onConfirm={async () => {}} />,
    );

    expect(screen.getByTestId("add-star-dialog-file-trigger")).toBeInTheDocument();
    expect(screen.getByTestId("add-star-dialog-textarea")).toBeInTheDocument();

    const nextButton = screen.getByTestId("add-star-dialog-next");
    expect(nextButton).toBeDisabled();
  });

  it("clicking Next calls recommendStarsForContent and moves to the suggestions step", async () => {
    mockedRecommend.mockResolvedValueOnce(makeRecommendResponse());

    render(
      <AddStarDialog open onOpenChange={() => {}} onConfirm={async () => {}} />,
    );

    const textarea = screen.getByTestId(
      "add-star-dialog-textarea",
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "perf hot loop" } });

    const next = screen.getByTestId("add-star-dialog-next");
    expect(next).not.toBeDisabled();
    fireEvent.click(next);

    await waitFor(() => {
      expect(mockedRecommend).toHaveBeenCalledWith("perf hot loop");
    });

    await waitFor(() => {
      expect(screen.getByTestId("add-star-dialog-suggestions")).toBeInTheDocument();
    });

    expect(screen.getByTestId("add-star-dialog-rec-star-aa")).toBeInTheDocument();
    expect(screen.getByTestId("add-star-dialog-rec-star-bb")).toBeInTheDocument();
    // Create-new card is always rendered, even when create_new_suggested is false.
    expect(screen.getByTestId("add-star-dialog-create-new")).toBeInTheDocument();
  });

  it("clicking Attach on a recommendation calls onConfirm with kind=attach and the star id", async () => {
    mockedRecommend.mockResolvedValueOnce(makeRecommendResponse());
    const decisions: AddDecision[] = [];
    const onConfirm = vi.fn(async (decision: AddDecision) => {
      decisions.push(decision);
    });

    render(
      <AddStarDialog open onOpenChange={() => {}} onConfirm={onConfirm} />,
    );

    fireEvent.change(screen.getByTestId("add-star-dialog-textarea"), {
      target: { value: "perf hot loop" },
    });
    fireEvent.click(screen.getByTestId("add-star-dialog-next"));

    await waitFor(() => {
      expect(screen.getByTestId("add-star-dialog-rec-star-aa")).toBeInTheDocument();
    });

    const attachButton = screen
      .getByTestId("add-star-dialog-rec-star-aa")
      .querySelector("button");
    expect(attachButton).not.toBeNull();
    fireEvent.click(attachButton as HTMLButtonElement);

    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalledTimes(1);
    });
    expect(decisions[0]).toMatchObject({
      kind: "attach",
      star_id: "star-aa",
      content: "perf hot loop",
    });
  });

  it("clamps out-of-range similarity values to [0, 100]% in label and aria-label", async () => {
    // StarRecommenderService can emit similarities slightly above 1.0 due to
    // content-type / project-member boosts, and degenerate embedders can
    // surface negative cosines. Both must clamp before render.
    mockedRecommend.mockResolvedValueOnce(
      makeRecommendResponse({
        recommendations: [
          {
            star_id: "star-high",
            similarity: 1.5,
            label: "Boosted match",
            archetype: "main_sequence",
          },
          {
            star_id: "star-neg",
            similarity: -0.12,
            label: "Negative match",
            archetype: "main_sequence",
          },
        ],
      }),
    );

    render(
      <AddStarDialog open onOpenChange={() => {}} onConfirm={async () => {}} />,
    );

    fireEvent.change(screen.getByTestId("add-star-dialog-textarea"), {
      target: { value: "any seed" },
    });
    fireEvent.click(screen.getByTestId("add-star-dialog-next"));

    await waitFor(() => {
      expect(screen.getByTestId("add-star-dialog-rec-star-high")).toBeInTheDocument();
    });

    // Visible label is clamped to 100% (not 150%).
    const highCard = screen.getByTestId("add-star-dialog-rec-star-high");
    expect(highCard.textContent).toContain("similarity 100%");
    // aria-label on the Attach button mirrors the clamped value.
    const highButton = highCard.querySelector("button");
    expect(highButton?.getAttribute("aria-label")).toContain("(100% similarity)");

    // Negative similarities clamp to 0%.
    const negCard = screen.getByTestId("add-star-dialog-rec-star-neg");
    expect(negCard.textContent).toContain("similarity 0%");
    const negButton = negCard.querySelector("button");
    expect(negButton?.getAttribute("aria-label")).toContain("(0% similarity)");
  });

  it("clicking Create on the create-new card calls onConfirm with kind=create_new", async () => {
    mockedRecommend.mockResolvedValueOnce(makeRecommendResponse());
    const decisions: AddDecision[] = [];
    const onConfirm = vi.fn(async (decision: AddDecision) => {
      decisions.push(decision);
    });

    render(
      <AddStarDialog open onOpenChange={() => {}} onConfirm={onConfirm} />,
    );

    fireEvent.change(screen.getByTestId("add-star-dialog-textarea"), {
      target: { value: "totally novel topic" },
    });
    fireEvent.click(screen.getByTestId("add-star-dialog-next"));

    await waitFor(() => {
      expect(screen.getByTestId("add-star-dialog-create-new")).toBeInTheDocument();
    });

    const createButton = screen
      .getByTestId("add-star-dialog-create-new")
      .querySelector("button");
    expect(createButton).not.toBeNull();
    fireEvent.click(createButton as HTMLButtonElement);

    await waitFor(() => {
      expect(onConfirm).toHaveBeenCalledTimes(1);
    });
    expect(decisions[0]).toMatchObject({
      kind: "create_new",
      content: "totally novel topic",
    });
  });
});
