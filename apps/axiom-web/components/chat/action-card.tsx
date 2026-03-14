"use client";

import { AlertTriangle, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ActionRequiredAction } from "@/lib/api";

export type ActionCardStatus = "pending" | "submitting" | "approved" | "denied";

interface ActionCardProps {
  runId: string;
  action: ActionRequiredAction;
  status: ActionCardStatus;
  onApprove?: () => void;
  onDeny?: () => void;
}

export function ActionCard({
  runId: _runId,
  action,
  status,
  onApprove,
  onDeny,
}: ActionCardProps) {
  const isPending = status === "pending";
  const isSubmitting = status === "submitting";

  return (
    <div
      className={cn(
        "rounded-lg border p-3 text-sm",
        status === "approved" && "border-emerald-500/30 bg-emerald-500/5",
        status === "denied" && "border-destructive/30 bg-destructive/5",
        (isPending || isSubmitting) && "border-amber-500/30 bg-amber-500/5",
      )}
    >
      <div className="flex items-start gap-2">
        <AlertTriangle className="mt-0.5 size-4 shrink-0 text-amber-500" />
        <div className="min-w-0 flex-1">
          <p className="font-medium capitalize text-foreground">
            {action.kind.replace(/_/g, " ")}
          </p>
          <p className="mt-0.5 text-muted-foreground">{action.summary}</p>
        </div>
        {status === "approved" && (
          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-500" />
        )}
        {status === "denied" && (
          <XCircle className="mt-0.5 size-4 shrink-0 text-destructive" />
        )}
      </div>

      {(isPending || isSubmitting) && (
        <div className="mt-2 flex gap-2">
          <Button
            size="sm"
            variant="default"
            className="h-7 bg-emerald-600 px-3 text-xs hover:bg-emerald-700"
            disabled={isSubmitting}
            onClick={onApprove}
          >
            {isSubmitting ? (
              <Loader2 className="size-3 animate-spin" />
            ) : (
              "Approve"
            )}
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="h-7 border-destructive/50 px-3 text-xs text-destructive hover:bg-destructive/10"
            disabled={isSubmitting}
            onClick={onDeny}
          >
            Deny
          </Button>
        </div>
      )}
    </div>
  );
}
