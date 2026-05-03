"use client";

interface Props {
  entryCount: number;
  maxEntries: number;
  playbookCount: number;
  lastReflectionAt?: string | null;
}

function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) return "never";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "unknown";
  const diffMs = Math.max(0, Date.now() - then);
  const sec = Math.floor(diffMs / 1000);
  if (sec < 60) return `${sec}s ago`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  const day = Math.floor(hr / 24);
  return `${day}d ago`;
}

export function MemoryStatsRow({
  entryCount,
  maxEntries,
  playbookCount,
  lastReflectionAt,
}: Props) {
  return (
    <div className="grid grid-cols-3 gap-3 text-xs">
      <Tile label="Memory entries" value={`${entryCount} / ${maxEntries}`} />
      <Tile label="Playbooks" value={`${playbookCount}`} />
      <Tile label="Last reflection" value={formatRelativeTime(lastReflectionAt)} />
    </div>
  );
}

function Tile({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/8 bg-black/10 p-3">
      <div className="text-muted-foreground">{label}</div>
      <div className="mt-1 font-medium text-foreground">{value}</div>
    </div>
  );
}
