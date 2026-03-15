"use client";

import { CheckCircle2, Clock, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { ActionRequiredAction, ChatActionStatus } from "@/lib/chat-types";

export interface ActionLogEntry {
  id: string;
  action: ActionRequiredAction;
  status: ChatActionStatus;
}

interface ActionLogProps {
  entries: ActionLogEntry[];
  className?: string;
}

export function ActionLog({ entries, className }: ActionLogProps) {
  if (entries.length === 0) return null;
  return (
    <div className={cn("space-y-1", className)}>
      {entries.map((entry) => (
        <div
          key={entry.id}
          className="flex items-center gap-1.5 text-xs text-muted-foreground"
        >
          {entry.status === "approved" && (
            <CheckCircle2 className="size-3 text-emerald-500" />
          )}
          {entry.status === "denied" && (
            <XCircle className="size-3 text-destructive" />
          )}
          {(entry.status === "pending" || entry.status === "submitting") && (
            <Clock className="size-3 text-amber-500" />
          )}
          <span className="capitalize">
            {entry.action.kind.replace(/_/g, " ")}
          </span>
          <span className="opacity-60">— {entry.status}</span>
        </div>
      ))}
    </div>
  );
}
