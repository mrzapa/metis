"use client";

import { useEffect, useMemo, type CSSProperties, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BorderBeam } from "@/components/ui/border-beam";
import { AnimatedLucideIcon } from "@/components/ui/animated-lucide-icon";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { PageChrome } from "@/components/shell/page-chrome";
import { GgufModelsPanel } from "@/components/gguf/gguf-models-panel";
import {
  fetchAssistantSettings,
  fetchSettings,
  updateAssistantSettings,
  updateSettings,
  type AssistantSettings,
} from "@/lib/api";
import { AlertCircle, CheckCircle2, ChevronDown, HelpCircle, Info, Loader2, RotateCcw, Search, TriangleAlert } from "lucide-react";
import { useArrowState } from "@/hooks/use-arrow-state";

const FORECAST_MAX_CONTEXT_LIMIT = 15360;
const FORECAST_MAX_HORIZON_LIMIT = 1000;

const schema = z.object({
  // ── Core ──────────────────────────────────────────────────────────────────
  llm_provider: z.string().min(1),
  llm_model: z.string().min(1),
  chat_path: z.enum(["RAG", "Direct", "Forecast"]),
  selected_mode: z.string().min(1),
  output_style: z.string().min(1),
  chat_history_max_turns: z.number().int().min(1, "Min 1").max(50, "Max 50"),
  show_retrieved_context: z.boolean(),
  verbose_mode: z.boolean(),
  forecast_model_id: z.string().min(1),
  forecast_max_context: z
    .number()
    .int()
    .min(1, "Min 1")
    .max(FORECAST_MAX_CONTEXT_LIMIT, `Max ${FORECAST_MAX_CONTEXT_LIMIT}`),
  forecast_max_horizon: z
    .number()
    .int()
    .min(1, "Min 1")
    .max(FORECAST_MAX_HORIZON_LIMIT, `Max ${FORECAST_MAX_HORIZON_LIMIT}`),
  forecast_use_quantiles: z.boolean(),
  forecast_xreg_mode: z.string().min(1),
  forecast_force_xreg_cpu: z.boolean(),
  // ── Advanced Retrieval ────────────────────────────────────────────────────
  chunk_size: z.number().int().min(100, "Min 100").max(10000, "Max 10000"),
  chunk_overlap: z.number().int().min(0, "Min 0").max(500, "Max 500"),
  parent_chunk_size: z.number().int().min(200, "Min 200").max(50000, "Max 50000"),
  parent_chunk_overlap: z.number().int().min(0, "Min 0").max(10000, "Max 10000"),
  retrieval_k: z.number().int().min(1, "Min 1").max(200, "Max 200"),
  top_k: z.number().int().min(1, "Min 1").max(50, "Max 50"),
  knowledge_search_top_k: z.number().int().min(1, "Min 1").max(50, "Max 50"),
  retrieval_mode: z.string().min(1),
  search_type: z.string().min(1),
  mmr_lambda: z.number().min(0).max(1),
  hybrid_alpha: z.number().min(0).max(1),
  retrieval_min_score: z.number().min(0).max(1),
  fallback_strategy: z.string().min(1),
  fallback_message: z.string(),
  use_reranker: z.boolean(),
  use_sub_queries: z.boolean(),
  enable_summarizer: z.boolean(),
  agentic_mode: z.boolean(),
  agentic_max_iterations: z.number().int().min(1, "Min 1").max(10, "Max 10"),
  agentic_iteration_budget: z.number().int().min(1, "Min 1").max(10, "Max 10"),
  agentic_convergence_threshold: z.number().min(0).max(1),
  subquery_max_docs: z.number().int().min(1, "Min 1").max(500, "Max 500"),
  document_loader: z.string().min(1),
  structure_aware_ingestion: z.boolean(),
  semantic_layout_ingestion: z.boolean(),
  deepread_mode: z.boolean(),
  build_digest_index: z.boolean(),
  build_comprehension_index: z.boolean(),
  build_llm_knowledge_graph: z.boolean(),
  comprehension_extraction_depth: z.string().min(1),
  prefer_comprehension_index: z.boolean(),
  swarm_n_personas: z.number().int().min(1, "Min 1").max(32, "Max 32"),
  swarm_n_rounds: z.number().int().min(1, "Min 1").max(16, "Max 16"),
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
  web_scrape_full_content: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

type AssistantFormValues = AssistantSettings;

const RETRIEVAL_MODES = ["flat", "mmr", "hybrid", "hierarchical"];
const SEARCH_TYPES = ["similarity", "mmr"];
const OUTPUT_STYLES = ["Default answer", "Concise", "Detailed", "Bullet points"];
const SKILL_MODES = ["Q&A", "Summary", "Tutor", "Research", "Evidence Pack", "Knowledge Search"];
const FORECAST_SELECTED_MODE = "Forecast";
const FORECAST_XREG_MODES = ["xreg + timesfm", "timesfm"];
const FALLBACK_STRATEGIES = ["synthesize_anyway", "no_answer"];
const KG_QUERY_MODES = ["hybrid", "vector", "keyword"];
const COMPREHENSION_DEPTHS = ["Standard", "Deep", "Exhaustive"];
const DOCUMENT_LOADERS = [
  { value: "auto", label: "Auto (kreuzberg)" },
  { value: "plain", label: "Plain text" },
  { value: "opendataloader", label: "opendataloader-pdf (highest PDF accuracy)" },
] as const;
type SettingsTabValue = "core" | "retrieval" | "graph" | "memory" | "provider" | "companion" | "models" | "privacy";

const SETTINGS_TAB_VALUES: readonly SettingsTabValue[] = [
  "core",
  "retrieval",
  "graph",
  "memory",
  "provider",
  "companion",
  "models",
  "privacy",
] as const;

function isSettingsTabValue(value: string | null | undefined): value is SettingsTabValue {
  return value !== null && value !== undefined && (SETTINGS_TAB_VALUES as readonly string[]).includes(value);
}

const ASSISTANT_DEFAULT_VALUES: AssistantFormValues = {
  assistant_identity: {
    assistant_id: "metis-companion",
    name: "METIS",
    archetype: "Local-first research companion",
    companion_enabled: true,
    greeting: "I can help you get started, reflect on completed work, and map what I learn in the Brain view.",
    prompt_seed:
      "You are METIS, a local-first companion who helps the user get oriented, suggests next steps, and records concise reflections without taking over the main chat.",
    docked: true,
    minimized: false,
  },
  assistant_runtime: {
    provider: "",
    model: "",
    local_gguf_model_path: "",
    local_gguf_context_length: 2048,
    local_gguf_gpu_layers: 0,
    local_gguf_threads: 0,
    fallback_to_primary: true,
    auto_bootstrap: true,
    auto_install: false,
    bootstrap_state: "pending",
    recommended_model_name: "",
    recommended_quant: "",
    recommended_use_case: "chat",
  },
  assistant_policy: {
    reflection_enabled: true,
    reflection_backend: "hybrid",
    reflection_cooldown_seconds: 180,
    max_memory_entries: 200,
    max_playbooks: 64,
    max_brain_links: 400,
    trigger_on_onboarding: true,
    trigger_on_index_build: true,
    trigger_on_completed_run: true,
    allow_automatic_writes: true,
    autonomous_research_enabled: false,
  },
};

function assistantToForm(values: AssistantSettings): AssistantFormValues {
  return {
    assistant_identity: {
      ...ASSISTANT_DEFAULT_VALUES.assistant_identity,
      ...values.assistant_identity,
    },
    assistant_runtime: {
      ...ASSISTANT_DEFAULT_VALUES.assistant_runtime,
      ...values.assistant_runtime,
    },
    assistant_policy: {
      ...ASSISTANT_DEFAULT_VALUES.assistant_policy,
      ...values.assistant_policy,
    },
  };
}

/** Default form values used for the "Reset to defaults" action. */
const FORM_DEFAULT_VALUES: FormValues = {
  llm_provider: "anthropic",
  llm_model: "claude-opus-4-6",
  chat_path: "RAG",
  selected_mode: "Q&A",
  output_style: "Default answer",
  chat_history_max_turns: 6,
  show_retrieved_context: false,
  verbose_mode: false,
  forecast_model_id: "google/timesfm-2.5-200m-pytorch",
  forecast_max_context: FORECAST_MAX_CONTEXT_LIMIT,
  forecast_max_horizon: FORECAST_MAX_HORIZON_LIMIT,
  forecast_use_quantiles: true,
  forecast_xreg_mode: "xreg + timesfm",
  forecast_force_xreg_cpu: true,
  chunk_size: 1000,
  chunk_overlap: 100,
  parent_chunk_size: 2800,
  parent_chunk_overlap: 320,
  retrieval_k: 25,
  top_k: 5,
  knowledge_search_top_k: 8,
  retrieval_mode: "flat",
  search_type: "similarity",
  mmr_lambda: 0.5,
  hybrid_alpha: 1.0,
  retrieval_min_score: 0.15,
  fallback_strategy: "synthesize_anyway",
  fallback_message:
    "I couldn't find enough grounded evidence in the selected index to answer confidently. Try Knowledge Search, increase retrieval depth, or rephrase the question.",
  use_reranker: true,
  use_sub_queries: true,
  enable_summarizer: true,
  agentic_mode: false,
  agentic_max_iterations: 2,
  agentic_iteration_budget: 4,
  agentic_convergence_threshold: 0.95,
  subquery_max_docs: 200,
  document_loader: "auto",
  structure_aware_ingestion: false,
  semantic_layout_ingestion: false,
  deepread_mode: false,
  build_digest_index: true,
  build_comprehension_index: false,
  build_llm_knowledge_graph: false,
  comprehension_extraction_depth: "Standard",
  prefer_comprehension_index: true,
  swarm_n_personas: 8,
  swarm_n_rounds: 4,
  kg_query_mode: "hybrid",
  enable_langextract: false,
  enable_structured_extraction: false,
  enable_recursive_retrieval: false,
  enable_recursive_memory: false,
  enable_citation_v2: true,
  enable_claim_level_grounding_citefix_lite: false,
  system_instructions: "",
  llm_temperature: 0.0,
  llm_max_tokens: 1024,
  embedding_provider: "voyage",
  embedding_model: "voyage-4-large",
  local_llm_url: "http://localhost:1234/v1",
  agent_lightning_enabled: false,
  web_scrape_full_content: false,
};

/** Search index metadata for all settings fields. Used by the search bar. */
const SEARCH_INDEX = [
  // ── Core ──
  { tab: "core", label: "LLM provider", description: "The AI provider used for chat (e.g. anthropic, openai, local)." },
  { tab: "core", label: "LLM model", description: "The model identifier for the primary LLM." },
  { tab: "core", label: "Query path", description: "RAG uses retrieved document context; Direct sends prompts straight to the LLM." },
  { tab: "core", label: "Skill mode", description: "Controls how the assistant approaches your questions (Q&A, Research, Tutor, etc.)." },
  { tab: "core", label: "Output style", description: "Format preference for generated answers." },
  { tab: "core", label: "History turns", description: "Number of past conversation turns included in each new request." },
  { tab: "core", label: "Show retrieved context", description: "Display the retrieved document chunks alongside answers in chat." },
  { tab: "core", label: "Verbose mode", description: "Log additional diagnostic information to the server console." },
  { tab: "core", label: "Forecast model ID", description: "TimesFM checkpoint to use for Forecast chat mode." },
  { tab: "core", label: "Forecast max context", description: "Maximum historical points passed into each TimesFM forecast run." },
  { tab: "core", label: "Forecast max horizon", description: "Upper bound for forecast steps in Forecast mode." },
  { tab: "core", label: "Forecast quantiles", description: "Include uncertainty bands like p10 and p90 in forecast artifacts." },
  { tab: "core", label: "Forecast XReg mode", description: "Covariate execution mode used when dynamic or static regressors are mapped." },
  { tab: "core", label: "Forecast force CPU", description: "Force XReg covariate runs onto CPU for stability, especially on Windows." },
  // ── Retrieval ──
  { tab: "retrieval", label: "Chunk size", description: "Token size of each ingested document chunk." },
  { tab: "retrieval", label: "Chunk overlap", description: "Overlap between consecutive chunks to avoid cutting context mid-sentence." },
  { tab: "retrieval", label: "Parent chunk size", description: "Size of the parent chunk used in hierarchical retrieval." },
  { tab: "retrieval", label: "Parent chunk overlap", description: "Overlap for parent chunks." },
  { tab: "retrieval", label: "Retrieval k", description: "Number of candidate chunks fetched from the vector store before ranking." },
  { tab: "retrieval", label: "Top k", description: "Number of final chunks passed to the LLM after ranking." },
  { tab: "retrieval", label: "Knowledge Search top k", description: "Result limit for the Knowledge Search skill." },
  { tab: "retrieval", label: "Retrieval mode", description: "flat, mmr, hybrid, or hierarchical retrieval strategy." },
  { tab: "retrieval", label: "Search type", description: "Vector similarity or MMR-based search." },
  { tab: "retrieval", label: "MMR lambda", description: "Diversity vs relevance trade-off for MMR retrieval (0 = max diversity, 1 = max relevance)." },
  { tab: "retrieval", label: "Hybrid search alpha", description: "Blend between keyword (BM25) and vector search. 1.0 = pure vector, 0.0 = pure keyword, 0.5 = equal weight." },
  { tab: "retrieval", label: "Retrieval min score", description: "Minimum similarity score required to include a chunk." },
  { tab: "retrieval", label: "Fallback strategy", description: "What to do when no high-quality chunks are found." },
  { tab: "retrieval", label: "Fallback message", description: "Message shown when retrieval quality is below the minimum score threshold." },
  { tab: "retrieval", label: "Use reranker", description: "Re-rank retrieved chunks for better relevance before generating answers." },
  { tab: "retrieval", label: "Use sub-queries", description: "Decompose complex questions into sub-queries for broader coverage." },
  { tab: "retrieval", label: "Enable summariser", description: "Summarise long context windows before passing to the LLM." },
  { tab: "retrieval", label: "Agentic mode", description: "Allow the system to iterate and self-correct using tool use loops." },
  { tab: "retrieval", label: "Agentic max iterations", description: "Maximum refinement cycles when agentic mode is on." },
  { tab: "retrieval", label: "Sub-query max docs", description: "Maximum documents fetched per sub-query expansion." },
  { tab: "retrieval", label: "Document loader", description: "Loader used to parse documents during ingestion." },
  { tab: "retrieval", label: "Structure-aware ingestion", description: "Parse document structure (headings, tables) during ingestion for better chunking." },
  { tab: "retrieval", label: "Semantic layout ingestion", description: "Use layout analysis to understand document spatial structure during ingestion." },
  { tab: "retrieval", label: "Deep-read mode", description: "Enable multi-pass deep reading for complex documents." },
  { tab: "retrieval", label: "Build digest index", description: "Build a fast summary digest index alongside the main vector index." },
  { tab: "retrieval", label: "Build comprehension index", description: "Build a deep comprehension index for richer retrieval (slower to build)." },
  { tab: "retrieval", label: "Comprehension depth", description: "How deeply to analyse documents when building the comprehension index." },
  { tab: "retrieval", label: "Prefer comprehension index", description: "Use the comprehension index when both indexes are available." },
  { tab: "retrieval", label: "Swarm personas", description: "Number of AI personas used in swarm simulation queries." },
  { tab: "retrieval", label: "Swarm rounds", description: "Number of debate rounds in swarm simulation before synthesising the final answer." },
  // ── Graph ──
  { tab: "graph", label: "Knowledge graph query mode", description: "hybrid combines vector + keyword; vector uses embeddings only; keyword uses BM25 only." },
  { tab: "graph", label: "Language extraction", description: "Enable language-aware extraction pipeline for multi-lingual documents." },
  { tab: "graph", label: "Structured extraction", description: "Extract structured data (tables, entities) from documents during ingestion." },
  { tab: "graph", label: "Recursive retrieval", description: "Recursively follow graph edges to retrieve additional related context." },
  { tab: "graph", label: "LLM knowledge graph enrichment", description: "Use the LLM to extract entities and relations during indexing for a richer knowledge graph." },
  // ── Memory ──
  { tab: "memory", label: "Citation v2", description: "Use the improved citation pipeline with claim-level source mapping." },
  { tab: "memory", label: "Claim-level grounding", description: "Post-process answers to verify and fix citation anchors at the claim level." },
  { tab: "memory", label: "Recursive memory", description: "Persist and recall prior conversation context across sessions." },
  { tab: "memory", label: "System instructions", description: "Override the default system prompt sent to the LLM." },
  // ── Provider ──
  { tab: "provider", label: "Temperature", description: "Controls output randomness. 0 = deterministic, 2 = highly creative." },
  { tab: "provider", label: "Max tokens", description: "Maximum tokens the LLM may generate in a single response." },
  { tab: "provider", label: "Embedding provider", description: "Provider for text embeddings used in vector search." },
  { tab: "provider", label: "Embedding model", description: "Embedding model identifier." },
  { tab: "provider", label: "Local LLM URL", description: "OpenAI-compatible endpoint for local models (e.g. LM Studio, Ollama)." },
  { tab: "provider", label: "Agent lightning mode", description: "Enable fast-path agent execution for simple queries." },
] as const;

function FieldError({ message }: { message?: string }) {
  if (!message) return null;
  return <p className="mt-0.5 text-xs text-destructive">{message}</p>;
}

function FieldLabel({ htmlFor, children, tooltip }: { htmlFor: string; children: ReactNode; tooltip?: string }) {
  if (!tooltip) {
    return (
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {children}
      </label>
    );
  }
  return (
    <div className="flex items-center gap-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {children}
      </label>
      <Tooltip>
        <TooltipTrigger render={
          <button
            type="button"
            aria-label={`Help for ${typeof children === "string" ? children : htmlFor}`}
            className="text-muted-foreground/60 hover:text-muted-foreground transition-colors"
          >
            <HelpCircle className="size-3.5" aria-hidden="true" />
          </button>
        } />
        <TooltipContent side="right">{tooltip}</TooltipContent>
      </Tooltip>
    </div>
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
      className="settings-toggle flex cursor-pointer items-start gap-3 rounded-xl px-4 py-3"
      data-checked={checked ? "true" : "false"}
    >
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        className="settings-toggle__input"
      />
      <span className="settings-toggle__switch mt-0.5" aria-hidden="true">
        <span className="settings-toggle__thumb" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium">{label}</p>
          <span className="settings-toggle__state">{checked ? "On" : "Off"}</span>
        </div>
        {description && <p className="text-xs text-muted-foreground">{description}</p>}
      </div>
    </label>
  );
}

export default function SettingsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const tabParam = searchParams.get("tab");
  const initialTab: SettingsTabValue = isSettingsTabValue(tabParam) ? tabParam : "core";
  const initialModelsTab = searchParams.get("modelsTab");
  const initialHereticModelId = searchParams.get("model_id");
  const [loading, setLoading] = useArrowState(true);
  const [loadError, setLoadError] = useArrowState<string | null>(null);
  const [saving, setSaving] = useArrowState(false);
  const [saveError, setSaveError] = useArrowState<string | null>(null);
  const [saved, setSaved] = useArrowState(false);
  const [assistantLoading, setAssistantLoading] = useArrowState(true);
  const [assistantLoadError, setAssistantLoadError] = useArrowState<string | null>(null);
  const [assistantSaving, setAssistantSaving] = useArrowState(false);
  const [assistantSaveError, setAssistantSaveError] = useArrowState<string | null>(null);
  const [assistantSaved, setAssistantSaved] = useArrowState(false);
  const [searchQuery, setSearchQuery] = useArrowState("");
  const [forecastAdvancedOpen, setForecastAdvancedOpen] = useArrowState(false);
  const [activeTab, setActiveTab] = useArrowState<SettingsTabValue>(initialTab);

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
      forecast_model_id: "google/timesfm-2.5-200m-pytorch",
      forecast_max_context: FORECAST_MAX_CONTEXT_LIMIT,
      forecast_max_horizon: FORECAST_MAX_HORIZON_LIMIT,
      forecast_use_quantiles: true,
      forecast_xreg_mode: "xreg + timesfm",
      forecast_force_xreg_cpu: true,
      // Advanced Retrieval
      chunk_size: 1000,
      chunk_overlap: 100,
      parent_chunk_size: 2800,
      parent_chunk_overlap: 320,
      retrieval_k: 25,
      top_k: 5,
      knowledge_search_top_k: 8,
      retrieval_mode: "flat",
      search_type: "similarity",
      mmr_lambda: 0.5,
      hybrid_alpha: 1.0,
      retrieval_min_score: 0.15,
      fallback_strategy: "synthesize_anyway",
      fallback_message:
        "I couldn't find enough grounded evidence in the selected index to answer confidently. Try Knowledge Search, increase retrieval depth, or rephrase the question.",
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
      build_llm_knowledge_graph: false,
      comprehension_extraction_depth: "Standard",
      prefer_comprehension_index: true,
      swarm_n_personas: 8,
      swarm_n_rounds: 4,
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
      web_scrape_full_content: false,
    },
  });

  const { register, handleSubmit, reset, watch, setValue, formState: { errors } } = form;
  const hasAdvancedForecastErrors = !!(
    errors.forecast_model_id ||
    errors.forecast_xreg_mode ||
    errors.forecast_max_context ||
    errors.forecast_max_horizon
  );
  const assistantForm = useForm<AssistantFormValues>({
    defaultValues: ASSISTANT_DEFAULT_VALUES,
  });
  const {
    register: registerAssistant,
    handleSubmit: handleAssistantSubmit,
    reset: resetAssistant,
    watch: watchAssistant,
    setValue: setAssistantValue,
  } = assistantForm;

  useEffect(() => {
    fetchSettings()
      .then((raw) => {
        const rawChatPath = String(raw.chat_path ?? "");
        reset({
          // Core
          llm_provider: (raw.llm_provider as string) ?? "anthropic",
          llm_model: (raw.llm_model as string) ?? "claude-opus-4-6",
          chat_path:
            rawChatPath === "Direct"
              ? "Direct"
              : "RAG", // legacy "Forecast" is coerced to "RAG"; forecasting is now triggered by file attachment
          selected_mode: (raw.selected_mode as string) ?? "Q&A",
          output_style: (raw.output_style as string) ?? "Default answer",
          chat_history_max_turns: (raw.chat_history_max_turns as number) ?? 6,
          show_retrieved_context: (raw.show_retrieved_context as boolean) ?? false,
          verbose_mode: (raw.verbose_mode as boolean) ?? false,
          forecast_model_id: (raw.forecast_model_id as string) ?? "google/timesfm-2.5-200m-pytorch",
          forecast_max_context: (raw.forecast_max_context as number) ?? FORECAST_MAX_CONTEXT_LIMIT,
          forecast_max_horizon: (raw.forecast_max_horizon as number) ?? FORECAST_MAX_HORIZON_LIMIT,
          forecast_use_quantiles: (raw.forecast_use_quantiles as boolean) ?? true,
          forecast_xreg_mode: (raw.forecast_xreg_mode as string) ?? "xreg + timesfm",
          forecast_force_xreg_cpu: (raw.forecast_force_xreg_cpu as boolean) ?? true,
          // Advanced Retrieval
          chunk_size: (raw.chunk_size as number) ?? 1000,
          chunk_overlap: (raw.chunk_overlap as number) ?? 100,
          parent_chunk_size: (raw.parent_chunk_size as number) ?? 2800,
          parent_chunk_overlap: (raw.parent_chunk_overlap as number) ?? 320,
          retrieval_k: (raw.retrieval_k as number) ?? 25,
          top_k: (raw.top_k as number) ?? 5,
          knowledge_search_top_k: (raw.knowledge_search_top_k as number) ?? 8,
          retrieval_mode: (raw.retrieval_mode as string) ?? "flat",
          search_type: (raw.search_type as string) ?? "similarity",
          mmr_lambda: (raw.mmr_lambda as number) ?? 0.5,
          hybrid_alpha: (raw.hybrid_alpha as number) ?? 1.0,
          retrieval_min_score: (raw.retrieval_min_score as number) ?? 0.15,
          fallback_strategy: (raw.fallback_strategy as string) ?? "synthesize_anyway",
          fallback_message:
            (raw.fallback_message as string) ??
            "I couldn't find enough grounded evidence in the selected index to answer confidently. Try Knowledge Search, increase retrieval depth, or rephrase the question.",
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
          build_llm_knowledge_graph: (raw.build_llm_knowledge_graph as boolean) ?? false,
          comprehension_extraction_depth: (raw.comprehension_extraction_depth as string) ?? "Standard",
          prefer_comprehension_index: (raw.prefer_comprehension_index as boolean) ?? true,
          swarm_n_personas: (raw.swarm_n_personas as number) ?? 8,
          swarm_n_rounds: (raw.swarm_n_rounds as number) ?? 4,
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
          web_scrape_full_content: (raw.web_scrape_full_content as boolean) ?? false,
        });
      })
      .catch((err) => setLoadError(err instanceof Error ? err.message : "Failed to load settings"))
      .finally(() => setLoading(false));
  }, [reset, setLoadError, setLoading]);

  useEffect(() => {
    fetchAssistantSettings()
      .then((assistant) => {
        resetAssistant(assistantToForm(assistant));
      })
      .catch((err) => setAssistantLoadError(err instanceof Error ? err.message : "Failed to load assistant settings"))
      .finally(() => setAssistantLoading(false));
  }, [resetAssistant, setAssistantLoadError, setAssistantLoading]);

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

  async function onAssistantSubmit(values: AssistantFormValues) {
    setAssistantSaving(true);
    setAssistantSaveError(null);
    setAssistantSaved(false);
    try {
      await updateAssistantSettings(values);
      setAssistantSaved(true);
      setTimeout(() => setAssistantSaved(false), 3000);
    } catch (err) {
      setAssistantSaveError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setAssistantSaving(false);
    }
  }

  const mmrLambda = watch("mmr_lambda");
  const hybridAlpha = watch("hybrid_alpha");
  const llmTemp = watch("llm_temperature");
  const chatPath = watch("chat_path");
  const selectedMode = watch("selected_mode");

  useEffect(() => {
    if (chatPath === "Forecast" && selectedMode !== FORECAST_SELECTED_MODE) {
      setValue("selected_mode", FORECAST_SELECTED_MODE);
      return;
    }
    if (chatPath !== "Forecast" && selectedMode === FORECAST_SELECTED_MODE) {
      setValue("selected_mode", "Q&A");
    }
  }, [chatPath, selectedMode, setValue]);

  const searchResults = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return null;
    return SEARCH_INDEX.filter(
      (entry) =>
        entry.label.toLowerCase().includes(q) ||
        entry.description.toLowerCase().includes(q) ||
        entry.tab.toLowerCase().includes(q),
    );
  }, [searchQuery]);

  function resetToDefaults() {
    reset(FORM_DEFAULT_VALUES);
  }

  // Sync the active tab to the URL via ``?tab=<value>`` so the page is
  // bookmarkable and deep-linkable. Preserves any other query params
  // (notably ``modelsTab`` / ``model_id`` used by the Heretic toolbar pill
  // when it deep-links into the Models tab). Uses ``router.replace`` to
  // avoid polluting browser history when the user clicks through tabs.
  function syncTabToUrl(tab: SettingsTabValue) {
    const params = new URLSearchParams(searchParams.toString());
    params.set("tab", tab);
    // ``modelsTab`` and ``model_id`` only make sense while on the Models
    // tab. Strip them when leaving so e.g. clicking back to Core doesn't
    // leave a stale ``?tab=core&modelsTab=heretic`` in the address bar.
    if (tab !== "models") {
      params.delete("modelsTab");
      params.delete("model_id");
    }
    router.replace(`/settings/?${params.toString()}`, { scroll: false });
  }

  function handleTabChange(tab: SettingsTabValue) {
    setActiveTab(tab);
    syncTabToUrl(tab);
  }

  function jumpToSearchResult(tab: SettingsTabValue) {
    setActiveTab(tab);
    syncTabToUrl(tab);
    setSearchQuery("");
  }

  return (
    <PageChrome
      eyebrow="Settings"
      title="Configure your workspace"
      description="Fine-tune model providers, retrieval parameters, graph behaviour, memory settings, and the companion assistant."
    >
      <TooltipProvider>
      <div className="mx-auto max-w-3xl space-y-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-lg font-semibold">Settings</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Core defaults, retrieval controls, graph, memory, model, and companion settings.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={resetToDefaults}
            className="gap-1.5 text-xs"
          >
            <RotateCcw className="size-3.5" />
            Reset to defaults
          </Button>
        </div>

        {/* Search bar */}
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground/60" />
          <Input
            type="search"
            placeholder="Search settings…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9"
            aria-label="Search settings"
          />
        </div>

        {/* Search results overlay */}
        {searchResults !== null && (
          <div className="glass-settings-pane rounded-[1.35rem] space-y-2">
            {searchResults.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">
                No settings matched <strong>&ldquo;{searchQuery}&rdquo;</strong>.
              </p>
            ) : (
              <>
                <p className="text-xs text-muted-foreground pb-1">
                  {searchResults.length} result{searchResults.length !== 1 ? "s" : ""} for &ldquo;{searchQuery}&rdquo;
                </p>
                <ul className="divide-y divide-white/6">
                  {searchResults.map((entry) => (
                    <li key={`${entry.tab}-${entry.label}`} className="py-1">
                      <button
                        type="button"
                        onClick={() => jumpToSearchResult(entry.tab as SettingsTabValue)}
                        className="flex w-full items-start gap-3 rounded-xl px-2 py-2 text-left transition-colors hover:bg-white/5"
                      >
                        <span className="mt-0.5 shrink-0 rounded-full bg-primary/12 px-2 py-0.5 text-xs uppercase tracking-[0.14em] text-primary/80">
                          {entry.tab}
                        </span>
                        <div className="min-w-0">
                          <p className="text-sm font-medium">{entry.label}</p>
                          <p className="mt-0.5 text-xs text-muted-foreground">{entry.description}</p>
                        </div>
                      </button>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}

        {/* Guardrail: API keys not editable */}
        <div className="flex gap-3 rounded-[1rem] border border-amber-500/20 bg-amber-500/8 px-4 py-3 text-sm text-amber-300/90 backdrop-blur-sm">
          <AnimatedLucideIcon icon={TriangleAlert} mode="idlePulse" className="mt-0.5 size-4 shrink-0" />
          <div>
            <p className="font-medium">API keys are not editable here</p>
            <p className="mt-0.5">
              The backend blocks <code className="rounded bg-amber-500/15 px-1">api_key_*</code> updates
              via this UI to prevent accidental exposure. To set API keys, edit{" "}
              <code className="rounded bg-amber-500/15 px-1">settings.json</code> at the repo root directly.
            </p>
          </div>
        </div>

        {/* Settings hint */}
        <div className="flex gap-3 rounded-[1rem] border border-sky-500/20 bg-sky-500/8 px-4 py-3 text-sm text-sky-300/90 backdrop-blur-sm">
          <AnimatedLucideIcon icon={Info} mode="hoverLift" className="mt-0.5 size-4 shrink-0" />
          <div>
            <p className="font-medium">Low-level settings</p>
            <p className="mt-0.5">
              Hardware overrides, vector DB connection strings, and GGUF model paths
              must be set in <code className="rounded bg-sky-500/15 px-1">settings.json</code> at
              the repo root. Changes take effect on next server restart.
            </p>
          </div>
        </div>

        {loadError && (
          <div className="flex items-center gap-1.5 text-sm text-destructive">
            <AnimatedLucideIcon icon={AlertCircle} mode="idlePulse" className="size-4" />
            {loadError}
          </div>
        )}

        {loading ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4" />
            Loading settings…
          </div>
        ) : (
          <Tabs value={activeTab} onValueChange={(value) => handleTabChange(value as SettingsTabValue)}>
            <TabsList className="glass-tab-rail h-auto w-full flex-wrap gap-1 p-1.5 group-data-horizontal/tabs:h-auto">
              <TabsTrigger value="core" className="glass-tab-pill">Core</TabsTrigger>
              <TabsTrigger value="retrieval" className="glass-tab-pill">Retrieval</TabsTrigger>
              <TabsTrigger value="graph" className="glass-tab-pill">Graph</TabsTrigger>
              <TabsTrigger value="memory" className="glass-tab-pill">Memory</TabsTrigger>
              <TabsTrigger value="provider" className="glass-tab-pill">Provider</TabsTrigger>
              <TabsTrigger value="companion" className="glass-tab-pill">Companion</TabsTrigger>
              <TabsTrigger value="models" className="glass-tab-pill">Models</TabsTrigger>
              <TabsTrigger value="privacy" className="glass-tab-pill">Privacy &amp; network</TabsTrigger>
            </TabsList>

          <form onSubmit={handleSubmit(onSubmit)} className="settings-glass-form space-y-6">

              {/* ── Core ──────────────────────────────────────────────────── */}
              <TabsContent value="core" className="glass-settings-pane mt-6 space-y-6">
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
                      <FieldLabel htmlFor="llm_provider" tooltip="The AI provider used for chat responses (e.g. anthropic, openai, local).">LLM provider</FieldLabel>
                      <Input id="llm_provider" type="text" {...register("llm_provider")} />
                      <FieldError message={errors.llm_provider?.message} />
                    </div>
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="llm_model" tooltip="The model identifier for the primary LLM (e.g. claude-opus-4-6, gpt-4o).">LLM model</FieldLabel>
                      <Input id="llm_model" type="text" {...register("llm_model")} />
                      <FieldError message={errors.llm_model?.message} />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="chat_path_RAG" tooltip="RAG grounds answers in your documents via retrieval. Direct sends prompts straight to the LLM without any context.">Query path</FieldLabel>
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
                    <FieldLabel htmlFor="selected_mode" tooltip="Q&A gives direct cited answers. Research adds sub-query expansion and graph traversal. Tutor uses Socratic back-and-forth. Evidence Pack grounds each claim. Forecast mode uses a dedicated structured path instead of these RAG-only skills.">Skill mode</FieldLabel>
                    {chatPath === "Forecast" ? (
                      <div className="rounded-xl border border-sky-500/20 bg-sky-500/8 px-4 py-3 text-sm text-sky-200/90">
                        Forecast mode uses the dedicated <code className="rounded bg-sky-500/15 px-1">selected_mode</code> value <strong>{FORECAST_SELECTED_MODE}</strong> and bypasses the RAG skill selector.
                      </div>
                    ) : (
                      <>
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
                      </>
                    )}
                  </div>

                  <div className="space-y-4 rounded-[1.2rem] border border-white/10 bg-white/[0.03] px-4 py-4">
                    <div>
                      <h3 className="text-sm font-semibold">Forecast defaults</h3>
                      <p className="mt-1 text-xs text-muted-foreground">
                        TimesFM settings used when the chat path is set to Forecast.
                      </p>
                    </div>

                    <button
                      type="button"
                      onClick={() => setForecastAdvancedOpen((prev) => !prev)}
                      className={cn(
                        "flex items-center gap-1.5 text-xs font-medium transition-colors",
                        hasAdvancedForecastErrors
                          ? "text-destructive hover:text-destructive/80"
                          : "text-muted-foreground hover:text-foreground",
                      )}
                      aria-expanded={forecastAdvancedOpen || hasAdvancedForecastErrors}
                    >
                      <ChevronDown
                        className={cn(
                          "size-3.5 transition-transform duration-150",
                          forecastAdvancedOpen || hasAdvancedForecastErrors ? "rotate-0" : "-rotate-90",
                        )}
                      />
                      Advanced
                      {hasAdvancedForecastErrors && (
                        <span className="ml-1 inline-block size-1.5 rounded-full bg-destructive" aria-hidden="true" />
                      )}
                    </button>

                    {(forecastAdvancedOpen || hasAdvancedForecastErrors) && (
                      <div className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="forecast_model_id" tooltip="TimesFM checkpoint identifier used for Forecast mode runs.">Forecast model ID</FieldLabel>
                            <Input id="forecast_model_id" type="text" {...register("forecast_model_id")} />
                            <FieldError message={errors.forecast_model_id?.message} />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="forecast_xreg_mode" tooltip="Covariate execution mode to send into TimesFM when regressors are mapped.">Forecast XReg mode</FieldLabel>
                            <select
                              id="forecast_xreg_mode"
                              {...register("forecast_xreg_mode")}
                              className="h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus:outline-none focus:ring-1 focus:ring-ring"
                            >
                              {FORECAST_XREG_MODES.map((mode) => (
                                <option key={mode} value={mode}>{mode}</option>
                              ))}
                            </select>
                            <FieldError message={errors.forecast_xreg_mode?.message} />
                          </div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="forecast_max_context" tooltip="Maximum number of historical points to pass into the TimesFM context window. TimesFM 2.5 supports substantially larger windows than the old 1k default, so METIS now defaults to a near-max 15,360-point context budget within the shared compile window.">Forecast max context</FieldLabel>
                            <Input
                              id="forecast_max_context"
                              type="number"
                              min={1}
                              max={FORECAST_MAX_CONTEXT_LIMIT}
                              {...register("forecast_max_context", { valueAsNumber: true })}
                            />
                            <FieldError message={errors.forecast_max_context?.message} />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="forecast_max_horizon" tooltip="Upper limit for horizon steps in Forecast mode. METIS now defaults to a 1k-step ceiling instead of the smaller 256-step cap.">Forecast max horizon</FieldLabel>
                            <Input
                              id="forecast_max_horizon"
                              type="number"
                              min={1}
                              max={FORECAST_MAX_HORIZON_LIMIT}
                              {...register("forecast_max_horizon", { valueAsNumber: true })}
                            />
                            <FieldError message={errors.forecast_max_horizon?.message} />
                          </div>
                        </div>
                      </div>
                    )}

                    <div className="space-y-2">
                      <ToggleRow
                        id="forecast_use_quantiles"
                        label="Forecast quantiles"
                        description="Include uncertainty bands like p10 and p90 in forecast artifacts."
                        checked={watch("forecast_use_quantiles")}
                        onChange={(value) => setValue("forecast_use_quantiles", value)}
                      />
                      <ToggleRow
                        id="forecast_force_xreg_cpu"
                        label="Force XReg on CPU"
                        description="Keep covariate-backed forecast runs on CPU for stability, especially on Windows."
                        checked={watch("forecast_force_xreg_cpu")}
                        onChange={(value) => setValue("forecast_force_xreg_cpu", value)}
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="output_style" tooltip="Affects the format and length of generated answers.">Output style</FieldLabel>
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
                      <FieldLabel htmlFor="chat_history_max_turns" tooltip="Number of past conversation turns included in each new request. Higher values give more context but cost more tokens.">History turns</FieldLabel>
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
              <TabsContent value="retrieval" className="glass-settings-pane mt-6 space-y-6">
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
                      <FieldLabel htmlFor="chunk_size" tooltip="Token size of each ingested document chunk. Smaller chunks improve precision; larger chunks preserve more context.">Chunk size</FieldLabel>
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
                      <FieldLabel htmlFor="chunk_overlap" tooltip="Overlap between consecutive chunks to avoid cutting context mid-sentence. Typically 10–20% of chunk size.">Chunk overlap</FieldLabel>
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
                      <FieldLabel htmlFor="parent_chunk_size" tooltip="Size of the parent chunk in hierarchical retrieval — a larger window of context surrounding the matched child chunk.">Parent chunk size</FieldLabel>
                      <Input
                        id="parent_chunk_size"
                        type="number"
                        min={200}
                        max={50000}
                        {...register("parent_chunk_size", { valueAsNumber: true })}
                      />
                      <FieldError message={errors.parent_chunk_size?.message} />
                    </div>
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="parent_chunk_overlap" tooltip="Overlap for parent chunks in hierarchical retrieval.">Parent chunk overlap</FieldLabel>
                      <Input
                        id="parent_chunk_overlap"
                        type="number"
                        min={0}
                        max={10000}
                        {...register("parent_chunk_overlap", { valueAsNumber: true })}
                      />
                      <FieldError message={errors.parent_chunk_overlap?.message} />
                    </div>
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="retrieval_k" tooltip="Number of candidate chunks fetched from the vector store before ranking. A higher value retrieves more candidates for reranking but is slower.">
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
                      <FieldLabel htmlFor="top_k" tooltip="Number of final chunks passed to the LLM after ranking. Keep lower for concise answers; raise for comprehensive coverage.">
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
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="knowledge_search_top_k" tooltip="Result limit for the Knowledge Search skill — how many items are surfaced in a direct knowledge-graph query.">
                        Knowledge Search top k
                      </FieldLabel>
                      <Input
                        id="knowledge_search_top_k"
                        type="number"
                        min={1}
                        max={50}
                        {...register("knowledge_search_top_k", { valueAsNumber: true })}
                      />
                      <FieldError message={errors.knowledge_search_top_k?.message} />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="retrieval_mode" tooltip="flat — basic similarity; mmr — diverse results; hybrid — combines vector + keyword; hierarchical — parent/child chunk retrieval.">Retrieval mode</FieldLabel>
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
                      <FieldLabel htmlFor="search_type" tooltip="similarity — direct vector cosine search; mmr — Maximal Marginal Relevance to balance relevance and diversity.">Search type</FieldLabel>
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
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="retrieval_min_score" tooltip="Minimum cosine similarity score (0–1) required to include a chunk in results. Raise to filter out weak matches; lower to retrieve more broadly.">Retrieval min score</FieldLabel>
                      <Input
                        id="retrieval_min_score"
                        type="number"
                        min={0}
                        max={1}
                        step={0.01}
                        {...register("retrieval_min_score", { valueAsNumber: true })}
                      />
                      <FieldError message={errors.retrieval_min_score?.message} />
                    </div>
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="fallback_strategy" tooltip="synthesize_anyway — generate an answer even with weak retrieval; no_answer — refuse and show the fallback message.">Fallback strategy</FieldLabel>
                      <select
                        id="fallback_strategy"
                        {...register("fallback_strategy")}
                        className="h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus:outline-none focus:ring-1 focus:ring-ring"
                      >
                        {FALLBACK_STRATEGIES.map((strategy) => (
                          <option key={strategy} value={strategy}>{strategy}</option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="mmr_lambda" tooltip="Maximal Marginal Relevance trade-off. 0 maximises diversity among retrieved chunks; 1 maximises relevance to the query.">
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
                      className="glass-slider"
                      style={{ "--slider-progress": `${Math.round(Number(mmrLambda) * 100)}%` } as CSSProperties}
                    />
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>0 — max diversity</span>
                      <span>1 — max relevance</span>
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="hybrid_alpha" tooltip="Controls the blend between keyword (BM25) and vector search. 1.0 = pure vector (default). 0.5 = equal weight — recommended for exact-phrase or technical queries. 0.0 = pure keyword.">
                      Hybrid search alpha{" "}
                      <span className="font-normal text-muted-foreground">
                        (keyword ↔ vector) — {Number(hybridAlpha).toFixed(2)}
                      </span>
                    </FieldLabel>
                    <input
                      id="hybrid_alpha"
                      type="range"
                      min={0}
                      max={1}
                      step={0.05}
                      {...register("hybrid_alpha", { valueAsNumber: true })}
                      className="glass-slider"
                      style={{ "--slider-progress": `${Math.round(Number(hybridAlpha) * 100)}%` } as CSSProperties}
                    />
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>0 — pure keyword (BM25)</span>
                      <span>1 — pure vector</span>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="subquery_max_docs" tooltip="Maximum total documents fetched across all sub-queries during an agentic research pass.">Sub-query max docs</FieldLabel>
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
                      <FieldLabel htmlFor="document_loader" tooltip="auto — kreuzberg (75+ formats); plain — UTF-8 text only; opendataloader — highest-accuracy PDF extraction (bundled, no Java install needed).">Document loader</FieldLabel>
                      <select
                        id="document_loader"
                        {...register("document_loader")}
                        className="h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus:outline-none focus:ring-1 focus:ring-ring"
                      >
                        {DOCUMENT_LOADERS.map((d) => (
                          <option key={d.value} value={d.value}>{d.label}</option>
                        ))}
                      </select>
                      <FieldError message={errors.document_loader?.message} />
                    </div>
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="comprehension_extraction_depth" tooltip="Standard — quick single-pass analysis; Deep — multi-pass with cross-referencing; Exhaustive — maximum depth (slowest, highest quality).">Comprehension depth</FieldLabel>
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
                      <FieldLabel htmlFor="agentic_max_iterations" tooltip="Maximum refinement cycles when agentic mode is enabled. More iterations can improve quality at the cost of latency.">Agentic max iterations</FieldLabel>
                      <Input
                        id="agentic_max_iterations"
                        type="number"
                        min={1}
                        max={10}
                        {...register("agentic_max_iterations", { valueAsNumber: true })}
                      />
                      <FieldError message={errors.agentic_max_iterations?.message} />
                    </div>
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="agentic_iteration_budget" tooltip="Total iteration budget for the convergence loop. The loop exits early if the answer converges before reaching this limit.">Iteration budget</FieldLabel>
                      <Input
                        id="agentic_iteration_budget"
                        type="number"
                        min={1}
                        max={10}
                        {...register("agentic_iteration_budget", { valueAsNumber: true })}
                      />
                      <FieldError message={errors.agentic_iteration_budget?.message} />
                    </div>
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="agentic_convergence_threshold" tooltip="Cosine similarity threshold (0–1) between successive drafts. When similarity exceeds this value the loop exits early.">Convergence threshold</FieldLabel>
                      <Input
                        id="agentic_convergence_threshold"
                        type="number"
                        min={0}
                        max={1}
                        step={0.01}
                        {...register("agentic_convergence_threshold", { valueAsNumber: true })}
                      />
                      <FieldError message={errors.agentic_convergence_threshold?.message} />
                    </div>
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="swarm_n_personas" tooltip="Number of AI personas simulated in each swarm debate round. Higher values increase answer diversity at the cost of latency.">Swarm personas</FieldLabel>
                      <Input
                        id="swarm_n_personas"
                        type="number"
                        min={1}
                        max={32}
                        {...register("swarm_n_personas", { valueAsNumber: true })}
                      />
                      <FieldError message={errors.swarm_n_personas?.message} />
                    </div>
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="swarm_n_rounds" tooltip="Number of debate rounds between swarm personas before producing the final answer.">Swarm rounds</FieldLabel>
                      <Input
                        id="swarm_n_rounds"
                        type="number"
                        min={1}
                        max={16}
                        {...register("swarm_n_rounds", { valueAsNumber: true })}
                      />
                      <FieldError message={errors.swarm_n_rounds?.message} />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="fallback_message" tooltip="The message shown to the user when retrieval quality falls below the minimum score threshold.">Fallback message</FieldLabel>
                    <Textarea
                      id="fallback_message"
                      rows={3}
                      {...register("fallback_message")}
                      placeholder="Shown when the retrieval score falls below the configured threshold."
                    />
                    <p className="text-xs text-muted-foreground">
                      Used when retrieval quality is below the minimum score threshold.
                    </p>
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
                      label="Enable summariser"
                      description="Summarise long context windows before passing to the LLM."
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
              <TabsContent value="graph" className="glass-settings-pane mt-6 space-y-6">
                <section className="space-y-4">
                  <div>
                    <h2 className="text-base font-semibold">Advanced graph controls</h2>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Knowledge graph query mode and graph-augmented extraction features.
                    </p>
                  </div>
                  <Separator />

                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="kg_query_mode" tooltip="hybrid — combines vector similarity and keyword BM25; vector — embedding-only search; keyword — BM25 only (fast, no embeddings needed).">Knowledge graph query mode</FieldLabel>
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
                    <ToggleRow
                      id="build_llm_knowledge_graph"
                      label="LLM knowledge graph enrichment"
                      description="Use the primary LLM to extract entities and relations during indexing, enriching the knowledge graph beyond regex heuristics."
                      checked={watch("build_llm_knowledge_graph")}
                      onChange={(v) => setValue("build_llm_knowledge_graph", v)}
                    />
                    <ToggleRow
                      id="web_scrape_full_content"
                      label="Web graph: full-page scrape"
                      description="Scrape the full page content (up to 2000 chars) when building web graph indexes. When off, uses a 1000-char preview."
                      checked={watch("web_scrape_full_content")}
                      onChange={(v) => setValue("web_scrape_full_content", v)}
                    />
                  </div>
                </section>
              </TabsContent>

              {/* ── Advanced Memory ────────────────────────────────────────── */}
              <TabsContent value="memory" className="glass-settings-pane mt-6 space-y-6">
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
                    <FieldLabel htmlFor="system_instructions" tooltip="Custom system prompt that shapes the LLM's behaviour and persona. Leave blank to use the built-in METIS default.">System instructions</FieldLabel>
                    <Textarea
                      id="system_instructions"
                      rows={5}
                      {...register("system_instructions")}
                      placeholder="Override the default system prompt sent to the LLM. Leave blank to use the built-in default."
                    />
                    <p className="text-xs text-muted-foreground">
                      Leave blank to use the built-in default system prompt.
                    </p>
                  </div>
                </section>
              </TabsContent>

              {/* ── Advanced Model / Provider ──────────────────────────────── */}
              <TabsContent value="provider" className="glass-settings-pane mt-6 space-y-6">
                <section className="space-y-4">
                  <div>
                    <h2 className="text-base font-semibold">Advanced model / provider controls</h2>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      LLM generation parameters, embedding provider, and local LLM settings.
                    </p>
                  </div>
                  <Separator />

                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="llm_temperature" tooltip="Controls output randomness. 0 = fully deterministic (best for factual Q&A). 1 = balanced. 2 = highly creative and variable.">
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
                      className="glass-slider"
                      style={{ "--slider-progress": `${Math.round((Number(llmTemp) / 2) * 100)}%` } as CSSProperties}
                    />
                    <div className="flex justify-between text-xs text-muted-foreground">
                      <span>0 — deterministic</span>
                      <span>2 — creative</span>
                    </div>
                    <FieldError message={errors.llm_temperature?.message} />
                  </div>

                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="llm_max_tokens" tooltip="Maximum tokens the LLM may generate in a single response. Raise for longer answers; lower to reduce cost and latency.">Max tokens</FieldLabel>
                    <Input
                      id="llm_max_tokens"
                      type="number"
                      min={64}
                      max={32768}
                      {...register("llm_max_tokens", { valueAsNumber: true })}
                      className="max-w-50"
                    />
                    <FieldError message={errors.llm_max_tokens?.message} />
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="embedding_provider" tooltip="Provider used to generate text embeddings for vector search (e.g. voyage, openai, local).">Embedding provider</FieldLabel>
                      <Input id="embedding_provider" type="text" {...register("embedding_provider")} />
                      <FieldError message={errors.embedding_provider?.message} />
                    </div>
                    <div className="space-y-1.5">
                      <FieldLabel htmlFor="embedding_model" tooltip="Embedding model identifier (e.g. voyage-4-large, text-embedding-3-small).">Embedding model</FieldLabel>
                      <Input id="embedding_model" type="text" {...register("embedding_model")} />
                      <FieldError message={errors.embedding_model?.message} />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <FieldLabel htmlFor="local_llm_url" tooltip="OpenAI-compatible REST endpoint for local LLM inference, e.g. LM Studio (http://localhost:1234/v1) or Ollama (http://localhost:11434/v1).">Local LLM URL</FieldLabel>
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

              {/* ── Companion ─────────────────────────────────────────────── */}
              <TabsContent value="companion" className="glass-settings-pane mt-6 space-y-6">
                <section className="space-y-4">
                  <div>
                    <h2 className="text-base font-semibold">Companion assistant settings</h2>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Tune the docked assistant identity, runtime, and reflection policy.
                    </p>
                  </div>
                  <Separator />

                  {assistantLoadError && (
                    <div className="flex items-center gap-1.5 text-sm text-destructive">
                      <AnimatedLucideIcon icon={AlertCircle} mode="idlePulse" className="size-4" />
                      {assistantLoadError}
                    </div>
                  )}

                  {assistantLoading ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground">
                      <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4" />
                      Loading companion settings…
                    </div>
                  ) : (
                    <div className="space-y-6">
                      <BorderBeam size="md" colorVariant="mono" strength={0.55}>
                      <div className="space-y-4 rounded-2xl border border-white/8 bg-black/10 p-4">
                        <div>
                          <h3 className="text-sm font-semibold">Assistant identity</h3>
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            Name, greeting, and dock behaviour for the companion.
                          </p>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_identity.assistant_id">Assistant ID</FieldLabel>
                            <Input
                              id="assistant_identity.assistant_id"
                              type="text"
                              {...registerAssistant("assistant_identity.assistant_id")}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_identity.name">Name</FieldLabel>
                            <Input
                              id="assistant_identity.name"
                              type="text"
                              {...registerAssistant("assistant_identity.name")}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_identity.archetype">Archetype</FieldLabel>
                            <Input
                              id="assistant_identity.archetype"
                              type="text"
                              {...registerAssistant("assistant_identity.archetype")}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_identity.greeting">Greeting</FieldLabel>
                            <Input
                              id="assistant_identity.greeting"
                              type="text"
                              {...registerAssistant("assistant_identity.greeting")}
                            />
                          </div>
                        </div>

                        <div className="space-y-1.5">
                          <FieldLabel htmlFor="assistant_identity.prompt_seed" tooltip="Seed prompt used to shape the companion's personality, tone, and boundaries.">Prompt seed</FieldLabel>
                          <Textarea
                            id="assistant_identity.prompt_seed"
                            rows={5}
                            {...registerAssistant("assistant_identity.prompt_seed")}
                            placeholder="Seed prompt used to shape the companion's tone and behaviour."
                          />
                        </div>

                        <div className="space-y-2">
                          <ToggleRow
                            id="assistant_identity.companion_enabled"
                            label="Companion enabled"
                            description="Show the assistant companion in the dock."
                            checked={watchAssistant("assistant_identity.companion_enabled")}
                            onChange={(v) => setAssistantValue("assistant_identity.companion_enabled", v)}
                          />
                          <ToggleRow
                            id="assistant_identity.docked"
                            label="Docked"
                            description="Keep the companion visible as a docked panel."
                            checked={watchAssistant("assistant_identity.docked")}
                            onChange={(v) => setAssistantValue("assistant_identity.docked", v)}
                          />
                          <ToggleRow
                            id="assistant_identity.minimized"
                            label="Start minimized"
                            description="Collapse the companion by default."
                            checked={watchAssistant("assistant_identity.minimized")}
                            onChange={(v) => setAssistantValue("assistant_identity.minimized", v)}
                          />
                        </div>
                      </div>
                      </BorderBeam>

                      <div className="space-y-4">
                        <div>
                          <h3 className="text-sm font-semibold">Runtime</h3>
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            Configure the local or remote model source used by the companion.
                          </p>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_runtime.provider">Provider</FieldLabel>
                            <Input
                              id="assistant_runtime.provider"
                              type="text"
                              {...registerAssistant("assistant_runtime.provider")}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_runtime.model">Model</FieldLabel>
                            <Input
                              id="assistant_runtime.model"
                              type="text"
                              {...registerAssistant("assistant_runtime.model")}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_runtime.local_gguf_model_path">GGUF path</FieldLabel>
                            <Input
                              id="assistant_runtime.local_gguf_model_path"
                              type="text"
                              {...registerAssistant("assistant_runtime.local_gguf_model_path")}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_runtime.bootstrap_state">Bootstrap state</FieldLabel>
                            <Input
                              id="assistant_runtime.bootstrap_state"
                              type="text"
                              {...registerAssistant("assistant_runtime.bootstrap_state")}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_runtime.local_gguf_context_length">
                              Context length
                            </FieldLabel>
                            <Input
                              id="assistant_runtime.local_gguf_context_length"
                              type="number"
                              min={512}
                              {...registerAssistant("assistant_runtime.local_gguf_context_length", {
                                valueAsNumber: true,
                              })}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_runtime.local_gguf_gpu_layers">GPU layers</FieldLabel>
                            <Input
                              id="assistant_runtime.local_gguf_gpu_layers"
                              type="number"
                              min={0}
                              {...registerAssistant("assistant_runtime.local_gguf_gpu_layers", {
                                valueAsNumber: true,
                              })}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_runtime.local_gguf_threads">Threads</FieldLabel>
                            <Input
                              id="assistant_runtime.local_gguf_threads"
                              type="number"
                              min={0}
                              {...registerAssistant("assistant_runtime.local_gguf_threads", {
                                valueAsNumber: true,
                              })}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_runtime.recommended_model_name">Recommended model</FieldLabel>
                            <Input
                              id="assistant_runtime.recommended_model_name"
                              type="text"
                              {...registerAssistant("assistant_runtime.recommended_model_name")}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_runtime.recommended_quant">Recommended quant</FieldLabel>
                            <Input
                              id="assistant_runtime.recommended_quant"
                              type="text"
                              {...registerAssistant("assistant_runtime.recommended_quant")}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_runtime.recommended_use_case">Recommended use case</FieldLabel>
                            <Input
                              id="assistant_runtime.recommended_use_case"
                              type="text"
                              {...registerAssistant("assistant_runtime.recommended_use_case")}
                            />
                          </div>
                        </div>

                        <div className="space-y-2">
                          <ToggleRow
                            id="assistant_runtime.fallback_to_primary"
                            label="Fallback to primary"
                            description="Use the main workspace model when the companion runtime is unavailable."
                            checked={watchAssistant("assistant_runtime.fallback_to_primary")}
                            onChange={(v) => setAssistantValue("assistant_runtime.fallback_to_primary", v)}
                          />
                          <ToggleRow
                            id="assistant_runtime.auto_bootstrap"
                            label="Auto bootstrap"
                            description="Automatically prepare the companion runtime when needed."
                            checked={watchAssistant("assistant_runtime.auto_bootstrap")}
                            onChange={(v) => setAssistantValue("assistant_runtime.auto_bootstrap", v)}
                          />
                          <ToggleRow
                            id="assistant_runtime.auto_install"
                            label="Auto install"
                            description="Allow the app to install a recommended local model automatically."
                            checked={watchAssistant("assistant_runtime.auto_install")}
                            onChange={(v) => setAssistantValue("assistant_runtime.auto_install", v)}
                          />
                        </div>
                      </div>

                      <div className="space-y-4">
                        <div>
                          <h3 className="text-sm font-semibold">Policy</h3>
                          <p className="mt-0.5 text-xs text-muted-foreground">
                            Control reflection behaviour and memory growth limits.
                          </p>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_policy.reflection_backend">Reflection backend</FieldLabel>
                            <Input
                              id="assistant_policy.reflection_backend"
                              type="text"
                              {...registerAssistant("assistant_policy.reflection_backend")}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_policy.reflection_cooldown_seconds">
                              Reflection cooldown
                            </FieldLabel>
                            <Input
                              id="assistant_policy.reflection_cooldown_seconds"
                              type="number"
                              min={0}
                              {...registerAssistant("assistant_policy.reflection_cooldown_seconds", {
                                valueAsNumber: true,
                              })}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_policy.max_memory_entries">Max memory entries</FieldLabel>
                            <Input
                              id="assistant_policy.max_memory_entries"
                              type="number"
                              min={1}
                              {...registerAssistant("assistant_policy.max_memory_entries", {
                                valueAsNumber: true,
                              })}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_policy.max_playbooks">Max playbooks</FieldLabel>
                            <Input
                              id="assistant_policy.max_playbooks"
                              type="number"
                              min={1}
                              {...registerAssistant("assistant_policy.max_playbooks", {
                                valueAsNumber: true,
                              })}
                            />
                          </div>
                          <div className="space-y-1.5">
                            <FieldLabel htmlFor="assistant_policy.max_brain_links">Max brain links</FieldLabel>
                            <Input
                              id="assistant_policy.max_brain_links"
                              type="number"
                              min={1}
                              {...registerAssistant("assistant_policy.max_brain_links", {
                                valueAsNumber: true,
                              })}
                            />
                          </div>
                        </div>

                        <div className="space-y-2">
                          <ToggleRow
                            id="assistant_policy.reflection_enabled"
                            label="Reflection enabled"
                            description="Allow the assistant to summarise and reflect on completed work."
                            checked={watchAssistant("assistant_policy.reflection_enabled")}
                            onChange={(v) => setAssistantValue("assistant_policy.reflection_enabled", v)}
                          />
                          <ToggleRow
                            id="assistant_policy.autonomous_research_enabled"
                            label="Autonomous Research"
                            description="Allow METIS to research sparse areas of your constellation and add new stars independently."
                            checked={watchAssistant("assistant_policy.autonomous_research_enabled") ?? false}
                            onChange={(v) => setAssistantValue("assistant_policy.autonomous_research_enabled", v)}
                          />
                          <ToggleRow
                            id="assistant_policy.trigger_on_onboarding"
                            label="Trigger on onboarding"
                            description="Run the assistant after onboarding-related events."
                            checked={watchAssistant("assistant_policy.trigger_on_onboarding")}
                            onChange={(v) => setAssistantValue("assistant_policy.trigger_on_onboarding", v)}
                          />
                          <ToggleRow
                            id="assistant_policy.trigger_on_index_build"
                            label="Trigger on index build"
                            description="Reflect after new indexes finish building."
                            checked={watchAssistant("assistant_policy.trigger_on_index_build")}
                            onChange={(v) => setAssistantValue("assistant_policy.trigger_on_index_build", v)}
                          />
                          <ToggleRow
                            id="assistant_policy.trigger_on_completed_run"
                            label="Trigger on completed run"
                            description="Reflect after finished chat or tool runs."
                            checked={watchAssistant("assistant_policy.trigger_on_completed_run")}
                            onChange={(v) => setAssistantValue("assistant_policy.trigger_on_completed_run", v)}
                          />
                          <ToggleRow
                            id="assistant_policy.allow_automatic_writes"
                            label="Allow automatic writes"
                            description="Let the assistant store reflections and memory entries automatically."
                            checked={watchAssistant("assistant_policy.allow_automatic_writes")}
                            onChange={(v) => setAssistantValue("assistant_policy.allow_automatic_writes", v)}
                          />
                        </div>

                        <div className="flex items-center gap-3">
                          <Button
                            type="button"
                            onClick={() => void handleAssistantSubmit(onAssistantSubmit)()}
                            disabled={assistantSaving}
                            className="gap-1.5"
                          >
                            {assistantSaving && <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4" />}
                            {assistantSaving ? "Saving…" : "Save companion settings"}
                          </Button>
                          {assistantSaved && (
                            <span className={cn("flex items-center gap-1.5 text-sm text-green-600 dark:text-green-400")}>
                              <AnimatedLucideIcon icon={CheckCircle2} mode="idlePulse" className="size-4" />
                              Saved
                            </span>
                          )}
                        </div>
                        {assistantSaveError && (
                          <div className="flex items-center gap-1.5 text-sm text-destructive">
                            <AnimatedLucideIcon icon={AlertCircle} mode="idlePulse" className="size-4" />
                            {assistantSaveError}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </section>
              </TabsContent>

            {/* Save controls — sticky at bottom */}
            <div className="sticky bottom-0 z-10 flex items-center gap-3 rounded-b-[1.35rem] border-t border-white/8 bg-card/90 px-4 py-3 backdrop-blur-md">
              <Button type="submit" disabled={saving} className="gap-1.5">
                {saving && <AnimatedLucideIcon icon={Loader2} mode="spin" className="size-4" />}
                {saving ? "Saving…" : "Save settings"}
              </Button>

              {saved && (
                <span className={cn("flex items-center gap-1.5 text-sm text-green-600 dark:text-green-400")}>
                  <AnimatedLucideIcon icon={CheckCircle2} mode="idlePulse" className="size-4" />
                  Saved
                </span>
              )}

              {saveError && (
                <span className="flex items-center gap-1.5 text-sm text-destructive">
                  <AnimatedLucideIcon icon={AlertCircle} mode="idlePulse" className="size-4" />
                  {saveError}
                </span>
              )}
            </div>
          </form>

            {/* ── Models (GGUF) ──────────────────────────────────────── */}
            <TabsContent value="models" className="glass-settings-pane mt-6">
              <GgufModelsPanel
                initialModelsTab={initialModelsTab}
                initialHereticModelId={initialHereticModelId}
              />
            </TabsContent>

            {/* ── Privacy & network audit ────────────────────────────── */}
            <TabsContent value="privacy" className="glass-settings-pane mt-6 space-y-4">
              <section className="space-y-3">
                <div>
                  <h2 className="text-base font-semibold">Privacy &amp; network audit</h2>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Every outbound call METIS makes is recorded in a local
                    audit store. The privacy panel shows the live feed,
                    per-provider matrix, and airplane-mode indicator.
                  </p>
                </div>
                <Separator />
                <p className="text-sm text-muted-foreground">
                  Read-only in this build. Kill-switch toggles, CSV export,
                  and the &ldquo;prove offline&rdquo; button land in the next update
                  (Phase 5c).
                </p>
                <div>
                  <a
                    href="/settings/privacy"
                    className="inline-flex items-center gap-2 rounded-lg border border-border/50 bg-card/40 px-4 py-2 text-sm font-medium text-foreground transition-colors hover:bg-muted/40"
                  >
                    Open privacy panel →
                  </a>
                </div>
              </section>
            </TabsContent>
          </Tabs>
        )}
      </div>
      </TooltipProvider>
    </PageChrome>
  );
}
