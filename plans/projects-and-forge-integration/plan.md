---
Milestone: M25 — Projects + Forge integration
Status: Draft
Claim: unclaimed
Last updated: 2026-05-03 by claude/constellation-ia-intake
Vision pillar: Cosmos / Cortex
TDD Mode: pragmatic
---

> **Depends on M24.** M25 layers the Project primitive (drawable scoped workspaces) on top of M24's content-cluster placement. Read M24's plan stub and the [combined design doc](../../docs/plans/2026-05-03-constellation-ia-reset-design.md) before starting.

## Why this exists

ChatGPT Projects and Claude Projects are the dominant vocabulary for "scoped chat workspace" — files + chats + per-project instructions in one place. Metis has the visual shape ("draw lines between stars to scope a chat") but no plumbing. M25 adds the data model, the click-to-select-then-confirm UX, the line-rendering, and the per-Project Forge config.

## Design

Full design at [`docs/plans/2026-05-03-constellation-ia-reset-design.md`](../../docs/plans/2026-05-03-constellation-ia-reset-design.md) (M25 section). ADR at [`docs/adr/0019-constellation-ia-content-first-projects.md`](../../docs/adr/0019-constellation-ia-content-first-projects.md).

## Progress

*(milestone not yet started; depends on M24 landing first)*

## Next up

Wait for M24 to land. Then Phase 1 — Backend Project schema + repo.

## Phases

| # | Phase | Scope | Est. |
|---|---|---|---|
| 1 | Backend: Project schema + repo | `project_types.py` + `project_repository.py` + tests | ~2 days |
| 2 | Backend: Project routes + chat | `routes/projects.py` + project-scoped retrieval + tests | ~3 days |
| 3 | Frontend: select + confirm UX | Selection-mode state + pulse rendering + floating Confirm + create dialog | ~3 days |
| 4 | Frontend: line rendering + force pull | Cubic Bezier line drawing + force-directed pull integration with M24 clusters | ~3 days |
| 5 | Frontend: Project detail + chat | Detail panel + member management + Project-scoped chat sheet | ~3 days |
| 6 | Per-Project Forge | Project Forge UI section + resolution-rule wiring + tests | ~2 days |
| 7 | Recommender boost + verify | Wire same-Project boost into M24's `recommend` endpoint; browser-preview QA | ~1 day |

~2.5 weeks total.

## Blockers

- **M24 must land first.** M25 builds on M24's cluster placement and `recommend` endpoint.

## Notes for the next agent

- **Settings-store vs SQLite for Projects** — Phase 4 of M24 confirmed user stars persist via the settings store (`landing_constellation_user_stars` key, JSON blob in `metis_app/settings_store.py`), not via separate `/v1/stars` CRUD endpoints. The M25 design assumed Projects would be SQLite-backed first-class entities. Two options to revisit before M25 starts:
  1. Keep SQLite for Projects (different pattern from user stars; adds CRUD endpoints + repository).
  2. Mirror the user-star pattern — store Projects as `metis_projects` array under settings store (similar shape, simpler infra, but harder to support per-project chat history if the array grows beyond a few hundred entries).

  The size argument matters most: per-project chat histories don't fit cleanly into a settings JSON blob. Lean toward option 1 (SQLite) for the persistence layer, but consider migrating user stars to SQLite at the same time for consistency. **Decision deferred to M25 brainstorm; not blocking for M24 closure.**
- **Project = saved selection, not separate workspace.** Don't add project-owned uploads or a separate index. Stars own content; Projects are filters.
- **Click-to-select, not drag-to-draw.** User explicitly chose this in the brainstorm. The line is the *result* of confirm, not the gesture.
- **Per-Project Forge inheritance** uses a Reset-to-default link per technique, not a tri-state checkbox (see design doc *Open question 7*).
- **Project chat scoping** filters at retrieval time (vector store filter by member-star-IDs). Don't build a virtual index per Project.
- **UUID-embedding fallback for empty stars** — when a user star has both empty `label` and `notes`, M24's clustering service currently embeds the star_id (a UUID) as fallback, which produces near-arbitrary placement. M25's Project-pull layout doesn't fix this — it makes empty stars cluster with whoever happens to share UUID-letter patterns. Consider treating empty stars as `cluster_id=-1` (skip clustering) or assigning a default position at the canvas centre. File-tracking: `metis_app/services/workspace_orchestrator.py:get_star_clusters`.
