---
Milestone: Mobile companion (M19, stretch)
Status: Draft needed
Claim: unclaimed
Last updated: 2026-04-27 by claude/review-codebase-standards-HSWD9 (stub created)
Vision pillar: Cosmos
---

> **Stretch milestone.** Promoted to a stub only because
> `plans/IMPLEMENTATION.md` row 74 referenced
> `plans/mobile-stretch/plan.md` without a directory backing it. Per
> the intake workflow, every promoted milestone gets a stub. Do not
> start work here until **M15 (Pro tier + public launch)** has
> landed — see *Blockers* below.

## Progress

*(milestone not started — this is a stub, not a plan)*

## Next up

Whoever claims this: replace this stub with a real phased plan doc.
The minimum decisions a plan must make, in order:

1. **Surface choice** — Tauri Mobile (single codebase with desktop)
   vs. PWA (zero install friction, weaker OS integration) vs.
   native shell over the existing web app. Write an ADR.
2. **Sync model** — read-only constellation snapshot pulled from the
   user's desktop instance, or a separate cloud read replica. The
   former preserves the local-first posture; the latter implies a
   server-side store and forces a reckoning with M17.
3. **Auth + pairing** — how a phone discovers and authenticates to
   the user's desktop instance. Tailscale / WireGuard / scan-a-QR /
   Pro-tier relay. Coordinate with M15 (Pro paywall gate).
4. **Feature surface** — explicitly read-only for v1. No editing
   archetypes, no triggering RAG queries. Constellation viewer,
   star inspector, growth-log feed. That's it.

## Blockers

- **M15 (Pro tier + public launch)** — mobile is a Pro-tier feature
  per `VISION.md`. Building it before the paywall has no business
  surface to attach to.
- **Cosmos UI churn** — `apps/metis-web/app/page.tsx` is currently
  the hottest hotspot in the repo (99.8th %ile churn). Any mobile
  surface that shares rendering code with desktop will inherit that
  instability. Consider waiting for the page.tsx decomposition
  (audit P2 #8) to settle before forking.

## Notes for the next agent

- Vision pillar: 🌌 Cosmos. *"The constellation as primary
  navigation"* extends naturally to mobile, but only if it doesn't
  drag the local-first posture off course.
- Out of scope for v1: write paths, file uploads, local model
  inference on-device, push notifications. Read-only or nothing.
- Tauri Mobile is the obvious first choice because the desktop
  shell is already Tauri (`apps/metis-desktop/src-tauri/`); a PWA
  is the obvious second choice if Tauri Mobile's iOS story is still
  rough at the time of work.
