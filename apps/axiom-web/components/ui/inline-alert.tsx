import type { ReactNode } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { AlertCircle, CheckCircle2, Info, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";

const alertVariants = cva(
  "flex items-start gap-3 rounded-xl border px-4 py-3 text-sm",
  {
    variants: {
      variant: {
        info: "border-primary/20 bg-primary/10 text-foreground",
        success: "border-emerald-500/20 bg-emerald-500/10 text-foreground",
        warning: "border-amber-500/20 bg-amber-500/10 text-foreground",
        error: "border-destructive/20 bg-destructive/10 text-foreground",
      },
    },
    defaultVariants: {
      variant: "info",
    },
  }
);

const ICONS = {
  info: Info,
  success: CheckCircle2,
  warning: TriangleAlert,
  error: AlertCircle,
};

interface InlineAlertProps extends VariantProps<typeof alertVariants> {
  children: ReactNode;
  className?: string;
}

export function InlineAlert({ variant = "info", children, className }: InlineAlertProps) {
  const Icon = ICONS[variant ?? "info"];
  return (
    <div className={cn(alertVariants({ variant }), className)} role="alert">
      <Icon className="mt-0.5 size-4 shrink-0 text-current opacity-70" />
      <div className="min-w-0 flex-1">{children}</div>
    </div>
  );
}
