#!/usr/bin/env bash
set -euo pipefail

python -m pip install --upgrade pip
pip install pyinstaller

# NOTE: no --icon is passed by default. PyInstaller on Windows requires
# .ico/.exe icons (or Pillow installed to convert from PNG), so using the
# repository PNG directly breaks CI builds.

pyinstaller \
  --noconfirm \
  --clean \
  --name Axiom \
  --windowed \
  --onefile \
  --add-data "axiom_app/default_settings.json:axiom_app" \
  --hidden-import tkinter \
  --collect-submodules axiom_app \
  release/axiom_mvc_entry.py

echo "Built dist/Axiom (or dist/Axiom.exe on Windows)"
