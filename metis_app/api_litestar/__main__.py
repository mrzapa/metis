"""CLI launcher for the local METIS Litestar API server.

Concurrency notes:
  - Uses an atomic O_EXCL lock file to ensure only one instance runs at a time.
  - The lock is released when the process exits (normally or via signal).
  - If the process crashes and leaves a stale lock, remove it manually:
      rm ~/.metis_api.lock  (or the path printed in the error message)
"""

from __future__ import annotations

import atexit
import os
import pathlib
import socket
import sys

import uvicorn

_HERE = pathlib.Path(__file__).resolve().parent
_PACKAGE_ROOT = _HERE.parent
_REPO_ROOT = _PACKAGE_ROOT.parent
_LOCK_FILE = _REPO_ROOT / ".metis_api.lock"


def _find_free_port(host: str) -> int:
    """Bind to port 0 and let the OS assign a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _acquire_lock() -> bool:
    """Acquire single-instance lock using atomic O_EXCL file creation."""
    try:
        fd = os.open(str(_LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return False


def _release_lock() -> None:
    try:
        _LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _port_from_settings() -> int | None:
    """Return api_port from settings.json if present and valid."""
    try:
        import json

        settings_path = _REPO_ROOT / "settings.json"
        if settings_path.exists():
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            raw = data.get("api_port")
            if raw is not None:
                port = int(raw)
                if 1 <= port <= 65535:
                    return port
    except Exception:
        pass
    return None


def main() -> None:
    if not _acquire_lock():
        print(
            "ERROR: Another METIS API instance is already running.\n"
            f"       Lock file: {_LOCK_FILE}\n"
            "       Stop the existing instance or remove the lock file to proceed.",
            file=sys.stderr,
        )
        sys.exit(1)

    atexit.register(_release_lock)

    host = os.getenv("METIS_API_HOST", "127.0.0.1")
    port_env = os.getenv("METIS_API_PORT")
    if port_env:
        port = int(port_env)
    else:
        port = _port_from_settings() or _find_free_port(host)

    # Sentinel consumed by apps/metis-desktop/src-tauri/src/lib.rs via strip_prefix.
    # Must remain a plain stdout line; reformatting breaks the Tauri host handshake.
    print(f"METIS_API_LISTENING=http://{host}:{port}", flush=True)
    sys.stdout.flush()

    uvicorn.run("metis_app.api_litestar.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
