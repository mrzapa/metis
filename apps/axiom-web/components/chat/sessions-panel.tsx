"use client";

import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useSessions } from "@/hooks/use-sessions";
import { cn } from "@/lib/utils";
import { MessageSquarePlus, Search, WifiOff } from "lucide-react";

interface SessionsPanelProps {
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
}

export function SessionsPanel({ selectedId, onSelect, onNewChat }: SessionsPanelProps) {
  const [search, setSearch] = useState("");
  const { sessions, loading, error } = useSessions(search);

  const isConnectionError = error?.toLowerCase().includes("connection error");

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-3 py-2">
        <h2 className="text-sm font-semibold">Sessions</h2>
        <Button variant="ghost" size="icon" className="size-7" aria-label="New chat" onClick={onNewChat}>
          <MessageSquarePlus className="size-4" />
        </Button>
      </div>

      {/* Search */}
      <div className="relative border-b px-3 py-2">
        <Search className="absolute left-5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search sessions…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-8 pl-8 text-sm"
          aria-label="Search sessions"
        />
      </div>

      {/* Session list */}
      <ScrollArea className="flex-1">
        <div className="p-1" role="listbox" aria-label="Sessions">
          {loading && (
            <p className="px-3 py-8 text-center text-xs text-muted-foreground">
              Loading…
            </p>
          )}

          {error && (
            <div className="flex flex-col items-center gap-2 px-3 py-8 text-center">
              {isConnectionError && (
                <WifiOff className="size-5 text-muted-foreground" />
              )}
              <p className="text-xs text-muted-foreground">
                {isConnectionError
                  ? "Server unreachable"
                  : "Could not load sessions"}
              </p>
            </div>
          )}

          {!loading && !error && sessions.length === 0 && (
            <p className="px-3 py-8 text-center text-xs text-muted-foreground">
              {search ? "No matching sessions" : "No sessions yet"}
            </p>
          )}

          {sessions.map((s) => (
            <button
              key={s.session_id}
              role="option"
              aria-selected={selectedId === s.session_id}
              onClick={() => onSelect(s.session_id)}
              className={cn(
                "flex w-full flex-col gap-0.5 rounded-md px-3 py-2 text-left text-sm transition-colors hover:bg-accent",
                selectedId === s.session_id && "bg-accent"
              )}
            >
              <span className="truncate font-medium">
                {s.title || "Untitled"}
              </span>
              <span className="truncate text-xs text-muted-foreground">
                {s.summary || formatDate(s.updated_at)}
              </span>
              {(s.mode || s.llm_provider) && (
                <div className="mt-0.5 flex gap-1">
                  {s.mode && (
                    <span className="rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">
                      {s.mode}
                    </span>
                  )}
                  {s.llm_provider && (
                    <span className="rounded bg-muted px-1 py-0.5 text-[10px] text-muted-foreground">
                      {s.llm_provider}
                    </span>
                  )}
                </div>
              )}
            </button>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}
