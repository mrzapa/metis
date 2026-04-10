"use client";

import { HudPanel } from "../HudPanel";
import type { AssistantSnapshot } from "@/lib/api";

const RAG_SKILLS: { name: string; description: string }[] = [
  { name: "Q&A", description: "Retrieval-augmented question answering" },
  { name: "Summary", description: "Condensed document summarisation" },
  { name: "Tutor", description: "Step-by-step explanatory guidance" },
  { name: "Research", description: "Multi-hop deep research synthesis" },
  { name: "Evidence Pack", description: "Source-attributed evidence compilation" },
  { name: "Knowledge Search", description: "Semantic search across indexed knowledge" },
];

const COMPANION_CAPABILITIES: {
  name: string;
  description: string;
  policyKey: keyof NonNullable<AssistantSnapshot>["policy"] | null;
}[] = [
  { name: "Reflection", description: "Autonomous self-reflection and memory writing", policyKey: "reflection_enabled" },
  {
    name: "Autonomous Research",
    description: "Background research triggered by context",
    policyKey: "autonomous_research_enabled",
  },
  { name: "Quick-Ask", description: "In-dock conversational LLM via WebGPU", policyKey: null },
  { name: "Atlas Memory", description: "Save high-quality answers to long-term Atlas", policyKey: null },
];

interface SkillsPanelProps {
  snapshot: AssistantSnapshot | null;
}

export function SkillsPanel({ snapshot }: SkillsPanelProps) {
  const policy = snapshot?.policy;

  function isEnabled(key: (typeof COMPANION_CAPABILITIES)[number]["policyKey"]): boolean | null {
    if (!key || !policy) return null;
    return !!(policy[key]);
  }

  return (
    <div className="grid gap-3 lg:grid-cols-[2fr_1fr]">
      {/* RAG Modes */}
      <HudPanel title="What I'm Learning — RAG Skills">
        <div className="space-y-2">
          {RAG_SKILLS.map((skill) => (
            <div
              key={skill.name}
              className="flex items-start gap-3 rounded px-2 py-1.5 transition-colors"
              style={{ background: "color-mix(in oklch, white 8%, transparent)" }}
            >
              <span
                className="mt-0.5 size-1.5 shrink-0 rounded-full"
                style={{ background: "var(--hud-success)" }}
              />
              <div>
                <p className="text-[13px] font-semibold" style={{ color: "var(--hud-text)" }}>
                  {skill.name}
                </p>
                <p className="text-[11px]" style={{ color: "var(--hud-text-dim)" }}>
                  {skill.description}
                </p>
              </div>
            </div>
          ))}
        </div>
      </HudPanel>

      {/* Companion Capabilities */}
      <HudPanel title="Companion Tools">
        <div className="space-y-2">
          {COMPANION_CAPABILITIES.map((cap) => {
            const enabled = isEnabled(cap.policyKey);
            return (
              <div key={cap.name} className="space-y-0.5">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[12px] font-medium" style={{ color: "var(--hud-text)" }}>
                    {cap.name}
                  </p>
                  {enabled !== null && (
                    <span
                      className="rounded px-1.5 py-0.5 text-[10px] font-bold uppercase"
                      style={{
                        background: enabled ? "var(--hud-success)" : "color-mix(in oklch, white 8%, transparent)",
                        color: enabled ? "var(--primary-foreground)" : "var(--hud-text-dim)",
                      }}
                    >
                      {enabled ? "on" : "off"}
                    </span>
                  )}
                </div>
                <p className="text-[11px]" style={{ color: "var(--hud-text-dim)" }}>
                  {cap.description}
                </p>
              </div>
            );
          })}
        </div>

        {policy && (
          <div className="mt-4 space-y-1 border-t pt-3" style={{ borderColor: "var(--hud-border)" }}>
            <p className="text-[10px] uppercase tracking-[0.15em]" style={{ color: "var(--hud-text-dim)" }}>
              Policy limits
            </p>
            <PolicyRow label="Max memories" value={policy.max_memory_entries} />
            <PolicyRow label="Max playbooks" value={policy.max_playbooks} />
            <PolicyRow label="Max brain links" value={policy.max_brain_links} />
          </div>
        )}
      </HudPanel>
    </div>
  );
}

function PolicyRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between text-[11px]">
      <span style={{ color: "var(--hud-text-dim)" }}>{label}</span>
      <span className="tabular-nums" style={{ color: "var(--hud-primary)" }}>
        {value}
      </span>
    </div>
  );
}
