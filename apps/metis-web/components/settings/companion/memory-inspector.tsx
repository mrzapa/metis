"use client";

import { useEffect, useState } from "react";
import {
  fetchAssistant,
  deleteAssistantMemoryEntry,
  deleteAssistantMemoryByKind,
  deleteAssistantPlaybook,
  clearAssistantMemory,
  type AssistantSnapshot,
  type AssistantMemoryEntry,
  type AssistantPlaybook,
} from "@/lib/api";
import { MemoryStatsRow } from "./memory-stats-row";
import { Button } from "@/components/ui/button";

export function MemoryInspector() {
  const [snapshot, setSnapshot] = useState<AssistantSnapshot | null>(null);

  useEffect(() => {
    fetchAssistant()
      .then(setSnapshot)
      .catch(() => setSnapshot(null));
  }, []);

  if (!snapshot) {
    return <div className="text-sm text-muted-foreground">Loading memory…</div>;
  }

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
    setSnapshot((prev) =>
      prev
        ? { ...prev, memory: prev.memory.filter((e) => e.entry_id !== entry.entry_id) }
        : prev,
    );
    try {
      await deleteAssistantMemoryEntry(entry.entry_id);
    } catch {
      setSnapshot((prev) => (prev ? { ...prev, memory: [...prev.memory, entry] } : prev));
    }
  }

  async function handleClearKind(kind: string) {
    const count = grouped[kind]?.length ?? 0;
    const ok = window.confirm(
      `Clear all ${count} ${kind} entries? This cannot be undone.`,
    );
    if (!ok) return;
    setSnapshot((prev) =>
      prev ? { ...prev, memory: prev.memory.filter((e) => e.kind !== kind) } : prev,
    );
    try {
      await deleteAssistantMemoryByKind(kind);
    } catch {
      try {
        const fresh = await fetchAssistant();
        setSnapshot(fresh);
      } catch {
        /* give up */
      }
    }
  }

  async function handleDeletePlaybook(pb: AssistantPlaybook) {
    setSnapshot((prev) =>
      prev
        ? { ...prev, playbooks: prev.playbooks.filter((p) => p.playbook_id !== pb.playbook_id) }
        : prev,
    );
    try {
      await deleteAssistantPlaybook(pb.playbook_id);
    } catch {
      setSnapshot((prev) =>
        prev ? { ...prev, playbooks: [...prev.playbooks, pb] } : prev,
      );
    }
  }

  async function handleClearOldest50() {
    const oldest = [...entries]
      .sort((a, b) => a.created_at.localeCompare(b.created_at))
      .slice(0, 50);
    const oldestIds = new Set(oldest.map((e) => e.entry_id));
    setSnapshot((prev) =>
      prev ? { ...prev, memory: prev.memory.filter((e) => !oldestIds.has(e.entry_id)) } : prev,
    );
    try {
      await clearAssistantMemory(50);
    } catch {
      try {
        const fresh = await fetchAssistant();
        setSnapshot(fresh);
      } catch {
        /* give up */
      }
    }
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
