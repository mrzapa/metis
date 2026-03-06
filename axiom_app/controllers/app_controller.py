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
import pathlib
import uuid
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any, Callable

from axiom_app.models.session_types import EvidenceSource
from axiom_app.services.index_service import (
    IndexBundle,
    build_index_bundle,
    load_index_bundle,
    query_index_bundle,
    save_index_bundle,
)
from axiom_app.services.session_repository import SessionRepository
from axiom_app.utils.background import BackgroundRunner, CancelToken
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
        db_path = getattr(self.model, "session_db_path", ":memory:")
        self.session_repository = session_repository or SessionRepository(db_path)
        self.session_repository.init_db()
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

        # Ctrl+Enter / Return in the multi-line Text input submits
        self.view.prompt_entry.bind("<Return>",
                                   lambda _e: self._on_send_clicked() or "break")

        # Pass loaded settings to the view for display in the Settings tab.
        # Called last so the settings tab is already built and widgets update immediately.
        self.view.populate_settings(self.model.settings)
        self.refresh_history_rows(update_detail=False)

    def _on_mode_state_changed(self, mode_state: dict[str, str]) -> None:
        """Keep runtime canonical chat mode state in the model settings."""
        self.model.settings["selected_mode"] = mode_state.get("selected_mode", "Q&A")
        self.model.settings["chat_path"] = mode_state.get("chat_path", "RAG")

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
                self._apply_index_bundle(result)
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

                header = (
                    f"Axiom [{provider}, rag, mode={selected_mode}, "
                    f"{n_chunks} chunk(s)]:\n\n"
                )
                self._safe_view_call("append_chat", header + response + "\n\n")
                self.model.chat_history.append({"role": "user", "content": prompt})
                self.model.chat_history.append({"role": "assistant", "content": response})
                self.model.last_sources = sources
                self._safe_view_call("render_evidence_sources", sources)
                self._persist_run(
                    prompt=prompt,
                    response=response,
                    run_id=run_id,
                    sources=sources,
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
                self._safe_view_call("render_evidence_sources", [])
                self._persist_run(
                    prompt=prompt,
                    response=response,
                    run_id=run_id,
                    sources=[],
                )
                self._log.info("Direct query answered — provider=%s", provider)
                self._safe_view_call("set_status", "Done.")

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

        index_dir = getattr(self.model, "index_storage_dir", None)

        def _worker(post_msg: Any, cancel: CancelToken) -> IndexBundle:
            bundle = build_index_bundle(
                docs,
                settings_snapshot,
                post_message=post_msg,
                cancel_token=cancel,
            )
            out_path = save_index_bundle(bundle, index_dir=index_dir)
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

        bundle = self._current_index_bundle()
        if bundle is None or not self.model.index_state.get("built"):
            self._safe_view_call(
                "append_chat",
                "⚠  No index built yet.\n"
                "   Open a text file and click 'Build Index' first, or switch to Direct mode.\n\n"
            )
            self._safe_view_call("switch_view", "chat")
            return

        query_result = query_index_bundle(bundle, prompt, dict(self.model.settings))
        self.model.last_sources = list(query_result.sources)
        self._safe_view_call("render_evidence_sources", list(query_result.sources))

        # Show the user's prompt immediately.
        sep = "─" * 52
        self._safe_view_call("append_chat", f"You: {prompt}\n{sep}\n", "user")
        self._safe_view_call("switch_view", "chat")

        # ── LLM synthesis (background thread) ────────────────────────────
        settings_snap = dict(self.model.settings)
        selected_mode = settings_snap.get("selected_mode", "Q&A")
        provider = str(settings_snap.get("llm_provider", "mock") or "mock")
        run_id = str(uuid.uuid4())

        def _rag_worker(post_msg: Any, cancel: CancelToken) -> dict[str, str]:
            post_msg({"type": "status", "text": "Generating answer…"})
            try:
                llm = create_llm(settings_snap)
            except (ValueError, ImportError) as exc:
                return {
                    "response": (
                        f"Axiom [rag, mode={selected_mode}]: "
                        f"LLM unavailable ({exc}). Showing raw retrieval.\n\n"
                        f"CONTEXT:\n{query_result.context_block}\n"
                    ),
                    "prompt": prompt,
                }

            system_prompt = (
                f"You are Axiom, an AI assistant. Mode: {selected_mode}.\n"
                "Answer the user's question using ONLY the CONTEXT below. "
                "Cite passages as [S1], [S2], etc. If the context is insufficient, say so.\n\n"
                f"CONTEXT:\n{query_result.context_block}"
            )
            messages = [
                {"type": "system", "content": system_prompt},
                {"type": "human", "content": prompt},
            ]
            result = llm.invoke(messages)
            answer = str(getattr(result, "content", result) or "")
            return {"response": answer, "prompt": prompt}

        # Store retrieval metadata for _handle_message to use.
        self._pending_task_meta = {
            "selected_mode": selected_mode,
            "n_chunks": len(bundle.embeddings),
            "top_score": query_result.top_score,
            "prompt": prompt,
            "provider": provider,
            "run_id": run_id,
            "sources": list(query_result.sources),
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

        settings_snap = dict(self.model.settings)
        run_id = str(uuid.uuid4())

        def _direct_worker(post_msg: Any, cancel: CancelToken) -> dict[str, str]:
            post_msg({"type": "status", "text": f"Generating ({provider_name})…"})
            try:
                llm = create_llm(settings_snap)
            except (ValueError, ImportError, RuntimeError) as exc:
                return {
                    "response": f"Axiom [{provider_name}, direct]: {exc}\n\n",
                    "prompt": prompt,
                    "error": str(exc),
                }

            messages = [
                {"type": "system", "content": "You are Axiom, an AI assistant. Answer the user's question."},
                {"type": "human", "content": prompt},
            ]
            try:
                result = llm.invoke(messages)
                answer = str(getattr(result, "content", result) or "")
            except Exception as exc:
                return {
                    "response": f"Axiom [{provider_name}, direct]: LLM error: {exc}\n\n",
                    "prompt": prompt,
                    "error": str(exc),
                }

            return {"response": answer, "prompt": prompt}

        self._pending_task_meta = {
            "prompt": prompt,
            "provider": provider_name,
            "run_id": run_id,
            "sources": [],
        }
        self.start_task(_TASK_DIRECT_QUERY, _direct_worker)

    def on_cancel_job(self) -> None:
        """Cancel any running background job."""
        self.cancel_current_task()

    def on_new_chat(self) -> None:
        """Start a persisted chat session and clear transient UI state."""
        session = self.session_repository.create_session(
            title="New Chat",
            mode=str(self.model.settings.get("selected_mode", "Q&A") or "Q&A"),
            index_id=str(getattr(self.model, "active_index_id", "") or ""),
            vector_backend="json",
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
        rows = self.session_repository.list_sessions(search=search)
        self.model.session_list = rows
        self._safe_view_call("set_history_rows", rows)
        if select_session_id:
            self._safe_view_call("select_history_session", select_session_id)
        if update_detail:
            self.on_history_selection_changed()

    def on_history_search_changed(self, _event: Any | None = None) -> None:
        self.refresh_history_rows(update_detail=True)

    def on_history_selection_changed(self, _event: Any | None = None) -> None:
        session_id = self._selected_history_session_id()
        if not session_id:
            return
        detail = self.session_repository.get_session(session_id)
        if detail is None:
            return
        self.model.loaded_session = detail
        self._safe_view_call("set_history_detail", detail)

    def on_open_session(self) -> None:
        session_id = self._selected_history_session_id()
        if not session_id:
            return
        detail = self.session_repository.get_session(session_id)
        if detail is None:
            return

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

    def _ensure_session(self, prompt: str = "") -> str:
        current = str(getattr(self.model, "current_session_id", "") or "")
        if current and self.session_repository.get_session(current) is not None:
            return current

        title = self._title_from_prompt(prompt) if prompt else "New Chat"
        session = self.session_repository.create_session(
            title=title,
            mode=str(self.model.settings.get("selected_mode", "Q&A") or "Q&A"),
            index_id=str(getattr(self.model, "active_index_id", "") or ""),
            vector_backend="json",
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
            mode=str(self.model.settings.get("selected_mode", "Q&A") or "Q&A"),
            index_id=str(getattr(self.model, "active_index_id", "") or ""),
            vector_backend="json",
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
        if getattr(summary, "mode", ""):
            self.model.settings["selected_mode"] = summary.mode
        if getattr(summary, "llm_provider", ""):
            self.model.settings["llm_provider"] = summary.llm_provider
        if getattr(summary, "llm_model", ""):
            self.model.settings["llm_model"] = summary.llm_model
        if getattr(summary, "embed_model", ""):
            self.model.settings["embedding_model"] = summary.embed_model
        self.model.settings["retrieval_k"] = getattr(summary, "retrieve_k", self.model.settings.get("retrieval_k", 3))
        self.model.settings["top_k"] = getattr(summary, "final_k", self.model.settings.get("top_k", 3))
        self.model.settings["mmr_lambda"] = getattr(summary, "mmr_lambda", self.model.settings.get("mmr_lambda", 0.5))
        self.model.settings["agentic_max_iterations"] = getattr(
            summary,
            "agentic_iterations",
            self.model.settings.get("agentic_max_iterations", 2),
        )
        self._safe_view_call("populate_settings", self.model.settings)

    def _restore_index_from_session(self, detail: Any) -> None:
        summary = detail.summary if hasattr(detail, "summary") else detail
        extra = getattr(summary, "extra", {})
        candidate = str(extra.get("selected_index_path") or "").strip() if isinstance(extra, dict) else ""
        if not candidate and getattr(summary, "index_id", ""):
            root = pathlib.Path(getattr(self.model, "index_storage_dir", pathlib.Path(".")))
            guessed = root / f"{summary.index_id}.json"
            if guessed.exists():
                candidate = str(guessed)
        if not candidate:
            return
        index_path = pathlib.Path(candidate)
        if not index_path.exists():
            return
        try:
            bundle = load_index_bundle(index_path)
        except Exception as exc:
            self._log.warning("Could not restore index '%s': %s", index_path, exc)
            return
        self._apply_index_bundle(bundle)

    def _apply_index_bundle(self, bundle: IndexBundle) -> None:
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
        self._safe_view_call(
            "set_active_index_summary",
            f"Active index: {bundle.index_id}  |  {len(bundle.documents)} file(s)  |  {len(bundle.chunks)} chunk(s)",
            bundle.index_path,
        )
        self._safe_view_call(
            "set_file_list",
            [pathlib.Path(p).name for p in bundle.documents],
        )

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
            "selected_index_path": str(getattr(self.model, "active_index_path", "") or ""),
            "selected_collection_name": str(getattr(self.model, "active_index_id", "") or ""),
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
        self._log.info("Settings saved successfully (%d keys).", len(coerced))

        new_theme = coerced.get("theme", self.view._theme_name)
        if new_theme != self.view._theme_name:
            self.view.apply_theme(new_theme)

        if getattr(self.model, "current_session_id", ""):
            self.session_repository.upsert_session(
                self.model.current_session_id,
                mode=str(self.model.settings.get("selected_mode", "Q&A") or "Q&A"),
                index_id=str(getattr(self.model, "active_index_id", "") or ""),
                vector_backend="json",
                llm_provider=str(self.model.settings.get("llm_provider", "") or ""),
                llm_model=self._effective_llm_model(),
                embed_model=self._effective_embedding_model(),
                retrieve_k=int(self.model.settings.get("retrieval_k", 0) or 0),
                final_k=int(self.model.settings.get("top_k", 0) or 0),
                mmr_lambda=float(self.model.settings.get("mmr_lambda", 0.0) or 0.0),
                agentic_iterations=int(self.model.settings.get("agentic_max_iterations", 0) or 0),
                extra_json=self._session_extra_json(),
            )
