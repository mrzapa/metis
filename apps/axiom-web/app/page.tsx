"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { SectionHeader } from "@/components/ui/section-header";
import { StatCard } from "@/components/ui/stat-card";
import { AmbientBackdrop } from "@/components/shell/ambient-backdrop";
import { StatusPill } from "@/components/shell/status-pill";
import {
  fetchSettings,
  fetchSessions,
  fetchIndexes,
  getApiBase,
  type SessionSummary,
  type IndexSummary,
} from "@/lib/api";
import {
  ArrowRight,
  BookOpen,
  Brain,
  Clock,
  Database,
  FolderOpen,
  LibraryBig,
  MessageSquare,
  Plus,
  Settings2,
  ShieldCheck,
  Sparkles,
} from "lucide-react";

type ApiStatus = "connected" | "disconnected" | "checking";

const HEALTH_CHECK_INTERVAL_MS = 8000;
const MAX_RECENT_SESSIONS = 5;

export default function Home() {
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");
  const [setupComplete, setSetupComplete] = useState<boolean | null>(null);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [indexes, setIndexes] = useState<IndexSummary[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(true);
  const [loadingIndexes, setLoadingIndexes] = useState(true);

  // Health check
  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const base = await getApiBase();
        const res = await fetch(`${base}/healthz`);
        const data = await res.json();
        if (!cancelled) setApiStatus(data.ok ? "connected" : "disconnected");
      } catch {
        if (!cancelled) setApiStatus("disconnected");
      }
    }
    check();
    const id = setInterval(check, HEALTH_CHECK_INTERVAL_MS);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // Fetch settings for setup state
  useEffect(() => {
    let cancelled = false;
    fetchSettings()
      .then((s) => { if (!cancelled) setSetupComplete(Boolean(s.basic_wizard_completed)); })
      .catch(() => { if (!cancelled) setSetupComplete(false); });
    return () => { cancelled = true; };
  }, []);

  // Fetch recent sessions
  useEffect(() => {
    let cancelled = false;
    fetchSessions()
      .then((data) => { if (!cancelled) setSessions(data.slice(0, MAX_RECENT_SESSIONS)); })
      .catch(() => { if (!cancelled) setSessions([]); })
      .finally(() => { if (!cancelled) setLoadingSessions(false); });
    return () => { cancelled = true; };
  }, []);

  // Fetch indexes
  useEffect(() => {
    let cancelled = false;
    fetchIndexes()
      .then((data) => { if (!cancelled) setIndexes(data); })
      .catch(() => { if (!cancelled) setIndexes([]); })
      .finally(() => { if (!cancelled) setLoadingIndexes(false); });
    return () => { cancelled = true; };
  }, []);

  const totalDocs = indexes.reduce((sum, idx) => sum + idx.document_count, 0);
  const totalChunks = indexes.reduce((sum, idx) => sum + idx.chunk_count, 0);

  const sessionCountLabel = loadingSessions
    ? "—"
    : String(sessions.length);
  const sessionDetailLabel = loadingSessions
    ? "Loading..."
    : sessions.length > 0
      ? "Recent conversations"
      : "No conversations yet";

  return (
    <div className="relative min-h-screen overflow-hidden">
      <AmbientBackdrop />

      <div className="relative z-10 mx-auto flex min-h-screen max-w-6xl flex-col px-4 pb-12 pt-4 sm:px-6 lg:px-8">
        {/* ── Header ──────────────────────────────────────────────── */}
        <motion.header
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: "easeOut" }}
          className="glass-panel flex items-center gap-3 rounded-2xl px-4 py-3 sm:px-5"
        >
          <div>
            <p className="text-lg font-semibold tracking-tight text-foreground">Axiom</p>
            <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
              Local-first AI workspace
            </p>
          </div>
          <nav className="ml-auto hidden items-center gap-1 md:flex">
            {[
              { href: "/chat", label: "Chat" },
              { href: "/library", label: "Library" },
              { href: "/settings", label: "Settings" },
            ].map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="rounded-lg px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:bg-white/8 hover:text-foreground"
              >
                {item.label}
              </Link>
            ))}
          </nav>
          <StatusPill
            label={
              apiStatus === "connected"
                ? "Online"
                : apiStatus === "disconnected"
                  ? "Offline"
                  : "Checking"
            }
            tone={apiStatus === "connected" ? "connected" : apiStatus === "disconnected" ? "disconnected" : "checking"}
            animate={apiStatus === "checking"}
            className="ml-auto md:ml-0"
          />
        </motion.header>

        {/* ── Hero ────────────────────────────────────────────────── */}
        <motion.section
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, ease: "easeOut", delay: 0.05 }}
          className="mt-8 space-y-4"
        >
          <h1 className="text-balance text-4xl font-semibold tracking-tight text-foreground sm:text-5xl">
            Your private research workspace
          </h1>
          <p className="max-w-2xl text-lg leading-relaxed text-muted-foreground">
            Import documents, build knowledge indexes, and get grounded answers — all running locally on your machine.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href={setupComplete ? "/chat" : "/setup"}>
              <Button size="lg" className="gap-2">
                {setupComplete ? "Open workspace" : "Get started"}
                <ArrowRight className="size-4" />
              </Button>
            </Link>
            {setupComplete && (
              <Link href="/library">
                <Button variant="outline" size="lg" className="gap-2">
                  <Plus className="size-4" />
                  Add documents
                </Button>
              </Link>
            )}
          </div>
        </motion.section>

        {/* ── Setup banner (if not complete) ──────────────────────── */}
        {setupComplete === false && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.1 }}
            className="mt-6 flex items-center gap-4 rounded-2xl border border-primary/20 bg-primary/8 px-5 py-4"
          >
            <Sparkles className="size-5 shrink-0 text-primary" />
            <div className="min-w-0 flex-1">
              <p className="font-medium text-foreground">Complete your setup</p>
              <p className="text-sm text-muted-foreground">
                Configure your model provider and import your first documents to unlock grounded AI conversations.
              </p>
            </div>
            <Link href="/setup">
              <Button size="sm" className="shrink-0 gap-1.5">
                Start setup <ArrowRight className="size-3.5" />
              </Button>
            </Link>
          </motion.div>
        )}

        {/* ── Quick actions grid ──────────────────────────────────── */}
        <motion.section
          initial={{ opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.12 }}
          className="mt-8"
        >
          <SectionHeader title="Quick actions" eyebrow="Get started" />
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              {
                href: "/library",
                icon: FolderOpen,
                title: "Add documents",
                desc: "Import files to build a searchable knowledge base.",
              },
              {
                href: "/chat",
                icon: MessageSquare,
                title: "Start a conversation",
                desc: "Ask questions with direct or retrieval-augmented chat.",
              },
              {
                href: "/settings",
                icon: Settings2,
                title: "Configure providers",
                desc: "Set up your preferred LLM and embedding models.",
              },
              {
                href: "/brain",
                icon: Brain,
                title: "Explore your brain",
                desc: "Visualize indexes, sessions, and knowledge connections.",
              },
            ].map((item) => {
              const Icon = item.icon;
              return (
                <Link
                  key={item.title}
                  href={item.href}
                  className="glass-panel group flex flex-col rounded-2xl p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/25"
                >
                  <div className="flex size-10 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-primary transition-colors group-hover:bg-primary/16">
                    <Icon className="size-5" />
                  </div>
                  <h3 className="mt-3 font-semibold text-foreground">{item.title}</h3>
                  <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{item.desc}</p>
                </Link>
              );
            })}
          </div>
        </motion.section>

        {/* ── Stats ───────────────────────────────────────────────── */}
        {setupComplete && (
          <motion.section
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.18 }}
            className="mt-8 grid gap-3 sm:grid-cols-3"
          >
            <StatCard
              icon={<Database className="size-4" />}
              label="Indexes"
              value={loadingIndexes ? "—" : indexes.length}
              detail={loadingIndexes ? "Loading..." : `${totalDocs} documents · ${totalChunks} chunks`}
            />
            <StatCard
              icon={<Clock className="size-4" />}
              label="Sessions"
              value={sessionCountLabel}
              detail={sessionDetailLabel}
            />
            <StatCard
              icon={<ShieldCheck className="size-4" />}
              label="Privacy"
              value="Local-first"
              detail="All data stays on your machine"
            />
          </motion.section>
        )}

        {/* ── Recent sessions ─────────────────────────────────────── */}
        {setupComplete && (
          <motion.section
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.22 }}
            className="mt-8"
          >
            <SectionHeader
              title="Recent sessions"
              eyebrow="History"
              action={
                sessions.length > 0 ? (
                  <Link href="/chat">
                    <Button variant="outline" size="sm" className="gap-1.5">
                      View all <ArrowRight className="size-3.5" />
                    </Button>
                  </Link>
                ) : undefined
              }
            />
            <div className="mt-4">
              {loadingSessions ? (
                <div className="glass-panel rounded-2xl p-8 text-center">
                  <p className="text-sm text-muted-foreground">Loading sessions…</p>
                </div>
              ) : sessions.length === 0 ? (
                <EmptyState
                  icon={<MessageSquare className="size-6" />}
                  title="No conversations yet"
                  description="Start your first conversation to see it here. You can chat directly or use retrieval-augmented mode with your indexed documents."
                  action={
                    <Link href="/chat">
                      <Button className="gap-2">
                        <MessageSquare className="size-4" />
                        Start a conversation
                      </Button>
                    </Link>
                  }
                  className="glass-panel rounded-2xl"
                />
              ) : (
                <div className="grid gap-2">
                  {sessions.map((session) => (
                    <Link
                      key={session.session_id}
                      href={`/chat?session=${session.session_id}`}
                      className="glass-panel group flex items-center gap-4 rounded-xl px-4 py-3 transition-all duration-200 hover:border-primary/20"
                    >
                      <div className="flex size-9 items-center justify-center rounded-lg border border-white/8 bg-white/4 text-muted-foreground group-hover:text-primary">
                        <BookOpen className="size-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate font-medium text-foreground">
                          {session.title || "Untitled session"}
                        </p>
                        <p className="truncate text-xs text-muted-foreground">
                          {session.mode} · {session.llm_provider}/{session.llm_model} ·{" "}
                          {new Date(session.updated_at).toLocaleDateString()}
                        </p>
                      </div>
                      <ArrowRight className="size-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </motion.section>
        )}

        {/* ── Library status ──────────────────────────────────────── */}
        {setupComplete && (
          <motion.section
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.26 }}
            className="mt-8"
          >
            <SectionHeader
              title="Knowledge library"
              eyebrow="Indexes"
              action={
                indexes.length > 0 ? (
                  <Link href="/library">
                    <Button variant="outline" size="sm" className="gap-1.5">
                      Manage library <ArrowRight className="size-3.5" />
                    </Button>
                  </Link>
                ) : undefined
              }
            />
            <div className="mt-4">
              {loadingIndexes ? (
                <div className="glass-panel rounded-2xl p-8 text-center">
                  <p className="text-sm text-muted-foreground">Loading indexes…</p>
                </div>
              ) : indexes.length === 0 ? (
                <EmptyState
                  icon={<LibraryBig className="size-6" />}
                  title="No documents indexed"
                  description="Import your first documents to unlock retrieval-augmented conversations. Axiom will chunk, embed, and index them for fast semantic search."
                  action={
                    <Link href="/library">
                      <Button className="gap-2">
                        <Plus className="size-4" />
                        Add documents
                      </Button>
                    </Link>
                  }
                  className="glass-panel rounded-2xl"
                />
              ) : (
                <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {indexes.map((idx) => (
                    <div key={idx.index_id} className="glass-panel rounded-xl p-4">
                      <div className="flex items-center gap-2">
                        <Database className="size-4 text-primary" />
                        <p className="truncate font-medium text-foreground">
                          {idx.index_id}
                        </p>
                      </div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <Badge variant="outline">{idx.document_count} docs</Badge>
                        <Badge variant="outline">{idx.chunk_count} chunks</Badge>
                        <Badge variant="outline">{idx.backend}</Badge>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.section>
        )}

        {/* ── Footer ──────────────────────────────────────────────── */}
        <footer className="mt-auto pt-12">
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/8 pt-4 text-xs text-muted-foreground">
            <p>Axiom — Private AI workspace</p>
            <div className="flex gap-3">
              <Link href="/settings" className="transition-colors hover:text-foreground">Settings</Link>
              <Link href="/diagnostics" className="transition-colors hover:text-foreground">Diagnostics</Link>
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
}
