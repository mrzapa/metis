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

import logging
import math
import pathlib
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any, Callable

from axiom_app.utils.background import BackgroundRunner, CancelToken
from axiom_app.utils.document_loader import KREUZBERG_EXTENSIONS, is_kreuzberg_available, load_document
from axiom_app.utils.embedding_providers import create_embeddings
from axiom_app.utils.knowledge_graph import build_knowledge_graph, collect_graph_chunk_candidates
from axiom_app.utils.llm_providers import create_llm
from axiom_app.utils.mock_embeddings import MockEmbeddings

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

    def __init__(self, model: AppModel, view: AppView) -> None:
        self.model = model
        self.view = view
        self.background_runner = BackgroundRunner()
        self._active_token: CancelToken | None = None
        self._active_future: Future | None = None
        self._log = logging.getLogger(__name__)
        # Metadata for in-flight RAG queries (set before task dispatch).
        self._pending_rag_meta: dict[str, Any] = {}

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

        self.view.switch_view("chat")

        # Chat view widgets
        self.view.btn_send.configure(command=self._on_send_clicked)
        self.view.btn_cancel_rag.configure(command=self.on_cancel_job)
        self.view.set_mode_state_callback(self._on_mode_state_changed)

        # Ctrl+Enter / Return in the multi-line Text input submits
        self.view.prompt_entry.bind("<Return>",
                                   lambda _e: self._on_send_clicked() or "break")

        # Pass loaded settings to the view for display in the Settings tab.
        # Called last so the settings tab is already built and widgets update immediately.
        self.view.populate_settings(self.model.settings)

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
        self.view.set_status("Cancelling…")

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
            self.view.reset_progress()
            # Re-enable Build Index and disable Cancel once any task finishes.
            try:
                self.view.btn_build_index.configure(state="normal")
                self.view.btn_cancel_rag.configure(state="disabled")
            except Exception:
                pass

    def _handle_message(self, msg: dict[str, Any]) -> None:
        mtype = msg.get("type")

        if mtype == "status":
            self.view.set_status(msg.get("text", ""))
            self.view.append_log(f"[status] {msg.get('text', '')}")

        elif mtype == "progress":
            current = int(msg.get("current", 0))
            total = msg.get("total")
            total = int(total) if total is not None else None
            self.view.set_progress(current, total)

        elif mtype == "error":
            text = msg.get("text", "unknown error")
            tb   = msg.get("traceback", "")
            self._log.error("Task error [%s]: %s", msg.get("task_name", "?"), text)
            if tb:
                self._log.debug("Traceback:\n%s", tb.rstrip())
            self.view.set_status(f"Error: {text}")
            self.view.append_log(f"[error] {text}")
            if tb:
                self.view.append_log(tb)

        elif mtype == "done":
            task   = msg.get("task_name", "")
            result = msg.get("result")
            self._log.info("Task complete: %s", task or "(unnamed)")

            if task == _TASK_BUILD_INDEX and isinstance(result, dict):
                # Commit worker result to the model on the main thread.
                self.model.chunks     = result["chunks"]
                self.model.embeddings = result["embeddings"]
                self.model.knowledge_graph = result.get("knowledge_graph")
                self.model.entity_to_chunks = result.get("entity_to_chunks", {})
                n = len(result["chunks"])
                self.model.index_state = {
                    "built":       True,
                    "doc_count":   len(self.model.documents),
                    "chunk_count": n,
                }
                info = f"Index ready — {n} chunk(s) from {len(self.model.documents)} file(s)."
                self.view.set_index_info(info)
                self.view.set_status(info)
                self.view.append_log(f"[done]  {info}")

            elif task == _TASK_RAG_QUERY and isinstance(result, dict):
                response = result.get("response", "")
                prompt   = result.get("prompt", "")
                meta     = getattr(self, "_pending_rag_meta", {})
                provider = str(self.model.settings.get("llm_provider", "mock") or "mock")
                selected_mode = meta.get("selected_mode", "Q&A")
                n_chunks = meta.get("n_chunks", 0)
                top_score = meta.get("top_score", 0.0)

                header = (
                    f"Axiom [{provider}, rag, mode={selected_mode}, "
                    f"{n_chunks} chunk(s)]:\n\n"
                )
                self.view.append_chat(header + response + "\n\n")
                self.model.chat_history.append({"role": "user", "content": prompt})
                self.model.chat_history.append({"role": "assistant", "content": response})
                self._log.info("RAG query answered — top score=%.3f", top_score)
                self.view.set_status("Done.")

            elif task == _TASK_DIRECT_QUERY and isinstance(result, dict):
                response = result.get("response", "")
                prompt   = result.get("prompt", "")
                provider = str(self.model.settings.get("llm_provider", "mock") or "mock")

                if result.get("error"):
                    self.view.append_log(f"[direct] error: {result['error']}")
                else:
                    self.view.append_log(
                        f"[direct] generation_completed provider={provider}"
                    )

                self.view.append_chat(
                    f"Axiom [{provider}, direct]:\n\n{response}\n\n"
                )
                self.model.chat_history.append({"role": "user", "content": prompt})
                self.model.chat_history.append({"role": "assistant", "content": response})
                self._log.info("Direct query answered — provider=%s", provider)
                self.view.set_status("Done.")

            else:
                label = f"{task} complete." if task else "Done."
                self.view.set_status(label)
                self.view.append_log(f"[done]  {label}")

        elif mtype == "log":
            self.view.append_log(msg.get("text", ""))

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
        self.view.set_file_list([pathlib.Path(p).name for p in paths])
        self.view.set_index_info("Files loaded — click 'Build Index' to index.")
        self.view.set_status(
            f"{len(paths)} file(s) loaded. Click 'Build Index' to index."
        )
        self.view.append_log(
            f"[open]  {len(paths)} file(s): "
            + ", ".join(pathlib.Path(p).name for p in paths)
        )
        self._log.info("Loaded %d file(s)", len(paths))

    def on_build_index(self) -> None:
        """Chunk and embed all loaded documents in a background thread."""
        if not self.model.documents:
            self.view.set_status("No files loaded — use 'Open Text File…' first.")
            return

        chunk_size = int(self.model.settings.get("chunk_size",   800))
        overlap    = int(self.model.settings.get("chunk_overlap", 100))
        docs       = list(self.model.documents)  # snapshot; safe to read in worker

        loader_setting = self.model.settings.get("document_loader", "auto")
        use_kreuzberg  = loader_setting != "plain"

        # Snapshot settings so the worker thread sees a frozen copy.
        settings_snapshot = dict(self.model.settings)

        def _worker(post_msg: Any, cancel: CancelToken) -> dict[str, Any]:
            try:
                emb = create_embeddings(settings_snapshot)
            except (ValueError, ImportError) as exc:
                post_msg({"type": "log",
                          "text": f"[warn]  Embedding provider failed: {exc}; falling back to mock"})
                emb = MockEmbeddings(dimensions=_EMB_DIM)

            all_chunks:  list[dict[str, Any]] = []
            all_vectors: list[list[float]]    = []

            for doc_idx, path in enumerate(docs):
                if cancel.cancelled:
                    break

                source = pathlib.Path(path).name
                post_msg({"type": "status", "text": f"Reading {source}…"})

                try:
                    text = load_document(path, use_kreuzberg=use_kreuzberg)
                except OSError as exc:
                    post_msg({"type": "log",
                              "text": f"[warn]  Could not read {path}: {exc}"})
                    continue

                raw = _chunk_text(text, chunk_size, overlap)
                n   = len(raw)

                for i, chunk_text_str in enumerate(raw):
                    if cancel.cancelled:
                        break
                    all_chunks.append({
                        "id":        f"{source}::chunk{i}",
                        "text":      chunk_text_str,
                        "source":    source,
                        "chunk_idx": i,
                    })
                    all_vectors.append(emb.embed_query(chunk_text_str))

                    # Report progress as a fraction across all documents.
                    post_msg({
                        "type":    "progress",
                        "current": doc_idx * 1000 + i + 1,
                        "total":   len(docs) * 1000,
                    })
                    # Periodic log line (every 10 chunks + last)
                    if (i + 1) % 10 == 0 or i == n - 1:
                        post_msg({"type": "log",
                                  "text": f"  {source}: chunk {i+1}/{n} embedded"})

            graph, entity_to_chunks = build_knowledge_graph([c["text"] for c in all_chunks])
            return {
                "chunks": all_chunks,
                "embeddings": all_vectors,
                "knowledge_graph": graph,
                "entity_to_chunks": entity_to_chunks,
            }

        self.view.btn_build_index.configure(state="disabled")
        self.view.set_index_info("Indexing…")
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

        if not self.model.index_state.get("built"):
            self.view.append_chat(
                "⚠  No index built yet.\n"
                "   Open a text file and click 'Build Index' first, or switch to Direct mode.\n\n"
            )
            self.view.switch_view("chat")
            return

        # ── Retrieval (synchronous) ──────────────────────────────────────
        top_k = int(self.model.settings.get("top_k", 3))

        try:
            emb = create_embeddings(dict(self.model.settings))
        except (ValueError, ImportError):
            emb = MockEmbeddings(dimensions=_EMB_DIM)

        q_vec = emb.embed_query(prompt)
        scores = [_cosine(q_vec, cv) for cv in self.model.embeddings]

        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)

        kg_mode = str(self.model.settings.get("kg_query_mode", "hybrid") or "hybrid")
        graph = getattr(self.model, "knowledge_graph", None)
        graph_hits: list[int] = []
        entity_to_chunks = getattr(self.model, "entity_to_chunks", {})
        if graph is not None and entity_to_chunks:
            graph_hits = collect_graph_chunk_candidates(
                graph=graph,
                entity_to_chunks=entity_to_chunks,
                question=prompt,
                mode=kg_mode,
                limit=max(top_k * 3, top_k),
            )

        if kg_mode in {"naive", "bypass"} or not graph_hits:
            hits = ranked[:top_k]
        else:
            graph_hit_set = set(graph_hits)
            ordered = graph_hits + [i for i in ranked if i not in graph_hit_set]
            hits = ordered[:top_k]

        # ── Build context string ─────────────────────────────────────────
        context_parts: list[str] = []
        for rank, idx in enumerate(hits, 1):
            chunk = self.model.chunks[idx]
            snippet = chunk["text"].strip()
            context_parts.append(
                f"[{rank}] {chunk['source']} > chunk {chunk['chunk_idx']} "
                f"(score={scores[idx]:.3f}):\n{snippet}"
            )
        context_block = "\n\n".join(context_parts) if context_parts else "(no relevant passages found)"

        # Show the user's prompt immediately.
        sep = "─" * 52
        self.view.append_chat(f"You: {prompt}\n{sep}\n")
        self.view.switch_view("chat")

        # ── LLM synthesis (background thread) ────────────────────────────
        settings_snap = dict(self.model.settings)
        selected_mode = settings_snap.get("selected_mode", "Q&A")

        # Snapshot model-level data the worker will need.
        n_chunks = len(self.model.embeddings)
        top_score = scores[hits[0]] if hits else 0.0

        def _rag_worker(post_msg: Any, cancel: CancelToken) -> dict[str, str]:
            post_msg({"type": "status", "text": "Generating answer…"})
            try:
                llm = create_llm(settings_snap)
            except (ValueError, ImportError) as exc:
                return {
                    "response": (
                        f"Axiom [rag, mode={selected_mode}]: "
                        f"LLM unavailable ({exc}). Showing raw retrieval.\n\n"
                        f"CONTEXT:\n{context_block}\n"
                    ),
                    "prompt": prompt,
                }

            system_prompt = (
                f"You are Axiom, an AI assistant. Mode: {selected_mode}.\n"
                "Answer the user's question using ONLY the CONTEXT below. "
                "Cite passages as [1], [2], etc. If the context is insufficient, say so.\n\n"
                f"CONTEXT:\n{context_block}"
            )
            messages = [
                {"type": "system", "content": system_prompt},
                {"type": "human", "content": prompt},
            ]
            result = llm.invoke(messages)
            answer = str(getattr(result, "content", result) or "")
            return {"response": answer, "prompt": prompt}

        # Store retrieval metadata for _handle_message to use.
        self._pending_rag_meta = {
            "kg_mode": kg_mode,
            "selected_mode": selected_mode,
            "n_chunks": n_chunks,
            "top_score": top_score,
            "prompt": prompt,
        }
        self.start_task(_TASK_RAG_QUERY, _rag_worker)

    def _handle_direct_prompt(self, prompt: str) -> None:
        """Handle direct-chat prompts (no retrieval) via the provider factory.

        All providers — OpenAI, Anthropic, Google, xAI, LM Studio, local GGUF,
        and mock — are routed through ``create_llm(settings)``.  The LLM call
        runs in a background thread so the UI stays responsive.
        """
        provider_name = str(self.model.settings.get("llm_provider", "mock") or "mock").strip() or "mock"
        self.view.append_log(f"[direct] provider_selected provider={provider_name}")

        sep = "─" * 52
        self.view.append_chat(f"You: {prompt}\n{sep}\n")
        self.view.switch_view("chat")

        settings_snap = dict(self.model.settings)

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

        self.start_task(_TASK_DIRECT_QUERY, _direct_worker)

    def on_cancel_job(self) -> None:
        """Cancel any running background job."""
        self.cancel_current_task()

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

        self.view.set_status("Settings saved to settings.json.")
        self.view.populate_settings(coerced)
        self.view.refresh_llm_status_badge()
        self._log.info("Settings saved successfully (%d keys).", len(coerced))

        new_theme = coerced.get("theme", self.view._theme_name)
        if new_theme != self.view._theme_name:
            self.view.apply_theme(new_theme)
