"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import {
  Activity,
  Home,
  MessageSquare,
  Settings2,
} from "lucide-react";
import { MetisCompanionDock } from "@/components/shell/metis-companion-dock";
import { WebGPUCompanionProvider } from "@/lib/webgpu-companion/webgpu-companion-context";
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
  hideHeader?: boolean;
  backdropVariant?: "ambient" | "starscape";
  tone?: "default" | "starscape";
  companionContext?: {
    sessionId?: string | null;
    runId?: string | null;
  };
}

const NAV_ITEMS = [
  { href: "/", label: "Home", icon: Home },
  { href: "/chat", label: "Chat", icon: MessageSquare },
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
  hideHeader = false,
  tone = "default",
  companionContext,
}: PageChromeProps) {
  const pathname = usePathname();
  const isStarscape = tone === "starscape";

  return (
    <WebGPUCompanionProvider>
    <div
      className={cn(
        "page-chrome relative min-h-screen overflow-hidden bg-transparent",
        isStarscape && "page-chrome--starscape",
      )}
    >
      <div className="relative z-10 flex min-h-screen">
        {/* ── Main content ────────────────────────────────────────── */}
        <div className="flex min-w-0 flex-1 flex-col p-3 sm:p-4">
          {/* Topbar */}
          <motion.header
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, ease: "easeOut" }}
            className={cn(
              "sticky top-0 z-50 -mx-3 sm:-mx-4 flex items-center px-10 py-7 bg-transparent",
            )}
          >
            <Link href="/">
              <span
                style={{
                  fontFamily: "var(--font-display, 'Space Grotesk', inherit)",
                  fontSize: "15px",
                  fontWeight: 600,
                  letterSpacing: "0.2em",
                  textTransform: "uppercase",
                  color: "oklch(0.92 0.01 248)",
                }}
              >
                METIS<sup style={{ fontSize: "8px", opacity: 0.4, verticalAlign: "super", marginLeft: "2px" }}>AI</sup>
              </span>
            </Link>

            <nav className="ml-10 flex items-center gap-8">
              {NAV_ITEMS.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  data-active={isActive(pathname, item.href) ? "true" : "false"}
                  className={cn(
                    "hidden text-[13px] font-normal tracking-[0.03em] transition-colors duration-300 sm:inline-flex",
                    isActive(pathname, item.href)
                      ? "text-foreground"
                      : "text-muted-foreground/60 hover:text-foreground",
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
              {!hideHeader && (
              <section className="mb-4 grid gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(320px,0.95fr)] xl:items-stretch">
                <div
                  className={cn(
                    "home-liquid-glass flex h-full flex-col rounded-2xl px-5 py-5 sm:px-6 sm:py-6",
                  )}
                >
                  <p
                    className={cn(
                      "text-xs font-medium uppercase tracking-[0.2em]",
                      isStarscape ? "page-chrome-eyebrow" : "eyebrow-gold",
                    )}
                  >
                    {eyebrow}
                  </p>
                  <h1
                    className={cn(
                      "mt-2 text-balance text-3xl font-semibold tracking-tight sm:text-4xl",
                      isStarscape ? "page-chrome-title" : "text-foreground",
                    )}
                  >
                    {title}
                  </h1>
                  <p
                    className={cn(
                      "mt-2 max-w-2xl text-pretty text-sm leading-relaxed",
                      isStarscape ? "page-chrome-description" : "text-muted-foreground",
                    )}
                  >
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
                    <div
                      className={cn(
                        "min-h-full rounded-2xl px-5 py-4 sm:px-6 sm:py-5",
                        isStarscape ? "page-chrome-hero-aside" : "home-liquid-glass",
                      )}
                    >
                      {heroAside}
                    </div>
                  </div>
                ) : null}
              </section>
              )}

              {/* Main content area */}
              <section
                className={cn(
                  fullBleed ? "" : "home-liquid-glass rounded-2xl p-4 sm:p-6",
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
    </WebGPUCompanionProvider>
  );
}
