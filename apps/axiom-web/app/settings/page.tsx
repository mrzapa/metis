"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { fetchSettings, updateSettings } from "@/lib/api";
import { AlertCircle, CheckCircle2, ChevronRight, Info, Loader2, TriangleAlert } from "lucide-react";
import { cn } from "@/lib/utils";

const schema = z.object({
  // ── Core ──────────────────────────────────────────────────────────────────
  llm_provider: z.string().min(1),
  llm_model: z.string().min(1),
  chat_path: z.enum(["RAG", "Direct"]),
  selected_mode: z.string().min(1),
  output_style: z.string().min(1),
  chat_history_max_turns: z.number().int().min(1, "Min 1").max(50, "Max 50"),
  show_retrieved_context: z.boolean(),
  verbose_mode: z.boolean(),
  // ── Advanced Retrieval ────────────────────────────────────────────────────
  chunk_size: z.number().int().min(100, "Min 100").max(10000, "Max 10000"),
  chunk_overlap: z.number().int().min(0, "Min 0").max(500, "Max 500"),
  retrieval_k: z.number().int().min(1, "Min 1").max(200, "Max 200"),
  top_k: z.number().int().min(1, "Min 1").max(50, "Max 50"),
  retrieval_mode: z.string().min(1),
  search_type: z.string().min(1),
  mmr_lambda: z.number().min(0).max(1),
  use_reranker: z.boolean(),
  use_sub_queries: z.boolean(),
  enable_summarizer: z.boolean(),
  agentic_mode: z.boolean(),
  agentic_max_iterations: z.number().int().min(1, "Min 1").max(10, "Max 10"),
  subquery_max_docs: z.number().int().min(1, "Min 1").max(500, "Max 500"),
  document_loader: z.string().min(1),
  structure_aware_ingestion: z.boolean(),
  semantic_layout_ingestion: z.boolean(),
  deepread_mode: z.boolean(),
  build_digest_index: z.boolean(),
  build_comprehension_index: z.boolean(),
  comprehension_extraction_depth: z.string().min(1),
  prefer_comprehension_index: z.boolean(),
  // ── Advanced Graph ────────────────────────────────────────────────────────
  kg_query_mode: z.string().min(1),
  enable_langextract: z.boolean(),
  enable_structured_extraction: z.boolean(),
  enable_recursive_retrieval: z.boolean(),
  // ── Advanced Memory ───────────────────────────────────────────────────────
  enable_recursive_memory: z.boolean(),
  enable_citation_v2: z.boolean(),
  enable_claim_level_grounding_citefix_lite: z.boolean(),
  system_instructions: z.string(),
  // ── Advanced Model / Provider ─────────────────────────────────────────────
  llm_temperature: z.number().min(0).max(2),
  llm_max_tokens: z.number().int().min(64, "Min 64").max(32768, "Max 32768"),
  embedding_provider: z.string().min(1),
  embedding_model: z.string().min(1),
  local_llm_url: z.string(),
  agent_lightning_enabled: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

const RETRIEVAL_MODES = ["flat", "mmr", "hybrid"];
const SEARCH_TYPES = ["similarity", "mmr"];
const OUTPUT_STYLES = ["Default answer", "Concise", "Detailed", "Bullet points"];
const SKILL_MODES = ["Q&A", "Summary", "Tutor", "Research", "Evidence Pack"];
const KG_QUERY_MODES = ["hybrid", "vector", "keyword"];
const COMPREHENSION_DEPTHS = ["Standard", "Deep", "Exhaustive"];

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
      // Core
      llm_provider: "anthropic",
      llm_model: "claude-opus-4-6",
      chat_path: "RAG",
      selected_mode: "Q&A",
      output_style: "Default answer",
      chat_history_max_turns: 6,
      show_retrieved_context: false,
      verbose_mode: false,
      // Advanced Retrieval
      chunk_size: 1000,
      chunk_overlap: 100,
      retrieval_k: 25,
      top_k: 5,
      retrieval_mode: "flat",
      search_type: "similarity",
      mmr_lambda: 0.5,
      use_reranker: true,
      use_sub_queries: true,
      enable_summarizer: true,
      agentic_mode: false,
      agentic_max_iterations: 2,
      subquery_max_docs: 200,
      document_loader: "auto",
      structure_aware_ingestion: false,
      semantic_layout_ingestion: false,
      deepread_mode: false,
      build_digest_index: true,
      build_comprehension_index: false,
      comprehension_extraction_depth: "Standard",
      prefer_comprehension_index: true,
      // Advanced Graph
      kg_query_mode: "hybrid",
      enable_langextract: false,
      enable_structured_extraction: false,
      enable_recursive_retrieval: false,
      // Advanced Memory
      enable_recursive_memory: false,
      enable_citation_v2: true,
      enable_claim_level_grounding_citefix_lite: false,
      system_instructions: "",
      // Advanced Model / Provider
      llm_temperature: 0.0,
      llm_max_tokens: 1024,
      embedding_provider: "voyage",
      embedding_model: "voyage-4-large",
      local_llm_url: "http://localhost:1234/v1",
      agent_lightning_enabled: false,
    },
  });

  const { register, handleSubmit, reset, watch, setValue, formState: { errors } } = form;

  useEffect(() => {
    fetchSettings()
      .then((raw) => {
        reset({
          // Core
          llm_provider: (raw.llm_provider as string) ?? "anthropic",
          llm_model: (raw.llm_model as string) ?? "claude-opus-4-6",
          chat_path: ((raw.chat_path as string) === "Direct" ? "Direct" : "RAG"),
          selected_mode: (raw.selected_mode as string) ?? "Q&A",
          output_style: (raw.output_style as string) ?? "Default answer",
          chat_history_max_turns: (raw.chat_history_max_turns as number) ?? 6,
          show_retrieved_context: (raw.show_retrieved_context as boolean) ?? false,
          verbose_mode: (raw.verbose_mode as boolean) ?? false,
          // Advanced Retrieval
          chunk_size: (raw.chunk_size as number) ?? 1000,
          chunk_overlap: (raw.chunk_overlap as number) ?? 100,
          retrieval_k: (raw.retrieval_k as number) ?? 25,
          top_k: (raw.top_k as number) ?? 5,
          retrieval_mode: (raw.retrieval_mode as string) ?? "flat",
          search_type: (raw.search_type as string) ?? "similarity",
          mmr_lambda: (raw.mmr_lambda as number) ?? 0.5,
          use_reranker: (raw.use_reranker as boolean) ?? true,
          use_sub_queries: (raw.use_sub_queries as boolean) ?? true,
          enable_summarizer: (raw.enable_summarizer as boolean) ?? true,
          agentic_mode: (raw.agentic_mode as boolean) ?? false,
          agentic_max_iterations: (raw.agentic_max_iterations as number) ?? 2,
          subquery_max_docs: (raw.subquery_max_docs as number) ?? 200,
          document_loader: (raw.document_loader as string) ?? "auto",
          structure_aware_ingestion: (raw.structure_aware_ingestion as boolean) ?? false,
          semantic_layout_ingestion: (raw.semantic_layout_ingestion as boolean) ?? false,
          deepread_mode: (raw.deepread_mode as boolean) ?? false,
          build_digest_index: (raw.build_digest_index as boolean) ?? true,
          build_comprehension_index: (raw.build_comprehension_index as boolean) ?? false,
          comprehension_extraction_depth: (raw.comprehension_extraction_depth as string) ?? "Standard",
          prefer_comprehension_index: (raw.prefer_comprehension_index as boolean) ?? true,
          // Advanced Graph
          kg_query_mode: (raw.kg_query_mode as string) ?? "hybrid",
          enable_langextract: (raw.enable_langextract as boolean) ?? false,
          enable_structured_extraction: (raw.enable_structured_extraction as boolean) ?? false,
          enable_recursive_retrieval: (raw.enable_recursive_retrieval as boolean) ?? false,
          // Advanced Memory
          enable_recursive_memory: (raw.enable_recursive_memory as boolean) ?? false,
          enable_citation_v2: (raw.enable_citation_v2 as boolean) ?? true,
          enable_claim_level_grounding_citefix_lite: (raw.enable_claim_level_grounding_citefix_lite as boolean) ?? false,
          system_instructions: (raw.system_instructions as string) ?? "",
          // Advanced Model / Provider
          llm_temperature: (raw.llm_temperature as number) ?? 0.0,
          llm_max_tokens: (raw.llm_max_tokens as number) ?? 1024,
          embedding_provider: (raw.embedding_provider as string) ?? "voyage",
          embedding_model: (raw.embedding_model as string) ?? "voyage-4-large",
          local_llm_url: (raw.local_llm_url as string) ?? "http://localhost:1234/v1",
          agent_lightning_enabled: (raw.agent_lightning_enabled as boolean) ?? false,
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
            Core defaults, retrieval controls, graph, memory, and model settings.
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

        {/* Settings hint */}
        <div className="flex gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-800 dark:border-blue-800 dark:bg-blue-950/30 dark:text-blue-400">
          <Info className="mt-0.5 size-4 shrink-0" />
          <div>
            <p className="font-medium">Low-level settings</p>
            <p className="mt-0.5">
              Hardware overrides, vector DB connection strings, and GGUF model paths
              must be set in <code className="rounded bg-blue-100 px-1 dark:bg-blue-900/50">settings.json</code> at
              the repo root. Changes take effect on next server restart.
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
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
            <Tabs defaultValue="core">
              <TabsList className="h-auto w-full flex-wrap gap-1">
                <TabsTrigger value="core">Core</TabsTrigger>
                <TabsTrigger value="retrieval">Retrieval</TabsTrigger>
                <TabsTrigger value="graph">Graph</TabsTrigger>
                <TabsTrigger value="memory">Memory</TabsTrigger>
                <TabsTrigger value="model">Model</TabsTrigger>
              </TabsList>

              {/* ── Core ──────────────────────────────────────────────────── */}
              <TabsContent value="core" className="mt-6 space-y-6">
                <section className="space-y-4">
                  <div>
                    <h2 className="text-base font-semibold">Core defaults</h2>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      The settings most users need to change.
                    </p>
                  </div>
                  <Separator />

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="llm_provider">LLM provider</FieldLabel>
                      <Input id="llm_provider" type="text" {...register("llm_provider")} />
                      <FieldError message={errors.llm_provider?.message} />
                    </div>
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="llm_model">LLM model</FieldLabel>
                      <Input id="llm_model" type="text" {...register("llm_model")} />
                      <FieldError message={errors.llm_model?.message} />
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

                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="selected_mode">Skill mode</FieldLabel>
                    <div className="flex flex-wrap gap-3">
                      {SKILL_MODES.map((mode) => (
                        <label key={mode} htmlFor={`mode_${mode}`} className="flex cursor-pointer items-center gap-2 text-sm">
                          <input
                            id={`mode_${mode}`}
                            type="radio"
                            value={mode}
                            {...register("selected_mode")}
                            className="accent-primary"
                          />
                          {mode}
                        </label>
                      ))}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Controls how the assistant approaches your questions.
                    </p>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
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
                  </div>

                  <div className="space-y-2">
                    <ToggleRow
                      id="show_retrieved_context"
                      label="Show retrieved context"
                      description="Display the retrieved document chunks alongside answers in chat."
                      checked={watch("show_retrieved_context")}
                      onChange={(v) => setValue("show_retrieved_context", v)}
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
              </TabsContent>

              {/* ── Advanced Retrieval ─────────────────────────────────────── */}
              <TabsContent value="retrieval" className="mt-6 space-y-6">
                <section className="space-y-4">
                  <div>
                    <h2 className="text-base font-semibold">Advanced retrieval controls</h2>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Chunking, candidate selection, ranking, and ingestion options.
                    </p>
                  </div>
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

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="subquery_max_docs">Sub-query max docs</FieldLabel>
                      <Input
                        id="subquery_max_docs"
                        type="number"
                        min={1}
                        max={500}
                        {...register("subquery_max_docs", { valueAsNumber: true })}
                      />
                      <FieldError message={errors.subquery_max_docs?.message} />
                    </div>
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="document_loader">Document loader</FieldLabel>
                      <Input id="document_loader" type="text" {...register("document_loader")} />
                      <FieldError message={errors.document_loader?.message} />
                    </div>
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="comprehension_extraction_depth">Comprehension depth</FieldLabel>
                      <select
                        id="comprehension_extraction_depth"
                        {...register("comprehension_extraction_depth")}
                        className="h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus:outline-none focus:ring-1 focus:ring-ring"
                      >
                        {COMPREHENSION_DEPTHS.map((d) => (
                          <option key={d} value={d}>{d}</option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="agentic_max_iterations">Agentic max iterations</FieldLabel>
                      <Input
                        id="agentic_max_iterations"
                        type="number"
                        min={1}
                        max={10}
                        {...register("agentic_max_iterations", { valueAsNumber: true })}
                      />
                      <FieldError message={errors.agentic_max_iterations?.message} />
                    </div>
                  </div>

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
                      id="structure_aware_ingestion"
                      label="Structure-aware ingestion"
                      description="Parse document structure (headings, tables) during ingestion for better chunking."
                      checked={watch("structure_aware_ingestion")}
                      onChange={(v) => setValue("structure_aware_ingestion", v)}
                    />
                    <ToggleRow
                      id="semantic_layout_ingestion"
                      label="Semantic layout ingestion"
                      description="Use layout analysis to understand document spatial structure during ingestion."
                      checked={watch("semantic_layout_ingestion")}
                      onChange={(v) => setValue("semantic_layout_ingestion", v)}
                    />
                    <ToggleRow
                      id="deepread_mode"
                      label="Deep-read mode"
                      description="Enable multi-pass deep reading for complex documents."
                      checked={watch("deepread_mode")}
                      onChange={(v) => setValue("deepread_mode", v)}
                    />
                    <ToggleRow
                      id="build_digest_index"
                      label="Build digest index"
                      description="Build a fast summary digest index alongside the main vector index."
                      checked={watch("build_digest_index")}
                      onChange={(v) => setValue("build_digest_index", v)}
                    />
                    <ToggleRow
                      id="build_comprehension_index"
                      label="Build comprehension index"
                      description="Build a deep comprehension index for richer retrieval (slower to build)."
                      checked={watch("build_comprehension_index")}
                      onChange={(v) => setValue("build_comprehension_index", v)}
                    />
                    <ToggleRow
                      id="prefer_comprehension_index"
                      label="Prefer comprehension index"
                      description="Use the comprehension index when both indexes are available."
                      checked={watch("prefer_comprehension_index")}
                      onChange={(v) => setValue("prefer_comprehension_index", v)}
                    />
                  </div>
                </section>
              </TabsContent>

              {/* ── Advanced Graph ─────────────────────────────────────────── */}
              <TabsContent value="graph" className="mt-6 space-y-6">
                <section className="space-y-4">
                  <div>
                    <h2 className="text-base font-semibold">Advanced graph controls</h2>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Knowledge graph query mode and graph-augmented extraction features.
                    </p>
                  </div>
                  <Separator />

                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="kg_query_mode">Knowledge graph query mode</FieldLabel>
                    <select
                      id="kg_query_mode"
                      {...register("kg_query_mode")}
                      className="h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus:outline-none focus:ring-1 focus:ring-ring"
                    >
                      {KG_QUERY_MODES.map((m) => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                    <p className="text-xs text-muted-foreground">
                      hybrid — combines vector and keyword search; vector — embedding only; keyword — BM25 only.
                    </p>
                  </div>

                  <div className="space-y-2">
                    <ToggleRow
                      id="enable_langextract"
                      label="Language extraction"
                      description="Enable language-aware extraction pipeline for multi-lingual documents."
                      checked={watch("enable_langextract")}
                      onChange={(v) => setValue("enable_langextract", v)}
                    />
                    <ToggleRow
                      id="enable_structured_extraction"
                      label="Structured extraction"
                      description="Extract structured data (tables, entities) from documents during ingestion."
                      checked={watch("enable_structured_extraction")}
                      onChange={(v) => setValue("enable_structured_extraction", v)}
                    />
                    <ToggleRow
                      id="enable_recursive_retrieval"
                      label="Recursive retrieval"
                      description="Recursively follow graph edges to retrieve additional related context."
                      checked={watch("enable_recursive_retrieval")}
                      onChange={(v) => setValue("enable_recursive_retrieval", v)}
                    />
                  </div>
                </section>
              </TabsContent>

              {/* ── Advanced Memory ────────────────────────────────────────── */}
              <TabsContent value="memory" className="mt-6 space-y-6">
                <section className="space-y-4">
                  <div>
                    <h2 className="text-base font-semibold">Advanced memory controls</h2>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Citation grounding, recursive memory, and system prompt overrides.
                    </p>
                  </div>
                  <Separator />

                  <div className="space-y-2">
                    <ToggleRow
                      id="enable_citation_v2"
                      label="Citation v2"
                      description="Use the improved citation pipeline with claim-level source mapping."
                      checked={watch("enable_citation_v2")}
                      onChange={(v) => setValue("enable_citation_v2", v)}
                    />
                    <ToggleRow
                      id="enable_claim_level_grounding_citefix_lite"
                      label="Claim-level grounding (citefix lite)"
                      description="Post-process answers to verify and fix citation anchors at the claim level."
                      checked={watch("enable_claim_level_grounding_citefix_lite")}
                      onChange={(v) => setValue("enable_claim_level_grounding_citefix_lite", v)}
                    />
                    <ToggleRow
                      id="enable_recursive_memory"
                      label="Recursive memory"
                      description="Persist and recall prior conversation context across sessions."
                      checked={watch("enable_recursive_memory")}
                      onChange={(v) => setValue("enable_recursive_memory", v)}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="system_instructions">System instructions</FieldLabel>
                    <textarea
                      id="system_instructions"
                      rows={5}
                      {...register("system_instructions")}
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm transition-colors focus:outline-none focus:ring-1 focus:ring-ring resize-y"
                      placeholder="Override the default system prompt sent to the LLM. Leave blank to use the built-in default."
                    />
                    <p className="text-xs text-muted-foreground">
                      Leave blank to use the built-in default system prompt.
                    </p>
                  </div>
                </section>
              </TabsContent>

              {/* ── Advanced Model / Provider ──────────────────────────────── */}
              <TabsContent value="model" className="mt-6 space-y-6">
                <section className="space-y-4">
                  <div>
                    <h2 className="text-base font-semibold">Advanced model / provider controls</h2>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      LLM generation parameters, embedding provider, and local LLM settings.
                    </p>
                  </div>
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

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="embedding_provider">Embedding provider</FieldLabel>
                      <Input id="embedding_provider" type="text" {...register("embedding_provider")} />
                      <FieldError message={errors.embedding_provider?.message} />
                    </div>
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="embedding_model">Embedding model</FieldLabel>
                      <Input id="embedding_model" type="text" {...register("embedding_model")} />
                      <FieldError message={errors.embedding_model?.message} />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="local_llm_url">Local LLM URL</FieldLabel>
                    <Input
                      id="local_llm_url"
                      type="text"
                      {...register("local_llm_url")}
                    />
                    <p className="text-xs text-muted-foreground">
                      OpenAI-compatible endpoint for local models (e.g. LM Studio, Ollama).
                    </p>
                    <FieldError message={errors.local_llm_url?.message} />
                  </div>

                  <div className="space-y-2">
                    <ToggleRow
                      id="agent_lightning_enabled"
                      label="Agent lightning mode"
                      description="Enable fast-path agent execution for simple queries."
                      checked={watch("agent_lightning_enabled")}
                      onChange={(v) => setValue("agent_lightning_enabled", v)}
                    />
                  </div>
                </section>
              </TabsContent>
            </Tabs>

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
