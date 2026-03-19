"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import {
  Activity,
  Brain,
  Cpu,
  Home,
  LibraryBig,
  MessageSquare,
  Settings2,
} from "lucide-react";
import { AmbientBackdrop } from "@/components/shell/ambient-backdrop";
import { StatusPill } from "@/components/shell/status-pill";
import { cn } from "@/lib/utils";

interface PageChromeProps {
  title: string;
  description: string;
  eyebrow?: string;
  actions?: ReactNode;
  heroAside?: ReactNode;
  children: ReactNode;
  contentClassName?: string;
  fullBleed?: boolean;
}

const NAV_ITEMS = [
  { href: "/", label: "Welcome", icon: Home },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/library", label: "Library", icon: LibraryBig },
  { href: "/brain", label: "Brain", icon: Brain },
  { href: "/gguf", label: "GGUF", icon: Cpu },
  { href: "/settings", label: "Settings", icon: Settings2 },
  { href: "/diagnostics", label: "Diagnostics", icon: Activity },
];

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function PageChrome({
  title,
  description,
  eyebrow = "Axiom Workspace",
  actions,
  heroAside,
  children,
  contentClassName,
  fullBleed = false,
}: PageChromeProps) {
  const pathname = usePathname();

  return (
    <div className="relative min-h-screen overflow-hidden">
      <AmbientBackdrop />
      <div className="relative z-10 flex min-h-screen">
        <aside className="hidden w-72 shrink-0 p-4 xl:block">
          <div className="glass-panel-strong sticky top-4 flex min-h-[calc(100vh-2rem)] flex-col rounded-[1.8rem] p-5">
            <div className="space-y-3">
              <div className="inline-flex w-fit items-center rounded-full border border-primary/20 bg-primary/12 px-3 py-1 text-[11px] font-medium uppercase tracking-[0.28em] text-primary">
                Local-first
              </div>
              <div>
                <h2 className="font-display text-2xl font-semibold tracking-[-0.04em] text-foreground">
                  Axiom
                </h2>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">
                  A cinematic research workspace for private retrieval, synthesis, and exploration.
                </p>
              </div>
            </div>

            <nav className="mt-8 space-y-2">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                const active = isActive(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-3 rounded-2xl px-3 py-3 text-sm transition-all duration-200",
                      active
                        ? "bg-primary/14 text-foreground shadow-lg shadow-primary/10"
                        : "text-muted-foreground hover:bg-white/6 hover:text-foreground",
                    )}
                  >
                    <span
                      className={cn(
                        "inline-flex size-9 items-center justify-center rounded-xl border",
                        active
                          ? "border-primary/25 bg-primary/16 text-primary"
                          : "border-white/8 bg-white/4 text-muted-foreground",
                      )}
                    >
                      <Icon className="size-4" />
                    </span>
                    {item.label}
                  </Link>
                );
              })}
            </nav>

            <div className="mt-auto space-y-3">
              <StatusPill label="Dark-first interface" tone="neutral" />
              <StatusPill label="Guided onboarding" tone="neutral" />
            </div>
          </div>
        </aside>

        <div className="flex min-w-0 flex-1 flex-col p-4">
          <motion.header
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.42, ease: "easeOut" }}
            className="glass-panel sticky top-4 z-20 rounded-[1.5rem] px-4 py-3 sm:px-5"
          >
            <div className="flex flex-wrap items-center gap-3">
              <Link href="/" className="font-display text-xl font-semibold tracking-[-0.04em] text-foreground">
                Axiom
              </Link>
              <div className="hidden items-center gap-2 md:flex">
                <StatusPill label="Desktop workspace" tone="neutral" />
                <StatusPill label="Private retrieval" tone="neutral" />
              </div>
              <div className="ml-auto flex flex-wrap items-center gap-2">
                {NAV_ITEMS.slice(1, 5).map((item) => (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
                      isActive(pathname, item.href)
                        ? "bg-primary/16 text-primary"
                        : "text-muted-foreground hover:bg-white/8 hover:text-foreground",
                    )}
                  >
                    {item.label}
                  </Link>
                ))}
              </div>
            </div>
          </motion.header>

          <main className="flex-1 py-6">
            <motion.div
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.52, ease: "easeOut" }}
              className="mx-auto w-full max-w-7xl"
            >
              <section className="mb-6 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.7fr)] lg:items-end">
                <div className="glass-panel rounded-[1.8rem] px-5 py-6 sm:px-6">
                  <p className="font-display text-xs uppercase tracking-[0.32em] text-primary/90">
                    {eyebrow}
                  </p>
                  <h1 className="mt-3 font-display text-balance text-4xl font-semibold tracking-[-0.05em] text-foreground">
                    {title}
                  </h1>
                  <p className="mt-3 max-w-3xl text-pretty text-sm leading-7 text-muted-foreground sm:text-base">
                    {description}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-3">
                  {actions}
                  {heroAside ? (
                    <div className="glass-panel min-h-full flex-1 rounded-[1.5rem] px-5 py-4">
                      {heroAside}
                    </div>
                  ) : null}
                </div>
              </section>

              <section className={cn(fullBleed ? "" : "glass-panel rounded-[1.8rem] p-4 sm:p-6", contentClassName)}>
                {children}
              </section>
            </motion.div>
          </main>
        </div>
      </div>
    </div>
  );
}
