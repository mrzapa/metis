<h1 align="center">METIS AI</h1>

<p align="center">
  <strong>The private, provider-agnostic AI workspace that runs entirely on your machine.</strong><br />
  Index your documents. Ask questions. Get grounded answers.<br />
  No API keys required. Bring a local model and go fully offline.
</p>

<p align="center">
  <a href="https://github.com/mrzapa/metis/actions/workflows/ci.yml"><img src="https://github.com/mrzapa/metis/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Proprietary-red" alt="Proprietary License" /></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="Alpha" />
</p>

<br />

**METIS AI** is a **local-first frontier AI workspace** built with Tauri + Next.js + Litestar. It runs entirely on your machine. Your files never leave your device.

- **Fully local.** Run with a local GGUF model and you don't even need an internet connection.
- **Swap anything.** LLM, embeddings, vector store. Change providers in a config file. Today it's OpenAI, tomorrow it's a model on your laptop.
- **Native shell available.** The same app can be packaged in Tauri for a native window experience with no Electron layer.
- **Constellation home.** The landing page is a live workspace surface for bringing documents into orbit, linking indexes, and jumping into grounded chat.
- **Six ways to think.** Q&A, Summary, Tutor, Research, Evidence Pack, and Knowledge Search modes give you different lenses on the same documents.
- **METIS Companion.** An always-on AI companion that learns from your sessions, reflects on conversations, and grows with your workspace.
- **Evidence-first chat.** Review retrieved sources, inspect trace events, and export grounded answers as JSON or PowerPoint.

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

This starts the local API at `http://127.0.0.1:8000` and opens the web UI in your browser.

Native desktop packaging lives in `apps/metis-desktop/`. The repo launcher intentionally opens the local web UI; use the Tauri shell when you need a native packaged build.

| Interface | Command |
|-----------|---------|
| **Web UI** | `metis` |
| **Web UI (from source)** | `python main.py` |
| **CLI** | `metis --cli <command>` |
| **Desktop GUI** | `metis --desktop` / `metis --gui` |
| **Native desktop shell** | See `apps/metis-desktop/README.md` |

### Use

1. **Build an index from the landing page**: upload files, add folders, or pull an existing index into the Home constellation flow
2. **Ask grounded questions**: switch between Q&A, Summary, Tutor, Research, Evidence Pack, and Knowledge Search in chat
3. **Inspect the answer**: review sources, follow the retrieval trace, or export the current result as an evidence pack or PowerPoint
4. **Keep working in context**: sessions persist to SQLite, while the companion dock and settings flows stay available across the app

---

## ✨ Features

### Zero lock-in: swap every layer

Most RAG apps hardcode their stack. METIS AI treats every layer as a plug-in. Switch providers in `settings.json` and restart. That's it.

| Layer | Options | Go fully offline? |
|-------|---------|:-----------------:|
| **LLM** | OpenAI · Anthropic · Google · xAI · Cohere · LM Studio · **local GGUF** | Yes, with GGUF |
| **Embeddings** | Voyage · Sentence Transformers · **local GGUF** | Yes, with GGUF or ST |
| **Vector store** | In-memory JSON · ChromaDB · Weaviate | Yes, all run locally |

### Constellation home

The landing page is no longer a static launcher. It is a constellation-style workspace where indexed sources become stars you can map, relink, inspect, and send directly into grounded chat. Build new indexes from uploads, filesystem paths, or existing manifests without leaving Home.

### Chat workspace

Chat is a split-panel workspace with persistent sessions on the left, the live conversation in the middle, and evidence plus trace panels on the right. Research runs stream in progressively, can resume after reconnects, and can export their grounded output as JSON or PPTX.

### Six ways to read a document

| Mode | What it's for |
|------|--------------|
| **Q&A** | Direct, cited answers from your documents |
| **Summary** | Condensed overviews of long or complex files |
| **Tutor** | Socratic-style back-and-forth to help you learn |
| **Research** | Deep dives with sub-query expansion and reranking |
| **Evidence Pack** | Structured claim-level grounding with source citations |
| **Knowledge Search** | Retrieval-first exploration when you want to inspect what the index knows before synthesising |

### METIS Companion

An always-on AI companion that lives in the workspace shell. It bootstraps an identity, reflects on active sessions, stores learned memories and playbooks, and surfaces contextual hints as you work. The companion is always available from the floating dock at the bottom of every page.

### Setup, settings, and the companion

The first-run setup flow now walks you through model provider choice, credentials, embeddings, a first index build, and staged starter prompts before dropping you into chat. From there, the settings surface exposes both simple controls and deep retrieval/model options, while the floating METIS Companion dock can reflect on work, surface memory, and stay docked across pages.

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
python -m metis_app.api_litestar
```

Runs the API at `http://127.0.0.1:8000`. Full API reference is available at `http://127.0.0.1:8000/schema` while the server is running.

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

### Forecast on Windows

TimesFM 2.5 currently works best in a dedicated Python 3.11 environment on
Windows. METIS includes a helper script that reproduces the validated setup and
starts the Litestar backend with forecast support enabled:

```powershell
.\scripts\run_forecast_api_dev.ps1
```

That script:

- creates `.venv311-forecast`
- installs `.[dev,api]`
- installs TimesFM from a pinned upstream Git revision with torch extras
- installs `jax` and `scikit-learn` for covariate-backed XReg runs
- starts the API on `http://127.0.0.1:8000` using the Litestar backend

Then run the web UI separately:

```powershell
cd apps/metis-web
pnpm dev
```

Forecast mode now defaults to a near-max 15,360-point context window and a 1k
horizon cap instead of the older 1k / 256 defaults. That keeps METIS close to
TimesFM's limit without advertising an invalid context+horizon pair.

---

## 🔧 Configuration

METIS AI ships with sensible defaults in `metis_app/default_settings.json`. To customise, copy it to `settings.json` in the project root. METIS picks it up automatically on the next launch.

### Brain pass native text gating

`enable_brain_pass` keeps METIS's placement and source-normalisation pass enabled. `brain_pass_native_enabled` allows native Tribev2 analysis when the runtime is installed, and `brain_pass_native_text_enabled` keeps text-backed sources on the native path by default.

```json
{
  "enable_brain_pass": true,
  "brain_pass_native_enabled": true,
  "brain_pass_native_text_enabled": true
}
```

Set `brain_pass_native_text_enabled` to `false` if you want text, document, or image uploads to stay on the lightweight fallback path. Audio and video inputs can still use native analysis when `brain_pass_native_enabled` is on and the runtime is available.

For the native text proxy path, METIS now prefers local system synthesis backends (Windows System.Speech, Linux `espeak`, macOS `say`, or `pyttsx3`) before falling back to gTTS.

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
├── api_litestar/   # Litestar routes (v1/*)
├── engine/         # Indexing + retrieval core (provider-agnostic)
├── models/         # BrainGraph, AppModel, session types
├── services/       # Session repository, index service, pipeline
└── utils/          # Knowledge graph, LLM/embedding providers

apps/
├── metis-web/      # Next.js web UI (TypeScript + Tailwind)
│   ├── app/
│   │   ├── chat/       # Chat interface (RAG Q&A)
│   │   ├── brain/      # Interactive Brain Graph visualisation
│   │   ├── setup/      # First-run onboarding wizard
│   │   └── settings/   # Provider and model configuration
│   └── components/
│       ├── brain/       # BrainGraph 3D component
│       ├── chat/        # Chat + evidence panels
│       └── shell/       # METIS Companion dock, page chrome
└── metis-desktop/  # Tauri desktop shell around metis-web

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

METIS is released under the proprietary license in [LICENSE](LICENSE).

Licensing cutover:

- Versions up to and including `v1.0.0` were released under MIT.
- Versions after `v1.0.0` are proprietary unless covered by a separate written license agreement.
