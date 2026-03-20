"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  Settings2,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import {
  AxiomHomeLogo,
  HomeLaunchIcon,
  type HomeLaunchKind,
} from "@/components/home/home-visual-system";
import { AxiomCompanionDock } from "@/components/shell/axiom-companion-dock";
import { SpaceAtmosphere } from "@/components/home/space-atmosphere";
import { fetchSettings } from "@/lib/api";
import { cn } from "@/lib/utils";

type LaunchItem = {
  href: string;
  label: string;
  railLabel: string;
  description: string;
  kind?: HomeLaunchKind;
  icon?: LucideIcon;
  emphasized?: boolean;
};

const ACTION_ITEMS: LaunchItem[] = [
  {
    href: "/chat",
    label: "Chat",
    railLabel: "Chat",
    description: "Direct neural synthesis link.",
    kind: "chat",
    emphasized: true,
  },
  {
    href: "/library",
    label: "Build a Neuron",
    railLabel: "Build",
    description: "Architect custom pipelines.",
    kind: "neuron",
  },
  {
    href: "/brain",
    label: "Explore Brain",
    railLabel: "Explore",
    description: "Visual topological mapping.",
    kind: "brain",
  },
];

const SIDE_RAIL_ITEMS: LaunchItem[] = [
  ...ACTION_ITEMS,
  {
    href: "/settings",
    label: "Settings",
    railLabel: "Settings",
    description: "Adjust providers and workspace options.",
    icon: Settings2,
  },
];

function resolveHref(href: string, setupComplete: boolean | null) {
  return setupComplete === false ? "/setup" : href;
}

function RailVisual({
  item,
  active,
  compact = false,
}: {
  item: LaunchItem;
  active: boolean;
  compact?: boolean;
}) {
  if (item.kind) {
    return (
      <HomeLaunchIcon
        kind={item.kind}
        size={compact ? 36 : 42}
        className={cn(
          "shrink-0 transition-[transform,opacity] duration-300",
          active
            ? "scale-100 opacity-100"
            : "scale-[0.98] opacity-85 group-hover/rail:scale-100 group-hover/rail:opacity-100",
        )}
      />
    );
  }

  const Icon = item.icon ?? Settings2;

  return (
    <span
      className={cn(
        "flex items-center justify-center rounded-full transition-all duration-300",
        compact ? "size-9" : "size-11 shrink-0",
        active
          ? "bg-[#adc6ff]/10 text-[#adc6ff]"
          : "bg-white/4 text-[#8c909f] group-hover/rail:bg-white/7 group-hover/rail:text-[#dfe2eb]",
      )}
    >
      <Icon className="size-4" />
    </span>
  );
}

function RailLink({
  item,
  setupComplete,
  compact = false,
}: {
  item: LaunchItem;
  setupComplete: boolean | null;
  compact?: boolean;
}) {
  const href = resolveHref(item.href, setupComplete);
  const active = Boolean(item.emphasized);

  return (
    <Link
      href={href}
      aria-label={item.label}
      className={cn(
        compact
          ? "flex flex-1 flex-col items-center justify-center gap-1.5 rounded-2xl px-2 py-2 text-center transition-colors"
          : "grid w-full grid-cols-[2.85rem_minmax(0,1fr)] items-center gap-2 rounded-[1.35rem] px-2.5 py-2.5 text-left transition-colors",
        active
          ? "text-[#dfe2eb]"
          : "text-[#8c909f] hover:text-[#dfe2eb]",
        compact && "hover:bg-white/5",
      )}
    >
      {compact ? (
        <RailVisual item={item} active={active} compact />
      ) : (
        <span className="flex items-center justify-center">
          <RailVisual item={item} active={active} />
        </span>
      )}
      <span
        className={cn(
          compact
            ? "max-w-[5.25rem] truncate font-display text-[10px] uppercase tracking-[0.18em]"
            : "min-w-0 overflow-hidden whitespace-nowrap font-display text-[11px] uppercase tracking-[0.28em] opacity-0 transition-all duration-300 group-hover/rail:translate-x-0 group-hover/rail:opacity-100",
          !compact && "translate-x-2",
        )}
      >
        {item.railLabel}
      </span>
    </Link>
  );
}

export default function Home() {
  const [setupComplete, setSetupComplete] = useState<boolean | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchSettings()
      .then((settings) => {
        if (!cancelled) {
          setSetupComplete(Boolean(settings.basic_wizard_completed));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSetupComplete(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="starfield-bg relative min-h-screen overflow-hidden bg-[#05070a] text-[#dfe2eb]">
      <div className="celestial-glow absolute inset-0" aria-hidden="true" />
      <div className="deep-space-overlay absolute inset-0" aria-hidden="true" />
      <SpaceAtmosphere />

      <aside className="fixed left-6 top-1/2 z-30 hidden -translate-y-1/2 md:block">
        <nav className="home-liquid-glass home-liquid-glass-rail group/rail flex w-20 flex-col gap-2.5 overflow-hidden rounded-[1.9rem] px-2.5 py-2.5 transition-[width] duration-500 hover:w-60">
          {SIDE_RAIL_ITEMS.map((item) => (
            <RailLink key={item.href} item={item} setupComplete={setupComplete} />
          ))}
        </nav>
      </aside>

      <nav className="home-liquid-glass home-liquid-glass-rail fixed bottom-4 left-1/2 z-30 w-[min(92vw,28rem)] -translate-x-1/2 rounded-[1.75rem] px-2 py-2 md:hidden">
        <div className="flex w-full flex-col gap-3">
          <div className="grid grid-cols-4 gap-1">
            {SIDE_RAIL_ITEMS.map((item) => (
              <RailLink
                key={item.href}
                item={item}
                setupComplete={setupComplete}
                compact
              />
            ))}
          </div>
        </div>
      </nav>

      <main className="relative z-10 flex min-h-screen items-center justify-center px-5 pb-32 pt-8 sm:px-8 md:px-12 lg:px-16">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-10 lg:gap-12">
          <motion.section
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease: "easeOut" }}
            className="grid gap-8 lg:grid-cols-[minmax(0,1.05fr)_minmax(320px,0.72fr)] lg:items-center"
          >
            <div className="space-y-8">
              <div className="space-y-6 text-left">
                <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-[0.72rem] uppercase tracking-[0.32em] text-[#92a4d4]">
                  <span className="size-1.5 rounded-full bg-[#59d9ff] shadow-[0_0_14px_rgba(89,217,255,0.9)]" />
                  Local-first workspace
                </div>

                <div className="flex flex-col gap-6 xl:flex-row xl:items-center xl:gap-8">
                  <h1 className="sr-only">AXIOM</h1>
                  <AxiomHomeLogo
                    className="size-40 sm:size-48 md:size-56 lg:size-60"
                    priority
                  />
                  <div className="hidden h-px flex-1 bg-gradient-to-r from-[#8fb3ff]/40 via-white/15 to-transparent xl:block" />
                </div>

                <div className="max-w-2xl space-y-4">
                  <h2 className="font-display text-balance text-4xl font-semibold tracking-[-0.05em] text-[#f4f7ff] sm:text-5xl lg:text-6xl">
                    Build, chat, and map your knowledge in one orbital cockpit.
                  </h2>
                  <p className="max-w-xl text-pretty text-base leading-8 text-[#98a2bf] sm:text-lg">
                    Axiom keeps sessions, indexes, the brain graph, and local GGUF models in one
                    private, desktop-native workspace so the empty space becomes usable surface.
                  </p>
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                {[
                  "Private by default",
                  "Desktop-first layout",
                  "Model and graph aware",
                ].map((label) => (
                  <div
                    key={label}
                    className="glass-panel rounded-full px-4 py-3 text-center text-xs uppercase tracking-[0.24em] text-[#b9c3dd]"
                  >
                    {label}
                  </div>
                ))}
              </div>
            </div>

            <motion.aside
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, ease: "easeOut", delay: 0.1 }}
              className="home-liquid-glass rounded-[2rem] p-5 sm:p-6"
            >
              <div className="space-y-5">
                <div className="space-y-2">
                  <p className="font-display text-xs uppercase tracking-[0.34em] text-[#6dd6ff]">
                    Launch posture
                  </p>
                  <h3 className="font-display text-2xl font-semibold tracking-[-0.04em] text-[#f4f7ff]">
                    One workspace, three modes.
                  </h3>
                  <p className="text-sm leading-7 text-[#97a2bd]">
                    Keep chat for direct synthesis, library for your indexes and GGUF models, and
                    brain for the graph of everything the workspace knows.
                  </p>
                </div>

                <div className="space-y-2 rounded-[1.35rem] border border-white/8 bg-[rgba(0,0,0,0.14)] p-4">
                  <div className="flex items-center justify-between gap-3 text-xs uppercase tracking-[0.26em] text-[#8f9bb7]">
                    <span>Local inference</span>
                    <span>Offline-ready</span>
                  </div>
                  <div className="mt-4 grid gap-2 text-sm text-[#dce3f6]">
                    <div className="flex items-center justify-between gap-4 rounded-full bg-white/5 px-3 py-2">
                      <span>Chat</span>
                      <span className="text-[#8fb3ff]">Grounded answers</span>
                    </div>
                    <div className="flex items-center justify-between gap-4 rounded-full bg-white/5 px-3 py-2">
                      <span>Brain</span>
                      <span className="text-[#8fb3ff]">Persistent topology</span>
                    </div>
                    <div className="flex items-center justify-between gap-4 rounded-full bg-white/5 px-3 py-2">
                      <span>Models</span>
                      <span className="text-[#8fb3ff]">Hardware aware</span>
                    </div>
                  </div>
                </div>

                {setupComplete === false ? (
                  <div className="flex items-center gap-3 rounded-[1.35rem] border border-[rgba(143,179,255,0.18)] bg-[rgba(143,179,255,0.08)] px-4 py-3 text-sm text-[#c5d1ef]">
                    <Sparkles className="size-4 shrink-0 text-[#8fb3ff]" />
                    <span>I’m keeping the launch paths pointed at onboarding until setup is complete.</span>
                  </div>
                ) : setupComplete === null ? (
                  <div className="flex items-center gap-3 rounded-[1.35rem] border border-[rgba(143,179,255,0.18)] bg-[rgba(143,179,255,0.08)] px-4 py-3 text-sm text-[#c5d1ef]">
                    <Sparkles className="size-4 shrink-0 text-[#8fb3ff]" />
                    <span>I’m checking your workspace setup before I hand you the right launch path.</span>
                  </div>
                ) : null}
              </div>
            </motion.aside>
          </motion.section>

          <motion.section
            initial={{ opacity: 0, y: 22 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease: "easeOut", delay: 0.08 }}
            className="grid gap-5 md:grid-cols-3 md:gap-6"
          >
            {ACTION_ITEMS.map((item, index) => {
              const href = resolveHref(item.href, setupComplete);

              return (
                <motion.div
                  key={item.href}
                  initial={{ opacity: 0, y: 22 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.45, ease: "easeOut", delay: 0.12 + index * 0.08 }}
                  whileHover={{ y: -6 }}
                  whileTap={{ scale: 0.99 }}
                >
                  <Link
                    href={href}
                    className="home-liquid-glass home-liquid-glass-card group flex min-h-[18rem] flex-col justify-between rounded-[2rem] p-6 text-left md:min-h-[19rem] md:p-7"
                  >
                    <div className="flex items-center justify-between gap-4">
                      <div className="rounded-full border border-white/8 bg-white/5 px-3 py-1 text-[10px] uppercase tracking-[0.28em] text-[#9aa4bf]">
                        0{index + 1}
                      </div>
                      <div className="h-px flex-1 bg-gradient-to-r from-white/10 via-white/5 to-transparent" />
                      <span className="text-[10px] uppercase tracking-[0.24em] text-[#6dd6ff]">
                        Launch
                      </span>
                    </div>

                    <div className="flex flex-1 flex-col items-center justify-center gap-5 text-center">
                      <div className="relative">
                        <HomeLaunchIcon
                          kind={item.kind ?? "chat"}
                          animated
                          size={92}
                          className="shadow-[0_0_0_1px_rgba(255,255,255,0.04)]"
                        />
                        <span className="pointer-events-none absolute inset-[-10%] rounded-full border border-[rgba(143,179,255,0.1)] opacity-70 blur-[1px]" />
                      </div>
                      <div className="space-y-3">
                        <h2 className="font-display text-[1.8rem] font-semibold tracking-[-0.04em] text-[#f4f7ff]">
                          {item.label}
                        </h2>
                        <p className="max-w-xs text-sm leading-7 text-[#8f98b1]">
                          {item.description}
                        </p>
                      </div>
                    </div>

                    <div className="flex items-center justify-between text-[11px] uppercase tracking-[0.24em] text-[#9aa4bf]">
                      <span>{item.railLabel}</span>
                      <span className="transition-transform duration-300 group-hover:translate-x-1">
                        Open
                      </span>
                    </div>
                  </Link>
                </motion.div>
              );
            })}
          </motion.section>
        </div>
      </main>

      <AxiomCompanionDock className="bottom-24 md:bottom-4" />

      <div className="pointer-events-none fixed bottom-24 left-1/2 z-20 w-40 -translate-x-1/2 md:bottom-10">
        <div className="thinking-indicator h-px rounded-full">
          <div className="thinking-indicator__bar h-full w-1/4 rounded-full bg-[#adc6ff]" />
        </div>
      </div>
    </div>
  );
}
