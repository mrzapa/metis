"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Download,
  FileBadge,
  Loader2,
  TriangleAlert,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  exportSkillBundle,
  fetchInstalledSkills,
  type ForgeInstalledSkill,
} from "@/lib/api";

// M14 Phase 7 — installed-skills pane with per-row Export.
//
// Mounted between <CandidateSkillsPane> and <TechniqueGallery>.
// Hides itself when no skills are installed so the gallery
// stays quiet on a fresh install. Each row's Export button packs
// the skill into a `.metis-skill` bundle (via the Phase 7 export
// route) and triggers a browser download. Version + author are
// captured inline so the user can stamp a meaningful version on
// the bundle without leaving the page.

interface InstalledSkillsPaneProps {
  /** Bumping this prop re-fetches the list. */
  refreshKey?: number;
}

export function InstalledSkillsPane({
  refreshKey = 0,
}: InstalledSkillsPaneProps) {
  const [skills, setSkills] = useState<ForgeInstalledSkill[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const payload = await fetchInstalledSkills();
      setSkills(payload.skills);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to load installed skills.";
      setError(message);
      setSkills([]);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh, refreshKey]);

  const handleExport = useCallback(
    async (skill: ForgeInstalledSkill, version: string, author: string) => {
      if (pendingId !== null) return;
      setActionError(null);
      setPendingId(skill.id);
      try {
        const trimmed = version.trim() || "0.1.0";
        const result = await exportSkillBundle(
          skill.id,
          trimmed,
          author.trim() || undefined,
        );
        const url = URL.createObjectURL(result.blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = result.filename;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : "Export failed.";
        setActionError(message);
      } finally {
        setPendingId(null);
      }
    },
    [pendingId],
  );

  if (skills === null) {
    return null;
  }

  if (error) {
    return (
      <div
        role="alert"
        data-testid="forge-installed-skills-error"
        className="flex items-start gap-2 rounded-xl border border-destructive/25 bg-destructive/10 px-3 py-2 text-xs text-destructive"
      >
        <TriangleAlert className="mt-0.5 size-4 shrink-0" />
        <span>{error}</span>
      </div>
    );
  }

  if (skills.length === 0) {
    return null;
  }

  return (
    <section
      data-testid="forge-installed-skills-pane"
      className="flex flex-col gap-3 rounded-2xl border border-emerald-400/15 bg-emerald-400/[0.04] p-5"
    >
      <header className="flex items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-base font-semibold text-foreground">
            Installed skills
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            {skills.length === 1
              ? "One skill is in your library. Export packages it as a `.metis-skill` bundle for sharing between installs."
              : `${skills.length} skills are in your library. Export packages each as a \`.metis-skill\` bundle for sharing between installs.`}
          </p>
        </div>
      </header>

      {actionError ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-destructive/25 bg-destructive/10 px-3 py-2 text-[11px] text-destructive"
        >
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          <span>{actionError}</span>
        </div>
      ) : null}

      <ul className="flex flex-col gap-2">
        {skills.map((skill) => (
          <li key={skill.id}>
            <SkillRow
              skill={skill}
              pending={pendingId === skill.id}
              disabled={pendingId !== null}
              onExport={handleExport}
            />
          </li>
        ))}
      </ul>
    </section>
  );
}

interface SkillRowProps {
  skill: ForgeInstalledSkill;
  pending: boolean;
  disabled: boolean;
  onExport: (
    skill: ForgeInstalledSkill,
    version: string,
    author: string,
  ) => void;
}

function SkillRow({ skill, pending, disabled, onExport }: SkillRowProps) {
  const [version, setVersion] = useState("0.1.0");
  const [author, setAuthor] = useState("");

  const inputClass = cn(
    "min-w-0 rounded-md border border-white/15 bg-white/[0.03] px-2 py-1 text-[11px] text-foreground",
    "placeholder:text-muted-foreground/50 focus:border-emerald-400/50 focus:outline-none",
  );

  return (
    <div
      data-testid="forge-installed-skill-row"
      data-skill-id={skill.id}
      className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/[0.02] p-3"
    >
      <header className="flex items-baseline justify-between gap-3">
        <h3 className="font-display text-sm font-semibold text-foreground">
          {skill.name}
        </h3>
        <code className="font-mono text-[10px] text-muted-foreground/70">
          {skill.id}
        </code>
      </header>
      <p className="text-xs leading-relaxed text-muted-foreground">
        {skill.description || "(No description.)"}
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-1 text-[10px] uppercase tracking-[0.12em] text-muted-foreground/70">
          version
          <input
            type="text"
            value={version}
            onChange={(e) => setVersion(e.target.value)}
            placeholder="0.1.0"
            className={cn(inputClass, "w-20")}
            aria-label={`Version for ${skill.name}`}
          />
        </label>
        <label className="flex flex-1 items-center gap-1 text-[10px] uppercase tracking-[0.12em] text-muted-foreground/70">
          author
          <input
            type="text"
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            placeholder="optional"
            className={cn(inputClass, "min-w-[8rem] flex-1")}
            aria-label={`Author for ${skill.name}`}
          />
        </label>
        <button
          type="button"
          onClick={() => onExport(skill, version, author)}
          disabled={disabled || !version.trim()}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-md border border-emerald-400/30 bg-emerald-400/10 px-3 py-1 text-[11px] font-medium text-emerald-200",
            "transition-colors hover:bg-emerald-400/15",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          {pending ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <Download className="size-3.5" aria-hidden="true" />
          )}
          Export
        </button>
      </div>
    </div>
  );
}

export { FileBadge as InstalledSkillsIcon };
