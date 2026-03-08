"""axiom_app.cli — Headless command-line interface for Axiom."""

from __future__ import annotations

import argparse
import pathlib
import sys
import tempfile
import textwrap
from typing import Sequence

from axiom_app.models.app_model import AppModel
from axiom_app.models.parity_types import SkillSessionState
from axiom_app.services.index_service import load_index_bundle
from axiom_app.services.runtime_resolution import infer_file_types, resolve_runtime_settings
from axiom_app.services.skill_repository import SkillRepository
from axiom_app.services.vector_store import resolve_vector_store

_SEP = "-" * 60
_MAX_QUERY_HITS = 20
_CONTEXT_CHARS = 140


def _safe_write(text: str, stream) -> None:
    try:
        stream.write(text)
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        data = text.encode(encoding, errors="replace")
        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            buffer.write(data)
            buffer.flush()
        else:
            stream.write(data.decode(encoding, errors="replace"))


def _safe_print(*values: object, sep: str = " ", end: str = "\n", file=None) -> None:
    stream = file if file is not None else sys.stdout
    _safe_write(sep.join(str(value) for value in values) + end, stream)


def _load_model() -> AppModel:
    model = AppModel()
    model.load_settings()
    return model


def _build_session_skill_state(args: argparse.Namespace) -> SkillSessionState:
    return SkillSessionState(
        pinned=[str(item).strip() for item in list(getattr(args, "pin_skill", []) or []) if str(item).strip()],
        muted=[str(item).strip() for item in list(getattr(args, "mute_skill", []) or []) if str(item).strip()],
    ).normalized()


def _resolve_query_runtime(model: AppModel, bundle, question: str, args: argparse.Namespace):
    skill_repository = SkillRepository(getattr(model, "skills_dir", None))
    for skill in skill_repository.list_invalid_skills():
        _safe_print(
            f"warning: skipping invalid skill {skill.skill_id}: {'; '.join(skill.errors)}",
            file=sys.stderr,
        )
    return resolve_runtime_settings(
        dict(model.settings),
        enabled_skills=skill_repository.enabled_skills(model.settings),
        session_skill_state=_build_session_skill_state(args),
        query=question,
        file_types=infer_file_types(list(getattr(bundle, "documents", []) or [])),
    )


def cmd_index(args: argparse.Namespace) -> int:
    src = pathlib.Path(args.file)
    if not src.exists():
        _safe_print(f"error: file not found: {src}", file=sys.stderr)
        return 1
    if not src.is_file():
        _safe_print(f"error: not a regular file: {src}", file=sys.stderr)
        return 1

    model = _load_model()
    model.set_documents([str(src)])
    adapter = resolve_vector_store(model.settings)
    available, reason = adapter.is_available(model.settings)
    if not available:
        _safe_print(f"error: vector backend unavailable: {reason}", file=sys.stderr)
        return 1
    try:
        text = src.read_text(encoding="utf-8", errors="replace")
        bundle = adapter.build([str(src)], model.settings)
    except OSError as exc:
        _safe_print(f"error reading {src}: {exc}", file=sys.stderr)
        return 1

    out_path = pathlib.Path(args.out) if args.out else src.with_name(src.name + ".axiom-index")
    try:
        adapter.save(bundle, target_path=out_path)
    except (OSError, ValueError) as exc:
        _safe_print(f"error writing index to {out_path}: {exc}", file=sys.stderr)
        return 1

    _safe_print(f"Indexing : {src}")
    _safe_print(f"  Characters : {len(text):>10,}")
    _safe_print(f"  Words      : {len(text.split()):>10,}")
    _safe_print(f"  Lines      : {len(text.splitlines()):>10,}")
    _safe_print(f"  Paragraphs : {len([p for p in text.split(chr(10) * 2) if p.strip()]):>10,}")
    _safe_print(f"  Chunks     : {len(bundle.chunks):>10,}")
    _safe_print(f"  Index ID   : {bundle.index_id}")
    _safe_print(f"  Backend    : {bundle.vector_backend}")
    _safe_print(f"Index written -> {out_path}")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    src = pathlib.Path(args.file)
    if not src.exists():
        _safe_print(f"error: file not found: {src}", file=sys.stderr)
        return 1
    if not src.is_file():
        _safe_print(f"error: not a regular file: {src}", file=sys.stderr)
        return 1

    question = str(args.question or "").strip()
    if not question:
        _safe_print("error: --question must not be empty", file=sys.stderr)
        return 1

    model = _load_model()
    try:
        if args.index:
            bundle = load_index_bundle(args.index)
            adapter_settings = {
                **model.settings,
                "vector_db_type": str(bundle.vector_backend or model.settings.get("vector_db_type", "json")),
            }
            adapter = resolve_vector_store(adapter_settings)
            available, reason = adapter.is_available(adapter_settings)
            if not available:
                _safe_print(f"error: vector backend unavailable: {reason}", file=sys.stderr)
                return 1
            bundle = adapter.load(args.index)
        else:
            adapter = resolve_vector_store(model.settings)
            available, reason = adapter.is_available(model.settings)
            if not available:
                _safe_print(f"error: vector backend unavailable: {reason}", file=sys.stderr)
                return 1
            bundle = adapter.build([str(src)], model.settings)
            if str(bundle.vector_backend or "json") != "json":
                with tempfile.TemporaryDirectory(prefix="axiom_cli_query_") as temp_dir:
                    manifest_path = adapter.save(bundle, index_dir=temp_dir)
                    bundle = adapter.load(manifest_path)
                    resolved = _resolve_query_runtime(model, bundle, question, args)
                    query_settings = dict(model.settings)
                    query_settings.update(
                        {
                            "selected_mode": resolved.mode,
                            "retrieval_k": resolved.retrieve_k,
                            "top_k": resolved.final_k,
                            "mmr_lambda": resolved.mmr_lambda,
                            "retrieval_mode": resolved.retrieval_mode,
                            "agentic_mode": resolved.agentic_mode,
                            "agentic_max_iterations": resolved.agentic_max_iterations,
                            "output_style": resolved.output_style,
                        }
                    )
                    result = adapter.query(bundle, question, query_settings)
                    return _print_query_result(
                        src,
                        question,
                        bundle,
                        result,
                        resolved=resolved,
                        show_skills=bool(args.show_skills),
                    )
    except OSError as exc:
        _safe_print(f"error reading/building index: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        _safe_print(f"error preparing index: {exc}", file=sys.stderr)
        return 1

    resolved = _resolve_query_runtime(model, bundle, question, args)
    query_settings = dict(model.settings)
    query_settings.update(
        {
            "selected_mode": resolved.mode,
            "retrieval_k": resolved.retrieve_k,
            "top_k": resolved.final_k,
            "mmr_lambda": resolved.mmr_lambda,
            "retrieval_mode": resolved.retrieval_mode,
            "agentic_mode": resolved.agentic_mode,
            "agentic_max_iterations": resolved.agentic_max_iterations,
            "output_style": resolved.output_style,
        }
    )
    result = adapter.query(bundle, question, query_settings)
    return _print_query_result(
        src,
        question,
        bundle,
        result,
        resolved=resolved,
        show_skills=bool(args.show_skills),
    )


def _print_query_result(src: pathlib.Path, question: str, bundle, result, *, resolved, show_skills: bool) -> int:
    _safe_print()
    _safe_print(f"Question : {question}")
    _safe_print(f"Source   : {src}")
    _safe_print(f"Backend  : shared retrieval ({bundle.vector_backend}:{bundle.index_id})")
    _safe_print(f"Mode     : {resolved.mode}")
    if show_skills:
        _safe_print(f"Primary  : {resolved.primary_skill_id or '(none)'}")
        selected = list(getattr(resolved, "selected_skills", []) or [])
        if selected:
            _safe_print("Skills   :")
            for skill in selected:
                _safe_print(f"  - {skill.skill_id}: {skill.reason}")
        else:
            _safe_print("Skills   : none")
    _safe_print()
    _safe_print(_SEP)

    if result.sources:
        for source in result.sources[:_MAX_QUERY_HITS]:
            snippet = source.snippet.strip()[:_CONTEXT_CHARS]
            if len(source.snippet.strip()) > _CONTEXT_CHARS:
                snippet += " ..."
            score = f"{source.score:.3f}" if source.score is not None else "-"
            _safe_print(f"  [{source.sid}] {source.source} (score={score})")
            _safe_print(f"      {snippet}")
        _safe_print(_SEP)
        _safe_print(f"  {len(result.sources)} evidence item(s) returned.")
    else:
        _safe_print("  (no relevant passages found)")
        _safe_print(_SEP)
        wrapped = textwrap.fill(
            "Tip: try broader wording, adjust chunk settings, or build an index first.",
            width=58,
            initial_indent="  ",
            subsequent_indent="  ",
        )
        _safe_print(wrapped)

    _safe_print()
    return 0


def cmd_skills_list(_args: argparse.Namespace) -> int:
    model = _load_model()
    repository = SkillRepository(getattr(model, "skills_dir", None))
    valid = repository.list_valid_skills()
    invalid = repository.list_invalid_skills()
    if not valid and not invalid:
        _safe_print("No skills found.")
        return 0
    for skill in valid:
        enabled = "enabled" if repository.is_globally_enabled(skill, model.settings) else "disabled"
        _safe_print(f"{skill.skill_id}\t{enabled}\tpriority={skill.priority}\t{skill.name}")
    for skill in invalid:
        _safe_print(f"{skill.skill_id}\tinvalid\t{'; '.join(skill.errors)}", file=sys.stderr)
    return 0


def cmd_skills_show(args: argparse.Namespace) -> int:
    model = _load_model()
    repository = SkillRepository(getattr(model, "skills_dir", None))
    skill = repository.get_skill(args.skill_id)
    if skill is None:
        _safe_print(f"error: skill not found: {args.skill_id}", file=sys.stderr)
        return 1
    _safe_print(f"id: {skill.skill_id}")
    _safe_print(f"name: {skill.name}")
    _safe_print(f"description: {skill.description}")
    _safe_print(f"enabled: {repository.is_globally_enabled(skill, model.settings)}")
    _safe_print(f"enabled_by_default: {skill.enabled_by_default}")
    _safe_print(f"priority: {skill.priority}")
    _safe_print(f"path: {skill.path}")
    _safe_print("triggers:")
    for key, values in sorted(dict(skill.triggers or {}).items()):
        _safe_print(f"  {key}: {', '.join(values) if values else '(none)'}")
    _safe_print("runtime_overrides:")
    if skill.runtime_overrides:
        for key, value in sorted(dict(skill.runtime_overrides or {}).items()):
            _safe_print(f"  {key}: {value}")
    else:
        _safe_print("  (none)")
    _safe_print()
    _safe_print(skill.body)
    return 0


def _set_skill_enabled(skill_id: str, enabled: bool) -> int:
    model = _load_model()
    repository = SkillRepository(getattr(model, "skills_dir", None))
    if repository.get_skill(skill_id) is None:
        _safe_print(f"error: skill not found: {skill_id}", file=sys.stderr)
        return 1
    model.save_settings(repository.set_global_enabled(model.settings, skill_id, enabled))
    _safe_print(f"{'enabled' if enabled else 'disabled'}: {skill_id}")
    return 0


def cmd_skills_enable(args: argparse.Namespace) -> int:
    return _set_skill_enabled(str(args.skill_id or "").strip(), True)


def cmd_skills_disable(args: argparse.Namespace) -> int:
    return _set_skill_enabled(str(args.skill_id or "").strip(), False)


def cmd_skills_lint(_args: argparse.Namespace) -> int:
    model = _load_model()
    repository = SkillRepository(getattr(model, "skills_dir", None))
    errors = repository.lint_errors()
    if not errors:
        _safe_print("OK")
        return 0
    for error in errors:
        _safe_print(error, file=sys.stderr)
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="axiom",
        description="Axiom CLI — headless document indexing, querying, and skill management.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """\
            examples:
              python main.py --cli index --file paper.txt
              python main.py --cli query --file paper.txt --question "main contribution" --show-skills
              python -m axiom_app.cli skills list
              python -m axiom_app.cli skills enable research-claims
            """
        ),
    )
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    sub.required = True

    p_index = sub.add_parser("index", help="Index a document file.")
    p_index.add_argument("--file", "-f", required=True, metavar="PATH", help="Path to the document to index.")
    p_index.add_argument(
        "--out",
        "-o",
        default=None,
        metavar="PATH",
        help="Output directory or manifest path for the persisted index (default: <file>.axiom-index).",
    )

    p_query = sub.add_parser("query", help="Query a document.")
    p_query.add_argument("--file", "-f", required=True, metavar="PATH", help="Path to the document to search.")
    p_query.add_argument("--question", "-q", required=True, metavar="TEXT", help="Question or keywords to search for.")
    p_query.add_argument(
        "--index",
        default=None,
        metavar="PATH",
        help="Optional path to a previously built index directory, manifest, or legacy JSON bundle.",
    )
    p_query.add_argument(
        "--pin-skill",
        action="append",
        default=[],
        metavar="SKILL_ID",
        help="Force-include a skill for this query.",
    )
    p_query.add_argument(
        "--mute-skill",
        action="append",
        default=[],
        metavar="SKILL_ID",
        help="Exclude a skill for this query unless it is pinned.",
    )
    p_query.add_argument(
        "--show-skills",
        action="store_true",
        help="Show the selected skills and match reasons before query output.",
    )

    p_skills = sub.add_parser("skills", help="Manage repo-local skills.")
    skills_sub = p_skills.add_subparsers(dest="skills_command", metavar="<skills-command>")
    skills_sub.required = True

    skills_sub.add_parser("list", help="List valid skills and their enable state.")

    p_show = skills_sub.add_parser("show", help="Show a skill definition.")
    p_show.add_argument("skill_id", metavar="SKILL_ID")

    p_enable = skills_sub.add_parser("enable", help="Enable a skill globally.")
    p_enable.add_argument("skill_id", metavar="SKILL_ID")

    p_disable = skills_sub.add_parser("disable", help="Disable a skill globally.")
    p_disable.add_argument("skill_id", metavar="SKILL_ID")

    skills_sub.add_parser("lint", help="Validate all skill files and fail on malformed frontmatter.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "index":
            return cmd_index(args)
        if args.command == "query":
            return cmd_query(args)
        if args.command == "skills":
            if args.skills_command == "list":
                return cmd_skills_list(args)
            if args.skills_command == "show":
                return cmd_skills_show(args)
            if args.skills_command == "enable":
                return cmd_skills_enable(args)
            if args.skills_command == "disable":
                return cmd_skills_disable(args)
            if args.skills_command == "lint":
                return cmd_skills_lint(args)
        parser.print_help()
        return 1
    except Exception as exc:  # noqa: BLE001
        _safe_print(f"internal error: {exc}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
