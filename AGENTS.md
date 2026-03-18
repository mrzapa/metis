# Axiom Agent Context

This file is repo-level guidance for Codex. It grounds future tasks in Axiom's current architecture and the PySide6 shell redesign. It does not change runtime APIs, types, or schemas.

## Product Snapshot

- Axiom is a local-first, provider-agnostic RAG app that runs as a desktop GUI or headless CLI.
- The GUI and CLI share the same retrieval and indexing core.
- Key user-facing modes: Q&A, Summary, Tutor, Research, Evidence Pack.

## Canonical Entry Points

- `main.py`: canonical launcher. Defaults to the PySide6 MVC app, switches to CLI with `--cli`, and can opt into the legacy Tk app with `AXIOM_NEW_APP=0`.
- `axiom_app/app.py`: MVC bootstrap. Initialises logging, loads settings, constructs model/view/controller, applies theme, and starts the Qt poll loop.
- `axiom_app/controllers/app_controller.py`: top-level orchestration for indexing, querying, sessions, skills, settings saves, and background task dispatch.

## Capability Map

- `axiom_app/services/*`: indexing, vector stores, response pipelines, runtime resolution, sessions, profiles, skills, traces, and model registry or recommendation services.
- `axiom_app/utils/*`: provider factories, embeddings, document loading, background helpers, logging, knowledge-graph helpers, and dependency bootstrap.
- `axiom_app/models/app_model.py`: settings merge behaviour plus repo-root persistence defaults.

## Persistence and Local State

- Settings defaults live in `axiom_app/default_settings.json`.
- User overrides live in repo-root `settings.json`.
- Repo-root persistence artefacts resolved by the model defaults: `rag_sessions.db`, `indexes/`, `profiles/`, `skills/`, `traces/`.
- Some directories are created on demand; treat them as canonical local state.

## Development Commands

```powershell
python -m pip install --upgrade pip
pip install -e .[dev]
python main.py
python main.py --cli --help
python -m axiom_app.cli --help
python -m pytest -q
$env:QT_QPA_PLATFORM="offscreen"; python -m pytest -q tests/test_app_view_smoke.py
ruff check .
```

- Use `python main.py --cli <command> ...` for headless `index`, `query`, or `skills` flows.

## Style Conventions

- Treat `ruff check .` and `python -m pytest -q` as the default quality gates.
- Prefer small, composable functions with clear names.
- Avoid unrelated refactors in the same change.

## How to Extend Safely

- Add new settings keys in `axiom_app/default_settings.json` first.
- Keep UI concerns in views and controllers; keep service logic in `axiom_app/services/*`.
- Preserve `populate_settings()` and `collect_settings()` as the persistence boundary for settings-facing UI work.
- Separate visual-shell refactors from unrelated behaviour changes.

## UI Overhaul Guardrails

This section is repo-level guidance for Codex during the PySide6 shell redesign.

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
- Do not rewrite backend behaviour as part of UI iteration.
- Do not rewrite controller, service, or model behaviour as part of UI iteration.
- Preserve `populate_settings()` and `collect_settings()` as the persistence boundary for settings-facing UI work.
- Prefer small, reviewable commits.
- Separate visual-shell refactors from unrelated behaviour changes.

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
