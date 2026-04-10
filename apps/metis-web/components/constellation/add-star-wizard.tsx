"use client";

import { useCallback, useRef, useState } from "react";
import { ArrowRight, CheckCircle2, ChevronLeft, Loader2, UploadCloud, X } from "lucide-react";
import { buildIndexStream, suggestStarArchetypes, uploadFiles } from "@/lib/api";
import type { IndexBuildResult } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { CONSTELLATION_FACULTIES, getFacultyColor } from "@/lib/constellation-home";
import type { ConstellationFacultyMetadata } from "@/lib/constellation-home";
import type { UserStar } from "@/lib/constellation-types";
import { cn } from "@/lib/utils";

// ── Faculty matching ──────────────────────────────────────────────────────────

const FACULTY_SIGNALS: Record<string, { keywords: string[]; extensions: string[] }> = {
  perception: {
    keywords: [
      "observation", "detect", "sensor", "observe", "visual", "measure",
      "metric", "monitor", "pattern", "raw", "sample", "signal", "recording",
      "dataset", "telemetry", "survey",
    ],
    extensions: ["csv", "json", "log", "ndjson", "jsonl", "tsv", "parquet"],
  },
  knowledge: {
    keywords: [
      "knowledge", "concept", "definition", "reference", "guide", "manual",
      "documentation", "wiki", "glossary", "learn", "fact", "encyclop",
      "handbook", "primer", "overview", "explainer",
    ],
    extensions: ["md", "mdx", "pdf", "docx", "txt", "rst", "tex", "html"],
  },
  memory: {
    keywords: [
      "journal", "diary", "log", "note", "memory", "session", "history",
      "past", "remember", "record", "archive", "meeting", "standup",
      "retrospective", "reflection", "changelog",
    ],
    extensions: ["md", "txt", "docx"],
  },
  reasoning: {
    keywords: [
      "analysis", "argument", "evidence", "hypothesis", "research", "logic",
      "inference", "proof", "evaluate", "critique", "thesis", "premise",
      "assess", "reasoning", "argument", "deduction",
    ],
    extensions: ["pdf", "md", "txt", "docx"],
  },
  skills: {
    keywords: [
      "tutorial", "how-to", "howto", "recipe", "procedure", "exercise",
      "practice", "skill", "technique", "implement", "build", "steps",
      "workshop", "walkthrough", "cookbook", "playbook",
    ],
    extensions: ["py", "ts", "tsx", "js", "jsx", "sh", "bash", "ipynb", "rb", "go", "rs", "cs", "java"],
  },
  strategy: {
    keywords: [
      "strategy", "plan", "roadmap", "goal", "objective", "okr",
      "priority", "quarter", "initiative", "vision", "mission",
      "decision", "tradeoff", "bet", "proposal", "alignment",
    ],
    extensions: ["md", "docx", "pdf", "pptx", "xlsx"],
  },
  personality: {
    keywords: [
      "personality", "style", "voice", "brand", "persona", "temperament",
      "preference", "about", "bio", "profile", "tone", "character",
      "identity", "self", "manifesto",
    ],
    extensions: ["md", "txt", "docx"],
  },
  values: {
    keywords: [
      "values", "principle", "ethics", "belief", "constitution",
      "constraint", "guideline", "rule", "policy", "conduct",
      "creed", "commitment", "covenant",
    ],
    extensions: ["md", "txt", "pdf"],
  },
  synthesis: {
    keywords: [
      "synthesis", "summary", "overview", "compilation", "integration",
      "cross-domain", "literature", "review", "connect", "combine",
      "aggregate", "meta", "distil", "consolidate",
    ],
    extensions: ["md", "pdf", "docx", "tex"],
  },
  emergence: {
    keywords: [
      "emerge", "emergence", "novel", "discovery", "unexpected",
      "experiment", "explore", "evolve", "adapt", "innovation",
      "prototype", "sketch", "draft", "hypothesis", "probe",
    ],
    extensions: ["md", "txt", "pdf", "ipynb"],
  },
  autonomy: {
    keywords: [
      "agent", "autonomy", "automation", "workflow", "self", "bot",
      "pipeline", "script", "schedule", "autonomous", "auto",
      "directed", "orchestrat", "daemon", "cron",
    ],
    extensions: ["py", "ts", "js", "yaml", "yml", "sh", "toml", "dockerfile"],
  },
};

export interface FacultyScore {
  faculty: ConstellationFacultyMetadata;
  /** 0-100 */
  score: number;
  signals: string[];
}

function scoreFaculties(files: File[], description: string): FacultyScore[] {
  const descLower = description.toLowerCase();
  const fileTokens = files
    .flatMap((f) => [
      f.name.toLowerCase(),
      f.type.toLowerCase(),
      f.name.replace(/[._-]/g, " ").toLowerCase(),
    ])
    .join(" ");

  const raw: Record<string, { raw: number; signals: string[] }> = {};

  for (const faculty of CONSTELLATION_FACULTIES) {
    const signals = FACULTY_SIGNALS[faculty.id];
    if (!signals) {
      raw[faculty.id] = { raw: 0, signals: [] };
      continue;
    }

    let score = 0;
    const matched: string[] = [];

    // Extension match (+2 per matching file)
    for (const file of files) {
      const ext = file.name.split(".").pop()?.toLowerCase() ?? "";
      if (signals.extensions.includes(ext)) {
        score += 2;
        if (!matched.includes(ext)) matched.push(ext);
      }
    }

    // Keyword in file names (+1 each unique match)
    for (const kw of signals.keywords) {
      if (fileTokens.includes(kw)) {
        score += 1;
        if (!matched.includes(kw)) matched.push(kw);
      }
    }

    // Keyword in description (+2 each — stronger signal)
    for (const kw of signals.keywords) {
      if (descLower.includes(kw)) {
        score += 2;
      }
    }

    raw[faculty.id] = { raw: score, signals: matched.slice(0, 3) };
  }

  const maxRaw = Math.max(...Object.values(raw).map((v) => v.raw), 1);

  return CONSTELLATION_FACULTIES.map((faculty) => {
    const entry = raw[faculty.id] ?? { raw: 0, signals: [] };
    return {
      faculty,
      score: Math.round((entry.raw / maxRaw) * 100),
      signals: entry.signals,
    };
  }).sort((a, b) => b.score - a.score);
}

// ── Types ─────────────────────────────────────────────────────────────────────

type WizardStep = "upload" | "analysing" | "match" | "building" | "done";

interface BuildProgress {
  reading: "idle" | "active" | "done";
  embedding: "idle" | "active" | "done";
  saving: "idle" | "active" | "done";
}

const INITIAL_BUILD_PROGRESS: BuildProgress = {
  reading: "idle",
  embedding: "idle",
  saving: "idle",
};

// ── Helpers ───────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function ProgressRow({ label, state }: { label: string; state: "idle" | "active" | "done" }) {
  return (
    <div className={cn("flex items-center gap-3 py-2", state === "idle" && "opacity-40")}>
      <span className="flex size-5 shrink-0 items-center justify-center">
        {state === "done" ? (
          <CheckCircle2 size={16} className="text-emerald-400" />
        ) : state === "active" ? (
          <Loader2 size={16} className="animate-spin text-violet-300" />
        ) : (
          <span className="size-1.5 rounded-full bg-white/30" />
        )}
      </span>
      <span className="text-sm text-slate-300">{label}</span>
    </div>
  );
}

// ── Component ─────────────────────────────────────────────────────────────────

export interface AddStarWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  addUserStar: (star: Omit<UserStar, "id" | "createdAt">) => Promise<UserStar | null>;
  onStarCreated: (star: UserStar) => void;
  onIndexBuilt?: (result: IndexBuildResult) => void;
}

export function AddStarWizard({
  open,
  onOpenChange,
  addUserStar,
  onStarCreated,
  onIndexBuilt,
}: AddStarWizardProps) {
  const [step, setStep] = useState<WizardStep>("upload");
  const [files, setFiles] = useState<File[]>([]);
  const [description, setDescription] = useState("");
  const [dragging, setDragging] = useState(false);
  const [facultyScores, setFacultyScores] = useState<FacultyScore[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [uploadedPaths, setUploadedPaths] = useState<string[]>([]);
  const [buildProgress, setBuildProgress] = useState<BuildProgress>(INITIAL_BUILD_PROGRESS);
  const [selectedFaculty, setSelectedFaculty] = useState<ConstellationFacultyMetadata | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const resetWizard = useCallback(() => {
    setStep("upload");
    setFiles([]);
    setDescription("");
    setFacultyScores([]);
    setError(null);
    setUploadedPaths([]);
    setBuildProgress(INITIAL_BUILD_PROGRESS);
    setSelectedFaculty(null);
  }, []);

  const handleClose = useCallback(() => {
    if (step === "building") return;
    onOpenChange(false);
    setTimeout(resetWizard, 300);
  }, [step, onOpenChange, resetWizard]);

  const mergeFiles = (incoming: FileList | null) => {
    if (!incoming) return;
    const next = Array.from(incoming);
    setFiles((prev) => {
      const names = new Set(prev.map((f) => f.name));
      return [...prev, ...next.filter((f) => !names.has(f.name))];
    });
  };

  const handleAnalyse = useCallback(async () => {
    if (files.length === 0) return;
    setStep("analysing");
    setError(null);

    try {
      const { paths } = await uploadFiles(files);
      setUploadedPaths(paths);

      // Compute frontend faculty scores immediately
      const scores = scoreFaculties(files, description);
      setFacultyScores(scores);
      setStep("match");

      // Boost scores based on archetype API (non-blocking)
      suggestStarArchetypes(paths)
        .then((archetypes) => {
          if (archetypes.length === 0) return;
          setFacultyScores((prev) => {
            const boostMap = new Map<string, number>();
            for (const arch of archetypes) {
              const archText = `${arch.name} ${arch.description} ${arch.why}`.toLowerCase();
              for (const faculty of CONSTELLATION_FACULTIES) {
                const signals = FACULTY_SIGNALS[faculty.id];
                if (!signals) continue;
                const hit = signals.keywords.some((kw) => archText.includes(kw));
                if (hit) {
                  boostMap.set(faculty.id, (boostMap.get(faculty.id) ?? 0) + arch.score * 4);
                }
              }
            }
            if (boostMap.size === 0) return prev;
            const boosted = prev.map((fs) => ({
              ...fs,
              score: Math.min(100, fs.score + (boostMap.get(fs.faculty.id) ?? 0)),
            }));
            return [...boosted].sort((a, b) => b.score - a.score);
          });
        })
        .catch(() => {
          /* archetype suggestion is best-effort */
        });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed — check your connection.");
      setStep("upload");
    }
  }, [files, description]);

  const handlePickFaculty = useCallback(
    async (faculty: ConstellationFacultyMetadata) => {
      setSelectedFaculty(faculty);
      setStep("building");
      setBuildProgress({ reading: "active", embedding: "idle", saving: "idle" });

      try {
        const buildResult = await buildIndexStream(uploadedPaths, {}, (event) => {
          const type = String(event.type ?? "");
          const text = String(event.text ?? "").toLowerCase();
          if (type === "status") {
            if (text.includes("read") || text.includes("load") || text.includes("chunk")) {
              setBuildProgress({ reading: "done", embedding: "active", saving: "idle" });
            } else if (text.includes("embed") || text.includes("vector")) {
              setBuildProgress({ reading: "done", embedding: "done", saving: "active" });
            } else if (text.includes("sav") || text.includes("writ") || text.includes("complet")) {
              setBuildProgress({ reading: "done", embedding: "done", saving: "done" });
            }
          }
        });

        setBuildProgress({ reading: "done", embedding: "done", saving: "done" });
        onIndexBuilt?.(buildResult);

        const star = await addUserStar({
          x: faculty.x,
          y: faculty.y,
          size: 0.82 + Math.random() * 0.55,
          primaryDomainId: faculty.id,
          stage: "seed",
          linkedManifestPaths: [buildResult.manifest_path],
          activeManifestPath: buildResult.manifest_path,
          linkedManifestPath: buildResult.manifest_path,
        });

        if (!star) {
          setError("Unable to place star — the constellation may be full.");
          setStep("match");
          return;
        }

        setStep("done");
        setTimeout(() => {
          onStarCreated(star);
          handleClose();
        }, 900);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to index content. Try again.");
        setStep("match");
      }
    },
    [uploadedPaths, addUserStar, onStarCreated, onIndexBuilt, handleClose],
  );

  // ── Drag & drop ─────────────────────────────────────────────────────────────

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    mergeFiles(e.dataTransfer.files);
  }, []);

  const onDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  }, []);

  const onDragLeave = useCallback(() => setDragging(false), []);

  // ── Step titles ──────────────────────────────────────────────────────────────

  const stepTitle: Record<WizardStep, string> = {
    upload: "Add a star",
    analysing: "Reading content…",
    match: "Choose a faculty",
    building: selectedFaculty ? `Indexing · ${selectedFaculty.label}` : "Building index…",
    done: "Star added ✦",
  };

  const stepSubtitle: Partial<Record<WizardStep, string>> = {
    upload: "Upload content and we'll match it to the right place in your constellation.",
    match: "Select the faculty that best captures this knowledge. We've ranked them by how well your content matches.",
    building: "Embedding and storing your content. This takes a few seconds.",
  };

  // ── Render ───────────────────────────────────────────────────────────────────

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent
        showCloseButton={step !== "building"}
        className="flex w-full max-w-lg flex-col overflow-hidden p-0 max-h-[min(90vh,44rem)]"
      >
        {/* Header */}
        <DialogHeader className="shrink-0 border-b border-white/8 px-6 py-5">
          <div className="flex items-start gap-3">
            {step === "match" && (
              <button
                type="button"
                className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full text-slate-400 transition-colors hover:text-white"
                onClick={() => setStep("upload")}
                aria-label="Back to upload"
              >
                <ChevronLeft size={15} />
              </button>
            )}
            <div className="min-w-0 flex-1">
              <DialogTitle className="font-display text-xl font-semibold tracking-tight text-white">
                {stepTitle[step]}
              </DialogTitle>
              {stepSubtitle[step] && (
                <DialogDescription className="mt-1 text-sm leading-relaxed text-slate-400">
                  {stepSubtitle[step]}
                </DialogDescription>
              )}
            </div>
          </div>
        </DialogHeader>

        {/* Body */}
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-5">

          {/* ── Step: upload ─────────────────────────────────────────────── */}
          {step === "upload" && (
            <div className="space-y-4">
              {/* Drop zone */}
              <button
                type="button"
                className={cn(
                  "relative flex w-full cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed px-6 py-8 text-center transition-colors",
                  dragging
                    ? "border-violet-400/70 bg-violet-500/10"
                    : files.length > 0
                    ? "border-white/20 bg-white/5"
                    : "border-white/12 bg-white/3 hover:border-white/25 hover:bg-white/5",
                )}
                onDrop={onDrop}
                onDragOver={onDragOver}
                onDragLeave={onDragLeave}
                onClick={() => fileInputRef.current?.click()}
                aria-label="Drop files here or click to browse"
              >
                <UploadCloud
                  size={28}
                  className={cn(
                    "transition-colors",
                    dragging ? "text-violet-300" : "text-slate-500",
                  )}
                />
                <p className="text-sm text-slate-300">
                  {files.length === 0
                    ? "Drop files here or click to browse"
                    : `${files.length} file${files.length !== 1 ? "s" : ""} selected — click to add more`}
                </p>
                <p className="text-xs text-slate-500">
                  PDF · MD · TXT · DOCX · CSV · JSON · Python · TypeScript · YAML · and more
                </p>
                <input
                  ref={fileInputRef}
                  type="file"
                  multiple
                  className="sr-only"
                  onChange={(e) => mergeFiles(e.target.files)}
                  accept=".pdf,.md,.mdx,.txt,.docx,.rst,.tex,.csv,.json,.jsonl,.ndjson,.py,.ts,.tsx,.js,.jsx,.sh,.bash,.yaml,.yml,.toml,.html,.ipynb,.rb,.go,.rs,.cs,.java,.log,.tsv"
                />
              </button>

              {/* File list */}
              {files.length > 0 && (
                <ul className="space-y-1.5">
                  {files.map((file, idx) => (
                    <li
                      key={file.name}
                      className="flex items-center gap-2.5 rounded-xl bg-white/5 px-3 py-2 text-sm"
                    >
                      <span className="min-w-0 flex-1 truncate text-slate-200">{file.name}</span>
                      <span className="shrink-0 text-xs text-slate-500">{formatBytes(file.size)}</span>
                      <button
                        type="button"
                        className="shrink-0 rounded-full p-0.5 text-slate-500 transition-colors hover:text-white"
                        aria-label={`Remove ${file.name}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          setFiles((prev) => prev.filter((_, i) => i !== idx));
                        }}
                      >
                        <X size={12} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              {/* Description */}
              <Textarea
                placeholder="Optional: briefly describe this content (e.g. 'my research notes on attention mechanisms')"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                className="resize-none"
              />

              {error && (
                <p className="rounded-xl bg-red-500/12 px-3 py-2 text-sm text-red-300">{error}</p>
              )}

              <div className="flex items-center justify-end gap-2 pt-1">
                <Button variant="ghost" size="sm" onClick={handleClose}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  onClick={handleAnalyse}
                  disabled={files.length === 0}
                  className="gap-1.5"
                >
                  Analyse content
                  <ArrowRight size={14} />
                </Button>
              </div>
            </div>
          )}

          {/* ── Step: analysing ──────────────────────────────────────────── */}
          {step === "analysing" && (
            <div className="flex flex-col items-center gap-4 py-8">
              <Loader2 size={32} className="animate-spin text-violet-400" />
              <p className="text-sm text-slate-400">Uploading and reading your content…</p>
            </div>
          )}

          {/* ── Step: match ──────────────────────────────────────────────── */}
          {step === "match" && (
            <div className="space-y-3">
              {error && (
                <p className="rounded-xl bg-red-500/12 px-3 py-2 text-sm text-red-300">{error}</p>
              )}

              <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {facultyScores.map(({ faculty, score, signals }) => {
                  const [r, g, b] = getFacultyColor(faculty.id);
                  const colorRaw = `${r},${g},${b}`;
                  return (
                    <li key={faculty.id}>
                      <button
                        type="button"
                        className="group relative w-full overflow-hidden rounded-2xl border border-white/8 bg-white/4 px-4 py-3.5 text-left transition-all hover:border-white/20 hover:bg-white/8 active:scale-[0.98]"
                        style={{ "--fc": colorRaw } as React.CSSProperties}
                        onClick={() => handlePickFaculty(faculty)}
                      >
                        {/* Score bar (decorative background fill) */}
                        <div
                          className="pointer-events-none absolute inset-y-0 left-0 rounded-2xl opacity-10 transition-[width] duration-500"
                          style={{
                            width: `${score}%`,
                            background: `rgb(${colorRaw})`,
                          }}
                          aria-hidden="true"
                        />

                        <div className="relative space-y-1">
                          <div className="flex items-baseline justify-between gap-2">
                            <span
                              className="text-sm font-semibold"
                              style={{ color: `rgb(${colorRaw})` }}
                            >
                              {faculty.label}
                            </span>
                            {score > 0 && (
                              <span className="text-xs tabular-nums text-slate-500">
                                {score}%
                              </span>
                            )}
                          </div>

                          <p className="text-xs leading-relaxed text-slate-400 line-clamp-2">
                            {faculty.description}
                          </p>

                          {signals.length > 0 && (
                            <div className="flex flex-wrap gap-1 pt-0.5">
                              {signals.map((s) => (
                                <span
                                  key={s}
                                  className="rounded-full px-1.5 py-0.5 text-[10px]"
                                  style={{
                                    background: `rgba(${colorRaw},0.15)`,
                                    color: `rgb(${colorRaw})`,
                                  }}
                                >
                                  {s}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {/* ── Step: building ───────────────────────────────────────────── */}
          {step === "building" && (
            <div className="space-y-1 py-4">
              {selectedFaculty && (
                <div className="mb-5 flex items-center gap-2">
                  <span
                    className="size-2.5 rounded-full"
                    style={{
                      background: `rgb(${getFacultyColor(selectedFaculty.id).join(",")})`,
                    }}
                  />
                  <span className="text-sm font-medium text-white">{selectedFaculty.label}</span>
                </div>
              )}
              <ProgressRow label="Reading documents" state={buildProgress.reading} />
              <ProgressRow label="Embedding content" state={buildProgress.embedding} />
              <ProgressRow label="Saving index" state={buildProgress.saving} />
              {error && (
                <p className="mt-3 rounded-xl bg-red-500/12 px-3 py-2 text-sm text-red-300">
                  {error}
                </p>
              )}
            </div>
          )}

          {/* ── Step: done ───────────────────────────────────────────────── */}
          {step === "done" && (
            <div className="flex flex-col items-center gap-3 py-8">
              <CheckCircle2 size={36} className="text-emerald-400" />
              <p className="text-sm text-slate-300">
                Star added to{" "}
                <span className="font-semibold text-white">{selectedFaculty?.label}</span>
              </p>
              <p className="text-xs text-slate-500">Opening details…</p>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
