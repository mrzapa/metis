import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryInspector } from "../memory-inspector";

const SNAPSHOT = {
  identity: { name: "METIS", tone_preset: "warm-curious" },
  status: { last_reflection_at: "2026-05-03T10:00:00+00:00" },
  policy: { max_memory_entries: 200 },
  memory: [
    {
      entry_id: "m1",
      kind: "reflection",
      title: "Note A",
      summary: "...",
      created_at: "2026-05-03T09:00:00+00:00",
      confidence: 0.7,
    },
    {
      entry_id: "m2",
      kind: "reflection",
      title: "Note B",
      summary: "...",
      created_at: "2026-05-03T08:00:00+00:00",
      confidence: 0.5,
    },
    {
      entry_id: "m3",
      kind: "skill",
      title: "Skill X",
      summary: "...",
      created_at: "2026-05-03T07:00:00+00:00",
      confidence: 0.9,
    },
  ],
  playbooks: [],
};

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchAssistant: vi.fn(async () => SNAPSHOT),
    deleteAssistantMemoryEntry: vi.fn(async () => ({ ok: true })),
    deleteAssistantMemoryByKind: vi.fn(async () => ({ ok: true, deleted_count: 2 })),
    deleteAssistantPlaybook: vi.fn(async () => ({ ok: true })),
  };
});

describe("MemoryInspector", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("optimistically removes an entry on delete", async () => {
    render(<MemoryInspector />);
    await waitFor(() => screen.getByText("Note A"));
    fireEvent.click(screen.getByRole("button", { name: /delete Note A/i }));
    expect(screen.queryByText("Note A")).not.toBeInTheDocument();
  });

  it("shows confirm and bulk-clears a kind group on accept", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MemoryInspector />);
    await waitFor(() => screen.getByText("Note A"));
    fireEvent.click(screen.getByRole("button", { name: /clear all reflection/i }));
    expect(confirmSpy).toHaveBeenCalled();
    await waitFor(() => {
      expect(screen.queryByText("Note A")).not.toBeInTheDocument();
      expect(screen.queryByText("Note B")).not.toBeInTheDocument();
    });
    confirmSpy.mockRestore();
  });

  it("renders empty-state CTA when no entries", async () => {
    const apiModule = await import("@/lib/api");
    (apiModule.fetchAssistant as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ...SNAPSHOT,
      memory: [],
      playbooks: [],
    });
    render(<MemoryInspector />);
    await waitFor(() => screen.getByText(/no reflections yet/i));
    expect(screen.getByRole("link", { name: /open a chat/i })).toHaveAttribute("href", "/chat");
  });
});
