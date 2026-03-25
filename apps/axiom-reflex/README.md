# axiom-reflex — Proof-of-concept Reflex UI

Minimal [Reflex](https://reflex.dev) prototype that wires up to the existing
`axiom_app` core: lists sessions from the repo-root SQLite database and
executes direct LLM queries through the current engine — **no changes** to
the API server or existing entrypoints required.

## Prerequisites

- Python 3.10+
- The `axiom_app` package available (either installed via the repo root or
  simply on `PYTHONPATH` — `rxconfig.py` adds the repo root automatically).
- A supported LLM API key (`ANTHROPIC_API_KEY` or `OPENAI_API_KEY`).

## Quick start

```bash
# 1. From the repo root, install the axiom_app core (skip if already installed)
pip install -e .

# 2. Enter the prototype directory
cd apps/axiom-reflex

# 3. Install Reflex
pip install -r requirements.txt

# 4. Set your LLM credentials (defaults to Anthropic claude-haiku)
export ANTHROPIC_API_KEY=sk-ant-...

# Optional: choose a different provider / model
# export AXIOM_LLM_PROVIDER=openai
# export AXIOM_LLM_MODEL=gpt-4o-mini
# export OPENAI_API_KEY=sk-...

# 5. Start the app
reflex run
```

Open <http://localhost:3000> in your browser.

## Features

| Feature | Details |
|---------|---------|
| Session listing | Reads `rag_sessions.db` from the repo root via `SessionRepository` |
| Direct query | Sends the prompt to the configured LLM via `query_direct` |
| Isolation | No modifications to existing entrypoints; runs entirely under `apps/` |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `AXIOM_LLM_PROVIDER` | `anthropic` | LLM provider (`anthropic`, `openai`, …) |
| `AXIOM_LLM_MODEL` | `claude-haiku-4-5-20251001` | Model name |
| `ANTHROPIC_API_KEY` | _(none)_ | Anthropic API key |
| `OPENAI_API_KEY` | _(none)_ | OpenAI API key |

## What this is NOT

This is a **prototype only**.  It does not replace:
- `python main.py` (canonical entrypoint — starts FastAPI + opens web UI)
- `python -m axiom_app.api` (FastAPI backend for axiom-web)

RAG queries, session creation/deletion, auth, and production routing are
out of scope for this proof-of-concept (see later WOR tickets).
