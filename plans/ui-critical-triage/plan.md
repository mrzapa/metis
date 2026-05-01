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
- **#3 `/v1/atlas/candidate` 404 noise** *(reprioritised P0 → P3 on
  closer look)*. The endpoint exists at
  [`metis_app/api_litestar/routes/atlas.py:16`](metis_app/api_litestar/routes/atlas.py)
  and the 404 is **semantic** — "no candidate yet for this run". The
  frontend already handles it (`fetchAtlasCandidate` returns null on 404,
  see [`apps/metis-web/lib/api.ts:3102-3119`](apps/metis-web/lib/api.ts)).
  The privacy/network audit shows `127.0.0.1` calls as non-outbound, so
  the 404 doesn't pollute that. The only remaining cost is dev-console
  noise. Defer to a future API-cleanliness pass that flips the contract
  to `200 OK { candidate: null }`.
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
- 2026-05-01 — **Phase 1 (P0 fixes) implemented** on this branch:
  - **#1 hydration:** `apps/metis-web/components/brand/metis-glow.tsx`
    now defers the motion branch behind a `mounted` state set from
    `useEffect`. SSR + first client render produce the static branch
    (matching what reduced-motion users see permanently); animated
    variant opts in after hydration. The Next.js dev-overlay "1 Issue"
    badge that fired on every page should clear.
  - **#3 reprioritised P0 → P3:** the `/v1/atlas/candidate` 404 is a
    semantic "no candidate yet", correctly handled by the frontend
    (`fetchAtlasCandidate` returns null on 404). Local-API 404s don't
    count as outbound, so privacy panel stays clean. Defer to a future
    cleanliness pass (`200 OK { candidate: null }`).
  - **#4 nav inconsistency:** added Forge + Research log to the home
    page's inline `metis-nav` (`apps/metis-web/app/page.tsx`); item set
    now matches `<PageChrome>` everywhere. Comment explains why two nav
    components exist.
  - **#2 library stub:** wired `apps/metis-web/app/library/page.tsx`
    to render the existing `<NyxCatalogPage>` component (which was
    fully implemented and orphaned). NYX deep-links from chat artifacts
    can now reach the catalog landing. The `[componentName]/page.tsx`
    detail route stays out of scope for this phase.
  - **#5 setup/settings api-key contradiction:** discovered this was a
    *functional* bug (not just copy): the wizard's `handleFinish` sent
    `api_key_*` in the settings PATCH, which the backend always 403s
    unless `METIS_ALLOW_API_KEY_WRITE=1`. Wizard saves were silently
    failing for any user who pasted a key. Removed `api_key_*` from
    the PATCH payload (the in-memory key is still threaded into
    `IndexBuildStudio.settingsOverrides` for one-shot index builds —
    that path doesn't go through the settings gate). Updated the
    wizard's help copy to be honest about the constraint and direct
    users to `settings.json` or the env-var override.
- 2026-05-01 — **Verification:**
  - `tsc --noEmit` (with junction to main-repo `node_modules`) — only
    a single pre-existing error in
    `apps/metis-web/components/shell/__tests__/metis-sigil.test.tsx`,
    unrelated to my touched files. None of the four files I edited
    flag.
  - `vitest run` — 593 passed, 10 skipped, 2 test files skipped, 0
    failed. Exit 0.
  - **Browser-preview verify skipped** — Turbopack rejects a
    `node_modules` junction in the worktree ("symlink points out of
    filesystem root"), and the worktree itself has no `node_modules`
    install. The static evidence (tsc + 593 passing tests + mechanical
    diff inspection) is the verification for these specific edits.

## Next up

Phase 1 PR review, then Phase 2 (P1 perf): #6 settings request-storm
dedup, #7 comets/events abort spam, #8 hard-reload nav, #9 model-load
progress.

## Addenda

### 2026-05-01 — Codex P1 follow-up on Phase 1 #5

Codex review of [PR #588](https://github.com/mrzapa/metis/pull/588) flagged
that **#5's first cut introduced a false-ready state on step 5 of the
setup wizard**. Removing `api_key_*` from the PATCH payload was correct,
but `directChatReadiness` still treated `apiKey.trim().length > 0` as
proof of credentials. So a user could:

1. Pick Anthropic/OpenAI in step 1
2. Paste a key in step 2 (key is now intentionally never persisted)
3. See a green "Direct chat ready" pill on step 5
4. Click "Finish and open chat"
5. Land in `/chat` with no stored credential → first request fails

**Fix (this commit):**

- Drop the `apiKey.trim().length > 0` shortcut from
  `directChatReadiness` — only a *persisted* credential
  (`baselineSettings.api_key_<provider>` or `credential_pool[<provider>]`)
  counts as ready.
- Add a third state: `{ ready: false, wizardKeyOnly: true }` for the
  case where the user typed a key but no persistent credential exists.
- Step-5 launch summary now renders a distinct amber `KEY WON'T PERSIST`
  pill (different from `MISSING API KEY`) and an explanatory line
  pointing the user at `settings.json` and the env-var override —
  matching the same constraint surfaced on the wizard's API-key step.

Browser-preview verified via a temporary main-repo mirror of
`apps/metis-web/app/setup/page.tsx` (worktree can't run Turbopack
because of the `node_modules` junction limitation). Step 5 with
Anthropic + a pasted key correctly shows:

> KEY WON'T PERSIST · STARTER PROMPT STAGED
>
> Direct chat won't work yet for Anthropic: the wizard does not save
> API keys. Copy the key from step 2 into settings.json (or set
> METIS_ALLOW_API_KEY_WRITE=1 to let UI writes through), then return
> to chat.

`vitest run` after the fix: 593 passed, 10 skipped, 0 failed.

**Lesson for the next agent.** When you delete a write path, audit every
*read* path that used to depend on it. The wizard had two consumers of
`apiKey`: the PATCH payload (deleted in Phase 1) and the readiness
predicate (missed in Phase 1). The PATCH was the noisy bug; the
readiness predicate was the silent one. Codex caught it in review,
which is the system working — but a careful walk of all `apiKey`
references at the time of the original fix would have caught it too.

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
