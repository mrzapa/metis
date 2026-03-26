#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# METIS — local API dev server
#
# Usage (from repo root):
#   bash scripts/run_api_dev.sh
#
# Creates .venv/ if absent, installs .[dev,api], then starts uvicorn with
# hot-reload on http://127.0.0.1:8000.
#
# Override the Python binary:
#   METIS_PYTHON=python3.12 bash scripts/run_api_dev.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PYTHON="${METIS_PYTHON:-python3}"
VENV_DIR=".venv"

# ── Sanity check ──────────────────────────────────────────────────────────────
if [ ! -f "pyproject.toml" ]; then
    printf '[run_api_dev] ERROR: pyproject.toml not found.\n' >&2
    printf '[run_api_dev] Run this script from the repo root.\n' >&2
    exit 1
fi

# ── Virtual environment ───────────────────────────────────────────────────────
if [ ! -d "$VENV_DIR" ]; then
    printf '[run_api_dev] Creating virtual environment...\n'
    "$PYTHON" -m venv "$VENV_DIR"
fi

printf '[run_api_dev] Installing .[dev,api]...\n'
"$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e ".[dev,api]"

# ── Start dev server ──────────────────────────────────────────────────────────
printf '[run_api_dev] Starting uvicorn at http://127.0.0.1:8000 (Ctrl-C to stop)\n'
exec "$VENV_DIR/bin/python" -m uvicorn metis_app.api.app:app \
    --reload \
    --host 127.0.0.1 \
    --port 8000
