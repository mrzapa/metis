"use client";

import type { UseFormReturn } from "react-hook-form";
import type { AssistantFormValues } from "@/app/settings/page";
import { FieldLabel, ToggleRow } from "@/app/settings/page";
import { Input } from "@/components/ui/input";

interface Props {
  form: UseFormReturn<AssistantFormValues>;
}

export function ReflectionPolicyCard({ form }: Props) {
  const { register: registerAssistant, watch: watchAssistant, setValue: setAssistantValue } = form;

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold">Policy</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Control reflection behaviour and memory growth limits.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_policy.reflection_backend">Reflection backend</FieldLabel>
          <Input
            id="assistant_policy.reflection_backend"
            type="text"
            {...registerAssistant("assistant_policy.reflection_backend")}
          />
        </div>
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_policy.reflection_cooldown_seconds">
            Reflection cooldown
          </FieldLabel>
          <Input
            id="assistant_policy.reflection_cooldown_seconds"
            type="number"
            min={0}
            {...registerAssistant("assistant_policy.reflection_cooldown_seconds", {
              valueAsNumber: true,
            })}
          />
        </div>
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_policy.max_memory_entries">Max memory entries</FieldLabel>
          <Input
            id="assistant_policy.max_memory_entries"
            type="number"
            min={1}
            {...registerAssistant("assistant_policy.max_memory_entries", {
              valueAsNumber: true,
            })}
          />
        </div>
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_policy.max_playbooks">Max playbooks</FieldLabel>
          <Input
            id="assistant_policy.max_playbooks"
            type="number"
            min={1}
            {...registerAssistant("assistant_policy.max_playbooks", {
              valueAsNumber: true,
            })}
          />
        </div>
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_policy.max_brain_links">Max brain links</FieldLabel>
          <Input
            id="assistant_policy.max_brain_links"
            type="number"
            min={1}
            {...registerAssistant("assistant_policy.max_brain_links", {
              valueAsNumber: true,
            })}
          />
        </div>
      </div>

      <div className="space-y-2">
        <ToggleRow
          id="assistant_policy.reflection_enabled"
          label="Reflection enabled"
          description="Allow the assistant to summarise and reflect on completed work."
          checked={watchAssistant("assistant_policy.reflection_enabled")}
          onChange={(v) => setAssistantValue("assistant_policy.reflection_enabled", v)}
        />
        <ToggleRow
          id="assistant_policy.autonomous_research_enabled"
          label="Autonomous Research"
          description="Allow METIS to research sparse areas of your constellation and add new stars independently."
          checked={watchAssistant("assistant_policy.autonomous_research_enabled") ?? false}
          onChange={(v) => setAssistantValue("assistant_policy.autonomous_research_enabled", v)}
        />
        <ToggleRow
          id="assistant_policy.trigger_on_onboarding"
          label="Trigger on onboarding"
          description="Run the assistant after onboarding-related events."
          checked={watchAssistant("assistant_policy.trigger_on_onboarding")}
          onChange={(v) => setAssistantValue("assistant_policy.trigger_on_onboarding", v)}
        />
        <ToggleRow
          id="assistant_policy.trigger_on_index_build"
          label="Trigger on index build"
          description="Reflect after new indexes finish building."
          checked={watchAssistant("assistant_policy.trigger_on_index_build")}
          onChange={(v) => setAssistantValue("assistant_policy.trigger_on_index_build", v)}
        />
        <ToggleRow
          id="assistant_policy.trigger_on_completed_run"
          label="Trigger on completed run"
          description="Reflect after finished chat or tool runs."
          checked={watchAssistant("assistant_policy.trigger_on_completed_run")}
          onChange={(v) => setAssistantValue("assistant_policy.trigger_on_completed_run", v)}
        />
        <ToggleRow
          id="assistant_policy.allow_automatic_writes"
          label="Allow automatic writes"
          description="Let the assistant store reflections and memory entries automatically."
          checked={watchAssistant("assistant_policy.allow_automatic_writes")}
          onChange={(v) => setAssistantValue("assistant_policy.allow_automatic_writes", v)}
        />
      </div>
    </div>
  );
}
