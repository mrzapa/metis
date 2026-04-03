export default function SettingsLoading() {
  return (
    <div className="flex h-screen w-full flex-col" aria-busy="true" aria-label="Loading settings">
      {/* Header */}
      <div className="flex h-14 items-center gap-4 border-b border-border/40 px-6">
        <div className="h-5 w-24 animate-pulse rounded bg-muted/40" />
        <div className="h-5 w-40 animate-pulse rounded bg-muted/30" />
      </div>
      {/* Tabs */}
      <div className="flex gap-2 border-b border-border/40 px-6 pt-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-8 w-20 animate-pulse rounded-lg bg-muted/30" />
        ))}
      </div>
      {/* Content cards */}
      <div className="flex-1 space-y-4 p-6">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-24 w-full animate-pulse rounded-xl bg-muted/20" />
        ))}
      </div>
    </div>
  );
}
