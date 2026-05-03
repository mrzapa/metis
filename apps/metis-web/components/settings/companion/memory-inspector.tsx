"use client";

import { useEffect, useState } from "react";
import {
  fetchAssistant,
  fetchAssistantMemory,
  fetchAssistantPlaybooks,
  deleteAssistantMemoryEntry,
  deleteAssistantMemoryByKind,
  deleteAssistantMemoryOldest,
  deleteAssistantPlaybook,
  type AssistantSnapshot,
  type AssistantMemoryEntry,
  type AssistantPlaybook,
} from "@/lib/api";
import { MemoryStatsRow } from "./memory-stats-row";
import { Button } from "@/components/ui/button";

type LoadState =
  | { status: "loading" }
  | { status: "ready"; snapshot: AssistantSnapshot }
  | { status: "error"; message: string };

export function MemoryInspector() {
  const [load, setLoad] = useState<LoadState>({ status: "loading" });

  async function refresh() {
    setLoad({ status: "loading" });
    try {
      // The ``fetchAssistant`` snapshot truncates ``memory`` to 8
      // entries and ``playbooks`` to 6 (sized for the dock). The
      // inspector needs the *full* working set up to the policy cap so
      // the at-cap banner, the entry count, and the per-kind grouping
      // all reflect reality. Fetch the small fields (identity, policy,
      // status) from the snapshot but pull memory/playbooks from the
      // dedicated list endpoints with high limits.
      const [snapshot, memory, playbooks] = await Promise.all([
        fetchAssistant(),
        fetchAssistantMemory(300),
        fetchAssistantPlaybooks(200),
      ]);
      setLoad({
        status: "ready",
        snapshot: { ...snapshot, memory, playbooks },
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load memory.";
      setLoad({ status: "error", message });
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  // Helper: mutate the ready snapshot in place. No-op if not ready.
  function setSnapshot(updater: (prev: AssistantSnapshot) => AssistantSnapshot) {
    setLoad((prev) =>
      prev.status === "ready" ? { status: "ready", snapshot: updater(prev.snapshot) } : prev,
    );
  }

  if (load.status === "loading") {
    return <div className="text-sm text-muted-foreground">Loading memory…</div>;
  }

  if (load.status === "error") {
    return (
      <section className="space-y-3 rounded-2xl border border-rose-400/20 bg-rose-400/5 p-4">
        <h3 className="text-sm font-semibold">Memory</h3>
        <p className="text-xs text-muted-foreground">Couldn&apos;t load memory: {load.message}</p>
        <Button type="button" variant="ghost" size="sm" onClick={refresh}>
          Retry
        </Button>
      </section>
    );
  }

  const snapshot = load.snapshot;
  const entries: AssistantMemoryEntry[] = snapshot.memory ?? [];
  const playbooks: AssistantPlaybook[] = snapshot.playbooks ?? [];

  if (entries.length === 0 && playbooks.length === 0) {
    return (
      <section className="space-y-3 rounded-2xl border border-white/8 bg-black/10 p-4">
        <h3 className="text-sm font-semibold">Memory</h3>
        <p className="text-xs text-muted-foreground">
          No reflections yet.{" "}
          <a href="/chat" className="underline">
            Open a chat
          </a>{" "}
          or run autonomous research to seed memory.
        </p>
      </section>
    );
  }

  const grouped = entries.reduce<Record<string, AssistantMemoryEntry[]>>((acc, e) => {
    (acc[e.kind] ||= []).push(e);
    return acc;
  }, {});

  async function handleDeleteEntry(entry: AssistantMemoryEntry) {
    setSnapshot((prev) => ({
      ...prev,
      memory: prev.memory.filter((e) => e.entry_id !== entry.entry_id),
    }));
    try {
      await deleteAssistantMemoryEntry(entry.entry_id);
    } catch {
      setSnapshot((prev) => ({ ...prev, memory: [...prev.memory, entry] }));
    }
  }

  async function handleClearKind(kind: string) {
    const count = grouped[kind]?.length ?? 0;
    const ok = window.confirm(
      `Clear all ${count} ${kind} entries? This cannot be undone.`,
    );
    if (!ok) return;
    setSnapshot((prev) => ({
      ...prev,
      memory: prev.memory.filter((e) => e.kind !== kind),
    }));
    try {
      await deleteAssistantMemoryByKind(kind);
    } catch {
      // Restore the full list from the server if the bulk delete
      // errored — we already optimistically removed the kind locally.
      void refresh();
    }
  }

  async function handleDeletePlaybook(pb: AssistantPlaybook) {
    setSnapshot((prev) => ({
      ...prev,
      playbooks: prev.playbooks.filter((p) => p.playbook_id !== pb.playbook_id),
    }));
    try {
      await deleteAssistantPlaybook(pb.playbook_id);
    } catch {
      setSnapshot((prev) => ({ ...prev, playbooks: [...prev.playbooks, pb] }));
    }
  }

  async function handleClearOldest50() {
    // Optimistic: hide oldest 50 immediately for snappy UI
    const oldest = [...entries]
      .sort((a, b) => a.created_at.localeCompare(b.created_at))
      .slice(0, 50);
    const oldestIds = new Set(oldest.map((e) => e.entry_id));
    setSnapshot((prev) => ({
      ...prev,
      memory: prev.memory.filter((e) => !oldestIds.has(e.entry_id)),
    }));
    // Always refetch — server picks which 50 to delete, may differ from our optimistic guess
    try {
      await deleteAssistantMemoryOldest(50);
    } catch {
      // fall through to refetch anyway
    }
    // Refresh from the dedicated list endpoints (not the truncated
    // snapshot) so the inspector reflects the full post-delete state.
    await refresh();
  }

  const maxEntries = snapshot.policy?.max_memory_entries ?? 200;
  const atCap = entries.length >= maxEntries;

  return (
    <section className="space-y-4 rounded-2xl border border-white/8 bg-black/10 p-4">
      <div>
        <h3 className="text-sm font-semibold">Memory</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          What METIS remembers from your chats and reflections.
        </p>
      </div>

      <MemoryStatsRow
        entryCount={entries.length}
        maxEntries={maxEntries}
        playbookCount={playbooks.length}
        lastReflectionAt={snapshot.status?.last_reflection_at}
      />

      {atCap && (
        <div className="flex items-center justify-between rounded-xl border border-amber-500/20 bg-amber-500/5 px-3 py-2 text-xs">
          <span>Older entries auto-evict at the cap.</span>
          <Button type="button" variant="ghost" size="sm" onClick={handleClearOldest50}>
            Clear oldest 50
          </Button>
        </div>
      )}

      <div className="space-y-3">
        {Object.entries(grouped).map(([kind, list]) => (
          <details key={kind} open className="rounded-xl border border-white/8 bg-black/20 p-3">
            <summary className="flex cursor-pointer items-center justify-between text-xs font-medium">
              <span>
                {kind} ({list.length})
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-label={`clear all ${kind}`}
                onClick={(e) => {
                  e.preventDefault();
                  void handleClearKind(kind);
                }}
              >
                clear all
              </Button>
            </summary>
            <ul className="mt-2 space-y-2">
              {list.map((entry) => (
                <li
                  key={entry.entry_id}
                  className="flex items-start justify-between gap-2 text-xs"
                >
                  <div className="min-w-0">
                    <div className="font-medium">{entry.title}</div>
                    <div className="line-clamp-2 text-muted-foreground">{entry.summary}</div>
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    aria-label={`delete ${entry.title}`}
                    onClick={() => void handleDeleteEntry(entry)}
                  >
                    ✕
                  </Button>
                </li>
              ))}
            </ul>
          </details>
        ))}
      </div>

      {playbooks.length > 0 && (
        <details open className="rounded-xl border border-white/8 bg-black/20 p-3">
          <summary className="cursor-pointer text-xs font-medium">
            Playbooks ({playbooks.length})
          </summary>
          <ul className="mt-2 space-y-2">
            {playbooks.map((pb) => (
              <li
                key={pb.playbook_id}
                className="flex items-start justify-between gap-2 text-xs"
              >
                <div>
                  <div className="font-medium">
                    {pb.title}
                    {pb.active ? " · active" : ""}
                  </div>
                  {pb.bullets.length > 0 && (
                    <div className="text-muted-foreground">{pb.bullets[0]}</div>
                  )}
                </div>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  aria-label={`delete playbook ${pb.title}`}
                  onClick={() => void handleDeletePlaybook(pb)}
                >
                  ✕
                </Button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
