from __future__ import annotations

import json
from importlib import import_module
from unittest.mock import MagicMock

from litestar.testing import TestClient
import pytest

from metis_app.models.brain_graph import BrainGraph
from metis_app.services.index_service import build_index_bundle, save_index_bundle
from metis_app.services import nyx_catalog as nyx_catalog_module
from metis_app.services.nyx_catalog import NyxCatalogComponentNotFoundError
from metis_app.services.stream_replay import ReplayableRunStreamManager, StreamReplayStore
from metis_app.services.nyx_catalog import (
    NyxCatalogComponentDetail,
    NyxCatalogComponentSummary,
    NyxCatalogFileSummary,
    NyxCatalogSearchResult,
)
from metis_app.services.nyx_install_executor import (
    NyxInstallActionExecutionError,
    NyxInstallExecutionResult,
)
from metis_app.services.trace_store import TraceStore

api_app_module = import_module("metis_app.api_litestar")
from tests._litestar_helpers import (  # noqa: E402
    patch_workspace_orchestrator as _patch_workspace_orchestrator,
    patch_trace_store as _patch_trace_store,
    patch_execute_nyx_install_action as _patch_execute_nyx_install_action,
    patch_rag_stream_manager as _patch_rag_stream_manager,
)
from metis_app.api_litestar.routes import autonomous as _autonomous_module  # noqa: E402


@pytest.fixture(autouse=True)
def reset_default_nyx_catalog_state() -> None:
    nyx_catalog_module.load_curated_nyx_components.cache_clear()
    nyx_catalog_module.load_nyx_snapshot_component_details.cache_clear()
    nyx_catalog_module.load_optional_nyx_snapshot_component_details.cache_clear()
    nyx_catalog_module._DEFAULT_BROKER = None
    yield
    nyx_catalog_module.load_curated_nyx_components.cache_clear()
    nyx_catalog_module.load_nyx_snapshot_component_details.cache_clear()
    nyx_catalog_module.load_optional_nyx_snapshot_component_details.cache_clear()
    nyx_catalog_module._DEFAULT_BROKER = None


def test_healthz_returns_ok() -> None:
    client = TestClient(app=api_app_module.create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_build_index_uses_orchestrator(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())
    captured: dict[str, object] = {}

    class _Result:
        manifest_path = "/tmp/index/manifest.json"
        index_id = "idx-new"
        document_count = 3
        chunk_count = 9
        embedding_signature = "sig-1"
        vector_backend = "json"
        brain_pass = {"provider": "fallback", "placement": {"faculty_id": "knowledge"}}

    fake_orchestrator = MagicMock()

    def _fake_build_index(document_paths, settings, *, index_id=None, progress_cb=None):
        captured["document_paths"] = document_paths
        captured["settings"] = settings
        captured["index_id"] = index_id
        captured["progress_cb"] = progress_cb
        return _Result()

    fake_orchestrator.build_index.side_effect = _fake_build_index
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.post(
        "/v1/index/build",
        json={
            "document_paths": ["/tmp/doc-1.txt", "/tmp/doc-2.txt"],
            "settings": {"llm_provider": "mock"},
            "index_id": "idx-new",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["index_id"] == "idx-new"
    assert payload["manifest_path"] == "/tmp/index/manifest.json"
    assert payload["brain_pass"]["provider"] == "fallback"
    assert captured == {
        "document_paths": ["/tmp/doc-1.txt", "/tmp/doc-2.txt"],
        "settings": {"llm_provider": "mock"},
        "index_id": "idx-new",
        "progress_cb": None,
    }
    assert fake_orchestrator.build_index.call_count == 1


def test_stream_build_index_uses_orchestrator_and_progress_callback(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())
    captured: dict[str, object] = {}

    class _Result:
        manifest_path = "/tmp/index/manifest.json"
        index_id = "idx-stream"
        document_count = 4
        chunk_count = 12
        embedding_signature = "sig-stream"
        vector_backend = "json"
        brain_pass = {"provider": "fallback", "placement": {"faculty_id": "knowledge"}}

    fake_orchestrator = MagicMock()

    def _fake_build_index(document_paths, settings, *, index_id=None, progress_cb=None):
        captured["document_paths"] = document_paths
        captured["settings"] = settings
        captured["index_id"] = index_id
        captured["progress_cb"] = progress_cb
        if progress_cb is not None:
            progress_cb({"type": "progress", "run_id": "idx-stream", "percent": 50})
        return _Result()

    fake_orchestrator.build_index.side_effect = _fake_build_index
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.post(
        "/v1/index/build/stream",
        json={
            "document_paths": ["/tmp/doc-1.txt"],
            "settings": {"llm_provider": "mock"},
            "index_id": "idx-stream",
        },
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    frames = _parse_sse_frames(response.text)
    assert [payload["type"] for _, payload in frames] == [
        "build_started",
        "progress",
        "build_complete",
    ]
    assert frames[-1][1]["brain_pass"]["provider"] == "fallback"
    assert captured["document_paths"] == ["/tmp/doc-1.txt"]
    assert captured["settings"] == {"llm_provider": "mock"}
    assert captured["index_id"] == "idx-stream"
    assert callable(captured["progress_cb"])
    assert fake_orchestrator.build_index.call_count == 1


def test_delete_index_removes_manifest_directory_and_preserves_sources(tmp_path) -> None:
    client = TestClient(app=api_app_module.create_app())
    src = tmp_path / "notes.txt"
    src.write_text("Delete the METIS index but keep the source file.\n", encoding="utf-8")
    bundle = build_index_bundle([str(src)], {"embedding_provider": "mock", "vector_db_type": "json"})
    manifest_path = save_index_bundle(bundle, index_dir=tmp_path / "indexes")

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


def test_delete_index_removes_legacy_bundle_and_preserves_sources(tmp_path) -> None:
    client = TestClient(app=api_app_module.create_app())
    src = tmp_path / "legacy.txt"
    src.write_text("Legacy index bundles should delete through the API.\n", encoding="utf-8")
    bundle = build_index_bundle([str(src)], {"embedding_provider": "mock"})
    bundle_path = save_index_bundle(bundle, target_path=tmp_path / "legacy.metis-index.json")

    response = client.delete("/v1/index", params={"manifest_path": str(bundle_path)})

    assert response.status_code == 200
    assert response.json() == {
        "deleted": True,
        "manifest_path": str(bundle_path.resolve()),
        "index_id": bundle.index_id,
    }
    assert not bundle_path.exists()
    assert src.exists()


def test_delete_index_returns_404_for_missing_manifest(tmp_path) -> None:
    client = TestClient(app=api_app_module.create_app())
    missing_manifest = tmp_path / "missing" / "manifest.json"

    response = client.delete("/v1/index", params={"manifest_path": str(missing_manifest)})

    assert response.status_code == 404
    assert response.json()["detail"] == "Index not found."


def test_search_nyx_catalog_uses_orchestrator(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())
    captured: dict[str, object] = {}

    fake_orchestrator = MagicMock()

    def _fake_search_nyx_catalog(*, query="", limit=None):
        captured["query"] = query
        captured["limit"] = limit
        return NyxCatalogSearchResult(
            query=query,
            total=2,
            matched=1,
            curated_only=True,
            source="nyx_registry",
            items=(
                NyxCatalogComponentSummary(
                    component_name="glow-card",
                    title="Glow Card",
                    description="A glow card.",
                    curated_description="Interactive card with glow-based accent effects.",
                    component_type="registry:ui",
                    install_target="@nyx/glow-card",
                    registry_url="https://nyxui.com/r/glow-card.json",
                    schema_url="https://ui.shadcn.com/schema/registry-item.json",
                    source="nyx_registry",
                    source_repo="https://github.com/MihirJaiswal/nyxui",
                    required_dependencies=("clsx",),
                    dependencies=("clsx",),
                    dev_dependencies=(),
                    registry_dependencies=(),
                    file_count=1,
                    targets=("components/ui/glow-card.tsx",),
                ),
            ),
        )

    fake_orchestrator.search_nyx_catalog.side_effect = _fake_search_nyx_catalog
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.get("/v1/nyx/catalog?q=glow&limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "glow"
    assert payload["matched"] == 1
    assert payload["items"][0]["component_name"] == "glow-card"
    assert payload["items"][0]["install_target"] == "@nyx/glow-card"
    assert captured == {"query": "glow", "limit": 5}


def test_get_nyx_component_detail_uses_orchestrator(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())
    captured: dict[str, object] = {}

    fake_orchestrator = MagicMock()

    def _fake_get_nyx_component_detail(component_name: str):
        captured["component_name"] = component_name
        return NyxCatalogComponentDetail(
            component_name="glow-card",
            title="Glow Card",
            description="A glow card.",
            curated_description="Interactive card with glow-based accent effects.",
            component_type="registry:ui",
            install_target="@nyx/glow-card",
            registry_url="https://nyxui.com/r/glow-card.json",
            schema_url="https://ui.shadcn.com/schema/registry-item.json",
            source="nyx_registry",
            source_repo="https://github.com/MihirJaiswal/nyxui",
            required_dependencies=("clsx", "tailwind-merge"),
            dependencies=("clsx", "tailwind-merge"),
            dev_dependencies=(),
            registry_dependencies=(),
            file_count=1,
            targets=("components/ui/glow-card.tsx",),
            files=(
                NyxCatalogFileSummary(
                    path="registry/ui/glow-card.tsx",
                    file_type="registry:ui",
                    target="components/ui/glow-card.tsx",
                    content_bytes=128,
                ),
            ),
        )

    fake_orchestrator.get_nyx_component_detail.side_effect = _fake_get_nyx_component_detail
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.get("/v1/nyx/catalog/glow-card")

    assert response.status_code == 200
    payload = response.json()
    assert payload["component_name"] == "glow-card"
    assert payload["files"][0]["target"] == "components/ui/glow-card.tsx"
    assert captured == {"component_name": "glow-card"}


def test_get_nyx_component_detail_returns_404_for_unknown_component(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())

    fake_orchestrator = MagicMock()
    fake_orchestrator.get_nyx_component_detail.side_effect = (
        NyxCatalogComponentNotFoundError(
            "Unsupported NyxUI component: does-not-exist"
        )
    )
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.get("/v1/nyx/catalog/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Unsupported NyxUI component: does-not-exist"}
    fake_orchestrator.get_nyx_component_detail.assert_called_once_with(
        "does-not-exist"
    )


def test_nyx_catalog_endpoints_use_packaged_snapshot_without_live_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetch_calls: list[str] = []

    def fail_fetch(url: str) -> dict[str, object]:
        fetch_calls.append(url)
        raise AssertionError(f"Unexpected live Nyx fetch: {url}")

    monkeypatch.setattr(nyx_catalog_module, "_default_fetch_json", fail_fetch)
    client = TestClient(app=api_app_module.create_app())

    catalog_response = client.get("/v1/nyx/catalog", params={"q": "glow", "limit": 1})
    detail_response = client.get("/v1/nyx/catalog/glow-card")

    assert catalog_response.status_code == 200
    assert catalog_response.json()["items"][0]["component_name"] == "glow-card"
    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["component_name"] == "glow-card"
    assert detail_payload["install_target"] == "@nyx/glow-card"
    assert detail_payload["schema_url"] == "https://ui.shadcn.com/schema/registry-item.json"
    assert detail_payload["files"][0]["target"] == "components/ui/glow-card.tsx"
    assert detail_payload["previewable"] is True
    assert detail_payload["installable"] is True
    assert fetch_calls == []


def test_nyx_catalog_endpoints_expose_preview_only_snapshot_components_without_live_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetch_calls: list[str] = []

    def fail_fetch(url: str) -> dict[str, object]:
        fetch_calls.append(url)
        raise AssertionError(f"Unexpected live Nyx fetch: {url}")

    monkeypatch.setattr(nyx_catalog_module, "_default_fetch_json", fail_fetch)
    client = TestClient(app=api_app_module.create_app())

    catalog_response = client.get("/v1/nyx/catalog", params={"q": "marquee", "limit": 5})
    detail_response = client.get("/v1/nyx/catalog/marquee")

    assert catalog_response.status_code == 200
    catalog_payload = catalog_response.json()
    assert catalog_payload["matched"] == 1
    assert catalog_payload["items"][0]["component_name"] == "marquee"
    assert catalog_payload["items"][0]["previewable"] is True
    assert catalog_payload["items"][0]["installable"] is False
    assert catalog_payload["items"][0]["review_status"] == "preview"

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["component_name"] == "marquee"
    assert detail_payload["previewable"] is True
    assert detail_payload["installable"] is False
    assert detail_payload["review_status"] == "preview"
    assert fetch_calls == []


def test_query_direct_happy_path(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())
    captured: dict[str, object] = {}

    class _Result:
        run_id = "run-xyz"
        answer_text = "Mock/Test Backend: hello"
        selected_mode = "Q&A"
        llm_provider = "mock"
        llm_model = "mock-model"

    fake_orchestrator = MagicMock()

    def _fake_run_direct_query(req, *, session_id=""):
        captured["prompt"] = req.prompt
        captured["session_id"] = session_id
        return _Result()

    fake_orchestrator.run_direct_query.side_effect = _fake_run_direct_query
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.post(
        "/v1/query/direct",
        json={
            "prompt": "Say hello",
            "settings": {"llm_provider": "mock", "selected_mode": "Q&A"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer_text"] == "Mock/Test Backend: hello"
    assert payload["selected_mode"] == "Q&A"
    assert payload["run_id"] == "run-xyz"
    assert captured == {"prompt": "Say hello", "session_id": ""}


def test_query_direct_serializes_artifacts(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())

    class _Result:
        run_id = "run-nyx-direct"
        answer_text = "Use Glow Card."
        selected_mode = "Q&A"
        llm_provider = "mock"
        llm_model = "mock-model"
        artifacts = [
            {
                "id": "nyx_component_selection",
                "type": "nyx_component_selection",
                "summary": "Nyx matched 1 component candidate.",
                "path": "nyx/component-selection",
                "mime_type": "application/vnd.metis.nyx+json",
                "payload": {
                    "schema_version": "1.0",
                    "query": "Build a glowing card",
                    "intent_type": "interface_pattern_selection",
                    "confidence": 0.81,
                    "matched_signals": ["pattern:card", "interaction:glow"],
                    "selected_components": [
                        {
                            "component_name": "glow-card",
                            "title": "Glow Card",
                            "install_target": "@nyx/glow-card",
                            "registry_url": "https://nyxui.com/r/glow-card.json",
                        }
                    ],
                },
                "payload_bytes": 512,
                "payload_truncated": False,
            }
        ]

    fake_orchestrator = MagicMock()
    fake_orchestrator.run_direct_query.return_value = _Result()
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.post(
        "/v1/query/direct",
        json={
            "prompt": "Build a glowing card",
            "settings": {"llm_provider": "mock", "selected_mode": "Q&A"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["artifacts"][0]["type"] == "nyx_component_selection"
    assert payload["artifacts"][0]["payload"]["schema_version"] == "1.0"
    assert payload["artifacts"][0]["payload"]["selected_components"][0]["component_name"] == "glow-card"


def test_query_direct_serializes_nyx_install_actions(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())

    class _Result:
        run_id = "run-nyx-action"
        answer_text = "Use Glow Card."
        selected_mode = "Q&A"
        llm_provider = "mock"
        llm_model = "mock-model"
        actions = [
            {
                "action_id": "nyx-install:abc123",
                "action_type": "nyx_install",
                "label": "Approve Nyx install proposal",
                "summary": "Approve installing Glow Card.",
                "requires_approval": True,
                "run_action_endpoint": "/v1/runs/run-nyx-action/actions",
                "payload": {
                    "action_id": "nyx-install:abc123",
                    "action_type": "nyx_install",
                    "proposal_token": "nyx-proposal:abc123",
                    "component_count": 1,
                    "component_names": ["glow-card"],
                },
                "proposal": {
                    "schema_version": "1.0",
                    "proposal_token": "nyx-proposal:abc123",
                    "source": "nyx_runtime",
                    "run_id": "run-nyx-action",
                    "query": "Design a glowing card.",
                    "intent_type": "interface_pattern_selection",
                    "matched_signals": ["explicit_nyx", "pattern:card"],
                    "component_names": ["glow-card"],
                    "component_count": 1,
                    "components": [
                        {
                            "component_name": "glow-card",
                            "title": "Glow Card",
                            "description": "Interactive card with glow-based accent effects.",
                            "curated_description": "Interactive card with glow-based accent effects.",
                            "component_type": "registry:ui",
                            "install_target": "@nyx/glow-card",
                            "registry_url": "https://nyxui.com/r/glow-card.json",
                            "source_repo": "https://github.com/MihirJaiswal/nyxui",
                            "required_dependencies": ["clsx", "tailwind-merge"],
                            "dependencies": ["clsx", "tailwind-merge"],
                            "dev_dependencies": [],
                            "registry_dependencies": [],
                            "file_count": 1,
                            "targets": ["components/ui/glow-card.tsx"],
                            "review_status": "installable",
                            "previewable": True,
                            "installable": True,
                            "install_path_policy": "metis_nyx_targets_v1",
                            "install_path_safe": True,
                            "install_path_issues": [],
                            "audit_issues": [],
                        }
                    ],
                },
            }
        ]

    fake_orchestrator = MagicMock()
    fake_orchestrator.run_direct_query.return_value = _Result()
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.post(
        "/v1/query/direct",
        json={
            "prompt": "Design a glowing card",
            "settings": {"llm_provider": "mock", "selected_mode": "Q&A"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["actions"][0]["action_type"] == "nyx_install"
    assert payload["actions"][0]["payload"]["proposal_token"] == "nyx-proposal:abc123"
    assert payload["actions"][0]["proposal"]["component_names"] == ["glow-card"]


def _make_persisted_nyx_action(
    *,
    action_id: str = "nyx-install:abc123",
    proposal_token: str = "nyx-proposal:abc123",
) -> dict[str, object]:
    return {
        "action_id": action_id,
        "action_type": "nyx_install",
        "label": "Approve Nyx install proposal",
        "summary": "Approve installing Glow Card.",
        "requires_approval": True,
        "run_action_endpoint": "/v1/runs/run-nyx-action/actions",
        "payload": {
            "action_id": action_id,
            "action_type": "nyx_install",
            "proposal_token": proposal_token,
            "component_count": 1,
            "component_names": ["glow-card"],
        },
        "proposal": {
            "schema_version": "1.0",
            "proposal_token": proposal_token,
            "source": "nyx_runtime",
            "run_id": "run-nyx-action",
            "query": "Design a glowing card.",
            "intent_type": "interface_pattern_selection",
            "matched_signals": ["explicit_nyx", "pattern:card"],
            "component_names": ["glow-card"],
            "component_count": 1,
            "components": [
                {
                    "component_name": "glow-card",
                    "title": "Glow Card",
                    "description": "Interactive card with glow-based accent effects.",
                    "curated_description": "Interactive card with glow-based accent effects.",
                    "component_type": "registry:ui",
                    "install_target": "@nyx/glow-card",
                    "registry_url": "https://nyxui.com/r/glow-card.json",
                    "source_repo": "https://github.com/MihirJaiswal/nyxui",
                    "required_dependencies": ["clsx", "tailwind-merge"],
                    "dependencies": ["clsx", "tailwind-merge"],
                    "dev_dependencies": [],
                    "registry_dependencies": [],
                    "file_count": 1,
                    "targets": ["components/ui/glow-card.tsx"],
                    "review_status": "installable",
                    "previewable": True,
                    "installable": True,
                    "install_path_policy": "metis_nyx_targets_v1",
                    "install_path_safe": True,
                    "install_path_issues": [],
                    "audit_issues": [],
                }
            ],
        },
    }


def test_run_action_infers_nyx_approval_without_action_type(monkeypatch, tmp_path) -> None:
    trace_store = TraceStore(tmp_path / "traces")
    persisted_action = _make_persisted_nyx_action()
    trace_store.append_event(
        run_id="run-nyx-action",
        stage="synthesis",
        event_type="final",
        payload={"actions": [persisted_action]},
    )

    def fake_execute_nyx_install_action(**_kwargs):
        return NyxInstallExecutionResult(
            action_id="nyx-install:abc123",
            proposal_token="nyx-proposal:abc123",
            component_names=("glow-card",),
            component_count=1,
            proposal=dict(persisted_action["proposal"]),
            command=("node", "scripts/add-nyx-component.mjs", "--", "glow-card"),
            cwd=str(tmp_path),
            returncode=0,
            stdout_excerpt="installed glow-card",
            stderr_excerpt="",
        )

    _patch_trace_store(monkeypatch, lambda: trace_store)
    _patch_execute_nyx_install_action(monkeypatch, fake_execute_nyx_install_action)
    client = TestClient(app=api_app_module.create_app())

    response = client.post(
        "/v1/runs/run-nyx-action/actions",
        json={
            "approved": True,
            "payload": {
                "action_id": "nyx-install:abc123",
                "proposal_token": "nyx-proposal:abc123",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["action_id"] == "nyx-install:abc123"
    assert payload["action_type"] == "nyx_install"
    assert payload["proposal_token"] == "nyx-proposal:abc123"
    assert payload["status"] == "completed"
    assert payload["execution_status"] == "completed"


def test_run_action_infers_nyx_decline_without_action_type(monkeypatch, tmp_path) -> None:
    trace_store = TraceStore(tmp_path / "traces")
    persisted_action = _make_persisted_nyx_action()
    trace_store.append_event(
        run_id="run-nyx-action",
        stage="synthesis",
        event_type="final",
        payload={"actions": [persisted_action]},
    )

    _patch_trace_store(monkeypatch, lambda: trace_store)
    client = TestClient(app=api_app_module.create_app())

    response = client.post(
        "/v1/runs/run-nyx-action/actions",
        json={"approved": False},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["approved"] is False
    assert payload["status"] == "declined"
    assert payload["action_id"] == "nyx-install:abc123"
    assert payload["action_type"] == "nyx_install"
    assert payload["proposal_token"] == "nyx-proposal:abc123"
    assert payload["execution_status"] == "declined"

    run_events = trace_store.read_run_events("run-nyx-action")
    submitted_event = next(
        event for event in run_events if event["event_type"] == "nyx_install_action_submitted"
    )
    assert submitted_event["payload"]["approved"] is False
    assert submitted_event["payload"]["status"] == "declined"
    assert submitted_event["payload"]["execution_status"] == "declined"


def test_run_action_returns_clear_nyx_mismatch_status_without_action_type(
    monkeypatch,
    tmp_path,
) -> None:
    trace_store = TraceStore(tmp_path / "traces")
    persisted_action = _make_persisted_nyx_action()
    trace_store.append_event(
        run_id="run-nyx-action",
        stage="synthesis",
        event_type="final",
        payload={"actions": [persisted_action]},
    )
    captured: dict[str, object] = {}

    def fake_execute_nyx_install_action(**kwargs):
        captured.update(kwargs)
        raise NyxInstallActionExecutionError(
            "Nyx install proposal token no longer matches the persisted proposal.",
            code="proposal_mismatch",
            metadata={
                "proposal_token": "nyx-proposal:abc123",
                "requested_proposal_token": "nyx-proposal:mismatch",
            },
        )

    _patch_trace_store(monkeypatch, lambda: trace_store)
    _patch_execute_nyx_install_action(monkeypatch, fake_execute_nyx_install_action)
    client = TestClient(app=api_app_module.create_app())

    response = client.post(
        "/v1/runs/run-nyx-action/actions",
        json={
            "approved": True,
            "payload": {
                "action_id": "nyx-install:abc123",
                "proposal_token": "nyx-proposal:mismatch",
            },
        },
    )

    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Nyx install proposal token no longer matches the persisted proposal."
    )
    assert captured["action_id"] == "nyx-install:abc123"
    assert captured["proposal_token"] == "nyx-proposal:mismatch"

    run_events = trace_store.read_run_events("run-nyx-action")
    submitted_event = next(
        event for event in run_events if event["event_type"] == "nyx_install_action_submitted"
    )
    assert submitted_event["payload"]["status"] == "error"
    assert submitted_event["payload"]["execution_status"] == "failed"
    assert submitted_event["payload"]["failure_code"] == "proposal_mismatch"


def test_run_action_revalidates_persisted_nyx_install_proposal(monkeypatch, tmp_path) -> None:
    trace_store = TraceStore(tmp_path / "traces")
    persisted_action = {
        "action_id": "nyx-install:abc123",
        "action_type": "nyx_install",
        "label": "Approve Nyx install proposal",
        "summary": "Approve installing Glow Card.",
        "requires_approval": True,
        "run_action_endpoint": "/v1/runs/run-nyx-action/actions",
        "payload": {
            "action_id": "nyx-install:abc123",
            "action_type": "nyx_install",
            "proposal_token": "nyx-proposal:abc123",
            "component_count": 1,
            "component_names": ["glow-card"],
        },
        "proposal": {
            "schema_version": "1.0",
            "proposal_token": "nyx-proposal:abc123",
            "source": "nyx_runtime",
            "run_id": "run-nyx-action",
            "query": "Design a glowing card.",
            "intent_type": "interface_pattern_selection",
            "matched_signals": ["explicit_nyx", "pattern:card"],
            "component_names": ["glow-card"],
            "component_count": 1,
            "components": [
                {
                    "component_name": "glow-card",
                    "title": "Glow Card",
                    "description": "Interactive card with glow-based accent effects.",
                    "curated_description": "Interactive card with glow-based accent effects.",
                    "component_type": "registry:ui",
                    "install_target": "@nyx/glow-card",
                    "registry_url": "https://nyxui.com/r/glow-card.json",
                    "source_repo": "https://github.com/MihirJaiswal/nyxui",
                    "required_dependencies": ["clsx", "tailwind-merge"],
                    "dependencies": ["clsx", "tailwind-merge"],
                    "dev_dependencies": [],
                    "registry_dependencies": [],
                    "file_count": 1,
                    "targets": ["components/ui/glow-card.tsx"],
                    "review_status": "installable",
                    "previewable": True,
                    "installable": True,
                    "install_path_policy": "metis_nyx_targets_v1",
                    "install_path_safe": True,
                    "install_path_issues": [],
                    "audit_issues": [],
                }
            ],
        },
    }
    trace_store.append_event(
        run_id="run-nyx-action",
        stage="synthesis",
        event_type="final",
        payload={"actions": [persisted_action]},
    )

    def fake_execute_nyx_install_action(**_kwargs):
        return NyxInstallExecutionResult(
            action_id="nyx-install:abc123",
            proposal_token="nyx-proposal:abc123",
            component_names=("glow-card",),
            component_count=1,
            proposal=dict(persisted_action["proposal"]),
            command=("node", "scripts/add-nyx-component.mjs", "--", "glow-card"),
            cwd=str(tmp_path),
            returncode=0,
            stdout_excerpt="installed glow-card",
            stderr_excerpt="",
        )

    _patch_trace_store(monkeypatch, lambda: trace_store)
    _patch_execute_nyx_install_action(monkeypatch, fake_execute_nyx_install_action)
    client = TestClient(app=api_app_module.create_app())

    response = client.post(
        "/v1/runs/run-nyx-action/actions",
        json={
            "approved": True,
            "payload": {
                "action_id": "nyx-install:abc123",
                "action_type": "nyx_install",
                "proposal_token": "nyx-proposal:abc123",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["action_id"] == "nyx-install:abc123"
    assert payload["proposal_token"] == "nyx-proposal:abc123"
    assert payload["status"] == "completed"
    assert payload["execution_status"] == "completed"
    assert payload["proposal"]["component_names"] == ["glow-card"]
    assert payload["installer"]["returncode"] == 0

    run_events = trace_store.read_run_events("run-nyx-action")
    submitted_event = next(
        event for event in run_events if event["event_type"] == "nyx_install_action_submitted"
    )
    assert submitted_event["payload"]["status"] == "success"
    assert submitted_event["payload"]["execution_status"] == "completed"
    assert submitted_event["payload"]["returncode"] == 0


def test_run_action_records_failed_nyx_install_execution(monkeypatch, tmp_path) -> None:
    trace_store = TraceStore(tmp_path / "traces")
    trace_store.append_event(
        run_id="run-nyx-action",
        stage="synthesis",
        event_type="final",
        payload={
            "actions": [
                {
                    "action_id": "nyx-install:abc123",
                    "action_type": "nyx_install",
                    "label": "Approve Nyx install proposal",
                    "summary": "Approve installing Glow Card.",
                    "requires_approval": True,
                    "run_action_endpoint": "/v1/runs/run-nyx-action/actions",
                    "payload": {
                        "action_id": "nyx-install:abc123",
                        "action_type": "nyx_install",
                        "proposal_token": "nyx-proposal:abc123",
                        "component_count": 1,
                        "component_names": ["glow-card"],
                    },
                    "proposal": {
                        "schema_version": "1.0",
                        "proposal_token": "nyx-proposal:abc123",
                        "source": "nyx_runtime",
                        "run_id": "run-nyx-action",
                        "query": "Design a glowing card.",
                        "intent_type": "interface_pattern_selection",
                        "matched_signals": ["explicit_nyx", "pattern:card"],
                        "component_names": ["glow-card"],
                        "component_count": 1,
                        "components": [{"component_name": "glow-card"}],
                    },
                }
            ]
        },
    )

    def fake_execute_nyx_install_action(**_kwargs):
        raise NyxInstallActionExecutionError(
            "Nyx install proposal is stale and must be regenerated.",
            code="stale_proposal",
            metadata={"current_action_id": "nyx-install:def456"},
        )

    _patch_trace_store(monkeypatch, lambda: trace_store)
    _patch_execute_nyx_install_action(monkeypatch, fake_execute_nyx_install_action)
    client = TestClient(app=api_app_module.create_app())

    response = client.post(
        "/v1/runs/run-nyx-action/actions",
        json={
            "approved": True,
            "payload": {
                "action_id": "nyx-install:abc123",
                "action_type": "nyx_install",
                "proposal_token": "nyx-proposal:abc123",
            },
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "Nyx install proposal is stale and must be regenerated."

    run_events = trace_store.read_run_events("run-nyx-action")
    submitted_event = next(
        event for event in run_events if event["event_type"] == "nyx_install_action_submitted"
    )
    assert submitted_event["payload"]["status"] == "error"
    assert submitted_event["payload"]["execution_status"] == "failed"
    assert submitted_event["payload"]["failure_code"] == "stale_proposal"


def test_query_rag_forwards_session_id_to_orchestrator(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())
    captured: dict[str, object] = {}

    class _Result:
        run_id = "run-rag"
        answer_text = "rag answer"
        sources: list[dict[str, object]] = []
        context_block = "context"
        top_score = 0.42
        selected_mode = "Q&A"
        retrieval_plan = {}
        fallback = {}

    fake_orchestrator = MagicMock()

    def _fake_run_rag_query(req, *, session_id=""):
        captured["question"] = req.question
        captured["session_id"] = session_id
        return _Result()

    fake_orchestrator.run_rag_query.side_effect = _fake_run_rag_query
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.post(
        "/v1/query/rag",
        json={
            "manifest_path": "/tmp/fake/manifest.json",
            "question": "What is METIS?",
            "session_id": "s1",
            "settings": {"llm_provider": "mock", "selected_mode": "Q&A"},
        },
    )

    assert response.status_code == 200
    assert captured["question"] == "What is METIS?"
    assert captured["session_id"] == "s1"
    assert fake_orchestrator.run_rag_query.call_count == 1


def test_query_rag_serializes_retrieval_plan_and_fallback(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())

    class _Result:
        run_id = "run-rag-plan"
        answer_text = "rag answer"
        sources: list[dict[str, object]] = []
        context_block = "context"
        top_score = 0.42
        selected_mode = "Q&A"
        retrieval_plan = {"stages": [{"stage_type": "retrieval_complete", "payload": {}}]}
        fallback = {"triggered": False, "strategy": "synthesize_anyway"}

    fake_orchestrator = MagicMock()
    fake_orchestrator.run_rag_query.return_value = _Result()
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.post(
        "/v1/query/rag",
        json={
            "manifest_path": "/tmp/fake/manifest.json",
            "question": "What is METIS?",
            "settings": {"llm_provider": "mock", "selected_mode": "Q&A"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["retrieval_plan"]["stages"][0]["stage_type"] == "retrieval_complete"
    assert payload["fallback"]["strategy"] == "synthesize_anyway"


def test_search_knowledge_forwards_session_id_to_orchestrator(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())
    captured: dict[str, object] = {}

    class _Result:
        run_id = "run-search"
        summary_text = "Found 2 passages."
        sources = [{"sid": "S1", "source": "doc", "snippet": "evidence"}]
        context_block = "context"
        top_score = 0.81
        selected_mode = "Knowledge Search"
        retrieval_plan = {"stages": [{"stage_type": "retrieval_complete", "payload": {}}]}
        fallback = {"triggered": False, "strategy": "synthesize_anyway"}

    fake_orchestrator = MagicMock()

    def _fake_run_knowledge_search(req, *, session_id=""):
        captured["question"] = req.question
        captured["session_id"] = session_id
        return _Result()

    fake_orchestrator.run_knowledge_search.side_effect = _fake_run_knowledge_search
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.post(
        "/v1/search/knowledge",
        json={
            "manifest_path": "/tmp/fake/manifest.json",
            "question": "Find evidence",
            "session_id": "s-search",
            "settings": {"llm_provider": "mock", "selected_mode": "Knowledge Search"},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary_text"] == "Found 2 passages."
    assert payload["retrieval_plan"]["stages"][0]["stage_type"] == "retrieval_complete"
    assert payload["fallback"]["strategy"] == "synthesize_anyway"
    assert captured == {"question": "Find evidence", "session_id": "s-search"}


def test_query_direct_forwards_session_id_to_orchestrator(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())
    captured: dict[str, object] = {}

    class _Result:
        run_id = "run-direct"
        answer_text = "direct answer"
        selected_mode = "Tutor"
        llm_provider = "mock"
        llm_model = "mock-model"

    fake_orchestrator = MagicMock()

    def _fake_run_direct_query(req, *, session_id=""):
        captured["prompt"] = req.prompt
        captured["session_id"] = session_id
        return _Result()

    fake_orchestrator.run_direct_query.side_effect = _fake_run_direct_query
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.post(
        "/v1/query/direct",
        json={
            "prompt": "Say hello",
            "session_id": "s2",
            "settings": {"llm_provider": "mock", "selected_mode": "Tutor"},
        },
    )

    assert response.status_code == 200
    assert captured["prompt"] == "Say hello"
    assert captured["session_id"] == "s2"
    assert fake_orchestrator.run_direct_query.call_count == 1


def _set_stream_manager(monkeypatch, tmp_path) -> None:
    manager = ReplayableRunStreamManager(StreamReplayStore(tmp_path / "traces"))
    _patch_rag_stream_manager(monkeypatch, manager)


def _parse_sse_frames(body: str) -> list[tuple[int | None, dict[str, object]]]:
    frames: list[tuple[int | None, dict[str, object]]] = []
    current_id: int | None = None
    current_payload: dict[str, object] | None = None
    for line in body.splitlines():
        if line.startswith("id: "):
            current_id = int(line[len("id: "):])
        elif line.startswith("data: "):
            current_payload = json.loads(line[len("data: "):])
        elif not line.strip() and current_payload is not None:
            frames.append((current_id, current_payload))
            current_id = None
            current_payload = None
    if current_payload is not None:
        frames.append((current_id, current_payload))
    return frames


def test_stream_rag_happy_path_includes_sse_ids(monkeypatch, tmp_path) -> None:
    _set_stream_manager(monkeypatch, tmp_path)
    client = TestClient(app=api_app_module.create_app())
    fake_orchestrator = MagicMock()

    def _fake_stream_rag_query(req, *, session_id=""):
        yield {"type": "run_started", "run_id": "r1"}
        yield {"type": "token", "run_id": "r1", "text": "hello"}
        yield {"type": "final", "run_id": "r1", "answer_text": "hello", "sources": []}

    fake_orchestrator.stream_rag_query.side_effect = _fake_stream_rag_query
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.post(
        "/v1/query/rag/stream",
        json={
            "manifest_path": "/tmp/fake/manifest.json",
            "question": "What is METIS?",
            "settings": {
                "llm_provider": "mock",
                "embedding_provider": "mock",
                "vector_db_type": "json",
            },
        },
    )

    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    frames = _parse_sse_frames(response.text)
    data_line_types = [
        json.loads(line[len("data: "):])["type"]
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]

    assert [frame_id for frame_id, _ in frames] == [1, 2, 3]
    assert [payload["type"] for _, payload in frames] == ["run_started", "token", "final"]
    assert data_line_types == ["run_started", "token", "final"]
    run_started = frames[0][1]
    assert run_started["event_type"] == "run_started"
    assert str(run_started["event_id"]).endswith(":1")
    assert run_started["timestamp"]
    assert run_started["status"] == "started"
    assert run_started["lifecycle"] == "run"
    assert run_started["context"]["run_id"] == run_started["run_id"]
    assert isinstance(run_started["payload"], dict)


def test_stream_rag_replays_only_events_after_last_event_id(monkeypatch, tmp_path) -> None:
    _set_stream_manager(monkeypatch, tmp_path)
    client = TestClient(app=api_app_module.create_app())
    fake_orchestrator = MagicMock()

    def _fake_stream_rag_query(req, *, session_id=""):
        yield {"type": "run_started", "run_id": "r1"}
        yield {"type": "token", "run_id": "r1", "text": "hello"}
        yield {"type": "final", "run_id": "r1", "answer_text": "hello", "sources": []}

    fake_orchestrator.stream_rag_query.side_effect = _fake_stream_rag_query
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    first = client.post(
        "/v1/query/rag/stream",
        json={
            "manifest_path": "/tmp/fake/manifest.json",
            "question": "What is METIS?",
            "run_id": "r1",
            "settings": {
                "llm_provider": "mock",
                "embedding_provider": "mock",
                "vector_db_type": "json",
            },
        },
    )
    assert first.status_code == 200

    replay = client.post(
        "/v1/query/rag/stream",
        headers={"Last-Event-ID": "1"},
        json={
            "manifest_path": "/tmp/fake/manifest.json",
            "question": "What is METIS?",
            "run_id": "r1",
            "settings": {
                "llm_provider": "mock",
                "embedding_provider": "mock",
                "vector_db_type": "json",
            },
        },
    )

    assert replay.status_code == 200
    replay_frames = _parse_sse_frames(replay.text)

    assert [frame_id for frame_id, _ in replay_frames] == [2, 3]
    assert [payload["type"] for _, payload in replay_frames] == ["token", "final"]


def test_stream_rag_reconnect_ignores_unrelated_trace_rows(monkeypatch, tmp_path) -> None:
    _set_stream_manager(monkeypatch, tmp_path)
    client = TestClient(app=api_app_module.create_app())
    fake_orchestrator = MagicMock()
    fake_orchestrator.stream_rag_query.return_value = iter(())
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    TraceStore(tmp_path / "traces").append_event(
        run_id="run-with-trace-only",
        stage="synthesis",
        event_type="llm_response",
        payload={"response_preview": "trace-only"},
    )

    response = client.post(
        "/v1/query/rag/stream",
        headers={"Last-Event-ID": "1"},
        json={
            "manifest_path": "/tmp/fake/manifest.json",
            "question": "What is METIS?",
            "run_id": "run-with-trace-only",
            "settings": {
                "llm_provider": "mock",
                "embedding_provider": "mock",
                "vector_db_type": "json",
            },
        },
    )

    assert response.status_code == 200
    assert response.text == ""


def test_stream_rag_error_event(monkeypatch, tmp_path) -> None:
    _set_stream_manager(monkeypatch, tmp_path)
    client = TestClient(app=api_app_module.create_app())
    fake_orchestrator = MagicMock()

    def _fake_stream_rag_query(req, *, session_id=""):
        yield {"type": "error", "run_id": "r0", "message": "question must not be empty."}

    fake_orchestrator.stream_rag_query.side_effect = _fake_stream_rag_query
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.post(
        "/v1/query/rag/stream",
        json={
            "manifest_path": "/tmp/fake/manifest.json",
            "question": "",
            "settings": {},
        },
    )

    assert response.status_code == 200
    frames = _parse_sse_frames(response.text)

    assert [frame_id for frame_id, _ in frames] == [1]
    assert [payload["type"] for _, payload in frames] == ["error"]


def test_brain_graph_returns_nodes_and_edges(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())
    fake_orchestrator = MagicMock()
    fake_orchestrator.get_workspace_graph.return_value = BrainGraph().build_from_indexes_and_sessions([], [])
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.get("/v1/brain/graph")

    assert response.status_code == 200
    payload = response.json()
    assert "nodes" in payload
    assert "edges" in payload
    # Root categories are always present
    node_ids = {n["node_id"] for n in payload["nodes"]}
    assert "category:brain" in node_ids
    assert "category:indexes" in node_ids
    assert "category:sessions" in node_ids
    assert all("weight" in edge for edge in payload["edges"])


def test_brain_scaffold_returns_topology_payload(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())
    fake_orchestrator = MagicMock()
    fake_orchestrator.get_workspace_graph.return_value = BrainGraph().build_from_indexes_and_sessions([], [])
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.get("/v1/brain/scaffold")

    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {
        "betti_0",
        "betti_1",
        "h0_pairs",
        "h1_pairs",
        "scaffold_edges",
        "summary",
    }
    assert payload["betti_0"] >= 1
    assert payload["betti_1"] >= 0


def test_ui_telemetry_endpoint_accepts_valid_events(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())
    captured: dict[str, object] = {}

    class _FakeOrchestrator:
        def ingest_ui_telemetry_events(self, events):
            captured["events"] = events
            return len(events)

    _patch_workspace_orchestrator(monkeypatch, lambda: _FakeOrchestrator())

    response = client.post(
        "/v1/telemetry/ui",
        json={
            "events": [
                {
                    "event_name": "artifact_render_success",
                    "source": "chat_artifact_boundary",
                    "occurred_at": "2026-03-23T12:00:00Z",
                    "run_id": "run-telemetry",
                    "session_id": "session-1",
                    "message_id": "message-1",
                    "is_streaming": False,
                    "payload": {
                        "artifact_count": 1,
                        "artifact_types": ["timeline"],
                        "artifact_ids": ["artifact-1"],
                        "renderer": "default",
                    },
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": 1}
    persisted = captured["events"]
    assert isinstance(persisted, list)
    assert persisted[0]["event_name"] == "artifact_render_success"
    assert persisted[0]["payload"]["artifact_types"] == ["timeline"]


def test_ui_telemetry_endpoint_rejects_invalid_payload(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())
    fake_orchestrator = MagicMock()
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.post(
        "/v1/telemetry/ui",
        json={
            "events": [
                {
                    "event_name": "artifact_render_success",
                    "source": "chat_artifact_boundary",
                    "occurred_at": "2026-03-23T12:00:00Z",
                    "run_id": "run-telemetry",
                    "payload": {
                        "artifact_count": 1,
                        "artifact_types": ["timeline"],
                        "artifact_ids": ["artifact-1"],
                        "renderer": "default",
                        "unexpected": True,
                    },
                }
            ]
        },
    )

    assert response.status_code == 422
    fake_orchestrator.ingest_ui_telemetry_events.assert_not_called()


def test_ui_telemetry_endpoint_accepts_runtime_lifecycle_events(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())
    captured: dict[str, object] = {}

    class _FakeOrchestrator:
        def ingest_ui_telemetry_events(self, events):
            captured["events"] = events
            return len(events)

    _patch_workspace_orchestrator(monkeypatch, lambda: _FakeOrchestrator())

    response = client.post(
        "/v1/telemetry/ui",
        json={
            "events": [
                {
                    "event_name": "artifact_runtime_attempt",
                    "source": "chat_artifact_boundary",
                    "occurred_at": "2026-03-23T12:00:00Z",
                    "run_id": "run-telemetry",
                    "payload": {
                        "artifact_index": 0,
                        "artifact_id": "artifact-1",
                        "artifact_type": "timeline",
                    },
                },
                {
                    "event_name": "artifact_runtime_skipped",
                    "source": "chat_artifact_boundary",
                    "occurred_at": "2026-03-23T12:00:01Z",
                    "run_id": "run-telemetry",
                    "payload": {
                        "artifact_index": 1,
                        "artifact_type": "metric_cards",
                        "reason": "runtime_disabled",
                    },
                },
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": 2}
    persisted = captured["events"]
    assert isinstance(persisted, list)
    assert persisted[0]["event_name"] == "artifact_runtime_attempt"
    assert persisted[1]["event_name"] == "artifact_runtime_skipped"


def test_ui_telemetry_endpoint_rejects_malformed_json() -> None:
    client = TestClient(app=api_app_module.create_app())

    response = client.post(
        "/v1/telemetry/ui",
        content='{"events": [',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 400


def test_ui_telemetry_endpoint_requires_auth_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("METIS_API_TOKEN", "secret-token")
    client = TestClient(app=api_app_module.create_app())

    response = client.post(
        "/v1/telemetry/ui",
        json={
            "events": [
                {
                    "event_name": "artifact_boundary_flag_state",
                    "source": "chat_artifact_boundary",
                    "occurred_at": "2026-03-23T12:00:00Z",
                    "run_id": "run-telemetry",
                    "payload": {"state": "enabled"},
                }
            ]
        },
    )

    assert response.status_code == 401


def test_ui_telemetry_endpoint_accepts_auth_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("METIS_API_TOKEN", "secret-token")
    client = TestClient(app=api_app_module.create_app())
    captured: dict[str, object] = {}

    class _FakeOrchestrator:
        def ingest_ui_telemetry_events(self, events):
            captured["events"] = events
            return len(events)

    _patch_workspace_orchestrator(monkeypatch, lambda: _FakeOrchestrator())

    response = client.post(
        "/v1/telemetry/ui",
        headers={"Authorization": "Bearer secret-token"},
        json={
            "events": [
                {
                    "event_name": "artifact_boundary_flag_state",
                    "source": "chat_artifact_boundary",
                    "occurred_at": "2026-03-23T12:00:00Z",
                    "run_id": "run-telemetry",
                    "payload": {"state": "enabled"},
                }
            ]
        },
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": 1}
    persisted = captured["events"]
    assert isinstance(persisted, list)
    assert persisted[0]["event_name"] == "artifact_boundary_flag_state"


def test_ui_telemetry_endpoint_rejects_oversized_request() -> None:
    client = TestClient(app=api_app_module.create_app())
    response = client.post(
        "/v1/telemetry/ui",
        content="x" * 20_000,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413


def test_ui_telemetry_summary_endpoint_returns_structured_summary(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())

    class _FakeOrchestrator:
        def get_ui_telemetry_summary(self, *, window_hours=24, limit=50_000):
            assert window_hours == 24
            assert limit == 999
            return {
                "window_hours": 24,
                "generated_at": "2026-03-23T12:00:00+00:00",
                "sampled_event_count": 12,
                "metrics": {
                    "exposure_count": 10,
                    "render_attempt_count": 10,
                    "render_success_rate": 0.9,
                    "render_failure_rate": 0.1,
                    "fallback_rate_by_reason": {
                        "feature_disabled": 0.0,
                        "no_artifacts": 0.0,
                        "invalid_payload": 0.1,
                        "render_error": 0.0,
                    },
                    "interaction_rate": 0.2,
                    "runtime_attempt_rate": 0.5,
                    "runtime_success_rate": 0.8,
                    "runtime_failure_rate": 0.2,
                    "runtime_skip_mix": {
                        "runtime_disabled": 0.5,
                        "unsupported_type": 0.5,
                        "payload_truncated": 0.0,
                        "invalid_payload": 0.0,
                    },
                    "data_quality": {
                        "events_with_run_id_pct": 99.0,
                        "events_with_source_boundary_pct": 100.0,
                        "events_with_client_timestamp_pct": 98.0,
                    },
                },
                "thresholds": {
                    "per_metric": {
                        "render_success_rate": {
                            "metric": "render_success_rate",
                            "status": "warn",
                            "observed": 0.9,
                            "sample_count": 10,
                            "comparator": "min",
                            "go_threshold": 0.995,
                            "rollback_threshold": 0.985,
                            "reason": "below_go_threshold",
                        }
                    },
                    "overall_recommendation": "hold",
                    "failed_conditions": [],
                    "sample": {
                        "exposure_count": 10,
                        "payload_detected_count": 10,
                        "render_attempt_count": 10,
                        "runtime_attempt_count": 5,
                        "minimum_exposure_count_for_go": 300,
                    },
                },
            }

    _patch_workspace_orchestrator(monkeypatch, lambda: _FakeOrchestrator())

    response = client.get("/v1/telemetry/ui/summary?window_hours=24&limit=999")

    assert response.status_code == 200
    payload = response.json()
    assert payload["window_hours"] == 24
    assert payload["metrics"]["exposure_count"] == 10
    assert payload["thresholds"]["overall_recommendation"] == "hold"


def test_ui_telemetry_summary_endpoint_validates_query_params() -> None:
    client = TestClient(app=api_app_module.create_app())

    response = client.get("/v1/telemetry/ui/summary?window_hours=0")

    assert response.status_code == 422


def test_ui_telemetry_summary_endpoint_requires_auth_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("METIS_API_TOKEN", "secret-token")
    client = TestClient(app=api_app_module.create_app())

    response = client.get("/v1/telemetry/ui/summary")

    assert response.status_code == 401


def test_ui_telemetry_summary_endpoint_accepts_auth_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("METIS_API_TOKEN", "secret-token")
    client = TestClient(app=api_app_module.create_app())

    class _FakeOrchestrator:
        def get_ui_telemetry_summary(self, *, window_hours=24, limit=50_000):
            return {
                "window_hours": window_hours,
                "generated_at": "2026-03-23T12:00:00+00:00",
                "sampled_event_count": 0,
                "metrics": {
                    "exposure_count": 0,
                    "render_attempt_count": 0,
                    "render_success_rate": None,
                    "render_failure_rate": None,
                    "fallback_rate_by_reason": {},
                    "interaction_rate": None,
                    "runtime_attempt_rate": None,
                    "runtime_success_rate": None,
                    "runtime_failure_rate": None,
                    "runtime_skip_mix": {},
                    "data_quality": {
                        "events_with_run_id_pct": None,
                        "events_with_source_boundary_pct": None,
                        "events_with_client_timestamp_pct": None,
                    },
                },
                "thresholds": {
                    "per_metric": {},
                    "overall_recommendation": "hold",
                    "failed_conditions": [],
                    "sample": {
                        "exposure_count": 0,
                        "payload_detected_count": 0,
                        "render_attempt_count": 0,
                        "runtime_attempt_count": 0,
                        "minimum_exposure_count_for_go": 300,
                    },
                },
            }

    _patch_workspace_orchestrator(monkeypatch, lambda: _FakeOrchestrator())

    response = client.get(
        "/v1/telemetry/ui/summary",
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 200
    assert response.json()["thresholds"]["overall_recommendation"] == "hold"


def test_brain_graph_preserves_assistant_node_types_and_scope_metadata(monkeypatch) -> None:
    client = TestClient(app=api_app_module.create_app())
    fake_orchestrator = MagicMock()
    fake_orchestrator.get_workspace_graph.return_value = BrainGraph().build_from_indexes_and_sessions(
        [],
        [],
        {
            "identity": {
                "assistant_id": "metis-companion",
                "name": "Guide",
                "companion_enabled": True,
            },
            "status": {
                "runtime_provider": "local_gguf",
                "runtime_model": "metis-q4",
                "paused": False,
            },
            "memory": [
                {
                    "entry_id": "memory-1",
                    "title": "Learned from a completed run",
                    "summary": "Captured a short next step.",
                    "confidence": 0.9,
                }
            ],
            "playbooks": [
                {
                    "playbook_id": "playbook-1",
                    "title": "Follow-up pattern",
                    "bullets": ["Lead with the next step."],
                    "confidence": 0.8,
                }
            ],
            "brain_links": [
                {
                    "source_node_id": "memory:memory-1",
                    "target_node_id": "assistant:metis",
                    "relation": "belongs_to",
                    "summary": "Captured a short next step.",
                    "confidence": 0.9,
                    "metadata": {"scope": "assistant_learned", "note": "derived"},
                }
            ],
        },
    )
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    response = client.get("/v1/brain/graph")

    assert response.status_code == 200
    payload = response.json()
    nodes = {node["node_id"]: node for node in payload["nodes"]}
    edges = {
        (edge["source_id"], edge["target_id"], edge["edge_type"]): edge for edge in payload["edges"]
    }

    assert nodes["category:brain"]["metadata"]["scope"] == "workspace"
    assert nodes["category:assistant"]["node_type"] == "category"
    assert nodes["category:assistant"]["metadata"]["scope"] == "assistant_self"
    assert nodes["assistant:metis"]["node_type"] == "assistant"
    assert nodes["assistant:metis"]["metadata"]["scope"] == "assistant_self"
    assert nodes["memory:memory-1"]["node_type"] == "memory"
    assert nodes["memory:memory-1"]["metadata"]["scope"] == "assistant_learned"
    assert nodes["playbook:playbook-1"]["node_type"] == "playbook"
    assert nodes["playbook:playbook-1"]["metadata"]["scope"] == "assistant_self"
    assert nodes["category:assistant:memory"]["metadata"]["scope"] == "assistant_self"
    assert nodes["category:assistant:playbooks"]["metadata"]["scope"] == "assistant_self"
    assert edges[("category:assistant", "category:brain", "category_member")]["metadata"]["scope"] == "assistant_self"
    assert edges[("memory:memory-1", "assistant:metis", "belongs_to")]["metadata"]["scope"] == "assistant_learned"
    assert edges[("memory:memory-1", "assistant:metis", "belongs_to")]["metadata"]["note"] == "derived"


def test_features_list_returns_known_flags() -> None:
    client = TestClient(app=api_app_module.create_app())

    response = client.get("/v1/features")

    assert response.status_code == 200
    payload = response.json()
    names = {item["name"] for item in payload["features"]}
    assert "api_compat_openai" in names
    assert "agent_loop_hardening" in names


def test_features_disable_and_enable_roundtrip(monkeypatch, tmp_path) -> None:
    from metis_app.services.workspace_orchestrator import WorkspaceOrchestrator as _RealWO

    _patch_workspace_orchestrator(monkeypatch, _RealWO)
    import metis_app.settings_store as _store

    monkeypatch.setattr(_store, "USER_PATH", tmp_path / "settings.json")
    monkeypatch.setattr(_store, "DEFAULT_PATH", tmp_path / "default_settings.json")
    _store.DEFAULT_PATH.write_text("{}", encoding="utf-8")

    client = TestClient(app=api_app_module.create_app())

    disable_response = client.post(
        "/v1/features/api_compat_openai/disable",
        json={"reason": "maintenance", "duration_ms": 120000},
    )
    assert disable_response.status_code == 200
    disabled_payload = disable_response.json()
    assert disabled_payload["feature"] == "api_compat_openai"
    assert disabled_payload["enabled"] is False
    assert disabled_payload["disabled_by_kill_switch"] is True
    assert disabled_payload["kill_switch_reason"] == "maintenance"
    assert disabled_payload["disabled_until"]

    enable_response = client.post(
        "/v1/features/api_compat_openai/enable",
        json={"enabled": True},
    )
    assert enable_response.status_code == 200
    enabled_payload = enable_response.json()
    assert enabled_payload["feature"] == "api_compat_openai"
    assert enabled_payload["enabled"] is True
    assert enabled_payload["disabled_by_kill_switch"] is False


def test_features_require_auth_when_token_is_configured(monkeypatch) -> None:
    monkeypatch.setenv("METIS_API_TOKEN", "secret-token")
    client = TestClient(app=api_app_module.create_app())

    response = client.get("/v1/features")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Phase 1A — OpenAI Chat Completions compatibility endpoint
# ---------------------------------------------------------------------------


def test_openai_chat_completions_disabled_by_default(monkeypatch) -> None:
    """Endpoint returns 404 when api_compat_openai flag is not enabled."""
    monkeypatch.setattr(
        __import__("metis_app.settings_store", fromlist=["_"]),
        "load_settings",
        lambda: {},
    )
    client = TestClient(app=api_app_module.create_app())

    response = client.post(
        "/v1/openai/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 404
    assert "api_compat_openai" in response.json()["detail"]


def test_openai_chat_completions_happy_path(monkeypatch) -> None:
    """Endpoint returns an OpenAI-shaped response when flag is enabled."""
    monkeypatch.setattr(
        __import__("metis_app.settings_store", fromlist=["_"]),
        "load_settings",
        lambda: {"feature_flags": {"api_compat_openai": True}},
    )

    class _Result:
        run_id = "run-openai-compat"
        answer_text = "Hello from METIS"
        selected_mode = "Q&A"
        llm_provider = "mock"
        llm_model = "mock-model"

    fake_orchestrator = MagicMock()
    fake_orchestrator.run_direct_query.return_value = _Result()
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    client = TestClient(app=api_app_module.create_app())
    response = client.post(
        "/v1/openai/chat/completions",
        json={
            "model": "metis",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "What is METIS?"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "chat.completion"
    assert payload["id"].startswith("metis-run-openai-compat")
    assert payload["model"] == "metis"
    assert isinstance(payload["created"], int)
    assert len(payload["choices"]) == 1
    choice = payload["choices"][0]
    assert choice["index"] == 0
    assert choice["finish_reason"] == "stop"
    assert choice["message"]["role"] == "assistant"
    assert choice["message"]["content"] == "Hello from METIS"
    assert payload["usage"]["prompt_tokens"] == 0
    assert payload["usage"]["completion_tokens"] == 0
    assert payload["usage"]["total_tokens"] == 0

    # Verify that the last user message was forwarded as the prompt.
    assert fake_orchestrator.run_direct_query.call_count == 1
    called_req = fake_orchestrator.run_direct_query.call_args[0][0]
    assert called_req.prompt == "What is METIS?"


def test_openai_chat_completions_rejects_empty_messages_list(monkeypatch) -> None:
    """Empty messages array fails Pydantic validation (min_length=1) → 422."""
    monkeypatch.setattr(
        __import__("metis_app.settings_store", fromlist=["_"]),
        "load_settings",
        lambda: {"feature_flags": {"api_compat_openai": True}},
    )
    client = TestClient(app=api_app_module.create_app())

    response = client.post(
        "/v1/openai/chat/completions",
        json={"model": "metis", "messages": []},
    )

    assert response.status_code == 422


def test_openai_chat_completions_rejects_no_user_message(monkeypatch) -> None:
    """Messages with only system role and no user turn get 422."""
    monkeypatch.setattr(
        __import__("metis_app.settings_store", fromlist=["_"]),
        "load_settings",
        lambda: {"feature_flags": {"api_compat_openai": True}},
    )
    client = TestClient(app=api_app_module.create_app())

    response = client.post(
        "/v1/openai/chat/completions",
        json={"messages": [{"role": "system", "content": "Be helpful."}]},
    )

    assert response.status_code == 422


def test_openai_chat_completions_requires_auth_when_configured(monkeypatch) -> None:
    """Auth parity: endpoint requires Bearer token when METIS_API_TOKEN is set."""
    monkeypatch.setenv("METIS_API_TOKEN", "secret-token")
    monkeypatch.setattr(
        __import__("metis_app.settings_store", fromlist=["_"]),
        "load_settings",
        lambda: {"feature_flags": {"api_compat_openai": True}},
    )
    client = TestClient(app=api_app_module.create_app())

    response = client.post(
        "/v1/openai/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 401


def test_openai_chat_completions_accepts_auth_when_configured(monkeypatch) -> None:
    """Endpoint works with a valid Bearer token when auth is configured."""
    monkeypatch.setenv("METIS_API_TOKEN", "secret-token")
    monkeypatch.setattr(
        __import__("metis_app.settings_store", fromlist=["_"]),
        "load_settings",
        lambda: {"feature_flags": {"api_compat_openai": True}},
    )

    class _Result:
        run_id = "run-auth-compat"
        answer_text = "Authorized response"
        selected_mode = "Q&A"
        llm_provider = "mock"
        llm_model = "mock-model"

    fake_orchestrator = MagicMock()
    fake_orchestrator.run_direct_query.return_value = _Result()
    _patch_workspace_orchestrator(monkeypatch, lambda: fake_orchestrator)

    client = TestClient(app=api_app_module.create_app())
    response = client.post(
        "/v1/openai/chat/completions",
        headers={"Authorization": "Bearer secret-token"},
        json={"messages": [{"role": "user", "content": "hello"}]},
    )

    assert response.status_code == 200
    assert response.json()["choices"][0]["message"]["content"] == "Authorized response"


def test_openai_chat_completions_rejects_stream_true(monkeypatch) -> None:
    """Streaming is not supported in this slice — stream=true returns 501."""
    monkeypatch.setattr(
        __import__("metis_app.settings_store", fromlist=["_"]),
        "load_settings",
        lambda: {"feature_flags": {"api_compat_openai": True}},
    )
    client = TestClient(app=api_app_module.create_app())

    response = client.post(
        "/v1/openai/chat/completions",
        json={"messages": [{"role": "user", "content": "hello"}], "stream": True},
    )

    assert response.status_code == 501


def test_autonomous_status_returns_enabled_false_by_default(monkeypatch) -> None:
    """GET /v1/autonomous/status returns enabled: false when not configured."""

    monkeypatch.setattr(
        __import__("metis_app.settings_store", fromlist=["_"]),
        "load_settings",
        lambda: {},
    )
    client = TestClient(app=api_app_module.create_app())

    response = client.get("/v1/autonomous/status")

    assert response.status_code == 200
    data = response.json()
    assert "enabled" in data
    assert data["enabled"] is False


def test_autonomous_trigger_returns_ok(monkeypatch) -> None:
    """POST /v1/autonomous/trigger returns ok field."""

    monkeypatch.setattr(
        __import__("metis_app.settings_store", fromlist=["_"]),
        "load_settings",
        lambda: {},
    )

    class _FakeOrchestrator:
        def run_autonomous_research(self, settings):
            return {"cycles": 0}

    monkeypatch.setattr(
        _autonomous_module,
        "WorkspaceOrchestrator",
        lambda: _FakeOrchestrator(),
    )
    client = TestClient(app=api_app_module.create_app())

    response = client.post("/v1/autonomous/trigger")

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


def test_autonomous_trigger_returns_500_on_error(monkeypatch) -> None:
    """POST /v1/autonomous/trigger returns 500 when research raises."""

    monkeypatch.setattr(
        __import__("metis_app.settings_store", fromlist=["_"]),
        "load_settings",
        lambda: {},
    )

    class BrokenOrchestrator:
        def run_autonomous_research(self, settings):
            raise RuntimeError("research failed")

    monkeypatch.setattr(
        _autonomous_module,
        "WorkspaceOrchestrator",
        lambda: BrokenOrchestrator(),
    )
    client = TestClient(app=api_app_module.create_app())

    response = client.post("/v1/autonomous/trigger")
    assert response.status_code == 500


def test_autonomous_research_stream_returns_sse_events(monkeypatch) -> None:
    """POST /v1/autonomous/research/stream streams SSE events, starts with research_started."""

    monkeypatch.setattr(
        __import__("metis_app.settings_store", fromlist=["_"]),
        "load_settings",
        lambda: {},
    )

    class _FakeOrchestrator:
        def run_autonomous_research(self, settings, progress_cb=None) -> dict:
            if progress_cb is not None:
                progress_cb({"phase": "scanning", "faculty_id": None, "detail": "Scanning..."})
                progress_cb({"phase": "skipped", "faculty_id": None, "detail": "No gaps found."})
            return {"cycles": 0}

    monkeypatch.setattr(
        _autonomous_module,
        "WorkspaceOrchestrator",
        lambda: _FakeOrchestrator(),
    )
    client = TestClient(app=api_app_module.create_app())

    response = client.post("/v1/autonomous/research/stream")

    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    text = response.text
    assert "research_started" in text
    assert "scanning" in text
    assert "research_complete" in text


def test_autonomous_research_stream_emits_error_event_on_failure(monkeypatch) -> None:
    """POST /v1/autonomous/research/stream emits research_error when orchestrator raises."""

    monkeypatch.setattr(
        __import__("metis_app.settings_store", fromlist=["_"]),
        "load_settings",
        lambda: {},
    )

    class _BrokenOrchestrator:
        def run_autonomous_research(self, settings, progress_cb=None) -> None:
            raise RuntimeError("search service down")

    monkeypatch.setattr(
        _autonomous_module,
        "WorkspaceOrchestrator",
        lambda: _BrokenOrchestrator(),
    )
    client = TestClient(app=api_app_module.create_app())

    response = client.post("/v1/autonomous/research/stream")

    assert response.status_code == 200
    assert "research_error" in response.text


# ---------------------------------------------------------------------------
# New Scion-inspired adoption tests
# ---------------------------------------------------------------------------


def test_brain_graph_events_route_is_registered() -> None:
    """GET /v1/brain/graph/events route exists in the FastAPI app."""
    app = api_app_module.create_app()
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/v1/brain/graph/events" in paths


def test_brain_graph_events_payload_structure(monkeypatch) -> None:
    """The SSE payload generated for brain graph events has expected fields."""
    import hashlib

    # Simulate the payload-building logic used in the SSE generator
    brain = BrainGraph().build_from_indexes_and_sessions([], [])
    nodes = [
        {"node_id": n.node_id, "node_type": n.node_type, "label": n.label,
         "x": n.x, "y": n.y, "metadata": n.metadata}
        for n in brain.nodes.values()
    ]
    edges = [
        {"source_id": e.source_id, "target_id": e.target_id,
         "edge_type": e.edge_type, "metadata": e.metadata, "weight": e.weight}
        for e in brain.edges
    ]
    payload = {"nodes": nodes, "edges": edges}
    data_str = json.dumps(payload, sort_keys=True, default=str)
    graph_hash = hashlib.sha256(data_str.encode()).hexdigest()[:16]
    event = json.loads(
        json.dumps({"type": "brain_snapshot", "subject": "brain.graph", "hash": graph_hash, **payload}, default=str)
    )

    assert event["type"] == "brain_snapshot"
    assert event["subject"] == "brain.graph"
    assert "hash" in event and len(event["hash"]) == 16
    assert "nodes" in event
    assert "edges" in event


def test_trace_playback_returns_manifest(monkeypatch, tmp_path) -> None:
    """GET /v1/traces/{run_id}/playback returns a PlaybackManifest."""

    run_id = "test-run-playback-001"
    sample_events = [
        {
            "run_id": run_id,
            "timestamp": "2025-01-01T00:00:00+00:00",
            "stage": "retrieval",
            "event_type": "retrieval_complete",
            "payload": {"sources": []},
            "citations_chosen": [],
        },
        {
            "run_id": run_id,
            "timestamp": "2025-01-01T00:00:01+00:00",
            "stage": "generation",
            "event_type": "final",
            "payload": {"answer": "done"},
            "citations_chosen": [],
        },
    ]

    fake_store = MagicMock()
    fake_store.read_run_events.return_value = sample_events
    _patch_trace_store(monkeypatch, lambda: fake_store)

    client = TestClient(app=api_app_module.create_app())
    response = client.get(f"/v1/traces/{run_id}/playback")

    assert response.status_code == 200
    manifest = response.json()
    assert manifest["type"] == "manifest"
    assert manifest["run_id"] == run_id
    assert manifest["event_count"] == 2
    assert len(manifest["events"]) == 2
    assert manifest["events"][0]["type"] == "retrieval_complete"
    assert manifest["events"][1]["type"] == "final"
    assert manifest["time_range"]["start"] == "2025-01-01T00:00:00+00:00"
    assert manifest["time_range"]["end"] == "2025-01-01T00:00:01+00:00"


def test_stream_events_normalize_adds_phase_and_activity() -> None:
    """normalize_stream_event adds agent_phase and agent_activity fields."""
    from metis_app.services.stream_events import normalize_stream_event

    event = {"type": "iteration_start", "run_id": "run-abc", "iteration": 1, "total_iterations": 2}
    result = normalize_stream_event(event)

    assert result["agent_phase"] == "running"
    assert result["agent_activity"] == "thinking"
    assert result["subject"] == "session.run-abc.events"


def test_stream_events_normalize_stopped_on_final() -> None:
    """Final event gets agent_phase='stopped' and agent_activity='completed'."""
    from metis_app.services.stream_events import normalize_stream_event

    event = {"type": "final", "run_id": "run-xyz", "answer": "done"}
    result = normalize_stream_event(event)

    assert result["agent_phase"] == "stopped"
    assert result["agent_activity"] == "completed"
