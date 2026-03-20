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
          <Cpu className="size-4" />
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
            <HardDrive className="size-4 text-muted-foreground" />
            <span className="min-w-0 truncate">{hardware.gpu_name}</span>
            {hardware.gpu_vram_gb && <span>({hardware.gpu_vram_gb} GB VRAM)</span>}
          </div>
        )}
        {!hardware.detected && (
          <div className="flex items-center gap-1 rounded-[1rem] border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-600">
            <AlertCircle className="size-3" />
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

function CatalogList({ entries }: { entries: GgufCatalogEntry[] }) {
  if (entries.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 rounded-[1.2rem] border border-white/8 bg-black/10 py-14 text-muted-foreground">
        <HardDrive className="size-8" />
        <p>No models in catalog</p>
      </div>
    );
  }

  return (
    <div className="grid gap-3 xl:grid-cols-2">
      {entries.map((entry) => (
        <Card
          key={entry.model_name}
          size="sm"
          className="gap-3"
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
          <CardContent className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
            <div className="flex flex-wrap gap-2">
              <span>{entry.estimated_tps.toFixed(1)} tok/s</span>
              <span>~{entry.memory_required_gb.toFixed(1)} GB</span>
            </div>
            <div className="flex items-center gap-2">
              <FitBadge level={entry.fit_level} />
              <Badge variant="outline">{entry.run_mode}</Badge>
            </div>
          </CardContent>
        </Card>
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
        <Upload className="size-8" />
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
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Trash2 className="size-4" />
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
      description="Browse the catalog, check hardware compatibility, validate, and register local models for fully offline inference."
      heroAside={
        <div className="space-y-3">
          <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
            Local inference posture
          </p>
          <p className="text-sm leading-7 text-muted-foreground">
            Browse advisory hardware fit, validate a GGUF file before registering it, and keep a local model catalog close to the rest of the workspace.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <OverviewPill
              label="Catalog"
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
        <section className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(18rem,0.8fr)] xl:items-end">
          <div className="glass-panel rounded-[1.6rem] px-5 py-5 sm:px-6">
            <p className="text-xs font-medium uppercase tracking-[0.22em] text-primary/80">
              Models
            </p>
            <div className="mt-3 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
              <div className="space-y-2">
                <h1 className="text-balance text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
                  Manage local GGUF models
                </h1>
                <p className="max-w-2xl text-pretty text-sm leading-6 text-muted-foreground">
                  Browse the catalog, check hardware compatibility, validate, and register local models for fully offline inference.
                </p>
              </div>
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
                  {refreshing ? <Loader2 className="size-4 animate-spin" /> : <RefreshCw className="size-4" />}
                  Refresh
                </Button>
              </div>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
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
          </div>
        </section>

        {error && (
          <div className="flex items-center gap-2 rounded-[1.1rem] border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <AlertCircle className="size-4" />
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center gap-2 rounded-[1.2rem] border border-white/8 bg-black/10 px-4 py-4 text-muted-foreground">
            <Loader2 className="size-6 animate-spin" />
            Loading models...
          </div>
        ) : (
          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.12fr)_minmax(20rem,0.88fr)]">
            <div className="space-y-6">
              <Card>
                <CardHeader className="pb-3">
                  <CardTitle>Model catalog and installed files</CardTitle>
                </CardHeader>
                <CardContent>
                  <Tabs defaultValue="catalog" className="space-y-5">
                    <TabsList className="grid w-full grid-cols-3">
                      <TabsTrigger value="catalog">Catalog ({catalog.length})</TabsTrigger>
                      <TabsTrigger value="installed">Installed ({installed.length})</TabsTrigger>
                      <TabsTrigger value="validate">Validate</TabsTrigger>
                    </TabsList>

                    <TabsContent value="catalog" className="mt-0">
                      <CatalogList entries={catalog} />
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
                            <FileCheck className="size-4" />
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
                              {validating && <Loader2 className="size-4 animate-spin" />}
                              Validate
                            </Button>
                          </div>

                          {validateError && (
                            <div className="flex items-center gap-2 rounded-[1rem] border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                              <AlertCircle className="size-4" />
                              {validateError}
                            </div>
                          )}

                          {validateResult && (
                            <div className="rounded-[1.2rem] border border-green-500/30 bg-green-500/10 p-4">
                              <div className="mb-3 flex items-center gap-2 text-green-600">
                                <CheckCircle2 className="size-4" />
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
                                {registering && <Loader2 className="size-4 animate-spin" />}
                                Register Model
                              </Button>
                            </div>
                          )}

                          {registerSuccess && (
                            <div className="flex items-center gap-2 rounded-[1rem] border border-green-500/30 bg-green-500/10 px-3 py-2 text-sm text-green-600">
                              <CheckCircle2 className="size-4" />
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
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-base">Why this layout</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 text-sm leading-6 text-muted-foreground">
                  <p>
                    The left side keeps the interactive workbench wide enough for model browsing and validation.
                  </p>
                  <p>
                    The right side stays sticky so hardware fit is always visible while you compare catalog entries or register a local file.
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
