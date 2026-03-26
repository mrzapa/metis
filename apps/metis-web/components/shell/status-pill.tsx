import { cn } from "@/lib/utils";

type StatusTone =
  | "connected"
  | "checking"
  | "disconnected"
  | "warning"
  | "neutral";

const TONE_STYLES: Record<StatusTone, { shell: string; dot: string }> = {
  connected: {
    shell: "border-emerald-400/20 bg-emerald-400/12 text-emerald-200",
    dot: "bg-emerald-400",
  },
  checking: {
    shell: "border-amber-300/20 bg-amber-300/12 text-amber-100",
    dot: "bg-amber-300",
  },
  disconnected: {
    shell: "border-rose-400/20 bg-rose-400/12 text-rose-100",
    dot: "bg-rose-400",
  },
  warning: {
    shell: "border-chart-4/25 bg-chart-4/12 text-chart-4",
    dot: "bg-chart-4",
  },
  neutral: {
    shell: "border-white/10 bg-white/6 text-foreground/85",
    dot: "bg-foreground/60",
  },
};

interface StatusPillProps {
  label: string;
  tone?: StatusTone;
  animate?: boolean;
  className?: string;
}

export function StatusPill({
  label,
  tone = "neutral",
  animate = false,
  className,
}: StatusPillProps) {
  const toneStyle = TONE_STYLES[tone];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium tracking-[0.16em] uppercase",
        toneStyle.shell,
        className,
      )}
    >
      <span className={cn("size-2 rounded-full", toneStyle.dot, animate && "motion-safe:animate-pulse")} />
      {label}
    </span>
  );
}
