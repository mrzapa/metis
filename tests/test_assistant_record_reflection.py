"""Tests for the Phase 4a Bonsai-driven reflection writer.

Covers ``AssistantCompanionService.record_external_reflection`` plus the
HTTP route ``POST /v1/assistant/record-reflection`` and the cooldown,
guard rails, and provenance plumbing called out in ADR 0013.
"""

from __future__ import annotations

from litestar.testing import TestClient

from metis_app.api_litestar import create_app
from metis_app.services.assistant_companion import AssistantCompanionService
from metis_app.services.assistant_repository import AssistantRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bonsai_settings(cooldown: float = 30.0, **overrides) -> dict:
    settings = {
        "assistant_identity": {
            "assistant_id": "metis-companion",
            "name": "METIS",
            "archetype": "Research companion",
            "companion_enabled": True,
            "greeting": "hi",
        },
        "assistant_runtime": {
            "provider": "",
            "model": "",
            "fallback_to_primary": False,
        },
        "assistant_policy": {
            "reflection_enabled": True,
            "reflection_backend": "heuristic",
            "max_memory_entries": 12,
            "max_playbooks": 4,
            "max_brain_links": 8,
        },
        "seedling_external_reflection_cooldown_seconds": cooldown,
        "llm_provider": "mock",
        "llm_model": "mock-v1",
    }
    settings.update(overrides)
    return settings


def _service(tmp_path) -> AssistantCompanionService:
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    return AssistantCompanionService(repository=repo)


# ---------------------------------------------------------------------------
# Service-level tests
# ---------------------------------------------------------------------------


def test_record_external_reflection_persists_summary_and_status(tmp_path) -> None:
    svc = _service(tmp_path)
    settings = _bonsai_settings(cooldown=0.0)

    result = svc.record_external_reflection(
        summary="Look into the Comet ABC paper before tomorrow.",
        why="The user just absorbed a related news comet.",
        trigger="news_comet",
        kind="while_you_work",
        confidence=0.65,
        source_event={
            "source": "news_comet",
            "comet_id": "comet_abc123",
            "summary": "ABC paper: structured generation",
        },
        settings=settings,
    )

    assert result["ok"] is True
    assert result["kind"] == "while_you_work"
    entry = result["memory_entry"]
    assert entry["kind"] == "bonsai_reflection"
    assert entry["summary"].startswith("Look into the Comet ABC")
    assert entry["why"].startswith("The user just absorbed")
    assert "while_you_work" in entry["tags"]
    # Provenance survived to the memory row.
    assert any("comet:comet_abc123" in node for node in entry["related_node_ids"])
    # AssistantStatus tracks the latest reflection.
    status = svc.repository.get_status()
    assert status.last_reflection_trigger == "news_comet"
    assert status.latest_summary.startswith("Look into the Comet ABC")


def test_record_external_reflection_rejects_empty_summary(tmp_path) -> None:
    svc = _service(tmp_path)
    settings = _bonsai_settings()

    result = svc.record_external_reflection(summary="   ", settings=settings)
    assert result["ok"] is False
    assert result["reason"] == "empty_summary"


def test_record_external_reflection_returns_disabled_when_companion_off(tmp_path) -> None:
    svc = _service(tmp_path)
    settings = _bonsai_settings()
    settings["assistant_identity"]["companion_enabled"] = False

    result = svc.record_external_reflection(summary="something", settings=settings)
    assert result["ok"] is False
    assert result["reason"] == "assistant_disabled"


def test_record_external_reflection_returns_disabled_when_reflection_off(tmp_path) -> None:
    svc = _service(tmp_path)
    settings = _bonsai_settings()
    settings["assistant_policy"]["reflection_enabled"] = False

    result = svc.record_external_reflection(summary="something", settings=settings)
    assert result["ok"] is False
    assert result["reason"] == "assistant_disabled"


def test_record_external_reflection_honors_allow_automatic_writes(tmp_path) -> None:
    """Codex P2 from PR #548: the dock fires this writer automatically on
    every CompanionActivityEvent, so it must respect the same
    ``allow_automatic_writes`` policy that already gates ``reflect()``
    for non-manual triggers. Otherwise users who explicitly opted out
    of automatic writes still see persisted memory rows.
    """
    svc = _service(tmp_path)
    settings = _bonsai_settings()
    settings["assistant_policy"]["allow_automatic_writes"] = False

    # The default trigger is "while_you_work" — i.e. an automatic write.
    blocked = svc.record_external_reflection(
        summary="Bonsai note from automatic event.",
        settings=settings,
    )
    assert blocked["ok"] is False
    assert blocked["reason"] == "writes_disabled"

    # An explicitly user-driven "manual" trigger bypasses the gate so
    # a future "save this thought" button still works even when the
    # user has automatic writes disabled.
    manual = svc.record_external_reflection(
        summary="User pinned this thought.",
        trigger="manual",
        settings=settings,
    )
    assert manual["ok"] is True


def test_record_external_reflection_truncates_overlong_text(tmp_path) -> None:
    svc = _service(tmp_path)
    settings = _bonsai_settings(cooldown=0.0)

    long_text = "x" * 1500
    result = svc.record_external_reflection(summary=long_text, settings=settings)

    assert result["ok"] is True
    summary = result["memory_entry"]["summary"]
    # 800-char cap plus the ellipsis rune.
    assert len(summary) <= 801
    assert summary.endswith("…")


def test_record_external_reflection_cooldown_buckets_by_trigger(tmp_path) -> None:
    """Same trigger fires once; a different trigger should fire even within the
    cooldown window. ADR 0013 §Open Questions calls for per-bucket pacing."""
    svc = _service(tmp_path)
    settings = _bonsai_settings(cooldown=120.0)

    first = svc.record_external_reflection(
        summary="First note.",
        trigger="news_comet",
        settings=settings,
    )
    assert first["ok"] is True

    second = svc.record_external_reflection(
        summary="Second note.",
        trigger="news_comet",
        settings=settings,
    )
    assert second["ok"] is False
    assert second["reason"] == "cooldown"

    # A different trigger is its own bucket — should still fire.
    other = svc.record_external_reflection(
        summary="Third note.",
        trigger="autonomous_research",
        settings=settings,
    )
    assert other["ok"] is True


def test_record_external_reflection_cooldown_buckets_by_kind(tmp_path) -> None:
    """*while_you_work* and *overnight* are independent cooldown buckets so a
    Bonsai burst does not block an overnight cycle."""
    svc = _service(tmp_path)
    settings = _bonsai_settings(cooldown=120.0)

    while_you_work = svc.record_external_reflection(
        summary="Bonsai note.",
        trigger="news_comet",
        kind="while_you_work",
        settings=settings,
    )
    assert while_you_work["ok"] is True
    assert while_you_work["memory_entry"]["kind"] == "bonsai_reflection"

    # Same trigger, different kind — different bucket — should fire.
    overnight = svc.record_external_reflection(
        summary="Overnight note.",
        trigger="news_comet",
        kind="overnight",
        settings=settings,
    )
    assert overnight["ok"] is True
    assert overnight["memory_entry"]["kind"] == "overnight_reflection"
    assert overnight["memory_entry"]["title"].startswith("Overnight ") or (
        overnight["memory_entry"]["title"] == "Overnight note."
    )


def test_record_external_reflection_cooldown_lookback_survives_unrelated_writes(
    tmp_path,
) -> None:
    """Unrelated memory writes between two same-bucket Bonsai reflections must
    not push the prior bucket entry out of the cooldown lookback window."""
    from metis_app.models.assistant_types import AssistantMemoryEntry as _Memory

    svc = _service(tmp_path)
    settings = _bonsai_settings(cooldown=120.0)

    first = svc.record_external_reflection(
        summary="First Bonsai note.",
        trigger="news_comet",
        settings=settings,
    )
    assert first["ok"] is True

    # Inject 32 unrelated memory rows between the two cooldown checks.
    for i in range(32):
        svc.repository.add_memory_entry(
            _Memory.create(
                kind="reflection",
                title=f"Filler {i}",
                summary=f"Filler {i}",
                trigger="manual",
            ),
            max_entries=200,
        )

    second = svc.record_external_reflection(
        summary="Second Bonsai note.",
        trigger="news_comet",
        settings=settings,
    )
    # Cooldown still trips even with 32 unrelated rows in between.
    assert second["ok"] is False
    assert second["reason"] == "cooldown"


def test_record_external_reflection_normalises_trigger_whitespace(tmp_path) -> None:
    """Trigger ``"news_comet "`` should be considered the same bucket as
    ``"news_comet"`` so a stray trailing space cannot bypass the cooldown."""
    svc = _service(tmp_path)
    settings = _bonsai_settings(cooldown=120.0)

    first = svc.record_external_reflection(
        summary="First.",
        trigger="news_comet",
        settings=settings,
    )
    assert first["ok"] is True

    second = svc.record_external_reflection(
        summary="Second.",
        trigger="news_comet ",  # trailing space
        settings=settings,
    )
    assert second["ok"] is False
    assert second["reason"] == "cooldown"


def test_record_external_reflection_zero_cooldown_disables_gate(tmp_path) -> None:
    svc = _service(tmp_path)
    settings = _bonsai_settings(cooldown=0.0)

    for i in range(3):
        out = svc.record_external_reflection(
            summary=f"Note {i}",
            trigger="news_comet",
            settings=settings,
        )
        assert out["ok"] is True


# ---------------------------------------------------------------------------
# HTTP route
# ---------------------------------------------------------------------------


def test_route_records_reflection_and_returns_payload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def _fake_record(self, **kwargs):
        captured["kwargs"] = kwargs
        return {
            "ok": True,
            "kind": kwargs["kind"],
            "status": {"latest_summary": kwargs["summary"]},
            "memory_entry": {"summary": kwargs["summary"]},
            "snapshot": {"identity": {}, "memory": []},
        }

    from metis_app.services import workspace_orchestrator as orch_mod

    monkeypatch.setattr(
        orch_mod.WorkspaceOrchestrator,
        "record_companion_reflection",
        _fake_record,
    )

    with TestClient(app=create_app()) as client:
        response = client.post(
            "/v1/assistant/record-reflection",
            json={
                "summary": "Bonsai reflection text.",
                "why": "Because the comet absorbed.",
                "trigger": "news_comet",
                "kind": "while_you_work",
                "confidence": 0.7,
                "source_event": {"source": "news_comet"},
                "tags": ["news_comet"],
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["kind"] == "while_you_work"

    # Orchestrator received the right kwargs (proves the wiring).
    kwargs = captured["kwargs"]
    assert kwargs["summary"] == "Bonsai reflection text."
    assert kwargs["trigger"] == "news_comet"
    assert kwargs["kind"] == "while_you_work"
    assert kwargs["source_event"] == {"source": "news_comet"}


def test_route_rejects_blank_summary(monkeypatch) -> None:
    from metis_app.services import workspace_orchestrator as orch_mod

    def _should_not_be_called(self, **kwargs):
        raise AssertionError("orchestrator should never be called for invalid body")

    monkeypatch.setattr(
        orch_mod.WorkspaceOrchestrator,
        "record_companion_reflection",
        _should_not_be_called,
    )

    with TestClient(app=create_app()) as client:
        response = client.post(
            "/v1/assistant/record-reflection",
            json={"summary": ""},
        )
    # Pydantic min_length=1 rejects empty summary.
    assert response.status_code in {400, 422}


def test_route_rejects_unknown_kind(monkeypatch) -> None:
    from metis_app.services import workspace_orchestrator as orch_mod

    def _should_not_be_called(self, **kwargs):
        raise AssertionError("orchestrator should never be called for invalid body")

    monkeypatch.setattr(
        orch_mod.WorkspaceOrchestrator,
        "record_companion_reflection",
        _should_not_be_called,
    )

    with TestClient(app=create_app()) as client:
        response = client.post(
            "/v1/assistant/record-reflection",
            json={
                "summary": "ok",
                "kind": "unknown_kind",
            },
        )
    assert response.status_code in {400, 422}
