from __future__ import annotations

from dataclasses import dataclass

from axiom_app.controllers.app_controller import AppController
from axiom_app.models.app_model import AppModel


class _FakeSignal:
    """Minimal stand-in for a Qt signal (connect does nothing)."""
    def connect(self, *_a, **_kw):
        pass


class _FakeButton:
    """Minimal stand-in for a QPushButton."""
    clicked = _FakeSignal()

    def setEnabled(self, _v):
        pass


class _FakeView:
    def __init__(self, chat_mode: str) -> None:
        self._chat_mode = chat_mode
        self.btn_cancel_rag = _FakeButton()
        self.btn_build_index = _FakeButton()
        self.chat_messages: list[str] = []
        self.log_messages: list[str] = []
        self.status_messages: list[str] = []
        self.sources = []
        self.grounding_info = ""
        self.history_detail = None
        self.response_ui_states: list[tuple[bool, bool]] = []
        self.selected_session_id = ""

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

    def set_chat_response_ui(self, has_completed_response: bool, feedback_pending: bool) -> None:
        self.response_ui_states.append((bool(has_completed_response), bool(feedback_pending)))

    def set_progress(self, current: int, total: int | None = None) -> None:
        _ = (current, total)

    def reset_progress(self) -> None:
        pass

    def render_evidence_sources(self, sources) -> None:
        self.sources = list(sources)

    def render_grounding_info(self, text: str) -> None:
        self.grounding_info = text

    def set_history_detail(self, detail) -> None:
        self.history_detail = detail

    def get_selected_history_session_id(self) -> str:
        return self.selected_session_id


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


def test_rag_prompt_shows_retrieved_context_and_grounding(tmp_path, monkeypatch) -> None:
    model = AppModel()
    model.session_db_path = tmp_path / "rag_sessions.db"
    model.index_storage_dir = tmp_path / "indexes"
    model.settings = {
        "llm_provider": "mock",
        "llm_model": "mock-v1",
        "embedding_provider": "mock",
        "selected_mode": "Research",
        "top_k": 1,
        "show_retrieved_context": True,
        "enable_langextract": True,
        "enable_claim_level_grounding_citefix_lite": True,
    }
    model.index_state = {"built": True}
    model.documents = ["doc.txt"]
    model.chunks = [
        {
            "id": "doc.txt::chunk0",
            "text": "Ada Lovelace wrote the first algorithm.",
            "source": "doc.txt",
            "chunk_idx": 0,
        }
    ]
    model.embeddings = [[0.1] * 32]
    view = _FakeView(chat_mode="rag")
    controller = AppController(model=model, view=view)

    class _FakeLLM:
        def invoke(self, _messages):
            return _FakeMessage(
                content="The document states that Ada Lovelace wrote the first algorithm for Babbage's machine."
            )

    monkeypatch.setattr("axiom_app.controllers.app_controller.create_llm", lambda _s: _FakeLLM())

    controller.on_send_prompt("Who wrote the first algorithm?")
    _drain(controller)

    assert any("Retrieved context:" in message for message in view.chat_messages)
    assert any("[grounding]" in line for line in view.log_messages)
    assert view.grounding_info.endswith(".html")


def test_tutor_mode_uses_structured_pipeline(tmp_path, monkeypatch) -> None:
    model = AppModel()
    model.session_db_path = tmp_path / "rag_sessions.db"
    model.settings = {
        "llm_provider": "mock",
        "llm_model": "mock-v1",
        "embedding_provider": "mock",
        "selected_mode": "Tutor",
        "top_k": 1,
    }
    model.index_state = {"built": True}
    model.documents = ["doc.txt"]
    model.chunks = [
        {
            "id": "doc.txt::chunk0",
            "text": "Embeddings map text into vectors for similarity search.",
            "source": "doc.txt",
            "chunk_idx": 0,
        }
    ]
    model.embeddings = [[0.1] * 32]
    view = _FakeView(chat_mode="rag")
    controller = AppController(model=model, view=view)

    tutor_json = """
    {
      "lesson": {
        "concept": "Embeddings",
        "explanation": "Embeddings convert text into vectors.",
        "sources": ["S1"]
      },
      "analogies": [{"example": "Like map coordinates for meaning.", "sources": ["S1"]}],
      "socratic_questions": ["How would similar meanings cluster?"],
      "flashcards": [{"q": "What is an embedding?", "a": "A vector representation of text.", "sources": ["S1"]}],
      "quiz": {
        "questions": [{"question": "What do embeddings represent?"}],
        "answer_key": [{"answer": "Semantic meaning.", "why": "They map language to vector space.", "sources": ["S1"]}]
      }
    }
    """

    class _FakeLLM:
        def invoke(self, _messages):
            return _FakeMessage(content=tutor_json)

    monkeypatch.setattr("axiom_app.controllers.app_controller.create_llm", lambda _s: _FakeLLM())

    controller.on_send_prompt("Teach me embeddings.")
    _drain(controller)

    assert any("### Flashcards" in message for message in view.chat_messages)
    assert any("### Quiz" in message for message in view.chat_messages)


def test_secure_mode_blocks_rag_without_override(tmp_path) -> None:
    model = AppModel()
    model.session_db_path = tmp_path / "rag_sessions.db"
    model.settings = {
        "llm_provider": "mock",
        "llm_model": "mock-v1",
        "embedding_provider": "mock",
        "selected_mode": "Research",
        "top_k": 1,
        "secure_mode": True,
        "enable_summarizer": False,
    }
    model.index_state = {"built": True}
    model.documents = ["doc.txt"]
    model.chunks = [{"id": "doc.txt::chunk0", "text": "Secure mode sample.", "source": "doc.txt", "chunk_idx": 0}]
    model.embeddings = [[0.1] * 32]
    view = _FakeView(chat_mode="rag")
    controller = AppController(model=model, view=view)

    controller.on_send_prompt("What does secure mode do?")

    assert controller._active_future is None
    assert any("Secure mode requires the summarizer safety pass." in message for message in view.chat_messages)


def test_feedback_note_is_saved(tmp_path, monkeypatch) -> None:
    model = AppModel()
    model.session_db_path = tmp_path / "rag_sessions.db"
    model.settings = {"llm_provider": "mock", "llm_model": "mock-v1"}
    view = _FakeView(chat_mode="direct")
    controller = AppController(model=model, view=view)

    class _FakeLLM:
        def invoke(self, _messages):
            return _FakeMessage(content="Direct response")

    monkeypatch.setattr("axiom_app.controllers.app_controller.create_llm", lambda _s: _FakeLLM())
    monkeypatch.setattr(controller, "_get_text_input", lambda *args, **kwargs: "useful")

    controller.on_send_prompt("hello")
    _drain(controller)
    controller.on_submit_feedback(1)

    sessions = controller.session_repository.list_sessions()
    detail = controller.session_repository.get_session(sessions[0].session_id)
    assert detail is not None
    assert detail.feedback
    assert detail.feedback[0].note == "useful"


def test_open_session_restores_pending_feedback_for_latest_run(tmp_path, monkeypatch) -> None:
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
    session_id = sessions[0].session_id

    assert view.response_ui_states[-1] == (True, True)

    model_reopen = AppModel()
    model_reopen.session_db_path = model.session_db_path
    model_reopen.settings = {"llm_provider": "mock", "llm_model": "mock-v1"}
    view_reopen = _FakeView(chat_mode="direct")
    view_reopen.selected_session_id = session_id
    controller_reopen = AppController(model=model_reopen, view=view_reopen)

    controller_reopen.on_open_session()

    assert controller_reopen.model.last_run_id
    assert view_reopen.response_ui_states[-1] == (True, True)


def test_feedback_submission_and_reopen_hide_pending_feedback(tmp_path, monkeypatch) -> None:
    model = AppModel()
    model.session_db_path = tmp_path / "rag_sessions.db"
    model.settings = {"llm_provider": "mock", "llm_model": "mock-v1"}
    view = _FakeView(chat_mode="direct")
    controller = AppController(model=model, view=view)

    class _FakeLLM:
        def invoke(self, _messages):
            return _FakeMessage(content="Direct response")

    monkeypatch.setattr("axiom_app.controllers.app_controller.create_llm", lambda _s: _FakeLLM())
    monkeypatch.setattr(controller, "_get_text_input", lambda *args, **kwargs: "")

    controller.on_send_prompt("hello")
    _drain(controller)
    controller.on_submit_feedback(1)

    sessions = controller.session_repository.list_sessions()
    session_id = sessions[0].session_id

    assert view.response_ui_states[-1] == (True, False)

    model_reopen = AppModel()
    model_reopen.session_db_path = model.session_db_path
    model_reopen.settings = {"llm_provider": "mock", "llm_model": "mock-v1"}
    view_reopen = _FakeView(chat_mode="direct")
    view_reopen.selected_session_id = session_id
    controller_reopen = AppController(model=model_reopen, view=view_reopen)

    controller_reopen.on_open_session()

    assert view_reopen.response_ui_states[-1] == (True, False)


def test_new_chat_and_delete_current_session_clear_response_ui(tmp_path, monkeypatch) -> None:
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
    controller.on_new_chat()

    assert controller.model.last_run_id == ""
    assert view.response_ui_states[-1] == (False, False)

    controller.on_send_prompt("second")
    _drain(controller)
    view.selected_session_id = controller.model.current_session_id
    controller.on_delete_session()

    assert controller.model.last_run_id == ""
    assert view.response_ui_states[-1] == (False, False)


def test_reset_test_mode_clears_response_ui(tmp_path, monkeypatch) -> None:
    model = AppModel()
    model.session_db_path = tmp_path / "rag_sessions.db"
    model.settings = {"llm_provider": "mock", "llm_model": "mock-v1"}
    view = _FakeView(chat_mode="direct")
    controller = AppController(model=model, view=view)

    class _FakeLLM:
        def invoke(self, _messages):
            return _FakeMessage(content="Direct response")

    monkeypatch.setattr("axiom_app.controllers.app_controller.create_llm", lambda _s: _FakeLLM())
    monkeypatch.setattr(model, "save_settings", lambda _settings: None)

    controller.on_send_prompt("hello")
    _drain(controller)
    controller.reset_test_mode()

    assert controller.model.last_run_id == ""
    assert view.response_ui_states[-1] == (False, False)
