# 0007 - Seedling Model and Runtime

- **Status:** Accepted (M13 Phase 1)
- **Date:** 2026-04-24

## Context

M13 makes the companion feel alive: a small local model wakes in the
background, classifies incoming feed items, reflects over recent activity,
and emits companion events without asking the user to open a chat tab. This
worker must fit the product promise in `VISION.md`: local-first, inspectable,
offline-capable, and honest about system-level growth rather than weight-level
continual learning.

The repo already ships the load-bearing local-model pieces:

- `metis_app/utils/llm_providers.py::LocalLlamaCppChatModel` wraps
  `llama-cpp-python` chat completion behind the same `.invoke(messages)`
  protocol as the RAG pipeline.
- `metis_app/utils/llm_backends.py::LocalGGUFBackend` wraps raw llama.cpp
  completion.
- `metis_app/services/local_llm_recommender.py` scores GGUF fit against
  detected RAM/VRAM and prefers `bartowski` / `unsloth` sources.
- `metis_app/services/local_model_registry.py` persists local GGUF entries
  and activates them through existing `local_gguf_*` settings.

Phase 1 therefore decides the Seedling model and serving shape. It does not
implement the worker.

## Decision

Use **Llama-3.2-1B-Instruct Q4_K_M GGUF** as the default Seedling model, served
**in-process through the existing llama-cpp GGUF stack** from the Litestar
sidecar lifecycle.

Runtime posture:

- The Seedling worker loads the model lazily through the existing local GGUF
  adapter path. Phase 2 should prefer the chat adapter
  (`LocalLlamaCppChatModel` via `create_llm`) for reflection prompts and only
  use `LocalGGUFBackend` if the worker needs raw completion semantics.
- The worker is started and stopped by Litestar startup/shutdown hooks. It is
  not an Ollama daemon and not a separate `metis-seedling-worker` process for
  M13 v1.
- Default context stays small: `local_gguf_context_length = 2048` for Seedling
  reflection/classification prompts, even though the selected model supports a
  much larger context. Phase 4 can raise this only for overnight reflection if
  measured memory stays healthy.
- Default GPU posture is CPU-first (`local_gguf_gpu_layers = 0`) so METIS
  works on 16 GB laptops without assuming CUDA/Metal setup. Users who already
  configured GPU offload keep that path.
- Target resident budget is **<= 2 GB** for the Seedling model plus normal
  context. The worker must not also load a second Seedling model for fallback
  in the same process.
- Use **Qwen2.5-0.5B-Instruct Q4_K_M** as the documented fallback for very
  low-memory machines or for a future "classification-only" mode. Do not use
  it as the default companion-reflection model.
- Do not use Phi-3.5-mini-instruct as the always-on default. It remains a
  higher-quality manual option for users who explicitly choose the memory cost.

## Evidence

External source check, 2026-04-24:

| Candidate | License / access | Q4_K_M GGUF file | Context | Fit for Seedling |
|---|---:|---:|---:|---|
| [Phi-3.5-mini-instruct](https://huggingface.co/microsoft/Phi-3.5-mini-instruct) | MIT, ungated | [2,393,232,672 bytes](https://huggingface.co/bartowski/Phi-3.5-mini-instruct-GGUF) | 128K-class | Best quality headroom, but too large for always-on default. |
| [Llama-3.2-1B-Instruct](https://huggingface.co/meta-llama/Llama-3.2-1B-Instruct) | Llama 3.2 license, gated upstream | [807,694,464 bytes](https://huggingface.co/bartowski/Llama-3.2-1B-Instruct-GGUF) | 128K-class | Best balance: small enough, better headroom than 0.5B. |
| [Qwen2.5-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct) | Apache-2.0, ungated | [397,808,192 bytes](https://huggingface.co/bartowski/Qwen2.5-0.5B-Instruct-GGUF) | 32K-class | Excellent fallback, but too little reasoning margin for the default companion. |

Repo-local estimator check, using
`metis_app.services.local_llm_recommender.CatalogModel.estimate_memory_gb`
and `estimate_tps` with Q4_K_M, 2048 context, 8 CPU cores, and an RTX 3060
8 GB profile:

| Candidate | Estimated resident memory | CPU-only estimate | RTX 3060 estimate |
|---|---:|---:|---:|
| Phi-3.5-mini-instruct | 2.62 GB | 7.0 tok/s | 103.6 tok/s |
| Llama-3.2-1B-Instruct | 1.18 GB | 21.6 tok/s | 322.0 tok/s |
| Qwen2.5-0.5B-Instruct | 0.77 GB | 53.8 tok/s | 801.6 tok/s |

These are advisory estimates, not benchmark claims. Their job is to keep the
Phase 2 implementation inside a safe memory envelope.

## Constraints

- Preserve ADR 0004: one product interface, local Litestar sidecar, no second
  daemon as a default product dependency.
- Preserve ADR 0005: the companion grows at the system level. This ADR does
  not promise LoRA, weight updates, or continual fine-tuning.
- Preserve local-first operation. The selected runtime must work offline after
  the model file is present.
- Do not add a new dependency in Phase 1. M13 uses the existing
  `llama-cpp-python` path already guarded by lazy import.
- Coordinate with M17: any model download/import path remains under the
  existing audited Hugging Face/catalog code paths. The worker itself should
  not make unaudited outbound calls.
- Keep explicit user-triggered reflection/research endpoints. The Seedling
  worker owns periodic scheduling, not manual actions.

## Alternatives Considered

- **Phi-3.5-mini-instruct Q4_K_M as default.** Rejected for v1 default. It has
  the best quality margin among the candidates, but the Q4 file is 2.39 GB and
  the repo-local 2048-context estimate is 2.62 GB resident. That misses the
  <=2 GB target before METIS loads indexes, embeddings, browser UI, and normal
  API state.
- **Qwen2.5-0.5B-Instruct Q4_K_M as default.** Rejected as the primary
  companion model. Its Apache-2.0 license, ungated access, and speed are
  attractive, but 0.5B leaves too little instruction-following and synthesis
  headroom for overnight reflection. It is the right fallback and can become
  a classification-only profile later.
- **Ollama daemon over HTTP.** Rejected as the default. It is useful for users
  who already run Ollama, but it adds a second service, extra health checks,
  and a new network-shaped integration for the baseline local experience.
- **Separate `metis-seedling-worker` subprocess embedding llama.cpp.** Rejected
  for M13 v1. It may eventually improve fault isolation, but it would add IPC,
  process supervision, packaging, and duplicate model-loading logic before the
  worker lifecycle has proven useful.
- **Use the user's primary chat model for Seedling work.** Rejected. The
  Seedling is meant to be always-on and local by default; routing background
  reflection through a remote provider would violate the product promise and
  increase network-audit noise.

## Consequences

Accepted implementation follow-ups:

- Add Llama-3.2-1B-Instruct to `llmfit_gguf_catalog.json` or a seedling-specific
  recommendation table before Phase 2 tries to import/activate the default.
  The current catalog contains Phi-3.5-mini-instruct and Qwen2.5-0.5B-Instruct,
  but not the selected Llama model.
- Phase 2 should introduce seedling-specific settings rather than silently
  mutating the user's primary chat model settings. Suggested keys:
  `seedling_model_name`, `seedling_gguf_model_path`,
  `seedling_context_length`, `seedling_gpu_layers`, `seedling_threads`, and
  `seedling_enabled`.
- The worker should hold at most one resident Seedling model instance and
  reuse it between ticks. Recreating llama.cpp on every feed poll would turn
  the lifecycle into a latency and memory churn problem.
- If no Seedling GGUF file is configured, `/v1/seedling/status` should report
  `running: false`, `model_status: "missing"`, and a clear next action. It
  should not fall back to remote LLM providers.
- Qwen fallback is opt-in or auto-selected only when hardware detection says
  the 1B model is too tight. The fallback should be reported in status so the
  user can see why the smaller model is active.
- Keep the first prompts small and structured: reflection summaries,
  feed-item classification, and candidate-skill notes. Long-form synthesis
  remains the user's primary chat/research model's job until measured.

## Open Questions

- Should Phase 2 add the selected Llama model to the global GGUF recommender
  catalog, or keep a smaller Seedling-specific catalog to avoid changing the
  user-facing model picker ranking?
- How should METIS handle upstream Llama license acceptance in the setup flow
  if the preferred GGUF mirror is reachable but the base model is gated?
- What exact prompt suite becomes the Seedling acceptance test? The first
  implementation should include short reflection/classification fixtures so
  the default-vs-fallback tradeoff can be measured rather than argued.
