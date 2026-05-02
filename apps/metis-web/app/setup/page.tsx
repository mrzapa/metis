"use client";

import Link from "next/link";
import { useEffect, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MetisLockup } from "@/components/brand";
import { AmbientBackdrop } from "@/components/shell/ambient-backdrop";
import { MetisCompanionDock } from "@/components/shell/metis-companion-dock";
import { WebGPUCompanionProvider } from "@/lib/webgpu-companion/webgpu-companion-context";
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
  Cpu,
  Database,
  Settings2,
  Sparkles,
} from "lucide-react";
import { BrainIcon } from "@/components/icons";
import { useArrowState } from "@/hooks/use-arrow-state";

const LLM_PROVIDERS = [
  { value: "anthropic", label: "Anthropic" },
  { value: "openai", label: "OpenAI" },
  { value: "local", label: "Local model" },
] as const;

const EMBEDDING_PROVIDERS = [
  { value: "openai", label: "OpenAI embeddings" },
  { value: "local", label: "Local embeddings" },
] as const;

const STEP_LABELS = [
  "Provider",
  "API key",
  "Embeddings",
  "Index",
  "Launch",
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

/**
 * M21 #17 — friendly labels for the routes that may redirect a
 * not-yet-set-up user here. Keeps the banner copy honest and avoids
 * leaking unfriendly path strings into product copy.
 */
const REDIRECT_FROM_LABEL: Record<string, string> = {
  "/chat": "chat",
  "/forge": "the Forge",
  "/improvements": "the research log",
  "/settings": "settings",
};

export default function SetupPage() {
  const router = useRouter();
  // M21 #17: when SetupGuard redirects a not-yet-set-up user away
  // from /chat (or /forge, /settings, /improvements), it appends
  // `?from=<origin-pathname>`. Read it once at mount, surface a
  // contextual banner so the user knows why they landed here, AND
  // honour the redirect when the launch handlers fire so the user
  // actually returns to where they came from rather than being
  // dropped on /chat regardless. The query string is read once on
  // mount — `searchParams` is stable for the page's lifetime and the
  // banner intentionally persists while the user is in the wizard
  // (we navigate AWAY on launch, so the param simply disappears).
  //
  // Open-redirect safety: we only trust `from` values that exist as
  // keys in `REDIRECT_FROM_LABEL`. Anything else falls back to
  // `/chat`. That allowlist is the same one we use to derive the
  // banner copy, so the banner and the launch redirect are always
  // in lockstep — there's no path where the banner says "we'll send
  // you back to X" but the launch sends you somewhere else.
  const searchParams = useSearchParams();
  const redirectFromPath = searchParams?.get("from") ?? null;
  const redirectFromLabel = redirectFromPath
    ? REDIRECT_FROM_LABEL[redirectFromPath] ?? null
    : null;
  // Resolved launch target: the `from` value if it's allowlisted,
  // otherwise `/chat`. Both `handleInstantLaunch` and `handleFinish`
  // route here at the end of the wizard.
  const launchTarget = useMemo<string>(() => {
    if (
      redirectFromPath
      && Object.prototype.hasOwnProperty.call(REDIRECT_FROM_LABEL, redirectFromPath)
    ) {
      return redirectFromPath;
    }
    return "/chat";
  }, [redirectFromPath]);
  // Wizard fork — `null` shows the binary "instant vs configure" picker;
  // `"configure"` runs the full 5-step wizard. The "instant" branch
  // commits a webgpu/Bonsai default and routes to /chat without ever
  // entering the step machine, so it has no `forkChoice` value of its
  // own.
  const [forkChoice, setForkChoice] = useArrowState<"configure" | null>(null);
  const [webgpuSupported, setWebgpuSupported] = useArrowState<boolean | null>(
    null,
  );
  const [instantLaunching, setInstantLaunching] = useArrowState(false);
  const [step, setStep] = useArrowState(0);
  const [llmProvider, setLlmProvider] =
    useArrowState<(typeof LLM_PROVIDERS)[number]["value"]>("anthropic");
  const [apiKey, setApiKey] = useArrowState("");
  const [embeddingProvider, setEmbeddingProvider] =
    useArrowState<(typeof EMBEDDING_PROVIDERS)[number]["value"]>("openai");
  const [embeddingProviderTouched, setEmbeddingProviderTouched] =
    useArrowState(false);
  const [baselineSettings, setBaselineSettings] = useArrowState<
    Record<string, unknown>
  >({});
  const [builtIndex, setBuiltIndex] = useArrowState<IndexBuildResult | null>(
    null,
  );
  const [selectedPrompt, setSelectedPrompt] = useArrowState<string>("");
  const [saving, setSaving] = useArrowState(false);
  const [error, setError] = useArrowState<string | null>(null);

  /**
   * M21 #13 — when a user revisits /setup/ AFTER completing the wizard,
   * detect their existing mode so the picker can surface a "currently
   * active" indicator instead of pretending it's first-run. Reads from
   * `baselineSettings` populated by the existing `fetchSettings`
   * effect; resolves to:
   *   - "browser-only"   → llm_provider === "webgpu"
   *   - "configured"     → wizard completed with any other provider
   *   - null             → wizard not yet completed (first-run flow)
   */
  const completedMode = useMemo<"browser-only" | "configured" | null>(() => {
    if (baselineSettings.basic_wizard_completed !== true) return null;
    return baselineSettings.llm_provider === "webgpu"
      ? "browser-only"
      : "configured";
  }, [baselineSettings.basic_wizard_completed, baselineSettings.llm_provider]);

  useEffect(() => {
    if (typeof navigator === "undefined") {
      setWebgpuSupported(false);
      return;
    }
    setWebgpuSupported("gpu" in navigator);
  }, [setWebgpuSupported]);

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
            setEmbeddingProviderTouched(true);
          }
        }
      })
      .catch(() => {
        // The onboarding flow can still proceed with sane defaults.
      });
  }, [
    setBaselineSettings,
    setEmbeddingProvider,
    setEmbeddingProviderTouched,
    setLlmProvider,
  ]);

  // Auto-pair embedding default with the chosen LLM provider until the user
  // overrides it. Anthropic and Local both default to local embeddings (the
  // local-first vision); OpenAI defaults to OpenAI embeddings so the same key
  // covers both calls.
  useEffect(() => {
    if (embeddingProviderTouched) {
      return;
    }
    const defaultEmbedding: (typeof EMBEDDING_PROVIDERS)[number]["value"] =
      llmProvider === "openai" ? "openai" : "local";
    setEmbeddingProvider(defaultEmbedding);
  }, [embeddingProviderTouched, llmProvider, setEmbeddingProvider]);

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

  // Providers that never require an API key — chat can launch even when
  // no credential is configured. Anything else needs a *persisted*
  // `api_key_<provider>` — either an existing entry in settings.json or
  // a `credential_pool` mapping. The wizard's apiKey input is **not**
  // counted: M21 #5 stopped persisting it (the backend's settings
  // PATCH 403s any api_key_* write unless METIS_ALLOW_API_KEY_WRITE=1
  // is set), so a key pasted into the wizard never reaches the chat
  // surface. Treating it as ready here would show a false-green
  // "Direct chat ready" pill on step 5. Codex caught this on the M21
  // Phase 1 PR.
  //
  // The result has three shapes now:
  //   - `ready: true`                   — local provider OR a
  //                                       persisted credential exists
  //   - `ready: false, wizardKeyOnly`   — user pasted a key in step 2
  //                                       but no persisted credential
  //                                       exists; needs settings.json
  //   - `ready: false`                  — no credential at all; user
  //                                       can switch to a local
  //                                       provider or skip
  const directChatReadiness = useMemo(() => {
    const NO_KEY_PROVIDERS = new Set<string>([
      "local",
      "mock",
      "browser_webgpu",
      "local_lm_studio",
      "local_gguf",
    ]);
    if (NO_KEY_PROVIDERS.has(llmProvider)) {
      return { ready: true as const };
    }
    const existingKey = baselineSettings[`api_key_${llmProvider}`];
    if (typeof existingKey === "string" && existingKey.trim().length > 0) {
      return { ready: true as const };
    }
    const credentialPool = baselineSettings.credential_pool;
    if (
      credentialPool &&
      typeof credentialPool === "object" &&
      !Array.isArray(credentialPool)
    ) {
      const entry = (credentialPool as Record<string, unknown>)[llmProvider];
      if (entry !== undefined && entry !== null && entry !== "") {
        return { ready: true as const };
      }
    }
    const providerLabel =
      LLM_PROVIDERS.find((provider) => provider.value === llmProvider)?.label ??
      llmProvider;
    const wizardKeyOnly = apiKey.trim().length > 0;
    return { ready: false as const, providerLabel, wizardKeyOnly };
  }, [apiKey, baselineSettings, llmProvider]);

  async function handleInstantLaunch() {
    setInstantLaunching(true);
    setError(null);
    try {
      await updateSettings({
        llm_provider: "webgpu",
        llm_model: "Bonsai 1.7B",
        basic_wizard_completed: true,
      });
      // M21 #17: honour `?from=` redirect when present; falls back
      // to /chat for the standard first-run flow. See the
      // `launchTarget` comment above for the safety story.
      router.push(launchTarget);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to launch in-browser model",
      );
      setInstantLaunching(false);
    }
  }

  async function handleFinish() {
    setSaving(true);
    setError(null);

    try {
      const updates: Record<string, unknown> = {
        llm_provider: llmProvider,
        embedding_provider: embeddingProvider,
        basic_wizard_completed: true,
      };

      // Note: api_key_* are intentionally NOT sent. The backend's
      // settings PATCH endpoint blocks api_key_* writes (403 unless
      // METIS_ALLOW_API_KEY_WRITE=1) — including them here used to
      // crash the whole wizard save. The wizard's API-key input is
      // captured for the user to copy into settings.json themselves.
      // See M21 #5.

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
      // M21 #17: honour `?from=` redirect when present.
      router.push(launchTarget);
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
              </button>
            );
          })}
        </div>
      ),
    },
    {
      title: "Add an API key (optional)",
      description:
        llmProvider === "local"
          ? "Local model mode does not require a hosted API key. You can continue immediately or add one later if you switch providers."
          : "API keys are not stored through the wizard. METIS reads them from settings.json — paste here as a reminder to copy it across after this step.",
      content: (
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
              : (
                <>
                  This wizard never writes <code className="rounded bg-amber-500/15 px-1">api_key_*</code> to settings —
                  the backend rejects those updates by design. To finish setup with a hosted provider, paste your key
                  into <code className="rounded bg-amber-500/15 px-1">settings.json</code> at the repo root after the
                  wizard completes (or set <code className="rounded bg-amber-500/15 px-1">METIS_ALLOW_API_KEY_WRITE=1</code> to
                  let UI writes through).
                </>
              )}
          </p>
        </div>
      ),
    },
    {
      title: "Choose your embedding provider",
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
                onClick={() => {
                  setEmbeddingProviderTouched(true);
                  setEmbeddingProvider(provider.value);
                }}
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
              </button>
            );
          })}
        </div>
      ),
    },
    {
      title: "Build the first knowledge base",
      description: "Optional. Index a few files now for grounded chat.",
      content: (
        <IndexBuildStudio
          settingsOverrides={buildSettings}
          showExistingIndexes={false}
          onIndexBuilt={setBuiltIndex}
          successMode="onboarding"
        />
      ),
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
                {directChatReadiness.ready ? (
                  <StatusPill
                    label={builtIndex ? "RAG ready" : "Direct chat ready"}
                    tone={builtIndex ? "connected" : "neutral"}
                  />
                ) : directChatReadiness.wizardKeyOnly ? (
                  <StatusPill
                    label="Key won’t persist"
                    tone="warning"
                  />
                ) : (
                  <StatusPill
                    label="Missing API key"
                    tone="warning"
                  />
                )}
                <StatusPill label="Starter prompt staged" tone="neutral" />
              </div>

              <p className="mt-4 text-sm leading-7 text-muted-foreground">
                {directChatReadiness.ready
                  ? builtIndex
                    ? "Opens chat with this index preselected and a starter prompt staged."
                    : "Opens direct chat with a starter prompt staged."
                  : directChatReadiness.wizardKeyOnly
                    ? `Direct chat won’t work yet for ${directChatReadiness.providerLabel}: the wizard does not save API keys. Copy the key from step 2 into settings.json (or set METIS_ALLOW_API_KEY_WRITE=1 to let UI writes through), then return to chat.`
                    : `Add an API key for ${directChatReadiness.providerLabel} in settings.json or switch to a local model.`}
              </p>
            </div>
          </div>
        </div>
      ),
    },
  ];

  return (
    <WebGPUCompanionProvider>
    <div className="relative min-h-screen overflow-hidden">
      <AmbientBackdrop />

      <div className="relative z-10 mx-auto flex min-h-screen max-w-7xl flex-col px-4 pb-8 pt-4 sm:px-6 lg:px-8">
        <header className="glass-panel flex flex-wrap items-center gap-3 rounded-2xl px-4 py-3 sm:px-5">
          <div>
            <p style={{ fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600, fontSize: 15, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
              METIS<sup style={{ fontSize: 8, opacity: 0.4, verticalAlign: 'super', marginLeft: 2 }}>AI</sup>
            </p>
            <p className="text-[11px] uppercase tracking-[0.22em] text-muted-foreground">
              Setup
            </p>
          </div>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            {forkChoice === "configure" ? (
              <StatusPill
                label={`Step ${step + 1} of ${steps.length}`}
                tone="checking"
              />
            ) : null}
            <Link href="/">
              <Button variant="outline" size="sm">
                Back to home
              </Button>
            </Link>
          </div>
        </header>

        {redirectFromLabel ? (
          <div
            data-testid="setup-redirect-banner"
            role="status"
            className="mt-3 flex flex-wrap items-center gap-2 rounded-2xl border border-amber-300/30 bg-amber-300/10 px-4 py-2.5 text-sm text-amber-100/95"
          >
            <Sparkles className="size-4 shrink-0 opacity-85" aria-hidden="true" />
            <span>
              Finish setup to start using {redirectFromLabel}. We&apos;ll send
              you back to {redirectFromLabel} as soon as you launch.
            </span>
          </div>
        ) : null}

        {forkChoice === null ? (
          <main className="flex flex-1 flex-col items-center justify-center gap-5 py-8">
            {completedMode ? (
              <div
                data-testid="setup-active-mode-banner"
                role="status"
                className="w-full max-w-4xl rounded-2xl border border-emerald-300/25 bg-emerald-300/8 px-4 py-3 text-sm text-emerald-100/95"
              >
                <p className="font-medium">
                  {completedMode === "browser-only"
                    ? "Browser-only mode is currently active."
                    : "Your own provider is currently configured."}
                </p>
                <p className="mt-1 text-emerald-100/75">
                  {completedMode === "browser-only"
                    ? "Pick “Use my own model” below to switch to Anthropic / OpenAI / a local GGUF, or just head back to chat."
                    : "Pick “Try it instantly” to switch to the in-browser model, or just head back to chat."}
                  {" "}
                  <Link href="/chat" className="underline-offset-2 hover:underline">
                    Open chat &rarr;
                  </Link>
                </p>
              </div>
            ) : null}
            <section className="grid w-full max-w-4xl gap-4 md:grid-cols-2">
              <button
                type="button"
                onClick={handleInstantLaunch}
                disabled={!webgpuSupported || instantLaunching}
                className={cn(
                  "glass-panel-strong group flex cursor-pointer flex-col gap-4 rounded-[1.75rem] p-6 text-left transition-all duration-200 sm:p-8",
                  webgpuSupported && !instantLaunching
                    ? "border border-primary/24 hover:border-primary/40 hover:shadow-lg hover:shadow-primary/10"
                    : "border border-white/8 opacity-60",
                )}
                aria-label="Try METIS instantly with browser-only model"
              >
                <div className="flex size-11 items-center justify-center rounded-2xl bg-primary/15 text-primary">
                  <Sparkles className="size-5" />
                </div>
                <div>
                  <h2 className="font-display text-2xl font-semibold tracking-[-0.03em] text-foreground">
                    Try it instantly
                  </h2>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    {webgpuSupported === false
                      ? "WebGPU not detected in this browser. Try Chrome or Edge 113+."
                      : "Browser-only model. No setup, no API key."}
                  </p>
                </div>
                <div className="mt-auto inline-flex items-center gap-1.5 rounded-full bg-primary/12 px-3 py-1.5 text-xs font-medium text-primary group-disabled:opacity-50">
                  {instantLaunching ? (
                    <>
                      <AnimatedLucideIcon
                        icon={Cpu}
                        mode="idlePulse"
                        className="size-3.5"
                      />
                      Loading…
                    </>
                  ) : (
                    <>
                      Get started
                      <ArrowRight className="size-3.5" />
                    </>
                  )}
                </div>
              </button>

              <button
                type="button"
                onClick={() => setForkChoice("configure")}
                disabled={instantLaunching}
                className="glass-panel group flex cursor-pointer flex-col gap-4 rounded-[1.75rem] border border-white/8 p-6 text-left transition-all duration-200 hover:border-white/16 hover:bg-white/4 sm:p-8"
                aria-label="Configure your own model provider"
              >
                <div className="flex size-11 items-center justify-center rounded-2xl bg-white/8 text-foreground">
                  <Settings2 className="size-5" />
                </div>
                <div>
                  <h2 className="font-display text-2xl font-semibold tracking-[-0.03em] text-foreground">
                    Use my own model
                  </h2>
                  <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                    Anthropic, OpenAI, or local GGUF.
                  </p>
                </div>
                <div className="mt-auto inline-flex items-center gap-1.5 rounded-full bg-white/8 px-3 py-1.5 text-xs font-medium text-foreground">
                  Configure
                  <ArrowRight className="size-3.5" />
                </div>
              </button>

              {error ? (
                <div className="md:col-span-2 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                  {error}
                </div>
              ) : null}
            </section>
          </main>
        ) : (
        <main className="flex-1 py-8">
          <section className="mb-6">
            <div className="glass-panel rounded-2xl px-5 py-5 sm:px-6">
              <MetisLockup size="md" wordmarkPosition="right" className="mb-4" />
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
                {STEP_LABELS[index]}
              </button>
            ))}
          </div>

          <OnboardingStep
            index={step}
            total={steps.length}
            title={steps[step].title}
            description={steps[step].description}
          >
            {steps[step].content}

            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-white/8 pt-6">
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    if (step === 0) {
                      setForkChoice(null);
                    } else {
                      setStep((current) => Math.max(0, current - 1));
                    }
                  }}
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
        )}
      </div>

      <MetisCompanionDock className="bottom-24 md:bottom-4" />
    </div>
    </WebGPUCompanionProvider>
  );
}
