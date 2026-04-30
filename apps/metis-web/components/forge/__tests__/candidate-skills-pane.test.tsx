import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { CandidateSkillsPane } from "../candidate-skills-pane";
import type { ForgeCandidateRecord } from "@/lib/api";

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  accept: vi.fn(),
  reject: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    listForgeCandidates: (...args: unknown[]) => mocks.list(...args),
    acceptForgeCandidate: (...args: unknown[]) => mocks.accept(...args),
    rejectForgeCandidate: (...args: unknown[]) => mocks.reject(...args),
  };
});

function makeCandidate(overrides: Partial<ForgeCandidateRecord> = {}): ForgeCandidateRecord {
  return {
    id: 1,
    query_text: "How does reranking work?",
    convergence_score: 0.97,
    created_at: 1716054000.0,
    default_slug: "how-does-reranking-work",
    trace_excerpt: "iterations: 3 · matches: 5",
    ...overrides,
  };
}

afterEach(() => {
  mocks.list.mockReset();
  mocks.accept.mockReset();
  mocks.reject.mockReset();
});

describe("<CandidateSkillsPane />", () => {
  it("renders nothing while the initial fetch is pending", () => {
    mocks.list.mockReturnValue(new Promise(() => {}));
    const { container } = render(<CandidateSkillsPane />);
    expect(container.firstChild).toBeNull();
  });

  it("renders nothing when there are no candidates", async () => {
    mocks.list.mockResolvedValue({ candidates: [] });
    const { container } = render(<CandidateSkillsPane />);
    await waitFor(() => expect(mocks.list).toHaveBeenCalled());
    expect(container.firstChild).toBeNull();
  });

  it("lists candidates with their query, convergence score, and trace excerpt", async () => {
    mocks.list.mockResolvedValue({
      candidates: [
        makeCandidate({ id: 7, query_text: "First query" }),
        makeCandidate({
          id: 8,
          query_text: "Second query",
          convergence_score: 0.91,
          default_slug: "second-query",
          trace_excerpt: "iterations: 2",
        }),
      ],
    });
    render(<CandidateSkillsPane />);
    await waitFor(() => {
      expect(screen.getByTestId("forge-candidate-pane")).toBeTruthy();
    });
    const rows = screen.getAllByTestId("forge-candidate-row");
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent(/First query/);
    expect(rows[0]).toHaveTextContent(/97% converged/);
    expect(rows[1]).toHaveTextContent(/Second query/);
    expect(rows[1]).toHaveTextContent(/91% converged/);
  });

  it("seeds the slug input from the server's default_slug", async () => {
    mocks.list.mockResolvedValue({
      candidates: [makeCandidate({ id: 1, default_slug: "my-skill" })],
    });
    render(<CandidateSkillsPane />);
    const input = await screen.findByLabelText(/skill slug/i);
    expect(input).toHaveValue("my-skill");
  });

  it("accepts with the default slug when the user does not edit it", async () => {
    mocks.list
      .mockResolvedValueOnce({
        candidates: [makeCandidate({ id: 11 })],
      })
      .mockResolvedValueOnce({ candidates: [] });
    mocks.accept.mockResolvedValue({
      slug: "how-does-reranking-work",
      skill_path: "skills/how-does-reranking-work/SKILL.md",
      candidate_id: 11,
      name: "How does reranking work?",
      description: "auto",
    });

    render(<CandidateSkillsPane />);
    const acceptBtn = await screen.findByRole("button", {
      name: /^Accept \(draft skill\)$/,
    });
    fireEvent.click(acceptBtn);

    await waitFor(() => {
      // Default slug → call without override.
      expect(mocks.accept).toHaveBeenCalledWith(11, undefined);
    });
  });

  it("accepts with an override when the user edits the slug", async () => {
    mocks.list
      .mockResolvedValueOnce({
        candidates: [makeCandidate({ id: 12 })],
      })
      .mockResolvedValueOnce({ candidates: [] });
    mocks.accept.mockResolvedValue({
      slug: "renamed-skill",
      skill_path: "skills/renamed-skill/SKILL.md",
      candidate_id: 12,
      name: "Renamed skill",
      description: "auto",
    });

    render(<CandidateSkillsPane />);
    const input = await screen.findByLabelText(/skill slug/i);
    fireEvent.change(input, { target: { value: "renamed-skill" } });
    fireEvent.click(
      await screen.findByRole("button", { name: /^Accept \(draft skill\)$/ }),
    );

    await waitFor(() => {
      expect(mocks.accept).toHaveBeenCalledWith(12, "renamed-skill");
    });
  });

  it("dismisses via the reject API and refetches", async () => {
    mocks.list
      .mockResolvedValueOnce({ candidates: [makeCandidate({ id: 22 })] })
      .mockResolvedValueOnce({ candidates: [] });
    mocks.reject.mockResolvedValue(undefined);

    render(<CandidateSkillsPane />);
    fireEvent.click(await screen.findByRole("button", { name: /^Dismiss$/ }));

    await waitFor(() => {
      expect(mocks.reject).toHaveBeenCalledWith(22);
    });
  });

  it("surfaces an inline alert when accept rejects (e.g. 409)", async () => {
    mocks.list.mockResolvedValue({ candidates: [makeCandidate({ id: 33 })] });
    mocks.accept.mockRejectedValue(new Error("conflict: skill exists"));

    render(<CandidateSkillsPane />);
    fireEvent.click(
      await screen.findByRole("button", { name: /^Accept \(draft skill\)$/ }),
    );

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/conflict/i);
  });

  it("surfaces an error when the initial fetch rejects", async () => {
    mocks.list.mockRejectedValue(new Error("server down"));
    render(<CandidateSkillsPane />);
    const alert = await screen.findByTestId("forge-candidate-pane-error");
    expect(alert).toHaveTextContent(/server down/);
  });

  it("re-fetches when refreshKey prop bumps", async () => {
    mocks.list.mockResolvedValue({ candidates: [] });
    const { rerender } = render(<CandidateSkillsPane refreshKey={0} />);
    await waitFor(() => expect(mocks.list).toHaveBeenCalledTimes(1));
    rerender(<CandidateSkillsPane refreshKey={1} />);
    await waitFor(() => expect(mocks.list).toHaveBeenCalledTimes(2));
  });
});
