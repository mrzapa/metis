"""Tests for the v1/gguf API routes."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from axiom_app.api import gguf as gguf_module
from axiom_app.api.app import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_recommender():
    with patch.object(gguf_module, "_RECOMMENDER") as mock:
        yield mock


@pytest.fixture
def mock_registry():
    with patch.object(gguf_module, "_REGISTRY") as mock:
        yield mock


@pytest.fixture
def mock_registry_operations():
    with (
        patch.object(gguf_module, "_load_registry") as load_mock,
        patch.object(gguf_module, "_save_registry") as save_mock,
    ):
        load_mock.return_value = {"gguf": []}
        yield {"load": load_mock, "save": save_mock}


# ---------------------------------------------------------------------------
# GET /v1/gguf/catalog
# ---------------------------------------------------------------------------


def test_catalog_returns_200(client, mock_recommender):
    mock_recommender.recommend_models.return_value = {
        "rows": [
            {
                "model_name": "Qwen2.5-7B",
                "provider": "bartowski",
                "parameter_count": "7B",
                "architecture": "qwen2",
                "use_case": "chat",
                "fit_level": "good",
                "run_mode": "gpu",
                "best_quant": "Q4_K_M",
                "estimated_tps": 45.0,
                "memory_required_gb": 4.5,
                "memory_available_gb": 24.0,
                "recommended_context_length": 4096,
                "source_repo": "Qwen/Qwen2.5-7B-Instruct-GGUF",
                "source_provider": "bartowski",
            }
        ]
    }

    response = client.get("/v1/gguf/catalog?use_case=general")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["model_name"] == "Qwen2.5-7B"
    assert data[0]["fit_level"] == "good"


def test_catalog_empty_when_no_matches(client, mock_recommender):
    mock_recommender.recommend_models.return_value = {"rows": []}

    response = client.get("/v1/gguf/catalog")

    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# GET /v1/gguf/hardware
# ---------------------------------------------------------------------------


def test_hardware_returns_detected_profile(client, mock_recommender):
    mock_hw = MagicMock()
    mock_hw.total_ram_gb = 32.0
    mock_hw.available_ram_gb = 16.0
    mock_hw.total_cpu_cores = 8
    mock_hw.cpu_name = "Intel(R) Core(TM)"
    mock_hw.has_gpu = True
    mock_hw.gpu_vram_gb = 12.0
    mock_hw.total_gpu_vram_gb = 12.0
    mock_hw.gpu_name = "NVIDIA RTX 4070"
    mock_hw.gpu_count = 1
    mock_hw.unified_memory = False
    mock_hw.backend = "cuda"
    mock_hw.detected = True
    mock_hw.override_enabled = False
    mock_hw.notes = []
    mock_recommender.detect_hardware.return_value = mock_hw

    response = client.get("/v1/gguf/hardware")

    assert response.status_code == 200
    data = response.json()
    assert data["total_ram_gb"] == 32.0
    assert data["has_gpu"] is True
    assert data["gpu_name"] == "NVIDIA RTX 4070"
    assert data["backend"] == "cuda"


# ---------------------------------------------------------------------------
# GET /v1/gguf/installed
# ---------------------------------------------------------------------------


def test_installed_returns_empty_when_no_models(client, mock_registry_operations):
    response = client.get("/v1/gguf/installed")

    assert response.status_code == 200
    assert response.json() == []


def test_installed_returns_registered_models(
    client, mock_registry_operations, mock_registry
):
    from axiom_app.models.parity_types import LocalModelEntry

    mock_entry = MagicMock(spec=LocalModelEntry)
    mock_entry.entry_id = "test-id-123"
    mock_entry.name = "Mistral-7B"
    mock_entry.path = "/models/mistral-7b.gguf"
    mock_entry.metadata = {"quant": "Q4_K_M"}
    mock_entry.model_type = "gguf"

    mock_registry.list_entries.return_value = [mock_entry]

    response = client.get("/v1/gguf/installed")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "test-id-123"
    assert data[0]["name"] == "Mistral-7B"
    assert data[0]["path"] == "/models/mistral-7b.gguf"


# ---------------------------------------------------------------------------
# POST /v1/gguf/validate
# ---------------------------------------------------------------------------


def test_validate_returns_404_when_file_missing(client, tmp_path):
    nonexistent = tmp_path / "does_not_exist.gguf"

    response = client.post("/v1/gguf/validate", json={"model_path": str(nonexistent)})

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_validate_returns_400_when_not_gguf_extension(client, tmp_path):
    bad_file = tmp_path / "model.bin"
    bad_file.write_text("fake model")

    response = client.post("/v1/gguf/validate", json={"model_path": str(bad_file)})

    assert response.status_code == 400
    assert ".gguf" in response.json()["detail"].lower()


def test_validate_returns_valid_for_good_file(client, tmp_path):
    good_file = tmp_path / "Qwen2.5-7B-Q4_K_M.gguf"
    good_file.write_bytes(b"fake gguf content")

    response = client.post("/v1/gguf/validate", json={"model_path": str(good_file)})

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["filename"] == "Qwen2.5-7B-Q4_K_M.gguf"
    assert data["quant"] == "Q4_K_M"
    assert "file_size_bytes" in data


def test_validate_requires_model_path(client):
    response = client.post("/v1/gguf/validate", json={})

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /v1/gguf/refresh
# ---------------------------------------------------------------------------


def test_refresh_invalidates_caches_and_returns(client, mock_recommender):
    mock_recommender.recommend_models.return_value = {
        "rows": [],
        "hardware": {"total_ram_gb": 32.0},
        "advisory_only": False,
    }

    response = client.post("/v1/gguf/refresh?use_case=coding")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "refreshed"
    assert data["use_case"] == "coding"
    mock_recommender.invalidate_hardware_cache.assert_called_once()
    mock_recommender.invalidate_repo_cache.assert_called_once()


# ---------------------------------------------------------------------------
# POST /v1/gguf/register
# ---------------------------------------------------------------------------


def test_register_returns_400_when_missing_fields(client, mock_registry_operations):
    response = client.post("/v1/gguf/register", json={"name": "Test"})
    assert response.status_code == 422


def test_register_returns_404_when_file_missing(client, mock_registry_operations):
    response = client.post(
        "/v1/gguf/register",
        json={"name": "TestModel", "path": "/nonexistent/model.gguf"},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_register_success(client, tmp_path, monkeypatch):
    model_file = tmp_path / "test-model.gguf"
    model_file.write_bytes(b"test content")

    mock_entry = MagicMock()
    mock_entry.entry_id = "new-entry-id"
    mock_entry.name = "TestModel"
    mock_entry.path = str(model_file)
    mock_entry.model_type = "gguf"

    def mock_load_registry():
        return {"gguf": []}

    def mock_save_registry(registry):
        pass

    mock_reg = MagicMock()
    mock_reg.add_gguf.return_value = {
        "gguf": [
            {
                "id": "new-entry-id",
                "name": "TestModel",
                "path": str(model_file),
                "type": "gguf",
                "value": str(model_file),
                "metadata": {},
            }
        ]
    }
    mock_reg.list_entries.return_value = [mock_entry]

    monkeypatch.setattr(gguf_module, "_load_registry", mock_load_registry)
    monkeypatch.setattr(gguf_module, "_save_registry", mock_save_registry)
    monkeypatch.setattr(gguf_module, "_REGISTRY", mock_reg)

    response = client.post(
        "/v1/gguf/register",
        json={"name": "TestModel", "path": str(model_file)},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "registered"
    assert data["id"] == "new-entry-id"


# ---------------------------------------------------------------------------
# DELETE /v1/gguf/installed/{model_id}
# ---------------------------------------------------------------------------


def test_delete_returns_404_when_not_found(
    client, mock_registry_operations, mock_registry
):
    mock_registry.get_entry.return_value = None

    response = client.delete("/v1/gguf/installed/nonexistent-id")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_delete_success(client, monkeypatch):
    mock_entry = MagicMock()
    mock_entry.entry_id = "to-delete"

    def mock_load_registry():
        return {"gguf": []}

    def mock_save_registry(registry):
        pass

    mock_reg = MagicMock()
    mock_reg.get_entry.return_value = mock_entry
    mock_reg.remove_entry.return_value = {"gguf": []}

    monkeypatch.setattr(gguf_module, "_load_registry", mock_load_registry)
    monkeypatch.setattr(gguf_module, "_save_registry", mock_save_registry)
    monkeypatch.setattr(gguf_module, "_REGISTRY", mock_reg)

    response = client.delete("/v1/gguf/installed/to-delete")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "unregistered"
    assert data["id"] == "to-delete"
