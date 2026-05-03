"""Smoke tests for the Litestar API."""

from __future__ import annotations

from litestar import Litestar
from litestar.testing import TestClient

from metis_app.services.index_service import build_index_bundle, save_index_bundle


def test_app_creation():
    """Verify the Litestar app can be created."""
    from metis_app.api_litestar import create_app

    app = create_app()
    assert isinstance(app, Litestar)


def test_healthz():
    """Test /healthz endpoint."""
    from metis_app.api_litestar import create_app

    with TestClient(app=create_app()) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"ok": True}


def test_version():
    """Test /v1/version endpoint."""
    from metis_app.api_litestar import create_app

    with TestClient(app=create_app()) as client:
        response = client.get("/v1/version")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data


def test_index_list():
    """Test /v1/index/list endpoint."""
    from metis_app.api_litestar import create_app

    with TestClient(app=create_app()) as client:
        response = client.get("/v1/index/list")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


def test_delete_index_removes_manifest_directory(tmp_path):
    """Test /v1/index deletes a persisted manifest directory."""
    from metis_app.api_litestar import create_app

    src = tmp_path / "notes.txt"
    src.write_text("Delete the index artifacts but keep the source.\n", encoding="utf-8")
    bundle = build_index_bundle([str(src)], {"embedding_provider": "mock", "vector_db_type": "json"})
    manifest_path = save_index_bundle(bundle, index_dir=tmp_path / "indexes")

    with TestClient(app=create_app()) as client:
        response = client.delete("/v1/index", params={"manifest_path": str(manifest_path)})
        assert response.status_code == 200
        assert response.json() == {
            "deleted": True,
            "manifest_path": str(manifest_path.resolve()),
            "index_id": bundle.index_id,
        }

    assert not manifest_path.exists()
    assert not manifest_path.parent.exists()
    assert src.exists()


def test_delete_index_returns_404_for_missing_manifest(tmp_path):
    """Test /v1/index returns 404 for an unknown manifest path."""
    from metis_app.api_litestar import create_app

    with TestClient(app=create_app()) as client:
        response = client.delete(
            "/v1/index",
            params={"manifest_path": str(tmp_path / "missing" / "manifest.json")},
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Index not found."


def test_gguf_hardware():
    """Test /v1/gguf/hardware endpoint."""
    from metis_app.api_litestar import create_app

    with TestClient(app=create_app()) as client:
        response = client.get("/v1/gguf/hardware")
        assert response.status_code == 200
        data = response.json()
        assert "total_ram_gb" in data
        assert "has_gpu" in data


def test_gguf_catalog():
    """Test /v1/gguf/catalog endpoint."""
    from metis_app.api_litestar import create_app

    with TestClient(app=create_app()) as client:
        response = client.get("/v1/gguf/catalog")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0

        row = data[0]
        assert "recommendation_summary" in row
        assert isinstance(row["recommendation_summary"], str)
        assert row["recommendation_summary"]
        assert "notes" in row
        assert isinstance(row["notes"], list)
        assert "caveats" in row
        assert isinstance(row["caveats"], list)
        assert "score_components" in row
        assert isinstance(row["score_components"], dict)


def test_gguf_installed():
    """Test /v1/gguf/installed endpoint."""
    from metis_app.api_litestar import create_app

    with TestClient(app=create_app()) as client:
        response = client.get("/v1/gguf/installed")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


def test_gguf_validate_not_found():
    """Test /v1/gguf/validate returns 404 for missing file."""
    from metis_app.api_litestar import create_app

    with TestClient(app=create_app()) as client:
        response = client.post(
            "/v1/gguf/validate",
            json={"model_path": "/nonexistent/model.gguf"},
        )
        assert response.status_code == 404


def test_gguf_validate_bad_extension(tmp_path):
    """Test /v1/gguf/validate returns 400 for non-.gguf files."""
    from metis_app.api_litestar import create_app

    model_file = tmp_path / "model.bin"
    model_file.write_bytes(b"fake")

    with TestClient(app=create_app()) as client:
        response = client.post(
            "/v1/gguf/validate",
            json={"model_path": str(model_file)},
        )
        assert response.status_code == 400
        assert ".gguf" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# M23 Phase 2 — DELETE routes for assistant memory / playbooks
# ---------------------------------------------------------------------------


def _patch_assistant_orchestrator(monkeypatch, fake):
    """Swap ``WorkspaceOrchestrator`` on the assistant route module."""
    from importlib import import_module

    assistant_api = import_module("metis_app.api_litestar.routes.assistant")
    monkeypatch.setattr(assistant_api, "WorkspaceOrchestrator", lambda: fake)


def test_delete_memory_entry_route_round_trip(monkeypatch):
    from metis_app.api_litestar import create_app

    captured: dict = {}

    class _FakeOrchestrator:
        def delete_assistant_memory_entry(self, entry_id: str) -> dict:
            captured["entry_id"] = entry_id
            return {"ok": True}

    _patch_assistant_orchestrator(monkeypatch, _FakeOrchestrator())

    with TestClient(app=create_app()) as client:
        response = client.delete("/v1/assistant/memory/seed-1")
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert captured == {"entry_id": "seed-1"}


def test_delete_memory_entry_route_missing_id(monkeypatch):
    from metis_app.api_litestar import create_app

    class _FakeOrchestrator:
        def delete_assistant_memory_entry(self, entry_id: str) -> dict:
            return {"ok": False}

    _patch_assistant_orchestrator(monkeypatch, _FakeOrchestrator())

    with TestClient(app=create_app()) as client:
        response = client.delete("/v1/assistant/memory/does-not-exist")
        assert response.status_code == 200
        assert response.json() == {"ok": False}


def test_delete_memory_by_kind_route(monkeypatch):
    from metis_app.api_litestar import create_app

    captured: dict = {}

    class _FakeOrchestrator:
        def delete_assistant_memory_by_kind(self, kind: str) -> dict:
            captured["kind"] = kind
            return {"ok": True, "deleted_count": 3}

    _patch_assistant_orchestrator(monkeypatch, _FakeOrchestrator())

    with TestClient(app=create_app()) as client:
        response = client.delete("/v1/assistant/memory/by-kind?kind=reflection")
        assert response.status_code == 200
        body = response.json()
        assert body["deleted_count"] == 3
        assert captured == {"kind": "reflection"}


def test_delete_memory_oldest_route(monkeypatch):
    """``DELETE /v1/assistant/memory/oldest?limit=N`` must dispatch to
    the orchestrator's ``delete_assistant_memory_oldest`` wrapper, NOT
    fall through to ``delete_assistant_memory_entry`` with
    ``entry_id="oldest"`` (a routing-order regression that would happen
    if the oldest route is registered after the dynamic ``{entry_id}``
    handler)."""
    from metis_app.api_litestar import create_app

    captured: dict = {}

    class _FakeOrchestrator:
        def delete_assistant_memory_oldest(self, *, limit: int) -> dict:
            captured["limit"] = limit
            return {"ok": True, "deleted_count": limit}

        def delete_assistant_memory_entry(self, entry_id: str) -> dict:
            # Must NOT be called — its presence here proves the literal
            # "oldest" segment is not being captured by ``{entry_id}``.
            captured["wrong_path"] = entry_id
            return {"ok": False}

    _patch_assistant_orchestrator(monkeypatch, _FakeOrchestrator())

    with TestClient(app=create_app()) as client:
        response = client.delete("/v1/assistant/memory/oldest?limit=42")
        assert response.status_code == 200
        body = response.json()
        assert body == {"ok": True, "deleted_count": 42}
        assert captured == {"limit": 42}


def test_delete_playbook_route_round_trip(monkeypatch):
    from metis_app.api_litestar import create_app

    captured: dict = {}

    class _FakeOrchestrator:
        def delete_assistant_playbook(self, playbook_id: str) -> dict:
            captured["playbook_id"] = playbook_id
            return {"ok": True}

    _patch_assistant_orchestrator(monkeypatch, _FakeOrchestrator())

    with TestClient(app=create_app()) as client:
        response = client.delete("/v1/assistant/playbooks/pb-1")
        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert captured == {"playbook_id": "pb-1"}


def test_delete_memory_entry_route_real_stack(tmp_path, monkeypatch):
    """End-to-end happy-path: real AssistantRepository, real
    AssistantCompanionService, real WorkspaceOrchestrator wired
    together. The route → orchestrator wrapper → companion service →
    repo round-trip is exercised through HTTP, proving the wiring (and
    the status-coherence refresh added in this milestone) survives the
    full stack."""
    from metis_app.api_litestar import create_app
    from metis_app.models.assistant_types import AssistantMemoryEntry
    from metis_app.services.assistant_companion import AssistantCompanionService
    from metis_app.services.assistant_repository import AssistantRepository
    from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator

    repo = AssistantRepository(tmp_path / "assistant_state.json")
    service = AssistantCompanionService(repository=repo)
    orchestrator = WorkspaceOrchestrator(assistant_service=service)

    # Seed one memory entry via the real repo path and prime the
    # status mirror so we can prove the refresh fires end-to-end.
    repo.add_memory_entry(
        AssistantMemoryEntry.from_payload(
            {
                "entry_id": "real-stack-1",
                "created_at": "2026-05-03T12:00:00Z",
                "kind": "reflection",
                "title": "Real stack head",
                "summary": "Real-stack summary.",
                "why": "Real-stack why.",
            }
        )
    )
    primed = repo.get_status()
    primed.latest_summary = "Real-stack summary."
    primed.latest_why = "Real-stack why."
    repo.update_status(primed)

    _patch_assistant_orchestrator(monkeypatch, orchestrator)

    with TestClient(app=create_app()) as client:
        response = client.delete("/v1/assistant/memory/real-stack-1")
        assert response.status_code == 200
        assert response.json() == {"ok": True}

    # Repo row is gone.
    assert repo.list_memory() == []
    # Status mirror was refreshed by the companion-service layer.
    status_after = repo.get_status()
    assert status_after.latest_summary == ""
    assert status_after.latest_why == ""


def test_gguf_validate_success_contract(tmp_path):
    """Test /v1/gguf/validate success payload contract."""
    from metis_app.api_litestar import create_app

    model_file = tmp_path / "Qwen2.5-7B-Q4_K_M.gguf"
    model_file.write_bytes(b"fake gguf content")

    with TestClient(app=create_app()) as client:
        response = client.post(
            "/v1/gguf/validate",
            json={"model_path": str(model_file)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["valid"] is True
        assert data["filename"] == "Qwen2.5-7B-Q4_K_M.gguf"
        assert data["quant"] == "Q4_K_M"
        assert "file_size_bytes" in data


# ---------------------------------------------------------------------------
# M24 Phase 1 — GET /v1/stars/clusters
# ---------------------------------------------------------------------------


def _patch_stars_orchestrator(monkeypatch, fake):
    """Swap ``WorkspaceOrchestrator`` on the stars route module."""
    from importlib import import_module

    stars_api = import_module("metis_app.api_litestar.routes.stars")
    monkeypatch.setattr(stars_api, "WorkspaceOrchestrator", lambda: fake)


def test_get_star_clusters_route_returns_assignments(monkeypatch):
    """Route returns 200 + a list of cluster assignment dicts.

    Mirrors the M23 pattern: monkeypatch the orchestrator so the
    route smoke test does not depend on the real embedding stack.
    """
    from metis_app.api_litestar import create_app

    captured: dict = {}

    class _FakeOrchestrator:
        def get_star_clusters(self, settings):
            captured["called_with"] = settings
            return [
                {
                    "star_id": "star1",
                    "cluster_id": 0,
                    "x": 0.42,
                    "y": -0.13,
                    "cluster_label": "",
                },
                {
                    "star_id": "star2",
                    "cluster_id": 0,
                    "x": -0.42,
                    "y": 0.13,
                    "cluster_label": "",
                },
            ]

    _patch_stars_orchestrator(monkeypatch, _FakeOrchestrator())

    with TestClient(app=create_app()) as client:
        response = client.get("/v1/stars/clusters")
        assert response.status_code == 200
        body = response.json()
        assert isinstance(body, list)
        assert len(body) == 2
        first = body[0]
        assert {"star_id", "cluster_id", "x", "y", "cluster_label"} <= set(first.keys())
        # Settings must have been forwarded through (load_settings always
        # returns at least an empty dict-like payload).
        assert "called_with" in captured


def test_get_star_clusters_route_empty_when_no_stars(monkeypatch):
    """No user stars -> 200 with an empty JSON list."""
    from metis_app.api_litestar import create_app

    class _FakeOrchestrator:
        def get_star_clusters(self, settings):
            # Mirrors the orchestrator's real empty-input contract.
            return []

    _patch_stars_orchestrator(monkeypatch, _FakeOrchestrator())

    with TestClient(app=create_app()) as client:
        response = client.get("/v1/stars/clusters")
        assert response.status_code == 200
        assert response.json() == []


