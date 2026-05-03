---
Milestone: M21 — UI critical-eye triage
Status: In progress
Claim: claude/frosty-hamilton-fd3889 (Phase 5 — constellation aesthetic pivot, #23–#27, code landed; awaiting verification + PR. P0 batch shipped via PR #588 + #6 request-storm dedup landed earlier on `claude/m21-p0-fixes`.)
Last updated: 2026-05-01 by claude/frosty-hamilton-fd3889
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
- **#8 Hard reloads on inter-page navigation. ✅ VERIFIED RESOLVED 2026-05-02 — no fix needed.**
  Live re-walk of `/` → `/chat/` → `/forge/` → `/settings/` → `/improvements/` → `/`
  on current `main` confirmed all six transitions are soft Next-router navs:
  - `window.__metis_doc_id` (random per-document marker) preserved across all six clicks → no document recreation.
  - `performance.getEntriesByType('navigation')` stays at length 1 throughout → no full HTML reload.
  - Network log shows only `?_rsc=…` payload fetches per transition, never a full HTML response.
  - Source-grep for `window.location.(href|assign|replace|reload)` and `location.(href|...)` in `apps/metis-web/`: zero matches. Both `<SetupGuard>` and `<DesktopReadyGuard>` use `router.replace` and `<Link>`.
  Likely cause of the original report: misinterpreting Next 16 dev-mode RSC payload fetches + Turbopack chunk loads as "full HTML reloads". The user's symptom may also have been transiently introduced and then incidentally fixed by other Phase 1 / 2 work (e.g. PR #588 hydration, PR #597 dedup). Either way, current `main` has no observable hard-nav.
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

- **#19 `motion.dev` reduced-motion warning. ✅ landed Phase 4 (P3).**
  `motion/react`'s informational `console.warn` ("You have Reduced
  Motion enabled… For more information visit
  https://motion.dev/troubleshooting/reduced-motion-disabled") is
  developer-facing and uninteresting to METIS's logs. New
  `<MotionConsoleFilter>` client component installs a one-shot
  console.warn wrapper that drops messages containing
  `reduced-motion-disabled` (or the canonical message text) and
  forwards everything else unchanged. Mounted once via
  `app/layout.tsx`; idempotent against double-mount in dev
  (`__metisMotionFiltered` flag).
- **#20 404 page has no "Back to home" link. ✅ landed Phase 4 (P3).**
  No `app/not-found.tsx` existed, so Next.js's default text-only 404
  was used. Added a custom one with the brand mark, an empathic
  one-line explanation, and two recovery actions (`Back to home`
  primary, `Open chat` secondary). No client JS, static, fast.
- **#21 Chat `Sources` panel "No sources yet" copy. ✅ resolved by
  PR #588 (P0 #2).** The original concern was the permanent empty
  state for users with no documents indexed; once PR #588 wired
  `/library/` to `<NyxCatalogPage>`, users have a path to add
  sources. Existing copy ("No sources yet. Sources will appear
  here when the assistant references documents.") is honest and
  doesn't need rewording. Marking resolved-via-#2 per the original
  triage note.
- **#22 Forge `RUNTIME CHECK` pattern — promote. (Punted.)** The
  RUNTIME CHECK card pattern (TimesFM, Heretic preflight badges) is
  genuinely good UX, and extending it to other optional-binary
  techniques would be valuable — but it's design + product work,
  not a polish fix. Filed as a follow-up idea instead of forcing it
  into a P3 polish PR. Belongs in M14's Phase 7 stretch or a future
  Forge enhancement pass.

### P-aesthetic (Phase 5) — constellation aesthetic critique

Filed 2026-05-01 from a direct user critique of `/`. Bundle of five
complaints, all addressed in a single phase rather than spread across
P1–P3 because they're a coherent aesthetic pivot (not a normal bug list).

- **#23 Faculty title text under each anchor was confusing.** "Memory",
  "Perception", "Knowledge" etc. paint as labels under the constellation
  anchors and the user reported they read as opaque "function"
  declarations — the labels announce a category without giving the user
  a way to see what makes a star belong to it. **Status: landed
  Phase 5.** The `fillText(n.concept.title, …)` in `drawNodes`
  (`apps/metis-web/app/page.tsx`) is removed; hit-zone bookkeeping
  (`syncNodeLabelLayout`) still runs because semantic-search and drag-
  to-reassign depend on it. Reverts to one-line.
- **#24 Central METIS star read as a JJ Abrams lens flare.** The
  rotating orbit ring (always-spinning dotted circle), 8-point
  diffraction spikes (slowly rotating cross/star pattern), and
  orbiting particles around the core combined to feel like
  decorative lens flare with no meaning. **Status: landed Phase 5.**
  Sections 3a / 3b / spike loops in `drawPolarisMetis` removed. Core
  star, halo, micro-nodes, animated constellation lines kept — those
  carry the actual visual story. Note: M10's H₁ topology data used to
  ride on the orbit-ring alpha and spike length; that signal currently
  has no visual surface and will need a new one if it ever becomes
  load-bearing.
- **#25 Star Observatory dialog tab strip overlapped under scaling.**
  Two `flex flex-wrap gap-2` button rows in
  `components/constellation/star-observatory-dialog.tsx` — the outer
  view tabs (`Add and build / Attached sources`) and the inner build
  tabs (`Choose files / Upload files / Local paths`) — wrapped into
  multiple rows under browser zoom or in narrow `sm` dialog widths,
  visually colliding with content below. **Status: landed Phase 5.**
  Both rows converted to `flex flex-nowrap … overflow-x-auto …
  [scrollbar-width:none] [&::-webkit-scrollbar]:hidden` with
  `shrink-0 whitespace-nowrap` on each pill so they scroll
  horizontally instead of wrap-stacking.
- **#26 Hover tooltip for `classical`-tier stars read as AI slop.**
  Auto-generated Bayer/Flamsteed name plus the footer
  `Classical star name (Bayer/Flamsteed convention)` displayed on every
  landmark and named-catalogue mouseover. The combination of generated
  name + over-explanatory footer felt machine-written. **Status:
  landed Phase 5.** Hover branches in `onCanvasPointerMove` for
  `classical`-tier hits removed. The dead `showCatalogueTooltip`
  function and the now-unused `getHoveredLandmarkStar` hit-test were
  also deleted (orphan cleanup); unused imports `SeededRNG`, `fnv1a32`
  dropped from `app/page.tsx`. The tooltip JSX element stays as a
  no-op surface; `hideCatalogueTooltip` stays as a defensive cleanup
  no-op called from many tool-change paths. ADR 0006's tiered-naming
  policy is preserved at the *data* layer (names still generate, still
  show on click in the catalogue inspector / observatory) — only the
  hover *surface* is removed.
- **#27 (Meta) Overall constellation page felt unappealing.** Items
  #23, #24, #26 together address most of #27 by removing the visual
  noise (text labels, lens flare, hover-pop names). Re-walk after
  Phase 5 lands; if the page still feels off, that's a follow-up
  bundle.

**Design pivot recorded in:**
[`docs/adr/0006-constellation-design-2d-primary.md` → *Addendum —
2026-05-01 (M21 Phase 5)*](../../docs/adr/0006-constellation-design-2d-primary.md).
The amendment is honest about what changed: the original ADR
over-specified *how* tiered names should surface (tooltip with footer)
when the load-bearing decision was the *naming policy itself*. Policy
preserved, surface removed.

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
- **Phase 5 — Constellation aesthetic pivot (#23–#27).** User critique
  of the home page's first impression: faculty labels confusing, central
  star reads as lens flare, observatory dialog tabs overlap under
  scaling, classical-name hover tooltip reads as AI slop. Bundles a
  recorded design reversal of two M02 / ADR 0006 implementation choices
  — see ADR 0006 *Addendum — 2026-05-01* and the Phase 5 entries above.

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

**Phase 5 (constellation aesthetic pivot, #23–#27):** code landed on
`claude/frosty-hamilton-fd3889` (this branch). Verification + PR
pending. Files touched:
- `apps/metis-web/app/page.tsx` — faculty title `fillText` removed in
  `drawNodes`; sections 3a/3b/spike-loops removed in `drawPolarisMetis`;
  `showCatalogueTooltip` + `getHoveredLandmarkStar` deleted; classical-
  hover branches in `onCanvasPointerMove` collapsed to a single
  `hideCatalogueTooltip()`; `SeededRNG`, `fnv1a32` imports dropped.
- `apps/metis-web/components/constellation/star-observatory-dialog.tsx`
  — both tab strips (outer view tabs + inner build tabs) converted to
  horizontal-scroll containers.
- `docs/adr/0006-constellation-design-2d-primary.md` — *Addendum —
  2026-05-01 (M21 Phase 5)* recording the design reversal.
- `plans/IDEAS.md` — Decision flipped to *Merged into M21 Phase 5*.

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
