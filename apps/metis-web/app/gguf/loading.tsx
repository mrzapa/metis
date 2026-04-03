export default function GgufLoading() {
  return (
    <div className="flex h-screen w-full flex-col" aria-busy="true" aria-label="Loading models">
      <div className="flex h-14 items-center gap-4 border-b border-border/40 px-6">
        <div className="h-5 w-32 animate-pulse rounded bg-muted/40" />
        <div className="h-5 w-20 animate-pulse rounded-full bg-muted/30 ml-auto" />
      </div>
      <div className="flex-1 space-y-3 p-6">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4 h-16 animate-pulse rounded-xl bg-muted/20 px-4">
            <div className="h-8 w-8 shrink-0 rounded-full bg-muted/40" />
            <div className="flex flex-col gap-2 flex-1">
              <div className="h-3 w-40 rounded bg-muted/40" />
              <div className="h-3 w-24 rounded bg-muted/30" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
