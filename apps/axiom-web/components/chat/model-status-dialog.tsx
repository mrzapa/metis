"use client";

import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { updateSettings } from "@/lib/api";
import { AlertCircle, Loader2 } from "lucide-react";

interface ModelStatusDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  provider: string;
  model: string;
  onSaved: (provider: string, model: string) => void;
}

export function ModelStatusDialog({
  open,
  onOpenChange,
  provider,
  model,
  onSaved,
}: ModelStatusDialogProps) {
  const [draftProvider, setDraftProvider] = useState(provider);
  const [draftModel, setDraftModel] = useState(model);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sync drafts when dialog opens
  useEffect(() => {
    if (open) {
      setDraftProvider(provider);
      setDraftModel(model);
      setError(null);
    }
  }, [open, provider, model]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const saved = await updateSettings({
        llm_provider: draftProvider.trim(),
        llm_model: draftModel.trim(),
      });
      const newProvider = String(saved.llm_provider ?? draftProvider);
      const newModel = String(saved.llm_model ?? draftModel);
      onSaved(newProvider, newModel);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  const canSave = !saving && draftProvider.trim().length > 0 && draftModel.trim().length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Change Model</DialogTitle>
        </DialogHeader>

        <div className="space-y-3">
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Provider
            </label>
            <Input
              value={draftProvider}
              onChange={(e) => setDraftProvider(e.target.value)}
              placeholder="e.g. anthropic, openai, local_gguf"
              disabled={saving}
            />
          </div>

          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Model
            </label>
            <Input
              value={draftModel}
              onChange={(e) => setDraftModel(e.target.value)}
              placeholder="e.g. claude-opus-4-6, gpt-4o"
              disabled={saving}
              onKeyDown={(e) => {
                if (e.key === "Enter" && canSave) handleSave();
              }}
            />
          </div>

          {error && (
            <div className="flex items-start gap-2 rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
              <AlertCircle className="mt-0.5 size-3.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button onClick={handleSave} disabled={!canSave} className="w-full sm:w-auto">
            {saving && <Loader2 className="mr-1.5 size-3.5 animate-spin" />}
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
