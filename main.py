"""main.py — Canonical entry point for the Axiom application.

Runs axiom_app.app.run_app() (PySide6 Qt UI) by default.

Automatic CLI fallback — two situations trigger headless mode instead:
  1. ``--cli`` flag is present anywhere in sys.argv.
  2. Qt raises an error at startup (no DISPLAY, headless server, etc.).

Explicit CLI invocations::

    python main.py --cli index --file paper.txt
    python main.py --cli query --file paper.txt --question "..."

Headless automatic fallback::

    python main.py          # -> CLI help if no display
"""

import sys


def _is_display_error(exc: BaseException) -> bool:
    """Return True if *exc* indicates that no graphical display is available."""
    name = type(exc).__name__
    if name == "QtFatalError":
        return True
    msg = str(exc).lower()
    return (
        "no display" in msg
        or "couldn't connect to display" in msg
        or "could not connect to display" in msg
        or "cannot load library" in msg
        or (isinstance(exc, ImportError) and "pyside6" in msg)
    )


def main() -> None:
    if "--cli" in sys.argv:
        cli_argv = [a for a in sys.argv[1:] if a != "--cli"]
        from axiom_app.cli import main as cli_main
        sys.exit(cli_main(cli_argv))

    try:
        from axiom_app.app import run_app
        run_app()
    except Exception as exc:
        if _is_display_error(exc):
            print(
                f"[axiom] GUI unavailable ({exc}).\n"
                "        Falling back to CLI — run with --cli <command> for headless use.\n"
                "        Example:  python main.py --cli index --file doc.txt",
                file=sys.stderr,
            )
            from axiom_app.cli import main as cli_main
            sys.exit(cli_main(sys.argv[1:]))
        else:
            import traceback
            detail = traceback.format_exc()
            print(f"Startup Error: {exc}", file=sys.stderr)
            print(detail, file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
