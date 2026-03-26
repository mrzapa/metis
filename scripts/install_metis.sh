#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# METIS Installer — install / reinstall / uninstall the METIS app
#
# Usage:
#   curl -fsSL <raw-url>/scripts/install_metis.sh | bash           # install
#   ./install_metis.sh                                              # install
#   ./install_metis.sh --reinstall                                  # reinstall
#   ./install_metis.sh --uninstall                                  # uninstall
#
# Configurable via environment:
#   METIS_INSTALL_DIR   — where to clone the repo  (default: ~/metis)
#   METIS_REPO          — git clone URL             (default: https://github.com/mrzapa/metis.git)
#   METIS_BRANCH        — branch to track           (default: main)
#   METIS_PYTHON        — python binary             (default: python3)
#   METIS_PIP_RETRIES   — pip network retries       (default: 10)
#   METIS_PIP_TIMEOUT   — pip network timeout (sec) (default: 120)
#   METIS_INSTALL_RETRIES — full install step retries (default: 4)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
INSTALL_DIR="${METIS_INSTALL_DIR:-$HOME/metis}"
REPO_URL="${METIS_REPO:-https://github.com/mrzapa/metis.git}"
BRANCH="${METIS_BRANCH:-main}"
PYTHON="${METIS_PYTHON:-python3}"
VENV_DIR="$INSTALL_DIR/.venv"
INSTALL_SPEC="${INSTALL_DIR}[runtime-all,api]"
PIP_RETRIES="${METIS_PIP_RETRIES:-10}"
PIP_TIMEOUT="${METIS_PIP_TIMEOUT:-120}"
INSTALL_RETRIES="${METIS_INSTALL_RETRIES:-4}"
LAUNCHER_DIR="$HOME/.local/bin"
LAUNCHER="$LAUNCHER_DIR/metis"

# ── Colors ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()  { printf "${CYAN}[metis]${NC} %s\n" "$*"; }
ok()    { printf "${GREEN}[metis]${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}[metis]${NC} %s\n" "$*"; }
err()   { printf "${RED}[metis]${NC} %s\n" "$*" >&2; }

retry_with_backoff() {
    local description="$1"
    local max_attempts="$2"
    shift 2

    local attempt=1
    local delay=2

    while [ "$attempt" -le "$max_attempts" ]; do
        if "$@"; then
            return 0
        fi

        if [ "$attempt" -ge "$max_attempts" ]; then
            err "$description failed after $attempt attempts."
            return 1
        fi

        warn "$description failed (attempt $attempt/$max_attempts)."
        info "Retrying in ${delay}s..."
        sleep "$delay"
        delay=$((delay * 2))
        if [ "$delay" -gt 30 ]; then
            delay=30
        fi
        attempt=$((attempt + 1))
    done
}

run_pip() {
    local venv_python="$1"
    shift

    "$venv_python" -m pip "$@" \
        --disable-pip-version-check \
        --no-input \
        --retries "$PIP_RETRIES" \
        --timeout "$PIP_TIMEOUT"
}

# ── Helpers ──────────────────────────────────────────────────────────────────
write_launcher() {
    mkdir -p "$LAUNCHER_DIR"

    cat > "$LAUNCHER" <<LAUNCHER_EOF
#!/usr/bin/env bash
# Auto-generated METIS launcher — do not edit.
# Usage:
#   metis                  -- Web UI (default)
#   metis --desktop        -- Qt desktop GUI
#   metis --gui            -- Qt desktop GUI (alias)
#   metis --web            -- Web UI (legacy no-op, same as default)
#   metis --cli <args>     -- CLI mode
set -euo pipefail

METIS_DIR="$INSTALL_DIR"
BRANCH="$BRANCH"
VENV_PYTHON="$VENV_DIR/bin/python"
API_HOST="127.0.0.1"
API_PORT="8000"
WEB_HOST="127.0.0.1"
WEB_PORT="3000"
API_URL="http://127.0.0.1:8000"
API_HEALTH_URL="\${API_URL}/healthz"
WEB_URL="http://127.0.0.1:3000"
WEB_DIR="\${METIS_DIR}/apps/metis-web/out"
API_PID=""
WEB_PID=""
API_STDOUT=""
API_STDERR=""
WEB_STDOUT=""
WEB_STDERR=""
CLEANUP_RUNNING=0

show_help() {
    cat <<'EOF'
METIS launcher

Usage:
  metis                  Start the local API and static web UI
  metis --desktop        Start the legacy Qt desktop shell
  metis --gui            Alias for --desktop
  metis --cli <args>     Run the CLI
  metis --help           Show this help
EOF
}

open_browser() {
    local url="\$1"
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "\$url" >/dev/null 2>&1 || true
    elif command -v open >/dev/null 2>&1; then
        open "\$url" >/dev/null 2>&1 || true
    else
        echo "Open \$url in your browser."
    fi
}

port_in_use() {
    "\$VENV_PYTHON" - "\$1" "\$2" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
    sock.settimeout(0.25)
    sys.exit(0 if sock.connect_ex((host, port)) == 0 else 1)
PY
}

url_ready() {
    "\$VENV_PYTHON" - "\$1" <<'PY'
import sys
import urllib.error
import urllib.request

url = sys.argv[1]
req = urllib.request.Request(url, headers={"User-Agent": "metis-launcher"})
try:
    with urllib.request.urlopen(req, timeout=0.5) as response:
        sys.exit(0 if 200 <= response.status < 500 else 1)
except (urllib.error.URLError, TimeoutError):
    sys.exit(1)
PY
}

wait_for_url() {
    local label="\$1"
    local url="\$2"
    local pid="\$3"
    local max_attempts="\${4:-60}"
    local attempt=0

    while [ "\$attempt" -lt "\$max_attempts" ]; do
        if url_ready "\$url"; then
            return 0
        fi
        if ! kill -0 "\$pid" 2>/dev/null; then
            return 1
        fi
        attempt=\$((attempt + 1))
        sleep 0.5
    done

    echo "\${label} did not respond within \$((max_attempts / 2)) seconds." >&2
    return 1
}

stop_pid() {
    local pid="\$1"
    if [ -n "\$pid" ] && kill -0 "\$pid" 2>/dev/null; then
        kill "\$pid" 2>/dev/null || true
        wait "\$pid" 2>/dev/null || true
    fi
}

log_tail() {
    local path="\$1"
    if [ -f "\$path" ]; then
        tail -n 40 "\$path" 2>/dev/null || true
    fi
}

startup_failure() {
    local label="\$1"
    local pid="\$2"
    local stdout_file="\$3"
    local stderr_file="\$4"
    local hint="\$5"

    {
        if [ -n "\$pid" ] && ! kill -0 "\$pid" 2>/dev/null; then
            echo "\${label} exited before becoming ready."
        fi

        local stdout_tail
        stdout_tail="\$(log_tail "\$stdout_file")"
        if [ -n "\$stdout_tail" ]; then
            printf '%s\n%s\n' "\${label} stdout:" "\$stdout_tail"
        fi

        local stderr_tail
        stderr_tail="\$(log_tail "\$stderr_file")"
        if [ -n "\$stderr_tail" ]; then
            printf '%s\n%s\n' "\${label} stderr:" "\$stderr_tail"
        fi

        if [ -n "\$hint" ]; then
            echo "\$hint"
        fi
    } >&2

    exit 1
}

cleanup() {
    local exit_code=\$?
    trap - EXIT INT TERM
    if [ "\$CLEANUP_RUNNING" -eq 0 ]; then
        CLEANUP_RUNNING=1
        stop_pid "\$WEB_PID"
        stop_pid "\$API_PID"
        rm -f "\$API_STDOUT" "\$API_STDERR" "\$WEB_STDOUT" "\$WEB_STDERR"
    fi
    exit "\$exit_code"
}

trap cleanup EXIT INT TERM

if [ -d "\$METIS_DIR/.git" ]; then
    head_before=\$(git -C "\$METIS_DIR" rev-parse HEAD 2>/dev/null || true)
    git -C "\$METIS_DIR" pull origin "\$BRANCH" --ff-only 2>/dev/null || true
    head_after=\$(git -C "\$METIS_DIR" rev-parse HEAD 2>/dev/null || true)

    needs_build=false
    if [ ! -f "\${WEB_DIR}/index.html" ]; then
        needs_build=true
    elif [ "\$head_before" != "\$head_after" ]; then
        needs_build=true
    fi

    if [ "\$needs_build" = true ] && command -v node >/dev/null 2>&1; then
        web_app_dir="\$METIS_DIR/apps/metis-web"
        if [ -f "\$web_app_dir/package.json" ]; then
            echo "Rebuilding web UI..."
            (cd "\$web_app_dir" && npm install --silent 2>/dev/null && npm run build 2>/dev/null) && {
                echo "Web UI rebuilt successfully."
            } || {
                echo "Web UI rebuild failed. Install Node.js and re-run the installer to fix." >&2
            }
        fi
    fi
fi

DESKTOP_MODE=false
CLI_MODE=false
SHOW_HELP=false
FILTERED_ARGS=()

for arg in "\$@"; do
    case "\$arg" in
        --desktop|--gui)
            DESKTOP_MODE=true
            ;;
        --cli)
            CLI_MODE=true
            ;;
        --web)
            ;;
        -h|--help)
            SHOW_HELP=true
            ;;
        *)
            FILTERED_ARGS+=("\$arg")
            ;;
    esac
done

if [ "\$SHOW_HELP" = true ]; then
    show_help
    exit 0
fi

cd "\$METIS_DIR"

if [ "\$DESKTOP_MODE" = true ] && [ "\$CLI_MODE" = true ]; then
    echo "Choose either --desktop/--gui or --cli, not both." >&2
    exit 1
fi

if [ "\$DESKTOP_MODE" = true ]; then
    exec "\$VENV_PYTHON" "\$METIS_DIR/main.py" "\${FILTERED_ARGS[@]}"
fi

if [ "\$CLI_MODE" = true ]; then
    exec "\$VENV_PYTHON" "\$METIS_DIR/main.py" --cli "\${FILTERED_ARGS[@]}"
fi

if [ ! -f "\${WEB_DIR}/index.html" ]; then
    echo "Built web UI not found at \${WEB_DIR}. Install Node.js and re-run the installer, or build apps/metis-web manually." >&2
    exit 1
fi

if port_in_use "\$API_HOST" "\$API_PORT" || port_in_use "\$WEB_HOST" "\$WEB_PORT"; then
    if url_ready "\$API_HEALTH_URL" && url_ready "\$WEB_URL"; then
        open_browser "\$WEB_URL"
        echo "METIS is already running at \${WEB_URL}."
        exit 0
    fi
    echo "Ports \${API_PORT}/\${WEB_PORT} are already in use. Stop the existing processes or close the app before starting a new instance." >&2
    exit 1
fi

API_STDOUT="\$(mktemp)"
API_STDERR="\$(mktemp)"
WEB_STDOUT="\$(mktemp)"
WEB_STDERR="\$(mktemp)"

"\$VENV_PYTHON" -m uvicorn metis_app.api.app:app --host "\$API_HOST" --port "\$API_PORT" >"\$API_STDOUT" 2>"\$API_STDERR" &
API_PID=\$!
if ! wait_for_url "API" "\$API_HEALTH_URL" "\$API_PID"; then
    startup_failure "API server" "\$API_PID" "\$API_STDOUT" "\$API_STDERR" "Verify that FastAPI dependencies are installed and that port \${API_PORT} is available."
fi

"\$VENV_PYTHON" -m http.server "\$WEB_PORT" --bind "\$WEB_HOST" --directory "\$WEB_DIR" >"\$WEB_STDOUT" 2>"\$WEB_STDERR" &
WEB_PID=\$!
if ! wait_for_url "Web UI" "\$WEB_URL" "\$WEB_PID"; then
    startup_failure "Web UI server" "\$WEB_PID" "\$WEB_STDOUT" "\$WEB_STDERR" "Verify that the exported web bundle exists at \${WEB_DIR} and that port \${WEB_PORT} is available."
fi

open_browser "\$WEB_URL"
echo "METIS running (API PID \$API_PID, Web PID \$WEB_PID) at \$WEB_URL. Press Ctrl+C to stop."

while :; do
    if ! kill -0 "\$API_PID" 2>/dev/null; then
        startup_failure "API server" "\$API_PID" "\$API_STDOUT" "\$API_STDERR" "The API server stopped unexpectedly."
    fi
    if ! kill -0 "\$WEB_PID" 2>/dev/null; then
        startup_failure "Web UI server" "\$WEB_PID" "\$WEB_STDOUT" "\$WEB_STDERR" "The static web server stopped unexpectedly."
    fi
    sleep 1
done
LAUNCHER_EOF

    chmod +x "$LAUNCHER"
}

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
    info "Uninstalling METIS…"
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
    ok "METIS has been uninstalled."
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
    retry_with_backoff "pip self-upgrade" "$INSTALL_RETRIES" \
        run_pip "$VENV_DIR/bin/python" install --upgrade pip --quiet
    retry_with_backoff "dependency installation" "$INSTALL_RETRIES" \
        run_pip "$VENV_DIR/bin/python" install -e "$INSTALL_SPEC" --quiet --prefer-binary
    ok "Dependencies installed."

    # ── Web UI (optional) ────────────────────────────────────────────────
    local web_app_dir="$INSTALL_DIR/apps/metis-web"
    if command -v node &>/dev/null; then
        if [ -f "$web_app_dir/package.json" ]; then
            info "Node.js detected — building web UI..."
            (cd "$web_app_dir" && npm install --silent && npm run build) && {
                ok "Web UI built successfully."
            } || {
                warn "Web UI build failed. The backend is still usable without the web UI."
            }
        else
            warn "Web UI package.json not found — skipping web build."
        fi
    else
        warn "Node.js not found — skipping web UI build."
        warn "Install Node.js (https://nodejs.org) to enable the web UI."
    fi

    # ── Launcher script ──────────────────────────────────────────────────
    write_launcher
    ok "Launcher installed: $LAUNCHER"

    # ── Summary ──────────────────────────────────────────────────────────
    echo ""
    printf "${BOLD}${GREEN}✔ METIS installed successfully!${NC}\n"
    echo ""
    info "Install directory : $INSTALL_DIR"
    info "Virtual env       : $VENV_DIR"
    info "Launcher          : $LAUNCHER"
    echo ""
    info "Run METIS:"
    printf "  ${BOLD}metis${NC}                          # Launch METIS\n"
    printf "  ${BOLD}metis --cli index --file f.txt${NC}  # CLI mode\n"
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
        err "METIS is not installed at $INSTALL_DIR. Run install first."
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
    retry_with_backoff "pip self-upgrade" "$INSTALL_RETRIES" \
        run_pip "$VENV_DIR/bin/python" install --upgrade pip --quiet
    retry_with_backoff "dependency update" "$INSTALL_RETRIES" \
        run_pip "$VENV_DIR/bin/python" install -e "$INSTALL_SPEC" --quiet --prefer-binary

    # ── Rebuild web UI ────────────────────────────────────────────────
    local web_app_dir="$INSTALL_DIR/apps/metis-web"
    if command -v node &>/dev/null; then
        if [ -f "$web_app_dir/package.json" ]; then
            info "Rebuilding web UI..."
            (cd "$web_app_dir" && npm install --silent && npm run build) && {
                ok "Web UI rebuilt successfully."
            } || {
                warn "Web UI rebuild failed. The backend is still usable without the web UI."
            }
        fi
    else
        warn "Node.js not found — skipping web UI rebuild."
    fi

    write_launcher

    ok "METIS updated to latest."
}

# ── CLI ──────────────────────────────────────────────────────────────────────
usage() {
    cat <<EOF
${BOLD}METIS Installer${NC}

Usage:
  $(basename "$0") [OPTION]

Options:
  --install       Install METIS (default if no option given)
  --reinstall     Remove venv and reinstall from scratch
  --uninstall     Remove METIS completely
  --update        Pull latest code and update dependencies
  -h, --help      Show this help message

Environment variables:
  METIS_INSTALL_DIR   Install location     (default: ~/metis)
  METIS_REPO          Git repository URL   (default: https://github.com/mrzapa/metis.git)
  METIS_BRANCH        Branch to track      (default: main)
  METIS_PYTHON        Python binary        (default: python3)
    METIS_PIP_RETRIES   pip request retries  (default: 10)
    METIS_PIP_TIMEOUT   pip timeout seconds  (default: 120)
    METIS_INSTALL_RETRIES  full pip step retries (default: 4)
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
    printf "${BOLD}${CYAN}═══ METIS Installer ═══${NC}\n"
    echo ""

    case "$action" in
        install)    do_install false  ;;
        reinstall)  do_install true   ;;
        uninstall)  do_uninstall      ;;
        update)     do_update         ;;
    esac
}

main "$@"
