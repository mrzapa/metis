# Rust-Native GUI Feasibility Spike

> **⚠️ DEPRECATED — HISTORICAL DOCUMENT ONLY**
> 
> This document is a historical experiment. It is not part of the current product direction.
> 
> **Axiom's product direction is Tauri + Next.js + FastAPI.**
> 
> Qt/PySide6 is no longer part of the product surface.

- **Status:** Draft
- **Date:** 2026-03-15
- **Scope:** Evaluate whether a Rust-native GUI toolkit (egui or iced) is a viable
  replacement for the Tauri/WebView desktop container introduced in WOR-13–WOR-16.
  Docs-only and decision-oriented; no Rust code lands in this ticket.

---

## 1. Motivation

The current experimental desktop path (WOR-13) wraps the Next.js web UI inside a
Tauri v2 WebView. This delivers fast iteration on the web UI but carries permanent
costs:

| Cost | Detail |
|------|--------|
| **Process weight** | Chromium/WebKit renderer; idle RSS ≈ 200–300 MB on macOS |
| **Bundle size** | Tauri installer ≈ 10–15 MB (framework only); the bundled Python sidecar adds 50+ MB |
| **Native feel gap** | WebView compositing artifacts, font rendering differences, missing native controls |
| **Accessibility** | Screen-reader integration depends on browser a11y APIs, not OS-native trees |

A Rust-native GUI would own the render path entirely, eliminating the WebView. The
open question is whether the toolkit ecosystem is mature enough, and which
Python-integration architecture best fits Axiom's constraints. **This memo does not
require a prototype to exist; its conclusions are assumption-driven and should be
revisited once a prototype is built.**

**Relationship to prior work:** This was a feasibility study from the migration era.
Axiom now ships as Tauri + Next.js + FastAPI (see ADR 0004).

---

## 2. Frameworks Under Consideration

### 2.1 egui

egui is an **immediate-mode** GUI library: every frame, the application re-describes
its entire UI tree from scratch; the library diffs and renders it. There is no
retained widget state managed by the framework.

**Strengths**
- Single-crate; minimal dependency tree; compiles quickly (~30 s cold on a modern
  laptop for a small app)
- First-class WASM/browser target — the same codebase can run in a web worker
- Very low boilerplate for simple tools and dashboards
- Active maintenance (emilk/egui; used in production by Rerun, among others)
- `eframe` provides a ready-made cross-platform app harness (winit + wgpu or glow)

**Weaknesses**
- Immediate-mode is ergonomically awkward for complex state machines; Axiom's
  multi-step RAG workflow maps more naturally to retained, event-driven UI
- Widget set is functional but sparse: no native date-picker, no virtualized list
  with scroll anchoring, no rich-text editor widget out of the box
- **Accessibility gap (critical):** egui has no native OS accessibility tree. There
  is a community effort (`accesskit` integration) but as of early 2026 it is
  incomplete. This is a hard blocker if WCAG or screen-reader support is a
  requirement. *Assumption — verify before committing.*
- Custom theming requires overriding low-level paint calls; it is doable but not
  designer-friendly

### 2.2 iced

iced is a **retained-mode** GUI library using an Elm-inspired architecture
(Message/Command/Subscription). The application describes a persistent widget tree;
the framework diffs it on each update.

**Strengths**
- Retained model fits Axiom's stateful sessions (active research run, library view,
  settings) more naturally than immediate-mode
- Richer built-in widget set: scrollables, lazy lists, text inputs with selection,
  canvas, SVG
- `iced_accessibility` integration is in progress (built on `accesskit`); more
  active investment than egui's a11y track *— still assumption-driven; verify*
- Async-first: `Command` and `Subscription` are built around futures/streams, which
  maps directly onto the SSE streaming protocol used by `axiom_app.api`
- Active development; 1.0 milestone in progress as of 2025

**Weaknesses**
- Cold compile time is significantly higher than egui (~3–5 min for a medium app
  with wgpu backend; incremental is fast)
- The Elm architecture introduces boilerplate: every interaction requires a message
  variant, an update arm, and potentially a command
- Fewer production deployments than egui; ecosystem of third-party widgets is
  thinner
- Styling/theming API has been revised across major versions; internal churn is
  possible before 1.0 stabilises

### 2.3 Side-by-Side Comparison

| Dimension | egui | iced |
|-----------|------|------|
| **Architecture** | Immediate-mode | Retained-mode (Elm) |
| **State management fit** | Awkward for deep session state | Natural for Axiom's session model |
| **Widget richness** | Minimal; sufficient for dashboards | Richer; scrollable lists, lazy views |
| **Accessibility** | Incomplete (accesskit in progress) | In-progress; more active investment |
| **Async / streaming** | Manual; no built-in concept | First-class via Command/Subscription |
| **Cold compile time** | Fast (~30 s) | Slow (~3–5 min, wgpu backend) |
| **WASM target** | Yes (first-class) | Partial (no wgpu on WASM yet) |
| **Ecosystem maturity** | Stable; ~5 years old | Younger; approaching 1.0 |
| **Theming** | Low-level paint override | Theme trait; structured but in flux |
| **Recommendation fit** | Prototyping, tooling, dashboards | Feature-complete desktop app |

**Provisional lean:** iced's retained model and async primitives are a better
architectural fit for Axiom. egui remains relevant if a fast throw-away prototype
is needed before committing to iced's compile overhead.
*Both conclusions are provisional until a working prototype validates them.*

---

## 3. Python Integration Approaches

The Axiom backend is Python (FastAPI + `axiom_app/services/`). Any Rust GUI must
either call into it or speak to it over a local channel.

### 3.1 Sidecar (HTTP / local socket)

The Rust GUI launches `python -m axiom_app.api` as a child process (identical to
the Tauri sidecar in WOR-14) and communicates over HTTP/SSE.

```
┌─────────────────────────────┐
│  Rust GUI binary             │
│  (egui or iced)              │
│                              │
│  reqwest / surf client  ──── │─── HTTP + SSE ───► python -m axiom_app.api
└─────────────────────────────┘                         (child process)
```

**Trade-offs**

| Aspect | Detail |
|--------|--------|
| **Python engine risk** | Zero: the Python process is identical to today's sidecar |
| **IPC overhead** | ~1 ms round-trip on localhost; negligible for Axiom's use case |
| **Process footprint** | Two processes; combined idle RSS ≈ Rust binary (< 30 MB) + Python sidecar (60–100 MB) |
| **Bundle** | Rust binary + PyInstaller-packaged Python sidecar (same as Tauri path) |
| **Implementation complexity** | Low: `reqwest` for REST, `eventsource-client` or manual SSE parsing for streaming |
| **Failure isolation** | GUI can restart the sidecar independently; Python crashes don't take the GUI down |
| **Upgrade path** | Python engine evolves independently of Rust GUI; no ABI coupling |

This is the **lower-risk path** and directly reuses the existing `axiom_app.api`
surface that was built for WOR-14.

### 3.2 Embedding (PyO3)

The Rust binary links against `libpython` via `pyo3` and calls Python engine
functions directly in-process.

```
┌──────────────────────────────────────────────┐
│  Rust GUI binary                              │
│                                              │
│  pyo3::Python::with_gil(|py| {               │
│      engine.call_method(py, "run", ...)       │
│  })                                          │
│                                              │
│  ╔══════════════════════════════╗            │
│  ║  Embedded CPython interpreter║            │
│  ║  axiom_app.engine / services ║            │
│  ╚══════════════════════════════╝            │
└──────────────────────────────────────────────┘
```

**Trade-offs**

| Aspect | Detail |
|--------|--------|
| **Python engine risk** | High: Rust build is coupled to CPython ABI; `pyo3` version pins Python minor version |
| **Async bridging** | Complex: `pyo3-asyncio` (or `pyo3-async-runtimes`) bridges Tokio ↔ asyncio; edge cases around the GIL and async cancellation are well-documented pain points |
| **IPC overhead** | Eliminated; direct in-process calls |
| **Bundle** | Smaller than sidecar: no separate process, but Python stdlib must still be bundled (~25–40 MB) |
| **Implementation complexity** | High: GIL management, Python object lifetime, async bridging, packaging |
| **Python engine changes** | Any internal refactor of `axiom_app` must consider Rust FFI call sites |
| **CI complexity** | Rust CI matrix must install matching Python dev headers |

This path is **not recommended at this stage.** The implementation complexity and
coupling risks outweigh the IPC savings, especially given that the sidecar path
already works.

### 3.3 Trade-off Summary

| | Sidecar | PyO3 Embedding |
|--|---------|----------------|
| **Risk to Python engine** | None | High |
| **Async complexity** | Low | High |
| **IPC latency** | ~1 ms | 0 |
| **Implementation effort** | Low | High |
| **Bundle size delta** | +0 (identical to Tauri) | −20–40 MB |
| **Recommended?** | **Yes** | No (revisit if sidecar IPC becomes a bottleneck) |

---

## 4. Success Criteria

A Rust-native GUI prototype should be evaluated against these thresholds before a
go/no-go decision is made. All numbers are targets, not measurements; they must be
validated empirically.

| Metric | Target | Rationale |
|--------|--------|-----------|
| **Installer size** | ≤ 80 MB | Current Tauri + sidecar baseline; no regression |
| **Idle RSS (GUI process only)** | ≤ 30 MB | Rust binary with wgpu; excludes Python sidecar |
| **Idle RSS (combined)** | ≤ 150 MB | GUI + Python sidecar; better than Tauri + WebView ≈ 250 MB |
| **Idle CPU** | ≤ 1% (60 s average) | No background render loop when window is idle |
| **Cold startup to interactive** | ≤ 3 s | From launch to first frame with session list visible |
| **Accessibility** | Screen-reader announces main nav items | Smoke test with VoiceOver (macOS) or NVDA (Windows) |
| **Dev velocity** | New screen in < 1 day | For a Rust-familiar developer using the chosen toolkit |
| **Core workflow parity** | RAG chat + library list functional | Minimum to declare prototype complete |

### Accessibility note

Neither egui nor iced has production-grade accessibility as of early 2026.
`accesskit` provides the underlying OS bridge for both, but integration completeness
varies. **If accessibility is a hard requirement, this is a potential blocker for
both frameworks.** A prototype must test `accesskit` integration early, not late.

---

## 5. Open Questions / Unknowns

These are explicitly assumption-driven. Each should be answered by a prototype
before a go/no-go decision.

1. **accesskit completeness** — Can a screen reader navigate the main session list
   and chat input in iced (or egui) today? Unknown without a real build.

2. **Compile time in CI** — iced with wgpu may push CI times past acceptable
   thresholds. Caching strategies (sccache, Rust target caching) must be evaluated.

3. **wgpu on Linux/Wayland** — wgpu targets Vulkan, Metal, and DX12. Wayland +
   Mesa coverage is good in principle; edge cases on older GPU drivers are unknown.

4. **SSE streaming in iced's Subscription model** — Mapping a long-lived HTTP SSE
   stream to an iced `Subscription` is theoretically clean but has not been
   prototyped. Backpressure and cancellation semantics need verification.

5. **Python sidecar startup race** — The Rust GUI must wait for the Python sidecar
   to be ready before issuing API requests. The current Tauri implementation uses
   a port-poll loop (WOR-15). This logic must be reproduced in the Rust GUI.

6. **Font rendering quality** — wgpu-based renderers use custom text pipelines
   (cosmic-text for iced). CJK and right-to-left rendering quality is unknown.

7. **Bundle size with PyInstaller** — The PyInstaller-packaged sidecar already
   exists (WOR-14). Whether it can be reused verbatim with a Rust GUI or needs
   adaptation for code-signing is unknown.

---

## 6. Recommendation

**Do not replace the Tauri container yet.** The Tauri/WebView path is experimental
but functional. A Rust-native GUI spike makes sense as a parallel investigation,
not an immediate migration.

**If a spike is approved:**

1. **Choose iced over egui** for the prototype, given Axiom's stateful session
   model and need for SSE streaming. Revisit if iced's compile times prove
   unacceptable in CI.

2. **Use the sidecar integration pattern** (HTTP/SSE to `axiom_app.api`). Do not
   attempt PyO3 embedding in the spike.

3. **Treat accessibility as a first-order concern**, not a post-hoc add-on. Wire
   `accesskit` from the start; if screen-reader support cannot be demonstrated by
   end of spike, record it as a hard blocker.

4. **Spike scope:** render the session list, open a session, send a RAG query, and
   stream the response. That is the minimum viable surface to validate the
   architecture and hit the success criteria above.

**This recommendation is provisional.** It is based on framework documentation,
community reports, and the existing Axiom architecture — not on a running prototype.
All conclusions should be treated as hypotheses until the spike is built and the
success criteria above are measured empirically.

---

*See also:*
- [`docs/desktop_updates.md`](../desktop_updates.md) — desktop versioning and updater placeholders
- [`docs/experiments/litestar_api.md`](litestar_api.md) — companion experiment doc (API layer)
