from __future__ import annotations

from unittest.mock import patch

from metis_app.services.learning_route_service import (
    LearningRouteIndexSummary,
    LearningRoutePreviewRequest,
    LearningRouteStarSnapshot,
    plan_learning_route_preview,
)


def _origin_star(**overrides: object) -> LearningRouteStarSnapshot:
    payload: dict[str, object] = {
        "id": "star-origin",
        "label": "Graph Thinking",
        "intent": "Learn how connected ideas fit together",
        "notes": "Focus on practical understanding",
        "active_manifest_path": "/indexes/origin-active.json",
        "linked_manifest_paths": [
            "/indexes/origin-active.json",
            "/indexes/origin-linked-b.json",
            "/indexes/origin-linked-c.json",
        ],
        "connected_user_star_ids": ["star-linked"],
    }
    payload.update(overrides)
    return LearningRouteStarSnapshot(**payload)


def _connected_star(**overrides: object) -> LearningRouteStarSnapshot:
    payload: dict[str, object] = {
        "id": "star-linked",
        "label": "Applied Graphs",
        "intent": "Map concepts onto real projects",
        "notes": "Bridge theory and use",
        "active_manifest_path": "/indexes/linked-active.json",
        "linked_manifest_paths": ["/indexes/linked-active.json"],
        "connected_user_star_ids": ["star-origin"],
    }
    payload.update(overrides)
    return LearningRouteStarSnapshot(**payload)


def _index(manifest_path: str, index_id: str) -> LearningRouteIndexSummary:
    return LearningRouteIndexSummary(
        index_id=index_id,
        manifest_path=manifest_path,
        document_count=4,
        chunk_count=18,
        created_at="2026-03-31T10:00:00+00:00",
        embedding_signature="embed-test",
    )


def test_learning_route_reuses_a_single_manifest_when_only_one_source_exists() -> None:
    request = LearningRoutePreviewRequest(
        origin_star=_origin_star(
            linked_manifest_paths=["/indexes/origin-active.json"],
            connected_user_star_ids=[],
        ),
        connected_stars=[],
        indexes=[_index("/indexes/origin-active.json", "Origin Active")],
    )

    preview = plan_learning_route_preview(request, settings={"llm_provider": "mock"})

    assert len(preview.steps) == 4
    assert [step.kind for step in preview.steps] == [
        "orient",
        "foundations",
        "synthesis",
        "apply",
    ]
    assert {step.manifest_path for step in preview.steps} == {"/indexes/origin-active.json"}
    assert all(step.source_star_id is None for step in preview.steps)


def test_learning_route_prioritizes_active_then_linked_then_connected_sources() -> None:
    request = LearningRoutePreviewRequest(
        origin_star=_origin_star(),
        connected_stars=[_connected_star()],
        indexes=[
            _index("/indexes/origin-active.json", "Origin Active"),
            _index("/indexes/origin-linked-b.json", "Origin Linked B"),
            _index("/indexes/origin-linked-c.json", "Origin Linked C"),
            _index("/indexes/linked-active.json", "Linked Active"),
        ],
    )

    preview = plan_learning_route_preview(request, settings={"llm_provider": "mock"})

    assert [step.manifest_path for step in preview.steps] == [
        "/indexes/origin-active.json",
        "/indexes/origin-linked-b.json",
        "/indexes/origin-linked-c.json",
        "/indexes/linked-active.json",
    ]


def test_learning_route_marks_connected_star_reuse_when_step_uses_connected_active_manifest() -> None:
    request = LearningRoutePreviewRequest(
        origin_star=_origin_star(
            linked_manifest_paths=["/indexes/origin-active.json", "/indexes/origin-linked-b.json"],
        ),
        connected_stars=[_connected_star()],
        indexes=[
            _index("/indexes/origin-active.json", "Origin Active"),
            _index("/indexes/origin-linked-b.json", "Origin Linked B"),
            _index("/indexes/linked-active.json", "Linked Active"),
        ],
    )

    preview = plan_learning_route_preview(request, settings={"llm_provider": "mock"})

    connected_step = next(
        step for step in preview.steps if step.manifest_path == "/indexes/linked-active.json"
    )
    assert connected_step.source_star_id == "star-linked"


def test_learning_route_falls_back_to_templates_when_llm_planning_fails() -> None:
    request = LearningRoutePreviewRequest(
        origin_star=_origin_star(),
        connected_stars=[_connected_star()],
        indexes=[
            _index("/indexes/origin-active.json", "Origin Active"),
            _index("/indexes/origin-linked-b.json", "Origin Linked B"),
            _index("/indexes/origin-linked-c.json", "Origin Linked C"),
            _index("/indexes/linked-active.json", "Linked Active"),
        ],
    )

    with patch(
        "metis_app.services.learning_route_service.create_llm",
        side_effect=RuntimeError("planner offline"),
    ):
        preview = plan_learning_route_preview(request, settings={"llm_provider": "openai"})

    assert preview.title == "Route Through the Stars: Graph Thinking"
    assert preview.steps[0].title == "Orient Around Graph Thinking"
    assert "Tutor me through an orientation" in preview.steps[0].tutor_prompt
