"""Tests for the M14 Phase 4b Forge proposal persistence layer."""

from __future__ import annotations

import pathlib

import pytest


@pytest.fixture
def tmp_db(tmp_path: pathlib.Path) -> pathlib.Path:
    return tmp_path / "forge_proposals.db"


def _sample_proposal_payload(**overrides: object) -> dict[str, object]:
    base = {
        "source_url": "https://arxiv.org/abs/2501.12345",
        "arxiv_id": "2501.12345",
        "title": "Cross-encoder reranking that matters",
        "summary": "We propose a sparse cross-encoder reranking method.",
        "proposal_name": "Sparse Cross-Encoder Reranking",
        "proposal_claim": "Reranks BM25 hits with a small cross-encoder.",
        "proposal_pillar": "cortex",
        "proposal_sketch": "Score top-k hits with a cross-encoder.",
    }
    base.update(overrides)
    return base


def test_save_proposal_returns_an_id_and_persists(tmp_db: pathlib.Path) -> None:
    """Saving a proposal returns the new row's autoincrement id and
    the row is readable through ``list_proposals``."""
    from metis_app.services.forge_proposals import (
        list_proposals,
        save_proposal,
    )

    proposal_id = save_proposal(db_path=tmp_db, **_sample_proposal_payload())  # type: ignore[arg-type]
    assert isinstance(proposal_id, int)
    assert proposal_id > 0

    rows = list_proposals(db_path=tmp_db)
    assert len(rows) == 1
    assert rows[0]["id"] == proposal_id
    assert rows[0]["title"] == "Cross-encoder reranking that matters"
    assert rows[0]["status"] == "pending"


def test_list_proposals_orders_newest_first(tmp_db: pathlib.Path) -> None:
    """Newer proposals come first so the review pane shows the user's
    most recent absorption at the top."""
    from metis_app.services.forge_proposals import list_proposals, save_proposal

    first_id = save_proposal(  # type: ignore[arg-type]
        db_path=tmp_db,
        **_sample_proposal_payload(proposal_name="Older proposal"),
    )
    second_id = save_proposal(  # type: ignore[arg-type]
        db_path=tmp_db,
        **_sample_proposal_payload(proposal_name="Newer proposal"),
    )

    rows = list_proposals(db_path=tmp_db)
    assert [r["id"] for r in rows] == [second_id, first_id]


def test_list_proposals_filters_by_status(tmp_db: pathlib.Path) -> None:
    """The review pane only wants ``pending`` rows by default;
    ``accepted`` / ``rejected`` filters expose the full audit history."""
    from metis_app.services.forge_proposals import (
        list_proposals,
        mark_accepted,
        save_proposal,
    )

    pending_id = save_proposal(db_path=tmp_db, **_sample_proposal_payload())  # type: ignore[arg-type]
    accepted_id = save_proposal(db_path=tmp_db, **_sample_proposal_payload(  # type: ignore[arg-type]
        proposal_name="Accepted",
    ))
    mark_accepted(db_path=tmp_db, proposal_id=accepted_id, skill_path="skills/accepted/SKILL.md")

    pending = list_proposals(db_path=tmp_db, status="pending")
    accepted = list_proposals(db_path=tmp_db, status="accepted")
    assert [r["id"] for r in pending] == [pending_id]
    assert [r["id"] for r in accepted] == [accepted_id]


def test_get_proposal_returns_the_row(tmp_db: pathlib.Path) -> None:
    """``get_proposal`` is the route's accept/reject handlers' lookup —
    they need every column, including ``skill_path`` once accepted."""
    from metis_app.services.forge_proposals import get_proposal, save_proposal

    proposal_id = save_proposal(db_path=tmp_db, **_sample_proposal_payload())  # type: ignore[arg-type]
    row = get_proposal(db_path=tmp_db, proposal_id=proposal_id)
    assert row is not None
    assert row["title"] == "Cross-encoder reranking that matters"
    assert row["proposal_pillar"] == "cortex"
    assert row["status"] == "pending"
    assert row["skill_path"] is None


def test_get_proposal_returns_none_for_unknown_id(tmp_db: pathlib.Path) -> None:
    from metis_app.services.forge_proposals import get_proposal

    assert get_proposal(db_path=tmp_db, proposal_id=999) is None


def test_mark_accepted_records_skill_path_and_resolved_at(
    tmp_db: pathlib.Path,
) -> None:
    """Acceptance writes the path of the drafted skill so the review
    pane can offer a "open the skill file" affordance later, and
    sets ``resolved_at`` so the audit history has a timestamp."""
    from metis_app.services.forge_proposals import (
        get_proposal,
        mark_accepted,
        save_proposal,
    )

    proposal_id = save_proposal(db_path=tmp_db, **_sample_proposal_payload())  # type: ignore[arg-type]
    mark_accepted(
        db_path=tmp_db,
        proposal_id=proposal_id,
        skill_path="skills/sparse-cross-encoder-reranking/SKILL.md",
    )

    row = get_proposal(db_path=tmp_db, proposal_id=proposal_id)
    assert row is not None
    assert row["status"] == "accepted"
    assert row["skill_path"] == "skills/sparse-cross-encoder-reranking/SKILL.md"
    assert isinstance(row["resolved_at"], float)
    assert row["resolved_at"] > 0


def test_mark_rejected_sets_status(tmp_db: pathlib.Path) -> None:
    from metis_app.services.forge_proposals import (
        get_proposal,
        mark_rejected,
        save_proposal,
    )

    proposal_id = save_proposal(db_path=tmp_db, **_sample_proposal_payload())  # type: ignore[arg-type]
    mark_rejected(db_path=tmp_db, proposal_id=proposal_id)

    row = get_proposal(db_path=tmp_db, proposal_id=proposal_id)
    assert row is not None
    assert row["status"] == "rejected"
    assert row["skill_path"] is None
    assert isinstance(row["resolved_at"], float)


def test_save_proposal_rejects_invalid_pillar(tmp_db: pathlib.Path) -> None:
    """Pillar enum mirrors ``TechniqueDescriptor`` — invalid values
    must be caught at write time so the gallery's render contract
    (``PILLAR_LABEL`` lookup) doesn't crash."""
    from metis_app.services.forge_proposals import save_proposal

    with pytest.raises(ValueError):
        save_proposal(  # type: ignore[arg-type]
            db_path=tmp_db,
            **_sample_proposal_payload(proposal_pillar="not-a-pillar"),
        )


# ── skill-draft writer tests ───────────────────────────────────────


def test_write_skill_draft_creates_yaml_frontmatter_skill_md(
    tmp_path: pathlib.Path,
) -> None:
    """Accepting a proposal drafts a ``skills/<slug>/SKILL.md`` with
    YAML frontmatter and a markdown body. ``enabled_by_default``
    is False — accepted proposals don't auto-activate; the user
    reviews + opts in."""
    from metis_app.services.forge_proposals import (
        save_proposal,
        write_skill_draft,
    )

    skills_root = tmp_path / "skills"
    proposal_id = save_proposal(  # type: ignore[arg-type]
        db_path=tmp_path / "forge_proposals.db",
        **_sample_proposal_payload(),
    )
    skill_path = write_skill_draft(
        db_path=tmp_path / "forge_proposals.db",
        proposal_id=proposal_id,
        skills_root=skills_root,
    )

    expected = skills_root / "sparse-cross-encoder-reranking" / "SKILL.md"
    assert skill_path == expected
    assert expected.exists()
    contents = expected.read_text(encoding="utf-8")
    assert contents.startswith("---\n")
    assert "id: sparse-cross-encoder-reranking" in contents
    assert "name: Sparse Cross-Encoder Reranking" in contents
    assert "enabled_by_default: false" in contents
    # Source URL belongs in the body so the user can re-open the
    # paper; never silently auto-applied as a setting.
    assert "https://arxiv.org/abs/2501.12345" in contents


def test_write_skill_draft_slugs_the_proposal_name(
    tmp_path: pathlib.Path,
) -> None:
    """Slug is lowercased, alphanumeric + hyphen-only, idempotent
    against weird input (whitespace, slashes, punctuation). Matches
    the URL-safety guard the gallery enforces on registry slugs."""
    from metis_app.services.forge_proposals import (
        save_proposal,
        write_skill_draft,
    )

    proposal_id = save_proposal(  # type: ignore[arg-type]
        db_path=tmp_path / "forge_proposals.db",
        **_sample_proposal_payload(
            proposal_name="  Sparse / Cross-Encoder!! Reranking v2  ",
        ),
    )
    skill_path = write_skill_draft(
        db_path=tmp_path / "forge_proposals.db",
        proposal_id=proposal_id,
        skills_root=tmp_path / "skills",
    )
    assert skill_path.parent.name == "sparse-cross-encoder-reranking-v2"


def test_write_skill_draft_round_trips_through_parse_skill_file(
    tmp_path: pathlib.Path,
) -> None:
    """The drafted ``SKILL.md`` must satisfy the canonical loader's
    schema. Codex P1 review on PR #582 caught that the original
    template emitted unknown keys (``pillar``, ``source_url``) and
    omitted required trigger keys (``file_types``, ``output_styles``),
    so every accepted skill landed in an unloadable state.

    This test runs the actual ``parse_skill_file`` over the drafted
    file and asserts ``errors`` is empty — the same gate any real
    skill in ``skills/`` has to pass.
    """
    from metis_app.services.forge_proposals import (
        save_proposal,
        write_skill_draft,
    )
    from metis_app.services.skill_repository import parse_skill_file

    proposal_id = save_proposal(  # type: ignore[arg-type]
        db_path=tmp_path / "forge_proposals.db",
        **_sample_proposal_payload(),
    )
    skill_path = write_skill_draft(
        db_path=tmp_path / "forge_proposals.db",
        proposal_id=proposal_id,
        skills_root=tmp_path / "skills",
    )

    skill_def = parse_skill_file(skill_path)
    assert skill_def.errors == [], (
        f"skill loader rejected the drafted file: {skill_def.errors}"
    )


def test_write_skill_draft_refuses_to_overwrite(tmp_path: pathlib.Path) -> None:
    """The user has accepted twice — second accept must not silently
    clobber the first draft; the route surfaces a friendly error
    instead."""
    from metis_app.services.forge_proposals import (
        save_proposal,
        write_skill_draft,
    )

    proposal_id = save_proposal(  # type: ignore[arg-type]
        db_path=tmp_path / "forge_proposals.db",
        **_sample_proposal_payload(),
    )
    write_skill_draft(
        db_path=tmp_path / "forge_proposals.db",
        proposal_id=proposal_id,
        skills_root=tmp_path / "skills",
    )

    with pytest.raises(FileExistsError):
        write_skill_draft(
            db_path=tmp_path / "forge_proposals.db",
            proposal_id=proposal_id,
            skills_root=tmp_path / "skills",
        )
