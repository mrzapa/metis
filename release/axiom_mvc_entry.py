"""PyInstaller entry point for the Axiom MVC desktop app.

This launcher guarantees the packaged executable always boots the new
MVC implementation rather than the legacy monolith branch.
"""

from __future__ import annotations

import os

from main import main


if __name__ == "__main__":
    os.environ.setdefault("AXIOM_NEW_APP", "1")
    main()
