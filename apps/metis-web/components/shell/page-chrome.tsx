"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import {
  Activity,
  Home,
  LibraryBig,
  MessageSquare,
  Settings2,
} from "lucide-react";
import { AmbientBackdrop } from "@/components/shell/ambient-backdrop";
import { MetisCompanionDock } from "@/components/shell/metis-companion-dock";
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
  companionContext?: {
    sessionId?: string | null;
    runId?: string | null;
  };
}

const NAV_ITEMS = [
  { href: "/", label: "Home", icon: Home },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/library", label: "Library", icon: LibraryBig },
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
  eyebrow = "METIS",
  actions,
  heroAside,
  children,
  contentClassName,
  fullBleed = false,
  companionContext,
}: PageChromeProps) {
  const pathname = usePathname();

  return (
    <div className="relative min-h-screen overflow-hidden">
      <AmbientBackdrop />
      <div className="relative z-10 flex min-h-screen">
        {/* ── Sidebar (xl+) ───────────────────────────────────────── */}
        <aside className="hidden w-64 shrink-0 p-3 xl:block">
          {/* top-3 + bottom p-3 = 1.5rem total vertical padding → min-h = 100dvh - 1.5rem */}
          <nav className="glass-panel-strong sticky top-3 flex min-h-[calc(100dvh-1.5rem)] flex-col rounded-2xl p-4">
            <Link href="/" className="mb-6 flex items-center gap-2.5 px-2">
              <span className="flex size-8 items-center justify-center rounded-lg bg-primary/14 text-primary">
                <Home className="size-4" />
              </span>
              <span className="text-base font-semibold tracking-tight text-foreground">
                METIS
              </span>
            </Link>

            <div className="space-y-1">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                const active = isActive(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={cn(
                      "flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm transition-colors duration-150",
                      active
                        ? "bg-primary/12 font-medium text-foreground"
                        : "text-muted-foreground hover:bg-white/6 hover:text-foreground",
                    )}
                  >
                    <Icon className={cn("size-4", active && "text-primary")} />
                    {item.label}
                  </Link>
                );
              })}
            </div>

            <div className="mt-auto px-2 pt-6">
              <p className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground/60">
                Local-first · Private by default
              </p>
            </div>
          </nav>
        </aside>

        {/* ── Main content ────────────────────────────────────────── */}
        <div className="flex min-w-0 flex-1 flex-col p-3 sm:p-4">
          {/* Topbar */}
          <motion.header
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: "easeOut" }}
            className="glass-panel sticky top-3 z-20 flex items-center gap-3 rounded-xl px-4 py-2.5 sm:top-4 sm:px-5"
          >
            <Link
              href="/"
              className="text-base font-semibold tracking-tight text-foreground xl:hidden"
            >
              METIS
            </Link>

            <nav className="ml-auto flex items-center gap-1">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={cn(
                    "hidden rounded-lg px-2.5 py-1.5 text-xs font-medium transition-colors sm:inline-flex",
                    isActive(pathname, item.href)
                      ? "bg-primary/14 text-primary"
                      : "text-muted-foreground hover:bg-white/6 hover:text-foreground",
                  )}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </motion.header>

          {/* Page content */}
          <main className="flex-1 py-4 sm:py-5">
            <motion.div
              initial={{ opacity: 0, y: 14 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45, ease: "easeOut" }}
              className="mx-auto w-full max-w-384"
            >
              {/* Page header */}
              <section className="mb-4 grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.95fr)] xl:items-stretch">
                <div className="glass-panel flex h-full flex-col rounded-2xl px-5 py-5 sm:px-6 sm:py-6">
                  <p className="text-xs font-medium uppercase tracking-[0.2em] text-primary/80">
                    {eyebrow}
                  </p>
                  <h1 className="mt-2 text-balance text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
                    {title}
                  </h1>
                  <p className="mt-2 max-w-2xl text-pretty text-sm leading-relaxed text-muted-foreground">
                    {description}
                  </p>
                  {actions && !heroAside ? (
                    <div className="mt-5 flex flex-wrap items-center gap-3">
                      {actions}
                    </div>
                  ) : null}
                </div>
                {heroAside ? (
                  <div className="flex min-w-0 flex-col gap-3">
                    {actions ? (
                      <div className="flex flex-wrap items-center gap-3">
                        {actions}
                      </div>
                    ) : null}
                    <div className="glass-panel min-h-full rounded-2xl px-5 py-4 sm:px-6 sm:py-5">
                      {heroAside}
                    </div>
                  </div>
                ) : null}
              </section>

              {/* Main content area */}
              <section
                className={cn(
                  fullBleed ? "" : "glass-panel rounded-2xl p-4 sm:p-6",
                  contentClassName,
                )}
              >
                {children}
              </section>
            </motion.div>
          </main>
        </div>
      </div>
      <MetisCompanionDock
        sessionId={companionContext?.sessionId}
        runId={companionContext?.runId}
      />
    </div>
  );
}
