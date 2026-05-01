---
Milestone: M21 — UI critical-eye triage
Status: In progress
Claim: claude/objective-napier-432f1e
Last updated: 2026-05-01 by claude
Vision pillar: Cross-cutting
TDD Mode: pragmatic
QA Execution Mode: agent-operated
---

## Why this exists

A full agent-operated walk of the metis-web UI on 2026-05-01 (every routable
page on desktop / tablet / mobile, with the local Litestar API and Next dev
server both running) surfaced a backlog of bugs, perf issues, and UX
inconsistencies that span many milestones and don't belong in any of them
individually. This row collects them as a single triage pass so they can be
fixed in priority order rather than being absorbed piecemeal into whatever
feature work happens to touch the file.

The bug list itself is the milestone: every entry below is a discrete fix,
each with a one-line repro. Land them in priority bands (P0 → P3) so the
most credibility-damaging issues clear first.

The QA pass is documented in the session transcript (2026-05-01); see also
the screenshots captured during the run (not committed — too noisy).

**TDD mode justification (pragmatic):** Most fixes are visual / structural
(SSR-safe rendering, dead-route removal, nav-component dedup). RED-step
tests for "Next.js dev overlay shows 1 Issue" or "the privacy tab said
read-only but the deep page has toggles" don't add signal — the visual diff
plus a manual re-walk after each fix is the verification. Where regression
risk is real (e.g. `/v1/atlas/candidate` removal — make sure no other
caller uses it; settings request-storm dedupe — make sure the dedup layer
doesn't drop legitimate refetches), targeted unit/integration tests get
written as the fix lands.

## Bug inventory (priority-ordered)

### P0 — broken or visibly wrong on first paint

- **#1 Hydration mismatch (every page).** `useReducedMotion()` returns
  `false` on the server but `true` on the client when prefers-reduced-motion
  is set, so SSR renders the `<svg>` ring branch and client renders the
  plain `<div>` branch in
  [`apps/metis-web/components/brand/metis-glow.tsx:138-156`](apps/metis-web/components/brand/metis-glow.tsx).
  Next.js dev overlay shows `1 Issue` on every page from first load; React
  tears down and re-renders the launch-stage tree on every navigation.
  **Fix shape:** SSR a stable shell (no motion branch), opt into the
  motion variant only after `useEffect` has run. M20-adjacent —
  coordinate with `claude/cranky-northcutt-42501d` if still active.
- **#2 `/library/` is a `notFound()` stub.**
  [`apps/metis-web/app/library/page.tsx`](apps/metis-web/app/library/page.tsx)
  is literally `notFound()`. VISION's "drop documents, paste URLs" loop has
  no home page — sources only surface inline in chat. **Decide:** delete the
  route entirely (and any links pointing at it) **or** ship a minimal
  documents-list view backed by `GET /v1/index/list`. Lean toward delete +
  redirect to `/?focus=library` until M14/M16 give it a real home.
- **#3 `/v1/atlas/candidate` returns 404 on every chat send.** Chat fires
  `GET /v1/atlas/candidate?session_id=…&run_id=…` immediately after creating
  a session. Backend has no such route. Find the caller in
  `apps/metis-web/components/chat/*` or `lib/api.ts`, remove the dead call
  (or rewire to whatever endpoint replaced it). Verify the privacy panel
  feed quiets down after the fix.
- **#4 Top navigation inconsistent across pages.**
  - `/` (home): `Metis home · Chat · Settings` (3 items)
  - Every other page: `Home · Chat · Forge · Settings · Research log`
  Two different `<nav>` components are rendered for `/` vs the rest. The
  Forge — central to Cortex per VISION — is invisible from the home page's
  top nav. Either align both navs or document why they differ (constellation
  takeover) with a visible alternative way to reach Forge.
- **#5 Setup-API-key contradiction.** Setup wizard step 2 invites a key
  paste; settings page warns "API keys are not editable here. The backend
  blocks `api_key_*` updates via this UI." Verify which surface is correct
  and align the copy. If the wizard uses an exempt first-run endpoint,
  surface that ("first-run keys persist via setup; later changes need
  `settings.json`").

### P1 — perf / request-storm

- **#6 `/v1/settings` called 30+ times on a fresh load.** 4-6 back-to-back
  per render. Symptoms of React-Strict double-mount + missing dedupe in
  [`apps/metis-web/lib/api.ts`](apps/metis-web/lib/api.ts). Same pattern for
  `/v1/forge/techniques`, `/v1/index/list`, `/v1/brain/scaffold`,
  `/v1/seedling/status`, `/v1/autonomous/status`. Fix: add a tiny in-flight
  request dedupe (key on URL + method) with a short cache window.
- **#7 `comets/events` long-poll abort spam.** Every nav produces multiple
  `200 OK [FAILED: net::ERR_ABORTED]` entries — polling hook starts before
  its `AbortController` is wired, or React 19 strict-mount triggers the
  teardown. Looks benign but pollutes the privacy-panel feed.
- **#8 Hard reloads on inter-page navigation.** Network log shows three
  full HTML/chunk reload chains when moving `/` → `/chat/` → `/setup/` →
  `/chat/`. Investigate whether soft `Link` navs are being defeated by
  `window.location.href = …` redirects in setup-guard hooks or
  `DesktopReadyGuard`.
- **#9 "Try it instantly" hides a multi-second model load.** After
  *Get started* + first chat send, the streaming spinner ran for 12+
  seconds with zero progress feedback while the webgpu Bonsai-1.7B
  presumably downloaded. Most fragile UX moment in the app — needs a
  first-load progress hint ("Downloading model… 200MB / 1.2GB").

### P2 — visual / UX bugs

- **#10 Companion chip + Issue badge always cover bottom-right edge content.**
  These floating chips obscure form labels (settings → "LLM provider"),
  privacy table rows, and chat footer hints on mobile. Add safe-area
  padding to page chrome or auto-hide on hover near the chip.
- **#11 "Discover everything" decorative heading clipped on home.** Big
  bottom-left text consistently overlaps the constellation toolbar
  (`SELECT / HAND / +ADD`) at narrow widths and on mobile.
- **#12 Setup banner overlaps top nav at narrow viewports.** "Workspace
  not set up yet · Set up →" sits directly on top of the `Chat / Settings`
  nav links — text bleeds through.
- **#13 Setup page allows revisit but ignores existing state.** After
  browser-only setup, `/setup/` shows the same first-run cards. Add a
  "Browser-only is currently active" indicator + a switch path.
- **#14 Triple naming inconsistency on improvements page.** URL
  `/improvements/`, nav label "Research log", page heading "Improvement
  Pipeline". Pick one.
- **#15 Settings → Privacy & network tab inconsistency.** Tab states
  "Read-only in this build. Kill-switch toggles… land in the next update
  (Phase 5c)" but the linked `/settings/privacy/` page has working
  airplane-mode and per-provider checkboxes. Either the deep page is the
  next-update surface that shipped early, or the read-only banner is stale.
  Reconcile.
- **#16 `/design/` kitchen-sink leaks into production.** Public route, no
  DEV-only gate, no nav, no exit button. Gate behind
  `process.env.NODE_ENV !== "production"` or move under `/_internal/design`.
- **#17 `/chat/` silently redirects to `/setup/` on first run.** No
  contextual hint. Show a one-line "Finish setup to start chatting" banner
  on the setup page when arriving from a redirect.
- **#18 Network-audit discoverability card overlays content.** "METIS
  shows you every outbound call" card sits over the Knowledge constellation
  on desktop and consumes ~25% of mobile viewport. Needs shadow/backdrop
  separation, smaller mobile variant, or anchored placement away from
  meaningful canvas content.

### P3 — minor

- **#19 `motion.dev` reduced-motion warning fires on every render.** Log
  noise; throttle or suppress.
- **#20 404 page has no "Back to home" link.** Users dead-end on stale
  URLs. Add a link.
- **#21 Chat `Sources` panel "No sources yet" copy is permanent for new
  users** because `/library/` is a stub (#2). Resolves when #2 is fixed.
- **#22 Forge `RUNTIME CHECK` cards (TimesFM, Heretic) are excellent
  pattern — promote.** Suggest extending to other techniques that depend on
  optional binaries.

## Phases

Land in priority bands. Each phase = one PR.

- **Phase 1 — P0 fixes (#1, #2, #3, #4, #5).** Visible-on-first-load bugs
  that undermine credibility. Branch: this milestone's claim branch.
- **Phase 2 — P1 perf (#6, #7, #8, #9).** Network log goes quiet, model
  load is honest about its progress.
- **Phase 3 — P2 polish (#10–#18).** Visual / copy / safe-area / route
  gating. Group by file when possible to reduce PR count.
- **Phase 4 — P3 cleanup (#19–#22).** Bonus pass; can be skipped if
  bandwidth is short.

## Progress

- 2026-05-01 — Milestone filed; QA walk completed by `claude` (agent-op).
  Bug inventory (#1–#22) captured. No code committed yet against this row.

## Next up

Phase 1 — start with #1 (hydration) as it lands on every page and is the
single visible "1 Issue" badge a reviewer sees first. Then #3 (dead atlas
endpoint, smallest fix), then #4 (nav alignment), then #2 (library stub
decision needs a one-line product call from the user — favor delete + soft
link until M14/M16 owns documents UX), then #5 (api-key contradiction —
might be a copy-only fix).

## Blockers

- **#2 needs a product decision:** delete `/library/` route entirely or
  ship a minimal documents page. Both are <1hr work; decision is who owns
  the documents surface long-term.
- **#5 needs a backend trace:** confirm whether the setup wizard's
  `/v1/settings` POST is actually allowed to set `api_key_*` (first-run
  exemption) or whether the wizard's key paste is silently dropped.

## Notes for the next agent

- The QA walk was agent-operated. Re-run it with the same `preview_*`
  tools after each phase to verify (look for "1 Issue" badge to disappear
  for #1, network log dedup for #6, etc.).
- The visible bug count (1 in the Next.js dev overlay) is artificially low
  because the overlay collapses identical hydration warnings; #1 actually
  fires on every page mount.
- Some entries here may overlap with active milestones — check before
  fixing:
  - **#1** touches `metis-glow.tsx` (M20 territory). Coordinate with
    `claude/cranky-northcutt-42501d` if M20 PR is still pending.
  - **#10** (companion chip) touches the seedling heartbeat widget from
    M13.
  - **#15** (privacy tab vs deep page) is M17 territory — its plan doc
    knows whether the deep page was a Phase 5c shipped-early or a stale
    banner.
- Branch naming note: this milestone was started on
  `claude/objective-napier-432f1e` (an existing worktree) instead of
  fresh `claude/m21-…`. Honour the original-name convention going
  forward; this is a one-off.
