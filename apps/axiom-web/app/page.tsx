"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion } from "motion/react";
import {
  Cpu,
  MessageSquare,
  Network,
  Settings2,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { fetchSettings } from "@/lib/api";
import { cn } from "@/lib/utils";

type LaunchItem = {
  href: string;
  label: string;
  railLabel: string;
  description: string;
  icon: LucideIcon;
  emphasized?: boolean;
};

const ACTION_ITEMS: LaunchItem[] = [
  {
    href: "/chat",
    label: "Chat",
    railLabel: "Chat",
    description: "Direct neural synthesis link.",
    icon: MessageSquare,
    emphasized: true,
  },
  {
    href: "/library",
    label: "Build a Neuron",
    railLabel: "Build",
    description: "Architect custom pipelines.",
    icon: Cpu,
  },
  {
    href: "/brain",
    label: "Explore Brain",
    railLabel: "Explore",
    description: "Visual topological mapping.",
    icon: Network,
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

function AxiomEmblem() {
  return (
    <div className="relative size-32 sm:size-40 md:size-48">
      <div className="absolute -inset-16 rounded-full bg-[#0969da]/12 blur-[96px]" />
      <div className="absolute inset-1 rounded-full bg-[radial-gradient(circle_at_50%_45%,rgba(173,198,255,0.22),rgba(9,13,20,0.95)_72%)] shadow-[0_0_80px_rgba(9,105,218,0.18)]" />
      <svg
        viewBox="0 0 240 240"
        className="relative z-10 size-full drop-shadow-[0_0_42px_rgba(9,105,218,0.42)]"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="axiom-core" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#f7fbff" />
            <stop offset="48%" stopColor="#adc6ff" />
            <stop offset="100%" stopColor="#0969da" />
          </linearGradient>
          <linearGradient id="axiom-orbit" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#00c1fd" />
            <stop offset="100%" stopColor="#adc6ff" />
          </linearGradient>
          <radialGradient id="axiom-planet" cx="35%" cy="35%" r="70%">
            <stop offset="0%" stopColor="#eaf1ff" />
            <stop offset="45%" stopColor="#75d1ff" />
            <stop offset="100%" stopColor="#0969da" />
          </radialGradient>
        </defs>
        <circle cx="120" cy="120" r="88" fill="rgba(4,8,14,0.96)" />
        <circle cx="120" cy="120" r="78" fill="url(#axiom-core)" opacity="0.1" />
        <ellipse
          cx="120"
          cy="131"
          rx="98"
          ry="31"
          fill="none"
          stroke="url(#axiom-orbit)"
          strokeWidth="11"
          opacity="0.95"
          transform="rotate(-18 120 120)"
        />
        <ellipse
          cx="120"
          cy="131"
          rx="98"
          ry="31"
          fill="none"
          stroke="rgba(10,14,22,0.9)"
          strokeWidth="5"
          transform="rotate(-18 120 120)"
        />
        <path
          d="M120 36 L146 116 L120 204 L94 116 Z"
          fill="url(#axiom-core)"
        />
        <path
          d="M120 53 L136 119 L120 172 L104 119 Z"
          fill="#f7fbff"
          opacity="0.9"
        />
        <path
          d="M120 36 L128 118 L120 164 L112 118 Z"
          fill="#00c1fd"
          opacity="0.9"
        />
        <circle cx="179" cy="92" r="12" fill="url(#axiom-planet)" />
        <circle cx="182" cy="90" r="3.5" fill="#dfe2eb" opacity="0.95" />
        <circle cx="77" cy="70" r="4.2" fill="#f7fbff" />
        <circle cx="172" cy="63" r="2.8" fill="#f7fbff" opacity="0.92" />
        <circle cx="61" cy="122" r="2.8" fill="#adc6ff" opacity="0.8" />
        <circle cx="156" cy="178" r="2.8" fill="#f7fbff" opacity="0.85" />
      </svg>
    </div>
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
  const Icon = item.icon;
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

      <aside className="fixed left-8 top-1/2 z-30 hidden -translate-y-1/2 md:block">
        <nav className="rail-shell group/rail flex w-16 flex-col gap-3 overflow-hidden rounded-full px-2 py-8 transition-[width] duration-500 hover:w-56">
          {SIDE_RAIL_ITEMS.map((item) => (
            <RailLink key={item.href} item={item} setupComplete={setupComplete} />
          ))}
        </nav>
      </aside>

      <nav className="rail-shell fixed bottom-4 left-1/2 z-30 w-[min(92vw,28rem)] -translate-x-1/2 rounded-[1.75rem] px-2 py-2 md:hidden">
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
            <AxiomEmblem />
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
              const Icon = item.icon;
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
                    className="glass-panel card-sheen group flex min-h-[15.5rem] flex-col items-center justify-center rounded-[2rem] px-7 py-10 text-center transition duration-300 hover:-translate-y-1 hover:bg-white/[0.04] md:min-h-[17rem] md:px-10"
                  >
                    <div className="mb-6 flex size-16 items-center justify-center rounded-full bg-[#adc6ff]/6 text-[#adc6ff] transition-all duration-300 group-hover:scale-110 group-hover:bg-[#adc6ff]/12">
                      <Icon className="size-8" />
                    </div>
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
