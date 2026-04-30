import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { ProposalReviewPane } from "../proposal-review-pane";
import type { ForgeProposalRecord } from "@/lib/api";

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  accept: vi.fn(),
  reject: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    listForgeProposals: (...args: unknown[]) => mocks.list(...args),
    acceptForgeProposal: (...args: unknown[]) => mocks.accept(...args),
    rejectForgeProposal: (...args: unknown[]) => mocks.reject(...args),
  };
});

function makeProposal(overrides: Partial<ForgeProposalRecord> = {}): ForgeProposalRecord {
  return {
    id: 1,
    source_url: "https://arxiv.org/abs/2501.12345",
    arxiv_id: "2501.12345",
    title: "Cross-encoder reranking that matters",
    summary: "We propose a reranker.",
    proposal_name: "Sparse Cross-Encoder Reranking",
    proposal_claim: "Reranks BM25 hits with a small cross-encoder.",
    proposal_pillar: "cortex",
    proposal_sketch: "Score top-k hits with a cross-encoder.",
    status: "pending",
    created_at: 1716054000.0,
    resolved_at: null,
    skill_path: null,
    source: "manual",
    comet_id: null,
    ...overrides,
  };
}

afterEach(() => {
  mocks.list.mockReset();
  mocks.accept.mockReset();
  mocks.reject.mockReset();
});

describe("<ProposalReviewPane />", () => {
  it("renders nothing while the initial fetch is pending", () => {
    mocks.list.mockReturnValue(new Promise(() => {}));
    const { container } = render(<ProposalReviewPane />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when there are no pending proposals", async () => {
    mocks.list.mockResolvedValue({ proposals: [] });
    const { container } = render(<ProposalReviewPane />);
    await waitFor(() => {
      expect(mocks.list).toHaveBeenCalled();
    });
    expect(container.firstChild).toBeNull();
  });

  it("lists pending proposals with the expected fields", async () => {
    mocks.list.mockResolvedValue({
      proposals: [
        makeProposal({ id: 7, proposal_name: "First Proposal" }),
        makeProposal({ id: 8, proposal_name: "Second Proposal" }),
      ],
    });
    render(<ProposalReviewPane />);
    await waitFor(() => {
      expect(screen.getByTestId("forge-proposal-review-pane")).toBeTruthy();
    });
    const rows = screen.getAllByTestId("forge-proposal-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent(/First Proposal/);
    expect(rows[1]).toHaveTextContent(/Second Proposal/);
  });

  it("calls acceptForgeProposal when Accept is clicked, then refetches", async () => {
    mocks.list
      .mockResolvedValueOnce({ proposals: [makeProposal({ id: 11 })] })
      .mockResolvedValueOnce({ proposals: [] });
    mocks.accept.mockResolvedValue({
      status: "accepted",
      skill_path: "skills/sparse-cross-encoder-reranking/SKILL.md",
      proposal_id: 11,
    });

    render(<ProposalReviewPane />);
    const acceptBtn = await screen.findByRole("button", {
      name: /^Accept \(draft skill\)$/,
    });
    fireEvent.click(acceptBtn);

    await waitFor(() => {
      expect(mocks.accept).toHaveBeenCalledWith(11);
    });
    await waitFor(() => {
      // Refetch returned an empty list — pane unmounts.
      expect(screen.queryByTestId("forge-proposal-review-pane")).toBeNull();
    });
    expect(mocks.list).toHaveBeenCalledTimes(2);
  });

  it("calls rejectForgeProposal when Dismiss is clicked", async () => {
    mocks.list
      .mockResolvedValueOnce({ proposals: [makeProposal({ id: 22 })] })
      .mockResolvedValueOnce({ proposals: [] });
    mocks.reject.mockResolvedValue(undefined);

    render(<ProposalReviewPane />);
    const dismissBtn = await screen.findByRole("button", { name: /^Dismiss$/ });
    fireEvent.click(dismissBtn);

    await waitFor(() => {
      expect(mocks.reject).toHaveBeenCalledWith(22);
    });
  });

  it("surfaces an error alert when the accept call rejects", async () => {
    mocks.list.mockResolvedValue({ proposals: [makeProposal({ id: 33 })] });
    mocks.accept.mockRejectedValue(new Error("conflict: skill exists"));

    render(<ProposalReviewPane />);
    const acceptBtn = await screen.findByRole("button", {
      name: /^Accept \(draft skill\)$/,
    });
    fireEvent.click(acceptBtn);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/conflict: skill exists/i);
  });

  it("surfaces an error when the initial fetch rejects", async () => {
    mocks.list.mockRejectedValue(new Error("server down"));
    render(<ProposalReviewPane />);
    const alert = await screen.findByTestId("forge-proposal-review-error");
    expect(alert).toHaveTextContent(/server down/);
  });

  it("renders a 'From comet feed' badge for comet-sourced proposals", async () => {
    mocks.list.mockResolvedValue({
      proposals: [
        makeProposal({
          id: 50,
          source: "comet",
          comet_id: "comet_xyz",
          proposal_name: "Comet-sourced proposal",
        }),
      ],
    });
    render(<ProposalReviewPane />);
    await waitFor(() => {
      expect(screen.getByTestId("forge-proposal-review-pane")).toBeTruthy();
    });
    expect(screen.getByTestId("forge-proposal-comet-badge")).toHaveTextContent(
      /from comet feed/i,
    );
  });

  it("does not render the comet badge for manually-pasted proposals", async () => {
    mocks.list.mockResolvedValue({
      proposals: [makeProposal({ source: "manual" })],
    });
    render(<ProposalReviewPane />);
    await waitFor(() => {
      expect(screen.getByTestId("forge-proposal-review-pane")).toBeTruthy();
    });
    expect(screen.queryByTestId("forge-proposal-comet-badge")).toBeNull();
  });

  it("re-fetches when refreshKey prop bumps", async () => {
    mocks.list.mockResolvedValue({ proposals: [] });
    const { rerender } = render(<ProposalReviewPane refreshKey={0} />);
    await waitFor(() => expect(mocks.list).toHaveBeenCalledTimes(1));
    rerender(<ProposalReviewPane refreshKey={1} />);
    await waitFor(() => expect(mocks.list).toHaveBeenCalledTimes(2));
  });
});
