"""Tests for the M14 Phase 5 Forge candidate-skill review service."""

from __future__ import annotations

import json
import pathlib
import sqlite3

import pytest


@pytest.fixture
def candidates_db(tmp_path: pathlib.Path) -> pathlib.Path:
    """A skill_candidates.db with three pending rows + one already-
    promoted row, to exercise the pending-only filter."""
    from metis_app.services.skill_repository import SkillRepository

    db_path = tmp_path / "skill_candidates.db"
    repo = SkillRepository(skills_dir=tmp_path / "skills")
    repo.save_candidate(
        db_path=db_path,
        query_text="How do I rerank results with a cross-encoder?",
        trace_json=json.dumps({"iterations": 3, "matches": 5}),
        convergence_score=0.97,
    )
    repo.save_candidate(
        db_path=db_path,
        query_text="What is hybrid retrieval?",
        trace_json=json.dumps({"iterations": 2, "matches": 4}),
        convergence_score=0.95,
    )
    repo.save_candidate(
        db_path=db_path,
        query_text="Already promoted",
        trace_json="{}",
        convergence_score=0.99,
    )
    repo.mark_candidate_promoted(db_path=db_path, candidate_id=3)
    return db_path


def test_list_pending_candidates_returns_unreviewed_only(
    candidates_db: pathlib.Path,
) -> None:
    """The Forge review pane should only see pending rows — promoted
    or rejected rows fall out of view."""
    from metis_app.services.forge_candidates import list_pending_candidates

    rows = list_pending_candidates(db_path=candidates_db)
    queries = [r["query_text"] for r in rows]
    assert "Already promoted" not in queries
    assert {"How do I rerank results with a cross-encoder?", "What is hybrid retrieval?"} == set(queries)


def test_list_pending_candidates_orders_by_convergence_desc(
    candidates_db: pathlib.Path,
) -> None:
    from metis_app.services.forge_candidates import list_pending_candidates

    rows = list_pending_candidates(db_path=candidates_db)
    scores = [r["convergence_score"] for r in rows]
    assert scores == sorted(scores, reverse=True)


def test_list_pending_candidates_exposes_default_slug_and_trace_excerpt(
    candidates_db: pathlib.Path,
) -> None:
    """The frontend renders a default slug (heuristic from query_text)
    so the user previews what file path the skill will land at, plus
    a short trace excerpt for context. Both are derived server-side
    so the UI stays a thin renderer."""
    from metis_app.services.forge_candidates import list_pending_candidates

    rows = list_pending_candidates(db_path=candidates_db)
    rerank_row = next(
        r for r in rows if "rerank" in r["query_text"].lower()
    )
    assert rerank_row["default_slug"] == "how-do-i-rerank-results-with-a"
    assert isinstance(rerank_row["trace_excerpt"], str)
    assert "iterations" in rerank_row["trace_excerpt"].lower()


def test_default_slug_for_query_handles_special_chars() -> None:
    """The slug must be URL-safe + filesystem-safe. Test the
    helper directly so future query shapes don't surprise us."""
    from metis_app.services.forge_candidates import default_slug_for_query

    assert default_slug_for_query("  Sparse / Cross-Encoder!! v2  ") == "sparse-cross-encoder-v2"
    # Empty / all-punct queries should never produce an empty slug.
    assert default_slug_for_query("???").startswith("candidate-")
    assert default_slug_for_query("") .startswith("candidate-")


def test_accept_candidate_writes_skill_file_and_flips_settings(
    candidates_db: pathlib.Path, tmp_path: pathlib.Path,
) -> None:
    """Accept produces a parse_skill_file-valid SKILL.md, flips
    ``settings["skills"]["enabled"][slug] = true``, and marks the
    candidate promoted in one transaction-shaped operation."""
    from metis_app.services.forge_candidates import accept_candidate
    from metis_app.services.skill_repository import parse_skill_file

    skills_root = tmp_path / "skills"
    settings_writes: list[dict[str, object]] = []

    def fake_settings_writer(payload: dict[str, object]) -> None:
        settings_writes.append(payload)

    result = accept_candidate(
        candidates_db=candidates_db,
        candidate_id=1,
        skills_root=skills_root,
        settings_writer=fake_settings_writer,
    )

    skill_path = pathlib.Path(result["skill_path"])
    assert skill_path.exists()
    skill_def = parse_skill_file(skill_path)
    assert skill_def.errors == [], (
        f"writer produced an invalid SKILL.md: {skill_def.errors}"
    )
    # Settings update routed through the injected writer.
    assert settings_writes, "expected settings_writer to be called"
    payload = settings_writes[0]
    assert "skills" in payload
    enabled = payload["skills"]["enabled"]  # type: ignore[index]
    assert enabled.get(result["slug"]) is True
    # Candidate row marked promoted.
    with sqlite3.connect(candidates_db) as conn:
        promoted = conn.execute(
            "SELECT promoted, rejected FROM skill_candidates WHERE id = 1"
        ).fetchone()
    assert promoted == (1, 0)


def test_accept_candidate_refuses_to_overwrite(
    candidates_db: pathlib.Path, tmp_path: pathlib.Path,
) -> None:
    """A second accept on the same slug must not silently clobber
    the user's edited draft. Surfaces ``FileExistsError``; the route
    layer translates that to a 409."""
    from metis_app.services.forge_candidates import accept_candidate

    skills_root = tmp_path / "skills"
    accept_candidate(
        candidates_db=candidates_db,
        candidate_id=1,
        skills_root=skills_root,
        settings_writer=lambda _payload: None,
    )

    with pytest.raises(FileExistsError):
        accept_candidate(
            candidates_db=candidates_db,
            candidate_id=2,  # different candidate, but slug overlaps if name forced
            skills_root=skills_root,
            settings_writer=lambda _payload: None,
            slug_override="how-do-i-rerank-results-with-a",
        )


def test_accept_candidate_returns_404_style_lookup_error(
    candidates_db: pathlib.Path, tmp_path: pathlib.Path,
) -> None:
    from metis_app.services.forge_candidates import accept_candidate

    with pytest.raises(LookupError):
        accept_candidate(
            candidates_db=candidates_db,
            candidate_id=999,
            skills_root=tmp_path / "skills",
            settings_writer=lambda _payload: None,
        )


def test_accept_candidate_uses_slug_override_when_provided(
    candidates_db: pathlib.Path, tmp_path: pathlib.Path,
) -> None:
    """The route exposes an optional ``slug`` field in the accept
    payload so the user can rename before commit. The override must
    be slugified the same way the default is, to keep the
    URL-safety / filesystem-safety contract."""
    from metis_app.services.forge_candidates import accept_candidate

    skills_root = tmp_path / "skills"
    result = accept_candidate(
        candidates_db=candidates_db,
        candidate_id=1,
        skills_root=skills_root,
        settings_writer=lambda _payload: None,
        slug_override="My Awesome Reranker!",
    )

    assert result["slug"] == "my-awesome-reranker"
    assert (skills_root / "my-awesome-reranker" / "SKILL.md").exists()


def test_accept_candidate_preserves_existing_skill_toggles(
    candidates_db: pathlib.Path, tmp_path: pathlib.Path,
) -> None:
    """Accept must not clobber unrelated skill toggles. ``save_settings``
    does a shallow ``dict.update``, so the service has to deep-merge the
    new slug into the *existing* ``settings["skills"]`` payload before
    handing it off to the writer.

    Regression for the Phase 5 Codex P1 review on PR #584: previously,
    the service handed the writer ``{"skills": {"enabled": {slug: True}}}``
    which would overwrite the entire existing ``skills`` object — wiping
    other-skill toggles and any sibling ``skills.config`` entries.
    """
    from metis_app.services.forge_candidates import accept_candidate

    skills_root = tmp_path / "skills"
    settings_writes: list[dict[str, object]] = []

    def fake_settings_writer(payload: dict[str, object]) -> None:
        settings_writes.append(payload)

    def fake_settings_reader() -> dict[str, object]:
        return {
            "skills": {
                "enabled": {
                    "existing-skill": True,
                    "another-disabled-one": False,
                },
                "config": {"existing-skill": {"foo": "bar"}},
            }
        }

    result = accept_candidate(
        candidates_db=candidates_db,
        candidate_id=1,
        skills_root=skills_root,
        settings_writer=fake_settings_writer,
        settings_reader=fake_settings_reader,
    )

    assert settings_writes, "expected settings_writer to be called"
    payload = settings_writes[0]
    assert "skills" in payload
    skills_payload = payload["skills"]
    assert isinstance(skills_payload, dict)
    enabled = skills_payload["enabled"]
    assert isinstance(enabled, dict)
    # Pre-existing toggles preserved.
    assert enabled["existing-skill"] is True
    assert enabled["another-disabled-one"] is False
    # The newly-accepted skill turned on.
    assert enabled[result["slug"]] is True
    # Sibling subkey (e.g. ``skills.config``) was not dropped.
    assert skills_payload["config"] == {"existing-skill": {"foo": "bar"}}


def test_accept_candidate_rolls_back_skill_file_on_writer_failure(
    candidates_db: pathlib.Path, tmp_path: pathlib.Path,
) -> None:
    """If ``settings_writer`` raises after the SKILL.md draft has been
    written, the service must delete the draft so the user can retry
    without hitting ``FileExistsError`` and the candidate row stays
    pending so the retry actually re-enters the accept flow.

    Regression for the Phase 5 Codex P2 review on PR #584.
    """
    import sqlite3 as _sqlite3

    from metis_app.services.forge_candidates import accept_candidate

    skills_root = tmp_path / "skills"

    def failing_writer(_payload: dict[str, object]) -> None:
        raise OSError("settings.json read-only")

    with pytest.raises(OSError):
        accept_candidate(
            candidates_db=candidates_db,
            candidate_id=1,
            skills_root=skills_root,
            settings_writer=failing_writer,
        )

    # The draft must NOT remain on disk: a retry would otherwise hit
    # FileExistsError and the user would be stuck in a partially-applied
    # state.
    expected = skills_root / "how-do-i-rerank-results-with-a" / "SKILL.md"
    assert not expected.exists()
    # Candidate stays pending so the retry can re-enter the flow.
    with _sqlite3.connect(candidates_db) as conn:
        row = conn.execute(
            "SELECT promoted, rejected FROM skill_candidates WHERE id = 1"
        ).fetchone()
    assert row == (0, 0)


def test_reject_candidate_marks_promoted_and_rejected(
    candidates_db: pathlib.Path,
) -> None:
    from metis_app.services.forge_candidates import reject_candidate

    reject_candidate(candidates_db=candidates_db, candidate_id=1)
    with sqlite3.connect(candidates_db) as conn:
        row = conn.execute(
            "SELECT promoted, rejected FROM skill_candidates WHERE id = 1"
        ).fetchone()
    assert row == (1, 1)


def test_reject_candidate_raises_lookup_error_for_unknown_id(
    candidates_db: pathlib.Path,
) -> None:
    from metis_app.services.forge_candidates import reject_candidate

    with pytest.raises(LookupError):
        reject_candidate(candidates_db=candidates_db, candidate_id=999)
