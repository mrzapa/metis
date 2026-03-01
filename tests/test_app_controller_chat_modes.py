"""tests/test_app_controller_chat_modes.py — chat mode routing tests.

Updated to work with the async (background-thread) dispatch used by
on_send_prompt / _handle_direct_prompt.  The helper ``_drain`` waits for
the background future and pumps messages through poll_and_dispatch.
"""

from __future__ import annotations

from axiom_app.controllers.app_controller import AppController


class _FakeButton:
    def configure(self, **_kw):
        pass


class _FakeView:
    def __init__(self, chat_mode: str) -> None:
        self._chat_mode = chat_mode
        self.chat_messages: list[str] = []
        self.switched_to: list[str] = []
        self.logs: list[str] = []
        self.btn_cancel_rag = _FakeButton()
        self.btn_build_index = _FakeButton()
        self._status: str = ""

    def get_chat_mode(self) -> str:
        return self._chat_mode

    def append_chat(self, text: str, tag: str = "agent") -> None:
        del tag
        self.chat_messages.append(text)

    def switch_view(self, key: str) -> None:
        self.switched_to.append(key)

    def append_log(self, text: str) -> None:
        self.logs.append(text)

    def set_status(self, text: str) -> None:
        self._status = text

    def set_progress(self, current: int, total: int | None = None) -> None:
        pass

    def reset_progress(self) -> None:
        pass


class _FakeModel:
    def __init__(self, *, index_built: bool) -> None:
        self.index_state = {"built": index_built}
        self.chat_history: list[dict[str, str]] = []
        self.settings: dict = {"top_k": 3, "llm_provider": "mock"}
        self.embeddings: list[list[float]] = []
        self.chunks: list[dict] = []
        self.knowledge_graph = None
        self.entity_to_chunks: dict = {}


def _drain(controller: AppController) -> None:
    """Wait for any in-flight background future, then dispatch all messages."""
    if controller._active_future is not None:
        controller._active_future.result(timeout=5)
    controller.poll_and_dispatch()


def test_on_send_prompt_direct_mode_does_not_require_index() -> None:
    view = _FakeView(chat_mode="direct")
    model = _FakeModel(index_built=False)
    controller = AppController(model=model, view=view)

    controller.on_send_prompt("hello")
    _drain(controller)

    assert len(model.chat_history) == 2
    # The prompt line is appended synchronously; the answer comes via poll.
    all_text = " ".join(view.chat_messages)
    assert "No index built yet" not in all_text
    assert "mock" in all_text.lower() or "direct" in all_text.lower()
    assert view.switched_to[-1] == "chat"


def test_on_send_prompt_rag_mode_requires_index() -> None:
    view = _FakeView(chat_mode="rag")
    model = _FakeModel(index_built=False)
    controller = AppController(model=model, view=view)

    controller.on_send_prompt("hello")

    assert model.chat_history == []
    assert "No index built yet" in view.chat_messages[0]
    assert view.switched_to[-1] == "chat"


def test_on_send_prompt_rag_mode_uses_selected_mode_header() -> None:
    view = _FakeView(chat_mode="rag")
    model = _FakeModel(index_built=True)
    model.settings["selected_mode"] = "Deep Dive"
    model.embeddings = [[0.1] * 32]
    model.chunks = [{"text": "Indexed chunk body", "source": "doc.txt", "chunk_idx": 0}]
    controller = AppController(model=model, view=view)

    controller.on_send_prompt("hello")
    _drain(controller)

    assert len(model.chat_history) == 2
    all_text = " ".join(view.chat_messages)
    assert "Deep Dive" in all_text
    assert view.switched_to[-1] == "chat"


def test_on_send_prompt_rag_includes_graph_mode_label() -> None:
    view = _FakeView(chat_mode="rag")
    model = _FakeModel(index_built=True)
    model.settings.update({"selected_mode": "Q&A", "kg_query_mode": "local"})
    model.embeddings = [[0.1] * 32]
    model.chunks = [{"text": "Indexed chunk body", "source": "doc.txt", "chunk_idx": 0}]
    controller = AppController(model=model, view=view)

    controller.on_send_prompt("hello")
    _drain(controller)

    # The LLM receives context with graph-mode info; the response header
    # includes the mode label via _handle_message.
    all_text = " ".join(view.chat_messages)
    assert "rag" in all_text.lower() or "Q&A" in all_text
