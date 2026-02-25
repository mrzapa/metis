"""axiom_app.cli — Headless command-line interface for Axiom.

Provides ``index`` and ``query`` sub-commands that operate without any
Tk/GUI dependency, making them usable in headless environments (CI, SSH,
Docker, no-display servers).

Usage
-----
Index a document::

    python main.py --cli index --file README.md
    python main.py --cli index --file paper.txt --out paper.axiom-index.json

Query a document (keyword match; no LLM required)::

    python main.py --cli query --file README.md --question "how to install"
    python main.py --cli query --file paper.txt --question "neural network"

Or invoke the module directly::

    python -m axiom_app.cli index --file README.md
    python -m axiom_app.cli query --file paper.txt --question "attention"

Backends
--------
Both commands use only stdlib and ``axiom_app.models.AppModel``.  When a
full LLM/embedding stack is configured in future, ``cmd_query`` will
delegate to it automatically; for now it performs a case-insensitive
keyword search and returns matching lines with surrounding context.

Exit codes
----------
0 — success
1 — user error (file not found, missing argument, …)
2 — unexpected internal error
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import textwrap
from typing import Sequence

from axiom_app.models.app_model import AppModel

# ── constants ────────────────────────────────────────────────────────────────

_SEP = "─" * 60
_MAX_QUERY_HITS = 20          # cap displayed keyword matches
_CONTEXT_CHARS  = 140         # chars shown per matching line
_SNIPPET_CHARS  = 300         # chars in index summary snippet


# ── sub-command implementations ──────────────────────────────────────────────


def cmd_index(args: argparse.Namespace) -> int:
    """Read *args.file*, compute basic statistics, write a JSON index stub."""
    src = pathlib.Path(args.file)
    if not src.exists():
        print(f"error: file not found: {src}", file=sys.stderr)
        return 1
    if not src.is_file():
        print(f"error: not a regular file: {src}", file=sys.stderr)
        return 1

    try:
        text = src.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"error reading {src}: {exc}", file=sys.stderr)
        return 1

    # ── statistics ───────────────────────────────────────────────────
    char_count  = len(text)
    word_count  = len(text.split())
    line_count  = len(text.splitlines())
    para_count  = len([p for p in text.split("\n\n") if p.strip()])

    # ── model bookkeeping ────────────────────────────────────────────
    model = AppModel()
    model.load_settings()
    model.set_documents([str(src)])

    # ── write index stub ─────────────────────────────────────────────
    out_path: pathlib.Path
    if args.out:
        out_path = pathlib.Path(args.out)
    else:
        out_path = src.with_name(src.name + ".axiom-index.json")

    index_payload: dict = {
        "source":     str(src.resolve()),
        "characters": char_count,
        "words":      word_count,
        "lines":      line_count,
        "paragraphs": para_count,
        "snippet":    text[:_SNIPPET_CHARS].replace("\n", " "),
        "status":     model.get_status_snapshot(),
        "_note":      (
            "Index stub — full vector index not yet implemented. "
            "Replace this file with a real embedding store once the "
            "LLM backend is wired in."
        ),
    }

    try:
        out_path.write_text(json.dumps(index_payload, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"error writing index to {out_path}: {exc}", file=sys.stderr)
        return 1

    # ── stdout report ────────────────────────────────────────────────
    print(f"Indexing : {src}")
    print(f"  Characters : {char_count:>10,}")
    print(f"  Words      : {word_count:>10,}")
    print(f"  Lines      : {line_count:>10,}")
    print(f"  Paragraphs : {para_count:>10,}")
    print(f"Index written → {out_path}")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    """Search *args.file* for lines relevant to *args.question*.

    Currently performs a plain keyword match.  When a full LLM/embedding
    stack is available it will be used instead and this note will be removed.
    """
    src = pathlib.Path(args.file)
    if not src.exists():
        print(f"error: file not found: {src}", file=sys.stderr)
        return 1
    if not src.is_file():
        print(f"error: not a regular file: {src}", file=sys.stderr)
        return 1

    question = args.question.strip()
    if not question:
        print("error: --question must not be empty", file=sys.stderr)
        return 1

    try:
        text = src.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"error reading {src}: {exc}", file=sys.stderr)
        return 1

    keywords = [kw for kw in question.lower().split() if len(kw) > 2]
    if not keywords:
        keywords = question.lower().split()  # fallback: use all tokens

    lines = text.splitlines()
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(lines, start=1):
        lc = line.lower()
        if any(kw in lc for kw in keywords):
            hits.append((lineno, line))

    # ── output ───────────────────────────────────────────────────────
    print()
    print(f"Question : {question}")
    print(f"Source   : {src}")
    print(f"Backend  : keyword match (no LLM configured)")
    print()
    print(_SEP)

    if hits:
        shown = hits[:_MAX_QUERY_HITS]
        for lineno, line in shown:
            clipped = line.strip()[:_CONTEXT_CHARS]
            if len(line.strip()) > _CONTEXT_CHARS:
                clipped += " …"
            print(f"  [line {lineno:5d}]  {clipped}")
        print(_SEP)
        total = len(hits)
        note  = f", showing first {_MAX_QUERY_HITS}" if total > _MAX_QUERY_HITS else ""
        print(f"  {total} match(es) found{note}.")
    else:
        print("  (no keyword matches found)")
        print(_SEP)
        wrapped = textwrap.fill(
            "Tip: try broader keywords, or configure an LLM backend for "
            "semantic search.",
            width=58,
            initial_indent="  ",
            subsequent_indent="  ",
        )
        print(wrapped)

    print()
    return 0


# ── argument parser ───────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="axiom",
        description="Axiom CLI — headless document indexing and querying.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            examples:
              python main.py --cli index --file paper.txt
              python main.py --cli index --file paper.txt --out paper.json
              python main.py --cli query --file paper.txt --question "main contribution"
              python -m axiom_app.cli query --file README.md --question "install"
        """),
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    # index
    p_index = sub.add_parser("index", help="Index a document file.")
    p_index.add_argument(
        "--file", "-f",
        required=True,
        metavar="PATH",
        help="Path to the document to index.",
    )
    p_index.add_argument(
        "--out", "-o",
        default=None,
        metavar="PATH",
        help="Output path for the index JSON (default: <file>.axiom-index.json).",
    )

    # query
    p_query = sub.add_parser("query", help="Query a document.")
    p_query.add_argument(
        "--file", "-f",
        required=True,
        metavar="PATH",
        help="Path to the document to search.",
    )
    p_query.add_argument(
        "--question", "-q",
        required=True,
        metavar="TEXT",
        help="Question or keywords to search for.",
    )

    return parser


# ── public entry point ────────────────────────────────────────────────────────


def main(argv: Sequence[str] | None = None) -> int:
    """Parse *argv* (or ``sys.argv[1:]``) and dispatch to the matching command.

    Returns an integer exit code (0 = success, 1 = user error, 2 = internal).
    main.py passes filtered argv so callers never need to strip ``--cli``
    before calling here.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "index":
            return cmd_index(args)
        if args.command == "query":
            return cmd_query(args)
        # unreachable — argparse enforces sub.required=True
        parser.print_help()
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"internal error: {exc}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
