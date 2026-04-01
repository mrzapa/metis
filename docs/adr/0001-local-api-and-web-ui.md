# 0001: Local API and Web UI

> ⚠️ **SUPERSEDED BY ADR 0004**  
> This ADR describes an earlier architecture that included Qt. See [ADR 0004](./0004-one-interface-tauri-next-fastapi.md) for the current architecture (Tauri + Next.js + FastAPI).

- `Status`: Superseded by ADR 0004
- `Date`: 2026-03-13

## Context

METIS currently runs as a local-first PySide6/Qt MVC desktop app with a shared CLI and shared backend services. The repo roadmap already points to a possible next step: add a local API layer, put a meta-framework web UI on top of it, and package both inside a desktop container.

This draft treats that direction as additive. The target is to complement the current PySide6 UI and CLI during migration, not to assume an immediate replacement.

## Proposed Direction

Introduce a local API layer that reuses the existing backend capabilities in `metis_app/services`, then build a meta-framework web UI against that API and distribute the combined experience inside a desktop container.

The near-term goal is to create a migration seam between the current PySide6 MVC shell and a future web-based shell without changing METIS's local-first product shape.

## Constraints

- Local-first
- Offline-capable
- Provider-agnostic
- Minimal vendor lock-in

## Alternatives Considered

- Keep Qt-only: lowest migration risk, but it limits UI iteration and web-style reuse.
- Pure web without desktop container: simpler deployment model, but weaker desktop integration and offline distribution story.
- Python-only UI via Reflex: keeps more of the stack in Python, but increases framework lock-in and may limit fit for the target UI direction.
- Performance-first API variant using Litestar: attractive for throughput, but premature before the API shape and migration seam are settled.

## Consequences

- The migration will need a clear boundary between reusable services and shell-specific UI concerns.
- Packaging choice remains important because the desktop container must preserve offline-capable local behavior.
- The PySide6 UI may need to coexist with the new shell for a meaningful transition period.

## Open Questions

- What migration sequence keeps the PySide6 app stable while the local API and web UI are introduced?
- Which desktop container best fits local distribution and offline updates?
- How long should the current PySide6 UI coexist with the new shell?
