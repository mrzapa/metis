# 0003 — 2026 Tech Stack Review

- **Status**: Accepted
- **Date**: 2026-03-15

## Context

We were commissioned a "Review of the Proposed Stack with 2026 Insights" report that assessed our original stack (Python + FastAPI, React + Vite + Tailwind + Radix/shadcn, Tauri) against the 2026 tooling landscape. The report made five recommendations. This ADR documents the completion status of each.

## Decision

We audited the codebase against each recommendation. Four of five are complete; one is partially addressed.

## Assessment

### 1. Keep Python + FastAPI; consider Reflex or Litestar — Complete

- FastAPI is the production backend (`axiom_app/api/app.py`) with routers for sessions, settings, logs, RAG queries, and SSE streaming.
- A Reflex proof-of-concept exists at `apps/axiom-reflex/`.
- Litestar/Falcon were not adopted (no performance need identified).

### 2. Adopt a meta-framework instead of bare Vite — Complete

- Next.js 16.1.6 is the primary frontend (`apps/axiom-web/`).
- React 19.2.3 with TypeScript 5.
- Static export (`output: 'export'`) configured for Tauri desktop bundling.

### 3. Leverage ShadCN Registry 2.0 and design tokens — Partial

- shadcn/ui v4.0.6 is adopted with `base-nova` style using `@base-ui/react` (replacing Radix).
- Design tokens exist as CSS variables in `globals.css` using OKLch color space with dark mode.
- **Gap**: Registry 2.0 is not configured (`"registries": {}` in `components.json`). Smart versioning, design-token synchronization, and cross-framework Web Component export are not set up.

### 4. Build for streaming and agentic AI interactions — Complete

- Custom agentic UI components in `components/chat/`:
  - `agentic-step-indicator.tsx` — Retrieval, Synthesis, Validation pipeline visualization.
  - `chat-panel.tsx` — streaming status, agentic mode toggle.
  - `use-chat-transcript.ts` — token buffering with 50ms debounced rendering.
- Backend SSE streaming (`engine/streaming.py`) with structured events and replay support (`services/stream_replay.py`).
- Astro present minimally at `apps/axiom-web-lite/`; Qwik not adopted (both optional).

### 5. Retain Tauri; evaluate Rust native GUI — Complete

- Tauri v2 configured at `apps/axiom-desktop/src-tauri/` (experimental).
- PySide6/Qt remains the production desktop app.
- Rust GUI spike documented at `docs/experiments/rust_gui_spike.md` (iced recommended for future, deferred by design).
- Electron is not used.

## Summary

| # | Recommendation | Status |
|---|---------------|--------|
| 1 | FastAPI + consider Reflex/Litestar | Complete |
| 2 | Meta-framework (Next.js/Remix) | Complete |
| 3 | ShadCN Registry 2.0 + design tokens | Partial |
| 4 | Streaming + agentic UI | Complete |
| 5 | Tauri + evaluate Rust GUI | Complete |

## Open Questions

- Should we prioritize ShadCN Registry 2.0 configuration, or is the current inline CSS variable approach sufficient for our needs?
- Is cross-framework Web Component export needed given that all frontends currently use React?

## Consequences

- The stack is ~90% aligned with the 2026 report recommendations.
- The remaining gap (Registry 2.0) is a configuration/tooling concern, not an architectural one. Design tokens already exist; it is a matter of migrating their management to the registry system.
