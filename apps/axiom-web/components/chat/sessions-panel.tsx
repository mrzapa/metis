"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useSessions } from "@/hooks/use-sessions";
import { cn } from "@/lib/utils";
import { MessageSquarePlus, Search, Settings, WifiOff } from "lucide-react";

interface SessionsPanelProps {
  selectedId: string | null;
  onSelect: (id: string) => void;
  onNewChat: () => void;
  refreshToken?: number;
}

export function SessionsPanel({ selectedId, onSelect, onNewChat, refreshToken }: SessionsPanelProps) {
  const [search, setSearch] = useState("");
  const { sessions, loading, error, reload } = useSessions(search);

  // Reload the session list whenever the parent bumps the refresh token.
  const prevRefreshTokenRef = useRef(refreshToken);
  useEffect(() => {
    if (refreshToken === undefined || prevRefreshTokenRef.current === refreshToken) return;
    prevRefreshTokenRef.current = refreshToken;
    reload();
  }, [refreshToken, reload]);

  const isConnectionError = error?.toLowerCase().includes("connection error");

  return (
    <div className="glass-panel flex h-full flex-col overflow-hidden rounded-[1.8rem]">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/8 px-4 py-3">
        <h2 className="text-sm font-semibold">Sessions</h2>
        <Button variant="ghost" size="icon" className="size-7" aria-label="New chat" onClick={onNewChat}>
          <MessageSquarePlus className="size-4" />
        </Button>
      </div>

      {/* Search */}
      <div className="relative border-b border-white/8 px-4 py-3">
        <Search className="absolute left-7 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
        <Input
          placeholder="Search sessions…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-9 pl-9 text-sm"
          aria-label="Search sessions"
        />
      </div>

      {/* Session list */}
      <ScrollArea className="flex-1">
        <div className="space-y-1 p-2" role="listbox" aria-label="Sessions">
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
            <div className="flex flex-col items-center gap-2 px-3 py-8 text-center">
              <MessageSquarePlus className="size-5 text-muted-foreground/60" />
              <p className="text-xs text-muted-foreground">
                {search ? "No matching sessions" : "No sessions yet"}
              </p>
              {!search && (
                <Button variant="outline" size="sm" className="mt-1" onClick={onNewChat}>
                  Start a conversation
                </Button>
              )}
            </div>
          )}

          {sessions.map((s) => (
            <button
              key={s.session_id}
              role="option"
              aria-selected={selectedId === s.session_id}
              onClick={() => onSelect(s.session_id)}
              className={cn(
                "flex w-full cursor-pointer flex-col gap-1 rounded-[1.2rem] border px-3 py-3 text-left text-sm transition-all duration-200 hover:border-primary/18 hover:bg-white/6",
                selectedId === s.session_id
                  ? "border-primary/20 bg-primary/10"
                  : "border-transparent bg-transparent"
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

      {/* Footer nav */}
      <div className="border-t border-white/8 px-4 py-3">
        <Link
          href="/settings"
          className="flex items-center gap-2 rounded-xl px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-white/6 hover:text-foreground"
        >
          <Settings className="size-3.5" />
          Settings
        </Link>
      </div>
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
