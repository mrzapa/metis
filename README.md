# Axiom (workx)

[![CI](https://github.com/mrzapa/workx/actions/workflows/ci.yml/badge.svg)](https://github.com/mrzapa/workx/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Axiom is a personal RAG desktop application currently in an MVC refactor. It supports:

- **Legacy GUI app** (`agentic_rag_gui.py`) as the default runtime.
- **New MVC app** (`axiom_app`) enabled via `AXIOM_NEW_APP=1`.
- **Headless CLI** for indexing and querying local files without Tk.

## Quick start

### 1) Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

### 2) Install in editable mode

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

`index` writes a JSON stub by default to `<file>.axiom-index.json`.

```bash
python -m axiom_app.cli index --file docs/my_notes.txt
```

### Query behavior

`query` currently performs case-insensitive keyword matching as a fallback when a full RAG backend is not wired.

```bash
python -m axiom_app.cli query --file docs/my_notes.txt --question "dependency"
```

## Environment variables

- `AXIOM_NEW_APP`
  - `0` (default): run legacy GUI path.
  - `1`: enable the new MVC path in `main.py`.
  - In new mode, `--cli` forces headless CLI handling.

## Optional dependencies and fallback behavior

Heavy ML/runtime dependencies are intentionally optional. The CLI is designed to work in headless/non-ML environments using stdlib behavior and local app model state.

## Testing

```bash
python -m pytest
python -m pytest --cov=axiom_app --cov-report=xml --cov-report=term
```

## Run CI checks locally

```bash
ruff check .
python -m pytest --cov=axiom_app --cov-report=xml --cov-report=term
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
