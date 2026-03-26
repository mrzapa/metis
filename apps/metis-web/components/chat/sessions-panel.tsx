"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { AnimatedLucideIcon } from "@/components/ui/animated-lucide-icon";
import { useArrowState } from "@/hooks/use-arrow-state";
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
  const [search, setSearch] = useArrowState("");
  const { sessions, loading, error, reload } = useSessions(search);

  // Reload the session list whenever the parent bumps the refresh token.
  const prevRefreshTokenRef = useRef(refreshToken);
  useEffect(() => {
    if (refreshToken === undefined || prevRefreshTokenRef.current === refreshToken) return;
    prevRefreshTokenRef.current = refreshToken;
    reload();
  }, [refreshToken, reload]);

  // ── Infinite-scroll state ─────────────────────────────────────────────────
  const DISPLAY_STEP = 20;
  const [displayCount, setDisplayCount] = useState(DISPLAY_STEP);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const sentinelRef = useRef<HTMLDivElement>(null);
  // Sync a ref so the IntersectionObserver closure always sees the latest count
  const displayCountRef = useRef(displayCount);
  displayCountRef.current = displayCount;

  // Reset visible window whenever the underlying sessions list changes (new search)
  useEffect(() => {
    setDisplayCount(DISPLAY_STEP);
  }, [sessions]);

  // Wire up the IntersectionObserver to reveal more items as the user scrolls
  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    // Walk up the DOM to find the Base UI scroll-area viewport that wraps us
    const viewport = sentinel.closest<HTMLElement>('[data-slot="scroll-area-viewport"]');
    if (!viewport) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting && displayCountRef.current < sessions.length) {
          setIsLoadingMore(true);
          requestAnimationFrame(() => {
            setDisplayCount((c) => c + DISPLAY_STEP);
            setIsLoadingMore(false);
          });
        }
      },
      { root: viewport, rootMargin: "0px 0px 200px 0px", threshold: 0 },
    );

    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [sessions]);

  const visibleSessions = sessions.slice(0, displayCount);

  const isConnectionError = error?.toLowerCase().includes("connection error");

  return (
    <div className="chat-pane-surface flex h-full min-h-0 flex-col overflow-hidden rounded-[1.9rem]">
      {/* Header */}
      <div className="glass-strip flex items-center justify-between border-b border-white/10 px-4 py-3">
        <h2 className="text-sm font-semibold">Sessions</h2>
        <Button variant="ghost" size="icon" className="size-7" aria-label="New chat" onClick={onNewChat}>
          <AnimatedLucideIcon icon={MessageSquarePlus} mode="hoverLift" className="size-4" />
        </Button>
      </div>

      {/* Search */}
      <div className="glass-strip relative border-b border-white/10 px-4 py-3">
        <AnimatedLucideIcon
          icon={Search}
          mode="hoverLift"
          className="absolute left-7 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground"
        />
        <Input
          placeholder="Search sessions…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="glass-micro-surface h-9 border-white/10 bg-white/6 pl-9 text-sm"
          aria-label="Search sessions"
        />
      </div>

      {/* Session list */}
      <ScrollArea className="flex-1 min-h-0">
        <div className="space-y-1.5 p-2.5" role="listbox" aria-label="Sessions">
          {loading && (
            <p className="px-3 py-8 text-center text-xs text-muted-foreground">
              Loading…
            </p>
          )}

          {error && (
            <div className="flex flex-col items-center gap-2 px-3 py-8 text-center">
              {isConnectionError && (
                <AnimatedLucideIcon icon={WifiOff} mode="idlePulse" className="size-5 text-muted-foreground" />
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
              <AnimatedLucideIcon icon={MessageSquarePlus} mode="idlePulse" className="size-5 text-muted-foreground/60" />
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

          {visibleSessions.map((s) => (
            <button
              key={s.session_id}
              role="option"
              aria-selected={selectedId === s.session_id}
              onClick={() => onSelect(s.session_id)}
              className={cn(
                "glass-micro-surface flex w-full cursor-pointer flex-col gap-1 rounded-[1.2rem] px-3 py-3 text-left text-sm transition-all duration-200 hover:border-primary/18 hover:bg-white/8",
                selectedId === s.session_id
                  ? "border-primary/20 bg-primary/10"
                  : ""
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
                    <span className="chat-control-pill rounded-full px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {s.mode}
                    </span>
                  )}
                  {s.llm_provider && (
                    <span className="chat-control-pill rounded-full px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {s.llm_provider}
                    </span>
                  )}
                </div>
              )}
            </button>
          ))}

          {/* Infinite-scroll sentinel — observed by IntersectionObserver above */}
          <div ref={sentinelRef} className="h-1" aria-hidden="true" />

          {/* Subtle loading indicator while the next batch is being revealed */}
          {isLoadingMore && (
            <div className="flex items-center justify-center py-3">
              <span className="inline-flex gap-1">
                <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground/40 [animation-delay:0ms]" />
                <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground/40 [animation-delay:150ms]" />
                <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground/40 [animation-delay:300ms]" />
              </span>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Footer nav */}
      <div className="glass-strip border-t border-white/10 px-4 py-3">
        <Link
          href="/settings"
          className="glass-micro-surface flex items-center gap-2 rounded-xl px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-white/8 hover:text-foreground"
        >
          <AnimatedLucideIcon icon={Settings} mode="hoverLift" className="size-3.5" />
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
