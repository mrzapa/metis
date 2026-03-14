"""CLI launcher for the local Axiom FastAPI app."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    host = os.getenv("AXIOM_API_HOST", "127.0.0.1")
    port = int(os.getenv("AXIOM_API_PORT", "8000"))
    uvicorn.run("axiom_app.api.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
