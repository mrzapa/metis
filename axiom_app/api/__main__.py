"""CLI launcher for the local Axiom FastAPI app.

Concurrency notes:
  - Uses a lock file to ensure only one instance runs at a time.
  - The lock is released when the process exits (normally or via signal).
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
_LOCK_FILE = _REPO_ROOT / ".axiom_api.lock"


def _find_free_port(host: str) -> int:
    """Bind to port 0 and let the OS assign a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def _acquire_lock() -> bool:
    """Acquire single-instance lock. Returns True if acquired, False if already held."""
    try:
        if _LOCK_FILE.exists():
            old_pid = _LOCK_FILE.read_text().strip()
            try:
                old_pid_int = int(old_pid)
                os.kill(old_pid_int, 0)
                return False
            except (ValueError, ProcessLookupError):
                pass
        _LOCK_FILE.write_text(str(os.getpid()))
        return True
    except OSError:
        return False


def _release_lock() -> None:
    """Release the single-instance lock."""
    try:
        if _LOCK_FILE.exists() and _LOCK_FILE.read_text().strip() == str(os.getpid()):
            _LOCK_FILE.unlink()
    except OSError:
        pass


def main() -> None:
    if not _acquire_lock():
        print(
            "ERROR: Another Axiom API instance is already running.\n"
            f"       Lock file: {_LOCK_FILE}\n"
            "       Stop the existing instance or remove the lock file to proceed.",
            file=sys.stderr,
        )
        sys.exit(1)

    atexit.register(_release_lock)

    host = os.getenv("AXIOM_API_HOST", "127.0.0.1")
    port_env = os.getenv("AXIOM_API_PORT")
    port = int(port_env) if port_env else _find_free_port(host)

    print(f"AXIOM_API_LISTENING=http://{host}:{port}", flush=True)
    sys.stdout.flush()

    uvicorn.run("axiom_app.api.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
