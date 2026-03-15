"use client";

import { useEffect, useRef, useState } from "react";
import { Copy, FileText, MoreHorizontal, NotebookText } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { ChatMessage } from "@/lib/chat-types";
import {
  formatAnswerWithSourcesForCopy,
  markdownToPlainText,
  normalizeMarkdownForCopy,
} from "@/lib/chat-copy";
import { cn } from "@/lib/utils";

type CopyVariant = "plain" | "markdown" | "answer-and-sources";

type CopyFeedback =
  | {
      tone: "success" | "error";
      message: string;
    }
  | null;

interface AssistantCopyActionsProps {
  message: Pick<ChatMessage, "content" | "run_id" | "sources" | "status">;
}

const COPY_VARIANTS: Array<{
  icon: typeof Copy;
  key: CopyVariant;
  label: string;
}> = [
  { icon: Copy, key: "plain", label: "Copy plain text" },
  { icon: FileText, key: "markdown", label: "Copy markdown" },
  { icon: NotebookText, key: "answer-and-sources", label: "Copy Answer + Sources" },
];

export function AssistantCopyActions({ message }: AssistantCopyActionsProps) {
  const [feedback, setFeedback] = useState<CopyFeedback>(null);
  const resetTimerRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (resetTimerRef.current !== null) {
        window.clearTimeout(resetTimerRef.current);
      }
    };
  }, []);

  if (message.status !== "complete" || !message.run_id) {
    return null;
  }

  const setTransientFeedback = (nextFeedback: Exclude<CopyFeedback, null>) => {
    setFeedback(nextFeedback);

    if (resetTimerRef.current !== null) {
      window.clearTimeout(resetTimerRef.current);
    }

    resetTimerRef.current = window.setTimeout(() => {
      setFeedback(null);
      resetTimerRef.current = null;
    }, nextFeedback.tone === "error" ? 3200 : 1800);
  };

  const buildCopyPayload = (variant: CopyVariant): string => {
    switch (variant) {
      case "plain":
        return markdownToPlainText(message.content);
      case "markdown":
        return normalizeMarkdownForCopy(message.content);
      case "answer-and-sources":
        return formatAnswerWithSourcesForCopy(message.content, message.sources);
    }
  };

  const handleCopy = async (variant: CopyVariant) => {
    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard API unavailable");
      }

      await navigator.clipboard.writeText(buildCopyPayload(variant));
      setTransientFeedback({
        tone: "success",
        message:
          variant === "answer-and-sources"
            ? "Copied answer + sources"
            : variant === "markdown"
            ? "Copied markdown"
            : "Copied plain text",
      });
    } catch {
      setTransientFeedback({
        tone: "error",
        message: "Clipboard unavailable",
      });
    }
  };

  return (
    <div className="ml-2 flex shrink-0 flex-col items-end gap-1">
      <DropdownMenu>
        <DropdownMenuTrigger
          render={
            <Button
              variant="ghost"
              size="icon-xs"
              className="text-muted-foreground/70 hover:text-foreground"
              aria-label="Open answer copy actions"
            />
          }
        >
          <MoreHorizontal className="size-3.5" />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" sideOffset={6} className="w-48">
          {COPY_VARIANTS.map((variant) => {
            const Icon = variant.icon;

            return (
              <DropdownMenuItem
                key={variant.key}
                onClick={() => {
                  void handleCopy(variant.key);
                }}
              >
                <Icon className="size-3.5" />
                {variant.label}
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>

      <p
        aria-live="polite"
        className={cn(
          "min-h-3 text-right text-[10px] leading-none",
          feedback?.tone === "error" ? "text-destructive" : "text-muted-foreground",
        )}
      >
        {feedback?.message ?? ""}
      </p>
    </div>
  );
}
