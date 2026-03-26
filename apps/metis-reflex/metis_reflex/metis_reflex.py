"""METIS Reflex Prototype — experimental web UI over the existing core.

Provides session management, direct and RAG queries, a document library with
index building, and a settings panel — all wired to the metis_app engine.
"""

import os

import reflex as rx


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class State(rx.State):
    # -- sessions --
    sessions: list[dict] = []
    new_session_title: str = ""

    # -- query --
    query: str = ""
    response: str = ""
    is_loading: bool = False

    # -- RAG --
    indexes: list[dict] = []
    selected_index: str = ""
    rag_question: str = ""
    rag_response: str = ""
    rag_loading: bool = False

    # -- settings --
    settings_llm_provider: str = ""
    settings_llm_model: str = ""
    settings_embedding_provider: str = ""
    settings_chunk_size: str = ""
    settings_retrieval_k: str = ""
    settings_status: str = ""

    # -- library --
    library_indexes: list[dict] = []
    build_doc_paths: str = ""
    build_index_id: str = ""
    build_status: str = ""
    build_loading: bool = False

    # -------------------------------------------------------------------
    # Sessions
    # -------------------------------------------------------------------

    def load_sessions(self):
        from metis_app.services.session_repository import SessionRepository

        repo = SessionRepository()
        repo.init_db()
        summaries = repo.list_sessions()
        self.sessions = [
            {
                "id": s.session_id,
                "title": s.title or "(untitled)",
                "updated": s.updated_at,
            }
            for s in summaries
        ]

    def create_session(self):
        from metis_app.services.session_repository import SessionRepository

        title = self.new_session_title.strip() or "New Chat"
        repo = SessionRepository()
        repo.init_db()
        repo.create_session(title=title)
        self.new_session_title = ""
        self.load_sessions()

    def delete_session(self, session_id: str):
        from metis_app.services.session_repository import SessionRepository

        repo = SessionRepository()
        repo.init_db()
        repo.delete_session(session_id)
        self.load_sessions()

    # -------------------------------------------------------------------
    # Direct query
    # -------------------------------------------------------------------

    def run_query(self):
        from metis_app.engine import DirectQueryRequest, query_direct

        if not self.query.strip():
            return

        self.is_loading = True
        self.response = ""
        yield

        settings = {
            "llm_provider": os.environ.get("METIS_LLM_PROVIDER", "anthropic"),
            "llm_model": os.environ.get("METIS_LLM_MODEL", "claude-haiku-4-5-20251001"),
            "api_key_anthropic": os.environ.get("ANTHROPIC_API_KEY", ""),
            "api_key_openai": os.environ.get("OPENAI_API_KEY", ""),
        }
        try:
            result = query_direct(
                DirectQueryRequest(prompt=self.query, settings=settings)
            )
            self.response = result.answer_text
        except Exception as exc:
            self.response = f"[error] {exc}"
        finally:
            self.is_loading = False

    # -------------------------------------------------------------------
    # RAG query
    # -------------------------------------------------------------------

    def load_indexes(self):
        from metis_app.engine.index_registry import list_indexes

        self.indexes = list_indexes()
        if self.indexes and not self.selected_index:
            self.selected_index = self.indexes[0].get("manifest_path", "")

    def set_selected_index(self, value: str):
        self.selected_index = value

    def run_rag_query(self):
        from metis_app.engine.querying import RagQueryRequest, query_rag

        if not self.rag_question.strip():
            return
        if not self.selected_index:
            self.rag_response = "[error] No index selected."
            return

        self.rag_loading = True
        self.rag_response = ""
        yield

        settings = {
            "llm_provider": os.environ.get("METIS_LLM_PROVIDER", "anthropic"),
            "llm_model": os.environ.get("METIS_LLM_MODEL", "claude-haiku-4-5-20251001"),
            "api_key_anthropic": os.environ.get("ANTHROPIC_API_KEY", ""),
            "api_key_openai": os.environ.get("OPENAI_API_KEY", ""),
        }
        try:
            result = query_rag(
                RagQueryRequest(
                    manifest_path=self.selected_index,
                    question=self.rag_question,
                    settings=settings,
                )
            )
            self.rag_response = result.answer_text
        except Exception as exc:
            self.rag_response = f"[error] {exc}"
        finally:
            self.rag_loading = False

    # -------------------------------------------------------------------
    # Settings
    # -------------------------------------------------------------------

    def load_settings(self):
        from metis_app.settings_store import load_settings

        s = load_settings()
        self.settings_llm_provider = str(s.get("llm_provider", ""))
        self.settings_llm_model = str(s.get("llm_model", ""))
        self.settings_embedding_provider = str(s.get("embedding_provider", ""))
        self.settings_chunk_size = str(s.get("chunk_size", ""))
        self.settings_retrieval_k = str(s.get("retrieval_k", ""))
        self.settings_status = ""

    def save_settings(self):
        from metis_app.settings_store import save_settings

        updates: dict = {}
        if self.settings_llm_provider.strip():
            updates["llm_provider"] = self.settings_llm_provider.strip()
        if self.settings_llm_model.strip():
            updates["llm_model"] = self.settings_llm_model.strip()
        if self.settings_embedding_provider.strip():
            updates["embedding_provider"] = self.settings_embedding_provider.strip()
        if self.settings_chunk_size.strip():
            try:
                updates["chunk_size"] = int(self.settings_chunk_size.strip())
            except ValueError:
                self.settings_status = "Invalid chunk_size (must be an integer)."
                return
        if self.settings_retrieval_k.strip():
            try:
                updates["retrieval_k"] = int(self.settings_retrieval_k.strip())
            except ValueError:
                self.settings_status = "Invalid retrieval_k (must be an integer)."
                return

        try:
            save_settings(updates)
            self.settings_status = "Settings saved."
        except Exception as exc:
            self.settings_status = f"[error] {exc}"

    # -------------------------------------------------------------------
    # Library
    # -------------------------------------------------------------------

    def load_library(self):
        from metis_app.engine.index_registry import list_indexes

        self.library_indexes = list_indexes()
        self.build_status = ""

    def build_index(self):
        from metis_app.engine.indexing import IndexBuildRequest, build_index

        paths = [p.strip() for p in self.build_doc_paths.split("\n") if p.strip()]
        if not paths:
            self.build_status = "Enter at least one document path."
            return

        self.build_loading = True
        self.build_status = "Building index…"
        yield

        settings = {
            "llm_provider": os.environ.get("METIS_LLM_PROVIDER", "anthropic"),
            "llm_model": os.environ.get("METIS_LLM_MODEL", "claude-haiku-4-5-20251001"),
            "embedding_provider": os.environ.get("METIS_EMBEDDING_PROVIDER", ""),
            "api_key_anthropic": os.environ.get("ANTHROPIC_API_KEY", ""),
            "api_key_openai": os.environ.get("OPENAI_API_KEY", ""),
        }
        try:
            result = build_index(
                IndexBuildRequest(
                    document_paths=paths,
                    settings=settings,
                    index_id=self.build_index_id.strip() or None,
                )
            )
            self.build_status = (
                f"Built index '{result.index_id}': "
                f"{result.document_count} docs, {result.chunk_count} chunks."
            )
            self.build_doc_paths = ""
            self.build_index_id = ""
            self.load_library()
        except Exception as exc:
            self.build_status = f"[error] {exc}"
        finally:
            self.build_loading = False


# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------

def session_row(session: dict) -> rx.Component:
    return rx.box(
        rx.hstack(
            rx.vstack(
                rx.text(session["title"], weight="bold", size="2"),
                rx.text(session["updated"], color_scheme="gray", size="1"),
                align="start",
                spacing="0",
                flex="1",
            ),
            rx.button(
                "Delete",
                size="1",
                color_scheme="red",
                variant="ghost",
                on_click=State.delete_session(session["id"]),
            ),
            width="100%",
            align="center",
        ),
        padding="0.5em",
        border_bottom="1px solid #e2e8f0",
        width="100%",
    )


def index_card(idx: dict) -> rx.Component:
    return rx.box(
        rx.text(idx["index_id"], weight="bold", size="2"),
        rx.text(
            f"{idx['document_count']} docs · {idx['chunk_count']} chunks · {idx['backend']}",
            color_scheme="gray",
            size="1",
        ),
        padding="0.75em",
        border="1px solid #e2e8f0",
        border_radius="6px",
        width="100%",
    )


def nav_bar() -> rx.Component:
    return rx.hstack(
        rx.link("Home", href="/", padding="0.5em"),
        rx.link("Library", href="/library", padding="0.5em"),
        rx.link("Settings", href="/settings", padding="0.5em"),
        border_bottom="1px solid #e2e8f0",
        padding="0.5em 2em",
        width="100%",
        spacing="4",
    )


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

def index() -> rx.Component:
    return rx.vstack(
        nav_bar(),
        rx.vstack(
            rx.heading("METIS Reflex", size="7", margin_bottom="0.5em"),
            rx.text(
                "Session management, direct queries, and RAG queries against the METIS engine.",
                color_scheme="gray",
                size="2",
                margin_bottom="1em",
            ),
            rx.hstack(
                # Left: session list
                rx.vstack(
                    rx.heading("Sessions", size="4"),
                    rx.hstack(
                        rx.input(
                            placeholder="New session title…",
                            value=State.new_session_title,
                            on_change=State.set_new_session_title,
                            flex="1",
                        ),
                        rx.button("Create", on_click=State.create_session, size="2"),
                        width="100%",
                    ),
                    rx.cond(
                        State.sessions.length() == 0,
                        rx.text("No sessions found.", color_scheme="gray", size="2"),
                        rx.scroll_area(
                            rx.vstack(
                                rx.foreach(State.sessions, session_row),
                                align="start",
                                spacing="0",
                                width="100%",
                            ),
                            height="400px",
                            width="100%",
                        ),
                    ),
                    align="start",
                    width="280px",
                    padding="1em",
                    border="1px solid #e2e8f0",
                    border_radius="8px",
                ),
                # Middle: direct query
                rx.vstack(
                    rx.heading("Direct Query", size="4"),
                    rx.text_area(
                        placeholder="Enter a prompt…",
                        value=State.query,
                        on_change=State.set_query,
                        width="100%",
                        min_height="120px",
                    ),
                    rx.button(
                        rx.cond(State.is_loading, "Running…", "Run Query"),
                        on_click=State.run_query,
                        loading=State.is_loading,
                        disabled=State.is_loading,
                        width="100%",
                    ),
                    rx.cond(
                        State.response != "",
                        rx.box(
                            rx.text(State.response, white_space="pre-wrap", size="2"),
                            padding="1em",
                            border="1px solid #e2e8f0",
                            border_radius="8px",
                            background="#f8fafc",
                            width="100%",
                            max_height="300px",
                            overflow_y="auto",
                        ),
                    ),
                    align="start",
                    flex="1",
                    padding="1em",
                    border="1px solid #e2e8f0",
                    border_radius="8px",
                ),
                # Right: RAG query
                rx.vstack(
                    rx.heading("RAG Query", size="4"),
                    rx.select(
                        [idx["manifest_path"] for idx in State.indexes],
                        placeholder="Select an index…",
                        value=State.selected_index,
                        on_change=State.set_selected_index,
                        width="100%",
                    ),
                    rx.text_area(
                        placeholder="Ask a question about your documents…",
                        value=State.rag_question,
                        on_change=State.set_rag_question,
                        width="100%",
                        min_height="100px",
                    ),
                    rx.button(
                        rx.cond(State.rag_loading, "Querying…", "Run RAG Query"),
                        on_click=State.run_rag_query,
                        loading=State.rag_loading,
                        disabled=State.rag_loading,
                        width="100%",
                    ),
                    rx.cond(
                        State.rag_response != "",
                        rx.box(
                            rx.text(State.rag_response, white_space="pre-wrap", size="2"),
                            padding="1em",
                            border="1px solid #e2e8f0",
                            border_radius="8px",
                            background="#f8fafc",
                            width="100%",
                            max_height="300px",
                            overflow_y="auto",
                        ),
                    ),
                    align="start",
                    flex="1",
                    padding="1em",
                    border="1px solid #e2e8f0",
                    border_radius="8px",
                ),
                align="start",
                spacing="4",
                width="100%",
            ),
            padding="2em",
            max_width="1200px",
            margin="0 auto",
            on_mount=[State.load_sessions, State.load_indexes],
        ),
        spacing="0",
        width="100%",
    )


@rx.page(route="/settings", on_load=State.load_settings)
def settings_page() -> rx.Component:
    return rx.vstack(
        nav_bar(),
        rx.vstack(
            rx.heading("Settings", size="7", margin_bottom="0.5em"),
            rx.text(
                "View and update METIS engine settings.",
                color_scheme="gray",
                size="2",
                margin_bottom="1em",
            ),
            rx.vstack(
                rx.text("LLM Provider", weight="bold", size="2"),
                rx.input(
                    value=State.settings_llm_provider,
                    on_change=State.set_settings_llm_provider,
                    placeholder="e.g. anthropic, openai",
                    width="100%",
                ),
                rx.text("LLM Model", weight="bold", size="2"),
                rx.input(
                    value=State.settings_llm_model,
                    on_change=State.set_settings_llm_model,
                    placeholder="e.g. claude-haiku-4-5-20251001",
                    width="100%",
                ),
                rx.text("Embedding Provider", weight="bold", size="2"),
                rx.input(
                    value=State.settings_embedding_provider,
                    on_change=State.set_settings_embedding_provider,
                    placeholder="e.g. openai, local",
                    width="100%",
                ),
                rx.text("Chunk Size", weight="bold", size="2"),
                rx.input(
                    value=State.settings_chunk_size,
                    on_change=State.set_settings_chunk_size,
                    placeholder="e.g. 512",
                    width="100%",
                ),
                rx.text("Retrieval K", weight="bold", size="2"),
                rx.input(
                    value=State.settings_retrieval_k,
                    on_change=State.set_settings_retrieval_k,
                    placeholder="e.g. 10",
                    width="100%",
                ),
                rx.button(
                    "Save Settings",
                    on_click=State.save_settings,
                    width="100%",
                    margin_top="0.5em",
                ),
                rx.cond(
                    State.settings_status != "",
                    rx.text(State.settings_status, size="2", color_scheme="gray"),
                ),
                spacing="2",
                max_width="480px",
                width="100%",
                padding="1em",
                border="1px solid #e2e8f0",
                border_radius="8px",
            ),
            padding="2em",
            max_width="700px",
            margin="0 auto",
        ),
        spacing="0",
        width="100%",
    )


@rx.page(route="/library", on_load=State.load_library)
def library_page() -> rx.Component:
    return rx.vstack(
        nav_bar(),
        rx.vstack(
            rx.heading("Library", size="7", margin_bottom="0.5em"),
            rx.text(
                "Browse existing indexes and build new ones.",
                color_scheme="gray",
                size="2",
                margin_bottom="1em",
            ),
            # Build new index
            rx.vstack(
                rx.heading("Build Index", size="4"),
                rx.text("Document paths (one per line)", size="2", color_scheme="gray"),
                rx.text_area(
                    placeholder="/path/to/doc1.pdf\n/path/to/doc2.txt",
                    value=State.build_doc_paths,
                    on_change=State.set_build_doc_paths,
                    width="100%",
                    min_height="100px",
                ),
                rx.input(
                    placeholder="Index ID (optional)",
                    value=State.build_index_id,
                    on_change=State.set_build_index_id,
                    width="100%",
                ),
                rx.button(
                    rx.cond(State.build_loading, "Building…", "Build Index"),
                    on_click=State.build_index,
                    loading=State.build_loading,
                    disabled=State.build_loading,
                    width="100%",
                ),
                rx.cond(
                    State.build_status != "",
                    rx.text(State.build_status, size="2", color_scheme="gray"),
                ),
                padding="1em",
                border="1px solid #e2e8f0",
                border_radius="8px",
                width="100%",
                max_width="600px",
                spacing="2",
            ),
            # Existing indexes
            rx.vstack(
                rx.heading("Indexes", size="4", margin_top="1em"),
                rx.cond(
                    State.library_indexes.length() == 0,
                    rx.text("No indexes found.", color_scheme="gray", size="2"),
                    rx.vstack(
                        rx.foreach(State.library_indexes, index_card),
                        spacing="2",
                        width="100%",
                    ),
                ),
                width="100%",
                max_width="600px",
                align="start",
            ),
            padding="2em",
            max_width="900px",
            margin="0 auto",
        ),
        spacing="0",
        width="100%",
    )


app = rx.App()
app.add_page(index, route="/")
