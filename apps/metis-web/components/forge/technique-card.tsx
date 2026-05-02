"use client";

import { useCallback, useState } from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import {
  ChevronDown,
  CircleDashed,
  CircleDot,
  ExternalLink,
  Loader2,
  Lock,
  ShieldAlert,
  Sparkles,
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
import type { ForgeRecentUseEvent, ForgeTechnique } from "@/lib/api";
import { fetchForgeRecentUses } from "@/lib/api";
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
        {technique.weekly_use_count > 0 ? (
          <WeeklyUsePill count={technique.weekly_use_count} />
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

      {technique.weekly_use_count > 0 ? (
        <RecentUsesPanel techniqueId={technique.id} />
      ) : null}
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
              {" "}and the engine&apos;s preflight messaging):
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

interface WeeklyUsePillProps {
  count: number;
}

function WeeklyUsePill({ count }: WeeklyUsePillProps) {
  // Phase 6 — card-face counter. The exact wording matters: "uses this
  // week" reads as evidence the technique is earning its slot, which
  // is the point of VISION's "intelligence grown, not bought" framing.
  // Singularised at exactly one to avoid the "1 uses" awkwardness.
  const noun = count === 1 ? "use" : "uses";
  return (
    <span
      data-testid="forge-weekly-use-pill"
      className="inline-flex items-center gap-1 rounded-md border border-emerald-400/25 bg-emerald-400/10 px-2 py-1 text-[10px] font-medium uppercase tracking-[0.1em] text-emerald-100/85"
    >
      <Sparkles className="size-3" aria-hidden="true" />
      {count} {noun} this week
    </span>
  );
}

interface RecentUsesPanelProps {
  techniqueId: string;
}

type FetchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; events: ForgeRecentUseEvent[] }
  | { status: "error"; message: string };

function RecentUsesPanel({ techniqueId }: RecentUsesPanelProps) {
  // The detail call is lazy: the gallery renders 13 cards in one
  // shot, and most users won't expand every one. We only hit
  // ``/recent-uses`` when the user explicitly opens the panel, and
  // we cache per-card (no refetch on collapse + re-open) so the
  // mini-timeline stays snappy.
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<FetchState>({ status: "idle" });

  const ensureLoaded = useCallback(async () => {
    // Skip refetching when we already have data or a request is in
    // flight; ``error`` state IS allowed through so the user can
    // recover from a transient blip by collapsing + re-opening (Codex
    // P2 on PR #585 — without this, the inline error was permanent
    // for the rest of the card's lifetime and the only escape was a
    // full page refresh).
    if (state.status === "loading" || state.status === "loaded") return;
    setState({ status: "loading" });
    try {
      const data = await fetchForgeRecentUses(techniqueId);
      setState({ status: "loaded", events: data.events });
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Could not load recent uses";
      setState({ status: "error", message });
    }
  }, [state, techniqueId]);

  const onTriggerClick = useCallback(() => {
    if (!open) {
      void ensureLoaded();
    }
    setOpen((prev) => !prev);
  }, [ensureLoaded, open]);

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        data-testid="forge-recent-uses-trigger"
        onClick={onTriggerClick}
        aria-expanded={open}
        aria-controls={`recent-uses-${techniqueId}`}
        className="inline-flex w-full items-center justify-between gap-2 rounded-md border border-white/8 bg-white/3 px-2.5 py-1.5 text-[11px] font-medium text-muted-foreground transition-colors hover:border-white/14 hover:text-foreground/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/40"
      >
        <span>Recent uses</span>
        <ChevronDown
          className={cn(
            "size-3.5 transition-transform",
            open ? "rotate-180" : undefined,
          )}
          aria-hidden="true"
        />
      </button>
      {open ? (
        <div
          id={`recent-uses-${techniqueId}`}
          className="flex flex-col gap-1.5 rounded-lg border border-white/6 bg-black/15 p-2"
        >
          {state.status === "loading" ? (
            <div
              data-testid="forge-recent-uses-loading"
              className="flex items-center gap-2 text-[11px] text-muted-foreground/80"
            >
              <Loader2 className="size-3 animate-spin" aria-hidden="true" />
              Loading…
            </div>
          ) : null}
          {state.status === "error" ? (
            <p
              role="alert"
              data-testid="forge-recent-uses-error"
              className="text-[11px] leading-snug text-destructive"
            >
              {state.message}
            </p>
          ) : null}
          {state.status === "loaded" && state.events.length === 0 ? (
            <p
              data-testid="forge-recent-uses-empty"
              className="text-[11px] text-muted-foreground/70"
            >
              No recent uses yet — your companion hasn&apos;t fired this technique
              in the last week.
            </p>
          ) : null}
          {state.status === "loaded" && state.events.length > 0 ? (
            <ul className="flex flex-col gap-1.5">
              {state.events.map((event, index) => (
                <li
                  key={`${event.run_id}-${index}`}
                  data-testid="forge-recent-uses-row"
                  className="flex flex-col gap-0.5 rounded-md border border-white/6 bg-white/3 px-2 py-1.5 text-[11px] leading-snug"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-muted-foreground/70">
                      {event.event_type}
                    </span>
                    <span className="text-[10px] text-muted-foreground/60">
                      {formatTimestamp(event.timestamp)}
                    </span>
                  </div>
                  {event.preview ? (
                    <p className="text-foreground/85">{event.preview}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function formatTimestamp(value: string): string {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
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
