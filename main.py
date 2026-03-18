"""main.py — Canonical entry point for the Axiom application.

Starts the Axiom API server (FastAPI + uvicorn) and opens the web interface
in the default browser.  The primary interface is Tauri + Next.js located in
``apps/axiom-web/``.

Headless CLI mode::

    python main.py --cli index --file paper.txt
    python main.py --cli query --file paper.txt --question "..."
"""

import sys


def main() -> None:
    if "--cli" in sys.argv:
        cli_argv = [a for a in sys.argv[1:] if a != "--cli"]
        from axiom_app.cli import main as cli_main
        sys.exit(cli_main(cli_argv))

    try:
        from axiom_app.app import run_app
        run_app()
    except Exception as exc:
        import traceback
        detail = traceback.format_exc()
        print(f"Startup Error: {exc}", file=sys.stderr)
        print(detail, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
