#!/usr/bin/env bash
set -euo pipefail

# PyInstaller --add-data syntax separator differs by platform:
#   Windows: ';'    POSIX: ':'
DATA_SEP=':'
case "$(uname -s | tr '[:upper:]' '[:lower:]')" in
  mingw*|msys*|cygwin*)
    DATA_SEP=';'
    ;;
esac

PYI_ARGS=(
  --noconfirm
  --clean
  --name Axiom
  --windowed
  --onefile
  --icon logo.png
  --add-data "axiom_app/default_settings.json${DATA_SEP}axiom_app"
  --hidden-import tkinter
  --collect-submodules axiom_app
  release/axiom_mvc_entry.py
)

if [[ "${AXIOM_DRY_RUN:-0}" == "1" ]]; then
  printf 'pyinstaller'
  printf ' %q' "${PYI_ARGS[@]}"
  printf '\n'
  exit 0
fi

# Ensure icon conversion dependency is always available when using PNG icon.
python -m pip install --upgrade pip
pip install pyinstaller pillow

pyinstaller "${PYI_ARGS[@]}"

echo "Built dist/Axiom (or dist/Axiom.exe on Windows)"
