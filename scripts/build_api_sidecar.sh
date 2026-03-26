#!/usr/bin/env bash
# Build the metis-api sidecar binary for Tauri desktop bundling (WOR-14).
#
# Produces a standalone one-file console binary of metis_app.api and places it
# at apps/metis-desktop/src-tauri/binaries/metis-api-{target-triple}, which is
# the naming convention Tauri v2 requires for externalBin sidecar binaries.
#
# Prerequisites: Python environment with metis-app[api] installed, Rust toolchain
# Usage: bash scripts/build_api_sidecar.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_TRIPLE="$(rustc -Vv | grep '^host:' | cut -d' ' -f2)"
OUT_DIR="${REPO_ROOT}/apps/metis-desktop/src-tauri/binaries"

echo "[build_api_sidecar] Target triple: ${TARGET_TRIPLE}"
echo "[build_api_sidecar] Output dir:    ${OUT_DIR}"

pip install pyinstaller

pyinstaller \
  --noconfirm \
  --clean \
  --name metis-api \
  --onefile \
  --console \
  --collect-submodules metis_app \
  --add-data "${REPO_ROOT}/metis_app/assets:metis_app/assets" \
  --add-data "${REPO_ROOT}/metis_app/default_settings.json:metis_app" \
  "${REPO_ROOT}/metis_app/api/__main__.py"

mkdir -p "${OUT_DIR}"
cp "dist/metis-api" "${OUT_DIR}/metis-api-${TARGET_TRIPLE}"
echo "[build_api_sidecar] Sidecar written to: ${OUT_DIR}/metis-api-${TARGET_TRIPLE}"
