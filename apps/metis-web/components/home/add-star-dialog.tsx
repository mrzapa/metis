"use client";

/**
 * AddStarDialog — M24 Phase 4 replacement for the canvas-pick "+ Add" tool.
 *
 * Two-step flow:
 *   1. Input — user pastes text and/or picks files describing the new content.
 *   2. Suggestions — backend ranks the user's existing stars by similarity to
 *      the content; the user either attaches to the best match or creates a
 *      brand-new star. The "Create new star" card is always present (per
 *      ADR 0019 D+1) — even when the recommender doesn't flag
 *      `create_new_suggested`, the user keeps the option.
 *
 * The dialog itself is presentational. The host page owns side effects
 * (uploading files, kicking off the index build, mutating the user-stars
 * settings entry) via the `onConfirm` callback.
 */

import { useEffect, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { recommendStarsForContent } from "@/lib/api";
import type { StarRecommendation } from "@/lib/api";

export type AddDecision =
  | {
      kind: "attach";
      star_id: string;
      content: string;
      files: File[];
    }
  | {
      kind: "create_new";
      content: string;
      files: File[];
      suggested_label?: string;
    };

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (decision: AddDecision) => Promise<void>;
}

type Step = "input" | "suggestions";

export function AddStarDialog({ open, onOpenChange, onConfirm }: Props) {
  const [step, setStep] = useState<Step>("input");
  const [content, setContent] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [recommendations, setRecommendations] = useState<StarRecommendation[]>([]);
  const [createNewSuggested, setCreateNewSuggested] = useState(false);
  const [loadingRecs, setLoadingRecs] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Reset internal state whenever the dialog is closed so the next open
  // starts fresh — without this, suggestions from the previous open
  // would flash back in for ~1 frame before the user types.
  useEffect(() => {
    if (open) return;
    setStep("input");
    setContent("");
    setFiles([]);
    setRecommendations([]);
    setCreateNewSuggested(false);
    setLoadingRecs(false);
    setSubmitting(false);
    setError(null);
  }, [open]);

  const nextDisabled = content.trim().length === 0 && files.length === 0;

  async function handleNext() {
    setError(null);
    setLoadingRecs(true);
    try {
      const seedText = content.trim().length > 0 ? content : files[0]?.name ?? "";
      const result = await recommendStarsForContent(seedText);
      setRecommendations(result.recommendations);
      setCreateNewSuggested(result.create_new_suggested);
      setStep("suggestions");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load suggestions");
    } finally {
      setLoadingRecs(false);
    }
  }

  async function handleAttach(rec: StarRecommendation) {
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm({
        kind: "attach",
        star_id: rec.star_id,
        content,
        files,
      });
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to attach to star");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCreateNew() {
    setSubmitting(true);
    setError(null);
    try {
      await onConfirm({
        kind: "create_new",
        content,
        files,
        suggested_label:
          content.trim().slice(0, 64) || files[0]?.name || undefined,
      });
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create star");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        data-testid="add-star-dialog"
        className="sm:max-w-2xl"
      >
        <DialogHeader>
          <DialogTitle>Add to your constellation</DialogTitle>
          <DialogDescription>
            {step === "input"
              ? "Drop in some content — text, files, or both. Metis will suggest where it best fits."
              : "Attach to a similar star, or create a new one."}
          </DialogDescription>
        </DialogHeader>

        {step === "input" ? (
          <div className="flex flex-col gap-3">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="rounded-2xl border border-dashed border-primary/30 bg-primary/5 px-4 py-6 text-center transition-colors hover:border-primary/50 hover:bg-primary/10"
              data-testid="add-star-dialog-file-trigger"
            >
              <p className="font-medium text-white">
                {files.length > 0
                  ? `${files.length} file${files.length === 1 ? "" : "s"} selected`
                  : "Pick files to add"}
              </p>
              <p className="mt-1 text-xs text-slate-300">
                PDFs, Markdown, transcripts, mixed research sets — anything indexable.
              </p>
            </button>
            <input
              ref={fileInputRef}
              type="file"
              multiple
              className="hidden"
              data-testid="add-star-dialog-file-input"
              onChange={(event) => {
                setFiles(Array.from(event.target.files ?? []));
              }}
            />

            <Textarea
              data-testid="add-star-dialog-textarea"
              placeholder="Or paste a note, abstract, or excerpt…"
              value={content}
              onChange={(event) => setContent(event.target.value)}
              rows={6}
            />

            {error ? (
              <p
                className="text-sm text-destructive"
                data-testid="add-star-dialog-error"
              >
                {error}
              </p>
            ) : null}
          </div>
        ) : (
          <div
            className="flex flex-wrap gap-3"
            data-testid="add-star-dialog-suggestions"
          >
            {recommendations.map((rec) => (
              <div
                key={rec.star_id}
                className="flex w-[200px] flex-col gap-2 rounded-2xl border border-white/10 bg-white/5 p-3"
                data-testid={`add-star-dialog-rec-${rec.star_id}`}
              >
                <div className="flex flex-col gap-1">
                  <span className="font-medium text-white">
                    {rec.label || rec.star_id}
                  </span>
                  <span className="text-xs text-slate-400">
                    {rec.archetype || "—"}
                  </span>
                  <span className="text-xs text-slate-500">
                    similarity {(rec.similarity * 100).toFixed(0)}%
                  </span>
                </div>
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={submitting}
                  aria-label={`Attach to ${rec.label || rec.star_id} (${Math.round(rec.similarity * 100)}% similarity)`}
                  onClick={() => handleAttach(rec)}
                >
                  Attach
                </Button>
              </div>
            ))}
            <div
              className="flex w-[200px] flex-col gap-2 rounded-2xl border border-primary/40 bg-primary/10 p-3"
              data-testid="add-star-dialog-create-new"
            >
              <div className="flex flex-col gap-1">
                <span className="font-medium text-white">Create new star</span>
                <span className="text-xs text-slate-400">
                  {createNewSuggested
                    ? "Recommended — no close match"
                    : "Make a brand-new star for this content"}
                </span>
              </div>
              <Button
                size="sm"
                variant="default"
                disabled={submitting}
                onClick={handleCreateNew}
              >
                Create
              </Button>
            </div>

            {error ? (
              <p
                className="w-full text-sm text-destructive"
                data-testid="add-star-dialog-error"
              >
                {error}
              </p>
            ) : null}
          </div>
        )}

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            Cancel
          </Button>
          {step === "input" ? (
            <Button
              onClick={handleNext}
              disabled={nextDisabled || loadingRecs}
              data-testid="add-star-dialog-next"
            >
              {loadingRecs ? "Loading…" : "Next"}
            </Button>
          ) : (
            <Button
              variant="ghost"
              onClick={() => setStep("input")}
              disabled={submitting}
            >
              Back
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
