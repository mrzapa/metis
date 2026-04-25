# 0013 - Seedling Runtime: Frontend Default, Backend Optional

- **Status:** Accepted (M13 runtime pivot — supersedes ADR 0007)
- **Date:** 2026-04-25

## Context

ADR 0007 (2026-04-24, *Accepted*) decided that the Seedling worker
would run an in-process backend GGUF — Llama-3.2-1B-Instruct Q4_K_M as
the default — through the existing `LocalGGUFBackend`/llama-cpp path
under Litestar lifecycle. That decision was written before this
codebase was re-audited against what is **already shipping** for
in-browser companion inference, and Phase 2 (PR #541, lifecycle shell)
was deliberately scoped to *not* load any model so the pivot stayed
cheap.

Re-auditing 2026-04-25 against the live tree:

- `apps/metis-web/lib/webgpu-companion/worker.ts:39` already pins
  **`onnx-community/Bonsai-1.7B-ONNX`** (1-bit quantized, ~500 MB) as
  the in-browser companion model, loaded through
  `@huggingface/transformers` in a dedicated Web Worker on WebGPU.
- `apps/metis-web/lib/webgpu-companion/use-webgpu-companion.ts`
  exposes a typed React hook with `status: "unsupported"|"idle"|"loading"|"ready"|"generating"|"oom"|"error"`
  plus a streaming token API. The download is **opt-in** (the worker
  is constructed only when `load()` is called), cached in IndexedDB
  after first load, and SSR-safe.
- `apps/metis-web/components/shell/metis-companion-dock.tsx` already
  wires "always-on Bonsai reflection": when the user toggles
  `metis:bonsai-always-on=1` and Bonsai is loaded, every completed
  `CompanionActivityEvent` triggers a one-or-two-sentence Bonsai
  reflection on top of the existing event stream
  (`metis-companion-dock.tsx:243-272`).
- `metis_app/seedling/` (PR #541) is a tickless lifecycle shell. It
  has *zero* model-loading code and `current_stage` is hardcoded.
  No backend GGUF is referenced from the worker.

The implication ADR 0007 missed: **the always-on companion is
already running, and it's running in the browser, not the backend.**
ADR 0007's proposed Llama-3.2-1B GGUF download is a parallel runtime,
not a primary one. Forcing every user through that download imposes
~700 MB + filesystem-write + llama-cpp-runtime constraints
(CPU-only fallback, GPU offload settings, OS-permission friction for
sandboxed installers) on top of the model the product is already
shipping.

ADR 0007's other unstated assumption was that overnight reflection
must run regardless of whether the browser is open. In practice,
"watch your companion grow" is a foreground-app moment for a
local-first workspace; the user generally has METIS open while they
work. A reflection that only fires when the app is open is honest;
forcing a backend model so reflection can fire in the dark is not
worth the install-time tax.

This ADR therefore inverts ADR 0007's runtime choice.

## Decision

**The default Seedling reflection model is the existing in-browser
Bonsai-1.7B WebGPU runtime. The in-process Litestar GGUF path
becomes opt-in — a power-user upgrade, not the baseline.**

### 1. Default runtime — Bonsai (frontend, WebGPU)

- The Seedling reflection surface uses the existing
  `useWebGPUCompanion()` / `webgpu-companion/worker.ts` pipeline.
  Phase 4 wires *overnight reflection* to that pipeline behind the
  same opt-in gate that already governs always-on reflection
  (`metis:bonsai-always-on`). Phase 5 reads the same `webgpu.status`
  to decide whether the dock's stage badge can show "reflecting now".
- No backend model download is required to use M13. A user who never
  uploads a GGUF still gets:
  - the lifecycle heartbeat from PR #541,
  - feed ingestion + comet decisioning from Phase 3 (no LLM in that
    loop — `comet_decision_engine` is rule-based, not generative),
  - growth-stage transitions from Phase 5 (the stage signal is
    structural — stars-indexed, faculties-spanned, skills-promoted,
    reflections-completed — none of those require a backend model),
  - in-browser Bonsai reflection while METIS is open, opt-in via the
    existing always-on toggle.
- Bonsai fallback when WebGPU is unavailable
  (`webgpu.status === "unsupported"`): the dock surfaces the existing
  `caniuse.com/webgpu` link the codebase already shows, plus a
  one-line *"Browser doesn't support WebGPU; configure a local GGUF in
  Settings → Models for backend reflection."* Phase 5's stage badge
  reports "Reflection unavailable in this browser" rather than
  silently doing nothing.

### 2. Optional backend runtime — user-uploaded GGUF

- Backend reflection is gated on the user explicitly importing a GGUF
  through the existing `apps/metis-web/app/gguf/` flow and toggling a
  new `seedling_backend_reflection_enabled` setting (default `false`).
- When enabled, the existing `LocalGGUFBackend`/llama-cpp path drives
  reflection from the Seedling worker tick, using whatever model the
  user already has registered through `local_model_registry`. The
  worker holds at most one resident instance and reuses it between
  ticks (this part of ADR 0007's *Consequences* still applies).
- METIS does **not** ship a default catalog entry for Llama-3.2-1B,
  Phi-3.5, or any other backend GGUF as part of M13. ADR 0007's
  "Add Llama-3.2-1B-Instruct to llmfit_gguf_catalog.json" follow-up
  is dropped from M13 scope. Power users pick what they want from
  the existing recommender.
- `GET /v1/seedling/status` reports a `model_status` field with
  values:
  - `"frontend_only"` (no GGUF registered),
  - `"backend_configured"` (a GGUF is registered and the toggle is on),
  - `"backend_disabled"` (a GGUF is registered but the toggle is off),
  - `"backend_unavailable"` (the toggle is on but the configured
    GGUF cannot load — file missing, OOM, llama-cpp init failure).
  `model_status` describes **only the backend reflection path.**
  WebGPU/Bonsai availability is reported separately on the
  frontend via `useWebGPUCompanion().status` (existing
  `unsupported|idle|loading|ready|generating|oom|error` enum).
  The two statuses are independent — a user can have
  `frontend_only` + WebGPU `ready` (the default happy path),
  `backend_configured` + WebGPU `unsupported` (backend power user
  on a no-WebGPU browser), and so on. The dock renders copy off
  the combination of the two; neither subsumes the other.
- **Runtime priority when both are available.** Bonsai owns
  while-you-work reflection (event-driven, browser-side); the
  backend GGUF owns overnight reflection (time-driven, backend).
  They coexist by default — a user with both Bonsai-ready and
  `backend_configured` gets Bonsai while the dock is open and
  backend overnight when the laptop is awake. Phase 4 should
  not expose a "which runtime to use right now" toggle in v0; the
  cadence boundary already disambiguates.
- A user with no GGUF and no WebGPU support gets a Seedling that
  ingests, classifies, and tracks growth — but cannot reflect.
  That state is honest and surfaced in the dock; it is not a crash.

### 3. Overnight reflection — opt-in, not promised in the marketing copy

- Phase 4 ships *while-you-work* reflection by default: Bonsai runs
  any time the dock is open and the always-on toggle is enabled. The
  cadence is event-driven (one reflection per completed
  `CompanionActivityEvent`), not time-of-day driven.
- A separate **overnight reflection** mode runs only when the user has
  also opted into the backend GGUF path (`seedling_backend_reflection_enabled = true`)
  AND configured `seedling_reflection_cadence_hours` (default 24). The
  worker tick chooses a quiet window
  (`last_user_activity > 30 min`) and calls
  `AssistantCompanionService.reflect(overnight=True)` against the
  configured backend GGUF.
- Marketing copy in the dock and onboarding never says "your
  companion reflects while you sleep" without the qualifier. It says:
  "While METIS is open, your companion reflects on every activity
  event." Users who set up backend reflection see an additional line:
  "Backend reflection runs in the background while your laptop is
  awake." VISION.md's *"the morning-after reflection"* phrase becomes
  a Phase 4 stretch tied to the backend opt-in, not a default
  promise.

### 4. What survives from ADR 0007

ADR 0007 is marked *Superseded* by this ADR, but two of its
sub-decisions still apply when a user *does* configure backend
reflection:

- The backend reflection process holds at most one resident model
  instance and reuses it between ticks; never re-instantiate
  llama-cpp on every poll.
- Seedling-specific settings (`seedling_*`) do not silently mutate
  the user's primary chat model settings.
- Backend reflection prompts stay small and structured (reflection
  summaries, feed-item classification, candidate notes), not
  long-form synthesis.

## Constraints

- Preserve ADR 0004 (one Litestar interface, no second daemon). The
  backend-optional path uses the existing in-process llama-cpp
  integration; no new daemon, no IPC.
- Preserve ADR 0005 (system-level growth, not weight-level continual
  learning). This pivot does not change the M13 deliverable; it
  changes which runtime carries it.
- Preserve ADR 0011's privacy posture. Bonsai runs entirely in the
  user's browser via WebGPU; **inference traffic stays on-device** —
  no prompt or completion text leaves the user's machine. The
  first-load model download from
  `huggingface.co/onnx-community/Bonsai-1.7B-ONNX` is a one-time
  outbound that **must be visible in the network-audit panel.** That
  download is currently flagged as an **open M17 audit item**
  (`plans/network-audit/plan.md` row M, pointing at
  `apps/metis-web/lib/webgpu-companion/worker.ts:39`) for
  classification — *"verify whether the model actually downloads
  from HF or is bundled"*. ADR 0013 does not introduce a new call
  site; it elevates an already-shipping fetch to a load-bearing
  default. **M17 should resolve row M before Phase 4 ships** so the
  dock can honestly tell users when the download hits the network
  versus when it is served from IndexedDB cache. Note also that the
  `@huggingface/transformers` library issues this fetch from the Web
  Worker via the browser's own `fetch()`, which is outside M17's
  stdlib `audited_urlopen` interception (M17 is backend-only); the
  classification needs to record this as browser-side egress, not
  Python-side.
- Do not silently start the Bonsai download. The opt-in posture from
  `useWebGPUCompanion.load()` is preserved — Phase 4 wires the toggle,
  it does not bypass it.
- The pivot must leave the Phase 2 lifecycle shell untouched. The
  worker stays a tickless heartbeat in v0; this ADR governs which
  reflection model fires from inside that tick, not the tick itself.

## Alternatives Considered

- **Keep ADR 0007: backend Llama-3.2-1B as default.** Rejected as the
  baseline. Re-auditing the tree showed the in-browser path was
  already shipping; baking a second always-on model into the install
  story violates the local-first promise *"intelligence grown, not
  bought"* by inflating first-run friction (~700 MB download,
  filesystem write, llama-cpp lazy-import surface area, OS-permission
  friction). The backend path remains available as opt-in.
- **Backend GGUF as default, Bonsai as fallback.** Rejected. Inverts
  the *"first run works, no setup required"* product principle and
  makes the WebGPU path feel like a downgrade, when in fact it is
  the lower-friction route on every laptop that supports it.
- **Run Bonsai server-side via ONNX Runtime.** Rejected for M13.
  ONNX Runtime + Bonsai-1.7B server-side would be a meaningful new
  dependency surface (native ONNX wheels, GPU bindings vary by OS),
  duplicates capability the browser already provides, and forces
  reflection into a background process when the natural moment is
  "while the user is in the app". The browser path is already
  on-device, already shipped, already cached.
- **Drop overnight reflection entirely from M13.** Rejected. The
  morning-after moment is part of VISION.md. We keep it as an opt-in
  Phase 4 stretch tied to backend GGUF, rather than promise it in
  every install.
- **Promote ADR 0007 to a "model catalog seeding" follow-up.**
  Rejected because the catalog already has Phi-3.5 and Qwen2.5-0.5B
  entries; users who want backend reflection have viable choices
  without M13 adding a new one. If a user-research signal later
  shows users want a one-click *"install Seedling backend"* button,
  that becomes its own scoped milestone, not buried inside M13.

## Consequences

Accepted implementation follow-ups:

- **ADR 0007 status flips to *Superseded* with a pointer to ADR 0013.**
  Its Open Questions about Llama license acceptance and catalog
  placement go away with the pivot; the Seedling acceptance prompt
  suite question moves to Phase 4 of the M13 plan.
- **Phase 3 scope shrinks.** The "Add Llama-3.2-1B catalog entry"
  bullet leaves M13 entirely (out of scope, not deferred). Phase 3
  ships the news-feed repository, the OPML import endpoint, and the
  Seedling worker tick driving ingestion — no model-loading work.
- **Phase 4 scope splits.** *While-you-work reflection* uses the
  existing Bonsai pipeline; the Phase 4 PR mainly wires
  `webgpu-companion` events into the new
  `AssistantCompanionService.reflect(overnight=True)` and the
  skill-candidate writer. *Overnight reflection* is gated on
  `seedling_backend_reflection_enabled` and ships behind a feature
  flag if the toggle is off, with one-line dock copy explaining
  the opt-in.
- **`/v1/seedling/status` gains `model_status`.** Phase 3 or Phase 4
  (whichever lands first) extends the existing
  `SeedlingStatus` dataclass (`metis_app/seedling/status.py`) and
  the matching frontend type (`apps/metis-web/lib/api.ts`
  `SeedlingStatus`) with the four-value enum above. **Additive only:**
  the dataclass adds the field with `default = "frontend_only"`,
  existing required fields keep their semantics; the frontend type
  adds `model_status?:` as optional (clients default it to
  `"frontend_only"` until the backend payload is observed). Tests
  cover all four values plus the default.
- **New settings.** Add to `metis_app/default_settings.json`:
  - `seedling_backend_reflection_enabled` (default `false`).
  - `seedling_reflection_cadence_hours` (default 24, used only when
    backend reflection is enabled).
  - `seedling_reflection_quiet_window_minutes` (default 30, used only
    when backend reflection is enabled).
- **No new frontend dependency.** `@huggingface/transformers` is
  already in `apps/metis-web/package.json` lockfile.
- **No new backend dependency.** `llama-cpp-python` stays
  lazy-imported only on the backend-opt-in path; users without it
  installed still get the Seedling.
- **Network-audit row.** The existing audit row for
  `huggingface.co/spaces/webml-community/bonsai-webgpu` /
  `onnx-community/Bonsai-1.7B-ONNX` remains the canonical entry for
  Seedling-related model traffic. The plan's
  *Coordinates with M17 (Network audit)* paragraph at the top of
  `plans/seedling-and-feed/plan.md` continues to apply: the worker
  itself emits no new outbound calls; backend opt-in inherits the
  audited HF download path that already exists.

## Open Questions

- The "while-you-work" cadence — one reflection per completed
  `CompanionActivityEvent` — is generous when the user has a busy
  research session. Phase 4 should measure whether to rate-limit it
  (e.g. ≥30 s between reflections) once real usage data exists. Not
  ADR-level; track in Phase 4 retro.
- Bonsai-1.7B vs. a smaller WebGPU model (Bonsai-0.5B, if/when one
  ships) for the always-on default. Phase 4 should sanity-check
  resident-VRAM cost on consumer GPUs and keep an eye on upstream
  ONNX weights; not a v0 concern.
- Whether the `seedling_backend_reflection_enabled` toggle should
  live in *Settings → Models* (next to the existing GGUF picker) or
  in a new *Settings → Seedling* surface. Phase 4 picks; this ADR
  does not pre-empt the UX call.
- Browser-private-mode behaviour. IndexedDB caching is the load-bearing
  reason Bonsai is fast on second load; in private mode the
  user re-downloads on every session. Phase 4 should detect private
  mode at `useWebGPUCompanion()` init and warn the user before they
  pay 500 MB. Worth a one-line dock note; not an ADR-level decision.
- **Phase 4 must surface first-load progress.** The hook exposes
  `progress: { loadedBytes, totalBytes, pct }` but the dock today
  only shows the bar in the Bonsai settings card. When a user
  toggles always-on for the first time, Phase 4 should render a
  "Bonsai downloading…" progress card in the dock thought log; do
  not silently drop reflection requests until `status === "ready"`.
- **Tab-close lifecycle.** The hook terminates the worker on
  unmount, so an in-flight Bonsai generation is dropped when the
  user closes the tab. For a single completed
  `CompanionActivityEvent`, that is by design and matches §3's
  *"the natural moment is 'while the user is in the app'"*. Phase 4
  copy should reflect this — Bonsai cannot deliver
  "I'll reflect on the last 30 minutes when you sit down tomorrow",
  only the backend GGUF can. Track in Phase 4 retro.
- **Phase 5 / ADR 0009 cross-concern.** Phase 5's proposed
  Seedling → Sapling threshold is *"≥10 stars AND ≥1 completed
  overnight reflection"*. As written, that permanently locks
  no-WebGPU + no-GGUF users at Seedling. ADR 0009 (or the
  growth-stage decision section that replaces it) should decide
  whether *while-you-work* reflections also count toward stage
  transitions. Not pre-empted here; flagged so it does not get lost.
- **Marketing-copy guard test.** Phase 4 should land a tiny pytest
  in `tests/test_seedling_marketing_copy.py` that fails CI if a
  forbidden phrase like *"reflects while you sleep"* (without the
  ADR 0013 §3 qualifier) appears anywhere under `apps/metis-web/`.
  Mechanical enforcement keeps the §3 guardrail honest without
  relying on reviewer vigilance.
