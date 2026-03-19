import { cn } from "@/lib/utils";

interface ProgressIndicatorProps {
  value?: number; // 0–100 for determinate, undefined for indeterminate
  label?: string;
  className?: string;
}

export function ProgressIndicator({ value, label, className }: ProgressIndicatorProps) {
  const indeterminate = value === undefined;

  return (
    <div className={cn("space-y-2", className)}>
      {label && (
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">{label}</span>
          {!indeterminate && (
            <span className="tabular-nums text-foreground">{Math.round(value)}%</span>
          )}
        </div>
      )}
      <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={cn(
            "h-full rounded-full bg-primary transition-all duration-300",
            indeterminate && "animate-progress-indeterminate w-1/3"
          )}
          style={indeterminate ? undefined : { width: `${Math.min(100, Math.max(0, value))}%` }}
        />
      </div>
    </div>
  );
}
