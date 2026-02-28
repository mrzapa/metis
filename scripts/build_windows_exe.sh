#!/usr/bin/env bash
set -euo pipefail

python -m pip install --upgrade pip
pip install pyinstaller

pyinstaller \
  --noconfirm \
  --clean \
  --name Axiom \
  --windowed \
  --onefile \
  --icon logo.png \
  --add-data "axiom_app/default_settings.json:axiom_app" \
  --hidden-import tkinter \
  --collect-submodules axiom_app \
  release/axiom_mvc_entry.py

echo "Built dist/Axiom (or dist/Axiom.exe on Windows)"
