"""axiom_app.cli — Headless command-line interface for Axiom.

Provides ``index`` and ``query`` sub-commands that operate without any
Tk/GUI dependency, making them usable in headless environments (CI, SSH,
Docker, no-display servers) while reusing the same shared indexing and
retrieval backends as the MVC app.

Usage
-----
Index a document::

    python main.py --cli index --file README.md
    python main.py --cli index --file paper.txt --out paper.axiom-index

Query a document::

    python main.py --cli query --file README.md --question "how to install"
    python main.py --cli query --file paper.txt --question "neural network"

Or invoke the module directly::

    python -m axiom_app.cli index --file README.md
    python -m axiom_app.cli query --file paper.txt --question "attention"

Exit codes
----------
0 — success
1 — user error (file not found, missing argument, …)
2 — unexpected internal error
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import tempfile
import textwrap
from typing import Sequence

from axiom_app.models.app_model import AppModel
from axiom_app.services.index_service import load_index_bundle
from axiom_app.services.vector_store import resolve_vector_store

# ── constants ────────────────────────────────────────────────────────────────

_SEP = "─" * 60
_MAX_QUERY_HITS = 20          # cap displayed keyword matches
_CONTEXT_CHARS  = 140         # chars shown per matching line
_SNIPPET_CHARS  = 300         # chars in index summary snippet


# ── sub-command implementations ──────────────────────────────────────────────


def cmd_index(args: argparse.Namespace) -> int:
    """Build and persist an index using the shared MVC backend."""
    src = pathlib.Path(args.file)
    if not src.exists():
        print(f"error: file not found: {src}", file=sys.stderr)
        return 1
    if not src.is_file():
        print(f"error: not a regular file: {src}", file=sys.stderr)
        return 1

    model = AppModel()
    model.load_settings()
    model.set_documents([str(src)])
    adapter = resolve_vector_store(model.settings)
    available, reason = adapter.is_available(model.settings)
    if not available:
        print(f"error: vector backend unavailable: {reason}", file=sys.stderr)
        return 1
    try:
        text = src.read_text(encoding="utf-8", errors="replace")
        bundle = adapter.build([str(src)], model.settings)
    except OSError as exc:
        print(f"error reading {src}: {exc}", file=sys.stderr)
        return 1

    out_path: pathlib.Path
    if args.out:
        out_path = pathlib.Path(args.out)
    else:
        out_path = src.with_name(src.name + ".axiom-index")

    try:
        adapter.save(bundle, target_path=out_path)
    except (OSError, ValueError) as exc:
        print(f"error writing index to {out_path}: {exc}", file=sys.stderr)
        return 1

    char_count  = len(text)
    word_count  = len(text.split())
    line_count  = len(text.splitlines())
    para_count  = len([p for p in text.split("\n\n") if p.strip()])

    print(f"Indexing : {src}")
    print(f"  Characters : {char_count:>10,}")
    print(f"  Words      : {word_count:>10,}")
    print(f"  Lines      : {line_count:>10,}")
    print(f"  Paragraphs : {para_count:>10,}")
    print(f"  Chunks     : {len(bundle.chunks):>10,}")
    print(f"  Index ID   : {bundle.index_id}")
    print(f"  Backend    : {bundle.vector_backend}")
    print(f"Index written → {out_path}")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    """Query a saved index or build one in memory from the source file."""
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

    model = AppModel()
    model.load_settings()

    try:
        if args.index:
            bundle = load_index_bundle(args.index)
            adapter = resolve_vector_store(
                {**model.settings, "vector_db_type": str(bundle.vector_backend or model.settings.get("vector_db_type", "json"))}
            )
            available, reason = adapter.is_available(
                {**model.settings, "vector_db_type": str(bundle.vector_backend or model.settings.get("vector_db_type", "json"))}
            )
            if not available:
                print(f"error: vector backend unavailable: {reason}", file=sys.stderr)
                return 1
            bundle = adapter.load(args.index)
        else:
            adapter = resolve_vector_store(model.settings)
            available, reason = adapter.is_available(model.settings)
            if not available:
                print(f"error: vector backend unavailable: {reason}", file=sys.stderr)
                return 1
            bundle = adapter.build([str(src)], model.settings)
            if str(bundle.vector_backend or "json") != "json":
                with tempfile.TemporaryDirectory(prefix="axiom_cli_query_") as temp_dir:
                    manifest_path = adapter.save(bundle, index_dir=temp_dir)
                    bundle = adapter.load(manifest_path)
                    result = adapter.query(bundle, question, model.settings)
                    return _print_query_result(src, question, bundle, result)
    except OSError as exc:
        print(f"error reading/building index: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error preparing index: {exc}", file=sys.stderr)
        return 1

    result = adapter.query(bundle, question, model.settings)
    return _print_query_result(src, question, bundle, result)


def _print_query_result(src: pathlib.Path, question: str, bundle, result) -> int:
    """Render a query result consistently for both saved and transient indexes."""

    print()
    print(f"Question : {question}")
    print(f"Source   : {src}")
    print(f"Backend  : shared retrieval ({bundle.vector_backend}:{bundle.index_id})")
    print()
    print(_SEP)

    if result.sources:
        for source in result.sources[:_MAX_QUERY_HITS]:
            snippet = source.snippet.strip()[:_CONTEXT_CHARS]
            if len(source.snippet.strip()) > _CONTEXT_CHARS:
                snippet += " …"
            score = f"{source.score:.3f}" if source.score is not None else "-"
            print(
                f"  [{source.sid}] {source.source} "
                f"(score={score})"
            )
            print(f"      {snippet}")
        print(_SEP)
        print(f"  {len(result.sources)} evidence item(s) returned.")
    else:
        print("  (no relevant passages found)")
        print(_SEP)
        wrapped = textwrap.fill(
            "Tip: try broader wording, adjust chunk settings, or build an index first.",
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
              python main.py --cli index --file paper.txt --out paper.axiom-index
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
        help="Output directory or manifest path for the persisted index (default: <file>.axiom-index).",
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
    p_query.add_argument(
        "--index",
        default=None,
        metavar="PATH",
        help="Optional path to a previously built index directory, manifest, or legacy JSON bundle.",
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
