#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"

echo "==> Running ruff check ."
ruff check .

echo "==> Running python -m pytest"
python -m pytest

echo "==> Validating metis_app/default_settings.json"
python -c "import json, pathlib; path = pathlib.Path('metis_app/default_settings.json'); json.loads(path.read_text(encoding='utf-8')); print(f'Settings JSON OK: {path}')"
