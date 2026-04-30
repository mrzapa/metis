"use client";

import { useState } from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import {
  CircleDashed,
  CircleDot,
  ExternalLink,
  Loader2,
  Lock,
  ShieldAlert,
  TriangleAlert,
} from "lucide-react";
import { AnimatedLucideIcon } from "@/components/ui/animated-lucide-icon";
import { BorderBeam } from "@/components/ui/border-beam";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
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
// ``disable_overrides`` payloads. Phase 3b adds a runtime-readiness
// branch: a toggleable technique whose runtime probe reports
// ``status="blocked"`` (Heretic with no CLI on PATH) renders the
// switch disabled with a "Get ready" CTA next to it; an
// informational-only blocked technique (TimesFM — activated by
// switching the chat mode) renders just the CTA, no switch.
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
  const [readyDialogOpen, setReadyDialogOpen] = useState(false);

  const handleToggle = async () => {
    if (
      !onToggle
      || !technique.toggleable
      || pending
      || technique.runtime_status === "blocked"
    ) {
      return;
    }
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

  const isBlocked = technique.runtime_status === "blocked";
  const showSwitch = Boolean(onToggle && technique.toggleable);
  const showLockBadge = !showSwitch && !isBlocked;

  const cardSwitch = showSwitch ? (
    <ToggleSwitch
      active={isActive}
      pending={pending}
      blocked={isBlocked}
      techniqueName={technique.name}
      onChange={handleToggle}
    />
  ) : showLockBadge ? (
    <ReadOnlyBadge />
  ) : null;

  const body = (
    <motion.article
      id={technique.id}
      data-active={isActive ? "true" : "false"}
      data-runtime-status={technique.runtime_status}
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
        {cardSwitch ? <div className="flex shrink-0 items-start">{cardSwitch}</div> : null}
      </header>

      <p className="text-sm leading-relaxed text-muted-foreground">
        {technique.description}
      </p>

      {isBlocked ? (
        <ReadinessRow
          technique={technique}
          onOpenInstallDialog={() => setReadyDialogOpen(true)}
        />
      ) : null}

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

  const wrapped = isActive ? (
    <BorderBeam size="md" colorVariant="mono" strength={0.55}>
      {body}
    </BorderBeam>
  ) : (
    body
  );

  return (
    <>
      {wrapped}
      <HereticInstallDialog
        open={readyDialogOpen}
        onOpenChange={setReadyDialogOpen}
      />
    </>
  );
}

interface ReadinessRowProps {
  technique: ForgeTechnique;
  onOpenInstallDialog: () => void;
}

function ReadinessRow({ technique, onOpenInstallDialog }: ReadinessRowProps) {
  const blockerSummary = technique.runtime_blockers[0] ?? "Not ready";
  return (
    <div
      data-testid="forge-readiness-row"
      className="flex flex-wrap items-start gap-2 rounded-xl border border-amber-300/20 bg-amber-300/5 px-3 py-2"
    >
      <ShieldAlert className="mt-0.5 size-4 shrink-0 text-amber-300/85" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-[11px] font-medium uppercase tracking-[0.12em] text-amber-200/85">
          Runtime check
        </p>
        <p className="mt-1 text-xs leading-relaxed text-amber-100/80">
          {blockerSummary}
        </p>
      </div>
      <ReadinessCta
        technique={technique}
        onOpenInstallDialog={onOpenInstallDialog}
      />
    </div>
  );
}

function ReadinessCta({ technique, onOpenInstallDialog }: ReadinessRowProps) {
  switch (technique.runtime_cta_kind) {
    case "install_heretic":
      return (
        <button
          type="button"
          data-testid="forge-readiness-cta"
          onClick={onOpenInstallDialog}
          className="shrink-0 rounded-md border border-amber-300/35 bg-amber-300/10 px-2.5 py-1 text-xs font-medium text-amber-100 transition-colors hover:border-amber-300/55 hover:bg-amber-300/16 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/55"
        >
          Get ready
        </button>
      );
    case "switch_chat_path":
      return (
        <Link
          href={technique.runtime_cta_target ?? "/chat"}
          data-testid="forge-readiness-cta"
          className="inline-flex shrink-0 items-center gap-1 rounded-md border border-amber-300/35 bg-amber-300/10 px-2.5 py-1 text-xs font-medium text-amber-100 transition-colors hover:border-amber-300/55 hover:bg-amber-300/16 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/55"
        >
          Open chat
          <ExternalLink className="size-3" aria-hidden="true" />
        </Link>
      );
    default:
      return null;
  }
}

interface HereticInstallDialogProps {
  open: boolean;
  onOpenChange: (next: boolean) => void;
}

function HereticInstallDialog({ open, onOpenChange }: HereticInstallDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Install Heretic CLI</DialogTitle>
          <DialogDescription>
            Heretic abliteration runs as an external CLI. Install it once on this
            machine, then reload the Forge — the toggle will become available.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-3 text-sm leading-relaxed text-muted-foreground">
          <ol className="list-decimal space-y-2 pl-5">
            <li>
              Install the package backend ships against (
              <code className="rounded bg-white/8 px-1.5 py-0.5 font-mono text-xs">heretic-llm</code>
              {" "}on PyPI; same string referenced by{" "}
              <code className="rounded bg-white/8 px-1.5 py-0.5 font-mono text-xs">pyproject.toml</code>
              {" "}and the engine's preflight messaging):
              <pre className="mt-2 rounded-lg border border-white/10 bg-black/30 px-3 py-2 font-mono text-xs">pip install heretic-llm</pre>
            </li>
            <li>
              Confirm the binary landed on your{" "}
              <code className="rounded bg-white/8 px-1.5 py-0.5 font-mono text-xs">$PATH</code>:
              <pre className="mt-2 rounded-lg border border-white/10 bg-black/30 px-3 py-2 font-mono text-xs">heretic --help</pre>
              METIS picks it up on the next gallery refresh (or whenever the home page comes back into focus).
            </li>
          </ol>
        </div>
      </DialogContent>
    </Dialog>
  );
}

interface ToggleSwitchProps {
  active: boolean;
  pending: boolean;
  blocked: boolean;
  techniqueName: string;
  onChange: () => void;
}

function ToggleSwitch({ active, pending, blocked, techniqueName, onChange }: ToggleSwitchProps) {
  const ariaLabel = blocked
    ? `${techniqueName} is blocked — runtime check required`
    : `${active ? "Deactivate" : "Activate"} ${techniqueName}`;
  return (
    <button
      type="button"
      role="switch"
      aria-checked={active}
      aria-label={ariaLabel}
      aria-disabled={blocked || pending}
      data-state={active ? "on" : "off"}
      data-pending={pending ? "true" : "false"}
      data-blocked={blocked ? "true" : "false"}
      onClick={onChange}
      disabled={pending || blocked}
      title={blocked ? "Resolve the runtime check below first" : undefined}
      className={cn(
        "relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors outline-none focus-visible:ring-2 focus-visible:ring-white/55",
        blocked
          ? "cursor-not-allowed border-white/12 bg-white/5 opacity-65"
          : "cursor-pointer disabled:cursor-progress",
        !blocked && active
          ? "border-emerald-400/40 bg-emerald-400/30"
          : !blocked && !active
            ? "border-white/15 bg-white/8 hover:bg-white/12"
            : "",
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
            download, etc).
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
