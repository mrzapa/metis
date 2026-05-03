"use client";

import { useEffect, useState } from "react";
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

  // One-time normalisation: if the loaded values describe a custom seed
  // but ``tone_preset`` still names a built-in preset (typical of data
  // saved from the pre-M23 free-text UI, where ``tone_preset`` defaults
  // to "warm-curious" while ``prompt_seed`` carries the user's
  // override), promote ``tone_preset`` to "custom" so the radio, the
  // resolved-seed preview, and the backend's ``resolve_prompt_seed``
  // path all agree. Marks the form dirty so the user is prompted to
  // save the migrated state — that's the desired surfacing.
  useEffect(() => {
    if (tonePreset !== "custom" && isCustomSeed(tonePreset, promptSeed)) {
      form.setValue("assistant_identity.tone_preset", "custom", { shouldDirty: true });
    }
    // Run once on mount only — guard against feedback loops between
    // ``tonePreset`` updates and the watch above.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  // Mirror the backend's ``resolve_prompt_seed`` rule: if the stored
  // ``prompt_seed`` is a user override (custom tone OR a non-matching
  // free-text seed that legacy data may carry) the override wins.
  // Otherwise fall back to the canonical preset text. Keeps the
  // preview, the form state, and the backend resolver in agreement so
  // the user sees what the AI will actually run on.
  const isCustom = isCustomSeed(tonePreset, promptSeed);
  const resolvedSeed = isCustom
    ? promptSeed
    : TONE_PRESETS[tonePreset] ?? TONE_PRESETS["warm-curious"];

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
              className="accent-primary"
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
            <FieldLabel
              htmlFor="assistant_identity.prompt_seed_override"
              tooltip="Seed prompt used to shape the companion's personality, tone, and boundaries."
            >
              Prompt seed
            </FieldLabel>
            <Textarea
              id="assistant_identity.prompt_seed_override"
              rows={5}
              placeholder="Seed prompt used to shape the companion's tone and behaviour."
              value={promptSeed}
              onChange={(e) => handleOverrideChange(e.target.value)}
            />
          </div>
        )}
      </div>
    </section>
  );
}
