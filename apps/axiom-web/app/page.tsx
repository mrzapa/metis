"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { AmbientBackdrop } from "@/components/shell/ambient-backdrop";
import { StatusPill } from "@/components/shell/status-pill";
import { WelcomeHero } from "@/components/shell/welcome-hero";
import { fetchSettings, getApiBase } from "@/lib/api";
import {
  ArrowRight,
  Brain,
  LibraryBig,
  MessageSquare,
  ShieldCheck,
} from "lucide-react";

type Status = "connected" | "disconnected" | "checking";

export default function Home() {
  const [status, setStatus] = useState<Status>("checking");
  const [sidecarError, setSidecarError] = useState<string | null>(null);
  const [setupComplete, setSetupComplete] = useState<boolean | null>(null);

  useEffect(() => {
    if (typeof window === "undefined" || !("__TAURI_INTERNALS__" in window)) {
      return;
    }
    let unlisten: (() => void) | undefined;
    import("@tauri-apps/api/event").then(({ listen }) => {
      listen<string>("sidecar-timeout", (event) => {
        setSidecarError(event.payload);
        setStatus("disconnected");
      }).then((fn) => {
        unlisten = fn;
      });
    });
    return () => unlisten?.();
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const base = await getApiBase();
        const res = await fetch(`${base}/healthz`);
        const data = await res.json();
        if (!cancelled) setStatus(data.ok ? "connected" : "disconnected");
      } catch {
        if (!cancelled) setStatus("disconnected");
      }
    }

    check();
    const id = setInterval(check, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

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
          setSetupComplete(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const statusTone =
    status === "connected"
      ? "connected"
      : status === "disconnected"
        ? "disconnected"
        : "checking";

  return (
    <div className="relative min-h-screen overflow-hidden">
      <AmbientBackdrop />

      <div className="relative z-10 mx-auto flex min-h-screen max-w-7xl flex-col px-4 pb-8 pt-4 sm:px-6 lg:px-8">
        <header className="glass-panel flex flex-wrap items-center gap-3 rounded-[1.6rem] px-4 py-3 sm:px-5">
          <div>
            <p className="font-display text-lg font-semibold tracking-[-0.04em] text-foreground">Axiom</p>
            <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
              local-first AI workspace
            </p>
          </div>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <StatusPill
              label={
                status === "connected"
                  ? "API online"
                  : status === "disconnected"
                    ? "API unavailable"
                    : "Checking API"
              }
              tone={statusTone}
              animate={status === "checking"}
            />
            <Link href="/diagnostics">
              <Button variant="outline" size="sm">Diagnostics</Button>
            </Link>
          </div>
        </header>

        <main className="flex-1 py-10 sm:py-12">
          <WelcomeHero
            eyebrow="Launch-First Workspace"
            title="A private research cockpit that feels inviting from the first second."
            description="Axiom now opens like a product instead of a placeholder: you can verify system health, complete setup with a guided path, build your first index, and move into chat without losing momentum."
            actions={
              <>
                <Link href={setupComplete ? "/chat" : "/setup"}>
                  <Button size="lg" className="gap-2">
                    {setupComplete ? "Open workspace" : "Start guided setup"}
                    <ArrowRight className="size-4" />
                  </Button>
                </Link>
                <Link href={setupComplete ? "/library" : "/diagnostics"}>
                  <Button variant="outline" size="lg">
                    {setupComplete ? "Build an index" : "Check diagnostics"}
                  </Button>
                </Link>
              </>
            }
            stats={[
              { label: "Privacy posture", value: "Local-first" },
              { label: "Primary flow", value: "Chat + Retrieval" },
              { label: "First-run tone", value: "Guided" },
            ]}
            preview={
              <div className="space-y-4">
                <div className="flex flex-wrap gap-2">
                  <Badge variant="outline">Grounded answers</Badge>
                  <Badge variant="outline">Recursive research</Badge>
                  <Badge variant="outline">Desktop sidecar API</Badge>
                </div>

                <div className="rounded-[1.5rem] border border-white/8 bg-black/12 p-5">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-xs uppercase tracking-[0.26em] text-muted-foreground">
                        System readiness
                      </p>
                      <p className="mt-2 font-display text-2xl font-semibold tracking-[-0.04em] text-foreground">
                        {status === "connected"
                          ? "Ready to launch"
                          : status === "disconnected"
                            ? "Needs attention"
                            : "Checking local services"}
                      </p>
                    </div>
                    <StatusPill
                      label={
                        status === "connected"
                          ? "Connected"
                          : status === "disconnected"
                            ? "Disconnected"
                            : "Checking"
                      }
                      tone={statusTone}
                      animate={status === "checking"}
                    />
                  </div>
                  <p className="mt-3 text-sm leading-7 text-muted-foreground">
                    {sidecarError ??
                      (status === "connected"
                        ? "The local API responded successfully. You can move straight into onboarding or open the workspace."
                        : "If the sidecar does not become available, use diagnostics to inspect logs, version compatibility, and safe settings." )}
                  </p>
                </div>
              </div>
            }
          />

          <section className="mt-8 grid gap-4 lg:grid-cols-3">
            {[
              {
                href: setupComplete ? "/chat" : "/setup",
                icon: MessageSquare,
                title: setupComplete ? "Chat immediately" : "Guided setup",
                body: setupComplete
                  ? "Direct and RAG chat are ready as soon as you enter the workspace."
                  : "Choose providers, set credentials, build an index, and launch with a starter prompt.",
              },
              {
                href: "/library",
                icon: LibraryBig,
                title: "Build knowledge bases",
                body: "Import documents with a calmer, more visual indexing workflow that carries cleanly into chat.",
              },
              {
                href: "/brain",
                icon: Brain,
                title: "See the shape of your workspace",
                body: "Explore sessions, indexes, and relationships without leaving the core shell.",
              },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.title}
                  href={item.href}
                  className="glass-panel group rounded-[1.7rem] p-5 transition-all duration-200 hover:-translate-y-1 hover:border-primary/25"
                >
                  <span className="inline-flex size-11 items-center justify-center rounded-2xl border border-primary/20 bg-primary/14 text-primary">
                    <Icon className="size-5" />
                  </span>
                  <h2 className="mt-4 font-display text-2xl font-semibold tracking-[-0.04em] text-foreground">
                    {item.title}
                  </h2>
                  <p className="mt-2 text-sm leading-7 text-muted-foreground">{item.body}</p>
                </Link>
              );
            })}
          </section>

          <section className="mt-8 glass-panel rounded-[1.8rem] p-5 sm:p-6">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
                  Trust signals
                </p>
                <h2 className="mt-2 font-display text-3xl font-semibold tracking-[-0.04em] text-foreground">
                  Designed to feel capable, not chaotic.
                </h2>
              </div>
              <ShieldCheck className="size-8 text-primary" />
            </div>
            <div className="mt-6 grid gap-4 md:grid-cols-3">
              <div className="rounded-[1.35rem] border border-white/8 bg-black/10 p-4">
                <p className="font-medium text-foreground">Local by default</p>
                <p className="mt-2 text-sm leading-7 text-muted-foreground">
                  The launch flow foregrounds privacy and system readiness instead of hiding them behind a blank screen.
                </p>
              </div>
              <div className="rounded-[1.35rem] border border-white/8 bg-black/10 p-4">
                <p className="font-medium text-foreground">Grounded research</p>
                <p className="mt-2 text-sm leading-7 text-muted-foreground">
                  Retrieval, trace, and evidence concepts show up early so users understand how answers are formed.
                </p>
              </div>
              <div className="rounded-[1.35rem] border border-white/8 bg-black/10 p-4">
                <p className="font-medium text-foreground">Actionable diagnostics</p>
                <p className="mt-2 text-sm leading-7 text-muted-foreground">
                  When something fails, diagnostics and setup stay accessible instead of trapping users behind app chrome.
                </p>
              </div>
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
