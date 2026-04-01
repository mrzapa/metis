# Interface Confusion Inventory

> **Note:** This document tracks cleanup work in progress based on [ADR 0004](../adr/0004-one-interface-tauri-next-fastapi.md) migration. Items listed here are being addressed to clarify the one-interface product direction (Tauri + Next.js).

**Summary:**
- Files affected: 15
- Items to rewrite: 8
- Items to delete: 4
- Items to quarantine as deprecated: 6
- Items to keep (dev-only): 2

---

## Inventory

| File | Line/Section | Confusing Text/Codepath | Why Confusing | Action |
|------|--------------|-------------------------|---------------|--------|
| `README.md` | Line 26 | "Desktop-native. A real Qt6 app..." | Says Qt is the desktop app, contradicts one-interface decision | **REWRITE** |
| `README.md` | Line 57 | "`metis` opens web UI. Use `--desktop`/`--gui` for Qt" | Explicitly documents Qt as override, should be reverse | **REWRITE** |
| `README.md` | Lines 123-127 | Interface table with "Desktop GUI" as separate entry | Table should show web as default, Qt as deprecated | **REWRITE** |
| `README.md` | Lines 150-160 | "Web UI (default)" vs "Desktop app" sections | Two sections imply equal status | **REWRITE** |
| `README.md` | Line 124 | "`bash scripts/run_nextgen_dev.sh` - next-gen web UI" | "next-gen" implies experimental, should say "web UI" | **REWRITE** |
| `README.md` | Lines 341-344 | "Web UI and local API now shipping alongside desktop app" | Implies two products, should say "now default" | **REWRITE** |
| `README.md` | Lines 334 | "agentic_rag_gui.py - Legacy Tkinter (kept for compatibility)" | Legacy Tkinter referenced | **DELETE** |
| `docs/migration/qt_to_web_container.md` | Entire doc | Full migration doc from Qt to web | Should be deleted or rewritten as "deprecated path" | **DELETE** |
| `docs/migration/qt_to_web_container.md` | Lines 138-144 | "Qt app alone" supported, "Qt + API" not supported | Qt should not be "supported" per one-interface | **DELETE** |
| `docs/migration/qt_to_web_container.md` | Lines 153-193 | Stage 0-4 migration plan with Qt as Stage 0 | Stages are obsolete now | **DELETE** |
| `docs/adr/0001-local-api-and-web-ui.md` | Full doc | Explains adding API + web while keeping Qt | Should be marked superseded | **MOVE TO DEPRECATED** |
| `docs/adr/0002-streaming-protocol.md` | Line 8,32 | References "Qt MVC-backed runtime" | Outdated | **REWRITE** |
| `docs/adr/0003-2026-tech-stack-review.md` | Line 48 | "PySide6/Qt remains the production desktop app" | Contradicts one-interface | **REWRITE** |
| `docs/desktop_updates.md` | Lines 30-34 | References to schema migration, session versioning | Should be simplified | **KEEP (DEV-ONLY)** |
| `docs/experiments/rust_gui_spike.md` | Full doc | Explains Tauri as experimental alongside Qt | Should be marked deprecated | **MOVE TO DEPRECATED** |
| `docs/experiments/litestar_api.md` | Full doc | Migration eval from FastAPI to Litestar | Not relevant to one-interface | **MOVE TO DEPRECATED** |
| `apps/README.md` | Line 3 | "Qt desktop app live at repo root" | Outdated | **REWRITE** |
| `apps/README.md` | Line 38 | "Qt desktop app (`python main.py`) is unaffected" | Should say "legacy" | **REWRITE** |
| `apps/metis-desktop/README.md` | Lines 5,16 | "Independent of Qt desktop app" | Should remove Qt reference | **REWRITE** |
| `apps/metis-reflex/README.md` | Full doc | Alternative to Tauri, references Qt | Should be deprecated | **MOVE TO DEPRECATED** |
| `apps/metis-reflex/README.md` | Line 61 | "`python main.py` (Qt desktop app)" | Should be removed | **DELETE** |
| `apps/metis-web/README.md` | Lines 35,80,89 | References to "web UI" | Keep but simplify | **KEEP (DEV-ONLY)** |
| `metis_app/engine/README.md` | Lines 5,19,261 | "Qt", "PySide6" references | Should say "any non-Qt frontend" | **REWRITE** |
| `metis_app/api/README.md` | Line 6 | "Does not import Qt" | Should say positive, not negative | **REWRITE** |
| `AGENTS.md` | Line 7 | "runs as a desktop GUI or headless CLI" | Says GUI, should say "web UI" | **REWRITE** |
| `AGENTS.md` | Line 13-14 | "PySide6 MVC app", "METIS_NEW_APP=0" | METIS_NEW_APP is dead code | **REWRITE** |
| `AGENTS.md` | Lines 35-36,43 | "python main.py" references | Should say "metis --cli" | **REWRITE** |
| `.agents/skills/launch-app/SKILL.md` | Lines 24,30,37 | "python main.py" references | Should update | **REWRITE** |
| `scripts/install_metis.sh` | Line 69 | "--web" flag handling | Legacy, documented as no-op | **KEEP (DEV-ONLY)** |
| `scripts/install_metis.ps1` | Lines 64,122 | "--web" comments | Legacy, documented as no-op | **KEEP (DEV-ONLY)** |

---

## Priority Actions

### P0 - Rewrite (Most Confusing)

1. **README.md** - Top priority. The main user-facing doc says Qt is the desktop app. Rewrite to lead with Tauri + Next.js as the product.

2. **docs/migration/qt_to_web_container.md** - Delete entirely. Migration story is over - we have one interface now.

3. **AGENTS.md** - Remove references to `METIS_NEW_APP` and "Qt". Update to web-first.

### P1 - Deprecate/Quarantine

4. **docs/adr/0001-local-api-and-web-ui.md** - Mark superseded by 0004
5. **docs/experiments/rust_gui_spike.md** - Move to deprecated experiments folder
6. **docs/experiments/litestar_api.md** - Move to deprecated experiments folder
7. **apps/metis-reflex/README.md** - Move to deprecated

### P2 - Minor Fixes

8. **apps/README.md** - Update Qt references
9. **apps/metis-desktop/README.md** - Remove Qt comparison
10. **metis_app/engine/README.md** - Update Qt references

---

## What to Do First

1. Delete `docs/migration/` folder - migration is over
2. Rewrite README.md to lead with Tauri + Next.js
3. Update AGENTS.md to remove Qt/METIS_NEW_APP references
4. Mark 0001 and 0003 ADRs as superseded
5. Move experiment docs to `docs/experiments/deprecated/`

The goal: a new user should never see "Qt" or "PySide6" in any user-facing doc.
