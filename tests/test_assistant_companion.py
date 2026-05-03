from __future__ import annotations

from importlib import import_module

from litestar.testing import TestClient

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


def test_reflect_emits_brain_link_created_activity_event(tmp_path, monkeypatch) -> None:
    """Phase 6 follow-up: a successful ``reflect()`` that wrote brain
    links emits exactly one ``kind="brain_link_created"`` activity
    event with a payload listing the new links. The brain-graph view
    subscribes to this to pulse the matching edges."""
    from metis_app.seedling.activity import (
        clear_seedling_activity_events,
        list_seedling_activity_events,
    )

    clear_seedling_activity_events()

    repo = AssistantRepository(tmp_path / "assistant_state.json")
    service = AssistantCompanionService(repository=repo)
    settings = {
        "assistant_identity": {
            "assistant_id": "metis-companion",
            "name": "Guide",
            "archetype": "Research companion",
            "companion_enabled": True,
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
            "max_brain_links": 8,
        },
        "llm_provider": "mock",
        "llm_model": "mock-v1",
    }

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
    new_links = result["brain_links"]
    assert len(new_links) >= 1

    events = list_seedling_activity_events()
    brain_link_events = [e for e in events if e.get("kind") == "brain_link_created"]
    assert len(brain_link_events) == 1, (
        "Expected exactly one brain_link_created event per reflect() call"
    )
    event = brain_link_events[0]
    assert event["state"] == "completed"
    assert event["trigger"] == "completed_run"
    payload_links = event["payload"]["status"]["links"]
    assert len(payload_links) == len(new_links)
    # Every emitted link carries the three triple fields the brain-graph
    # subscriber needs to find the matching edge.
    for link in payload_links:
        assert "source_node_id" in link
        assert "target_node_id" in link
        assert "relation" in link
    # The event also carries the memory entry id so the frontend can
    # correlate the pulse with the originating reflection.
    assert event["payload"]["status"]["memory_entry_id"] == result["memory_entry"]["entry_id"]


def test_reflect_emits_only_persisted_links_when_max_items_truncates(
    tmp_path, monkeypatch
) -> None:
    """Phase 6 follow-up Codex P2 regression: ``add_brain_links``
    enforces ``max_items`` by sorting the merged set DESC by
    ``created_at`` and slicing. With ``max_brain_links=2`` and a
    pre-seeded brain-link table, a reflect() that creates 4 new links
    will see some pre-existing rows survive while older incoming links
    drop. The emitted ``brain_link_created`` event must list only the
    links that were actually persisted — otherwise the frontend would
    animate edges that aren't in the stored graph state."""
    from metis_app.models.assistant_types import AssistantBrainLink
    from metis_app.seedling.activity import (
        clear_seedling_activity_events,
        list_seedling_activity_events,
    )

    clear_seedling_activity_events()

    repo = AssistantRepository(tmp_path / "assistant_state.json")

    # Seed the table with one PRE-EXISTING brain link that has a
    # NEWER created_at than the about-to-be-created links. Because
    # ``add_brain_links`` sorts merged DESC by created_at and truncates,
    # this row will survive. With max_brain_links=2 and reflect()
    # producing 3 new links, the merged set is 4 → top 2 by created_at
    # survive: the pre-existing newer + the most recent of the new.
    pre_existing = AssistantBrainLink.from_payload(
        {
            "link_id": "pre-existing-1",
            "created_at": "2099-01-01T00:00:00Z",
            "source_node_id": "memory:pre-existing",
            "target_node_id": "assistant:metis",
            "relation": "belongs_to",
            "label": "Belongs To",
        }
    )
    repo.add_brain_links([pre_existing], max_items=8)

    service = AssistantCompanionService(repository=repo)
    settings = {
        "assistant_identity": {
            "assistant_id": "metis-companion",
            "name": "Guide",
            "archetype": "Research companion",
            "companion_enabled": True,
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
            # Tight cap → some incoming links will be truncated.
            "max_brain_links": 2,
        },
        "llm_provider": "mock",
        "llm_model": "mock-v1",
    }

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
    new_links_count = len(result["brain_links"])
    assert new_links_count >= 2, (
        "Expected reflect() to create at least 2 brain links to exercise "
        f"truncation (got {new_links_count})"
    )

    # Confirm the repository genuinely truncated.
    persisted_after = repo.list_brain_links()
    assert len(persisted_after) == 2, (
        f"max_brain_links=2 should cap at 2 (got {len(persisted_after)})"
    )

    events = list_seedling_activity_events()
    brain_link_events = [
        e for e in events if e.get("kind") == "brain_link_created"
    ]
    assert len(brain_link_events) == 1
    payload_links = brain_link_events[0]["payload"]["status"]["links"]

    # The event must list ONLY the new links that survived truncation,
    # not the pre-existing one (and not any incoming links that got
    # truncated). ``result["brain_links"]`` is a list of payload dicts;
    # each carries ``source_node_id`` / ``target_node_id`` / ``relation``.
    persisted_ids = {item.link_id for item in persisted_after}
    pre_existing_id = pre_existing.link_id
    new_link_persisted_ids = persisted_ids - {pre_existing_id}

    payload_tuples = {
        (item["source_node_id"], item["target_node_id"], item["relation"])
        for item in payload_links
    }
    surviving_new_link_tuples = {
        (item.source_node_id, item.target_node_id, item.relation)
        for item in persisted_after
        if item.link_id in new_link_persisted_ids
    }
    assert payload_tuples == surviving_new_link_tuples, (
        f"Payload must contain only persisted-and-new links. "
        f"Got: {payload_tuples}, expected: {surviving_new_link_tuples}"
    )

    # Sanity: payload must be SHORTER than the input link count —
    # otherwise this test isn't actually exercising the regression.
    assert len(payload_links) < new_links_count, (
        "Truncation must have dropped at least one incoming link for "
        f"this test to exercise the regression (payload={len(payload_links)}, "
        f"input={new_links_count})"
    )


def test_orchestrator_note_user_input_uses_partial_dict_update(tmp_path) -> None:
    """Codex P1 regression (PR #572): ``_note_user_input`` MUST use
    the partial-dict overload of ``update_status``, not the
    ``get_status() → mutate → update_status(full_object)`` pattern.

    The full-object pattern races with concurrent reflection updates:
    a reflection writing ``latest_summary`` between our read and our
    write would be silently reverted by our stale rewrite.

    Direct verification — capture every ``update_status`` call from
    ``_note_user_input`` and assert each is a partial dict containing
    ONLY ``last_user_input_at``, never a full ``AssistantStatus``
    object that would carry stale snapshots of every other field."""
    from metis_app.models.assistant_types import AssistantStatus
    from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator
    from metis_app.services.session_repository import SessionRepository

    session_repo = SessionRepository(db_path=tmp_path / "sessions.db")
    session_repo.init_db()
    session_repo.create_session(session_id="s1", title="Test session")
    assistant_repo = AssistantRepository(tmp_path / "assistant.json")

    captured_updates: list = []
    real_update = assistant_repo.update_status

    def _spy_update_status(payload):
        captured_updates.append(payload)
        return real_update(payload)

    assistant_repo.update_status = _spy_update_status  # type: ignore[method-assign]

    assistant_service = AssistantCompanionService(
        repository=assistant_repo,
        session_repo=session_repo,
    )
    orch = WorkspaceOrchestrator(
        session_repo=session_repo,
        assistant_service=assistant_service,
    )

    # User message → triggers _note_user_input → calls update_status.
    orch.append_message("s1", role="user", content="hello")

    # Find the call that was made FROM _note_user_input. There may be
    # other update_status calls in the chain; we assert at least one
    # is the user-input bump and that one is a partial dict (not a
    # full AssistantStatus).
    user_input_calls = [
        p for p in captured_updates
        if isinstance(p, dict) and "last_user_input_at" in p
    ]
    assert user_input_calls, (
        "Expected at least one update_status call carrying "
        "last_user_input_at"
    )
    for call in user_input_calls:
        # Critical: must be a partial dict, NOT a full AssistantStatus
        # object. The full-object path is the race-prone pattern.
        assert not isinstance(call, AssistantStatus), (
            "_note_user_input must use the partial-dict overload, "
            "not pass a full AssistantStatus (Codex P1 fix)"
        )
        # And the partial dict must carry ONLY the user-input field —
        # carrying anything else risks clobbering concurrent writes
        # to that other field too.
        assert set(call.keys()) == {"last_user_input_at"}, (
            f"Partial-dict call must contain ONLY last_user_input_at "
            f"(got keys: {set(call.keys())})"
        )


def test_orchestrator_append_message_user_bumps_last_user_input_at(tmp_path) -> None:
    """M13 retro fix: ``WorkspaceOrchestrator.append_message`` with
    ``role="user"`` MUST bump ``AssistantStatus.last_user_input_at``
    so the Phase 4b overnight quiet-window gate sees the user as
    present even when no reflection fires for the message.

    Assistant-role messages MUST NOT bump the field — they're the
    response, not user activity."""
    from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator
    from metis_app.services.session_repository import SessionRepository

    session_repo = SessionRepository(db_path=tmp_path / "sessions.db")
    session_repo.init_db()
    session_repo.create_session(session_id="s1", title="Test session")
    assistant_repo = AssistantRepository(tmp_path / "assistant.json")
    assistant_service = AssistantCompanionService(
        repository=assistant_repo,
        session_repo=session_repo,
    )
    orch = WorkspaceOrchestrator(
        session_repo=session_repo,
        assistant_service=assistant_service,
    )

    # Baseline: status has no last_user_input_at.
    assert assistant_repo.get_status().last_user_input_at == ""

    # User message → bumps the field.
    orch.append_message("s1", role="user", content="hello")
    after_user = assistant_repo.get_status().last_user_input_at
    assert after_user, "Expected last_user_input_at to be bumped on user message"

    # Assistant message → must NOT change the timestamp (stays at
    # the user-message bump).
    orch.append_message("s1", role="assistant", content="hi back")
    after_assistant = assistant_repo.get_status().last_user_input_at
    assert after_assistant == after_user, (
        "Assistant-role messages must not bump last_user_input_at"
    )


def test_reflect_does_not_emit_brain_link_created_when_reflection_skipped(
    tmp_path, monkeypatch
) -> None:
    """If ``reflect()`` short-circuits (assistant disabled, cooldown,
    duplicate), no brain links are written and no
    ``brain_link_created`` event is emitted."""
    from metis_app.seedling.activity import (
        clear_seedling_activity_events,
        list_seedling_activity_events,
    )

    clear_seedling_activity_events()

    repo = AssistantRepository(tmp_path / "assistant_state.json")
    service = AssistantCompanionService(repository=repo)
    # Companion disabled → reflect short-circuits before brain-link write.
    settings = {
        "assistant_identity": {"companion_enabled": False},
        "assistant_policy": {"reflection_enabled": True},
    }

    result = service.reflect(trigger="completed_run", settings=settings)
    assert result["ok"] is False

    events = list_seedling_activity_events()
    brain_link_events = [e for e in events if e.get("kind") == "brain_link_created"]
    assert brain_link_events == []


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
    assistant_api = import_module("metis_app.api_litestar.routes.assistant")
    api_app = import_module("metis_app.api_litestar")

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

    client = TestClient(app=api_app.create_app())

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
    """reflect() spawns a thread that writes an auto-generated skill file via the LLM quality gate."""
    import json as _json
    import time
    from unittest.mock import MagicMock, patch
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

    mock_llm = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content=_json.dumps({
        "is_generalizable": True,
        "skill_name": "Entropy Explainer",
        "skill_description": "Explains entropy in information theory.",
        "confidence": 0.92,
    }))

    settings = {
        "assistant_identity": {"companion_enabled": True},
        "assistant_policy": {
            "reflection_enabled": True,
            "allow_automatic_writes": True,
            "reflection_backend": "heuristic",
            "trigger_on_completed_run": True,
        },
    }
    with patch("metis_app.services.assistant_companion.create_llm", return_value=mock_llm), \
         patch.object(svc, "_resolve_runtime_llm_settings", return_value={"llm_provider": "openai"}):
        svc.reflect(trigger="completed_run", settings=settings, force=True)

        # Poll for the daemon promotion thread to write the skill file (up to 5s).
        auto_dir = skills_dir / "auto-generated"
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if auto_dir.exists() and list(auto_dir.glob("*.md")):
                break
            time.sleep(0.02)

    auto_dir = skills_dir / "auto-generated"
    written = list(auto_dir.glob("*.md")) if auto_dir.exists() else []
    assert len(written) == 1, f"Expected 1 auto-generated skill file, got: {written}"

    # Candidate should be marked promoted so it isn't re-promoted next cycle
    candidates = skill_repo.list_candidates(db_path=db_path, limit=10)
    assert candidates == [], "Candidate should be marked promoted and no longer listed"


def test_update_config_persists_tone_preset(tmp_path, monkeypatch) -> None:
    """Tone preset round-trips through the companion service."""
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    service = AssistantCompanionService(repository=repo)

    # Redirect settings_store to a tmp_path-backed dict so update_config
    # does not write to the repo's actual settings.json.
    fake_settings: dict = {}
    monkeypatch.setattr(
        "metis_app.settings_store.load_settings",
        lambda: dict(fake_settings),
    )
    monkeypatch.setattr(
        "metis_app.settings_store.save_settings",
        lambda values: fake_settings.update(values),
    )

    service.update_config(identity={"tone_preset": "concise-analyst"})
    snapshot = service.get_snapshot({})
    assert snapshot["identity"]["tone_preset"] == "concise-analyst"


def test_reflection_prompt_uses_resolved_seed_when_tone_preset_set_with_empty_seed() -> None:
    """Regression for M23 final-review I2: ``build_assistant_reflection_prompt``
    must route ``identity.prompt_seed`` through ``resolve_prompt_seed`` so that
    a ``tone_preset`` set with an empty ``prompt_seed`` resolves to the canonical
    preset seed rather than producing an empty leading prompt segment.

    This is the latent bug from M23 Phase 1's dead-resolver gap: previously the
    reflection prompt read ``identity.prompt_seed.strip()`` directly, bypassing
    the resolver entirely.
    """
    from metis_app.models.assistant_types import AssistantIdentity, TONE_PRESETS
    from metis_app.services.companion_voice import resolve_prompt_seed
    from metis_app.services.runtime_resolution import build_assistant_reflection_prompt

    # tone_preset set, prompt_seed empty: the resolver should pick the
    # canonical preset seed; the prompt builder must include it verbatim.
    identity = AssistantIdentity()
    object.__setattr__(identity, "tone_preset", "concise-analyst")
    object.__setattr__(identity, "prompt_seed", "")

    expected_seed = TONE_PRESETS["concise-analyst"]
    assert resolve_prompt_seed(identity) == expected_seed

    prompt = build_assistant_reflection_prompt(
        identity,
        context_lines=["A test context line."],
        trace_events=[],
        seed_summary="",
        nourishment_block="",
    )

    # The canonical concise-analyst preset seed must be the leading
    # segment of the prompt — proving runtime_resolution honours the
    # resolver and not the raw stored prompt_seed string.
    assert prompt.startswith(expected_seed), (
        f"Expected reflection prompt to start with the resolved preset seed.\n"
        f"  expected_seed = {expected_seed!r}\n"
        f"  prompt[:200]  = {prompt[:200]!r}"
    )


# ---------------------------------------------------------------------------
# M23 Phase 2 — AssistantRepository delete methods
# ---------------------------------------------------------------------------


def test_delete_memory_entry_round_trip(tmp_path) -> None:
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    repo.add_memory_entry(
        AssistantMemoryEntry(
            entry_id="abc-123",
            created_at="2026-05-03T00:00:00+00:00",
            kind="reflection",
            title="Test entry",
            summary="A test reflection",
        )
    )
    assert repo.delete_memory_entry("abc-123") is True
    assert all(item.entry_id != "abc-123" for item in repo.list_memory())


def test_delete_memory_entry_missing_id_returns_false(tmp_path) -> None:
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    assert repo.delete_memory_entry("does-not-exist") is False


def test_delete_memory_by_kind_filters_correctly(tmp_path) -> None:
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    for i, kind in enumerate(["reflection", "reflection", "reflection", "skill", "skill"]):
        repo.add_memory_entry(
            AssistantMemoryEntry(
                entry_id=f"id-{i}",
                created_at="2026-05-03T00:00:00+00:00",
                kind=kind,
                title=f"t{i}",
                summary="s",
            )
        )
    deleted = repo.delete_memory_by_kind("reflection")
    assert deleted == 3
    remaining = repo.list_memory()
    assert len(remaining) == 2
    assert all(item.kind == "skill" for item in remaining)


def test_delete_memory_by_kind_unknown_kind_returns_zero(tmp_path) -> None:
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    assert repo.delete_memory_by_kind("nonexistent") == 0


def test_delete_playbook_round_trip(tmp_path) -> None:
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    pb = AssistantPlaybook.create(title="t", bullets=["a", "b"])
    repo.add_playbook(pb)
    assert repo.delete_playbook(pb.playbook_id) is True
    assert all(item.playbook_id != pb.playbook_id for item in repo.list_playbooks())


def test_delete_playbook_missing_id_returns_false(tmp_path) -> None:
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    assert repo.delete_playbook("not-real") is False


# ---------------------------------------------------------------------------
# M23 Phase 2 — AssistantCompanion delete methods (status-coherence layer)
# ---------------------------------------------------------------------------


def _seed_status_summary(repo: AssistantRepository, summary: str, why: str = "") -> None:
    """Set status.latest_summary / latest_why directly. Mirrors the
    pattern used by reflect() to seed status before testing."""
    status = repo.get_status()
    status.latest_summary = summary
    status.latest_why = why
    repo.update_status(status)


def test_companion_delete_memory_entry_clears_latest_summary_when_head(
    tmp_path,
) -> None:
    """Deleting the only memory entry must clear status.latest_summary
    so the dock no longer shows a summary backed by a row that no
    longer exists."""
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    service = AssistantCompanionService(repository=repo)

    repo.add_memory_entry(
        AssistantMemoryEntry.from_payload(
            {
                "entry_id": "head-1",
                "created_at": "2026-05-03T10:00:00Z",
                "kind": "reflection",
                "title": "Head reflection",
                "summary": "Most recent thought.",
                "why": "Because of the latest run.",
            }
        )
    )
    _seed_status_summary(repo, "Most recent thought.", "Because of the latest run.")

    result = service.delete_memory_entry("head-1")
    assert result == {"ok": True}

    status_after = repo.get_status()
    assert status_after.latest_summary == ""
    assert status_after.latest_why == ""


def test_companion_delete_memory_entry_refreshes_to_next_when_head_removed(
    tmp_path,
) -> None:
    """When the head entry is removed and another entry remains,
    status.latest_summary must be refreshed to the new head's summary."""
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    service = AssistantCompanionService(repository=repo)

    repo.add_memory_entry(
        AssistantMemoryEntry.from_payload(
            {
                "entry_id": "older",
                "created_at": "2026-05-03T09:00:00Z",
                "kind": "reflection",
                "title": "Older",
                "summary": "An older thought.",
                "why": "older why",
            }
        )
    )
    repo.add_memory_entry(
        AssistantMemoryEntry.from_payload(
            {
                "entry_id": "head",
                "created_at": "2026-05-03T10:00:00Z",
                "kind": "reflection",
                "title": "Head",
                "summary": "The newest thought.",
                "why": "newest why",
            }
        )
    )
    _seed_status_summary(repo, "The newest thought.", "newest why")

    service.delete_memory_entry("head")

    status_after = repo.get_status()
    assert status_after.latest_summary == "An older thought."
    assert status_after.latest_why == "older why"


def test_companion_delete_memory_entry_preserves_status_when_not_head(
    tmp_path,
) -> None:
    """Deleting a non-head entry must leave status.latest_summary
    pointing at the still-current head."""
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    service = AssistantCompanionService(repository=repo)

    repo.add_memory_entry(
        AssistantMemoryEntry.from_payload(
            {
                "entry_id": "older",
                "created_at": "2026-05-03T09:00:00Z",
                "kind": "reflection",
                "title": "Older",
                "summary": "An older thought.",
                "why": "older why",
            }
        )
    )
    repo.add_memory_entry(
        AssistantMemoryEntry.from_payload(
            {
                "entry_id": "head",
                "created_at": "2026-05-03T10:00:00Z",
                "kind": "reflection",
                "title": "Head",
                "summary": "The newest thought.",
                "why": "newest why",
            }
        )
    )
    _seed_status_summary(repo, "The newest thought.", "newest why")

    service.delete_memory_entry("older")

    status_after = repo.get_status()
    # Status still mirrors the (still-present) head entry.
    assert status_after.latest_summary == "The newest thought."
    assert status_after.latest_why == "newest why"


def test_companion_delete_memory_entry_missing_id_skips_status_refresh(
    tmp_path,
) -> None:
    """A no-op delete (missing id) must not touch the status mirror."""
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    service = AssistantCompanionService(repository=repo)

    _seed_status_summary(repo, "Pinned summary.", "Pinned why.")

    result = service.delete_memory_entry("does-not-exist")
    assert result == {"ok": False}

    status_after = repo.get_status()
    assert status_after.latest_summary == "Pinned summary."
    assert status_after.latest_why == "Pinned why."


def test_companion_delete_memory_by_kind_refreshes_when_head_in_kind(
    tmp_path,
) -> None:
    """Deleting a kind that includes the most-recent entry must
    refresh status.latest_summary to the next-most-recent surviving
    entry's summary (or empty if none)."""
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    service = AssistantCompanionService(repository=repo)

    repo.add_memory_entry(
        AssistantMemoryEntry.from_payload(
            {
                "entry_id": "skill-older",
                "created_at": "2026-05-03T08:00:00Z",
                "kind": "skill",
                "title": "Skill older",
                "summary": "Skill summary that survives.",
                "why": "skill why",
            }
        )
    )
    repo.add_memory_entry(
        AssistantMemoryEntry.from_payload(
            {
                "entry_id": "reflection-head",
                "created_at": "2026-05-03T10:00:00Z",
                "kind": "reflection",
                "title": "Reflection head",
                "summary": "Reflection that gets nuked.",
                "why": "reflection why",
            }
        )
    )
    _seed_status_summary(
        repo,
        "Reflection that gets nuked.",
        "reflection why",
    )

    result = service.delete_memory_by_kind("reflection")
    assert result == {"ok": True, "deleted_count": 1}

    status_after = repo.get_status()
    # The surviving skill entry now backs the status mirror.
    assert status_after.latest_summary == "Skill summary that survives."
    assert status_after.latest_why == "skill why"


def test_companion_delete_memory_by_kind_no_matches_skips_status_refresh(
    tmp_path,
) -> None:
    """deleted_count == 0 must not touch the status mirror — the
    refresh path is gated on a real deletion having happened."""
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    service = AssistantCompanionService(repository=repo)

    _seed_status_summary(repo, "Pinned summary.", "Pinned why.")

    result = service.delete_memory_by_kind("no-such-kind")
    assert result == {"ok": True, "deleted_count": 0}

    status_after = repo.get_status()
    assert status_after.latest_summary == "Pinned summary."
    assert status_after.latest_why == "Pinned why."


def test_companion_delete_playbook_does_not_touch_status(tmp_path) -> None:
    """Playbook delete must NOT refresh the status mirror — status
    mirrors the most-recent memory entry, not playbooks."""
    repo = AssistantRepository(tmp_path / "assistant_state.json")
    service = AssistantCompanionService(repository=repo)

    pb = AssistantPlaybook.create(title="t", bullets=["a", "b"])
    repo.add_playbook(pb)
    _seed_status_summary(repo, "Pinned summary.", "Pinned why.")

    result = service.delete_playbook(pb.playbook_id)
    assert result == {"ok": True}

    status_after = repo.get_status()
    assert status_after.latest_summary == "Pinned summary."
    assert status_after.latest_why == "Pinned why."
