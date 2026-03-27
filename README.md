<h1 align="center">METIS AI</h1>

<p align="center">
  <strong>The private, provider-agnostic AI workspace that runs entirely on your machine.</strong><br />
  Index your documents. Ask questions. Get grounded answers.<br />
  No API keys required. Bring a local model and go fully offline.
</p>

<p align="center">
  <a href="https://github.com/mrzapa/metis/actions/workflows/ci.yml"><img src="https://github.com/mrzapa/metis/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="Alpha" />
</p>

<br />

**METIS AI** is a **local-first frontier AI workspace** built with Tauri + Next.js + FastAPI. It runs entirely on your machine. Your files never leave your device.

- **Fully local.** Run with a local GGUF model and you don't even need an internet connection.
- **Swap anything.** LLM, embeddings, vector store. Change providers in a config file. Today it's OpenAI, tomorrow it's a model on your laptop.
- **Desktop-native.** Built with Tauri for a native window experience with no Electron bloat.
- **Five ways to think.** Q&A, Summary, Tutor, Research, and Evidence Pack modes give you different lenses on the same documents.
- **METIS Companion.** An always-on AI companion that learns from your sessions, reflects on conversations, and grows with your workspace.
- **Brain Graph.** An interactive 3D visualisation of your workspace including indexes, sessions, companion memory, and their relationships.

<br />

<p align="center">
  <a href="#-quick-start">Quick Start</a> · <a href="#-features">Features</a> · <a href="#-cli">CLI</a> · <a href="#-configuration">Configuration</a> · <a href="#-contributing">Contributing</a>
</p>

---

## ⚡ Quick Start

### Install

**macOS / Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/mrzapa/metis/main/scripts/install_metis.sh | bash
```

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/mrzapa/metis/main/scripts/install_metis.ps1 | iex
```

The installer clones the repo, sets up a virtual environment, installs dependencies, and drops a launcher on your PATH. It auto-updates on every run.

### Run

**Installed launcher (recommended):**

```bash
metis
```

This starts the local API plus static web UI and opens `http://127.0.0.1:3000`.

**From source (no launcher):**

```bash
python main.py
```

This starts the FastAPI app directly at `http://127.0.0.1:8000`.

| Interface | Command |
|-----------|---------|
| **Web UI (installed launcher)** | `metis` |
| **Web UI (from source)** | `python main.py` |
| **Desktop GUI** | `metis --desktop` or `metis --gui` |
| **CLI** | `metis --cli <command>` |

### Use

1. **Add documents**: bring files into the Home constellation flow or use the CLI
2. **Ask questions**: select a mode (Q&A, Summary, Tutor, Research, Evidence Pack) and chat
3. **Explore the Brain**: navigate the 3D graph to see how your workspace connects
4. **Persist sessions**: conversations auto-save to SQLite

---

## ✨ Features

### Zero lock-in: swap every layer

Most RAG apps hardcode their stack. METIS AI treats every layer as a plug-in. Switch providers in `settings.json` and restart. That's it.

| Layer | Options | Go fully offline? |
|-------|---------|:-----------------:|
| **LLM** | OpenAI · Anthropic · Google · xAI · Cohere · LM Studio · **local GGUF** | Yes, with GGUF |
| **Embeddings** | Voyage · Sentence Transformers · **local GGUF** | Yes, with GGUF or ST |
| **Vector store** | In-memory JSON · ChromaDB · Weaviate | Yes, all run locally |

### Five ways to read a document

| Mode | What it's for |
|------|--------------|
| **Q&A** | Direct, cited answers from your documents |
| **Summary** | Condensed overviews of long or complex files |
| **Tutor** | Socratic-style back-and-forth to help you learn |
| **Research** | Deep dives with sub-query expansion and reranking |
| **Evidence Pack** | Structured claim-level grounding with source citations |

### METIS Companion

An always-on AI companion that lives in the workspace shell. It bootstraps an identity, reflects on active sessions, stores learned memories and playbooks, and surfaces contextual hints as you work. The companion is always available from the floating dock at the bottom of every page.

### Brain Graph

An interactive 3D force-directed graph visualising your entire workspace (indexes, sessions, the METIS Self, and learned companion memory) as glowing neural nodes connected by animated edges. Rotate, zoom, and click any node to inspect it.

| Scope | What it shows |
|-------|--------------|
| **Workspace** | Indexes, sessions, and structural categories |
| **METIS Self** | The companion's identity and self-structure |
| **Assistant-Learned** | Memories, playbooks, and learned links |

### Everything else

- **Knowledge graphs**: automatic entity extraction and relationship linking
- **Persistent sessions**: SQLite-backed conversations that auto-save
- **Agent profiles**: save different configurations for different projects
- **Structure-aware ingestion**: parses PDFs, DOCX, Markdown, HTML, and plain text
- **Background processing**: indexing and queries run in threads; the UI never freezes
- **Theming**: Space Dust, Light, and Dark themes

---

## 💻 CLI

The CLI shares the same retrieval backend as the app: same results, no window.

```bash
# Index a file
metis --cli index --file docs/my_notes.txt

# Query it
metis --cli query --file docs/my_notes.txt --question "What are the key takeaways?"
```

You can also run the same CLI entrypoint from source:

```bash
python main.py --cli index --file docs/my_notes.txt
python main.py --cli query --file docs/my_notes.txt --question "What are the key takeaways?"
```

---

## 🛠️ Local Development

### API only

```bash
python -m metis_app.api
```

Runs the API at `http://127.0.0.1:8000`. Full API reference is available at `http://127.0.0.1:8000/docs` while the server is running.

### API + Next.js dev UI

**macOS / Linux:**

```bash
bash scripts/run_nextgen_dev.sh
```

**Windows (PowerShell):**

```powershell
.\scripts\run_nextgen_dev.ps1
```

This starts:

- API at `http://127.0.0.1:8000`
- Next.js dev UI at `http://127.0.0.1:3000`

---

## 🔧 Configuration

METIS AI ships with sensible defaults in `metis_app/default_settings.json`. To customise, copy it to `settings.json` in the project root. METIS picks it up automatically on the next launch.

### Environment variables

| Variable | What it does |
|----------|-------------|
| `NEXT_PUBLIC_METIS_API_BASE` | Overrides the API base URL used by the web UI during local Next.js development |
| `METIS_API_TOKEN` | When set, all protected endpoints require a Bearer token |
| `METIS_TEST_WEAVIATE_URL` | Weaviate endpoint for live parity tests |
| `METIS_TEST_WEAVIATE_API_KEY` | Weaviate API key |
| `METIS_TEST_WEAVIATE_GRPC_HOST` | Weaviate gRPC host |
| `METIS_TEST_WEAVIATE_GRPC_PORT` | Weaviate gRPC port |
| `METIS_TEST_WEAVIATE_GRPC_SECURE` | Enable TLS for gRPC |

---

## 🧪 Testing

```bash
# Run the test suite
python -m pytest

# With coverage
python -m pytest --cov=metis_app --cov-report=term
```

---

## 📁 Project Layout

```
metis_app/
├── api/            # FastAPI routes (v1/*)
├── engine/         # Indexing + retrieval core (provider-agnostic)
├── models/         # BrainGraph, AppModel, session types
├── services/       # Session repository, index service, pipeline
└── utils/          # Knowledge graph, LLM/embedding providers

apps/
├── metis-web/      # Tauri + Next.js UI (TypeScript + Tailwind)
│   ├── app/
│   │   ├── chat/       # Chat interface (RAG Q&A)
│   │   ├── brain/      # Interactive Brain Graph visualisation
│   │   ├── setup/      # First-run onboarding wizard
│   │   └── settings/   # Provider and model configuration
│   └── components/
│       ├── brain/       # BrainGraph 3D component
│       ├── chat/        # Chat + evidence panels
│       └── shell/       # METIS Companion dock, page chrome
└── metis-desktop/  # Tauri desktop shell

scripts/            # Installers and dev scripts
skills/             # Self-contained agentic skill workflows
tests/              # pytest suite
docker/             # Weaviate for integration testing
```

---

## 🤝 Contributing

```bash
pip install -e ".[dev]"
ruff check .
python -m pytest
```

For full-stack local development:

```bash
bash scripts/run_nextgen_dev.sh
```

Make sure linting and tests pass before opening a PR. See [CONTRIBUTING.md](CONTRIBUTING.md) for full guidelines.

---

## License

[MIT](LICENSE)
