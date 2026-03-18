"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { updateSettings } from "@/lib/api";
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react";

const LLM_PROVIDERS = ["anthropic", "openai", "local"] as const;
const EMBEDDING_PROVIDERS = ["openai", "local"] as const;

type LlmProvider = (typeof LLM_PROVIDERS)[number];
type EmbeddingProvider = (typeof EMBEDDING_PROVIDERS)[number];

export default function SetupPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [llmProvider, setLlmProvider] = useState<LlmProvider>("anthropic");
  const [apiKey, setApiKey] = useState("");
  const [embeddingProvider, setEmbeddingProvider] =
    useState<EmbeddingProvider>("openai");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleFinish() {
    setSaving(true);
    setError(null);
    try {
      const updates: Record<string, unknown> = {
        llm_provider: llmProvider,
        embedding_provider: embeddingProvider,
        basic_wizard_completed: true,
      };
      // Only include api_key if user provided one (backend may reject it,
      // but we pass the intent through).
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
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  const steps = [
    // Step 0 — Choose LLM provider
    <Card key="llm">
      <CardHeader>
        <CardTitle>Choose LLM Provider</CardTitle>
        <CardDescription>
          Select the language model provider Axiom will use for chat and
          retrieval-augmented generation.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <select
          id="llm_provider"
          value={llmProvider}
          onChange={(e) => setLlmProvider(e.target.value as LlmProvider)}
          className="h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus:outline-none focus:ring-1 focus:ring-ring"
        >
          {LLM_PROVIDERS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </CardContent>
      <CardFooter>
        <Button onClick={() => setStep(1)}>Next</Button>
      </CardFooter>
    </Card>,

    // Step 1 — Enter API key
    <Card key="apikey">
      <CardHeader>
        <CardTitle>Enter API Key</CardTitle>
        <CardDescription>
          Provide the API key for your chosen provider. You can leave this blank
          and set it later in <code>settings.json</code>.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Input
          id="api_key"
          type="password"
          placeholder="sk-..."
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
        />
      </CardContent>
      <CardFooter>
        <div className="flex w-full gap-2">
          <Button variant="outline" onClick={() => setStep(0)}>
            Back
          </Button>
          <Button onClick={() => setStep(2)}>Next</Button>
        </div>
      </CardFooter>
    </Card>,

    // Step 2 — Choose embedding provider
    <Card key="embedding">
      <CardHeader>
        <CardTitle>Choose Embedding Provider</CardTitle>
        <CardDescription>
          Select the provider used for generating document embeddings during
          indexing and retrieval.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <select
          id="embedding_provider"
          value={embeddingProvider}
          onChange={(e) =>
            setEmbeddingProvider(e.target.value as EmbeddingProvider)
          }
          className="h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors focus:outline-none focus:ring-1 focus:ring-ring"
        >
          {EMBEDDING_PROVIDERS.map((p) => (
            <option key={p} value={p}>
              {p}
            </option>
          ))}
        </select>
      </CardContent>
      <CardFooter>
        <div className="flex w-full gap-2">
          <Button variant="outline" onClick={() => setStep(1)}>
            Back
          </Button>
          <Button onClick={() => setStep(3)}>Next</Button>
        </div>
      </CardFooter>
    </Card>,

    // Step 3 — Confirm and save
    <Card key="confirm">
      <CardHeader>
        <CardTitle>Confirm Setup</CardTitle>
        <CardDescription>
          Review your choices below and click Finish to save.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="space-y-2 text-sm">
          <div className="flex justify-between">
            <dt className="font-medium">LLM Provider</dt>
            <dd className="text-muted-foreground">{llmProvider}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="font-medium">API Key</dt>
            <dd className="text-muted-foreground">
              {apiKey ? "\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022" : "(not set)"}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="font-medium">Embedding Provider</dt>
            <dd className="text-muted-foreground">{embeddingProvider}</dd>
          </div>
        </dl>

        {error && (
          <div className="mt-4 flex items-center gap-1.5 text-sm text-destructive">
            <AlertCircle className="size-4" />
            {error}
          </div>
        )}
      </CardContent>
      <CardFooter>
        <div className="flex w-full gap-2">
          <Button variant="outline" onClick={() => setStep(2)}>
            Back
          </Button>
          <Button onClick={handleFinish} disabled={saving} className="gap-1.5">
            {saving && <Loader2 className="size-4 animate-spin" />}
            {saving ? "Saving\u2026" : "Finish"}
          </Button>
        </div>
      </CardFooter>
    </Card>,
  ];

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <h1 className="text-lg font-semibold">Axiom Setup</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Step {step + 1} of {steps.length}
          </p>
        </div>

        {/* Progress dots */}
        <div className="flex justify-center gap-2">
          {steps.map((_, i) => (
            <div
              key={i}
              className={`size-2 rounded-full transition-colors ${
                i <= step ? "bg-primary" : "bg-muted"
              }`}
            />
          ))}
        </div>

        {steps[step]}
      </div>
    </div>
  );
}
