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
- **Decision:** awaiting user confirmation of **Park**.

---

## Agent observations

<!-- Agents append here when they notice something the user should see. -->

*(empty)*

---

## Iced

<!-- Parked ideas — not rejected, not active. -->

*(empty)*

---

## Rejected (kept for memory)

<!-- Struck-through items with reasons. -->

*(empty)*
