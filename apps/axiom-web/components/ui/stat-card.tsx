import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface StatCardProps {
  icon?: ReactNode;
  label: string;
  value: string | number;
  detail?: string;
  className?: string;
}

export function StatCard({ icon, label, value, detail, className }: StatCardProps) {
  return (
    <div className={cn("glass-panel rounded-2xl p-4", className)}>
      <div className="flex items-center gap-3">
        {icon && (
          <div className="flex size-10 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary">
            {icon}
          </div>
        )}
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">
            {label}
          </p>
          <p className="mt-0.5 text-xl font-semibold tabular-nums text-foreground">
            {value}
          </p>
        </div>
      </div>
      {detail && (
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{detail}</p>
      )}
    </div>
  );
}
