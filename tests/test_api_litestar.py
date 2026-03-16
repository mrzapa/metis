"""Smoke tests for the experimental Litestar API."""

from __future__ import annotations

from litestar import Litestar
from litestar.testing import TestClient


def test_app_creation():
    """Verify the Litestar app can be created."""
    from axiom_app.api_litestar import create_app

    app = create_app()
    assert isinstance(app, Litestar)


def test_healthz():
    """Test /healthz endpoint."""
    from axiom_app.api_litestar import create_app

    with TestClient(app=create_app()) as client:
        response = client.get("/healthz")
        assert response.status_code == 200
        assert response.json() == {"ok": True}


def test_version():
    """Test /v1/version endpoint."""
    from axiom_app.api_litestar import create_app

    with TestClient(app=create_app()) as client:
        response = client.get("/v1/version")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data


def test_index_list():
    """Test /v1/index/list endpoint."""
    from axiom_app.api_litestar import create_app

    with TestClient(app=create_app()) as client:
        response = client.get("/v1/index/list")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


def test_gguf_hardware():
    """Test /v1/gguf/hardware endpoint."""
    from axiom_app.api_litestar import create_app

    with TestClient(app=create_app()) as client:
        response = client.get("/v1/gguf/hardware")
        assert response.status_code == 200
        data = response.json()
        assert "total_ram_gb" in data
        assert "has_gpu" in data


def test_gguf_catalog():
    """Test /v1/gguf/catalog endpoint."""
    from axiom_app.api_litestar import create_app

    with TestClient(app=create_app()) as client:
        response = client.get("/v1/gguf/catalog")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


def test_gguf_installed():
    """Test /v1/gguf/installed endpoint."""
    from axiom_app.api_litestar import create_app

    with TestClient(app=create_app()) as client:
        response = client.get("/v1/gguf/installed")
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


def test_gguf_validate_not_found():
    """Test /v1/gguf/validate returns 404 for missing file."""
    from axiom_app.api_litestar import create_app

    with TestClient(app=create_app()) as client:
        response = client.post(
            "/v1/gguf/validate",
            json={"model_path": "/nonexistent/model.gguf"},
        )
        assert response.status_code == 404
