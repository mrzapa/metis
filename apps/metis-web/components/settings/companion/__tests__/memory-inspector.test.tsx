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
    fetchAssistantMemory: vi.fn(async () => SNAPSHOT.memory),
    fetchAssistantPlaybooks: vi.fn(async () => SNAPSHOT.playbooks),
    deleteAssistantMemoryEntry: vi.fn(async () => ({ ok: true })),
    deleteAssistantMemoryByKind: vi.fn(async () => ({ ok: true, deleted_count: 2 })),
    deleteAssistantMemoryOldest: vi.fn(async () => ({ ok: true, deleted_count: 50 })),
    deleteAssistantPlaybook: vi.fn(async () => ({ ok: true })),
  };
});

describe("MemoryInspector", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("optimistically removes an entry on delete and calls the API with its id", async () => {
    const apiModule = await import("@/lib/api");
    render(<MemoryInspector />);
    await waitFor(() => screen.getByText("Note A"));
    fireEvent.click(screen.getByRole("button", { name: /delete Note A/i }));
    expect(screen.queryByText("Note A")).not.toBeInTheDocument();
    await waitFor(() => {
      expect(apiModule.deleteAssistantMemoryEntry).toHaveBeenCalledWith("m1");
    });
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

  it("does not bulk-clear when confirm is rejected", async () => {
    const confirmSpy = vi.spyOn(window, "confirm").mockReturnValue(false);
    const apiModule = await import("@/lib/api");
    render(<MemoryInspector />);
    await waitFor(() => screen.getByText("Note A"));
    fireEvent.click(screen.getByRole("button", { name: /clear all reflection/i }));
    expect(confirmSpy).toHaveBeenCalled();
    // Both reflection entries should still be in the DOM
    expect(screen.getByText("Note A")).toBeInTheDocument();
    expect(screen.getByText("Note B")).toBeInTheDocument();
    // No API call should have happened
    expect(apiModule.deleteAssistantMemoryByKind).not.toHaveBeenCalled();
    confirmSpy.mockRestore();
  });

  it("renders empty-state CTA when no entries", async () => {
    const apiModule = await import("@/lib/api");
    (apiModule.fetchAssistant as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ...SNAPSHOT,
      memory: [],
      playbooks: [],
    });
    (
      apiModule.fetchAssistantMemory as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValueOnce([]);
    (
      apiModule.fetchAssistantPlaybooks as unknown as ReturnType<typeof vi.fn>
    ).mockResolvedValueOnce([]);
    render(<MemoryInspector />);
    await waitFor(() => screen.getByText(/no reflections yet/i));
    expect(screen.getByRole("link", { name: /open a chat/i })).toHaveAttribute("href", "/chat");
  });

  it("loads the full memory and playbook lists, not the truncated snapshot", async () => {
    const apiModule = await import("@/lib/api");
    render(<MemoryInspector />);
    await waitFor(() => screen.getByText("Note A"));
    // The inspector must call the dedicated list endpoints with high
    // limits so the full working set is available — not rely on
    // ``fetchAssistant`` which truncates memory to 8 / playbooks to 6.
    expect(apiModule.fetchAssistantMemory).toHaveBeenCalledWith(300);
    expect(apiModule.fetchAssistantPlaybooks).toHaveBeenCalledWith(200);
  });

  it("refetches when delete-entry returns {ok: false} (server says row was already gone)", async () => {
    const apiModule = await import("@/lib/api");
    // The server returns ``{ok: false}`` (200) when the row didn't
    // exist — typically because another tab already deleted it. The
    // inspector previously treated this as success and the UI ended
    // up out of sync. It must refetch instead.
    (apiModule.deleteAssistantMemoryEntry as unknown as ReturnType<typeof vi.fn>)
      .mockResolvedValueOnce({ ok: false });
    // Spy on the refetch path: ``fetchAssistantMemory`` is the
    // dedicated list endpoint our refresh hits.
    const memoryFetch = apiModule.fetchAssistantMemory as unknown as ReturnType<
      typeof vi.fn
    >;
    render(<MemoryInspector />);
    await waitFor(() => screen.getByText("Note A"));
    const initialCalls = memoryFetch.mock.calls.length;

    fireEvent.click(screen.getByRole("button", { name: /delete Note A/i }));

    await waitFor(() => {
      expect(memoryFetch.mock.calls.length).toBeGreaterThan(initialCalls);
    });
  });
});
