"use client";

import { useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import { CircleDashed, CircleDot, Loader2, Lock, TriangleAlert } from "lucide-react";
import { AnimatedLucideIcon } from "@/components/ui/animated-lucide-icon";
import { BorderBeam } from "@/components/ui/border-beam";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import type { ForgeTechnique } from "@/lib/api";
import {
  PILLAR_GLYPH_TONE,
  PILLAR_ICON,
  PILLAR_LABEL,
  PILLAR_TONE,
} from "@/components/forge/pillar";

interface TechniqueCardProps {
  technique: ForgeTechnique;
  // Phase 3 — when supplied AND ``technique.toggleable``, the card
  // renders an interactive switch. The handler is expected to:
  //   1. Optimistically update the ``technique`` prop's source of
  //      truth so the next render picks up the new ``enabled`` state.
  //   2. Call the underlying API to write the settings.
  //   3. Surface the toggle through the companion dock.
  // It must return a Promise so the card can show a pending spinner
  // and ``throw`` to signal failure (the card reverts the optimistic
  // visual state and surfaces an error badge).
  onToggle?: (technique: ForgeTechnique, enabled: boolean) => Promise<void>;
}

// One technique = one card. Phase 3 wires interactive toggles for
// the descriptors that ship ``enable_overrides`` /
// ``disable_overrides`` payloads; non-toggleable techniques (Heretic
// CLI, TimesFM model download — see Phase 3b) keep the read-only
// posture they had through Phase 2a.
//
// The card's DOM `id` matches the technique slug so deep-links from
// `/forge#<technique-id>` (Phase 1's `useHashScroll`, Phase 2b's
// constellation Skills-sector stars) land directly on the right card.
export function TechniqueCard({ technique, onToggle }: TechniqueCardProps) {
  const reducedMotion = useReducedMotion();
  const Icon = PILLAR_ICON[technique.pillar];
  const isActive = technique.enabled;
  const [pending, setPending] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleToggle = async () => {
    if (!onToggle || !technique.toggleable || pending) return;
    const next = !isActive;
    setErrorMessage(null);
    setPending(true);
    try {
      await onToggle(technique, next);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Toggle failed";
      setErrorMessage(message);
    } finally {
      setPending(false);
    }
  };

  const switchControl = onToggle && technique.toggleable
    ? (
      <ToggleSwitch
        active={isActive}
        pending={pending}
        techniqueName={technique.name}
        onChange={handleToggle}
      />
    )
    : (
      <ReadOnlyBadge />
    );

  const body = (
    <motion.article
      id={technique.id}
      data-active={isActive ? "true" : "false"}
      className={cn(
        "group relative flex h-full flex-col gap-4 rounded-2xl border bg-white/3 p-5 transition-colors",
        isActive
          ? "border-white/14 bg-white/[0.045]"
          : "border-white/8 hover:border-white/12",
      )}
      whileHover={reducedMotion ? undefined : { y: -1 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
    >
      <header className="flex items-start gap-3">
        <div
          className={cn(
            "flex size-10 shrink-0 items-center justify-center rounded-xl border",
            PILLAR_GLYPH_TONE[technique.pillar],
          )}
          aria-hidden="true"
        >
          <AnimatedLucideIcon
            icon={Icon}
            mode={isActive ? "idlePulse" : "hoverLift"}
            className="size-5"
          />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="font-display text-base font-semibold leading-tight text-foreground">
            {technique.name}
          </h3>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            <span
              className={cn(
                "rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em]",
                PILLAR_TONE[technique.pillar],
              )}
            >
              {PILLAR_LABEL[technique.pillar]}
            </span>
            <StatusBadge active={isActive} />
          </div>
        </div>
        <div className="flex shrink-0 items-start">{switchControl}</div>
      </header>

      <p className="text-sm leading-relaxed text-muted-foreground">
        {technique.description}
      </p>

      <div className="flex flex-wrap items-center gap-2">
        {technique.setting_keys.length > 0 ? (
          <Tooltip>
            <TooltipTrigger
              render={
                <button
                  type="button"
                  aria-label={`Settings keys for ${technique.name}`}
                  className="rounded-md border border-white/8 bg-white/4 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground/70 transition-colors hover:border-white/16 hover:text-foreground/90"
                />
              }
            >
              {technique.setting_keys.length === 1
                ? "1 setting key"
                : `${technique.setting_keys.length} setting keys`}
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-sm">
              <div className="flex flex-col gap-1">
                <span className="text-[10px] uppercase tracking-[0.12em] opacity-70">
                  Wired to
                </span>
                <code className="font-mono text-[11px] leading-snug">
                  {technique.setting_keys.join(", ")}
                </code>
              </div>
            </TooltipContent>
          </Tooltip>
        ) : null}
        {errorMessage ? (
          <span
            role="alert"
            className="inline-flex items-center gap-1 rounded-md border border-destructive/30 bg-destructive/10 px-2 py-1 text-[10px] text-destructive"
          >
            <TriangleAlert className="size-3" aria-hidden="true" />
            {errorMessage}
          </span>
        ) : null}
      </div>
    </motion.article>
  );

  if (isActive) {
    return (
      <BorderBeam size="md" colorVariant="mono" strength={0.55}>
        {body}
      </BorderBeam>
    );
  }
  return body;
}

interface ToggleSwitchProps {
  active: boolean;
  pending: boolean;
  techniqueName: string;
  onChange: () => void;
}

function ToggleSwitch({ active, pending, techniqueName, onChange }: ToggleSwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={active}
      aria-label={`${active ? "Deactivate" : "Activate"} ${techniqueName}`}
      data-state={active ? "on" : "off"}
      data-pending={pending ? "true" : "false"}
      onClick={onChange}
      disabled={pending}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border transition-colors outline-none focus-visible:ring-2 focus-visible:ring-white/55 disabled:cursor-progress",
        active
          ? "border-emerald-400/40 bg-emerald-400/30"
          : "border-white/15 bg-white/8 hover:bg-white/12",
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          "pointer-events-none inline-flex size-4 items-center justify-center rounded-full bg-white shadow-md transition-transform",
          active ? "translate-x-6" : "translate-x-1",
        )}
      >
        {pending ? (
          <Loader2 className="size-3 animate-spin text-foreground/70" />
        ) : null}
      </span>
    </button>
  );
}

function ReadOnlyBadge() {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span
            aria-label="Read-only — needs runtime check"
            className="inline-flex size-7 items-center justify-center rounded-full border border-white/10 bg-white/4 text-muted-foreground/60"
          />
        }
      >
        <Lock className="size-3.5" aria-hidden="true" />
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-xs">
        <div className="flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-[0.12em] opacity-70">
            Read-only
          </span>
          <span className="text-[11px] leading-snug">
            Activation needs a runtime pre-flight check (CLI, model
            download, etc). Coming in a follow-up phase.
          </span>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

function StatusBadge({ active }: { active: boolean }) {
  if (active) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-emerald-200">
        <CircleDot className="size-2.5" aria-hidden="true" />
        Active
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-white/10 bg-white/4 px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
      <CircleDashed className="size-2.5" aria-hidden="true" />
      Standby
    </span>
  );
}
