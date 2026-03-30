"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AmbientBackdrop } from "@/components/shell/ambient-backdrop";
import { MetisCompanionDock } from "@/components/shell/metis-companion-dock";
import { OnboardingStep } from "@/components/shell/onboarding-step";
import { StatusPill } from "@/components/shell/status-pill";
import { IndexBuildStudio } from "@/components/library/index-build-studio";
import {
  fetchSettings,
  reflectAssistant,
  updateSettings,
  type IndexBuildResult,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { AnimatedLucideIcon } from "@/components/ui/animated-lucide-icon";
import {
  ArrowLeft,
  ArrowRight,
  BetweenHorizontalEnd,
  CheckCircle2,
  Database,
  KeyRound,
  Sparkles,
} from "lucide-react";
import { BrainIcon } from "@/components/icons";
import { useArrowState } from "@/hooks/use-arrow-state";

const LLM_PROVIDERS = [
  {
    value: "anthropic",
    label: "Anthropic",
    description:
      "Strong writing quality and research synthesis out of the box.",
  },
  {
    value: "openai",
    label: "OpenAI",
    description: "Balanced reasoning, tool use, and a broad model lineup.",
  },
  {
    value: "local",
    label: "Local model",
    description:
      "Keep inference on-device when you prefer a fully local stack.",
  },
] as const;

const EMBEDDING_PROVIDERS = [
  {
    value: "openai",
    label: "OpenAI embeddings",
    description: "A fast default for most hosted setups.",
  },
  {
    value: "local",
    label: "Local embeddings",
    description: "Good when you want indexing to stay on your machine.",
  },
] as const;

const STEP_HINTS = [
  "Choose your chat model provider. You can change it later in Settings.",
  "Add credentials only if needed. Local mode can stay blank.",
  "Choose how documents are embedded for indexing and retrieval.",
  "Optional: build a first index now for grounded chat.",
  "Choose a starter prompt. It is staged, not auto-sent.",
];

const STARTER_PROMPTS_WITH_INDEX = [
  "Give me a fast overview of what is inside this index and what kinds of questions it can answer.",
  "What are the most important themes or findings in these documents?",
  "Suggest three high-value questions I should ask next based on this material.",
];

const STARTER_PROMPTS_DIRECT = [
  "Help me plan my first workflow in METIS and explain when to use direct chat versus RAG.",
  "Teach me how to set up a grounded research session in this workspace.",
  "What should I import first if I want METIS to feel useful within ten minutes?",
];

export default function SetupPage() {
  const router = useRouter();
  const [step, setStep] = useArrowState(0);
  const [llmProvider, setLlmProvider] =
    useArrowState<(typeof LLM_PROVIDERS)[number]["value"]>("anthropic");
  const [apiKey, setApiKey] = useArrowState("");
  const [embeddingProvider, setEmbeddingProvider] =
    useArrowState<(typeof EMBEDDING_PROVIDERS)[number]["value"]>("openai");
  const [baselineSettings, setBaselineSettings] = useArrowState<
    Record<string, unknown>
  >({});
  const [builtIndex, setBuiltIndex] = useArrowState<IndexBuildResult | null>(
    null,
  );
  const [selectedPrompt, setSelectedPrompt] = useArrowState<string>("");
  const [saving, setSaving] = useArrowState(false);
  const [error, setError] = useArrowState<string | null>(null);

  useEffect(() => {
    fetchSettings()
      .then((settings) => {
        setBaselineSettings(settings);
        if (typeof settings.llm_provider === "string") {
          const candidate = settings.llm_provider as string;
          if (LLM_PROVIDERS.some((provider) => provider.value === candidate)) {
            setLlmProvider(
              candidate as (typeof LLM_PROVIDERS)[number]["value"],
            );
          }
        }
        if (typeof settings.embedding_provider === "string") {
          const candidate = settings.embedding_provider as string;
          if (
            EMBEDDING_PROVIDERS.some((provider) => provider.value === candidate)
          ) {
            setEmbeddingProvider(
              candidate as (typeof EMBEDDING_PROVIDERS)[number]["value"],
            );
          }
        }
      })
      .catch(() => {
        // The onboarding flow can still proceed with sane defaults.
      });
  }, [setBaselineSettings, setEmbeddingProvider, setLlmProvider]);

  const starterPrompts = builtIndex
    ? STARTER_PROMPTS_WITH_INDEX
    : STARTER_PROMPTS_DIRECT;

  useEffect(() => {
    setSelectedPrompt((current) => {
      if (starterPrompts.includes(current)) {
        return current;
      }
      return starterPrompts[0];
    });
  }, [setSelectedPrompt, starterPrompts]);

  const buildSettings = useMemo(() => {
    const nextSettings: Record<string, unknown> = {
      ...baselineSettings,
      llm_provider: llmProvider,
      embedding_provider: embeddingProvider,
      basic_wizard_completed: false,
    };
    if (apiKey) {
      const keyField =
        llmProvider === "anthropic"
          ? "api_key_anthropic"
          : llmProvider === "openai"
            ? "api_key_openai"
            : null;
      if (keyField) {
        nextSettings[keyField] = apiKey;
      }
    }
    return nextSettings;
  }, [apiKey, baselineSettings, embeddingProvider, llmProvider]);

  async function handleFinish() {
    setSaving(true);
    setError(null);

    try {
      const updates: Record<string, unknown> = {
        llm_provider: llmProvider,
        embedding_provider: embeddingProvider,
        basic_wizard_completed: true,
      };

      if (apiKey) {
        const keyField =
          llmProvider === "anthropic"
            ? "api_key_anthropic"
            : llmProvider === "openai"
              ? "api_key_openai"
              : null;
        if (keyField) {
          updates[keyField] = apiKey;
        }
      }

      await updateSettings(updates);

      void reflectAssistant({
        trigger: "onboarding",
        context_id: "onboarding:primary",
      }).catch(() => {
        // Reflection is best-effort so the onboarding flow can continue.
      });

      if (builtIndex) {
        localStorage.setItem(
          "metis_active_index",
          JSON.stringify({
            manifest_path: builtIndex.manifest_path,
            label: builtIndex.index_id,
          }),
        );
      }

      localStorage.setItem("metis_chat_seed_prompt", selectedPrompt);
      router.push("/chat");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  const steps = [
    {
      title: "Choose the primary model provider",
      description:
        "This provider is used for direct chat and synthesis. You can change it later.",
      content: (
        <div className="grid gap-4 md:grid-cols-3">
          {LLM_PROVIDERS.map((provider) => {
            const active = provider.value === llmProvider;
            return (
              <button
                key={provider.value}
                type="button"
                onClick={() => setLlmProvider(provider.value)}
                className={cn(
                  "cursor-pointer rounded-[1.5rem] border p-5 text-left transition-all duration-200",
                  active
                    ? "border-primary/30 bg-primary/12 shadow-lg shadow-primary/10"
                    : "border-white/8 bg-black/10 hover:border-primary/16 hover:bg-white/6",
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="font-display text-2xl font-semibold tracking-[-0.04em] text-foreground">
                    {provider.label}
                  </span>
                  {active ? (
                    <CheckCircle2 className="size-5 text-primary" />
                  ) : null}
                </div>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">
                  {provider.description}
                </p>
              </button>
            );
          })}
        </div>
      ),
      hint: STEP_HINTS[0],
    },
    {
      title: "Add credentials only if I need them",
      description:
        llmProvider === "local"
          ? "Local model mode does not require a hosted API key. You can continue immediately or add one later if you switch providers."
          : "Paste the API key for the selected provider. You can also add it later in settings.",
      content: (
        <div className="space-y-5">
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_220px]">
            <div className="space-y-3">
              <label
                htmlFor="api_key"
                className="text-sm font-medium text-foreground"
              >
                {llmProvider === "anthropic"
                  ? "Anthropic API key"
                  : llmProvider === "openai"
                    ? "OpenAI API key"
                    : "Optional API key"}
              </label>
              <Input
                id="api_key"
                type="password"
                placeholder={llmProvider === "local" ? "Optional" : "sk-..."}
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
              />
              <p className="text-sm leading-7 text-muted-foreground">
                {llmProvider === "local"
                  ? "Leave this blank if you’re staying fully local."
                  : "If you skip this now, you can still add it later in your settings file."}
              </p>
            </div>

            <div className="rounded-[1.45rem] border border-white/8 bg-black/10 p-4">
              <AnimatedLucideIcon
                icon={KeyRound}
                mode="hoverLift"
                className="size-5 text-primary"
              />
              <p className="mt-3 font-medium text-foreground">
                Credential posture
              </p>
              <p className="mt-2 text-sm leading-7 text-muted-foreground">
                Keys are not echoed back in the UI. They are only forwarded to
                the backend settings update when you finish onboarding.
              </p>
            </div>
          </div>
        </div>
      ),
      hint: STEP_HINTS[1],
    },
    {
      title: "Choose how I should embed documents",
      description:
        "Embeddings power document similarity, search quality, and grounded answers. This decision mostly affects indexing, not direct chat.",
      content: (
        <div className="grid gap-4 md:grid-cols-2">
          {EMBEDDING_PROVIDERS.map((provider) => {
            const active = provider.value === embeddingProvider;
            return (
              <button
                key={provider.value}
                type="button"
                onClick={() => setEmbeddingProvider(provider.value)}
                className={cn(
                  "cursor-pointer rounded-[1.5rem] border p-5 text-left transition-all duration-200",
                  active
                    ? "border-primary/30 bg-primary/12 shadow-lg shadow-primary/10"
                    : "border-white/8 bg-black/10 hover:border-primary/16 hover:bg-white/6",
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <AnimatedLucideIcon
                      icon={BetweenHorizontalEnd}
                      mode={active ? "idlePulse" : "hoverLift"}
                      active={active || undefined}
                      className={cn(
                        "size-4",
                        active ? "text-primary" : "text-muted-foreground",
                      )}
                    />
                    <span className="font-display text-2xl font-semibold tracking-[-0.04em] text-foreground">
                      {provider.label}
                    </span>
                  </div>
                  {active ? (
                    <CheckCircle2 className="size-5 text-primary" />
                  ) : null}
                </div>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">
                  {provider.description}
                </p>
              </button>
            );
          })}
        </div>
      ),
      hint: STEP_HINTS[2],
    },
    {
      title: "Build the first knowledge base",
      description:
        "Indexing a small set of documents here makes the app feel useful immediately. You can skip this and import more later, but a quick first index is the smoothest path into chat.",
      content: (
        <IndexBuildStudio
          settingsOverrides={buildSettings}
          showExistingIndexes={false}
          onIndexBuilt={setBuiltIndex}
          successMode="onboarding"
        />
      ),
      hint: STEP_HINTS[3],
    },
    {
      title: "Stage your first question",
      description:
        "A starter prompt is placed in the composer. Nothing is auto-sent.",
      content: (
        <div className="space-y-6">
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
            <div className="space-y-4">
              <div className="grid gap-3">
                {starterPrompts.map((prompt) => {
                  const active = prompt === selectedPrompt;
                  return (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => setSelectedPrompt(prompt)}
                      className={cn(
                        "cursor-pointer rounded-[1.4rem] border p-4 text-left transition-all duration-200",
                        active
                          ? "border-primary/30 bg-primary/12"
                          : "border-white/8 bg-black/10 hover:border-primary/16 hover:bg-white/6",
                      )}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <p className="text-sm leading-7 text-foreground">
                          {prompt}
                        </p>
                        {active ? (
                          <AnimatedLucideIcon
                            icon={Sparkles}
                            mode="idlePulse"
                            className="size-4 text-primary"
                          />
                        ) : null}
                      </div>
                    </button>
                  );
                })}
              </div>

              {error ? (
                <div className="rounded-[1.3rem] border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  {error}
                </div>
              ) : null}
            </div>

            <div className="rounded-[1.55rem] border border-white/8 bg-black/10 p-5">
              <p className="text-xs uppercase tracking-[0.28em] text-muted-foreground">
                Launch summary
              </p>
              <div className="mt-4 space-y-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-muted-foreground">LLM provider</span>
                  <span className="text-foreground">{llmProvider}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-muted-foreground">Embeddings</span>
                  <span className="text-foreground">{embeddingProvider}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="text-muted-foreground">First index</span>
                  <span className="text-foreground">
                    {builtIndex ? builtIndex.index_id : "Not built yet"}
                  </span>
                </div>
              </div>

              <div className="mt-5 flex flex-wrap gap-2">
                <StatusPill
                  label={builtIndex ? "RAG ready" : "Direct chat ready"}
                  tone={builtIndex ? "connected" : "neutral"}
                />
                <StatusPill label="Starter prompt staged" tone="neutral" />
              </div>

              <p className="mt-4 text-sm leading-7 text-muted-foreground">
                {builtIndex
                  ? "Opens chat with this index preselected and a starter prompt staged."
                  : "Opens direct chat with a starter prompt staged."}
              </p>
            </div>
          </div>
        </div>
      ),
      hint: STEP_HINTS[4],
    },
  ];

  return (
    <div className="relative min-h-screen overflow-hidden">
      <AmbientBackdrop />

      <div className="relative z-10 mx-auto flex min-h-screen max-w-7xl flex-col px-4 pb-8 pt-4 sm:px-6 lg:px-8">
        <header className="glass-panel flex flex-wrap items-center gap-3 rounded-2xl px-4 py-3 sm:px-5">
          <div>
            <p className="text-lg font-semibold tracking-tight text-foreground">
              METIS Setup
            </p>
            <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
              Setup
            </p>
          </div>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <StatusPill
              label={`Step ${step + 1} of ${steps.length}`}
              tone="checking"
            />
            <Link href="/">
              <Button variant="outline" size="sm">
                Back to home
              </Button>
            </Link>
          </div>
        </header>

        <main className="flex-1 py-8">
          <section className="mb-6">
            <div className="glass-panel rounded-2xl px-5 py-5 sm:px-6">
              <p className="text-xs font-medium uppercase tracking-[0.2em] text-primary/80">
                Quick setup
              </p>
              <h1 className="mt-2 text-balance text-3xl font-semibold tracking-tight text-foreground sm:text-4xl">
                Set up your workspace
              </h1>
              <p className="mt-2 max-w-2xl text-pretty text-sm leading-relaxed text-muted-foreground">
                Choose providers, add an optional API key, and optionally build
                your first index.
              </p>
            </div>
          </section>

          <div className="mb-5 flex flex-wrap gap-2">
            {steps.map((entry, index) => (
              <button
                key={entry.title}
                type="button"
                onClick={() => {
                  if (index <= step) {
                    setStep(index);
                  }
                }}
                className={cn(
                  "cursor-pointer rounded-full px-4 py-2 text-sm font-medium transition-all",
                  index === step
                    ? "bg-primary/16 text-primary"
                    : index < step
                      ? "bg-emerald-400/12 text-emerald-200"
                      : "bg-white/6 text-muted-foreground",
                )}
              >
                {index + 1}. {shortenStepTitle(entry.title)}
              </button>
            ))}
          </div>

          <OnboardingStep
            index={step}
            total={steps.length}
            title={steps[step].title}
            description={steps[step].description}
            hint={steps[step].hint}
          >
            {steps[step].content}

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/8 pt-6">
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setStep((current) => Math.max(0, current - 1))}
                  disabled={step === 0}
                  className="gap-2"
                >
                  <ArrowLeft className="size-4" />
                  Back
                </Button>
                {step === 3 ? (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => setStep(4)}
                  >
                    Skip indexing for now
                  </Button>
                ) : null}
              </div>

              {step < steps.length - 1 ? (
                <Button
                  type="button"
                  onClick={() =>
                    setStep((current) =>
                      Math.min(current + 1, steps.length - 1),
                    )
                  }
                  className="gap-2"
                >
                  Continue
                  <ArrowRight className="size-4" />
                </Button>
              ) : (
                <Button
                  type="button"
                  onClick={handleFinish}
                  disabled={saving}
                  className="gap-2"
                >
                  {saving ? (
                    <AnimatedLucideIcon
                      icon={Database}
                      mode="idlePulse"
                      className="size-4"
                    />
                  ) : (
                    <BrainIcon size={16} className="shrink-0" />
                  )}
                  {saving ? "Launching workspace..." : "Finish and open chat"}
                </Button>
              )}
            </div>
          </OnboardingStep>
        </main>
      </div>

      <MetisCompanionDock className="bottom-24 md:bottom-4" />
    </div>
  );
}

function shortenStepTitle(title: string): string {
  if (title.length <= 28) {
    return title;
  }
  return `${title.slice(0, 25)}...`;
}
