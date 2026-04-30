import React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { AbsorbForm } from "../absorb-form";
import type { ForgeAbsorbResponse } from "@/lib/api";

const mockAbsorb = vi.hoisted(() => ({
  fn: vi.fn<(...args: unknown[]) => Promise<ForgeAbsorbResponse>>(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    absorbForgeUrl: (...args: unknown[]) => mockAbsorb.fn(...args),
  };
});

const arxivResponse: ForgeAbsorbResponse = {
  source_kind: "arxiv",
  title: "Cross-encoder reranking that matters",
  summary: "We propose a sparse cross-encoder reranking method.",
  source_url: "https://arxiv.org/abs/2501.12345",
  matches: [
    {
      id: "reranker",
      name: "Reranker",
      pillar: "cortex",
      description: "Cross-encoder over retrieved passages.",
      match_score: 4,
    },
  ],
  proposal: {
    name: "Sparse Cross-Encoder Reranking",
    claim: "Reranks BM25 hits with a small cross-encoder.",
    pillar_guess: "cortex",
    implementation_sketch: "Score top-k hits with a cross-encoder.",
  },
  error: null,
};

afterEach(() => {
  mockAbsorb.fn.mockReset();
});

describe("<AbsorbForm />", () => {
  it("renders the form scaffolding with an URL input + submit button", () => {
    render(<AbsorbForm />);
    expect(screen.getByLabelText(/paper or article URL/i)).toBeTruthy();
    expect(
      screen.getByRole("button", { name: /^absorb$/i }),
    ).toBeTruthy();
  });

  it("does nothing when the form is submitted with an empty URL", () => {
    render(<AbsorbForm />);
    fireEvent.submit(screen.getByTestId("forge-absorb-form"));
    expect(mockAbsorb.fn).not.toHaveBeenCalled();
  });

  it("calls absorbForgeUrl with the trimmed URL on submit", async () => {
    mockAbsorb.fn.mockResolvedValue(arxivResponse);
    render(<AbsorbForm />);
    const input = screen.getByLabelText(/paper or article URL/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "  https://arxiv.org/abs/2501.12345  " } });
    fireEvent.click(screen.getByRole("button", { name: /^absorb$/i }));

    await waitFor(() => {
      expect(mockAbsorb.fn).toHaveBeenCalledWith("https://arxiv.org/abs/2501.12345");
    });
  });

  it("shows the proposal + matches when the API returns an arxiv result", async () => {
    mockAbsorb.fn.mockResolvedValue(arxivResponse);
    render(<AbsorbForm />);
    fireEvent.change(screen.getByLabelText(/paper or article URL/i), {
      target: { value: "https://arxiv.org/abs/2501.12345" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^absorb$/i }));

    const proposal = await screen.findByTestId("forge-absorb-proposal");
    expect(proposal).toHaveTextContent(/Sparse Cross-Encoder Reranking/);
    expect(proposal).toHaveTextContent(/Reranks BM25 hits/);

    const matches = screen.getByTestId("forge-absorb-matches");
    expect(matches).toHaveTextContent(/Reranker/);
  });

  it("renders an unsupported-source message when the response is unsupported", async () => {
    mockAbsorb.fn.mockResolvedValue({
      source_kind: "unsupported",
      title: null,
      summary: null,
      source_url: "https://example.com/blog",
      matches: [],
      proposal: null,
      error: null,
    });
    render(<AbsorbForm />);
    fireEvent.change(screen.getByLabelText(/paper or article URL/i), {
      target: { value: "https://example.com/blog" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^absorb$/i }));

    const result = await screen.findByTestId("forge-absorb-result");
    expect(result).toHaveTextContent(/arxiv.org/i);
    expect(result).toHaveTextContent(/follow-up phase/i);
  });

  it("surfaces an inline alert when absorbForgeUrl rejects", async () => {
    mockAbsorb.fn.mockRejectedValue(new Error("server angry"));
    render(<AbsorbForm />);
    fireEvent.change(screen.getByLabelText(/paper or article URL/i), {
      target: { value: "https://arxiv.org/abs/2501.12345" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^absorb$/i }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/server angry/);
  });

  it("disables the submit button while the request is in flight", async () => {
    let resolveAbsorb: ((value: ForgeAbsorbResponse) => void) | null = null;
    mockAbsorb.fn.mockImplementation(
      () =>
        new Promise<ForgeAbsorbResponse>((resolve) => {
          resolveAbsorb = resolve;
        }),
    );
    render(<AbsorbForm />);
    fireEvent.change(screen.getByLabelText(/paper or article URL/i), {
      target: { value: "https://arxiv.org/abs/2501.12345" },
    });
    const button = screen.getByRole("button", { name: /^absorb$/i });
    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /absorbing/i })).toBeDisabled();
    });

    resolveAbsorb?.(arxivResponse);
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /^absorb$/i })).not.toBeDisabled();
    });
  });

  it("renders a hint about LLM configuration when the proposal is missing", async () => {
    mockAbsorb.fn.mockResolvedValue({
      ...arxivResponse,
      proposal: null,
    });
    render(<AbsorbForm />);
    fireEvent.change(screen.getByLabelText(/paper or article URL/i), {
      target: { value: "https://arxiv.org/abs/2501.12345" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^absorb$/i }));

    const hint = await screen.findByText(/LLM provider is configured/i);
    expect(hint).toBeTruthy();
  });
});
