"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { fetchSettings, updateSettings } from "@/lib/api";
import { AlertCircle, CheckCircle2, ChevronRight, Info, Loader2, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";

const schema = z.object({
  // Retrieval
  chunk_size: z.number().int().min(100, "Min 100").max(10000, "Max 10000"),
  chunk_overlap: z.number().int().min(0, "Min 0").max(500, "Max 500"),
  retrieval_k: z.number().int().min(1, "Min 1").max(200, "Max 200"),
  top_k: z.number().int().min(1, "Min 1").max(50, "Max 50"),
  retrieval_mode: z.string().min(1),
  search_type: z.string().min(1),
  mmr_lambda: z.number().min(0).max(1),
  // Chat / RAG
  chat_history_max_turns: z.number().int().min(1, "Min 1").max(50, "Max 50"),
  output_style: z.string().min(1),
  chat_path: z.enum(["RAG", "Direct"]),
  show_retrieved_context: z.boolean(),
  // Feature toggles
  use_reranker: z.boolean(),
  use_sub_queries: z.boolean(),
  agentic_mode: z.boolean(),
  enable_summarizer: z.boolean(),
  verbose_mode: z.boolean(),
  // LLM fine-tuning
  llm_temperature: z.number().min(0).max(2),
  llm_max_tokens: z.number().int().min(64, "Min 64").max(32768, "Max 32768"),
});

type FormValues = z.infer<typeof schema>;

const RETRIEVAL_MODES = ["flat", "mmr", "hybrid"];
const SEARCH_TYPES = ["similarity", "mmr"];
const OUTPUT_STYLES = ["Default answer", "Concise", "Detailed", "Bullet points"];

function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return <p className="mt-0.5 text-xs text-destructive">{message}</p>;
}

function FieldLabel({ htmlFor, children }: { htmlFor: string; children: React.ReactNode }) {
  return (
    <label htmlFor={htmlFor} className="text-sm font-medium">
      {children}
    </label>
  );
}

function ToggleRow({
  id,
  label,
  description,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  description?: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label
      htmlFor={id}
      className="flex cursor-pointer items-start gap-3 rounded-lg border px-4 py-3 transition-colors hover:bg-muted/30"
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 size-4 rounded accent-primary"
      />
      <div>
        <p className="text-sm font-medium">{label}</p>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>
    </label>
  );
}

export default function SettingsPage() {
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      chunk_size: 1000,
      chunk_overlap: 100,
      retrieval_k: 25,
      top_k: 5,
      retrieval_mode: "flat",
      search_type: "similarity",
      mmr_lambda: 0.5,
      chat_history_max_turns: 6,
      output_style: "Default answer",
      chat_path: "RAG",
      show_retrieved_context: false,
      use_reranker: true,
      use_sub_queries: true,
      agentic_mode: false,
      enable_summarizer: true,
      verbose_mode: false,
      llm_temperature: 0.0,
      llm_max_tokens: 1024,
    },
  });

  const { register, handleSubmit, reset, watch, setValue, formState: { errors } } = form;

  useEffect(() => {
    fetchSettings()
      .then((raw) => {
        reset({
          chunk_size: (raw.chunk_size as number) ?? 1000,
          chunk_overlap: (raw.chunk_overlap as number) ?? 100,
          retrieval_k: (raw.retrieval_k as number) ?? 25,
          top_k: (raw.top_k as number) ?? 5,
          retrieval_mode: (raw.retrieval_mode as string) ?? "flat",
          search_type: (raw.search_type as string) ?? "similarity",
          mmr_lambda: (raw.mmr_lambda as number) ?? 0.5,
          chat_history_max_turns: (raw.chat_history_max_turns as number) ?? 6,
          output_style: (raw.output_style as string) ?? "Default answer",
          chat_path: ((raw.chat_path as string) === "Direct" ? "Direct" : "RAG"),
          show_retrieved_context: (raw.show_retrieved_context as boolean) ?? false,
          use_reranker: (raw.use_reranker as boolean) ?? true,
          use_sub_queries: (raw.use_sub_queries as boolean) ?? true,
          agentic_mode: (raw.agentic_mode as boolean) ?? false,
          enable_summarizer: (raw.enable_summarizer as boolean) ?? true,
          verbose_mode: (raw.verbose_mode as boolean) ?? false,
          llm_temperature: (raw.llm_temperature as number) ?? 0.0,
          llm_max_tokens: (raw.llm_max_tokens as number) ?? 1024,
        });
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Failed to load settings"))
      .finally(() => setLoading(false));
  }, [reset]);

  async function onSubmit(values: FormValues) {
    setSaving(true);
    setSaveError(null);
    setSaved(false);
    try {
      await updateSettings(values as Record<string, unknown>);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  const mmrLambda = watch("mmr_lambda");
  const llmTemp = watch("llm_temperature");

  return (
    <div className="min-h-screen bg-background">
      {/* Nav */}
      <header className="flex h-12 items-center gap-4 border-b px-6">
        <Link href="/" className="text-sm font-semibold tracking-tight">
          Axiom
        </Link>
        <ChevronRight className="size-3.5 text-muted-foreground" />
        <span className="text-sm text-muted-foreground">Settings</span>
        <div className="ml-auto flex items-center gap-4">
          <Link href="/library" className="text-sm text-muted-foreground hover:text-foreground">
            Library
          </Link>
          <Link href="/chat" className="text-sm text-muted-foreground hover:text-foreground">
            Chat →
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-2xl space-y-8 px-4 py-8">
        <div>
          <h1 className="text-lg font-semibold">Settings</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Configure retrieval, chat, and feature options.
          </p>
        </div>

        {/* Guardrail: API keys not editable */}
        <div className="flex gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-400">
          <TriangleAlert className="mt-0.5 size-4 shrink-0" />
          <div>
            <p className="font-medium">API keys are not editable here</p>
            <p className="mt-0.5">
              The backend blocks <code className="rounded bg-amber-100 px-1 dark:bg-amber-900/50">api_key_*</code> updates
              via this UI to prevent accidental exposure. To set API keys, edit{" "}
              <code className="rounded bg-amber-100 px-1 dark:bg-amber-900/50">settings.json</code> at the repo root directly.
            </p>
          </div>
        </div>

        {/* Advanced settings hint */}
        <div className="flex gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800 dark:border-blue-800 dark:bg-blue-950/30 dark:text-blue-400">
          <Info className="mt-0.5 size-4 shrink-0" />
          <div>
            <p className="font-medium">Advanced settings</p>
            <p className="mt-0.5">
              For provider/model selection, local LLM config, embeddings, and vector DB settings,
              edit <code className="rounded bg-blue-100 px-1 dark:bg-blue-900/50">settings.json</code> at
              the repo root directly. Changes made there take effect on next server restart.
            </p>
          </div>
        </div>

        {loadError && (
          <div className="flex items-center gap-1.5 text-sm text-destructive">
            <AlertCircle className="size-4" />
            {loadError}
          </div>
        )}

        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Loading settings…
          </div>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-8">
            {/* Section 1 — Retrieval */}
            <section className="space-y-4">
              <h2 className="text-base font-semibold">Retrieval</h2>
              <Separator />

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <FieldLabel htmlFor="chunk_size">Chunk size</FieldLabel>
                  <Input
                    id="chunk_size"
                    type="number"
                    min={100}
                    max={10000}
                    {...register("chunk_size", { valueAsNumber: true })}
                  />
                  <FieldError message={errors.chunk_size?.message} />
                </div>

                <div className="space-y-1.5">
                  <FieldLabel htmlFor="chunk_overlap">Chunk overlap</FieldLabel>
                  <Input
                    id="chunk_overlap"
                    type="number"
                    min={0}
                    max={500}
                    {...register("chunk_overlap", { valueAsNumber: true })}
                  />
                  <FieldError message={errors.chunk_overlap?.message} />
                </div>

                <div className="space-y-1.5">
                  <FieldLabel htmlFor="retrieval_k">
                    Retrieval k{" "}
                    <span className="font-normal text-muted-foreground">(candidates)</span>
                  </FieldLabel>
                  <Input
                    id="retrieval_k"
                    type="number"
                    min={1}
                    max={200}
                    {...register("retrieval_k", { valueAsNumber: true })}
                  />
                  <FieldError message={errors.retrieval_k?.message} />
                </div>

                <div className="space-y-1.5">
                  <FieldLabel htmlFor="top_k">
                    Top k{" "}
                    <span className="font-normal text-muted-foreground">(returned)</span>
                  </FieldLabel>
                  <Input
                    id="top_k"
                    type="number"
                    min={1}
                    max={50}
                    {...register("top_k", { valueAsNumber: true })}
                  />
                  <FieldError message={errors.top_k?.message} />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <FieldLabel htmlFor="retrieval_mode">Retrieval mode</FieldLabel>
                  <select
                    id="retrieval_mode"
                    {...register("retrieval_mode")}
                    className="h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus:outline-none focus:ring-1 focus:ring-ring"
                  >
                    {RETRIEVAL_MODES.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </div>

                <div className="space-y-1.5">
                  <FieldLabel htmlFor="search_type">Search type</FieldLabel>
                  <select
                    id="search_type"
                    {...register("search_type")}
                    className="h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus:outline-none focus:ring-1 focus:ring-ring"
                  >
                    {SEARCH_TYPES.map((t) => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="space-y-1.5">
                <FieldLabel htmlFor="mmr_lambda">
                  MMR lambda{" "}
                  <span className="font-normal text-muted-foreground">
                    (diversity ↔ relevance) — {Number(mmrLambda).toFixed(2)}
                  </span>
                </FieldLabel>
                <input
                  id="mmr_lambda"
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  {...register("mmr_lambda", { valueAsNumber: true })}
                  className="w-full accent-primary"
                />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>0 — max diversity</span>
                  <span>1 — max relevance</span>
                </div>
              </div>
            </section>

            {/* Section 2 — Chat / RAG */}
            <section className="space-y-4">
              <h2 className="text-base font-semibold">Chat / RAG</h2>
              <Separator />

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <FieldLabel htmlFor="chat_history_max_turns">History turns</FieldLabel>
                  <Input
                    id="chat_history_max_turns"
                    type="number"
                    min={1}
                    max={50}
                    {...register("chat_history_max_turns", { valueAsNumber: true })}
                  />
                  <FieldError message={errors.chat_history_max_turns?.message} />
                </div>

                <div className="space-y-1.5">
                  <FieldLabel htmlFor="output_style">Output style</FieldLabel>
                  <select
                    id="output_style"
                    {...register("output_style")}
                    className="h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus:outline-none focus:ring-1 focus:ring-ring"
                  >
                    {OUTPUT_STYLES.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="space-y-1.5">
                <FieldLabel htmlFor="chat_path_rag">Query path</FieldLabel>
                <div className="flex gap-4">
                  {(["RAG", "Direct"] as const).map((path) => (
                    <label key={path} htmlFor={`chat_path_${path}`} className="flex cursor-pointer items-center gap-2 text-sm">
                      <input
                        id={`chat_path_${path}`}
                        type="radio"
                        value={path}
                        {...register("chat_path")}
                        className="accent-primary"
                      />
                      {path === "RAG" ? "RAG (document-grounded)" : "Direct (LLM only)"}
                    </label>
                  ))}
                </div>
              </div>

              <ToggleRow
                id="show_retrieved_context"
                label="Show retrieved context"
                description="Display the retrieved document chunks alongside answers in chat."
                checked={watch("show_retrieved_context")}
                onChange={(v) => setValue("show_retrieved_context", v)}
              />
            </section>

            {/* Section 3 — Feature Toggles */}
            <section className="space-y-4">
              <h2 className="text-base font-semibold">Feature toggles</h2>
              <Separator />
              <div className="space-y-2">
                <ToggleRow
                  id="use_reranker"
                  label="Use reranker"
                  description="Re-rank retrieved chunks for better relevance before generating answers."
                  checked={watch("use_reranker")}
                  onChange={(v) => setValue("use_reranker", v)}
                />
                <ToggleRow
                  id="use_sub_queries"
                  label="Use sub-queries"
                  description="Decompose complex questions into sub-queries for broader coverage."
                  checked={watch("use_sub_queries")}
                  onChange={(v) => setValue("use_sub_queries", v)}
                />
                <ToggleRow
                  id="enable_summarizer"
                  label="Enable summarizer"
                  description="Summarize long context windows before passing to the LLM."
                  checked={watch("enable_summarizer")}
                  onChange={(v) => setValue("enable_summarizer", v)}
                />
                <ToggleRow
                  id="agentic_mode"
                  label="Agentic mode"
                  description="Allow the system to iterate and self-correct using tool use loops."
                  checked={watch("agentic_mode")}
                  onChange={(v) => setValue("agentic_mode", v)}
                />
                <ToggleRow
                  id="verbose_mode"
                  label="Verbose mode"
                  description="Log additional diagnostic information to the server console."
                  checked={watch("verbose_mode")}
                  onChange={(v) => setValue("verbose_mode", v)}
                />
              </div>
            </section>

            {/* Section 4 — LLM Fine-tuning */}
            <section className="space-y-4">
              <h2 className="text-base font-semibold">LLM fine-tuning</h2>
              <Separator />

              <div className="space-y-1.5">
                <FieldLabel htmlFor="llm_temperature">
                  Temperature{" "}
                  <span className="font-normal text-muted-foreground">
                    — {Number(llmTemp).toFixed(1)}
                  </span>
                </FieldLabel>
                <input
                  id="llm_temperature"
                  type="range"
                  min={0}
                  max={2}
                  step={0.1}
                  {...register("llm_temperature", { valueAsNumber: true })}
                  className="w-full accent-primary"
                />
                <div className="flex justify-between text-xs text-muted-foreground">
                  <span>0 — deterministic</span>
                  <span>2 — creative</span>
                </div>
                <FieldError message={errors.llm_temperature?.message} />
              </div>

              <div className="space-y-1.5">
                <FieldLabel htmlFor="llm_max_tokens">Max tokens</FieldLabel>
                <Input
                  id="llm_max_tokens"
                  type="number"
                  min={64}
                  max={32768}
                  {...register("llm_max_tokens", { valueAsNumber: true })}
                  className="max-w-[200px]"
                />
                <FieldError message={errors.llm_max_tokens?.message} />
              </div>
            </section>

            {/* Save controls */}
            <div className="flex items-center gap-3 pb-8">
              <Button type="submit" disabled={saving} className="gap-1.5">
                {saving && <Loader2 className="size-4 animate-spin" />}
                {saving ? "Saving…" : "Save settings"}
              </Button>

              {saved && (
                <span className={cn("flex items-center gap-1.5 text-sm text-green-600 dark:text-green-400")}>
                  <CheckCircle2 className="size-4" />
                  Saved
                </span>
              )}

              {saveError && (
                <span className="flex items-center gap-1.5 text-sm text-destructive">
                  <AlertCircle className="size-4" />
                  {saveError}
                </span>
              )}
            </div>
          </form>
        )}
      </main>
    </div>
  );
}
