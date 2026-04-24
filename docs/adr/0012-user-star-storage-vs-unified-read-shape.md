# 0012 — User-star storage stays `UserStar`; unified shape is a read-view

- **Status:** Accepted
- **Date:** 2026-04-24

## Context

[M12](../../plans/interactive-star-catalogue/plan.md) Phase 4 set out to
"unify" the two user-star type families that have grown in the codebase:

- `UserStar` (`apps/metis-web/lib/constellation-types.ts`) — the **legacy
  storage shape**. Normalised constellation-point coords (`x, y` ∈ ~[0, 1]),
  optional metadata fields, `UserStarStage = "seed" | "growing" |
  "integrated"`, `learningRoute: LearningRoute` (a structured object with
  ordered steps). Persisted today; consumed by every star-rendering code
  path in the web app.
- `CatalogueUserStar` (`apps/metis-web/lib/star-catalogue/types.ts`) — a
  placeholder declared during the M12 Phase 1 data-layer work. Inherits
  `CatalogueStar` (galaxy world-space `wx, wy` coords, `StellarProfile`,
  `apparentMagnitude`, `depthLayer`, `name`) and bolts on user metadata.
  Originally declared with a **divergent stage vocabulary** (`"seed" |
  "sprout" | "bloom" | "nova"`) and `learningRoute: string | null`. No
  code path instantiated it on `main` before this ADR.

Phase 4a (PR #539) shipped the user-visible promote contract — any
catalogue star can become a user star via the inspector. Phase 4b is this
ADR plus the adapter helper that materialises the unified shape.

The original "migrate `UserStar` → `CatalogueUserStar`" plan-doc framing
implied a single-PR storage migration. On execution that scope reveals
itself to be much larger than the rest of M12 combined:

1. **Coordinate-system flip.** Hundreds of sites consume `UserStar.x/y`
   (rendering, drag-and-drop, faculty inference, focus animation, the
   semantic-search shifter, the build-section editor, M09 SSE thought
   log, M10 BrainGraph node placement). Every one would need to switch
   from `[0, 1]`-normalised to unbounded world-space coords, or carry an
   inverse projection at every read site.
2. **Stage vocabulary divergence.** `UserStar.stage` is shipped data;
   migrating to a different vocabulary would need a backfill across the
   stored star DB and a sequence-aware mapping (`growing` → ?, etc.).
3. **`learningRoute` shape mismatch.** `UserStar.learningRoute` is a
   structured `LearningRoute` (id + ordered `LearningRouteStep[]` with
   `kind`, `manifestPath`, `tutorPrompt`, `status`). Reducing to a
   `string | null` is a lossy round-trip; promoting in the other
   direction is an unbounded blowup.
4. **No production consumer of the unified shape exists yet.** M14 (The
   Forge) is the eventual driver; today it is `Draft`.

The cost is multi-day refactor + migration risk on the most-churn file
in the repo (`apps/metis-web/app/page.tsx` at 99.8th-percentile churn).
The benefit is a uniform shape for a single yet-to-be-built consumer.

## Decision

Keep `UserStar` as **the canonical storage shape**. Reshape
`CatalogueUserStar` into the **unified read-view shape** that downstream
consumers (M14 Forge, M16 evals, future marketplace) use to read user
stars when they want them in catalogue-aligned form. The shape is
materialised on demand by an adapter; storage is unchanged.

Concretely:

1. `CatalogueUserStar.stage: UserStarStage` (legacy vocabulary).
2. `CatalogueUserStar.learningRoute: LearningRoute | null` (legacy shape).
3. New helper `userStarToCatalogueUserStar(user, options)` projects a
   `UserStar` into the unified shape. World-space coords come from the
   inverse of the existing projection helper. `StellarProfile`,
   `apparentMagnitude`, and `depthLayer` are derived deterministically
   from the user star id so the same star always projects to the same
   profile and magnitude.
4. The adapter is pure / side-effect-free / fully unit-tested.

This bridges the API surface that M12 promised without paying the
storage-migration cost.

## Constraints

- **Storage compatibility.** Existing user-star data stays readable. No
  backfill, no schema change, no version bump.
- **One coordinate system per star at write time.** The adapter does
  the projection at read time. Consumers that need world coords use
  `userStarToCatalogueUserStar`; consumers that need normalised coords
  keep using `UserStar` directly.
- **Determinism.** The adapter is pure of `(user, viewport)` — no clocks,
  no randomness — so the projected `wx/wy` and derived
  `profile`/`apparentMagnitude` are stable across renders for a given
  viewport.

## Alternatives Considered

### Full storage migration
Replace `UserStar.x/y` with `wx/wy`, drop the legacy stage vocabulary,
collapse `learningRoute` into a string. **Rejected.** Multi-day refactor
with high regression surface, no consumer that requires it today, and
the storage flip is a one-way door.

### Two parallel storage tables
Persist both shapes side-by-side, deduplicated on `id`. **Rejected.**
Doubles write paths and creates split-brain risk on every user-star
update. The adapter approach gives the same read shape with no
write-path change.

### Make `CatalogueUserStar` *extend* `UserStar` directly
Avoids the projection question by making the unified shape additive.
**Rejected.** The *purpose* of the unified shape is the
`CatalogueStar`-aligned identity (world-space coords, profile,
magnitude). Inheriting from `UserStar` keeps the bad legacy normalised
coordinate system at the centre of the new shape.

## Consequences

- M14 (The Forge) reads user stars through
  `userStarToCatalogueUserStar(...)` when it needs the unified shape.
- M16 (personal evals) gets the unified shape for free if it adopts the
  same read pattern.
- A future Phase 4c (post-v1) may revisit storage migration if mobile
  sync, multi-galaxy support, or LoRA fine-tuning's per-star contexts
  demand a single canonical shape on disk. The adapter approach does
  not preclude this — it is forward-compatible with a future flip.
- Reviewers should not see `CatalogueUserStar` and assume storage
  uses it. The JSDoc on the type now points at this ADR.

## Open Questions

- **Where does the viewport come from in non-render contexts?** The
  adapter requires a `viewport: { width, height }` to project
  coordinates. Render-loop consumers have it trivially; offline
  consumers (e.g. a CLI export) need a sensible default. We'll cross
  that bridge when the first such consumer appears.
- **Should the derived `apparentMagnitude` and `depthLayer` come from
  the legacy `size` field instead of a hash of the id?** Today `size`
  is a render hint (~0.8–1.4). The hash-derived magnitude is uniformly
  distributed across `[0, 6.5]`, which gives more visual variety but
  doesn't honour the user's manual size choice. Revisit when Forge or
  Evals UI surface either field.
