<p align="center">
  <img src="logo.png" alt="Axiom" width="140" />
</p>

<h1 align="center">Axiom</h1>

<p align="center">
  <strong>Personal RAG desktop app with an MVC runtime</strong>
</p>

<p align="center">
  <a href="https://github.com/mrzapa/workx/actions/workflows/ci.yml"><img src="https://github.com/mrzapa/workx/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT" /></a>
</p>

---

## Features

- **MVC app** (`axiom_app`) — default runtime with model / controller / view layers
- **Legacy GUI** (`agentic_rag_gui.py`) — available via `AXIOM_NEW_APP=0`
- **Headless CLI** — index and query local files without Tk

---

## Quick Install

### One-liner (recommended)

**macOS / Linux:**

```bash
curl -fsSL https://raw.githubusercontent.com/mrzapa/workx/main/scripts/install_axiom.sh | bash
```

**Windows (PowerShell):**

```powershell
irm https://raw.githubusercontent.com/mrzapa/workx/main/scripts/install_axiom.ps1 | iex
```

The installer clones the repo, creates a virtual environment, installs the
pinned `runtime-all` bundle, and generates an `axiom` launcher that auto-pulls
the latest code on every run.

### Installer options

| Flag | Description |
|------|-------------|
| `--install` | Fresh install (default) |
| `--reinstall` | Remove venv and reinstall from scratch |
| `--uninstall` | Remove Axiom completely |
| `--update` | Pull latest code and update dependencies |

```bash
# Reinstall from scratch
./scripts/install_axiom.sh --reinstall

# Uninstall
./scripts/install_axiom.sh --uninstall
```

> **Environment overrides:** `AXIOM_INSTALL_DIR`, `AXIOM_REPO`, `AXIOM_BRANCH`, `AXIOM_PYTHON`

If a later update changes the pinned runtime bundle, run `axiom update` to
repair the installation.

### Manual setup

<details>
<summary><strong>Click to expand manual setup steps</strong></summary>

#### 1) Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

#### 2) Install a runtime bundle

```bash
# Full GUI runtime
pip install -e ".[runtime-all]"

# Dev/test extras
pip install -e ".[dev]"

# Dev + full GUI runtime
pip install -e ".[dev,runtime-all]"

# Strict live-backend proof extras
pip install -e ".[dev,live-backends]"
```

</details>

---

## Usage

### MVC GUI (default)

```bash
python main.py
```

### Legacy GUI

```bash
AXIOM_NEW_APP=0 python main.py
```

### CLI (headless)

```bash
python main.py --cli index --file README.md
python main.py --cli query --file README.md --question "quick start"
```

Or run the CLI module directly:

```bash
python -m axiom_app.cli index --file README.md
python -m axiom_app.cli query --file README.md --question "install"
```

---

## CLI Examples

### Indexing

`index` writes a manifest-backed persisted index to `<file>.axiom-index/manifest.json` by default.

```bash
python -m axiom_app.cli index --file docs/my_notes.txt
```

### Querying

`query` uses the same shared retrieval backend as the MVC app and can load previously saved indexes.

```bash
python -m axiom_app.cli query --file docs/my_notes.txt --question "dependency"
```

### Parity audit

```bash
axiom-parity-audit
```

Run the strict live-backend audit against local Docker Weaviate:

```bash
pip install -e .[dev,live-backends]
docker compose -f docker/weaviate/docker-compose.yml up -d

export AXIOM_TEST_WEAVIATE_URL=http://127.0.0.1:8080
export AXIOM_TEST_WEAVIATE_GRPC_HOST=127.0.0.1
export AXIOM_TEST_WEAVIATE_GRPC_PORT=50051
export AXIOM_TEST_WEAVIATE_GRPC_SECURE=false

axiom-parity-audit --require-live-backends
```

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `AXIOM_NEW_APP` | `1` (default): MVC path. `0`: legacy GUI. `--cli` forces headless mode regardless. |
| `AXIOM_TEST_WEAVIATE_URL` | Weaviate instance URL for live parity proof |
| `AXIOM_TEST_WEAVIATE_API_KEY` | Weaviate API key |
| `AXIOM_TEST_WEAVIATE_GRPC_HOST` | Weaviate gRPC host |
| `AXIOM_TEST_WEAVIATE_GRPC_PORT` | Weaviate gRPC port |
| `AXIOM_TEST_WEAVIATE_GRPC_SECURE` | Enable TLS for gRPC |
| `AXIOM_PARITY_REQUIRE_LIVE_BACKENDS` | `1`: fail audit unless the live backend proof passes |

---

## Testing

```bash
# Unit tests
python -m pytest

# With coverage
python -m pytest --cov=axiom_app --cov-report=xml --cov-report=term

# Live Weaviate proof
pip install -e ".[dev,live-backends]"
python -m pytest -q tests/test_live_weaviate_proof.py
```

<details>
<summary><strong>Run CI checks locally</strong></summary>

```bash
ruff check .
python -m pytest --cov=axiom_app --cov-report=xml --cov-report=term
axiom-parity-audit --require-live-backends
python - <<'PY'
import json
json.load(open('axiom_app/default_settings.json', encoding='utf-8'))
print('default_settings.json is valid JSON')
PY
```

</details>

---

## Project Layout

| Path | Description |
|------|-------------|
| `axiom_app/` | Default MVC package, CLI, model/controller/view layers |
| `tests/` | Unit and integration-style tests |
| `agentic_rag_gui.py` | Legacy monolithic GUI implementation |
| `main.py` | Canonical entry point with mode switching |

---

## Optional Dependencies

Heavy ML/runtime dependencies are intentionally optional for manual minimal
installs. The installers provision the pinned `runtime-all` bundle, while the
MVC app and CLI surface backend-readiness errors when a selected provider or
vector backend is unavailable in a custom environment.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow and standards.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
