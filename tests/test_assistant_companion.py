from __future__ import annotations

from importlib import import_module

from fastapi.testclient import TestClient

from metis_app.models.assistant_types import (
    AssistantBrainLink,
    AssistantMemoryEntry,
    AssistantPlaybook,
)
from metis_app.services.assistant_companion import AssistantCompanionService
from metis_app.services.assistant_repository import AssistantRepository


def test_assistant_repository_persists_state_and_orders_memory(tmp_path) -> None:
    repo = AssistantRepository(tmp_path / "assistant_state.json")

    default_state = repo.load_state()

    assert default_state["status"]["state"] == "idle"
    assert default_state["memory"] == []

    repo.save_state(
        {
            "status": {"state": "ready", "latest_summary": "Saved state."},
            "memory": [
                {
                    "entry_id": "old-entry",
                    "created_at": "2026-03-08T12:00:00Z",
                    "kind": "reflection",
                    "title": "Old",
                    "summary": "Older memory",
                }
            ],
            "playbooks": [{"playbook_id": "pb-1", "created_at": "2026-03-08T12:05:00Z", "title": "PB"}],
            "brain_links": [
                {
                    "link_id": "link-1",
                    "created_at": "2026-03-08T12:06:00Z",
                    "source_node_id": "memory:old-entry",
                    "target_node_id": "assistant:metis",
                    "relation": "belongs_to",
                    "label": "Belongs To",
                }
            ],
        }
    )

    repo.add_memory_entry(
        AssistantMemoryEntry.from_payload(
            {
                "entry_id": "new-entry",
                "created_at": "2026-03-08T13:00:00Z",
                "kind": "reflection",
                "title": "New",
                "summary": "Newer memory",
            }
        )
    )

    status = repo.update_status({"paused": True, "latest_why": "Testing"})

    memory_ids = [item.entry_id for item in repo.list_memory()]
    assert memory_ids == ["new-entry", "old-entry"]
    assert repo.list_memory(limit=1)[0].entry_id == "new-entry"
    assert status.paused is True
    assert status.latest_why == "Testing"
    assert repo.list_playbooks()[0].title == "PB"
    assert repo.list_brain_links()[0].source_node_id == "memory:old-entry"
    assert (tmp_path / "rag_sessions.db").exists()


def test_assistant_service_snapshot_and_reflect_updates_repository(tmp_path, monkeypatch) -> None:
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    service = AssistantCompanionService(repository=repo)

    settings = {
        "assistant_identity": {
            "assistant_id": "metis-companion",
            "name": "Guide",
            "archetype": "Research companion",
            "companion_enabled": True,
            "greeting": "Hello from the companion.",
        },
        "assistant_runtime": {
            "provider": "",
            "model": "",
            "fallback_to_primary": False,
        },
        "assistant_policy": {
            "reflection_enabled": True,
            "reflection_backend": "heuristic",
            "max_memory_entries": 4,
            "max_playbooks": 2,
            "max_brain_links": 6,
        },
        "llm_provider": "mock",
        "llm_model": "mock-v1",
    }

    repo.add_memory_entry(
        AssistantMemoryEntry.from_payload(
            {
                "entry_id": "memory-1",
                "created_at": "2026-03-08T12:30:00Z",
                "kind": "reflection",
                "title": "Prior reflection",
                "summary": "Kept the last summary.",
            }
        )
    )
    repo.add_playbook(
        AssistantPlaybook.from_payload(
            {
                "playbook_id": "playbook-1",
                "created_at": "2026-03-08T12:31:00Z",
                "title": "Follow-up pattern",
                "bullets": ["Lead with the next step."],
            }
        )
    )
    repo.add_brain_links(
        [
            AssistantBrainLink.from_payload(
                {
                    "link_id": "link-1",
                    "created_at": "2026-03-08T12:32:00Z",
                    "source_node_id": "memory:memory-1",
                    "target_node_id": "assistant:metis",
                    "relation": "belongs_to",
                    "label": "Belongs To",
                }
            )
        ]
    )

    snapshot = service.get_snapshot(settings)

    assert snapshot["identity"]["name"] == "Guide"
    assert snapshot["runtime"]["fallback_to_primary"] is False
    assert snapshot["status"]["state"] == "ready"
    assert snapshot["status"]["runtime_ready"] is False
    assert snapshot["status"]["bootstrap_message"] == "Companion runtime is not configured yet."
    assert snapshot["memory"][0]["entry_id"] == "memory-1"
    assert snapshot["playbooks"][0]["playbook_id"] == "playbook-1"

    monkeypatch.setattr(
        service,
        "_generate_reflection",
        lambda *args, **kwargs: {
            "title": "Learned from a completed run",
            "summary": "Captured a short next step.",
            "details": "Keep it concise.",
            "why": "A completed run gives useful context.",
            "confidence": 0.9,
            "tags": ["completed_run"],
            "related_node_ids": ["session:sess-1"],
            "playbook_title": "Follow-up pattern",
            "playbook_bullets": ["Lead with the next step."],
        },
    )

    result = service.reflect(
        trigger="completed_run",
        settings=settings,
        session_id="sess-1",
        run_id="run-1",
    )

    assert result["ok"] is True
    assert result["memory_entry"]["title"] == "Learned from a completed run"
    assert result["playbook"]["title"] == "Follow-up pattern"
    assert len(result["brain_links"]) == 3
    assert repo.get_status().last_reflection_trigger == "completed_run"
    assert repo.get_status().latest_summary == "Captured a short next step."
    assert repo.list_memory(limit=1)[0].summary == "Captured a short next step."
    assert repo.list_playbooks(limit=1)[0].title == "Follow-up pattern"
    assert result["snapshot"]["status"]["last_reflection_trigger"] == "completed_run"


def test_assistant_service_dedupes_by_context_for_non_chat_reflections(
    tmp_path,
    monkeypatch,
) -> None:
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    service = AssistantCompanionService(repository=repo)

    settings = {
        "assistant_identity": {"companion_enabled": True},
        "assistant_runtime": {"fallback_to_primary": True},
        "assistant_policy": {
            "reflection_enabled": True,
            "reflection_backend": "heuristic",
            "reflection_cooldown_seconds": 0,
        },
        "llm_provider": "mock",
        "llm_model": "mock-v1",
    }

    monkeypatch.setattr(
        service,
        "_generate_reflection",
        lambda *args, **kwargs: {
            "title": "Index reflection",
            "summary": "Captured an index-level insight.",
            "details": "Reusable note.",
            "why": "Each index build should get its own reflection.",
            "confidence": 0.8,
            "tags": ["index_build"],
            "related_node_ids": [],
            "playbook_title": "",
            "playbook_bullets": [],
        },
    )

    first = service.reflect(
        trigger="index_build",
        context_id="index:alpha",
        settings=settings,
    )
    duplicate = service.reflect(
        trigger="index_build",
        context_id="index:alpha",
        settings=settings,
    )
    second = service.reflect(
        trigger="index_build",
        context_id="index:beta",
        settings=settings,
    )

    assert first["ok"] is True
    assert duplicate["ok"] is False
    assert duplicate["reason"] == "duplicate"
    assert second["ok"] is True
    assert [item.context_id for item in repo.list_memory(limit=2)] == ["index:beta", "index:alpha"]


def test_assistant_api_routes_return_snapshot_and_reflection(monkeypatch) -> None:
    assistant_api = import_module("metis_app.api.assistant")
    api_app = import_module("metis_app.api.app")

    snapshot = {
        "identity": {
            "assistant_id": "metis-companion",
            "name": "Guide",
            "archetype": "Research companion",
            "companion_enabled": True,
            "greeting": "Hello from the companion.",
            "prompt_seed": "You are METIS, a local-first companion who helps the user get oriented, suggests next steps, and records concise reflections without taking over the main chat.",
            "docked": True,
            "minimized": False,
        },
        "runtime": {
            "provider": "",
            "model": "",
            "local_gguf_model_path": "",
            "local_gguf_context_length": 2048,
            "local_gguf_gpu_layers": 0,
            "local_gguf_threads": 0,
            "fallback_to_primary": True,
            "auto_bootstrap": True,
            "auto_install": False,
            "bootstrap_state": "pending",
            "recommended_model_name": "",
            "recommended_quant": "",
            "recommended_use_case": "chat",
        },
        "policy": {
            "reflection_enabled": True,
            "reflection_backend": "heuristic",
            "reflection_cooldown_seconds": 180,
            "max_memory_entries": 4,
            "max_playbooks": 2,
            "max_brain_links": 6,
            "trigger_on_onboarding": True,
            "trigger_on_index_build": True,
            "trigger_on_completed_run": True,
            "allow_automatic_writes": True,
            "autonomous_research_enabled": False,
            "autonomous_research_provider": "tavily",
        },
        "status": {
            "state": "ready",
            "paused": False,
            "runtime_ready": True,
            "runtime_source": "primary_fallback",
            "runtime_provider": "",
            "runtime_model": "",
            "bootstrap_state": "fallback",
            "bootstrap_message": "Saved.",
            "recommended_model_name": "",
            "recommended_quant": "",
            "recommended_use_case": "chat",
            "last_reflection_at": "",
            "last_reflection_trigger": "",
            "latest_summary": "Saved.",
            "latest_why": "",
        },
        "memory": [
            {
                "entry_id": "memory-1",
                "created_at": "2026-03-08T12:30:00Z",
                "kind": "reflection",
                "title": "Prior reflection",
                "summary": "Kept the last summary.",
                "details": "",
                "why": "",
                "provenance": "assistant_local",
                "confidence": 0.5,
                "trigger": "",
                "session_id": "",
                "run_id": "",
                "tags": [],
                "related_node_ids": [],
            }
        ],
        "playbooks": [],
        "brain_links": [],
    }
    reflection = {
        "ok": True,
        "status": {"state": "reflected"},
        "memory_entry": {"title": "Follow-up"},
        "playbook": None,
        "brain_links": [],
        "snapshot": snapshot,
    }
    captured: dict[str, object] = {}

    class _FakeOrchestrator:
        def get_assistant_snapshot(self) -> dict[str, object]:
            return snapshot

        def reflect_assistant(self, **kwargs) -> dict[str, object]:
            captured.update(kwargs)
            return reflection

    monkeypatch.setattr(assistant_api, "WorkspaceOrchestrator", lambda: _FakeOrchestrator())

    client = TestClient(api_app.create_app())

    snapshot_response = client.get("/v1/assistant")
    assert snapshot_response.status_code == 200
    assert snapshot_response.json()["status"]["state"] == "ready"

    reflect_response = client.post(
        "/v1/assistant/reflect",
        json={"trigger": "completed_run", "session_id": "sess-1", "run_id": "run-1", "force": True},
    )
    assert reflect_response.status_code == 200
    assert reflect_response.json()["status"]["state"] == "reflected"
    assert captured == {"trigger": "completed_run", "session_id": "sess-1", "run_id": "run-1", "force": True}


def test_assistant_policy_autonomous_fields_default_to_false():
    from metis_app.models.assistant_types import AssistantPolicy
    policy = AssistantPolicy()
    assert policy.autonomous_research_enabled is False
    assert policy.autonomous_research_provider == "tavily"


def test_assistant_policy_roundtrip_autonomous_fields():
    from metis_app.models.assistant_types import AssistantPolicy
    policy = AssistantPolicy(
        autonomous_research_enabled=True,
        autonomous_research_provider="duckduckgo",
    )
    restored = AssistantPolicy.from_payload(policy.to_payload())
    assert restored.autonomous_research_enabled is True
    assert restored.autonomous_research_provider == "duckduckgo"


def test_reflect_triggers_autonomous_research_when_enabled(tmp_path):
    """After reflect(), autonomous research runs in background when policy enables it."""
    import threading
    from metis_app.services.assistant_companion import AssistantCompanionService
    from metis_app.services.assistant_repository import AssistantRepository

    research_called = threading.Event()

    class MockOrchestrator:
        def run_autonomous_research(self, settings):
            research_called.set()
            return {
                "faculty_id": "emergence",
                "index_id": "auto_emergence_abc",
                "title": "Emergence Research",
                "sources": ["http://example.com"],
            }

    settings = {
        "assistant_identity": {"companion_enabled": True},
        "assistant_policy": {
            "reflection_enabled": True,
            "autonomous_research_enabled": True,
            "allow_automatic_writes": True,
        },
        "llm_provider": "mock",
    }

    svc = AssistantCompanionService(
        repository=AssistantRepository(tmp_path / "state.json")
    )
    svc.reflect(
        trigger="manual",
        settings=settings,
        force=True,
        _orchestrator=MockOrchestrator(),
    )

    # Wait for the daemon thread to call the orchestrator (up to 5s timeout)
    fired = research_called.wait(timeout=5.0)
    assert fired, "autonomous research daemon thread did not fire within 5 seconds"


def test_reflect_promotes_high_scoring_skill_candidates(tmp_path) -> None:
    """reflect() writes an auto-generated skill file for high-scoring candidates."""
    import json as _json
    from metis_app.services.assistant_companion import AssistantCompanionService
    from metis_app.services.assistant_repository import AssistantRepository
    from metis_app.services.skill_repository import SkillRepository

    db_path = tmp_path / "skill_candidates.db"
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()

    skill_repo = SkillRepository(skills_dir=skills_dir)
    skill_repo.save_candidate(
        db_path=db_path,
        query_text="What is entropy?",
        trace_json=_json.dumps({"run_id": "run-1", "iterations_used": 3}),
        convergence_score=0.95,
    )

    svc = AssistantCompanionService(
        repository=AssistantRepository(tmp_path / "state.json"),
        skill_repo=skill_repo,
        candidates_db_path=db_path,
    )

    settings = {
        "assistant_identity": {"companion_enabled": True},
        "assistant_policy": {
            "reflection_enabled": True,
            "allow_automatic_writes": True,
            "reflection_backend": "heuristic",
        },
        "llm_provider": "mock",
    }
    svc.reflect(trigger="manual", settings=settings, force=True)

    auto_dir = skills_dir / "auto-generated"
    written = list(auto_dir.glob("*.md")) if auto_dir.exists() else []
    assert len(written) == 1, f"Expected 1 auto-generated skill file, got: {written}"

    # Candidate should be marked promoted so it isn't re-promoted next cycle
    candidates = skill_repo.list_candidates(db_path=db_path, limit=10)
    assert candidates == [], "Candidate should be marked promoted and no longer listed"
