# Axiom

[![CI](https://github.com/mrzapa/workx/actions/workflows/ci.yml/badge.svg)](https://github.com/mrzapa/workx/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Axiom is a personal RAG desktop application with an opt-in MVC runtime. It supports:

- **Legacy GUI app** (`agentic_rag_gui.py`) as the default runtime.
- **New MVC app** (`axiom_app`) enabled via `AXIOM_NEW_APP=1`.
- **Headless CLI** for indexing and querying local files without Tk.

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

The installer clones the repo, creates a virtual environment, installs
dependencies, and generates an `axiom` launcher that auto-pulls the latest code
on every run.

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

Environment overrides: `AXIOM_INSTALL_DIR`, `AXIOM_REPO`, `AXIOM_BRANCH`, `AXIOM_PYTHON`.

### Manual setup

#### 1) Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

#### 2) Install in editable mode

```bash
pip install -e .
```

For test/dev extras:

```bash
pip install -e .[dev]
```

## Run modes (GUI + CLI)

### Legacy GUI (default path)

```bash
python main.py
```

### New MVC GUI

```bash
AXIOM_NEW_APP=1 python main.py
```

### CLI mode (headless)

```bash
AXIOM_NEW_APP=1 python main.py --cli index --file README.md
AXIOM_NEW_APP=1 python main.py --cli query --file README.md --question "quick start"
```

You can also run the CLI module directly:

```bash
python -m axiom_app.cli index --file README.md
python -m axiom_app.cli query --file README.md --question "install"
```

## CLI examples

### Index output file

`index` writes a manifest-backed persisted index to `<file>.axiom-index/manifest.json` by default.

```bash
python -m axiom_app.cli index --file docs/my_notes.txt
```

Run the MVC parity audit:

```bash
axiom-parity-audit
```

Run the strict live-backend audit against local Docker Weaviate:

```bash
docker compose -f docker/weaviate/docker-compose.yml up -d
export AXIOM_TEST_WEAVIATE_URL=http://127.0.0.1:8080
export AXIOM_TEST_WEAVIATE_GRPC_HOST=127.0.0.1
export AXIOM_TEST_WEAVIATE_GRPC_PORT=50051
export AXIOM_TEST_WEAVIATE_GRPC_SECURE=false
axiom-parity-audit --require-live-backends
```

### Query behavior

`query` uses the same shared retrieval backend as the MVC app and can load previously saved indexes.

```bash
python -m axiom_app.cli query --file docs/my_notes.txt --question "dependency"
```

## Environment variables

- `AXIOM_NEW_APP`
  - `0` (default): run legacy GUI path.
  - `1`: enable the new MVC path in `main.py`.
  - In new mode, `--cli` forces headless CLI handling.
- `AXIOM_TEST_WEAVIATE_URL`
- `AXIOM_TEST_WEAVIATE_API_KEY`
- `AXIOM_TEST_WEAVIATE_GRPC_HOST`
- `AXIOM_TEST_WEAVIATE_GRPC_PORT`
- `AXIOM_TEST_WEAVIATE_GRPC_SECURE`
  - Canonical env contract for the live Weaviate parity proof.
- `AXIOM_PARITY_REQUIRE_LIVE_BACKENDS`
  - `1`: make `axiom-parity-audit` fail unless the live backend proof runs and passes.

## Optional dependencies and fallback behavior

Heavy ML/runtime dependencies are intentionally optional. The MVC app and CLI surface backend-readiness errors when a selected provider or vector backend is unavailable.

## Testing

```bash
python -m pytest
python -m pytest --cov=axiom_app --cov-report=xml --cov-report=term
python -m pytest -q tests/test_live_weaviate_proof.py
```

## Run CI checks locally

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

## Project layout

- `axiom_app/` — new MVC package, CLI, model/controller/view layers.
- `tests/` — unit and integration-style tests.
- `agentic_rag_gui.py` — legacy monolithic GUI implementation.
- `main.py` — canonical entry point with mode switching.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow and standards.

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
