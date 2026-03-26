# 0004 - One Interface: Next.js + Tauri + FastAPI

- **Status:** Accepted
- **Date:** 2026-03-17

## Decision

METIS has one product interface only:

- **UI Layer:** Next.js app (shipped in Tauri shell)
- **Desktop Shell:** Tauri (wraps Next.js + FastAPI)
- **Backend:** FastAPI (local sidecar)
- **CLI:** Developer/power-user workflows only

The Qt GUI is deprecated and removed from the product surface. Browser-only mode is dev-only, not a product mode.

## Because

- Fastest iteration: Next.js + Tauri enables rapid UI iteration with hot reload
- Best streaming UX: Next.js handles SSE streaming with minimal latency
- Best design system: shcn/ui registry provides consistent, maintainable components
- Best local-first path: Tauri provides native desktop integration without Electron overhead
- Least product confusion: One clear interface eliminates "which one do I use?" friction

## What Changes Now

- Documentation rewritten around one interface (web-first default)
- Installers launch Tauri shell by default; Qt available via `--desktop` / `--gui` override
- Old GUI paths removed from user-facing flows
- Repo language simplified: "desktop" means Tauri, not Qt

## Constraints

- Must maintain CLI for automation and CI/CD workflows
- Must support offline/local-only operation
- Must preserve data portability (local SQLite, local file system)

## Alternatives Considered

- **Qt GUI:** Rejected. Adds maintenance burden, limits design system options, diverges from web UX.
- **Electron:** Rejected. Larger bundle size, higher resource usage than Tauri.
- **Browser-only:** Rejected. Not a product—users expect a desktop app with native integration.

## Consequences

- Single code path for UI (Next.js)
- Single installer for desktop distribution
- Simpler onboarding ("download METIS, it just works")
- Reduced maintenance: one frontend stack, one backend stack

## Open Questions

None. This decision is final for the 1.0 release cycle.
