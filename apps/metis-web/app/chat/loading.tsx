export default function ChatLoading() {
  return (
    <div className="flex h-screen w-full overflow-hidden" aria-busy="true" aria-label="Loading chat">
      {/* Sessions sidebar skeleton */}
      <div className="flex w-64 shrink-0 flex-col border-r border-border/40 bg-background/60 p-3 gap-2">
        {/* Search skeleton */}
        <div className="h-8 w-full animate-pulse rounded-lg bg-muted/40" />
        {/* Session items */}
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="h-10 w-full animate-pulse rounded-lg bg-muted/30"
            style={{ opacity: 1 - i * 0.1 }}
          />
        ))}
      </div>
      {/* Main chat area skeleton */}
      <div className="flex flex-1 flex-col">
        {/* Header */}
        <div className="flex h-12 items-center gap-3 border-b border-border/40 px-4">
          <div className="h-5 w-32 animate-pulse rounded bg-muted/40" />
          <div className="h-5 w-16 animate-pulse rounded-full bg-muted/30" />
        </div>
        {/* Message area */}
        <div className="flex-1 space-y-4 p-6">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="flex gap-3">
              <div className="h-8 w-8 shrink-0 animate-pulse rounded-full bg-muted/40" />
              <div className="flex flex-col gap-2 flex-1">
                <div className="h-4 animate-pulse rounded bg-muted/40" style={{ width: `${60 + i * 10}%` }} />
                <div className="h-4 animate-pulse rounded bg-muted/30" style={{ width: `${45 + i * 8}%` }} />
              </div>
            </div>
          ))}
        </div>
        {/* Input bar */}
        <div className="border-t border-border/40 p-4">
          <div className="h-12 w-full animate-pulse rounded-xl bg-muted/30" />
        </div>
      </div>
    </div>
  );
}
