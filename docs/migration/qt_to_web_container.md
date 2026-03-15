# Qt-to-Web-Container Migration Strategy

- **Status:** Draft
- **Date:** 2026-03-15
- **Scope:** How Axiom keeps the current Qt app supported while the web UI, local API,
  and desktop container mature.

---

## 1. Current Supported Path

The following workflow is **supported and stable** today:

```
python main.py           # PySide6/Qt MVC desktop app (default)
python main.py --cli     # Headless CLI mode
AXIOM_NEW_APP=0 python main.py  # Legacy Tkinter fallback (agentic_rag_gui.py)
```

Support commitment: `python main.py` and the Qt-backed workflow remain the
production-recommended path until the web-plus-desktop-container stack explicitly
reaches parity on core workflows (see Stage 2 below). No deprecation notice will be
issued before that gate is passed and communicated.

---

## 2. Next-Gen Surfaces (Experimental)

Three additive components landed from WOR-13, WOR-14, and WOR-15. They are
**experimental** — not yet a replacement for the Qt app:

| Component | What it is | Entry point | Status |
|-----------|-----------|-------------|--------|
| **Local API sidecar** | FastAPI server wrapping `axiom_app/services` | `python -m axiom_app.api` | Experimental |
| **Next.js web UI** | Browser-based chat, library, and settings interface | `apps/axiom-web/` | Experimental |
| **Tauri desktop container** | Native window wrapping the web UI; supervises the API sidecar | `apps/axiom-desktop/` | Experimental |

These surfaces reuse the same backend services (`axiom_app/services/`,
`axiom_app/engine/`) as the Qt app. They are additive: running `python -m axiom_app.api`
alongside the Qt app is technically possible but see compatibility risks in Section 4.

---

## 3. Shared Local State

Both stacks read and write the same local persistence assets. There is currently **no
separate database or index store** for the next-gen surfaces.

| Asset | Default location | Owner service | Qt stack | API/web stack |
|-------|-----------------|---------------|----------|---------------|
| **Session database** | `rag_sessions.db` (repo root) | `SessionRepository` (`axiom_app/services/session_repository.py`) | Read/write | Read/write via `/v1/sessions` |
| **Index bundles** | `indexes/` (repo root) | `IndexService` (`axiom_app/services/index_service.py`) | Read/write | Read/write via `/v1/index/*` |
| **Settings file** | `settings.json` (repo root) | `settings_store.py` (`axiom_app/settings_store.py`) | Read/write | Read via `/v1/settings`; write restricted by `AXIOM_ALLOW_API_KEY_WRITE` |
| **Legacy config** | `agentic_rag_config.json` | `settings_store.py` (auto-merge) | Read-only (merged into `settings.json`) | Not accessed directly |

The `Config` dataclass in `axiom_app/config.py` is the authoritative source of
runtime defaults and path resolution for all three assets.

---

## 4. Compatibility Risks and Mitigations

### 4.1 Concurrent SQLite writes

**Risk:** Both the Qt app and the API sidecar use `SessionRepository` to write to
`rag_sessions.db`. Running them simultaneously can cause SQLite lock contention or
write conflicts on session and message rows.

**Mitigation:** Do not run both stacks concurrently against the same database in the
current stage. If concurrent access is required for testing, open `rag_sessions.db` in
WAL mode (`PRAGMA journal_mode=WAL`) — but this is not yet the default and is not
validated for production use.

### 4.2 Index mutations during live queries

**Risk:** If one stack builds or rebuilds an index while the other holds an open query
against the same index directory, the in-progress read may see a partial write.

**Mitigation:** Do not trigger index rebuilds from one stack while the other is
actively querying. A write-lock or rename-swap strategy for index bundles is deferred
until Stage 2.

### 4.3 Settings schema version drift

**Risk:** The Qt app and the API sidecar both load and may write `settings.json`. If
one stack adds a new key that the other does not recognise, the unknown key may be
silently dropped on the next write.

**Mitigation:** `settings_store.py` uses a merge-on-load strategy: it starts from
`default_settings.json` and overlays user overrides. Unknown keys survive a merge
round-trip as long as neither stack writes a fresh defaults-only file. Explicit schema
versioning is deferred but should be introduced before Stage 3.

### 4.4 API key write restriction

**Risk:** The API sidecar by default refuses to update `api_key_*` fields via
`POST /v1/settings`. A user who configures keys through the web UI may find the
operation silently rejected.

**Mitigation:** Set `AXIOM_ALLOW_API_KEY_WRITE=1` before starting the sidecar when
key-write access is needed via the API. Document this in the setup guide; do not
change the default.

### 4.5 Port conflicts

**Risk:** The API sidecar currently binds to a fixed port (`0.0.0.0:8000`). Running
multiple instances or an unrelated process on that port will prevent sidecar startup.

**Mitigation:** Dynamic port selection is deferred to WOR-15 (now landed). Confirm the
sidecar startup logs show the resolved port before connecting the web UI.

---

## 5. Migration Stages

Stages describe decision points and criteria, not a schedule. The current tempo of
the Qt app versus the web-container stack is still an assumption; do not treat these
as dates.

### Stage 0 — Qt only (current state)

- `python main.py` is the sole supported production path.
- The API sidecar and Tauri container exist in `apps/` but are experimental.
- **Entry criterion:** already here.
- **Exit criterion:** API sidecar and web UI cover at least chat (index, query, session
  history). Tauri container runs reliably on all three target platforms without
  requiring a terminal.

### Stage 1 — Qt primary, API/web experimental (in progress)

- `python main.py` remains the supported and recommended path.
- The API sidecar (`python -m axiom_app.api`) and web UI (`apps/axiom-web/`) are
  available for evaluation and feedback but carry no support commitment.
- The Tauri desktop container (`apps/axiom-desktop/`) is available as a preview build.
- Shared state coexists under the rules described in Section 3 and Section 4.
- **Exit criterion:** the next-gen stack passes a defined parity checklist covering
  core workflows (index build, RAG query with streaming, session history, settings
  management, and provider configuration). No production-blocking bugs on any target
  platform.

### Stage 2 — Parity gate

- The API/web/container stack is declared feature-complete for core workflows.
- A formal deprecation notice is issued for the Qt app; a support window is announced.
- Schema versioning for `settings.json` is introduced.
- Write-safe index mutation is implemented.
- **Entry criterion:** Stage 1 exit criterion met and reviewed.
- **Exit criterion:** deprecation window opens; both stacks remain supported in parallel.

### Stage 3 — Qt deprecated, both supported

- Both paths are officially supported for the duration of the announced window.
- No new features are added to the Qt app; bug fixes only.
- Migration guides and tooling (if needed) are published.
- **Exit criterion:** deprecation window closes; no material user base remains on Qt
  path per telemetry or explicit survey.

### Stage 4 — Qt removed

- `agentic_rag_gui.py`, `axiom_app/views/`, `axiom_app/controllers/`, and
  Qt-specific model code are removed from the main branch.
- The `AXIOM_NEW_APP` environment variable and legacy fallback logic in `main.py` are
  removed.
- **Entry criterion:** Stage 3 exit criterion met.

---

## 6. Non-Goals

The following are explicitly out of scope for this document and for WOR-19:

- **No Litestar or API framework swap.** Framework evaluation is tracked separately
  in `docs/experiments/litestar_api.md` and WOR-20.
- **No Reflex shell prototype.** A Python-based web UI is a separate prototype tracked
  in WOR-21.
- **No Rust-native GUI evaluation.** Feasibility spike is tracked in WOR-22.
- **No axiom-web-lite streaming shell.** Streaming shell experiment is tracked in
  WOR-23.
- **No production update infrastructure.** Updater wiring, signing keys, and CDN
  setup are deferred and tracked in `docs/desktop_updates.md`.
- **No forced migration schedule.** This document defines stages and decision
  criteria; the tempo depends on prototype outcomes and user feedback, not a fixed
  date.
- **No change to the Qt app or its Python services.** The Qt MVC workflow is left
  untouched until Stage 2 parity is achieved.
- **No cross-device or network sync.** Axiom remains local-first throughout all stages.

---

## 7. Relationship to ADRs and Related Docs

This document describes the migration strategy and coexistence rules. It does not
re-state architectural decisions that are already captured elsewhere:

| Document | What it covers | Relationship to this doc |
|----------|---------------|--------------------------|
| [`docs/adr/0001-local-api-and-web-ui.md`](../adr/0001-local-api-and-web-ui.md) | Why a local API plus web UI plus desktop container is the chosen direction; alternatives considered | Provides the architectural rationale that this strategy implements |
| [`docs/adr/0002-streaming-protocol.md`](../adr/0002-streaming-protocol.md) | Framework-neutral streaming contract between the API and the web UI | Defines the transport contract that Stage 1 prototypes must satisfy |
| [`docs/desktop_updates.md`](../desktop_updates.md) | Versioning, lockstep release model, and updater placeholder for the Tauri container | Governs how the desktop container is distributed and updated; deferred until Stage 2+ |

---

## 8. Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-03-15 | Qt app remains the supported production path at Stage 0/1 | No demonstrated parity on core workflows yet |
| 2026-03-15 | Shared persistence assets (`indexes/`, `rag_sessions.db`, `settings.json`) are not duplicated per stack | Avoids data divergence; coexistence risks are mitigated by usage discipline (Section 4) |
| 2026-03-15 | Migration stages are gated on criteria, not a schedule | Tempo is still an assumption; premature scheduling adds false certainty |
