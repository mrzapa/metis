#!/usr/bin/env bash
set -euo pipefail

python -m pip install --upgrade pip
pip install pyinstaller

pyinstaller \
  --noconfirm \
  --clean \
  --name METIS \
  --windowed \
  --onefile \
  --icon logo.png \
  --add-data "metis_app/assets:metis_app/assets" \
  --add-data "metis_app/default_settings.json:metis_app" \
  --hidden-import tkinter \
  --collect-submodules metis_app \
  release/metis_mvc_entry.py

echo "Built dist/METIS (or dist/METIS.exe on Windows)"
