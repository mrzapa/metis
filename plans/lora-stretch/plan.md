---
Milestone: LoRA fine-tuning (M18, stretch)
Status: Draft needed
Claim: unclaimed
Last updated: 2026-04-27 by claude/review-codebase-standards-HSWD9 (stub created)
Vision pillar: Companion
---

> **Stretch milestone.** Promoted to a stub only because
> `plans/IMPLEMENTATION.md` row 73 referenced
> `plans/lora-stretch/plan.md` without a directory backing it. Per the
> intake workflow, every promoted milestone gets a stub. Do not start
> work here until **M13 (Seedling + Feed)** and **M16 (Personal evals)**
> have landed — see *Blockers* below.

## Progress

*(milestone not started — this is a stub, not a plan)*

## Next up

Whoever claims this: replace this stub with a real phased plan doc.
The minimum decisions a plan must make, in order:

1. **Training substrate** — local PEFT (e.g. `peft` + `trl`) on the
   Seedling base model vs. exporting LoRA training to a one-shot
   cloud burst with the user's explicit consent (M17 network-audit
   tagged).
2. **Eval gate** — what M16 score delta justifies promoting weights.
   Without M16 producing real per-user signal, this milestone has
   nothing to gate on.
3. **Weight swap mechanic** — hot-swap LoRA adapter on the running
   Seedling process, or restart-with-new-weights. Tauri sidecar
   lifecycle implications (see M13).
4. **Data provenance** — which traces / feedback events feed training,
   how to honour deletion requests, and how this surfaces in the
   network-audit panel.

## Blockers

- **M13 (Seedling + Feed)** must be running a quantized local model
  with a stable inference loop. LoRA on top of an unstable base is
  pointless.
- **M16 (Personal evals)** must produce a measurable per-user score
  delta. Without it, you cannot tell whether a fine-tune made the
  companion better or worse — and the whole milestone is a coin flip.
- **M17 (Network audit)** Phase 7 already landed; if cloud training
  is on the table, M18 must register a provider entry and respect the
  Pro-only outbound posture.

## Notes for the next agent

- Vision pillar: 🌱 Companion. *"Intelligence grown, not bought" —
  the LoRA path is the most concrete expression of this principle.*
- The harvest from the trace + feedback infrastructure already in
  `metis_app/services/trace_feedback.py` and
  `metis_app/services/message_feedback.py` is substantial; ~40-50%
  of the data plumbing for an eval-gated training loop is already in
  place per the M16 stub.
- Out of scope: distillation, RLHF, full pretraining. LoRA only.
