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
import { Separator } from "@/components/ui/separator";
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
  MemoryStick,
} from "lucide-react";

const USE_CASES = [
  { value: "general", label: "General" },
  { value: "chat", label: "Chat" },
  { value: "coding", label: "Coding" },
  { value: "reasoning", label: "Reasoning" },
];

function HardwareCard({ hardware }: { hardware: GgufHardwareProfile }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base">
          <Cpu className="size-4" />
          Hardware Profile
        </CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <div className="flex items-center gap-2">
          <MemoryStick className="size-4 text-muted-foreground" />
          <span className="text-muted-foreground">RAM:</span>
          <span>{hardware.total_ram_gb.toFixed(1)} GB</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">Available:</span>
          <span>{hardware.available_ram_gb.toFixed(1)} GB</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">CPU:</span>
          <span>{hardware.total_cpu_cores} cores</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">Backend:</span>
          <Badge variant="secondary">{hardware.backend}</Badge>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-muted-foreground">GPU:</span>
          <span>{hardware.has_gpu ? "Yes" : "No"}</span>
        </div>
        {hardware.has_gpu && hardware.gpu_name && (
          <div className="flex items-center gap-2 col-span-2">
            <HardDrive className="size-4 text-muted-foreground" />
            <span>{hardware.gpu_name}</span>
            {hardware.gpu_vram_gb && <span>({hardware.gpu_vram_gb} GB VRAM)</span>}
          </div>
        )}
        {!hardware.detected && (
          <div className="col-span-2 flex items-center gap-1 text-xs text-amber-600">
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
      <div className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
        <HardDrive className="size-8" />
        <p>No models in catalog</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {entries.map((entry) => (
        <div
          key={entry.model_name}
          className="flex items-center justify-between rounded-lg border p-3"
        >
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-2">
              <span className="font-medium">{entry.model_name}</span>
              <Badge variant="outline">{entry.parameter_count}</Badge>
              <Badge variant="outline">{entry.architecture}</Badge>
            </div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{entry.provider}</span>
              <span>•</span>
              <span>{entry.best_quant}</span>
              <span>•</span>
              <span>{entry.estimated_tps.toFixed(1)} tok/s</span>
              <span>•</span>
              <span>~{entry.memory_required_gb.toFixed(1)} GB</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <FitBadge level={entry.fit_level} />
            <Badge variant="outline">{entry.run_mode}</Badge>
          </div>
        </div>
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
      <div className="flex flex-col items-center gap-2 py-12 text-muted-foreground">
        <Upload className="size-8" />
        <p>No locally registered models</p>
        <p className="text-xs">Use the validator below to register a model</p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {entries.map((entry) => (
        <div
          key={entry.id}
          className="flex items-center justify-between rounded-lg border p-3"
        >
          <div className="flex flex-col gap-1 min-w-0">
            <span className="font-medium truncate">{entry.name}</span>
            <span className="text-xs text-muted-foreground truncate">{entry.path}</span>
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
        </div>
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
      actions={
        <>
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
        </>
      }
      heroAside={
        <div className="space-y-2">
          <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
            Local inference posture
          </p>
          <p className="text-sm leading-7 text-muted-foreground">
            Browse advisory hardware fit, validate a GGUF file before registering it, and keep a local model catalog close to the rest of the workspace.
          </p>
        </div>
      }
    >
      <div className="mx-auto max-w-4xl space-y-6">
        <div>
          <h1 className="text-lg font-semibold">GGUF Model Management</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Browse the model catalog, manage locally installed GGUF files, and validate new models.
          </p>
        </div>

        {error && (
          <div className="flex items-center gap-2 rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <AlertCircle className="size-4" />
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex items-center gap-2 py-12 text-muted-foreground">
            <Loader2 className="size-6 animate-spin" />
            Loading...
          </div>
        ) : (
          <>
            {/* Hardware Profile */}
            {hardware && <HardwareCard hardware={hardware} />}

            <Separator />

            {/* Tabs */}
            <Tabs defaultValue="catalog" className="space-y-4">
              <TabsList>
                <TabsTrigger value="catalog">Catalog ({catalog.length})</TabsTrigger>
                <TabsTrigger value="installed">Installed ({installed.length})</TabsTrigger>
                <TabsTrigger value="validate">Validate</TabsTrigger>
              </TabsList>

              <TabsContent value="catalog">
                <CatalogList entries={catalog} />
              </TabsContent>

              <TabsContent value="installed">
                <InstalledList
                  entries={installed}
                  onUnregister={handleUnregister}
                  unregistering={unregistering}
                />
              </TabsContent>

              <TabsContent value="validate" className="space-y-4">
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <FileCheck className="size-4" />
                      Validate Model
                    </CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="flex gap-2">
                      <Input
                        placeholder="Path to GGUF file (e.g., C:\models\model.gguf)"
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
                      <div className="flex items-center gap-2 text-sm text-destructive">
                        <AlertCircle className="size-4" />
                        {validateError}
                      </div>
                    )}

                    {validateResult && (
                      <div className="rounded-lg border border-green-500/50 bg-green-500/10 p-4">
                        <div className="flex items-center gap-2 text-green-600 mb-2">
                          <CheckCircle2 className="size-4" />
                          <span className="font-medium">Valid GGUF Model</span>
                        </div>
                        <div className="grid grid-cols-2 gap-2 text-sm">
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
                          className="mt-3 gap-1.5"
                          size="sm"
                        >
                          {registering && <Loader2 className="size-4 animate-spin" />}
                          Register Model
                        </Button>
                      </div>
                    )}

                    {registerSuccess && (
                      <div className="flex items-center gap-2 text-sm text-green-600">
                        <CheckCircle2 className="size-4" />
                        Model registered successfully
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </>
        )}
      </div>
    </PageChrome>
  );
}
