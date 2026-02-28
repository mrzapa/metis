"""tests/test_app_controller_chat_modes.py — chat mode routing tests."""

from __future__ import annotations

from axiom_app.controllers.app_controller import AppController


class _FakeView:
    def __init__(self, chat_mode: str) -> None:
        self._chat_mode = chat_mode
        self.chat_messages: list[str] = []
        self.switched_to: list[str] = []
        self.logs: list[str] = []

    def get_chat_mode(self) -> str:
        return self._chat_mode

    def append_chat(self, text: str, tag: str = "agent") -> None:
        del tag
        self.chat_messages.append(text)

    def switch_view(self, key: str) -> None:
        self.switched_to.append(key)

    def append_log(self, text: str) -> None:
        self.logs.append(text)


class _FakeModel:
    def __init__(self, *, index_built: bool) -> None:
        self.index_state = {"built": index_built}
        self.chat_history: list[dict[str, str]] = []
        self.settings = {"top_k": 3}
        self.embeddings: list[list[float]] = []
        self.chunks: list[dict[str, str | int]] = []


def test_on_send_prompt_direct_mode_does_not_require_index() -> None:
    view = _FakeView(chat_mode="direct")
    model = _FakeModel(index_built=False)
    controller = AppController(model=model, view=view)

    controller.on_send_prompt("hello")

    assert len(model.chat_history) == 2
    assert "No index built yet" not in view.chat_messages[0]
    assert "Axiom [mock, direct]" in view.chat_messages[0]
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

    assert len(model.chat_history) == 2
    assert "Axiom [mock rag, mode=Deep Dive, 1 chunk(s) indexed]:" in view.chat_messages[0]
    assert view.switched_to[-1] == "chat"
