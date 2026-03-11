# UI Overhaul Guardrails

This file is repo-level guidance for Codex during the PySide6 shell redesign. It does not change runtime APIs, types, or schemas.

## Run These Checks

Run these before handing off UI-overhaul changes:

```powershell
ruff check .
python -m pytest -q
$env:QT_QPA_PLATFORM="offscreen"; python -m pytest -q tests/test_app_view_smoke.py
```

## UI Overhaul Working Agreements

- Keep the app in PySide6 MVC.
- Rule: do not rewrite backend.
- Do not rewrite backend behavior as part of UI iteration.
- Do not rewrite controller, service, or model behavior as part of UI iteration.
- Preserve `populate_settings()` and `collect_settings()` as the persistence boundary for settings-facing UI work.
- Prefer small, reviewable commits.
- Separate visual-shell refactors from unrelated behavior changes.

## Axiom Q1 2026 GUI Redesign Plan Principles

This section is a distilled summary of the current shell redesign intent in the repo.

- Clean by default: keep drawers and panels closed unless the current task needs them.
- Prompt-first chat shell: preserve the empty-state-first workflow and avoid cluttering the primary compose area.
- Keep context visible in lightweight summary or chip form before expanding into heavier controls.
- Treat library, session, and inspector surfaces as contextual tools, not always-on chrome.
- Keep everyday surfaces calm; developer-only controls belong outside the main workspace.
- Improve shell clarity and reliability without changing backend semantics.

## Styling Boundaries

- Shared tokens, palettes, fonts, spacing, and reusable theme values live in `axiom_app/views/styles.py`.
- Per-widget or one-off appearance rules belong in local widget or component QSS.
- Do not duplicate shared tokens as ad hoc literals when they should be promoted to `styles.py`.
