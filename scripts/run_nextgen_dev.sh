#!/usr/bin/env bash
# Axiom - combined local API + next-gen web dev launcher.
#
# Starts the existing API dev script and the Next.js dev server together on
# localhost, then stops both when this script exits.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
WEB_DIR="${REPO_ROOT}/apps/axiom-web"
API_SCRIPT="${SCRIPT_DIR}/run_api_dev.sh"
API_HOST="127.0.0.1"
API_PORT="8000"
WEB_HOST="127.0.0.1"
WEB_PORT="3000"
API_URL="http://${API_HOST}:${API_PORT}"
API_HEALTH_URL="${API_URL}/healthz"
WEB_URL="http://${WEB_HOST}:${WEB_PORT}"
PORT_CHECK_PYTHON="${AXIOM_PYTHON:-python3}"
API_PID=""
WEB_PID=""
CLEANUP_RUNNING=0

log() {
    printf '[run_nextgen_dev] %s\n' "$1"
}

fail() {
    printf '[run_nextgen_dev] ERROR: %s\n' "$1" >&2
    exit 1
}

install_hint() {
    if [ -f "${WEB_DIR}/pnpm-lock.yaml" ]; then
        printf 'cd apps/axiom-web && pnpm install'
        return
    fi
    printf 'cd apps/axiom-web && npm install'
}

port_in_use() {
    "${PORT_CHECK_PYTHON}" - "$1" "$2" <<'PY'
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
    "${PORT_CHECK_PYTHON}" - "$1" <<'PY'
import sys
import urllib.error
import urllib.request

url = sys.argv[1]
req = urllib.request.Request(url, headers={"User-Agent": "axiom-nextgen-dev"})
try:
    with urllib.request.urlopen(req, timeout=0.5) as response:
        sys.exit(0 if 200 <= response.status < 500 else 1)
except (urllib.error.URLError, TimeoutError):
    sys.exit(1)
PY
}

wait_for_url() {
    local label="$1"
    local url="$2"
    local pid="$3"
    local attempt=0
    local max_attempts=240

    while [ "$attempt" -lt "$max_attempts" ]; do
        if url_ready "$url"; then
            return 0
        fi
        if ! kill -0 "$pid" 2>/dev/null; then
            return 1
        fi
        attempt=$((attempt + 1))
        sleep 0.5
    done

    log "${label} did not respond within $((max_attempts / 2)) seconds."
    return 1
}

stop_pid() {
    local pid="$1"
    local label="$2"

    if [ -z "$pid" ]; then
        return
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
        return
    fi

    log "Stopping ${label}..."
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
}

cleanup() {
    local exit_code=$?

    trap - EXIT INT TERM
    if [ "$CLEANUP_RUNNING" -eq 0 ]; then
        CLEANUP_RUNNING=1
        stop_pid "$WEB_PID" "web dev server"
        stop_pid "$API_PID" "API dev server"
    fi
    exit "$exit_code"
}

trap cleanup EXIT INT TERM

cd "$REPO_ROOT"

if [ ! -f "${REPO_ROOT}/pyproject.toml" ]; then
    fail "pyproject.toml not found at repo root."
fi
if [ ! -f "${WEB_DIR}/package.json" ]; then
    fail "apps/axiom-web/package.json not found."
fi
if ! command -v "${PORT_CHECK_PYTHON}" >/dev/null 2>&1; then
    fail "Python interpreter '${PORT_CHECK_PYTHON}' is not available on PATH."
fi
if [ ! -d "${WEB_DIR}/node_modules" ] || [ ! -e "${WEB_DIR}/node_modules/.bin/next" ]; then
    fail "Web dependencies are missing. Run '$(install_hint)' and retry."
fi
if port_in_use "${API_HOST}" "${API_PORT}"; then
    fail "Port ${API_PORT} is already in use. Stop the process on ${API_URL} or run the API separately."
fi
if port_in_use "${WEB_HOST}" "${WEB_PORT}"; then
    fail "Port ${WEB_PORT} is already in use. Stop the process on ${WEB_URL} or free the Next dev port."
fi

log "API URL: ${API_URL}"
log "Web URL: ${WEB_URL}"
log "Stop both servers with Ctrl-C."
log "Troubleshooting: free ports ${API_PORT}/${WEB_PORT} if occupied; reinstall web deps with '$(install_hint)'."
log "Starting API bootstrap via scripts/run_api_dev.sh (first run may take longer while .venv and deps install)..."
(
    cd "${REPO_ROOT}"
    exec bash "${API_SCRIPT}"
) &
API_PID=$!

log "Starting Next.js dev server in apps/axiom-web..."
(
    cd "${WEB_DIR}"
    export NEXT_PUBLIC_AXIOM_API_BASE="${API_URL}"
    exec "./node_modules/.bin/next" dev --hostname "${WEB_HOST}" --port "${WEB_PORT}"
) &
WEB_PID=$!

log "Waiting for API health check at ${API_HEALTH_URL}..."
if ! wait_for_url "API" "${API_HEALTH_URL}" "${API_PID}"; then
    fail "API server did not become ready at ${API_HEALTH_URL}. Check the console output above."
fi
log "API is responding."

log "Waiting for web UI at ${WEB_URL}..."
if ! wait_for_url "Web UI" "${WEB_URL}" "${WEB_PID}"; then
    fail "Web UI did not become ready at ${WEB_URL}. Check the console output above."
fi
log "Web UI is responding."
log "Both servers are ready."

while :; do
    if ! kill -0 "${API_PID}" 2>/dev/null; then
        fail "API dev server exited unexpectedly."
    fi
    if ! kill -0 "${WEB_PID}" 2>/dev/null; then
        fail "Web dev server exited unexpectedly."
    fi
    sleep 1
done
