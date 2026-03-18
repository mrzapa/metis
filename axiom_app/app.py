"""axiom_app.app — Application bootstrap.

Entry point for the Axiom application.  Initialises logging and starts the
FastAPI web server.  The primary interface is the Tauri + Next.js web
application in ``apps/axiom-web/``.  The legacy PySide6 desktop interface
has been removed.

Usage::

    python main.py

Or directly::

    python -m axiom_app.app
"""

from __future__ import annotations

import pathlib
import sys
import traceback
import webbrowser

from axiom_app.utils.logging_setup import setup_logging

# Log directory relative to the repo root (parent of the axiom_app package).
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent

# Default host/port for the development web server.
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8000


def _enable_windows_dpi_awareness(platform_name: str | None = None, ctypes_module=None) -> bool:
    """Best-effort Windows DPI awareness bootstrap."""
    platform_name = platform_name or sys.platform
    if platform_name != "win32":
        return False
    try:
        ctypes_module = ctypes_module or __import__("ctypes")
        user32 = getattr(getattr(ctypes_module, "windll", None), "user32", None)
        shcore = getattr(getattr(ctypes_module, "windll", None), "shcore", None)
        if user32 is not None and hasattr(user32, "SetProcessDpiAwarenessContext"):
            # PER_MONITOR_AWARE_V2
            if user32.SetProcessDpiAwarenessContext(-4):
                return True
        if shcore is not None and hasattr(shcore, "SetProcessDpiAwareness"):
            shcore.SetProcessDpiAwareness(2)
            return True
        if user32 is not None and hasattr(user32, "SetProcessDPIAware"):
            user32.SetProcessDPIAware()
            return True
    except Exception:
        return False
    return False


def run_app(
    host: str = _DEFAULT_HOST,
    port: int = _DEFAULT_PORT,
    *,
    open_browser: bool = True,
) -> None:
    """Initialise logging and start the Axiom API + web server."""

    # ── 1. Logging — must be first ────────────────────────────────────
    _default_log_dir = _REPO_ROOT / "logs"
    logger = setup_logging(_default_log_dir, level="DEBUG")
    logger.info("Log file: %s", (_default_log_dir / "axiom.log").resolve())
    logger.info("=" * 60)
    logger.info("Axiom starting up (web mode)")

    try:
        import uvicorn  # type: ignore[import-untyped]

        from axiom_app.api.app import app as fastapi_app

        url = f"http://{host}:{port}"
        logger.info("Starting API server at %s", url)

        if open_browser:
            import threading

            def _open() -> None:
                import time
                time.sleep(1.5)
                webbrowser.open(url)

            threading.Thread(target=_open, daemon=True).start()

        uvicorn.run(fastapi_app, host=host, port=port, log_level="info")

    except Exception as exc:
        detail = traceback.format_exc()
        concise = f"Startup Error: {exc}"
        logger.critical("Fatal startup error: %s", exc, exc_info=True)
        print(concise, file=sys.stderr)
        print(detail, file=sys.stderr)
        sys.exit(1)

    finally:
        logger.info("Axiom process ending")
        logger.info("=" * 60)


if __name__ == "__main__":
    run_app()
