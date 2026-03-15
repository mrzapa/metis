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

Most RAG tools are either locked to one provider, trapped behind a SaaS login, or require you to glue together a dozen libraries yourself. Axiom is different:

- **Fully local.** Your files never leave your machine. Run with a local GGUF model and you don't even need an internet connection.
- **Swap anything.** LLM, embeddings, vector store — change providers in a config file, not in code. Today it's OpenAI, tomorrow it's a model running on your laptop. Axiom doesn't care.
- **Desktop-native.** A real Qt6 app with themes, sessions, and keyboard shortcuts.
- **Web UI included.** A Next.js browser interface ships alongside the desktop app — same backend, different window.
- **Five ways to think.** Q&A, Summary, Tutor, Research, and Evidence Pack modes give you different lenses on the same documents. Most tools only do Q&A.
- **GUI and CLI share one brain.** Same retrieval engine powers both interfaces. Script it, automate it, or just click around.

<br />

<p align="center">
  <a href="#-quick-start">Quick Start</a> · <a href="#-features">Features</a> · <a href="#-usage">Usage</a> · <a href="#web-ui">Web UI</a> · <a href="#-configuration">Configuration</a> · <a href="#-contributing">Contributing</a>
</p>

---

## ⚡ Quick Start

### One-liner install

**macOS / Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/mrzapa/axiom/main/scripts/install_axiom.sh | bash
```

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/mrzapa/axiom/main/scripts/install_axiom.ps1 | iex
```

That's it. The installer clones the repo, sets up a virtual environment, installs dependencies, and drops an `axiom` launcher on your PATH. It even auto-pulls the latest code every time you run it.

### Installer flags

```bash
./scripts/install_axiom.sh --reinstall   # Nuke the venv and start fresh
./scripts/install_axiom.sh --uninstall   # Remove Axiom completely
./scripts/install_axiom.sh --update      # Pull latest + update deps
```

> You can override the install location, repo URL, branch, and Python binary with `AXIOM_INSTALL_DIR`, `AXIOM_REPO`, `AXIOM_BRANCH`, and `AXIOM_PYTHON`.

<details>
<summary><strong>Manual setup (for the hands-on types)</strong></summary>

<br />

```bash
# 1. Clone and enter the repo
git clone https://github.com/mrzapa/axiom.git && cd axiom

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install --upgrade pip

# 3. Pick your install flavour
pip install -e ".[runtime-all]"            # Full GUI + all ML deps
pip install -e ".[dev]"                    # Dev tools only
pip install -e ".[dev,runtime-all]"        # Everything
pip install -e ".[dev,live-backends]"      # Dev + live Weaviate testing
```

</details>

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

Q&A is table stakes. Axiom ships with **five distinct chat modes**, each designed for a different workflow:

| Mode | What it's for |
|------|--------------|
| **Q&A** | Direct, cited answers from your documents |
| **Summary** | Condensed overviews of long or complex files |
| **Tutor** | Socratic-style back-and-forth to help you learn the material |
| **Research** | Deep dives with sub-query expansion and reranking |
| **Evidence Pack** | Structured claim-level grounding with source citations |

### Use it how you want

| Interface | Launch command | Best for |
|-----------|---------------|----------|
| **Desktop GUI** | `python main.py` | Daily use — themes, sessions, keyboard shortcuts |
| **Web UI** | `pnpm dev` (in `apps/axiom-web`) | Browser-based access; requires API server |
| **Headless CLI** | `python main.py --cli ...` | Automation, scripting, servers, CI pipelines |
| **API server** | `bash scripts/run_api_dev.sh` | Powers the web UI; exposes HTTP endpoints |
| **Legacy GUI** | `AXIOM_NEW_APP=0 python main.py` | If you prefer the original Tkinter interface |

All interfaces share the same retrieval engine. Same index, same results.

### Everything else

- **Knowledge graphs** — automatic entity extraction and relationship linking across your documents
- **Persistent sessions** — pick up any conversation where you left off (SQLite-backed)
- **Agent profiles** — save different configurations for different projects or tasks
- **Structure-aware ingestion** — parses PDFs, DOCX, Markdown, HTML, and plain text with layout awareness
- **Background processing** — indexing and queries run in threads, so the UI never freezes
- **Theming** — ships with Space Dust, Light, and Dark themes out of the box

---

## 🚀 Usage

### Desktop app

```bash
python main.py
```

Opens the MVC desktop interface. Load a file, build an index, and start asking questions.

### CLI

The CLI shares the same retrieval backend as the GUI — same results, no window required.

```bash
# Index a file
python -m axiom_app.cli index --file docs/my_notes.txt

# Query it
python -m axiom_app.cli query --file docs/my_notes.txt --question "What are the key takeaways?"
```

You can also run via the main entry point:

```bash
python main.py --cli index --file README.md
python main.py --cli query --file README.md --question "how do I install this?"
```

### Run local API

Start a hot-reloading FastAPI server on `http://127.0.0.1:8000`. The script creates `.venv/` and installs `.[dev,api]` automatically on first run.

**macOS / Linux:**

```bash
bash scripts/run_api_dev.sh
```

**Windows (PowerShell):**

```powershell
.\scripts\run_api_dev.ps1
```

Override the Python binary with `AXIOM_PYTHON` if needed. Once running, check `GET /healthz` or browse the auto-generated docs at `http://127.0.0.1:8000/docs`.

### Web UI

The web UI is a Next.js app located in `apps/axiom-web`. It requires the API server to be running first.

**Prerequisites:** Node.js 18+ and [pnpm](https://pnpm.io/installation)

```bash
# 1. Start the API server (in one terminal)
bash scripts/run_api_dev.sh

# 2. Start the web UI (in another terminal)
cd apps/axiom-web
pnpm install
pnpm dev
```

Then open [http://localhost:3000](http://localhost:3000). The web UI provides chat, document library management, and settings — all powered by the same local API.

### Parity audit

Axiom includes a built-in audit tool that verifies consistent behavior across all vector store backends:

```bash
axiom-parity-audit                         # Against mock backends
axiom-parity-audit --require-live-backends  # Against real Weaviate (needs Docker)
```

<details>
<summary><strong>Setting up Weaviate for live audits</strong></summary>

<br />

```bash
pip install -e ".[dev,live-backends]"
docker compose -f docker/weaviate/docker-compose.yml up -d

export AXIOM_TEST_WEAVIATE_URL=http://127.0.0.1:8080
export AXIOM_TEST_WEAVIATE_GRPC_HOST=127.0.0.1
export AXIOM_TEST_WEAVIATE_GRPC_PORT=50051
export AXIOM_TEST_WEAVIATE_GRPC_SECURE=false

axiom-parity-audit --require-live-backends
```

</details>

---

## 🔧 Configuration

Axiom ships with sensible defaults in `axiom_app/default_settings.json`. To customize, copy it to `settings.json` in the project root and tweak away — Axiom will pick it up automatically.

### Environment variables

| Variable | What it does |
|----------|-------------|
| `AXIOM_NEW_APP` | `1` (default) uses the MVC app. `0` falls back to the legacy GUI. The `--cli` flag always forces headless mode. |
| `AXIOM_TEST_WEAVIATE_URL` | Weaviate endpoint for live parity tests |
| `AXIOM_TEST_WEAVIATE_API_KEY` | Weaviate API key |
| `AXIOM_TEST_WEAVIATE_GRPC_HOST` | Weaviate gRPC host |
| `AXIOM_TEST_WEAVIATE_GRPC_PORT` | Weaviate gRPC port |
| `AXIOM_TEST_WEAVIATE_GRPC_SECURE` | Enable TLS for gRPC |
| `AXIOM_PARITY_REQUIRE_LIVE_BACKENDS` | Set to `1` to fail the audit if the live backend proof doesn't pass |

---

## 🧪 Testing

```bash
# Run the test suite
python -m pytest

# With coverage reporting
python -m pytest --cov=axiom_app --cov-report=term

# Live Weaviate integration tests
python -m pytest -q tests/test_live_weaviate_proof.py
```

<details>
<summary><strong>Full CI check (run locally)</strong></summary>

<br />

```bash
ruff check .
python -m pytest --cov=axiom_app --cov-report=xml --cov-report=term
axiom-parity-audit --require-live-backends
python -c "import json; json.load(open('axiom_app/default_settings.json')); print('Settings JSON OK')"
```

</details>

---

## 📁 Project Layout

```
axiom_app/
├── models/          # Application state — no UI, no I/O
├── views/           # PySide6 (Qt6) interface
├── controllers/     # Business logic, event handling
├── services/        # Indexing, retrieval, sessions, pipelines
├── utils/           # LLM/embedding factories, document loaders, helpers
└── assets/          # Bundled resources

apps/
└── axiom-web/       # Next.js web UI (TypeScript + Tailwind)
    ├── app/
    │   ├── chat/    # Chat interface
    │   ├── library/ # Document library management
    │   └── settings/# Provider and model configuration
    └── components/  # Shared UI components

tests/               # pytest suite (unit + integration)
scripts/             # Installers (bash, PowerShell, Windows EXE builder)
docker/              # Weaviate compose for integration testing
main.py              # Entry point — routes to GUI or CLI
agentic_rag_gui.py   # Legacy Tkinter app (kept for compatibility)
```

---

## Roadmap

The web UI and local API server are now shipping alongside the desktop app and CLI. Here's what's next:

- **Desktop packaging** — bundle the web UI and API server into a self-contained desktop app (no terminal required).
- **Streaming responses** — stream tokens from the API to the web UI for snappier chat.
- **Collaborative sessions** — share a running Axiom instance across devices on a local network.

---

## 🤝 Contributing

Contributions are welcome! Check out [CONTRIBUTING.md](CONTRIBUTING.md) for the development workflow, coding standards, and how to submit a pull request.

**The short version:**

```bash
pip install -e ".[dev]"
ruff check .
python -m pytest
```

Make sure linting and tests pass before opening a PR.

---

## 📝 Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

[MIT](LICENSE) — do whatever you want with it.
