from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from axiom_app.controllers.app_controller import AppController, _TASK_IMPORT_LOCAL_GGUF
from axiom_app.models.app_model import AppModel
from axiom_app.services.local_llm_recommender import ImportPlan
from axiom_app.services.session_repository import SessionRepository


class _FakeRoot:
    def protocol(self, *_a, **_kw):
        pass


class _FakeButton:
    def configure(self, **_kw):
        pass


class _Token:
    cancelled = False


@dataclass
class _FakeView:
    root: _FakeRoot = field(default_factory=_FakeRoot)
    btn_cancel_rag: _FakeButton = field(default_factory=_FakeButton)
    btn_build_index: _FakeButton = field(default_factory=_FakeButton)
    _status: str = ""
    switched_to: list[str] = field(default_factory=list)
    selected_recommendation: dict[str, Any] | None = None
    local_rows: list[dict[str, Any]] = field(default_factory=list)
    populated_settings: list[dict[str, Any]] = field(default_factory=list)
    recommendation_payloads: list[dict[str, Any]] = field(default_factory=list)
    picked_repo_file: str = ""
    logs: list[str] = field(default_factory=list)

    def set_mode_state_callback(self, _callback):
        pass

    def populate_settings(self, settings: dict[str, Any]) -> None:
        self.populated_settings.append(dict(settings))

    def set_status(self, text: str) -> None:
        self._status = text

    def append_log(self, text: str) -> None:
        self.logs.append(text)

    def set_progress(self, *_args) -> None:
        pass

    def reset_progress(self) -> None:
        pass

    def switch_view(self, name: str) -> None:
        self.switched_to.append(name)

    def set_file_list(self, _paths: list[str]) -> None:
        pass

    def set_local_model_rows(self, rows: list[dict[str, Any]], _dependency_status: dict[str, Any] | None = None) -> None:
        self.local_rows = list(rows)

    def set_local_gguf_recommendations(self, payload: dict[str, Any]) -> None:
        self.recommendation_payloads.append(dict(payload))

    def get_selected_local_gguf_recommendation(self) -> dict[str, Any] | None:
        return dict(self.selected_recommendation or {}) if self.selected_recommendation else None

    def show_hardware_override_editor(self, _settings: dict[str, Any], _detected: dict[str, Any]):
        return None

    def pick_local_gguf_repo_file(self, _candidates: list[dict[str, Any]], _title: str, _detail: str) -> str:
        return self.picked_repo_file

    def get_selected_history_session_id(self) -> str:
        return ""

    def get_selected_local_model_id(self) -> str:
        return ""

    def get_selected_profile_label(self) -> str:
        return "Built-in: Default"


def _build_controller(monkeypatch) -> tuple[AppController, AppModel, _FakeView]:
    model = AppModel()
    view = _FakeView()
    controller = AppController(
        model=model,
        view=view,
        session_repository=SessionRepository(":memory:"),
    )
    monkeypatch.setattr(model, "save_settings", lambda settings: setattr(model, "settings", dict(settings)))
    monkeypatch.setattr(
        controller.local_llm_recommender_service,
        "recommend_models",
        lambda **_kwargs: {
            "rows": [],
            "hardware": {"total_ram_gb": 16.0, "available_ram_gb": 12.0, "total_cpu_cores": 8, "backend": "cpu_x86"},
            "use_case": "general",
            "advisory_only": False,
        },
    )
    monkeypatch.setattr(controller, "_ask_yes_no", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(controller, "_show_info_dialog", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(controller, "_show_error_dialog", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(controller, "_pick_open_file", lambda **_kwargs: "")
    return controller, model, view


def _capture_task(monkeypatch, controller: AppController) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def _start_task(task_name, fn, *args):
        captured["task_name"] = task_name
        captured["fn"] = fn
        captured["args"] = args

    monkeypatch.setattr(controller, "start_task", _start_task)
    return captured


def _complete_import(controller: AppController, captured: dict[str, Any]) -> dict[str, Any]:
    result = captured["fn"](lambda _msg: None, _Token(), *captured["args"])
    controller._handle_message({"type": "done", "task_name": _TASK_IMPORT_LOCAL_GGUF, "result": result})
    return result


def test_apply_local_gguf_recommendation_mutates_only_after_background_success(monkeypatch, tmp_path) -> None:
    controller, model, view = _build_controller(monkeypatch)
    model.settings = {
        "llm_provider": "anthropic",
        "llm_model": "claude-opus-4-6",
        "local_model_registry": {"gguf": [], "sentence_transformers": []},
    }
    view.selected_recommendation = {
        "model_name": "Qwen/Test-7B-Instruct",
        "best_quant": "Q4_K_M",
        "fit_level": "good",
        "recommended_context_length": 4096,
    }

    def _plan_import(**_kwargs) -> ImportPlan:
        return ImportPlan(
            source_repo="bartowski/test",
            source_provider="bartowski",
            filename="Qwen-Test-Instruct-Q4_K_M.gguf",
            destination_path=str(tmp_path / "Qwen-Test-Instruct-Q4_K_M.gguf"),
            registry_metadata={
                "catalog_name": "Qwen/Test-7B-Instruct",
                "fit_level": "good",
                "recommended_context_length": 4096,
                "quantization": "Q4_K_M",
            },
            expected_size_bytes=4,
            activation_safe=True,
        )

    def _download_import(plan: ImportPlan, **_kwargs) -> Path:
        path = Path(plan.destination_path)
        path.write_bytes(b"gguf")
        return path

    monkeypatch.setattr(controller.local_llm_recommender_service, "plan_import", _plan_import)
    monkeypatch.setattr(controller.local_llm_recommender_service, "download_import", _download_import)
    captured = _capture_task(monkeypatch, controller)

    controller.on_apply_local_gguf_recommendation()

    assert captured["task_name"] == _TASK_IMPORT_LOCAL_GGUF
    assert model.settings["llm_provider"] == "anthropic"

    _complete_import(controller, captured)

    assert model.settings["llm_provider"] == "local_gguf"
    assert model.settings["local_gguf_context_length"] == 4096
    assert model.settings["local_gguf_gpu_layers"] == 0
    assert model.settings["local_gguf_threads"] == 0
    assert model.settings["local_gguf_model_path"].endswith("Qwen-Test-Instruct-Q4_K_M.gguf")
    assert model.settings["local_model_registry"]["gguf"][0]["metadata"]["catalog_name"] == "Qwen/Test-7B-Instruct"
    assert view._status.startswith("Applied")


def test_apply_local_gguf_recommendation_requires_confirmation_for_marginal(monkeypatch) -> None:
    controller, _model, view = _build_controller(monkeypatch)
    view.selected_recommendation = {
        "model_name": "Qwen/Test-7B-Instruct",
        "best_quant": "Q4_K_M",
        "fit_level": "marginal",
        "recommended_context_length": 4096,
    }
    monkeypatch.setattr(controller, "_ask_yes_no", lambda *_args, **_kwargs: False)
    started = {"value": False}
    monkeypatch.setattr(controller, "start_task", lambda *_args, **_kwargs: started.__setitem__("value", True))

    controller.on_apply_local_gguf_recommendation()

    assert started["value"] is False
    assert "Activation cancelled" in view._status


def test_apply_local_gguf_recommendation_blocks_too_tight(monkeypatch) -> None:
    controller, _model, view = _build_controller(monkeypatch)
    view.selected_recommendation = {
        "model_name": "Qwen/Test-70B",
        "best_quant": "Q4_K_M",
        "fit_level": "too_tight",
        "recommended_context_length": 4096,
    }
    started = {"value": False}
    monkeypatch.setattr(controller, "start_task", lambda *_args, **_kwargs: started.__setitem__("value", True))
    info_messages: list[str] = []
    monkeypatch.setattr(controller, "_show_info_dialog", lambda _title, text: info_messages.append(text))

    controller.on_apply_local_gguf_recommendation()

    assert started["value"] is False
    assert info_messages
    assert "activation is blocked" in info_messages[0].lower()


def test_import_worker_requests_manual_selection_for_ambiguous_file(monkeypatch, tmp_path) -> None:
    controller, model, view = _build_controller(monkeypatch)
    model.settings = {"local_model_registry": {"gguf": [], "sentence_transformers": []}}
    view.selected_recommendation = {
        "model_name": "Qwen/Test-7B-Instruct",
        "best_quant": "Q4_K_M",
        "fit_level": "good",
        "recommended_context_length": 4096,
    }

    def _plan_import(**kwargs) -> ImportPlan:
        selected_filename = str(kwargs.get("selected_filename") or "")
        if not selected_filename:
            return ImportPlan(
                source_repo="bartowski/test",
                source_provider="bartowski",
                filename="",
                destination_path=str(tmp_path),
                registry_metadata={"catalog_name": "Qwen/Test-7B-Instruct"},
                manual_selection_required=True,
                manual_reason="Multiple GGUF files match this recommendation.",
                candidate_filenames=["one.gguf", "two.gguf"],
            )
        return ImportPlan(
            source_repo="bartowski/test",
            source_provider="bartowski",
            filename=selected_filename,
            destination_path=str(tmp_path / selected_filename),
            registry_metadata={"catalog_name": "Qwen/Test-7B-Instruct"},
        )

    monkeypatch.setattr(controller.local_llm_recommender_service, "plan_import", _plan_import)
    monkeypatch.setattr(
        controller.local_llm_recommender_service,
        "list_repo_files",
        lambda _repo: [],
    )
    monkeypatch.setattr(
        controller.local_llm_recommender_service,
        "describe_repo_files",
        lambda _files: [{"filename": "two.gguf", "quant": "Q4_K_M", "size_bytes": 4_000_000, "hint": "chat/instruct"}],
    )
    calls: list[tuple[str, tuple[Any, ...]]] = []

    def _start_task(task_name, fn, *args):
        calls.append((task_name, args))

    monkeypatch.setattr(controller, "start_task", _start_task)
    view.picked_repo_file = "two.gguf"

    controller.on_import_local_gguf_recommendation()
    result = controller._local_gguf_import_worker(lambda _msg: None, _Token(), *calls[0][1])
    controller._handle_message({"type": "done", "task_name": _TASK_IMPORT_LOCAL_GGUF, "result": result})

    assert len(calls) == 2
    assert calls[1][0] == _TASK_IMPORT_LOCAL_GGUF
    assert calls[1][1][-1] == "two.gguf"


def test_apply_wizard_result_keeps_current_llm_until_import_succeeds(monkeypatch, tmp_path) -> None:
    controller, model, view = _build_controller(monkeypatch)
    model.settings = {
        "llm_provider": "anthropic",
        "llm_model": "claude-opus-4-6",
        "llm_model_custom": "claude-opus-4-6",
        "embedding_provider": "voyage",
        "embedding_model": "voyage-4-large",
        "local_model_registry": {"gguf": [], "sentence_transformers": []},
    }
    captured = _capture_task(monkeypatch, controller)

    def _plan_import(**_kwargs) -> ImportPlan:
        return ImportPlan(
            source_repo="bartowski/test",
            source_provider="bartowski",
            filename="Wizard-Q4_K_M.gguf",
            destination_path=str(tmp_path / "Wizard-Q4_K_M.gguf"),
            registry_metadata={
                "catalog_name": "Wizard/Test-7B-Instruct",
                "fit_level": "good",
                "recommended_context_length": 8192,
                "quantization": "Q4_K_M",
            },
        )

    monkeypatch.setattr(controller.local_llm_recommender_service, "plan_import", _plan_import)

    result = {
        "chunk_size": 900,
        "chunk_overlap": 100,
        "llm_provider": "local_gguf",
        "llm_model": "Wizard/Test-7B-Instruct",
        "embedding_provider": "voyage",
        "embedding_model": "voyage-4-large",
        "mode_preset": "Research",
        "retrieval_k": 12,
        "top_k": 5,
        "selected_local_gguf_recommendation": {
            "model_name": "Wizard/Test-7B-Instruct",
            "best_quant": "Q4_K_M",
            "fit_level": "good",
            "recommended_context_length": 8192,
        },
        "import_local_gguf_recommendation": True,
    }

    controller._apply_wizard_result(result)

    assert captured["task_name"] == _TASK_IMPORT_LOCAL_GGUF
    assert model.settings["llm_provider"] == "anthropic"
    assert model.settings["selected_mode"] == "Research"
    assert view.switched_to[-1] == "chat"
    assert view._status == "Setup complete."

    controller._handle_message(
        {"type": "error", "task_name": _TASK_IMPORT_LOCAL_GGUF, "text": "download failed", "traceback": ""}
    )

    assert model.settings["llm_provider"] == "anthropic"
