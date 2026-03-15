"""CLI launcher for the local Axiom FastAPI app."""

from __future__ import annotations

import os
import socket
import sys

import uvicorn


def _find_free_port(host: str) -> int:
    """Bind to port 0 and let the OS assign a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def main() -> None:
    host = os.getenv("AXIOM_API_HOST", "127.0.0.1")
    port_env = os.getenv("AXIOM_API_PORT")
    port = int(port_env) if port_env else _find_free_port(host)

    # Print the negotiated URL so the Tauri host can read it from stdout.
    print(f"AXIOM_API_LISTENING=http://{host}:{port}", flush=True)
    sys.stdout.flush()

    uvicorn.run("axiom_app.api.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
