"use client";

import { useArrowState } from "@/hooks/use-arrow-state";
import { Copy, Check, ChevronDown, ChevronUp } from "lucide-react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { EvidenceSource } from "@/lib/chat-types";

const SNIPPET_COLLAPSE_THRESHOLD = 160;

interface EvidenceSourceCardProps {
  source: EvidenceSource;
}

function uniqueText(values: Array<string | undefined | null>): string[] {
  return values
    .map((value) => String(value ?? "").trim())
    .filter(Boolean)
    .filter((value, index, items) => items.indexOf(value) === index);
}

function toPreviewList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((entry) => String(entry ?? "").trim())
    .filter(Boolean)
    .slice(0, 3);
}

export function EvidenceSourceCard({ source: src }: EvidenceSourceCardProps) {
  const [expanded, setExpanded] = useArrowState(false);
  const [copied, setCopied] = useArrowState(false);

  const citation = `[${src.sid}]`;
  const isLong = src.snippet.length > SNIPPET_COLLAPSE_THRESHOLD;
  const label = src.label || src.title || src.source;
  const typeLabel = String(src.entry_type ?? src.type ?? "").trim();
  const matchedChildCountValue = src.metadata?.matched_child_count;
  const matchedChildCount =
    typeof matchedChildCountValue === "number"
      ? matchedChildCountValue
      : null;
  const matchedChildPreviews = toPreviewList(src.metadata?.matched_child_previews);
  const locationHints = uniqueText([
    src.section_hint,
    src.locator,
    src.breadcrumb,
    src.header_path,
    src.anchor,
  ]);
  const contextMeta = uniqueText([
    src.file_path,
    src.date,
    src.timestamp,
    src.speaker,
    src.actor,
  ]);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(citation);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <TooltipProvider>
      <Card className="gap-0 py-0">
        <CardHeader className="px-3 py-1.5">
          <div className="flex items-start justify-between gap-2">
            {/* Sid badge + label */}
            <div className="flex min-w-0 items-start gap-1.5">
              <Badge
                variant="outline"
                className="shrink-0 font-mono text-[10px]"
              >
                {src.sid}
              </Badge>
              <div className="min-w-0">
                <p className="truncate text-xs font-medium leading-snug">
                  {label}
                </p>
                {src.source && src.source !== label && (
                  <p className="truncate text-[10px] text-muted-foreground">
                    {src.source}
                  </p>
                )}
              </div>
            </div>

            {/* Score + copy button */}
            <div className="flex shrink-0 items-center gap-1">
              {typeLabel && (
                <Badge variant="outline" className="text-[10px] capitalize">
                  {typeLabel.replace(/_/g, " ")}
                </Badge>
              )}
              {src.chunk_idx != null && (
                <Badge variant="secondary" className="text-[10px]">
                  Chunk {src.chunk_idx}
                </Badge>
              )}
              {src.score != null && (
                <Badge variant="secondary" className="text-[10px]">
                  {(src.score * 100).toFixed(0)}%
                </Badge>
              )}
              <Tooltip>
                <TooltipTrigger
                  render={(
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      aria-label={`Copy citation ${citation}`}
                    />
                  )}
                  onClick={handleCopy}
                >
                  {copied ? (
                    <Check className="size-3 text-green-500" />
                  ) : (
                    <Copy className="size-3" />
                  )}
                </TooltipTrigger>
                <TooltipContent>
                  {copied ? "Copied!" : `Copy citation ${citation}`}
                </TooltipContent>
              </Tooltip>
            </div>
          </div>
        </CardHeader>

        <CardContent className="px-3 pb-2">
          {locationHints.length > 0 && (
            <div className="mb-1.5 flex flex-wrap gap-0.5">
              {locationHints.map((hint) => (
                <span
                  key={hint}
                  className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground"
                >
                  {hint}
                </span>
              ))}
            </div>
          )}

          {contextMeta.length > 0 && (
            <p className="mb-2 text-[10px] text-muted-foreground/70">
              {contextMeta.join(" · ")}
            </p>
          )}

          {/* Snippet */}
          <p
            className={cn(
                "text-xs leading-snug text-muted-foreground",
              !expanded && isLong && "line-clamp-3",
            )}
          >
            {src.snippet}
          </p>

            {matchedChildCount !== null && matchedChildCount > 0 && (
              <div className="mt-2 rounded-xl border border-white/8 bg-black/10 px-2.5 py-2">
              <p className="text-[10px] font-medium text-foreground">
                Matched child chunks: {matchedChildCount}
              </p>
              {matchedChildPreviews.length > 0 && (
                <div className="mt-1 space-y-1">
                  {matchedChildPreviews.map((preview) => (
                    <p key={preview} className="text-[10px] text-muted-foreground">
                      {preview}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Show more / Show less toggle */}
          {isLong && (
            <button
              type="button"
              className="mt-1 flex items-center gap-0.5 text-[10px] text-muted-foreground/70 hover:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50 rounded"
              aria-expanded={expanded}
              onClick={() => setExpanded((v) => !v)}
            >
              {expanded ? (
                <>
                  Show less <ChevronUp className="size-3" />
                </>
              ) : (
                <>
                  Show more <ChevronDown className="size-3" />
                </>
              )}
            </button>
          )}
        </CardContent>
      </Card>
    </TooltipProvider>
  );
}
