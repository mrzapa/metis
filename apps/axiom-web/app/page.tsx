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
        size={compact ? 36 : 40}
        className={cn(
          "shrink-0 transition-opacity duration-300",
          active ? "opacity-100" : "opacity-85 group-hover/rail:opacity-100",
        )}
      />
    );
  }

  const Icon = item.icon ?? Settings2;

  return (
    <span
      className={cn(
        "flex items-center justify-center rounded-full transition-all duration-300",
        compact ? "size-9" : "size-10 shrink-0",
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
          : "flex items-center gap-4 rounded-full px-3 py-2.5 transition-colors",
        active
          ? "text-[#dfe2eb]"
          : "text-[#8c909f] hover:text-[#dfe2eb]",
        compact && "hover:bg-white/5",
      )}
    >
      <RailVisual item={item} active={active} compact={compact} />
      <span
        className={cn(
          compact
            ? "max-w-[5.25rem] truncate font-display text-[10px] uppercase tracking-[0.18em]"
            : "min-w-0 overflow-hidden whitespace-nowrap font-display text-xs uppercase tracking-[0.28em] opacity-0 transition-all duration-300 group-hover/rail:translate-x-0 group-hover/rail:opacity-100",
          !compact && "translate-x-1",
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

      <aside className="fixed left-8 top-[34%] z-30 hidden -translate-y-1/2 md:block">
        <nav className="home-liquid-glass home-liquid-glass-rail group/rail flex w-16 flex-col gap-3 overflow-hidden rounded-full px-2 py-6 transition-[width] duration-500 hover:w-56">
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

      <main className="relative z-10 flex min-h-screen items-center justify-center px-6 pb-32 pt-10 sm:px-10 md:px-20 md:pb-12">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center">
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease: "easeOut" }}
            className="mb-16 flex flex-col items-center text-center md:mb-24"
          >
            <h1 className="sr-only">AXIOM</h1>
            <AxiomHomeLogo
              className="size-36 sm:size-44 md:size-52"
              priority
            />
          </motion.div>

          {setupComplete === false ? (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, ease: "easeOut", delay: 0.08 }}
              className="glass-panel mb-8 flex w-full max-w-2xl items-center gap-3 rounded-full px-4 py-3 text-sm text-[#c2c6d6] md:mb-10"
            >
              <Sparkles className="size-4 shrink-0 text-[#adc6ff]" />
              <span>Setup is incomplete. The launch cards will send you to onboarding.</span>
            </motion.div>
          ) : null}

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease: "easeOut", delay: 0.08 }}
            className="grid w-full gap-5 md:grid-cols-3 md:gap-8"
          >
            {ACTION_ITEMS.map((item, index) => {
              const href = resolveHref(item.href, setupComplete);

              return (
                <motion.div
                  key={item.href}
                  initial={{ opacity: 0, y: 24 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.45, ease: "easeOut", delay: 0.12 + index * 0.08 }}
                >
                  <Link
                    href={href}
                    className="home-liquid-glass home-liquid-glass-card group flex min-h-[15.5rem] flex-col items-center justify-center rounded-[2rem] px-7 py-10 text-center md:min-h-[17rem] md:px-10"
                  >
                    <HomeLaunchIcon
                      kind={item.kind ?? "chat"}
                      animated
                      size={80}
                      className="mb-6"
                    />
                    <h2 className="font-display text-[1.9rem] font-semibold tracking-[-0.04em] text-[#f2f5ff]">
                      {item.label}
                    </h2>
                    <p className="mt-3 max-w-xs text-sm leading-7 text-[#8c909f]">
                      {item.description}
                    </p>
                  </Link>
                </motion.div>
              );
            })}
          </motion.div>
        </div>
      </main>

      <div className="pointer-events-none fixed bottom-24 left-1/2 z-20 w-40 -translate-x-1/2 md:bottom-10">
        <div className="thinking-indicator h-px rounded-full">
          <div className="thinking-indicator__bar h-full w-1/4 rounded-full bg-[#adc6ff]" />
        </div>
      </div>
    </div>
  );
}
