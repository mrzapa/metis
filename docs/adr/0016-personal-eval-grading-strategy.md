# 0016 - Personal Eval Grading Strategy

- **Status:** Accepted (M16 Phase 1)
- **Date:** 2026-05-01

## Context

M16 needs to answer a specific product question from `VISION.md`:

> Is this user's companion getting better at this user's tasks?

The repo already emits three usable signal families on `main`:

- `trace_feedback` labels written by `POST /v1/traces/{run_id}/feedback`
  (`reinforce`, `suppress`, `investigate`).
- `message_feedback.vote` thumbs attached to message rows.
- `BehaviorProfile`, a rubric-free heuristic summary derived from the
  trace store without calling another model.

There is also a local JSON-judge pattern in
`assistant_companion._promote_skill_candidates()`, but shipping that in
v1 would add another model call and a second source of reviewer bias
before METIS has any real personal-eval history to calibrate against.

Two constraints make the grading decision load-bearing:

1. **Cold start is normal.** Fresh installs and lightly-used workspaces
   will have zero thumbs, zero trace labels, and no seeded corpus yet.
   Missing signals cannot be treated as failures.
2. **The product surface is prose, not a benchmark dashboard.** The
   report must explain what improved or regressed, while keeping the raw
   mechanics available only in drill-down views.

## Decision

### 1. v1 ships three grading lanes

M16 v1 uses exactly these grading lanes:

1. **Trace label lane** from `trace_feedback.label`.
2. **Message vote lane** from `message_feedback.vote`.
3. **Implicit behavior lane** from `BehaviorProfile`.

No fourth lane ships in v1.

### 2. Lane normalization contract

Each lane produces a normalized score in `[0.0, 1.0]` plus optional
status flags:

- **Trace labels**
  - `reinforce` => `1.0`
  - `suppress` => `0.0`
  - `investigate` => no numeric contribution; set
    `review_required=true`
- **Message votes**
  - positive vote => `1.0`
  - negative vote => `0.0`
- **Implicit behavior score**
  - derived from `convergence_score`, `citation_count`,
    `citation_diversity_score`, and similar positive trace signals
  - penalized by `fallback_triggered`, `had_error`, and anomaly flags
  - normalized to `[0.0, 1.0]`

Missing lanes are omitted from the aggregate. They are not treated as
`0.0`.

### 3. Explicit feedback outranks heuristics

The aggregate score is a weighted blend of available lanes with weights
renormalized across whichever lanes are present:

- trace label lane: `0.50`
- message vote lane: `0.20`
- implicit behavior lane: `0.30`

This makes direct user feedback dominant when it exists, while still
allowing runs with no manual labels to produce a meaningful baseline via
the implicit lane.

If any `investigate` label is present, the run is still scored from the
remaining lanes but carries `review_required=true` so the report can
avoid describing it as a clean improvement.

### 4. Deferred and rejected lanes

- **Deferred to v2:** local pinned LLM-as-judge.
- **Deferred to v3:** task-specific rubric scoring.
- **Rejected for M16:** any cloud or external LLM-as-judge service.

### 5. Reporting semantics

The report surface talks about deltas in natural language by task type
and task history, for example "got better at summarising your feeds".
Raw per-lane scores remain part of the stored run record and can power a
drill-down view, but they are not the headline UX.

## Constraints

- The grading strategy must work when all explicit lanes are absent.
- The strategy must remain per-user and per-task; no generic benchmark
  import is part of M16.
- The grading path must not add a second model call in v1.
- The aggregate must be explainable from stored per-lane signals.

## Alternatives Considered

- **Implicit-only scoring.** Rejected because it ignores the user's
  strongest available preference signals when they do exist.
- **Explicit-only scoring.** Rejected because it leaves fresh installs
  and lightly-used workspaces with no score at all.
- **Ship local LLM-as-judge in v1.** Rejected because it adds cost and
  reviewer bias before the base lanes have any observed history.
- **Ship cloud LLM-as-judge in v1.** Rejected because M16 cannot depend
  on a new external grading service.

## Consequences

- `metis_app/evals/grading.py` becomes a lane combiner, not a monolith.
- Stored eval runs must persist the per-lane score blob and the
  `review_required` flag alongside the aggregate.
- The Phase 2 implementation can ship with no new feedback UI because it
  harvests signal that already exists on `main`.
- Weight tuning can happen later without changing the three-lane shape.

## Open Questions

- After real user history exists, should the message-vote lane gain more
  weight for task types that rarely receive trace labels?
- Should `investigate` promote a separate review queue in the UI, or is
  the run-level flag sufficient for v1?