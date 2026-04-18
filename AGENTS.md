# METIS Agents

METIS is a local-first AI workspace that runs entirely on your machine.  The
primary interface is the **Tauri + Next.js web application** (`apps/metis-web/`)
backed by a **Litestar** ASGI service (`metis_app/api_litestar/`).

---

## Before you implement anything new

If the user asks you to implement something that came from **outside this
repo** — a GitHub link, a paper, a concept, a technique, a screenshot —
**do not start coding.** Run the intake workflow documented in
[`plans/README.md`](plans/README.md#intake-workflow-for-implementation-requests-from-external-sources):

1. File the request to [`plans/IDEAS.md`](plans/IDEAS.md).
2. Triage inline (pillar fit, overlap, recommendation, scope).
3. Wait for go/no-go from the user.
4. Only then promote to a milestone / plan doc, or merge into an existing
   one, and implement.

Skip this only for bug fixes, trivial tweaks, or when the user explicitly
says "just do it". See [`VISION.md`](VISION.md) for the product pillars the
triage step checks against.

---

## Quick start

```bash
# Start the API server and open the web UI in your browser
python main.py

# Headless CLI
python main.py --cli index --file my_docs/
python main.py --cli query --file my_docs/ --question "What are the key findings?"
```

---

## Architecture overview

```
main.py                  Entry point — starts Litestar + opens browser
metis_app/
  api_litestar/          Litestar routes (v1/*)
  engine/                Indexing + retrieval core (provider-agnostic)
  models/                BrainGraph, AppModel, session types
  services/              Session repository, index service, pipeline
  utils/                 Knowledge graph, LLM/embedding providers

apps/metis-web/          Tauri + Next.js frontend
  app/
    chat/                Chat interface (RAG Q&A)
    brain/               Interactive brain graph visualisation
    settings/            Provider and model configuration
  components/
    brain/               BrainGraph SVG component
    chat/                Chat + evidence panels
  lib/api.ts             API client (typed fetch wrappers)
```

---

## Development

```bash
# Install (dev mode)
pip install -e ".[dev,api]"

# Test — always run from repo root
python -m pytest
python -m pytest --cov=metis_app --cov-report=term

# Lint
ruff check .

# Full dev check (lint + tests + settings validation)
./scripts/dev_check.sh          # macOS / Linux
.\scripts\dev_check.ps1         # Windows PowerShell
```

> **Pitfall**: run tests from the repo root, not a subdirectory. A different checkout may be on `PYTHONPATH` and silently shadow the local package.

See [CONTRIBUTING.md](CONTRIBUTING.md) for PR workflow and environment setup.

---

## Conventions

### Backend

- **Request/Result dataclasses** — engine operations pair `*Request` → `*Result` types (see `metis_app/engine/querying.py`)
- **Adapter ABC** — new vector store backends implement `VectorStoreAdapter` (`metis_app/services/vector_store.py`); never call vector stores directly
- **Settings secrets** — use `"env:VAR_NAME"` syntax in `settings.json`; the store resolves values from the environment at runtime. Never hardcode API keys.
- **Schema migration** — increment `schema_version` for breaking settings changes and register a handler in `_MIGRATIONS` (`metis_app/settings_store.py`)
- **`lru_cache` isolation** — always call `cache.cache_clear()` in `autouse` fixtures; tests share process state and cached values leak between runs

### Testing

- **Fresh client per test** — create `TestClient(create_app())` inside each test function, not at module level
- **Prefer `monkeypatch`** — use `monkeypatch.setattr` over `unittest.mock` for factory injection (`create_llm`, `create_embedder`)
- **Litestar tests** — wrap in a context manager: `with TestClient(app=create_app()) as client:`
- **Pipeline path** — test new retrieval stages through `execute_retrieval_plan`; do not call the vector store adapters directly in tests

### Frontend (`apps/metis-web`)

- **Typed fetch wrappers** — all backend calls go through `lib/api.ts`; no raw `fetch()` inside components
- **App Router** — pages live at `app/(route)/page.tsx` following Next.js App Router conventions
- **Tauri API base** — resolved dynamically via `invoke('get_api_base_url')`, not a hardcoded constant; dev mode falls back to `NEXT_PUBLIC_METIS_API_BASE`

---

## Architecture decisions

Key decisions live in `docs/adr/`. The canonical decision is **[ADR 0004](docs/adr/0004-one-interface-tauri-next-fastapi.md)**: single product interface — Next.js UI in Tauri shell, Litestar backend. Qt GUI is deprecated and removed from the product surface; CLI is retained for automation.

---

## Agentic capabilities

### RAG modes

| Mode | Description |
|------|-------------|
| **Q&A** | Direct, cited answers from indexed documents |
| **Summary** | Condensed overview of long files |
| **Tutor** | Socratic back-and-forth |
| **Research** | Deep dives with sub-query expansion and knowledge-graph traversal |
| **Evidence Pack** | Claim-level grounding with source citations |

### Recursive agent (Research mode)

When `agentic_mode` is enabled, METIS iterates over its own output to refine
answers.  The loop:

1. Initial retrieval + synthesis
2. Self-critique: identify gaps and generate sub-queries
3. Retrieve additional context for each sub-query
4. Synthesise a refined answer incorporating new evidence
5. Repeat up to `agentic_max_iterations` times (default 2)

Configure via `settings.json`:

```json
{
  "agentic_mode": true,
  "agentic_max_iterations": 3
}
```

---

## Skills

Skills are self-contained agentic workflows in `skills/`.  Each skill
directory contains a `SKILL.md` describing the workflow, safety checks,
and when to ask for user confirmation.

To invoke a skill from the API, include `skill_ids` in the session settings.

---

## Brain graph

The brain graph (`GET /v1/brain/graph`) returns a JSON representation of all
indexes, sessions, skill categories, and their relationships.  The frontend
renders it as an interactive SVG at `/brain`.

---

## API reference

All routes are documented at `http://localhost:8000/schema` when the server is
running.

Key endpoints:

| Route | Method | Description |
|-------|--------|-------------|
| `/v1/brain/graph` | GET | Brain graph (nodes + edges) |
| `/v1/index/list` | GET | List available indexes |
| `/v1/index/build` | POST | Build a new index |
| `/v1/index/build/stream` | POST | Build with SSE progress stream |
| `/v1/query/rag` | POST | RAG query (batch) |
| `/v1/query/rag/stream` | POST | RAG query (SSE stream, resumable) |
| `/v1/sessions` | GET | List chat sessions |
| `/v1/sessions/{id}` | GET | Session detail |
| `/v1/settings` | GET/POST | Read / update settings |
| `/v1/gguf/*` | GET/POST | Local GGUF model management |
| `/v1/heretic/preflight` | GET | Check heretic tool availability |
| `/v1/heretic/abliterate/stream` | POST | Run abliteration pipeline (SSE stream) |

---

## Security

When `METIS_API_TOKEN` is set, all protected endpoints require a Bearer token.
In the default local-only mode no token is required.
