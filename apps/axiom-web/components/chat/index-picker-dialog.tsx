"use client";

import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { fetchIndexes } from "@/lib/api";
import type { IndexSummary } from "@/lib/api";
import { Database, Loader2, AlertCircle } from "lucide-react";

interface IndexPickerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (manifestPath: string, label: string) => void;
}

export function IndexPickerDialog({
  open,
  onOpenChange,
  onSelect,
}: IndexPickerDialogProps) {
  const [indexes, setIndexes] = useState<IndexSummary[] | null>(open ? null : []);
  const [error, setError] = useState<string | null>(null);
  const [syncedOpen, setSyncedOpen] = useState(open);

  if (open !== syncedOpen) {
    setSyncedOpen(open);
    if (open) {
      setIndexes(null);
      setError(null);
    }
  }

  const loading = open && indexes === null && error === null;
  const indexList = indexes ?? [];

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    fetchIndexes()
      .then((nextIndexes) => {
        if (!cancelled) {
          setIndexes(nextIndexes);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load indexes");
          setIndexes([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  function handleSelect(idx: IndexSummary) {
    onSelect(idx.manifest_path, idx.index_id);
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Select an Index</DialogTitle>
        </DialogHeader>

        {loading && (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="size-5 animate-spin text-muted-foreground" />
          </div>
        )}

        {!loading && error && (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <AlertCircle className="size-5 text-destructive" />
            <p className="text-sm text-destructive">{error}</p>
          </div>
        )}

        {!loading && !error && indexList.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-8 text-center">
            <Database className="size-5 text-muted-foreground" />
            <p className="text-sm text-muted-foreground">
              No indexes found. Build one first.
            </p>
          </div>
        )}

        {!loading && !error && indexList.length > 0 && (
          <ScrollArea className="max-h-80">
            <div className="space-y-1.5 pr-1">
              {indexList.map((idx) => (
                <button
                  key={idx.index_id}
                  type="button"
                  onClick={() => handleSelect(idx)}
                  className="flex w-full flex-col gap-1 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors hover:bg-accent"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium truncate">{idx.index_id}</span>
                    <Badge variant="secondary" className="shrink-0 text-[10px]">
                      {idx.backend}
                    </Badge>
                  </div>
                  <div className="flex gap-3 text-[11px] text-muted-foreground">
                    <span>{idx.document_count} doc{idx.document_count !== 1 ? "s" : ""}</span>
                    <span>{idx.chunk_count} chunks</span>
                    <span>{formatDate(idx.created_at)}</span>
                  </div>
                </button>
              ))}
            </div>
          </ScrollArea>
        )}
      </DialogContent>
    </Dialog>
  );
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}
