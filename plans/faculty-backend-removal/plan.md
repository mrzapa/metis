---
Milestone: M26 — Backend faculty taxonomy removal
Status: Draft
Claim: unclaimed
Last updated: 2026-05-03 by claude/constellation-ia-intake
Vision pillar: Cross-cutting
TDD Mode: pragmatic
---

> **Depends on M24 + M25 + M16 evals.** M26 replaces faculty-gap-scoring with cluster-gap-scoring across every backend pipeline that currently uses faculty IDs. Eval gate: cluster signal must achieve research-quality parity with faculty signal before flip. Read M24 + M25 plan stubs and the [combined design doc](../../docs/plans/2026-05-03-constellation-ia-reset-design.md) before starting.

## Why this exists

After M24 + M25 ship, the user-visible constellation is content-first and Projects-organised — but the backend still tags content by faculty IDs (8 in `app/page.tsx` data, 11 in `autonomous_research_service.py`) and runs the M04 reverse curriculum on faculty-gap-scoring. Leaving faculty as an "invisible internal forever" creates a permanent dual-codepath and a 11-vs-8 mismatch with no user-visible justification. M26 closes that gap.

The challenge: replacing the curriculum signal that M04 was tuned for risks regressing autonomous research quality. M26 gates on M16 evals.

## Design

Full design at [`docs/plans/2026-05-03-constellation-ia-reset-design.md`](../../docs/plans/2026-05-03-constellation-ia-reset-design.md) (M26 section). ADR at [`docs/adr/0019-constellation-ia-content-first-projects.md`](../../docs/adr/0019-constellation-ia-content-first-projects.md).

## Progress

*(milestone not yet started; depends on M24 + M25 + M16 evals being far enough along to validate the cluster signal)*

## Next up

Wait for M24 + M25 to land + M16 evals to be runnable on the curriculum-signal A/B comparison. Then Phase 1 — Eval design + harness.

## Pipelines affected

| File | Faculty → Cluster |
|---|---|
| `metis_app/services/autonomous_research_service.py` | `FACULTY_ORDER` → cluster IDs; query formulation seeded by cluster centroid keywords |
| `metis_app/services/comet_decision_engine.py` | Per-faculty gap scoring → per-cluster gap scoring |
| `metis_app/models/star_nourishment.py` | `FacultyNourishment` → `ClusterNourishment` |
| `metis_app/services/star_nourishment_gen.py` | Poetic copy templates rewired from `{faculty}` to `{cluster_label}` |
| `metis_app/services/news_ingest_service.py` | News classified to nearest cluster instead of faculty |
| `metis_app/services/news_feed_repository.py` | Schema migration: `faculty_id` → `cluster_id` |
| `metis_app/models/comet_event.py` | `faculty_id` field replaced with `cluster_id` |
| `metis_app/services/brain_pass.py` | Per-faculty reflection passes → per-cluster |
| Tribev2 classifier | Output rewired from faculty to cluster |

## Phases

| # | Phase | Scope | Est. |
|---|---|---|---|
| 1 | Eval design + harness | M26-specific eval tasks for curriculum-signal comparison; wire into M16 store | ~3 days |
| 2 | Cluster-gap-scoring service | New `cluster_gap_service.py` + tests (parallel to existing faculty-gap path) | ~3 days |
| 3 | A/B run + validation | Run autonomous research with both signals; compare evals; iterate cluster signal until parity | ~5 days (variable) |
| 4 | Pipeline rewrites | One file at a time; each commit pairs the rewrite with a regression test | ~5 days |
| 5 | Schema migration | News-feed schema rename + backfill from existing `faculty_id` via embedding-distance + tests | ~2 days |
| 6 | Tribev2 classifier rewire | Rewrite classifier output to cluster IDs | ~3 days |
| 7 | Companion copy migration | `star_nourishment_gen` template rewrite + cluster-label generator + tests | ~2 days |
| 8 | Final flip + cleanup | Delete `FACULTY_ORDER`, `FACULTY_DESCRIPTIONS`, faculty fields on data classes | ~1 day |

~3.5 weeks. Variable because Phase 3 may surface eval regressions.

## Blockers

- **M24 + M25 must be landed.** M26's cluster signal depends on M24's clustering service.
- **M16 eval store must be runnable** for the curriculum-signal A/B comparison.

## Notes for the next agent

- **Don't start without M16 evals on the eval-bench.** Phase 3 (A/B validation) is the gate.
- **Cluster-label generator quality matters for companion copy.** The poetic copy currently reads as `"the {faculty} region is sparse, almost bare"` — keyword-extracted cluster labels need to read at least as readably. Phase 7 invests specifically in this.
- **News-feed schema migration** must backfill existing `faculty_id` rows with their nearest `cluster_id` via embedding-distance — don't drop existing data.
- **Final flip is `Phase 8`** — only delete the faculty constants after every pipeline has been rewired and tested. Bisect-friendly history matters here for diagnosing any regressions.
