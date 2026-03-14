from __future__ import annotations

from importlib import import_module

from fastapi.testclient import TestClient

api_app_module = import_module("axiom_app.api.app")


def test_healthz_returns_ok() -> None:
    client = TestClient(api_app_module.create_app())

    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_query_direct_happy_path(monkeypatch) -> None:
    client = TestClient(api_app_module.create_app())

    def _fake_query_direct(req):
        class _Result:
            run_id = req.run_id or "run-xyz"
            answer_text = "Mock/Test Backend: hello"
            selected_mode = "Q&A"

        return _Result()

    monkeypatch.setattr(api_app_module, "query_direct", _fake_query_direct)

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
