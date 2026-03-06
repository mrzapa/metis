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

from axiom_app.models.parity_types import AgentProfile
from axiom_app.models.session_types import EvidenceSource
from axiom_app.services.index_service import (
    IndexBundle,
    list_index_manifests,
    load_index_bundle,
    refresh_index_bundle,
)
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
        self.profile_repository = ProfileRepository(getattr(self.model, "profiles_dir", None))
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

    def _safe_view_call(self, method_name: str, *args: Any) -> Any:
        method = getattr(self.view, method_name, None)
        if callable(method):
            return method(*args)
        return None

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
        from tkinter import messagebox

        body = "\n".join(f"- {item}" for item in blockers)
        approved = messagebox.askyesno(
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
        self.model.settings.update(updates)
        self.model.save_settings(self.model.settings)
        self._safe_view_call("populate_settings", self.model.settings)

        selected_index = str(result.get("selected_index_path", "") or "").strip()
        source_file = str(result.get("file_path", "") or "").strip()
        if selected_index:
            self._load_bundle_from_path(selected_index, persist=True)
        elif source_file:
            self.model.set_documents([source_file])
            self._safe_view_call("set_file_list", [pathlib.Path(source_file).name])
            self.on_build_index()
        self._safe_view_call("switch_view", "chat")
        self._safe_view_call("set_status", "Setup complete.")

    # ------------------------------------------------------------------
    # Event wiring
    # ------------------------------------------------------------------

    def wire_events(self) -> None:
        """Bind view widgets to controller callbacks."""
        self.view.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # Library view buttons (lazily built — switch_view("library") triggers build)
        # We pre-switch to ensure library is built before wiring, then return to chat.
        self.view.switch_view("library")
        self.view.btn_open_files.configure(command=self.on_open_files)
        self.view.btn_build_index.configure(command=self.on_build_index)

        # Settings view (lazily built) — force build now so btn_save_settings exists.
        self.view.switch_view("settings")
        self.view.btn_save_settings.configure(command=self.on_save_settings)

        # History view — build before wiring its actions.
        self.view.switch_view("history")
        for attr, callback in (
            ("btn_history_new_chat", self.on_new_chat),
            ("btn_history_open", self.on_open_session),
            ("btn_history_delete", self.on_delete_session),
            ("btn_history_rename", self.on_rename_session),
            ("btn_history_duplicate", self.on_duplicate_session),
            ("btn_history_export", self.on_export_session),
            ("btn_history_refresh", self.refresh_history_rows),
        ):
            widget = getattr(self.view, attr, None)
            if widget is not None:
                widget.configure(command=callback)
        bind_history_search = getattr(self.view, "bind_history_search", None)
        if callable(bind_history_search):
            bind_history_search(self.on_history_search_changed)
        bind_history_selection = getattr(self.view, "bind_history_selection", None)
        if callable(bind_history_selection):
            bind_history_selection(self.on_history_selection_changed)
        bind_history_profile = getattr(self.view, "bind_history_profile_filter", None)
        if callable(bind_history_profile):
            bind_history_profile(self.on_history_profile_changed)
        history_tree = getattr(self.view, "_history_tree", None)
        if history_tree is not None:
            history_tree.bind("<Double-1>", lambda _e: self.on_open_session())

        self.view.switch_view("chat")

        # Chat view widgets
        self.view.btn_send.configure(command=self._on_send_clicked)
        self.view.btn_cancel_rag.configure(command=self.on_cancel_job)
        self.view.set_mode_state_callback(self._on_mode_state_changed)
        btn_new_chat = getattr(self.view, "btn_new_chat", None)
        if btn_new_chat is not None:
            btn_new_chat.configure(command=self.on_new_chat)
        btn_reset_test_mode = getattr(self.view, "btn_reset_test_mode", None)
        if btn_reset_test_mode is not None:
            btn_reset_test_mode.configure(command=self.reset_test_mode)
        for attr, callback in (
            ("btn_profile_load", self.on_load_profile),
            ("btn_profile_save", self.on_save_profile),
            ("btn_profile_duplicate", self.on_duplicate_profile),
            ("btn_feedback_up", lambda: self.on_submit_feedback(1)),
            ("btn_feedback_down", lambda: self.on_submit_feedback(-1)),
        ):
            widget = getattr(self.view, attr, None)
            if widget is not None:
                widget.configure(command=callback)

        # Ctrl+Enter / Return in the multi-line Text input submits
        self.view.prompt_entry.bind("<Return>",
                                   lambda _e: self._on_send_clicked() or "break")

        for attr, callback in (
            ("btn_library_load_index", self.on_load_selected_index),
        ):
            widget = getattr(self.view, attr, None)
            if widget is not None:
                widget.configure(command=callback)

        for attr, callback in (
            ("btn_add_local_gguf_model", self.on_add_local_gguf_model),
            ("btn_add_local_st_model", self.on_add_local_st_model),
            ("btn_remove_local_model", self.on_remove_local_model),
            ("btn_activate_local_model_llm", lambda: self.on_activate_local_model("llm")),
            ("btn_activate_local_model_embedding", lambda: self.on_activate_local_model("embedding")),
            ("btn_open_local_model_folder", self.on_open_local_model_folder),
            ("btn_install_local_gguf_dep", lambda: self.on_install_local_dependency(["llama-cpp-python"])),
            ("btn_install_local_st_dep", lambda: self.on_install_local_dependency(["sentence-transformers"])),
        ):
            widget = getattr(self.view, attr, None)
            if widget is not None:
                widget.configure(command=callback)

        # Pass loaded settings to the view for display in the Settings tab.
        # Called last so the settings tab is already built and widgets update immediately.
        self.view.populate_settings(self.model.settings)
        self.refresh_history_rows(update_detail=False)

    def _on_mode_state_changed(self, mode_state: dict[str, str]) -> None:
        """Keep runtime canonical chat mode state in the model settings."""
        self.model.settings["selected_mode"] = mode_state.get("selected_mode", "Q&A")
        self.model.settings["chat_path"] = mode_state.get("chat_path", "RAG")

    def bootstrap_app(self) -> None:
        """Synchronize profiles, indexes, local models, and startup mode."""
        self._sync_profile_options()
        self._sync_local_model_rows()
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
        self.model.documents = []
        self.model.index_state = {"built": False, "doc_count": 0, "chunk_count": 0}
        self.model.chunks = []
        self.model.embeddings = []
        self.model.index_bundle = None
        self.model.active_index_id = ""
        self.model.active_index_path = ""
        self.model.rag_blocked_reason = ""
        self.model.save_settings(self.model.settings)
        if temp_dir and os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        self._safe_view_call("set_file_list", [])
        self._safe_view_call("set_active_index_summary", "No persisted index selected.", "")
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
        try:
            self.view.btn_cancel_rag.configure(state="normal")
        except Exception:
            pass

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
            # Re-enable Build Index and disable Cancel once any task finishes.
            try:
                self.view.btn_build_index.configure(state="normal")
                self.view.btn_cancel_rag.configure(state="disabled")
            except Exception:
                pass

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
            self._log.error("Task error [%s]: %s", msg.get("task_name", "?"), text)
            if tb:
                self._log.debug("Traceback:\n%s", tb.rstrip())
            self._safe_view_call("set_status", f"Error: {text}")
            self._safe_view_call("append_log", f"[error] {text}")
            if tb:
                self._safe_view_call("append_log", tb)

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
        self.view.root.destroy()

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def on_open_files(self) -> None:
        """Open a file dialog and load selected files into the model."""
        from tkinter import filedialog  # lazy: only valid when Tk is running

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

        paths = filedialog.askopenfilenames(title=title, filetypes=filetypes)
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

        self.view.btn_build_index.configure(state="disabled")
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
        self.model.loaded_session = None
        self.model.chat_history = []
        self.model.last_sources = []
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
        self._safe_view_call("set_history_detail", detail)

    def on_open_session(self) -> None:
        session_id = self._selected_history_session_id()
        if not session_id:
            return
        detail = self.session_repository.get_session(session_id)
        if detail is None:
            return
        detail.traces = self._session_trace_payload(detail)

        self.model.current_session_id = session_id
        self.model.loaded_session = detail
        self.model.chat_history = [
            {"role": msg.role, "content": msg.content}
            for msg in detail.messages
        ]
        self._restore_session_settings(detail)
        self._restore_index_from_session(detail)
        self._safe_view_call("set_chat_transcript", detail.messages)

        last_sources: list[EvidenceSource] = []
        for message in reversed(detail.messages):
            if message.sources:
                last_sources = list(message.sources)
                break
        self.model.last_sources = last_sources
        self._safe_view_call("render_evidence_sources", last_sources)
        self._render_bundle_metadata(getattr(self.model, "index_bundle", None), detail.traces)
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
            self.model.last_sources = []
            self._safe_view_call("set_chat_transcript", [])
            self._safe_view_call("render_evidence_sources", [])
        self.refresh_history_rows(update_detail=False)
        self._safe_view_call("set_status", "Session deleted.")

    def on_rename_session(self) -> None:
        session_id = self._selected_history_session_id()
        if not session_id:
            return
        from tkinter import simpledialog

        title = simpledialog.askstring("Rename Session", "New session title:")
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

        from tkinter import filedialog, messagebox

        save_dir = filedialog.askdirectory(title="Select export directory")
        if not save_dir:
            return
        try:
            md_path, json_path = self.session_repository.export_session(session_id, save_dir)
        except OSError as exc:
            messagebox.showerror("Export Failed", f"Could not export session: {exc}")
            return

        self._safe_view_call(
            "append_log",
            f"[history] Exported session to {md_path} and {json_path}",
        )
        self._safe_view_call(
            "set_status",
            f"Exported session: {pathlib.Path(md_path).name}",
        )
        messagebox.showinfo("Session Export", f"Exported:\n{md_path}\n{json_path}")

    def on_load_profile(self) -> None:
        label = self._current_profile_label()
        profile = self.profile_repository.get_profile(label)
        self._apply_profile_to_settings(profile, label=label)
        self.model.save_settings(self.model.settings)
        self._safe_view_call("populate_settings", self.model.settings)
        self._sync_profile_options()
        self._safe_view_call("set_status", f"Loaded profile: {profile.name}")

    def on_save_profile(self) -> None:
        from tkinter import messagebox, simpledialog

        current_label = self._current_profile_label()
        current_path = self.profile_repository.path_from_label(current_label)
        if current_path is not None:
            target_name = current_path.stem
            target_path = current_path
        else:
            target_name = simpledialog.askstring("Save Profile", "Profile name:")
            target_path = None
        if not target_name:
            return
        profile = self._profile_from_settings(str(target_name))
        try:
            saved_path = self.profile_repository.save_profile(profile, target_path=target_path)
        except OSError as exc:
            messagebox.showerror("Save Profile Failed", str(exc))
            return
        label = self.profile_repository.label_for_path(saved_path)
        self.model.current_profile_label = label
        self.model.settings["selected_profile"] = label
        self.model.save_settings(self.model.settings)
        self._sync_profile_options()
        self._safe_view_call("select_profile_label", label)
        self._safe_view_call("set_status", f"Saved profile: {profile.name}")

    def on_duplicate_profile(self) -> None:
        from tkinter import messagebox, simpledialog

        current_label = self._current_profile_label()
        source = self.profile_repository.get_profile(current_label)
        new_name = simpledialog.askstring(
            "Duplicate Profile",
            "Name for the duplicate profile:",
            initialvalue=f"{source.name} Copy",
        )
        if not new_name:
            return
        try:
            saved_path = self.profile_repository.duplicate_profile(
                current_label,
                new_name=new_name,
            )
        except OSError as exc:
            messagebox.showerror("Duplicate Profile Failed", str(exc))
            return
        label = self.profile_repository.label_for_path(saved_path)
        self.model.current_profile_label = label
        self.model.settings["selected_profile"] = label
        self.model.save_settings(self.model.settings)
        self._sync_profile_options()
        self._safe_view_call("select_profile_label", label)
        self._safe_view_call("set_status", f"Duplicated profile: {new_name}")

    def on_submit_feedback(self, vote: int) -> None:
        from tkinter import simpledialog

        session_id = str(getattr(self.model, "current_session_id", "") or "")
        run_id = str(getattr(self.model, "last_run_id", "") or "")
        if not session_id or not run_id:
            self._safe_view_call("set_status", "No completed run is available for feedback.")
            return
        note = simpledialog.askstring(
            "Feedback note",
            "Optional note for this rating:",
            initialvalue="",
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
            self._safe_view_call("set_history_detail", detail)
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

    def on_add_local_gguf_model(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
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
        self.model.save_settings(self.model.settings)
        self._sync_local_model_rows()
        self._safe_view_call("set_status", f"Added GGUF model: {pathlib.Path(path).name}")

    def on_add_local_st_model(self) -> None:
        from tkinter import simpledialog

        name = simpledialog.askstring(
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
        self._safe_view_call("set_status", "Local model removed.")

    def on_activate_local_model(self, target: str) -> None:
        from tkinter import messagebox

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
            messagebox.showerror("Activation Failed", str(exc))
            return
        self.model.save_settings(self.model.settings)
        self._safe_view_call("populate_settings", self.model.settings)
        self._sync_local_model_rows()
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

    def on_save_settings(self) -> None:
        """Collect settings from the view, coerce types, and persist via the model.

        Called when the user clicks "Save Settings" in the Settings pane.
        Validates all numeric fields and shows a messagebox on error or success.
        """
        from tkinter import messagebox  # lazy; only valid while Tk is running

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
            ("local_st_batch_size",       int, 1,   None),
            ("agentic_max_iterations",    int, 1,   10),
            ("subquery_max_docs",         int, 1,   None),
            ("chat_history_max_turns",    int, 1,   None),
        ]
        _FLOAT_FIELDS = [
            ("llm_temperature", float, 0.0, 2.0),
            ("mmr_lambda",      float, 0.0, 1.0),
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
        ]
        _STRING_FIELDS = [
            "local_gguf_model_path",
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
            messagebox.showerror(
                "Invalid Settings",
                "Please fix these errors before saving:\n\n"
                + "\n".join(f"• {e}" for e in errors),
            )
            return

        if (
            str(coerced.get("llm_provider", "") or "").strip() == "local_gguf"
            and not str(coerced.get("local_gguf_model_path", "") or "").strip()
        ):
            messagebox.showerror(
                "Local GGUF Model Required",
                "LLM Provider is set to local_gguf, but GGUF Model Path is empty. "
                "Please select a .gguf model file before saving.",
            )
            self.view.set_status("Settings warning: local_gguf requires a GGUF model path.")
            return

        if str(coerced.get("llm_provider", "") or "").strip() == "local_gguf":
            model_path = pathlib.Path(str(coerced.get("local_gguf_model_path", "")).strip()).expanduser()
            if not model_path.is_file():
                messagebox.showerror(
                    "Invalid Local GGUF Model",
                    "LLM Provider is set to local_gguf, but the configured GGUF model file "
                    f"does not exist:\n\n{model_path}",
                )
                self.view.set_status("Settings warning: local_gguf model file was not found.")
                return

        try:
            self.model.save_settings(coerced)
        except OSError as exc:
            messagebox.showerror(
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
        self.refresh_available_indexes(select_path=str(self.model.settings.get("selected_index_path", "") or ""))
        self._log.info("Settings saved successfully (%d keys).", len(coerced))

        new_theme = coerced.get("theme", self.view._theme_name)
        if new_theme != self.view._theme_name:
            self.view.apply_theme(new_theme)

        if getattr(self.model, "current_session_id", ""):
            self.session_repository.upsert_session(
                self.model.current_session_id,
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
