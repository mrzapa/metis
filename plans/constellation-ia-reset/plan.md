---
Milestone: M24 — Faculty UI purge + content-first IA + Add flow + Everything chat
Status: Ready for review
Claim: claude/m24-impl (all 6 phases shipped via 30+ commits — Phase 1 backend clustering + Phase 2 backend recommender + Phase 3 frontend cluster placement + Phase 4 AddStarDialog + Phase 5 EverythingChatSheet + Phase 6 cleanup; Task 3.4 partial cleanup landed in Phase 4 stretch; remaining faculty-ring rendering preserved for comet/RAG/focus consumers until M26)
Last updated: 2026-05-03 by claude/m24-impl
Vision pillar: Cosmos
TDD Mode: pragmatic
---

> **Coordinates with M02 / ADR 0006 / ADR 0019.** M24 ships the UI half of the constellation IA reset. M25 layers Projects on top. M26 removes the backend faculty signal end-to-end. Read [`docs/plans/2026-05-03-constellation-ia-reset-design.md`](../../docs/plans/2026-05-03-constellation-ia-reset-design.md) and [`docs/adr/0019-constellation-ia-content-first-projects.md`](../../docs/adr/0019-constellation-ia-content-first-projects.md) before starting any phase.

## Why this exists

VISION's claim that "stars are placed by faculty" is false on multiple counts: the taxonomy drifted from 8 to 11 across files, faculty has no user-visible value (direct user feedback 2026-05-03: "we struggled to see the use case"), and M21 Phase 5 already half-removed it. M24 completes the *user-visible* purge and replaces faculty-anchored placement with content-embedding clusters; introduces an AI-suggested Add flow; gives the central METIS star a real job (Everything chat).

Backend faculty signal stays as invisible internal through M24 + M25 — `comet_decision_engine`, `autonomous_research_service`, `star_nourishment_gen`, Tribev2 classifier are all untouched. M26 removes them after M16 evals validate the cluster-gap signal.

## Design

Full design at [`docs/plans/2026-05-03-constellation-ia-reset-design.md`](../../docs/plans/2026-05-03-constellation-ia-reset-design.md). Read it before any phase.

ADR at [`docs/adr/0019-constellation-ia-content-first-projects.md`](../../docs/adr/0019-constellation-ia-content-first-projects.md).

## Implementation plan

Task-by-task at [`docs/plans/2026-05-03-constellation-ia-reset-m24-implementation.md`](../../docs/plans/2026-05-03-constellation-ia-reset-m24-implementation.md). 17 tasks across 6 phases. Use `superpowers:executing-plans` to drive it (or `superpowers:subagent-driven-development` for in-session orchestration).

## Progress

All 6 phases shipped on `claude/m24-impl`:

- **Phase 1 — Backend clustering** (`star_clustering_service.py` + `GET /v1/stars/clusters` + tests). Landed.
- **Phase 2 — Backend recommender** (`POST /v1/stars/recommend` + cosine ranking + tests). Landed.
- **Phase 3 — Frontend cluster placement** (cluster-projection rendering replaces faculty-anchored layout for new stars; legacy faculty rings preserved for comet/RAG/focus consumers per the M26 carve-out). Landed.
- **Phase 4 — AddStarDialog** (file picker + recommender display + create-new fallback; in-flight guard; M24 stretch removed `showConceptAtNode` and the dead `activeNodeRef` state from `app/page.tsx`). Landed.
- **Phase 5 — EverythingChatSheet** (central METIS star click → ChatPanel against a virtual `_all_stars` index; per-index error surfacing + reranker carve-out doc). Landed.
- **Phase 6 — Verify + cleanup** (faculty-glyph side panel + dead `FacultyConceptPanel` removed; user-visible faculty copy purged in `app/page.tsx`; landmark tier in `star-name-generator` retired with the 8 classical-named constellations; dead `tool === "add"` canvas-pick path + ADD_CANDIDATE_HIT_RADIUS_PX constants removed). Landed.

Vitest 761/10 (frontend), backend pytest 1621/12 (no backend changes in Phase 6), tsc clean.

## Next up

Open the PR; browser-preview QA on main repo post-merge. The 7-step walk specified in the M24 implementation plan (Task 6.5) covers cluster layout, AddStarDialog flow, EverythingChatSheet, observatory cleanup, layout persistence, reduced-motion, and degraded-backend rendering. Browser-preview verification was deferred from this worktree because Turbopack rejects the vitest junction; main repo's dev server is unaffected. Once QA passes and the PR merges, flip `Status` to `Landed` with the merge SHA and update IMPLEMENTATION.md's M24 row in the same edit.

## Phases

| # | Phase | Scope | Est. |
|---|---|---|---|
| 1 | Backend: clustering service | `star_clustering_service.py` + `GET /v1/stars/clusters` + tests | ~2 days |
| 2 | Backend: Add recommender | `POST /v1/stars/recommend` + cosine ranking + tests | ~1 day |
| 3 | Frontend: cluster placement | Replace `FACULTY_CONCEPTS` rendering with cluster-projection rendering | ~3 days |
| 4 | Frontend: Add flow | `AddStarDialog` + file picker + recommendation display + create-new fallback | ~3 days |
| 5 | Frontend: Everything chat | `EverythingChatSheet` + central-star click handler + virtual-all-stars retrieval | ~2 days |
| 6 | Verify + observatory cleanup | Browser-preview QA; remove `faculty-glyph-panel`; purge faculty references in copy; retire 8 named landmark constellations from `star-name-generator.ts` | ~2 days |

~2 weeks total. Backend phases (1–2) ship safely under unchanged frontend. Frontend phases gate on backend.

## Blockers

- **Phase 3 migration of existing user data** — forced re-layout with session-scoped undo (see design doc *Open question 9*). Default: forced. Verify with user before locking.
- *(Resolved 2026-05-03)* Phase 6 named-landmark retirement was a blocker; user approved during brainstorm and ADR 0019's *Open Questions* records the resolution. Phase 6 Task 6.3 proceeds without further confirmation.

## Notes for the next agent

- **Backend faculty references stay untouched in M24.** Don't refactor `autonomous_research_service.py`, `comet_decision_engine.py`, `star_nourishment_gen.py`, or Tribev2 classifier — that's M26's scope. M04 reverse curriculum keeps working unchanged.
- **The 11-vs-8 faculty mismatch is real.** `app/page.tsx` uses 8; `autonomous_research_service.py:24` uses 11. Don't try to reconcile in M24 — both go away by M26.
- **`StellarProfile` archetype system survives** (per ADR 0006 carve-out). Don't break it.
- **Star Observatory dialog stays** — only the `faculty-glyph-panel` inside it is removed. Archetype picker, learning-route panel, attached-indexes management all survive.
- **Companion dock is untouched.** Companion-chat lives there; central-star Everything chat is the new RAG-over-all-stars surface, not a companion-chat duplicate.
- **Cluster placement is precomputed by the backend, fetched as a list of `(star_id, cluster_id, x, y)`, rendered by the frontend.** The frontend doesn't run clustering itself.
- **HDBSCAN + PCA are the default algorithms** but easy to swap. If clustering looks bad in Phase 1 evals, try k-means + UMAP.
- **Migration is derive-on-render** (à la M02 Phase 8.5 archetype migration). Cluster IDs and 2D coords are NOT persisted on `UserStar`; they're cached in the clustering service.
