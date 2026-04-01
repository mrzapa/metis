from __future__ import annotations

from dataclasses import dataclass
import importlib.util
import json
import os

import pytest

from metis_app.cli import main as cli_main
from metis_app.controllers.app_controller import AppController
from metis_app.models.app_model import AppModel
import metis_app.models.app_model as app_model_module
from metis_app.services.index_service import load_index_manifest
from metis_app.services.vector_store import (
    WeaviateVectorStoreAdapter,
    normalize_weaviate_settings,
    resolve_vector_store,
    weaviate_test_settings_from_env,
)

_REQUIRE_LIVE_ENV = "METIS_REQUIRE_LIVE_BACKENDS"


class _FakeRoot:
    def protocol(self, *_a, **_kw):
        pass


class _FakeButton:
    def configure(self, **_kw):
        pass


class _FakeView:
    def __init__(self, chat_mode: str) -> None:
        self.root = _FakeRoot()
        self._chat_mode = chat_mode
        self.selected_session_id = ""
        self.btn_cancel_rag = _FakeButton()
        self.btn_build_index = _FakeButton()
        self.chat_messages: list[str] = []
        self.log_messages: list[str] = []
        self.status_messages: list[str] = []
        self.transcript_messages: list[object] = []
        self.sources = []
        self.history_detail = None

    def get_chat_mode(self) -> str:
        return self._chat_mode

    def append_chat(self, text: str, tag: str = "agent") -> None:
        _ = tag
        self.chat_messages.append(text)

    def append_log(self, text: str) -> None:
        self.log_messages.append(text)

    def switch_view(self, _name: str) -> None:
        pass

    def set_status(self, text: str) -> None:
        self.status_messages.append(text)

    def set_progress(self, current: int, total: int | None = None) -> None:
        _ = (current, total)

    def reset_progress(self) -> None:
        pass

    def render_evidence_sources(self, sources) -> None:
        self.sources = list(sources)

    def set_history_detail(self, detail) -> None:
        self.history_detail = detail

    def get_selected_history_session_id(self) -> str:
        return self.selected_session_id

    def set_chat_transcript(self, messages) -> None:
        self.transcript_messages = list(messages or [])


@dataclass
class _FakeMessage:
    content: str
    type: str = "ai"


def _drain(controller: AppController) -> None:
    if controller._active_future is not None:
        controller._active_future.result(timeout=10)
    controller.poll_and_dispatch()


def _live_weaviate_settings() -> dict[str, object]:
    if importlib.util.find_spec("weaviate") is None:
        if os.environ.get(_REQUIRE_LIVE_ENV) == "1":
            pytest.fail("weaviate-client is required for the live backend proof.")
        pytest.skip("weaviate-client is not installed.")
    try:
        normalized = weaviate_test_settings_from_env()
    except ValueError as exc:
        if os.environ.get(_REQUIRE_LIVE_ENV) == "1":
            pytest.fail(f"Live Weaviate proof requires configured env vars: {exc}")
        pytest.skip(f"Live Weaviate proof is not configured: {exc}")
    return {
        **normalized,
        "vector_db_type": "weaviate",
        "embedding_provider": "mock",
        "llm_provider": "mock",
        "llm_model": "mock-v1",
        "selected_mode": "Research",
        "top_k": 1,
    }


def _collection_exists(settings: dict[str, object], collection_name: str) -> bool:
    client = WeaviateVectorStoreAdapter._connect(normalize_weaviate_settings(settings))
    try:
        return bool(client.collections.exists(collection_name))
    finally:
        client.close()


def test_live_weaviate_adapter_round_trip_and_cleanup(tmp_path) -> None:
    settings = _live_weaviate_settings()
    adapter = resolve_vector_store(settings)
    src = tmp_path / "weaviate.txt"
    src.write_text(
        "Weaviate stores vectors in a remote native collection.\n"
        "Sessions must restore those collections without JSON fallback.\n",
        encoding="utf-8",
    )
    bundle = adapter.build([str(src)], settings)
    manifest_path = adapter.save(bundle, index_dir=tmp_path / "indexes")
    manifest = load_index_manifest(manifest_path)
    try:
        assert _collection_exists(settings, manifest.collection_name)
        restored = adapter.load(manifest_path)
        result = adapter.query(restored, "Where are vectors stored?", settings)

        assert manifest.backend == "weaviate"
        assert manifest.collection_name
        assert manifest.restore_requirements["weaviate_url"] == settings["weaviate_url"]
        assert manifest.metadata["weaviate_settings"]["weaviate_url"] == settings["weaviate_url"]
        assert result.sources
        assert result.sources[0].sid == "S1"
    finally:
        adapter.delete(manifest_path)

    assert not manifest_path.exists()
    assert not _collection_exists(settings, manifest.collection_name)


def test_live_weaviate_session_restore_and_follow_up_query(tmp_path, monkeypatch) -> None:
    settings = _live_weaviate_settings()
    adapter = resolve_vector_store(settings)
    src = tmp_path / "restore.txt"
    src.write_text(
        "Remote native collections should survive a restored MVC session.\n"
        "A second query must hit the same Weaviate collection.\n",
        encoding="utf-8",
    )
    bundle = adapter.build([str(src)], settings)
    manifest_path = adapter.save(bundle, index_dir=tmp_path / "indexes")
    manifest = load_index_manifest(manifest_path)
    try:
        initial_bundle = adapter.load(manifest_path)

        model_one = AppModel()
        model_one.session_db_path = tmp_path / "rag_sessions.db"
        model_one.index_storage_dir = tmp_path / "indexes"
        model_one.settings = dict(settings)
        view_one = _FakeView(chat_mode="rag")
        controller_one = AppController(model=model_one, view=view_one)
        controller_one._apply_index_bundle(initial_bundle, persist=False)

        class _FakeLLM:
            def invoke(self, _messages):
                return _FakeMessage(content="The document states that the collection is restored from Weaviate. [S1]")

        monkeypatch.setattr("metis_app.controllers.app_controller.create_llm", lambda _s: _FakeLLM())

        controller_one.on_send_prompt("How is the collection stored?")
        _drain(controller_one)

        session_id = controller_one.session_repository.list_sessions()[0].session_id
        controller_one.shutdown()

        model_two = AppModel()
        model_two.session_db_path = tmp_path / "rag_sessions.db"
        model_two.index_storage_dir = tmp_path / "indexes"
        model_two.settings = {
            "llm_provider": "mock",
            "llm_model": "mock-v1",
            "embedding_provider": "mock",
            "selected_mode": "Research",
            "top_k": 1,
        }
        view_two = _FakeView(chat_mode="rag")
        view_two.selected_session_id = session_id
        controller_two = AppController(model=model_two, view=view_two)

        controller_two.on_open_session()

        assert controller_two.model.current_session_id == session_id
        assert controller_two.model.active_index_id == manifest.index_id
        assert controller_two.model.rag_blocked_reason == ""
        assert view_two.transcript_messages

        controller_two.on_send_prompt("What proves the restore is native?")
        _drain(controller_two)

        assert controller_two.model.last_sources
        assert any("METIS [" in message for message in view_two.chat_messages)
        controller_two.shutdown()
    finally:
        adapter.delete(manifest_path)


def test_live_weaviate_cli_round_trip_uses_shared_backend(tmp_path, monkeypatch, capsys) -> None:
    settings = _live_weaviate_settings()
    defaults = tmp_path / "default_settings.json"
    user_settings = tmp_path / "settings.json"
    defaults.write_text(
        json.dumps(
            {
                "vector_db_type": "json",
                "embedding_provider": "mock",
                "llm_provider": "mock",
                "llm_model": "mock-v1",
                "top_k": 1,
            }
        ),
        encoding="utf-8",
    )
    user_settings.write_text(json.dumps(settings), encoding="utf-8")
    monkeypatch.setattr(app_model_module, "_DEFAULT_SETTINGS_PATH", defaults)
    monkeypatch.setattr(app_model_module, "_USER_SETTINGS_PATH", user_settings)

    src = tmp_path / "cli.txt"
    out = tmp_path / "cli.metis-index"
    manifest_path = out / "manifest.json"
    src.write_text(
        "CLI and GUI should share the same Weaviate manifest-backed retrieval path.\n",
        encoding="utf-8",
    )
    adapter = resolve_vector_store(settings)
    try:
        assert cli_main(["index", "--file", str(src), "--out", str(out)]) == 0
        assert manifest_path.exists()
        capsys.readouterr()

        assert cli_main(
            ["query", "--file", str(src), "--index", str(manifest_path), "--question", "shared retrieval path"]
        ) == 0
        stdout = capsys.readouterr().out
        manifest = load_index_manifest(manifest_path)

        assert manifest.backend == "weaviate"
        assert f"shared retrieval (weaviate:{manifest.index_id})" in stdout
        assert "[S1]" in stdout or "[S2]" in stdout
    finally:
        if manifest_path.exists():
            adapter.delete(manifest_path)
