# 0003 — 2026 Tech Stack Review

> ⚠️ **SUPERSEDED BY ADR 0004**  
> This historical tech review is from 2026. [ADR 0004](./0004-one-interface-tauri-next-fastapi.md) contains the current technology decision.

- **Status**: Superseded
- **Date**: 2026-03-15
- **Superseded by**: 0004-one-interface-tauri-next-fastapi.md

## Context

We were commissioned a "Review of the Proposed Stack with 2026 Insights" report that assessed our original stack (Python + FastAPI, React + Vite + Tailwind + Radix/shadcn, Tauri) against the 2026 tooling landscape. The report made five recommendations. This ADR documents the completion status of each.

## Decision

We audited the codebase against each recommendation. All five are now complete.

## Assessment

### 1. Keep Python + FastAPI; consider Reflex or Litestar — Complete

- FastAPI is the production backend (`metis_app/api/app.py`) with routers for sessions, settings, logs, RAG queries, and SSE streaming.
- A Reflex proof-of-concept exists at `apps/metis-reflex/`.
- Litestar/Falcon were not adopted (no performance need identified).

### 2. Adopt a meta-framework instead of bare Vite — Complete

- Next.js 16.1.6 is the primary frontend (`apps/metis-web/`).
- React 19.2.3 with TypeScript 5.
- Static export (`output: 'export'`) configured for Tauri desktop bundling.

### 3. Leverage ShadCN Registry 2.0 and design tokens — Complete

- shadcn/ui v4.0.6 is adopted with `base-nova` style using `@base-ui/react` (replacing Radix).
- Design tokens extracted to a dedicated `app/tokens.css` (CSS variables, OKLch color space, light + dark) and `app/tokens.json` (W3C DTCG format for tooling and cross-project synchronization).
- Registry 2.0 configured in `components.json` with upstream shadcn registry URL. Smart versioning enabled via `npm run ui:diff` (`npx shadcn diff`).
- Local component manifest at `registry.json` catalogs all 11 UI components with their dependencies and base shadcn version.
- Cross-framework Web Component export deferred by design: metis-web (React) is the only production frontend; metis-web-lite (Astro) consumes React natively; metis-reflex (Python) generates its own UI. The shared `tokens.css`/`tokens.json` files provide the real cross-project shared layer.

### 4. Build for streaming and agentic AI interactions — Complete

- Custom agentic UI components in `components/chat/`:
  - `agentic-step-indicator.tsx` — Retrieval, Synthesis, Validation pipeline visualization.
  - `chat-panel.tsx` — streaming status, agentic mode toggle.
  - `use-chat-transcript.ts` — token buffering with 50ms debounced rendering.
- Backend SSE streaming (`engine/streaming.py`) with structured events and replay support (`services/stream_replay.py`).
- Astro present minimally at `apps/metis-web-lite/`; Qwik not adopted (both optional).

### 5. Retain Tauri — Complete

- Tauri v2 is the canonical desktop shell (`apps/metis-desktop/`).
- Electron is not used.
- PySide6/Qt is no longer part of the product surface (historical only).

## Summary

| # | Recommendation | Status |
|---|---------------|--------|
| 1 | FastAPI + consider Reflex/Litestar | Complete |
| 2 | Meta-framework (Next.js/Remix) | Complete |
| 3 | ShadCN Registry 2.0 + design tokens | Complete |
| 4 | Streaming + agentic UI | Complete |
| 5 | Tauri desktop shell | Complete |

## Consequences

- The stack is fully aligned with all five 2026 report recommendations.
- Design tokens are now managed in a dedicated file (`tokens.css`) with a machine-readable DTCG representation (`tokens.json`) for tooling integration.
- Upstream component drift is detectable via `npm run ui:diff`.
