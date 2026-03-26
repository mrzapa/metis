# METIS Agents

METIS is a local-first AI workspace that runs entirely on your machine.  The
primary interface is the **Tauri + Next.js web application** (`apps/metis-web/`)
backed by a **FastAPI** service (`metis_app/api/`).

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
main.py                  Entry point — starts FastAPI + opens browser
metis_app/
  api/                   FastAPI routes (v1/*)
  engine/                Indexing + retrieval core (provider-agnostic)
  models/                BrainGraph, AppModel, session types
  services/              Session repository, index service, pipeline
  utils/                 Knowledge graph, LLM/embedding providers

apps/metis-web/          Tauri + Next.js frontend
  app/
    chat/                Chat interface (RAG Q&A)
    library/             Document & index library
    brain/               Interactive brain graph visualisation
    settings/            Provider and model configuration
  components/
    brain/               BrainGraph SVG component
    chat/                Chat + evidence panels
  lib/api.ts             API client (typed fetch wrappers)
```

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

All routes are documented at `http://localhost:8000/docs` when the server is
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

---

## Security

When `METIS_API_TOKEN` is set, all protected endpoints require a Bearer token.
In the default local-only mode no token is required.
