export default function DiagnosticsLoading() {
  return (
    <div className="flex h-screen w-full flex-col" aria-busy="true" aria-label="Loading diagnostics">
      <div className="flex h-14 items-center gap-4 border-b border-border/40 px-6">
        <div className="h-5 w-28 animate-pulse rounded bg-muted/40" />
      </div>
      <div className="flex-1 grid grid-cols-2 gap-4 p-6">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-32 animate-pulse rounded-xl bg-muted/20" />
        ))}
      </div>
    </div>
  );
}
