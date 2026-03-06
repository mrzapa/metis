from __future__ import annotations

import os

import pytest

from axiom_app.services.vector_store import (
    normalize_weaviate_settings,
    resolve_vector_store,
    weaviate_test_settings_from_env,
)


def test_normalize_weaviate_settings_parses_bool_and_port() -> None:
    normalized = normalize_weaviate_settings(
        {
            "weaviate_url": "http://127.0.0.1:8080",
            "weaviate_grpc_host": "127.0.0.1",
            "weaviate_grpc_port": "50051",
            "weaviate_grpc_secure": "false",
        }
    )

    assert normalized["weaviate_url"] == "http://127.0.0.1:8080"
    assert normalized["weaviate_grpc_host"] == "127.0.0.1"
    assert normalized["weaviate_grpc_port"] == 50051
    assert normalized["weaviate_grpc_secure"] is False


def test_normalize_weaviate_settings_rejects_bad_values() -> None:
    with pytest.raises(ValueError, match="Invalid weaviate_url"):
        normalize_weaviate_settings({"weaviate_url": "://bad"})

    with pytest.raises(ValueError, match="weaviate_grpc_port"):
        normalize_weaviate_settings(
            {
                "weaviate_url": "http://127.0.0.1:8080",
                "weaviate_grpc_port": "not-a-port",
            }
        )

    with pytest.raises(ValueError, match="weaviate_grpc_secure"):
        normalize_weaviate_settings(
            {
                "weaviate_url": "http://127.0.0.1:8080",
                "weaviate_grpc_secure": "maybe",
            }
        )


def test_weaviate_test_settings_from_env_uses_canonical_contract(monkeypatch) -> None:
    monkeypatch.setenv("AXIOM_TEST_WEAVIATE_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("AXIOM_TEST_WEAVIATE_GRPC_HOST", "127.0.0.1")
    monkeypatch.setenv("AXIOM_TEST_WEAVIATE_GRPC_PORT", "50051")
    monkeypatch.setenv("AXIOM_TEST_WEAVIATE_GRPC_SECURE", "false")
    monkeypatch.setenv("AXIOM_TEST_WEAVIATE_API_KEY", "")

    normalized = weaviate_test_settings_from_env(dict(os.environ))

    assert normalized["weaviate_url"] == "http://127.0.0.1:8080"
    assert normalized["weaviate_grpc_port"] == 50051
    assert normalized["weaviate_grpc_secure"] is False


def test_weaviate_is_available_reports_connectivity_failure() -> None:
    pytest.importorskip("weaviate")
    adapter = resolve_vector_store(
        {
            "vector_db_type": "weaviate",
            "weaviate_url": "http://127.0.0.1:9",
            "weaviate_grpc_host": "127.0.0.1",
            "weaviate_grpc_port": "9",
            "weaviate_grpc_secure": "false",
        }
    )

    available, reason = adapter.is_available(
        {
            "vector_db_type": "weaviate",
            "weaviate_url": "http://127.0.0.1:9",
            "weaviate_grpc_host": "127.0.0.1",
            "weaviate_grpc_port": "9",
            "weaviate_grpc_secure": "false",
        }
    )

    assert available is False
    assert "Could not connect to Weaviate" in reason or "preflight failed" in reason
