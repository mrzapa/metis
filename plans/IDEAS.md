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

### dot/matrix loaders + DAB pixel/braille editor — quiet UI loaders + tooling

- **Source:**
  - https://icons.icantcode.fyi/ (gallery; backing repo https://github.com/icantcodefyi/dot-matrix-animations, dot/matrix v0.2, 2026)
  - https://obaidnadeem.github.io/dab/ ("DAB — Draw & Animate Braille", browser-based dot/braille animator)
- **Ask:** Explore whether dot/matrix's quiet loaders are worth copying / vendoring into METIS, and whether DAB earns a place as a designer tool — assess the integration story for both.
- **Context:** User pointed at both URLs together. They are sibling artefacts: dot/matrix is a finished gallery of 60 5×5 dot-matrix SVG animations (~4 KB each, single CSS keyframe + per-dot delay map, no JS runtime); DAB is a browser-based dot-grid / Unicode-braille editor that exports frame arrays to JS / JSON / Python / Rust / C, designed for exactly the workflow that produces that style of asset. Brand-relevance is strong: METIS's M-star mark is itself a sparse-dot composition (see [`docs/plans/2026-04-28-metis-logo-rollout-design.md`](../docs/plans/2026-04-28-metis-logo-rollout-design.md) and the topographic ripple reference in M20), so a dot-matrix loader vocabulary is tonally coherent with the brand language M20 just established.
- **Filed:** 2026-05-02 by claude/distracted-wilbur-f2ffc4
- **Triage:**
  - **What it is:**
    - **dot/matrix** is a tightly-scoped gallery of 60 SVG loader animations. Every animation is a 5×5 grid of circles, one CSS keyframe (`@keyframes`) per file, and a per-dot `animation-delay` map; the choreography emerges from delay phasing alone. No noise sampling, no rasterization, no GIF, no JS runtime — drop the SVG inline, it loops forever for ~4 KB. The set is tagged into seven semantic categories: `spinner`, `progress`, `ambient`, `agent`, `status`, plus the unfiltered "all" — the **agent** subset (Thinking, Stream, Handshake, Knight's Tour, Cipher, Listening, Caret) is unusually well-suited to AI/companion surfaces, and the **status** subset (Heartbeat, Beacon, Verify, Halt, Roulette) maps onto state-machine outcomes. The site exposes tint + speed + density + density-mode controls but the underlying SVGs are static — you'd consume them as either inline SVG or as a `<DotMatrixLoader name="thinking" />` React primitive that toggles the keyframe class, with `prefers-reduced-motion` gating in one place.
    - **DAB** is the producer-side companion: an in-browser dot-grid + Unicode-braille editor with frame timeline, onion-skin, dup/del frame, FPS slider, loop/bounce/onion playback, import/export to JS Braille / JS Termdot / JS Grid / JSON / Python / Rust / C. It does not ship code we'd run in production — it's a designer tool. Its value to METIS is indirect: if we end up wanting more dot-matrix loaders than the 60 dot/matrix ships (e.g. a comet trail loader matched to M22, a constellation-twinkle loader for the seedling widget), DAB is the path of least resistance to author them, and it exports JSON frame arrays we can adapt to the same one-keyframe-plus-delay-map shape dot/matrix uses.
  - **Pillar fit:** **Cross-cutting + Companion** (🔧🌱). dot/matrix fits cleanly under principle #2 ("beauty is a feature") — it's a generic UI loader vocabulary, not a vision-pillar feature on its own. The agent/status subsets specifically reinforce the **Companion** pillar (seedling thought states, retrieval/reflection progress) and the brand-coherent dot aesthetic threads back to the M20 mark. DAB does not fit any pillar as a shipped feature; it's a designer tool, not a runtime component.
  - **Overlap:**
    - **M01 (Rolling)** — natural home for a low-risk "consolidate spinners on a `<DotMatrixLoader>` primitive" patch under the *preserve and productise* ethos. There is no audit yet of which spinner/skeleton/loader patterns currently exist across `apps/metis-web` (chat thinking-state, comet activity dock, forge technique-card progress, settings save buttons, evals run progress, etc.), so the first useful step is enumeration, not vendoring.
    - **M13 (Landed)** — owns the Seedling heartbeat widget + edge-pulse follow-up. icon-06 (*Heartbeat*), icon-19 (*Thinking*), icon-20 (*Stream*), and icon-26 (*Listening*) map directly onto seedling thought-loop states. If we adopt the loader vocabulary, the Seedling widget is its highest-impact consumer; coordinate with M13's deferred-items audit.
    - **M14 (Phases 1–6 Landed; Phase 7 stretch)** — Forge technique cards have lifecycle states (idle / proposed / promoted / running) that today rely on chip text. icon-28 (*Compile*), icon-38 (*Verify*), icon-39 (*Halt*), icon-40 (*Roulette*) are tonally on-brand for those state transitions. Soft overlap — not a blocker, but a candidate consumer.
    - **M16 (In progress)** — Personal evals has progress-bar surfaces. icon-13 (*Pyramid*), icon-28 (*Compile*), icon-35 (*Ladder*), icon-44 (*Bar*), icon-50 (*Equalizer*) are progress-shaped. Soft overlap.
    - **M20 (Ready; not yet in PR)** — `<MetisMark>` + `<MetisGlow>` primitives. A `<DotMatrixLoader>` primitive should sit alongside them at `apps/metis-web/components/brand/*` (or a sibling `components/loaders/*`) and reuse the same `currentColor`-themed convention so tinting cascades cleanly. Land **after** M20 is in PR so the brand-primitive convention exists to copy.
    - **M21 (Phase 5 landed; later phases unclaimed)** — the constellation aesthetic pivot just removed several spinning/orbital decorations from the home hero. Loader vocabulary is downstream of that decision; don't reintroduce orbital motion on chrome surfaces M21 just quieted.
    - **M22 (Landed)** — comet headline labels. icon-46 (*Comet* — perimeter sweep with a long soft tail) is tonally adjacent to METIS's own comet motif. Probably not a direct consumer, but worth noting if a future "comet ingestion in flight" indicator surfaces.
    - **No overlap with backend milestones (M03–M11, M17, M18).**
  - **Risks worth noting:**
    - **License confirmation needed.** The site footer says only "[github](https://github.com/icantcodefyi/dot-matrix-animations)" — I have not yet confirmed the LICENSE file (likely MIT for a small loader pack, but worth verifying before vendoring). DAB has no visible license; not blocking because we'd not ship it, but worth recording.
    - **Pre-1.0 upstream.** dot/matrix is at v0.2 (2026). If we vendor SVGs, we own them — no upgrade churn. If we npm-install, we expose ourselves to breaking changes.
    - **Scope creep.** Sixty loaders is too many for METIS surfaces. The right move is a curated 6–10 (one per role: thinking / streaming / listening / progress / verify / halt / heartbeat / comet) — not a full mirror.
    - **Reduced-motion gate.** Every loader needs `prefers-reduced-motion: reduce` honoured (M21's P0 batch fixed reduced-motion regressions; we must not regress that). One wrapper, one gate.
  - **Recommendation:** **Brainstorm before promote.** Specifically:
    1. Run a quick audit of existing loader/spinner/progress patterns across `apps/metis-web` (chat send, forge cards, evals run, comet dock, settings, setup). This is currently unknown; without it, vendoring is premature.
    2. With the audit in hand, run `superpowers:brainstorming` on a curated subset (~6–10 loaders) + the `<DotMatrixLoader>` primitive shape (props: `name`, `tint`, `speed`, `paused`, reduced-motion fallback) + the consume-as-inline-SVG vs. consume-as-React-component decision.
    3. **Most likely outcome:** **Merge** the result into **M01** as a *Quiet loader pass* item (~1–2 day patch), gated on M20 landing in PR so the brand-primitive convention exists. **Less likely:** if the brainstorm surfaces seedling/forge/evals consumers worth coordinating, **Promote** as a small **M23 — Quiet loaders** milestone that lands across M13/M14/M16 surfaces in one coherent pass.
    4. **DAB:** **Reject** as a code/integration target. **Park as a reference** in the same M01 *Quiet loader pass* note — it earns a one-line "if we need bespoke loaders, DAB is the tool" bookmark, nothing more.
  - **Rough scope:**
    - **Audit + brainstorm:** half-day.
    - **Patch path (most likely):** ~1–2 days. License vet + curated SVG vendor (`apps/metis-web/public/loaders/*.svg` or inline modules at `apps/metis-web/components/loaders/*.tsx`) + `<DotMatrixLoader>` primitive + 3–5 surface swaps + reduced-motion check + visual-regression screenshot pass.
    - **Milestone path (less likely):** multi-day (~3–4) if M13/M14/M16 surfaces all opt in.
    - **DAB bookmark:** zero scope (a sentence in M01 notes).
- **Decision:** **Brainstormed 2026-05-02; merged into M01.** Design at [`docs/plans/2026-05-02-quiet-loaders-design.md`](../docs/plans/2026-05-02-quiet-loaders-design.md); implementation plan at [`docs/plans/2026-05-02-quiet-loaders-implementation.md`](../docs/plans/2026-05-02-quiet-loaders-implementation.md). Six-loader vocabulary (`thinking`, `stream`, `compile`, `verify`, `halt`, `breath`) ships as `<DotMatrixLoader>` next to M20's `<MetisLoader>` at `apps/metis-web/components/brand/dot-matrix/*`. Six surface migrations: chat thinking-bubble, chat send-button, Forge technique-card pending, companion-dock reflect-now, companion-dock atlas-save, `app/loading.tsx` cyan-ring outlier. Reduced-motion gate explicitly dropped; `verify`/`halt` ship unconsumed (cheap insurance for future Forge UX). DAB rejected as runtime integration target — reference-only. Upstream permission obtained for the dot-matrix technique.

### Constellation landing page — aesthetic + IA critique (faculty labels, spinning glow, observatory tab scaling, classical-name AI slop)

- **Source:** User critique, 2026-05-01 — direct observation of `/` on `apps/metis-web` and the star observatory dialog opened from it.
- **Ask:** Triage a four-item complaint bundle about the constellation landing page: (a) overall page is unappealing, (b) the faculty labels / "functions" overlay is confusing in practice and should be removed, (c) the central spinning glow reads like a stray lens flare with no clear purpose, (d) opening a star opens a dialog whose tabs overlap each other and break under scaling, (e) some hovered stars surface a classical Bayer/Flamsteed-style name that reads as AI slop.
- **Context:** User's own product critique, not external. They want this assessed against the existing UI work, not implemented blind. Adjacent prior critique is the [M21 *UI critical-eye triage*](ui-critical-triage/plan.md) (in progress; P0 batch landed via PR #588) and the 2026-04-25 *Web UI new-user walkthrough* already merged into M01 — both touched a few of these surfaces but did **not** cover the same complaints exactly:
  - M21 #10 mentions floating chips overlapping content but **not** the observatory dialog's internal tab strip.
  - M21 #11 covers the "Discover everything" decorative heading clipping — a different element from the central glow.
  - M01 audit #7 covers the METIS central-star sprite mis-concentricity, **not** the orbital halo / spin animation that the user is calling lens flare.
  - Neither audit ever questioned the faculty-ring labels or the classical-name tooltip — both are *deliberate* design choices today. Faculty labels (`FACULTY_CONCEPTS` in [`apps/metis-web/app/page.tsx:176`](apps/metis-web/app/page.tsx:176), with strings `"Faculty 01"` … `"Faculty 11"`) are the navigation primitive M02 was built around. Classical names come from [`generateStarName({ tier: "landmark" })`](apps/metis-web/lib/star-catalogue/star-name-generator.ts) and are governed by [ADR 0006](../docs/adr/0006-star-naming-tiers.md) — they are a *contract*, not an oversight.
- **Filed:** 2026-05-01 by claude/frosty-hamilton-fd3889
- **Triage:**
  - **What it is:** A directional critique of the constellation pillar's first-impression UX. Two items are concrete bugs (observatory tab overlap, classical-name tooltip wording); two items are *design pushback* against load-bearing decisions (faculty labels are M02's navigation metaphor; the orbital glow is part of M02 + M20's brand language). The bundle is genuine — the user has complained about lens-flare-y central-star sprites before (M01 audit #7 covered the gold "+" lens flare on a different element) — so this is the same skeptical eye now landing on the home page's central glow + faculty ring. It is **not** an external feature import; nothing here is being copied from a paper or repo.
  - **Pillar fit:** **Cosmos** (🌌). All four sub-items live entirely on the constellation home + observatory surface. Item (a–c) touches the M02 visual system (`apps/metis-web/components/home/home-visual-system.tsx`, `app/page.tsx` faculty-ring code, `lib/landing-stars/*`); item (d) touches `components/constellation/star-observatory-dialog.tsx`; item (e) touches the catalogue tooltip path (`generateStarName` + the `metis-catalogue-tooltip` rendering near `app/page.tsx:5489–5506`).
  - **Overlap:**
    - **M21 (In progress)** — natural home for items (d) and (e). Both are bug-shaped, both fit the "credibility-damaging UI defects" framing of the milestone, and M21's Phase 3 (P2 polish) is unclaimed. Item (d) sits next to existing #10 (companion chip overlay); item (e) is net-new and would slot as a new P2 entry.
    - **M02 (Landed)** — owns the faculty ring + central glow + landing visual system. Item (b) "remove the faculty labels" is a *reversal* of an M02 deliberate choice (faculty-anchored placement is how stars get coordinates; the visible labels are the surfacing of that anchor). Item (c) "spinning glow makes no sense" is partly M02 (orbital halo behind the central star) and partly M20 (`<MetisGlow>` ripple rings). Both need a brainstorm before any code change so the right thing gets removed (or kept and re-explained).
    - **M20 (Ready)** — owns `<MetisGlow>` and brand motion. If the central glow is removed, the brand-language story for the home hero needs a coherent replacement. Coordinate with M20 before touching this if M20 has not yet landed in PR.
    - **ADR 0006 (Star naming tiers)** — item (e) reopens the contract. The current behaviour (landmark tier → classical Bayer/Flamsteed name in tooltip) is the ADR's prescribed surface. Either the ADR needs an addendum or the tooltip wording needs to be rewritten to feel less generated.
  - **Recommendation:** **Merge** items (d) and (e) into [M21](ui-critical-triage/plan.md) as new P2 entries (#23 — observatory dialog tab strip overlap / scaling; #24 — classical-name tooltip reads as AI slop, gate or rewrite). **Brainstorm before promote** for items (a–c) — they require a design conversation (faculty-ring necessity + central-glow purpose) before they become code. Run `superpowers:brainstorming` once the user gives a go-ahead, then either fold the outcome into M21 as a Phase 5 (constellation aesthetics) or promote as a fresh **M23** (constellation IA + visual reset) depending on scope.
  - **Rough scope:**
    - **Item (d) — observatory tab overlap / scaling:** patch (~half-day). The `tab` state at [`star-observatory-dialog.tsx:435`](apps/metis-web/components/constellation/star-observatory-dialog.tsx:435) and the three buttons at lines 1115/1128/1140 likely just need a flex/grid container with `overflow-hidden` and a min-width breakpoint. Worth a screenshot pass at 1024 / 1280 / 1920 widths.
    - **Item (e) — classical name AI slop:** patch (~1–2 hours). Either drop the classical-name footer entirely (smallest fix), reword the convention line, or only show the classical name on user click rather than hover. Touches the `kind: "classical"` branch in `app/page.tsx:5489–5506` and the CSS at `app/page.tsx:7425`. ADR 0006 addendum needed if the contract changes.
    - **Items (a–c) — faculty labels + spinning glow + overall feel:** **brainstorm first**, then either patch (½ day to remove labels + dim halo) or multi-day (true IA reset; could grow into a new milestone).
    - **Aggregate:** 1–2 days for the bug-shaped slice (d + e); items (a–c) cannot be scoped without the brainstorm.
- **Decision:** **Merged into M21 — Phase 5** (2026-05-01). User accepted the design pivot rather than parking (a–c) for a brainstorm; the change set bundles all five complaints into one phase. Faculty title text removed from canvas, central-star rotating ring + diffraction spikes + orbiting motes removed, observatory dialog tab strips converted to horizontal-scroll, and the classical-name hover tooltip silenced. Design reversal recorded in [`docs/adr/0006-constellation-design-2d-primary.md` → *Addendum — 2026-05-01 (M21 Phase 5)*](../docs/adr/0006-constellation-design-2d-primary.md). M21 plan doc updated under *Phase 5*.

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

### ~~chenglou/pretext — fast canvas text measurement & layout~~ → merged into M01 ([`docs/preserve-and-productize-plan.md`](../docs/preserve-and-productize-plan.md) → *2026-05-01 — Notes for the next agent*)

- **Source:** https://github.com/chenglou/pretext (npm `@chenglou/pretext`, MIT, 45.9k★ on a 2-month-old repo, primary lang TypeScript, last push 2026-04-22).
- **Ask:** Add to ideas and triage how/if to implement pretext into METIS.
- **Context:** Pretext is a "pure JS/TS library for multiline text measurement & layout" by Cheng Lou (ex-React core). Avoids `getBoundingClientRect`-induced reflow by measuring via `Intl.Segmenter` + Canvas 2D directly. Ships line-breaking, word-wrap, BiDi/RTL, soft-hyphens. Targets browsers (no SSR yet). Pinned at `0.0.5`.
- **Filed:** 2026-05-01 by claude/gifted-knuth-27aeb0
- **Triage:**
  - What it is: A performance-oriented browser text-layout primitive. Inputs: a string + a Canvas font shorthand. Outputs: line ranges, widths, segment cursors. The library *measures*; the caller renders (DOM, Canvas, SVG, WebGL sprite atlas — wherever). Notable for combining `Intl.Segmenter` grapheme awareness (correct for emoji, CJK, combining marks) with native canvas measurement, and for not touching the layout tree.
  - **Already in the codebase.** Integrated on 2026-03-29 in commit `3c6dd61` (bundled into a feature commit titled "feat: add index deletion functionality"). Today it powers node-cluster label sprites in [apps/metis-web/app/page.tsx:2542-2552](apps/metis-web/app/page.tsx:2542) (and one more call around [line 4234](apps/metis-web/app/page.tsx:4234)) via the wrapper at [apps/metis-web/lib/pretext-labels.ts](apps/metis-web/lib/pretext-labels.ts), which adds a font-keyed measurement cache and a `ctx.measureText` fallback. So the question isn't "should we adopt pretext" — it's "where else does it earn its keep, and is the existing integration healthy".
  - Audit of remaining unwrapped `ctx.measureText` calls: only one — [apps/metis-web/components/brain/brain-graph-3d.tsx:219](apps/metis-web/components/brain/brain-graph-3d.tsx:219), which sizes BrainGraph node-label pills with raw canvas measurement. Migrating it to `measureSingleLineTextWidth` would: (a) inherit the cache (BrainGraph can re-measure the same labels per frame during pan/zoom), (b) get grapheme-cluster correctness for any concept titles containing emoji or CJK, and (c) consolidate the project on one measurement primitive. Comets/landing-starfield don't currently render text via canvas measureText; OG image is Next.js metadata routes (server-side, where pretext has no SSR support yet).
  - Pillar fit: **Cross-cutting + Cosmos** (🔧🌌). Pure infrastructure beneath label rendering on Cosmos surfaces (constellation, BrainGraph). Not a vision-pillar feature on its own.
  - Overlap:
    - **M01 (Rolling)** — natural home: "consolidate canvas text measurement on the pretext wrapper" is exactly the surface-existing-infrastructure ethos.
    - **M10 (Landed)** — owns BrainGraph homological surfaces; the label-pill code in `brain-graph-3d.tsx` lives downstream of M10's data. Migrating its measurement is purely cosmetic to that milestone.
    - **M14 (In progress)** — Forge technique cards are plain DOM React components; no text-measurement need. Not impacted.
    - **M21 / Living Mark (parked above)** — formation animation; doesn't need text layout.
  - Risks worth noting: (1) Library is at `0.0.5` — pre-1.0 means breaking changes are normal; we should keep the wrapper as our only import surface so a future bump or fork can be done in one file. (2) Hard requirement on `Intl.Segmenter` and Canvas 2D — both fine in Tauri's webview and modern browsers, but we should not assume them in any Node-side code path (server-rendered metadata, future tests).
  - Recommendation: **Merge into M01** as a small, scoped item under *Notes for the next agent*: (a) migrate `brain-graph-3d.tsx`'s `ctx.measureText` call to `measureSingleLineTextWidth`, (b) add a one-paragraph "All canvas text measurement goes through `lib/pretext-labels.ts`" note in the M01 cleanup conventions, (c) flag the `0.0.x` pin so a future agent watches for the 0.1.0 / 1.0.0 release. No dedicated milestone.
  - Rough scope: **half-day patch** (single-file migration + a tiny visual-regression check on the BrainGraph label pills + a docs note in M01).
- **Decision:** **Merged into M01 + Promoted as M22** 2026-05-01.
  - **M01 part:** the canvas-text-measurement convention rule + 0.0.x pin warning landed in [`docs/preserve-and-productize-plan.md` → *2026-05-01 — Notes for the next agent*](../docs/preserve-and-productize-plan.md), and the brain-graph-3d subtree is filed under M01 §4.9 as a cleanup-vs-remount decision (the original migration target turned out to be unmounted; reverted before merge).
  - **M22 part:** UI exploration during the intake (preview tour + canvas-text census across all reachable routes) found that pretext is already in the only place in METIS where it currently applies — and the **proper** new home for it is a feature that doesn't exist yet: comet headline labels. Brainstormed 2026-05-01; design approved; promoted to M22 with design doc at [`docs/plans/2026-05-01-comet-headline-labels-design.md`](../docs/plans/2026-05-01-comet-headline-labels-design.md). First consumer of pretext's line-breaking surface in METIS.

### Living Mark — M-star formation from the starfield

- **Source:** Approach 3 from the M20 brainstorming (2026-04-28); parked at the time so M20 could ship the primitives + metadata cleanly without expanding scope.
- **Ask:** On home-page first-load, animate a subset of the existing starfield stars (`app/layout.tsx` radial-gradient layers) into the M-star silhouette over 2–3 seconds, then settle into the static glowing mark. The mark "lives" in the constellation rather than sitting on top of it.
- **Context:** The README header reference image already conveys this aesthetic via the topographic ripple rings; Living Mark is the *temporal* version — the brand emerges from the same particles that paint the rest of the home page. Reuses the existing `<MetisGlow>` primitive for the settle state, so this is purely additive — no rework of M20's primitives.
- **Filed:** 2026-04-29 by claude/cranky-northcutt-42501d
- **Triage:**
  - What it is: A motion-design effort that ties the brand mark to the constellation pillar at the level of the home page's first impression. Stars in the existing `app/layout.tsx` starfield (`radial-gradient` layers + nebula blobs) animate into the mark's silhouette via constrained physics or pre-computed paths, then transition to the static glowing mark via the existing `<MetisGlow>`. Subsequent visits skip the formation if cached. Only fires on `/`; chrome stays static.
  - Pillar fit: **Cosmos** (🌌). Reinforces the *constellation as identity* metaphor that M02 / M12 are built around. Cross-cuts mildly into M01 polish.
  - Overlap: M02 (Landed; owns the home visual system + landing-stars), M01 (Rolling; first-impression UX). Touches `apps/metis-web/components/home/home-visual-system.tsx` and possibly `apps/metis-web/lib/landing-stars/*` for the formation pathing.
  - Recommendation: **Promote** as a new milestone (M21). Substantial creative work (~multi-day) that warrants brainstorm + design + plan, not a patch. Should be claimed *after* M20 lands so the primitives are stable.
  - Rough scope: **multi-day**. Brainstorm + design (half-day) → formation animation prototype (1 day) → integration + reduced-motion fallback (half-day) → tuning (half-day).
- **Decision:** **Promote — gated on M20 PR #574 landing** (2026-04-29). Living Mark touches the same `home-visual-system.tsx` hero that M20 modifies; stacking on the open PR risks merge-conflict pain if PR feedback rewrites that file. After M20 merges to `main`, the next agent runs `superpowers:brainstorming` on this entry, produces an M21 design doc, and adds the row to `IMPLEMENTATION.md`.

### ~~Metis logo rollout — M-star mark + glow primitives~~ → promoted as M20 ([`plans/metis-logo-rollout/plan.md`](metis-logo-rollout/plan.md))
- **Source:** `m_star_logo_traced.svg` provided by the design team on 2026-04-28 (1000×1000 viewBox, single fill-rule:evenodd path, `fill="#111111"`). Reference image: GitHub README header with white mark + cyan halo + topographic ripple rings + lowercase `metis` wordmark on dark navy.
- **Ask:** Implement the supplied logo into the frontend across brand, system metadata, and motion surfaces.
- **Context:** User confirmed scope 3 (brand + metadata + motion) and option A (mark replaces wordmark in chrome; lowercase `metis` lockup reserved for external surfaces only — OG, splash, setup welcome). User specifically called out liking the white version of the mark with the subtle glow per the README header.
- **Filed:** 2026-04-28 by claude/cranky-northcutt-42501d
- **Triage:**
  - What it is: A finished logo asset from the design team, plus a finished GitHub README header that doubles as a style reference. The frontend has no logo glyph today — only typographic wordmarks (`METIS<sup>AI</sup>` in Space Grotesk) in the topbar, landing nav, and a raster `metis-logo.png` in the home hero. No favicon beyond the default Next.js `.ico`, no `app/icon.tsx`, no `apple-icon`, no `opengraph-image`, no Tauri icon suite from a brand source. The work is to wire three composable React primitives (`<MetisMark>`, `<MetisGlow>`, `<MetisLockup>`) backed by a cleaned `currentColor`-themed SVG into all the surfaces that need branding, and to add motion (sonar/topography ripple) on hero + splash without disrupting chrome.
  - Pillar fit: **Cross-cutting + Cosmos** (🔧🌌). Visual identity is foundational — supports M15 (launch credibility), M01 (productise polish), and the Cosmos/constellation metaphor M02/M12 are built around. The glow + ripple aesthetic specifically reinforces the constellation pillar.
  - Overlap:
    - **M01 (Rolling)** — the home-hero swap touches `apps/metis-web/components/home/home-visual-system.tsx`, which is part of M01's audit scope. Coordinate before Phase 2.
    - **M02 (Landed)** — owns the home visual system. M20 is purely additive (replace one PNG with a primitive); no architectural conflict.
    - **M14 (Draft)** — Forge technique-card aesthetic could reuse the glow recipe. Soft coordination.
    - **M15 (Draft needed)** — OG image and Tauri icon suite are load-bearing for launch. M20 unblocks marketing surfaces.
    - **M17 (Landed)** — metadata files render statically at build time, no outbound calls. Google Fonts `@import` is a separate posture issue, out of M20 scope.
  - Recommendation: **Promote** as M20 with a 4-phase plan (asset prep + primitives → in-app surfaces → system metadata → motion polish). Approach 3 ("Living Mark" formed from the starfield) is parked as a follow-up milestone after M20 lands.
  - Rough scope: **multi-day** (4 phases, ~1 phase per day if attacked sequentially; primitives in 1 day, surfaces in 1 day, metadata in half-day, motion polish in 1 day).
- **Decision:** **Promoted as M20** 2026-04-28. Plan doc stub: [`plans/metis-logo-rollout/plan.md`](metis-logo-rollout/plan.md). Full design captured in [`docs/plans/2026-04-28-metis-logo-rollout-design.md`](../docs/plans/2026-04-28-metis-logo-rollout-design.md).

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
  - **Merged into [M01](../docs/preserve-and-productize-plan.md)** — items 1–4, 6–9, 14–17, 19–30, 32–33 captured under *Web UI new-user audit (2026-04-25)* with a 6-phase implementation plan. **Refined + extended later that same day** under *2026-04-25 — UI/UX skill-pass refinements* with 12 new findings (items 35–46) and 4 refinement specs (unified gold FAB, procedural prompt chips, Diagnostics behind shortcut + Pipeline rename, GSAP seedling widget) — see that section in the M01 plan.
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

### Wordmark typography lock-in for the lockup
- **Source:** M20 implementation note; `<MetisLockup>` ships with `Inter Tight Medium` as a placeholder font-family.
- **Ask:** Decide the canonical font for the lowercase `metis` wordmark in `<MetisLockup>` (OG image, `/setup` welcome, Apple touch, Tauri splash). The README header reference image looks like Inter Tight or Geist; design team has not formally specified.
- **Context:** Inter is already loaded via `app/layout.tsx`; Inter Tight is the same Google-Fonts family with tighter tracking. Geist would require a new font load. A custom face is also possible. The choice affects only `<MetisLockup>`'s `font-family` rule — one-line code change once the typeface is decided. Visible on every external surface, so the choice is brand-load-bearing.
- **Filed:** 2026-04-29 by claude/cranky-northcutt-42501d
- **Triage:**
  - What it is: A design decision, not an engineering effort. The implementation cost once a typeface is chosen is trivial (font-family swap + maybe an `@font-face` import).
  - Pillar fit: **Cross-cutting** — visual identity, no behavior change.
  - Overlap: None mechanical. Touches `apps/metis-web/components/brand/metis-lockup.tsx` only.
  - Recommendation: **Park** until the design team weighs in. The current Inter Tight Medium placeholder is not embarrassing and degrades gracefully (Inter is already loaded). Revisit when (a) marketing surfaces ship to the public and brand consistency becomes load-bearing, or (b) design specifies a font.
  - Rough scope: **1-hour patch** once the typeface is decided.
- **Decision:** **Parked** 2026-04-29. Revisit when design specifies a typeface or marketing surfaces ship publicly.

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
