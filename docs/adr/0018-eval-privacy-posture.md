# 0018 - Eval Privacy Posture

- **Status:** Accepted (M16 Phase 1)
- **Date:** 2026-05-01

## Context

M16 touches some of the most sensitive product data in METIS:

- a user's personal task corpus
- stored eval scores over time
- run outputs that may include private notes, feeds, and documents

`VISION.md` sets the boundary clearly: METIS is local by default, cloud
features are opt-in, and no feature should quietly turn into telemetry.
M17 (Network Audit) makes that boundary visible at runtime, but M16
still needs an architectural rule for what privacy means in eval code
paths.

The main ambiguity is task execution. Personal evals are supposed to
measure the user's actual companion. Some users will keep that companion
fully local; others may explicitly configure a remote provider for normal
interactive work.

## Decision

### 1. Eval data stays local

M16 does not upload or synchronize any of the following by default:

- corpus tasks
- eval runs
- aggregate scores
- per-lane signals
- prose reports

There is no anonymous telemetry path, no background sync, and no
cross-user leaderboard in M16.

### 2. M16 introduces no eval-specific external service

Eval storage, grading, aggregation, and reporting are local-only.
M16 does not add:

- a cloud LLM judge
- a hosted rubric service
- a metrics collector
- a community benchmark endpoint

If the user's interactive companion is configured to use a remote model,
the eval runner may reuse that same runtime path when executing the task,
because that is the companion the user explicitly chose to evaluate.
Those calls are not a new eval-specific egress class; they are the same
provider choice METIS would make during normal interaction and remain
visible to M17's network audit surface.

### 3. Sharing is out of scope for v1

`evals_share_optin` may exist as a reserved settings key, but it remains
`false` and inert in M16 v1. Any future "share this result" or export
flow requires a separate milestone and a separate ADR.

### 4. Personal evals remain personal

M16 does not auto-import public benchmark corpora such as HumanEval,
MMLU, or GSM8K into the personal-eval path. The corpus is derived from
the user's own METIS activity and explicitly exported runs.

## Constraints

- The privacy rule must stay compatible with `VISION.md` principle #6.
- The rule must not make it impossible to evaluate the user's actual
  configured companion.
- Any network activity caused by eval reruns must remain attributable to
  an already-configured provider, not to a hidden eval subsystem.

## Alternatives Considered

- **Force all eval reruns to local models only.** Rejected because it
  would stop measuring the actual companion for users who explicitly run
  METIS against a remote provider.
- **Allow anonymous upload of aggregate scores.** Rejected because it is
  still telemetry and collapses the personal-eval metaphor into product
  analytics.
- **Use a cloud judge but keep the corpus local.** Rejected because it
  still leaks evaluation content to a second external service.

## Consequences

- The M16 runner must not silently call any second model or service just
  for grading.
- UI copy can honestly say eval storage and reports stay on the machine,
  while still reflecting the user's current companion configuration.
- M17 needs no special waiver for M16; it only needs to show the same
  provider traffic the user already opted into.
- A future share/export flow starts from a clean baseline: nothing leaves
  the machine today.

## Open Questions

- If a future export flow exists, should it produce a local artefact file
  only, or is a one-off encrypted share link ever compatible with the
  product posture?
- Should the UI explicitly mark eval runs executed against a remote
  provider so the privacy posture stays obvious at the point of use?