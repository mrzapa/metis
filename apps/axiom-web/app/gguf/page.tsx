"use client";

import { useCallback, useEffect, useState } from "react";
import {
  fetchGgufCatalog,
  fetchGgufHardware,
  fetchGgufInstalled,
  validateGgufModel,
  refreshGgufCatalog,
  registerGgufModel,
  unregisterGgufModel,
  type GgufCatalogEntry,
  type GgufHardwareProfile,
  type GgufInstalledEntry,
  type GgufValidateResult,
} from "@/lib/api";
import { PageChrome } from "@/components/shell/page-chrome";
import { AnimatedLucideIcon } from "@/components/ui/animated-lucide-icon";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  AlertCircle,
  CheckCircle2,
  Cpu,
  HardDrive,
  Loader2,
  RefreshCw,
  Trash2,
  FileCheck,
  Upload,
} from "lucide-react";

const USE_CASES = [
  { value: "general", label: "General" },
  { value: "chat", label: "Chat" },
  { value: "coding", label: "Coding" },
  { value: "reasoning", label: "Reasoning" },
];

const SCORE_LABELS: Record<string, string> = {
  quality: "Quality",
  speed: "Speed",
  fit: "Hardware fit",
  context: "Context",
};

function OverviewPill({
  label,
  value,
  note,
}: {
  label: string;
  value: string;
  note: string;
}) {
  return (
    <div className="rounded-[1.1rem] border border-white/8 bg-black/10 px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
        {label}
      </p>
      <p className="mt-2 text-lg font-semibold text-foreground">{value}</p>
      <p className="mt-1 text-xs leading-5 text-muted-foreground">{note}</p>
    </div>
  );
}

function HardwareCard({ hardware }: { hardware: GgufHardwareProfile }) {
  const totalMemory = hardware.total_ram_gb.toFixed(1);
  const availableMemory = hardware.available_ram_gb.toFixed(1);
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-base">
          <AnimatedLucideIcon icon={Cpu} mode="hoverLift" className="size-4" />
          Hardware Profile
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2">
          <OverviewPill label="RAM" value={`${totalMemory} GB`} note="Total system memory." />
          <OverviewPill
            label="Available"
            value={`${availableMemory} GB`}
            note="Headroom for local inference."
          />
          <OverviewPill
            label="CPU"
            value={`${hardware.total_cpu_cores} cores`}
            note="Detected compute budget."
          />
          <OverviewPill label="Backend" value={hardware.backend} note="Current inference backend." />
        </div>

        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">GPU:</span>
          <span>{hardware.has_gpu ? "Yes" : "No"}</span>
          <Badge variant="secondary" className="ml-1">
            {hardware.detected ? "Detected" : "Advisory"}
          </Badge>
        </div>

        {hardware.has_gpu && hardware.gpu_name && (
          <div className="flex items-center gap-2 rounded-[1rem] border border-white/8 bg-black/10 px-3 py-3">
            <AnimatedLucideIcon icon={HardDrive} mode="hoverLift" className="size-4 text-muted-foreground" />
            <span className="min-w-0 truncate">{hardware.gpu_name}</span>
            {hardware.gpu_vram_gb && <span>({hardware.gpu_vram_gb} GB VRAM)</span>}
          </div>
        )}
        {!hardware.detected && (
          <div className="flex items-center gap-1 rounded-[1rem] border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-600">
            <AnimatedLucideIcon icon={AlertCircle} mode="idlePulse" className="size-3" />
            Hardware detection limited — recommendations are advisory only
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function FitBadge({ level }: { level: string }) {
  const variants: Record<string, "default" | "secondary" | "destructive"> = {
    perfect: "default",
    good: "default",
    marginal: "secondary",
    too_tight: "destructive",
  };
  return <Badge variant={variants[level] || "secondary"}>{level}</Badge>;
}

function ScoreBreakdown({ entry }: { entry: GgufCatalogEntry }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {Object.entries(entry.score_components).map(([key, value]) => (
        <div key={key} className="rounded-[1rem] border border-white/8 bg-black/10 px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs uppercase tracking-[0.18em] text-muted-foreground">
              {SCORE_LABELS[key] || key}
            </span>
            <span className="text-sm font-semibold text-foreground">{value.toFixed(1)}</span>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/8">
            <div
              className="h-full rounded-full bg-primary/80"
              style={{ width: `${Math.max(0, Math.min(value, 100))}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}

function RecommendationDetails({
  entry,
  alternatives,
}: {
  entry: GgufCatalogEntry | null;
  alternatives: GgufCatalogEntry[];
}) {
  if (!entry) {
    return (
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Fit explanation</CardTitle>
        </CardHeader>
        <CardContent className="text-sm leading-6 text-muted-foreground">
          Select a catalogue entry to inspect why it fits this machine.
        </CardContent>
      </Card>
    );
  }

  const signals = entry.notes.filter((note) => !entry.caveats.includes(note));

  return (
    <Card data-testid="gguf-fit-panel">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="text-base">Why this model</CardTitle>
            <p className="mt-1 text-sm text-muted-foreground">{entry.model_name}</p>
          </div>
          <FitBadge level={entry.fit_level} />
        </div>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <OverviewPill label="Score" value={entry.score.toFixed(1)} note="Weighted recommendation score." />
          <OverviewPill
            label="Run mode"
            value={entry.run_mode.replaceAll("_", " ")}
            note={`${entry.best_quant} · ${entry.estimated_tps.toFixed(1)} tok/s`}
          />
        </div>

        <div className="rounded-[1rem] border border-white/8 bg-black/10 px-4 py-4 text-sm leading-6 text-muted-foreground">
          {entry.recommendation_summary}
        </div>

        <div className="space-y-3">
          <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Score breakdown</p>
          <ScoreBreakdown entry={entry} />
        </div>

        {signals.length > 0 && (
          <div className="space-y-3">
            <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Positive signals</p>
            <div className="space-y-2">
              {signals.map((note) => (
                <div key={note} className="rounded-[1rem] border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300">
                  {note}
                </div>
              ))}
            </div>
          </div>
        )}

        {entry.caveats.length > 0 && (
          <div className="space-y-3">
            <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Caveats</p>
            <div className="space-y-2">
              {entry.caveats.map((note) => (
                <div key={note} className="rounded-[1rem] border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300">
                  {note}
                </div>
              ))}
            </div>
          </div>
        )}

        {alternatives.length > 0 && (
          <div className="space-y-3">
            <p className="text-xs uppercase tracking-[0.22em] text-muted-foreground">Nearby alternatives</p>
            <div className="space-y-2">
              {alternatives.map((alternative) => (
                <div key={alternative.model_name} className="rounded-[1rem] border border-white/8 bg-black/10 px-3 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-foreground">{alternative.model_name}</p>
                      <p className="text-xs text-muted-foreground">
                        {alternative.best_quant} · {alternative.estimated_tps.toFixed(1)} tok/s
                      </p>
                    </div>
                    <FitBadge level={alternative.fit_level} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function CatalogList({
  entries,
  onSelect,
  selectedModelName,
}: {
  entries: GgufCatalogEntry[];
  onSelect: (modelName: string) => void;
  selectedModelName: string | null;
}) {
  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-[1.2rem] border border-white/8 bg-black/10 py-14 text-muted-foreground">
        <AnimatedLucideIcon icon={HardDrive} mode="idlePulse" className="size-8" />
        <p>No models in catalogue</p>
      </div>
    );
  }

  return (
    <div className="grid gap-3 xl:grid-cols-2">
      {entries.map((entry) => (
        <button
          key={entry.model_name}
          type="button"
          onClick={() => onSelect(entry.model_name)}
          className="text-left"
          aria-pressed={selectedModelName === entry.model_name}
        >
          <Card
            size="sm"
            className={`gap-3 transition-colors ${
              selectedModelName === entry.model_name
                ? "border-primary/60 bg-primary/5"
                : "hover:border-primary/20"
            }`}
          >
            <CardHeader className="pb-2">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="space-y-1">
                  <CardTitle className="text-sm">{entry.model_name}</CardTitle>
                  <p className="text-xs text-muted-foreground">
                    {entry.provider} · {entry.best_quant}
                  </p>
                </div>
                <div className="flex flex-wrap justify-end gap-2">
                  <Badge variant="outline">{entry.parameter_count}</Badge>
                  <Badge variant="outline">{entry.architecture}</Badge>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-3 text-xs text-muted-foreground">
              <p className="line-clamp-3 leading-5">{entry.recommendation_summary}</p>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap gap-2">
                  <span>{entry.estimated_tps.toFixed(1)} tok/s</span>
                  <span>~{entry.memory_required_gb.toFixed(1)} GB</span>
                </div>
                <div className="flex items-center gap-2">
                  <FitBadge level={entry.fit_level} />
                  <Badge variant="outline">{entry.run_mode}</Badge>
                </div>
              </div>
            </CardContent>
          </Card>
        </button>
      ))}
    </div>
  );
}

function InstalledList({
  entries,
  onUnregister,
  unregistering,
}: {
  entries: GgufInstalledEntry[];
  onUnregister: (id: string) => void;
  unregistering: string | null;
}) {
  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-[1.2rem] border border-white/8 bg-black/10 py-14 text-muted-foreground">
        <AnimatedLucideIcon icon={Upload} mode="idlePulse" className="size-8" />
        <p>No locally registered models</p>
        <p className="text-xs">Use the validator below to register a model</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {entries.map((entry) => (
        <Card
          key={entry.id}
          size="sm"
          className="gap-3"
        >
          <CardContent className="flex items-center justify-between gap-4 pt-4">
            <div className="min-w-0 flex-1 space-y-1">
              <span className="block truncate font-medium">{entry.name}</span>
              <span className="block truncate text-xs text-muted-foreground">
                {entry.path}
              </span>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onUnregister(entry.id)}
              disabled={unregistering === entry.id}
              className="text-destructive hover:text-destructive"
            >
              {unregistering === entry.id ? (
                <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4" />
              ) : (
                <AnimatedLucideIcon icon={Trash2} mode="hoverLift" className="size-4" />
              )}
            </Button>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function GgufPage() {
  const [hardware, setHardware] = useState<GgufHardwareProfile | null>(null);
  const [catalog, setCatalog] = useState<GgufCatalogEntry[]>([]);
  const [installed, setInstalled] = useState<GgufInstalledEntry[]>([]);
  const [selectedModelName, setSelectedModelName] = useState<string | null>(null);
  const [useCase, setUseCase] = useState("general");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  // Validation state
  const [validatePath, setValidatePath] = useState("");
  const [validating, setValidating] = useState(false);
  const [validateResult, setValidateResult] = useState<GgufValidateResult | null>(null);
  const [validateError, setValidateError] = useState<string | null>(null);

  // Register state
  const [registering, setRegistering] = useState(false);
  const [registerSuccess, setRegisterSuccess] = useState(false);

  // Unregister state
  const [unregistering, setUnregistering] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [hw, cat, inst] = await Promise.all([
        fetchGgufHardware(),
        fetchGgufCatalog(useCase),
        fetchGgufInstalled(),
      ]);
      setHardware(hw);
      setCatalog(cat);
      setInstalled(inst);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  }, [useCase]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (catalog.length === 0) {
      setSelectedModelName(null);
      return;
    }
    if (!catalog.some((entry) => entry.model_name === selectedModelName)) {
      setSelectedModelName(catalog[0]?.model_name ?? null);
    }
  }, [catalog, selectedModelName]);

  const selectedCatalogEntry =
    catalog.find((entry) => entry.model_name === selectedModelName) ?? catalog[0] ?? null;
  const alternativeEntries = selectedCatalogEntry
    ? catalog.filter((entry) => entry.model_name !== selectedCatalogEntry.model_name).slice(0, 3)
    : [];

  async function handleRefresh() {
    setRefreshing(true);
    try {
      await refreshGgufCatalog(useCase);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh");
    } finally {
      setRefreshing(false);
    }
  }

  async function handleValidate() {
    if (!validatePath.trim()) return;
    setValidating(true);
    setValidateError(null);
    setValidateResult(null);
    setRegisterSuccess(false);
    try {
      const result = await validateGgufModel(validatePath);
      setValidateResult(result);
    } catch (err) {
      setValidateError(err instanceof Error ? err.message : "Validation failed");
    } finally {
      setValidating(false);
    }
  }

  async function handleRegister() {
    if (!validateResult) return;
    setRegistering(true);
    setRegisterSuccess(false);
    try {
      await registerGgufModel(validateResult.filename, validateResult.path);
      setRegisterSuccess(true);
      setValidateResult(null);
      setValidatePath("");
      const inst = await fetchGgufInstalled();
      setInstalled(inst);
    } catch (err) {
      setValidateError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setRegistering(false);
    }
  }

  async function handleUnregister(id: string) {
    setUnregistering(id);
    try {
      await unregisterGgufModel(id);
      setInstalled(installed.filter((e) => e.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to unregister");
    } finally {
      setUnregistering(null);
    }
  }

  return (
    <PageChrome
      eyebrow="Models"
      title="Manage local GGUF models"
      description="Browse the catalogue, check hardware compatibility, validate, and register local models for fully offline inference."
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-2 rounded-full border border-white/8 bg-black/10 px-3 py-1.5 text-sm">
            <span className="text-muted-foreground">Use case</span>
            <select
              value={useCase}
              onChange={(e) => setUseCase(e.target.value)}
              className="bg-transparent text-foreground outline-none"
            >
              {USE_CASES.map((uc) => (
                <option key={uc.value} value={uc.value} className="bg-background text-foreground">
                  {uc.label}
                </option>
              ))}
            </select>
          </div>
          <Button variant="outline" onClick={handleRefresh} disabled={refreshing} className="gap-1.5">
            {refreshing ? (
              <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4" />
            ) : (
              <AnimatedLucideIcon icon={RefreshCw} mode="hoverLift" className="size-4" />
            )}
            Refresh
          </Button>
        </div>
      }
      heroAside={
        <div className="space-y-3">
          <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
            Local inference posture
          </p>
          <p className="text-sm leading-7 text-muted-foreground">
            Browse advisory hardware fit, validate a GGUF file before registering it, and keep a local model catalogue close to the rest of the workspace.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <OverviewPill
              label="Catalogue"
              value={`${catalog.length}`}
              note="Models surfaced for this use case."
            />
            <OverviewPill
              label="Installed"
              value={`${installed.length}`}
              note="Locally registered files."
            />
          </div>
        </div>
      }
    >
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <section className="grid gap-3 md:grid-cols-2">
          <OverviewPill
            label="Hardware"
            value={hardware ? `${hardware.total_cpu_cores} cores` : "—"}
            note="Detected compute profile."
          />
          <OverviewPill
            label="Memory"
            value={hardware ? `${hardware.available_ram_gb.toFixed(1)} GB free` : "—"}
            note="Headroom for local inference."
          />
        </section>

        {error && (
          <div className="flex items-center gap-2 rounded-[1.1rem] border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <AnimatedLucideIcon icon={AlertCircle} mode="idlePulse" className="size-4" />
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center gap-2 rounded-[1.2rem] border border-white/8 bg-black/10 px-4 py-4 text-muted-foreground">
            <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-6" />
            Loading models...
          </div>
        ) : (
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.12fr)_minmax(20rem,0.88fr)]">
            <div className="space-y-6">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle>Model catalogue and installed files</CardTitle>
                </CardHeader>
                <CardContent>
                  <Tabs defaultValue="catalog" className="space-y-5">
                    <TabsList className="grid w-full grid-cols-3">
                      <TabsTrigger value="catalog">Catalogue ({catalog.length})</TabsTrigger>
                      <TabsTrigger value="installed">Installed ({installed.length})</TabsTrigger>
                      <TabsTrigger value="validate">Validate</TabsTrigger>
                    </TabsList>

                    <TabsContent value="catalog" className="mt-0">
                      <CatalogList
                        entries={catalog}
                        onSelect={setSelectedModelName}
                        selectedModelName={selectedModelName}
                      />
                    </TabsContent>

                    <TabsContent value="installed" className="mt-0">
                      <InstalledList
                        entries={installed}
                        onUnregister={handleUnregister}
                        unregistering={unregistering}
                      />
                    </TabsContent>

                    <TabsContent value="validate" className="mt-0 space-y-4">
                      <Card className="border-white/8 bg-black/10">
                        <CardHeader className="pb-2">
                          <CardTitle className="flex items-center gap-2 text-base">
                            <AnimatedLucideIcon icon={FileCheck} mode="hoverLift" className="size-4" />
                            Validate Model
                          </CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                          <div className="flex flex-col gap-2 md:flex-row">
                            <Input
                              placeholder="Path to GGUF file (e.g., C:\\models\\model.gguf)"
                              value={validatePath}
                              onChange={(e) => setValidatePath(e.target.value)}
                              onKeyDown={(e) => e.key === "Enter" && handleValidate()}
                              className="flex-1"
                            />
                            <Button onClick={handleValidate} disabled={validating || !validatePath.trim()} className="gap-1.5">
                              {validating && <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4" />}
                              Validate
                            </Button>
                          </div>

                          {validateError && (
                            <div className="flex items-center gap-2 rounded-[1rem] border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                              <AnimatedLucideIcon icon={AlertCircle} mode="idlePulse" className="size-4" />
                              {validateError}
                            </div>
                          )}

                          {validateResult && (
                            <div className="rounded-[1.2rem] border border-green-500/30 bg-green-500/10 p-4">
                              <div className="mb-3 flex items-center gap-2 text-green-600">
                                <AnimatedLucideIcon icon={CheckCircle2} mode="idlePulse" className="size-4" />
                                <span className="font-medium">Valid GGUF Model</span>
                              </div>
                              <div className="grid gap-2 text-sm sm:grid-cols-2">
                                <div>
                                  <span className="text-muted-foreground">Filename:</span> {validateResult.filename}
                                </div>
                                <div>
                                  <span className="text-muted-foreground">Quantization:</span> {validateResult.quant || "unknown"}
                                </div>
                                <div>
                                  <span className="text-muted-foreground">Type:</span> {validateResult.is_instruct ? "Instruct/Chat" : "Base"}
                                </div>
                                <div>
                                  <span className="text-muted-foreground">Size:</span> {(validateResult.file_size_bytes / 1024 / 1024 / 1024).toFixed(2)} GB
                                </div>
                              </div>
                              <Button
                                onClick={handleRegister}
                                disabled={registering}
                                className="mt-4 gap-1.5"
                                size="sm"
                              >
                                {registering && <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4" />}
                                Register Model
                              </Button>
                            </div>
                          )}

                          {registerSuccess && (
                            <div className="flex items-center gap-2 rounded-[1rem] border border-green-500/30 bg-green-500/10 px-3 py-2 text-sm text-green-600">
                              <AnimatedLucideIcon icon={CheckCircle2} mode="idlePulse" className="size-4" />
                              Model registered successfully
                            </div>
                          )}
                        </CardContent>
                      </Card>
                    </TabsContent>
                  </Tabs>
                </CardContent>
              </Card>
            </div>

            <aside className="space-y-6 xl:sticky xl:top-24">
              {hardware && <HardwareCard hardware={hardware} />}
              <RecommendationDetails entry={selectedCatalogEntry} alternatives={alternativeEntries} />
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Why this layout</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm leading-6 text-muted-foreground">
                  <p>
                    The left side keeps the interactive workbench wide enough for model browsing and validation.
                  </p>
                  <p>
                    The right side stays sticky so hardware fit is always visible while you compare catalogue entries or register a local file.
                  </p>
                </CardContent>
              </Card>
            </aside>
          </div>
        )}
      </div>
    </PageChrome>
  );
}
