from __future__ import annotations

from dataclasses import dataclass

from axiom_app.controllers.app_controller import AppController
from axiom_app.models.app_model import AppModel


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
        self.btn_cancel_rag = _FakeButton()
        self.btn_build_index = _FakeButton()
        self.chat_messages: list[str] = []
        self.log_messages: list[str] = []
        self.status_messages: list[str] = []
        self.sources = []

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


@dataclass
class _FakeMessage:
    content: str
    type: str = "ai"


def _drain(controller: AppController) -> None:
    if controller._active_future is not None:
        controller._active_future.result(timeout=5)
    controller.poll_and_dispatch()


def test_direct_prompt_is_persisted_to_session_db(tmp_path, monkeypatch) -> None:
    model = AppModel()
    model.session_db_path = tmp_path / "rag_sessions.db"
    model.settings = {"llm_provider": "mock", "llm_model": "mock-v1"}
    view = _FakeView(chat_mode="direct")
    controller = AppController(model=model, view=view)

    class _FakeLLM:
        def invoke(self, _messages):
            return _FakeMessage(content="Direct response")

    monkeypatch.setattr("axiom_app.controllers.app_controller.create_llm", lambda _s: _FakeLLM())

    controller.on_send_prompt("hello")
    _drain(controller)

    sessions = controller.session_repository.list_sessions()
    assert len(sessions) == 1
    detail = controller.session_repository.get_session(sessions[0].session_id)
    assert detail is not None
    assert [message.role for message in detail.messages] == ["user", "assistant"]
    assert detail.messages[1].content == "Direct response"


def test_rag_prompt_persists_sources_to_session_db(tmp_path, monkeypatch) -> None:
    model = AppModel()
    model.session_db_path = tmp_path / "rag_sessions.db"
    model.settings = {
        "llm_provider": "mock",
        "llm_model": "mock-v1",
        "embedding_provider": "mock",
        "selected_mode": "Research",
        "top_k": 1,
    }
    model.index_state = {"built": True}
    model.documents = ["doc.txt"]
    model.chunks = [{"id": "doc.txt::chunk0", "text": "Ada Lovelace wrote the first algorithm.", "source": "doc.txt", "chunk_idx": 0}]
    model.embeddings = [[0.1] * 32]
    view = _FakeView(chat_mode="rag")
    controller = AppController(model=model, view=view)

    class _FakeLLM:
        def invoke(self, _messages):
            return _FakeMessage(content="Answer with citation [S1]")

    monkeypatch.setattr("axiom_app.controllers.app_controller.create_llm", lambda _s: _FakeLLM())

    controller.on_send_prompt("Who wrote the first algorithm?")
    _drain(controller)

    sessions = controller.session_repository.list_sessions()
    assert len(sessions) == 1
    detail = controller.session_repository.get_session(sessions[0].session_id)
    assert detail is not None
    assert detail.messages[1].sources
    assert detail.messages[1].sources[0].sid == "S1"
    assert view.sources
