"""axiom_app.controllers.app_controller — Top-level application controller.

AppController mediates between AppModel (state) and AppView (UI).

Implemented actions
-------------------
* on_open_files()     — file dialog → model.documents → view listbox
* on_build_index()    — background chunking + embedding (any provider) → model
* on_send_prompt()    — retrieve → LLM synthesis → chat (any provider)
* on_save_settings()  — coerce, validate, persist settings

Background task contract
------------------------
Workers receive (post_message, cancel_token, *args) as their first two
positional arguments, injected by BackgroundRunner.submit().  All model
writes from worker *results* happen in _handle_message() on the main thread
via the poll loop in axiom_app.app — never inside the worker thread.
"""

from __future__ import annotations

import json
import logging
import math
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import uuid
from concurrent.futures import Future
import importlib.util
from typing import TYPE_CHECKING, Any, Callable

from axiom_app.models.brain_graph import BrainGraph
from axiom_app.models.parity_types import AgentProfile
from axiom_app.models.session_types import EvidenceSource
from axiom_app.services.index_service import (
    IndexBundle,
    list_index_manifests,
    load_index_bundle,
    refresh_index_bundle,
)
from axiom_app.services.local_llm_recommender import ImportPlan, LocalLlmRecommenderService
from axiom_app.services.local_model_registry import LocalModelRegistryService
from axiom_app.services.profile_repository import ProfileRepository
from axiom_app.services.response_pipeline import (
    apply_claim_level_grounding,
    build_grounding_html,
    is_blinkist_summary_mode,
    is_tutor_mode,
    run_blinkist_summary_pipeline,
    run_tutor_pipeline,
)
from axiom_app.services.runtime_resolution import resolve_runtime_settings
from axiom_app.services.session_repository import SessionRepository
from axiom_app.services.trace_store import TraceStore
from axiom_app.services.vector_store import resolve_vector_store
from axiom_app.services.wizard_recommendation import recommend_auto_settings
from axiom_app.utils.background import BackgroundRunner, CancelToken
from axiom_app.utils.dependency_bootstrap import install_packages
from axiom_app.utils.document_loader import KREUZBERG_EXTENSIONS, is_kreuzberg_available
from axiom_app.utils.llm_providers import create_llm
from axiom_app.utils.model_presets import list_llm_providers, provider_requires_custom_model

if TYPE_CHECKING:
    from axiom_app.models.app_model import AppModel
    from axiom_app.views.app_view import AppView

# Fallback embedding dimension when using MockEmbeddings directly.
_EMB_DIM = 32

# Task-name constants used to route "done" payloads in _handle_message.
_TASK_BUILD_INDEX = "Build index"
_TASK_RAG_QUERY = "RAG query"
_TASK_DIRECT_QUERY = "Direct query"
_TASK_INSTALL_DEPENDENCIES = "Install dependencies"
_TASK_IMPORT_LOCAL_GGUF = "Import local GGUF"


# ---------------------------------------------------------------------------
# Pure helpers (no Tk, no model — fully unit-testable)
# ---------------------------------------------------------------------------


def _chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split *text* into overlapping fixed-size chunks.

    Parameters
    ----------
    text:       Source string to split.
    chunk_size: Maximum characters per chunk (must be > 0).
    overlap:    Characters shared between consecutive chunks.
                Clamped to [0, chunk_size - 1].
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    overlap = max(0, min(overlap, chunk_size - 1))
    chunks: list[str] = []
    start = 0
    step = chunk_size - overlap
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start += step
    return chunks


def _cosine(v1: list[float], v2: list[float]) -> float:
    """Return cosine similarity in [-1, 1]; returns 0.0 for zero vectors."""
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    return dot / (n1 * n2) if n1 > 0 and n2 > 0 else 0.0


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------


class AppController:
    """Mediates between AppModel and AppView.

    Parameters
    ----------
    model:
        The single AppModel instance holding application state.
    view:
        The AppView instance owning the root Tk window.

    Attributes
    ----------
    background_runner:
        Public BackgroundRunner; ``app.py`` drives its poll loop.
    """

    def __init__(
        self,
        model: AppModel,
        view: AppView,
        *,
        session_repository: SessionRepository | None = None,
    ) -> None:
        self.model = model
        self.view = view
        self.background_runner = BackgroundRunner()
        self._active_token: CancelToken | None = None
        self._active_future: Future | None = None
        self._log = logging.getLogger(__name__)
        self._pending_task_meta: dict[str, Any] = {}
        self._queued_local_gguf_import: dict[str, Any] | None = None
        self.profile_repository = ProfileRepository(getattr(self.model, "profiles_dir", None))
        self.local_llm_recommender_service = LocalLlmRecommenderService()
        self.local_model_registry_service = LocalModelRegistryService()
        self.trace_store = TraceStore(getattr(self.model, "trace_dir", None))
        self._test_mode_temp_dir = ""
        self._test_mode_sample_file = ""
        db_path = getattr(self.model, "session_db_path", ":memory:")
        self.session_repository = session_repository or SessionRepository(db_path)
        self.session_repository.init_db()
        self.model.current_profile_label = str(
            self.model.settings.get("selected_profile", getattr(self.model, "current_profile_label", "Built-in: Default"))
            or "Built-in: Default"
        )
        self.refresh_history_rows(update_detail=False)
        self._clear_completed_response_state()

    def _safe_view_call(self, method_name: str, *args: Any) -> Any:
        method = getattr(self.view, method_name, None)
        if callable(method):
            return method(*args)
        return None

    def _set_chat_response_ui(self, has_completed_response: bool, feedback_pending: bool) -> None:
        self._safe_view_call(
            "set_chat_response_ui",
            bool(has_completed_response),
            bool(feedback_pending) and bool(has_completed_response),
        )

    def _clear_completed_response_state(self) -> None:
        self.model.last_run_id = ""
        self.model.last_sources = []
        self._set_chat_response_ui(False, False)

    @staticmethod
    def _run_has_feedback(detail: Any | None, run_id: str) -> bool:
        target = str(run_id or "").strip()
        if not target or detail is None:
            return False
        for item in list(getattr(detail, "feedback", []) or []):
            if str(getattr(item, "run_id", "") or "") == target:
                return True
        return False

    @classmethod
    def _latest_completed_assistant_run(
        cls,
        detail: Any | None,
    ) -> tuple[str, list[EvidenceSource], bool]:
        if detail is None:
            return "", [], False
        for message in reversed(list(getattr(detail, "messages", []) or [])):
            if str(getattr(message, "role", "") or "").strip().lower() != "assistant":
                continue
            run_id = str(getattr(message, "run_id", "") or "").strip()
            if not run_id:
                continue
            sources = [
                item if isinstance(item, EvidenceSource) else EvidenceSource.from_dict(item)
                for item in (getattr(message, "sources", []) or [])
            ]
            return run_id, sources, not cls._run_has_feedback(detail, run_id)
        return "", [], False

    @staticmethod
    def _connect_signal(signal: Any, callback: Callable[..., Any]) -> bool:
        if signal is None or not hasattr(signal, "connect"):
            return False
        signal.connect(callback)
        return True

    @staticmethod
    def _configure_command(widget: Any, callback: Callable[..., Any]) -> bool:
        if widget is None:
            return False
        if hasattr(widget, "configure"):
            widget.configure(command=callback)
            return True
        signal = getattr(widget, "clicked", None)
        if signal is not None and hasattr(signal, "connect"):
            signal.connect(callback)
            return True
        return False

    @staticmethod
    def _set_widget_enabled(widget: Any, enabled: bool) -> None:
        if widget is None:
            return
        if hasattr(widget, "setEnabled"):
            widget.setEnabled(bool(enabled))
            return
        if hasattr(widget, "configure"):
            widget.configure(state="normal" if enabled else "disabled")

    def _dialog_parent(self) -> Any:
        getter = getattr(self.view, "dialog_parent", None)
        if callable(getter):
            return getter()
        return None

    @staticmethod
    def _to_qt_filter(filetypes: list[tuple[str, str]]) -> str:
        parts: list[str] = []
        for label, pattern in filetypes:
            cleaned = " ".join(part.strip() for part in str(pattern or "").split() if part.strip())
            cleaned = cleaned or "*"
            parts.append(f"{label} ({cleaned})")
        return ";;".join(parts)

    def _ask_yes_no(self, title: str, text: str) -> bool:
        from PySide6.QtWidgets import QMessageBox

        result = QMessageBox.question(
            self._dialog_parent(),
            title,
            text,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return result == QMessageBox.Yes

    def _show_error_dialog(self, title: str, text: str) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.critical(self._dialog_parent(), title, text)

    def _show_info_dialog(self, title: str, text: str) -> None:
        from PySide6.QtWidgets import QMessageBox

        QMessageBox.information(self._dialog_parent(), title, text)

    def _pick_open_files(self, *, title: str, filetypes: list[tuple[str, str]]) -> list[str]:
        from PySide6.QtWidgets import QFileDialog

        paths, _ = QFileDialog.getOpenFileNames(
            self._dialog_parent(),
            title,
            "",
            self._to_qt_filter(filetypes),
        )
        return [str(path) for path in paths]

    def _pick_open_file(self, *, title: str, filetypes: list[tuple[str, str]]) -> str:
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(
            self._dialog_parent(),
            title,
            "",
            self._to_qt_filter(filetypes),
        )
        return str(path or "")

    def _pick_directory(self, *, title: str) -> str:
        from PySide6.QtWidgets import QFileDialog

        return str(QFileDialog.getExistingDirectory(self._dialog_parent(), title) or "")

    def _get_text_input(
        self,
        title: str,
        label: str,
        *,
        text: str = "",
    ) -> str:
        from PySide6.QtWidgets import QInputDialog

        value, accepted = QInputDialog.getText(self._dialog_parent(), title, label, text=text)
        return str(value or "") if accepted else ""

    def _pick_item_from_list(
        self,
        title: str,
        label: str,
        items: list[str],
        *,
        current: str = "",
        editable: bool = False,
    ) -> str:
        from PySide6.QtWidgets import QInputDialog

        if not items:
            return ""
        index = items.index(current) if current in items else 0
        value, accepted = QInputDialog.getItem(
            self._dialog_parent(),
            title,
            label,
            items,
            index,
            editable,
        )
        return str(value or "") if accepted else ""

    def _selected_history_session_id(self) -> str:
        getter = getattr(self.view, "get_selected_history_session_id", None)
        if callable(getter):
            return str(getter() or "")
        return ""

    def _selected_local_model_entry_id(self) -> str:
        getter = getattr(self.view, "get_selected_local_model_id", None)
        if callable(getter):
            return str(getter() or "")
        return ""

    def _current_profile_label(self) -> str:
        getter = getattr(self.view, "get_selected_profile_label", None)
        selected = getter() if callable(getter) else ""
        label = str(
            selected
            or getattr(self.model, "current_profile_label", "")
            or self.model.settings.get("selected_profile", "")
            or "Built-in: Default"
        ).strip()
        self.model.current_profile_label = label or "Built-in: Default"
        self.model.settings["selected_profile"] = self.model.current_profile_label
        return self.model.current_profile_label

    def _current_vector_backend(self) -> str:
        bundle = getattr(self.model, "index_bundle", None)
        if isinstance(bundle, IndexBundle):
            return str(bundle.vector_backend or "json")
        return str(self.model.settings.get("vector_db_type", "json") or "json")

    def _current_local_gguf_use_case(self) -> str:
        selected_mode = str(self.model.settings.get("selected_mode", "Q&A") or "Q&A")
        return self.local_llm_recommender_service.wizard_mode_to_use_case(selected_mode)

    def _local_gguf_recommendations(self, *, use_case: str | None = None) -> dict[str, Any]:
        requested_use_case = str(use_case or self._current_local_gguf_use_case() or "general")
        return self.local_llm_recommender_service.recommend_models(
            use_case=requested_use_case,
            settings=self.model.settings,
            current_mode=str(self.model.settings.get("selected_mode", "Q&A") or "Q&A"),
        )

    def _sync_local_gguf_recommendations(self, *, use_case: str | None = None) -> None:
        payload = self._local_gguf_recommendations(use_case=use_case)
        self._safe_view_call("set_local_gguf_recommendations", payload)

    def _apply_detected_hardware_overrides(self, overrides: dict[str, Any]) -> None:
        def _float(value: Any) -> float:
            try:
                return float(value or 0.0)
            except (TypeError, ValueError):
                return 0.0

        def _int(value: Any) -> int:
            try:
                return int(float(value or 0))
            except (TypeError, ValueError):
                return 0

        normalized = {
            "hardware_override_enabled": bool(overrides.get("hardware_override_enabled", False)),
            "hardware_override_total_ram_gb": _float(overrides.get("hardware_override_total_ram_gb")),
            "hardware_override_available_ram_gb": _float(overrides.get("hardware_override_available_ram_gb")),
            "hardware_override_gpu_name": str(overrides.get("hardware_override_gpu_name") or ""),
            "hardware_override_gpu_vram_gb": _float(overrides.get("hardware_override_gpu_vram_gb")),
            "hardware_override_gpu_count": _int(overrides.get("hardware_override_gpu_count")),
            "hardware_override_backend": str(overrides.get("hardware_override_backend") or ""),
            "hardware_override_unified_memory": bool(overrides.get("hardware_override_unified_memory", False)),
        }
        self.model.settings.update(normalized)
        self.model.save_settings(self.model.settings)
        self._safe_view_call("populate_settings", self.model.settings)
        self._sync_local_gguf_recommendations()

    def _set_build_index_enabled(self, enabled: bool) -> None:
        if callable(getattr(self.view, "set_build_index_enabled", None)):
            self.view.set_build_index_enabled(enabled)
            return
        self._set_widget_enabled(getattr(self.view, "btn_build_index", None), enabled)

    def _set_cancel_rag_enabled(self, enabled: bool) -> None:
        if callable(getattr(self.view, "set_cancel_rag_enabled", None)):
            self.view.set_cancel_rag_enabled(enabled)
            return
        self._set_widget_enabled(getattr(self.view, "btn_cancel_rag", None), enabled)

    def _set_model_switch_enabled(self, enabled: bool) -> None:
        if callable(getattr(self.view, "set_model_switch_enabled", None)):
            self.view.set_model_switch_enabled(enabled)
            return
        self._set_widget_enabled(getattr(self.view, "_llm_status_badge", None), enabled)

    def _sync_profile_options(self) -> None:
        labels = self.profile_repository.list_labels()
        current = self._current_profile_label()
        if current not in labels:
            current = "Built-in: Default"
            self.model.current_profile_label = current
            self.model.settings["selected_profile"] = current
        self._safe_view_call("set_profile_options", labels, current)

    def _sync_local_model_rows(self) -> None:
        registry = self.model.settings.get("local_model_registry", {})
        rows: list[dict[str, Any]] = []
        active_llm_path = str(self.model.settings.get("local_gguf_model_path", "") or "").strip()
        active_st_name = str(
            self.model.settings.get("local_st_model_name")
            or self.model.settings.get("sentence_transformers_model")
            or ""
        ).strip()
        for entry in self.local_model_registry_service.list_entries(registry):
            rows.append(
                {
                    "entry_id": entry.entry_id,
                    "model_type": entry.model_type,
                    "name": entry.name,
                    "value": entry.value,
                    "path": entry.path,
                    "metadata": dict(entry.metadata or {}),
                    "active_llm": bool(entry.model_type == "gguf" and (entry.path or entry.value) == active_llm_path),
                    "active_embedding": bool(
                        entry.model_type == "sentence_transformers"
                        and entry.value == active_st_name
                    ),
                }
            )
        dependency_status = {
            "llama_cpp_python": importlib.util.find_spec("llama_cpp") is not None,
            "sentence_transformers": importlib.util.find_spec("sentence_transformers") is not None,
        }
        self._safe_view_call("set_local_model_rows", rows, dependency_status)

    def _index_option_rows(self) -> list[dict[str, Any]]:
        root = pathlib.Path(getattr(self.model, "index_storage_dir", pathlib.Path(".")))
        if not root.exists():
            return []
        rows: list[dict[str, Any]] = []
        for manifest in list_index_manifests(root):
            rows.append(
                {
                    "index_id": manifest.index_id,
                    "label": (
                        f"{manifest.index_id} "
                        f"({manifest.backend or 'json'} · {manifest.document_count} file(s) · "
                        f"{manifest.chunk_count} chunk(s))"
                    ),
                    "path": str(manifest.manifest_path),
                    "vector_backend": str(manifest.backend or "json"),
                    "document_count": int(manifest.document_count or 0),
                    "chunk_count": int(manifest.chunk_count or 0),
                    "created_at": manifest.created_at,
                    "embedding_signature": manifest.embedding_signature,
                    "collection_name": str(manifest.collection_name or ""),
                    "legacy_compat": bool(manifest.legacy_compat),
                }
            )
        return rows

    def _rebuild_brain_graph(self, *, selected_node_id: str | None = None) -> None:
        previous = getattr(self.model, "brain_graph", None)
        graph = BrainGraph().build_from_indexes_and_sessions(
            getattr(self.model, "available_indexes", []),
            getattr(self.model, "session_list", []),
        )
        graph.copy_positions_from(previous if isinstance(previous, BrainGraph) else None)
        if isinstance(previous, BrainGraph):
            graph.apply_force_layout(iterations=70)
        preferred = str(
            selected_node_id
            or getattr(self.model, "selected_brain_node", "")
            or self._safe_view_call("get_selected_brain_node_id")
            or ""
        ).strip()
        if preferred and preferred not in graph.nodes:
            preferred = ""
        if not preferred and "category:brain" in graph.nodes:
            preferred = "category:brain"
        self.model.brain_graph = graph
        self.model.selected_brain_node = preferred
        self._safe_view_call("set_brain_graph", graph, preferred)

    def refresh_available_indexes(self, select_path: str | None = None) -> None:
        rows = self._index_option_rows()
        self.model.available_indexes = rows
        selected = str(
            select_path
            or getattr(self.model, "active_index_path", "")
            or self.model.settings.get("selected_index_path", "")
            or ""
        )
        self._safe_view_call("set_available_indexes", rows, selected)
        preferred_node_id = str(getattr(self.model, "selected_brain_node", "") or "")
        if not preferred_node_id and getattr(self.model, "active_index_id", ""):
            preferred_node_id = f"index:{self.model.active_index_id}"
        self._rebuild_brain_graph(selected_node_id=preferred_node_id)

    def _persist_active_index_selection(self, bundle: IndexBundle | None, *, save: bool = True) -> None:
        if bundle is None:
            return
        self.model.settings["selected_index_path"] = str(bundle.index_path or "")
        self.model.settings["selected_collection_name"] = str(
            bundle.metadata.get("collection_name") or bundle.index_id or ""
        )
        self.model.settings["index_embedding_signature"] = str(bundle.embedding_signature or "")
        self.model.settings["vector_db_type"] = str(bundle.vector_backend or "json")
        if save:
            self.model.save_settings(self.model.settings)

    def _load_bundle_from_path(
        self,
        index_path: str | pathlib.Path,
        *,
        persist: bool = False,
    ) -> IndexBundle | None:
        path = pathlib.Path(index_path)
        if not path.exists():
            self.model.rag_blocked_reason = f"Index not found: {path}"
            self._safe_view_call("set_status", self.model.rag_blocked_reason)
            return None
        try:
            initial_bundle = load_index_bundle(path)
        except Exception as exc:
            self.model.rag_blocked_reason = f"Could not load index: {exc}"
            self._safe_view_call("set_status", self.model.rag_blocked_reason)
            self._log.warning("Could not load index '%s': %s", path, exc)
            return None

        backend_settings = {
            **dict(self.model.settings),
            **dict(initial_bundle.metadata.get("weaviate_settings") or {}),
            "vector_db_type": str(initial_bundle.vector_backend or "json"),
        }
        adapter = resolve_vector_store(backend_settings)
        available, reason = adapter.is_available(backend_settings)
        try:
            bundle = adapter.load(path)
        except Exception as exc:
            self.model.rag_blocked_reason = f"Could not restore index: {exc}"
            self._safe_view_call("set_status", self.model.rag_blocked_reason)
            self._log.warning("Could not restore index '%s': %s", path, exc)
            return None

        self._apply_index_bundle(bundle)
        if available:
            self.model.rag_blocked_reason = ""
        else:
            self.model.rag_blocked_reason = reason
            self._safe_view_call(
                "append_log",
                f"[index] Restored index metadata, but RAG is blocked: {reason}",
            )
        if persist:
            self._persist_active_index_selection(bundle)
        self.refresh_available_indexes(select_path=str(bundle.index_path or path))
        self._render_bundle_metadata(bundle, traces={})
        return bundle

    def _restore_index_from_settings(self) -> None:
        candidate = str(self.model.settings.get("selected_index_path", "") or "").strip()
        if not candidate:
            selected_collection = str(self.model.settings.get("selected_collection_name", "") or "").strip()
            for row in self.model.available_indexes:
                if str(row.get("index_id", "") or "") == selected_collection or str(row.get("collection_name", "") or "") == selected_collection:
                    candidate = str(row.get("path", "") or "")
                    break
        if candidate:
            self._load_bundle_from_path(candidate, persist=False)

    @staticmethod
    def _flatten_trace_events(trace_payload: dict[str, list[dict[str, Any]]] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if isinstance(trace_payload, list):
            events = [dict(item) for item in trace_payload if isinstance(item, dict)]
        else:
            events = []
            for run_id, rows in (trace_payload or {}).items():
                for row in rows or []:
                    if not isinstance(row, dict):
                        continue
                    item = dict(row)
                    item.setdefault("run_id", run_id)
                    events.append(item)
        return sorted(events, key=lambda item: str(item.get("timestamp") or ""))

    def _render_bundle_metadata(
        self,
        bundle: IndexBundle | None,
        traces: dict[str, list[dict[str, Any]]] | list[dict[str, Any]] | None,
    ) -> None:
        if bundle is None:
            self._safe_view_call("render_events", [])
            self._safe_view_call("render_semantic_regions", [])
            self._safe_view_call("render_document_outline", [], "")
            self._safe_view_call("render_grounding_info", "")
        else:
            summary = (
                f"Active index: {bundle.index_id}  |  "
                f"{bundle.vector_backend or 'json'}  |  "
                f"{len(bundle.documents)} file(s)  |  {len(bundle.chunks)} chunk(s)"
            )
            self._safe_view_call("set_active_index_summary", summary, bundle.index_path)
            self._safe_view_call("render_events", list(bundle.events))
            self._safe_view_call("render_semantic_regions", list(bundle.semantic_regions))
            self._safe_view_call(
                "render_document_outline",
                list(bundle.document_outline),
                str(bundle.grounding_html_path or ""),
            )
            grounding_text = str(bundle.grounding_html_path or "")
            if not grounding_text:
                metadata = dict(bundle.metadata or {})
                selected_sources = metadata.get("selected_source_paths") or []
                grounding_text = "\n".join(str(item) for item in selected_sources)
            self._safe_view_call("render_grounding_info", grounding_text)
        self._safe_view_call("render_trace_events", self._flatten_trace_events(traces))

    def _session_trace_payload(self, detail: Any) -> dict[str, list[dict[str, Any]]]:
        messages = list(getattr(detail, "messages", []) or [])
        run_ids = []
        for message in messages:
            run_id = str(getattr(message, "run_id", "") or "")
            if run_id and run_id not in run_ids:
                run_ids.append(run_id)
        return self.trace_store.read_runs(run_ids)

    def _profile_from_settings(self, name: str) -> AgentProfile:
        return AgentProfile(
            name=str(name or "Custom Profile").strip() or "Custom Profile",
            system_instructions=str(self.model.settings.get("system_instructions", "") or ""),
            retrieval_strategy={
                "retrieve_k": int(self.model.settings.get("retrieval_k", 25) or 25),
                "final_k": int(self.model.settings.get("top_k", 5) or 5),
                "mmr_lambda": float(self.model.settings.get("mmr_lambda", 0.5) or 0.5),
                "search_type": str(self.model.settings.get("search_type", "similarity") or "similarity"),
            },
            iteration_strategy={
                "agentic_mode": bool(self.model.settings.get("agentic_mode", False)),
                "max_iterations": int(self.model.settings.get("agentic_max_iterations", 2) or 2),
            },
            comprehension_pipeline_on_ingest={
                "enabled": bool(self.model.settings.get("build_comprehension_index", False)),
                "depth": str(self.model.settings.get("comprehension_extraction_depth", "Standard") or "Standard"),
            },
            mode_default=str(self.model.settings.get("selected_mode", "Q&A") or "Q&A"),
            provider=str(self.model.settings.get("llm_provider", "") or ""),
            model=self._effective_llm_model(),
            retrieval_mode=str(self.model.settings.get("retrieval_mode", "flat") or "flat"),
            llm_max_tokens=int(self.model.settings.get("llm_max_tokens", 0) or 0) or None,
            frontier_toggles={
                key: self.model.settings.get(key)
                for key in (
                    "enable_summarizer",
                    "enable_langextract",
                    "enable_structured_extraction",
                    "enable_recursive_memory",
                    "enable_recursive_retrieval",
                    "enable_citation_v2",
                    "enable_claim_level_grounding_citefix_lite",
                    "agent_lightning_enabled",
                )
            },
            digest_usage=bool(self.model.settings.get("build_digest_index", True)),
        )

    @staticmethod
    def _wizard_preset_to_runtime_mode(preset: str) -> str:
        mapping = {
            "Q&A": "Q&A",
            "Book summary": "Summary",
            "Summary": "Summary",
            "Tutor": "Tutor",
            "Research": "Research",
            "Evidence Pack": "Evidence Pack",
        }
        return mapping.get(str(preset or "").strip(), "Q&A")

    def _active_index_has_deepread_metadata(self) -> bool:
        bundle = self._current_index_bundle()
        if bundle is None:
            return False
        if bundle.document_outline:
            return True
        for chunk in bundle.chunks:
            header_path = str(chunk.get("header_path") or "").strip()
            metadata = dict(chunk.get("metadata") or {})
            if header_path or str(metadata.get("header_path") or "").strip():
                return True
        return False

    def _current_state_constraints(
        self,
        settings: dict[str, Any] | None = None,
        *,
        scope: str = "query",
    ) -> dict[str, Any]:
        effective = dict(self.model.settings)
        if settings:
            effective.update(settings)
        blockers: list[str] = []
        advisories: list[str] = []
        if bool(effective.get("structure_aware_ingestion")) and bool(
            effective.get("semantic_layout_ingestion")
        ):
            blockers.append(
                "Structure-aware ingestion cannot be combined with Semantic Layout. Disable one option."
            )
        if bool(effective.get("secure_mode")) and not bool(
            effective.get("enable_summarizer", True)
        ):
            blockers.append(
                "Secure mode requires the summarizer safety pass. Enable summarizer or disable Secure mode."
            )
        if scope == "query" and bool(effective.get("deepread_mode")) and not self._active_index_has_deepread_metadata():
            blockers.append(
                "DeepRead requires document outline/header metadata in the active index."
            )
        active_backend = str(
            effective.get("vector_db_type")
            or self._current_vector_backend()
            or "json"
        )
        if bool(effective.get("semantic_layout_ingestion")) and active_backend != "chroma":
            advisories.append(
                "Semantic Layout is tuned for Chroma indexes; non-Chroma backends remain experimental."
            )
        if scope == "build" and bool(effective.get("deepread_mode")):
            advisories.append(
                "DeepRead build will force structure-aware ingestion and comprehension metadata."
            )
        return {"blockers": blockers, "advisories": advisories}

    def _confirm_experimental_override(self, scope: str, blockers: list[str]) -> bool:
        if not blockers:
            return True
        if not bool(self.model.settings.get("experimental_override", False)):
            return False

        body = "\n".join(f"- {item}" for item in blockers)
        approved = self._ask_yes_no(
            "Experimental override",
            f"{scope} has incompatible settings:\n\n{body}\n\nProceed anyway with Experimental override?",
        )
        if approved:
            self._safe_view_call("append_log", f"[override] {scope}: {'; '.join(blockers)}")
        return approved

    def _grounding_output_dir(self) -> pathlib.Path:
        bundle = self._current_index_bundle()
        active_path = pathlib.Path(str(getattr(self.model, "active_index_path", "") or ""))
        if bundle is not None and str(bundle.index_path or "").strip():
            active_path = pathlib.Path(str(bundle.index_path or ""))
        if active_path.exists():
            if active_path.is_dir():
                return active_path
            if active_path.name == "manifest.json":
                return active_path.parent / "artifacts"
            return active_path.parent
        return pathlib.Path(getattr(self.model, "index_storage_dir", pathlib.Path(".")))

    def _persist_runtime_artifacts(self, bundle: IndexBundle | None) -> None:
        if bundle is None or not str(bundle.index_path or "").strip():
            return
        try:
            refresh_index_bundle(bundle)
        except Exception as exc:
            self._safe_view_call("append_log", f"[artifacts] Failed to refresh index metadata: {exc}")

    def _apply_profile_to_settings(self, profile: AgentProfile, *, label: str) -> None:
        self.model.current_profile_label = label
        self.model.settings["selected_profile"] = label
        if profile.mode_default:
            self.model.settings["selected_mode"] = profile.mode_default
        if profile.provider:
            self.model.settings["llm_provider"] = profile.provider
        if profile.model:
            self.model.settings["llm_model"] = profile.model
            self.model.settings["llm_model_custom"] = profile.model
        if profile.retrieval_mode:
            self.model.settings["retrieval_mode"] = profile.retrieval_mode
        if profile.llm_max_tokens is not None:
            self.model.settings["llm_max_tokens"] = profile.llm_max_tokens
        retrieval = dict(profile.retrieval_strategy or {})
        if "retrieve_k" in retrieval:
            self.model.settings["retrieval_k"] = int(retrieval["retrieve_k"] or 1)
        if "final_k" in retrieval:
            self.model.settings["top_k"] = int(retrieval["final_k"] or 1)
        if "mmr_lambda" in retrieval:
            self.model.settings["mmr_lambda"] = float(retrieval["mmr_lambda"] or 0.0)
        if "search_type" in retrieval:
            self.model.settings["search_type"] = str(retrieval["search_type"] or "similarity")
        iteration = dict(profile.iteration_strategy or {})
        if "agentic_mode" in iteration:
            self.model.settings["agentic_mode"] = bool(iteration["agentic_mode"])
        if "max_iterations" in iteration:
            self.model.settings["agentic_max_iterations"] = int(iteration["max_iterations"] or 1)
        if profile.system_instructions:
            self.model.settings["system_instructions"] = profile.system_instructions
        for key, value in dict(profile.frontier_toggles or {}).items():
            self.model.settings[key] = value
        if profile.digest_usage is not None:
            self.model.settings["build_digest_index"] = bool(profile.digest_usage)
        comprehension = profile.comprehension_pipeline_on_ingest
        if isinstance(comprehension, dict):
            self.model.settings["build_comprehension_index"] = bool(comprehension.get("enabled", False))
            if comprehension.get("depth"):
                self.model.settings["comprehension_extraction_depth"] = str(comprehension["depth"])

    def _apply_wizard_result(self, result: dict[str, Any]) -> None:
        runtime_mode = self._wizard_preset_to_runtime_mode(
            str(result.get("mode_preset", self.model.settings.get("selected_mode", "Q&A")) or "Q&A")
        )
        updates = {
            "chunk_size": int(result.get("chunk_size", self.model.settings.get("chunk_size", 1000)) or 1000),
            "chunk_overlap": int(result.get("chunk_overlap", self.model.settings.get("chunk_overlap", 100)) or 100),
            "build_digest_index": bool(result.get("build_digest_index", self.model.settings.get("build_digest_index", True))),
            "build_comprehension_index": bool(
                result.get(
                    "build_comprehension_index",
                    self.model.settings.get("build_comprehension_index", False),
                )
            ),
            "comprehension_extraction_depth": str(
                result.get(
                    "comprehension_extraction_depth",
                    self.model.settings.get("comprehension_extraction_depth", "Standard"),
                )
                or "Standard"
            ),
            "prefer_comprehension_index": bool(
                result.get(
                    "prefer_comprehension_index",
                    self.model.settings.get("prefer_comprehension_index", True),
                )
            ),
            "llm_provider": str(result.get("llm_provider", self.model.settings.get("llm_provider", "")) or ""),
            "llm_model": str(result.get("llm_model", self._effective_llm_model()) or ""),
            "embedding_provider": str(
                result.get("embedding_provider", self.model.settings.get("embedding_provider", "")) or ""
            ),
            "embedding_model": str(result.get("embedding_model", self._effective_embedding_model()) or ""),
            "selected_mode": runtime_mode,
            "basic_wizard_completed": True,
            "startup_mode_setting": "advanced",
            "last_used_mode": "advanced",
            "deepread_mode": bool(result.get("deepread_mode", self.model.settings.get("deepread_mode", False))),
            "local_gguf_models_dir": str(
                result.get(
                    "local_gguf_models_dir",
                    self.model.settings.get(
                        "local_gguf_models_dir",
                        self.local_llm_recommender_service.default_models_dir(self.model.settings),
                    ),
                )
                or ""
            ),
            "hardware_override_enabled": bool(
                result.get("hardware_override_enabled", self.model.settings.get("hardware_override_enabled", False))
            ),
            "hardware_override_total_ram_gb": float(
                result.get(
                    "hardware_override_total_ram_gb",
                    self.model.settings.get("hardware_override_total_ram_gb", 0.0),
                )
                or 0.0
            ),
            "hardware_override_available_ram_gb": float(
                result.get(
                    "hardware_override_available_ram_gb",
                    self.model.settings.get("hardware_override_available_ram_gb", 0.0),
                )
                or 0.0
            ),
            "hardware_override_gpu_name": str(
                result.get("hardware_override_gpu_name", self.model.settings.get("hardware_override_gpu_name", ""))
                or ""
            ),
            "hardware_override_gpu_vram_gb": float(
                result.get(
                    "hardware_override_gpu_vram_gb",
                    self.model.settings.get("hardware_override_gpu_vram_gb", 0.0),
                )
                or 0.0
            ),
            "hardware_override_gpu_count": int(
                result.get("hardware_override_gpu_count", self.model.settings.get("hardware_override_gpu_count", 0))
                or 0
            ),
            "hardware_override_backend": str(
                result.get("hardware_override_backend", self.model.settings.get("hardware_override_backend", ""))
                or ""
            ),
            "hardware_override_unified_memory": bool(
                result.get(
                    "hardware_override_unified_memory",
                    self.model.settings.get("hardware_override_unified_memory", False),
                )
            ),
        }
        typed_keys = {
            "retrieval_k": int,
            "top_k": int,
            "mmr_lambda": float,
            "retrieval_mode": str,
            "agentic_mode": bool,
            "agentic_max_iterations": int,
            "output_style": str,
            "use_reranker": bool,
        }
        for key, caster in typed_keys.items():
            if key not in result:
                continue
            raw_value = result[key]
            if caster is bool:
                updates[key] = bool(raw_value)
                continue
            try:
                updates[key] = caster(raw_value)
            except (TypeError, ValueError):
                continue
        if updates["deepread_mode"]:
            updates["structure_aware_ingestion"] = True
            updates["build_comprehension_index"] = True
            updates["prefer_comprehension_index"] = True
        for key in (
            "api_key_openai",
            "api_key_anthropic",
            "api_key_google",
            "api_key_xai",
            "vector_db_type",
        ):
            if key in result:
                updates[key] = result[key]
        previous_provider = str(self.model.settings.get("llm_provider", "") or "")
        previous_model = str(self._effective_llm_model() or "")
        previous_model_custom = str(self.model.settings.get("llm_model_custom", "") or "")
        working_settings = dict(self.model.settings)
        working_settings.update(updates)
        import_request: dict[str, Any] | None = None
        selected_recommendation = result.get("selected_local_gguf_recommendation")
        if (
            working_settings.get("llm_provider") == "local_gguf"
            and bool(result.get("import_local_gguf_recommendation", False))
            and isinstance(selected_recommendation, dict)
        ):
            activation_request = self._resolve_local_gguf_activation_request(
                dict(selected_recommendation),
                requested=True,
                allow_import_only_fallback=True,
            )
            if activation_request is not None:
                import_request = {
                    "recommendation": dict(selected_recommendation),
                    "activate": bool(activation_request),
                    "origin": "wizard",
                    "settings_snapshot": dict(working_settings),
                }
            if not self._has_valid_local_gguf_path(working_settings):
                working_settings["llm_provider"] = previous_provider
                working_settings["llm_model"] = previous_model
                working_settings["llm_model_custom"] = previous_model_custom
        elif working_settings.get("llm_provider") == "local_gguf" and not self._has_valid_local_gguf_path(working_settings):
            working_settings["llm_provider"] = previous_provider
            working_settings["llm_model"] = previous_model
            working_settings["llm_model_custom"] = previous_model_custom
        self.model.settings = working_settings
        self.model.save_settings(self.model.settings)
        self._safe_view_call("populate_settings", self.model.settings)
        self._sync_local_model_rows()
        self._sync_local_gguf_recommendations()

        self._queued_local_gguf_import = None
        selected_index = str(result.get("selected_index_path", "") or "").strip()
        source_file = str(result.get("file_path", "") or "").strip()
        if selected_index:
            self._load_bundle_from_path(selected_index, persist=True)
        if source_file:
            self.model.set_documents([source_file])
            self._safe_view_call("set_file_list", [pathlib.Path(source_file).name])
            self._queued_local_gguf_import = import_request
            self.on_build_index()
        elif import_request is not None:
            self._start_local_gguf_import_task(
                dict(import_request.get("recommendation") or {}),
                activate=bool(import_request.get("activate", False)),
                origin=str(import_request.get("origin", "wizard") or "wizard"),
                settings_snapshot=dict(import_request.get("settings_snapshot") or working_settings),
            )
        self._safe_view_call("switch_view", "chat")
        self._safe_view_call("set_status", "Setup complete.")

    # ------------------------------------------------------------------
    # Event wiring
    # ------------------------------------------------------------------

    def wire_events(self) -> None:
        """Bind view widgets to controller callbacks."""
        if not self._connect_signal(getattr(self.view, "closeRequested", None), self._on_close):
            root = getattr(self.view, "root", None)
            if root is not None and hasattr(root, "protocol"):
                root.protocol("WM_DELETE_WINDOW", self._on_close)

        self._connect_signal(getattr(self.view, "openFilesRequested", None), self.on_open_files)
        self._connect_signal(getattr(self.view, "buildIndexRequested", None), self.on_build_index)
        self._connect_signal(getattr(self.view, "saveSettingsRequested", None), self.on_save_settings)
        self._connect_signal(getattr(self.view, "sendRequested", None), self._on_send_clicked)
        self._connect_signal(getattr(self.view, "cancelRequested", None), self.on_cancel_job)
        self._connect_signal(getattr(self.view, "newChatRequested", None), self.on_new_chat)
        self._connect_signal(getattr(self.view, "loadProfileRequested", None), self.on_load_profile)
        self._connect_signal(getattr(self.view, "saveProfileRequested", None), self.on_save_profile)
        self._connect_signal(getattr(self.view, "duplicateProfileRequested", None), self.on_duplicate_profile)
        self._connect_signal(getattr(self.view, "feedbackRequested", None), self.on_submit_feedback)
        self._connect_signal(getattr(self.view, "historyOpenRequested", None), self.on_open_session)
        self._connect_signal(getattr(self.view, "historyDeleteRequested", None), self.on_delete_session)
        self._connect_signal(getattr(self.view, "historyRenameRequested", None), self.on_rename_session)
        self._connect_signal(getattr(self.view, "historyDuplicateRequested", None), self.on_duplicate_session)
        self._connect_signal(getattr(self.view, "historyExportRequested", None), self.on_export_session)
        self._connect_signal(getattr(self.view, "historyRefreshRequested", None), self.refresh_history_rows)
        self._connect_signal(getattr(self.view, "historySearchRequested", None), self.on_history_search_changed)
        self._connect_signal(getattr(self.view, "historySelectionRequested", None), self.on_history_selection_changed)
        self._connect_signal(getattr(self.view, "historyProfileFilterRequested", None), self.on_history_profile_changed)
        self._connect_signal(getattr(self.view, "brainNodeSelected", None), self.on_brain_node_selected)
        self._connect_signal(getattr(self.view, "brainNodeActivated", None), self.on_brain_node_activated)
        self._connect_signal(getattr(self.view, "brainRefreshRequested", None), self.on_brain_refresh_requested)
        self._connect_signal(getattr(self.view, "loadIndexRequested", None), self.on_load_selected_index)
        self._connect_signal(getattr(self.view, "addLocalGgufRequested", None), self.on_add_local_gguf_model)
        self._connect_signal(getattr(self.view, "addLocalSentenceTransformerRequested", None), self.on_add_local_st_model)
        self._connect_signal(getattr(self.view, "removeLocalModelRequested", None), self.on_remove_local_model)
        self._connect_signal(getattr(self.view, "activateLocalModelRequested", None), self.on_activate_local_model)
        self._connect_signal(getattr(self.view, "openLocalModelFolderRequested", None), self.on_open_local_model_folder)
        self._connect_signal(getattr(self.view, "installLocalDependencyRequested", None), self.on_install_local_dependency)
        self._connect_signal(
            getattr(self.view, "refreshLocalGgufRecommendationsRequested", None),
            self.on_refresh_local_gguf_recommendations,
        )
        self._connect_signal(
            getattr(self.view, "importLocalGgufRecommendationRequested", None),
            self.on_import_local_gguf_recommendation,
        )
        self._connect_signal(
            getattr(self.view, "applyLocalGgufRecommendationRequested", None),
            self.on_apply_local_gguf_recommendation,
        )
        self._connect_signal(
            getattr(self.view, "editHardwareAssumptionsRequested", None),
            self.on_edit_hardware_assumptions,
        )
        self._connect_signal(getattr(self.view, "quickModelChangeRequested", None), self.on_quick_model_change)

        self._configure_command(getattr(self.view, "btn_open_files", None), self.on_open_files)
        self._configure_command(getattr(self.view, "btn_build_index", None), self.on_build_index)
        self._configure_command(getattr(self.view, "btn_save_settings", None), self.on_save_settings)
        self._configure_command(getattr(self.view, "btn_send", None), self._on_send_clicked)
        self._configure_command(getattr(self.view, "btn_cancel_rag", None), self.on_cancel_job)
        self._configure_command(getattr(self.view, "btn_new_chat", None), self.on_new_chat)
        self._configure_command(getattr(self.view, "btn_reset_test_mode", None), self.reset_test_mode)
        self._configure_command(getattr(self.view, "btn_profile_load", None), self.on_load_profile)
        self._configure_command(getattr(self.view, "btn_profile_save", None), self.on_save_profile)
        self._configure_command(getattr(self.view, "btn_profile_duplicate", None), self.on_duplicate_profile)
        self._configure_command(getattr(self.view, "btn_feedback_up", None), lambda: self.on_submit_feedback(1))
        self._configure_command(getattr(self.view, "btn_feedback_down", None), lambda: self.on_submit_feedback(-1))
        self._configure_command(getattr(self.view, "btn_history_new_chat", None), self.on_new_chat)
        self._configure_command(getattr(self.view, "btn_history_open", None), self.on_open_session)
        self._configure_command(getattr(self.view, "btn_history_delete", None), self.on_delete_session)
        self._configure_command(getattr(self.view, "btn_history_rename", None), self.on_rename_session)
        self._configure_command(getattr(self.view, "btn_history_duplicate", None), self.on_duplicate_session)
        self._configure_command(getattr(self.view, "btn_history_export", None), self.on_export_session)
        self._configure_command(getattr(self.view, "btn_history_refresh", None), self.refresh_history_rows)
        self._configure_command(getattr(self.view, "btn_library_load_index", None), self.on_load_selected_index)
        self._configure_command(getattr(self.view, "btn_add_local_gguf_model", None), self.on_add_local_gguf_model)
        self._configure_command(getattr(self.view, "btn_add_local_st_model", None), self.on_add_local_st_model)
        self._configure_command(getattr(self.view, "btn_remove_local_model", None), self.on_remove_local_model)
        self._configure_command(getattr(self.view, "btn_activate_local_model_llm", None), lambda: self.on_activate_local_model("llm"))
        self._configure_command(getattr(self.view, "btn_activate_local_model_embedding", None), lambda: self.on_activate_local_model("embedding"))
        self._configure_command(getattr(self.view, "btn_open_local_model_folder", None), self.on_open_local_model_folder)
        self._configure_command(getattr(self.view, "btn_install_local_gguf_dep", None), lambda: self.on_install_local_dependency(["llama-cpp-python"]))
        self._configure_command(getattr(self.view, "btn_install_local_st_dep", None), lambda: self.on_install_local_dependency(["sentence-transformers"]))
        self._configure_command(
            getattr(self.view, "btn_refresh_local_gguf_recommendations", None),
            self.on_refresh_local_gguf_recommendations,
        )
        self._configure_command(
            getattr(self.view, "btn_import_local_gguf_recommendation", None),
            self.on_import_local_gguf_recommendation,
        )
        self._configure_command(
            getattr(self.view, "btn_apply_local_gguf_recommendation", None),
            self.on_apply_local_gguf_recommendation,
        )
        self._configure_command(
            getattr(self.view, "btn_edit_hardware_assumptions", None),
            self.on_edit_hardware_assumptions,
        )

        bind_history_search = getattr(self.view, "bind_history_search", None)
        if callable(bind_history_search):
            bind_history_search(self.on_history_search_changed)
        bind_history_selection = getattr(self.view, "bind_history_selection", None)
        if callable(bind_history_selection):
            bind_history_selection(self.on_history_selection_changed)
        bind_history_profile = getattr(self.view, "bind_history_profile_filter", None)
        if callable(bind_history_profile):
            bind_history_profile(self.on_history_profile_changed)

        self.view.set_mode_state_callback(self._on_mode_state_changed)
        self.view.populate_settings(self.model.settings)
        self._sync_local_gguf_recommendations()
        self.refresh_history_rows(update_detail=False)

    def _on_mode_state_changed(self, mode_state: dict[str, str]) -> None:
        """Keep runtime canonical chat mode state in the model settings."""
        self.model.settings["selected_mode"] = mode_state.get("selected_mode", "Q&A")
        self.model.settings["chat_path"] = mode_state.get("chat_path", "RAG")

    def bootstrap_app(self) -> None:
        """Synchronize profiles, indexes, local models, and startup mode."""
        self._sync_profile_options()
        self._sync_local_model_rows()
        self._sync_local_gguf_recommendations()
        self.refresh_available_indexes()
        self.refresh_history_rows(update_detail=False)
        self._restore_index_from_settings()
        self._safe_view_call("select_profile_label", self.model.current_profile_label)
        startup_mode = str(
            self.model.settings.get("startup_mode_setting")
            or self.model.settings.get("last_used_mode")
            or "advanced"
        ).strip().lower()
        if startup_mode == "basic":
            self.run_setup_wizard()
        elif startup_mode == "test":
            self.start_test_mode()
        else:
            self.switch_to_advanced_mode(save=False)
        self.model.bootstrap_complete = True

    def switch_to_advanced_mode(self, *, save: bool = True) -> None:
        self.model.settings["startup_mode_setting"] = "advanced"
        self.model.settings["last_used_mode"] = "advanced"
        self.model.settings["basic_wizard_completed"] = True
        if save:
            self.model.save_settings(self.model.settings)
        self._safe_view_call("set_status", "Advanced mode ready.")

    def run_setup_wizard(self) -> None:
        self.model.settings["startup_mode_setting"] = "basic"
        self.model.settings["last_used_mode"] = "basic"
        self.model.settings["basic_wizard_completed"] = False
        result = self._safe_view_call(
            "show_setup_wizard",
            self._wizard_initial_state(),
            self._index_option_rows(),
        )
        if not isinstance(result, dict):
            self._safe_view_call("set_status", "Setup wizard dismissed.")
            return
        self._apply_wizard_result(result)

    def start_test_mode(self) -> None:
        self.model.settings.update(
            {
                "startup_mode_setting": "test",
                "last_used_mode": "test",
                "llm_provider": "mock",
                "embedding_provider": "mock",
                "llm_model": "mock-test-v1",
                "embedding_model": "mock-embed-v1",
                "vector_db_type": "json",
                "chunk_size": 450,
                "chunk_overlap": 80,
                "retrieval_k": 8,
                "top_k": 4,
                "build_digest_index": False,
            }
        )
        sample_file = self._ensure_test_mode_environment()
        self.model.set_documents([sample_file])
        self._safe_view_call("set_file_list", [pathlib.Path(sample_file).name])
        self._safe_view_call("set_prompt_text", "Summarize the sample timeline and cite supporting passages.")
        self._safe_view_call("set_status", "Preparing sample index for Test Mode…")
        self.model.save_settings(self.model.settings)
        self.on_build_index()

    def reset_test_mode(self) -> None:
        temp_dir = self._test_mode_temp_dir
        self._test_mode_temp_dir = ""
        self._test_mode_sample_file = ""
        self.model.settings["startup_mode_setting"] = "advanced"
        self.model.settings["last_used_mode"] = "advanced"
        self.model.current_session_id = ""
        self.model.loaded_session = None
        self.model.documents = []
        self.model.index_state = {"built": False, "doc_count": 0, "chunk_count": 0}
        self.model.chat_history = []
        self.model.chunks = []
        self.model.embeddings = []
        self.model.index_bundle = None
        self.model.active_index_id = ""
        self.model.active_index_path = ""
        self.model.rag_blocked_reason = ""
        self._clear_completed_response_state()
        self.model.save_settings(self.model.settings)
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        self._safe_view_call("set_file_list", [])
        self._safe_view_call("set_active_index_summary", "No persisted index selected.", "")
        self._safe_view_call("set_chat_transcript", [])
        self._safe_view_call("render_evidence_sources", [])
        self._safe_view_call("render_events", [])
        self._safe_view_call("render_semantic_regions", [])
        self._safe_view_call("render_document_outline", [], "")
        self._safe_view_call("render_trace_events", [])
        self._safe_view_call("render_grounding_info", "")
        self._safe_view_call("set_status", "Test mode reset.")

    def _wizard_initial_state(self) -> dict[str, Any]:
        current_mode = str(self.model.settings.get("selected_mode", "Q&A") or "Q&A")
        recommendation = recommend_auto_settings(
            file_path=self.model.documents[0] if self.model.documents else None,
            index_path=str(self.model.settings.get("selected_index_path", "") or "") or None,
        )
        local_gguf_use_case = self.local_llm_recommender_service.wizard_mode_to_use_case(current_mode)
        local_gguf_recommendations = self.local_llm_recommender_service.recommend_models(
            use_case=local_gguf_use_case,
            settings=self.model.settings,
            current_mode=current_mode,
        )
        return {
            "file_path": self.model.documents[0] if self.model.documents else "",
            "selected_index_path": str(self.model.settings.get("selected_index_path", "") or ""),
            "chunk_size": int(
                self.model.settings.get("chunk_size", recommendation.get("chunk_size", 1000)) or 1000
            ),
            "chunk_overlap": int(
                self.model.settings.get("chunk_overlap", recommendation.get("chunk_overlap", 100)) or 100
            ),
            "build_digest_index": bool(
                self.model.settings.get(
                    "build_digest_index",
                    recommendation.get("build_digest_index", True),
                )
            ),
            "build_comprehension_index": bool(
                self.model.settings.get(
                    "build_comprehension_index",
                    recommendation.get("build_comprehension_index", False),
                )
            ),
            "comprehension_extraction_depth": str(self.model.settings.get("comprehension_extraction_depth", "Standard") or "Standard"),
            "prefer_comprehension_index": bool(
                self.model.settings.get(
                    "prefer_comprehension_index",
                    recommendation.get("prefer_comprehension_index", True),
                )
            ),
            "llm_provider": str(self.model.settings.get("llm_provider", "") or ""),
            "llm_model": self._effective_llm_model(),
            "embedding_provider": str(self.model.settings.get("embedding_provider", "") or ""),
            "embedding_model": self._effective_embedding_model(),
            "mode_preset": "Book summary" if current_mode == "Summary" else current_mode,
            "retrieval_k": int(self.model.settings.get("retrieval_k", recommendation.get("retrieval_k", 25)) or 25),
            "top_k": int(self.model.settings.get("top_k", recommendation.get("final_k", 5)) or 5),
            "mmr_lambda": float(
                self.model.settings.get("mmr_lambda", recommendation.get("mmr_lambda", 0.5)) or 0.5
            ),
            "retrieval_mode": str(
                self.model.settings.get("retrieval_mode", recommendation.get("retrieval_mode", "flat"))
                or "flat"
            ),
            "agentic_mode": bool(
                self.model.settings.get("agentic_mode", recommendation.get("agentic_mode", False))
            ),
            "agentic_max_iterations": int(
                self.model.settings.get(
                    "agentic_max_iterations",
                    recommendation.get("agentic_max_iterations", 2),
                )
                or 2
            ),
            "output_style": str(
                self.model.settings.get(
                    "output_style",
                    "Blinkist-style summary" if current_mode == "Summary" else "Default answer",
                )
                or ""
            ),
            "use_reranker": bool(
                self.model.settings.get("use_reranker", recommendation.get("use_reranker", False))
            ),
            "deepread_mode": bool(
                self.model.settings.get("deepread_mode", recommendation.get("deepread_mode", False))
            ),
            "wizard_recommendation": recommendation,
            "local_gguf_use_case": local_gguf_use_case,
            "local_gguf_recommendations": local_gguf_recommendations,
            "local_gguf_models_dir": str(
                self.local_llm_recommender_service.default_models_dir(self.model.settings)
            ),
            "hardware_override_enabled": bool(self.model.settings.get("hardware_override_enabled", False)),
            "hardware_override_total_ram_gb": float(self.model.settings.get("hardware_override_total_ram_gb", 0.0) or 0.0),
            "hardware_override_available_ram_gb": float(
                self.model.settings.get("hardware_override_available_ram_gb", 0.0) or 0.0
            ),
            "hardware_override_gpu_name": str(self.model.settings.get("hardware_override_gpu_name", "") or ""),
            "hardware_override_gpu_vram_gb": float(self.model.settings.get("hardware_override_gpu_vram_gb", 0.0) or 0.0),
            "hardware_override_gpu_count": int(self.model.settings.get("hardware_override_gpu_count", 0) or 0),
            "hardware_override_backend": str(self.model.settings.get("hardware_override_backend", "") or ""),
            "hardware_override_unified_memory": bool(
                self.model.settings.get("hardware_override_unified_memory", False)
            ),
        }

    def _ensure_test_mode_environment(self) -> str:
        if not self._test_mode_temp_dir:
            self._test_mode_temp_dir = tempfile.mkdtemp(prefix="axiom_test_mode_")
        sample_path = pathlib.Path(self._test_mode_temp_dir) / "sample_document.txt"
        sample_path.write_text(
            "January 2024: The team migrated the retrieval layer.\n"
            "March 2024: A follow-up review identified citation gaps.\n"
            "June 2024: The remediation added evidence-linked responses.\n",
            encoding="utf-8",
        )
        self._test_mode_sample_file = str(sample_path)
        return str(sample_path)

    # ------------------------------------------------------------------
    # Background task management
    # ------------------------------------------------------------------

    def start_task(self, task_name: str, fn: Callable[..., Any], /, *args: Any) -> None:
        """Submit *fn* to the background runner."""
        if self._active_token is not None:
            self._log.debug("Cancelling previous task before starting '%s'", task_name)
            self._active_token.cancel()
        token = CancelToken()
        self._active_token = token
        self._active_future = self.background_runner.submit(
            fn, *args, cancel_token=token, task_name=task_name
        )
        self._log.info("Task started: %s", task_name)
        self._set_cancel_rag_enabled(True)
        self._set_model_switch_enabled(False)

    def cancel_current_task(self) -> None:
        """Signal the active background task to stop (cooperative)."""
        if self._active_token is not None:
            self._active_token.cancel()
        self._safe_view_call("set_status", "Cancelling…")

    def shutdown(self) -> None:
        """Tear down the thread pool."""
        self._log.info("AppController shutting down")
        if self._active_token is not None:
            self._active_token.cancel()
        self.background_runner.shutdown(wait=False)

    # ------------------------------------------------------------------
    # Message dispatch (called by the poll loop in app.py every 100 ms)
    # ------------------------------------------------------------------

    def poll_and_dispatch(self) -> None:
        """Drain the message queue and update the view."""
        for msg in self.background_runner.poll_messages():
            self._handle_message(msg)
        if self._active_future is not None and self._active_future.done():
            self._active_future = None
            self._active_token = None
            self._pending_task_meta = {}
            self._safe_view_call("reset_progress")
            self._set_build_index_enabled(True)
            self._set_cancel_rag_enabled(False)
            self._set_model_switch_enabled(True)

    def _handle_message(self, msg: dict[str, Any]) -> None:
        mtype = msg.get("type")

        if mtype == "status":
            self._safe_view_call("set_status", msg.get("text", ""))
            self._safe_view_call("append_log", f"[status] {msg.get('text', '')}")

        elif mtype == "progress":
            current = int(msg.get("current", 0))
            total = msg.get("total")
            total = int(total) if total is not None else None
            self._safe_view_call("set_progress", current, total)

        elif mtype == "error":
            text = msg.get("text", "unknown error")
            tb   = msg.get("traceback", "")
            task_name = str(msg.get("task_name", "") or "")
            self._log.error("Task error [%s]: %s", task_name or "?", text)
            if tb:
                self._log.debug("Traceback:\n%s", tb.rstrip())
            self._safe_view_call("set_status", f"Error: {text}")
            self._safe_view_call("append_log", f"[error] {text}")
            if tb:
                self._safe_view_call("append_log", tb)
            if task_name == _TASK_IMPORT_LOCAL_GGUF:
                if "cancelled" not in str(text).lower():
                    self._offer_manual_local_gguf_fallback(
                        dict(getattr(self, "_pending_task_meta", {})),
                        reason=str(text or ""),
                    )
            elif task_name == _TASK_BUILD_INDEX:
                self._start_queued_local_gguf_import_if_any()

        elif mtype == "done":
            task   = msg.get("task_name", "")
            result = msg.get("result")
            self._log.info("Task complete: %s", task or "(unnamed)")

            if task == _TASK_BUILD_INDEX and isinstance(result, IndexBundle):
                self._apply_index_bundle(result, persist=True)
                self.model.rag_blocked_reason = ""
                self.refresh_available_indexes(select_path=result.index_path)
                self._render_bundle_metadata(result, traces={})
                info = (
                    f"Index ready — {len(result.chunks)} chunk(s) "
                    f"from {len(result.documents)} file(s)."
                )
                self._safe_view_call("set_index_info", info)
                self._safe_view_call("set_status", info)
                self._safe_view_call("append_log", f"[done]  {info}")
                self._start_queued_local_gguf_import_if_any()

            elif task == _TASK_IMPORT_LOCAL_GGUF and isinstance(result, dict):
                meta = dict(getattr(self, "_pending_task_meta", {}))
                state = str(result.get("state") or "")
                if state == "needs_selection":
                    plan_payload = dict(result.get("plan") or {})
                    plan = self._import_plan_from_payload(plan_payload)
                    candidate_rows = list(result.get("candidate_files") or [])
                    selected_name = ""
                    picker = getattr(self.view, "pick_local_gguf_repo_file", None)
                    if callable(picker):
                        selected_name = str(
                            picker(
                                candidate_rows,
                                "Choose GGUF File",
                                plan.manual_reason or "Select the GGUF file to import.",
                            )
                            or ""
                        )
                    if not selected_name:
                        selected_name = self._pick_item_from_list(
                            "Choose GGUF File",
                            plan.manual_reason or "Select the GGUF file to import:",
                            [str(row.get("filename") or "") for row in candidate_rows] or plan.candidate_filenames,
                        )
                    if not selected_name:
                        self._safe_view_call("set_status", "GGUF import cancelled.")
                        return
                    self._start_local_gguf_import_task(
                        dict(meta.get("recommendation") or {}),
                        activate=bool(meta.get("activate", False)),
                        origin=str(meta.get("origin", "settings") or "settings"),
                        settings_snapshot=dict(meta.get("settings_snapshot") or self.model.settings),
                        selected_filename=selected_name,
                    )
                    return
                if state == "downloaded":
                    plan = self._import_plan_from_payload(dict(result.get("plan") or {}))
                    imported_path = pathlib.Path(str(result.get("downloaded_path") or "")).expanduser()
                    self._safe_view_call("set_status", "Registering")
                    if bool(meta.get("activate", False)):
                        self._safe_view_call("append_log", "[status] Activating")
                    self._commit_local_gguf_import(
                        plan,
                        imported_path,
                        activate=bool(meta.get("activate", False)),
                    )
                    label = str(
                        (meta.get("recommendation") or {}).get("model_name")
                        or plan.registry_metadata.get("catalog_name")
                        or imported_path.stem
                    )
                    if bool(meta.get("activate", False)):
                        self._safe_view_call("set_status", f"Applied {label} as the local LLM.")
                    else:
                        self._safe_view_call("set_status", f"Imported {label}.")
                    return

            elif task == _TASK_RAG_QUERY and isinstance(result, dict):
                response = result.get("response", "")
                prompt   = result.get("prompt", "")
                meta     = dict(getattr(self, "_pending_task_meta", {}))
                provider = str(meta.get("provider", self.model.settings.get("llm_provider", "mock")) or "mock")
                selected_mode = meta.get("selected_mode", "Q&A")
                n_chunks = meta.get("n_chunks", 0)
                top_score = meta.get("top_score", 0.0)
                sources = [
                    item if isinstance(item, EvidenceSource) else EvidenceSource.from_dict(item)
                    for item in (meta.get("sources") or [])
                ]
                run_id = str(meta.get("run_id") or "")
                context_block = str(result.get("context_block") or meta.get("context_block") or "").strip()

                if bool(meta.get("show_retrieved_context")) and context_block:
                    self._safe_view_call(
                        "append_chat",
                        f"Retrieved context:\n{context_block}\n\n",
                        "system",
                    )

                header = (
                    f"Axiom [{provider}, rag, mode={selected_mode}, "
                    f"{n_chunks} chunk(s)]:\n\n"
                )
                self._safe_view_call("append_chat", header + response + "\n\n")
                for note in result.get("validation_notes") or []:
                    self._safe_view_call("append_log", f"[grounding] {note}")
                self.model.chat_history.append({"role": "user", "content": prompt})
                self.model.chat_history.append({"role": "assistant", "content": response})
                self.model.last_sources = sources
                self.model.last_run_id = run_id
                self._safe_view_call("render_evidence_sources", sources)
                bundle = self._current_index_bundle()
                grounding_html_path = str(result.get("grounding_html_path", "") or "").strip()
                if grounding_html_path:
                    if bundle is not None:
                        bundle.grounding_html_path = grounding_html_path
                        self._persist_runtime_artifacts(bundle)
                    self._safe_view_call("render_grounding_info", grounding_html_path)
                self._persist_run(
                    prompt=prompt,
                    response=response,
                    run_id=run_id,
                    sources=sources,
                )
                self._render_bundle_metadata(
                    bundle,
                    {run_id: self.trace_store.read_run(run_id)},
                )
                self._set_chat_response_ui(True, True)
                self._log.info("RAG query answered — top score=%.3f", top_score)
                self._safe_view_call("set_status", "Done.")

            elif task == _TASK_DIRECT_QUERY and isinstance(result, dict):
                response = result.get("response", "")
                prompt   = result.get("prompt", "")
                meta = dict(getattr(self, "_pending_task_meta", {}))
                provider = str(meta.get("provider", self.model.settings.get("llm_provider", "mock")) or "mock")
                run_id = str(meta.get("run_id") or "")

                if result.get("error"):
                    self._safe_view_call("append_log", f"[direct] error: {result['error']}")
                else:
                    self._safe_view_call(
                        "append_log",
                        f"[direct] generation_completed provider={provider}"
                    )

                self._safe_view_call(
                    "append_chat",
                    f"Axiom [{provider}, direct]:\n\n{response}\n\n"
                )
                self.model.chat_history.append({"role": "user", "content": prompt})
                self.model.chat_history.append({"role": "assistant", "content": response})
                self.model.last_sources = []
                self.model.last_run_id = run_id
                self._safe_view_call("render_evidence_sources", [])
                self._persist_run(
                    prompt=prompt,
                    response=response,
                    run_id=run_id,
                    sources=[],
                )
                self._render_bundle_metadata(
                    self._current_index_bundle(),
                    {run_id: self.trace_store.read_run(run_id)},
                )
                self._set_chat_response_ui(True, True)
                self._log.info("Direct query answered — provider=%s", provider)
                self._safe_view_call("set_status", "Done.")

            elif task == _TASK_INSTALL_DEPENDENCIES and isinstance(result, dict):
                installed = ", ".join(str(item) for item in (result.get("packages") or []))
                message = f"Installed {installed}. Restart may be required."
                self._safe_view_call("append_log", f"[deps] {message}")
                self._safe_view_call("set_status", message)

            else:
                label = f"{task} complete." if task else "Done."
                self._safe_view_call("set_status", label)
                self._safe_view_call("append_log", f"[done]  {label}")

        elif mtype == "log":
            self._safe_view_call("append_log", msg.get("text", ""))

    # ------------------------------------------------------------------
    # Window close
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        self.shutdown()
        close_window = getattr(self.view, "close_window", None)
        if callable(close_window):
            close_window()
            return
        root = getattr(self.view, "root", None)
        if root is not None and hasattr(root, "destroy"):
            root.destroy()

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def on_open_files(self) -> None:
        """Open a file dialog and load selected files into the model."""
        if is_kreuzberg_available():
            # Build a rich filetype list from the extensions kreuzberg supports.
            filetypes: list[tuple[str, str]] = [
                ("All supported", " ".join(
                    ext for exts in KREUZBERG_EXTENSIONS.values() for ext in exts
                ) + " *.txt *.md"),
            ]
            for label, exts in KREUZBERG_EXTENSIONS.items():
                filetypes.append((label, " ".join(exts)))
            filetypes += [
                ("Text / Markdown", "*.txt *.md"),
                ("All files",       "*.*"),
            ]
            title = "Select document(s)"
        else:
            filetypes = [
                ("Text files", "*.txt"),
                ("Markdown",   "*.md"),
                ("All files",  "*.*"),
            ]
            title = "Select text file(s)"

        paths = self._pick_open_files(title=title, filetypes=filetypes)
        if not paths:
            return  # user cancelled

        self.model.set_documents(list(paths))
        # Show basenames in the listbox; full paths stay in the model.
        self._safe_view_call("set_file_list", [pathlib.Path(p).name for p in paths])
        self._safe_view_call("set_index_info", "Files loaded — click 'Build Index' to index.")
        self._safe_view_call(
            "set_status",
            f"{len(paths)} file(s) loaded. Click 'Build Index' to index."
        )
        self._safe_view_call(
            "append_log",
            f"[open]  {len(paths)} file(s): "
            + ", ".join(pathlib.Path(p).name for p in paths)
        )
        self._log.info("Loaded %d file(s)", len(paths))

    def on_build_index(self) -> None:
        """Chunk and embed all loaded documents in a background thread."""
        if not self.model.documents:
            self._safe_view_call("set_status", "No files loaded — use 'Open Files…' first.")
            return

        settings_snapshot = dict(self.model.settings)
        docs = list(self.model.documents)
        build_settings_getter = getattr(self.view, "get_library_build_settings", None)
        if callable(build_settings_getter):
            for key, value in dict(build_settings_getter() or {}).items():
                try:
                    settings_snapshot[key] = int(str(value).strip())
                    self.model.settings[key] = settings_snapshot[key]
                except (TypeError, ValueError):
                    continue
        if bool(settings_snapshot.get("deepread_mode")):
            settings_snapshot["structure_aware_ingestion"] = True
            settings_snapshot["build_comprehension_index"] = True
            settings_snapshot["prefer_comprehension_index"] = True

        constraints = self._current_state_constraints(settings_snapshot, scope="build")
        blockers = list(constraints.get("blockers") or [])
        advisories = list(constraints.get("advisories") or [])
        if blockers and not self._confirm_experimental_override("Index build", blockers):
            self._safe_view_call("set_status", blockers[0])
            return
        for advisory in advisories:
            self._safe_view_call("append_log", f"[build] advisory: {advisory}")

        adapter = resolve_vector_store(settings_snapshot)
        available, reason = adapter.is_available(settings_snapshot)
        if not available:
            self.model.rag_blocked_reason = reason
            self._safe_view_call("set_status", f"Vector backend unavailable: {reason}")
            return

        index_dir = getattr(self.model, "index_storage_dir", None)

        def _worker(post_msg: Any, cancel: CancelToken) -> IndexBundle:
            bundle = adapter.build(
                docs,
                settings_snapshot,
                post_message=post_msg,
                cancel_token=cancel,
            )
            out_path = adapter.save(bundle, index_dir=index_dir)
            post_msg({"type": "log", "text": f"[index] Saved persisted index to {out_path}"})
            return bundle

        self._set_build_index_enabled(False)
        self._safe_view_call("set_index_info", "Indexing…")
        self.start_task(_TASK_BUILD_INDEX, _worker)

    def _on_send_clicked(self) -> None:
        """Invoked by the Send button and <Return> in the prompt entry."""
        prompt = self.view.get_prompt_text().strip()
        if prompt:
            self.view.clear_prompt()
            self.on_send_prompt(prompt)

    def on_send_prompt(self, prompt: str = "") -> None:
        """Retrieve relevant chunks, then synthesise an answer via the LLM.

        Retrieval (cosine similarity + knowledge graph) runs synchronously on
        the main thread — it's pure Python over small vectors and is fast even
        for thousands of chunks.  The LLM call is dispatched to a background
        thread so the UI stays responsive for cloud providers.
        """
        if not prompt.strip():
            return

        self._clear_completed_response_state()

        get_chat_mode = getattr(self.view, "get_chat_mode", None)
        chat_mode = get_chat_mode() if callable(get_chat_mode) else "rag"

        if chat_mode == "direct":
            self._handle_direct_prompt(prompt)
            return

        if str(getattr(self.model, "rag_blocked_reason", "") or "").strip():
            self._safe_view_call(
                "append_chat",
                f"⚠  RAG is blocked until the vector backend is configured.\n"
                f"   {self.model.rag_blocked_reason}\n\n",
            )
            self._safe_view_call("switch_view", "chat")
            return

        bundle = self._current_index_bundle()
        if bundle is None or not self.model.index_state.get("built"):
            self._safe_view_call(
                "append_chat",
                "⚠  No index built yet.\n"
                "   Open a text file and click 'Build Index' first, or switch to Direct mode.\n\n"
            )
            self._safe_view_call("switch_view", "chat")
            return

        profile_label = self._current_profile_label()
        profile = self.profile_repository.get_profile(profile_label)
        resolved = resolve_runtime_settings(
            dict(self.model.settings),
            profile,
            profile_label=profile_label,
            query=prompt,
        )
        query_settings = dict(self.model.settings)
        query_settings.update(
            {
                "selected_mode": resolved.mode,
                "retrieval_k": resolved.retrieve_k,
                "top_k": resolved.final_k,
                "mmr_lambda": resolved.mmr_lambda,
                "retrieval_mode": resolved.retrieval_mode,
                "agentic_mode": resolved.agentic_mode,
                "agentic_max_iterations": resolved.agentic_max_iterations,
            }
        )
        constraints = self._current_state_constraints(query_settings, scope="query")
        blockers = list(constraints.get("blockers") or [])
        advisories = list(constraints.get("advisories") or [])
        if blockers and not self._confirm_experimental_override("RAG query", blockers):
            self._safe_view_call("append_chat", f"⚠  {' '.join(blockers)}\n\n")
            self._safe_view_call("set_status", blockers[0])
            self._safe_view_call("switch_view", "chat")
            return
        for advisory in advisories:
            self._safe_view_call("append_log", f"[query] advisory: {advisory}")
        adapter = resolve_vector_store(
            {**dict(self.model.settings), "vector_db_type": getattr(bundle, "vector_backend", self.model.settings.get("vector_db_type", "json"))}
        )
        available, reason = adapter.is_available(
            {
                **dict(self.model.settings),
                "vector_db_type": getattr(bundle, "vector_backend", self.model.settings.get("vector_db_type", "json")),
            }
        )
        if not available:
            self.model.rag_blocked_reason = reason
            self._safe_view_call(
                "append_chat",
                f"⚠  RAG is blocked until the vector backend is configured.\n"
                f"   {reason}\n\n",
            )
            self._safe_view_call("switch_view", "chat")
            return
        query_result = adapter.query(bundle, prompt, query_settings)
        self.model.last_sources = list(query_result.sources)
        self._safe_view_call("render_evidence_sources", list(query_result.sources))

        # Show the user's prompt immediately.
        sep = "─" * 52
        self._safe_view_call("append_chat", f"You: {prompt}\n{sep}\n", "user")
        self._safe_view_call("switch_view", "chat")

        # ── LLM synthesis (background thread) ────────────────────────────
        settings_snap = dict(self.model.settings)
        settings_snap.update(
            {
                "selected_mode": resolved.mode,
                "llm_provider": resolved.llm_provider or settings_snap.get("llm_provider", "mock"),
                "llm_model": resolved.llm_model or settings_snap.get("llm_model", ""),
                "embedding_provider": resolved.embedding_provider or settings_snap.get("embedding_provider", ""),
                "embedding_model": resolved.embedding_model or settings_snap.get("embedding_model", ""),
                "retrieval_k": resolved.retrieve_k,
                "top_k": resolved.final_k,
                "mmr_lambda": resolved.mmr_lambda,
                "retrieval_mode": resolved.retrieval_mode,
                "agentic_mode": resolved.agentic_mode,
                "agentic_max_iterations": resolved.agentic_max_iterations,
            }
        )
        selected_mode = resolved.mode
        provider = str(settings_snap.get("llm_provider", "mock") or "mock")
        run_id = str(uuid.uuid4())
        self.trace_store.append_event(
            run_id=run_id,
            stage="retrieval",
            event_type="retrieval_results",
            retrieval_results={
                "top_score": query_result.top_score,
                "source_count": len(query_result.sources),
                "sources": [item.to_dict() for item in query_result.sources],
            },
            citations_chosen=[item.sid for item in query_result.sources],
            payload={"profile": profile_label, "mode": selected_mode},
        )

        def _rag_worker(post_msg: Any, cancel: CancelToken) -> dict[str, Any]:
            post_msg({"type": "status", "text": "Generating answer…"})
            try:
                llm = create_llm(settings_snap)
            except (ValueError, ImportError) as exc:
                self.trace_store.append_event(
                    run_id=run_id,
                    stage="synthesis",
                    event_type="llm_unavailable",
                    payload={"error": str(exc)},
                )
                return {
                    "response": (
                        f"Axiom [rag, mode={selected_mode}]: "
                        f"LLM unavailable ({exc}). Showing raw retrieval.\n\n"
                        f"CONTEXT:\n{query_result.context_block}\n"
                    ),
                    "prompt": prompt,
                    "context_block": query_result.context_block,
                }
            grounding_html_path = ""
            validation_notes: list[str] = []
            if is_blinkist_summary_mode(selected_mode, str(settings_snap.get("output_style", "") or "")):
                self.trace_store.append_event(
                    run_id=run_id,
                    stage="pipeline",
                    event_type="blinkist_summary",
                    payload={"provider": provider, "profile": profile_label},
                )
                pipeline_result = run_blinkist_summary_pipeline(
                    llm,
                    query_text=prompt,
                    context_block=query_result.context_block,
                    sources=list(query_result.sources),
                )
                answer = pipeline_result.response_text
            elif is_tutor_mode(selected_mode):
                self.trace_store.append_event(
                    run_id=run_id,
                    stage="pipeline",
                    event_type="tutor_mode",
                    payload={"provider": provider, "profile": profile_label},
                )
                pipeline_result = run_tutor_pipeline(
                    llm,
                    query_text=prompt,
                    context_block=query_result.context_block,
                    sources=list(query_result.sources),
                )
                answer = pipeline_result.response_text
            else:
                system_prompt = (
                    f"{resolved.system_prompt}\n\n"
                    "Answer the user's question using ONLY the CONTEXT below. "
                    "Cite passages as [S1], [S2], etc. If the context is insufficient, say so.\n\n"
                    f"CONTEXT:\n{query_result.context_block}"
                )
                messages = [
                    {"type": "system", "content": system_prompt},
                    {"type": "human", "content": prompt},
                ]
                self.trace_store.append_event(
                    run_id=run_id,
                    stage="synthesis",
                    event_type="llm_request",
                    prompt={"system": system_prompt[:4000], "user": prompt},
                    payload={"provider": provider, "profile": profile_label},
                )
                result = llm.invoke(messages)
                answer = str(getattr(result, "content", result) or "")
                self.trace_store.append_event(
                    run_id=run_id,
                    stage="synthesis",
                    event_type="llm_response",
                    citations_chosen=[item.sid for item in query_result.sources],
                    payload={"response_preview": answer[:400], "provider": provider},
                )

            if bool(settings_snap.get("enable_claim_level_grounding_citefix_lite")):
                answer, validation_notes = apply_claim_level_grounding(answer, list(query_result.sources))
                self.trace_store.append_event(
                    run_id=run_id,
                    stage="validation",
                    event_type="claim_grounding",
                    citations_chosen=[item.sid for item in query_result.sources],
                    validator={"notes": list(validation_notes)},
                    payload={"note_count": len(validation_notes)},
                )

            if bool(settings_snap.get("enable_langextract")):
                grounding_html_path = build_grounding_html(
                    self._grounding_output_dir(),
                    title=f"Axiom grounding · {selected_mode}",
                    query_text=prompt,
                    answer_text=answer,
                    sources=list(query_result.sources),
                )
                self.trace_store.append_event(
                    run_id=run_id,
                    stage="grounding",
                    event_type="langextract_html",
                    payload={"artifact_path": grounding_html_path},
                )

            return {
                "response": answer,
                "prompt": prompt,
                "grounding_html_path": grounding_html_path,
                "validation_notes": validation_notes,
                "context_block": query_result.context_block,
            }

        # Store retrieval metadata for _handle_message to use.
        self._pending_task_meta = {
            "selected_mode": selected_mode,
            "n_chunks": len(bundle.embeddings),
            "top_score": query_result.top_score,
            "prompt": prompt,
            "provider": provider,
            "run_id": run_id,
            "sources": list(query_result.sources),
            "profile_label": profile_label,
            "show_retrieved_context": bool(settings_snap.get("show_retrieved_context", False)),
            "context_block": query_result.context_block,
            "trace_payload": self.trace_store.read_run(run_id),
        }
        self.start_task(_TASK_RAG_QUERY, _rag_worker)

    def _handle_direct_prompt(self, prompt: str) -> None:
        """Handle direct-chat prompts (no retrieval) via the provider factory.

        All providers — OpenAI, Anthropic, Google, xAI, LM Studio, local GGUF,
        and mock — are routed through ``create_llm(settings)``.  The LLM call
        runs in a background thread so the UI stays responsive.
        """
        provider_name = str(self.model.settings.get("llm_provider", "mock") or "mock").strip() or "mock"
        self._safe_view_call("append_log", f"[direct] provider_selected provider={provider_name}")

        sep = "─" * 52
        self._safe_view_call("append_chat", f"You: {prompt}\n{sep}\n", "user")
        self._safe_view_call("switch_view", "chat")
        self._safe_view_call("render_evidence_sources", [])

        profile_label = self._current_profile_label()
        profile = self.profile_repository.get_profile(profile_label)
        resolved = resolve_runtime_settings(
            dict(self.model.settings),
            profile,
            profile_label=profile_label,
            query=prompt,
        )
        settings_snap = dict(self.model.settings)
        settings_snap.update(
            {
                "selected_mode": resolved.mode,
                "llm_provider": resolved.llm_provider or settings_snap.get("llm_provider", "mock"),
                "llm_model": resolved.llm_model or settings_snap.get("llm_model", ""),
            }
        )
        run_id = str(uuid.uuid4())
        self.trace_store.append_event(
            run_id=run_id,
            stage="direct",
            event_type="direct_prompt",
            prompt={"user": prompt},
            payload={"provider": provider_name, "profile": profile_label},
        )

        def _direct_worker(post_msg: Any, cancel: CancelToken) -> dict[str, str]:
            post_msg({"type": "status", "text": f"Generating ({provider_name})…"})
            try:
                llm = create_llm(settings_snap)
            except (ValueError, ImportError, RuntimeError) as exc:
                self.trace_store.append_event(
                    run_id=run_id,
                    stage="direct",
                    event_type="llm_unavailable",
                    payload={"error": str(exc)},
                )
                return {
                    "response": f"Axiom [{provider_name}, direct]: {exc}\n\n",
                    "prompt": prompt,
                    "error": str(exc),
                }

            messages = [
                {"type": "system", "content": resolved.system_prompt},
                {"type": "human", "content": prompt},
            ]
            self.trace_store.append_event(
                run_id=run_id,
                stage="direct",
                event_type="llm_request",
                prompt={"system": resolved.system_prompt[:4000], "user": prompt},
                payload={"provider": provider_name, "profile": profile_label},
            )
            try:
                result = llm.invoke(messages)
                answer = str(getattr(result, "content", result) or "")
            except Exception as exc:
                self.trace_store.append_event(
                    run_id=run_id,
                    stage="direct",
                    event_type="llm_error",
                    payload={"error": str(exc)},
                )
                return {
                    "response": f"Axiom [{provider_name}, direct]: LLM error: {exc}\n\n",
                    "prompt": prompt,
                    "error": str(exc),
                }
            self.trace_store.append_event(
                run_id=run_id,
                stage="direct",
                event_type="llm_response",
                payload={"response_preview": answer[:400], "provider": provider_name},
            )

            return {"response": answer, "prompt": prompt}

        self._pending_task_meta = {
            "prompt": prompt,
            "provider": provider_name,
            "run_id": run_id,
            "sources": [],
            "profile_label": profile_label,
        }
        self.start_task(_TASK_DIRECT_QUERY, _direct_worker)

    def on_cancel_job(self) -> None:
        """Cancel any running background job."""
        self.cancel_current_task()

    def on_new_chat(self) -> None:
        """Start a persisted chat session and clear transient UI state."""
        session = self.session_repository.create_session(
            title="New Chat",
            active_profile=self._current_profile_label(),
            mode=str(self.model.settings.get("selected_mode", "Q&A") or "Q&A"),
            index_id=str(getattr(self.model, "active_index_id", "") or ""),
            vector_backend=self._current_vector_backend(),
            llm_provider=str(self.model.settings.get("llm_provider", "") or ""),
            llm_model=self._effective_llm_model(),
            embed_model=self._effective_embedding_model(),
            retrieve_k=int(self.model.settings.get("retrieval_k", 0) or 0),
            final_k=int(self.model.settings.get("top_k", 0) or 0),
            mmr_lambda=float(self.model.settings.get("mmr_lambda", 0.0) or 0.0),
            agentic_iterations=int(self.model.settings.get("agentic_max_iterations", 0) or 0),
            extra_json=self._session_extra_json(),
        )
        self.model.current_session_id = session.session_id
        self.model.selected_brain_node = f"session:{session.session_id}"
        self.model.loaded_session = None
        self.model.chat_history = []
        self._clear_completed_response_state()
        self._safe_view_call("set_chat_transcript", [])
        self._safe_view_call("render_evidence_sources", [])
        self._safe_view_call("set_status", "New chat started.")
        self._safe_view_call("switch_view", "chat")
        self.refresh_history_rows(select_session_id=session.session_id, update_detail=True)

    def refresh_history_rows(
        self,
        select_session_id: str | None = None,
        update_detail: bool = True,
    ) -> None:
        getter = getattr(self.view, "get_history_search_query", None)
        search = getter() if callable(getter) else ""
        profile_getter = getattr(self.view, "get_history_profile_filter", None)
        profile = profile_getter() if callable(profile_getter) else ""
        rows = self.session_repository.list_sessions(search=search, profile=profile)
        self.model.session_list = rows
        self._safe_view_call("set_history_rows", rows)
        selected_node_id = f"session:{select_session_id}" if select_session_id else getattr(self.model, "selected_brain_node", "")
        self._rebuild_brain_graph(selected_node_id=selected_node_id)
        if select_session_id:
            self._safe_view_call("select_history_session", select_session_id)
        if update_detail:
            self.on_history_selection_changed()

    def on_history_search_changed(self, _event: Any | None = None) -> None:
        self.refresh_history_rows(update_detail=True)

    def on_history_profile_changed(self, _event: Any | None = None) -> None:
        self.refresh_history_rows(update_detail=True)

    def on_history_selection_changed(self, _event: Any | None = None) -> None:
        session_id = self._selected_history_session_id()
        if not session_id:
            return
        detail = self.session_repository.get_session(session_id)
        if detail is None:
            return
        detail.traces = self._session_trace_payload(detail)
        self.model.loaded_session = detail
        self.model.selected_brain_node = f"session:{session_id}"
        self._safe_view_call("set_history_detail", detail)

    def on_brain_node_selected(self, node_id: str) -> None:
        selected = str(node_id or "").strip()
        self.model.selected_brain_node = selected
        graph = getattr(self.model, "brain_graph", None)
        if not isinstance(graph, BrainGraph):
            return
        node = graph.get_node(selected)
        if node is None:
            return
        if node.node_type == "session":
            session_id = str(node.metadata.get("session_id", "") or "")
            if session_id:
                detail = self.session_repository.get_session(session_id)
                if detail is None:
                    return
                detail.traces = self._session_trace_payload(detail)
                self.model.loaded_session = detail
                self._safe_view_call("set_history_detail", detail)

    def on_brain_node_activated(self, node_id: str) -> None:
        selected = str(node_id or "").strip()
        graph = getattr(self.model, "brain_graph", None)
        if not isinstance(graph, BrainGraph):
            return
        node = graph.get_node(selected)
        if node is None:
            return
        self.model.selected_brain_node = selected
        if node.node_type == "index":
            self.on_load_selected_index()
        elif node.node_type == "session":
            self.on_open_session()

    def on_brain_refresh_requested(self) -> None:
        self._rebuild_brain_graph(selected_node_id=getattr(self.model, "selected_brain_node", ""))

    def on_open_session(self) -> None:
        session_id = self._selected_history_session_id()
        if not session_id:
            return
        detail = self.session_repository.get_session(session_id)
        if detail is None:
            return
        detail.traces = self._session_trace_payload(detail)

        self.model.current_session_id = session_id
        self.model.selected_brain_node = f"session:{session_id}"
        self.model.loaded_session = detail
        self.model.chat_history = [
            {"role": msg.role, "content": msg.content}
            for msg in detail.messages
        ]
        self._restore_session_settings(detail)
        self._restore_index_from_session(detail)
        self._safe_view_call("set_chat_transcript", detail.messages)
        last_run_id, last_sources, feedback_pending = self._latest_completed_assistant_run(detail)
        self.model.last_run_id = last_run_id
        self.model.last_sources = last_sources
        self._safe_view_call("render_evidence_sources", last_sources)
        self._render_bundle_metadata(getattr(self.model, "index_bundle", None), detail.traces)
        self._set_chat_response_ui(bool(last_run_id), feedback_pending)
        self._safe_view_call("set_history_detail", detail)
        self._safe_view_call("set_status", f"Loaded session: {detail.summary.title}")
        self._safe_view_call("switch_view", "chat")
        self.refresh_history_rows(select_session_id=session_id, update_detail=False)

    def on_delete_session(self) -> None:
        session_id = self._selected_history_session_id()
        if not session_id:
            return
        self.session_repository.delete_session(session_id)
        if getattr(self.model, "current_session_id", "") == session_id:
            self.model.current_session_id = ""
            self.model.loaded_session = None
            self.model.chat_history = []
            self._clear_completed_response_state()
            self._safe_view_call("set_chat_transcript", [])
            self._safe_view_call("render_evidence_sources", [])
        self.refresh_history_rows(update_detail=False)
        self._safe_view_call("set_status", "Session deleted.")

    def on_rename_session(self) -> None:
        session_id = self._selected_history_session_id()
        if not session_id:
            return
        title = self._get_text_input("Rename Session", "New session title:")
        if not title:
            return
        summary = self.session_repository.rename_session(session_id, title)
        self.refresh_history_rows(select_session_id=summary.session_id, update_detail=True)
        self._safe_view_call("set_status", f"Renamed session: {summary.title}")

    def on_duplicate_session(self) -> None:
        session_id = self._selected_history_session_id()
        if not session_id:
            return
        summary = self.session_repository.duplicate_session(session_id)
        self.refresh_history_rows(select_session_id=summary.session_id, update_detail=True)
        self._safe_view_call("set_status", f"Duplicated session: {summary.title}")

    def on_export_session(self) -> None:
        session_id = self._selected_history_session_id()
        if not session_id:
            return

        save_dir = self._pick_directory(title="Select export directory")
        if not save_dir:
            return
        try:
            md_path, json_path = self.session_repository.export_session(session_id, save_dir)
        except OSError as exc:
            self._show_error_dialog("Export Failed", f"Could not export session: {exc}")
            return

        self._safe_view_call(
            "append_log",
            f"[history] Exported session to {md_path} and {json_path}",
        )
        self._safe_view_call(
            "set_status",
            f"Exported session: {pathlib.Path(md_path).name}",
        )
        self._show_info_dialog("Session Export", f"Exported:\n{md_path}\n{json_path}")

    def on_load_profile(self) -> None:
        label = self._current_profile_label()
        profile = self.profile_repository.get_profile(label)
        self._apply_profile_to_settings(profile, label=label)
        self.model.save_settings(self.model.settings)
        self._safe_view_call("populate_settings", self.model.settings)
        self._sync_profile_options()
        self._safe_view_call("set_status", f"Loaded profile: {profile.name}")

    def on_save_profile(self) -> None:
        current_label = self._current_profile_label()
        current_path = self.profile_repository.path_from_label(current_label)
        if current_path is not None:
            target_name = current_path.stem
            target_path = current_path
        else:
            target_name = self._get_text_input("Save Profile", "Profile name:")
            target_path = None
        if not target_name:
            return
        profile = self._profile_from_settings(str(target_name))
        try:
            saved_path = self.profile_repository.save_profile(profile, target_path=target_path)
        except OSError as exc:
            self._show_error_dialog("Save Profile Failed", str(exc))
            return
        label = self.profile_repository.label_for_path(saved_path)
        self.model.current_profile_label = label
        self.model.settings["selected_profile"] = label
        self.model.save_settings(self.model.settings)
        self._sync_profile_options()
        self._safe_view_call("select_profile_label", label)
        self._safe_view_call("set_status", f"Saved profile: {profile.name}")

    def on_duplicate_profile(self) -> None:
        current_label = self._current_profile_label()
        source = self.profile_repository.get_profile(current_label)
        new_name = self._get_text_input(
            "Duplicate Profile",
            "Name for the duplicate profile:",
            text=f"{source.name} Copy",
        )
        if not new_name:
            return
        try:
            saved_path = self.profile_repository.duplicate_profile(
                current_label,
                new_name=new_name,
            )
        except OSError as exc:
            self._show_error_dialog("Duplicate Profile Failed", str(exc))
            return
        label = self.profile_repository.label_for_path(saved_path)
        self.model.current_profile_label = label
        self.model.settings["selected_profile"] = label
        self.model.save_settings(self.model.settings)
        self._sync_profile_options()
        self._safe_view_call("select_profile_label", label)
        self._safe_view_call("set_status", f"Duplicated profile: {new_name}")

    def on_submit_feedback(self, vote: int) -> None:
        session_id = str(getattr(self.model, "current_session_id", "") or "")
        run_id = str(getattr(self.model, "last_run_id", "") or "")
        if not session_id or not run_id:
            self._safe_view_call("set_status", "No completed run is available for feedback.")
            return
        note = self._get_text_input(
            "Feedback note",
            "Optional note for this rating:",
            text="",
        )
        self.session_repository.save_feedback(
            session_id,
            run_id=run_id,
            vote=int(vote),
            note=str(note or ""),
        )
        detail = self.session_repository.get_session(session_id)
        if detail is not None:
            detail.traces = self._session_trace_payload(detail)
            self.model.loaded_session = detail
            self._safe_view_call("set_history_detail", detail)
            latest_run_id, latest_sources, feedback_pending = self._latest_completed_assistant_run(detail)
            self.model.last_run_id = latest_run_id
            self.model.last_sources = latest_sources
            self._set_chat_response_ui(bool(latest_run_id), feedback_pending)
        self._safe_view_call("set_status", "Feedback saved.")

    def on_load_selected_index(self) -> None:
        getter = getattr(self.view, "get_selected_available_index_path", None)
        path = getter() if callable(getter) else ""
        if not path:
            self._safe_view_call("set_status", "Select a saved index first.")
            return
        bundle = self._load_bundle_from_path(path, persist=True)
        if bundle is not None:
            self._safe_view_call("set_status", f"Loaded index: {bundle.index_id}")

    def _selected_local_gguf_recommendation(self) -> dict[str, Any] | None:
        getter = getattr(self.view, "get_selected_local_gguf_recommendation", None)
        payload = getter() if callable(getter) else None
        return dict(payload or {}) if isinstance(payload, dict) else None

    @staticmethod
    def _import_plan_from_payload(payload: dict[str, Any]) -> ImportPlan:
        return ImportPlan(
            source_repo=str(payload.get("source_repo") or ""),
            source_provider=str(payload.get("source_provider") or ""),
            filename=str(payload.get("filename") or ""),
            destination_path=str(payload.get("destination_path") or ""),
            registry_metadata=dict(payload.get("registry_metadata") or {}),
            expected_size_bytes=(
                int(payload["expected_size_bytes"])
                if payload.get("expected_size_bytes") not in (None, "")
                else None
            ),
            activation_safe=bool(payload.get("activation_safe", False)),
            manual_reason=str(payload.get("manual_reason") or ""),
            manual_selection_required=bool(payload.get("manual_selection_required", False)),
            candidate_filenames=[str(item) for item in (payload.get("candidate_filenames") or [])],
        )

    def _has_valid_local_gguf_path(self, settings: dict[str, Any] | None = None) -> bool:
        raw_path = str((settings or self.model.settings).get("local_gguf_model_path", "") or "").strip()
        if not raw_path:
            return False
        try:
            return pathlib.Path(raw_path).expanduser().is_file()
        except OSError:
            return False

    def _resolve_local_gguf_activation_request(
        self,
        recommendation: dict[str, Any],
        *,
        requested: bool,
        allow_import_only_fallback: bool,
    ) -> bool | None:
        if not requested:
            return False
        fit_level = str(recommendation.get("fit_level") or "").strip().lower()
        model_name = str(recommendation.get("model_name") or "This recommendation").strip()
        if fit_level in {"perfect", "good"}:
            return True
        if fit_level == "marginal":
            confirmed = self._ask_yes_no(
                "Marginal GGUF Fit",
                f"{model_name} is a marginal fit for the detected hardware. Activate it after import?",
            )
            if confirmed:
                return True
            if allow_import_only_fallback:
                self._safe_view_call("set_status", f"{model_name} will be imported without activation.")
                return False
            self._safe_view_call(
                "set_status",
                "Activation cancelled. Use Import Selected if you only want to download the GGUF.",
            )
            return None
        if fit_level == "too_tight":
            message = (
                f"{model_name} is too tight for the detected hardware. "
                "Import is allowed, but activation is blocked."
            )
            if allow_import_only_fallback:
                self._safe_view_call("set_status", message)
                return False
            self._show_info_dialog("Activation Blocked", message)
            self._safe_view_call("set_status", message)
            return None
        return True

    def _start_local_gguf_import_task(
        self,
        recommendation: dict[str, Any],
        *,
        activate: bool,
        origin: str,
        settings_snapshot: dict[str, Any] | None = None,
        selected_filename: str = "",
    ) -> None:
        snapshot = dict(settings_snapshot or self.model.settings)
        self._pending_task_meta = {
            "recommendation": dict(recommendation),
            "activate": bool(activate),
            "origin": str(origin or "settings"),
            "settings_snapshot": snapshot,
        }
        self.start_task(
            _TASK_IMPORT_LOCAL_GGUF,
            self._local_gguf_import_worker,
            dict(recommendation),
            snapshot,
            str(selected_filename or ""),
        )

    def _local_gguf_import_worker(
        self,
        post_message: Callable[[dict[str, Any]], None],
        cancel_token: CancelToken,
        recommendation: dict[str, Any],
        settings_snapshot: dict[str, Any],
        selected_filename: str,
    ) -> dict[str, Any]:
        model_name = str(recommendation.get("model_name") or "").strip()
        best_quant = str(recommendation.get("best_quant") or "").strip()
        fit_level = str(recommendation.get("fit_level") or "").strip()
        context_length = int(recommendation.get("recommended_context_length") or 2048)
        if not model_name or not best_quant:
            raise ValueError("Select a recommended GGUF model first.")

        post_message({"type": "status", "text": "Resolving source"})
        plan = self.local_llm_recommender_service.plan_import(
            model_name=model_name,
            best_quant=best_quant,
            fit_level=fit_level,
            recommended_context_length=context_length,
            settings=settings_snapshot,
            selected_filename=selected_filename,
        )
        if plan.manual_selection_required and not selected_filename:
            post_message({"type": "status", "text": "Selecting file"})
            repo_files = self.local_llm_recommender_service.list_repo_files(plan.source_repo)
            candidate_set = set(plan.candidate_filenames)
            candidate_rows = self.local_llm_recommender_service.describe_repo_files(
                [item for item in repo_files if item.filename in candidate_set]
            )
            return {
                "state": "needs_selection",
                "plan": plan.to_payload(),
                "candidate_files": candidate_rows,
            }

        post_message({"type": "status", "text": "Downloading"})

        def _progress(current: int, total: int | None) -> None:
            post_message({"type": "progress", "current": int(current), "total": total})

        imported_path = self.local_llm_recommender_service.download_import(
            plan,
            progress_callback=_progress,
            cancel_token=cancel_token,
        )
        return {
            "state": "downloaded",
            "plan": plan.to_payload(),
            "downloaded_path": str(imported_path),
        }

    def _commit_local_gguf_import(
        self,
        plan: ImportPlan,
        imported_path: pathlib.Path,
        *,
        activate: bool,
    ) -> dict[str, Any]:
        working_settings = dict(self.model.settings)
        metadata = dict(plan.registry_metadata or {})
        metadata["source_filename"] = plan.filename
        metadata["download_path"] = str(imported_path)
        registry = self.local_model_registry_service.add_gguf(
            working_settings.get("local_model_registry", {}),
            name=imported_path.stem,
            path=str(imported_path),
            metadata=metadata,
        )
        working_settings["local_model_registry"] = registry
        working_settings["local_gguf_models_dir"] = str(imported_path.parent)
        if activate:
            entry = next(
                (
                    item
                    for item in self.local_model_registry_service.list_entries(registry)
                    if item.model_type == "gguf" and (item.path or item.value) == str(imported_path)
                ),
                None,
            )
            if entry is not None:
                working_settings = self.local_model_registry_service.activate_entry(
                    working_settings,
                    entry,
                    target="llm",
                )
        self.model.settings = working_settings
        self.model.save_settings(self.model.settings)
        self._safe_view_call("populate_settings", self.model.settings)
        self._sync_local_model_rows()
        self._sync_local_gguf_recommendations()
        return working_settings

    def _register_manual_local_gguf_path(self, path: str, *, activate: bool) -> bool:
        candidate = pathlib.Path(path).expanduser()
        if not candidate.is_file():
            self._show_error_dialog("Invalid GGUF File", "Choose an existing .gguf file.")
            return False
        registry = self.local_model_registry_service.add_gguf(
            self.model.settings.get("local_model_registry", {}),
            name=candidate.stem,
            path=str(candidate),
            metadata={},
        )
        working_settings = dict(self.model.settings)
        working_settings["local_model_registry"] = registry
        working_settings["local_gguf_models_dir"] = str(candidate.parent)
        if activate:
            entry = next(
                (
                    item
                    for item in self.local_model_registry_service.list_entries(registry)
                    if item.model_type == "gguf" and (item.path or item.value) == str(candidate)
                ),
                None,
            )
            if entry is not None:
                working_settings = self.local_model_registry_service.activate_entry(
                    working_settings,
                    entry,
                    target="llm",
                )
        self.model.settings = working_settings
        self.model.save_settings(self.model.settings)
        self._safe_view_call("populate_settings", self.model.settings)
        self._sync_local_model_rows()
        self._sync_local_gguf_recommendations()
        return True

    def _offer_manual_local_gguf_fallback(self, meta: dict[str, Any], *, reason: str) -> None:
        recommendation = dict(meta.get("recommendation") or {})
        model_name = str(recommendation.get("model_name") or "the selected GGUF")
        prompt = (
            f"{reason}\n\nChoose an existing local .gguf file instead of {model_name}?"
            if reason
            else f"Choose an existing local .gguf file instead of {model_name}?"
        )
        if not self._ask_yes_no("Use Existing GGUF", prompt):
            return
        path = self._pick_open_file(
            title="Select GGUF model file",
            filetypes=[("GGUF files", "*.gguf"), ("All files", "*.*")],
        )
        if not path:
            return
        if self._register_manual_local_gguf_path(path, activate=bool(meta.get("activate", False))):
            verb = "Applied" if bool(meta.get("activate", False)) else "Imported"
            self._safe_view_call("set_status", f"{verb} local GGUF from {pathlib.Path(path).name}.")

    def _start_queued_local_gguf_import_if_any(self) -> None:
        queued = dict(self._queued_local_gguf_import or {})
        if not queued:
            return
        self._queued_local_gguf_import = None
        self._start_local_gguf_import_task(
            dict(queued.get("recommendation") or {}),
            activate=bool(queued.get("activate", False)),
            origin=str(queued.get("origin", "wizard") or "wizard"),
            settings_snapshot=dict(queued.get("settings_snapshot") or self.model.settings),
        )

    def on_refresh_local_gguf_recommendations(self, use_case: str = "") -> None:
        requested = str(use_case or "").strip() or None
        self.local_llm_recommender_service.invalidate_hardware_cache()
        self.local_llm_recommender_service.invalidate_repo_cache()
        self._sync_local_gguf_recommendations(use_case=requested)
        self._safe_view_call("set_status", "Local GGUF recommendations refreshed.")

    def on_import_local_gguf_recommendation(self) -> None:
        recommendation = self._selected_local_gguf_recommendation()
        if not recommendation:
            self._safe_view_call("set_status", "Select a recommended GGUF model first.")
            return
        self._start_local_gguf_import_task(recommendation, activate=False, origin="settings")

    def on_apply_local_gguf_recommendation(self) -> None:
        recommendation = self._selected_local_gguf_recommendation()
        if not recommendation:
            self._safe_view_call("set_status", "Select a recommended GGUF model first.")
            return
        activation_request = self._resolve_local_gguf_activation_request(
            recommendation,
            requested=True,
            allow_import_only_fallback=False,
        )
        if activation_request is None:
            return
        self._start_local_gguf_import_task(
            recommendation,
            activate=bool(activation_request),
            origin="settings",
        )

    def on_edit_hardware_assumptions(self) -> None:
        self.local_llm_recommender_service.invalidate_hardware_cache()
        base_settings = dict(self.model.settings)
        base_settings["hardware_override_enabled"] = False
        detected = self.local_llm_recommender_service.detect_hardware(base_settings).to_payload()
        editor = getattr(self.view, "show_hardware_override_editor", None)
        result = editor(self.model.settings, detected) if callable(editor) else None
        if not isinstance(result, dict):
            self._safe_view_call("set_status", "Hardware assumptions unchanged.")
            return
        self._apply_detected_hardware_overrides(result)
        self._sync_local_gguf_recommendations()
        self._safe_view_call("set_status", "Hardware assumptions updated.")

    def on_add_local_gguf_model(self) -> None:
        path = self._pick_open_file(
            title="Select GGUF model file",
            filetypes=[("GGUF files", "*.gguf"), ("All files", "*.*")],
        )
        if not path:
            return
        updated = self.local_model_registry_service.add_gguf(
            self.model.settings.get("local_model_registry", {}),
            name=pathlib.Path(path).stem,
            path=path,
        )
        self.model.settings["local_model_registry"] = updated
        self.model.settings["local_gguf_models_dir"] = str(pathlib.Path(path).parent)
        self.model.save_settings(self.model.settings)
        self._sync_local_model_rows()
        self._sync_local_gguf_recommendations()
        self._safe_view_call("set_status", f"Added GGUF model: {pathlib.Path(path).name}")

    def on_add_local_st_model(self) -> None:
        name = self._get_text_input(
            "Add Sentence Transformer",
            "Model name or HF id:",
        )
        if not name:
            return
        updated = self.local_model_registry_service.add_sentence_transformer(
            self.model.settings.get("local_model_registry", {}),
            name=name,
        )
        self.model.settings["local_model_registry"] = updated
        self.model.save_settings(self.model.settings)
        self._sync_local_model_rows()
        self._sync_local_gguf_recommendations()
        self._safe_view_call("set_status", f"Added embedding model: {name}")

    def on_remove_local_model(self) -> None:
        entry_id = self._selected_local_model_entry_id()
        if not entry_id:
            self._safe_view_call("set_status", "Select a local model first.")
            return
        updated = self.local_model_registry_service.remove_entry(
            self.model.settings.get("local_model_registry", {}),
            entry_id,
        )
        self.model.settings["local_model_registry"] = updated
        self.model.save_settings(self.model.settings)
        self._sync_local_model_rows()
        self._sync_local_gguf_recommendations()
        self._safe_view_call("set_status", "Local model removed.")

    def on_activate_local_model(self, target: str) -> None:
        entry_id = self._selected_local_model_entry_id()
        entry = self.local_model_registry_service.get_entry(
            self.model.settings.get("local_model_registry", {}),
            entry_id,
        )
        if entry is None:
            self._safe_view_call("set_status", "Select a local model first.")
            return
        try:
            self.model.settings = self.local_model_registry_service.activate_entry(
                self.model.settings,
                entry,
                target=target,
            )
        except ValueError as exc:
            self._show_error_dialog("Activation Failed", str(exc))
            return
        self.model.save_settings(self.model.settings)
        self._safe_view_call("populate_settings", self.model.settings)
        self._sync_local_model_rows()
        self._sync_local_gguf_recommendations()
        self._safe_view_call("set_status", f"Activated local model for {target}.")

    def on_open_local_model_folder(self) -> None:
        entry_id = self._selected_local_model_entry_id()
        entry = self.local_model_registry_service.get_entry(
            self.model.settings.get("local_model_registry", {}),
            entry_id,
        )
        if entry is None:
            self._safe_view_call("set_status", "Select a local model first.")
            return
        folder = self.local_model_registry_service.open_path_for_entry(self.model.settings, entry)
        try:
            if os.name == "nt":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:
            self._safe_view_call("append_log", f"[local-models] open failed: {exc}")
            self._safe_view_call("set_status", f"Could not open: {folder}")
            return
        self._safe_view_call("set_status", f"Opened: {folder}")

    def on_install_local_dependency(self, packages: list[str]) -> None:
        normalized = [str(item).strip() for item in packages if str(item).strip()]
        if not normalized:
            return

        def _worker(post_msg: Any, cancel: CancelToken) -> dict[str, Any]:
            _ = cancel
            install_packages(
                normalized,
                logger=self._log,
                progress_callback=lambda line: post_msg({"type": "log", "text": f"[deps] {line}"}),
            )
            post_msg({"type": "status", "text": "Dependency install complete. Restart may be required."})
            return {"packages": normalized}

        self.start_task(_TASK_INSTALL_DEPENDENCIES, _worker)

    def _ensure_session(self, prompt: str = "") -> str:
        current = str(getattr(self.model, "current_session_id", "") or "")
        if current and self.session_repository.get_session(current) is not None:
            return current

        title = self._title_from_prompt(prompt) if prompt else "New Chat"
        session = self.session_repository.create_session(
            title=title,
            active_profile=self._current_profile_label(),
            mode=str(self.model.settings.get("selected_mode", "Q&A") or "Q&A"),
            index_id=str(getattr(self.model, "active_index_id", "") or ""),
            vector_backend=self._current_vector_backend(),
            llm_provider=str(self.model.settings.get("llm_provider", "") or ""),
            llm_model=self._effective_llm_model(),
            embed_model=self._effective_embedding_model(),
            retrieve_k=int(self.model.settings.get("retrieval_k", 0) or 0),
            final_k=int(self.model.settings.get("top_k", 0) or 0),
            mmr_lambda=float(self.model.settings.get("mmr_lambda", 0.0) or 0.0),
            agentic_iterations=int(self.model.settings.get("agentic_max_iterations", 0) or 0),
            extra_json=self._session_extra_json(),
        )
        self.model.current_session_id = session.session_id
        self.refresh_history_rows(select_session_id=session.session_id, update_detail=False)
        return session.session_id

    def _persist_run(
        self,
        *,
        prompt: str,
        response: str,
        run_id: str,
        sources: list[EvidenceSource],
    ) -> None:
        session_id = self._ensure_session(prompt)
        self.session_repository.upsert_session(
            session_id,
            title=self._title_from_prompt(prompt),
            summary=self._summary_from_response(response),
            active_profile=self._current_profile_label(),
            mode=str(self.model.settings.get("selected_mode", "Q&A") or "Q&A"),
            index_id=str(getattr(self.model, "active_index_id", "") or ""),
            vector_backend=self._current_vector_backend(),
            llm_provider=str(self.model.settings.get("llm_provider", "") or ""),
            llm_model=self._effective_llm_model(),
            embed_model=self._effective_embedding_model(),
            retrieve_k=int(self.model.settings.get("retrieval_k", 0) or 0),
            final_k=int(self.model.settings.get("top_k", 0) or 0),
            mmr_lambda=float(self.model.settings.get("mmr_lambda", 0.0) or 0.0),
            agentic_iterations=int(self.model.settings.get("agentic_max_iterations", 0) or 0),
            extra_json=self._session_extra_json(),
        )
        self.session_repository.append_message(
            session_id,
            role="user",
            content=prompt,
            run_id=run_id,
        )
        self.session_repository.append_message(
            session_id,
            role="assistant",
            content=response,
            run_id=run_id,
            sources=sources,
        )
        self.refresh_history_rows(select_session_id=session_id, update_detail=False)

    def _restore_session_settings(self, detail: Any) -> None:
        summary = detail.summary if hasattr(detail, "summary") else detail
        extra = getattr(summary, "extra", {})
        if isinstance(extra, dict):
            self.model.settings.update(extra)
        profile_label = str(
            getattr(summary, "active_profile", "")
            or (extra.get("selected_profile") if isinstance(extra, dict) else "")
            or "Built-in: Default"
        ).strip()
        self.model.current_profile_label = profile_label or "Built-in: Default"
        self.model.settings["selected_profile"] = self.model.current_profile_label
        if getattr(summary, "mode", ""):
            self.model.settings["selected_mode"] = summary.mode
        if getattr(summary, "llm_provider", ""):
            self.model.settings["llm_provider"] = summary.llm_provider
        if getattr(summary, "llm_model", ""):
            self.model.settings["llm_model"] = summary.llm_model
        if getattr(summary, "embed_model", ""):
            self.model.settings["embedding_model"] = summary.embed_model
        if getattr(summary, "vector_backend", ""):
            self.model.settings["vector_db_type"] = summary.vector_backend
        self.model.settings["retrieval_k"] = getattr(summary, "retrieve_k", self.model.settings.get("retrieval_k", 3))
        self.model.settings["top_k"] = getattr(summary, "final_k", self.model.settings.get("top_k", 3))
        self.model.settings["mmr_lambda"] = getattr(summary, "mmr_lambda", self.model.settings.get("mmr_lambda", 0.5))
        self.model.settings["agentic_max_iterations"] = getattr(
            summary,
            "agentic_iterations",
            self.model.settings.get("agentic_max_iterations", 2),
        )
        self._safe_view_call("populate_settings", self.model.settings)
        self._safe_view_call("select_profile_label", self.model.current_profile_label)

    def _restore_index_from_session(self, detail: Any) -> None:
        summary = detail.summary if hasattr(detail, "summary") else detail
        extra = getattr(summary, "extra", {})
        candidate = str(extra.get("selected_index_path") or "").strip() if isinstance(extra, dict) else ""
        if not candidate and getattr(summary, "index_id", ""):
            root = pathlib.Path(getattr(self.model, "index_storage_dir", pathlib.Path(".")))
            guessed_manifest = root / str(summary.index_id) / "manifest.json"
            guessed_legacy = root / f"{summary.index_id}.json"
            if guessed_manifest.exists():
                candidate = str(guessed_manifest)
            elif guessed_legacy.exists():
                candidate = str(guessed_legacy)
        if not candidate and isinstance(extra, dict):
            selected_collection = str(extra.get("selected_collection_name") or "").strip()
            for row in self.model.available_indexes:
                if str(row.get("collection_name", "") or "") == selected_collection:
                    candidate = str(row.get("path", "") or "")
                    break
        if not candidate:
            return
        self._load_bundle_from_path(candidate, persist=False)

    def _apply_index_bundle(self, bundle: IndexBundle, *, persist: bool = False) -> None:
        self.model.index_bundle = bundle
        self.model.documents = list(bundle.documents)
        self.model.chunks = list(bundle.chunks)
        self.model.embeddings = list(bundle.embeddings)
        self.model.knowledge_graph = bundle.knowledge_graph
        self.model.entity_to_chunks = dict(bundle.entity_to_chunks)
        self.model.active_index_id = bundle.index_id
        self.model.active_index_path = bundle.index_path
        self.model.selected_brain_node = f"index:{bundle.index_id}"
        self.model.index_state = {
            "built": True,
            "doc_count": len(bundle.documents),
            "chunk_count": len(bundle.chunks),
        }
        self.model.settings["selected_index_path"] = str(bundle.index_path or "")
        self.model.settings["selected_collection_name"] = str(
            bundle.metadata.get("collection_name") or bundle.index_id or ""
        )
        self.model.settings["index_embedding_signature"] = str(bundle.embedding_signature or "")
        self.model.settings["vector_db_type"] = str(bundle.vector_backend or "json")
        weaviate_settings = dict(bundle.metadata.get("weaviate_settings") or {})
        for key, value in weaviate_settings.items():
            self.model.settings[str(key)] = value
        self._safe_view_call(
            "set_active_index_summary",
            f"Active index: {bundle.index_id}  |  {len(bundle.documents)} file(s)  |  {len(bundle.chunks)} chunk(s)",
            bundle.index_path,
        )
        self._safe_view_call(
            "set_file_list",
            [pathlib.Path(p).name for p in bundle.documents],
        )
        if persist:
            self._persist_active_index_selection(bundle)

    def _current_index_bundle(self) -> IndexBundle | None:
        bundle = getattr(self.model, "index_bundle", None)
        if isinstance(bundle, IndexBundle):
            return bundle
        if not getattr(self.model, "chunks", None) or not getattr(self.model, "embeddings", None):
            return None
        return IndexBundle(
            index_id=str(getattr(self.model, "active_index_id", "") or "in-memory"),
            created_at="",
            documents=list(getattr(self.model, "documents", []) or []),
            chunks=list(self.model.chunks),
            embeddings=list(self.model.embeddings),
            knowledge_graph=getattr(self.model, "knowledge_graph", None),
            entity_to_chunks=dict(getattr(self.model, "entity_to_chunks", {}) or {}),
            index_path=str(getattr(self.model, "active_index_path", "") or ""),
            vector_backend=self._current_vector_backend(),
            embedding_signature=str(self.model.settings.get("index_embedding_signature", "") or ""),
            metadata={
                "collection_name": str(self.model.settings.get("selected_collection_name", "") or ""),
            },
        )

    def _effective_llm_model(self) -> str:
        return (
            str(self.model.settings.get("llm_model", "") or "").strip()
            or str(self.model.settings.get("llm_model_custom", "") or "").strip()
        )

    def _effective_embedding_model(self) -> str:
        return (
            str(self.model.settings.get("embedding_model", "") or "").strip()
            or str(self.model.settings.get("embedding_model_custom", "") or "").strip()
            or str(self.model.settings.get("sentence_transformers_model", "") or "").strip()
        )

    def _session_extra_json(self) -> str:
        payload = {
            "selected_profile": self._current_profile_label(),
            "selected_index_path": str(getattr(self.model, "active_index_path", "") or ""),
            "selected_collection_name": str(
                (
                    getattr(getattr(self.model, "index_bundle", None), "metadata", {}) or {}
                ).get("collection_name")
                or getattr(self.model, "active_index_id", "")
                or ""
            ),
            "index_embedding_signature": str(self.model.settings.get("index_embedding_signature", "") or ""),
            "output_style": self.model.settings.get("output_style", ""),
            "llm_temperature": self.model.settings.get("llm_temperature", 0.0),
            "llm_max_tokens": self.model.settings.get("llm_max_tokens", 0),
            "embedding_provider": self.model.settings.get("embedding_provider", ""),
            "llm_model_custom": self.model.settings.get("llm_model_custom", ""),
            "embedding_model_custom": self.model.settings.get("embedding_model_custom", ""),
            "local_gguf_model_path": self.model.settings.get("local_gguf_model_path", ""),
            "local_gguf_context_length": self.model.settings.get("local_gguf_context_length", 0),
            "local_gguf_gpu_layers": self.model.settings.get("local_gguf_gpu_layers", 0),
            "local_gguf_threads": self.model.settings.get("local_gguf_threads", 0),
            "search_type": self.model.settings.get("search_type", ""),
            "retrieval_mode": self.model.settings.get("retrieval_mode", ""),
            "agentic_mode": self.model.settings.get("agentic_mode", False),
            "use_reranker": self.model.settings.get("use_reranker", False),
            "use_sub_queries": self.model.settings.get("use_sub_queries", False),
            "subquery_max_docs": self.model.settings.get("subquery_max_docs", 0),
            "chat_path": self.model.settings.get("chat_path", "RAG"),
            "vector_db_type": self._current_vector_backend(),
            "weaviate_url": self.model.settings.get("weaviate_url", ""),
            "weaviate_api_key": self.model.settings.get("weaviate_api_key", ""),
            "weaviate_grpc_host": self.model.settings.get("weaviate_grpc_host", ""),
            "weaviate_grpc_port": self.model.settings.get("weaviate_grpc_port", ""),
            "weaviate_grpc_secure": self.model.settings.get("weaviate_grpc_secure", ""),
            "startup_mode_setting": self.model.settings.get("startup_mode_setting", "advanced"),
            "last_used_mode": self.model.settings.get("last_used_mode", "advanced"),
            "basic_wizard_completed": self.model.settings.get("basic_wizard_completed", False),
            "local_st_model_name": self.model.settings.get("local_st_model_name", ""),
            "local_model_registry": self.model.settings.get("local_model_registry", {}),
            "deepread_mode": self.model.settings.get("deepread_mode", False),
            "secure_mode": self.model.settings.get("secure_mode", False),
            "experimental_override": self.model.settings.get("experimental_override", False),
            "show_retrieved_context": self.model.settings.get("show_retrieved_context", False),
        }
        return json.dumps(payload, ensure_ascii=False)

    def _sync_current_session_metadata(self) -> None:
        session_id = str(getattr(self.model, "current_session_id", "") or "").strip()
        if not session_id:
            return
        self.session_repository.upsert_session(
            session_id,
            active_profile=self._current_profile_label(),
            mode=str(self.model.settings.get("selected_mode", "Q&A") or "Q&A"),
            index_id=str(getattr(self.model, "active_index_id", "") or ""),
            vector_backend=self._current_vector_backend(),
            llm_provider=str(self.model.settings.get("llm_provider", "") or ""),
            llm_model=self._effective_llm_model(),
            embed_model=self._effective_embedding_model(),
            retrieve_k=int(self.model.settings.get("retrieval_k", 0) or 0),
            final_k=int(self.model.settings.get("top_k", 0) or 0),
            mmr_lambda=float(self.model.settings.get("mmr_lambda", 0.0) or 0.0),
            agentic_iterations=int(self.model.settings.get("agentic_max_iterations", 0) or 0),
            extra_json=self._session_extra_json(),
        )

    @staticmethod
    def _title_from_prompt(prompt: str) -> str:
        text = " ".join(str(prompt or "").split()).strip()
        if not text:
            return "New Chat"
        return text[:72] + ("…" if len(text) > 72 else "")

    @staticmethod
    def _summary_from_response(response: str) -> str:
        text = " ".join(str(response or "").split()).strip()
        if not text:
            return ""
        return text[:180] + ("…" if len(text) > 180 else "")

    def on_quick_model_change(self, payload: dict[str, Any] | None = None) -> None:
        request = dict(payload or {})
        provider = str(request.get("llm_provider", "") or "").strip()
        requested_model = str(request.get("llm_model", "") or "").strip()
        requested_custom = str(request.get("llm_model_custom", "") or "").strip()

        if provider not in set(list_llm_providers()):
            self._safe_view_call("set_status", "Model switch ignored: unknown provider.")
            return

        is_custom_value = provider_requires_custom_model(provider) or bool(requested_custom)
        resolved_model = requested_custom if requested_custom else requested_model
        resolved_model = str(resolved_model or "").strip()
        if not resolved_model:
            self._show_error_dialog("Model Required", "Choose or enter a model before applying the switch.")
            self._safe_view_call("set_status", "Model switch ignored: no model was provided.")
            return

        next_settings = dict(self.model.settings)
        next_settings["llm_provider"] = provider
        next_settings["llm_model"] = resolved_model
        next_settings["llm_model_custom"] = resolved_model if is_custom_value else ""

        if provider == "local_gguf" and not self._has_valid_local_gguf_path(next_settings):
            self._show_error_dialog(
                "Invalid Local GGUF Model",
                "Quick switch blocked because no valid GGUF model file is configured in Settings.",
            )
            self._safe_view_call("set_status", "Model switch blocked: configure a valid GGUF file first.")
            return

        try:
            self.model.save_settings(next_settings)
        except OSError as exc:
            self._show_error_dialog("Save Failed", f"Could not write settings.json:\n{exc}")
            self._log.error("quick model switch save failed: %s", exc)
            return

        self._safe_view_call("populate_settings", self.model.settings)
        self._safe_view_call("refresh_llm_status_badge")
        self._sync_current_session_metadata()
        self.refresh_history_rows(select_session_id=str(getattr(self.model, "current_session_id", "") or ""), update_detail=False)
        self._safe_view_call("set_status", f"Model switched to {provider} / {resolved_model}.")
        self._log.info("Quick model switch applied: provider=%s model=%s", provider, resolved_model)

    def on_save_settings(self) -> None:
        """Collect settings from the view, coerce types, and persist via the model.

        Called when the user clicks "Save Settings" in the Settings pane.
        Validates all numeric fields and shows a messagebox on error or success.
        """
        raw = self.view.collect_settings()
        raw["selected_profile"] = self._current_profile_label()
        raw["selected_index_path"] = str(getattr(self.model, "active_index_path", "") or "")
        raw["selected_collection_name"] = str(
            (
                getattr(getattr(self.model, "index_bundle", None), "metadata", {}) or {}
            ).get("collection_name")
            or getattr(self.model, "active_index_id", "")
            or ""
        )
        raw["index_embedding_signature"] = str(self.model.settings.get("index_embedding_signature", "") or "")

        # ── Type coercion tables ────────────────────────────────────────
        # (key, cast_fn, clamp_min_or_None, clamp_max_or_None)
        _INT_FIELDS = [
            ("chunk_size",                int, 1,   None),
            ("chunk_overlap",             int, 0,   None),
            ("top_k",                     int, 1,   None),
            ("retrieval_k",               int, 1,   None),
            ("llm_max_tokens",            int, 1,   None),
            ("local_gguf_context_length", int, 128, None),
            ("local_gguf_gpu_layers",     int, 0,   None),
            ("local_gguf_threads",        int, 0,   None),
            ("hardware_override_gpu_count", int, 0, None),
            ("local_st_batch_size",       int, 1,   None),
            ("agentic_max_iterations",    int, 1,   10),
            ("subquery_max_docs",         int, 1,   None),
            ("chat_history_max_turns",    int, 1,   None),
        ]
        _FLOAT_FIELDS = [
            ("llm_temperature", float, 0.0, 2.0),
            ("mmr_lambda",      float, 0.0, 1.0),
            ("hardware_override_total_ram_gb", float, 0.0, None),
            ("hardware_override_available_ram_gb", float, 0.0, None),
            ("hardware_override_gpu_vram_gb", float, 0.0, None),
        ]
        _BOOL_FIELDS = [
            "verbose_mode", "force_embedding_compat",
            "structure_aware_ingestion", "semantic_layout_ingestion",
            "build_digest_index", "build_comprehension_index",
            "use_reranker", "use_sub_queries",
            "agentic_mode", "show_retrieved_context",
            "enable_summarizer", "enable_langextract",
            "enable_structured_extraction", "enable_recursive_memory",
            "enable_recursive_retrieval", "enable_citation_v2",
            "enable_claim_level_grounding_citefix_lite",
            "agent_lightning_enabled", "prefer_comprehension_index",
            "deepread_mode", "secure_mode", "experimental_override",
            "hardware_override_enabled", "hardware_override_unified_memory",
        ]
        _STRING_FIELDS = [
            "local_gguf_model_path",
            "local_gguf_models_dir",
            "hardware_override_gpu_name",
            "hardware_override_backend",
        ]

        coerced: dict[str, Any] = {}
        errors: list[str] = []

        for key, cast_fn, lo, hi in _INT_FIELDS:
            raw_val = raw.get(key, "")
            try:
                v = cast_fn(str(raw_val).strip())
                if lo is not None:
                    v = max(lo, v)
                if hi is not None:
                    v = min(hi, v)
                coerced[key] = v
            except (ValueError, TypeError):
                errors.append(f"'{key}' must be a whole number (got: {raw_val!r})")

        for key, cast_fn, lo, hi in _FLOAT_FIELDS:
            raw_val = raw.get(key, "")
            try:
                v = cast_fn(str(raw_val).strip())
                if lo is not None:
                    v = max(lo, v)
                if hi is not None:
                    v = min(hi, v)
                coerced[key] = v
            except (ValueError, TypeError):
                errors.append(f"'{key}' must be a number (got: {raw_val!r})")

        for key in _BOOL_FIELDS:
            coerced[key] = bool(raw.get(key, False))

        for key in _STRING_FIELDS:
            coerced[key] = str(raw.get(key, "") or "").strip()

        # All remaining keys are strings — strip whitespace.
        _typed_keys = (
            {k for k, *_ in _INT_FIELDS}
            | {k for k, *_ in _FLOAT_FIELDS}
            | set(_BOOL_FIELDS)
            | set(_STRING_FIELDS)
        )
        for key, val in raw.items():
            if key not in _typed_keys:
                coerced[key] = str(val).strip() if isinstance(val, str) else val

        if errors:
            self._show_error_dialog(
                "Invalid Settings",
                "Please fix these errors before saving:\n\n"
                + "\n".join(f"• {e}" for e in errors),
            )
            return

        if (
            str(coerced.get("llm_provider", "") or "").strip() == "local_gguf"
            and not str(coerced.get("local_gguf_model_path", "") or "").strip()
        ):
            self._show_error_dialog(
                "Local GGUF Model Required",
                "LLM Provider is set to local_gguf, but GGUF Model Path is empty. "
                "Please select a .gguf model file before saving.",
            )
            self.view.set_status("Settings warning: local_gguf requires a GGUF model path.")
            return

        if str(coerced.get("llm_provider", "") or "").strip() == "local_gguf":
            model_path = pathlib.Path(str(coerced.get("local_gguf_model_path", "")).strip()).expanduser()
            if not model_path.is_file():
                self._show_error_dialog(
                    "Invalid Local GGUF Model",
                    "LLM Provider is set to local_gguf, but the configured GGUF model file "
                    f"does not exist:\n\n{model_path}",
                )
                self.view.set_status("Settings warning: local_gguf model file was not found.")
                return

        try:
            self.model.save_settings(coerced)
        except OSError as exc:
            self._show_error_dialog(
                "Save Failed",
                f"Could not write settings.json:\n{exc}",
            )
            self._log.error("save_settings failed: %s", exc)
            return

        self._safe_view_call("set_status", "Settings saved to settings.json.")
        self._safe_view_call("populate_settings", coerced)
        self._safe_view_call("refresh_llm_status_badge")
        self._sync_profile_options()
        self._sync_local_model_rows()
        self._sync_local_gguf_recommendations()
        self.refresh_available_indexes(select_path=str(self.model.settings.get("selected_index_path", "") or ""))
        self._log.info("Settings saved successfully (%d keys).", len(coerced))

        current_theme = getattr(self.view, "_theme_name", coerced.get("theme", "space_dust"))
        new_theme = coerced.get("theme", current_theme)
        if new_theme != current_theme and callable(getattr(self.view, "apply_theme", None)):
            self.view.apply_theme(new_theme)

        if getattr(self.model, "current_session_id", ""):
            self._sync_current_session_metadata()
