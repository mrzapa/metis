#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Axiom Installer — install / reinstall / uninstall the Axiom MVC app
#
# Usage:
#   curl -fsSL <raw-url>/scripts/install_axiom.sh | bash           # install
#   ./install_axiom.sh                                              # install
#   ./install_axiom.sh --reinstall                                  # reinstall
#   ./install_axiom.sh --uninstall                                  # uninstall
#
# Configurable via environment:
#   AXIOM_INSTALL_DIR   — where to clone the repo  (default: ~/axiom)
#   AXIOM_REPO          — git clone URL             (default: https://github.com/mrzapa/workx.git)
#   AXIOM_BRANCH        — branch to track           (default: main)
#   AXIOM_PYTHON        — python binary             (default: python3)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
INSTALL_DIR="${AXIOM_INSTALL_DIR:-$HOME/axiom}"
REPO_URL="${AXIOM_REPO:-https://github.com/mrzapa/workx.git}"
BRANCH="${AXIOM_BRANCH:-main}"
PYTHON="${AXIOM_PYTHON:-python3}"
VENV_DIR="$INSTALL_DIR/.venv"
LAUNCHER_DIR="$HOME/.local/bin"
LAUNCHER="$LAUNCHER_DIR/axiom"

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()  { printf "${CYAN}[axiom]${NC} %s\n" "$*"; }
ok()    { printf "${GREEN}[axiom]${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}[axiom]${NC} %s\n" "$*"; }
err()   { printf "${RED}[axiom]${NC} %s\n" "$*" >&2; }

# ── Helpers ──────────────────────────────────────────────────────────────────
require_cmd() {
    if ! command -v "$1" &>/dev/null; then
        err "Required command '$1' not found. Please install it and try again."
        exit 1
    fi
}

ensure_python_version() {
    local ver
    ver=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || {
        err "Could not determine Python version. Is '$PYTHON' installed?"
        exit 1
    }
    local major minor
    major="${ver%%.*}"
    minor="${ver##*.}"
    if (( major < 3 || (major == 3 && minor < 10) )); then
        err "Python >= 3.10 is required (found $ver)."
        exit 1
    fi
    ok "Python $ver detected."
}

# ── Uninstall ────────────────────────────────────────────────────────────────
do_uninstall() {
    info "Uninstalling Axiom…"
    if [ -f "$LAUNCHER" ]; then
        rm -f "$LAUNCHER"
        ok "Removed launcher: $LAUNCHER"
    fi
    if [ -d "$INSTALL_DIR" ]; then
        rm -rf "$INSTALL_DIR"
        ok "Removed install directory: $INSTALL_DIR"
    else
        warn "Install directory not found: $INSTALL_DIR (already removed?)"
    fi
    ok "Axiom has been uninstalled."
}

# ── Install / Reinstall ─────────────────────────────────────────────────────
do_install() {
    local is_reinstall="${1:-false}"

    require_cmd git
    require_cmd "$PYTHON"
    ensure_python_version

    # ── Clone or pull ────────────────────────────────────────────────────
    if [ -d "$INSTALL_DIR/.git" ]; then
        if [ "$is_reinstall" = "true" ]; then
            info "Reinstall requested — pulling latest code…"
            git -C "$INSTALL_DIR" fetch origin "$BRANCH"
            git -C "$INSTALL_DIR" checkout "$BRANCH" 2>/dev/null || git -C "$INSTALL_DIR" checkout -b "$BRANCH" "origin/$BRANCH"
            git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
            ok "Repository updated to latest origin/$BRANCH."
        else
            info "Existing installation found — pulling latest code…"
            git -C "$INSTALL_DIR" fetch origin "$BRANCH"
            git -C "$INSTALL_DIR" checkout "$BRANCH" 2>/dev/null || true
            git -C "$INSTALL_DIR" pull origin "$BRANCH" --ff-only || {
                warn "Fast-forward pull failed. Running hard reset to origin/$BRANCH."
                git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
            }
            ok "Repository up to date."
        fi
    else
        info "Cloning repository from $REPO_URL (branch: $BRANCH)…"
        git clone --branch "$BRANCH" --single-branch "$REPO_URL" "$INSTALL_DIR"
        ok "Repository cloned."
    fi

    # ── Virtual environment ──────────────────────────────────────────────
    if [ "$is_reinstall" = "true" ] && [ -d "$VENV_DIR" ]; then
        info "Reinstall: removing old virtual environment…"
        rm -rf "$VENV_DIR"
    fi

    if [ ! -d "$VENV_DIR" ]; then
        info "Creating virtual environment…"
        "$PYTHON" -m venv "$VENV_DIR"
        ok "Virtual environment created."
    fi

    info "Installing dependencies…"
    "$VENV_DIR/bin/python" -m pip install --upgrade pip --quiet
    "$VENV_DIR/bin/pip" install -e "$INSTALL_DIR" --quiet
    ok "Dependencies installed."

    # ── Launcher script ──────────────────────────────────────────────────
    mkdir -p "$LAUNCHER_DIR"

    cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
# Auto-generated Axiom launcher — do not edit.
# Pulls latest code and runs the MVC app.
set -euo pipefail

AXIOM_DIR="$INSTALL_DIR"
BRANCH="$BRANCH"

# Pull latest code silently
if [ -d "\$AXIOM_DIR/.git" ]; then
    git -C "\$AXIOM_DIR" pull origin "\$BRANCH" --ff-only 2>/dev/null || true
fi

# Activate venv and run
export AXIOM_NEW_APP=1
exec "$VENV_DIR/bin/python" "\$AXIOM_DIR/main.py" "\$@"
LAUNCHER_EOF

    chmod +x "$LAUNCHER"
    ok "Launcher installed: $LAUNCHER"

    # ── Summary ──────────────────────────────────────────────────────────
    echo ""
    printf "${BOLD}${GREEN}✔ Axiom installed successfully!${NC}\n"
    echo ""
    info "Install directory : $INSTALL_DIR"
    info "Virtual env       : $VENV_DIR"
    info "Launcher          : $LAUNCHER"
    echo ""
    info "Run Axiom:"
    printf "  ${BOLD}axiom${NC}                          # GUI mode\n"
    printf "  ${BOLD}axiom --cli index --file f.txt${NC}  # CLI mode\n"
    echo ""
    if [[ ":$PATH:" != *":$LAUNCHER_DIR:"* ]]; then
        warn "$LAUNCHER_DIR is not in your PATH."
        warn "Add it with:  export PATH=\"$LAUNCHER_DIR:\$PATH\""
        warn "Or add the line above to your ~/.bashrc / ~/.zshrc"
    fi
}

# ── Update (pull latest only, no venv rebuild) ───────────────────────────────
do_update() {
    require_cmd git

    if [ ! -d "$INSTALL_DIR/.git" ]; then
        err "Axiom is not installed at $INSTALL_DIR. Run install first."
        exit 1
    fi

    info "Pulling latest code…"
    git -C "$INSTALL_DIR" fetch origin "$BRANCH"
    git -C "$INSTALL_DIR" checkout "$BRANCH" 2>/dev/null || true
    git -C "$INSTALL_DIR" pull origin "$BRANCH" --ff-only || {
        warn "Fast-forward pull failed. Running hard reset to origin/$BRANCH."
        git -C "$INSTALL_DIR" reset --hard "origin/$BRANCH"
    }

    info "Updating dependencies…"
    "$VENV_DIR/bin/python" -m pip install --upgrade pip --quiet
    "$VENV_DIR/bin/pip" install -e "$INSTALL_DIR" --quiet

    ok "Axiom updated to latest."
}

# ── CLI ──────────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
${BOLD}Axiom Installer${NC}

Usage:
  $(basename "$0") [OPTION]

Options:
  --install       Install Axiom (default if no option given)
  --reinstall     Remove venv and reinstall from scratch
  --uninstall     Remove Axiom completely
  --update        Pull latest code and update dependencies
  -h, --help      Show this help message

Environment variables:
  AXIOM_INSTALL_DIR   Install location     (default: ~/axiom)
  AXIOM_REPO          Git repository URL   (default: https://github.com/mrzapa/workx.git)
  AXIOM_BRANCH        Branch to track      (default: main)
  AXIOM_PYTHON        Python binary        (default: python3)
EOF
}

main() {
    local action="install"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --install)    action="install";    shift ;;
            --reinstall)  action="reinstall";  shift ;;
            --uninstall)  action="uninstall";  shift ;;
            --update)     action="update";     shift ;;
            -h|--help)    usage; exit 0        ;;
            *)
                err "Unknown option: $1"
                usage
                exit 1
                ;;
        esac
    done

    echo ""
    printf "${BOLD}${CYAN}═══ Axiom Installer ═══${NC}\n"
    echo ""

    case "$action" in
        install)    do_install false  ;;
        reinstall)  do_install true   ;;
        uninstall)  do_uninstall      ;;
        update)     do_update         ;;
    esac
}

main "$@"
