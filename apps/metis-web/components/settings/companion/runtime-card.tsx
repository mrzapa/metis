"use client";

import type { UseFormReturn } from "react-hook-form";
import type { AssistantFormValues } from "@/app/settings/page";
import { FieldLabel, ToggleRow } from "@/app/settings/page";
import { Input } from "@/components/ui/input";

interface Props {
  form: UseFormReturn<AssistantFormValues>;
}

export function RuntimeCard({ form }: Props) {
  const { register: registerAssistant, watch: watchAssistant, setValue: setAssistantValue } = form;

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold">Runtime</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Configure the local or remote model source used by the companion.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_runtime.provider">Provider</FieldLabel>
          <Input
            id="assistant_runtime.provider"
            type="text"
            {...registerAssistant("assistant_runtime.provider")}
          />
        </div>
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_runtime.model">Model</FieldLabel>
          <Input
            id="assistant_runtime.model"
            type="text"
            {...registerAssistant("assistant_runtime.model")}
          />
        </div>
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_runtime.local_gguf_model_path">GGUF path</FieldLabel>
          <Input
            id="assistant_runtime.local_gguf_model_path"
            type="text"
            {...registerAssistant("assistant_runtime.local_gguf_model_path")}
          />
        </div>
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_runtime.bootstrap_state">Bootstrap state</FieldLabel>
          <Input
            id="assistant_runtime.bootstrap_state"
            type="text"
            {...registerAssistant("assistant_runtime.bootstrap_state")}
          />
        </div>
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_runtime.local_gguf_context_length">
            Context length
          </FieldLabel>
          <Input
            id="assistant_runtime.local_gguf_context_length"
            type="number"
            min={512}
            {...registerAssistant("assistant_runtime.local_gguf_context_length", {
              valueAsNumber: true,
            })}
          />
        </div>
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_runtime.local_gguf_gpu_layers">GPU layers</FieldLabel>
          <Input
            id="assistant_runtime.local_gguf_gpu_layers"
            type="number"
            min={0}
            {...registerAssistant("assistant_runtime.local_gguf_gpu_layers", {
              valueAsNumber: true,
            })}
          />
        </div>
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_runtime.local_gguf_threads">Threads</FieldLabel>
          <Input
            id="assistant_runtime.local_gguf_threads"
            type="number"
            min={0}
            {...registerAssistant("assistant_runtime.local_gguf_threads", {
              valueAsNumber: true,
            })}
          />
        </div>
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_runtime.recommended_model_name">Recommended model</FieldLabel>
          <Input
            id="assistant_runtime.recommended_model_name"
            type="text"
            {...registerAssistant("assistant_runtime.recommended_model_name")}
          />
        </div>
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_runtime.recommended_quant">Recommended quant</FieldLabel>
          <Input
            id="assistant_runtime.recommended_quant"
            type="text"
            {...registerAssistant("assistant_runtime.recommended_quant")}
          />
        </div>
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_runtime.recommended_use_case">Recommended use case</FieldLabel>
          <Input
            id="assistant_runtime.recommended_use_case"
            type="text"
            {...registerAssistant("assistant_runtime.recommended_use_case")}
          />
        </div>
      </div>

      <div className="space-y-2">
        <ToggleRow
          id="assistant_runtime.fallback_to_primary"
          label="Fallback to primary"
          description="Use the main workspace model when the companion runtime is unavailable."
          checked={watchAssistant("assistant_runtime.fallback_to_primary")}
          onChange={(v) => setAssistantValue("assistant_runtime.fallback_to_primary", v)}
        />
        <ToggleRow
          id="assistant_runtime.auto_bootstrap"
          label="Auto bootstrap"
          description="Automatically prepare the companion runtime when needed."
          checked={watchAssistant("assistant_runtime.auto_bootstrap")}
          onChange={(v) => setAssistantValue("assistant_runtime.auto_bootstrap", v)}
        />
        <ToggleRow
          id="assistant_runtime.auto_install"
          label="Auto install"
          description="Allow the app to install a recommended local model automatically."
          checked={watchAssistant("assistant_runtime.auto_install")}
          onChange={(v) => setAssistantValue("assistant_runtime.auto_install", v)}
        />
      </div>
    </div>
  );
}
