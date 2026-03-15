#!/usr/bin/env bash
# Build the axiom-api sidecar binary for Tauri desktop bundling (WOR-14).
#
# Produces a standalone one-file console binary of axiom_app.api and places it
# at apps/axiom-desktop/src-tauri/binaries/axiom-api-{target-triple}, which is
# the naming convention Tauri v2 requires for externalBin sidecar binaries.
#
# Prerequisites: Python environment with axiom-app[api] installed, Rust toolchain
# Usage: bash scripts/build_api_sidecar.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_TRIPLE="$(rustc -Vv | grep '^host:' | cut -d' ' -f2)"
OUT_DIR="${REPO_ROOT}/apps/axiom-desktop/src-tauri/binaries"

echo "[build_api_sidecar] Target triple: ${TARGET_TRIPLE}"
echo "[build_api_sidecar] Output dir:    ${OUT_DIR}"

pip install pyinstaller

pyinstaller \
  --noconfirm \
  --clean \
  --name axiom-api \
  --onefile \
  --console \
  --collect-submodules axiom_app \
  --add-data "${REPO_ROOT}/axiom_app/assets:axiom_app/assets" \
  --add-data "${REPO_ROOT}/axiom_app/default_settings.json:axiom_app" \
  "${REPO_ROOT}/axiom_app/api/__main__.py"

mkdir -p "${OUT_DIR}"
cp "dist/axiom-api" "${OUT_DIR}/axiom-api-${TARGET_TRIPLE}"
echo "[build_api_sidecar] Sidecar written to: ${OUT_DIR}/axiom-api-${TARGET_TRIPLE}"
