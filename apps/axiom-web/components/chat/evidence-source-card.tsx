"use client";

import { useState } from "react";
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

export function EvidenceSourceCard({ source: src }: EvidenceSourceCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

  const citation = `[${src.sid}]`;
  const isLong = src.snippet.length > SNIPPET_COLLAPSE_THRESHOLD;

  const handleCopy = async () => {
    await navigator.clipboard.writeText(citation);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <TooltipProvider>
      <Card className="gap-0 py-0">
        <CardHeader className="px-3 py-2">
          <div className="flex items-start justify-between gap-2">
            {/* Sid badge + label */}
            <div className="flex min-w-0 items-start gap-1.5">
              <Badge
                variant="outline"
                className="shrink-0 font-mono text-[10px]"
              >
                {src.sid}
              </Badge>
              <span className="text-xs font-medium leading-snug">
                {src.title || src.source}
              </span>
            </div>

            {/* Score + copy button */}
            <div className="flex shrink-0 items-center gap-1">
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
          {/* Section hint */}
          {src.section_hint && (
            <p className="mb-1 truncate text-[10px] text-muted-foreground">
              {src.section_hint}
            </p>
          )}

          {/* Breadcrumb (only if different from section_hint) */}
          {src.breadcrumb && src.breadcrumb !== src.section_hint && (
            <p className="mb-1 truncate text-[10px] text-muted-foreground/70">
              {src.breadcrumb}
            </p>
          )}

          {/* Snippet */}
          <p
            className={cn(
              "text-xs text-muted-foreground",
              !expanded && isLong && "line-clamp-3",
            )}
          >
            {src.snippet}
          </p>

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
