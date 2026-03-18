<p align="center">
  <img src="logo.png" alt="Axiom" width="160" />
</p>

<h1 align="center">Axiom</h1>

<p align="center">
  <strong>The private, provider-agnostic RAG app that runs entirely on your machine.</strong><br />
  Index your documents. Ask questions. Get grounded answers.<br />
  No API keys required — bring a local model and go fully offline.
</p>

<p align="center">
  <a href="https://github.com/mrzapa/axiom/actions/workflows/ci.yml"><img src="https://github.com/mrzapa/axiom/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="Alpha" />
</p>

<br />

Axiom is a **local-first desktop AI workspace** built with Tauri + Next.js + FastAPI. It runs entirely on your machine — your files never leave your device.

- **Fully local.** Run with a local GGUF model and you don't even need an internet connection.
- **Swap anything.** LLM, embeddings, vector store — change providers in a config file. Today it's OpenAI, tomorrow it's a model on your laptop.
- **Desktop-native.** Built with Tauri for a native window experience — no Electron bloat.
- **Five ways to think.** Q&A, Summary, Tutor, Research, and Evidence Pack modes give you different lenses on the same documents.

<br />

<p align="center">
  <a href="#-quick-start">Quick Start</a> · <a href="#-features">Features</a> · <a href="#-cli">CLI</a> · <a href="#-configuration">Configuration</a> · <a href="#-contributing">Contributing</a>
</p>

---

## ⚡ Quick Start

### Install

**macOS / Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/mrzapa/axiom/main/scripts/install_axiom.sh | bash
```

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/mrzapa/axiom/main/scripts/install_axiom.ps1 | iex
```

The installer clones the repo, sets up a virtual environment, installs dependencies, and drops an `axiom` launcher on your PATH. It auto-updates on every run.

### Run

```bash
axiom
```

Axiom opens the local web UI at `http://127.0.0.1:3000` by default.

| Interface | Command |
|-----------|---------|
| **Web UI** | `axiom` |
| **Desktop GUI** | `axiom --desktop` or `axiom --gui` |
| **CLI** | `axiom --cli <command>` |

### Use

1. **Add documents** — drag files into the library or use the CLI
2. **Ask questions** — select a mode (Q&A, Summary, Tutor, Research, Evidence Pack) and chat
3. **Persist sessions** — conversations auto-save to SQLite

---

## ✨ Features

### Zero lock-in — swap every layer

Most RAG apps hardcode their stack. Axiom treats every layer as a plug-in. Switch providers in `settings.json` and restart — that's it.

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

### Everything else

- **Knowledge graphs** — automatic entity extraction and relationship linking
- **Persistent sessions** — SQLite-backed conversations
- **Agent profiles** — save different configurations for different projects
- **Structure-aware ingestion** — parses PDFs, DOCX, Markdown, HTML, plain text
- **Background processing** — indexing and queries run in threads, UI never freezes
- **Theming** — Space Dust, Light, and Dark themes

---

## 💻 CLI

The CLI shares the same retrieval backend as the app — same results, no window.

```bash
# Index a file
axiom --cli index --file docs/my_notes.txt

# Query it
axiom --cli query --file docs/my_notes.txt --question "What are the key takeaways?"
```

---

## 🔧 Configuration

Axiom ships with sensible defaults in `axiom_app/default_settings.json`. To customize, copy it to `settings.json` in the project root — Axiom picks it up automatically.

### Environment variables

| Variable | What it does |
|----------|-------------|
| `AXIOM_TEST_WEAVIATE_URL` | Weaviate endpoint for live parity tests |
| `AXIOM_TEST_WEAVIATE_API_KEY` | Weaviate API key |
| `AXIOM_TEST_WEAVIATE_GRPC_HOST` | Weaviate gRPC host |
| `AXIOM_TEST_WEAVIATE_GRPC_PORT` | Weaviate gRPC port |
| `AXIOM_TEST_WEAVIATE_GRPC_SECURE` | Enable TLS for gRPC |

---

## 🧪 Testing

```bash
# Run the test suite
python -m pytest

# With coverage
python -m pytest --cov=axiom_app --cov-report=term
```

---

## 📁 Project Layout

```
axiom_app/
├── models/          # Application state
├── services/       # Indexing, retrieval, sessions, pipelines
├── utils/          # LLM/embedding factories, document loaders
└── assets/         # Bundled resources

apps/
├── axiom-web/      # Next.js UI (TypeScript + Tailwind)
│   ├── app/
│   │   ├── chat/   # Chat interface
│   │   ├── library/ # Document library
│   │   └── settings/ # Provider and model config
│   └── components/  # Shared UI components
└── axiom-desktop/ # Tauri desktop shell

scripts/             # Installers and dev scripts
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

Make sure linting and tests pass before opening a PR.

---

## License

[MIT](LICENSE)
