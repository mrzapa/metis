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
  printf 'python -m PyInstaller'
  printf ' %q' "${PYI_ARGS[@]}"
  printf '\n'
  exit 0
fi

# Keep installation and execution bound to the same interpreter.
python -m pip install --upgrade pip
python -m pip install pyinstaller pillow
python -m PyInstaller "${PYI_ARGS[@]}"

echo "Built dist/Axiom (or dist/Axiom.exe on Windows)"
