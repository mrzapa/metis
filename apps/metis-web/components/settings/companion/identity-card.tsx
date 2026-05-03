"use client";

import type { UseFormReturn } from "react-hook-form";
import type { AssistantFormValues } from "@/app/settings/page";
import { FieldLabel, ToggleRow } from "@/app/settings/page";
import { Input } from "@/components/ui/input";
import { BorderBeam } from "@/components/ui/border-beam";

interface Props {
  form: UseFormReturn<AssistantFormValues>;
}

export function IdentityCard({ form }: Props) {
  const { register: registerAssistant, watch: watchAssistant, setValue: setAssistantValue } = form;

  return (
    <BorderBeam size="md" colorVariant="mono" strength={0.55}>
    <div className="space-y-4 rounded-2xl border border-white/8 bg-black/10 p-4">
      <div>
        <h3 className="text-sm font-semibold">Assistant identity</h3>
        <p className="mt-0.5 text-xs text-muted-foreground">
          Name, greeting, and dock behaviour for the companion.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_identity.assistant_id">Assistant ID</FieldLabel>
          <Input
            id="assistant_identity.assistant_id"
            type="text"
            {...registerAssistant("assistant_identity.assistant_id")}
          />
        </div>
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_identity.name">Name</FieldLabel>
          <Input
            id="assistant_identity.name"
            type="text"
            {...registerAssistant("assistant_identity.name")}
          />
        </div>
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_identity.archetype">Archetype</FieldLabel>
          <Input
            id="assistant_identity.archetype"
            type="text"
            {...registerAssistant("assistant_identity.archetype")}
          />
        </div>
        <div className="space-y-1.5">
          <FieldLabel htmlFor="assistant_identity.greeting">Greeting</FieldLabel>
          <Input
            id="assistant_identity.greeting"
            type="text"
            {...registerAssistant("assistant_identity.greeting")}
          />
        </div>
      </div>

      <div className="space-y-2">
        <ToggleRow
          id="assistant_identity.companion_enabled"
          label="Companion enabled"
          description="Show the assistant companion in the dock."
          checked={watchAssistant("assistant_identity.companion_enabled")}
          onChange={(v) => setAssistantValue("assistant_identity.companion_enabled", v)}
        />
        <ToggleRow
          id="assistant_identity.docked"
          label="Docked"
          description="Keep the companion visible as a docked panel."
          checked={watchAssistant("assistant_identity.docked")}
          onChange={(v) => setAssistantValue("assistant_identity.docked", v)}
        />
        <ToggleRow
          id="assistant_identity.minimized"
          label="Start minimized"
          description="Collapse the companion by default."
          checked={watchAssistant("assistant_identity.minimized")}
          onChange={(v) => setAssistantValue("assistant_identity.minimized", v)}
        />
      </div>
    </div>
    </BorderBeam>
  );
}
