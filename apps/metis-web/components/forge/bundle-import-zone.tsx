"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  AlertOctagon,
  Check,
  FileWarning,
  Loader2,
  Sparkles,
  TriangleAlert,
  Upload,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  installSkillBundle,
  previewSkillBundle,
  publishCompanionActivity,
  type ForgeBundlePreview,
} from "@/lib/api";

// M14 Phase 7 — drop-zone + preview-dialog for `.metis-skill`
// bundle import.
//
// Mounted between <ProposalReviewPane> and <CandidateSkillsPane>
// so the import path sits visually with the other "review before
// activate" surfaces. The flow is:
//   1. User drops or picks a file → preview route inspects it
//      without touching disk and returns the manifest + errors
//      + a `conflict` flag.
//   2. Preview dialog renders manifest fields, an optional
//      "Replace existing skill" checkbox if `conflict` is true,
//      and an "Install" button that dispatches to the install
//      route with the appropriate `replace` flag.
//   3. On success, fire a `kind: "skill_imported"`
//      `CompanionActivityEvent` so the dock acknowledges the
//      absorbed capability and call `onInstalled` so the parent
//      page re-fetches the installed-skills pane.

interface BundleImportZoneProps {
  /** Called once after a successful install completes. */
  onInstalled?: (skillId: string, replaced: boolean) => void;
}

export function BundleImportZone({ onInstalled }: BundleImportZoneProps) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ForgeBundlePreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [installError, setInstallError] = useState<string | null>(null);
  const [replaceConfirmed, setReplaceConfirmed] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const reset = useCallback(() => {
    setFile(null);
    setPreview(null);
    setInstallError(null);
    setReplaceConfirmed(false);
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }, []);

  const handleFile = useCallback(async (selected: File) => {
    setFile(selected);
    setPreview(null);
    setInstallError(null);
    setReplaceConfirmed(false);
    setPreviewing(true);
    try {
      const result = await previewSkillBundle(selected);
      setPreview(result);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Could not preview the bundle.";
      setInstallError(message);
    } finally {
      setPreviewing(false);
    }
  }, []);

  const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const picked = event.target.files?.[0];
    if (picked) {
      void handleFile(picked);
    }
  };

  const handleDragOver = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(true);
  };

  const handleDragLeave = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragActive(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) {
      void handleFile(dropped);
    }
  };

  const handleInstall = useCallback(async () => {
    if (!file || !preview) return;
    if (preview.errors.length > 0) return;
    setInstalling(true);
    setInstallError(null);
    try {
      const result = await installSkillBundle(file, {
        replace: preview.conflict && replaceConfirmed,
      });
      publishCompanionActivity({
        source: "forge",
        kind: "skill_imported",
        state: "completed",
        trigger: result.skill_id,
        summary: result.replaced
          ? `Companion replaced ${preview.manifest.name || result.skill_id}.`
          : `Companion absorbed ${preview.manifest.name || result.skill_id}.`,
        timestamp: Date.now(),
        payload: {
          skill_id: result.skill_id,
          replaced: result.replaced,
        },
      });
      onInstalled?.(result.skill_id, result.replaced);
      reset();
    } catch (err: unknown) {
      const status =
        err instanceof Error
          ? (err as Error & { status?: number }).status
          : undefined;
      if (status === 409) {
        // Race-condition fallback: a second installer slipped in
        // between preview and install. Surface the prompt again
        // so the user explicitly confirms the overwrite.
        setInstallError(
          "Skill already installed. Tick `Replace existing` and try again.",
        );
        setPreview((current) =>
          current ? { ...current, conflict: true } : current,
        );
      } else {
        const message =
          err instanceof Error ? err.message : "Install failed.";
        setInstallError(message);
      }
    } finally {
      setInstalling(false);
    }
  }, [file, preview, replaceConfirmed, onInstalled, reset]);

  // The Install button is disabled if there are validation
  // errors, or the bundle would conflict with an existing skill
  // and the user has not opted in to replace.
  const installDisabled =
    !preview ||
    preview.errors.length > 0 ||
    (preview.conflict && !replaceConfirmed);

  return (
    <section
      data-testid="forge-bundle-import-zone"
      className="flex flex-col gap-3 rounded-2xl border border-cyan-400/15 bg-cyan-400/[0.04] p-5"
    >
      <header className="flex items-center justify-between gap-3">
        <div>
          <h2 className="font-display text-base font-semibold text-foreground">
            Import a skill bundle
          </h2>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            Drop a `.metis-skill` file you received from another METIS
            install. The companion previews the manifest before anything
            touches your skill library.
          </p>
        </div>
      </header>

      {!preview && !previewing ? (
        <DropZone
          dragActive={dragActive}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onPick={() => inputRef.current?.click()}
        />
      ) : null}

      <input
        ref={inputRef}
        type="file"
        accept=".metis-skill,application/x-metis-skill,application/octet-stream"
        className="sr-only"
        onChange={handleInputChange}
        aria-label="Choose a .metis-skill bundle to import"
      />

      {previewing ? (
        <div
          className="flex items-center gap-2 rounded-xl border border-white/10 bg-white/[0.02] px-3 py-3 text-xs text-muted-foreground"
          role="status"
        >
          <Loader2 className="size-3.5 animate-spin" />
          <span>Previewing bundle…</span>
        </div>
      ) : null}

      {preview ? (
        <PreviewCard
          file={file!}
          preview={preview}
          replaceConfirmed={replaceConfirmed}
          onReplaceChange={setReplaceConfirmed}
          installDisabled={installDisabled}
          installing={installing}
          installError={installError}
          onCancel={reset}
          onInstall={handleInstall}
        />
      ) : null}

      {!preview && installError ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-destructive/25 bg-destructive/10 px-3 py-2 text-[11px] text-destructive"
        >
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          <span>{installError}</span>
        </div>
      ) : null}
    </section>
  );
}

interface DropZoneProps {
  dragActive: boolean;
  onDragOver: (event: React.DragEvent<HTMLDivElement>) => void;
  onDragLeave: (event: React.DragEvent<HTMLDivElement>) => void;
  onDrop: (event: React.DragEvent<HTMLDivElement>) => void;
  onPick: () => void;
}

function DropZone({
  dragActive,
  onDragOver,
  onDragLeave,
  onDrop,
  onPick,
}: DropZoneProps) {
  return (
    <div
      onDragOver={onDragOver}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
      data-testid="forge-bundle-drop-zone"
      data-drag-active={dragActive ? "true" : "false"}
      className={cn(
        "flex flex-col items-center gap-2 rounded-xl border border-dashed px-4 py-8 text-center text-xs",
        "border-cyan-400/30 bg-cyan-400/[0.02] text-muted-foreground",
        "transition-colors",
        dragActive && "border-cyan-300 bg-cyan-400/10 text-cyan-100",
      )}
    >
      <Upload className="size-5 text-cyan-300/80" aria-hidden="true" />
      <p>
        Drop a <code className="font-mono text-[11px]">.metis-skill</code> file
        here
      </p>
      <button
        type="button"
        onClick={onPick}
        className="rounded-md border border-cyan-400/30 bg-cyan-400/10 px-3 py-1 text-[11px] font-medium text-cyan-200 transition-colors hover:bg-cyan-400/15"
      >
        or pick a file
      </button>
    </div>
  );
}

interface PreviewCardProps {
  file: File;
  preview: ForgeBundlePreview;
  replaceConfirmed: boolean;
  onReplaceChange: (value: boolean) => void;
  installDisabled: boolean;
  installing: boolean;
  installError: string | null;
  onCancel: () => void;
  onInstall: () => void;
}

function PreviewCard({
  file,
  preview,
  replaceConfirmed,
  onReplaceChange,
  installDisabled,
  installing,
  installError,
  onCancel,
  onInstall,
}: PreviewCardProps) {
  return (
    <div
      data-testid="forge-bundle-preview"
      className="flex flex-col gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-3 text-xs"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <Sparkles className="size-3.5 text-cyan-300" aria-hidden="true" />
          <h3 className="font-display text-sm font-semibold text-foreground">
            {preview.manifest.name || preview.manifest.skill_id || "(unknown)"}
          </h3>
        </div>
        <span className="font-mono text-[10px] text-muted-foreground/70">
          {file.name} · {(file.size / 1024).toFixed(1)} KB
        </span>
      </header>

      {preview.manifest.description ? (
        <p className="text-xs leading-relaxed text-muted-foreground">
          {preview.manifest.description}
        </p>
      ) : null}

      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px] sm:grid-cols-3">
        <ManifestField label="Slug" value={preview.manifest.skill_id} mono />
        <ManifestField label="Version" value={preview.manifest.version} mono />
        <ManifestField
          label="Format"
          value={`v${preview.manifest.bundle_format_version}`}
        />
        <ManifestField
          label="Min METIS"
          value={preview.manifest.min_metis_version}
          mono
        />
        <ManifestField
          label="Author"
          value={preview.manifest.author || "—"}
        />
        <ManifestField
          label="Exported"
          value={preview.manifest.exported_at}
          mono
        />
      </dl>

      {preview.errors.length > 0 ? (
        <div
          role="alert"
          data-testid="forge-bundle-preview-errors"
          className="flex flex-col gap-1 rounded-md border border-destructive/30 bg-destructive/10 p-2 text-[11px] text-destructive"
        >
          <div className="flex items-center gap-1">
            <AlertOctagon className="size-3.5" aria-hidden="true" />
            <strong>This bundle won&apos;t install:</strong>
          </div>
          <ul className="list-disc pl-5">
            {preview.errors.map((err) => (
              <li key={err}>{err}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {preview.conflict ? (
        <label
          data-testid="forge-bundle-replace-confirm"
          className="flex items-start gap-2 rounded-md border border-amber-400/30 bg-amber-400/10 p-2 text-[11px] text-amber-200"
        >
          <input
            type="checkbox"
            className="mt-0.5"
            checked={replaceConfirmed}
            onChange={(event) => onReplaceChange(event.target.checked)}
          />
          <span>
            <FileWarning
              className="-mt-0.5 mr-1 inline size-3.5"
              aria-hidden="true"
            />
            <strong>{preview.manifest.skill_id}</strong> is already installed.
            Replace the existing skill (your local edits will be overwritten).
          </span>
        </label>
      ) : null}

      {installError ? (
        <div
          role="alert"
          className="flex items-start gap-2 rounded-md border border-destructive/25 bg-destructive/10 px-2 py-1.5 text-[11px] text-destructive"
        >
          <TriangleAlert className="mt-0.5 size-3.5 shrink-0" />
          <span>{installError}</span>
        </div>
      ) : null}

      <footer className="flex items-center justify-end gap-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={installing}
          className="inline-flex items-center gap-1 rounded-md border border-white/15 bg-white/[0.03] px-3 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-white/[0.05] disabled:opacity-50"
        >
          <X className="size-3.5" aria-hidden="true" />
          Cancel
        </button>
        <button
          type="button"
          onClick={onInstall}
          disabled={installDisabled || installing}
          className={cn(
            "inline-flex items-center gap-1 rounded-md border px-3 py-1 text-[11px] font-medium transition-colors",
            "border-cyan-400/30 bg-cyan-400/10 text-cyan-200 hover:bg-cyan-400/15",
            "disabled:cursor-not-allowed disabled:opacity-50",
          )}
        >
          {installing ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
          ) : (
            <Check className="size-3.5" aria-hidden="true" />
          )}
          {preview.conflict && replaceConfirmed ? "Replace" : "Install"}
        </button>
      </footer>
    </div>
  );
}

interface ManifestFieldProps {
  label: string;
  value: string;
  mono?: boolean;
}

function ManifestField({ label, value, mono = false }: ManifestFieldProps) {
  return (
    <div className="flex flex-col">
      <dt className="text-[10px] uppercase tracking-[0.12em] text-muted-foreground/60">
        {label}
      </dt>
      <dd
        className={cn(
          "truncate text-foreground",
          mono ? "font-mono text-[11px]" : "text-[11px]",
        )}
      >
        {value || "—"}
      </dd>
    </div>
  );
}
