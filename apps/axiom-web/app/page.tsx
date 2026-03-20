"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  Settings2,
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
  animated = false,
}: {
  item: LaunchItem;
  active: boolean;
  compact?: boolean;
  animated?: boolean;
}) {
  if (item.kind) {
    return (
      <HomeLaunchIcon
        kind={item.kind}
        animated={animated}
        size={compact ? 36 : 40}
        className={cn(
          "shrink-0 transition-[transform,opacity,filter] duration-300",
          active
            ? "scale-100 opacity-100"
            : "scale-[0.985] opacity-90 group-hover/rail-link:scale-[1.03] group-hover/rail-link:opacity-100",
        )}
      />
    );
  }

  const Icon = item.icon ?? Settings2;

  return (
    <span
      className={cn(
        "flex items-center justify-center rounded-full ring-1 ring-transparent transition-all duration-300",
        compact ? "size-9" : "size-10 shrink-0",
        active
          ? "bg-[#adc6ff]/10 text-[#adc6ff]"
          : "bg-white/4 text-[#8c909f] group-hover/rail-link:bg-white/7 group-hover/rail-link:text-[#dfe2eb] group-hover/rail-link:ring-white/10",
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
          ? "group/rail-link flex flex-1 flex-col items-center justify-center gap-1.5 rounded-2xl px-2 py-2 text-center transition-colors"
          : "group/rail-link flex w-full items-center gap-3 rounded-[1.45rem] px-3 py-3 text-left transition-[background-color,color,transform] duration-300",
        active
          ? "text-[#dfe2eb]"
          : "text-[#8c909f] hover:bg-white/[0.045] hover:text-[#dfe2eb]",
        compact && "hover:bg-white/5",
      )}
    >
      {compact ? (
        <RailVisual item={item} active={active} compact animated={false} />
      ) : (
        <span className="flex shrink-0 items-center justify-center">
          <RailVisual item={item} active={active} animated />
        </span>
      )}
      <span
        className={cn(
          compact
            ? "max-w-[5.25rem] truncate font-display text-[10px] uppercase tracking-[0.18em]"
            : "min-w-0 max-w-0 overflow-hidden whitespace-nowrap font-display text-[10.5px] uppercase tracking-[0.28em] opacity-0 transition-[max-width,opacity,transform] duration-300 group-hover/rail:max-w-[8.75rem] group-hover/rail:translate-x-0 group-hover/rail:opacity-100 group-focus-within/rail:max-w-[8.75rem] group-focus-within/rail:translate-x-0 group-focus-within/rail:opacity-100 group-hover/rail-link:text-[#eef3ff]",
          !compact && "-translate-x-1",
        )}
      >
        {item.railLabel}
      </span>
    </Link>
  );
}

function CardCornerSparkles() {
  return (
    <>
      <span className="home-card-sparkle home-card-sparkle--tl" />
      <span className="home-card-sparkle home-card-sparkle--tr" />
      <span className="home-card-sparkle home-card-sparkle--bl" />
      <span className="home-card-sparkle home-card-sparkle--br" />
    </>
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

      {/* Side rail – desktop */}
      <aside className="fixed left-6 top-1/2 z-30 hidden -translate-y-1/2 md:block">
        <nav className="home-liquid-glass home-liquid-glass-rail group/rail flex w-[5.35rem] flex-col gap-1.5 overflow-hidden rounded-[1.9rem] px-3 py-3 transition-[width] duration-500 hover:w-[15.75rem] focus-within:w-[15.75rem]">
          {SIDE_RAIL_ITEMS.map((item) => (
            <RailLink key={item.href} item={item} setupComplete={setupComplete} />
          ))}
        </nav>
      </aside>

      {/* Bottom rail – mobile */}
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

      {/* Main content – centered logo + cards */}
      <main className="relative z-10 flex min-h-screen flex-col items-center justify-center px-5 pb-32 pt-8 sm:px-8 md:px-12 lg:px-16">
        {/* Central logo with orbital ring */}
        <motion.div
          initial={{ opacity: 0, scale: 0.92 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.7, ease: "easeOut" }}
          className="mb-16 flex flex-col items-center sm:mb-20"
        >
          <h1 className="sr-only">AXIOM</h1>
          <div className="home-orbital-ring relative flex items-center justify-center">
            <AxiomHomeLogo
              className="size-28 sm:size-32 md:size-36"
              priority
            />
          </div>
        </motion.div>

        {/* Action cards */}
        <motion.section
          initial={{ opacity: 0, y: 28 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, ease: "easeOut", delay: 0.15 }}
          className="grid w-full max-w-4xl gap-5 md:grid-cols-3 md:gap-6"
        >
          {ACTION_ITEMS.map((item, index) => {
            const href = resolveHref(item.href, setupComplete);

            return (
              <motion.div
                key={item.href}
                initial={{ opacity: 0, y: 22 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45, ease: "easeOut", delay: 0.25 + index * 0.1 }}
                whileHover={{ y: -6 }}
                whileTap={{ scale: 0.98 }}
              >
                <Link
                  href={href}
                  className="home-cosmos-card group relative flex flex-col items-center gap-5 rounded-2xl px-6 py-8 text-center md:px-8 md:py-10"
                >
                  <CardCornerSparkles />

                  <div className="relative">
                    <HomeLaunchIcon
                      kind={item.kind ?? "chat"}
                      animated
                      size={80}
                      className="transition-transform duration-500 group-hover:-translate-y-1 group-hover:scale-[1.06]"
                    />
                  </div>

                  <div className="space-y-2">
                    <h2 className="font-display text-xl font-semibold tracking-[-0.03em] text-[#f4f7ff]">
                      {item.label}
                    </h2>
                    <p className="text-sm leading-6 text-[#8f98b1]">
                      {item.description}
                    </p>
                  </div>
                </Link>
              </motion.div>
            );
          })}
        </motion.section>
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
