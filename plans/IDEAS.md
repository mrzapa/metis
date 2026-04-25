# METIS — Ideas Inbox

> **This is the user's scratchpad.** Drop anything here — a paper, a feature
> wish, a UI tweak, a technique to try, a weird thought at midnight.
> Implementation agents **do not touch active plans based on things in here**
> unless a triage pass has promoted the idea into
> [`IMPLEMENTATION.md`](IMPLEMENTATION.md).

## How to use this file

- **User:** Append to *Open ideas* at will. No format required. A one-liner
  is fine. Link to papers, screenshots, tweets if relevant. Don't worry
  about triaging — just dump.
- **Agents:** Read this file when asked to. Only modify it in three ways:
  1. Append under *Agent observations* at the bottom if you spot something
     while working that the user should see.
  2. During an explicit triage pass (requested by the user), walk *Open
     ideas* top-to-bottom and promote / reject / park / merge each item per
     [`plans/README.md`](README.md).
  3. File a new intake entry under *Open ideas* when running the intake
     workflow (user asks to implement something from outside the repo) — see
     [`plans/README.md`](README.md#intake-workflow-for-implementation-requests-from-external-sources).

## Triage outcomes (what happens to an idea)

- **Promote** → becomes a new row in `IMPLEMENTATION.md` with a plan doc
  stub. Strike through here with a link to the new milestone row.
- **Reject** → strike through with a one-line reason. Stays in the file
  so we remember we considered it.
- **Park** → move to *Iced* at the bottom. Not rejected, just not now.
- **Merge** → fold into an existing plan doc's *Notes for the next agent*,
  strike through here, link to where it went.

---

## Open ideas

<!--
Append new ideas below. Newest at the top is fine.

When a user asks an agent to "implement X from GitHub" or similar, the
agent files it here using the template below (see plans/README.md →
"Intake workflow"). One-liner user notes are also welcome — the template
is only required for agent-filed intake entries.

Template for agent-filed intake:

### <short title>
- **Source:** <link or description>
- **Ask:** <one-line summary of the user request>
- **Context:** <anything the user said>
- **Filed:** YYYY-MM-DD by <agent/session>
- **Triage:**
  - What it is: <one paragraph>
  - Pillar fit: Cosmos / Companion / Cortex / Cross-cutting / doesn't fit
  - Overlap: <M## rows it touches>
  - Recommendation: Promote | Merge into M## | Park | Reject
  - Rough scope: patch | day | multi-day | multi-week | multi-month
- **Decision:** <awaiting go/no-go | promoted as M## | merged into M## | parked | rejected>
-->

### Web UI new-user walkthrough — P0–P3 punch list
- **Source:** Live click-through of `apps/metis-web` at localhost:3000 acting as a brand-new user with no context. Captured 2026-04-25 by claude/youthful-agnesi-8ab627 using the Claude-in-Chrome MCP, plus DOM/network instrumentation.
- **Ask:** File the findings as ideas and triage into an implementation plan.
- **Context:** User flagged that the UI has many issues, has lag in many places, has an ugly lens flare on the constellation page, that zooming all the way into the METIS star reveals misaligned sprite layers, that there are three sparkle/star icons on home with confusingly similar shapes, and that the setup process has too much text. We reset `basic_wizard_completed=false` and walked the actual first-run flow (which is gated except on `/`, `/setup`, `/diagnostics`, `/design`).
- **Filed:** 2026-04-25 by claude/youthful-agnesi-8ab627
- **Findings (grouped by severity):**
  - **P0 — first-run blockers**
    1. **`prefers-reduced-motion: reduce` breaks the page reveal animation.** Elements get `style="opacity: 0; transform: translateY(…)"` as the initial state, but the reveal-to-1 animation never fires under reduced-motion (`transition: 1e-06s` is set, but the trigger that should toggle the visible state never runs). Verified on Pipeline (`<h3>No entries yet</h3>` and the empty-state copy stuck at computed opacity 0) and on Chat right after Finish-and-open-chat. Until shaken loose by layout recalc/scroll, users with reduced-motion see invisible content. This is the dominant source of the "lag in many places" the user reported.
    2. **Setup-guard exempts `/` from the wizard redirect** ([components/setup-guard.tsx:16](apps/metis-web/components/setup-guard.tsx:16)). A fresh user with `basic_wizard_completed=false` lands on the constellation home with zero indication setup is required.
    3. **"DIRECT CHAT READY" badge in the wizard's Step 5 launch summary lies** when no API key was provided — chat is "ready" only because of the silent mock fallback.
    4. **Silent mock backend** returns `[Mock/Test Backend] / Short answer: Local mock backend executed successfully with deterministic output. / Citations: [S1] chunk_ids: [1] / Debug retrieved: …` styled like a real reply. Indistinguishable from a real answer to anyone outside the codebase.
    5. **API keys are not editable from the UI.** Settings page warns the user must edit `settings.json` at the repo root and restart the server. Hard-blocks any non-developer path.
  - **P1 — visual / rendering**
    6. **Lens-flare ring on the gold "+" New-Chat button** (bottom-right of `/`). Hard-edged blue-white circular halo around a warm-gold star — clashes badly with the rest of the design.
    7. **METIS central-star sprite is non-concentric.** At max in-app zoom (2000×) the inner core dot is offset down-and-right of the outer halo ring; the rays emanate from yet a third center point. Three layers drawn on different anchor coordinates.
    8. **Canvas DPR mismatch.** 1920×855 internal canvas CSS-stretched larger → rays/connector lines aliased and jagged at every zoom level. Should be `canvas.width = clientWidth * devicePixelRatio`.
    9. **Three near-identical sparkle/star icons on home page** with totally different actions (user call-out): purple "+" = thread-by-meaning search; gold "+" bottom-right = New Chat; gold sparkle/diamond top-right = spectral-filter panel toggle.
    10. **Detail panels overlap** when a star is selected (Faculty Sigil card clobbers the alignment-text sentence).
    11. **Translucent cards bleed background star labels through** ("onomy", "detection", "observation" visible behind the Stellar Identity card).
  - **P1 — broken interactive features**
    12. **"Type to thread stars by meaning…" search is dead.** Typing + Enter fires zero network requests, doesn't filter the canvas, doesn't highlight matching labels (e.g. "memory" with the Memory star visible on screen).
    13. **Spectral-class filter and magnitude slider don't visibly do anything.** Clicking "K" updates URL to `#fams=K`. Dragging magnitude updates URL to `#fams=K&mag=2`. Canvas renders identically. Zero network calls. Pure URL theater.
    14. **Magnitude slider's bounding rect is reported at x=1591 in a 1568-wide viewport** — possible layout overflow at this width (reproducible in default Chrome window).
  - **P1 — performance / network**
    15. **Chat send latency on mock backend = ~2.2s** for `/v1/query/direct`. Plus ~7 other API calls fanned out around it.
    16. **Redundant API fan-out per chat send**: `/v1/assistant` x3, `/v1/sessions` x2, `/v1/seedling/status` x3, `/v1/settings` x4 — within a few seconds.
    17. **31.5-second long-poll connections** held open by `/v1/comets/active` (two parallel) and `/v1/comets/events?poll_seconds=10`.
    18. **One 404 was blocked by Chrome** for sensitive query-string data: `[BLOCKED: Cookie/query string data]` — possible PII in URL params (must investigate).
    19. **Home FCP = 696ms / load = 334ms** on localhost — slower than expected for a local Next dev server. Probably acceptable; flag-and-defer.
  - **P2 — information architecture**
    20. **Nav is inconsistent**: home shows `Chat / Settings`; every other page shows `Home / Chat / Settings / Diagnostics / Pipeline`. Why hide half on home?
    21. **Diagnostics in primary nav** — dev/ops page surfaced like a normal feature.
    22. **Implicit Forecast feature**: Settings has Forecast (TimesFM) defaults, but Chat only exposes `Direct / RAG` toggle. No way to use Forecast from the UI.
    23. **Companion overlay** opens by default, persists across pages, and covers the right pane on Chat (Sources panel).
  - **P2 — onboarding / copy** (user call-out: setup has too much text)
    24. **Setup pages drown the user in copy**: hero card + "QUICK SETUP" eyebrow + H1 + body description + step tabs + step number + step heading + step subhead + body description + cards with their own descriptions + sidebar "WHAT THIS UNLOCKS" panel that often duplicates the body. Per step.
    25. **Step tabs truncated** ("1. Choose the primary model …", "2. Add credentials only if l…") — user can't read what step labels actually say.
    26. **Wizard headings use first-person from the AI** ("Choose how I should embed documents", "Add credentials only if I need them") — inconsistent voice and slightly weird.
    27. **Default selections cause silent mismatches**: Anthropic pre-selected at step 1, OpenAI pre-selected at step 3 for embeddings — the combo requires both keys but neither is required to proceed.
    28. **Chat toolbar jargon**: `Agentic off`, `Heretic`, `mock / mock`, `Evidence Pack`, `local_gguf` — no tooltips.
    29. **Astronomy metaphor untranslated**: Faculty Sigil, Stellar Identity, Spectral Class M7 V, Magnitude ≤ 6.5, halo/rim/core/accent palette, "Main sequence" — no glossary.
    30. **"Discover everything" hero copy only paints after a click** — hidden on first impression.
    31. **"Seedling heartbeat" × 6** in companion-overlay Recent Activity is opaque jargon.
  - **P3 — minor**
    32. **"Export PPTX"** button visible on Chat → Sources panel even when "No sources yet."
    33. **No first-run banner on `/`**: the home page is the user's first impression and currently teaches them nothing about getting started.
- **Triage:**
  - What it is: A bundle of UI/UX defects from a real new-user walkthrough — a mix of one near-systemic accessibility bug (reduced-motion), several broken features (thread search, spectral filter, magnitude), several visual/sprite bugs, network noise, and a lot of copy/IA polish. None of these justify a new milestone; nearly all fold into existing rolling/in-flight work.
  - Pillar fit: **Cross-cutting** (M01 owns "preserve and productise" — surfacing existing features, killing dead paths). Some items map to **Cosmos** (M12 interactive star catalogue) and one to **Companion** (M13 seedling jargon).
  - Overlap:
    - **M01** (Rolling) — natural home for items 1, 2, 3, 4, 6, 7, 8, 9, 14, 15, 16, 17, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 32, 33.
    - **M12** (Ready, claim active) — items 10, 11, 12, 13 (these are interactive-star-catalogue surface defects).
    - **M13** (In progress) — item 31 ("Seedling heartbeat" jargon belongs with that milestone's UX work).
    - **M17** (Landed; Phase 8 deferred) — item 18 (the blocked URL with query-string data needs a security-posture pass).
    - **vision question** — item 5 (UI-editable API keys) reopens the *settings.json-only credentials* posture; should be a tiny ADR before any code change.
  - Recommendation:
    - **Merge** the bulk into M01's plan doc as a "Web UI new-user audit" notes block under *Notes for the next agent* with the full findings + priorities.
    - **Merge** items 10/11/12/13 into M12's *Notes for the next agent* (constellation interactive surface).
    - **Merge** item 31 into M13's *Notes for the next agent*.
    - **Park** item 5 (UI-editable API keys) as its own *Iced* entry until M17 next-up — it ties back to the same posture decision as 2026-04-18's parked telemetry idea.
    - **Park** item 18 (blocked URL / PII) until reproducible — needs a verified network capture before promoting; flag for M17 if confirmed.
    - **Park** item 19 (home FCP 696ms) — not user-blocking; revisit if perf becomes a complaint.
  - Rough scope per merge target:
    - **M01 batch**: P0 fixes ≈ 1–2 days · P1 visual ≈ 1 day · P1 perf/network ≈ 1 day · P2 IA ≈ half-day · P2 copy ≈ multi-day · P3 ≈ patch. Aggregate: ~1 working week if attacked by one agent in priority order.
    - **M12 merges**: ≈ 1–2 days inside the existing claim window.
    - **M13 merge**: patch.
- **Decision:** **Merged + Parked** 2026-04-25.
  - **Merged into [M01](../docs/preserve-and-productize-plan.md)** — items 1–4, 6–9, 14–17, 19–30, 32–33 captured under *Web UI new-user audit (2026-04-25)* with a 6-phase implementation plan.
  - **Merged into [M12](interactive-star-catalogue/plan.md)** — items 10, 11, 12, 13 captured under *Notes for the next agent → Web UI new-user audit findings*.
  - **Merged into [M13](seedling-and-feed/plan.md)** — item 31 captured under *Notes for the next agent → Web UI new-user audit finding*.
  - **Parked in *Iced* below** — items 5 (UI-editable API keys), 18 (blocked-URL/PII), 19 (home FCP).

### ~~founders-kit — strategic review pass~~ → merged into M15 ([`plans/pro-tier-launch/plan.md`](pro-tier-launch/plan.md))
- **Source:** https://github.com/avinash201199/founders-kit
- **Ask:** Walk the founders-kit repo and propose tweaks to `VISION.md` and `plans/IMPLEMENTATION.md` (plus overall strategic direction) if warranted.
- **Context:** User flagged this as a knowledge source to cross-check METIS's strategy against.
- **Filed:** 2026-04-18 by claude/review-metis-strategy-EiscA
- **Triage:**
  - What it is: A curated awesome-list for founders — ~40 sections linking books, essays (Paul Graham, Sam Altman), YC content, co-founder matching, equity splits, KPIs/OKRs, design tools, growth/marketing stacks, cloud infra, payments, fundraising (pitch decks, angel/VC lists), launch venues (Product Hunt, Betalist, HN), and startup programs / cloud credits. General-purpose for any early-stage startup; not specific to AI, local-first, or indie lifestyle businesses.
  - Pillar fit: Mostly **doesn't fit the vision**. METIS is an explicit lifestyle business — no VC, no team, no enterprise/compliance, no co-founder search, no hiring. ~70% of founders-kit (fundraising, hiring, team ops, enterprise SaaS plays) is actively contra-vision per `VISION.md` "What we are explicitly not doing". A thin slice maps to **Cross-cutting** launch/pricing work under M15.
  - Overlap: Only M15 (*Pro tier + public launch*) — launch venues (add Betalist, Product Hunt, Indie Hackers alongside existing HN/r/LocalLLaMA), Stripe/lifetime-deal playbooks, newsletter tooling for marketing site. Possibly M01 preserve-and-productize's onboarding work (time-to-magic-moment). No overlap with Cosmos/Companion/Cortex milestones.
  - Recommendation: **Reject** as a wholesale input to vision; **Merge** a narrow slice into M15's plan doc when that milestone drafts. No change to `VISION.md` warranted — the current vision already took a deliberate stance against the kinds of moves founders-kit optimizes for (VC, team, enterprise), and generic startup advice shouldn't dilute that stance.
  - Rough scope: harvest captured in [`plans/pro-tier-launch/plan.md`](pro-tier-launch/plan.md) on 2026-04-18 as a thin stub under *Notes for the next agent*. No further work until M15 is claimed.
- **Decision:** **Merge into M15** — harvest captured in [`plans/pro-tier-launch/plan.md`](pro-tier-launch/plan.md) (2026-04-18). Onboarding-measurement thread (local-first product analytics) split out as a separate idea below.
- **Deeper pass notes (2026-04-18):** After fetching the actual links (not just section headings), concrete items worth folding into M15 if/when promoted:
  - **AlternativeTo + SaaSHub listings** — METIS is genuinely *alternative-to* Jan, LM Studio, Open WebUI, AnythingLLM; these directories are a free distribution channel aligned with the vision.
  - **Niche developer launch venues** beyond HN/r/LocalLLaMA — Lobsters, DataTau, Designer News, Changelog, Sidebar, Indie Hackers, r/SideProject, r/IMadeThis, AwesomeIndie, SideProjectors.
  - **Privacy-first analytics** (Plausible / Pirsch / Simple Analytics / Fathom) — brand-coherent choice for the marketing site given METIS's "nothing phones home" stance. Google Analytics on the marketing site would be tonally off.
  - **Buttondown / Substack** — a weekly "what METIS learned this week" growth-log newsletter ties directly to the *Intelligence grown, not bought* promise and doubles as distribution. Worth considering as an M15 content mechanic.
  - **Merchant-of-Record payments** (Dodo Payments / Paddle / Lemon Squeezy) — Stripe alone does not handle global VAT for an indie seller. Genuinely net-new consideration for M15 — METIS has zero payments decisions so far.
  - **Design pattern libraries** (Mobbin / Page Flows / UX Archive / Pttrns / SaaSPages) — reference material for M02 / M12 / M14 UI polish. Not a vision tweak; just bookmarks.
  - **Non-findings:** No lifetime-deal platform playbooks (my earlier note about AppSumo guidance was wrong — the kit doesn't cover LTD ops). AI-tool section is copywriting/chat (Copy.ai, Jasper) — not relevant. PG/Sama essays are mostly VC/YC-shaped; only *Do Things That Don't Scale* and *Maker's Schedule* are universal — already implicit in METIS's indie stance.
  - Triage recommendation unchanged: **Reject** at vision level, **Merge** the items above into M15's plan doc when it drafts.

---

## Agent observations

<!-- Agents append here when they notice something the user should see. -->

*(empty)*

---

## Iced

<!-- Parked ideas — not rejected, not active. -->

### Local-first product analytics for onboarding measurement
- **Source:** Observation from founders-kit review pass (2026-04-18)
- **Ask:** Decide how METIS measures whether onboarding works — time-to-magic-moment, setup-wizard completion, first-query success — without violating *local by default, always*.
- **Context:** M01 (preserve-and-productize) frames onboarding tactically as "route to setup wizard if no config"; there is currently no measurement layer. Founders-kit surfaces PostHog / Microsoft Clarity / session replay as defaults, but all are cloud-hosted and would contradict the *nothing phones home* stance. Options to weigh when this comes up: self-hosted PostHog, opt-in anonymized telemetry (single-pixel ping), local-only event log inspectable by the user through the trace timeline, or no remote analytics at all. This touches M01 (onboarding) and has real vision tension with M17 (Network audit), which argues for treating both as a single posture decision.
- **Filed:** 2026-04-18 by claude/review-metis-strategy-EiscA
- **Triage:**
  - What it is: A posture decision, not a feature. How (if at all) does METIS observe its own users' behaviour, and how does that square with local-first?
  - Pillar fit: Cross-cutting (affects M01 onboarding, M15 launch, M17 network audit).
  - Overlap: M01 (Rolling), M15 (Draft needed), M17 (Draft needed).
  - Recommendation: **Park** until M13 (Seedling) lands, then revisit alongside M17 so the product-telemetry and outbound-call posture are decided together rather than drift-wise.
  - Rough scope: posture decision → ADR (1 day). Implementation of the chosen option (if any) → multi-day.
- **Decision:** **Parked** 2026-04-18. Revisit when M13 lands or when M17 (Network audit) is next-up — whichever comes first.

### UI-editable API keys (vs settings.json-only)
- **Source:** Item 5 of the *Web UI new-user walkthrough — P0–P3 punch list* (2026-04-25).
- **Ask:** Decide whether API keys should be settable from the web UI (with appropriate at-rest protection) instead of only via hand-editing `settings.json` at the repo root + restarting the server. The Settings page currently shows two warnings telling the user to edit JSON files and restart the server — a hard-block for any non-developer.
- **Context:** This is a posture decision, not a feature. The current setup (UI blocks `api_key_*` writes; user must edit `settings.json`) was chosen to prevent accidental exposure in the UI. Reopening it requires deciding how keys are stored at rest (OS keychain, encrypted file, env-substituted config), how the UI handles them (write-only fields, no echo), and how this interacts with M17's offline-proof posture. Tightly coupled to the parked telemetry posture decision (above) and to M17 Phase 8 (Tauri-layer enforcement).
- **Filed:** 2026-04-25 by claude/youthful-agnesi-8ab627
- **Triage:**
  - What it is: Posture decision + small implementation. Settings page UX problem hides a non-trivial security architecture call.
  - Pillar fit: Cross-cutting (affects M01 onboarding ergonomics, M15 launch credibility, M17 outbound posture).
  - Overlap: M01 (Rolling), M15 (Draft needed), M17 (Phase 8 deferred).
  - Recommendation: **Park** until M17 next-up. Bundle with the parked telemetry posture decision so credentials posture and outbound posture are decided in one ADR.
  - Rough scope: ADR + small UI change → 1–2 days.
- **Decision:** **Parked** 2026-04-25. Revisit when M17 is next-up.

### Blocked URL with query-string data — possible PII leak
- **Source:** Item 18 of the *Web UI new-user walkthrough — P0–P3 punch list* (2026-04-25).
- **Ask:** Reproduce the 404 that Chrome's tracking protection blocked with `[BLOCKED: Cookie/query string data]` during a chat send, identify the offending request, and decide whether it's a real PII-in-URL leak (move to body / scrub) or a false positive.
- **Context:** Captured during a fetch-hook trace of a single "hi" chat send. URL was redacted by the browser before reaching the JS hook so we don't yet know which endpoint. May be a stale endpoint or a legitimate concern — needs reproduction before promoting. If confirmed PII-in-URL: M17 (Network audit) territory.
- **Filed:** 2026-04-25 by claude/youthful-agnesi-8ab627
- **Triage:**
  - What it is: Unverified security signal. Could be nothing, could be a real leak.
  - Pillar fit: Cross-cutting (M17 if confirmed).
  - Overlap: M17 (Landed; Phase 8 deferred), M01 Phase 3 audit item 12 (the same finding will be re-investigated there in network-cleanup work).
  - Recommendation: **Park** until reproduced. M01 Phase 3 will surface it naturally; if confirmed, file a new entry promoting it to M17.
  - Rough scope: investigation patch (hours) → fix patch.
- **Decision:** **Parked** 2026-04-25. Will be re-encountered during M01 Phase 3 perf/network audit; promote to M17 if confirmed PII.

### Home page FCP (~696ms on localhost)
- **Source:** Item 19 of the *Web UI new-user walkthrough — P0–P3 punch list* (2026-04-25).
- **Ask:** Decide whether home-page first-contentful-paint of ~700ms on a local Next dev server warrants optimization.
- **Context:** Measured via Performance API: domContentLoaded 111ms, load 334ms, first-contentful-paint 696ms, transferSize 9KB. Slower than expected for a local SPA but not user-blocking. Likely tied to the canvas + animation init.
- **Filed:** 2026-04-25 by claude/youthful-agnesi-8ab627
- **Triage:**
  - Pillar fit: Cross-cutting (M01 polish if pursued).
  - Recommendation: **Park** — not user-blocking. Revisit if perf becomes a complaint or if production builds (not dev) show similar numbers.
  - Rough scope: investigation half-day, fix patch–day.
- **Decision:** **Parked** 2026-04-25. No action.

---

## Rejected (kept for memory)

<!-- Struck-through items with reasons. -->

*(empty)*
