"""main.py — Canonical entry point for the Axiom application.

Default behaviour (AXIOM_NEW_APP unset or 1):
  Runs axiom_app.app.run_app() (tabbed Tk UI).

Legacy GUI fallback (explicit opt-out via AXIOM_NEW_APP=0):
  Delegates to agentic_rag_gui so that ``AXIOM_NEW_APP=0 python main.py`` is
  identical to ``python agentic_rag_gui.py``.

  Automatic CLI fallback — two situations trigger headless mode instead:
    1. ``--cli`` flag is present anywhere in sys.argv.
    2. Tk raises TclError at startup (no DISPLAY, headless server, etc.).

  Explicit CLI invocations::

      AXIOM_NEW_APP=1 python main.py --cli index --file paper.txt
      AXIOM_NEW_APP=1 python main.py --cli query --file paper.txt --question "..."

  Headless automatic fallback::

      AXIOM_NEW_APP=1 python main.py          # → CLI help if no display

Runtime path:
  TODO: add CLI argument parsing here (--smoke, --profile, --theme …)
        so agentic_rag_gui.py no longer needs to inspect sys.argv directly.

  TODO: set up logging configuration before handing off to the app bootstrap.
"""

import os
import sys


def _is_display_error(exc: BaseException) -> bool:
    """Return True if *exc* indicates that no graphical display is available."""
    # TclError is the canonical Tk error; we match by name to avoid importing
    # tkinter at the top level (it may not be installed on headless servers).
    if type(exc).__name__ == "TclError":
        return True
    msg = str(exc).lower()
    return (
        "no display" in msg
        or "couldn't connect to display" in msg
        or "can't find a usable init.tcl" in msg
        or (isinstance(exc, ImportError) and "tkinter" in msg)
    )


def main() -> None:
    if os.environ.get("AXIOM_NEW_APP", "1").strip() != "0":
        # -----------------------------------------------------------------------
        # New MVC app (default path; AXIOM_NEW_APP=0 opts out to legacy)
        # -----------------------------------------------------------------------
        if "--cli" in sys.argv:
            # Explicit CLI mode: strip the --cli sentinel and hand the rest
            # directly to axiom_app.cli.main() so it sees clean argv.
            cli_argv = [a for a in sys.argv[1:] if a != "--cli"]
            from axiom_app.cli import main as cli_main
            sys.exit(cli_main(cli_argv))

        # GUI mode with automatic CLI fallback on display errors.
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
                # Pass whatever the user originally gave (minus the program
                # name); if no sub-command was given, the CLI will print help.
                sys.exit(cli_main(sys.argv[1:]))
            else:
                import traceback
                detail = traceback.format_exc()
                print(f"Startup Error: {exc}", file=sys.stderr)
                print(detail, file=sys.stderr)
                sys.exit(1)
    else:
        # -----------------------------------------------------------------------
        # Legacy path: run the monolithic app unchanged.
        # -----------------------------------------------------------------------
        # Import triggers module-level setup in agentic_rag_gui (UI backend
        # detection, constant definitions) exactly as if the file were run directly.
        import agentic_rag_gui  # noqa: F401  (imported for side-effects / __main__ block)

        # agentic_rag_gui uses `if __name__ == "__main__"` to start the Tk loop.
        # We replicate that logic here so `python main.py` works the same way.
        import tkinter as tk
        import traceback
        from tkinter import messagebox

        from agentic_rag_gui import AgenticRAGApp

        try:
            root = tk.Tk()
            # Hide window while UI builds to avoid a blank flash (mirrors
            # the behaviour in agentic_rag_gui.__main__).
            root.withdraw()
            app = AgenticRAGApp(root)  # noqa: F841
            root.mainloop()
        except Exception as exc:
            detail = traceback.format_exc()
            concise = f"Startup Error: {exc}"
            print(concise, file=sys.stderr)
            print(detail, file=sys.stderr)
            try:
                messagebox.showerror(
                    "Startup Error",
                    f"{concise}\n\nDetails have been written to stderr.",
                )
            except Exception:
                pass


if __name__ == "__main__":
    main()
