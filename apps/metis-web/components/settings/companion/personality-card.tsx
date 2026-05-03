"use client";

import { useState } from "react";
import type { UseFormReturn } from "react-hook-form";
import type { AssistantFormValues } from "@/app/settings/page";
import { FieldLabel } from "@/app/settings/page";
import {
  TONE_PRESETS,
  TONE_PRESET_LABELS,
  isCustomSeed,
  type TonePreset,
} from "@/lib/companion-voice";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";

interface Props {
  form: UseFormReturn<AssistantFormValues>;
}

export function PersonalityCard({ form }: Props) {
  const tonePreset = (form.watch("assistant_identity.tone_preset") ?? "warm-curious") as TonePreset;
  const promptSeed = form.watch("assistant_identity.prompt_seed") ?? "";
  const [showOverride, setShowOverride] = useState(false);

  function handlePresetChange(next: TonePreset) {
    const currentlyCustom = isCustomSeed(tonePreset, promptSeed);
    if (currentlyCustom && next !== "custom") {
      const ok = window.confirm(
        "Switching presets will overwrite your custom prompt seed. Continue?",
      );
      if (!ok) return;
    }
    form.setValue("assistant_identity.tone_preset", next, { shouldDirty: true });
    if (next !== "custom" && next in TONE_PRESETS) {
      form.setValue(
        "assistant_identity.prompt_seed",
        TONE_PRESETS[next],
        { shouldDirty: true },
      );
    }
  }

  function handleOverrideChange(value: string) {
    form.setValue("assistant_identity.prompt_seed", value, { shouldDirty: true });
    if (tonePreset !== "custom") {
      form.setValue("assistant_identity.tone_preset", "custom", { shouldDirty: true });
    }
  }

  const resolvedSeed =
    tonePreset === "custom"
      ? promptSeed
      : (TONE_PRESETS as Record<string, string>)[tonePreset] ?? TONE_PRESETS["warm-curious"];

  return (
    <section className="space-y-4 rounded-2xl border border-white/8 bg-black/10 p-4">
      <div>
        <h3 className="text-sm font-semibold">Personality</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">How should METIS speak?</p>
      </div>

      <fieldset className="space-y-2">
        {(Object.keys(TONE_PRESET_LABELS) as TonePreset[]).map((preset) => (
          <label key={preset} className="flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="radio"
              name="tone_preset"
              checked={tonePreset === preset}
              onChange={() => handlePresetChange(preset)}
              aria-label={TONE_PRESET_LABELS[preset]}
            />
            {TONE_PRESET_LABELS[preset]}
          </label>
        ))}
      </fieldset>

      <div className="space-y-2 rounded-xl border border-white/8 bg-black/20 p-3">
        <div className="text-xs font-medium text-muted-foreground">Resolved prompt seed</div>
        <p data-testid="resolved-seed-preview" className="whitespace-pre-wrap text-xs">
          {resolvedSeed}
        </p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setShowOverride((v) => !v)}
        >
          {showOverride ? "Hide" : "Edit prompt seed directly"}
        </Button>
        {showOverride && (
          <div className="space-y-1.5">
            <FieldLabel htmlFor="assistant_identity.prompt_seed_override">Prompt seed</FieldLabel>
            <Textarea
              id="assistant_identity.prompt_seed_override"
              rows={5}
              value={promptSeed}
              onChange={(e) => handleOverrideChange(e.target.value)}
            />
          </div>
        )}
      </div>
    </section>
  );
}
