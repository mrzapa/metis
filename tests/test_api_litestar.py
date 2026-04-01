"""Smoke tests for the experimental Litestar API."""

from __future__ import annotations

from unittest.mock import MagicMock

from litestar import Litestar
from litestar.testing import TestClient
from fastapi.testclient import TestClient as FastAPITestClient
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


def test_gguf_hardware_parity_with_fastapi(monkeypatch):
    """Ensure FastAPI and Litestar /hardware responses stay identical."""
    from metis_app.api.app import create_app as create_fastapi_app
    from metis_app.api import gguf as fastapi_gguf
    from metis_app.api_litestar import create_app as create_litestar_app
    from metis_app.api_litestar.routes import gguf as litestar_gguf

    hardware = MagicMock()
    hardware.total_ram_gb = 32.0
    hardware.available_ram_gb = 16.0
    hardware.total_cpu_cores = 8
    hardware.cpu_name = "Intel"
    hardware.has_gpu = True
    hardware.gpu_vram_gb = 12.0
    hardware.total_gpu_vram_gb = 12.0
    hardware.gpu_name = "NVIDIA RTX"
    hardware.gpu_count = 1
    hardware.unified_memory = False
    hardware.backend = "cuda"
    hardware.detected = True
    hardware.override_enabled = False
    hardware.notes = []

    recommender = MagicMock()
    recommender.detect_hardware.return_value = hardware

    monkeypatch.setattr(fastapi_gguf, "_RECOMMENDER", recommender)
    monkeypatch.setattr(litestar_gguf, "_RECOMMENDER", recommender)

    with FastAPITestClient(create_fastapi_app()) as fastapi_client, TestClient(
        app=create_litestar_app()
    ) as litestar_client:
        fastapi_response = fastapi_client.get("/v1/gguf/hardware")
        litestar_response = litestar_client.get("/v1/gguf/hardware")

        assert fastapi_response.status_code == 200
        assert litestar_response.status_code == 200
        assert fastapi_response.json() == litestar_response.json()


def test_gguf_validate_parity_with_fastapi(tmp_path):
    """Ensure FastAPI and Litestar /validate responses stay identical."""
    from metis_app.api.app import create_app as create_fastapi_app
    from metis_app.api_litestar import create_app as create_litestar_app

    model_file = tmp_path / "Qwen2.5-7B-Q4_K_M.gguf"
    model_file.write_bytes(b"fake gguf content")
    payload = {"model_path": str(model_file)}

    with FastAPITestClient(create_fastapi_app()) as fastapi_client, TestClient(
        app=create_litestar_app()
    ) as litestar_client:
        fastapi_response = fastapi_client.post("/v1/gguf/validate", json=payload)
        litestar_response = litestar_client.post("/v1/gguf/validate", json=payload)

        assert fastapi_response.status_code == 200
        assert litestar_response.status_code == 200
        assert fastapi_response.json() == litestar_response.json()
