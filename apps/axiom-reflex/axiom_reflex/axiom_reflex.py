"""Axiom Reflex Prototype — proof-of-concept web UI over the existing core.

Lists sessions from the repo-root SQLite store and executes direct queries
via the axiom_app engine without modifying any existing entrypoints.
"""

import os
import reflex as rx


class State(rx.State):
    sessions: list[dict] = []
    query: str = ""
    response: str = ""
    is_loading: bool = False

    def load_sessions(self):
        from axiom_app.services.session_repository import SessionRepository

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

    def run_query(self):
        from axiom_app.engine import DirectQueryRequest, query_direct

        if not self.query.strip():
            return

        self.is_loading = True
        self.response = ""
        yield

        settings = {
            "llm_provider": os.environ.get("AXIOM_LLM_PROVIDER", "anthropic"),
            "llm_model": os.environ.get("AXIOM_LLM_MODEL", "claude-haiku-4-5-20251001"),
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


def session_row(session: dict) -> rx.Component:
    return rx.box(
        rx.text(session["title"], weight="bold", size="2"),
        rx.text(session["updated"], color_scheme="gray", size="1"),
        padding="0.5em",
        border_bottom="1px solid #e2e8f0",
        width="100%",
    )


def index() -> rx.Component:
    return rx.vstack(
        rx.heading("Axiom Reflex Prototype", size="7", margin_bottom="0.5em"),
        rx.text(
            "Proof-of-concept: session listing + direct query against existing core.",
            color_scheme="gray",
            size="2",
            margin_bottom="1em",
        ),
        rx.hstack(
            # Left: session list
            rx.vstack(
                rx.heading("Sessions", size="4"),
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
            # Right: query interface
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
            align="start",
            spacing="4",
            width="100%",
        ),
        padding="2em",
        max_width="900px",
        margin="0 auto",
        on_mount=State.load_sessions,
    )


app = rx.App()
app.add_page(index, route="/")
