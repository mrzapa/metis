"""Forge proposal persistence + skill-draft writer (M14 Phase 4b).

Phase 4a returned absorb-pipeline results in-memory only — the
proposal vanished when the user reloaded the gallery. Phase 4b
persists every successful proposal to ``forge_proposals.db`` so the
review pane can survive a reload, and adds an "accept" handler that
drafts a ``skills/<slug>/SKILL.md`` from the proposal for the user
to review before activation.

ADR 0014's "no untrusted code from papers" boundary still holds:
the accept handler writes a YAML-frontmatter skill draft
(``enabled_by_default: false``, ``runtime_overrides: {}``), never
executable engine code. The user opens the file, edits the
runtime_overrides, and flips it on themselves.

The schema is intentionally separate from
``skill_candidates.db`` (the M06 capture path) — different domain
(URL-driven absorption vs. high-convergence trace capture) and
different fields. The two stores can coexist; a future ADR can
unify them when the use cases overlap more obviously.
"""

from __future__ import annotations

import logging
import pathlib
import re
import sqlite3
import time
from typing import Any

log = logging.getLogger(__name__)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = _REPO_ROOT / "forge_proposals.db"

# Mirrors ``ForgePillar`` in ``forge_registry.py`` — duplicated as a
# constant rather than imported because the proposals module is
# importable from migrations / scripts that should not pull in the
# whole registry stack.
_VALID_PILLARS = frozenset({"cosmos", "companion", "cortex", "cross-cutting"})

# Slug rules match ``test_list_techniques_ids_are_unique_and_url_safe``
# in ``test_api_forge.py``: lowercase, alphanumeric + hyphens, no
# leading/trailing/consecutive hyphens. URL-safe so the same
# ``/forge#<id>`` deep-link contract holds once the user activates
# the drafted skill.
_SLUG_KEEP = re.compile(r"[^a-z0-9]+")
_SLUG_DEDUP = re.compile(r"-+")


def _init_db(db_path: pathlib.Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS forge_proposals (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            source_url      TEXT NOT NULL,
            arxiv_id        TEXT,
            title           TEXT NOT NULL,
            summary         TEXT,
            proposal_name   TEXT NOT NULL,
            proposal_claim  TEXT NOT NULL,
            proposal_pillar TEXT NOT NULL,
            proposal_sketch TEXT NOT NULL,
            status          TEXT NOT NULL DEFAULT 'pending',
            created_at      REAL NOT NULL,
            resolved_at     REAL,
            skill_path      TEXT
        )
    """)
    conn.commit()
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "source_url": row["source_url"],
        "arxiv_id": row["arxiv_id"],
        "title": row["title"],
        "summary": row["summary"],
        "proposal_name": row["proposal_name"],
        "proposal_claim": row["proposal_claim"],
        "proposal_pillar": row["proposal_pillar"],
        "proposal_sketch": row["proposal_sketch"],
        "status": row["status"],
        "created_at": row["created_at"],
        "resolved_at": row["resolved_at"],
        "skill_path": row["skill_path"],
    }


def save_proposal(
    *,
    db_path: pathlib.Path,
    source_url: str,
    arxiv_id: str | None,
    title: str,
    summary: str | None,
    proposal_name: str,
    proposal_claim: str,
    proposal_pillar: str,
    proposal_sketch: str,
) -> int:
    """Persist a successful absorb-pipeline proposal.

    Returns the new row's autoincrement id. Validates ``proposal_pillar``
    against the known enum so the review pane's
    ``PILLAR_LABEL[proposal.proposal_pillar]`` lookup never crashes.
    """
    if proposal_pillar not in _VALID_PILLARS:
        raise ValueError(
            f"invalid proposal pillar {proposal_pillar!r}; "
            f"must be one of {sorted(_VALID_PILLARS)}"
        )

    conn = _init_db(db_path)
    try:
        with conn:
            cursor = conn.execute(
                """
                INSERT INTO forge_proposals (
                    source_url, arxiv_id, title, summary,
                    proposal_name, proposal_claim, proposal_pillar,
                    proposal_sketch, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_url,
                    arxiv_id,
                    title,
                    summary,
                    proposal_name,
                    proposal_claim,
                    proposal_pillar,
                    proposal_sketch,
                    time.time(),
                ),
            )
            new_id = cursor.lastrowid
        if new_id is None:
            raise RuntimeError("sqlite did not return a lastrowid")
        return int(new_id)
    finally:
        conn.close()


def list_proposals(
    *,
    db_path: pathlib.Path,
    status: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Return persisted proposals newest-first, optionally filtered
    by ``status``."""
    conn = _init_db(db_path)
    try:
        if status is None:
            cursor = conn.execute(
                "SELECT * FROM forge_proposals ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM forge_proposals WHERE status = ? "
                "ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            )
        return [_row_to_dict(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def get_proposal(
    *,
    db_path: pathlib.Path,
    proposal_id: int,
) -> dict[str, Any] | None:
    conn = _init_db(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM forge_proposals WHERE id = ?",
            (proposal_id,),
        ).fetchone()
        return _row_to_dict(row) if row else None
    finally:
        conn.close()


def mark_accepted(
    *,
    db_path: pathlib.Path,
    proposal_id: int,
    skill_path: str,
) -> None:
    conn = _init_db(db_path)
    try:
        with conn:
            conn.execute(
                """
                UPDATE forge_proposals
                SET status = 'accepted',
                    resolved_at = ?,
                    skill_path = ?
                WHERE id = ?
                """,
                (time.time(), skill_path, proposal_id),
            )
    finally:
        conn.close()


def mark_rejected(
    *,
    db_path: pathlib.Path,
    proposal_id: int,
) -> None:
    conn = _init_db(db_path)
    try:
        with conn:
            conn.execute(
                """
                UPDATE forge_proposals
                SET status = 'rejected',
                    resolved_at = ?
                WHERE id = ?
                """,
                (time.time(), proposal_id),
            )
    finally:
        conn.close()


# ── Skill-draft writer ────────────────────────────────────────────


def slugify_proposal_name(name: str) -> str:
    """Turn a proposal name into a URL-safe filesystem slug.

    Lowercases, replaces every non-alphanumeric run with a single
    hyphen, strips leading/trailing hyphens. Matches the URL-safety
    guard the gallery enforces on registry slugs (see
    ``test_list_techniques_ids_are_unique_and_url_safe``).
    """
    lowered = name.strip().lower()
    no_punct = _SLUG_KEEP.sub("-", lowered)
    deduped = _SLUG_DEDUP.sub("-", no_punct)
    return deduped.strip("-")


def write_skill_draft(
    *,
    db_path: pathlib.Path,
    proposal_id: int,
    skills_root: pathlib.Path,
) -> pathlib.Path:
    """Write a YAML-frontmatter skill draft for *proposal_id*.

    Creates ``<skills_root>/<slug>/SKILL.md`` with a minimal
    frontmatter (id, name, description, ``enabled_by_default: false``,
    priority 50, empty triggers + runtime_overrides) and a markdown
    body that surfaces the proposal claim, the implementation sketch,
    and the source URL so the user can re-read the paper.

    Refuses to overwrite an existing file — accepting the same
    proposal twice would otherwise silently clobber a draft the user
    has already edited. The route surfaces a 409-style error in that
    case.
    """
    proposal = get_proposal(db_path=db_path, proposal_id=proposal_id)
    if proposal is None:
        raise LookupError(f"unknown proposal {proposal_id}")

    slug = slugify_proposal_name(str(proposal["proposal_name"]))
    if not slug:
        raise ValueError(
            f"proposal name {proposal['proposal_name']!r} produced an empty slug"
        )

    skill_dir = skills_root / slug
    skill_path = skill_dir / "SKILL.md"
    if skill_path.exists():
        raise FileExistsError(f"skill draft already exists at {skill_path}")

    skill_dir.mkdir(parents=True, exist_ok=True)
    contents = _format_skill_draft(proposal, slug)
    skill_path.write_text(contents, encoding="utf-8")
    return skill_path


def _format_skill_draft(proposal: dict[str, Any], slug: str) -> str:
    name = str(proposal["proposal_name"]).strip()
    description = str(proposal["proposal_claim"]).strip()
    sketch = str(proposal["proposal_sketch"]).strip()
    source_url = str(proposal["source_url"]).strip()
    pillar = str(proposal["proposal_pillar"]).strip() or "cross-cutting"
    title = str(proposal["title"]).strip() or name

    frontmatter = (
        "---\n"
        f"id: {slug}\n"
        f"name: {_yaml_escape(name)}\n"
        f"description: {_yaml_escape(description)}\n"
        "enabled_by_default: false\n"
        "priority: 50\n"
        f"pillar: {pillar}\n"
        "triggers:\n"
        "  keywords: []\n"
        "  modes: []\n"
        "runtime_overrides: {}\n"
        f"source_url: {_yaml_escape(source_url)}\n"
        "---\n"
    )
    body = (
        f"# {name}\n\n"
        "> **Phase 4a draft.** Generated from a paper the user "
        "asked METIS to absorb. Edit before activation; the empty "
        "`runtime_overrides` block is intentional.\n\n"
        "## Source\n\n"
        f"- Title: {title}\n"
        f"- URL: {source_url}\n\n"
        "## Claim\n\n"
        f"{description}\n\n"
        "## Implementation sketch\n\n"
        f"{sketch}\n\n"
        "## Notes for the user\n\n"
        "Fill in `runtime_overrides` once you know which engine "
        "settings to flip (the Forge gallery's existing toggles are a "
        "good reference). Keep `enabled_by_default: false` until the "
        "skill has been exercised manually.\n"
    )
    return frontmatter + "\n" + body


def _yaml_escape(value: str) -> str:
    """Quote *value* if it contains YAML-significant characters.

    This is enough for the small set of fields we write — frontmatter
    consumers in this repo are tolerant. We don't depend on PyYAML
    so the writer stays import-cheap.
    """
    if value == "":
        return '""'
    if any(ch in value for ch in ":#&*!|>'%@`?\n"):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value
