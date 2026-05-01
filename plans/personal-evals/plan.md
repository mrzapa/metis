---
Milestone: Personal evals (M16)
Status: In progress
Claim: claude/m16-phase2-eval-store
Last updated: 2026-05-01 by claude/m16-phase2-eval-store
Vision pillar: Companion
---

TDD Mode: pragmatic (Phase 1) -> strict (Phase 2)
QA Execution Mode: agent-operated
Phase 1 rationale: docs-only ADR slice; there is no meaningful RED -> GREEN loop, so verification comes from the harvest audit, local DB/corpus probe, and repo checks recorded in Progress.
Phase 2 rationale: implementation slice with three new pure-Python modules (store, corpus, generation) — each has clean RED -> GREEN evidence (schema migrations, JSONL seed-import idempotency, content-addressed generation hashing). RED tests are written first against `:memory:` SQLite and `tmp_path` JSONL fixtures before the module bodies, captured in *Progress* under cited test names.

## Progress

*(Milestone not started as a cohesive unit — this doc is the first real
plan pass. Significant adjacent scaffolding already exists in the repo
and will be harvested rather than rebuilt. See the harvest list in
*Notes for the next agent*.)*

- 2026-05-01 Phase 1 claimed on branch `claude/m16-phase1-adrs`; the
  M16 row in `plans/IMPLEMENTATION.md` is now `In progress`.
- 2026-05-01 inventory spike confirmed the checked-in harvest surface on
  `main`: `ArtifactConverter.export_as_eval()`, `trace_feedback`,
  `message_feedback`, `BehaviorProfile`, and the existing
  `CompanionActivityEvent` bus all exist already. Local data is still
  cold-start: `rag_sessions.db` exists but both feedback tables currently
  have `0` rows, and `evals/golden_dataset.jsonl` is absent.
- 2026-05-01 draft ADR numbering corrected for current trunk state:
  `0010`–`0012` were already consumed by M17/M12 work, so M16 Phase 1
  uses ADR `0016` (grading lanes), `0017` (storage + generation
  versioning), and `0018` (privacy posture). Optional judge-model
  pinning moves to `0019` if M16 v2 needs it.
- 2026-05-01 Phase 1 ADR set landed: ADR 0016 locks the three-lane
  grading strategy, ADR 0017 chooses a dedicated `evals.db` with
  content-addressed generation ids, and ADR 0018 keeps storage/grading
  local while allowing reruns to reuse the user's already-selected
  companion provider.
- 2026-05-01 verification snapshot for the Phase 1 docs slice:
  `npx vitest run` passed in `apps/metis-web`; required repo gates remain
  blocked by unrelated baseline failures on `main` — backend pytest fails
  in `tests/test_install_launcher.py` because `README.md` no longer
  documents `--desktop` / "landing page", `npx tsc --noEmit` fails in
  `components/shell/__tests__/metis-sigil.test.tsx` on a pre-existing
  `stage` typing mismatch, and `ruff check <touched files>` is not a
  usable command for this docs-only slice because Ruff parses the targeted
  `.md` files as Python and exits with syntax errors.
- 2026-05-01 verification unblock landed: `README.md` now documents the
  launcher's `--desktop` / `--gui` overrides and explicitly calls the
  default web surface the "Constellation home landing page"; the
  `MetisSigil` test now types its fixture data as `GrowthStage` so
  `npx tsc --noEmit` no longer widens `stage` to `string`.
- 2026-05-01 required verification passed after the Phase 1 docs +
  verification-unblock slice:
  `python -m pytest tests/ --ignore=tests/_litestar_helpers --ignore=tests/test_api_app.py`
  => `1511 passed, 12 skipped`; `cd apps/metis-web && npx tsc --noEmit`
  => clean; `cd apps/metis-web && npx vitest run` => `74 passed, 2
  skipped`; `ruff check tests/test_install_launcher.py` => clean.
- 2026-05-01 Phase 2 claim flipped on the M16 row to
  `claude/m16-phase2-eval-store`; plan-doc frontmatter and TDD-mode
  declaration updated to record the strict-mode shift for the
  implementation slice.
- 2026-05-01 Phase 2 RED tests landed first as
  `tests/test_evals_store.py`, `tests/test_evals_corpus.py`,
  `tests/test_evals_generation.py`, `tests/test_evals_settings_keys.py`
  (36 total). Initial run captured the expected RED with
  `ModuleNotFoundError: No module named 'metis_app.evals'` across all
  three import sites — strict-mode evidence per the Phase 2 rationale
  declared above.
- 2026-05-01 Phase 2 GREEN landed: new package `metis_app/evals/` ships
  `store.py` (ADR 0017 schema for `tasks`/`runs`/`generations` plus an
  env-overridable default-store singleton mirroring the
  `network_audit` pattern), `corpus.py` (`EvalTask` dataclass mirroring
  the `ArtifactConverter.export_as_eval` shape + idempotent
  `import_seed_jsonl` keyed on `eval_id` per ADR 0017 §3), and
  `generation.py` (content-addressed SHA-256 `current_generation_id`,
  `GENERATION_SETTINGS` material-settings allowlist, and
  `bump_if_needed` that preserves `first_seen_at`/`notes` on repeat
  via `ON CONFLICT DO NOTHING`). Settings keys `evals_enabled` /
  `evals_cadence_hours` / `evals_auto_seed_enabled` /
  `evals_share_optin` added to `metis_app/default_settings.json` and
  `AppSettings` with defaults aligned to ADR 0018 (off / 24h / off /
  off) so fresh installs do not surface a hollow report and
  `evals_share_optin` stays inert.
- 2026-05-01 Phase 2 verification:
  `python -m pytest tests/ --ignore=tests/_litestar_helpers --ignore=tests/test_api_app.py`
  => `1547 passed, 12 skipped` (delta = 36 new tests, all GREEN);
  `cd apps/metis-web && npx tsc --noEmit` => clean;
  `cd apps/metis-web && npx vitest run` => `74 passed, 2 skipped`;
  `ruff check metis_app/evals metis_app/settings_store.py
  tests/test_evals_*.py` => clean (after dropping unused
  `os`/`uuid`/`pytest` imports + an unused `store` binding flagged on
  the first ruff pass).
- 2026-05-01 Phase 2 review-fix slice landed on PR #599 — six items
  flagged on the open PR addressed in one squash:
  1. **(P1)** `import_seed_jsonl` now filters on
     `label == "reinforce"` before importing. The export endpoint at
     `observe.py:177` forwards `_latest_label(run_id)` verbatim, so
     suppress / investigate rows DO appear in
     `evals/golden_dataset.jsonl`; without the filter they would have
     been graded as if they were golden cases. Plan-doc semantics
     (only `reinforce` enters the corpus) is now enforced at the
     import layer too.
  2. **(P2)** `assistant_runtime` is projected to a material-subkey
     allowlist (`provider`, `model`, GGUF tuning, context-window,
     `fallback_to_primary`) before hashing. Volatile fields
     (`bootstrap_state`, `recommended_*`, `auto_install`,
     `auto_bootstrap`) no longer bump generations on cold start or
     hardware-detection refresh. `_NESTED_PROJECTIONS` is the
     extension point for future nested-block settings.
  3. **(P2)** `EvalStore.insert_task_if_absent(row) -> bool` lands as
     the right primitive for importers and any other call site that
     must not clobber existing rows. Uses `INSERT ... ON CONFLICT DO
     NOTHING` and reports via `cursor.rowcount`. `import_seed_jsonl`
     drops its `list_tasks()` pre-scan and uses this method directly,
     resolving both the O(N) read-amplification finding and the
     pre-scan-failure idempotency hole flagged in the same review.
  4. **(P2)** Same fix as item 3 — pre-scan pathway is gone, so a
     read failure can no longer fall through to an `upsert_task`
     overwrite of an existing row.
  5. **(P2)** `get_default_store` now uses double-checked locking
     under a module-level `threading.Lock`, mirroring
     `metis_app/network_audit/runtime.py`. Concurrent first callers
     under Litestar's executor pool can no longer race into building
     two stores against the same env override; subsequent calls take
     the fast path with no lock cost.
  6. **(P2)** `EvalStore.close()` releases any shared SQLite
     connection (essential for `:memory:` stores, which would
     otherwise leak across tests) and is idempotent; new
     `close_default_store()` mirrors the network_audit shutdown helper
     and is what `reset_default_store_for_tests()` now calls under the
     hood.
- 2026-05-01 Review-fix verification:
  `python -m pytest tests/ --ignore=tests/_litestar_helpers --ignore=tests/test_api_app.py`
  => `1562 passed, 12 skipped` (delta = 15 new pytest cases — 4 label-
  filter, 4 assistant-runtime projection, 2 `insert_task_if_absent`,
  1 idempotency-against-edits, 1 concurrent-singleton, 3 close /
  reset-close); `cd apps/metis-web && npx tsc --noEmit` => clean;
  `cd apps/metis-web && npx vitest run` => `74 passed, 2 skipped`;
  `ruff check metis_app/evals tests/test_evals_*.py` => clean.

What's in place today that M16 will lean on — "personal evals" is
closer to shipping than the table status suggests, because the raw
signals are already flowing, they just are not aggregated into a
time-series or surfaced as an eval report:

- **Golden-dataset eval cases (already writing to disk).**
  `metis_app/services/artifact_converter.py` contains
  `ArtifactConverter.export_as_eval()` (lines 142–188). Reinforce-
  labeled trace runs are packaged with `query`, `context_chunks`,
  `expected_strategy`, `expected_min_citations`, `expected_min_iterations`,
  `answer_preview`, and behavioral `assertions`, then appended to
  `evals/golden_dataset.jsonl`. This is the *write* side of a
  user-specific eval corpus — M16's job is to build the *read + run +
  score* side, not to re-invent the capture format. The endpoint
  wiring is live at `POST /v1/traces/{run_id}/export/eval`
  (`metis_app/api_litestar/routes/observe.py:177`).
- **Trace feedback store (already grading runs).**
  `session_repository.init_db()` at lines 163–177 creates
  `trace_feedback(feedback_id, run_id, segment, label, note, created_at)`
  with labels in the set `{"reinforce", "suppress", "investigate"}`.
  `POST /v1/traces/{run_id}/feedback` writes to it
  (`observe.py:115-133`). This is an **explicit per-run grading
  signal** already sitting in the DB — M16 can treat a `reinforce` as
  +1, a `suppress` as −1, and `investigate` as "needs LLM-judge".
- **Message feedback store (thumbs up/down).**
  `session_repository.init_db()` at lines 148–162 creates
  `message_feedback(feedback_id, session_id, run_id, vote INTEGER,
  note, ts)`. This is a per-answer thumbs signal keyed by `run_id` —
  a second independent grading lane that M16 can aggregate separately
  from trace feedback.
- **Behavior profile extractor.**
  `metis_app/services/behavior_discovery.py` distills raw trace events
  into a `BehaviorProfile` (iteration count, citation count,
  citation diversity, convergence score, fallback triggered, had
  error, anomalies, interestingness score) — no LLM required. This is
  the **implicit grading signal**: a run with zero citations and low
  convergence scores low; a run with good citations and clean
  convergence scores high. M16 uses this as its rubric-free baseline
  score.
- **Trace store + run events.**
  `metis_app/services/trace_store.py` owns the underlying run /
  events store that the behavior discovery service reads. Eval runs
  produce traces; the same store can be reused so eval runs are
  first-class behavior-profile rows.
- **LLM-as-judge pattern (already in use, locally).**
  `assistant_companion._promote_skill_candidates()` at lines 898–974
  runs the configured local LLM as a JSON-returning judge over skill
  candidates (`confidence` threshold 0.7, JSON {`is_generalizable`,
  `skill_name`, `skill_description`, `confidence`}). This is the
  template for a local-only judge in M16 — no external API, no
  phone-home, uses whatever model the user has configured.
- **Autonomous research reflection (M09 landed).**
  `autonomous_research_service.run()` emits progress events and a
  synthesised document; `assistant_companion.reflect()` emits a
  reflection summary. Both are perfect eval-task candidates
  (*"rerun yesterday's reflection with today's companion — did the
  summary improve?"*) and both already emit
  `CompanionActivityEvent` the eval harness can piggyback on.
- **Companion realtime visibility (M09 landed).**
  `apps/metis-web/lib/api.ts` exposes the `CompanionActivityEvent`
  pub/sub with a `source` union; `metis-companion-dock.tsx` is the
  canonical live-thought surface. M16 eval runs will emit through
  this bus so the user sees "companion is being tested" in the dock
  while it runs.
- **Settings store.**
  `metis_app/settings_store.py` + `metis_app/default_settings.json`
  — the 21 KB settings store already has the shape M16 needs
  (e.g. the `news_comets_*` keys are the template for `evals_*`
  keys). No `eval_*` / `benchmark_*` keys exist yet; this is the
  first place M16 will touch backend config.

## Next up

1. **Phase 3 — eval run harness.** Land
  `metis_app/evals/runner.py` with `run_eval(task, settings, *,
  progress_cb=None) -> EvalRun` that builds a `WorkspaceOrchestrator`
  invocation against the task's `query` / `expected_strategy` / `mode`,
  records the trace `run_id`, captures the answer text and behavior
  profile, and emits through `progress_cb`. Wire the runner into
  Litestar's executor pool the way `autonomous_research_service`
  already does so interactive use never blocks. Call
  `bump_if_needed` from `metis_app.evals.generation` once per run so
  every `runs.generation_id` row has a matching entry in `generations`.
2. **Phase 3 prep — extend the activity + API surface before the
  runner lands.** Add a `"eval_run"` value to
  `CompanionActivityEvent.source` (frontend `apps/metis-web/lib/api.ts`
  + backend emitters), and sketch `/v1/evals/tasks` / `/v1/evals/runs`
  / `/v1/evals/run/{task_id}` against the field names captured in
  the 2026-05-01 inventory memo below.
3. **Phase 3 — grading lanes (ADR 0016).** Add
  `metis_app/evals/grading.py` with the three v1 lanes (trace label,
  message vote, implicit `BehaviorProfile`) renormalised over whichever
  lanes are present, plus the `review_required=true` propagation when
  any `investigate` label appears in the run's `trace_feedback`
  history.

## Blockers

- **M13 (Seedling + Feed) must be landed far enough that growth
  signals exist.** An eval surface with nothing to evaluate is a
  skeleton. The companion needs to be *doing work* on the user's
  data regularly enough that there's a nontrivial per-user task
  corpus and nontrivial week-over-week delta to show. If M13 is in
  Draft when M16 starts, the eval harness can still be built — but
  it will benchmark cold (zero user-specific tasks) and the reports
  will be hollow. **Recommendation: start M16 implementation while
  M13 Phase 1–3 is landing, so the first real eval run has at least
  a week of seedling activity to score against.** Phase 7 of M13
  (LoRA training-log capture) and M16's Phase 2 (task corpus) should
  share a JSONL shape.
- **Privacy posture — nothing phones home (VISION product principle
  #6).** Eval storage, grading, and reporting stay local. No task
  corpus is uploaded, no results are uploaded, and no eval leaderboard
  exists across users. Reruns may reuse the user's already-selected
  companion provider, but M16 must not introduce any second eval-
  specific service or hidden telemetry path. The M17 Network Audit
  milestone will prove this at the network layer. Flag any grading
  strategy that requires an external API (e.g. a cloud LLM-as-judge) as
  out of scope under ADR 0018.
- **Base-rate problem.** Fresh installs have no history. The first
  month of eval output is N=1..10 datapoints and must not be
  surfaced as "your companion is 7% worse this week" — that's
  noise. UI copy must explicitly frame the early window as
  "collecting — come back in a week". Honest framing here is a
  churn defence, not a polish concern (see VISION *Risks and
  honest tradeoffs*).
- **Companion-generation semantics are not yet defined.** If the
  user swaps the local LLM, promotes a skill via M06, or lands a
  LoRA adapter (M18), every subsequent eval result is apples-to-
  oranges with the prior result. M16 cannot meaningfully say "the
  companion improved on summary tasks" without knowing which
  *companion* it's comparing. This is ADR 0017's core job.

## Notes for the next agent

This milestone is one half of VISION.md's *"Personal Evals and
Network Audit"* item — the half that turns "intelligence grown, not
bought" (product principle #1) into an observable, time-series
surface. Under-deliver here and the whole *"watch it grow"* narrative
is a vibe, not a claim; over-deliver into generic model-eval
territory (HumanEval, MMLU, cloud leaderboards) and you've built
someone else's product. Keep it personal, keep it local, keep it
honest about small sample sizes.

### 2026-05-01 inventory memo — checked-in schema vs local data

- `ArtifactConverter.export_as_eval()` currently writes JSONL rows with
  `eval_id`, `derived_from_run`, `created_at`, `label`,
  `feedback_note`, `query`, `mode`, `context_chunks`,
  `expected_strategy`, `expected_min_iterations`,
  `expected_min_citations`, `answer_preview`, and `assertions`.
- `message_feedback` is already the explicit thumbs lane with schema
  `(feedback_id, session_id, run_id, vote, note, ts)`.
- `trace_feedback` is already the richer explicit-label lane with schema
  `(feedback_id, run_id, segment, label, note, created_at)`.
- `BehaviorProfile` already yields the implicit lane fields M16 can
  score without an LLM: `query_preview`, `mode`, `primary_skill`,
  `strategy_fingerprint`, `iterations_used`, `gap_count_total`,
  `citation_count`, `citation_diversity_score`, `convergence_score`,
  `source_count`, `retrieval_delta_per_iter`, `fallback_triggered`,
  `had_error`, `first_seen`, `interestingness_score`, and `anomalies`.
- Local development data is still empty-state. On 2026-05-01 the local
  `rag_sessions.db` existed, but both `trace_feedback` and
  `message_feedback` contained `0` rows; `evals/golden_dataset.jsonl`
  was absent. Phase 2 therefore needs cold-start handling to be the
  default path, not an afterthought.
- The frontend companion activity bus already supports `rag_stream`,
  `index_build`, `autonomous_research`, `reflection`, `seedling`,
  `news_comet`, and `forge`. `eval_run` must be additive on this bus,
  not a new channel.

### Harvest list — do not rebuild these

Before writing a single line of new code, read each of these in the
existing repo. Roughly 40–50% of "build personal evals" is wiring
capture points that already exist into a time-series + a report
surface:

| Area | File | What to harvest |
|---|---|---|
| Golden eval case writer | `metis_app/services/artifact_converter.py` (`export_as_eval`, lines 142–188) | Eval-case schema with `eval_id`, `query`, `context_chunks`, `expected_strategy`, `expected_min_citations`, `assertions`. This is the **v1 task-corpus row**. |
| Eval export HTTP endpoint | `metis_app/api_litestar/routes/observe.py:177-186` (`POST /v1/traces/{run_id}/export/eval`) | Already-live endpoint to promote a reinforce-labeled run into the corpus. Do not invent a second path. |
| Trace feedback labels | `session_repository.init_db()` (lines 163–177) + `observe.py` feedback endpoints | Per-run grade signal: `reinforce` / `suppress` / `investigate`. |
| Message feedback thumbs | `session_repository.init_db()` (lines 148–162) | Per-answer vote (INTEGER, ±1). |
| Behavior profile | `metis_app/services/behavior_discovery.py` (`BehaviorProfile`) | Rubric-free implicit score: `convergence_score`, `citation_count`, `citation_diversity_score`, `fallback_triggered`, `anomalies`, `interestingness_score`. |
| Trace run events | `metis_app/services/trace_store.py` | Source of truth for run events; eval reruns produce new traces here. |
| LLM-as-judge template | `assistant_companion._promote_skill_candidates()` (lines 898–974) | How to run a local LLM as a JSON-returning judge with a confidence threshold. Reuse pattern when v2 lands. |
| Settings store | `metis_app/settings_store.py` + `metis_app/default_settings.json` | Where `evals_enabled`, `evals_cadence_hours`, `evals_judge_strategy`, `evals_share_optin` live. |
| Companion activity bus | `apps/metis-web/lib/api.ts` (`CompanionActivityEvent`, `subscribeCompanionActivity`) | Eval runs emit here — **do not introduce a second bus**. Add a new `source: "eval_run"` value. |
| Companion dock | `apps/metis-web/components/shell/metis-companion-dock.tsx` | Eval-in-progress badge lives here. Eval *report* lives elsewhere (see Phase 5). |
| Settings page | `apps/metis-web/app/settings/page.tsx` (hotspot, 99th %ile churn) | v1 report surface — a new `evals` tab is the fastest path to visibility. |
| Autonomous research | `metis_app/services/autonomous_research_service.py` | Canonical "task" that can be rerun against a historical query and graded for improvement. |
| Reflection loop | `assistant_companion.reflect()` (line 175) | Second canonical reruanable task. |

### Core conceptual framing (read before phase planning)

Personal evals are **not generic model benchmarks**. HumanEval, MMLU,
GSM8K and the cloud leaderboards answer "how good is this model at
these tasks, for everyone". That's explicitly a *"stranger's mind"*
question (VISION.md pitch: *"Every other AI product rents you a
stranger's mind. METIS grows one with you."*). Personal evals answer
a different question:

> **"How good is *this user's companion* at *this user's* specific
> tasks, and has it improved since last week?"**

That shifts four things from standard practice:

1. **The task corpus is per-user and grows over time.** Tasks are
   things this user actually asks METIS to do — Q&A against *their*
   documents, summaries of *their* feeds, retrieval over *their*
   brain graph, reflections on *their* journal. Each corpus is
   different. Each is small. Tasks enter the corpus when the user
   explicitly labels a run `reinforce` (via existing
   `POST /v1/traces/{run_id}/export/eval`) or when a seed heuristic
   picks them up (see Phase 6).
2. **The grading signal is hybrid and avoids self-grading.** The
   companion grading itself is gameable. Options:
   - *Explicit thumbs* (`message_feedback.vote`) — free, sparse, noisy.
   - *Explicit labels* (`trace_feedback.label`) — free, sparse, richer.
   - *Implicit heuristics* (`BehaviorProfile` fields) — free, dense,
     rubric-free.
   - *LLM-as-judge with a frozen local reference model* — costs local
     compute, introduces reviewer bias, but runs offline.
   - *Task-specific rubrics* (retrieval precision@k against pinned
     sources; citation coverage; structured-output parse rate) —
     expensive to author per task, high quality when authored.
   v1 ships the first three. v2 layers on the fourth. Rubric
   scoring stays an expert/power-user feature.
3. **The report is a time series keyed by task × user × companion-
   generation.** "Generation" bumps when the model swaps, when a
   LoRA adapter lands (M18), when M06 promotes a skill, or when
   settings materially change. Without generation tracking, "week
   over week improvement" is meaningless.
4. **The report surface *is* the product.** VISION.md's
   *"morning 'here's what I learned overnight' surface"* is not a
   separate feature from evals — it *is* the eval report, dressed
   for a human. M16's UI must say *"your companion got better at
   summarising your feeds this week"*, not *"ROUGE-L rose 0.03"*.

### Proposed phase breakdown

A first cut. The claimant is free to restructure, but every phase
should have an explicit *what NOT to do* boundary.

#### Phase 1 — ADR 0010: grading-signal strategy

**Goal:** pick the v1 grading lanes and defend the choice in writing.

- Candidate lanes, with explicit tradeoffs:
  - *trace_feedback labels* (already in DB) — free, rich, sparse.
  - *message_feedback thumbs* (already in DB) — free, binary, sparse.
  - *BehaviorProfile implicit score* (already computable) — free,
    dense, rubric-free, noisy for short runs.
  - *LLM-as-judge with local frozen model* — local-compute cost,
    reviewer-bias risk, requires a pinned judge model per user.
  - *Task-specific rubrics* — expensive to author, very high quality.
- Recommendation (see also *Open decisions* below): v1 ships
  explicit-thumbs + explicit-label + implicit-profile, aggregated
  via a simple weighted sum. v2 layers on local LLM-as-judge. v3
  supports user-authored rubrics. **Do not reach for external LLM
  APIs** — violates product principle #6.
- Output: `docs/adr/0016-personal-eval-grading-strategy.md`.

**Not this phase:** the weighting math (that's Phase 4), the UI copy
(Phase 5), any code.

#### Phase 2 — Task corpus model

**Goal:** a stable data model for "one thing the companion can be
tested on" that survives companion-generation bumps.

- New module: `metis_app/evals/corpus.py` defining:
  ```
  class EvalTask:
      task_id: str           # stable uuid, survives generations
      created_at: str
      task_type: Literal["qa","summary","retrieval","reflection","custom"]
      source_run_id: str | None  # the reinforce-labeled run it was derived from, if any
      query: str
      context_chunks: list[ContextChunk]    # reuse ArtifactConverter shape
      expected_strategy: str
      expected_min_citations: int
      expected_min_iterations: int
      assertions: list[Assertion]           # reuse ArtifactConverter shape
      tags: list[str]
      user_pinned_sources: list[str] | None # for rubric-grade retrieval scoring (v3)
  ```
- Storage: **ADR 0017 picks** a `tasks` table in
  a new `evals.db` SQLite file under the existing data directory,
  keyed by `task_id`. Mirror on-disk as JSONL snapshot weekly for
  portability (user can eyeball the file, diff across weeks).
- Import path from existing corpus: the
  `evals/golden_dataset.jsonl` file (written by
  `ArtifactConverter.export_as_eval`) is the **seed**. On M16
  startup, if `evals.db` has no `tasks` rows but the JSONL exists,
  migrate it. Do not break the JSONL write path — keep it as an
  append-only audit log alongside the SQLite index (product
  principle #5: *Trace everything*).

**Not this phase:** the run harness, the store, the report.

#### Phase 3 — Eval run harness

**Goal:** a thing that takes a corpus item, runs the current
companion against it, records input / output / grades, without
blocking interactive use.

- New module: `metis_app/evals/runner.py`.
  - Entrypoint: `run_eval(task: EvalTask, settings, *, progress_cb=None) -> EvalRun`.
  - Internally: build a fresh `WorkspaceOrchestrator` invocation
    with the task's `query`, `expected_strategy`, `mode`. Capture
    the trace run_id, the answer text, the behavior profile.
  - Grading: query all enabled grading lanes for the new run_id
    (`trace_feedback` — likely empty at eval time, so auto-skipped;
    `message_feedback` — same; `BehaviorProfile` — always available).
    Compute aggregate score per ADR 0016 weights.
  - Async: never block UI. Hook into Litestar's executor pool the
    same way `autonomous_research_service` does. Single-threaded
    across eval runs so we don't thrash CPU; the Seedling (M13) may
    own the scheduling slot.
- Events: every run emits through the existing `progress_cb`
  hook → `CompanionActivityEvent` with a new source value
  `"eval_run"` and states `"running"` / `"completed"` / `"error"`.
  The dock (M09) and constellation (M09 refresh hook) already
  subscribe — no new frontend plumbing needed.
- HTTP endpoints (live but gated):
  - `POST /v1/evals/run/{task_id}` — run one task now.
  - `POST /v1/evals/run/batch` — run all active tasks (background).
  - `POST /v1/evals/run/stream` — SSE variant mirroring
    `/v1/autonomous/research/stream`.
  - `GET /v1/evals/tasks` — list tasks.
  - `GET /v1/evals/runs?task_id=...&since=...` — list runs for a
    task.
- Safety: **eval runs must use the same companion configuration as
  interactive use**, including any LoRA adapter. Do not silently
  swap to a "pristine" model — that makes eval-vs-interactive
  comparisons meaningless. The *frozen judge model* (if enabled in
  v2) is the only exception, and it's a separate LLM spec in
  settings.

**Not this phase:** companion-generation versioning (Phase 4),
reports (Phase 5).

#### Phase 4 — Time-series store + companion-generation versioning

**Goal:** every eval run is keyed so "week over week improvement"
is meaningful.

- Schema (inside `evals.db` per ADR 0017):
  ```
  runs(
    run_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    companion_generation_id TEXT NOT NULL,
    timestamp TEXT,
    input_query TEXT,
    output_text TEXT,
    trace_run_id TEXT,
    signals_json TEXT,   -- per-lane scores as JSON blob
    aggregate_score REAL
  )
  generations(
    generation_id TEXT PRIMARY KEY,
    created_at TEXT,
    model_spec_json TEXT,    -- llm provider, model, quantization, context length
    lora_adapter_id TEXT,    -- null until M18
    skill_set_hash TEXT,     -- hash of currently-enabled skills (covers M06 promotions)
    settings_hash TEXT,      -- hash of materially-relevant settings keys
    notes TEXT               -- "user swapped to Phi-3.5", etc.
  )
  ```
- A **generation bump** is triggered by:
  - LLM provider / model / quantization change (hash of
    `llm_settings`).
  - LoRA adapter load/unload (M18 only — for now, always null).
  - Enabled-skills set change (M06 promotion / demotion).
  - Materially-relevant settings change (defined list, not every
    setting — e.g. `retrieval_mode`, `agentic_max_iterations`, the
    seedling model). Full list lives in a `_GENERATION_SETTINGS`
    tuple in `evals/generation.py`.
- On generation bump, emit `CompanionActivityEvent(source="eval_run",
  kind="generation_bump")` so the user sees *"your companion's
  config changed — evals will restart their comparison window"*.
- Reports compare within the same `generation_id` by default;
  cross-generation comparisons are shown separately and flagged.
- **Why generation tracking is CRITICAL and non-optional:** without
  it, eval results mix pre-LoRA and post-LoRA runs, making the
  "did this LoRA help or hurt?" question that M18 depends on
  literally unanswerable. This is the M16/M18 interface.

**Not this phase:** the LoRA adapter code itself (that's M18).

#### Phase 5 — Report surface ("here's what I learned")

**Goal:** the user sees the companion's week, not a spreadsheet.

- Route / tab options:
  - *(a)* A new `evals` tab in `apps/metis-web/app/settings/page.tsx`
    (fastest path; lives in a hotspot file already; risk: looks like
    a settings page, not the product-principle-#1 surface).
  - *(b)* A new route at `apps/metis-web/app/evals/` (cleanest; risk:
    split from the constellation main view).
  - *(c)* A collapsible panel in the expanded `MetisCompanionDock`
    under "Recent activity" (most on-brand; risk: limited vertical
    space for chart).
  - **Recommendation:** ship (c) as the default surface with a
    one-line summary + a "see full report →" link that opens (b)
    for users who want depth. Avoid (a) — the settings page does
    not grow (product principle #4: *Skills over settings*).
- The default view is prose, not a chart:
  *"This week your companion got better at summarising your feeds
  (3 out of 4 recent summary tasks scored above their previous
  best). It regressed on retrieval over your journal index (2 out
  of 3 below last week's median). No new tasks added to the
  corpus this week — pin more reinforce-labeled traces to teach
  it what matters to you."*
- A sparkline per task-type (Q&A / summary / retrieval / reflection)
  sits under the prose for users who want the data.
- Per-task drill-down opens the trace-run explorer for that
  run_id, reusing the existing observability surface.
- Cross-generation note: when a generation bump occurred in the
  reporting window, prefix with *"your companion's configuration
  changed on {date} — comparisons across that line are not
  apples-to-apples"*.

**Not this phase:** fancy charting, cross-user leaderboards (never
shipping — privacy), export-to-CSV (v2 if anyone asks).

#### Phase 6 — Seed corpus auto-collection

**Goal:** a fresh install has no corpus. Seed it from actual use.

- Default heuristic (off by default, opt-in via settings key
  `evals_auto_seed_enabled`):
  - Every RAG run whose behavior profile scores above a threshold
    (high convergence, ≥N citations, no `fallback_triggered`,
    no anomalies) becomes a *candidate* corpus item.
  - Candidates go into `tasks` with `source_run_id` set and
    `tags=["auto-seed"]`, not surfaced to the eval run loop until
    the user confirms them in a nightly "review new eval tasks"
    prompt.
  - User can bulk-accept or bulk-ignore. Explicit `reinforce`-
    labeled runs skip the candidate step and land in the corpus
    directly (the existing `ArtifactConverter.export_as_eval`
    path).
- The first week after install is **collection only** — no eval
  report, just a *"learning what matters to you — first eval
  report in 7 days"* note in the dock. This is the base-rate honesty
  posture from *Blockers*.
- Second week onwards: first real eval report, with explicit
  N-of-runs displayed so the user knows how much signal to trust.

**Not this phase:** any automatic action on low eval scores (e.g.
auto-retry, auto-retrain). Evals observe, they don't fix.

#### Phase 7 (stretch, coordinates with M18) — LoRA gate

**Goal:** before M18 swaps in a new LoRA adapter, the user sees
whether it helped.

- When M18 trains a LoRA adapter, it produces a new candidate
  `generation_id` (let's call it `G_candidate`). The current
  production one is `G_current`.
- Eval harness runs every active task twice: once against
  `G_current`, once against `G_candidate`. Same tasks, same inputs.
- Report to the user: *"the proposed adapter improved N of M tasks,
  regressed K of M. Promote / discard / evaluate more."*
- **Key constraint:** this is the only gate that decides whether a
  LoRA adapter ships to the user's interactive path. Without it,
  M18 risks regressions the user only feels after they've
  committed.
- Deliverable in M16 is the *interface* (the dual-generation eval
  comparison API and report); the training path and the promote
  action are M18's.

**Not this phase:** the training code, the model swapping
mechanism, any GPU work.

### ADRs landed in Phase 1 + remaining optional decision

1. **ADR 0016 — Grading-signal strategy.** Landed in Phase 1.
  Locks in the v1 lanes (trace labels, thumbs, implicit behavior
  score), explicitly rejects external cloud judges, and defers local
  LLM-as-judge to v2.
2. **ADR 0017 — Eval-run storage format & companion-generation
  versioning.** Landed in Phase 1. Locks in `evals.db`, the
  `generations` table shape, and the bump-trigger criteria M18 will
  depend on later.
3. **ADR 0018 — Eval privacy posture.** Landed in Phase 1. Locks the
  default to local-only execution and keeps any future share flow out
  of M16 scope.
4. *(Optional, if M16 v2 needs it)* **ADR 0019 — LLM-as-judge model
  pinning.** If/when v2 layers on LLM-as-judge: which model, how is it
  frozen across generation bumps, what happens when the user changes
  the judge model, and how reviewer bias is surfaced.

### Coordination risks

- **M13 (Seedling + Feed)** owns the growth-signals pipeline and
  the overnight reflection cycle. M16 consumes both. Do not re-
  invent growth tracking. The Seedling worker is also the natural
  scheduler for background eval runs — hook in via the same
  `progress_cb` rather than running an independent cron.
- **M09 (Companion realtime visibility, Landed)** owns the
  `CompanionActivityEvent` bus and the companion dock. Eval runs
  emit `source: "eval_run"` on that bus. **Do not introduce a
  second event channel, a second dock, or a second subscribe
  hook.** See the identical coordination note in M13's plan doc
  — the smell is the same.
- **M06 (Skill self-evolution, Ready)** owns skill candidate
  promotion. A promoted skill triggers a generation bump (Phase 4).
  Coordinate: the promotion handler must call into
  `evals.generation.bump_if_needed()` so the bump isn't missed.
- **M18 (LoRA fine-tuning, stretch)** depends on M16. Phase 7
  above is M18's gate. Schema stability matters: once M16 ships
  Phase 4, the `generations` table cannot change shape cheaply —
  design it with LoRA in mind from day one.
- **M10 (Tribev2 homological scaffold, Draft)** is parallel. Its
  homology signals (retrieval topology stability, concept
  coverage gaps) could become *rubric grading* lanes in v3. Don't
  try to integrate v1 — note the opportunity in this doc and
  revisit when M10 lands.
- **M17 (Network Audit)** proves the "no phone-home" posture. M16
  must not need a waiver. Keep all eval code paths offline.
- **M01 (Preserve & productise, Rolling)** — the observability
  surface (`routes/observe.py`, `behavior_discovery.py`,
  `artifact_converter.py`) is already in the Preserve list.
  M16's work reinforces that surface, it doesn't relocate it.

### What NOT to do in M16

- **Don't build a generic model-eval framework.** This is
  *personal* evals — per-user, per-corpus, per-task. If the
  implementation starts to look like a mini version of
  `lm-evaluation-harness`, back out.
- **Don't use HumanEval / MMLU / GSM8K / any public benchmark as
  the eval set.** Those are the *stranger's mind* metric.
  VISION.md's entire pitch is the opposite. If a user wants to
  run HumanEval, that's an M14 (Forge) technique, not an M16
  feature.
- **Don't surface eval numbers as raw percentages the user has to
  interpret.** Frame as *"the companion got better at summarising
  your feeds"*, not *"aggregate_score rose 0.03"*. The raw numbers
  live in the drill-down for the curious; the headline is prose.
- **Don't allow any default-on upload of eval data — including to
  an ownership-attested endpoint.** Product principle #6; M17
  will prove this at the network layer; M16 must not violate it
  at the architecture layer. No telemetry. No opt-out. A user-
  initiated *"share this result"* is the only acceptable egress
  path, and it's out of scope for M16.
- **Don't auto-retry or auto-retrain on low eval scores.** Evals
  observe; they don't fix. Closing the "bad score → auto action"
  loop is its own project (closer to M18 in shape) and must not
  be bundled.
- **Don't grade the companion with the same LLM the companion is
  running.** Self-grading is gameable; the golden rule. If v2
  ships LLM-as-judge, the judge model is a separate pinned model
  in settings.
- **Don't build a cross-user leaderboard. Ever.** Even anonymised.
  Even opt-in. Even if a marketing idea says "the community would
  love it". The whole product premise is *your* companion on
  *your* machine. A leaderboard breaks the metaphor.
- **Don't double up on M13's growth-stages UI.** Seedling →
  Sapling → Bloom → Elder is M13's surface. The eval report is
  "here's what got better *within* your current stage". They
  share a dock surface but they are not the same chart.

### Key files the next agent will touch

Backend:
- `metis_app/evals/` *(new package)*
  - `corpus.py` — `EvalTask`, corpus read/write, JSONL migration.
  - `runner.py` — `run_eval`, batch runner, SSE integration.
  - `store.py` — `evals.db` schema, `runs` + `generations` tables.
  - `generation.py` — `current_generation_id()`, `bump_if_needed()`.
  - `grading.py` — per-lane scorers wiring into existing feedback/
    behavior stores.
  - `report.py` — aggregation + prose summary generator.
- `metis_app/api_litestar/routes/evals.py` *(new)* — `/v1/evals/*`.
- `metis_app/api_litestar/app.py` *(register router)*.
- `metis_app/services/skill_repository.py` *(hook into
  generation.bump_if_needed on candidate promotion)*.
- `metis_app/services/assistant_companion.py` *(no changes expected;
  judge pattern is reference only)*.
- `metis_app/services/artifact_converter.py` *(no changes expected;
  corpus seeds from existing write path)*.
- `metis_app/services/session_repository.py` *(no schema changes;
  read-only consumer)*.
- `metis_app/default_settings.json` *(add `evals_*` keys:
  `evals_enabled`, `evals_cadence_hours`, `evals_auto_seed_enabled`,
  `evals_share_optin`, `evals_judge_model_spec` [v2])*.

Frontend:
- `apps/metis-web/lib/api.ts` *(extend `CompanionActivityEvent.source`
  to include `"eval_run"`; add `EvalTask`, `EvalRun`, `EvalReport`
  types; add `runEvalTask`, `listEvalTasks`, `listEvalRuns`,
  `getEvalReport` helpers)*.
- `apps/metis-web/components/shell/metis-companion-dock.tsx`
  *(eval-in-progress badge; "here's what got better" one-liner
  slot)*.
- `apps/metis-web/app/evals/page.tsx` *(new route for the full
  report; only if Phase 5 picks option (b))*.
- `apps/metis-web/app/settings/page.tsx` *(hotspot — avoid growing
  it; only settings knobs land here)*.

ADRs (new):
- `docs/adr/0016-personal-eval-grading-strategy.md`
- `docs/adr/0017-eval-storage-and-generation-versioning.md`
- `docs/adr/0018-eval-privacy-posture.md`
- *(optional)* `docs/adr/0019-llm-as-judge-model-pinning.md`

### Prior art to read before starting

- `VISION.md` — especially *How an AI grows in METIS* (the
  personal-evals paragraph) and *Risks and honest tradeoffs* (the
  "growth rings, personal evals, and the morning surface aren't
  nice-to-have — they're the product" line).
- `plans/seedling-and-feed/plan.md` — M13's plan. The overnight
  reflection cycle (Phase 4) and the LoRA training-log capture
  (Phase 7) are the two upstream data sources M16 layers on.
- `plans/companion-realtime-visibility/plan.md` — M09's landed
  plan. The pub/sub wiring is the canonical template for eval
  progress events.
- `metis_app/services/artifact_converter.py` — the already-shipping
  eval-case exporter. Read before designing the corpus schema.
- `metis_app/services/behavior_discovery.py` — the implicit-score
  source. Read before designing the grading pipeline.
- `metis_app/services/session_repository.py` lines 148–177 — the
  feedback tables already powering the explicit-label and thumbs
  lanes.
- `docs/adr/0005-product-vision-living-ai-workspace.md` — the
  vision ADR; every eval-facing decision must stay consistent.
- `docs/adr/0004-one-interface-next-plus-litestar.md` — why the
  eval service is a Litestar route + SSE stream, not a separate
  daemon.
