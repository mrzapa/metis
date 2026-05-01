# 0017 - Eval Storage and Generation Versioning

- **Status:** Accepted (M16 Phase 1)
- **Date:** 2026-05-01

## Context

M16 needs two things that the current repo does not yet provide:

1. A queryable store for personal-eval tasks and run history.
2. A stable way to say whether two eval runs belong to the same
   "companion generation" so week-over-week deltas are meaningful.

The repo already has adjacent storage surfaces:

- `rag_sessions.db` for sessions, messages, and feedback.
- `traces/runs*.jsonl` for detailed trace events.
- `evals/golden_dataset.jsonl` as an append-only export path from
  `ArtifactConverter.export_as_eval()`.

The design choice here is whether to extend one of those existing
stores, or add a dedicated eval store that can evolve without coupling
itself to chat/session persistence.

## Decision

### 1. M16 gets a dedicated `evals.db`

Personal-eval state lives in a new SQLite database,
`evals.db`, stored alongside the existing local runtime data.

`rag_sessions.db` remains the source of truth for interactive session
history and feedback. M16 reads from it; it does not add new tables to
it.

### 2. `evals.db` owns three primary tables

The v1 schema is split into:

```sql
tasks(
  task_id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  task_type TEXT NOT NULL,
  source_run_id TEXT,
  payload_json TEXT NOT NULL,
  tags_json TEXT NOT NULL
)

runs(
  run_id TEXT PRIMARY KEY,
  task_id TEXT NOT NULL,
  generation_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  trace_run_id TEXT,
  signals_json TEXT NOT NULL,
  aggregate_score REAL,
  output_text TEXT,
  review_required INTEGER NOT NULL DEFAULT 0
)

generations(
  generation_id TEXT PRIMARY KEY,
  first_seen_at TEXT NOT NULL,
  runtime_spec_json TEXT NOT NULL,
  lora_adapter_id TEXT,
  skill_set_hash TEXT NOT NULL,
  settings_hash TEXT NOT NULL,
  notes TEXT NOT NULL DEFAULT ''
)
```

`payload_json` preserves the task shape harvested from
`export_as_eval()` so the corpus can evolve without repeated SQLite
schema churn. The JSON shape remains documented and validated in code.

### 3. `golden_dataset.jsonl` remains the seed and audit log

`evals/golden_dataset.jsonl` keeps its existing append-only writer.
M16 does not replace that path.

Instead, the Phase 2 corpus loader imports from the JSONL file into the
`tasks` table when:

- `evals.db` exists but `tasks` is empty, or
- the JSONL file contains rows whose `eval_id` has not been imported yet.

When importing seed rows, `task_id` is set to the source row's
`eval_id`. No separate per-run JSONL mirror ships in v1; traces already
record execution detail, and a second append-only run log would be
redundant until a concrete export use case appears.

### 4. `generation_id` is content-addressed, not a counter

`generation_id` is the SHA-256 hash of a canonical JSON object
containing the material comparison inputs:

- runtime model spec (provider, model id, quantization, context window)
- selected LoRA adapter id, if any
- enabled skill id set
- a curated subset of material settings keys

The `generations` table stores the canonical payload in
`runtime_spec_json`, the derived hashes, and `first_seen_at`.

This means:

- restarting METIS does not create a new generation
- reverting to a prior config reuses the same `generation_id`
- M18 can compare candidate and current generations without inventing a
  separate numbering system

### 5. Material settings are explicit

The generation fingerprint uses only settings that change behavior in a
way that makes score comparisons unfair. The implementation will keep
that allowlist in one place, `_GENERATION_SETTINGS`, inside
`metis_app/evals/generation.py`.

Cosmetic or reporting-only settings are excluded from the hash.

## Constraints

- The store must remain local-first and human-recoverable.
- Session persistence and eval persistence must be independently
  evolvable.
- Generation comparison must survive process restarts.
- The storage model must leave room for M18's LoRA gate without another
  schema reset.

## Alternatives Considered

- **Add eval tables to `rag_sessions.db`.** Rejected because it couples
  eval evolution to chat/session persistence and makes future cleanup
  riskier.
- **JSONL-only storage.** Rejected because task/run/generation queries,
  grouping, and comparison windows become awkward and slow.
- **Monotonic generation counter.** Rejected because it is stateful,
  restart-sensitive, and cannot naturally reuse an older generation when
  a user returns to an earlier config.

## Consequences

- M16 Phase 2 needs a dedicated store module under `metis_app/evals/`.
- Eval imports are idempotent because `task_id` reuses `eval_id` from the
  source JSONL row.
- Generation changes become diffable from stored JSON rather than hidden
  in a single opaque integer.
- A future export or backup story can be built on top of SQLite dump or
  a targeted JSON export, instead of forcing JSONL into the primary path.

## Open Questions

- Should v2 add a user-facing export of `tasks` and `runs` as JSON for
  backup/sharing, or is SQLite plus the seed JSONL sufficient?
- Which exact settings belong in `_GENERATION_SETTINGS` beyond the
  obvious retrieval and model knobs?