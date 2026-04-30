"""Forge candidate-skill review service (M14 Phase 5).

The Seedling's overnight reflection populates ``skill_candidates.db``
via :meth:`SkillRepository.save_candidate` whenever a high-convergence
agentic run looks like a generalisable skill pattern. Phase 5 surfaces
those candidates in the Forge gallery's *Candidate skills* section so
the user can review, name, and accept (or dismiss) each one — instead
of relying solely on the ``_promote_skill_candidates`` LLM-judge path
that already exists for the autonomous backend reflection.

Phase 5 contract:

* **Read-only with respect to ``trace_json``.** The service never
  parses or executes anything inside the trace; it only surfaces a
  short excerpt for context. ADR 0014's "no untrusted code from
  papers" boundary applies equally to "no untrusted code from
  traces".
* **Accept writes a ``parse_skill_file``-valid ``SKILL.md`` draft.**
  All four trigger axes are emitted as empty lists; the user fills
  in the relevant ones once the skill has been exercised manually.
  ``enabled_by_default: false`` is hard-coded — instead, the accept
  handler flips ``settings["skills"]["enabled"][slug] = true`` via
  the injected ``settings_writer`` so the override path turns the
  skill on.
* **Reject is final-but-soft.** ``mark_candidate_rejected`` flips
  both ``promoted = 1`` and ``rejected = 1``; the row stays in the
  database for audit but never resurfaces in the review pane.
"""

from __future__ import annotations

import json
import logging
import pathlib
import re
from typing import Any, Callable

from metis_app.services.skill_repository import SkillRepository

log = logging.getLogger(__name__)

SettingsWriter = Callable[[dict[str, Any]], None]

# Slug regex matches the rules ``parse_skill_file`` consumers
# enforce: lowercase, alphanumeric + hyphen, no leading/trailing
# hyphens, no consecutive hyphens.
_SLUG_KEEP = re.compile(r"[^a-z0-9]+")
_SLUG_DEDUP = re.compile(r"-+")
_SLUG_DEFAULT_WORD_COUNT = 7


def default_slug_for_query(query_text: str) -> str:
    """Derive a URL-safe slug from the originating query.

    Takes the first ~7 word-tokens to keep the slug readable and
    short enough to fit in a folder name. Empty / all-punctuation
    inputs fall back to a ``candidate-<sha>`` style placeholder so
    the user always sees *some* draft path; they can rename via
    ``slug_override`` before commit.
    """
    cleaned = (query_text or "").strip().lower()
    tokens = re.findall(r"[a-z0-9]+", cleaned)
    if tokens:
        slug = "-".join(tokens[:_SLUG_DEFAULT_WORD_COUNT])
        slug = _SLUG_DEDUP.sub("-", slug).strip("-")
        if slug:
            return slug
    # Falling back to a content-derived hash keeps the placeholder
    # stable across reloads — important so the user editing the
    # name doesn't lose context. ``hash()`` would change between
    # processes; ``sha256`` doesn't.
    import hashlib

    digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:8]
    return f"candidate-{digest}"


def _trace_excerpt(trace_json: str, *, max_chars: int = 240) -> str:
    """Render a short, human-readable excerpt of the trace.

    The trace is opaque JSON the producer side wrote; we just
    pretty-print the top-level keys + truncate. Errors collapse to
    the original string so a parse problem here never breaks the
    review pane.
    """
    raw = (trace_json or "").strip()
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw[:max_chars]
    if not isinstance(parsed, dict):
        return raw[:max_chars]
    bits = [f"{key}: {value!r}" for key, value in parsed.items()]
    excerpt = " · ".join(bits)
    if len(excerpt) > max_chars:
        excerpt = excerpt[: max_chars - 1] + "…"
    return excerpt


def list_pending_candidates(
    *,
    db_path: pathlib.Path,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return un-promoted, un-rejected candidates with the
    metadata the review pane needs (default slug, trace excerpt).

    Ordered by convergence score descending so the strongest
    patterns surface first.
    """
    repo = SkillRepository(skills_dir=None)
    rows = repo.list_candidates(db_path=db_path, limit=limit)
    out: list[dict[str, Any]] = []
    for row in rows:
        query_text = str(row.get("query_text") or "")
        out.append(
            {
                "id": int(row["id"]),
                "query_text": query_text,
                "convergence_score": float(row["convergence_score"]),
                "created_at": float(row["created_at"]),
                "default_slug": default_slug_for_query(query_text),
                "trace_excerpt": _trace_excerpt(str(row.get("trace_json") or "")),
            }
        )
    return out


def _get_candidate_row(
    *,
    db_path: pathlib.Path,
    candidate_id: int,
) -> dict[str, Any] | None:
    """Direct lookup by id — the public ``list_candidates`` filters
    out promoted rows, so we read raw to support accept-on-not-yet-
    promoted-but-found cases."""

    repo = SkillRepository(skills_dir=None)
    conn = repo._init_candidates_db(db_path)  # noqa: SLF001 — internal seam
    try:
        row = conn.execute(
            "SELECT id, query_text, trace_json, convergence_score, created_at, "
            "promoted, rejected FROM skill_candidates WHERE id = ?",
            (candidate_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    return {
        "id": row[0],
        "query_text": row[1],
        "trace_json": row[2],
        "convergence_score": row[3],
        "created_at": row[4],
        "promoted": int(row[5]),
        "rejected": int(row[6]),
    }


_PARSE_SKILL_FILE_FRONTMATTER_TEMPLATE = (
    "---\n"
    "id: {slug}\n"
    "name: {name}\n"
    "description: {description}\n"
    "enabled_by_default: false\n"
    "priority: 60\n"
    "triggers:\n"
    "  keywords: []\n"
    "  modes: []\n"
    "  file_types: []\n"
    "  output_styles: []\n"
    "runtime_overrides: {{}}\n"
    "---\n"
)


def _format_skill_draft(
    *,
    slug: str,
    name: str,
    description: str,
    candidate: dict[str, Any],
) -> str:
    frontmatter = _PARSE_SKILL_FILE_FRONTMATTER_TEMPLATE.format(
        slug=slug,
        name=_yaml_escape(name),
        description=_yaml_escape(description),
    )
    body = (
        f"# {name}\n\n"
        "> **Phase 5 candidate skill.** Promoted from a "
        "high-convergence agentic trace the seedling captured. "
        "The user reviewed and accepted; "
        "`enabled_by_default: false` plus the explicit "
        "`settings.skills.enabled` flip together mean this skill is "
        "ON for the current user but stays opt-in for others.\n\n"
        "## Originating query\n\n"
        f"> {candidate.get('query_text', '').strip()}\n\n"
        "## Convergence score\n\n"
        f"{float(candidate.get('convergence_score', 0.0)):.2f}\n\n"
        "## Trace excerpt\n\n"
        f"{_trace_excerpt(str(candidate.get('trace_json') or ''))}\n\n"
        "## Notes for the user\n\n"
        "Fill in `runtime_overrides` once you've confirmed which "
        "engine settings the skill should bias. Add the relevant "
        "`triggers.keywords`, `modes`, `file_types`, and "
        "`output_styles` so the skill auto-activates in the right "
        "contexts.\n"
    )
    return frontmatter + "\n" + body


def _yaml_escape(value: str) -> str:
    if value == "":
        return '""'
    if any(ch in value for ch in ":#&*!|>'%@`?\n"):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def accept_candidate(
    *,
    candidates_db: pathlib.Path,
    candidate_id: int,
    skills_root: pathlib.Path,
    settings_writer: SettingsWriter,
    slug_override: str | None = None,
) -> dict[str, Any]:
    """Promote a candidate into a real skill draft + activate it.

    Steps (in order):

    1. Look up the candidate by id; raise ``LookupError`` if missing
       so the route can surface a 404.
    2. Compute the slug (``slug_override`` if provided, else
       :func:`default_slug_for_query`). Slugs are URL-safe.
    3. Refuse to overwrite an existing ``skills/<slug>/SKILL.md``
       (raises ``FileExistsError`` → route translates to 409).
    4. Write the skill draft (``parse_skill_file``-valid frontmatter
       per the round-trip test in ``test_forge_candidates.py``).
    5. Call ``settings_writer({"skills": {"enabled": {slug: True}}})``
       so the runtime turns the skill on; the writer is injected so
       callers can route the update through the existing
       ``/v1/settings`` endpoint or test fixtures.
    6. Mark the candidate row promoted via the existing repo helper.

    Returns ``{slug, skill_path, candidate_id, name, description}``
    so the route can surface the file path back to the frontend
    deep-link.
    """
    candidate = _get_candidate_row(db_path=candidates_db, candidate_id=candidate_id)
    if candidate is None:
        raise LookupError(f"unknown candidate {candidate_id}")

    raw_slug = slug_override or candidate["query_text"]
    slug = default_slug_for_query(raw_slug)
    if not slug:
        raise ValueError(
            f"could not derive slug from {raw_slug!r}; pick a different name"
        )

    skill_dir = skills_root / slug
    skill_path = skill_dir / "SKILL.md"
    if skill_path.exists():
        raise FileExistsError(f"skill draft already exists at {skill_path}")
    skill_dir.mkdir(parents=True, exist_ok=True)

    # Use the originating query as the human-readable name unless
    # the caller provided an override (which we slugified above
    # for the path; we keep the original casing for display).
    display_name = (slug_override or candidate["query_text"]).strip() or slug
    description = (
        f"Generalised from a high-convergence trace "
        f"(score {float(candidate['convergence_score']):.2f})."
    )

    contents = _format_skill_draft(
        slug=slug,
        name=display_name,
        description=description,
        candidate=candidate,
    )
    skill_path.write_text(contents, encoding="utf-8")

    # Flip the settings override so the runtime treats the skill as
    # ON for this user. The writer is responsible for merging this
    # patch into the live settings store; we hand it the minimal
    # diff so the same endpoint that powers Phase 3a's toggle
    # writes can be reused.
    settings_writer(
        {
            "skills": {
                "enabled": {slug: True},
            },
        }
    )

    # Finally, mark the candidate row promoted so the auto-promotion
    # path doesn't re-process it. We keep ``rejected = 0`` because
    # the user accepted, not dismissed.
    repo = SkillRepository(skills_dir=None)
    repo.mark_candidate_promoted(db_path=candidates_db, candidate_id=candidate_id)

    return {
        "slug": slug,
        "skill_path": str(skill_path),
        "candidate_id": candidate_id,
        "name": display_name,
        "description": description,
    }


def reject_candidate(
    *,
    candidates_db: pathlib.Path,
    candidate_id: int,
) -> None:
    """Mark a candidate dismissed. Raises ``LookupError`` for
    unknown ids so the route can surface a 404."""
    candidate = _get_candidate_row(db_path=candidates_db, candidate_id=candidate_id)
    if candidate is None:
        raise LookupError(f"unknown candidate {candidate_id}")
    repo = SkillRepository(skills_dir=None)
    repo.mark_candidate_rejected(db_path=candidates_db, candidate_id=candidate_id)
