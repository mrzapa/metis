from __future__ import annotations

from metis_app.models.improvement_types import ImprovementEntry
from metis_app.services.improvement_repository import ImprovementRepository


def test_improvement_repository_persists_and_materializes_entries(tmp_path) -> None:
    repo = ImprovementRepository(
        db_path=":memory:",
        improvements_root=tmp_path,
    )
    entry = ImprovementEntry.create(
        artifact_key="idea:test:session-1:run-1",
        artifact_type="idea",
        title="Promote a better retrieval plan",
        summary="A reflection suggested a stronger retrieval loop.",
        body_md="Use the last grounded run to seed the next experiment.",
        session_id="session-1",
        run_id="run-1",
        status="draft",
        tags=["assistant_reflection"],
        upstream_ids=["source-1"],
        metadata={"origin": "assistant_reflection"},
    )

    stored = repo.upsert_entry(entry)
    listed = repo.list_entries(artifact_type="idea", limit=10)

    assert stored.entry_id
    assert len(listed) == 1
    assert listed[0].artifact_key == "idea:test:session-1:run-1"
    assert listed[0].metadata["origin"] == "assistant_reflection"
    assert listed[0].markdown_path
    assert (tmp_path / "ideas" / f"{stored.slug}.md").exists()


def test_improvement_repository_filters_by_status_and_type(tmp_path) -> None:
    repo = ImprovementRepository(
        db_path=":memory:",
        improvements_root=tmp_path,
    )
    repo.upsert_entry(
        ImprovementEntry.create(
            artifact_key="source:auto:1",
            artifact_type="source",
            title="Research source",
            status="active",
        )
    )
    repo.upsert_entry(
        ImprovementEntry.create(
            artifact_key="idea:auto:1",
            artifact_type="idea",
            title="Reflection idea",
            status="draft",
        )
    )

    active_sources = repo.list_entries(artifact_type="source", status="active", limit=10)
    draft_ideas = repo.list_entries(artifact_type="idea", status="draft", limit=10)

    assert [item.artifact_type for item in active_sources] == ["source"]
    assert [item.status for item in draft_ideas] == ["draft"]
