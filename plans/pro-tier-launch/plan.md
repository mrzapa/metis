---
Milestone: Pro tier + public launch (M15)
Status: Draft
Claim: unclaimed
Last updated: 2026-04-21 by claude/m17-phase7-export-discoverability (coordination link)
Vision pillar: Cross-cutting
---

> **Coordinates with M17 (Network audit).** The audit panel stays
> Free; Pro-only outbound features must register their own provider
> entries and `trigger_feature` tags; marketing-site analytics is
> out of M17 scope. Full contract:
> [`plans/network-audit/plan.md` → Coordination hooks (Phase 7)](../network-audit/plan.md#coordination-hooks-phase-7).

## Progress

*(milestone not started — this is a harvest stub, not a plan)*

## Next up

Whoever claims this: read the harvest under *Notes for the next agent*,
make the three real decisions (payments posture, marketing-site
analytics vendor, newsletter mechanic), write ADRs for each, then
replace this stub with a real phased plan doc.

## Blockers

- **M13 (Seedling + Feed)** must be far enough along that a growth-log
  newsletter has real content. Do not draft launch copy before then.
- **M16 (Personal evals)** must be producing measurable per-user
  improvement signal, or "what METIS learned this week" becomes
  fabricated.

## Notes for the next agent

Harvest from the founders-kit review pass (2026-04-18). Reject at
vision level; merged here. Source: `plans/IDEAS.md` → struck-through
*founders-kit — strategic review pass* entry.

- **Positioning**: METIS is alternative-to Jan / LM Studio /
  Open WebUI / AnythingLLM. List on **AlternativeTo** and **SaaSHub**
  early — free channels, vision-aligned.
- **Launch venues (open)**: HN, r/LocalLLaMA, Product Hunt, Betalist,
  Indie Hackers, r/SideProject, r/IMadeThis, r/MachineLearning,
  Designer News, AwesomeIndie, SideProjectors.
- **Launch venues (gated)**: **Lobsters** and **DataTau** both demand
  a technical artifact to justify the post — a writeup of the trace
  system, IterRAG convergence, or the homology scaffold. Do not launch
  there without one; you'll burn the channel.
- **Analytics (marketing site)**: Plausible / Pirsch / Simple
  Analytics / Fathom / self-hosted Umami. Google Analytics is tonally
  wrong given *nothing phones home*. Pick one; write an ADR.
- **Analytics (product telemetry)**: **separate question** — filed
  as its own IDEAS entry (*Local-first product analytics for
  onboarding measurement*). Do not conflate with marketing-site
  analytics. Decision belongs there, not here.
- **Payments**: Stripe alone does not handle global VAT for an indie
  seller. Compare **Merchant of Record** options — Dodo Payments,
  Paddle, Lemon Squeezy — against direct Stripe + self-managed tax.
  Write an ADR. METIS has zero payments code / decisions so far; this
  is a clean-slate call.
- **Newsletter / distribution mechanic**: Buttondown or Substack. A
  *what METIS learned this week* format ties directly to *Intelligence
  grown, not bought* and doubles as distribution. Only real once M13
  and M16 are landed — see *Blockers* above.
- **Landing page tooling**: Framer / Carrd / Webflow. Prefer a
  static-site deploy so the marketing site can mirror the product's
  local-first posture if ever self-hosted.
- **Design pattern references for polish**: Mobbin / Page Flows /
  UX Archive / Pttrns / SaaSPages. Reference only — applies to
  M02 / M12 / M14 as much as M15.
- **Out of scope / explicit non-moves**: cloud credits (METIS is
  local-first), enterprise startup programs, co-founder matching,
  VC fundraising infrastructure, hiring playbooks. Founders-kit
  covers these heavily; none apply per `VISION.md` *What we are
  explicitly not doing*.
