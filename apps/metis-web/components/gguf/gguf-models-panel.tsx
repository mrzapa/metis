"use client";

import { useCallback, useEffect } from "react";
import {
  fetchGgufCatalog,
  fetchGgufHardware,
  fetchHereticPreflight,
  fetchGgufInstalled,
  refreshGgufCatalog,
  registerGgufModel,
  runHereticAbliterateStream,
  unregisterGgufModel,
  validateGgufModel,
  type GgufCatalogEntry,
  type GgufHardwareProfile,
  type HereticPreflightResponse,
  type GgufInstalledEntry,
  type GgufValidateResult,
} from "@/lib/api";
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
  Scissors,
  Trash2,
  Square,
  FileCheck,
  Upload,
  Copy,
} from "lucide-react";
import { useArrowState } from "@/hooks/use-arrow-state";

type ModelsTabValue = "catalog" | "installed" | "validate" | "heretic";

interface GgufModelsPanelProps {
  initialModelsTab?: string | null;
  initialHereticModelId?: string | null;
}

function resolveModelsTab(value: string | null | undefined): ModelsTabValue {
  return value === "installed" || value === "validate" || value === "heretic" ? value : "catalog";
}

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
    <div className="glass-settings-pane rounded-[1.1rem] px-4 py-3">
      <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">{label}</p>
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
          <div className="glass-settings-pane flex items-center gap-2 rounded-[1rem] px-3 py-3">
            <AnimatedLucideIcon icon={HardDrive} mode="hoverLift" className="size-4 text-muted-foreground" />
            <span className="min-w-0 truncate">{hardware.gpu_name}</span>
            {hardware.gpu_vram_gb && <span>({hardware.gpu_vram_gb} GB VRAM)</span>}
          </div>
        )}

        {!hardware.detected && (
          <div className="flex items-center gap-1 rounded-[1rem] border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-600">
            <AnimatedLucideIcon icon={AlertCircle} mode="idlePulse" className="size-3" />
            Hardware detection limited - recommendations are advisory only
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
        <div key={key} className="glass-settings-pane rounded-[1rem] px-4 py-3">
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

        <div className="glass-settings-pane rounded-[1rem] px-4 py-4 text-sm leading-6 text-muted-foreground">
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
                <div
                  key={note}
                  className="rounded-[1rem] border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-300"
                >
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
                <div
                  key={note}
                  className="rounded-[1rem] border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-300"
                >
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
                <div key={alternative.model_name} className="glass-settings-pane rounded-[1rem] px-3 py-3">
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
      <div className="glass-panel flex flex-col items-center gap-2 rounded-[1.2rem] py-14 text-muted-foreground">
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
      <div className="glass-panel flex flex-col items-center gap-2 rounded-[1.2rem] py-14 text-muted-foreground">
        <AnimatedLucideIcon icon={Upload} mode="idlePulse" className="size-8" />
        <p>No locally registered models</p>
        <p className="text-xs">Use the validator below to register a model</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {entries.map((entry) => (
        <Card key={entry.id} size="sm" className="gap-3">
          <CardContent className="flex items-center justify-between gap-4 pt-4">
            <div className="min-w-0 flex-1 space-y-1">
              <span className="block truncate font-medium">{entry.name}</span>
              <span className="block truncate text-xs text-muted-foreground">{entry.path}</span>
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

export function GgufModelsPanel({ initialModelsTab, initialHereticModelId }: GgufModelsPanelProps) {
  const [hardware, setHardware] = useArrowState<GgufHardwareProfile | null>(null);
  const [catalog, setCatalog] = useArrowState<GgufCatalogEntry[]>([]);
  const [installed, setInstalled] = useArrowState<GgufInstalledEntry[]>([]);
  const [modelsTab, setModelsTab] = useArrowState<ModelsTabValue>(resolveModelsTab(initialModelsTab));
  const [selectedModelName, setSelectedModelName] = useArrowState<string | null>(null);
  const [useCase, setUseCase] = useArrowState("general");
  const [loading, setLoading] = useArrowState(true);
  const [error, setError] = useArrowState<string | null>(null);
  const [refreshing, setRefreshing] = useArrowState(false);

  const [validatePath, setValidatePath] = useArrowState("");
  const [validating, setValidating] = useArrowState(false);
  const [validateResult, setValidateResult] = useArrowState<GgufValidateResult | null>(null);
  const [validateError, setValidateError] = useArrowState<string | null>(null);

  const [registering, setRegistering] = useArrowState(false);
  const [registerSuccess, setRegisterSuccess] = useArrowState(false);
  const [unregistering, setUnregistering] = useArrowState<string | null>(null);

  const [hereticModelId, setHereticModelId] = useArrowState(initialHereticModelId ?? "");
  const [hereticBnb4Bit, setHereticBnb4Bit] = useArrowState(false);
  const [hereticOuttype, setHereticOuttype] = useArrowState("f16");
  const [hereticPreflight, setHereticPreflight] = useArrowState<HereticPreflightResponse | null>(null);
  const [hereticPreflightLoading, setHereticPreflightLoading] = useArrowState(false);
  const [hereticPreflightError, setHereticPreflightError] = useArrowState<string | null>(null);
  const [hereticRunning, setHereticRunning] = useArrowState(false);
  const [hereticLogs, setHereticLogs] = useArrowState<string[]>([]);
  const [hereticRunError, setHereticRunError] = useArrowState<string | null>(null);
  const [hereticGgufPath, setHereticGgufPath] = useArrowState<string | null>(null);
  const [hereticCopiedPath, setHereticCopiedPath] = useArrowState(false);
  const [hereticAbortController, setHereticAbortController] = useArrowState<AbortController | null>(null);

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
  }, [setCatalog, setError, setHardware, setInstalled, setLoading, useCase]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    return () => {
      hereticAbortController?.abort();
    };
  }, [hereticAbortController]);

  useEffect(() => {
    if (catalog.length === 0) {
      setSelectedModelName(null);
      return;
    }

    if (!catalog.some((entry) => entry.model_name === selectedModelName)) {
      setSelectedModelName(catalog[0]?.model_name ?? null);
    }
  }, [catalog, selectedModelName, setSelectedModelName]);

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

  async function loadHereticPreflight() {
    setHereticPreflightLoading(true);
    setHereticPreflightError(null);
    try {
      const result = await fetchHereticPreflight();
      setHereticPreflight(result);
    } catch (err) {
      setHereticPreflightError(err instanceof Error ? err.message : "Failed to load Heretic preflight");
    } finally {
      setHereticPreflightLoading(false);
    }
  }

  useEffect(() => {
    if (modelsTab !== "heretic") {
      return;
    }
    if (!hereticPreflight && !hereticPreflightLoading) {
      loadHereticPreflight();
    }
  }, [hereticPreflight, hereticPreflightLoading, modelsTab]);

  async function handleRunHeretic() {
    if (!hereticModelId.trim() || hereticRunning || !hereticPreflight?.ready) {
      return;
    }

    const controller = new AbortController();
    setHereticAbortController(controller);
    setHereticRunning(true);
    setHereticRunError(null);
    setHereticGgufPath(null);
    setHereticCopiedPath(false);
    setHereticLogs([]);

    try {
      await runHereticAbliterateStream(
        {
          model_id: hereticModelId.trim(),
          bnb_4bit: hereticBnb4Bit,
          outtype: hereticOuttype.trim() || "f16",
        },
        {
          signal: controller.signal,
          onEvent: (event) => {
            if (event.type === "complete") {
              if (event.gguf_path) {
                setHereticGgufPath(event.gguf_path);
              }
              setHereticLogs((prev) => [...prev, event.message || "Abliteration pipeline complete"].slice(-400));
              return;
            }

            if (event.type === "error") {
              setHereticRunError(event.message || "Heretic pipeline failed");
            }

            setHereticLogs((prev) => [...prev, event.message || event.type].slice(-400));
          },
        },
      );
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        setHereticLogs((prev) => [...prev, "Pipeline stopped by user"].slice(-400));
      } else {
        setHereticRunError(err instanceof Error ? err.message : "Heretic pipeline failed");
      }
    } finally {
      setHereticRunning(false);
      setHereticAbortController(null);
    }
  }

  function handleStopHeretic() {
    hereticAbortController?.abort();
  }

  async function handleCopyGgufPath() {
    if (!hereticGgufPath || typeof navigator === "undefined" || !navigator.clipboard) {
      return;
    }
    try {
      await navigator.clipboard.writeText(hereticGgufPath);
      setHereticCopiedPath(true);
      window.setTimeout(() => setHereticCopiedPath(false), 1500);
    } catch {
      setHereticCopiedPath(false);
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
      setInstalled(installed.filter((entry) => entry.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to unregister");
    } finally {
      setUnregistering(null);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">Local GGUF models</h2>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Browse the catalogue, check hardware compatibility, validate, and register local models.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <div className="glass-panel flex items-center gap-2 rounded-full px-3 py-1.5 text-sm">
            <span className="text-muted-foreground">Use case</span>
            <select
              value={useCase}
              onChange={(event) => setUseCase(event.target.value)}
              className="bg-transparent text-foreground outline-none"
            >
              {USE_CASES.map((useCaseOption) => (
                <option
                  key={useCaseOption.value}
                  value={useCaseOption.value}
                  className="bg-background text-foreground"
                >
                  {useCaseOption.label}
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
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <OverviewPill
          label="Hardware"
          value={hardware ? `${hardware.total_cpu_cores} cores` : "-"}
          note="Detected compute profile."
        />
        <OverviewPill
          label="Memory"
          value={hardware ? `${hardware.available_ram_gb.toFixed(1)} GB free` : "-"}
          note="Headroom for local inference."
        />
      </div>

      {error && (
        <div className="flex items-center gap-2 rounded-[1.1rem] border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          <AnimatedLucideIcon icon={AlertCircle} mode="idlePulse" className="size-4" />
          {error}
        </div>
      )}

      {loading ? (
        <div className="glass-panel flex items-center gap-2 rounded-[1.2rem] px-4 py-4 text-muted-foreground">
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
                <Tabs value={modelsTab} onValueChange={(value) => setModelsTab(resolveModelsTab(value))} className="space-y-5">
                  <TabsList className="glass-tab-rail grid w-full grid-cols-4">
                    <TabsTrigger value="catalog">Catalogue ({catalog.length})</TabsTrigger>
                    <TabsTrigger value="installed">Installed ({installed.length})</TabsTrigger>
                    <TabsTrigger value="validate">Validate</TabsTrigger>
                    <TabsTrigger value="heretic">Heretic</TabsTrigger>
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
                    <Card className="glass-panel">
                      <CardHeader className="pb-2">
                        <CardTitle className="flex items-center gap-2 text-base">
                          <AnimatedLucideIcon icon={FileCheck} mode="hoverLift" className="size-4" />
                          Validate Model
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        <div className="flex flex-col gap-2 md:flex-row">
                          <Input
                            placeholder="Path to GGUF file (e.g., C:\models\model.gguf)"
                            value={validatePath}
                            onChange={(event) => setValidatePath(event.target.value)}
                            onKeyDown={(event) => event.key === "Enter" && handleValidate()}
                            className="flex-1"
                          />
                          <Button
                            onClick={handleValidate}
                            disabled={validating || !validatePath.trim()}
                            className="gap-1.5"
                          >
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
                                <span className="text-muted-foreground">Size:</span>{" "}
                                {(validateResult.file_size_bytes / 1024 / 1024 / 1024).toFixed(2)} GB
                              </div>
                            </div>
                            <Button onClick={handleRegister} disabled={registering} className="mt-4 gap-1.5" size="sm">
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

                  <TabsContent value="heretic" className="mt-0 space-y-4">
                    <Card className="glass-panel">
                      <CardHeader className="pb-2">
                        <CardTitle className="flex items-center gap-2 text-base">
                          <AnimatedLucideIcon icon={Scissors} mode="hoverLift" className="size-4" />
                          Heretic Abliteration
                        </CardTitle>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        <div className="rounded-[1rem] border border-white/10 bg-white/5 px-3 py-3 text-sm">
                          <div className="flex flex-wrap items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <span className="text-muted-foreground">Preflight</span>
                              <Badge variant={hereticPreflight?.ready ? "default" : "secondary"}>
                                {hereticPreflight?.ready ? "Ready" : "Not ready"}
                              </Badge>
                            </div>
                            <Button
                              type="button"
                              variant="outline"
                              size="sm"
                              onClick={loadHereticPreflight}
                              disabled={hereticPreflightLoading}
                              className="gap-1.5"
                            >
                              {hereticPreflightLoading ? (
                                <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4" />
                              ) : (
                                <AnimatedLucideIcon icon={RefreshCw} mode="hoverLift" className="size-4" />
                              )}
                              Refresh
                            </Button>
                          </div>
                          {hereticPreflight?.convert_script && (
                            <p className="mt-2 break-all text-xs text-muted-foreground">
                              convert_hf_to_gguf.py: {hereticPreflight.convert_script}
                            </p>
                          )}
                          {hereticPreflightError && (
                            <p className="mt-2 text-xs text-destructive">{hereticPreflightError}</p>
                          )}
                          {hereticPreflight && hereticPreflight.errors.length > 0 && (
                            <div className="mt-2 space-y-1">
                              {hereticPreflight.errors.map((entry) => (
                                <p key={entry} className="text-xs text-amber-300">
                                  {entry}
                                </p>
                              ))}
                            </div>
                          )}
                        </div>

                        <div className="grid gap-3 md:grid-cols-2">
                          <div className="space-y-2 md:col-span-2">
                            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Model ID</p>
                            <Input
                              placeholder="meta-llama/Llama-3.1-8B-Instruct"
                              value={hereticModelId}
                              onChange={(event) => setHereticModelId(event.target.value)}
                            />
                          </div>
                          <div className="space-y-2">
                            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Outtype</p>
                            <Input
                              placeholder="f16"
                              value={hereticOuttype}
                              onChange={(event) => setHereticOuttype(event.target.value)}
                            />
                          </div>
                          <label className="flex items-center gap-2 pt-7 text-sm text-muted-foreground">
                            <input
                              type="checkbox"
                              checked={hereticBnb4Bit}
                              onChange={(event) => setHereticBnb4Bit(event.target.checked)}
                              className="accent-primary"
                            />
                            Enable bnb_4bit
                          </label>
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          <Button
                            type="button"
                            onClick={handleRunHeretic}
                            disabled={
                              hereticRunning ||
                              !hereticModelId.trim() ||
                              !hereticPreflight?.ready
                            }
                            className="gap-1.5"
                          >
                            {hereticRunning && <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4" />}
                            Start pipeline
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            onClick={handleStopHeretic}
                            disabled={!hereticRunning}
                            className="gap-1.5"
                          >
                            <AnimatedLucideIcon icon={Square} mode="hoverLift" className="size-4" />
                            Stop
                          </Button>
                        </div>

                        {hereticRunError && (
                          <div className="flex items-center gap-2 rounded-[1rem] border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                            <AnimatedLucideIcon icon={AlertCircle} mode="idlePulse" className="size-4" />
                            {hereticRunError}
                          </div>
                        )}

                        {hereticGgufPath && (
                          <div className="rounded-[1rem] border border-green-500/30 bg-green-500/10 px-3 py-3 text-sm">
                            <div className="mb-2 flex items-center gap-2 text-green-600">
                              <AnimatedLucideIcon icon={CheckCircle2} mode="idlePulse" className="size-4" />
                              GGUF ready
                            </div>
                            <div className="flex flex-col gap-2 md:flex-row">
                              <Input value={hereticGgufPath} readOnly className="font-mono text-xs" />
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={handleCopyGgufPath}
                                className="gap-1.5"
                              >
                                <AnimatedLucideIcon icon={Copy} mode="hoverLift" className="size-4" />
                                {hereticCopiedPath ? "Copied" : "Copy"}
                              </Button>
                            </div>
                          </div>
                        )}

                        <div className="rounded-[1rem] border border-white/10 bg-black/35 p-3">
                          <p className="mb-2 text-xs uppercase tracking-[0.14em] text-muted-foreground">Live log</p>
                          <div className="max-h-56 overflow-auto font-mono text-xs leading-5 text-slate-200">
                            {hereticLogs.length === 0 ? (
                              <p className="text-muted-foreground">No events yet</p>
                            ) : (
                              hereticLogs.map((entry, index) => (
                                <p key={`${entry}-${index}`}>{entry}</p>
                              ))
                            )}
                          </div>
                        </div>
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
          </aside>
        </div>
      )}
    </div>
  );
}