import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox, simpledialog
import threading
import logging
import os
import sys
import time
import json
import subprocess
import importlib.util
import re
import hashlib
import sqlite3
import uuid
import html
import webbrowser
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

APP_NAME = "Agentic RAG"
APP_VERSION = "1.0"
APP_SUBTITLE = "LangChain + Chroma/Weaviate + Cohere"

try:
    import langextract
except ImportError:
    langextract = None
    logger.info("optional dependency not installed: langextract")

try:
    import agent_lightning
except ImportError:
    agent_lightning = None
    logger.info("optional dependency not installed: agent_lightning")

# --- Libraries check is done inside the class to prevent instant crash ---
# Required: pip install langchain langchain-community langchain-openai langchain-anthropic langchain-google-genai langchain-cohere langchain-text-splitters chromadb beautifulsoup4 tiktoken

RAW_COLLECTION_NAME = "rag_collection"
DIGEST_COLLECTION_NAME = "rag_digest_collection"
CONCEPT_COLLECTION_NAME = "rag_concept_cards"
DIGEST_WINDOW_MIN = 10
DIGEST_WINDOW_MAX = 20
DIGEST_WINDOW_TARGET = 15
MINI_DIGEST_BOOST_MULTIPLIER = 3
MINI_DIGEST_MIN_POOL = 40
MAX_DIGEST_NODES = 60
MAX_RAW_CHUNKS = 200
MAX_HIERARCHICAL_RECURSION_ITERATIONS = 3
HIERARCHICAL_COVERAGE_MIN_SCORE = 0.55
MAX_PACKED_CONTEXT_CHARS = 60000
TOKENS_TO_CHARS_RATIO = 4
CONTEXT_SAFETY_MARGIN_TOKENS = 512
MAX_GROUP_DOCS = 2
MIN_UNIQUE_INCIDENTS = 8
MAX_UNIQUE_INCIDENTS = 12
AGENTIC_MAX_ITERATIONS_HARD_CAP = 12
MONTH_INDEX_TO_LABEL = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}
MONTH_NAME_TO_INDEX = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


@dataclass
class EvidenceRef:
    source_id: str
    quote: str = ""
    span_start: Optional[int] = None
    span_end: Optional[int] = None
    chunk_id: str = ""


@dataclass
class Incident:
    incident_id: str
    date_start: Optional[str]
    date_end: Optional[str]
    month_bucket: str
    people: list[str] = field(default_factory=list)
    channel: str = "unknown"
    what_happened: str = ""
    impact: str = ""
    operational_impact: str = ""
    personal_impact: str = ""
    evidence_refs: list[EvidenceRef] = field(default_factory=list)


@dataclass
class SourceLocator:
    source_id: str
    label: str
    anchor: str
    metadata: dict


@dataclass
class AgentProfile:
    name: str
    system_instructions: str = ""
    style_template: str = ""
    citation_policy: str = ""
    retrieval_strategy: dict = field(default_factory=dict)
    iteration_strategy: dict = field(default_factory=dict)
    comprehension_pipeline_on_ingest: Optional[dict] = None


@dataclass
class TraceEvent:
    run_id: str
    event_id: str
    stage: str
    event_type: str
    timestamp: str
    iteration: int = 0
    latency_ms: Optional[int] = None
    prompt: Optional[dict[str, Any]] = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    retrieval_results: Optional[dict[str, Any]] = None
    citations_chosen: list[str] = field(default_factory=list)
    validator: Optional[dict[str, Any]] = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class TraceStore:
    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        self.runs_dir = os.path.join(base_dir, "runs")
        self.runs_jsonl = os.path.join(base_dir, "runs.jsonl")
        os.makedirs(self.runs_dir, exist_ok=True)

    def append(self, record: dict[str, Any]) -> None:
        if not isinstance(record, dict):
            return
        run_id = str(record.get("run_id") or "unknown")
        run_path = os.path.join(self.runs_dir, f"{run_id}.jsonl")
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        for path in (self.runs_jsonl, run_path):
            try:
                with open(path, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
            except OSError:
                continue

    def read_run(self, run_id: str) -> list[dict[str, Any]]:
        path = os.path.join(self.runs_dir, f"{run_id}.jsonl")
        if not run_id or not os.path.exists(path):
            return []
        events = []
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return events


class CitationManager:
    def __init__(self):
        self._label_by_source = {}
        self._source_by_label = {}

    def register(self, source_id: str) -> str:
        if source_id not in self._label_by_source:
            label = f"S{len(self._label_by_source) + 1}"
            self._label_by_source[source_id] = label
            self._source_by_label[label] = source_id
        return self._label_by_source[source_id]

    def label_for(self, source_id: str) -> str:
        return self._label_by_source.get(source_id, "")

    def source_for(self, label: str) -> str:
        return self._source_by_label.get(label, "")

    def as_dict(self) -> dict:
        return dict(self._label_by_source)



class CollapsibleFrame(ttk.Frame):
    def __init__(self, parent, title, expanded=False, **kwargs):
        super().__init__(parent, **kwargs)
        self._expanded = tk.BooleanVar(value=expanded)
        header = ttk.Frame(self)
        header.pack(fill="x")
        self.btn = ttk.Button(header, text="▾" if expanded else "▸", width=2, command=self.toggle)
        self.btn.pack(side="left")
        ttk.Label(header, text=title, style="Bold.TLabel").pack(side="left", padx=(4, 0))
        self.content = ttk.Frame(self)
        if expanded:
            self.content.pack(fill="x", pady=(6, 0))

    def set_expanded(self, expanded):
        expanded = bool(expanded)
        if expanded != bool(self._expanded.get()):
            self.toggle()

    def toggle(self):
        if self._expanded.get():
            self.content.pack_forget()
            self.btn.config(text="▸")
            self._expanded.set(False)
        else:
            self.content.pack(fill="x", pady=(6, 0))
            self.btn.config(text="▾")
            self._expanded.set(True)


class AgenticRAGApp:
    def __init__(self, root):
        self.root = root
        self.root.title(
            f"{APP_NAME} — {APP_SUBTITLE}" if APP_SUBTITLE else APP_NAME
        )
        self.load_icon()
        self.root.geometry("1200x900")
        self.main_thread = threading.current_thread()
        self.config_path = os.path.join(os.getcwd(), "agentic_rag_config.json")
        self.telemetry_log_filename = "agentic_rag_runs.jsonl"
        self._active_run_id = None
        self._startup_started_at = time.perf_counter()
        self._startup_pipeline_finished = False
        self._index_scan_in_progress = False
        self._pending_selected_index_label = None
        self._langchain_core_cache = None
        self.default_system_instructions = (
            "You are an expert analyst assistant. Use ONLY the provided context for factual claims. "
            "Never ask for details already present in the retrieved context. "
            "Omit unsupported claims; deepen supported ones; do not ask for more docs or missing info; "
            "do not use placeholders. If evidence is thin, you may add one short 'Scope:' note at the "
            "top describing limitations. Every paragraph with factual content must end with one or more "
            "[S#] citations. Use the exact [S#] format only; do not use alternative formats "
            "(e.g., (1), [1], or inline URLs). Example: \"The policy was revised in 2023.\" [S1] "
            "For Script / talk track and Structured report styles, include at least one short verbatim "
            "quote (<=25 words) per major section with an [S#] citation. "
            "Coverage rule: if N items are requested, output N items, omitting unsupported claims."
        )
        self.verbose_system_instructions = (
            "You are an expert analyst assistant. Use ONLY the provided context for factual claims. "
            "Never ask for details already present in the retrieved context. "
            "Omit unsupported claims; deepen supported ones; do not ask the user for missing info; "
            "do not use placeholders. Every paragraph with factual content must end with one or more "
            "[S#] citations. Use the exact [S#] format only; do not use alternative formats "
            "(e.g., (1), [1], or inline URLs). Example: \"The policy was revised in 2023.\" [S1] "
            "For Script / talk track and Structured report styles, include at least one short verbatim "
            "quote (<=25 words) per major section with an [S#] citation. "
            "Provide a concise summary, cite evidence from the context, list key points, "
            "and explicitly note uncertainties or gaps."
        )

        # --- State Variables ---
        self.api_keys = {
            "openai": tk.StringVar(),
            "anthropic": tk.StringVar(),
            "google": tk.StringVar(),
            "cohere": tk.StringVar(),
            "weaviate_url": tk.StringVar(value="http://localhost:8080"),
            "weaviate_key": tk.StringVar(),
            "mistral": tk.StringVar(),
            "groq": tk.StringVar(),
            "azure_openai": tk.StringVar(),
            "together": tk.StringVar(),
            "voyage": tk.StringVar(),
            "huggingface": tk.StringVar(),
            "fireworks": tk.StringVar(),
            "perplexity": tk.StringVar(),
        }

        self.llm_provider = tk.StringVar(value="anthropic")
        self.embedding_provider = tk.StringVar(value="voyage")
        self.vector_db_type = tk.StringVar(value="chroma")
        self.local_llm_url = tk.StringVar(value="http://localhost:1234/v1")
        self.chunk_size = tk.IntVar(value=1000)
        self.chunk_overlap = tk.IntVar(value=200)
        self.build_digest_index = tk.BooleanVar(value=True)
        self.build_comprehension_index = tk.BooleanVar(value=False)
        self.comprehension_extraction_depth = tk.StringVar(value="Standard")
        self.prefer_comprehension_index = tk.BooleanVar(value=True)

        self.llm_model = tk.StringVar(value="claude-opus-4-6")
        self.llm_model_custom = tk.StringVar()
        self.embedding_model = tk.StringVar(value="voyage-4-large")
        self.embedding_model_custom = tk.StringVar()
        self.llm_temperature = tk.DoubleVar(value=0.0)
        self.llm_max_tokens = tk.IntVar(value=1024)
        self.force_embedding_compat = tk.BooleanVar(value=False)
        self.verbose_mode = tk.BooleanVar(value=False)
        self.system_instructions = tk.StringVar(
            value=self.default_system_instructions
        )
        self.output_style_options = [
            "Default answer",
            "Detailed answer",
            "Brief / exec summary",
            "Script / talk track",
            "Structured report",
            "Blinkist-style summary",
        ]
        self.output_style = tk.StringVar(value="Default answer")
        self.mode_options = [
            "Standard RAG Q&A",
            "Book Tutor",
            "Blinkist-style Summary",
            "Research Analyst",
            "Evidence Pack",
        ]
        self.selected_mode = tk.StringVar(value="Standard RAG Q&A")
        self.profiles_dir = os.path.join(os.getcwd(), "profiles")
        self.builtin_profiles = self._get_builtin_profiles()
        self.selected_profile = tk.StringVar(value="Built-in: Default")
        self.profile_options = []
        self.retrieval_k = tk.IntVar(value=25)
        self.final_k = tk.IntVar(value=5)
        self.fallback_final_k = tk.IntVar(value=self.final_k.get())
        self.search_type = tk.StringVar(value="similarity")
        self.retrieval_mode_options = [
            "Flat (Chunks)",
            "Hierarchical (Digest→Chunk)",
        ]
        self.retrieval_mode = tk.StringVar(value="Flat (Chunks)")
        self.mmr_lambda = tk.DoubleVar(value=0.5)
        self.agentic_mode = tk.BooleanVar(value=False)
        self.agentic_max_iterations = tk.IntVar(value=2)
        self.show_retrieved_context = tk.BooleanVar(value=False)
        self.use_reranker = tk.BooleanVar(value=True)
        self.use_sub_queries = tk.BooleanVar(value=True)
        self.subquery_max_docs = tk.IntVar(value=200)
        self.enable_langextract = tk.BooleanVar(value=False)
        self.enable_structured_incidents = tk.BooleanVar(value=False)
        self.enable_recursive_memory = tk.BooleanVar(value=False)
        self.enable_recursive_retrieval = tk.BooleanVar(value=False)
        self.enable_citation_v2 = tk.BooleanVar(value=True)
        self.enable_claim_level_grounding_citefix_lite = tk.BooleanVar(value=False)
        self.agent_lightning_enabled = tk.BooleanVar(value=False)
        self.enable_agent_lightning_telemetry = self.agent_lightning_enabled
        self._frontier_evidence_pack_mode = False
        self._last_evidence_pack_synthesis_cards = []
        self._trace_events = []
        self._agent_lightning_runs_by_id = {}
        self._agent_lightning_last_exportable_run = None
        self._agent_lightning_trace_events_by_run = {}
        self._agent_lightning_run_summaries = []
        self._latest_source_map = {}
        self._latest_blinkist_plan = {}
        self._latest_incidents = []
        self._latest_grounding_html_path = ""
        self._source_id_by_tree_iid = {}

        self.vector_store = None
        self.index_embedding_signature = ""
        self.chat_history = []
        self.chat_history_max_turns = 6
        self.selected_file = None
        self.last_answer = ""
        self.dependency_prompted = False
        self.existing_index_var = tk.StringVar(value="(default)")
        self.existing_index_paths = {}
        self.selected_index_path = None
        self.selected_collection_name = RAW_COLLECTION_NAME
        self.lexical_db_path = None
        self.lexical_db_available = False
        self.session_db_path = os.path.join(os.getcwd(), "rag_sessions.db")
        self.trace_store = TraceStore(os.path.join(os.getcwd(), "trace_store"))
        self.current_session_id = None
        self.session_title_llm_enabled = tk.BooleanVar(value=False)
        self._session_list_items = []
        self._assistant_message_counter = 0

        self._init_sessions_db()

        self.setup_ui()
        self.start_new_chat(load_in_ui=False)
        self.refresh_sessions_list()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._schedule_startup_pipeline()

    def _now_iso(self):
        return datetime.now(timezone.utc).isoformat()

    def _init_sessions_db(self):
        with sqlite3.connect(self.session_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS sessions(
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT,
                    updated_at TEXT,
                    title TEXT,
                    summary TEXT,
                    active_profile TEXT,
                    mode TEXT,
                    index_id TEXT,
                    vector_backend TEXT,
                    llm_provider TEXT,
                    llm_model TEXT,
                    embed_model TEXT,
                    retrieve_k INT,
                    final_k INT,
                    mmr_lambda REAL,
                    agentic_iterations INT,
                    extra_json TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages(
                    message_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    ts TEXT,
                    role TEXT,
                    content TEXT,
                    run_id TEXT,
                    sources_json TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_session_ts ON messages(session_id, ts)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS message_feedback(
                    feedback_id TEXT PRIMARY KEY,
                    session_id TEXT,
                    run_id TEXT,
                    vote INTEGER,
                    note TEXT,
                    ts TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_feedback_session ON message_feedback(session_id, ts)"
            )

    def _collect_session_extra_json(self):
        payload = {
            "selected_index_path": self.selected_index_path,
            "selected_collection_name": self.selected_collection_name,
            "output_style": self.output_style.get(),
            "session_title_llm_enabled": bool(self.session_title_llm_enabled.get()),
            "llm_temperature": float(self.llm_temperature.get()),
            "llm_max_tokens": int(self.llm_max_tokens.get()),
            "embedding_provider": self.embedding_provider.get(),
            "embedding_model_custom": self.embedding_model_custom.get(),
            "llm_model_custom": self.llm_model_custom.get(),
            "search_type": self.search_type.get(),
            "retrieval_mode": self.retrieval_mode.get(),
            "agentic_mode": bool(self.agentic_mode.get()),
            "use_reranker": bool(self.use_reranker.get()),
            "use_sub_queries": bool(self.use_sub_queries.get()),
            "subquery_max_docs": int(self.subquery_max_docs.get()),
        }
        return json.dumps(payload, ensure_ascii=False)

    def _upsert_session_row(self, *, session_id, title=None, summary=None):
        ts = self._now_iso()
        resolved_title = title or "New Chat"
        with sqlite3.connect(self.session_db_path) as conn:
            existing = conn.execute(
                "SELECT session_id FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE sessions
                    SET updated_at = ?,
                        title = COALESCE(?, title),
                        summary = COALESCE(?, summary),
                        active_profile = ?,
                        mode = ?,
                        index_id = ?,
                        vector_backend = ?,
                        llm_provider = ?,
                        llm_model = ?,
                        embed_model = ?,
                        retrieve_k = ?,
                        final_k = ?,
                        mmr_lambda = ?,
                        agentic_iterations = ?,
                        extra_json = ?
                    WHERE session_id = ?
                    """,
                    (
                        ts,
                        title,
                        summary,
                        self.selected_profile.get(),
                        self.selected_mode.get(),
                        self._format_index_label(
                            self.selected_index_path, self.selected_collection_name
                        )
                        if self.selected_index_path
                        else "(default)",
                        self.vector_db_type.get(),
                        self.llm_provider.get(),
                        self._resolve_llm_model(),
                        self._resolve_embedding_model(),
                        int(self.retrieval_k.get()),
                        int(self.final_k.get()),
                        float(self.mmr_lambda.get()),
                        int(self.agentic_max_iterations.get()),
                        self._collect_session_extra_json(),
                        session_id,
                    ),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO sessions(
                        session_id, created_at, updated_at, title, summary,
                        active_profile, mode, index_id, vector_backend,
                        llm_provider, llm_model, embed_model,
                        retrieve_k, final_k, mmr_lambda, agentic_iterations, extra_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        session_id,
                        ts,
                        ts,
                        resolved_title,
                        summary,
                        self.selected_profile.get(),
                        self.selected_mode.get(),
                        self._format_index_label(
                            self.selected_index_path, self.selected_collection_name
                        )
                        if self.selected_index_path
                        else "(default)",
                        self.vector_db_type.get(),
                        self.llm_provider.get(),
                        self._resolve_llm_model(),
                        self._resolve_embedding_model(),
                        int(self.retrieval_k.get()),
                        int(self.final_k.get()),
                        float(self.mmr_lambda.get()),
                        int(self.agentic_max_iterations.get()),
                        self._collect_session_extra_json(),
                    ),
                )

    def _insert_session_message(self, *, role, content, run_id=None, sources_json=None):
        if not self.current_session_id:
            return
        self._upsert_session_row(session_id=self.current_session_id)
        with sqlite3.connect(self.session_db_path) as conn:
            conn.execute(
                """
                INSERT INTO messages(message_id, session_id, ts, role, content, run_id, sources_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    self.current_session_id,
                    self._now_iso(),
                    role,
                    content,
                    run_id,
                    sources_json,
                ),
            )

    def _record_trace_stage(self, run_id, stage, event_type, payload=None, iteration=0):
        if not run_id:
            return
        event = {
            "timestamp": self._now_iso(),
            "session_id": self.current_session_id,
            "run_id": run_id,
            "iteration": int(iteration or 0),
            "stage": str(stage),
            "event_type": str(event_type),
            "payload": payload or {},
        }
        self.trace_store.append(event)

    @staticmethod
    def _source_locators_from_docs(documents, max_items=20):
        locators = []
        for doc in (documents or [])[:max_items]:
            metadata = getattr(doc, "metadata", {}) or {}
            source = str(metadata.get("source") or metadata.get("file_path") or metadata.get("filename") or "unknown")
            locator = {
                "source_id": str(metadata.get("chunk_id") or metadata.get("id") or hashlib.md5(source.encode("utf-8", errors="ignore")).hexdigest()[:12]),
                "label": source,
                "anchor": str(metadata.get("char_range") or metadata.get("char_start") or metadata.get("section_title") or ""),
                "metadata": {
                    "score": metadata.get("relevance_score"),
                    "month_bucket": metadata.get("month_bucket"),
                    "channel": metadata.get("channel_type"),
                    "role": metadata.get("role_kind"),
                },
            }
            locators.append(locator)
        return locators

    def _record_feedback(self, run_id, vote, note):
        if not self.current_session_id:
            return
        with sqlite3.connect(self.session_db_path) as conn:
            conn.execute(
                """
                INSERT INTO message_feedback(feedback_id, session_id, run_id, vote, note, ts)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), self.current_session_id, run_id, int(vote), str(note or ""), self._now_iso()),
            )
        self._record_trace_stage(
            run_id,
            "feedback",
            "user_feedback",
            payload={"vote": int(vote), "note": str(note or "")},
        )

    def _submit_feedback(self, run_id, vote):
        vote_icon = "👍" if int(vote) > 0 else "👎"
        note = simpledialog.askstring(
            "Message Feedback",
            f"{vote_icon} feedback noted. Optional comment:",
            parent=self.root,
        )
        self._record_feedback(run_id=run_id, vote=vote, note=note or "")
        self.log(f"Saved feedback for run {run_id}: vote={vote_icon}")

    def start_new_chat(self, load_in_ui=True):
        self.current_session_id = str(uuid.uuid4())
        self._upsert_session_row(session_id=self.current_session_id, title="New Chat")
        if load_in_ui:
            self.clear_chat()
            self.append_chat("system", "Started a new chat session.")
        self.refresh_sessions_list()

    def refresh_sessions_list(self):
        if not hasattr(self, "sessions_tree"):
            return
        search_query = ""
        if hasattr(self, "history_search_var"):
            search_query = (self.history_search_var.get() or "").strip().lower()
        with sqlite3.connect(self.session_db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT session_id, updated_at, title, summary, active_profile, mode, index_id, llm_model
                FROM sessions
                ORDER BY updated_at DESC
                LIMIT 500
                """
            ).fetchall()
        self._session_list_items = []
        for row in rows:
            item = dict(row)
            haystack = f"{item.get('title', '')} {item.get('summary', '')}".lower()
            if search_query and search_query not in haystack:
                continue
            self._session_list_items.append(item)

        self.sessions_tree.delete(*self.sessions_tree.get_children())
        for row in self._session_list_items:
            title = (row["title"] or "Untitled").strip() or "Untitled"
            updated = (row["updated_at"] or "")[:19].replace("T", " ")
            iid = row["session_id"]
            self.sessions_tree.insert(
                "",
                tk.END,
                iid=iid,
                values=(
                    title,
                    updated,
                    row.get("active_profile") or "-",
                    row.get("mode") or "-",
                    row.get("index_id") or "(default)",
                    row.get("llm_model") or "-",
                ),
            )
        self._refresh_history_details()

    def _on_history_search_change(self, _event=None):
        self.refresh_sessions_list()

    def _session_row_by_id(self, session_id):
        for row in self._session_list_items:
            if row.get("session_id") == session_id:
                return row
        return None

    def _fetch_session_and_messages(self, session_id):
        with sqlite3.connect(self.session_db_path) as conn:
            conn.row_factory = sqlite3.Row
            session = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            ).fetchone()
            messages = conn.execute(
                """
                SELECT role, content, ts, run_id, sources_json
                FROM messages
                WHERE session_id = ?
                ORDER BY ts ASC
                """,
                (session_id,),
            ).fetchall()
        return session, messages

    def _fetch_feedback_for_session(self, session_id):
        with sqlite3.connect(self.session_db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(
                """
                SELECT feedback_id, session_id, run_id, vote, note, ts
                FROM message_feedback
                WHERE session_id = ?
                ORDER BY ts ASC
                """,
                (session_id,),
            ).fetchall()

    def _selected_history_session_id(self):
        if not hasattr(self, "sessions_tree"):
            return None
        selected = self.sessions_tree.selection()
        if not selected:
            return None
        return selected[0]

    def _restore_session_state(self, session):
        self.selected_profile.set(session["active_profile"] or self.selected_profile.get())
        self.selected_mode.set(session["mode"] or self.selected_mode.get())
        self.llm_provider.set(session["llm_provider"] or self.llm_provider.get())
        self.llm_model.set(session["llm_model"] or self.llm_model.get())
        self.embedding_model.set(session["embed_model"] or self.embedding_model.get())
        if session["retrieve_k"]:
            self.retrieval_k.set(int(session["retrieve_k"]))
        if session["final_k"]:
            self.final_k.set(int(session["final_k"]))
        if session["mmr_lambda"] is not None:
            self.mmr_lambda.set(float(session["mmr_lambda"]))
        if session["agentic_iterations"]:
            self.agentic_max_iterations.set(int(session["agentic_iterations"]))

        extra = {}
        try:
            extra = json.loads(session["extra_json"] or "{}")
        except json.JSONDecodeError:
            extra = {}

        self.output_style.set(extra.get("output_style", self.output_style.get()))
        self.llm_temperature.set(float(extra.get("llm_temperature", self.llm_temperature.get())))
        self.llm_max_tokens.set(int(extra.get("llm_max_tokens", self.llm_max_tokens.get())))
        self.embedding_provider.set(extra.get("embedding_provider", self.embedding_provider.get()))
        self.llm_model_custom.set(extra.get("llm_model_custom", self.llm_model_custom.get()))
        self.embedding_model_custom.set(
            extra.get("embedding_model_custom", self.embedding_model_custom.get())
        )
        self.search_type.set(extra.get("search_type", self.search_type.get()))
        self.retrieval_mode.set(extra.get("retrieval_mode", self.retrieval_mode.get()))
        self.agentic_mode.set(bool(extra.get("agentic_mode", self.agentic_mode.get())))
        self.use_reranker.set(bool(extra.get("use_reranker", self.use_reranker.get())))
        self.use_sub_queries.set(bool(extra.get("use_sub_queries", self.use_sub_queries.get())))
        try:
            if extra.get("subquery_max_docs") is not None:
                self.subquery_max_docs.set(int(extra.get("subquery_max_docs")))
        except (TypeError, ValueError):
            pass
        self.session_title_llm_enabled.set(
            bool(extra.get("session_title_llm_enabled", self.session_title_llm_enabled.get()))
        )

        previous_index = (self.selected_index_path, self.selected_collection_name)
        self.selected_index_path = extra.get("selected_index_path", self.selected_index_path)
        self.selected_collection_name = extra.get(
            "selected_collection_name", self.selected_collection_name
        )
        new_index = (self.selected_index_path, self.selected_collection_name)
        if self.selected_index_path:
            self._pending_selected_index_label = self._format_index_label(
                self.selected_index_path,
                self.selected_collection_name,
            )

        self._refresh_profile_options()
        self._sync_model_options()
        if new_index != previous_index:
            self._refresh_existing_indexes_async(reason="Loading indexes…")

    def load_selected_session(self):
        session_id = self._selected_history_session_id()
        if not session_id:
            messagebox.showinfo("No Session", "Select a session to load.")
            return
        session, messages = self._fetch_session_and_messages(session_id)
        if not session:
            return
        self.current_session_id = session_id
        self.clear_chat()
        self.chat_history = []
        for row in messages:
            role = (row["role"] or "").strip().lower()
            content = row["content"] or ""
            if role == "user":
                self.append_chat("user", f"You: {content}")
                self._append_history(self._human_message(content=content))
            elif role == "assistant":
                self.append_chat("agent", f"AI: {content}", run_id=row["run_id"])
                self._append_history(self._ai_message(content=content))
                self.last_answer = content
            elif role == "system":
                self.append_chat("system", content)
            elif role == "source":
                self.append_chat("source", content)
        self._restore_session_state(session)
        self.append_chat("system", f"Loaded session: {session['title'] or session_id}")
        self.notebook.select(self.tab_chat)

    def rename_selected_session(self):
        session_id = self._selected_history_session_id()
        if not session_id:
            messagebox.showinfo("No Session", "Select a session to rename.")
            return
        row = self._session_row_by_id(session_id) or {}
        current_title = (row.get("title") or "Untitled").strip() or "Untitled"
        new_title = simpledialog.askstring(
            "Rename Session",
            "New session title:",
            initialvalue=current_title,
            parent=self.root,
        )
        if new_title is None:
            return
        new_title = new_title.strip()
        if not new_title:
            messagebox.showwarning("Invalid Title", "Session title cannot be empty.")
            return
        with sqlite3.connect(self.session_db_path) as conn:
            conn.execute(
                "UPDATE sessions SET title = ?, updated_at = ? WHERE session_id = ?",
                (new_title, self._now_iso(), session_id),
            )
        self.refresh_sessions_list()

    def duplicate_selected_session(self):
        session_id = self._selected_history_session_id()
        if not session_id:
            messagebox.showinfo("No Session", "Select a session to duplicate.")
            return
        session, _messages = self._fetch_session_and_messages(session_id)
        if not session:
            return

        new_session_id = str(uuid.uuid4())
        title = (session["title"] or "Untitled").strip() or "Untitled"
        clone_title = f"Copy of {title}"
        ts = self._now_iso()
        with sqlite3.connect(self.session_db_path) as conn:
            conn.execute(
                """
                INSERT INTO sessions(
                    session_id, created_at, updated_at, title, summary,
                    active_profile, mode, index_id, vector_backend,
                    llm_provider, llm_model, embed_model,
                    retrieve_k, final_k, mmr_lambda, agentic_iterations, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new_session_id,
                    ts,
                    ts,
                    clone_title,
                    session["summary"],
                    session["active_profile"],
                    session["mode"],
                    session["index_id"],
                    session["vector_backend"],
                    session["llm_provider"],
                    session["llm_model"],
                    session["embed_model"],
                    session["retrieve_k"],
                    session["final_k"],
                    session["mmr_lambda"],
                    session["agentic_iterations"],
                    session["extra_json"],
                ),
            )

        self.current_session_id = new_session_id
        self.clear_chat()
        self.chat_history = []
        self._restore_session_state(session)
        self.append_chat("system", f"Started duplicated session: {clone_title}")
        self.refresh_sessions_list()
        if self.sessions_tree.exists(new_session_id):
            self.sessions_tree.selection_set(new_session_id)
            self.sessions_tree.focus(new_session_id)
            self.sessions_tree.see(new_session_id)
        self.notebook.select(self.tab_chat)

    def _session_export_payload(self, session, messages):
        payload = dict(session)
        payload["messages"] = []
        run_ids = set()
        for msg in messages:
            record = {
                "role": msg["role"],
                "content": msg["content"],
                "ts": msg["ts"],
                "run_id": msg["run_id"],
                "sources": [],
            }
            if msg["run_id"]:
                run_ids.add(msg["run_id"])
            try:
                parsed = json.loads(msg["sources_json"] or "[]")
                if isinstance(parsed, list):
                    record["sources"] = parsed
            except json.JSONDecodeError:
                pass
            payload["messages"].append(record)
        feedback_rows = self._fetch_feedback_for_session(session["session_id"])
        payload["feedback"] = [dict(row) for row in feedback_rows]
        payload["traces"] = {run_id: self.trace_store.read_run(run_id) for run_id in sorted(run_ids)}
        return payload

    def export_selected_session(self):
        session_id = self._selected_history_session_id()
        if not session_id:
            messagebox.showinfo("No Session", "Select a session to export.")
            return
        session, messages = self._fetch_session_and_messages(session_id)
        if not session:
            return

        save_dir = filedialog.askdirectory(title="Select export directory")
        if not save_dir:
            return

        title = (session["title"] or "Untitled").strip() or "Untitled"
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", title).strip("_") or "session"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = os.path.join(save_dir, f"{slug}_{stamp}")
        md_path = f"{base}.md"
        json_path = f"{base}.json"

        payload = self._session_export_payload(session, messages)
        lines = [
            f"# Session Export: {title}",
            "",
            f"- Session ID: `{session_id}`",
            f"- Updated: `{session['updated_at'] or ''}`",
            f"- Profile: `{session['active_profile'] or '-'}`",
            f"- Mode: `{session['mode'] or '-'}`",
            f"- Index: `{session['index_id'] or '(default)'}`",
            f"- Model: `{session['llm_model'] or '-'}`",
            "",
            "## Summary",
            (session["summary"] or "(none)"),
            "",
            "## Transcript + Sources",
            "",
        ]
        for idx, msg in enumerate(payload["messages"], start=1):
            role = (msg.get("role") or "unknown").capitalize()
            ts = msg.get("ts") or ""
            lines.append(f"### {idx}. {role} ({ts})")
            lines.append(msg.get("content") or "")
            sources = msg.get("sources") or []
            if sources:
                lines.append("")
                lines.append("Sources:")
                for source in sources:
                    lines.append(
                        f"- source={source.get('source') or '-'} | "
                        f"chunk_id={source.get('chunk_id') or '-'} | "
                        f"score={source.get('score') if source.get('score') is not None else '-'}"
                    )
            lines.append("")

        feedback = payload.get("feedback") or []
        if feedback:
            lines.extend(["## Feedback", ""])
            for item in feedback:
                vote = "👍" if int(item.get("vote") or 0) > 0 else "👎"
                lines.append(f"- {vote} run_id={item.get('run_id') or '-'} @ {item.get('ts') or ''}: {item.get('note') or ''}")
            lines.append("")

        try:
            with open(md_path, "w", encoding="utf-8") as handle:
                handle.write("\n".join(lines).strip() + "\n")
            with open(json_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            self.log(f"Session exported to {md_path} and {json_path}")
            messagebox.showinfo("Session Export", f"Exported:\n{md_path}\n{json_path}")
        except OSError as exc:
            messagebox.showerror("Export Failed", f"Could not export session: {exc}")

    def delete_selected_session(self):
        session_id = self._selected_history_session_id()
        if not session_id:
            return
        with sqlite3.connect(self.session_db_path) as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        if self.current_session_id == session_id:
            self.start_new_chat(load_in_ui=True)
        self.refresh_sessions_list()

    def _load_last_run_telemetry(self, run_id):
        if not run_id:
            return None
        log_path = self._get_telemetry_log_path()
        if not os.path.exists(log_path):
            return None
        latest = None
        try:
            with open(log_path, "r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if payload.get("run_id") == run_id:
                        latest = payload
        except OSError:
            return None
        return latest

    def _refresh_history_details(self, _event=None):
        if not hasattr(self, "history_summary_text"):
            return
        session_id = self._selected_history_session_id()
        summary_text = ""
        config_text = ""
        telemetry_text = ""

        if session_id:
            session, messages = self._fetch_session_and_messages(session_id)
            if session:
                title = (session["title"] or "Untitled").strip() or "Untitled"
                summary = (session["summary"] or "").strip() or "(No summary saved.)"
                summary_text = (
                    f"Title: {title}\n"
                    f"Session ID: {session_id}\n"
                    f"Updated: {session['updated_at'] or ''}\n"
                    f"Messages: {len(messages)}\n\n"
                    f"Summary:\n{summary}"
                )

                extra = {}
                try:
                    extra = json.loads(session["extra_json"] or "{}")
                except json.JSONDecodeError:
                    extra = {}
                snapshot = {
                    "profile": session["active_profile"],
                    "mode": session["mode"],
                    "index": session["index_id"],
                    "llm_provider": session["llm_provider"],
                    "llm_model": session["llm_model"],
                    "embed_model": session["embed_model"],
                    "retrieve_k": session["retrieve_k"],
                    "final_k": session["final_k"],
                    "mmr_lambda": session["mmr_lambda"],
                    "agentic_iterations": session["agentic_iterations"],
                    "extra": extra,
                }
                config_text = json.dumps(snapshot, ensure_ascii=False, indent=2)

                run_id = None
                for msg in reversed(messages):
                    if msg["run_id"]:
                        run_id = msg["run_id"]
                        break
                telemetry = self._load_last_run_telemetry(run_id)
                if telemetry:
                    telemetry_text = json.dumps(telemetry, ensure_ascii=False, indent=2)
                elif run_id:
                    telemetry_text = f"No telemetry event found for run_id={run_id}."
                else:
                    telemetry_text = "No run telemetry available for this session."

        self._set_readonly_text(self.history_summary_text, summary_text)
        self._set_readonly_text(self.history_config_text, config_text)
        self._set_readonly_text(self.history_telemetry_text, telemetry_text)

    def _maybe_autotitle_session(self, first_user_text):
        text = (first_user_text or "").strip()
        if not text:
            return
        default_title = (text[:72] + "…") if len(text) > 72 else text
        self._upsert_session_row(session_id=self.current_session_id, title=default_title)

    def _sources_to_json(self, docs):
        if not docs:
            return None
        records = []
        for d in docs:
            metadata = getattr(d, "metadata", {}) or {}
            records.append(
                {
                    "chunk_id": metadata.get("chunk_id"),
                    "source": metadata.get("source")
                    or metadata.get("file_path")
                    or metadata.get("filename"),
                    "score": metadata.get("relevance_score"),
                }
            )
        try:
            return json.dumps(records, ensure_ascii=False)
        except (TypeError, ValueError):
            return None

    def _setup_langchain_globals(self):
        langchain = _lazy_import_langchain()
        if not hasattr(langchain, "llm_cache"):
            langchain.llm_cache = None
            if hasattr(langchain, "globals") and hasattr(langchain.globals, "set_llm_cache"):
                langchain.globals.set_llm_cache(None)
        if not hasattr(langchain, "verbose"):
            langchain.verbose = False
            if hasattr(langchain, "globals") and hasattr(langchain.globals, "set_verbose"):
                langchain.globals.set_verbose(False)
        if not hasattr(langchain, "debug"):
            langchain.debug = False
            if hasattr(langchain, "globals") and hasattr(langchain.globals, "set_debug"):
                langchain.globals.set_debug(False)

    def _lazy_lc_classes(self):
        if self._langchain_core_cache is None:
            self._langchain_core_cache = _lazy_import_langchain_core()
        return self._langchain_core_cache

    def _document(self, page_content="", metadata=None):
        Document, _, _, _ = self._lazy_lc_classes()
        return Document(page_content=page_content or "", metadata=metadata or {})

    def _human_message(self, content=""):
        _, _, HumanMessage, _ = self._lazy_lc_classes()
        return HumanMessage(content=content)

    def _ai_message(self, content=""):
        _, AIMessage, _, _ = self._lazy_lc_classes()
        return AIMessage(content=content)

    def _system_message(self, content=""):
        _, _, _, SystemMessage = self._lazy_lc_classes()
        return SystemMessage(content=content)

    def _is_human_message(self, value):
        _, _, HumanMessage, _ = self._lazy_lc_classes()
        return isinstance(value, HumanMessage)

    def setup_ui(self):
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Status.TLabel", font=("Segoe UI", 9))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tab_config = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_config, text="1. Configuration")
        ttk.Label(self.tab_config, text="Loading configuration...").pack(anchor="w", padx=14, pady=14)

        self.tab_ingest = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_ingest, text="2. Data Ingestion")
        ttk.Label(self.tab_ingest, text="Loading ingestion tools...").pack(anchor="w", padx=14, pady=14)

        self.tab_chat = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_chat, text="3. Agentic Chat")
        chat_wrap = ttk.Frame(self.tab_chat, padding=14)
        chat_wrap.pack(fill=tk.BOTH, expand=True)
        self.chat_display = scrolledtext.ScrolledText(chat_wrap, state="disabled", height=12)
        self.chat_display.pack(fill=tk.BOTH, expand=True, pady=(0, 8))
        input_frame = ttk.Frame(chat_wrap)
        input_frame.pack(fill="x")
        self.txt_input = ttk.Entry(input_frame)
        self.txt_input.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.txt_input.bind("<Return>", lambda _e: self.send_message())
        ttk.Button(input_frame, text="Send", command=self.send_message).pack(side="right")

        self.status_var = tk.StringVar(value="Ready")
        self.startup_elapsed_var = tk.StringVar(value="0 ms")
        status_wrap = ttk.Frame(self.root)
        status_wrap.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Label(status_wrap, textvariable=self.status_var, style="Status.TLabel", anchor="w").pack(side="left")
        ttk.Label(status_wrap, textvariable=self.startup_elapsed_var, style="Status.TLabel", anchor="e").pack(side="right")

    def _schedule_startup_pipeline(self):
        self.root.after(0, self._startup_step_build_full_ui)
        self.root.after(50, self._startup_step_load_config)
        self.root.after(100, self._startup_step_post_load)
        self.root.after(150, self._startup_step_scan_indexes)
        self.root.after(200, self._startup_step_check_dependencies)

    def _set_startup_status(self, text):
        elapsed_ms = int((time.perf_counter() - self._startup_started_at) * 1000)
        if hasattr(self, "status_var"):
            self.status_var.set(text)
        if hasattr(self, "startup_elapsed_var"):
            self.startup_elapsed_var.set(f"{elapsed_ms} ms")

    def _startup_step_build_full_ui(self):
        self._set_startup_status("Initialising UI...")
        self.notebook.destroy()
        self._build_full_ui()

    def _startup_step_load_config(self):
        self._set_startup_status("Loading settings...")
        self.load_config()

    def _startup_step_post_load(self):
        self._set_startup_status("Applying runtime defaults...")
        self._setup_langchain_globals()
        self._sync_model_options()
        self.vector_db_type.trace_add("write", self._on_vector_db_type_change)

    def _startup_step_scan_indexes(self):
        self._refresh_existing_indexes_async(reason="Loading indexes…")

    def _startup_step_check_dependencies(self):
        self._set_startup_status("Checking deps…")
        self.check_dependencies()
        self._startup_pipeline_finished = True
        self._set_startup_status("Ready")

    def _build_full_ui(self):
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Bold.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 9))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tab_config = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_config, text="1. Configuration")
        self.build_config_tab()

        self.tab_ingest = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_ingest, text="2. Data Ingestion")
        self.build_ingest_tab()

        self.tab_chat = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_chat, text="3. Agentic Chat")
        self.build_chat_tab()

    def load_icon(self):
        """Best-effort cross-platform icon loading without hard failure."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        assets_dir = os.path.join(script_dir, "assets")
        ico_path = os.path.join(assets_dir, "app.ico")
        png_path = os.path.join(assets_dir, "app.png")

        # Keep a reference so Tk doesn't garbage-collect the icon image.
        self._app_icon_photo = None

        if sys.platform.startswith("win") and os.path.exists(ico_path):
            try:
                self.root.iconbitmap(ico_path)
            except Exception as exc:
                logger.debug("unable to set .ico window icon: %s", exc)

        if os.path.exists(png_path):
            try:
                self._app_icon_photo = tk.PhotoImage(file=png_path)
                self.root.iconphoto(True, self._app_icon_photo)
            except Exception as exc:
                logger.debug("unable to set .png window icon: %s", exc)

    def _get_required_packages(self):
        return [
            "langchain",
            "langchain-community",
            "langchain-openai",
            "langchain-anthropic",
            "langchain-google-genai",
            "langchain-cohere",
            "langchain-voyageai",
            "langchain-chroma",
            "langchain-weaviate",
            "langchain-text-splitters",
            "chromadb",
            "beautifulsoup4",
            "tiktoken",
            "weaviate-client",
        ]

    def _build_evidence_pack_context(self, docs, budget_chars, per_doc_chars=600):
        context_blocks = []
        used_chars = 0
        packed_count = 0
        truncated_flag = False
        citation_v2_enabled = self._frontier_enabled("citation_v2")
        citation_manager = CitationManager()

        for idx, doc in enumerate(docs, start=1):
            metadata = getattr(doc, "metadata", {}) or {}
            chunk_id = metadata.get("chunk_id", "N/A")
            month_key = metadata.get("month_key")
            channel_key = metadata.get("channel_key", "N/A")
            role = metadata.get("role", "N/A")
            evidence_kind = metadata.get("evidence_kind", "N/A")
            source = (
                metadata.get("source")
                or metadata.get("file_path")
                or metadata.get("filename")
            )
            locator = self._build_source_locator(metadata, getattr(doc, "page_content", "") or "")
            citation_label = citation_manager.register(locator.source_id) if citation_v2_enabled else f"Chunk {idx}"
            header_parts = [
                f"[{citation_label}",
                f"chunk_id: {chunk_id}",
                f"channel_key: {channel_key}",
                f"role: {role}",
                f"evidence_kind: {evidence_kind}",
            ]
            if month_key:
                header_parts.append(f"month_key: {month_key}")
            if source:
                header_parts.append(f"source: {source}")
            if citation_v2_enabled:
                header_parts.append(f"source_label: {locator.label}")
            header = " | ".join(header_parts) + "]"

            excerpt = (getattr(doc, "page_content", "") or "").strip()[:per_doc_chars]
            chunk_text = f"{header}\n{excerpt}"
            added_chars = len(chunk_text) + (2 if context_blocks else 0)

            if used_chars + added_chars > budget_chars:
                truncated_flag = True
                break

            context_blocks.append(chunk_text)
            used_chars += added_chars
            packed_count += 1

        self.log(
            "Evidence-pack context: "
            f"packed_count={packed_count}, truncated={truncated_flag}, "
            f"per_doc_chars={per_doc_chars}, used_chars={used_chars}/{budget_chars}"
        )

        return "\n\n".join(context_blocks), packed_count, truncated_flag

    def setup_ui(self):
        # Styles
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Bold.TLabel", font=("Segoe UI", 10, "bold"))
        style.configure("Header.TLabel", font=("Segoe UI", 12, "bold"))
        style.configure("Status.TLabel", font=("Segoe UI", 9))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.tab_chat = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_chat, text="Chat")
        self.build_chat_tab()

        self.tab_library = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_library, text="Library")
        self.build_ingest_tab()

        self.tab_history = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_history, text="History")
        self.build_history_tab()

        self.tab_settings = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_settings, text="Settings")
        self.build_config_tab()

        self.tab_logs = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_logs, text="Logs")
        self.build_logs_tab()

        # Status Bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(
            self.root, textvariable=self.status_var, style="Status.TLabel", anchor="w"
        )
        status_bar.pack(fill="x", padx=10, pady=(0, 8))

    def _run_on_ui(self, func, *args, **kwargs):
        if threading.current_thread() == self.main_thread:
            func(*args, **kwargs)
        else:
            self.root.after(0, lambda: func(*args, **kwargs))

    def _get_llm_model_options(self, provider):
        options = {
            "openai": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "custom"],
            "anthropic": [
                "claude-opus-4-6",
                "claude-3-5-sonnet-20240620",
                "claude-3-5-haiku-20241022",
                "custom",
            ],
            "google": ["gemini-1.5-flash", "gemini-1.5-pro", "custom"],
            "local_lm_studio": ["custom"],
        }
        return options.get(provider, ["custom"])

    def _get_embedding_model_options(self, provider):
        options = {
            "openai": ["text-embedding-3-small", "text-embedding-3-large", "custom"],
            "google": ["models/embedding-001", "custom"],
            "local_huggingface": ["all-MiniLM-L6-v2", "custom"],
            "voyage": [
                "voyage-4-large",
                "voyage-4-lite",
                "voyage-4-nano",
                "voyage-4",
                "custom",
            ],
        }
        return options.get(provider, ["custom"])

    def _sync_model_options(self):
        llm_provider = self.llm_provider.get()
        emb_provider = self.embedding_provider.get()

        llm_options = self._get_llm_model_options(llm_provider)
        emb_options = self._get_embedding_model_options(emb_provider)

        self.cb_llm_model["values"] = llm_options
        if hasattr(self, "cb_chat_model"):
            self.cb_chat_model["values"] = llm_options
        self.cb_emb_model["values"] = emb_options

        if self.llm_model.get() not in llm_options:
            self.llm_model.set(llm_options[0])
        if self.embedding_model.get() not in emb_options:
            self.embedding_model.set(emb_options[0])

        self._toggle_custom_entries()

    def _toggle_custom_entries(self):
        llm_custom_enabled = self.llm_model.get() == "custom"
        emb_custom_enabled = self.embedding_model.get() == "custom"
        hf_enabled = self.embedding_provider.get() == "local_huggingface"

        self.llm_model_custom_entry.config(
            state="normal" if llm_custom_enabled else "disabled"
        )
        self.embedding_model_custom_entry.config(
            state="normal" if emb_custom_enabled else "disabled"
        )
        self.btn_browse_hf_model.config(state="normal" if hf_enabled else "disabled")

    def _on_llm_provider_change(self, event=None):
        self._sync_model_options()

    def _on_embedding_provider_change(self, event=None):
        self._sync_model_options()
        self._refresh_compatibility_warning()

    def _on_llm_model_change(self, event=None):
        self._toggle_custom_entries()

    def _on_embedding_model_change(self, event=None):
        self._toggle_custom_entries()
        self._refresh_compatibility_warning()

    def _on_instructions_change(self, event=None):
        self.system_instructions.set(self.instructions_box.get("1.0", tk.END).strip())

    def _on_verbose_mode_toggle(self):
        if self.verbose_mode.get():
            self._apply_instruction_template(self.verbose_system_instructions)
        else:
            self._apply_instruction_template(self.default_system_instructions)

    def _apply_instruction_template(self, template):
        self.system_instructions.set(template)
        self._run_on_ui(self._refresh_instructions_box)

    def _get_builtin_profiles(self):
        return {
            "Built-in: Default": AgentProfile(name="Default"),
            "Built-in: Tutor": AgentProfile(
                name="Tutor",
                style_template="Teach concept first, then short quiz and optional flashcards.",
                citation_policy="Cite each factual teaching block using standard citation format.",
                iteration_strategy={"agentic_mode": True, "max_iterations": 2},
            ),
            "Built-in: Blinkist": AgentProfile(
                name="Blinkist",
                style_template="Deliver a concise top-level summary with key insights.",
                citation_policy="Use concise citations at end of each insight.",
                retrieval_strategy={"retrieve_k": 20, "final_k": 4, "mmr_lambda": 0.6},
            ),
            "Built-in: Research Analyst": AgentProfile(
                name="Research Analyst",
                style_template="Structure output as claims, arguments, and counterclaims.",
                citation_policy="Every claim and counterclaim requires citation.",
                retrieval_strategy={"retrieve_k": 30, "final_k": 7, "mmr_lambda": 0.4},
                iteration_strategy={"agentic_mode": True, "max_iterations": 3},
            ),
            "Built-in: Evidence Pack": AgentProfile(
                name="Evidence Pack",
                style_template="Courtroom-ready packet with chronology and incidents.",
                citation_policy="Use [S#] style citations for factual lines.",
                retrieval_strategy={"retrieve_k": 35, "final_k": 10, "mmr_lambda": 0.5},
                iteration_strategy={"agentic_mode": True, "max_iterations": 3},
            ),
        }

    def _ensure_profiles_dir(self):
        os.makedirs(self.profiles_dir, exist_ok=True)

    def _get_file_profile_options(self):
        self._ensure_profiles_dir()
        profile_files = []
        for name in sorted(os.listdir(self.profiles_dir)):
            if name.lower().endswith(".json"):
                profile_files.append(name)
        return [f"File: {name}" for name in profile_files]

    def _refresh_profile_options(self):
        self.profile_options = list(self.builtin_profiles.keys()) + self._get_file_profile_options()
        if hasattr(self, "cb_profile"):
            self.cb_profile["values"] = self.profile_options
        if self.selected_profile.get() not in self.profile_options:
            self.selected_profile.set("Built-in: Default")

    def _profile_path_from_label(self, label):
        if not str(label).startswith("File: "):
            return ""
        return os.path.join(self.profiles_dir, label.replace("File: ", "", 1))

    def _load_profile_from_file(self, path):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return AgentProfile(
            name=data.get("name", os.path.splitext(os.path.basename(path))[0]),
            system_instructions=data.get("system_instructions", ""),
            style_template=data.get("style_template", ""),
            citation_policy=data.get("citation_policy", ""),
            retrieval_strategy=data.get("retrieval_strategy", {}),
            iteration_strategy=data.get("iteration_strategy", {}),
            comprehension_pipeline_on_ingest=data.get("comprehension_pipeline_on_ingest"),
        )

    def _get_selected_profile_obj(self):
        label = self.selected_profile.get().strip()
        if label in self.builtin_profiles:
            return self.builtin_profiles[label]
        path = self._profile_path_from_label(label)
        if path and os.path.exists(path):
            try:
                return self._load_profile_from_file(path)
            except (OSError, json.JSONDecodeError):
                self.log(f"Failed to parse profile: {path}")
        return self.builtin_profiles["Built-in: Default"]

    def _apply_profile_to_controls(self, profile):
        retrieval = profile.retrieval_strategy or {}
        if "retrieve_k" in retrieval:
            self.retrieval_k.set(max(1, int(retrieval["retrieve_k"])))
        if "final_k" in retrieval:
            self.final_k.set(max(1, int(retrieval["final_k"])))
        if "mmr_lambda" in retrieval:
            self.mmr_lambda.set(float(retrieval["mmr_lambda"]))
        if "search_type" in retrieval and retrieval["search_type"] in {"similarity", "mmr"}:
            self.search_type.set(retrieval["search_type"])

        iteration = profile.iteration_strategy or {}
        if "agentic_mode" in iteration:
            self.agentic_mode.set(bool(iteration["agentic_mode"]))
        if "max_iterations" in iteration:
            self.agentic_max_iterations.set(
                max(1, min(AGENTIC_MAX_ITERATIONS_HARD_CAP, int(iteration["max_iterations"])))
            )

        if profile.system_instructions:
            self.system_instructions.set(profile.system_instructions)
            self._refresh_instructions_box()

    def load_selected_profile(self):
        profile = self._get_selected_profile_obj()
        self._apply_profile_to_controls(profile)
        self.save_config()
        self.append_chat("system", f"Loaded profile: {profile.name}")

    def save_profile(self):
        self._ensure_profiles_dir()
        path = filedialog.asksaveasfilename(
            title="Save Profile",
            defaultextension=".json",
            initialdir=self.profiles_dir,
            filetypes=[("JSON files", "*.json")],
        )
        if not path:
            return
        profile = AgentProfile(
            name=os.path.splitext(os.path.basename(path))[0],
            system_instructions=self.system_instructions.get().strip(),
            style_template="",
            citation_policy="",
            retrieval_strategy={
                "retrieve_k": int(self.retrieval_k.get()),
                "final_k": int(self.final_k.get()),
                "mmr_lambda": float(self.mmr_lambda.get()),
                "search_type": self.search_type.get().strip(),
            },
            iteration_strategy={
                "agentic_mode": bool(self.agentic_mode.get()),
                "max_iterations": int(self.agentic_max_iterations.get()),
            },
        )
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(profile), f, indent=2)
        self._refresh_profile_options()
        self.selected_profile.set(f"File: {os.path.basename(path)}")
        self.save_config()

    def duplicate_profile(self):
        source = self._get_selected_profile_obj()
        self._ensure_profiles_dir()
        path = filedialog.asksaveasfilename(
            title="Duplicate Profile As",
            defaultextension=".json",
            initialdir=self.profiles_dir,
            initialfile=f"{source.name.lower().replace(' ', '_')}_copy.json",
            filetypes=[("JSON files", "*.json")],
        )
        if not path:
            return
        clone = AgentProfile(**asdict(source))
        clone.name = os.path.splitext(os.path.basename(path))[0]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(clone), f, indent=2)
        self._refresh_profile_options()
        self.selected_profile.set(f"File: {os.path.basename(path)}")
        self.save_config()

    def _current_embedding_signature(self):
        provider = self.embedding_provider.get()
        try:
            model = self._resolve_embedding_model()
        except ValueError:
            model = ""
        return f"{provider}:{model}".strip(":")

    def _refresh_compatibility_warning(self):
        if not self.index_embedding_signature:
            self.compat_warning.config(text="")
            return
        current_signature = self._current_embedding_signature()
        if not current_signature or current_signature == self.index_embedding_signature:
            self.compat_warning.config(text="")
            return
        message = (
            "Embedding mismatch: this index was built with "
            f"{self.index_embedding_signature}. Re-embed or use a dual-index "
            "migration. Force to bypass warning."
        )
        self.compat_warning.config(text=message)

    def browse_hf_model(self):
        path = filedialog.askdirectory()
        if path:
            self.embedding_model.set("custom")
            self.embedding_model_custom.set(path)
            self._toggle_custom_entries()
            self._refresh_compatibility_warning()

    def load_config(self):
        if not os.path.exists(self.config_path):
            return
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        for key, var in self.api_keys.items():
            if key in data.get("api_keys", {}):
                var.set(data["api_keys"][key])

        self.llm_provider.set(data.get("llm_provider", self.llm_provider.get()))
        self.embedding_provider.set(
            data.get("embedding_provider", self.embedding_provider.get())
        )
        self.vector_db_type.set(data.get("vector_db_type", self.vector_db_type.get()))
        self.local_llm_url.set(data.get("local_llm_url", self.local_llm_url.get()))
        self.chunk_size.set(data.get("chunk_size", self.chunk_size.get()))
        self.chunk_overlap.set(data.get("chunk_overlap", self.chunk_overlap.get()))
        self.build_digest_index.set(
            bool(data.get("build_digest_index", self.build_digest_index.get()))
        )
        self.build_comprehension_index.set(
            bool(
                data.get(
                    "build_comprehension_index",
                    self.build_comprehension_index.get(),
                )
            )
        )
        self.prefer_comprehension_index.set(
            bool(
                data.get(
                    "prefer_comprehension_index",
                    self.prefer_comprehension_index.get(),
                )
            )
        )
        extraction_depth = str(
            data.get(
                "comprehension_extraction_depth",
                self.comprehension_extraction_depth.get(),
            )
        ).strip()
        if extraction_depth not in {"Light", "Standard", "Deep"}:
            extraction_depth = "Standard"
        self.comprehension_extraction_depth.set(extraction_depth)
        self.llm_model.set(data.get("llm_model", self.llm_model.get()))
        self.llm_model_custom.set(data.get("llm_model_custom", self.llm_model_custom.get()))
        self.embedding_model.set(data.get("embedding_model", self.embedding_model.get()))
        self.embedding_model_custom.set(
            data.get("embedding_model_custom", self.embedding_model_custom.get())
        )
        self.llm_temperature.set(data.get("llm_temperature", self.llm_temperature.get()))
        self.llm_max_tokens.set(data.get("llm_max_tokens", self.llm_max_tokens.get()))
        self.force_embedding_compat.set(
            data.get("force_embedding_compat", self.force_embedding_compat.get())
        )
        self.retrieval_k.set(data.get("retrieval_k", self.retrieval_k.get()))
        self.final_k.set(data.get("final_k", self.final_k.get()))
        self.search_type.set(data.get("search_type", self.search_type.get()))
        retrieval_mode = data.get("retrieval_mode", self.retrieval_mode.get())
        if retrieval_mode not in self.retrieval_mode_options:
            retrieval_mode = "Flat (Chunks)"
        self.retrieval_mode.set(retrieval_mode)
        self.mmr_lambda.set(data.get("mmr_lambda", self.mmr_lambda.get()))
        # New config fields: agentic_mode, agentic_max_iterations, show_retrieved_context
        self.agentic_mode.set(data.get("agentic_mode", self.agentic_mode.get()))
        try:
            max_iterations = int(
                data.get("agentic_max_iterations", self.agentic_max_iterations.get())
            )
        except (TypeError, ValueError):
            max_iterations = self.agentic_max_iterations.get()
        clamped_max_iterations = max(
            1, min(AGENTIC_MAX_ITERATIONS_HARD_CAP, max_iterations)
        )
        self.agentic_max_iterations.set(clamped_max_iterations)
        self.show_retrieved_context.set(
            data.get("show_retrieved_context", self.show_retrieved_context.get())
        )
        self.use_reranker.set(data.get("use_reranker", self.use_reranker.get()))
        self.use_sub_queries.set(
            bool(data.get("use_sub_queries", self.use_sub_queries.get()))
        )
        try:
            subquery_max_docs = int(
                data.get("subquery_max_docs", self.subquery_max_docs.get())
            )
        except (TypeError, ValueError):
            subquery_max_docs = self.subquery_max_docs.get()
        self.subquery_max_docs.set(max(10, min(500, subquery_max_docs)))
        try:
            fallback_final_k = int(
                data.get("fallback_final_k", self.fallback_final_k.get())
            )
        except (TypeError, ValueError):
            fallback_final_k = self.fallback_final_k.get()
        self.fallback_final_k.set(max(1, fallback_final_k))
        self.enable_langextract.set(
            bool(data.get("enable_langextract", self.enable_langextract.get()))
        )
        self.enable_structured_incidents.set(
            bool(
                data.get(
                    "enable_structured_incidents",
                    self.enable_structured_incidents.get(),
                )
            )
        )
        self.enable_recursive_memory.set(
            bool(
                data.get("enable_recursive_memory", self.enable_recursive_memory.get())
            )
        )
        self.enable_recursive_retrieval.set(
            bool(
                data.get(
                    "enable_recursive_retrieval",
                    self.enable_recursive_retrieval.get(),
                )
            )
        )
        self.enable_citation_v2.set(
            bool(data.get("enable_citation_v2", self.enable_citation_v2.get()))
        )
        self.enable_claim_level_grounding_citefix_lite.set(
            bool(
                data.get(
                    "enable_claim_level_grounding_citefix_lite",
                    self.enable_claim_level_grounding_citefix_lite.get(),
                )
            )
        )
        agent_lightning_enabled_value = data.get(
            "agent_lightning_enabled",
            data.get(
                "enable_agent_lightning_telemetry",
                self.agent_lightning_enabled.get(),
            ),
        )
        self.agent_lightning_enabled.set(bool(agent_lightning_enabled_value))
        self.index_embedding_signature = data.get(
            "index_embedding_signature", self.index_embedding_signature
        )
        self.selected_index_path = data.get(
            "selected_index_path", self.selected_index_path
        )
        self.selected_collection_name = data.get(
            "selected_collection_name", self.selected_collection_name
        )
        output_style = data.get("output_style", self.output_style.get())
        if output_style not in self.output_style_options:
            output_style = "Default answer"
        self.output_style.set(output_style)
        selected_mode = data.get("selected_mode", self.selected_mode.get())
        if selected_mode not in self.mode_options:
            selected_mode = "Standard RAG Q&A"
        self.selected_mode.set(selected_mode)
        self.selected_profile.set(data.get("selected_profile", self.selected_profile.get()))
        self._refresh_profile_options()

        instructions = data.get("system_instructions", self.system_instructions.get())
        self.system_instructions.set(instructions or self.default_system_instructions)
        self.instructions_box.delete("1.0", tk.END)
        self.instructions_box.insert(tk.END, self.system_instructions.get())

        self._sync_model_options()
        self._refresh_compatibility_warning()
        if self.selected_index_path:
            self._pending_selected_index_label = self._format_index_label(
                self.selected_index_path, self.selected_collection_name
            )

    def save_config(self):
        try:
            subquery_max_docs = int(self.subquery_max_docs.get())
        except (TypeError, ValueError):
            subquery_max_docs = self.subquery_max_docs.get()
        try:
            max_iterations = int(self.agentic_max_iterations.get())
        except (TypeError, ValueError):
            max_iterations = self.agentic_max_iterations.get()
        max_iterations = max(1, min(AGENTIC_MAX_ITERATIONS_HARD_CAP, max_iterations))
        self.agentic_max_iterations.set(max_iterations)
        data = {
            "api_keys": {key: var.get() for key, var in self.api_keys.items()},
            "llm_provider": self.llm_provider.get(),
            "embedding_provider": self.embedding_provider.get(),
            "vector_db_type": self.vector_db_type.get(),
            "local_llm_url": self.local_llm_url.get(),
            "chunk_size": self.chunk_size.get(),
            "chunk_overlap": self.chunk_overlap.get(),
            "build_digest_index": self.build_digest_index.get(),
            "build_comprehension_index": bool(self.build_comprehension_index.get()),
            "prefer_comprehension_index": bool(self.prefer_comprehension_index.get()),
            "comprehension_extraction_depth": str(
                self.comprehension_extraction_depth.get()
            ),
            "llm_model": self.llm_model.get(),
            "llm_model_custom": self.llm_model_custom.get(),
            "embedding_model": self.embedding_model.get(),
            "embedding_model_custom": self.embedding_model_custom.get(),
            "llm_temperature": self.llm_temperature.get(),
            "llm_max_tokens": self.llm_max_tokens.get(),
            "system_instructions": self.system_instructions.get(),
            "force_embedding_compat": self.force_embedding_compat.get(),
            "retrieval_k": self.retrieval_k.get(),
            "final_k": self.final_k.get(),
            "search_type": self.search_type.get(),
            "retrieval_mode": self.retrieval_mode.get(),
            "mmr_lambda": self.mmr_lambda.get(),
            # New config fields: agentic_mode, agentic_max_iterations, show_retrieved_context
            "agentic_mode": self.agentic_mode.get(),
            "agentic_max_iterations": max_iterations,
            "show_retrieved_context": self.show_retrieved_context.get(),
            "use_reranker": self.use_reranker.get(),
            "use_sub_queries": bool(self.use_sub_queries.get()),
            "subquery_max_docs": subquery_max_docs,
            "fallback_final_k": self.fallback_final_k.get(),
            "enable_langextract": bool(self.enable_langextract.get()),
            "enable_structured_incidents": bool(
                self.enable_structured_incidents.get()
            ),
            "enable_recursive_memory": bool(self.enable_recursive_memory.get()),
            "enable_recursive_retrieval": bool(self.enable_recursive_retrieval.get()),
            "enable_citation_v2": bool(self.enable_citation_v2.get()),
            "enable_claim_level_grounding_citefix_lite": bool(
                self.enable_claim_level_grounding_citefix_lite.get()
            ),
            "agent_lightning_enabled": bool(self.agent_lightning_enabled.get()),
            "enable_agent_lightning_telemetry": bool(self.agent_lightning_enabled.get()),
            "index_embedding_signature": self.index_embedding_signature,
            "selected_index_path": self.selected_index_path,
            "selected_collection_name": self.selected_collection_name,
            "output_style": self.output_style.get(),
            "selected_mode": self.selected_mode.get(),
            "selected_profile": self.selected_profile.get(),
        }
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError:
            pass

    def on_close(self):
        self.save_config()
        self.root.destroy()

    def build_history_tab(self):
        frame = ttk.Frame(self.tab_history, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)

        actions = ttk.Frame(frame)
        actions.pack(fill="x", pady=(0, 8))
        ttk.Button(actions, text="New Chat", command=lambda: self.start_new_chat(load_in_ui=True)).pack(side="left")
        ttk.Button(actions, text="Open/Resume", command=self.load_selected_session).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Rename", command=self.rename_selected_session).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Delete", command=self.delete_selected_session).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Export", command=self.export_selected_session).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Duplicate", command=self.duplicate_selected_session).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Refresh", command=self.refresh_sessions_list).pack(side="left", padx=(8, 0))
        ttk.Checkbutton(
            actions,
            text="Auto-title with LLM",
            variable=self.session_title_llm_enabled,
        ).pack(side="right")

        search_row = ttk.Frame(frame)
        search_row.pack(fill="x", pady=(0, 8))
        ttk.Label(search_row, text="Search:").pack(side="left")
        self.history_search_var = tk.StringVar()
        self.history_search_entry = ttk.Entry(search_row, textvariable=self.history_search_var)
        self.history_search_entry.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.history_search_entry.bind("<KeyRelease>", self._on_history_search_change)

        split = ttk.Panedwindow(frame, orient=tk.HORIZONTAL)
        split.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(split)
        right = ttk.Frame(split)
        split.add(left, weight=3)
        split.add(right, weight=2)

        tree_wrap = ttk.LabelFrame(left, text="Saved Sessions", padding=8)
        tree_wrap.pack(fill=tk.BOTH, expand=True)
        columns = ("title", "updated", "profile", "mode", "index", "model")
        self.sessions_tree = ttk.Treeview(tree_wrap, columns=columns, show="headings", selectmode="browse")
        self.sessions_tree.heading("title", text="Title")
        self.sessions_tree.heading("updated", text="Updated")
        self.sessions_tree.heading("profile", text="Profile")
        self.sessions_tree.heading("mode", text="Mode")
        self.sessions_tree.heading("index", text="Index")
        self.sessions_tree.heading("model", text="Model")
        self.sessions_tree.column("title", width=240, anchor="w")
        self.sessions_tree.column("updated", width=150, anchor="w")
        self.sessions_tree.column("profile", width=120, anchor="w")
        self.sessions_tree.column("mode", width=110, anchor="w")
        self.sessions_tree.column("index", width=180, anchor="w")
        self.sessions_tree.column("model", width=140, anchor="w")
        yscroll = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.sessions_tree.yview)
        self.sessions_tree.configure(yscrollcommand=yscroll.set)
        self.sessions_tree.pack(side="left", fill=tk.BOTH, expand=True)
        yscroll.pack(side="right", fill="y")
        self.sessions_tree.bind("<Double-1>", lambda _e: self.load_selected_session())
        self.sessions_tree.bind("<<TreeviewSelect>>", self._refresh_history_details)

        details = ttk.LabelFrame(right, text="Session Details", padding=8)
        details.pack(fill=tk.BOTH, expand=True)

        ttk.Label(details, text="Summary", style="Bold.TLabel").pack(anchor="w")
        self.history_summary_text = scrolledtext.ScrolledText(details, height=8, state="disabled", wrap=tk.WORD)
        self.history_summary_text.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        ttk.Label(details, text="Config Snapshot", style="Bold.TLabel").pack(anchor="w")
        self.history_config_text = scrolledtext.ScrolledText(details, height=10, state="disabled", wrap=tk.WORD)
        self.history_config_text.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        ttk.Label(details, text="Last Run Telemetry", style="Bold.TLabel").pack(anchor="w")
        self.history_telemetry_text = scrolledtext.ScrolledText(details, height=8, state="disabled", wrap=tk.WORD)
        self.history_telemetry_text.pack(fill=tk.BOTH, expand=True)

    def build_logs_tab(self):
        frame = ttk.Frame(self.tab_logs, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        self.log_area = scrolledtext.ScrolledText(
            frame, height=8, state="disabled", font=("Consolas", 9)
        )
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def build_config_tab(self):
        frame = ttk.Frame(self.tab_settings, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        toggle_row = ttk.Frame(frame)
        toggle_row.grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=(0, 8))
        ttk.Label(toggle_row, text="Detail level:").pack(side="left")
        ttk.Checkbutton(
            toggle_row,
            text="Advanced",
            variable=self.advanced_ui,
            command=self._apply_basic_advanced_visibility,
        ).pack(side="left", padx=(8, 0))

        self.settings_model_section = CollapsibleFrame(frame, "Model & Provider", expanded=False)
        self.settings_model_section.grid(row=1, column=0, columnspan=2, sticky="ew", padx=5, pady=5)

        # --- LLM Provider Settings ---
        llm_frame = ttk.LabelFrame(self.settings_model_section.content, text="LLM & Embedding Provider", padding=15)
        llm_frame.pack(fill="x", padx=2, pady=(0, 8))
        llm_frame.columnconfigure(1, weight=1)

        ttk.Label(llm_frame, text="Generation Provider:").grid(
            row=0, column=0, sticky="w"
        )
        cb_llm = ttk.Combobox(
            llm_frame,
            textvariable=self.llm_provider,
            values=["openai", "anthropic", "google", "local_lm_studio"],
            state="readonly",
        )
        cb_llm.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        cb_llm.bind("<<ComboboxSelected>>", self._on_llm_provider_change)

        ttk.Label(llm_frame, text="Generation Model:").grid(
            row=1, column=0, sticky="w"
        )
        self.cb_llm_model = ttk.Combobox(
            llm_frame,
            textvariable=self.llm_model,
        )
        self.cb_llm_model.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.cb_llm_model.bind("<<ComboboxSelected>>", self._on_llm_model_change)

        ttk.Label(llm_frame, text="Custom Generation Model (optional):").grid(
            row=2, column=0, sticky="w"
        )
        self.llm_model_custom_entry = ttk.Entry(
            llm_frame, textvariable=self.llm_model_custom
        )
        self.llm_model_custom_entry.grid(
            row=2, column=1, sticky="ew", padx=5, pady=5
        )

        ttk.Label(llm_frame, text="Embedding Provider:").grid(
            row=3, column=0, sticky="w"
        )
        cb_emb = ttk.Combobox(
            llm_frame,
            textvariable=self.embedding_provider,
            values=["voyage", "openai", "google", "local_huggingface"],
            state="readonly",
        )
        cb_emb.grid(row=3, column=1, sticky="ew", padx=5, pady=5)
        cb_emb.bind("<<ComboboxSelected>>", self._on_embedding_provider_change)

        ttk.Label(llm_frame, text="Embedding Model:").grid(
            row=4, column=0, sticky="w"
        )
        self.cb_emb_model = ttk.Combobox(
            llm_frame,
            textvariable=self.embedding_model,
        )
        self.cb_emb_model.grid(row=4, column=1, sticky="ew", padx=5, pady=5)
        self.cb_emb_model.bind("<<ComboboxSelected>>", self._on_embedding_model_change)

        ttk.Label(llm_frame, text="Custom Embedding Model (optional):").grid(
            row=5, column=0, sticky="w"
        )
        self.embedding_model_custom_entry = ttk.Entry(
            llm_frame, textvariable=self.embedding_model_custom
        )
        self.embedding_model_custom_entry.grid(
            row=5, column=1, sticky="ew", padx=5, pady=5
        )
        self.btn_browse_hf_model = ttk.Button(
            llm_frame, text="Browse Local HF Model...", command=self.browse_hf_model
        )
        self.btn_browse_hf_model.grid(row=6, column=1, sticky="w", padx=5, pady=(0, 5))

        self.compat_warning = ttk.Label(
            llm_frame,
            text="",
            foreground="#a33",
            wraplength=360,
            justify="left",
        )
        self.compat_warning.grid(row=7, column=1, sticky="w", padx=5, pady=(0, 5))
        self.force_compat_check = ttk.Checkbutton(
            llm_frame,
            text="Force embedding compatibility (skip warning)",
            variable=self.force_embedding_compat,
        )
        self.force_compat_check.grid(row=8, column=1, sticky="w", padx=5, pady=(0, 5))

        ttk.Label(llm_frame, text="Local LLM URL (if using LM Studio):").grid(
            row=9, column=0, sticky="w"
        )
        ttk.Entry(llm_frame, textvariable=self.local_llm_url).grid(
            row=9, column=1, sticky="ew", padx=5, pady=5
        )

        ttk.Label(llm_frame, text="Temperature:").grid(row=10, column=0, sticky="w")
        ttk.Entry(llm_frame, textvariable=self.llm_temperature).grid(
            row=10, column=1, sticky="ew", padx=5, pady=5
        )

        ttk.Label(llm_frame, text="Max Tokens:").grid(row=11, column=0, sticky="w")
        ttk.Entry(llm_frame, textvariable=self.llm_max_tokens).grid(
            row=11, column=1, sticky="ew", padx=5, pady=5
        )

        ttk.Label(llm_frame, text="System Instructions:").grid(
            row=12, column=0, sticky="nw"
        )
        self.instructions_box = scrolledtext.ScrolledText(
            llm_frame, height=6, font=("Segoe UI", 9)
        )
        self.instructions_box.grid(row=12, column=1, sticky="ew", padx=5, pady=5)
        self.instructions_box.insert(tk.END, self.system_instructions.get())
        self.instructions_box.bind("<KeyRelease>", self._on_instructions_change)
        ttk.Checkbutton(
            llm_frame,
            text="Verbose/Analytical mode",
            variable=self.verbose_mode,
            command=self._on_verbose_mode_toggle,
        ).grid(row=13, column=1, sticky="w", padx=5, pady=(0, 5))

        # --- Vector DB Settings ---
        db_frame = ttk.LabelFrame(self.settings_model_section.content, text="Vector Database Strategy", padding=15)
        db_frame.pack(fill="x", padx=2, pady=(0, 8))

        ttk.Radiobutton(
            db_frame,
            text="ChromaDB (Local File - Recommended)",
            variable=self.vector_db_type,
            value="chroma",
        ).pack(anchor="w", pady=2)
        ttk.Radiobutton(
            db_frame,
            text="Weaviate (Server)",
            variable=self.vector_db_type,
            value="weaviate",
        ).pack(anchor="w", pady=2)

        ttk.Label(db_frame, text="Weaviate URL:").pack(anchor="w", pady=(10, 0))
        ttk.Entry(db_frame, textvariable=self.api_keys["weaviate_url"]).pack(
            fill="x", pady=2
        )

        # --- API Keys ---
        key_frame = ttk.LabelFrame(
            frame, text="API Keys (Required for selected services)", padding=15
        )
        key_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=10)
        key_frame.columnconfigure(1, weight=1)

        keys = [
            ("OpenAI API Key:", "openai"),
            ("Anthropic API Key:", "anthropic"),
            ("Google Gemini Key:", "google"),
            ("Cohere API Key (For Reranking):", "cohere"),
            ("Weaviate API Key (Optional):", "weaviate_key"),
            ("Voyage API Key:", "voyage"),
            ("Mistral API Key:", "mistral"),
            ("Groq API Key:", "groq"),
            ("Azure OpenAI API Key:", "azure_openai"),
            ("Together API Key:", "together"),
            ("Hugging Face Token (Optional):", "huggingface"),
            ("Fireworks API Key:", "fireworks"),
            ("Perplexity API Key:", "perplexity"),
        ]

        for i, (label, key_name) in enumerate(keys):
            ttk.Label(key_frame, text=label).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Entry(
                key_frame, textvariable=self.api_keys[key_name], show="*", width=50
            ).grid(row=i, column=1, sticky="w", padx=10, pady=2)

        deps_frame = ttk.LabelFrame(frame, text="Dependencies", padding=15)
        deps_frame.grid(row=3, column=0, columnspan=2, sticky="ew", padx=5, pady=10)
        deps_frame.columnconfigure(1, weight=1)

        ttk.Label(
            deps_frame,
            text="Check for required packages or reinstall them if needed.",
            wraplength=720,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Button(
            deps_frame, text="Check Dependencies", command=self.check_dependencies
        ).grid(row=1, column=0, sticky="w", padx=(0, 10), pady=(8, 0))
        ttk.Button(
            deps_frame, text="Install / Reinstall Dependencies", command=self.reinstall_dependencies
        ).grid(row=1, column=1, sticky="w", pady=(8, 0))


        retrieval_section = CollapsibleFrame(frame, "Retrieval", expanded=False)
        retrieval_section.grid(row=4, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 8))
        self.settings_retrieval_section = retrieval_section
        ttk.Label(retrieval_section.content, text="Search Type:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            retrieval_section.content,
            textvariable=self.search_type,
            values=["similarity", "mmr"],
            state="readonly",
            width=12,
        ).grid(row=0, column=1, sticky="w", padx=(5, 15), pady=2)
        ttk.Label(retrieval_section.content, text="Retrieval mode:").grid(row=0, column=2, sticky="w")
        ttk.Combobox(
            retrieval_section.content,
            textvariable=self.retrieval_mode,
            values=self.retrieval_mode_options,
            state="readonly",
            width=28,
        ).grid(row=0, column=3, sticky="w", padx=(5, 0), pady=2)
        ttk.Label(retrieval_section.content, text="MMR lambda:").grid(row=1, column=0, sticky="w")
        ttk.Entry(retrieval_section.content, textvariable=self.mmr_lambda, width=8).grid(row=1, column=1, sticky="w", padx=(5, 15), pady=2)
        ttk.Checkbutton(
            retrieval_section.content,
            text="Use Cohere Reranker (Higher Precision)",
            variable=self.use_reranker,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Checkbutton(
            retrieval_section.content,
            text="Use Sub-Queries (Broader Recall)",
            variable=self.use_sub_queries,
        ).grid(row=2, column=2, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Label(retrieval_section.content, text="Max Merged Docs:").grid(row=3, column=0, sticky="w")
        ttk.Entry(retrieval_section.content, textvariable=self.subquery_max_docs, width=8).grid(row=3, column=1, sticky="w", padx=(5, 15), pady=2)
        ttk.Label(retrieval_section.content, text="Fallback Final K:").grid(row=3, column=2, sticky="w")
        ttk.Entry(retrieval_section.content, textvariable=self.fallback_final_k, width=8).grid(row=3, column=3, sticky="w", padx=(5, 0), pady=2)

        agentic_section = CollapsibleFrame(frame, "Agentic / Iterations", expanded=False)
        agentic_section.grid(row=5, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 8))
        self.settings_agentic_section = agentic_section
        ttk.Checkbutton(
            agentic_section.content,
            text="Agentic mode (iterate)",
            variable=self.agentic_mode,
        ).pack(anchor="w")
        row = ttk.Frame(agentic_section.content)
        row.pack(fill="x", pady=(6, 0))
        ttk.Label(row, text="Max iterations:").pack(side="left")
        ttk.Spinbox(
            row,
            from_=1,
            to=AGENTIC_MAX_ITERATIONS_HARD_CAP,
            textvariable=self.agentic_max_iterations,
            width=4,
        ).pack(side="left", padx=(6, 12))
        ttk.Checkbutton(
            row,
            text="Show retrieved context in chat",
            variable=self.show_retrieved_context,
        ).pack(side="left")

        frontier_section = CollapsibleFrame(frame, "Frontier", expanded=False)
        frontier_section.grid(row=6, column=0, columnspan=2, sticky="ew", padx=5, pady=(0, 8))
        self.settings_frontier_section = frontier_section
        ttk.Checkbutton(frontier_section.content, text="Enable langextract", variable=self.enable_langextract).pack(anchor="w")
        ttk.Checkbutton(frontier_section.content, text="Enable structured incidents", variable=self.enable_structured_incidents).pack(anchor="w")
        ttk.Checkbutton(frontier_section.content, text="Enable recursive memory", variable=self.enable_recursive_memory).pack(anchor="w")
        ttk.Checkbutton(frontier_section.content, text="Enable recursive retrieval mode", variable=self.enable_recursive_retrieval).pack(anchor="w")
        ttk.Checkbutton(frontier_section.content, text="Prefer Comprehension Index for summaries/teaching", variable=self.prefer_comprehension_index).pack(anchor="w")
        ttk.Checkbutton(frontier_section.content, text="Enable citation v2 (defaults ON in evidence-pack mode)", variable=self.enable_citation_v2).pack(anchor="w")
        ttk.Checkbutton(frontier_section.content, text="Claim-level grounding (CiteFix-lite)", variable=self.enable_claim_level_grounding_citefix_lite).pack(anchor="w")
        ttk.Checkbutton(frontier_section.content, text="Agent Lightning traces", variable=self.agent_lightning_enabled).pack(anchor="w")

        self._apply_basic_advanced_visibility()

    def _apply_basic_advanced_visibility(self):
        advanced = bool(self.advanced_ui.get())
        for section_name in (
            "settings_model_section",
            "settings_retrieval_section",
            "settings_agentic_section",
            "settings_frontier_section",
        ):
            section = getattr(self, section_name, None)
            if section is not None:
                section.set_expanded(advanced)

    def build_ingest_tab(self):
        frame = ttk.Frame(self.tab_library, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        # File Selection
        sel_frame = ttk.Frame(frame)
        sel_frame.pack(fill="x", pady=10)

        ttk.Label(
            sel_frame,
            text="Select HTML/Text File (2M+ tokens supported):",
            style="Header.TLabel",
        ).pack(anchor="w")
        self.lbl_file = ttk.Label(sel_frame, text="No file selected", foreground="gray")
        self.lbl_file.pack(anchor="w", pady=5)
        self.lbl_file_info = ttk.Label(sel_frame, text="", foreground="#666666")
        self.lbl_file_info.pack(anchor="w")

        file_btn_frame = ttk.Frame(sel_frame)
        file_btn_frame.pack(anchor="w")
        btn_browse = ttk.Button(
            file_btn_frame, text="Browse File...", command=self.browse_file
        )
        btn_browse.pack(side="left")
        ttk.Button(
            file_btn_frame, text="Clear Selection", command=self.clear_selected_file
        ).pack(side="left", padx=8)

        # Chunking Config
        chunk_frame = ttk.LabelFrame(frame, text="Chunking Strategy", padding=10)
        chunk_frame.pack(fill="x", pady=10)

        ttk.Label(chunk_frame, text="Chunk Size (chars):").pack(side="left")
        ttk.Entry(chunk_frame, textvariable=self.chunk_size, width=10).pack(
            side="left", padx=5
        )

        ttk.Label(chunk_frame, text="Overlap (chars):").pack(side="left", padx=(20, 0))
        ttk.Entry(chunk_frame, textvariable=self.chunk_overlap, width=10).pack(
            side="left", padx=5
        )

        ttk.Checkbutton(
            chunk_frame,
            text="Build digest index",
            variable=self.build_digest_index,
        ).pack(side="left", padx=(20, 0))

        comprehension_frame = ttk.LabelFrame(
            frame, text="Comprehension Index", padding=10
        )
        comprehension_frame.pack(fill="x", pady=(0, 10))

        ttk.Checkbutton(
            comprehension_frame,
            text="Build Comprehension Index (langextract)",
            variable=self.build_comprehension_index,
        ).pack(side="left")

        ttk.Label(comprehension_frame, text="Extraction depth:").pack(
            side="left", padx=(20, 5)
        )
        ttk.Combobox(
            comprehension_frame,
            textvariable=self.comprehension_extraction_depth,
            values=["Light", "Standard", "Deep"],
            width=12,
            state="readonly",
        ).pack(side="left")

        # Action
        self.btn_ingest = ttk.Button(
            frame,
            text="Start Ingestion (Process -> Chunk -> Embed -> Store)",
            command=self.start_ingestion,
        )
        self.btn_ingest.pack(fill="x", pady=20)

        self.progress = ttk.Progressbar(frame, orient="horizontal", mode="determinate")
        self.progress.pack(fill="x")

    def build_chat_tab(self):
        if not hasattr(self, "use_sub_queries"):
            self.use_sub_queries = tk.BooleanVar(value=True)
        if not hasattr(self, "subquery_max_docs"):
            self.subquery_max_docs = tk.IntVar(value=200)
        frame = ttk.Frame(self.tab_chat, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        # Existing Index Selection
        index_frame = ttk.LabelFrame(frame, text="Vector Store Selection", padding=10)
        index_frame.pack(fill="x", pady=(0, 10))
        index_frame.columnconfigure(1, weight=1)

        ttk.Label(index_frame, text="Existing Index (optional):").grid(
            row=0, column=0, sticky="w"
        )
        self.cb_existing_index = ttk.Combobox(
            index_frame,
            textvariable=self.existing_index_var,
            state="readonly",
        )
        self.cb_existing_index.grid(row=0, column=1, sticky="ew", padx=5)
        self.cb_existing_index.bind(
            "<<ComboboxSelected>>", self._on_existing_index_change
        )
        ttk.Button(
            index_frame, text="Refresh", command=self._refresh_existing_indexes_async
        ).grid(row=0, column=2, padx=(5, 0))

        basic_frame = ttk.LabelFrame(frame, text="Basic Controls", padding=8)
        basic_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(basic_frame, text="Model:").pack(side="left")
        self.cb_chat_model = ttk.Combobox(
            basic_frame, textvariable=self.llm_model, state="readonly", width=20
        )
        self.cb_chat_model.pack(side="left", padx=(5, 12))
        self.cb_chat_model.bind("<<ComboboxSelected>>", self._on_llm_model_change)
        ttk.Label(basic_frame, text="Retrieve K:").pack(side="left")
        ttk.Entry(basic_frame, textvariable=self.retrieval_k, width=6).pack(side="left", padx=(5, 12))
        ttk.Label(basic_frame, text="Final K:").pack(side="left")
        ttk.Entry(basic_frame, textvariable=self.final_k, width=6).pack(side="left", padx=(5, 0))

        content_split = ttk.Panedwindow(frame, orient=tk.HORIZONTAL)
        content_split.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        left_pane = ttk.Frame(content_split)
        right_pane = ttk.Frame(content_split, width=380)
        content_split.add(left_pane, weight=4)
        content_split.add(right_pane, weight=2)

        # Chat Display
        self.chat_display = scrolledtext.ScrolledText(
            left_pane, state="disabled", font=("Segoe UI", 10), wrap=tk.WORD
        )
        self.chat_display.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.chat_display.tag_config("citation", foreground="#1254a3", underline=1)
        self.chat_display.tag_bind("citation", "<Button-1>", self._on_citation_click)
        self.chat_display.tag_bind("citation", "<Enter>", lambda _e: self.chat_display.config(cursor="hand2"))
        self.chat_display.tag_bind("citation", "<Leave>", lambda _e: self.chat_display.config(cursor=""))

        # Tag configuration for coloring
        self.chat_display.tag_config(
            "user", foreground="blue", font=("Segoe UI", 10, "bold")
        )
        self.chat_display.tag_config("agent", foreground="green")
        self.chat_display.tag_config(
            "system", foreground="gray", font=("Segoe UI", 8, "italic")
        )
        self.chat_display.tag_config("source", foreground="#888888", font=("Consolas", 8))

        # Input
        input_frame = ttk.Frame(left_pane)
        input_frame.pack(fill="x")

        self.txt_input = ttk.Entry(input_frame, font=("Segoe UI", 11))
        self.txt_input.pack(side="left", fill="both", expand=True, padx=(0, 10))
        self.txt_input.bind("<Return>", lambda e: self.send_message())

        btn_send = ttk.Button(input_frame, text="Send", command=self.send_message)
        btn_send.pack(side="right")

        # Quick Actions
        action_frame = ttk.Frame(left_pane)
        action_frame.pack(fill="x", pady=(8, 4))
        ttk.Button(
            action_frame,
            text="New Chat",
            command=lambda: self.start_new_chat(load_in_ui=True),
        ).pack(side="left")
        ttk.Button(
            action_frame, text="Copy Last Answer", command=self.copy_last_answer
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            action_frame,
            text="Export notes to Markdown",
            command=self.export_notes_to_markdown,
        ).pack(side="left", padx=8)
        if agent_lightning is not None:
            ttk.Button(
                action_frame,
                text="Export to Agent Lightning format",
                command=self.export_run_as_agent_lightning_dataset,
            ).pack(side="left")
        ttk.Button(
            action_frame,
            text="Export Eval Set",
            command=self.export_eval_set,
        ).pack(side="left", padx=8)

        output_frame = ttk.Frame(left_pane)
        output_frame.pack(fill="x", pady=(2, 4))
        ttk.Label(output_frame, text="Output style:").pack(side="left")
        ttk.Combobox(
            output_frame,
            textvariable=self.output_style,
            values=self.output_style_options,
            state="readonly",
            width=22,
        ).pack(side="left", padx=(6, 0))

        profile_frame = ttk.LabelFrame(left_pane, text="Mode & Agent Profile", padding=8)
        profile_frame.pack(fill="x", pady=(4, 0))
        ttk.Label(profile_frame, text="Mode:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            profile_frame,
            textvariable=self.selected_mode,
            values=self.mode_options,
            state="readonly",
            width=24,
        ).grid(row=0, column=1, sticky="w", padx=(6, 12))

        ttk.Label(profile_frame, text="Profile:").grid(row=0, column=2, sticky="w")
        self.cb_profile = ttk.Combobox(
            profile_frame,
            textvariable=self.selected_profile,
            state="readonly",
            width=30,
        )
        self.cb_profile.grid(row=0, column=3, sticky="ew", padx=(6, 0))
        profile_frame.columnconfigure(3, weight=1)

        ttk.Button(profile_frame, text="Save Profile", command=self.save_profile).grid(
            row=1, column=1, sticky="w", pady=(8, 0)
        )
        ttk.Button(profile_frame, text="Load Profile", command=self.load_selected_profile).grid(
            row=1, column=2, sticky="w", pady=(8, 0)
        )
        ttk.Button(profile_frame, text="Duplicate", command=self.duplicate_profile).grid(
            row=1, column=3, sticky="w", padx=(6, 0), pady=(8, 0)
        )
        self._refresh_profile_options()

        agentic_frame = ttk.LabelFrame(left_pane, text="Agentic Options", padding=8)
        agentic_frame.pack(fill="x", pady=(5, 0))
        ttk.Checkbutton(
            agentic_frame,
            text="Agentic mode (iterate)",
            variable=self.agentic_mode,
        ).pack(side="left")
        ttk.Label(agentic_frame, text="Max iterations:").pack(side="left", padx=(12, 4))
        ttk.Spinbox(
            agentic_frame,
            from_=1,
            to=AGENTIC_MAX_ITERATIONS_HARD_CAP,
            textvariable=self.agentic_max_iterations,
            width=4,
        ).pack(side="left")
        ttk.Checkbutton(
            agentic_frame,
            text="Show retrieved context in chat",
            variable=self.show_retrieved_context,
        ).pack(side="left", padx=(12, 0))

        frontier_wrap = ttk.LabelFrame(left_pane, text="Advanced / Frontier", padding=8)
        frontier_wrap.pack(fill="x", pady=(6, 0))
        self.frontier_collapsed = tk.BooleanVar(value=True)

        def _toggle_frontier_section():
            if self.frontier_collapsed.get():
                self.frontier_options_frame.pack(fill="x", pady=(6, 0))
                self.frontier_toggle_btn.config(text="Hide")
                self.frontier_collapsed.set(False)
            else:
                self.frontier_options_frame.pack_forget()
                self.frontier_toggle_btn.config(text="Show")
                self.frontier_collapsed.set(True)

        header_row = ttk.Frame(frontier_wrap)
        header_row.pack(fill="x")
        ttk.Label(header_row, text="Optional frontier components").pack(side="left")
        self.frontier_toggle_btn = ttk.Button(
            header_row, text="Show", width=8, command=_toggle_frontier_section
        )
        self.frontier_toggle_btn.pack(side="right")

        self.frontier_options_frame = ttk.Frame(frontier_wrap)
        ttk.Checkbutton(
            self.frontier_options_frame,
            text="Enable langextract",
            variable=self.enable_langextract,
        ).pack(anchor="w")
        ttk.Checkbutton(
            self.frontier_options_frame,
            text="Enable structured incidents",
            variable=self.enable_structured_incidents,
        ).pack(anchor="w")
        ttk.Checkbutton(
            self.frontier_options_frame,
            text="Enable recursive memory",
            variable=self.enable_recursive_memory,
        ).pack(anchor="w")
        ttk.Checkbutton(
            self.frontier_options_frame,
            text="Enable recursive retrieval mode",
            variable=self.enable_recursive_retrieval,
        ).pack(anchor="w")
        ttk.Checkbutton(
            self.frontier_options_frame,
            text="Enable citation v2 (defaults ON in evidence-pack mode)",
            variable=self.enable_citation_v2,
        ).pack(anchor="w")
        ttk.Checkbutton(
            self.frontier_options_frame,
            text="Claim-level grounding (CiteFix-lite)",
            variable=self.enable_claim_level_grounding_citefix_lite,
        ).pack(anchor="w")
        ttk.Checkbutton(
            self.frontier_options_frame,
            text="Agent Lightning traces",
            variable=self.agent_lightning_enabled,
        ).pack(anchor="w")

        # Right evidence pane
        evidence_wrap = ttk.LabelFrame(right_pane, text="Evidence Navigator", padding=8)
        evidence_wrap.pack(fill=tk.BOTH, expand=True)
        self.evidence_notebook = ttk.Notebook(evidence_wrap)
        self.evidence_notebook.pack(fill=tk.BOTH, expand=True)

        self.answer_tab = ttk.Frame(self.evidence_notebook)
        self.evidence_notebook.add(self.answer_tab, text="Answer")
        self.answer_text = scrolledtext.ScrolledText(
            self.answer_tab, height=20, wrap=tk.WORD, state="disabled", font=("Segoe UI", 10)
        )
        self.answer_text.tag_config("citation", foreground="#1254a3", underline=1)
        self.answer_text.tag_bind("citation", "<Button-1>", self._on_answer_citation_click)
        self.answer_text.tag_bind("citation", "<Enter>", lambda _e: self.answer_text.config(cursor="hand2"))
        self.answer_text.tag_bind("citation", "<Leave>", lambda _e: self.answer_text.config(cursor=""))
        self.answer_text.pack(fill=tk.BOTH, expand=True)

        self.sources_tab = ttk.Frame(self.evidence_notebook)
        self.evidence_notebook.add(self.sources_tab, text="Sources")
        self.sources_tree = ttk.Treeview(
            self.sources_tab,
            columns=("sid", "doc", "section", "location", "speaker", "timestamp", "snippet"),
            show="headings",
            height=10,
            selectmode="extended",
        )
        for col, label, width in [
            ("sid", "S#", 50),
            ("doc", "Document", 170),
            ("section", "Section/Chapter", 180),
            ("location", "Position", 180),
            ("speaker", "Speaker/Role", 120),
            ("timestamp", "Timestamp", 150),
            ("snippet", "Snippet", 260),
        ]:
            self.sources_tree.heading(col, text=label)
            self.sources_tree.column(col, width=width, anchor="w")
        self.sources_tree.tag_configure("supporting", background="#fff4cc")
        self.sources_tree.pack(fill=tk.BOTH, expand=True)
        self.sources_tree.bind("<<TreeviewSelect>>", self._on_source_selected)

        source_actions = ttk.Frame(self.sources_tab)
        source_actions.pack(fill="x", pady=(6, 4))
        ttk.Button(source_actions, text="Open selected source", command=self._open_selected_source).pack(side="left")

        self.source_detail_text = scrolledtext.ScrolledText(
            self.sources_tab, height=8, wrap=tk.WORD, state="disabled", font=("Consolas", 9)
        )
        self.source_detail_text.pack(fill=tk.BOTH, expand=True, pady=(8, 0))

        self.incidents_json_tab = ttk.Frame(self.evidence_notebook)
        self.evidence_notebook.add(self.incidents_json_tab, text="Incidents JSON")
        self.incidents_json_text = scrolledtext.ScrolledText(
            self.incidents_json_tab, height=14, wrap=tk.NONE, state="disabled", font=("Consolas", 9)
        )
        self.incidents_json_text.pack(fill=tk.BOTH, expand=True)

        self.trace_tab = ttk.Frame(self.evidence_notebook)
        self.evidence_notebook.add(self.trace_tab, text="Trace")
        self.trace_text = scrolledtext.ScrolledText(
            self.trace_tab, height=14, wrap=tk.WORD, state="disabled", font=("Consolas", 9)
        )
        self.trace_text.pack(fill=tk.BOTH, expand=True)

        self.grounding_tab = ttk.Frame(self.evidence_notebook)
        self.grounding_label_var = tk.StringVar(value="LangExtract grounding HTML is not available yet.")
        ttk.Label(self.grounding_tab, textvariable=self.grounding_label_var, wraplength=300).pack(
            fill="x", anchor="w", pady=(0, 8)
        )
        ttk.Button(
            self.grounding_tab,
            text="Open grounding HTML",
            command=self._open_grounding_html,
        ).pack(anchor="w")
        self._grounding_tab_added = False
        self.enable_langextract.trace_add("write", self._toggle_grounding_tab)
        self._toggle_grounding_tab()

    def _toggle_grounding_tab(self, *args):
        should_show = bool(self.enable_langextract.get())
        currently_added = bool(getattr(self, "_grounding_tab_added", False))
        if should_show and not currently_added:
            self.evidence_notebook.add(self.grounding_tab, text="Grounding")
            self._grounding_tab_added = True
        elif not should_show and currently_added:
            self.evidence_notebook.forget(self.grounding_tab)
            self._grounding_tab_added = False

    def _open_grounding_html(self):
        path = getattr(self, "_latest_grounding_html_path", "")
        if not path or not os.path.isfile(path):
            messagebox.showinfo("Grounding", "No LangExtract grounding HTML is available for this run.")
            return
        webbrowser.open_new_tab(f"file://{os.path.abspath(path)}")

    def _render_incident_evidence(self, incident):
        # Legacy method retained for compatibility with older call paths.
        return

    def _set_readonly_text(self, widget, text):
        widget.config(state="normal")
        widget.delete("1.0", tk.END)
        widget.insert(tk.END, text)
        widget.config(state="disabled")

    def _select_source_by_sid(self, sid):
        if not sid:
            return
        if sid not in self.sources_tree.get_children():
            return
        self.evidence_notebook.select(self.sources_tab)
        self.sources_tree.selection_set((sid,))
        self.sources_tree.focus(sid)
        self.sources_tree.see(sid)
        self._on_source_selected()

    def _on_citation_click(self, event=None):
        try:
            index = self.chat_display.index(f"@{event.x},{event.y}") if event else self.chat_display.index(tk.INSERT)
            ranges = self.chat_display.tag_prevrange("citation", index)
            if not ranges:
                return
            raw = self.chat_display.get(ranges[0], ranges[1]).strip()
            match = re.search(r"S\d+", raw)
            if match:
                self._select_source_by_sid(match.group(0))
        except Exception:
            return


    def _on_answer_citation_click(self, event=None):
        try:
            index = self.answer_text.index(f"@{event.x},{event.y}") if event else self.answer_text.index(tk.INSERT)
            ranges = self.answer_text.tag_prevrange("citation", index)
            if not ranges:
                return
            raw = self.answer_text.get(ranges[0], ranges[1]).strip()
            match = re.search(r"S\d+", raw)
            if match:
                self._select_source_by_sid(match.group(0))
        except Exception:
            return

    def _tag_citations_in_answer(self):
        text = self.answer_text.get("1.0", tk.END)
        self.answer_text.tag_remove("citation", "1.0", tk.END)
        for match in re.finditer(r"S\d+", text or ""):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            self.answer_text.tag_add("citation", start, end)

    def _on_source_selected(self, event=None):
        selection = self.sources_tree.selection()
        if not selection:
            return
        item_id = selection[0]
        source_id = self._source_id_by_tree_iid.get(item_id)
        entry = (self._latest_source_map or {}).get(source_id or "", {})
        if not entry:
            return
        metadata_blob = json.dumps(entry.get("metadata") or {}, ensure_ascii=False, indent=2, sort_keys=True)
        excerpt = str(entry.get("excerpt") or "").strip() or "(no excerpt captured)"
        detail_lines = [
            f"Citation: {entry.get('sid', '')}",
            f"Source Card: {entry.get('label', 'unknown')}",
            f"Doc: {entry.get('title', 'unknown')}",
            f"Section hint: {entry.get('section_hint') or entry.get('section') or entry.get('chapter') or '-'}",
            f"Position hint: {entry.get('position_hint') or entry.get('locator', 'unknown')}",
            f"Date/Month: {entry.get('date', entry.get('month_bucket', 'undated'))}",
            f"Timestamp: {entry.get('timestamp') or '-'}",
            f"Speaker/Role: {entry.get('speaker', entry.get('actor', 'unknown'))}",
            f"Type: {entry.get('type', 'unknown')}",
            f"Open path: {entry.get('file_path') or '-'}",
            f"Anchor: {entry.get('anchor', '') or '(none)'}",
            "",
            "Evidence snippet:",
            excerpt,
            "",
            "Full metadata:",
            metadata_blob,
        ]
        self.source_detail_text.config(state="normal")
        self.source_detail_text.delete("1.0", tk.END)
        self.source_detail_text.insert(tk.END, "\n".join(detail_lines))
        self.source_detail_text.config(state="disabled")


    def _open_selected_source(self):
        selection = self.sources_tree.selection()
        if not selection:
            messagebox.showinfo("Open source", "Select a source row first.")
            return
        item_id = selection[0]
        source_id = self._source_id_by_tree_iid.get(item_id)
        entry = (self._latest_source_map or {}).get(source_id or "", {})
        file_path = str(entry.get("file_path") or ((entry.get("metadata") or {}).get("source_path")) or "").strip()
        if file_path and os.path.isfile(file_path):
            webbrowser.open_new_tab(f"file://{os.path.abspath(file_path)}")
            return
        excerpt = str(entry.get("excerpt") or "").strip() or "(no excerpt captured)"
        popup = tk.Toplevel(self.root)
        popup.title(f"{entry.get('sid', 'S?')} - {entry.get('title', 'Source')}")
        popup.geometry("900x520")
        viewer = scrolledtext.ScrolledText(popup, wrap=tk.WORD, font=("Consolas", 10))
        viewer.pack(fill=tk.BOTH, expand=True)
        viewer.insert(
            tk.END,
            f"Source: {entry.get('title', 'unknown')}\n"
            f"Section: {entry.get('section_hint') or entry.get('section') or '-'}\n"
            f"Position: {entry.get('position_hint') or entry.get('locator') or '-'}\n"
            f"Speaker/Role: {entry.get('speaker', 'unknown')}\n"
            f"Timestamp: {entry.get('timestamp') or entry.get('date') or 'unknown'}\n\n"
            f"{excerpt}",
        )
        viewer.config(state="disabled")

    def _refresh_evidence_pane(self, source_map, incidents, grounding_html_path=""):
        self._source_id_by_tree_iid = {}
        ordered_source_ids = sorted(
            (source_map or {}).keys(),
            key=lambda source_id: int(str((source_map or {}).get(source_id, {}).get("sid", "S999")).lstrip("S") or "999"),
        )
        label_by_source = {
            source_id: str((source_map or {}).get(source_id, {}).get("sid") or source_id)
            for source_id in ordered_source_ids
        }
        self.sources_tree.delete(*self.sources_tree.get_children())
        for source_id in ordered_source_ids:
            entry = (source_map or {}).get(source_id, {})
            sid = label_by_source[source_id]
            section_label = entry.get("section_hint") or entry.get("section") or entry.get("chapter") or "-"
            if section_label != "-" and entry.get("section_idx"):
                section_label = f"{entry.get('section_idx')}. {section_label}"
            position_label = entry.get("position_hint") or entry.get("locator") or "unknown"
            self.sources_tree.insert(
                "",
                tk.END,
                iid=sid,
                values=(
                    sid,
                    entry.get("title", "unknown"),
                    section_label,
                    position_label,
                    entry.get("speaker", entry.get("actor", "unknown")),
                    entry.get("timestamp") or entry.get("date", entry.get("month_bucket", "unknown")),
                    entry.get("snippet_preview") or re.sub(r"\s+", " ", str(entry.get("excerpt") or "").strip())[:180],
                ),
            )
            self._source_id_by_tree_iid[sid] = source_id

        normalized_incidents = []
        for incident in incidents or []:
            raw_support = incident.get("supporting_chunks") or []
            normalized_support = []
            for ref in raw_support:
                candidate = str(ref).strip()
                if candidate in label_by_source.values():
                    normalized_support.append(candidate)
                elif candidate in label_by_source:
                    normalized_support.append(label_by_source[candidate])
            copied = dict(incident)
            copied["supporting_chunks"] = sorted(set(normalized_support))
            normalized_incidents.append(copied)

        incidents_blob = {"incidents": sorted(normalized_incidents, key=self._incident_sort_key_for_pack)}
        self._set_readonly_text(
            self.incidents_json_text,
            json.dumps(incidents_blob, ensure_ascii=False, indent=2),
        )

        self._latest_grounding_html_path = grounding_html_path or ""
        if self._latest_grounding_html_path and os.path.isfile(self._latest_grounding_html_path):
            self.grounding_label_var.set(f"Saved grounding HTML: {self._latest_grounding_html_path}")
        else:
            self.grounding_label_var.set("LangExtract grounding HTML is not available yet.")
        self._set_readonly_text(
            self.source_detail_text,
            "Select an S# source row to inspect excerpt and metadata."
        )

    def _append_trace(self, msg):
        stamped = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        self._trace_events.append(stamped)
        if len(self._trace_events) > 500:
            self._trace_events = self._trace_events[-500:]
        if hasattr(self, "trace_text"):
            self._set_readonly_text(self.trace_text, "\n".join(self._trace_events))

    def _save_langextract_grounding_html(self, payload):
        if not payload:
            return ""
        persist_dir = self.selected_index_path or getattr(self.vector_store, "_persist_directory", None) or os.getcwd()
        os.makedirs(persist_dir, exist_ok=True)
        path = os.path.join(persist_dir, "langextract_grounding_latest.html")
        html_body = payload.get("grounding_html") or payload.get("html") or ""
        if not html_body:
            incidents_blob = html.escape(json.dumps(payload.get("incidents", []), ensure_ascii=False, indent=2))
            html_body = f"<html><body><h2>LangExtract grounding fallback</h2><pre>{incidents_blob}</pre></body></html>"
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(html_body)
            return path
        except Exception as exc:
            self.log(f"Failed to write LangExtract grounding HTML. ({exc})")
            return ""

    # --- Logic ---

    @staticmethod
    def _humanize_bytes(num_bytes):
        if num_bytes < 1024:
            return f"{num_bytes} B"
        for unit in ["KB", "MB", "GB", "TB"]:
            num_bytes /= 1024
            if num_bytes < 1024:
                return f"{num_bytes:.1f} {unit}"
        return f"{num_bytes:.1f} PB"

    def _frontier_enabled(self, name: str) -> bool:
        var_name = f"enable_{name}"
        var = getattr(self, var_name, None)
        enabled = bool(var.get()) if hasattr(var, "get") else False
        if name == "citation_v2":
            return enabled or bool(getattr(self, "_frontier_evidence_pack_mode", False))
        return enabled

    def _append_history(self, message):
        self.chat_history.append(message)
        max_messages = self.chat_history_max_turns * 2
        if len(self.chat_history) > max_messages:
            self.chat_history = self.chat_history[-max_messages:]

    def _get_history_window(self, current_query=None):
        history = list(self.chat_history)
        if (
            current_query
            and history
            and self._is_human_message(history[-1])
            and history[-1].content == current_query
        ):
            history = history[:-1]
        max_messages = self.chat_history_max_turns * 2
        if len(history) > max_messages:
            history = history[-max_messages:]
        return history

    def _parse_subquery_response(self, text):
        cleaned = text.strip()
        if "```" in cleaned:
            parts = cleaned.split("```")
            if len(parts) >= 2:
                cleaned = parts[1].strip()
                if cleaned.lower().startswith("json"):
                    cleaned = cleaned.split("\n", 1)[-1].strip()
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(item).strip() for item in parsed if str(item).strip()]
        lines = []
        for line in cleaned.splitlines():
            item = line.strip().lstrip("-*0123456789. ").strip()
            if item:
                lines.append(item)
        return lines

    def _generate_sub_queries(self, query):
        try:
            llm = self.get_llm()
            system_prompt = (
                "You generate search sub-queries for retrieval. "
                "Return 3-5 concise sub-queries as a JSON array of strings. "
                "Do not include any extra text."
            )
            messages = [
                self._system_message(content=system_prompt),
                self._human_message(content=query),
            ]
            response = llm.invoke(messages)
            candidates = self._parse_subquery_response(response.content)
        except Exception as exc:
            self.log(f"Sub-query generation failed, using base query only. ({exc})")
            return []
        seen = set()
        sub_queries = []
        for candidate in candidates:
            normalized = candidate.strip()
            if not normalized or normalized.lower() == query.strip().lower():
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            sub_queries.append(normalized)
        return sub_queries[:5]

    def _merge_dedupe_docs(self, docs):
        seen = set()
        merged = []
        for doc in docs:
            if doc is None:
                continue
            metadata = getattr(doc, "metadata", {}) or {}
            content = (getattr(doc, "page_content", "") or "").strip()
            chunk_id = metadata.get("chunk_id")
            ingest_id = metadata.get("ingest_id")
            if chunk_id is not None and ingest_id:
                key = (ingest_id, chunk_id)
            else:
                content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
                key = content_hash
            if key in seen:
                continue
            seen.add(key)
            merged.append(doc)
        return merged

    @staticmethod
    def _doc_identity_key(doc):
        metadata = getattr(doc, "metadata", {}) or {}
        content = (getattr(doc, "page_content", "") or "").strip()
        chunk_id = metadata.get("chunk_id")
        ingest_id = metadata.get("ingest_id")
        if chunk_id is not None and ingest_id:
            return f"{ingest_id}:{chunk_id}"
        chunk_db_id = metadata.get("chunk_db_id")
        if chunk_db_id:
            return f"chunk_db:{chunk_db_id}"
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return f"content:{content_hash}"

    def _fuse_ranked_results(self, ranked_lists, k_rrf=60, fused_pool_size=600):
        score_by_key = {}
        doc_by_key = {}
        systems_by_key = {}
        for system_name, docs in ranked_lists:
            for rank_idx, doc in enumerate(docs or [], start=1):
                if doc is None:
                    continue
                key = self._doc_identity_key(doc)
                score = 1.0 / (k_rrf + rank_idx)
                score_by_key[key] = score_by_key.get(key, 0.0) + score
                doc_by_key[key] = doc
                systems_by_key.setdefault(key, set()).add(system_name)

        ranked_items = sorted(score_by_key.items(), key=lambda item: item[1], reverse=True)
        if fused_pool_size > 0:
            ranked_items = ranked_items[:fused_pool_size]

        fused_docs = []
        for rank_idx, (key, score) in enumerate(ranked_items, start=1):
            doc = doc_by_key[key]
            metadata = (getattr(doc, "metadata", {}) or {}).copy()
            metadata["rrf_score"] = round(score, 8)
            metadata["relevance_score"] = round(score, 8)
            metadata["rrf_rank"] = rank_idx
            metadata["retrieval_systems"] = sorted(systems_by_key.get(key, set()))
            doc.metadata = metadata
            fused_docs.append(doc)
        return fused_docs

    @staticmethod
    def _doc_group_key(doc):
        metadata = getattr(doc, "metadata", {}) or {}
        for field in (
            "section",
            "section_title",
            "heading",
            "header",
            "title",
            "doc_title",
        ):
            value = metadata.get(field)
            if value:
                return f"{field}:{value}"
        digest_window = metadata.get("digest_window") or metadata.get("digest_id")
        if digest_window:
            return f"digest_window:{digest_window}"
        source = metadata.get("source") or metadata.get("file_path") or metadata.get(
            "filename"
        )
        content = (getattr(doc, "page_content", "") or "").strip()
        prefix = content[:80]
        return f"{source}:{prefix}"

    @staticmethod
    def _is_priority_doc(doc):
        metadata = getattr(doc, "metadata", {}) or {}
        if metadata.get("lexical_boost") or metadata.get("lexical_boosted"):
            return True
        if metadata.get("critic_missing") or metadata.get("critic_missing_items"):
            return True
        missing_items = metadata.get("missing_items") or metadata.get(
            "missing_coverage"
        )
        if isinstance(missing_items, (list, tuple, set)):
            return len(missing_items) > 0
        return bool(missing_items)

    @staticmethod
    def _is_must_include(doc):
        metadata = getattr(doc, "metadata", {}) or {}
        return bool(
            metadata.get("must_include")
            or metadata.get("force_include")
            or metadata.get("required_context")
        )

    @staticmethod
    def _detect_channel_hint(text, metadata):
        source = (
            str(metadata.get("source") or metadata.get("file_path") or metadata.get("filename") or "")
        )
        combined = f"{source}\n{text}".lower()
        if "teams" in combined:
            return "teams"
        if "whatsapp" in combined:
            return "whatsapp"
        if "email" in combined or "e-mail" in combined:
            return "email"
        if "call" in combined or "phone" in combined or "dial" in combined:
            return "call"
        return "unknown"

    @staticmethod
    def _extract_channel(text):
        normalized = (text or "").lower()
        if not normalized:
            return "unknown"
        if re.search(r"\b(teams|slack|discord|chat)\b", normalized):
            return "chat"
        if "whatsapp" in normalized:
            return "whatsapp"
        if re.search(r"\b(email|e-mail|mail)\b", normalized):
            return "email"
        if re.search(r"\b(call|phone|dial|voicemail|zoom|meet)\b", normalized):
            return "call"
        if re.search(r"\b(ticket|case|jira|zendesk|servicenow)\b", normalized):
            return "ticket"
        return "unknown"

    @staticmethod
    def _month_to_number(month_name):
        months = {
            "jan": 1,
            "january": 1,
            "feb": 2,
            "february": 2,
            "mar": 3,
            "march": 3,
            "apr": 4,
            "april": 4,
            "may": 5,
            "jun": 6,
            "june": 6,
            "jul": 7,
            "july": 7,
            "aug": 8,
            "august": 8,
            "sep": 9,
            "sept": 9,
            "september": 9,
            "oct": 10,
            "october": 10,
            "nov": 11,
            "november": 11,
            "dec": 12,
            "december": 12,
        }
        return months.get(month_name.lower())

    def _extract_dates(self, text):
        mentions = []
        if not text:
            return mentions
        patterns = []
        patterns.append(
            (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "ymd")
        )
        patterns.append(
            (re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b"), "numeric")
        )
        patterns.append(
            (
                re.compile(
                    r"\b(\d{1,2})\s+"
                    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
                    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
                    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+"
                    r"(\d{4})\b",
                    flags=re.I,
                ),
                "day_month_year",
            )
        )
        patterns.append(
            (
                re.compile(
                    r"\b(?:early|mid|late)\s+"
                    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
                    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
                    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+"
                    r"(\d{4})\b",
                    flags=re.I,
                ),
                "month_year",
            )
        )
        patterns.append(
            (
                re.compile(
                    r"\b"
                    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|"
                    r"jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
                    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+"
                    r"(\d{4})\b",
                    flags=re.I,
                ),
                "month_year",
            )
        )
        for pattern, kind in patterns:
            for match in pattern.finditer(text):
                if kind == "ymd":
                    year, month, day = match.groups()
                elif kind == "numeric":
                    month, day, year = match.groups()
                elif kind == "day_month_year":
                    day, month_name, year = match.groups()
                    month = self._month_to_number(month_name) or 0
                    day = int(day)
                    year = int(year)
                    if month:
                        mentions.append((match.start(), f"{year:04d}-{month:02d}-{day:02d}"))
                    continue
                elif kind == "month_year":
                    month_name, year = match.groups()
                    month = self._month_to_number(month_name) or 0
                    year = int(year)
                    if month:
                        mentions.append((match.start(), f"{year:04d}-{month:02d}"))
                    continue
                if kind in {"ymd", "numeric"}:
                    if len(year) == 2:
                        year = int(f"20{year}")
                    else:
                        year = int(year)
                    month = int(month)
                    day = int(day)
                    mentions.append((match.start(), f"{year:04d}-{month:02d}-{day:02d}"))
        mentions.sort(key=lambda item: item[0])
        return [value for _idx, value in mentions]

    def _extract_date_mentions(self, text):
        return self._extract_dates(text)

    def _extract_incident_signature(self, text):
        date_mentions = self._extract_dates(text)
        date_key = date_mentions[0] if date_mentions else "undated"
        channel = self._extract_channel(text)
        normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
        participant = ""
        participant_match = re.search(
            r"\b([A-Z][a-z]+ [A-Z][a-z]+|[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})\b",
            text or "",
        )
        if participant_match:
            participant = participant_match.group(1).lower()
        digest = hashlib.sha256(normalized[:200].encode("utf-8")).hexdigest()[:12]
        return f"{date_key}|{channel}|{participant or digest}"

    @staticmethod
    def _extract_role_kind(doc):
        metadata = getattr(doc, "metadata", {}) or {}
        role = str(
            metadata.get("speaker_role") or metadata.get("role") or "unknown"
        ).strip().lower()
        if role in {"assistant", "system", "bot", "ai"}:
            return "assistant"
        if role in {"user", "human", "employee", "complainant", "reporter"}:
            return "user"
        if role in {"manager", "supervisor", "lead", "hr", "legal"}:
            return "authority"
        return "other"

    def _evidence_kind(self, doc):
        metadata = getattr(doc, "metadata", {}) or {}
        kind = str(metadata.get("evidence_kind") or "").strip().lower()
        if kind:
            return kind
        role_kind = self._extract_role_kind(doc)
        if role_kind == "user":
            return "primary"
        if role_kind == "assistant":
            return "secondary"
        return "unknown"

    def _build_incident_key(self, doc):
        content = (getattr(doc, "page_content", "") or "").strip()
        metadata = getattr(doc, "metadata", {}) or {}
        signature_text = "\n".join(
            [
                str(
                    metadata.get("source")
                    or metadata.get("file_path")
                    or metadata.get("filename")
                    or ""
                ),
                content,
            ]
        )
        return self._extract_incident_signature(signature_text)

    def _score_doc_for_selection(
        self,
        doc,
        evidence_pack_mode=False,
        evidence_thin=False,
        incident_key=None,
        month_key=None,
        channel_key=None,
        seen_chunk_ids=None,
    ):
        content = (getattr(doc, "page_content", "") or "").strip()
        metadata = getattr(doc, "metadata", {}) or {}
        base_score = metadata.get("relevance_score")
        try:
            base_score = float(base_score)
        except (TypeError, ValueError):
            base_score = 0.0

        date_mentions = self._extract_date_mentions(content)
        quote_match = re.search(r"(\"[^\"]+\"|“[^”]+”)", content)
        participant_match = re.search(
            r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", content
        ) or re.search(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", content
        )
        what_happened_match = re.search(
            r"\b(incident|issue|complaint|reported|alleged|occurred|happened|"
            r"breach|violation|harassment|grievance|escalated|confirmed|said|"
            r"stated|told|raised)\b",
            content,
            flags=re.I,
        )
        advice_match = re.search(
            r"\b(you should|we should|i recommend|recommend|suggest|consider|"
            r"best practice|steps to|how to|guidance|advice|tips|as an ai)\b",
            content,
            flags=re.I,
        )

        channel = channel_key or self._extract_channel(
            "\n".join(
                [
                    str(
                        metadata.get("source")
                        or metadata.get("file_path")
                        or metadata.get("filename")
                        or ""
                    ),
                    content,
                ]
            )
        )
        month_bucket = month_key or (date_mentions[0][:7] if date_mentions else "undated")
        incident_signature = incident_key or self._extract_incident_signature(content)
        role_kind = self._extract_role_kind(doc)
        evidence_kind = self._evidence_kind(doc)

        score = base_score
        if date_mentions:
            score += 0.3
        if quote_match:
            score += 0.2
        if participant_match:
            score += 0.2
        if what_happened_match:
            score += 0.2
        if advice_match:
            score -= 0.2 if (evidence_pack_mode and evidence_thin) else (0.5 if evidence_pack_mode else 0.3)

        if role_kind == "assistant" and evidence_pack_mode:
            score -= 0.1 if evidence_thin else 0.25
        elif role_kind == "user":
            score += 0.15

        if evidence_kind == "primary":
            score += 0.1

        seen_ids = seen_chunk_ids if isinstance(seen_chunk_ids, set) else set(seen_chunk_ids or [])
        doc_id = metadata.get("chunk_id") or metadata.get("source_id")
        doc_key = str(doc_id) if doc_id is not None else self._doc_identity_key(doc)
        seen_before = bool(doc_key in seen_ids)
        if seen_before and not self._is_must_include(doc):
            score -= 0.15

        incident_key = incident_key or self._build_incident_key(doc)
        metadata["incident_key"] = incident_key
        metadata["incident_signature"] = incident_signature
        metadata["month_bucket"] = month_bucket
        metadata["channel_type"] = channel
        metadata["role_kind"] = role_kind
        metadata["evidence_kind"] = evidence_kind
        metadata["selection_score"] = round(score, 4)
        metadata["date_mentions"] = date_mentions
        metadata["selection_seen_before"] = seen_before
        doc.metadata = metadata
        return score, incident_key

    def _apply_coverage_selection(
        self,
        docs,
        final_k,
        group_limit=2,
        evidence_pack_mode=False,
        seen_chunk_ids=None,
    ):
        must_include = []
        remaining = []
        for doc in docs:
            if self._is_must_include(doc):
                must_include.append(doc)
            else:
                remaining.append(doc)

        selected = list(must_include)
        selected_ids = {id(doc) for doc in selected}
        group_counts = {}
        incident_counts = {}
        month_counts = {}
        channel_counts = {}
        signature_counts = {}
        pool_non_assistant = 0
        for doc in docs:
            if self._extract_role_kind(doc) != "assistant":
                pool_non_assistant += 1
        evidence_thin = evidence_pack_mode and pool_non_assistant <= max(2, final_k // 3)

        for doc in selected:
            group_key = self._doc_group_key(doc)
            group_counts[group_key] = group_counts.get(group_key, 0) + 1
            _score, incident_key = self._score_doc_for_selection(
                doc,
                evidence_pack_mode,
                evidence_thin=evidence_thin,
                seen_chunk_ids=seen_chunk_ids,
            )
            incident_counts[incident_key] = incident_counts.get(incident_key, 0) + 1
            metadata = getattr(doc, "metadata", {}) or {}
            month = metadata.get("month_bucket") or "undated"
            channel = metadata.get("channel_type") or "unknown"
            signature = metadata.get("incident_signature") or incident_key
            month_counts[month] = month_counts.get(month, 0) + 1
            channel_counts[channel] = channel_counts.get(channel, 0) + 1
            signature_counts[signature] = signature_counts.get(signature, 0) + 1

        priority_docs = [doc for doc in remaining if self._is_priority_doc(doc)]
        other_docs = [doc for doc in remaining if doc not in priority_docs]

        scored_priority = []
        scored_other = []
        for doc in priority_docs:
            score, incident_key = self._score_doc_for_selection(
                doc,
                evidence_pack_mode,
                evidence_thin=evidence_thin,
                seen_chunk_ids=seen_chunk_ids,
            )
            scored_priority.append((score, incident_key, doc))
        for doc in other_docs:
            score, incident_key = self._score_doc_for_selection(
                doc,
                evidence_pack_mode,
                evidence_thin=evidence_thin,
                seen_chunk_ids=seen_chunk_ids,
            )
            scored_other.append((score, incident_key, doc))
        all_channels = {
            (getattr(doc, "metadata", {}) or {}).get("channel_type") or "unknown"
            for _score, _incident_key, doc in (scored_priority + scored_other)
        }
        all_channels.discard("unknown")
        month_pool = {
            (getattr(doc, "metadata", {}) or {}).get("month_bucket") or "undated"
            for _score, _incident_key, doc in (scored_priority + scored_other)
        }
        month_pool.discard("undated")
        min_month_buckets = min(3, len(month_pool))

        def _diversity_boost(item):
            score, incident_key, doc = item
            metadata = getattr(doc, "metadata", {}) or {}
            month = metadata.get("month_bucket") or "undated"
            channel = metadata.get("channel_type") or "unknown"
            signature = metadata.get("incident_signature") or incident_key
            boost = 0.0
            boost += 0.25 if month_counts.get(month, 0) == 0 else 0.0
            boost += 0.2 if channel != "unknown" and channel_counts.get(channel, 0) == 0 else 0.0
            boost += 0.25 if signature_counts.get(signature, 0) == 0 else 0.0
            return score + boost

        scored_priority.sort(key=_diversity_boost, reverse=True)
        scored_other.sort(key=_diversity_boost, reverse=True)
        scored_all = scored_priority + scored_other

        if final_k < MIN_UNIQUE_INCIDENTS:
            target_unique = final_k
        else:
            target_unique = min(final_k, MAX_UNIQUE_INCIDENTS)

        def _add_docs(candidates):
            nonlocal selected
            for _score, incident_key, doc in candidates:
                if len(selected) >= final_k and not self._is_must_include(doc):
                    break
                if id(doc) in selected_ids:
                    continue
                group_key = self._doc_group_key(doc)
                count = group_counts.get(group_key, 0)
                if count >= group_limit and not self._is_must_include(doc):
                    continue
                selected.append(doc)
                selected_ids.add(id(doc))
                group_counts[group_key] = count + 1
                incident_counts[incident_key] = incident_counts.get(incident_key, 0) + 1
                metadata = getattr(doc, "metadata", {}) or {}
                month = metadata.get("month_bucket") or "undated"
                channel = metadata.get("channel_type") or "unknown"
                signature = metadata.get("incident_signature") or incident_key
                month_counts[month] = month_counts.get(month, 0) + 1
                channel_counts[channel] = channel_counts.get(channel, 0) + 1
                signature_counts[signature] = signature_counts.get(signature, 0) + 1

        missing_channels = [
            channel
            for channel in sorted(all_channels)
            if channel_counts.get(channel, 0) == 0
        ]
        for channel in missing_channels:
            if len(selected) >= final_k:
                break
            for _score, incident_key, doc in scored_all:
                metadata = getattr(doc, "metadata", {}) or {}
                if (metadata.get("channel_type") or "unknown") != channel:
                    continue
                _add_docs([(_score, incident_key, doc)])
                break

        missing_months = [
            month
            for month in sorted(month_pool)
            if month_counts.get(month, 0) == 0
        ]
        for month in missing_months:
            represented_months = len([m for m, c in month_counts.items() if c > 0 and m != "undated"])
            if represented_months >= min_month_buckets or len(selected) >= final_k:
                break
            for _score, incident_key, doc in scored_all:
                metadata = getattr(doc, "metadata", {}) or {}
                if (metadata.get("month_bucket") or "undated") != month:
                    continue
                _add_docs([(_score, incident_key, doc)])
                break

        for _score, incident_key, doc in scored_all:
            if len(selected) >= final_k:
                break
            if id(doc) in selected_ids:
                continue
            if incident_counts.get(incident_key):
                continue
            if len(incident_counts) >= target_unique:
                break
            group_key = self._doc_group_key(doc)
            count = group_counts.get(group_key, 0)
            if count >= group_limit and not self._is_must_include(doc):
                continue
            _add_docs([(_score, incident_key, doc)])

        _add_docs(scored_all)

        if len(selected) > final_k and len(must_include) <= final_k:
            selected = selected[:final_k]
        return selected

    def _prioritize_must_include(self, docs):
        must_include = [doc for doc in docs if self._is_must_include(doc)]
        remainder = [doc for doc in docs if doc not in must_include]
        return [*must_include, *remainder]

    @staticmethod
    def _detect_exact_detail_cues(query):
        cues = {
            "quotes": False,
            "dates": False,
            "ids": False,
            "numeric_heavy": False,
        }
        if re.search(r"\"[^\"]+\"", query):
            cues["quotes"] = True
        if re.search(r"\b\d{4}-\d{2}-\d{2}\b", query) or re.search(
            r"\b\d{1,2}/\d{1,2}/\d{2,4}\b", query
        ):
            cues["dates"] = True
        if re.search(
            r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}\b",
            query,
            flags=re.I,
        ):
            cues["dates"] = True
        if re.search(r"\b[A-Z]{2,}-\d+\b", query) or re.search(
            r"\b(?:id|ticket|case|ref)[\s:#-]*[A-Za-z0-9-]{3,}\b",
            query,
            flags=re.I,
        ):
            cues["ids"] = True
        alnum_count = sum(ch.isalnum() for ch in query)
        digit_count = sum(ch.isdigit() for ch in query)
        if alnum_count:
            ratio = digit_count / alnum_count
            if digit_count >= 4 or ratio >= 0.2:
                cues["numeric_heavy"] = True
        return cues

    @staticmethod
    def _tokenize_for_overlap(text):
        return set(re.findall(r"[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*", text.lower()))

    def _lexical_overlap_score(self, query, content, cues):
        query_tokens = self._tokenize_for_overlap(query)
        if not query_tokens:
            return 0.0
        content_tokens = self._tokenize_for_overlap(content)
        shared = query_tokens & content_tokens
        base = len(shared) / max(1, len(query_tokens))
        bonus = 0.0
        if cues.get("quotes"):
            for quoted in re.findall(r"\"([^\"]+)\"", query):
                if quoted and quoted.lower() in content.lower():
                    bonus += 0.2
                    break
        if cues.get("dates") or cues.get("ids") or cues.get("numeric_heavy"):
            numeric_shared = [token for token in shared if any(ch.isdigit() for ch in token)]
            if numeric_shared:
                bonus += 0.15
        return min(1.0, base + bonus)

    def _promote_lexical_overlap(self, docs, query):
        cues = self._detect_exact_detail_cues(query)
        scored = []
        for idx, doc in enumerate(docs):
            content = (getattr(doc, "page_content", "") or "").strip()
            score = self._lexical_overlap_score(query, content, cues)
            metadata = getattr(doc, "metadata", {}) or {}
            metadata["lexical_overlap"] = round(score, 4)
            if score >= 0.3 or (any(cues.values()) and score >= 0.15):
                metadata["lexical_boost"] = True
            doc.metadata = metadata
            scored.append((idx, score, doc))
        scored.sort(
            key=lambda item: (
                (item[2].metadata or {}).get("lexical_boost") is True,
                item[1],
            ),
            reverse=True,
        )
        return [doc for _idx, _score, doc in scored]

    def log(self, msg):
        def _append():
            self.log_area.config(state="normal")
            self.log_area.insert(
                tk.END, f"[{datetime.now().strftime('%H:%M:%S')}] {msg}\n"
            )
            self.log_area.see(tk.END)
            self.log_area.config(state="disabled")
            self.root.update_idletasks()
            if hasattr(self, "status_var"):
                self.status_var.set(msg)

        self._run_on_ui(_append)
        self._run_on_ui(self._append_trace, msg)
        self._emit_log_to_console(msg)

    @staticmethod
    def _emit_log_to_console(msg):
        stream = sys.stderr if ("ERROR" in msg or "Failed" in msg) else sys.stdout
        if not stream or not stream.isatty():
            return
        print(msg, file=stream)

    def _format_role_distribution(self, docs):
        role_counts = {}
        for doc in docs or []:
            metadata = getattr(doc, "metadata", {}) or {}
            role = metadata.get("speaker_role") or "unknown"
            role_counts[role] = role_counts.get(role, 0) + 1
        if not role_counts:
            return "none"
        parts = [f"{role}={count}" for role, count in sorted(role_counts.items())]
        return ", ".join(parts)

    def _format_selected_distribution(self, docs):
        def _fmt(counter):
            if not counter:
                return "none"
            return ", ".join(
                f"{key}={value}" for key, value in sorted(counter.items(), key=lambda kv: kv[0])
            )

        month_counts = {}
        channel_counts = {}
        role_counts = {}
        evidence_counts = {}
        for doc in docs or []:
            metadata = getattr(doc, "metadata", {}) or {}
            month = metadata.get("month_bucket")
            if not month:
                dates = self._extract_dates(getattr(doc, "page_content", "") or "")
                month = dates[0][:7] if dates else "undated"
            channel = metadata.get("channel_type") or self._extract_channel(
                "\n".join(
                    [
                        str(
                            metadata.get("source")
                            or metadata.get("file_path")
                            or metadata.get("filename")
                            or ""
                        ),
                        getattr(doc, "page_content", "") or "",
                    ]
                )
            )
            role = metadata.get("role_kind") or self._extract_role_kind(doc)
            evidence = metadata.get("evidence_kind") or self._evidence_kind(doc)
            month_counts[month] = month_counts.get(month, 0) + 1
            channel_counts[channel] = channel_counts.get(channel, 0) + 1
            role_counts[role] = role_counts.get(role, 0) + 1
            evidence_counts[evidence] = evidence_counts.get(evidence, 0) + 1
        return {
            "months": _fmt(month_counts),
            "channels": _fmt(channel_counts),
            "roles": _fmt(role_counts),
            "evidence_kind": _fmt(evidence_counts),
        }

    def _log_final_docs_selection(
        self,
        retrieve_k,
        candidate_k,
        final_k,
        trunc_used_chars,
        trunc_budget_chars,
        unique_incidents,
        role_distribution,
        rerank_top_n,
        new_incidents_added,
        selected_distribution,
    ):
        self.log(
            "Final-docs selection telemetry | "
            f"retrieve_k={retrieve_k}, candidate_k={candidate_k}, final_k={final_k}, "
            f"packed_context_chars={trunc_used_chars}/{trunc_budget_chars}, "
            f"unique_incidents={unique_incidents}, role_distribution={role_distribution}, "
            f"rerank_top_n={rerank_top_n}, new_incidents_added={new_incidents_added}, "
            f"months={selected_distribution.get('months')}, "
            f"channels={selected_distribution.get('channels')}, "
            f"roles={selected_distribution.get('roles')}, "
            f"evidence_kind={selected_distribution.get('evidence_kind')}"
        )

    def _on_vector_db_type_change(self, *_args):
        self._refresh_existing_indexes_async(reason="Loading indexes…")

    def _get_chroma_persist_root(self):
        return os.path.join(os.getcwd(), "chroma_db")

    def _get_lexical_db_path(self):
        persist_root = self._get_chroma_persist_root()
        parent_dir = os.path.dirname(os.path.abspath(persist_root))
        return os.path.join(parent_dir, "rag_lexical.db")

    def _get_telemetry_log_path(self):
        candidate_dir = self.selected_index_path
        if candidate_dir and os.path.isdir(candidate_dir):
            base_dir = os.path.dirname(os.path.abspath(candidate_dir))
        else:
            base_dir = os.path.dirname(os.path.abspath(self.config_path))
        return os.path.join(base_dir, self.telemetry_log_filename)

    def _append_jsonl_telemetry(self, payload):
        if not isinstance(payload, dict):
            return
        record = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            **payload,
        }
        try:
            log_path = self._get_telemetry_log_path()
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        except Exception:
            return

    def _agent_lightning_telemetry_enabled(self):
        return bool(self.agent_lightning_enabled.get())

    @staticmethod
    def _trace_stage_from_node(node_name):
        stage_map = {
            "Ingest": "ingest",
            "Retrieve": "retrieve",
            "Rerank": "rerank",
            "Select": "select",
            "Synthesize": "generate",
            "VerifyCitations": "verify",
            "ExtractIncidents": "select",
        }
        return stage_map.get(str(node_name), str(node_name).lower())

    def _append_trace_event(self, run_id, event: TraceEvent):
        if not self._agent_lightning_telemetry_enabled():
            return
        bucket = self._agent_lightning_trace_events_by_run.setdefault(run_id, [])
        bucket.append(event.to_dict())

    def _trace_from_span(self, run_id, node, iteration, latency_ms, input_payload=None, output_payload=None, metrics=None):
        stage = self._trace_stage_from_node(node)
        prompt_payload = None
        retrieval_payload = None
        validator_payload = None
        citations = []
        payload = {
            "input": input_payload if isinstance(input_payload, (dict, list, str, int, float, bool)) else str(input_payload),
            "output": output_payload if isinstance(output_payload, (dict, list, str, int, float, bool)) else str(output_payload),
            "metrics": metrics or {},
        }
        if stage == "generate":
            prompt_payload = {"context": input_payload or {}, "response_preview": str(output_payload or "")[:1000]}
        if stage == "retrieve":
            retrieval_payload = output_payload if isinstance(output_payload, dict) else {"result": output_payload}
        if stage == "verify":
            out_text = str(output_payload or "")
            citations = sorted(set(re.findall(r"\[(?:Chunk\s+\d+|S\d+(?:\s*,\s*S\d+)*)\]", out_text)))
            validator_payload = {
                "outcome": "pass" if (metrics or {}).get("citation_pass_rate", 0) >= 0.6 else "needs_review",
                "metrics": metrics or {},
            }
        event = TraceEvent(
            run_id=run_id,
            event_id=str(uuid.uuid4()),
            stage=stage,
            event_type="span",
            timestamp=datetime.now().isoformat(timespec="seconds"),
            iteration=int(iteration or 0),
            latency_ms=int(latency_ms or 0),
            prompt=prompt_payload,
            retrieval_results=retrieval_payload,
            citations_chosen=citations,
            validator=validator_payload,
            payload=payload,
        )
        self._append_trace_event(run_id, event)

    def _trace_from_event(self, run_id, event_name, payload):
        event_name = str(event_name)
        stage = {
            "ingestion": "ingest",
            "retrieval": "retrieve",
            "selection": "select",
            "generation": "generate",
            "verification": "verify",
            "rerank": "rerank",
        }.get(event_name, event_name)
        payload = payload or {}
        citations = []
        validator_payload = None
        retrieval_payload = None
        tool_calls = []
        if stage == "retrieve":
            retrieval_payload = {
                "queries": payload.get("queries", []),
                "dense_k": payload.get("dense_k"),
                "lexical_k": payload.get("lexical_k"),
                "fused_k": payload.get("fused_k"),
            }
            tool_calls = [
                {"tool": "vector_retriever", "args": {"k": payload.get("dense_k")}},
                {"tool": "lexical_search", "args": {"k": payload.get("lexical_k")}},
            ]
        if stage == "verify":
            validator_payload = {
                "claims_dropped": payload.get("claims_dropped", 0),
                "claims_cited": payload.get("claims_cited", 0),
            }
        if stage == "generate":
            citations = payload.get("citations", []) if isinstance(payload.get("citations"), list) else []
        event = TraceEvent(
            run_id=run_id,
            event_id=str(uuid.uuid4()),
            stage=stage,
            event_type="event",
            timestamp=datetime.now().isoformat(timespec="seconds"),
            iteration=int(payload.get("iter", 0) or 0),
            latency_ms=payload.get("latency_ms"),
            tool_calls=tool_calls,
            retrieval_results=retrieval_payload,
            citations_chosen=citations,
            validator=validator_payload,
            payload=dict(payload),
        )
        self._append_trace_event(run_id, event)

    @staticmethod
    def _payload_size_hint(payload):
        if payload is None:
            return 0
        if isinstance(payload, (str, bytes, list, tuple, dict, set)):
            try:
                return len(payload)
            except Exception:
                pass
        try:
            return len(json.dumps(payload, ensure_ascii=False, default=str))
        except Exception:
            return len(str(payload))

    def _record_agent_lightning_span(self, run_id, node, iteration, started_at, input_payload=None, output_payload=None, metrics=None):
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        stage = self._trace_stage_from_node(node)
        payload = {
            "node": str(node),
            "latency_ms": latency_ms,
            "input": input_payload if isinstance(input_payload, (dict, list, str, int, float, bool)) else str(input_payload),
            "output": output_payload if isinstance(output_payload, (dict, list, str, int, float, bool)) else str(output_payload),
            "metrics": metrics or {},
        }
        self._record_trace_stage(run_id, stage, "span", payload=payload, iteration=iteration)
        if self._agent_lightning_telemetry_enabled():
            run_payload = self._agent_lightning_runs_by_id.get(run_id)
            if not run_payload:
                return
            event = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "run_id": run_id,
                "event": "node_span",
                "node": str(node),
                "iter": int(iteration or 0),
                "latency_ms": latency_ms,
                "input_size": int(self._payload_size_hint(input_payload)),
                "output_size": int(self._payload_size_hint(output_payload)),
                "metrics": metrics or {},
            }
            run_payload.setdefault("trajectory_events", []).append(event)
            self._trace_from_span(
                run_id,
                node,
                iteration,
                latency_ms,
                input_payload=input_payload,
                output_payload=output_payload,
                metrics=metrics,
            )

    def _start_agent_lightning_run(self, run_id, query):
        if not self._agent_lightning_telemetry_enabled():
            return
        run_payload = {
            "run_id": run_id,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "query": query,
            "knobs": {
                "agentic_mode": bool(self.agentic_mode.get()),
                "agentic_max_iterations": int(self.agentic_max_iterations.get()),
                "retrieval_k": int(self.retrieval_k.get()),
                "final_k": int(self.final_k.get()),
                "search_type": str(self.search_type.get()),
                "mmr_lambda": float(self.mmr_lambda.get()),
                "use_sub_queries": bool(self.use_sub_queries.get()),
                "use_reranker": bool(self.use_reranker.get()),
                "enable_structured_incidents": bool(self.enable_structured_incidents.get()),
                "output_style": str(self.output_style.get()),
                "llm_provider": str(self.llm_provider.get()),
                "llm_model": str(self._resolve_llm_model()),
            },
            "events": [],
            "trajectory_events": [],
            "trace_events": [],
            "trajectory_path": "",
            "example": {
                "query": query,
                "incidents": [],
                "final_output": "",
            },
        }
        self._agent_lightning_runs_by_id[run_id] = run_payload
        self._agent_lightning_trace_events_by_run[run_id] = []

    def _record_agent_lightning_event(self, run_id, event, payload):
        payload = payload or {}
        stage = {
            "retrieval": "retrieval",
            "verification": "validation",
            "generation": "final_answer",
            "selection": "rerank",
        }.get(str(event), str(event))
        self._record_trace_stage(run_id, stage, str(event), payload=payload, iteration=payload.get("iter", 0))
        if self._agent_lightning_telemetry_enabled():
            run_payload = self._agent_lightning_runs_by_id.get(run_id)
            if not run_payload:
                return
            record = {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "run_id": run_id,
                "event": event,
                **payload,
            }
            run_payload["events"].append(record)
            self._trace_from_event(run_id, event, payload)

    def _build_incident_export_payload(self, docs):
        incidents = {}
        month_buckets = set()
        dated_count = 0
        undated_count = 0
        for doc in docs or []:
            metadata = getattr(doc, "metadata", {}) or {}
            incident_key = metadata.get("incident_key") or self._build_incident_key(doc)
            month_bucket = str(metadata.get("month_bucket") or "undated").strip() or "undated"
            if month_bucket != "undated":
                month_buckets.add(month_bucket)
                dated_count += 1
            else:
                undated_count += 1
            item = incidents.setdefault(
                incident_key,
                {
                    "incident_key": incident_key,
                    "month_bucket": month_bucket,
                    "channel": str(metadata.get("channel_type") or self._extract_channel(getattr(doc, "page_content", "") or "")),
                    "role": str(metadata.get("role_kind") or self._extract_role_kind(doc)),
                    "chunk_ids": [],
                },
            )
            chunk_id = str(metadata.get("chunk_id") or "")
            if chunk_id and chunk_id not in item["chunk_ids"]:
                item["chunk_ids"].append(chunk_id)
        return {
            "incidents": list(incidents.values()),
            "incident_count": len(incidents),
            "dated_count": dated_count,
            "undated_count": undated_count,
            "months_covered": sorted(month_buckets, key=self._month_sort_key),
        }

    @staticmethod
    def _count_claim_like_sentences(text):
        parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+", str(text or "")) if p.strip()]
        return len(parts)

    @staticmethod
    def _count_citations(text):
        return len(re.findall(r"\[(?:Chunk\s+\d+|S\d+(?:\s*,\s*S\d+)*)\]", str(text or "")))

    def _finalize_agent_lightning_run(self, run_id, final_docs, final_output):
        if not self._agent_lightning_telemetry_enabled():
            return
        run_payload = self._agent_lightning_runs_by_id.get(run_id)
        if not run_payload:
            return
        incident_payload = self._build_incident_export_payload(final_docs)
        run_payload["example"]["incidents"] = incident_payload["incidents"]
        run_payload["example"]["final_output"] = final_output
        run_payload["example"]["sources"] = [
            {
                "chunk_id": str((getattr(doc, "metadata", {}) or {}).get("chunk_id") or ""),
                "source": str((getattr(doc, "metadata", {}) or {}).get("source") or (getattr(doc, "metadata", {}) or {}).get("file_path") or "unknown"),
            }
            for doc in (final_docs or [])
        ]
        trajectory_path = ""
        try:
            base_dir = os.path.dirname(os.path.abspath(self._get_telemetry_log_path()))
            trajectory_path = os.path.join(base_dir, f"agent_lightning_trajectory_{run_id}.jsonl")
            with open(trajectory_path, "w", encoding="utf-8") as handle:
                for event in run_payload.get("trajectory_events", []):
                    handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
                final_record = {
                    "timestamp": datetime.now().isoformat(timespec="seconds"),
                    "run_id": run_id,
                    "event": "trajectory_final",
                    "final_answer": final_output,
                    "sources": run_payload["example"].get("sources", []),
                    "incident_count": int(incident_payload.get("incident_count", 0)),
                }
                handle.write(json.dumps(final_record, ensure_ascii=False, sort_keys=True) + "\n")
            run_payload["trajectory_path"] = trajectory_path
            self.log(f"Agent Lightning trajectory saved: {trajectory_path}")
        except Exception as exc:
            self.log(f"Agent Lightning trajectory export skipped ({exc}).")
        trace_events = list(self._agent_lightning_trace_events_by_run.get(run_id, []))
        run_payload["trace_events"] = trace_events
        summary = {
            "run_id": run_id,
            "query": run_payload.get("query", ""),
            "final_output": str(final_output or ""),
            "trace_event_count": len(trace_events),
            "created_at": run_payload.get("created_at"),
        }
        self._agent_lightning_run_summaries.append(summary)
        if len(self._agent_lightning_run_summaries) > 100:
            self._agent_lightning_run_summaries = self._agent_lightning_run_summaries[-100:]
        self._agent_lightning_last_exportable_run = run_payload

    def _write_jsonl(self, path, records):
        with open(path, "w", encoding="utf-8") as handle:
            for record in records or []:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def _compute_offline_eval_metrics(self, run_payload):
        trace_events = list((run_payload or {}).get("trace_events") or [])
        verifier_events = [e for e in trace_events if e.get("stage") == "verify"]
        generation_events = [e for e in trace_events if e.get("stage") == "generate"]
        retrieval_events = [e for e in trace_events if e.get("stage") == "retrieve"]
        citation_total = 0
        for event in verifier_events:
            validator = event.get("validator") or {}
            metrics = validator.get("metrics") or {}
            citation_total += float(metrics.get("citation_pass_rate", 0) or 0)
        avg_citation_pass_rate = citation_total / max(1, len(verifier_events))
        avg_generation_latency = sum(int(e.get("latency_ms") or 0) for e in generation_events) / max(1, len(generation_events))
        return {
            "prompt_count": 1,
            "trace_event_count": len(trace_events),
            "retrieval_event_count": len(retrieval_events),
            "generation_event_count": len(generation_events),
            "verification_event_count": len(verifier_events),
            "avg_citation_pass_rate": round(avg_citation_pass_rate, 4),
            "avg_generation_latency_ms": int(avg_generation_latency),
        }

    def export_run_as_agent_lightning_dataset(self):
        if not self._agent_lightning_last_exportable_run:
            messagebox.showinfo(
                "AgentLightning export",
                "No telemetry-enabled run available yet. Enable Agent Lightning traces and run a query first.",
            )
            return
        parent_dir = filedialog.askdirectory(title="Select export directory")
        if not parent_dir:
            return
        run_payload = self._agent_lightning_last_exportable_run
        run_id = run_payload.get("run_id")
        folder_name = f"agent_lightning_dataset_{run_id}"
        export_dir = os.path.join(parent_dir, folder_name)
        try:
            os.makedirs(export_dir, exist_ok=True)
            trace_events = list(run_payload.get("trace_events") or self._agent_lightning_trace_events_by_run.get(run_id, []))
            local_trace_events = self.trace_store.read_run(run_id)
            merged_trace = trace_events + [event for event in local_trace_events if event not in trace_events]
            self._write_jsonl(os.path.join(export_dir, "trace_events.jsonl"), merged_trace)
            self._write_jsonl(os.path.join(export_dir, "runs.jsonl"), run_payload.get("events", []))
            with sqlite3.connect(self.session_db_path) as conn:
                conn.row_factory = sqlite3.Row
                feedback_rows = conn.execute(
                    "SELECT feedback_id, session_id, run_id, vote, note, ts FROM message_feedback WHERE run_id = ? ORDER BY ts ASC",
                    (run_id,),
                ).fetchall()
            self._write_jsonl(os.path.join(export_dir, "feedback.jsonl"), [dict(row) for row in feedback_rows])
            example_payload = {"run_id": run_id, **(run_payload.get("example") or {})}
            self._write_jsonl(os.path.join(export_dir, "examples.jsonl"), [example_payload])
            metrics = self._compute_offline_eval_metrics(run_payload)
            manifest = {
                "manifest_version": 1,
                "dataset_type": "agent_lightning_trace_dataset",
                "run_id": run_id,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "query": run_payload.get("query", ""),
                "files": {
                    "config": "config.json",
                    "runs": "runs.jsonl",
                    "examples": "examples.jsonl",
                    "trace_events": "trace_events.jsonl",
                    "eval_metrics": "eval_metrics.json",
                    "feedback": "feedback.jsonl",
                },
                "counts": {
                    "events": len(run_payload.get("events", [])),
                    "trajectory_events": len(run_payload.get("trajectory_events", [])),
                    "trace_events": len(merged_trace),
                },
            }
            with open(os.path.join(export_dir, "config.json"), "w", encoding="utf-8") as handle:
                json.dump(run_payload.get("knobs", {}), handle, indent=2, ensure_ascii=False, sort_keys=True)
            with open(os.path.join(export_dir, "manifest.json"), "w", encoding="utf-8") as handle:
                json.dump(manifest, handle, indent=2, ensure_ascii=False, sort_keys=True)
            with open(os.path.join(export_dir, "eval_metrics.json"), "w", encoding="utf-8") as handle:
                json.dump(metrics, handle, indent=2, ensure_ascii=False, sort_keys=True)
            self.log(f"AgentLightning dataset exported to: {export_dir}")
            messagebox.showinfo("AgentLightning export", f"Exported dataset to:\n{export_dir}")
        except Exception as exc:
            messagebox.showerror("AgentLightning export", f"Export failed:\n{exc}")

    def export_eval_set(self):
        if not self._agent_lightning_run_summaries:
            messagebox.showinfo(
                "Export Eval Set",
                "No telemetry-enabled runs are available yet. Enable Agent Lightning traces and run at least one query first.",
            )
            return
        parent_dir = filedialog.askdirectory(title="Select eval export directory")
        if not parent_dir:
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_dir = os.path.join(parent_dir, f"agent_lightning_eval_set_{timestamp}")
        try:
            os.makedirs(export_dir, exist_ok=True)
            eval_examples = []
            suite_metrics = {
                "run_count": 0,
                "avg_trace_events": 0,
                "avg_citation_pass_rate": 0.0,
                "avg_generation_latency_ms": 0,
            }
            total_trace_events = 0
            total_citation = 0.0
            total_generation_latency = 0
            for summary in self._agent_lightning_run_summaries:
                run_id = summary.get("run_id")
                run_payload = self._agent_lightning_runs_by_id.get(run_id) or {}
                metrics = self._compute_offline_eval_metrics(run_payload)
                eval_examples.append(
                    {
                        "run_id": run_id,
                        "prompt": summary.get("query", ""),
                        "response": summary.get("final_output", ""),
                        "metrics": metrics,
                    }
                )
                suite_metrics["run_count"] += 1
                total_trace_events += int(metrics.get("trace_event_count", 0))
                total_citation += float(metrics.get("avg_citation_pass_rate", 0.0))
                total_generation_latency += int(metrics.get("avg_generation_latency_ms", 0))
            count = max(1, suite_metrics["run_count"])
            suite_metrics["avg_trace_events"] = int(total_trace_events / count)
            suite_metrics["avg_citation_pass_rate"] = round(total_citation / count, 4)
            suite_metrics["avg_generation_latency_ms"] = int(total_generation_latency / count)
            self._write_jsonl(os.path.join(export_dir, "eval_set.jsonl"), eval_examples)
            with open(os.path.join(export_dir, "metrics.json"), "w", encoding="utf-8") as handle:
                json.dump(suite_metrics, handle, indent=2, ensure_ascii=False, sort_keys=True)
            with open(os.path.join(export_dir, "manifest.json"), "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "manifest_version": 1,
                        "dataset_type": "agent_lightning_eval_set",
                        "created_at": datetime.now().isoformat(timespec="seconds"),
                        "files": {"eval_set": "eval_set.jsonl", "metrics": "metrics.json"},
                        "run_count": suite_metrics["run_count"],
                    },
                    handle,
                    indent=2,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            self.log(f"Eval set exported to: {export_dir}")
            messagebox.showinfo("Export Eval Set", f"Exported eval set to:\n{export_dir}")
        except Exception as exc:
            messagebox.showerror("Export Eval Set", f"Export failed:\n{exc}")

    def _ensure_lexical_db(self):
        db_path = self._get_lexical_db_path()
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chunks(
                        chunk_id TEXT PRIMARY KEY,
                        source TEXT,
                        role TEXT,
                        evidence_kind TEXT,
                        text TEXT,
                        meta_json TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts
                    USING fts5(text, content='chunks', content_rowid='rowid')
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS concept_cards(
                        id TEXT PRIMARY KEY,
                        title TEXT,
                        kind TEXT,
                        content_json TEXT,
                        source_refs_json TEXT,
                        card_text TEXT,
                        ingest_id TEXT,
                        created_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS concept_cards_fts
                    USING fts5(title, kind, card_text, content='concept_cards', content_rowid='rowid')
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS comprehension_artifacts(
                        id TEXT PRIMARY KEY,
                        ingest_id TEXT,
                        artifact_type TEXT,
                        name TEXT,
                        text TEXT,
                        definition TEXT,
                        aliases_json TEXT,
                        chapter TEXT,
                        support_quote TEXT,
                        source_locator TEXT,
                        why_it_matters TEXT,
                        content_json TEXT,
                        created_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS summary_tree_nodes(
                        id TEXT PRIMARY KEY,
                        ingest_id TEXT,
                        tree_level INTEGER,
                        digest_scope TEXT,
                        node_title TEXT,
                        source TEXT,
                        summary_text TEXT,
                        metadata_json TEXT,
                        created_at TEXT
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS comprehension_artifacts_fts
                    USING fts5(name, text, definition, support_quote, why_it_matters, content='comprehension_artifacts', content_rowid='rowid')
                    """
                )
                conn.commit()
            self.lexical_db_path = db_path
            self.lexical_db_available = True
            return True
        except Exception as exc:
            self.lexical_db_path = db_path
            self.lexical_db_available = False
            self.log(f"Lexical DB unavailable; skipping SQLite sidecar. ({exc})")
            return False

    @staticmethod
    def _chunk_pk(metadata):
        ingest_id = metadata.get("ingest_id")
        chunk_id = metadata.get("chunk_id")
        if ingest_id is None or chunk_id is None:
            return None
        return f"{ingest_id}:{chunk_id}"

    def _doc_identity_key(self, doc):
        metadata = getattr(doc, "metadata", {}) or {}
        chunk_pk = self._chunk_pk(metadata)
        if chunk_pk:
            return chunk_pk
        chunk_db_id = metadata.get("chunk_db_id")
        if chunk_db_id:
            return str(chunk_db_id)
        content = (getattr(doc, "page_content", "") or "").strip()
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _upsert_lexical_chunks(self, docs):
        if not self._ensure_lexical_db():
            return False
        try:
            with sqlite3.connect(self.lexical_db_path) as conn:
                for doc in docs:
                    metadata = (doc.metadata or {}).copy()
                    chunk_pk = self._chunk_pk(metadata)
                    if not chunk_pk:
                        continue
                    source = metadata.get("source") or ""
                    role = metadata.get("role") or metadata.get("speaker_role") or ""
                    evidence_kind = metadata.get("evidence_kind") or ""
                    text = doc.page_content or ""
                    meta_json = json.dumps(metadata, ensure_ascii=False, sort_keys=True)
                    conn.execute(
                        """
                        INSERT INTO chunks(chunk_id, source, role, evidence_kind, text, meta_json)
                        VALUES(?, ?, ?, ?, ?, ?)
                        ON CONFLICT(chunk_id) DO UPDATE SET
                            source=excluded.source,
                            role=excluded.role,
                            evidence_kind=excluded.evidence_kind,
                            text=excluded.text,
                            meta_json=excluded.meta_json
                        """,
                        (chunk_pk, source, role, evidence_kind, text, meta_json),
                    )
                conn.execute("INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild')")
                conn.commit()
            self.lexical_db_available = True
            return True
        except Exception as exc:
            self.lexical_db_available = False
            self.log(f"Lexical chunk upsert skipped (SQLite/FTS5 issue). ({exc})")
            return False

    def _depth_chunk_limit(self):
        depth = str(self.comprehension_extraction_depth.get() or "Standard").strip()
        if depth == "Light":
            return 4
        if depth == "Deep":
            return 14
        return 8

    @staticmethod
    def _truncate_for_card(text, max_chars=700):
        compact = re.sub(r"\s+", " ", str(text or "")).strip()
        if len(compact) <= max_chars:
            return compact
        return compact[: max_chars - 1].rstrip() + "…"

    def _card_text_from_item(self, item):
        title = str(item.get("title") or "").strip()
        kind = str(item.get("kind") or "").strip()
        content = item.get("content") or {}
        if isinstance(content, dict):
            content_blob = " ".join(str(v) for v in content.values() if v)
        else:
            content_blob = str(content)
        return self._truncate_for_card(f"{kind}: {title}. {content_blob}", max_chars=1200)

    def _upsert_concept_cards(self, ingest_id, cards):
        if not cards or not self._ensure_lexical_db():
            return 0
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.lexical_db_path) as conn:
            for card in cards:
                conn.execute(
                    """
                    INSERT INTO concept_cards(id, title, kind, content_json, source_refs_json, card_text, ingest_id, created_at)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title,
                        kind=excluded.kind,
                        content_json=excluded.content_json,
                        source_refs_json=excluded.source_refs_json,
                        card_text=excluded.card_text,
                        ingest_id=excluded.ingest_id,
                        created_at=excluded.created_at
                    """,
                    (
                        card["id"],
                        card.get("title", ""),
                        card.get("kind", ""),
                        json.dumps(card.get("content") or {}, ensure_ascii=False, sort_keys=True),
                        json.dumps(card.get("source_refs") or [], ensure_ascii=False, sort_keys=True),
                        card.get("card_text", ""),
                        ingest_id,
                        now_iso,
                    ),
                )
            conn.execute("INSERT INTO concept_cards_fts(concept_cards_fts) VALUES('rebuild')")
            conn.commit()
        return len(cards)

    def _write_comprehension_jsonl(self, ingest_id, artifacts):
        if not ingest_id or not artifacts:
            return ""
        base_dir = self.selected_index_path or self._get_chroma_persist_root()
        out_dir = os.path.join(base_dir, "comprehension")
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"comprehension_{ingest_id}.jsonl")
        with open(out_path, "w", encoding="utf-8") as handle:
            for item in artifacts:
                handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        return out_path

    def _upsert_comprehension_artifacts(self, ingest_id, artifacts):
        if not artifacts or not self._ensure_lexical_db():
            return 0
        now_iso = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.lexical_db_path) as conn:
            for item in artifacts:
                content = item.get("content") or {}
                conn.execute(
                    """
                    INSERT INTO comprehension_artifacts(
                        id, ingest_id, artifact_type, name, text, definition, aliases_json, chapter,
                        support_quote, source_locator, why_it_matters, content_json, created_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        ingest_id=excluded.ingest_id,
                        artifact_type=excluded.artifact_type,
                        name=excluded.name,
                        text=excluded.text,
                        definition=excluded.definition,
                        aliases_json=excluded.aliases_json,
                        chapter=excluded.chapter,
                        support_quote=excluded.support_quote,
                        source_locator=excluded.source_locator,
                        why_it_matters=excluded.why_it_matters,
                        content_json=excluded.content_json,
                        created_at=excluded.created_at
                    """,
                    (
                        item.get("id") or str(uuid.uuid4()),
                        ingest_id,
                        item.get("artifact_type", ""),
                        item.get("name", ""),
                        item.get("text", ""),
                        item.get("definition", ""),
                        json.dumps(item.get("aliases") or [], ensure_ascii=False),
                        item.get("chapter", ""),
                        item.get("support_quote", ""),
                        item.get("source_locator", ""),
                        item.get("why_it_matters", ""),
                        json.dumps(content, ensure_ascii=False, sort_keys=True),
                        now_iso,
                    ),
                )
            conn.execute("INSERT INTO comprehension_artifacts_fts(comprehension_artifacts_fts) VALUES('rebuild')")
            conn.commit()
        return len(artifacts)

    def search_comprehension_artifacts(self, query: str, k: int = 12):
        if not query or k <= 0 or not self._ensure_lexical_db():
            return []
        safe_q = self._fts5_sanitize_query(query)
        if not safe_q:
            return []
        with sqlite3.connect(self.lexical_db_path) as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.artifact_type, c.name, c.text, c.definition, c.aliases_json,
                       c.chapter, c.support_quote, c.source_locator, c.why_it_matters, c.content_json
                FROM comprehension_artifacts_fts
                JOIN comprehension_artifacts c ON c.rowid = comprehension_artifacts_fts.rowid
                WHERE comprehension_artifacts_fts MATCH ?
                ORDER BY bm25(comprehension_artifacts_fts) ASC
                LIMIT ?
                """,
                (safe_q, int(k)),
            ).fetchall()
        out = []
        for row in rows:
            out.append(
                {
                    "id": row[0],
                    "artifact_type": row[1],
                    "name": row[2] or "",
                    "text": row[3] or "",
                    "definition": row[4] or "",
                    "aliases": json.loads(row[5] or "[]"),
                    "chapter": row[6] or "",
                    "support_quote": row[7] or "",
                    "source_locator": row[8] or "",
                    "why_it_matters": row[9] or "",
                    "content": json.loads(row[10] or "{}"),
                }
            )
        return out

    def _is_comprehension_first_query(self, query_text):
        text = (query_text or "").lower()
        if not text:
            return False
        triggers = ("summarise", "summarize", "teach me", "blinkist", "key ideas", "key takeaways", "expand key idea", "zoom")
        return any(token in text for token in triggers)

    def _render_comprehension_context(self, artifacts):
        if not artifacts:
            return ""
        lines = ["COMPREHENSION_ARTIFACTS (prefer these first, then corroborate with raw context):"]
        for item in artifacts:
            kind = str(item.get("artifact_type") or "").strip()
            loc = str(item.get("source_locator") or "").strip() or "unknown"
            if kind == "concept":
                lines.append(
                    f"- Concept(name={item.get('name','')}, definition={item.get('definition','')}, aliases={item.get('aliases',[])}, chapter={item.get('chapter','')}, source_locator={loc})"
                )
            elif kind == "claim":
                lines.append(
                    f"- Claim(text={item.get('text','')}, support_quote={item.get('support_quote','')}, source_locator={loc})"
                )
            elif kind == "takeaway":
                lines.append(
                    f"- Takeaway(text={item.get('text','')}, why_it_matters={item.get('why_it_matters','')}, source_locator={loc})"
                )
            else:
                lines.append(f"- {kind.title()}: {item.get('text') or item.get('name')} (source_locator={loc})")
        return "\n".join(lines)

    def search_concepts(self, query: str, k: int = 8):
        if not query or k <= 0 or not self._ensure_lexical_db():
            return []
        safe_q = self._fts5_sanitize_query(query)
        if not safe_q:
            return []
        with sqlite3.connect(self.lexical_db_path) as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.title, c.kind, c.content_json, c.source_refs_json, c.card_text
                FROM concept_cards_fts
                JOIN concept_cards c ON c.rowid = concept_cards_fts.rowid
                WHERE concept_cards_fts MATCH ?
                ORDER BY bm25(concept_cards_fts) ASC
                LIMIT ?
                """,
                (safe_q, int(k)),
            ).fetchall()
        results = []
        for row in rows:
            results.append(
                {
                    "id": row[0],
                    "title": row[1],
                    "kind": row[2],
                    "content": json.loads(row[3] or "{}"),
                    "source_refs": json.loads(row[4] or "[]"),
                    "card_text": row[5] or "",
                }
            )
        return results

    def _build_outline_cards(self, docs, ingest_id, doc_title):
        outline_items = []
        seen = set()
        for doc in docs:
            md = getattr(doc, "metadata", {}) or {}
            chapter = str(md.get("chapter_title") or "").strip()
            section = str(md.get("section_title") or "").strip()
            key = (md.get("chapter_idx"), chapter, md.get("section_idx"), section)
            if key in seen:
                continue
            seen.add(key)
            if chapter:
                title = f"Chapter {md.get('chapter_idx') or '?'}: {chapter}" if md.get("chapter_idx") else chapter
                outline_items.append({"title": title, "kind": "outline.chapter", "content": {"chapter": chapter, "chapter_idx": md.get("chapter_idx")}})
            if section:
                section_title = f"Section {md.get('section_idx') or '?'}: {section}" if md.get("section_idx") else section
                outline_items.append({"title": section_title, "kind": "outline.section", "content": {"chapter": chapter, "section": section, "section_idx": md.get("section_idx")}})
        if not outline_items:
            outline_items.append({"title": doc_title or "Document", "kind": "outline.document", "content": {"title": doc_title or "Document"}})
        cards = []
        for item in outline_items:
            cards.append({
                "id": str(uuid.uuid4()),
                "title": item["title"],
                "kind": item["kind"],
                "content": item["content"],
                "source_refs": [],
                "card_text": self._card_text_from_item(item),
            })
        return cards

    def _extract_with_langextract(self, text_payload, prompt):
        if langextract is None:
            return []
        try:
            result = langextract.extract(text_payload, prompt=prompt)
            if isinstance(result, dict):
                return result.get("items") or result.get("extractions") or []
            if isinstance(result, list):
                return result
        except Exception as exc:
            self.log(f"Comprehension langextract pass failed; using heuristic fallback. ({exc})")
        return []

    def _build_comprehension_cards(self, docs, ingest_id, doc_title, source_map):
        depth_limit = self._depth_chunk_limit()
        sampled_docs = list(docs[:depth_limit]) if docs else []
        if self.comprehension_extraction_depth.get() == "Deep":
            sampled_docs = list(docs)
        text_payload = [
            {
                "id": str((getattr(doc, "metadata", {}) or {}).get("chunk_id") or i + 1),
                "text": self._truncate_for_card(getattr(doc, "page_content", ""), max_chars=2200),
            }
            for i, doc in enumerate(sampled_docs)
        ]

        cards = self._build_outline_cards(docs, ingest_id, doc_title)

        concept_items = self._extract_with_langextract(
            text_payload,
            "Extract key concepts as JSON list entries with fields: term, definition, explanation.",
        )
        claim_items = self._extract_with_langextract(
            text_payload,
            "Extract key claims/arguments with fields: claim, support, counterpoints.",
        )
        quote_items = self._extract_with_langextract(
            text_payload,
            "Extract memorable quotes with fields: quote, why_memorable.",
        )

        if not concept_items:
            for doc in sampled_docs[: max(2, depth_limit // 2)]:
                first_sentence = re.split(r"(?<=[.!?])\s+", getattr(doc, "page_content", "") or "", maxsplit=1)[0]
                if not first_sentence:
                    continue
                concept_items.append(
                    {
                        "term": self._truncate_for_card(first_sentence, max_chars=70),
                        "definition": self._truncate_for_card(getattr(doc, "page_content", ""), max_chars=220),
                        "explanation": "Heuristic concept extracted from representative chunk.",
                    }
                )
        if not claim_items:
            for doc in sampled_docs[: max(2, depth_limit // 3)]:
                first_sentence = re.split(r"(?<=[.!?])\s+", getattr(doc, "page_content", "") or "", maxsplit=1)[0]
                if first_sentence:
                    claim_items.append(
                        {
                            "claim": self._truncate_for_card(first_sentence, max_chars=220),
                            "support": "Grounded in source chunk context.",
                            "counterpoints": "Not explicitly stated.",
                        }
                    )
        if not quote_items:
            quote_re = re.compile(r'([\"“][^\"”]{30,220}[\"”])')
            for doc in sampled_docs:
                match = quote_re.search(getattr(doc, "page_content", "") or "")
                if match:
                    quote_items.append({"quote": match.group(1), "why_memorable": "Direct phrasing from source."})
                    if len(quote_items) >= 6:
                        break

        def _source_refs_for_doc(doc):
            md = (getattr(doc, "metadata", {}) or {}).copy()
            source_id = self._build_source_locator(md, getattr(doc, "page_content", "") or "").source_id
            source_entry = (source_map or {}).get(source_id, {})
            return [{
                "sid": source_entry.get("sid", ""),
                "source_id": source_id,
                "locator": source_entry.get("locator") or md.get("source_locator") or "",
                "chunk_id": md.get("chunk_id"),
            }]

        anchor_docs = sampled_docs or docs[:1]
        for idx, item in enumerate(concept_items[:40]):
            doc = anchor_docs[idx % len(anchor_docs)] if anchor_docs else None
            source_refs = _source_refs_for_doc(doc) if doc else []
            content = {
                "term": str(item.get("term") or item.get("title") or "").strip(),
                "definition": str(item.get("definition") or "").strip(),
                "explanation": str(item.get("explanation") or "").strip(),
            }
            title = content["term"] or f"Concept {idx + 1}"
            card = {"title": title, "kind": "concept", "content": content}
            cards.append({"id": str(uuid.uuid4()), "title": title, "kind": "concept", "content": content, "source_refs": source_refs, "card_text": self._card_text_from_item(card)})

        for idx, item in enumerate(claim_items[:40]):
            doc = anchor_docs[idx % len(anchor_docs)] if anchor_docs else None
            source_refs = _source_refs_for_doc(doc) if doc else []
            content = {
                "claim": str(item.get("claim") or "").strip(),
                "support": str(item.get("support") or "").strip(),
                "counterpoints": str(item.get("counterpoints") or "").strip(),
            }
            title = self._truncate_for_card(content["claim"] or f"Claim {idx + 1}", max_chars=90)
            card = {"title": title, "kind": "claim", "content": content}
            cards.append({"id": str(uuid.uuid4()), "title": title, "kind": "claim", "content": content, "source_refs": source_refs, "card_text": self._card_text_from_item(card)})

        for idx, item in enumerate(quote_items[:20]):
            doc = anchor_docs[idx % len(anchor_docs)] if anchor_docs else None
            source_refs = _source_refs_for_doc(doc) if doc else []
            content = {
                "quote": str(item.get("quote") or "").strip(),
                "why_memorable": str(item.get("why_memorable") or "").strip(),
            }
            title = self._truncate_for_card(content["quote"] or f"Quote {idx + 1}", max_chars=90)
            card = {"title": title, "kind": "quote", "content": content}
            cards.append({"id": str(uuid.uuid4()), "title": title, "kind": "quote", "content": content, "source_refs": source_refs, "card_text": self._card_text_from_item(card)})

        return cards

    def _build_comprehension_artifacts(self, docs, ingest_id, source_map):
        depth_limit = self._depth_chunk_limit()
        sampled_docs = list(docs[:depth_limit]) if docs else []
        if self.comprehension_extraction_depth.get() == "Deep":
            sampled_docs = list(docs)
        text_payload = [
            {
                "id": str((getattr(doc, "metadata", {}) or {}).get("chunk_id") or i + 1),
                "text": self._truncate_for_card(getattr(doc, "page_content", ""), max_chars=2200),
            }
            for i, doc in enumerate(sampled_docs)
        ]

        concept_items = self._extract_with_langextract(
            text_payload,
            "Extract concepts with fields: name, definition, aliases(list), chapter.",
        )
        claim_items = self._extract_with_langextract(
            text_payload,
            "Extract claims with fields: text, support_quote, source_locator.",
        )
        takeaway_items = self._extract_with_langextract(
            text_payload,
            "Extract blinkist-style takeaways with fields: text, why_it_matters, source_locator.",
        )
        framework_items = self._extract_with_langextract(
            text_payload,
            "Extract framework/process steps with fields: name, steps(list), source_locator.",
        )
        entity_items = self._extract_with_langextract(
            text_payload,
            "Extract entities/characters with fields: name, role, source_locator.",
        )

        if not concept_items:
            for doc in sampled_docs[:4]:
                md = getattr(doc, "metadata", {}) or {}
                sentence = re.split(r"(?<=[.!?])\s+", getattr(doc, "page_content", "") or "", maxsplit=1)[0]
                if sentence:
                    concept_items.append({"name": self._truncate_for_card(sentence, 80), "definition": self._truncate_for_card(doc.page_content, 220), "aliases": [], "chapter": md.get("chapter_title") or ""})
        if not claim_items:
            for doc in sampled_docs[:4]:
                sentence = re.split(r"(?<=[.!?])\s+", getattr(doc, "page_content", "") or "", maxsplit=1)[0]
                if sentence:
                    claim_items.append({"text": self._truncate_for_card(sentence, 220), "support_quote": self._truncate_for_card(sentence, 140)})
        if not takeaway_items:
            for doc in sampled_docs[:4]:
                sentence = re.split(r"(?<=[.!?])\s+", getattr(doc, "page_content", "") or "", maxsplit=1)[0]
                if sentence:
                    takeaway_items.append({"text": self._truncate_for_card(sentence, 180), "why_it_matters": "Captures a central idea from the book."})

        def _locator_for_doc(doc):
            md = (getattr(doc, "metadata", {}) or {}).copy()
            source_id = self._build_source_locator(md, getattr(doc, "page_content", "") or "").source_id
            source_entry = (source_map or {}).get(source_id, {})
            return source_entry.get("locator") or md.get("source_locator") or ""

        artifacts = []
        anchor_docs = sampled_docs or docs[:1]

        def _mk(kind, idx, payload):
            doc = anchor_docs[idx % len(anchor_docs)] if anchor_docs else None
            locator = _locator_for_doc(doc) if doc else str(payload.get("source_locator") or "")
            chapter = ""
            if doc:
                chapter = str(((getattr(doc, "metadata", {}) or {}).get("chapter_title") or "")).strip()
            return {
                "id": str(uuid.uuid4()),
                "ingest_id": ingest_id,
                "artifact_type": kind,
                "name": str(payload.get("name") or "").strip(),
                "text": str(payload.get("text") or payload.get("claim") or "").strip(),
                "definition": str(payload.get("definition") or "").strip(),
                "aliases": payload.get("aliases") or [],
                "chapter": str(payload.get("chapter") or chapter or "").strip(),
                "support_quote": str(payload.get("support_quote") or payload.get("support") or "").strip(),
                "source_locator": str(locator or "").strip(),
                "why_it_matters": str(payload.get("why_it_matters") or "").strip(),
                "content": payload,
            }

        for i, item in enumerate(concept_items[:40]):
            artifacts.append(_mk("concept", i, item if isinstance(item, dict) else {"name": str(item)}))
        for i, item in enumerate(claim_items[:40]):
            artifacts.append(_mk("claim", i, item if isinstance(item, dict) else {"text": str(item)}))
        for i, item in enumerate(takeaway_items[:40]):
            artifacts.append(_mk("takeaway", i, item if isinstance(item, dict) else {"text": str(item)}))
        for i, item in enumerate(framework_items[:20]):
            payload = item if isinstance(item, dict) else {"text": str(item)}
            payload.setdefault("text", str(payload.get("steps") or ""))
            artifacts.append(_mk("framework", i, payload))
        for i, item in enumerate(entity_items[:20]):
            payload = item if isinstance(item, dict) else {"name": str(item)}
            payload.setdefault("text", str(payload.get("role") or ""))
            artifacts.append(_mk("entity", i, payload))
        return artifacts

    @staticmethod
    def _fts5_query_tokens(q: str) -> list[str]:
        return re.findall(r"[a-z0-9]{2,}", (q or "").lower())[:16]

    def _fts5_sanitize_query(self, q: str) -> str:
        tokens = self._fts5_query_tokens(q)
        if not tokens:
            return ""
        return " OR ".join(f'"{token}"*' for token in tokens)

    def lexical_search(self, query: str, k: int) -> list[Document]:
        if not query or k <= 0:
            return []
        if not self.lexical_db_available:
            self._ensure_lexical_db()
        if not self.lexical_db_available or not self.lexical_db_path:
            return []
        safe_q = self._fts5_sanitize_query(query)
        if not safe_q:
            self.log("lexical skipped (empty after sanitize)")
            return []
        tokens = self._fts5_query_tokens(query)
        sql = """
                    SELECT
                        c.chunk_id,
                        c.source,
                        c.role,
                        c.evidence_kind,
                        c.text,
                        c.meta_json,
                        bm25(chunks_fts) AS lexical_score
                    FROM chunks_fts
                    JOIN chunks c ON c.rowid = chunks_fts.rowid
                    WHERE chunks_fts MATCH ?
                    ORDER BY lexical_score ASC
                    LIMIT ?
                    """
        try:
            with sqlite3.connect(self.lexical_db_path) as conn:
                rows = conn.execute(sql, (safe_q, int(k))).fetchall()
        except sqlite3.OperationalError as exc:
            msg = str(exc).lower()
            retryable = "fts5" in msg or "syntax" in msg
            if retryable and tokens:
                safe_q2 = " ".join(tokens)
                self.log(f"Lexical MATCH retry with conservative query. ({exc})")
                try:
                    with sqlite3.connect(self.lexical_db_path) as conn:
                        rows = conn.execute(sql, (safe_q2, int(k))).fetchall()
                except Exception as retry_exc:
                    retry_msg = str(retry_exc).lower()
                    if any(
                        marker in retry_msg
                        for marker in (
                            "no such table",
                            "unable to open database",
                            "not authorized",
                            "no such module: fts5",
                        )
                    ):
                        self.lexical_db_available = False
                    self.log(
                        f"Lexical search failed after retry; continuing without it. ({retry_exc})"
                    )
                    return []
            else:
                if any(
                    marker in msg
                    for marker in (
                        "no such table",
                        "unable to open database",
                        "not authorized",
                        "no such module: fts5",
                    )
                ):
                    self.lexical_db_available = False
                self.log(f"Lexical search failed; continuing without it. ({exc})")
                return []
        except Exception as exc:
            msg = str(exc).lower()
            if any(
                marker in msg
                for marker in (
                    "no such table",
                    "unable to open database",
                    "not authorized",
                    "no such module: fts5",
                )
            ):
                self.lexical_db_available = False
            self.log(f"Lexical search failed; continuing without it. ({exc})")
            return []

        docs = []
        for chunk_id, source, role, evidence_kind, text, meta_json, score in rows:
            metadata = {}
            if meta_json:
                try:
                    metadata = json.loads(meta_json)
                except json.JSONDecodeError:
                    metadata = {}
            if source and "source" not in metadata:
                metadata["source"] = source
            if role and "speaker_role" not in metadata:
                metadata["speaker_role"] = role
            if evidence_kind and "evidence_kind" not in metadata:
                metadata["evidence_kind"] = evidence_kind
            metadata["chunk_db_id"] = chunk_id
            metadata["lexical_score"] = float(score)
            metadata["lexical_match"] = True
            docs.append(self._document(page_content=text or "", metadata=metadata))
        return docs

    @staticmethod
    def _safe_file_stem(file_path):
        base_name = os.path.basename(file_path or "")
        stem = os.path.splitext(base_name)[0]
        safe_stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_")
        return safe_stem or "ingest"

    @staticmethod
    def _compact_chunk_ids(chunk_ids):
        filtered = sorted({int(cid) for cid in chunk_ids if str(cid).isdigit()})
        if not filtered:
            return ""
        ranges = []
        start = prev = filtered[0]
        for cid in filtered[1:]:
            if cid == prev + 1:
                prev = cid
                continue
            ranges.append((start, prev))
            start = prev = cid
        ranges.append((start, prev))
        return ",".join(
            str(start) if start == end else f"{start}-{end}"
            for start, end in ranges
        )

    @staticmethod
    def _expand_compact_chunk_ids(compact_ids):
        if not compact_ids:
            return set()
        ids = set()
        for part in str(compact_ids).split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                start, end = part.split("-", 1)
                if start.strip().isdigit() and end.strip().isdigit():
                    ids.update(range(int(start), int(end) + 1))
            elif part.isdigit():
                ids.add(int(part))
        return ids

    def _split_into_digest_windows(self, docs):
        windows = []
        total = len(docs)
        if total <= DIGEST_WINDOW_MAX:
            return [docs]
        idx = 0
        while idx < total:
            remaining = total - idx
            if remaining <= DIGEST_WINDOW_MAX:
                windows.append(docs[idx:])
                break
            take = min(DIGEST_WINDOW_TARGET, DIGEST_WINDOW_MAX)
            if remaining - take < DIGEST_WINDOW_MIN:
                take = remaining - DIGEST_WINDOW_MIN
            take = max(DIGEST_WINDOW_MIN, min(DIGEST_WINDOW_MAX, take))
            windows.append(docs[idx : idx + take])
            idx += take
        return windows

    def _group_chunks_for_digest(self, docs):
        groups = []
        buffer = []
        buffer_title = None

        def _flush():
            nonlocal buffer, buffer_title
            if not buffer:
                return
            if buffer_title and len(buffer) > DIGEST_WINDOW_MAX:
                windows = self._split_into_digest_windows(buffer)
            elif buffer_title:
                windows = [buffer]
            else:
                windows = self._split_into_digest_windows(buffer)
            for window in windows:
                groups.append((window, buffer_title))
            buffer = []
            buffer_title = None

        for doc in docs:
            section_title = (doc.metadata or {}).get("section_title")
            if section_title:
                if buffer and buffer_title != section_title:
                    _flush()
                buffer_title = section_title
                buffer.append(doc)
            else:
                if buffer and buffer_title:
                    _flush()
                buffer_title = None
                buffer.append(doc)
                if len(buffer) >= DIGEST_WINDOW_MAX:
                    _flush()

        _flush()
        return groups

    def _group_chunks_for_chapter_digest(self, docs):
        chapter_groups = {}
        for doc in docs:
            metadata = (doc.metadata or {})
            chapter_idx = metadata.get("chapter_idx")
            chapter_title = metadata.get("chapter_title")
            if chapter_idx is None and not chapter_title:
                continue
            key = (chapter_idx if chapter_idx is not None else "na", chapter_title or "Untitled chapter")
            chapter_groups.setdefault(key, []).append(doc)
        ordered_items = sorted(chapter_groups.items(), key=lambda item: item[0][0])
        return [((chapter_idx, chapter_title), chunk_docs) for (chapter_idx, chapter_title), chunk_docs in ordered_items]

    def _build_chapter_digest_documents(self, docs, ingest_id, source_basename, doc_title):
        chapter_groups = self._group_chunks_for_chapter_digest(docs)
        if not chapter_groups:
            return []
        llm = self._get_llm_with_temperature(0.2)
        digest_docs = []
        system_prompt = (
            "Summarize this chapter into concise bullet points for routing. "
            "Highlight topics, events, key actors, and chapter-specific decisions. "
            "Use bullets only with no introductory text."
        )
        for chapter_ordinal, ((chapter_idx, chapter_title), chunk_docs) in enumerate(chapter_groups, start=1):
            chunk_ids = [
                (doc.metadata or {}).get("chunk_id")
                for doc in chunk_docs
                if (doc.metadata or {}).get("chunk_id") is not None
            ]
            compact_ids = self._compact_chunk_ids(chunk_ids)
            digest_id = f"chapter-{ingest_id}-{chapter_ordinal}"
            group_text = "\n\n".join(doc.page_content for doc in chunk_docs[:DIGEST_WINDOW_MAX])
            response = llm.invoke(
                [
                    self._system_message(content=system_prompt),
                    self._human_message(content=f"Chapter title: {chapter_title}\n\nContent:\n{group_text}"),
                ]
            )
            metadata = {
                "doc_type": "chapter_digest",
                "digest_scope": "chapter",
                "tree_level": 1,
                "ingest_id": ingest_id,
                "source": source_basename,
                "digest_id": digest_id,
                "node_id": f"l1:{digest_id}",
                "parent_node_id": f"l2:{ingest_id}",
                "child_chunk_ids": compact_ids,
                "chapter_title": chapter_title,
            }
            if chapter_idx is not None and str(chapter_idx).isdigit():
                metadata["chapter_idx"] = int(chapter_idx)
            if doc_title:
                metadata["doc_title"] = doc_title
            digest_docs.append(self._document(page_content=response.content.strip(), metadata=metadata))
        return digest_docs

    def _build_chunk_summary_nodes(self, docs, ingest_id, source_basename, doc_title):
        chunk_nodes = []
        for doc in docs:
            metadata = (getattr(doc, "metadata", {}) or {}).copy()
            chunk_id = metadata.get("chunk_id")
            if chunk_id is None:
                continue
            chunk_text = str(getattr(doc, "page_content", "") or "").strip()
            first_sentence = re.split(r"(?<=[.!?])\s+", chunk_text, maxsplit=1)[0].strip()
            short_summary = self._truncate_for_card(first_sentence or chunk_text, max_chars=180)
            node_meta = {
                "doc_type": "chunk_summary",
                "digest_scope": "chunk",
                "tree_level": 0,
                "ingest_id": ingest_id,
                "source": source_basename,
                "digest_id": f"chunk-{ingest_id}-{chunk_id}",
                "node_id": f"l0:{ingest_id}:{chunk_id}",
                "parent_node_id": f"l1:{ingest_id}",
                "chunk_id": chunk_id,
                "chapter_idx": metadata.get("chapter_idx"),
                "chapter_title": metadata.get("chapter_title", ""),
                "section_idx": metadata.get("section_idx"),
                "section_title": metadata.get("section_title", ""),
            }
            if doc_title:
                node_meta["doc_title"] = doc_title
            chunk_nodes.append(self._document(page_content=short_summary, metadata=node_meta))
        return chunk_nodes

    def _build_part_digest_documents(self, chapter_digest_docs, ingest_id, source_basename, doc_title):
        if not chapter_digest_docs:
            return []
        grouped_parts = {}
        for chapter_doc in chapter_digest_docs:
            meta = getattr(chapter_doc, "metadata", {}) or {}
            part_idx = meta.get("part_idx")
            part_title = str(meta.get("part_title") or "").strip()
            if part_idx is None:
                chapter_idx = meta.get("chapter_idx")
                if isinstance(chapter_idx, int):
                    part_idx = ((chapter_idx - 1) // 5) + 1
            if part_idx is None and not part_title:
                part_idx = 1
            part_key = (part_idx if part_idx is not None else "na", part_title or f"Part {part_idx or 1}")
            grouped_parts.setdefault(part_key, []).append(chapter_doc)
        llm = self._get_llm_with_temperature(0.2)
        part_nodes = []
        for ordinal, ((part_idx, part_title), chapter_docs) in enumerate(sorted(grouped_parts.items(), key=lambda item: str(item[0][0])), start=1):
            rollup = []
            chapter_ids = []
            for chapter_doc in chapter_docs:
                md = getattr(chapter_doc, "metadata", {}) or {}
                chapter_ids.append(str(md.get("digest_id") or ""))
                rollup.append(f"- {md.get('chapter_title') or md.get('chapter_idx') or 'Chapter'}\n{chapter_doc.page_content}")
            response = llm.invoke(
                [
                    self._system_message(content="Summarize this part in 5-8 bullets focused on themes and progression. Bullets only."),
                    self._human_message(content=f"Part: {part_title}\n\nChapter summaries:\n" + "\n\n".join(rollup)),
                ]
            )
            metadata = {
                "doc_type": "part_digest",
                "digest_scope": "part",
                "tree_level": 2,
                "ingest_id": ingest_id,
                "source": source_basename,
                "digest_id": f"part-{ingest_id}-{ordinal}",
                "node_id": f"l2:part:{ingest_id}:{ordinal}",
                "parent_node_id": f"l3:{ingest_id}",
                "part_idx": int(part_idx) if str(part_idx).isdigit() else None,
                "part_title": part_title,
                "child_digest_ids": json.dumps([cid for cid in chapter_ids if cid]),
            }
            if doc_title:
                metadata["doc_title"] = doc_title
            part_nodes.append(self._document(page_content=str(response.content or "").strip(), metadata=metadata))
        return part_nodes

    @staticmethod
    def _is_short_factual_query(query):
        text = (query or "").strip()
        if not text:
            return False
        tokens = re.findall(r"\w+", text.lower())
        if len(tokens) > 14:
            return False
        factual_patterns = (
            r"^who\b",
            r"^what\s+(is|are|was|were|did|does|do)\b",
            r"^when\b",
            r"^where\b",
            r"^which\b",
            r"^define\b",
        )
        return any(re.search(pattern, text.lower()) for pattern in factual_patterns)

    def _resolve_retrieval_mode(self, query, resolved_settings, has_digest_store):
        configured_mode = (self.retrieval_mode.get() or "Flat (Chunks)").strip()
        mode_name = (resolved_settings or {}).get("mode", "")
        should_default_hierarchical = mode_name in {"Book Tutor", "Blinkist-style Summary"}
        is_short_factual = self._is_short_factual_query(query)
        if configured_mode == "Hierarchical (Digest→Chunk)":
            return "hierarchical"
        if should_default_hierarchical and not is_short_factual and has_digest_store:
            return "hierarchical"
        return "flat"

    def search_digests(self, query, k, digest_store, tree_level=None, digest_scope=None):
        if not digest_store or not query:
            return []
        retriever = digest_store.as_retriever(
            search_type=self.search_type.get(),
            search_kwargs={"k": max(1, int(k))},
        )
        digest_docs = retriever.invoke(query)
        filtered = []
        for doc in digest_docs:
            metadata = (getattr(doc, "metadata", {}) or {})
            if tree_level is not None and int(metadata.get("tree_level", 1)) != int(tree_level):
                continue
            if digest_scope and metadata.get("digest_scope") != digest_scope:
                continue
            filtered.append(doc)
        return filtered

    def expand_digest_to_chunks(self, digest_id, k_within, digest_store):
        if not digest_store or not digest_id:
            return []
        if not hasattr(self.vector_store, "_collection"):
            return []
        try:
            fetch = digest_store._collection.get(
                where={"digest_id": digest_id},
                include=["metadatas"],
                limit=1,
            )
        except Exception:
            return []
        metadatas = fetch.get("metadatas") or []
        if not metadatas:
            return []
        metadata = metadatas[0] or {}
        ingest_id = metadata.get("ingest_id")
        chunk_ids = sorted(self._expand_compact_chunk_ids(metadata.get("child_chunk_ids", "")))
        if not ingest_id or not chunk_ids:
            return []
        max_expand = max(1, int(k_within))
        try:
            result = self.vector_store._collection.get(
                where={"ingest_id": ingest_id},
                include=["documents", "metadatas"],
            )
        except Exception:
            return []
        docs = []
        chunk_id_set = {str(item) for item in chunk_ids}
        for content, chunk_meta in zip(result.get("documents") or [], result.get("metadatas") or []):
            meta = chunk_meta or {}
            if str(meta.get("chunk_id")) not in chunk_id_set:
                continue
            meta["digest_window"] = digest_id
            docs.append(self._document(page_content=content or "", metadata=meta))
            if len(docs) >= max_expand:
                break
        return docs

    @staticmethod
    def _estimate_digest_coverage_score(digest_docs):
        if not digest_docs:
            return 0.0
        chapter_keys = set()
        section_keys = set()
        for doc in digest_docs:
            metadata = (getattr(doc, "metadata", {}) or {})
            chapter_key = metadata.get("chapter_idx") or metadata.get("chapter_title")
            section_key = metadata.get("section_idx") or metadata.get("section_title")
            if chapter_key:
                chapter_keys.add(str(chapter_key))
            if section_key:
                section_keys.add(str(section_key))
        diversity = min(1.0, len(chapter_keys) / 3.0)
        detail = min(1.0, len(section_keys) / 4.0)
        return round((0.7 * diversity) + (0.3 * detail), 3)

    @staticmethod
    def _refine_digest_queries(query_list, digest_docs):
        base_queries = [q for q in query_list if q]
        anchors = []
        for doc in digest_docs[:3]:
            metadata = (getattr(doc, "metadata", {}) or {})
            anchor = metadata.get("chapter_title") or metadata.get("section_title")
            if anchor:
                anchors.append(str(anchor))
        refined = list(base_queries)
        for anchor in anchors:
            refined.append(f"{base_queries[0] if base_queries else ''} {anchor}".strip())
        seen = set()
        deduped = []
        for item in refined:
            key = item.lower().strip()
            if key and key not in seen:
                seen.add(key)
                deduped.append(item)
        return deduped[:8]

    def _build_digest_documents(self, docs, ingest_id, source_basename, doc_title):
        groups = self._group_chunks_for_digest(docs)
        if not groups:
            return []
        llm = self._get_llm_with_temperature(0.2)
        digest_docs = []
        system_prompt = (
            "Summarize the provided content into concise bullet points. "
            "Focus on entities, dates, decisions, and key statements. "
            "Use bullets only with no introductory text."
        )
        for digest_index, (group_docs, section_title) in enumerate(groups, start=1):
            chunk_ids = [
                (doc.metadata or {}).get("chunk_id")
                for doc in group_docs
                if (doc.metadata or {}).get("chunk_id") is not None
            ]
            compact_ids = self._compact_chunk_ids(chunk_ids)
            group_text = "\n\n".join(doc.page_content for doc in group_docs)
            if section_title:
                human_content = (
                    f"Section title: {section_title}\n\nContent:\n{group_text}"
                )
            else:
                human_content = f"Content:\n{group_text}"
            response = llm.invoke(
                [
                    self._system_message(content=system_prompt),
                    self._human_message(content=human_content),
                ]
            )
            metadata = {
                "doc_type": "digest",
                "digest_scope": "section",
                "tree_level": 1,
                "ingest_id": ingest_id,
                "source": source_basename,
                "digest_id": f"{ingest_id}-{digest_index}",
                "node_id": f"l1:{ingest_id}-{digest_index}",
                "parent_node_id": f"l2:{ingest_id}",
                "child_chunk_ids": compact_ids,
            }
            if section_title:
                metadata["section_title"] = section_title
            if doc_title:
                metadata["doc_title"] = doc_title
            digest_docs.append(
                self._document(page_content=response.content.strip(), metadata=metadata)
            )
        return digest_docs

    def _build_document_summary_node(
        self,
        digest_docs,
        ingest_id,
        source_basename,
        doc_title,
    ):
        if not digest_docs:
            return []
        llm = self._get_llm_with_temperature(0.2)
        section_rollup = []
        for idx, digest_doc in enumerate(digest_docs, start=1):
            metadata = getattr(digest_doc, "metadata", {}) or {}
            section_title = metadata.get("section_title") or f"Section {idx}"
            digest_id = metadata.get("digest_id", f"{ingest_id}-{idx}")
            section_rollup.append(
                f"[{digest_id}] {section_title}\n{digest_doc.page_content.strip()}"
            )
        system_prompt = (
            "Create a concise whole-book summary from chapter/part summaries. "
            "Return clear bullets capturing thesis, progression, and outcomes. "
            "End with a 'Key takeaways:' subsection with 5 bullets."
        )
        response = llm.invoke(
            [
                self._system_message(content=system_prompt),
                self._human_message(content="\n\n".join(section_rollup)),
            ]
        )
        child_digest_ids = [
            (getattr(doc, "metadata", {}) or {}).get("digest_id") for doc in digest_docs
        ]
        child_digest_ids = [item for item in child_digest_ids if item]
        metadata = {
            "doc_type": "book_summary",
            "digest_scope": "book",
            "tree_level": 3,
            "ingest_id": ingest_id,
            "source": source_basename,
            "digest_id": f"book-{ingest_id}",
            "node_id": f"l3:{ingest_id}",
            "child_digest_ids": json.dumps(child_digest_ids),
        }
        if doc_title:
            metadata["doc_title"] = doc_title
        return [self._document(page_content=response.content.strip(), metadata=metadata)]

    def _persist_summary_tree(self, ingest_id, summary_nodes, persist_dir):
        if not summary_nodes:
            return ""
        payload = []
        now_iso = datetime.now(timezone.utc).isoformat()
        for node in summary_nodes:
            md = getattr(node, "metadata", {}) or {}
            payload.append({"metadata": md, "summary": str(getattr(node, "page_content", "") or "")})
        if self._ensure_lexical_db():
            with sqlite3.connect(self.lexical_db_path) as conn:
                for item in payload:
                    md = item["metadata"]
                    conn.execute(
                        """
                        INSERT INTO summary_tree_nodes(
                            id, ingest_id, tree_level, digest_scope, node_title, source, summary_text, metadata_json, created_at
                        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            ingest_id=excluded.ingest_id,
                            tree_level=excluded.tree_level,
                            digest_scope=excluded.digest_scope,
                            node_title=excluded.node_title,
                            source=excluded.source,
                            summary_text=excluded.summary_text,
                            metadata_json=excluded.metadata_json,
                            created_at=excluded.created_at
                        """,
                        (
                            str(md.get("node_id") or md.get("digest_id") or str(uuid.uuid4())),
                            ingest_id,
                            int(md.get("tree_level", 0)),
                            str(md.get("digest_scope") or ""),
                            str(md.get("chapter_title") or md.get("part_title") or md.get("doc_title") or ""),
                            str(md.get("source") or ""),
                            item["summary"],
                            json.dumps(md, ensure_ascii=False, sort_keys=True),
                            now_iso,
                        ),
                    )
                conn.commit()
        out_path = ""
        if persist_dir:
            try:
                os.makedirs(persist_dir, exist_ok=True)
                out_path = os.path.join(persist_dir, f"summary_tree_{ingest_id}.json")
                with open(out_path, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
            except OSError:
                out_path = ""
        return out_path

    @staticmethod
    def _extract_zoom_key_idea_index(query_text):
        match = re.search(r"(?:expand|zoom|drill\s*down\s*on)\s+(?:key\s+idea\s*)?#?(\d{1,2})", str(query_text or ""), re.I)
        return int(match.group(1)) if match else None

    def _build_mini_digest_documents(self, docs, query):
        groups = self._group_chunks_for_digest(docs)
        if not groups:
            return []
        llm = self._get_llm_with_temperature(0.2)
        digest_docs = []
        system_prompt = (
            "Summarize the provided content into concise bullet points for routing. "
            "Focus on entities, dates, decisions, and key statements that are useful "
            "for answering the user's query. Use bullets only with no introductory text."
        )
        for digest_index, (group_docs, section_title) in enumerate(groups, start=1):
            chunk_ids = [
                (doc.metadata or {}).get("chunk_id")
                for doc in group_docs
                if (doc.metadata or {}).get("chunk_id") is not None
            ]
            compact_ids = self._compact_chunk_ids(chunk_ids)
            group_text = "\n\n".join(doc.page_content for doc in group_docs)
            if section_title:
                human_content = (
                    f"User query: {query}\n"
                    f"Section title: {section_title}\n\nContent:\n{group_text}"
                )
            else:
                human_content = f"User query: {query}\n\nContent:\n{group_text}"
            response = llm.invoke(
                [
                    self._system_message(content=system_prompt),
                    self._human_message(content=human_content),
                ]
            )
            metadata = {
                "doc_type": "mini_digest",
                "digest_id": f"mini-{digest_index}",
                "child_chunk_ids": compact_ids,
            }
            if section_title:
                metadata["section_title"] = section_title
            digest_docs.append(
                self._document(page_content=response.content.strip(), metadata=metadata)
            )
        return digest_docs

    def _route_with_mini_digest(self, docs, query, final_k):
        if not docs:
            return []
        docs_sorted = sorted(
            docs,
            key=lambda doc: (
                (doc.metadata or {}).get("chunk_id", 0),
                (doc.metadata or {}).get("source", ""),
            ),
        )
        digest_docs = self._build_mini_digest_documents(docs_sorted, query)
        if not digest_docs:
            return docs_sorted
        embeddings = self.get_embeddings()
        digest_texts = [doc.page_content for doc in digest_docs]
        digest_vectors = embeddings.embed_documents(digest_texts)
        query_vector = embeddings.embed_query(query)

        def _cosine_similarity(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            norm_a = sum(x * x for x in a) ** 0.5
            norm_b = sum(y * y for y in b) ** 0.5
            if norm_a == 0 or norm_b == 0:
                return 0.0
            return dot / (norm_a * norm_b)

        scored = [
            (idx, _cosine_similarity(vec, query_vector))
            for idx, vec in enumerate(digest_vectors)
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        target_digest_k = min(max(3, final_k), len(scored))
        selected_digest_ids = {idx for idx, _score in scored[:target_digest_k]}
        selected_chunk_ids = set()
        for idx in selected_digest_ids:
            metadata = digest_docs[idx].metadata or {}
            selected_chunk_ids.update(
                self._expand_compact_chunk_ids(metadata.get("child_chunk_ids", ""))
            )
        if not selected_chunk_ids:
            return docs_sorted
        routed_docs = [
            doc
            for doc in docs_sorted
            if (doc.metadata or {}).get("chunk_id") in selected_chunk_ids
        ]
        return routed_docs or docs_sorted

    @staticmethod
    def _is_chroma_persist_dir(path):
        if not os.path.isdir(path):
            return False
        return os.path.exists(os.path.join(path, "chroma.sqlite3")) or os.path.exists(
            os.path.join(path, "index")
        )

    def _has_digest_collection(self, persist_dir):
        if not persist_dir or not os.path.isdir(persist_dir):
            return False
        try:
            Chroma = _lazy_import_chroma()
        except ImportError:
            return False
        try:
            digest_store = Chroma(
                collection_name=DIGEST_COLLECTION_NAME,
                embedding_function=self.get_embeddings(),
                persist_directory=persist_dir,
            )
        except Exception:
            return False
        count = None
        if hasattr(digest_store, "_collection"):
            try:
                count = digest_store._collection.count()
            except Exception:
                count = None
        if count is None and hasattr(digest_store, "count"):
            try:
                count = digest_store.count()
            except Exception:
                count = None
        return bool(count)

    @staticmethod
    def _format_index_label(path, collection_name=RAW_COLLECTION_NAME):
        try:
            label = os.path.relpath(path, os.getcwd())
        except ValueError:
            label = path
        if collection_name and collection_name != RAW_COLLECTION_NAME:
            return f"{label} (digest)"
        return label

    def _list_existing_indexes(self):
        db_type = self.vector_db_type.get()
        indexes = []
        if db_type == "chroma":
            base_dir = self._get_chroma_persist_root()
            if os.path.isdir(base_dir):
                if self._is_chroma_persist_dir(base_dir):
                    indexes.append(base_dir)
                for entry in sorted(os.listdir(base_dir)):
                    path = os.path.join(base_dir, entry)
                    if self._is_chroma_persist_dir(path):
                        indexes.append(path)
        return indexes

    def _refresh_existing_indexes_async(self, reason="Loading indexes…"):
        if self._index_scan_in_progress:
            return
        self._index_scan_in_progress = True
        self._set_startup_status(reason)

        def _worker():
            indexes = self._list_existing_indexes()
            self._run_on_ui(self._apply_existing_indexes, indexes)

        threading.Thread(target=_worker, daemon=True).start()

    def _apply_existing_indexes(self, indexes):
        display_values = ["(default)"]
        self.existing_index_paths = {}
        for path in indexes:
            raw_label = self._format_index_label(path, RAW_COLLECTION_NAME)
            display_values.append(raw_label)
            self.existing_index_paths[raw_label] = (path, RAW_COLLECTION_NAME)
            digest_label = self._format_index_label(path, DIGEST_COLLECTION_NAME)
            display_values.append(digest_label)
            self.existing_index_paths[digest_label] = (path, DIGEST_COLLECTION_NAME)
        if hasattr(self, "cb_existing_index"):
            self.cb_existing_index["values"] = display_values

        desired = self.existing_index_var.get()
        if self._pending_selected_index_label:
            desired = self._pending_selected_index_label
            self._pending_selected_index_label = None
        if desired not in display_values:
            desired = "(default)"
        self.existing_index_var.set(desired)
        self._index_scan_in_progress = False
        if self._startup_pipeline_finished:
            self._set_startup_status("Ready")

    def _get_selected_index_path(self):
        selection = self.existing_index_var.get()
        if not selection or selection == "(default)":
            return self.selected_index_path, self.selected_collection_name
        return self.existing_index_paths.get(selection, (selection, RAW_COLLECTION_NAME))

    def _on_existing_index_change(self, _event=None):
        selected_path, selected_collection = self._get_selected_index_path()
        if not selected_path:
            return
        self.selected_index_path = selected_path
        self.selected_collection_name = selected_collection
        self.save_config()
        threading.Thread(
            target=self._load_existing_index,
            args=(selected_path, selected_collection),
            daemon=True,
        ).start()

    def _load_existing_index(self, selected_path, selected_collection):
        try:
            self.log(
                "Loading existing index from "
                f"{self._format_index_label(selected_path, selected_collection)}..."
            )
            db_type = self.vector_db_type.get()
            embeddings = self.get_embeddings()
            if db_type == "chroma":
                try:
                    Chroma = _lazy_import_chroma()
                except ImportError as err:
                    self._prompt_dependency_install(
                        ["langchain-chroma", "chromadb"], "Chroma vector store", err
                    )
                    return
                self.vector_store = Chroma(
                    collection_name=selected_collection,
                    embedding_function=embeddings,
                    persist_directory=selected_path,
                )
                self._ensure_lexical_db()
                self.index_embedding_signature = self._current_embedding_signature()
                self.save_config()
                self.log(
                    "Active index set to "
                    f"{self._format_index_label(selected_path, selected_collection)}."
                )
            elif db_type == "weaviate":
                self.log(
                    "Weaviate indexes must be loaded via server connection. "
                    "Please ingest or connect first."
                )
            else:
                self.log(f"Unknown vector DB type: {db_type}")
        except Exception as exc:
            self.log(f"Failed to load existing index: {exc}")

    def check_dependencies(self):
        def has_module(module_name):
            return importlib.util.find_spec(module_name) is not None

        missing_modules = []
        missing_packages = set()
        mismatched_symbols = []

        def record_missing(module_name, packages, context=None):
            label = module_name if context is None else f"{module_name} ({context})"
            missing_modules.append(label)
            missing_packages.update(packages)

        def check_module(module_name, packages, context=None):
            if has_module(module_name):
                return True
            record_missing(module_name, packages, context=context)
            return False

        def check_symbol(module_name, symbol_name, packages, context=None):
            try:
                module = __import__(module_name, fromlist=[symbol_name])
                getattr(module, symbol_name)
                return True
            except (ImportError, AttributeError) as err:
                detail = f"{module_name}.{symbol_name}"
                detail_context = context or "import"
                record_missing(detail, packages, context=detail_context)
                self.log(f"Dependency import failed for {detail}: {err}")
                return False

        def check_any_symbol(module_name, symbol_names, packages, context=None):
            try:
                module = __import__(module_name, fromlist=symbol_names)
            except ImportError as err:
                detail_context = context or "import"
                record_missing(module_name, packages, context=detail_context)
                self.log(f"Dependency import failed for {module_name}: {err}")
                return False
            for symbol_name in symbol_names:
                if hasattr(module, symbol_name):
                    return True
            detail = f"{module_name}.[{', '.join(symbol_names)}]"
            detail_context = context or "API mismatch"
            record_missing(detail, packages, context=detail_context)
            self.log(
                f"{module_name} is installed but missing expected symbols "
                f"{', '.join(symbol_names)}. This is likely an API mismatch; "
                "please upgrade or downgrade langchain-voyageai."
            )
            return False

        core_checks = {
            "langchain": ["langchain"],
            "chromadb": ["chromadb"],
            "bs4": ["beautifulsoup4"],
            "tiktoken": ["tiktoken"],
        }
        for module_name, packages in core_checks.items():
            check_module(module_name, packages)

        llm_provider = self.llm_provider.get()
        embedding_provider = self.embedding_provider.get()
        vector_db_type = self.vector_db_type.get()

        llm_checks = {
            "openai": ("langchain_openai", "ChatOpenAI", ["langchain-openai"]),
            "anthropic": ("langchain_anthropic", "ChatAnthropic", ["langchain-anthropic"]),
            "google": (
                "langchain_google_genai",
                "ChatGoogleGenerativeAI",
                ["langchain-google-genai"],
            ),
            "local_lm_studio": ("langchain_openai", "ChatOpenAI", ["langchain-openai"]),
        }
        if llm_provider in llm_checks:
            module_name, symbol_name, packages = llm_checks[llm_provider]
            check_symbol(
                module_name,
                symbol_name,
                packages,
                context=f"LLM provider {llm_provider}",
            )

        embedding_checks = {
            "openai": ("langchain_openai", "OpenAIEmbeddings", ["langchain-openai"]),
            "google": (
                "langchain_google_genai",
                "GoogleGenerativeAIEmbeddings",
                ["langchain-google-genai"],
            ),
            "local_huggingface": (
                "langchain_community.embeddings",
                "HuggingFaceEmbeddings",
                ["langchain-community"],
            ),
        }
        if embedding_provider in embedding_checks:
            module_name, symbol_name, packages = embedding_checks[embedding_provider]
            check_symbol(
                module_name,
                symbol_name,
                packages,
                context=f"embedding provider {embedding_provider}",
            )
        if embedding_provider == "voyage":
            check_any_symbol(
                "langchain_voyageai",
                ["VoyageAIEmbeddings", "VoyageEmbeddings"],
                ["langchain-voyageai"],
                context="embedding provider voyage",
            )

        vector_checks = {
            "chroma": ("langchain_chroma", "Chroma", ["langchain-chroma", "chromadb"]),
            "weaviate": (
                "langchain_weaviate",
                "WeaviateVectorStore",
                ["langchain-weaviate", "weaviate-client"],
            ),
        }
        if vector_db_type in vector_checks:
            module_name, symbol_name, packages = vector_checks[vector_db_type]
            check_symbol(
                module_name,
                symbol_name,
                packages,
                context=f"vector DB {vector_db_type}",
            )
            if vector_db_type == "weaviate":
                check_module("weaviate", ["weaviate-client"], context="weaviate client")

        if self.use_reranker.get() and self.api_keys["cohere"].get():
            check_symbol(
                "langchain_cohere",
                "CohereRerank",
                ["langchain-cohere"],
                context="Cohere reranker",
            )

        if missing_packages:
            if missing_modules:
                self.log(
                    "Missing dependencies detected: "
                    + ", ".join(sorted(missing_modules))
                )
            self.prompt_install(sorted(missing_packages))
            return

        if mismatched_symbols:
            self.log(
                "Installed packages found, but expected symbols are missing: "
                + ", ".join(sorted(mismatched_symbols))
            )
            return

        self.log("All required dependencies found.")

    def reinstall_dependencies(self):
        packages = self._get_required_packages()
        if messagebox.askyesno(
            "Install Dependencies",
            "Install or re-install required libraries now?",
        ):
            threading.Thread(
                target=self.install_packages,
                args=(packages, ["--upgrade", "--force-reinstall"]),
                daemon=True,
            ).start()
        else:
            self.log("Dependency install canceled.")

    def prompt_install(self, packages):
        if messagebox.askyesno(
            "Missing Dependencies", "Required libraries are missing. Install them automatically now?"
        ):
            threading.Thread(
                target=self.install_packages, args=(packages,), daemon=True
            ).start()
        else:
            self.log("Dependencies missing. App may crash.")

    def _prompt_dependency_install(self, packages, label, err):
        self.log(f"{label} dependency issue: {err}")
        if not self.dependency_prompted:
            self.dependency_prompted = True
            self.prompt_install(packages)

    def install_packages(self, packages, extra_args=None):
        self.log("Starting automatic installation...")
        cmd = [sys.executable, "-m", "pip", "install"]
        if extra_args:
            cmd.extend(extra_args)
        cmd.extend(packages)

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
            )

            for line in process.stdout:
                self.log(line.strip())

            process.wait()

            if process.returncode == 0:
                self.log("Installation Complete! Please restart the application.")
                messagebox.showinfo(
                    "Restart Required",
                    "Dependencies installed successfully.\n\nPlease close and restart the application.",
                )
            else:
                stderr = process.stderr.read()
                self.log(f"Installation Failed: {stderr}")
                messagebox.showerror(
                    "Installation Failed", "Could not install dependencies. Check logs."
                )

        except Exception as e:
            self.log(f"Installation Error: {e}")

    def browse_file(self):
        f = filedialog.askopenfilename(filetypes=[("HTML/Text", "*.html *.htm *.txt")])
        if f:
            self.selected_file = f
            self.lbl_file.config(text=f, foreground="black")
            self._update_file_info()

    def clear_selected_file(self):
        self.selected_file = None
        self.lbl_file.config(text="No file selected", foreground="gray")
        if hasattr(self, "lbl_file_info"):
            self.lbl_file_info.config(text="")

    def _update_file_info(self):
        if not self.selected_file:
            return
        try:
            size_bytes = os.path.getsize(self.selected_file)
            size_label = self._humanize_bytes(size_bytes)
            self.lbl_file_info.config(text=f"File size: {size_label}")
        except OSError:
            self.lbl_file_info.config(text="")

    def _validate_model_settings(self):
        try:
            temperature = float(self.llm_temperature.get())
        except (TypeError, ValueError):
            self._run_on_ui(
                messagebox.showerror, "Invalid Temperature", "Temperature must be a number."
            )
            return None

        if not 0 <= temperature <= 2:
            self._run_on_ui(
                messagebox.showerror,
                "Invalid Temperature",
                "Temperature must be between 0 and 2.",
            )
            return None

        try:
            max_tokens = int(self.llm_max_tokens.get())
        except (TypeError, ValueError):
            self._run_on_ui(
                messagebox.showerror, "Invalid Max Tokens", "Max tokens must be an integer."
            )
            return None

        if max_tokens <= 0:
            self._run_on_ui(
                messagebox.showerror,
                "Invalid Max Tokens",
                "Max tokens must be a positive integer.",
            )
            return None

        return temperature, max_tokens

    def get_model_caps(self, provider: str, model: str) -> dict:
        provider_name = (provider or "").strip().lower()
        model_name = (model or "").strip().lower()

        caps = {
            "max_context_tokens": 8192,
            "max_output_tokens": 2048,
        }

        provider_defaults = {
            "openai": {"max_context_tokens": 128000, "max_output_tokens": 4096},
            "anthropic": {
                "max_context_tokens": 200000,
                "max_output_tokens": 4096,
            },
            "google": {"max_context_tokens": 32000, "max_output_tokens": 4096},
            "local_lm_studio": {
                "max_context_tokens": 8192,
                "max_output_tokens": 2048,
            },
        }
        caps.update(provider_defaults.get(provider_name, {}))

        model_overrides = {
            "openai": [
                (r"gpt-4o|o4-mini", 128000, 16384),
                (r"gpt-4\.1", 1000000, 16384),
                (r"gpt-4-turbo", 128000, 4096),
                (r"gpt-4", 8192, 2048),
                (r"gpt-3\.5-turbo", 16384, 4096),
            ],
            "anthropic": [
                (r"claude-(opus|sonnet|haiku)-4", 200000, 8192),
                (r"claude-3\.7-sonnet", 200000, 8192),
                (r"claude-3\.5-(sonnet|haiku)", 200000, 8192),
                (r"claude-3-(opus|sonnet|haiku)", 200000, 4096),
            ],
        }
        for pattern, max_context_tokens, max_output_tokens in model_overrides.get(
            provider_name, []
        ):
            if re.search(pattern, model_name):
                caps["max_context_tokens"] = max_context_tokens
                caps["max_output_tokens"] = max_output_tokens
                break

        return caps

    def _get_capped_output_tokens(self, provider: str, model_name: str, requested_max_tokens: int) -> int:
        requested = max(1, int(requested_max_tokens))
        caps = self.get_model_caps(provider, model_name)
        capped = max(1, int(caps.get("max_output_tokens", requested)))
        return min(requested, capped)

    def _get_mode_prompt_pack(self, mode_name):
        mode = (mode_name or "").strip()
        packs = {
            "Standard RAG Q&A": "",
            "Book Tutor": (
                "Mode: Book Tutor. Teach in plain English using the book's framing. "
                "Prefer concept cards + chapter digests; retrieve raw chunks only when needed for missing support. "
                "Include 2-3 analogies/examples, ask exactly 3 Socratic questions unless user asks one-shot output, "
                "generate exactly 10 flashcards (Q/A), and generate a short 5-question quiz with answer key. "
                "Use minimal claim-level [S#] citations."
            ),
            "Blinkist-style Summary": (
                "Mode: Blinkist-style Summary. Produce a concise summary: big idea, key takeaways, "
                "and practical actions. Keep it compact and structured."
            ),
            "Research Analyst": (
                "Mode: Research Analyst. Structure output as claims, supporting arguments, and "
                "counterclaims with evidence quality notes."
            ),
            "Evidence Pack": (
                "Mode: Evidence Pack. Prepare evidence for formal review with chronology, incidents, "
                "and strictly grounded citations."
            ),
        }
        return packs.get(mode, "")

    def _is_one_shot_learning_request(self, query):
        text = (query or "").strip().lower()
        if not text:
            return False
        one_shot_signals = [
            "one-shot",
            "one shot",
            "no follow-up",
            "no follow up",
            "without questions",
            "just teach me",
            "single response",
        ]
        return any(signal in text for signal in one_shot_signals)

    def _render_flashcards(self, flashcards):
        rendered = ["### Flashcards (10)"]
        for idx, card in enumerate(flashcards or [], start=1):
            question = str(card.get("q") or "").strip()
            answer = str(card.get("a") or "").strip()
            sources = [str(s).strip() for s in (card.get("sources") or []) if str(s).strip()]
            citation = f" [{' '.join(sources)}]" if sources else ""
            if not question or not answer:
                continue
            rendered.append(f"{idx}. Q: {question}")
            rendered.append(f"   A: {answer}{citation}")
        return "\n".join(rendered)

    def _render_quiz(self, quiz_items, answer_key):
        rendered = ["### Quiz (5 questions)"]
        for idx, item in enumerate(quiz_items or [], start=1):
            q_text = str(item.get("question") or "").strip()
            if q_text:
                rendered.append(f"{idx}. {q_text}")
        rendered.append("\n### Answer Key")
        for idx, item in enumerate(answer_key or [], start=1):
            answer = str(item.get("answer") or "").strip()
            reason = str(item.get("why") or "").strip()
            sources = [str(s).strip() for s in (item.get("sources") or []) if str(s).strip()]
            citation = f" [{' '.join(sources)}]" if sources else ""
            if answer:
                line = f"{idx}. {answer}"
                if reason:
                    line += f" — {reason}"
                line += citation
                rendered.append(line)
        return "\n".join(rendered)

    def _resolve_mode_profile_settings(self, query=None):
        mode = self.selected_mode.get().strip() or "Standard RAG Q&A"
        profile = self._get_selected_profile_obj()
        retrieval = profile.retrieval_strategy or {}
        iteration = profile.iteration_strategy or {}
        resolved = {
            "mode": mode,
            "profile": profile,
            "retrieve_k": max(1, int(retrieval.get("retrieve_k", self.retrieval_k.get()))),
            "final_k": max(1, int(retrieval.get("final_k", self.final_k.get()))),
            "mmr_lambda": float(retrieval.get("mmr_lambda", self.mmr_lambda.get())),
            "search_type": retrieval.get("search_type", self.search_type.get()),
            "retrieval_mode": retrieval.get("retrieval_mode", self.retrieval_mode.get()),
            "agentic_mode": bool(iteration.get("agentic_mode", self.agentic_mode.get())),
            "agentic_max_iterations": max(
                1,
                min(
                    AGENTIC_MAX_ITERATIONS_HARD_CAP,
                    int(iteration.get("max_iterations", self.agentic_max_iterations.get())),
                ),
            ),
        }
        resolved["mode_prompt_pack"] = self._get_mode_prompt_pack(mode)
        inferred_evidence_pack = self.is_evidence_pack_query(query or "", self.output_style.get())
        resolved["evidence_pack_mode"] = mode == "Evidence Pack" or (
            mode == "Standard RAG Q&A" and inferred_evidence_pack
        )
        return resolved

    def _get_system_instructions(self, resolved_settings=None):
        base_instructions = self.system_instructions.get().strip() or self.default_system_instructions
        if not self.system_instructions.get().strip():
            self.system_instructions.set(base_instructions)
            self._run_on_ui(self._refresh_instructions_box)

        profile = None
        mode_prompt = ""
        if resolved_settings:
            profile = resolved_settings.get("profile")
            mode_prompt = resolved_settings.get("mode_prompt_pack", "")
        if profile is None:
            profile = self._get_selected_profile_obj()
            mode_prompt = self._get_mode_prompt_pack(self.selected_mode.get())

        segments = [base_instructions]
        if profile.system_instructions:
            segments.append(f"Profile overlay:\n{profile.system_instructions}")
        if profile.style_template:
            segments.append(f"Profile style template:\n{profile.style_template}")
        if profile.citation_policy:
            segments.append(f"Profile citation policy:\n{profile.citation_policy}")
        if mode_prompt:
            segments.append(mode_prompt)
        instructions = "\n\n".join(part for part in segments if part)

        if self._frontier_enabled("citation_v2"):
            instructions = instructions.replace("[Chunk N]", "[S#]")
            instructions = instructions.replace("Chunk 4", "S1")
        return instructions

    def _citation_references_regex(self):
        return re.compile(r"\[(?:Chunk\s+\d+|S\d+(?:\s*,\s*S\d+)*)\]")

    @staticmethod
    def _extract_chunk_citation_numbers(text):
        return [int(num) for num in re.findall(r"\[Chunk\s+(\d+)\]", str(text or ""))]

    def _get_output_style_instruction(self):
        style = self.output_style.get().strip()
        if not style or style == "Default answer":
            return ""
        style_instructions = {
            "Detailed answer": (
                "Output style: Detailed answer. Provide a thorough, well-structured "
                "response with clear sections, concrete details, and explicit coverage "
                "of requested items. Keep formatting readable with headings and bullets "
                "as needed."
            ),
            "Brief / exec summary": (
                "Output style: Brief / exec summary. Provide a concise executive summary "
                "in 3-6 bullets or short paragraphs, focusing on key outcomes only."
            ),
            "Script / talk track": (
                "Output style: Script / talk track. Provide a short talk track or script "
                "with speaker-ready phrasing, organized as numbered beats or bullet points. "
                "Include at least one short verbatim quote (<=25 words) per major section "
                f"with a {'[S#]' if self._frontier_enabled('citation_v2') else '[Chunk N]'} citation."
            ),
            "Structured report": (
                "Output style: Structured report. Use clear section headings such as "
                "Summary, Findings, Evidence, and Gaps/Unknowns. Use bullets within sections "
                "where helpful. Include at least one short verbatim quote (<=25 words) per "
                f"major section with a {'[S#]' if self._frontier_enabled('citation_v2') else '[Chunk N]'} citation."
            ),
            "Blinkist-style summary": (
                "Output style: Blinkist-style summary. Use a compact, practical structure with: "
                "1-line premise, key ideas, actionable exercises, memorable quotes, and a final "
                "'If you only remember 3 things' section. Ground factual lines with citations and "
                "omit unsupported points instead of using placeholders."
            ),
        }
        return style_instructions.get(style, "")

    """
    Acceptance-test behavior notes (comments only; do not execute):
    1) Final K=50 long-form evidence-pack respects 50 and packed_count <= 50.
    2) Agentic max iterations 10 can run >3 when required.
    3) Output never contains "NOT FOUND IN CONTEXT".
    4) Jan 2026 incidents and Teams DM are surfaced when present.
    5) SQLite FTS exact-phrase queries surface in candidate pool when available.
    6) Default mode produces identical output to before for the same prompt.
    7) Switching mode changes system prompt and output structure deterministically.
    8) Blinkist-style summary output follows the exact template sections in order.
    9) Blinkist-style summary sources should be chapter/section meaningful (S# mapped via source locator), not chunk-id-only references.
    """
    def is_evidence_pack_query(self, query, output_style):
        normalized = f"{query} {output_style}".lower()
        keywords = [
            "evidence pack",
            "chronology",
            "timeline",
            "grievance",
            "when did it happen",
            "impact",
            "examples",
        ]
        return any(keyword in normalized for keyword in keywords)

    def _get_evidence_pack_instruction(self):
        return (
            "Evidence pack mode: Produce a courtroom-ready evidence pack. Use only supported claims. "
            "Required sections: (1) one-page overview covering allegations, themes, remedies sought; "
            "(2) timeline table with columns date | what happened | impact | sources; "
            "(3) key incidents (6-12) with consistent fields: date, actors, channel, what happened, impact, evidence; "
            "(4) supporting incidents (2-4 concise bullets); "
            "(5) witness list only when witnesses are explicitly present in evidence. "
            "All factual lines must end in [S#] citations. Omit unsupported details, placeholders, and requests for more evidence. "
            "If evidence is thin, include one short Scope note."
        )

    def _format_month_label(self, year, month):
        month_label = MONTH_INDEX_TO_LABEL.get(month)
        if not month_label:
            return None
        return f"{month_label} {year}"

    def _month_sort_key(self, month_label):
        if not month_label:
            return (9999, 99)
        parts = month_label.split()
        if len(parts) != 2:
            return (9999, 99)
        month_part, year_part = parts
        month_index = MONTH_NAME_TO_INDEX.get(month_part.lower(), 99)
        try:
            year_value = int(year_part)
        except ValueError:
            year_value = 9999
        return (year_value, month_index)

    def _extract_month_years(self, text):
        if not text:
            return set()
        months = set()
        month_name_re = re.compile(
            r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
            r"Dec(?:ember)?)\s+(\d{4})\b",
            re.IGNORECASE,
        )
        for match in month_name_re.finditer(text):
            month_index = MONTH_NAME_TO_INDEX.get(match.group(1).lower())
            if not month_index:
                continue
            try:
                year_value = int(match.group(2))
            except ValueError:
                continue
            label = self._format_month_label(year_value, month_index)
            if label:
                months.add(label)
        iso_date_re = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
        for match in iso_date_re.finditer(text):
            try:
                year_value = int(match.group(1))
                month_index = int(match.group(2))
            except ValueError:
                continue
            if 1 <= month_index <= 12:
                label = self._format_month_label(year_value, month_index)
                if label:
                    months.add(label)
        year_month_re = re.compile(r"\b(\d{4})-(\d{2})\b")
        for match in year_month_re.finditer(text):
            try:
                year_value = int(match.group(1))
                month_index = int(match.group(2))
            except ValueError:
                continue
            if 1 <= month_index <= 12:
                label = self._format_month_label(year_value, month_index)
                if label:
                    months.add(label)
        slash_full_re = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
        for match in slash_full_re.finditer(text):
            try:
                month_index = int(match.group(1))
                year_value = int(match.group(3))
            except ValueError:
                continue
            if 1 <= month_index <= 12:
                label = self._format_month_label(year_value, month_index)
                if label:
                    months.add(label)
        slash_re = re.compile(r"\b(\d{1,2})/(\d{4})\b")
        for match in slash_re.finditer(text):
            try:
                month_index = int(match.group(1))
                year_value = int(match.group(2))
            except ValueError:
                continue
            if 1 <= month_index <= 12:
                label = self._format_month_label(year_value, month_index)
                if label:
                    months.add(label)
        return months

    def _extract_date_tokens(self, text):
        if not text:
            return set()
        tokens = set()
        patterns = [
            r"\b\d{4}-\d{2}-\d{2}\b",
            r"\b\d{4}-\d{2}\b",
            r"\b\d{1,2}/\d{1,2}/\d{4}\b",
            r"\b\d{1,2}/\d{4}\b",
            r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
            r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
            r"Dec(?:ember)?)\s+\d{4}\b",
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                tokens.add(match.group(0))
        return tokens

    def _extract_channels(self, docs):
        channels = set()
        for doc in docs:
            metadata = getattr(doc, "metadata", {}) or {}
            source = str(
                metadata.get("source")
                or metadata.get("file_path")
                or metadata.get("filename")
                or ""
            )
            content = (getattr(doc, "page_content", "") or "").strip()
            channel = metadata.get("channel_type") or self._extract_channel(
                f"{source}\n{content}"
            )
            if channel:
                channels.add(channel)
        return channels

    @staticmethod
    def _extract_iso_date(value):
        raw = str(value or "").strip()
        if not raw:
            return ""
        candidate = re.sub(r"\s+", " ", raw)
        iso_candidate = candidate.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(iso_candidate)
            return parsed.date().isoformat()
        except ValueError:
            pass
        patterns = [
            (r"\b(\d{4}-\d{2}-\d{2})\b", "%Y-%m-%d"),
            (r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", None),
            (
                r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
                r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|"
                r"Dec(?:ember)?)\s+(\d{1,2}),?\s+(\d{4})\b",
                None,
            ),
        ]
        for pattern, _ in patterns:
            match = re.search(pattern, candidate, re.IGNORECASE)
            if not match:
                continue
            if len(match.groups()) == 1:
                try:
                    return datetime.strptime(match.group(1), "%Y-%m-%d").date().isoformat()
                except ValueError:
                    continue
            if pattern.startswith(r"\b(\d{1,2})/(\d{1,2})"):
                try:
                    month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                    return datetime(year, month, day).date().isoformat()
                except ValueError:
                    continue
            month_idx = MONTH_NAME_TO_INDEX.get(match.group(1).lower())
            if not month_idx:
                continue
            try:
                day = int(match.group(2))
                year = int(match.group(3))
                return datetime(year, month_idx, day).date().isoformat()
            except ValueError:
                continue
        return ""

    def _source_type_for_file(self, file_path, metadata=None):
        metadata = metadata or {}
        source = f"{file_path} {(metadata.get('source') or '')}".lower()
        ext = os.path.splitext(file_path or "")[1].lower()
        if ext == ".pdf":
            return "pdf"
        if ext in {".htm", ".html"}:
            return "html"
        if ext in {".txt", ".md", ".rtf", ".csv", ".json", ".log"}:
            return "txt"
        if "email" in source or ext in {".eml", ".msg"}:
            return "email"
        if metadata.get("message_index") is not None or "chat" in source:
            return "chat"
        return "unknown"

    @staticmethod
    def _clean_source_title(value):
        raw = str(value or "").strip()
        if not raw:
            return "unknown"
        base = os.path.basename(raw)
        stem, _ext = os.path.splitext(base)
        title = stem or base
        title = re.sub(r"[_-]+", " ", title)
        title = re.sub(r"\s+", " ", title).strip(" -_	")
        return title or "unknown"

    @staticmethod
    def _build_section_hint(meta):
        for key in ("section_hint", "section_title", "chapter_title", "heading", "header"):
            value = str(meta.get(key) or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _build_position_hint(meta):
        page_num = meta.get("page") or meta.get("page_number")
        if page_num is not None and str(page_num).strip():
            return f"page {page_num}"
        chunk_id = str(meta.get("chunk_id") or "?").strip() or "?"
        char_start = meta.get("char_start")
        char_end = meta.get("char_end")
        if char_start is not None or char_end is not None:
            start = "?" if char_start is None else str(char_start)
            end = "?" if char_end is None else str(char_end)
            return f"chunk {chunk_id}, chars {start}-{end}"
        return f"chunk {chunk_id}"

    def _ensure_source_metadata(self, metadata, selected_file, content):
        meta = (metadata or {}).copy()
        source_title = (
            str(meta.get("source_title") or meta.get("doc_title") or meta.get("title") or meta.get("source") or "").strip()
        )
        if not source_title:
            source_title = os.path.basename(selected_file or "") or "unknown"
        source_title = self._clean_source_title(source_title)
        source_type = str(meta.get("source_type") or "").strip().lower() or self._source_type_for_file(
            selected_file, meta
        )
        source_actor = str(
            meta.get("source_actor")
            or meta.get("speaker")
            or meta.get("speaker_role")
            or meta.get("author")
            or meta.get("from")
            or meta.get("role")
            or ""
        ).strip()
        raw_date = (
            meta.get("source_date")
            or meta.get("timestamp")
            or meta.get("date")
            or meta.get("created_at")
            or ""
        )
        source_date = self._extract_iso_date(raw_date) or self._extract_iso_date(content)
        chunk_id = meta.get("chunk_id")
        locator = str(meta.get("source_locator") or "").strip()
        if not locator:
            page_num = meta.get("page") or meta.get("page_number")
            if page_num is not None and str(page_num).strip():
                locator = f"p{page_num}"
            elif meta.get("message_index") is not None:
                locator = f"msg {meta.get('message_index')}"
            elif chunk_id is not None:
                locator = f"chunk {chunk_id}"
            else:
                locator = "chunk unknown"
        meta["source_title"] = source_title
        meta["section_hint"] = self._build_section_hint(meta)
        meta["position_hint"] = self._build_position_hint(meta)
        meta["source_type"] = source_type
        meta["source_date"] = source_date
        meta["source_actor"] = source_actor
        meta["source_locator"] = locator
        meta.setdefault("role", str(meta.get("speaker_role") or meta.get("role") or "unknown"))
        meta.setdefault(
            "speaker",
            str(meta.get("speaker") or meta.get("source_actor") or meta.get("author") or "").strip(),
        )
        channel_key = str(meta.get("channel_key") or meta.get("channel_type") or "").strip().lower()
        if not channel_key:
            channel_key = self._extract_channel(f"{source_title}\n{content}") or "unknown"
        meta["channel_key"] = channel_key
        date_for_month = meta.get("month_key") or source_date or raw_date
        month_key = ""
        if date_for_month:
            normalized = self._extract_iso_date(date_for_month)
            if normalized and len(normalized) >= 7:
                month_key = normalized[:7]
        meta["month_key"] = month_key or "undated"
        return meta

    @staticmethod
    def _short_anchor(text, min_words=6, max_words=12):
        content = re.sub(r"\s+", " ", str(text or "")).strip()
        if not content:
            return ""
        sentence = re.split(r"(?<=[.!?])\s+", content, maxsplit=1)[0].strip()
        words = sentence.split()
        if len(words) < min_words:
            words = content.split()
        if len(words) < min_words:
            return ""
        return " ".join(words[:max_words]).strip(" ,;:-")

    @staticmethod
    def _detect_structure_markers(text):
        chapter_markers = []
        section_markers = []
        chapter_idx = 0
        section_idx = 0
        cursor = 0
        for raw_line in (text or "").splitlines(keepends=True):
            line = raw_line.strip()
            if not line:
                cursor += len(raw_line)
                continue

            chapter_candidate = None
            section_candidate = None
            md_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            chapter_match = re.match(r"^(chapter|part)\s+([\w.-]+)?\s*[:\-–]?\s*(.*)$", line, re.IGNORECASE)
            looks_all_caps = (
                len(line) >= 6
                and len(line) <= 90
                and bool(re.search(r"[A-Z]", line))
                and line.upper() == line
                and len(re.findall(r"[A-Z]", line)) >= 4
            )

            if chapter_match:
                suffix = (chapter_match.group(3) or "").strip()
                chapter_candidate = suffix or line
            elif md_match:
                level = len(md_match.group(1))
                title = md_match.group(2).strip()
                if level <= 2:
                    chapter_candidate = title
                else:
                    section_candidate = title
            elif looks_all_caps:
                chapter_candidate = line.title()

            if chapter_candidate:
                chapter_idx += 1
                chapter_markers.append(
                    {"char_start": cursor, "chapter_idx": chapter_idx, "chapter_title": chapter_candidate}
                )
                section_idx = 0
            if section_candidate:
                section_idx += 1
                section_markers.append(
                    {"char_start": cursor, "section_idx": section_idx, "section_title": section_candidate}
                )

            cursor += len(raw_line)
        return chapter_markers, section_markers

    @staticmethod
    def _structure_at_offset(offset, markers):
        active = None
        for marker in markers:
            if marker.get("char_start", -1) <= offset:
                active = marker
            else:
                break
        return active or {}

    @staticmethod
    def _format_char_bucket(value):
        if value is None:
            return "?"
        try:
            n = int(value)
        except (TypeError, ValueError):
            return "?"
        if n >= 1000:
            return f"{round(n / 1000)}k"
        return str(n)

    def _build_source_locator(self, metadata, content):
        enriched = self._ensure_source_metadata(
            metadata,
            metadata.get("source") or metadata.get("file_path") or metadata.get("filename") or "",
            content,
        )
        title = str(
            enriched.get("source_title")
            or enriched.get("doc_title")
            or enriched.get("title")
            or enriched.get("filename")
            or "unknown"
        ).strip()
        date = str(enriched.get("source_date") or enriched.get("month_key") or "undated").strip() or "undated"
        month_key = str(enriched.get("month_key") or "undated").strip() or "undated"
        channel_key = str(enriched.get("channel_key") or "unknown channel").strip().lower() or "unknown channel"
        role = str(enriched.get("role") or enriched.get("speaker_role") or "unknown role").strip().lower() or "unknown role"
        speaker = str(enriched.get("speaker") or enriched.get("source_actor") or role).strip() or role
        anchor = self._short_anchor(content)
        chapter_idx = enriched.get("chapter_idx")
        chapter_title = str(enriched.get("chapter_title") or "").strip()
        section_title = str(enriched.get("section_title") or "").strip()
        char_start = enriched.get("char_start")
        char_end = enriched.get("char_end")
        loc_parts = [title]
        if chapter_title:
            ch_label = f"Ch. {chapter_idx}" if chapter_idx else "Ch."
            loc_parts.append(f"{ch_label} '{chapter_title}'")
        if section_title:
            loc_parts.append(f"§ '{section_title}'")
        position_hint = str(enriched.get("position_hint") or "").strip()
        if position_hint:
            loc_parts.append(position_hint)
        elif enriched.get("page") or enriched.get("page_number"):
            loc_parts.append(f"p. {enriched.get('page') or enriched.get('page_number')}")
        elif char_start is not None or char_end is not None:
            loc_parts.append(
                f"chars {self._format_char_bucket(char_start)}–{self._format_char_bucket(char_end)}"
            )
        source_locator_text = " — ".join(loc_parts)
        enriched["source_locator"] = source_locator_text
        stable_input = "|".join(
            [
                title.lower(),
                date.lower(),
                month_key.lower(),
                channel_key.lower(),
                role.lower(),
                speaker.lower(),
                anchor.lower(),
                str(chapter_idx or "").lower(),
                chapter_title.lower(),
                section_title.lower(),
                str(char_start or "").lower(),
                str(char_end or "").lower(),
            ]
        )
        source_id = hashlib.sha1(stable_input.encode("utf-8")).hexdigest()[:12]
        label = f"{title} • {month_key} • {channel_key} • {speaker}"
        if chapter_title:
            label += f" • {chapter_title}"
        if anchor:
            label += f' • "{anchor}"'
        return SourceLocator(source_id=source_id, label=label, anchor=anchor, metadata=enriched)

    def _build_source_cards(self, final_docs) -> tuple[dict, str]:
        source_map = {}
        citation_manager = CitationManager()
        for doc in final_docs or []:
            metadata = getattr(doc, "metadata", {}) or {}
            content = getattr(doc, "page_content", "") or ""
            source_locator = self._build_source_locator(metadata, content)
            enriched = source_locator.metadata
            title = enriched.get("source_title") or "unknown"
            date = enriched.get("source_date") or enriched.get("month_key") or "undated"
            actor = enriched.get("source_actor") or "unknown"
            source_type = enriched.get("source_type") or "unknown"
            source_locator_text = enriched.get("source_locator") or "unknown"
            role_kind = str(enriched.get("role") or enriched.get("speaker_role") or "unknown").strip().lower() or "unknown"
            channel_key = str(enriched.get("channel_key") or "unknown channel").strip().lower() or "unknown channel"
            stable_source_id = source_locator.source_id
            sid = citation_manager.register(stable_source_id)
            entry = source_map.setdefault(
                stable_source_id,
                {
                    "sid": sid,
                    "title": title,
                    "date": date,
                    "actor": actor,
                    "type": source_type,
                    "locator": source_locator_text,
                    "chapter": str(enriched.get("chapter_title") or "").strip(),
                    "chapter_idx": enriched.get("chapter_idx"),
                    "section": str(enriched.get("section_title") or "").strip(),
                    "section_idx": enriched.get("section_idx"),
                    "section_hint": str(enriched.get("section_hint") or enriched.get("section_title") or enriched.get("chapter_title") or "").strip(),
                    "position_hint": str(enriched.get("position_hint") or "").strip(),
                    "speaker": str(enriched.get("speaker") or enriched.get("source_actor") or "").strip() or "unknown",
                    "month_bucket": str(enriched.get("month_key") or "undated"),
                    "chunk_ids": [],
                    "role_kind": role_kind,
                    "channel_key": channel_key,
                    "timestamp": str(enriched.get("timestamp") or "").strip(),
                    "file_path": str(enriched.get("source_path") or enriched.get("file_path") or "").strip(),
                    "label": source_locator.label,
                    "anchor": source_locator.anchor,
                    "metadata": enriched,
                    "excerpt": (content or "")[:900],
                    "snippet_preview": re.sub(r"\s+", " ", (content or "").strip())[:180],
                },
            )
            chunk_id = str((metadata or {}).get("chunk_id", "")).strip()
            if chunk_id and chunk_id not in entry["chunk_ids"]:
                entry["chunk_ids"].append(chunk_id)
            if not entry.get("excerpt") and content:
                entry["excerpt"] = content[:900]

        ordered_source_ids = sorted(
            source_map.keys(), key=lambda sid_key: int(source_map[sid_key].get("sid", "S999")[1:])
        )
        lines = ["Sources:"]
        for source_id in ordered_source_ids:
            entry = source_map[source_id]
            lines.append(
                f"- [{entry['sid']}] {entry['title']} | {entry.get('section_hint') or entry['locator']} | {entry.get('position_hint') or entry['locator']}"
            )
        return source_map, "\n".join(lines)

    def _rewrite_evidence_pack_citations(self, answer_text, final_docs, source_map):
        if not answer_text:
            return answer_text
        label_by_source = {
            source_id: (entry or {}).get("sid", "")
            for source_id, entry in (source_map or {}).items()
        }
        chunk_to_source = {}
        for idx, doc in enumerate(final_docs or [], start=1):
            metadata = getattr(doc, "metadata", {}) or {}
            content = getattr(doc, "page_content", "") or ""
            source_id = self._build_source_locator(metadata, content).source_id
            label = label_by_source.get(source_id)
            if not label:
                continue
            chunk_id = str((metadata or {}).get("chunk_id", "")).strip()
            if chunk_id:
                chunk_to_source[chunk_id.lower()] = label
                chunk_to_source[f"chunk {chunk_id}".lower()] = label
                chunk_to_source[f"chunk_id:{chunk_id}".lower()] = label
                chunk_to_source[f"chunk_id: {chunk_id}".lower()] = label
            chunk_to_source[str(idx)] = label
            chunk_to_source[f"chunk {idx}"] = label

        bracket_re = re.compile(r"\[([^\[\]]+)\]")

        def _replace(match):
            inner = match.group(1)
            candidates = [item.strip() for item in re.split(r"[,;]", inner) if item.strip()]
            mapped = []
            for candidate in candidates:
                key = candidate.lower()
                if key in chunk_to_source:
                    mapped.append(chunk_to_source[key])
                    continue
                chunk_match = re.search(r"chunk\s*(\d+)", key)
                if chunk_match and chunk_match.group(1) in chunk_to_source:
                    mapped.append(chunk_to_source[chunk_match.group(1)])
            if not mapped:
                return match.group(0)
            ordered = []
            for label in mapped:
                if label not in ordered:
                    ordered.append(label)
            return "[" + ", ".join(ordered) + "]"

        rewritten = bracket_re.sub(_replace, answer_text)
        return rewritten

    @staticmethod
    def _normalize_incident_channel(channel_value):
        value = str(channel_value or "").strip().lower()
        if value in {"email", "chat", "call", "ticket", "unknown"}:
            return value
        if "team" in value or "slack" in value or "chat" in value or "dm" in value:
            return "chat"
        if "mail" in value:
            return "email"
        if "phone" in value or "call" in value or "zoom" in value or "meeting" in value:
            return "call"
        if "ticket" in value or "case" in value or "jira" in value or "zendesk" in value:
            return "ticket"
        return "unknown"

    def _derive_incident_month_bucket(self, date_start, date_end):
        for candidate in [date_start, date_end]:
            iso_value = self._extract_iso_date(candidate)
            if iso_value and len(iso_value) >= 7:
                return iso_value[:7]
        return ""

    @staticmethod
    def _evidence_ref_from_dict(item):
        return EvidenceRef(
            source_id=str(item.get("source_id", "")).strip(),
            quote=str(item.get("quote_anchor") or item.get("quote") or "").strip(),
            span_start=item.get("span_start") if isinstance(item.get("span_start"), int) else None,
            span_end=item.get("span_end") if isinstance(item.get("span_end"), int) else None,
            chunk_id=str(item.get("chunk_id", "")).strip(),
        )

    def _build_incident_id(self, incident):
        ref_basis = "|".join(
            f"{ref.source_id}:{ref.span_start}:{ref.span_end}:{ref.quote[:40]}" for ref in incident.evidence_refs
        )
        raw = "|".join(
            [
                incident.date_start or "",
                incident.date_end or "",
                incident.month_bucket or "",
                ",".join(sorted([p.lower() for p in incident.people])),
                incident.channel,
                incident.what_happened[:180],
                incident.impact[:180],
                ref_basis,
            ]
        )
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]

    def _incident_date_for_pack(self, incident):
        iso_date = self._extract_iso_date(incident.date_start) or self._extract_iso_date(incident.date_end)
        if iso_date:
            return iso_date
        month_key = str(incident.month_bucket or "").strip()
        if re.match(r"^\d{4}-\d{2}$", month_key):
            return f"{month_key}-unknown"
        return "unknown"

    def _incident_to_stage_a_payload(self, incident, source_label_by_id):
        supporting_chunks = []
        evidence_refs = []
        for ref in incident.evidence_refs:
            source_label = source_label_by_id.get(ref.source_id)
            if source_label and source_label not in supporting_chunks:
                supporting_chunks.append(source_label)
            evidence_refs.append(
                {
                    "source_id": source_label or ref.source_id,
                    "span_start": ref.span_start,
                    "span_end": ref.span_end,
                    "quote_anchor": ref.quote,
                    "chunk_id": ref.chunk_id,
                }
            )
        operational_impact = str(incident.operational_impact or "").strip()
        personal_impact = str(incident.personal_impact or "").strip()
        if not operational_impact and not personal_impact and incident.impact:
            operational_impact = str(incident.impact).strip()
        return {
            "incident_id": incident.incident_id,
            "date": self._incident_date_for_pack(incident),
            "month_key": incident.month_bucket or "",
            "channel": incident.channel,
            "people": incident.people,
            "what_happened": incident.what_happened,
            "impact": {
                "operational": operational_impact,
                "personal": personal_impact,
            },
            "supporting_chunks": supporting_chunks,
            "evidence_refs": evidence_refs,
        }

    @staticmethod
    def _is_advice_request(query_text):
        query = str(query_text or "").lower()
        advice_terms = [
            "advice", "recommend", "recommendation", "suggest", "suggestion",
            "next steps", "what should", "how should", "what can i do",
            "what do i do", "strategy", "coach", "guidance", "action plan",
        ]
        return any(term in query for term in advice_terms)

    @staticmethod
    def _incident_sort_key_for_pack(item):
        date_value = str(item.get("date") or "").strip()
        iso_value = AgenticRAGApp._extract_iso_date(date_value)
        if iso_value:
            return (0, iso_value, str(item.get("title") or "").lower())
        return (1, "9999-12-31", str(item.get("title") or "").lower())

    def _write_incidents_json_artifact(self, incidents_payload):
        artifact_path = os.path.join(os.getcwd(), "incidents.json")
        try:
            with open(artifact_path, "w", encoding="utf-8") as handle:
                json.dump(incidents_payload, handle, ensure_ascii=False, indent=2)
            self.log(f"Evidence pack Stage A saved: {artifact_path}")
        except Exception as exc:
            self.log(f"Failed to write incidents.json artifact. ({exc})")

    def _build_incident_synthesis_cards(self, incidents):
        ranked = []
        for incident in sorted(incidents or [], key=self._incident_sort_key_for_pack):
            supporting = []
            for ref in incident.get("supporting_chunks") or []:
                label = str(ref).strip()
                if re.match(r"^S\d+$", label) and label not in supporting:
                    supporting.append(label)
            if not supporting:
                continue

            when_text = str(incident.get("date") or "").strip() or "unknown"
            what_text = str(incident.get("what_happened") or "").strip()
            impact_raw = incident.get("impact") or {}
            if isinstance(impact_raw, dict):
                operational = str(impact_raw.get("operational") or "").strip()
                personal = str(impact_raw.get("personal") or "").strip()
                impact_text = "; ".join([f"operational: {operational}" if operational else "", f"personal: {personal}" if personal else ""]).strip("; ")
            else:
                impact_text = str(impact_raw).strip()

            if not what_text and not impact_text:
                continue

            month_key = str(incident.get("month_key") or "").strip() or "undated"
            channel = str(incident.get("channel") or "unknown").strip() or "unknown"
            evidence_refs = []
            for ref in incident.get("evidence_refs") or []:
                if not isinstance(ref, dict):
                    continue
                label = str(ref.get("source_id") or "").strip()
                if re.match(r"^S\d+$", label) and label not in evidence_refs:
                    evidence_refs.append(label)
            if not evidence_refs:
                evidence_refs = supporting[:]
            ranked.append(
                {
                    "incident_id": str(incident.get("incident_id") or incident.get("title") or "").strip(),
                    "when": when_text,
                    "month_key": month_key,
                    "channel": channel,
                    "what_happened": what_text,
                    "impact": impact_text,
                    "evidence": evidence_refs[:3],
                    "evidence_refs": evidence_refs[:3],
                    "strength": len(evidence_refs) * 10 + len(what_text) + len(impact_text),
                }
            )

        if not ranked:
            return []

        target_primary = min(12, max(6, len(ranked)))
        selected = []
        used_months = set()
        used_channels = set()

        for item in sorted(ranked, key=lambda x: (-x["strength"], x["when"])):
            if len(selected) >= target_primary:
                break
            month = item.get("month_key") or "undated"
            channel = item.get("channel") or "unknown"
            if month not in used_months or channel not in used_channels or len(selected) < 6:
                selected.append(item)
                used_months.add(month)
                used_channels.add(channel)

        for item in sorted(ranked, key=lambda x: (-x["strength"], x["when"])):
            if len(selected) >= target_primary:
                break
            if item not in selected:
                selected.append(item)

        supporting_count = min(4, max(2, len(ranked) - len(selected)))
        for item in sorted(ranked, key=lambda x: x["strength"]):
            if supporting_count <= 0:
                break
            if item in selected:
                continue
            selected.append(item)
            supporting_count -= 1

        for card in selected:
            card.pop("strength", None)
        return selected

    @staticmethod
    def _has_witness_data(incidents):
        for item in incidents or []:
            people = item.get("people") or []
            if isinstance(people, list) and any(str(p).strip() for p in people):
                return True
        return False

    def _build_timeline_table(self, incidents):
        rows = ["| Date | What happened | Impact | Sources |", "|---|---|---|---|"]
        for incident in sorted(incidents or [], key=self._incident_sort_key_for_pack)[:12]:
            when = str(incident.get("date") or incident.get("month_key") or "unknown").strip()
            what = re.sub(r"\s+", " ", str(incident.get("what_happened") or "").strip()) or "n/a"
            impact_raw = incident.get("impact") or {}
            if isinstance(impact_raw, dict):
                impact = "; ".join(
                    [
                        str(impact_raw.get("operational") or "").strip(),
                        str(impact_raw.get("personal") or "").strip(),
                    ]
                ).strip("; ") or "n/a"
            else:
                impact = str(impact_raw).strip() or "n/a"
            refs = [
                str(x).strip()
                for x in (incident.get("supporting_chunks") or [])
                if re.match(r"^S\d+$", str(x).strip())
            ]
            sources = ", ".join(dict.fromkeys(refs)) or "n/a"
            rows.append(f"| {when} | {what[:140]} | {impact[:120]} | {sources} |")
        if len(rows) == 2:
            rows.append("| unknown | No supported incidents extracted | n/a | n/a |")
        return "\n".join(rows)

    def _ensure_evidence_pack_template(self, answer_text, incidents):
        text = str(answer_text or "").strip()
        if not text:
            return text
        lowered = text.lower()
        if "one-page overview" not in lowered:
            text = (
                "## One-page overview\n"
                "- Allegations: grounded in cited incidents.\n"
                "- Themes: chronology, impact, and escalation patterns.\n"
                "- Remedies sought: reflect only items explicitly present in evidence.\n\n"
            ) + text
        if "timeline" not in lowered or "| date |" not in lowered:
            timeline = self._build_timeline_table(incidents)
            text = f"{text.rstrip()}\n\n## Timeline table\n{timeline}"
        if "key incidents" not in text.lower():
            text = f"{text.rstrip()}\n\n## Key incidents\n- Use fields: Date; Actors; Channel; What happened; Impact; Evidence [S#]."
        if "supporting incidents" not in text.lower():
            text = f"{text.rstrip()}\n\n## Supporting incidents\n- Include 2-4 concise incidents that broaden month/channel coverage with [S#]."
        has_witness = self._has_witness_data(incidents)
        if has_witness and "witness list" not in text.lower():
            text = f"{text.rstrip()}\n\n## Witness list\n- Witnesses named in evidence only, each with supporting [S#] citations."
        return text

    def _verify_evidence_pack_claims(self, answer_text, synthesis_cards):
        if not answer_text:
            return answer_text
        citation_re = re.compile(r"\[(S\d+(?:\s*,\s*S\d+)*)\]")
        bullet_re = re.compile(r"^(\s*(?:[-*+]\s+|\d+[.)]\s+))(.*)$")
        factual_hint_re = re.compile(
            r"\b(is|are|was|were|has|have|had|shows?|indicates?|states?|reports?|found|observed|according|caused?|led|resulted|occurred|happened)\b",
            re.I,
        )

        indexed_cards = []
        for card in synthesis_cards or []:
            incident_id = str(card.get("incident_id") or "").strip()
            evidence_refs = []
            for ref in card.get("evidence_refs") or card.get("evidence") or []:
                label = str(ref).strip()
                if re.match(r"^S\d+$", label) and label not in evidence_refs:
                    evidence_refs.append(label)
            if not evidence_refs:
                continue
            text_blob = " ".join(
                [
                    str(card.get("when") or ""),
                    str(card.get("what_happened") or ""),
                    str(card.get("impact") or ""),
                ]
            )
            indexed_cards.append(
                {
                    "incident_id": incident_id,
                    "incident_id_l": incident_id.lower(),
                    "evidence_refs": evidence_refs,
                    "tokens": self._claim_tokens(text_blob),
                }
            )

        cleaned_lines = []
        for raw_line in answer_text.splitlines():
            if not raw_line.strip():
                cleaned_lines.append(raw_line)
                continue
            stripped = raw_line.strip()
            if stripped == "Sources:" or re.match(r"^-\s*S\d+\s*->", stripped):
                cleaned_lines.append(raw_line)
                continue
            if re.match(r"^\s{0,3}#{1,6}\s+\S", raw_line):
                cleaned_lines.append(raw_line)
                continue

            bullet_match = bullet_re.match(raw_line)
            bullet_prefix = ""
            body = raw_line
            if bullet_match:
                bullet_prefix = bullet_match.group(1)
                body = bullet_match.group(2)

            existing_labels = []
            for group in citation_re.findall(body):
                for label in [part.strip() for part in group.split(",") if part.strip()]:
                    if label not in existing_labels:
                        existing_labels.append(label)

            kept_sentences = []
            for sentence in self._sentence_split(body):
                sentence = sentence.strip()
                if not sentence:
                    continue
                if sentence.lower().startswith("scope:"):
                    kept_sentences.append(sentence)
                    continue

                is_factual = bool(factual_hint_re.search(sentence)) or bool(re.search(r"\d", sentence)) or len(sentence) >= 48
                if not is_factual:
                    kept_sentences.append(sentence)
                    continue

                sentence_labels = []
                for group in citation_re.findall(sentence):
                    for label in [part.strip() for part in group.split(",") if part.strip()]:
                        if label not in sentence_labels:
                            sentence_labels.append(label)
                mapped_labels = list(sentence_labels or existing_labels)

                lower_sentence = sentence.lower()
                sentence_tokens = self._claim_tokens(sentence)
                if not mapped_labels:
                    best_labels = []
                    best_score = 0
                    for card in indexed_cards:
                        score = len(sentence_tokens & card["tokens"])
                        if card["incident_id_l"] and card["incident_id_l"] in lower_sentence:
                            score += 3
                        if score > best_score:
                            best_score = score
                            best_labels = card["evidence_refs"]
                    if best_score >= 2 and best_labels:
                        mapped_labels = best_labels[:2]

                if not mapped_labels:
                    continue

                if not sentence_labels:
                    sentence = sentence.rstrip() + " [" + ", ".join(mapped_labels[:2]) + "]"
                kept_sentences.append(sentence)

            if not kept_sentences:
                continue
            rebuilt = " ".join(kept_sentences).strip()
            cleaned_lines.append(f"{bullet_prefix}{rebuilt}" if bullet_prefix else rebuilt)

        return "\n".join(cleaned_lines).strip()

    @staticmethod
    def _infer_theme_from_incident(incident):
        text = " ".join(
            [
                str(incident.get("channel", "")),
                str(incident.get("what_happened", "")),
                str(incident.get("impact", "")),
            ]
        ).lower()
        theme_rules = [
            ("escalation_grievance", ["grievance", "escalat", "formal complaint", "hr", "tribunal"]),
            ("communication_breakdown", ["email", "chat", "teams", "dm", "message", "call", "meeting"]),
            ("process_policy", ["policy", "process", "procedure", "compliance", "protocol"]),
            ("workload_delivery", ["deadline", "deliver", "workload", "capacity", "timeline", "delay"]),
            ("people_conduct", ["behavior", "conduct", "harass", "bully", "retaliat", "hostile"]),
        ]
        for label, needles in theme_rules:
            if any(needle in text for needle in needles):
                return label
        return "other"

    def _build_recursive_memories(self, incidents):
        month_groups = {}
        theme_groups = {}
        for incident in incidents or []:
            if not isinstance(incident, dict):
                continue
            month_bucket = str(incident.get("date") or "").strip()
            iso_date = self._extract_iso_date(month_bucket)
            if iso_date:
                month_bucket = iso_date[:7]
            elif re.match(r"^\d{4}-\d{2}$", month_bucket):
                month_bucket = month_bucket
            else:
                month_bucket = "undated"
            theme = self._infer_theme_from_incident(incident)
            month_groups.setdefault(month_bucket, []).append(incident)
            theme_groups.setdefault(theme, []).append(incident)

        def _summarize_group(items, key_name):
            sorted_items = sorted(items, key=self._incident_sort_key_for_pack)
            fragments = []
            for item in sorted_items[:4]:
                what_text = re.sub(r"\s+", " ", str(item.get("what_happened", "")).strip())
                impact_text = re.sub(r"\s+", " ", str(item.get("impact", "")).strip())
                detail = what_text[:120]
                if impact_text:
                    detail = f"{detail}; impact: {impact_text[:80]}"
                fragments.append(detail)
            return {
                "summary": f"{len(items)} incidents in {key_name}. " + " | ".join([f for f in fragments if f]),
                "incident_count": len(items),
                "sample_titles": [str(it.get("title", "")).strip() for it in sorted_items[:3] if str(it.get("title", "")).strip()],
            }

        month_memory = {
            key: _summarize_group(value, key)
            for key, value in sorted(month_groups.items(), key=lambda item: self._month_sort_key(item[0]))
        }
        theme_memory = {
            key: _summarize_group(value, key)
            for key, value in sorted(theme_groups.items(), key=lambda item: item[0])
        }
        return month_memory, theme_memory

    def _build_recursive_coverage_queries(self, candidate_pool, incidents, max_queries=5):
        pool_months = set()
        for doc in candidate_pool or []:
            metadata = getattr(doc, "metadata", {}) or {}
            month_bucket = str(metadata.get("month_bucket", "")).strip()
            if month_bucket and month_bucket != "undated":
                pool_months.add(month_bucket)
            content = getattr(doc, "page_content", "") or ""
            for month in self._extract_month_years(content):
                pool_months.add(month)

        incident_months = set()
        for item in incidents or []:
            month_bucket = str(item.get("date") or "").strip()
            iso_date = self._extract_iso_date(month_bucket)
            if iso_date:
                incident_months.add(iso_date[:7])
            elif re.match(r"^\d{4}-\d{2}$", month_bucket):
                incident_months.add(month_bucket)

        missing_months = sorted(pool_months - incident_months, key=self._month_sort_key)
        if not missing_months:
            return [], {
                "triggered": False,
                "missing_months": [],
                "pool_months": sorted(pool_months, key=self._month_sort_key),
                "incident_months": sorted(incident_months, key=self._month_sort_key),
            }

        query_templates = [
            "{month} incident timeline what happened impact evidence",
            "{month} complaint escalation chronology primary facts",
            "{month} formal report dates participants outcomes",
        ]
        queries = []
        for month in missing_months:
            for template in query_templates:
                queries.append(template.format(month=month))
                if len(queries) >= max_queries:
                    break
            if len(queries) >= max_queries:
                break
        if 0 < len(queries) < 2:
            queries.append("undated incident chronology evidence summary")
        return queries[:max_queries], {
            "triggered": True,
            "missing_months": missing_months,
            "pool_months": sorted(pool_months, key=self._month_sort_key),
            "incident_months": sorted(incident_months, key=self._month_sort_key),
        }

    def _save_recursive_memory_artifact(self, query_text, artifact_payload):
        persist_dir = self.selected_index_path
        if not persist_dir:
            persist_dir = getattr(self.vector_store, "_persist_directory", None)
        if not persist_dir:
            return ""
        artifact_path = os.path.join(persist_dir, "recursive_memory_artifacts.jsonl")
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "query_hash": hashlib.sha1((query_text or "").strip().lower().encode("utf-8")).hexdigest()[:16],
            **(artifact_payload or {}),
        }
        try:
            with open(artifact_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as exc:
            self.log(f"Failed to write recursive memory artifact. ({exc})")
            return ""
        return artifact_path


    def _incident_cache_path(self):
        persist_dir = self.selected_index_path
        if not persist_dir:
            persist_dir = getattr(self.vector_store, "_persist_directory", None)
        if not persist_dir:
            return ""
        return os.path.join(persist_dir, "incidents_cache.jsonl")

    def _incident_cache_key(self, query_text, final_docs):
        ingest_ids = sorted(
            {
                str((getattr(doc, "metadata", {}) or {}).get("ingest_id", "")).strip()
                for doc in (final_docs or [])
                if str((getattr(doc, "metadata", {}) or {}).get("ingest_id", "")).strip()
            }
        )
        ingest_basis = "|".join(ingest_ids) if ingest_ids else "unknown"
        query_hash = hashlib.sha1((query_text or "").strip().lower().encode("utf-8")).hexdigest()[:16]
        return f"{ingest_basis}:{query_hash}"

    def _load_incident_cache(self, query_text, final_docs):
        cache_path = self._incident_cache_path()
        if not cache_path or not os.path.isfile(cache_path):
            return []
        cache_key = self._incident_cache_key(query_text, final_docs)
        try:
            with open(cache_path, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    if row.get("key") != cache_key:
                        continue
                    incidents = []
                    for item in row.get("incidents", []):
                        refs = [self._evidence_ref_from_dict(ref) for ref in item.get("evidence_refs", []) if isinstance(ref, dict)]
                        incidents.append(
                            Incident(
                                incident_id=str(item.get("incident_id", "")).strip(),
                                date_start=item.get("date_start"),
                                date_end=item.get("date_end"),
                                month_bucket=str(item.get("month_bucket", "")).strip(),
                                people=[str(p).strip() for p in item.get("people", []) if str(p).strip()],
                                channel=self._normalize_incident_channel(item.get("channel")),
                                what_happened=str(item.get("what_happened", "")).strip(),
                                impact=(str(item.get("impact", "")).strip() if not isinstance(item.get("impact"), dict) else ""),
                                operational_impact=str(item.get("operational_impact", "")).strip(),
                                personal_impact=str(item.get("personal_impact", "")).strip(),
                                evidence_refs=refs,
                            )
                        )
                    return incidents
        except Exception as exc:
            self.log(f"Incident cache read failed; recomputing incidents. ({exc})")
        return []

    def _save_incident_cache(self, query_text, final_docs, incidents):
        cache_path = self._incident_cache_path()
        if not cache_path:
            return
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        record = {
            "key": self._incident_cache_key(query_text, final_docs),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "incidents": [asdict(item) for item in incidents],
        }
        try:
            with open(cache_path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as exc:
            self.log(f"Incident cache write failed. ({exc})")

    def _extract_incidents_langextract(self, final_docs, source_map) -> list[Incident]:
        if not final_docs:
            return []
        ordered_source_ids = sorted(source_map.keys())
        source_label_by_id = {source_id: f"S{idx}" for idx, source_id in enumerate(ordered_source_ids, start=1)}
        docs_payload = []
        chunk_lookup = {}
        for doc in final_docs:
            metadata = getattr(doc, "metadata", {}) or {}
            content = getattr(doc, "page_content", "") or ""
            enriched = self._ensure_source_metadata(
                metadata,
                metadata.get("source") or metadata.get("file_path") or metadata.get("filename") or "",
                content,
            )
            title = enriched.get("source_title") or "unknown"
            date = enriched.get("source_date") or "unknown"
            locator = enriched.get("source_locator") or "unknown"
            role_kind = str(enriched.get("role") or enriched.get("speaker_role") or "unknown").strip().lower() or "unknown"
            channel_key = str(enriched.get("channel_type") or self._extract_channel(f"{title}\n{content}") or "unknown").strip().lower()
            stable_input = f"{title}|{date}|{locator}|{role_kind}|{channel_key}".lower()
            source_id = hashlib.sha1(stable_input.encode("utf-8")).hexdigest()[:12]
            chunk_id = str(enriched.get("chunk_id", "")).strip()
            chunk_lookup[chunk_id] = (source_id, content)
            docs_payload.append(
                {
                    "id": chunk_id or hashlib.sha1(content.encode("utf-8")).hexdigest()[:12],
                    "text": content,
                    "metadata": {
                        "source_id": source_id,
                        "source_label": source_label_by_id.get(source_id, ""),
                        "chunk_id": chunk_id,
                        "date": date,
                    },
                }
            )

        incidents = []
        if langextract is not None:
            try:
                prompt = (
                    "Extract incident objects. Ground each incident to exact spans. "
                    "Return JSON with incidents[] where each incident has incident_id, date_start/date_end or month_bucket, "
                    "people[], channel(email/chat/call/ticket/unknown), what_happened, impact{operational,personal}, evidence_refs[]. "
                    "Each evidence_ref includes source_id, quote_anchor (or quote), span_start, span_end, chunk_id."
                )
                result = langextract.extract(docs_payload, prompt=prompt)
                payload = result if isinstance(result, dict) else {}
                grounding_html_path = self._save_langextract_grounding_html(payload)
                if grounding_html_path:
                    self._latest_grounding_html_path = grounding_html_path
                raw_incidents = payload.get("incidents", []) if isinstance(payload, dict) else []
                for item in raw_incidents:
                    if not isinstance(item, dict):
                        continue
                    refs = []
                    for ref in item.get("evidence_refs", []):
                        if not isinstance(ref, dict):
                            continue
                        refs.append(self._evidence_ref_from_dict(ref))
                    incident = Incident(
                        incident_id="",
                        date_start=self._extract_iso_date(item.get("date_start")) or None,
                        date_end=self._extract_iso_date(item.get("date_end")) or None,
                        month_bucket=str(item.get("month_bucket") or "").strip(),
                        people=[str(p).strip() for p in item.get("people", []) if str(p).strip()],
                        channel=self._normalize_incident_channel(item.get("channel")),
                        what_happened=str(item.get("what_happened", "")).strip(),
                        impact=(str(item.get("impact", "")).strip() if not isinstance(item.get("impact"), dict) else ""),
                        operational_impact=str((item.get("impact") or {}).get("operational", "")).strip() if isinstance(item.get("impact"), dict) else "",
                        personal_impact=str((item.get("impact") or {}).get("personal", "")).strip() if isinstance(item.get("impact"), dict) else "",
                        evidence_refs=refs,
                    )
                    incident.month_bucket = incident.month_bucket or self._derive_incident_month_bucket(incident.date_start, incident.date_end)
                    incident.incident_id = self._build_incident_id(incident)
                    if incident.evidence_refs:
                        incidents.append(incident)
            except Exception as exc:
                self.log(f"LangExtract incident extraction failed; falling back to LLM JSON extraction. ({exc})")

        if incidents:
            return incidents

        llm = self.get_llm()
        fallback_prompt = (
            "Extract incidents from FINAL_DOCS. Return STRICT JSON object with incidents array. "
            "Each incident fields: incident_id, date_start/date_end or month_bucket, people, channel, what_happened, impact{operational,personal}, evidence_refs. "
            "evidence_refs fields: source_id, quote_anchor (or quote), span_start, span_end, chunk_id. Use source_id values from metadata only."
        )
        response = llm.invoke(
            [
                self._system_message(content=fallback_prompt),
                self._human_message(content=json.dumps(docs_payload, ensure_ascii=False)),
            ]
        )
        payload = {}
        try:
            payload = json.loads(str(response.content).strip().strip("`").replace("json\n", "", 1))
        except Exception:
            payload = {}
        for item in payload.get("incidents", []):
            if not isinstance(item, dict):
                continue
            refs = [self._evidence_ref_from_dict(ref) for ref in item.get("evidence_refs", []) if isinstance(ref, dict)]
            incident = Incident(
                incident_id="",
                date_start=self._extract_iso_date(item.get("date_start")) or None,
                date_end=self._extract_iso_date(item.get("date_end")) or None,
                month_bucket=str(item.get("month_bucket") or "").strip(),
                people=[str(p).strip() for p in item.get("people", []) if str(p).strip()],
                channel=self._normalize_incident_channel(item.get("channel")),
                what_happened=str(item.get("what_happened", "")).strip(),
                impact=(str(item.get("impact", "")).strip() if not isinstance(item.get("impact"), dict) else ""),
                operational_impact=str((item.get("impact") or {}).get("operational", "")).strip() if isinstance(item.get("impact"), dict) else "",
                personal_impact=str((item.get("impact") or {}).get("personal", "")).strip() if isinstance(item.get("impact"), dict) else "",
                evidence_refs=refs,
            )
            incident.month_bucket = incident.month_bucket or self._derive_incident_month_bucket(incident.date_start, incident.date_end)
            incident.incident_id = self._build_incident_id(incident)
            if incident.evidence_refs:
                incidents.append(incident)
        return incidents

    def _compute_unique_incidents(self, docs):
        incidents = set()
        for doc in docs:
            metadata = getattr(doc, "metadata", {}) or {}
            source = (
                metadata.get("source")
                or metadata.get("file_path")
                or metadata.get("filename")
                or "unknown"
            )
            content = (doc.page_content or "").strip()
            months = sorted(self._extract_month_years(content), key=self._month_sort_key)
            date_tokens = sorted(self._extract_date_tokens(content))
            if months:
                key_basis = months[0]
            elif date_tokens:
                key_basis = date_tokens[0]
            else:
                key_basis = re.sub(r"\s+", " ", content)[:80]
            if not key_basis:
                key_basis = "unknown"
            incidents.add(f"{source}|{key_basis}".lower())
        return len(incidents)

    def _extract_months_and_tokens(self, docs):
        months = set()
        tokens = set()
        for doc in docs:
            content = doc.page_content or ""
            months.update(self._extract_month_years(content))
            tokens.update(self._extract_date_tokens(content))
        return months, tokens

    def coverage_audit(self, final_docs, candidate_pool):
        available_months, candidate_tokens = self._extract_months_and_tokens(candidate_pool)
        selected_months, _ = self._extract_months_and_tokens(final_docs)
        available_channels = self._extract_channels(candidate_pool)
        selected_channels = self._extract_channels(final_docs)
        missing_months = sorted(available_months - selected_months, key=self._month_sort_key)
        missing_channels = sorted(available_channels - selected_channels)
        role_balance = {}
        for doc in final_docs:
            metadata = getattr(doc, "metadata", {}) or {}
            role = metadata.get("speaker_role") or metadata.get("role") or "unknown"
            role_balance[role] = role_balance.get(role, 0) + 1
        return {
            "selected_months": sorted(selected_months, key=self._month_sort_key),
            "available_months": sorted(available_months, key=self._month_sort_key),
            "selected_channels": sorted(selected_channels),
            "available_channels": sorted(available_channels),
            "incident_count": self._compute_unique_incidents(final_docs),
            "role_balance": role_balance,
            "missing_months": missing_months,
            "missing_channels": missing_channels,
            "candidate_date_tokens": sorted(candidate_tokens),
            "missing_indicators": {
                "months": bool(missing_months),
                "channels": bool(missing_channels),
            },
        }

    def _extract_candidate_keyphrases(self, candidate_pool, max_phrases=6):
        stop_words = {
            "the", "and", "that", "with", "from", "this", "have", "were", "been", "they",
            "their", "about", "would", "could", "there", "which", "what", "when", "where",
            "while", "into", "than", "then", "them", "also", "only", "other", "after",
            "before", "under", "over", "between", "because", "during", "meeting", "incident",
            "timeline", "details", "reported", "report", "issue", "complaint", "email", "teams",
        }
        counts = {}
        for doc in candidate_pool:
            content = (getattr(doc, "page_content", "") or "").lower()
            for phrase in re.findall(r"\b[a-z][a-z0-9]{3,}(?:\s+[a-z][a-z0-9]{3,}){1,2}\b", content):
                parts = phrase.split()
                if any(part in stop_words for part in parts):
                    continue
                if phrase.isdigit():
                    continue
                counts[phrase] = counts.get(phrase, 0) + 1
        ranked = sorted(counts.items(), key=lambda item: item[1], reverse=True)
        return [phrase for phrase, _count in ranked[:max_phrases]]

    def _generate_follow_up_queries(self, coverage, candidate_pool, max_queries=10):
        queries = []
        months = coverage.get("missing_months", [])
        channels = coverage.get("missing_channels", [])
        date_tokens = coverage.get("candidate_date_tokens", [])

        for month in months[:4]:
            if channels:
                for channel in channels[:3]:
                    queries.append(f"{month} {channel} incident timeline what happened impact")
            else:
                queries.append(f"{month} incident timeline what happened impact")

        for channel in channels[:4]:
            queries.append(f"{channel} incident grievance escalation timeline")

        for token in date_tokens[:4]:
            queries.append(f"{token} incident details what happened outcome")

        for phrase in self._extract_candidate_keyphrases(candidate_pool):
            queries.append(f"{phrase} incident evidence chronology")

        deduped = []
        seen = set()
        for candidate in queries:
            key = candidate.lower().strip()
            if key and key not in seen:
                seen.add(key)
                deduped.append(candidate)
            if len(deduped) >= max_queries:
                break
        return deduped

    def _extract_chunks(self, context_text):
        chunks = {}
        matches = list(re.finditer(r"^\[Chunk (\d+)[^\]]*\]\n", context_text, re.M))
        for idx, match in enumerate(matches):
            chunk_num = int(match.group(1))
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(context_text)
            chunks[chunk_num] = context_text[start:end].strip()
        return chunks

    def _extract_sources(self, context_text):
        sources = {}
        header_re = re.compile(r"^\[(Chunk\s+\d+|S\d+)[^\]]*\]\n", re.M)
        matches = list(header_re.finditer(context_text or ""))
        for idx, match in enumerate(matches):
            label = match.group(1).strip()
            start = match.end()
            end = matches[idx + 1].start() if idx + 1 < len(matches) else len(context_text)
            sources[label] = (context_text[start:end] or "").strip()
        return sources

    def _split_major_sections(self, answer_text):
        lines = answer_text.splitlines()
        sections = []
        current = []

        def _flush():
            if current:
                section_text = "\n".join(current).strip()
                if section_text:
                    sections.append(section_text)

        for line in lines:
            if re.match(r"^\s*#{1,6}\s+\S", line) or re.match(
                r"^[A-Za-z][A-Za-z /&-]{0,50}:$", line.strip()
            ):
                _flush()
                current = [line]
            else:
                current.append(line)
        _flush()
        return sections or [answer_text.strip()]

    def _find_quotes(self, text):
        quotes = []
        paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
        for paragraph in paragraphs:
            for match in re.finditer(r"\"([^\"]+)\"", paragraph):
                quote_text = match.group(1).strip()
                if quote_text:
                    quotes.append((quote_text, paragraph))
        return quotes

    @staticmethod
    def _sentence_split(text):
        sentence_re = re.compile(r"[^.!?\n]+(?:[.!?](?=\s|$))?", re.M)
        return [match.group(0).strip() for match in sentence_re.finditer(text) if match.group(0).strip()]

    def _split_claims(self, text):
        claims = []
        for line in str(text or "").splitlines():
            if not line.strip():
                continue
            bullet_match = re.match(r"^(\s*(?:[-*+]\s+|\d+[.)]\s+))(.*)$", line)
            prefix = bullet_match.group(1) if bullet_match else ""
            body = bullet_match.group(2) if bullet_match else line
            for sentence in self._sentence_split(body):
                claims.append((prefix, sentence.strip()))
                prefix = ""
        return claims

    @staticmethod
    def _extract_source_labels(text):
        labels = set()
        for value in re.findall(r"\[(Chunk\s+\d+|S\d+(?:\s*,\s*S\d+)*)\]", str(text or "")):
            parts = [part.strip() for part in value.split(",")]
            for part in parts:
                if part:
                    labels.add(part)
        return sorted(labels)

    @staticmethod
    def _claim_tokens(text):
        stop_words = {
            "the", "and", "that", "with", "from", "this", "have", "were", "been", "they",
            "their", "about", "would", "could", "there", "which", "what", "when", "where",
            "while", "into", "than", "then", "them", "also", "only", "other", "after",
            "before", "under", "over", "between", "because", "during", "across", "within",
        }
        tokens = re.findall(r"[A-Za-z0-9]{4,}", text.lower())
        return {token for token in tokens if token not in stop_words}

    def _get_claim_embedding_model(self):
        if hasattr(self, "_claim_embedding_model"):
            return self._claim_embedding_model
        try:
            self._claim_embedding_model = self.get_embeddings()
        except Exception as exc:
            self._claim_embedding_model = None
            self.log(f"Claim-level embedding support unavailable; using lexical overlap. ({exc})")
        return self._claim_embedding_model

    @staticmethod
    def _cosine_similarity(vec_a, vec_b):
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0
        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        norm_a = sum(a * a for a in vec_a) ** 0.5
        norm_b = sum(b * b for b in vec_b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    def _claim_supported(self, claim_text, cited_chunks, chunks, chunk_tokens, chunk_embeddings, embedding_model):
        claim_tokens = self._claim_tokens(claim_text)
        if not claim_tokens:
            return False
        claim_embedding = None
        for chunk_num in cited_chunks:
            chunk_text = chunks.get(chunk_num, "")
            if not chunk_text:
                continue
            overlap = claim_tokens & chunk_tokens.get(chunk_num, set())
            if len(overlap) >= 2:
                ratio = len(overlap) / max(1, len(claim_tokens))
                if ratio >= 0.12:
                    return True
            if embedding_model is not None:
                if claim_embedding is None:
                    try:
                        claim_embedding = embedding_model.embed_query(claim_text)
                    except Exception:
                        claim_embedding = []
                chunk_embedding = chunk_embeddings.get(chunk_num)
                if claim_embedding and chunk_embedding:
                    if self._cosine_similarity(claim_embedding, chunk_embedding) >= 0.55:
                        return True
        return False

    def _best_supporting_chunk(self, claim_text, chunks, chunk_tokens, chunk_embeddings, embedding_model):
        claim_tokens = self._claim_tokens(claim_text)
        if not claim_tokens:
            return None, 0.0

        best_chunk = None
        best_score = 0.0
        claim_embedding = None
        for chunk_num, chunk_text in chunks.items():
            if not chunk_text:
                continue
            overlap = claim_tokens & chunk_tokens.get(chunk_num, set())
            overlap_ratio = len(overlap) / max(1, len(claim_tokens))
            score = overlap_ratio

            if embedding_model is not None:
                if claim_embedding is None:
                    try:
                        claim_embedding = embedding_model.embed_query(claim_text)
                    except Exception:
                        claim_embedding = []
                chunk_embedding = chunk_embeddings.get(chunk_num)
                if claim_embedding and chunk_embedding:
                    score = max(score, self._cosine_similarity(claim_embedding, chunk_embedding))

            if score > best_score:
                best_score = score
                best_chunk = chunk_num

        return best_chunk, best_score

    def _score_claim_support(self, claim_text, source_label, source_text, source_tokens, source_embeddings, embedding_model):
        claim_tokens = self._claim_tokens(claim_text)
        if not claim_tokens:
            return 0.0
        overlap = claim_tokens & source_tokens.get(source_label, set())
        lexical_ratio = len(overlap) / max(1, len(claim_tokens))
        lexical_score = min(1.0, lexical_ratio * 2.2)

        embed_score = 0.0
        if embedding_model is not None:
            try:
                claim_embedding = embedding_model.embed_query(claim_text)
                source_embedding = source_embeddings.get(source_label)
                if claim_embedding and source_embedding:
                    embed_score = max(0.0, self._cosine_similarity(claim_embedding, source_embedding))
            except Exception:
                embed_score = 0.0

        cross_encoder_score = 0.0
        scorer = getattr(self, "_claim_cross_encoder", None)
        if scorer is not None:
            try:
                cross_encoder_score = max(0.0, float(scorer(claim_text, source_text)))
            except Exception:
                cross_encoder_score = 0.0

        return (0.55 * lexical_score) + (0.35 * embed_score) + (0.10 * cross_encoder_score)

    def _rewrite_claim_to_supported_generalization(self, claim_text, best_label, source_text):
        claim_core = re.sub(r"\[(?:Chunk\s+\d+|S\d+(?:\s*,\s*S\d+)*)\]", "", claim_text).strip()
        source_sentences = self._sentence_split(source_text)
        claim_tokens = self._claim_tokens(claim_core)
        best_sentence = ""
        best_overlap = 0
        for sentence in source_sentences:
            overlap = len(claim_tokens & self._claim_tokens(sentence))
            if overlap > best_overlap:
                best_overlap = overlap
                best_sentence = sentence.strip()
        if best_sentence and len(best_sentence) > 16:
            generalized = best_sentence
        else:
            key_terms = sorted(claim_tokens)[:3]
            if key_terms:
                generalized = f"The evidence discusses {'; '.join(key_terms)}."
            else:
                return ""
        generalized = generalized.rstrip(" .") + "."
        generalized = re.sub(r"\s+", " ", generalized).strip()
        return f"{generalized} [{best_label}]"

    def _claim_level_grounding_validate(self, answer_text, context_text):
        sources = self._extract_sources(context_text)
        if not sources:
            return answer_text, []

        source_tokens = {label: self._claim_tokens(text) for label, text in sources.items()}
        embedding_model = self._get_claim_embedding_model()
        source_embeddings = {}
        if embedding_model is not None:
            try:
                labels = sorted(sources)
                vectors = embedding_model.embed_documents([sources[label] for label in labels])
                for label, vector in zip(labels, vectors):
                    source_embeddings[label] = vector
            except Exception as exc:
                embedding_model = None
                self.log(f"Claim-level source embeddings unavailable; using lexical overlap. ({exc})")

        kept = []
        failures = []
        support_threshold = 0.58 if embedding_model is not None else 0.32
        rewrite_threshold = max(0.22, support_threshold - 0.18)
        factual_hint_re = re.compile(r"\b(is|are|was|were|has|have|had|shows?|indicates?|states?|reports?|found|observed|according|caused?|led|resulted)\b", re.I)

        for prefix, claim in self._split_claims(answer_text):
            if not claim:
                continue
            if re.match(r"^\s{0,3}#{1,6}\s+\S", claim):
                kept.append(f"{prefix}{claim}" if prefix else claim)
                continue
            is_factual = bool(factual_hint_re.search(claim)) or len(claim) >= 40
            if not is_factual:
                kept.append(f"{prefix}{claim}" if prefix else claim)
                continue

            cited_labels = self._extract_source_labels(claim)
            candidate_labels = cited_labels or list(sources.keys())
            scored = []
            claim_wo_cites = re.sub(r"\[(?:Chunk\s+\d+|S\d+(?:\s*,\s*S\d+)*)\]", "", claim).strip()
            for label in candidate_labels:
                source_text = sources.get(label, "")
                if not source_text:
                    continue
                score = self._score_claim_support(
                    claim_wo_cites, label, source_text, source_tokens, source_embeddings, embedding_model
                )
                scored.append((score, label))
            scored.sort(reverse=True)

            if scored and scored[0][0] >= support_threshold:
                best_label = scored[0][1]
                kept_claim = f"{claim_wo_cites} [{best_label}]".strip()
                kept.append(f"{prefix}{kept_claim}" if prefix else kept_claim)
                continue

            if scored and scored[0][0] >= rewrite_threshold:
                best_label = scored[0][1]
                rewritten = self._rewrite_claim_to_supported_generalization(
                    claim_wo_cites, best_label, sources.get(best_label, "")
                )
                if rewritten:
                    kept.append(f"{prefix}{rewritten}" if prefix else rewritten)
                    failures.append("Generalized weakly supported claim to grounded statement.")
                    continue

            failures.append("Dropped unsupported factual claim during claim-level grounding.")

        cleaned = "\n".join(line for line in kept if line.strip()).strip()
        return cleaned, failures

    def _claim_level_sanitize(self, answer_text, context_text):
        bullet_re = re.compile(r"^(\s*(?:[-*+]\s+|\d+[.)]\s+))(.*)$")
        chunks = self._extract_chunks(context_text)
        chunk_tokens = {num: self._claim_tokens(text) for num, text in chunks.items()}
        embedding_model = self._get_claim_embedding_model() if chunks else None
        chunk_embeddings = {}
        if embedding_model is not None:
            try:
                texts = [chunks[num] for num in sorted(chunks)]
                vectors = embedding_model.embed_documents(texts)
                for num, vector in zip(sorted(chunks), vectors):
                    chunk_embeddings[num] = vector
            except Exception as exc:
                chunk_embeddings = {}
                embedding_model = None
                self.log(f"Claim-level chunk embeddings unavailable; using lexical overlap. ({exc})")

        failures = []
        cleaned_lines = []
        factual_hint_re = re.compile(r"\b(is|are|was|were|has|have|had|shows?|indicates?|states?|reports?|found|observed|according|caused?|led|resulted)\b", re.I)

        for raw_line in answer_text.splitlines():
            if not raw_line.strip():
                cleaned_lines.append(raw_line)
                continue
            if re.match(r"^\s{0,3}#{1,6}\s+\S", raw_line):
                cleaned_lines.append(raw_line)
                continue

            bullet_match = bullet_re.match(raw_line)
            bullet_prefix = ""
            body = raw_line
            if bullet_match:
                bullet_prefix = bullet_match.group(1)
                body = bullet_match.group(2)

            bullet_citations = self._extract_chunk_citation_numbers(body)
            sentences = self._sentence_split(body)
            if not sentences:
                cleaned_lines.append(raw_line)
                continue

            kept_sentences = []
            for sentence in sentences:
                is_factual = bool(factual_hint_re.search(sentence)) or len(sentence) >= 40
                if not is_factual:
                    kept_sentences.append(sentence)
                    continue

                sentence_citations = self._extract_chunk_citation_numbers(sentence)
                cited_chunks = sentence_citations or bullet_citations

                has_supported_citation = bool(cited_chunks) and self._claim_supported(
                    sentence,
                    cited_chunks,
                    chunks,
                    chunk_tokens,
                    chunk_embeddings,
                    embedding_model,
                )
                if has_supported_citation:
                    kept_sentences.append(sentence)
                    continue

                best_chunk, best_score = self._best_supporting_chunk(
                    sentence,
                    chunks,
                    chunk_tokens,
                    chunk_embeddings,
                    embedding_model,
                )
                support_threshold = 0.12 if embedding_model is None else 0.55
                if best_chunk is not None and best_score >= support_threshold:
                    sentence_wo_chunk_cites = re.sub(r"\[Chunk\s+\d+\]", "", sentence).rstrip()
                    sentence_wo_chunk_cites = re.sub(r"\s{2,}", " ", sentence_wo_chunk_cites).strip()
                    sentence = f"{sentence_wo_chunk_cites} [Chunk {best_chunk}]".strip()
                    kept_sentences.append(sentence)
                    if cited_chunks:
                        failures.append("Repaired weakly grounded claim by reattaching best supporting citation.")
                    else:
                        failures.append("Added citation to previously uncited factual claim.")
                    continue

                if cited_chunks:
                    failures.append("Removed factual claim with unsupported citation evidence.")
                else:
                    failures.append("Removed uncited factual claim with no supporting evidence.")
                continue

            if not kept_sentences:
                continue
            rebuilt = " ".join(kept_sentences).strip()
            cleaned_lines.append(f"{bullet_prefix}{rebuilt}" if bullet_prefix else rebuilt)

        cleaned_text = "\n".join(cleaned_lines).strip()
        return cleaned_text, failures

    @staticmethod
    def _strip_unsupported_placeholders(text):
        cleaned = str(text or "")
        cleaned = re.sub(r"(?im)^.*not\s+found(?:\s+in\s+context)?[^\n]*$", "", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned.strip()

    @staticmethod
    def _summarize_failures(failures):
        unique = []
        seen = set()
        for item in failures:
            key = item.strip()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(key)
            if len(unique) >= 5:
                break
        return unique

    def _validate_answer(self, answer_text, context_text, output_style):
        failures = []
        citation_re = self._citation_references_regex()
        heading_re = re.compile(r"^\s{0,3}#{1,6}\s+\S+")
        setext_re = re.compile(r"^[=-]{3,}\s*$")
        verb_re = re.compile(
            r"\b("
            r"is|are|was|were|be|been|being|"
            r"has|have|had|"
            r"does|do|did|"
            r"shows?|indicates?|suggests?|states?|notes?|reports?|"
            r"causes?|led|leads?|resulted|results?|"
            r"increases?|decreases?|"
            r"includes?|including|"
            r"found|finds?|observed|estimated|expected|"
            r"according"
            r")\b",
            re.IGNORECASE,
        )
        structural_labels = {
            "executive summary",
            "summary",
            "overview",
            "timeline",
            "background",
            "context",
            "approach",
            "methodology",
            "analysis",
            "findings",
            "discussion",
            "recommendations",
            "next steps",
            "conclusion",
            "appendix",
        }
        min_citation_chars = 40

        def is_structural_paragraph(paragraph_text: str) -> bool:
            lines = [line.strip() for line in paragraph_text.splitlines() if line.strip()]
            if not lines:
                return True
            if len(lines) == 1:
                line = lines[0]
                if heading_re.match(line):
                    return True
                if line.rstrip(":").strip().lower() in structural_labels:
                    return True
                if line.endswith(":") and len(line.split()) <= 5:
                    return True
            if len(lines) == 2 and setext_re.match(lines[1]):
                return True
            return False

        def needs_citation(paragraph_text: str) -> bool:
            if is_structural_paragraph(paragraph_text):
                return False
            alnum_match = re.search(r"[A-Za-z0-9]", paragraph_text)
            if not alnum_match:
                return False
            if verb_re.search(paragraph_text):
                return True
            return len(paragraph_text.strip()) >= min_citation_chars

        paragraphs = [p for p in re.split(r"\n\s*\n", answer_text) if p.strip()]
        for paragraph in paragraphs:
            if needs_citation(paragraph) and not citation_re.search(paragraph):
                failures.append(
                    "Factual paragraph missing at least one citation ([Chunk N] or [S#])."
                )

        if output_style in {"Script / talk track", "Structured report"}:
            chunks = self._extract_chunks(context_text)
            sections = self._split_major_sections(answer_text)
            for index, section in enumerate(sections, start=1):
                quotes = self._find_quotes(section)
                section_has_quote = False
                for quote_text, paragraph in quotes:
                    word_count = len(quote_text.split())
                    if word_count > 25:
                        continue
                    chunk_citations = self._extract_chunk_citation_numbers(paragraph)
                    if not chunk_citations and re.search(r"\[S\d+(?:\s*,\s*S\d+)*\]", paragraph):
                        section_has_quote = True
                        break
                    for chunk_num in chunk_citations:
                        chunk_text = chunks.get(chunk_num, "")
                        if quote_text in chunk_text:
                            section_has_quote = True
                            break
                    if section_has_quote:
                        break
                if not section_has_quote:
                    failures.append(
                        "Missing short verbatim quote (<=25 words) with valid citation "
                        f"in section {index}."
                    )

        return len(failures) == 0, failures

    def _repair_answer(self, draft_text, context_text, failures, output_style):
        repair_llm = self._get_llm_with_temperature(0.0)
        failure_text = "\n".join(f"- {item}" for item in failures)
        repair_prompt = (
            "You are a repair assistant. Fix the draft using ONLY the provided context. "
            "Rules: remove unsupported content, add correct citations ([Chunk N] or [S#]) to every "
            "factual paragraph, include no placeholders, and omit unsupported content. "
            "Omit unsupported claims; deepen supported ones; do not ask for more docs or missing info; "
            "do not use placeholders. If evidence is thin, you may include one short 'Scope:' note "
            "at the top. "
            "For Script / talk track and Structured report styles, ensure at least one short "
            "verbatim quote (<=25 words) per major section with a citation, and "
            "the quote must appear in the cited chunk text. "
            "Output ONLY the repaired answer."
        )
        repair_messages = [
            self._system_message(content=repair_prompt),
            self._human_message(
                content=(
                    f"OUTPUT_STYLE: {output_style}\n\n"
                    f"FAILURES:\n{failure_text}\n\n"
                    f"CONTEXT:\n{context_text}\n\n"
                    f"DRAFT:\n{draft_text}"
                )
            ),
        ]
        repaired = repair_llm.invoke(repair_messages)
        return repaired.content

    def _validate_and_repair(self, answer_text, context_text, iteration_id=None, evidence_pack_mode=False, synthesis_cards=None):
        answer_text = self._strip_unsupported_placeholders(answer_text)
        output_style = self.output_style.get().strip()
        agentic_mode = self.agentic_mode.get()
        if evidence_pack_mode:
            answer_text = self._verify_evidence_pack_claims(
                answer_text, synthesis_cards or self._last_evidence_pack_synthesis_cards
            )
            if iteration_id is not None:
                self.log(
                    "Iter "
                    f"{iteration_id} repair | style={output_style}, "
                    f"agentic={int(agentic_mode)}, triggered=0, failures=none"
                )
            return answer_text

        claim_level_enabled = self._frontier_enabled("claim_level_grounding_citefix_lite")
        chunks_available = bool(self._extract_chunks(context_text))
        if not chunks_available:
            chunks_available = bool(self._extract_sources(context_text))

        failures = []
        if claim_level_enabled:
            answer_text, claim_failures = self._claim_level_grounding_validate(answer_text, context_text)
            failures.extend(claim_failures)
            is_valid = len(claim_failures) == 0
        elif chunks_available:
            answer_text, claim_failures = self._claim_level_sanitize(answer_text, context_text)
            failures.extend(claim_failures)
            is_valid = len(claim_failures) == 0
        else:
            is_valid, fallback_failures = self._validate_answer(
                answer_text, context_text, output_style
            )
            failures.extend(fallback_failures)
        if is_valid:
            unique_failures = self._summarize_failures(failures)
            if iteration_id is not None:
                self.log(
                    "Iter "
                    f"{iteration_id} repair | style={output_style}, "
                    f"agentic={int(agentic_mode)}, triggered=0, failures=none"
                )
            if unique_failures:
                self.log(
                    "Claim-level pass removed/adjusted unsupported content. Top unique issues: "
                    + "; ".join(unique_failures)
                )
            return answer_text
        unique_failures = self._summarize_failures(failures)
        self.log(
            "Validation failed; triggering repair pass. Reasons: "
            + "; ".join(unique_failures)
        )
        if iteration_id is not None:
            self.log(
                "Iter "
                f"{iteration_id} repair | style={output_style}, "
                f"agentic={int(agentic_mode)}, triggered=1, failures="
                + "; ".join(unique_failures)
            )
        repaired = self._repair_answer(answer_text, context_text, unique_failures, output_style)
        repaired = self._append_missing_citations(repaired, context_text)
        if claim_level_enabled:
            repaired, post_failures = self._claim_level_grounding_validate(repaired, context_text)
        else:
            repaired, post_failures = self._claim_level_sanitize(repaired, context_text)
        post_unique = self._summarize_failures(post_failures)
        if post_unique:
            self.log(
                "Post-repair claim-level cleanup applied. Top unique issues: "
                + "; ".join(post_unique)
            )
        return self._strip_unsupported_placeholders(repaired)

    def _append_missing_citations(self, answer_text, context_text):
        citation_re = self._citation_references_regex()
        paragraphs = [p for p in re.split(r"\n\s*\n", answer_text) if p.strip()]
        missing = [
            idx
            for idx, paragraph in enumerate(paragraphs)
            if re.search(r"[A-Za-z0-9]", paragraph)
            and not citation_re.search(paragraph)
        ]
        if not missing:
            return answer_text

        chunks = self._extract_chunks(context_text)
        if not chunks:
            return answer_text

        def _tokens(text):
            return set(re.findall(r"[A-Za-z0-9]{4,}", text.lower()))

        chunk_tokens = {num: _tokens(text) for num, text in chunks.items()}
        updated = list(paragraphs)
        for idx in missing:
            paragraph = paragraphs[idx]
            paragraph_tokens = _tokens(paragraph)
            best_chunk = None
            best_score = 0
            for chunk_num in sorted(chunk_tokens):
                score = len(paragraph_tokens & chunk_tokens[chunk_num])
                if score > best_score:
                    best_score = score
                    best_chunk = chunk_num
            if best_chunk and best_score > 0:
                updated[idx] = paragraph.rstrip() + f" [Chunk {best_chunk}]"
        return "\n\n".join(updated)

    def _refresh_instructions_box(self):
        self.instructions_box.delete("1.0", tk.END)
        self.instructions_box.insert(tk.END, self.system_instructions.get())

    def _resolve_llm_model(self):
        selected = self.llm_model.get().strip()
        custom = self.llm_model_custom.get().strip()
        if selected == "custom":
            if not custom:
                raise ValueError("Custom generation model is selected but empty")
            return custom
        return selected or custom

    def _resolve_embedding_model(self):
        selected = self.embedding_model.get().strip()
        custom = self.embedding_model_custom.get().strip()
        if selected == "custom":
            if not custom:
                raise ValueError("Custom embedding model is selected but empty")
            return custom
        return selected or custom

    def get_embeddings(self):
        """Factory for embedding model"""
        provider = self.embedding_provider.get()
        api_key = self.api_keys[provider].get() if provider in self.api_keys else ""
        model_name = self._resolve_embedding_model()

        if provider == "openai":
            try:
                from langchain_openai import OpenAIEmbeddings
            except ImportError as err:
                self._prompt_dependency_install(
                    ["langchain-openai"], "OpenAI embeddings", err
                )
                raise

            if not api_key:
                raise ValueError("OpenAI API Key missing")
            return OpenAIEmbeddings(openai_api_key=api_key, model=model_name)

        if provider == "google":
            try:
                from langchain_google_genai import GoogleGenerativeAIEmbeddings
            except ImportError as err:
                self._prompt_dependency_install(
                    ["langchain-google-genai"], "Google embeddings", err
                )
                raise

            if not api_key:
                raise ValueError("Google API Key missing")
            return GoogleGenerativeAIEmbeddings(google_api_key=api_key, model=model_name)

        if provider == "voyage":
            try:
                from langchain_voyageai import VoyageAIEmbeddings
                embedding_cls = VoyageAIEmbeddings
            except ImportError as err:
                try:
                    module = __import__("langchain_voyageai", fromlist=["VoyageEmbeddings"])
                except ImportError as module_err:
                    self._prompt_dependency_install(
                        ["langchain-voyageai"], "Voyage embeddings", module_err
                    )
                    raise
                if hasattr(module, "VoyageEmbeddings"):
                    embedding_cls = module.VoyageEmbeddings
                else:
                    mismatch_msg = (
                        "langchain-voyageai is installed but does not export "
                        "VoyageAIEmbeddings or VoyageEmbeddings. This is likely an "
                        "API mismatch; please upgrade or downgrade langchain-voyageai."
                    )
                    self._prompt_dependency_install(
                        ["langchain-voyageai"], "Voyage embeddings (API mismatch)", mismatch_msg
                    )
                    raise ImportError(mismatch_msg) from err

            if not api_key:
                raise ValueError("Voyage API Key missing")
            return embedding_cls(voyage_api_key=api_key, model=model_name)

        if provider == "local_huggingface":
            # Uses local CPU/GPU via HuggingFace
            try:
                from langchain_community.embeddings import HuggingFaceEmbeddings
            except (ImportError, AttributeError) as err:
                self._prompt_dependency_install(
                    ["langchain-community"], "Local HuggingFace embeddings", err
                )
                raise

            resolved_model = model_name or "all-MiniLM-L6-v2"
            self.log(f"Loading local HuggingFace embeddings ({resolved_model})...")
            return HuggingFaceEmbeddings(model_name=resolved_model)

        raise ValueError(f"Unknown embedding provider: {provider}")

    def get_llm(self):
        """Factory for LLM"""
        validated = self._validate_model_settings()
        if not validated:
            raise ValueError("Invalid model settings")
        temperature, gui_llm_max_tokens = validated
        provider = self.llm_provider.get()
        model_name = self._resolve_llm_model()
        output_max_tokens = self._get_capped_output_tokens(
            provider, model_name, gui_llm_max_tokens
        )

        if provider == "openai":
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as err:
                self._prompt_dependency_install(["langchain-openai"], "OpenAI LLM", err)
                raise

            key = self.api_keys["openai"].get()
            return ChatOpenAI(
                api_key=key,
                model=model_name,
                temperature=temperature,
                max_tokens=output_max_tokens,
            )

        if provider == "anthropic":
            try:
                from langchain_anthropic import ChatAnthropic
            except ImportError as err:
                self._prompt_dependency_install(
                    ["langchain-anthropic"], "Anthropic LLM", err
                )
                raise

            key = self.api_keys["anthropic"].get()
            return ChatAnthropic(
                api_key=key,
                model=model_name,
                temperature=temperature,
                max_tokens=output_max_tokens,
            )

        if provider == "google":
            try:
                from langchain_google_genai import ChatGoogleGenerativeAI
            except ImportError as err:
                self._prompt_dependency_install(
                    ["langchain-google-genai"], "Google LLM", err
                )
                raise

            key = self.api_keys["google"].get()
            return ChatGoogleGenerativeAI(
                google_api_key=key,
                model=model_name,
                temperature=temperature,
                max_output_tokens=output_max_tokens,
            )

        if provider == "local_lm_studio":
            try:
                from langchain_openai import ChatOpenAI
            except ImportError as err:
                self._prompt_dependency_install(
                    ["langchain-openai"], "Local LLM Studio", err
                )
                raise

            url = self.local_llm_url.get()
            self.log(f"Connecting to Local LLM at {url}...")
            # LM Studio uses OpenAI compatible endpoint
            return ChatOpenAI(
                base_url=url,
                api_key="lm-studio",
                model=model_name,
                temperature=temperature,
                max_tokens=output_max_tokens,
            )

        raise ValueError(f"Unknown LLM provider: {provider}")

    def _get_llm_with_temperature(self, temperature):
        original_temperature = self.llm_temperature.get()
        self.llm_temperature.set(temperature)
        try:
            return self.get_llm()
        finally:
            self.llm_temperature.set(original_temperature)

    def start_ingestion(self):
        if not self._startup_pipeline_finished:
            messagebox.showinfo("Please wait", "Initialisation is still running. Please retry in a moment.")
            return
        if not self.selected_file:
            messagebox.showerror("Error", "Please select a file first.")
            return

        threading.Thread(target=self._ingest_process, daemon=True).start()

    def _ingest_process(self):
        try:
            self._run_on_ui(self.btn_ingest.config, state="disabled")
            self._frontier_evidence_pack_mode = False
            self.log("Starting ingestion pipeline...")
            self.log(
                "Frontier flags (ingestion): "
                f"langextract={self._frontier_enabled('langextract')}, "
                f"structured_incidents={self._frontier_enabled('structured_incidents')}, "
                f"recursive_memory={self._frontier_enabled('recursive_memory')}, "
                f"citation_v2={self._frontier_enabled('citation_v2')}, "
                f"agent_lightning_telemetry={self._frontier_enabled('agent_lightning_telemetry')}"
            )

            # 1. Load & Clean
            self.log("Step 1/4: Parsing File...")
            text_content = ""

            chatgpt_messages = None
            if self.selected_file.lower().endswith(".html"):
                from bs4 import BeautifulSoup
                from bs4 import NavigableString

                def _normalize_timestamp(raw_timestamp):
                    if raw_timestamp is None:
                        return None
                    candidate = str(raw_timestamp).strip()
                    if not candidate:
                        return None
                    compact = re.sub(r"\s+", " ", candidate)
                    iso_candidate = compact.replace("Z", "+00:00")
                    try:
                        return datetime.fromisoformat(iso_candidate).isoformat()
                    except ValueError:
                        return compact

                def _contains_quoted_primary_evidence(text):
                    if not text:
                        return False
                    lowered = text.lower()
                    quote_markers = [
                        r'"[^"\n]{8,}"',
                        r"'[^'\n]{8,}'",
                        r"“[^”\n]{8,}”",
                        r"‘[^’\n]{8,}’",
                        r"(^|\n)>\s*.+",
                    ]
                    has_quote = any(
                        re.search(pattern, text, flags=re.MULTILINE)
                        for pattern in quote_markers
                    )
                    if not has_quote:
                        return False
                    evidence_signals = [
                        "user",
                        "customer",
                        "client",
                        "transcript",
                        "email",
                        "chat",
                        "message",
                        "said",
                        "wrote",
                    ]
                    return any(signal in lowered for signal in evidence_signals)

                def _detect_message_role(node):
                    classes = [cls.lower() for cls in (node.get("class") or [])]
                    class_blob = " ".join(classes)
                    if "user-message" in classes or re.search(r"\buser\b", class_blob):
                        return "user"
                    if "assistant-message" in classes or re.search(
                        r"\bassistant\b", class_blob
                    ):
                        return "assistant"

                    attr_candidates = [
                        node.get("data-message-author-role"),
                        node.get("data-author-role"),
                        node.get("data-role"),
                        node.get("aria-label"),
                        node.get("data-testid"),
                    ]
                    for value in attr_candidates:
                        lowered = str(value or "").strip().lower()
                        if not lowered:
                            continue
                        if "user" in lowered:
                            return "user"
                        if any(token in lowered for token in ["assistant", "chatgpt", "model"]):
                            return "assistant"

                    role_label_node = node.find(
                        attrs={"data-message-author-role": True}
                    )
                    if role_label_node:
                        nested_role = str(
                            role_label_node.get("data-message-author-role") or ""
                        ).strip().lower()
                        if nested_role in {"user", "assistant"}:
                            return nested_role

                    return "unknown"

                def _extract_timestamp(node):
                    time_node = node.find("time")
                    if time_node:
                        raw = time_node.get("datetime") or time_node.get_text(
                            " ", strip=True
                        )
                        parsed = _normalize_timestamp(raw)
                        if parsed:
                            return parsed, time_node

                    timestamp_node = node.select_one(
                        ".timestamp, [data-testid*='timestamp'], [class*='timestamp']"
                    )
                    if timestamp_node:
                        raw = timestamp_node.get("datetime") or timestamp_node.get_text(
                            " ", strip=True
                        )
                        parsed = _normalize_timestamp(raw)
                        if parsed:
                            return parsed, timestamp_node

                    return None, None

                def _extract_chatgpt_messages(soup):
                    message_nodes = soup.select(
                        "div.message.user-message, "
                        "div.message.assistant-message, "
                        "[data-message-author-role], "
                        "article[data-testid*='conversation-turn'], "
                        "div[data-testid*='conversation-turn']"
                    )
                    if not message_nodes:
                        return None
                    extracted = []
                    seen_messages = set()
                    for node in message_nodes:
                        role = _detect_message_role(node)
                        timestamp, timestamp_node = _extract_timestamp(node)
                        node_copy = BeautifulSoup(str(node), "html.parser")
                        if timestamp_node:
                            copy_time_node = node_copy.find("time") or node_copy.select_one(
                                ".timestamp, [data-testid*='timestamp'], [class*='timestamp']"
                            )
                            if copy_time_node:
                                copy_time_node.extract()
                        content = node_copy.get_text(" ", strip=True)
                        if not content:
                            continue
                        dedupe_key = (role, timestamp, content)
                        if dedupe_key in seen_messages:
                            continue
                        seen_messages.add(dedupe_key)
                        extracted.append(
                            {
                                "role": role,
                                "timestamp": timestamp,
                                "content": content,
                            }
                        )
                    return extracted

                def _append_text_line(lines, text):
                    clean = text.strip()
                    if clean:
                        lines.append(clean)

                def _process_table(table_tag, lines):
                    for row in table_tag.find_all("tr"):
                        cells = [
                            cell.get_text(" ", strip=True)
                            for cell in row.find_all(["th", "td"])
                        ]
                        if any(cells):
                            lines.append(" | ".join(cells))

                def _process_list(list_tag, lines):
                    for item in list_tag.find_all("li", recursive=False):
                        nested_lists = item.find_all(["ul", "ol"], recursive=False)
                        for nested in nested_lists:
                            nested.extract()
                        item_text = " ".join(item.stripped_strings)
                        if item_text:
                            lines.append(f"- {item_text}")
                        for nested in nested_lists:
                            _process_list(nested, lines)

                def _process_children(parent, lines):
                    for child in parent.children:
                        if isinstance(child, NavigableString):
                            _append_text_line(lines, str(child))
                            continue
                        if not hasattr(child, "name"):
                            continue
                        if child.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
                            heading_text = child.get_text(" ", strip=True)
                            if heading_text:
                                lines.append(f"### {heading_text}")
                            continue
                        if child.name in {"ul", "ol"}:
                            _process_list(child, lines)
                            continue
                        if child.name == "table":
                            _process_table(child, lines)
                            continue
                        if child.name in {"p", "pre", "blockquote"}:
                            paragraph_text = child.get_text(" ", strip=True)
                            _append_text_line(lines, paragraph_text)
                            continue
                        _process_children(child, lines)

                with open(self.selected_file, "r", encoding="utf-8", errors="ignore") as f:
                    soup = BeautifulSoup(f, "html.parser")
                    doc_title = None
                    if soup.title and soup.title.string:
                        doc_title = soup.title.string.strip() or None
                    # Aggressive cleaning for RAG
                    for tag in soup(["script", "style", "svg", "path", "nav", "footer"]):
                        tag.extract()
                    chatgpt_messages = _extract_chatgpt_messages(soup)
                    if chatgpt_messages:
                        text_content = "\n".join(
                            msg["content"] for msg in chatgpt_messages if msg["content"]
                        )
                    else:
                        lines = []
                        root = soup.body or soup
                        _process_children(root, lines)
                        text_content = "\n".join(lines)
            else:
                with open(self.selected_file, "r", encoding="utf-8") as f:
                    text_content = f.read()
                doc_title = None

            self.log(f"File loaded. Raw text length: {len(text_content)} characters.")

            # 2. Split
            self.log("Step 2/4: Splitting Text...")
            try:
                from langchain.text_splitter import RecursiveCharacterTextSplitter
            except ImportError:
                from langchain_text_splitters import RecursiveCharacterTextSplitter

            chunk_ingest_id = datetime.now(timezone.utc).isoformat()
            source_basename = os.path.basename(self.selected_file)
            chatgpt_docs = None
            if chatgpt_messages:
                chatgpt_docs = []
                for index, message in enumerate(chatgpt_messages, start=1):
                    role = message.get("role") or "unknown"
                    content = message["content"]
                    prefixed_content = f"[ROLE={role}] {content}".strip()
                    if role == "user":
                        evidence_kind = "primary"
                    elif role == "assistant":
                        evidence_kind = (
                            "primary" if _contains_quoted_primary_evidence(content) else "advice"
                        )
                    else:
                        evidence_kind = "unknown"
                    metadata = {
                        "role": role,
                        "speaker_role": role,
                        "message_index": index,
                        "evidence_kind": evidence_kind,
                        "source": source_basename,
                        "source_path": self.selected_file,
                        "chunk_id": index,
                        "ingest_id": chunk_ingest_id,
                    }
                    if message.get("timestamp"):
                        metadata["timestamp"] = message["timestamp"]
                    if doc_title:
                        metadata["doc_title"] = doc_title
                    metadata = self._ensure_source_metadata(
                        metadata, self.selected_file, prefixed_content
                    )
                    chatgpt_docs.append(
                        self._document(page_content=prefixed_content, metadata=metadata)
                    )

            if chatgpt_docs is not None:
                docs = chatgpt_docs
            else:
                splitter = RecursiveCharacterTextSplitter(
                    chunk_size=self.chunk_size.get(),
                    chunk_overlap=self.chunk_overlap.get(),
                    separators=["\n\n", "\n", ".", " ", ""],
                )
                docs = splitter.create_documents([text_content])

            chapter_markers, section_markers = self._detect_structure_markers(text_content)

            def _last_section_title(text):
                last_heading = None
                for line in text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith("### "):
                        candidate = stripped[4:].strip()
                        if candidate:
                            last_heading = candidate
                return last_heading

            if chatgpt_docs is None:
                last_section_title = None
                search_cursor = 0
                for chunk_id, doc in enumerate(docs, start=1):
                    section_title = _last_section_title(doc.page_content)
                    if section_title:
                        last_section_title = section_title
                    chunk_body = str(doc.page_content or "")
                    char_start = text_content.find(chunk_body, search_cursor)
                    if char_start < 0:
                        char_start = text_content.find(chunk_body)
                    if char_start < 0:
                        char_start = search_cursor
                    char_end = char_start + len(chunk_body)
                    search_cursor = max(search_cursor, max(char_end - self.chunk_overlap.get(), char_start))
                    active_chapter = self._structure_at_offset(char_start, chapter_markers)
                    active_section = self._structure_at_offset(char_start, section_markers)
                    metadata = (doc.metadata or {}).copy()
                    metadata.update(
                        {
                            "source": source_basename,
                            "source_path": self.selected_file,
                            "chunk_id": chunk_id,
                            "ingest_id": chunk_ingest_id,
                            "char_start": char_start,
                            "char_end": char_end,
                        }
                    )
                    if doc_title:
                        metadata["doc_title"] = doc_title
                    if last_section_title:
                        metadata["section_title"] = last_section_title
                    if active_chapter.get("chapter_title"):
                        metadata["chapter_title"] = active_chapter.get("chapter_title")
                    if active_chapter.get("chapter_idx"):
                        metadata["chapter_idx"] = active_chapter.get("chapter_idx")
                    if active_section.get("section_title") and not metadata.get("section_title"):
                        metadata["section_title"] = active_section.get("section_title")
                    if active_section.get("section_idx"):
                        metadata["section_idx"] = active_section.get("section_idx")
                    metadata = self._ensure_source_metadata(
                        metadata, self.selected_file, doc.page_content
                    )
                    doc.metadata = metadata
            self.log(f"Created {len(docs)} text chunks.")

            db_type = self.vector_db_type.get()
            if db_type == "chroma":
                if self._upsert_lexical_chunks(docs):
                    self.log(f"Lexical sidecar updated: {self.lexical_db_path}")

            concept_cards = []
            comprehension_artifacts = []
            if self.build_comprehension_index.get():
                source_map_seed, _ = self._build_source_cards(docs)
                concept_cards = self._build_comprehension_cards(
                    docs,
                    chunk_ingest_id,
                    doc_title,
                    source_map_seed,
                )
                comprehension_artifacts = self._build_comprehension_artifacts(
                    docs,
                    chunk_ingest_id,
                    source_map_seed,
                )
                stored_cards = self._upsert_concept_cards(chunk_ingest_id, concept_cards)
                stored_artifacts = self._upsert_comprehension_artifacts(chunk_ingest_id, comprehension_artifacts)
                jsonl_path = self._write_comprehension_jsonl(chunk_ingest_id, comprehension_artifacts)
                self.log(
                    f"Comprehension index built: {stored_cards} concept cards, {stored_artifacts} structured artifacts "
                    f"(depth={self.comprehension_extraction_depth.get()}, "
                    f"langextract={'on' if langextract is not None else 'fallback'})."
                )
                if jsonl_path:
                    self.log(f"Comprehension JSONL exported: {jsonl_path}")

            # 3. Initialize Vector DB & Embeddings
            self.log("Step 3/4: Initializing Vector Store...")
            embeddings = self.get_embeddings()

            new_index_path = None
            digest_docs = []
            summary_tree_docs = []
            summary_tree_artifact_path = ""

            if self.build_digest_index.get():
                if db_type == "chroma":
                    self.log("Building summary tree (L0 chunk, L1 chapter/section, L2 part, L3 book)...")
                    chunk_summary_docs = self._build_chunk_summary_nodes(
                        docs, chunk_ingest_id, source_basename, doc_title
                    )
                    section_digest_docs = self._build_digest_documents(
                        docs, chunk_ingest_id, source_basename, doc_title
                    )
                    chapter_digest_docs = self._build_chapter_digest_documents(
                        docs, chunk_ingest_id, source_basename, doc_title
                    )
                    part_digest_docs = self._build_part_digest_documents(
                        chapter_digest_docs,
                        chunk_ingest_id,
                        source_basename,
                        doc_title,
                    )
                    digest_docs = [*part_digest_docs, *chapter_digest_docs, *section_digest_docs]
                    summary_tree_docs = [*chunk_summary_docs, *digest_docs]
                    summary_tree_docs.extend(
                        self._build_document_summary_node(
                            part_digest_docs or chapter_digest_docs or section_digest_docs,
                            chunk_ingest_id,
                            source_basename,
                            doc_title,
                        )
                    )
                    self.log(
                        "Prepared summary tree nodes: "
                        f"chunk_summaries={len(chunk_summary_docs)}, "
                        f"chapter_digests={len(chapter_digest_docs)}, "
                        f"section_digests={len(section_digest_docs)}, "
                        f"part_digests={len(part_digest_docs)}, "
                        f"book_nodes={max(0, len(summary_tree_docs) - len(chunk_summary_docs) - len(digest_docs))}."
                    )
                else:
                    self.log("Digest indexing is only supported for Chroma. Skipping.")

            if db_type == "chroma":
                persist_root = self._get_chroma_persist_root()
                index_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                safe_stem = self._safe_file_stem(self.selected_file)
                persist_dir = os.path.join(
                    persist_root, f"{safe_stem}__{index_id}"
                )
                os.makedirs(persist_root, exist_ok=True)
                new_index_path = persist_dir
                if summary_tree_docs:
                    summary_tree_artifact_path = self._persist_summary_tree(
                        chunk_ingest_id,
                        summary_tree_docs,
                        persist_dir,
                    )
                try:
                    Chroma = _lazy_import_chroma()
                except ImportError as err:
                    self._prompt_dependency_install(
                        ["langchain-chroma", "chromadb"], "Chroma vector store", err
                    )
                    raise

                # Using a new client per ingestion to ensure clean slate or append
                self.vector_store = Chroma(
                    collection_name=RAW_COLLECTION_NAME,
                    embedding_function=embeddings,
                    persist_directory=persist_dir,
                )
            elif db_type == "weaviate":
                try:
                    weaviate, WeaviateVectorStore = _lazy_import_weaviate_stack()
                except ImportError as err:
                    self._prompt_dependency_install(
                        ["langchain-weaviate", "weaviate-client"],
                        "Weaviate vector store",
                        err,
                    )
                    raise

                url = self.api_keys["weaviate_url"].get()
                key = self.api_keys["weaviate_key"].get()
                auth = weaviate.auth.AuthApiKey(api_key=key) if key else None

                client = weaviate.Client(url=url, auth_client_secret=auth)
                self.vector_store = WeaviateVectorStore(
                    client=client, index_name="RagDocument", text_key="text", embedding=embeddings
                )
            else:
                raise ValueError(f"Unknown vector DB type: {db_type}")

            self.index_embedding_signature = self._current_embedding_signature()
            self.save_config()
            self._run_on_ui(self._refresh_compatibility_warning)

            # 4. Batch Embed & Upsert
            self.log("Step 4/4: Embedding & Storing (This takes time)...")
            batch_size = 100  # Adjust based on API limits
            total_docs = len(docs)

            self._run_on_ui(self.progress.config, maximum=total_docs, value=0)

            for i in range(0, total_docs, batch_size):
                batch = docs[i : i + batch_size]
                self.vector_store.add_documents(batch)
                self._run_on_ui(self.progress.config, value=i + len(batch))
                self.log(f"Indexed {min(i + batch_size, total_docs)}/{total_docs} chunks...")

            if summary_tree_docs:
                self.log("Storing summary tree nodes...")
                digest_store = Chroma(
                    collection_name=DIGEST_COLLECTION_NAME,
                    embedding_function=embeddings,
                    persist_directory=persist_dir,
                )
                total_digests = len(summary_tree_docs)
                for i in range(0, total_digests, batch_size):
                    batch = summary_tree_docs[i : i + batch_size]
                    digest_store.add_documents(batch)
                self.log(f"Indexed {total_digests} summary tree nodes.")
                if summary_tree_artifact_path:
                    self.log(f"Summary tree artifact saved: {summary_tree_artifact_path}")

            if concept_cards:
                concept_docs = []
                for card in concept_cards:
                    concept_docs.append(
                        self._document(
                            page_content=card.get("card_text") or "",
                            metadata={
                                "card_id": card.get("id"),
                                "kind": card.get("kind"),
                                "title": card.get("title"),
                                "source_refs_json": json.dumps(card.get("source_refs") or [], ensure_ascii=False),
                                "ingest_id": chunk_ingest_id,
                                "source": source_basename,
                                "content_type": "concept_card",
                            },
                        )
                    )
                if db_type == "chroma":
                    concept_store = Chroma(
                        collection_name=CONCEPT_COLLECTION_NAME,
                        embedding_function=embeddings,
                        persist_directory=persist_dir,
                    )
                    for i in range(0, len(concept_docs), batch_size):
                        concept_store.add_documents(concept_docs[i : i + batch_size])
                else:
                    self.vector_store.add_documents(concept_docs)
                self.log(f"Indexed {len(concept_docs)} concept cards for retrieval.")

            self.log("Ingestion Complete! You can now chat.")
            if new_index_path:
                def _select_new_index():
                    selection_label = self._format_index_label(new_index_path)
                    self._pending_selected_index_label = selection_label
                    self.selected_index_path = new_index_path
                    self.selected_collection_name = RAW_COLLECTION_NAME
                    self.save_config()
                    self._refresh_existing_indexes_async(reason="Loading indexes…")

                self._run_on_ui(_select_new_index)
            else:
                self._run_on_ui(self._refresh_existing_indexes_async)
            self._run_on_ui(
                messagebox.showinfo,
                "Success",
                "File successfully ingested into Vector Database.",
            )

        except Exception as e:
            self.log(f"INGESTION ERROR: {str(e)}")
            self._run_on_ui(messagebox.showerror, "Error", f"Ingestion failed:\n{str(e)}")
        finally:
            self._run_on_ui(self.btn_ingest.config, state="normal")

    def send_message(self):
        if not self._startup_pipeline_finished:
            self.append_chat("system", "Initialisation not finished yet. Please retry in a moment.")
            return
        query = self.txt_input.get()
        if not query:
            return

        self.txt_input.delete(0, tk.END)
        self.append_chat("user", f"You: {query}")
        self._append_history(self._human_message(content=query))
        self._insert_session_message(role="user", content=query)
        with sqlite3.connect(self.session_db_path) as conn:
            count_row = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id = ? AND role = 'user'",
                (self.current_session_id,),
            ).fetchone()
        if count_row and int(count_row[0]) == 1:
            self._maybe_autotitle_session(query)
        self.refresh_sessions_list()

        if self.index_embedding_signature:
            current_signature = self._current_embedding_signature()
            if (
                current_signature
                and current_signature != self.index_embedding_signature
                and not self.force_embedding_compat.get()
            ):
                self.append_chat(
                    "system",
                    "Embedding mismatch detected. Re-embed documents or enable force "
                    "compatibility to proceed.",
                )
                return

        if not self.vector_store:
            # Try to load existing DB if available
            try:
                self.log("Attempting to load existing Vector DB...")
                embeddings = self.get_embeddings()
                if self.vector_db_type.get() == "chroma":
                    selected_path, selected_collection = self._get_selected_index_path()
                    if not selected_path and self.selected_index_path:
                        if os.path.isdir(self.selected_index_path):
                            selected_path = self.selected_index_path
                    persist_dir = selected_path or self._get_chroma_persist_root()
                    collection_name = (
                        selected_collection or self.selected_collection_name or RAW_COLLECTION_NAME
                    )
                    Chroma = _lazy_import_chroma()

                    self.vector_store = Chroma(
                        collection_name=collection_name,
                        embedding_function=embeddings,
                        persist_directory=persist_dir,
                    )
                    if selected_path:
                        self.selected_index_path = selected_path
                        self.selected_collection_name = collection_name
                        self.save_config()
                        self.log(
                            "Active index set to "
                            f"{self._format_index_label(persist_dir, collection_name)}."
                        )
                else:
                    self.append_chat(
                        "system", "Error: No Weaviate connection. Please Ingest first."
                    )
                    return
            except Exception as e:
                self.append_chat("system", f"Error: Please ingest a file first. ({e})")
                return

        threading.Thread(target=self._rag_pipeline, args=(query,), daemon=True).start()

    def _rag_pipeline(self, query):
        stage = "retrieval"
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        run_started_at = time.perf_counter()
        self._active_run_id = run_id
        self._trace_events = []
        self._run_on_ui(self._set_readonly_text, self.trace_text, "")
        try:
            self.log("Starting Retrieval...")

            # 1. Retrieval
            output_style = self.output_style.get().strip() or "Default answer"
            resolved_settings = self._resolve_mode_profile_settings(query=query)
            retrieve_k = max(1, int(resolved_settings["retrieve_k"]))
            user_final_k = max(1, int(resolved_settings["final_k"]))
            final_k = user_final_k
            mode_name = resolved_settings["mode"]
            provider = self.llm_provider.get()
            model_name = self._resolve_llm_model()
            gui_llm_max_tokens = max(1, int(self.llm_max_tokens.get()))
            caps = self.get_model_caps(provider, model_name)
            output_max_tokens = self._get_capped_output_tokens(
                provider, model_name, gui_llm_max_tokens
            )
            context_budget_tokens = max(
                1024,
                int(caps.get("max_context_tokens", 8192))
                - output_max_tokens
                - CONTEXT_SAFETY_MARGIN_TOKENS,
            )
            candidate_k = max(retrieve_k, final_k)
            long_form_keywords = (
                "evidence",
                "evidence pack",
                "full report",
                "timeline",
                "all details",
                "complete",
                "extract all",
                "every",
                "required details",
            )
            normalized_query = query.lower()
            is_long_form = any(
                keyword in normalized_query for keyword in long_form_keywords
            )
            is_evidence_pack = bool(resolved_settings.get("evidence_pack_mode"))
            comprehension_first_intent = self._is_comprehension_first_query(query) or output_style == "Blinkist-style summary" or mode_name in {"Book Tutor", "Blinkist-style Summary"}
            use_comprehension_first = bool(self.prefer_comprehension_index.get() and comprehension_first_intent)
            precomputed_comprehension_artifacts = []
            if use_comprehension_first:
                precomputed_comprehension_artifacts = self.search_comprehension_artifacts(query, k=18)
                self.log(
                    "Comprehension routing: queried structured index first "
                    f"({len(precomputed_comprehension_artifacts)} artifacts), then retrieving raw chunks for corroboration."
                )
            recursive_mode_enabled = bool(self.enable_recursive_retrieval.get())
            use_recursive_retrieval = (
                recursive_mode_enabled and (is_long_form or is_evidence_pack)
            )
            self._frontier_evidence_pack_mode = bool(is_evidence_pack)
            self._last_evidence_pack_synthesis_cards = []
            self._latest_source_map = {}
            self._latest_incidents = []
            self._latest_grounding_html_path = ""
            self._run_on_ui(self._refresh_evidence_pane, {}, [], "")
            self.log(
                "Frontier flags (chat): "
                f"langextract={self._frontier_enabled('langextract')}, "
                f"structured_incidents={self._frontier_enabled('structured_incidents')}, "
                f"recursive_memory={self._frontier_enabled('recursive_memory')}, "
                f"citation_v2={self._frontier_enabled('citation_v2')}, "
                f"agent_lightning_telemetry={self._frontier_enabled('agent_lightning_telemetry')}, "
                f"recursive_retrieval={int(use_recursive_retrieval)}, "
                f"evidence_pack_mode={is_evidence_pack}, "
                f"mode={mode_name}, profile={self.selected_profile.get()}"
            )
            if is_long_form:
                boosted_final_k = max(final_k, 12)
                if boosted_final_k > final_k:
                    original_final_k = final_k
                    final_k = boosted_final_k
                    candidate_k = max(candidate_k, final_k)
                    self.log(
                        "Long-form intent detected; raised final_k from "
                        f"{original_final_k} to {final_k} "
                        "(GUI value remains authoritative with long-form floor only)."
                    )
            if recursive_mode_enabled and not use_recursive_retrieval:
                self.log(
                    "Recursive retrieval toggle is ON, but request is not long-form/evidence-pack; using default retrieval."
                )
            self._append_jsonl_telemetry(
                {
                    "event": "run_start",
                    "run_id": run_id,
                    "iter": 0,
                    "query": query,
                    "user_final_k": user_final_k,
                    "effective_final_k": final_k,
                    "agentic": int(resolved_settings["agentic_mode"]),
                    "output_style": output_style,
                    "mode": mode_name,
                    "profile": self.selected_profile.get(),
                    "recursive_mode_enabled": int(recursive_mode_enabled),
                    "recursive_mode_active": int(use_recursive_retrieval),
                }
            )
            self._record_trace_stage(
                run_id,
                "planner",
                "run_start",
                payload={
                    "query": query,
                    "output_style": output_style,
                    "mode": mode_name,
                    "agentic": bool(resolved_settings["agentic_mode"]),
                },
            )
            self._start_agent_lightning_run(run_id, query)
            search_type = resolved_settings.get("search_type", self.search_type.get()) or "similarity"
            mmr_lambda = float(resolved_settings.get("mmr_lambda", self.mmr_lambda.get()))
            total_docs_cap = max(10, min(500, int(self.subquery_max_docs.get())))
            persist_dir = self.selected_index_path
            if not persist_dir:
                persist_dir = getattr(self.vector_store, "_persist_directory", None)
            if not persist_dir and self.vector_db_type.get() == "chroma":
                persist_dir = self._get_chroma_persist_root()
            digest_missing = (
                not self.build_digest_index.get()
                or (
                    self.vector_db_type.get() == "chroma"
                    and not self._has_digest_collection(persist_dir)
                )
            )
            digest_store = None
            if not digest_missing and self.vector_db_type.get() == "chroma":
                try:
                    embeddings = self.get_embeddings()
                    Chroma = _lazy_import_chroma()

                    digest_store = Chroma(
                        collection_name=DIGEST_COLLECTION_NAME,
                        embedding_function=embeddings,
                        persist_directory=persist_dir,
                    )
                except Exception as exc:
                    self.log(f"Digest store unavailable; skipping digest tier. ({exc})")
                    digest_store = None
            resolved_retrieval_mode = self._resolve_retrieval_mode(
                query, resolved_settings, bool(digest_store)
            )
            use_hierarchical_retrieval = resolved_retrieval_mode == "hierarchical" and bool(digest_store)
            if resolved_retrieval_mode == "hierarchical" and not digest_store:
                self.log("Hierarchical retrieval requested, but digest index unavailable; falling back to flat retrieval.")
            self.log(f"Retrieval mode resolved: {resolved_retrieval_mode}.")
            use_mini_digest = (
                digest_missing and self.selected_collection_name == RAW_COLLECTION_NAME
            )
            if use_mini_digest:
                self.log(
                    "Digest layer missing; using temporary mini-digest routing for this request."
                )
            routing_candidate_k = candidate_k
            if use_mini_digest:
                routing_candidate_k = min(
                    max(candidate_k * MINI_DIGEST_BOOST_MULTIPLIER, MINI_DIGEST_MIN_POOL),
                    total_docs_cap,
                )
                if routing_candidate_k > candidate_k:
                    self.log(
                        f"Mini-digest routing enabled; boosted retrieval pool to {routing_candidate_k}."
                    )

            recursive_expansion_cache = {}

            def _extract_json_payload(text):
                cleaned = text.strip()
                if "```" in cleaned:
                    parts = cleaned.split("```")
                    if len(parts) >= 2:
                        cleaned = parts[1].strip()
                        if cleaned.lower().startswith("json"):
                            cleaned = cleaned.split("\n", 1)[-1].strip()
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    return None

            def _build_chunk_reference_lookup(doc_list):
                lookup = {}
                for idx, doc in enumerate(doc_list, start=1):
                    metadata = getattr(doc, "metadata", {}) or {}
                    chunk_id = str(metadata.get("chunk_id", "")).strip()
                    canonical = chunk_id if chunk_id and chunk_id != "N/A" else f"Chunk {idx}"
                    keys = {
                        canonical,
                        canonical.lower(),
                        f"Chunk {idx}",
                        f"chunk {idx}",
                        str(idx),
                    }
                    if chunk_id and chunk_id != "N/A":
                        keys.update(
                            {
                                chunk_id,
                                chunk_id.lower(),
                                f"chunk_id:{chunk_id}",
                                f"chunk_id: {chunk_id}",
                                f"chunk id {chunk_id}",
                            }
                        )
                    for key in keys:
                        lookup[str(key).strip().lower()] = canonical
                return lookup

            def _normalize_incident_payload(payload, doc_list):
                scope_note = ""
                if isinstance(payload, list):
                    incidents_raw = payload
                elif isinstance(payload, dict):
                    incidents_raw = payload.get("incidents", [])
                    scope_note = str(payload.get("scope_note", "")).strip()
                else:
                    incidents_raw = []

                lookup = _build_chunk_reference_lookup(doc_list)
                incidents = []
                for item in incidents_raw:
                    if not isinstance(item, dict):
                        continue
                    supporting_raw = item.get("supporting_chunks", [])
                    if isinstance(supporting_raw, str):
                        supporting_raw = [supporting_raw]
                    supporting_chunks = []
                    seen = set()
                    for ref in supporting_raw:
                        normalized = lookup.get(str(ref).strip().lower())
                        if normalized and normalized not in seen:
                            supporting_chunks.append(normalized)
                            seen.add(normalized)
                    if not supporting_chunks:
                        continue

                    people_value = item.get("people", [])
                    if isinstance(people_value, str):
                        people_value = [p.strip() for p in people_value.split(",") if p.strip()]
                    elif isinstance(people_value, list):
                        people_value = [str(p).strip() for p in people_value if str(p).strip()]
                    else:
                        people_value = []

                    impact_value = item.get("impact", {})
                    if isinstance(impact_value, dict):
                        operational_impact = str(impact_value.get("operational", "")).strip()
                        personal_impact = str(impact_value.get("personal", "")).strip()
                    else:
                        operational_impact = str(impact_value).strip()
                        personal_impact = ""

                    normalized_refs = []
                    for ref in item.get("evidence_refs", []):
                        if not isinstance(ref, dict):
                            continue
                        src = str(ref.get("source_id", "")).strip()
                        if src and re.match(r"^S\d+$", src) and src not in supporting_chunks:
                            supporting_chunks.append(src)
                        normalized_refs.append(
                            {
                                "source_id": src,
                                "span_start": ref.get("span_start") if isinstance(ref.get("span_start"), int) else None,
                                "span_end": ref.get("span_end") if isinstance(ref.get("span_end"), int) else None,
                                "quote_anchor": str(ref.get("quote_anchor") or ref.get("quote") or "").strip(),
                                "chunk_id": str(ref.get("chunk_id", "")).strip(),
                            }
                        )

                    incidents.append(
                        {
                            "incident_id": str(item.get("incident_id") or item.get("title") or "").strip(),
                            "date": str(item.get("date", "")).strip(),
                            "month_key": str(item.get("month_key", "")).strip(),
                            "channel": str(item.get("channel", "")).strip(),
                            "people": people_value,
                            "what_happened": str(item.get("what_happened", "")).strip(),
                            "impact": {
                                "operational": operational_impact,
                                "personal": personal_impact,
                            },
                            "supporting_chunks": supporting_chunks,
                            "evidence_refs": normalized_refs,
                        }
                    )
                return incidents, scope_note

            def _run_evidence_pack_two_stage(llm, query_text, context_text, doc_list, checklist_text="", section_plan_items=None, coverage_note=""):
                section_plan_items = section_plan_items or []
                recursive_memory_enabled = bool(self.enable_recursive_memory.get())
                use_langextract_incidents = bool(langextract is not None and self.enable_langextract.get())
                _source_map_seed, _source_cards_text = self._build_source_cards(doc_list)
                scope_note = ""

                def _extract_stage_a_incidents(working_docs, working_context):
                    local_scope_note = ""
                    working_source_map, _ = self._build_source_cards(working_docs)
                    if use_langextract_incidents:
                        incidents_structured = self._load_incident_cache(query_text, working_docs)
                        if incidents_structured:
                            self.log("Loaded structured incidents from cache.")
                        else:
                            incidents_structured = self._extract_incidents_langextract(working_docs, working_source_map)
                            if incidents_structured:
                                self._save_incident_cache(query_text, working_docs, incidents_structured)
                        ordered_source_ids = sorted(working_source_map.keys())
                        source_label_by_id = {
                            source_id: f"S{idx}" for idx, source_id in enumerate(ordered_source_ids, start=1)
                        }
                        extracted_incidents = [
                            self._incident_to_stage_a_payload(item, source_label_by_id)
                            for item in incidents_structured
                        ]
                    else:
                        stage_a_prompt = (
                            "You are Stage A for evidence-pack mode. Use ONLY FINAL_DOCS context below. "
                            "Extract incidents and return STRICT JSON only (no markdown, no commentary).\n\n"
                            "Schema (object with incidents array):\n"
                            "{\"incidents\": [{\n"
                            '  "incident_id": "",\n'
                            '  "date": "ISO date (YYYY-MM-DD) if known; else YYYY-MM-unknown",\n'
                            '  "month_key": "YYYY-MM when day is unknown",\n'
                            '  "channel": "email|chat|call|ticket|unknown",\n'
                            '  "people": ["name/role"],\n'
                            '  "what_happened": "verbatim-grounded summary with minimal paraphrase",\n'
                            '  "impact": {"operational": "", "personal": ""},\n'
                            '  "evidence_refs": [{"source_id": "S# or chunk reference", "span_start": 0, "span_end": 0, "quote_anchor": "", "chunk_id": ""}]\n'
                            "}]}\n\n"
                            "Rules: every incident must include evidence_refs; do not invent dates. "
                            "If day is missing, keep month_key and set date to YYYY-MM-unknown. "
                            "If no incidents are supported, return {\"incidents\": []}."
                        )
                        stage_a_messages = [
                            self._system_message(content=stage_a_prompt),
                            self._human_message(
                                content=(
                                    f"User request:\n{query_text}\n\n"
                                    f"FINAL_DOCS:\n{working_context}{coverage_note}"
                                )
                            ),
                        ]
                        stage_a_response = llm.invoke(stage_a_messages)
                        stage_a_payload = _extract_json_payload(stage_a_response.content)
                        extracted_incidents, local_scope_note = _normalize_incident_payload(stage_a_payload, working_docs)
                    return extracted_incidents, local_scope_note

                incidents, scope_note = _extract_stage_a_incidents(doc_list, context_text)
                self._latest_incidents = incidents
                self._write_incidents_json_artifact({"incidents": incidents})

                month_memory = {}
                theme_memory = {}
                memory_coverage = {
                    "triggered": False,
                    "missing_months": [],
                }

                if recursive_memory_enabled:
                    follow_up_queries_rm, memory_coverage = self._build_recursive_coverage_queries(doc_list, incidents)
                    if memory_coverage.get("triggered") and follow_up_queries_rm:
                        self.log(
                            "Recursive memory coverage gate triggered: "
                            f"missing_months={memory_coverage.get('missing_months', [])}, queries={follow_up_queries_rm}."
                        )
                        follow_docs, _follow_count, _follow_cap = _retrieve_for_queries(
                            follow_up_queries_rm,
                            remaining_cap=min(total_docs_cap, max(120, final_k * 10)),
                            k_value=max(retrieve_k, final_k * 4),
                        )
                        if follow_docs:
                            routed_docs, _route_meta = self._route_followup_docs_by_query(
                                follow_docs, follow_up_queries_rm
                            )
                            merged_docs = self._merge_dedupe_docs(doc_list + routed_docs)
                            selected_docs = _select_evidence_pack(
                                merged_docs,
                                query_text,
                                is_evidence_pack,
                                seen_chunk_ids=seen_chunk_ids,
                            )
                            if selected_docs:
                                doc_list = selected_docs
                                refreshed_context, _was_trunc, _used, _budget, _packed = _build_context(doc_list)
                                incidents, scope_note = _extract_stage_a_incidents(doc_list, refreshed_context)
                    month_memory, theme_memory = self._build_recursive_memories(incidents)
                    artifact_path = self._save_recursive_memory_artifact(
                        query_text,
                        {
                            "month_memory": month_memory,
                            "theme_memory": theme_memory,
                            "coverage": memory_coverage,
                            "incident_count": len(incidents or []),
                        },
                    )
                    if artifact_path:
                        self.log(f"Recursive memory artifacts saved to {artifact_path}.")

                if not incidents:
                    if scope_note:
                        return f"Scope: {scope_note}"
                    return "No supported incidents were found in final_docs."

                synthesis_cards = self._build_incident_synthesis_cards(incidents)
                if not synthesis_cards:
                    if scope_note:
                        return f"Scope: {scope_note}"
                    return "No supported incidents were found in final_docs."

                incident_json = json.dumps(incidents, ensure_ascii=False, indent=2)
                cards_json = json.dumps(synthesis_cards, ensure_ascii=False, indent=2)
                section_text = (
                    "\nSECTION PLAN:\n" + "\n".join(f"- {item}" for item in section_plan_items)
                    if section_plan_items
                    else ""
                )
                checklist_block = f"\nCHECKLIST:\n{checklist_text}" if checklist_text else ""
                advice_requested = self._is_advice_request(query_text)
                tone_rule = (
                    "Advice is allowed only because the user explicitly asked for advice. Keep it concise and separate from factual findings."
                    if advice_requested
                    else "Default to a factual evidence pack only. Do not give coaching, guidance, recommendations, or action plans."
                )
                stage_b_prompt = (
                    "You are Stage B for evidence-pack mode. Write the final narrative using ONLY INCIDENT_SYNTHESIS_CARDS, "
                    "which were produced from Stage A incidents.json. Do NOT quote or infer directly from raw chunks. "
                    "If the user asks for an incident not present in INCIDENT_SYNTHESIS_CARDS, use the closest matching extracted incidents "
                    "and state what is supportable without asking the user for additional evidence. "
                    "Use MONTH_MEMORY and THEME_MEMORY as compressed guidance to improve coverage across time periods and recurring themes. "
                    "For each incident block: When / What happened / Impact / Evidence, and end the block with [S#] citations from evidence_refs. "
                    "Never invent dates: if date is YYYY-MM-unknown or unknown, preserve it as-is. "
                    "Never output NOT FOUND IN CONTEXT (or variants), placeholders, or requests for user-supplied evidence. "
                    f"{tone_rule} "
                    "Required output format:\n"
                    "1) One-page overview (allegations, themes, remedies sought).\n"
                    "2) Timeline table with columns: Date | What happened | Impact | Sources ([S#]).\n"
                    "3) Key incidents (6-12) with consistent fields: Date; Actors; Channel; What happened; Impact; Evidence [S#].\n"
                    "4) Supporting incidents (2-4 concise entries) to widen month/channel coverage.\n"
                    "5) Witness list only if witnesses are explicitly present in evidence; otherwise omit.\n"
                    "6) Appendix: Source Cards list."
                )
                stage_b_messages = [
                    self._system_message(content=stage_b_prompt),
                    self._human_message(
                        content=(
                            f"User request:\n{query_text}{section_text}{checklist_block}\n\n"
                            f"INCIDENT_SYNTHESIS_CARDS (from Stage A Incident objects):\n{cards_json}\n\n"
                            f"MONTH_MEMORY:\n{json.dumps(month_memory, ensure_ascii=False, indent=2)}\n\n"
                            f"THEME_MEMORY:\n{json.dumps(theme_memory, ensure_ascii=False, indent=2)}\n\n"
                            f"INCIDENT JSON (reference only):\n{incident_json}"
                        )
                    ),
                ]
                stage_b_response = llm.invoke(stage_b_messages)
                self._last_evidence_pack_synthesis_cards = synthesis_cards
                return stage_b_response.content

            def _run_blinkist_summary_two_stage(llm, query_text, doc_list, digest_docs=None):
                digest_docs = digest_docs or []
                source_map, source_cards_text = self._build_source_cards(doc_list)
                if not source_map:
                    return ""

                zoom_key_idea = self._extract_zoom_key_idea_index(query_text)
                label_to_source = {
                    locator.label: source_id
                    for source_id, locator in source_map.items()
                    if getattr(locator, "label", "")
                }

                concept_cards = self.search_concepts(query_text, k=16)
                comprehension_artifacts = self.search_comprehension_artifacts(query_text, k=24)
                chapter_digests = []
                part_digests = []
                book_summary_text = ""
                for digest_doc in digest_docs:
                    metadata = getattr(digest_doc, "metadata", {}) or {}
                    digest_scope = str(metadata.get("digest_scope") or "").strip().lower()
                    payload = {
                        "digest_scope": digest_scope,
                        "chapter_idx": metadata.get("chapter_idx"),
                        "chapter_title": str(metadata.get("chapter_title") or "").strip(),
                        "section_idx": metadata.get("section_idx"),
                        "section_title": str(metadata.get("section_title") or "").strip(),
                        "part_idx": metadata.get("part_idx"),
                        "part_title": str(metadata.get("part_title") or "").strip(),
                        "summary": str(getattr(digest_doc, "page_content", "") or "").strip(),
                    }
                    if digest_scope in {"chapter", "section"}:
                        chapter_digests.append(payload)
                    elif digest_scope == "part":
                        part_digests.append(payload)
                    elif digest_scope == "book":
                        book_summary_text = payload.get("summary") or ""

                if zoom_key_idea and isinstance(self._latest_blinkist_plan, dict):
                    key_ideas = self._latest_blinkist_plan.get("key_ideas") or []
                    idx = int(zoom_key_idea) - 1
                    if 0 <= idx < len(key_ideas):
                        selected_idea = key_ideas[idx] or {}
                        selected_labels = [
                            str(s).strip() for s in (selected_idea.get("sources") or []) if str(s).strip()
                        ]
                        selected_source_ids = {
                            label_to_source.get(label) for label in selected_labels if label in label_to_source
                        }
                        supporting_docs = []
                        for doc in doc_list:
                            metadata = getattr(doc, "metadata", {}) or {}
                            source_id = self._build_source_locator(metadata, getattr(doc, "page_content", "") or "").source_id
                            if source_id in selected_source_ids:
                                supporting_docs.append(doc)
                        _, supporting_cards = self._build_source_cards(supporting_docs or doc_list[:10])
                        stage_zoom_prompt = (
                            "You are the Blinkist zoom tool. Expand the selected key idea with a chapter-aware explanation. "
                            "Use only provided key idea payload, chapter summaries, and source cards. "
                            "Structure: (1) Idea restatement, (2) Deeper explanation, (3) Chapter evidence map, (4) Practical application checklist. "
                            "Cite supported claims with [S#]."
                        )
                        stage_zoom_messages = [
                            self._system_message(content=stage_zoom_prompt),
                            self._human_message(
                                content=(
                                    f"User request:\n{query_text}\n\n"
                                    f"KEY_IDEA:\n{json.dumps(selected_idea, ensure_ascii=False, indent=2)}\n\n"
                                    f"CHAPTER_DIGESTS:\n{json.dumps(chapter_digests[:8], ensure_ascii=False, indent=2)}\n\n"
                                    f"SOURCE_CARDS:\n{supporting_cards}"
                                )
                            ),
                        ]
                        stage_zoom_response = llm.invoke(stage_zoom_messages)
                        return str(stage_zoom_response.content or "")

                compact_cards = []
                for card in concept_cards[:16]:
                    compact_cards.append(
                        {
                            "title": str(card.get("title") or "").strip(),
                            "kind": str(card.get("kind") or "").strip(),
                            "content": card.get("content") or {},
                            "source_refs": card.get("source_refs") or [],
                        }
                    )

                stage_a_prompt = (
                    "You are Stage A planner for Blinkist-style summary mode. "
                    "Build a strict JSON plan using BOOK_SUMMARY + PART_DIGESTS + CHAPTER_DIGESTS as the primary evidence, "
                    "then corroborate with COMPREHENSION_ARTIFACTS, concept cards, and SOURCE_CARDS. "
                    "Do not ask for more information. Omit unsupported claims and fields entirely. "
                    "Never emit placeholders like NOT FOUND.\n\n"
                    "Return ONLY valid JSON with keys:\n"
                    "{\n"
                    "  \"premise\": \"single sentence\",\n"
                    "  \"key_ideas\": [{\"title\":\"\",\"what\":\"\",\"why\":\"\",\"how\":\"\",\"sources\":[\"S#\"],\"supporting_chapters\":[\"\"]}],\n"
                    "  \"actionable_takeaways\": [{\"title\":\"\",\"steps\":[\"\"],\"sources\":[\"S#\"]}],\n"
                    "  \"memorable_quotes\": [{\"quote\":\"\",\"why_it_matters\":\"\",\"source_locator\":\"\",\"sources\":[\"S#\"]}],\n"
                    "  \"key_takeaways\": [\"\"],\n"
                    "  \"chapter_mini_summaries\": [{\"chapter\":\"\",\"summary\":\"\",\"sources\":[\"S#\"]}]\n"
                    "}\n\n"
                    "Rules:\n"
                    "- premise: exactly 1 line.\n"
                    "- key_ideas: exactly 10 items, each with what/why/how, supporting_chapters, and S# labels.\n"
                    "- actionable_takeaways: exactly 5 items grounded in supported ideas.\n"
                    "- memorable_quotes: exactly 3 short grounded quotes with source_locator and S# labels.\n"
                    "- key_takeaways: 3-5 concise whole-book bullets.\n"
                    "- chapter_mini_summaries is optional: include only when chapter-level support exists.\n"
                    "- Omit-if-unsupported everywhere; do not include empty strings, null placeholders, or fallback text."
                )
                stage_a_messages = [
                    self._system_message(content=stage_a_prompt),
                    self._human_message(
                        content=(
                            f"User request:\n{query_text}\n\n"
                            f"BOOK_SUMMARY:\n{book_summary_text}\n\n"
                            f"PART_DIGESTS:\n{json.dumps(part_digests, ensure_ascii=False, indent=2)}\n\n"
                            f"SOURCE_CARDS:\n{source_cards_text}\n\n"
                            f"CHAPTER_DIGESTS:\n{json.dumps(chapter_digests, ensure_ascii=False, indent=2)}\n\n"
                            f"CONCEPT_CARDS:\n{json.dumps(compact_cards, ensure_ascii=False, indent=2)}\n\n"
                            f"COMPREHENSION_ARTIFACTS:\n{json.dumps(comprehension_artifacts, ensure_ascii=False, indent=2)}"
                        )
                    ),
                ]
                stage_a_response = llm.invoke(stage_a_messages)
                stage_a_payload = _extract_json_payload(stage_a_response.content)
                if not isinstance(stage_a_payload, dict):
                    stage_a_payload = {}
                self._latest_blinkist_plan = stage_a_payload

                stage_b_prompt = (
                    "You are Stage B renderer for Blinkist-style summary mode. "
                    "Render final output from PLAN_JSON only. Keep the exact template and headings below. "
                    "Ground each factual line with [S#] citations from source labels present in PLAN_JSON/SOURCE_CARDS. "
                    "Never output placeholders, NOT FOUND text, or requests for additional user info.\n\n"
                    "Template (follow exactly):\n"
                    "1) Premise (1 line)\n"
                    "2) 10 Key Ideas\n"
                    "   - For each idea use exactly:\n"
                    "     Idea N — <title>\n"
                    "     What it is: ... [S#]\n"
                    "     Why it matters: ... [S#]\n"
                    "     How to apply: ... [S#]\n"
                    "3) 5 Actionable Takeaways\n"
                    "4) 3 Memorable Quotes (with source locator)\n"
                    "5) Whole-book key takeaways\n"
                    "6) Optional: Chapter-by-chapter mini-summaries (append only if present in PLAN_JSON).\n\n"
                    "If PLAN_JSON has fewer than requested supported items, output only supported items without explanatory filler."
                )
                stage_b_messages = [
                    self._system_message(content=stage_b_prompt),
                    self._human_message(
                        content=(
                            f"User request:\n{query_text}\n\n"
                            f"PLAN_JSON:\n{json.dumps(stage_a_payload, ensure_ascii=False, indent=2)}\n\n"
                            f"SOURCE_CARDS:\n{source_cards_text}"
                        )
                    ),
                ]
                stage_b_response = llm.invoke(stage_b_messages)
                return str(stage_b_response.content or "")

            def _run_book_tutor_two_stage(llm, query_text, doc_list, digest_docs=None):
                digest_docs = digest_docs or []
                source_map, source_cards_text = self._build_source_cards(doc_list)
                if not source_map:
                    return ""

                concept_cards = self.search_concepts(query_text, k=20)
                comprehension_artifacts = self.search_comprehension_artifacts(query_text, k=24)
                chapter_digests = []
                for digest_doc in digest_docs:
                    metadata = getattr(digest_doc, "metadata", {}) or {}
                    digest_scope = str(metadata.get("digest_scope") or "").strip().lower()
                    if digest_scope not in {"chapter", "section"}:
                        continue
                    chapter_digests.append(
                        {
                            "digest_scope": digest_scope,
                            "chapter_idx": metadata.get("chapter_idx"),
                            "chapter_title": str(metadata.get("chapter_title") or "").strip(),
                            "section_idx": metadata.get("section_idx"),
                            "section_title": str(metadata.get("section_title") or "").strip(),
                            "summary": str(getattr(digest_doc, "page_content", "") or "").strip(),
                        }
                    )

                compact_cards = []
                for card in concept_cards[:20]:
                    compact_cards.append(
                        {
                            "title": str(card.get("title") or "").strip(),
                            "kind": str(card.get("kind") or "").strip(),
                            "content": card.get("content") or {},
                            "source_refs": card.get("source_refs") or [],
                        }
                    )

                one_shot_mode = self._is_one_shot_learning_request(query_text)
                socratic_rule = (
                    "- socratic_questions: empty array because user asked for one-shot output with no interaction.\n"
                    if one_shot_mode
                    else "- socratic_questions: exactly 3 questions.\n"
                )
                stage_a_prompt = (
                    "You are Stage A planner for Book Tutor mode. "
                    "Build strict JSON for a lesson grounded in SOURCE_CARDS, CHAPTER_DIGESTS, CONCEPT_CARDS, and COMPREHENSION_ARTIFACTS. "
                    "Prefer structured comprehension artifacts and chapter digests first; only rely on raw chunk detail when required to fill unsupported gaps. "
                    "Use plain English and the book's framing. Keep citations minimal and claim-level with S# labels. "
                    "Return only supported content; omit unsupported points entirely.\n\n"
                    "Return ONLY valid JSON:\n"
                    "{\n"
                    "  \"lesson\": {\"concept\":\"\",\"explanation\":\"\",\"sources\":[\"S#\"]},\n"
                    "  \"analogies\": [{\"example\":\"\",\"sources\":[\"S#\"]}],\n"
                    "  \"socratic_questions\": [\"\"],\n"
                    "  \"flashcards\": [{\"q\":\"\",\"a\":\"\",\"sources\":[\"S#\"]}],\n"
                    "  \"quiz\": {\"questions\": [{\"question\":\"\"}], \"answer_key\": [{\"answer\":\"\",\"why\":\"\",\"sources\":[\"S#\"]}]}\n"
                    "}\n\n"
                    "Rules:\n"
                    "- lesson.explanation: plain English using the book framing.\n"
                    "- analogies: 2-3 entries.\n"
                    f"{socratic_rule}"
                    "- flashcards: exactly 10 Q/A cards.\n"
                    "- quiz.questions: exactly 5 questions.\n"
                    "- quiz.answer_key: exactly 5 entries matching quiz.questions order.\n"
                    "- Omit placeholders or TODO markers.\n"
                )
                stage_a_messages = [
                    self._system_message(content=stage_a_prompt),
                    self._human_message(
                        content=(
                            f"User request:\n{query_text}\n\n"
                            f"SOURCE_CARDS:\n{source_cards_text}\n\n"
                            f"CHAPTER_DIGESTS:\n{json.dumps(chapter_digests, ensure_ascii=False, indent=2)}\n\n"
                            f"CONCEPT_CARDS:\n{json.dumps(compact_cards, ensure_ascii=False, indent=2)}\n\n"
                            f"COMPREHENSION_ARTIFACTS:\n{json.dumps(comprehension_artifacts, ensure_ascii=False, indent=2)}"
                        )
                    ),
                ]
                stage_a_response = llm.invoke(stage_a_messages)
                plan_payload = _extract_json_payload(stage_a_response.content)
                if not isinstance(plan_payload, dict):
                    plan_payload = {}

                lesson = plan_payload.get("lesson") or {}
                analogies = plan_payload.get("analogies") or []
                socratic_questions = plan_payload.get("socratic_questions") or []
                flashcards = plan_payload.get("flashcards") or []
                quiz_payload = plan_payload.get("quiz") or {}
                quiz_questions = quiz_payload.get("questions") or []
                answer_key = quiz_payload.get("answer_key") or []

                lesson_title = str(lesson.get("concept") or "").strip() or "Concept"
                lesson_body = str(lesson.get("explanation") or "").strip()
                lesson_sources = [str(s).strip() for s in (lesson.get("sources") or []) if str(s).strip()]
                lesson_citation = f" [{' '.join(lesson_sources)}]" if lesson_sources else ""

                rendered = [f"## Book Tutor — {lesson_title}"]
                if lesson_body:
                    rendered.append(f"{lesson_body}{lesson_citation}")

                rendered.append("\n### Analogies & Examples")
                for idx, item in enumerate(analogies[:3], start=1):
                    example = str(item.get("example") or "").strip()
                    sources = [str(s).strip() for s in (item.get("sources") or []) if str(s).strip()]
                    citation = f" [{' '.join(sources)}]" if sources else ""
                    if example:
                        rendered.append(f"{idx}. {example}{citation}")

                if not one_shot_mode:
                    rendered.append("\n### Socratic Questions")
                    for idx, q in enumerate(socratic_questions[:3], start=1):
                        question = str(q).strip()
                        if question:
                            rendered.append(f"{idx}. {question}")

                rendered.append("\n" + self._render_flashcards(flashcards[:10]))
                rendered.append("\n" + self._render_quiz(quiz_questions[:5], answer_key[:5]))
                return "\n".join(rendered).strip()

            def _build_search_kwargs(k_value):
                search_kwargs_local = {"k": k_value}
                if search_type == "mmr":
                    fetch_k = min(max(4 * k_value, 50), 200)
                    if fetch_k <= k_value:
                        fetch_k = k_value + 1
                    search_kwargs_local.update(
                        {"fetch_k": fetch_k, "lambda_mult": mmr_lambda}
                    )
                return search_kwargs_local
            def _retrieve_digest_nodes(query_list, remaining_cap, k_value, digest_store, tree_level=None, digest_scope=None):
                if remaining_cap <= 0 or not digest_store:
                    return [], 0, True
                filtered_queries = [q for q in query_list if q]
                if not filtered_queries:
                    return [], 0, False
                digest_cap = min(MAX_DIGEST_NODES, remaining_cap)
                min_per_query_k = min(2, k_value)
                per_query_k = max(
                    min_per_query_k,
                    min(k_value, max(1, digest_cap // len(filtered_queries))),
                )
                cap_reached = False
                retrieved_count_local = 0
                docs_local = []
                for sub_query in filtered_queries:
                    if len(docs_local) >= digest_cap:
                        cap_reached = True
                        break
                    query_k = min(per_query_k, digest_cap - len(docs_local))
                    batch = self.search_digests(
                        sub_query,
                        query_k,
                        digest_store,
                        tree_level=tree_level,
                        digest_scope=digest_scope,
                    )
                    self.log(
                        f"search_digests(query='{sub_query[:48]}', k={query_k}) -> {len(batch)} digest hits."
                    )
                    retrieved_count_local += len(batch)
                    docs_local.extend(batch)
                docs_local = self._merge_dedupe_docs(docs_local)
                if len(docs_local) > digest_cap:
                    docs_local = docs_local[:digest_cap]
                    cap_reached = True
                return docs_local, retrieved_count_local, cap_reached

            def _expand_digest_nodes(digest_docs, remaining_cap):
                if not digest_docs or remaining_cap <= 0:
                    return [], False
                max_expand = min(MAX_RAW_CHUNKS, remaining_cap)
                raw_docs = []
                cap_reached = False
                for digest_doc in digest_docs:
                    digest_id = ((getattr(digest_doc, "metadata", {}) or {}).get("digest_id"))
                    if not digest_id:
                        continue
                    remaining = max_expand - len(raw_docs)
                    if remaining <= 0:
                        cap_reached = True
                        break
                    expanded_docs = self.expand_digest_to_chunks(
                        digest_id=digest_id,
                        k_within=remaining,
                        digest_store=digest_store,
                    )
                    self.log(
                        f"expand_digest_to_chunks(digest_id='{digest_id}', k_within={remaining}) -> {len(expanded_docs)} chunks."
                    )
                    raw_docs.extend(expanded_docs)
                raw_docs = self._merge_dedupe_docs(raw_docs)
                if len(raw_docs) > max_expand:
                    raw_docs = raw_docs[:max_expand]
                    cap_reached = True
                return raw_docs, cap_reached

            def _retrieve_with_digest(query_list, remaining_cap, k_value):
                digest_retrieved = 0
                digest_selected = 0
                raw_expanded_count = 0
                levels_used = []
                if use_hierarchical_retrieval and digest_store:
                    working_queries = [q for q in query_list if q]
                    digest_docs = []
                    # Acceptance test (logs): book-scale queries should emit digest search
                    # then focused chunk expansion within selected chapters/sections.
                    # Acceptance test (context): final selected chunks should reflect chapter diversity,
                    # not only nearest-neighbor chunk locality.
                    for iteration in range(MAX_HIERARCHICAL_RECURSION_ITERATIONS):
                        chapter_docs, chapter_retrieved, chapter_cap = _retrieve_digest_nodes(
                            working_queries,
                            remaining_cap,
                            k_value,
                            digest_store,
                            tree_level=1,
                            digest_scope="chapter",
                        )
                        section_docs, section_retrieved, section_cap = _retrieve_digest_nodes(
                            working_queries,
                            remaining_cap,
                            k_value,
                            digest_store,
                            tree_level=1,
                            digest_scope="section",
                        )
                        digest_docs = self._merge_dedupe_docs(chapter_docs + section_docs)
                        digest_retrieved = chapter_retrieved + section_retrieved
                        digest_selected = len(digest_docs)
                        coverage_score = self._estimate_digest_coverage_score(digest_docs)
                        self.log(
                            "Hierarchical retrieval iteration "
                            f"{iteration + 1}: selected_digests={digest_selected}, coverage_score={coverage_score}."
                        )
                        if coverage_score >= HIERARCHICAL_COVERAGE_MIN_SCORE or iteration + 1 >= MAX_HIERARCHICAL_RECURSION_ITERATIONS:
                            break
                        refined_queries = self._refine_digest_queries(working_queries, digest_docs)
                        if refined_queries == working_queries:
                            break
                        working_queries = refined_queries
                        self.log(
                            "Coverage score below threshold; refining digest queries for another pass: "
                            f"{working_queries}."
                        )
                    if digest_docs:
                        levels_used.extend(["L1", "L0"])
                    raw_docs, raw_cap_reached = _expand_digest_nodes(digest_docs, remaining_cap)
                    raw_expanded_count = len(raw_docs)
                    if raw_docs:
                        return (
                            raw_docs,
                            0,
                            chapter_cap or section_cap or raw_cap_reached,
                            digest_docs,
                            raw_expanded_count,
                            digest_retrieved,
                            digest_selected,
                            levels_used,
                        )
                    self.log("Hierarchical digest expansion returned no chunks; falling back to flat retrieval.")
                raw_docs, retrieved_count, cap_reached = _retrieve_for_queries(
                    query_list, remaining_cap, k_value
                )
                return (
                    raw_docs,
                    retrieved_count,
                    cap_reached,
                    [],
                    0,
                    digest_retrieved,
                    digest_selected,
                    ["L0"],
                )

            def _retrieve_for_queries(query_list, remaining_cap, k_value):
                if remaining_cap <= 0:
                    return [], 0, True
                filtered_queries = [q for q in query_list if q]
                if not filtered_queries:
                    return [], 0, False
                cap_reached = False
                rrf_base = max(200, final_k * 20)
                dense_k = max(1, min(rrf_base, remaining_cap)) if is_evidence_pack else k_value
                lexical_k = max(1, min(rrf_base, remaining_cap)) if is_evidence_pack else max(1, min(k_value, remaining_cap))
                if len(filtered_queries) == 1:
                    retriever = self.vector_store.as_retriever(
                        search_type=search_type,
                        search_kwargs=_build_search_kwargs(dense_k),
                    )
                    docs_local = retriever.invoke(filtered_queries[0])
                else:
                    min_per_query_k = min(2, dense_k)
                    per_query_k = max(
                        min_per_query_k,
                        min(dense_k, max(1, remaining_cap) // len(filtered_queries)),
                    )
                    retriever = self.vector_store.as_retriever(
                        search_type=search_type,
                        search_kwargs=_build_search_kwargs(per_query_k),
                    )
                    docs_local = []
                    for sub_query in filtered_queries:
                        docs_local.extend(retriever.invoke(sub_query))
                vector_retrieved_count = len(docs_local)
                dense_docs = self._merge_dedupe_docs(docs_local)
                lexical_docs = []
                lexical_ran = False
                lexical_available = False
                if is_evidence_pack:
                    lexical_available = self.lexical_db_available or self._ensure_lexical_db()
                elif self.lexical_db_available:
                    lexical_available = True
                if lexical_available:
                    lexical_ran = True
                    for sub_query in filtered_queries:
                        lexical_docs.extend(self.lexical_search(sub_query, lexical_k))
                dense_ranked = self._merge_dedupe_docs(dense_docs)
                lexical_ranked = self._merge_dedupe_docs(lexical_docs)
                retrieved_count_local = vector_retrieved_count + len(lexical_docs)
                if is_evidence_pack and lexical_docs:
                    pool_cap = min(600, remaining_cap)
                    docs_local = self._fuse_ranked_results(
                        [("dense", dense_ranked), ("lexical", lexical_ranked)],
                        k_rrf=60,
                        fused_pool_size=pool_cap,
                    )
                else:
                    docs_local = dense_ranked
                    if lexical_docs:
                        docs_local = self._merge_dedupe_docs(docs_local + lexical_docs)
                self.log(
                    "Retrieval candidates: "
                    f"dense={len(dense_ranked)}, lexical={len(lexical_ranked)} "
                    f"(ran={int(lexical_ran)}), fused={len(docs_local)}."
                )
                self._record_agent_lightning_event(
                    run_id,
                    "retrieval",
                    {
                        "queries": filtered_queries,
                        "dense_k": int(dense_k),
                        "lexical_k": int(lexical_k),
                        "fused_k": int(len(docs_local)),
                    },
                )
                if len(docs_local) > remaining_cap:
                    docs_local = docs_local[:remaining_cap]
                    cap_reached = True
                return docs_local, retrieved_count_local, cap_reached

            def _retrieve_with_rrf(query_list, remaining_cap, k_value):
                if remaining_cap <= 0:
                    return [], 0, True
                filtered_queries = [q for q in query_list if q]
                if not filtered_queries:
                    return [], 0, False
                fused_scores = {}
                fused_docs = {}
                retrieved_count_local = 0
                cap_reached = False
                rrf_k = 60
                if len(filtered_queries) == 1:
                    per_query_k = min(k_value, remaining_cap)
                else:
                    per_query_k = max(2, min(k_value, max(1, remaining_cap) // len(filtered_queries)))
                retriever = self.vector_store.as_retriever(
                    search_type=search_type,
                    search_kwargs=_build_search_kwargs(per_query_k),
                )
                for sub_query in filtered_queries:
                    dense_docs = retriever.invoke(sub_query)
                    retrieved_count_local += len(dense_docs)
                    for rank, doc in enumerate(dense_docs, start=1):
                        key = self._doc_identity_key(doc)
                        fused_scores[key] = fused_scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
                        fused_docs.setdefault(key, doc)
                    if self.lexical_db_available:
                        lexical_docs = self.lexical_search(sub_query, per_query_k)
                        retrieved_count_local += len(lexical_docs)
                        for rank, doc in enumerate(lexical_docs, start=1):
                            key = self._doc_identity_key(doc)
                            fused_scores[key] = fused_scores.get(key, 0.0) + 1.0 / (rrf_k + rank)
                            fused_docs.setdefault(key, doc)
                ranked_keys = sorted(fused_scores, key=lambda key: fused_scores[key], reverse=True)
                docs_local = []
                for key in ranked_keys:
                    doc = fused_docs[key]
                    metadata = getattr(doc, "metadata", {}) or {}
                    metadata["rrf_score"] = round(fused_scores[key], 6)
                    if metadata.get("relevance_score") is None:
                        metadata["relevance_score"] = round(fused_scores[key], 6)
                    doc.metadata = metadata
                    docs_local.append(doc)
                    if len(docs_local) >= remaining_cap:
                        cap_reached = True
                        break
                self.log(
                    "RRF fusion retrieval combined dense+lexical results into "
                    f"{len(docs_local)} unique candidates."
                )
                self._record_agent_lightning_event(
                    run_id,
                    "retrieval",
                    {
                        "queries": filtered_queries,
                        "dense_k": int(per_query_k),
                        "lexical_k": int(per_query_k if self.lexical_db_available else 0),
                        "fused_k": int(len(docs_local)),
                    },
                )
                return docs_local, retrieved_count_local, cap_reached

            def _select_evidence_pack(
                doc_list,
                rerank_query,
                evidence_pack_mode,
                seen_chunk_ids=None,
            ):
                candidates = self._promote_lexical_overlap(doc_list, rerank_query)
                rerank_top_n = min(len(candidates), max(final_k * 6, 80))
                if self.use_reranker.get() and self.api_keys["cohere"].get():
                    try:
                        self.log("Reranking with Cohere...")
                        from langchain_cohere import CohereRerank

                        compressor = CohereRerank(
                            cohere_api_key=self.api_keys["cohere"].get(),
                            top_n=rerank_top_n,
                            model="rerank-english-v3.0",
                        )
                        compressed_docs = compressor.compress_documents(
                            candidates, rerank_query
                        )
                        self.log(
                            f"Reranked down to {len(compressed_docs)} high-relevance chunks."
                        )
                        candidates = compressed_docs
                    except Exception as exc:
                        self.log(f"Rerank Error (Using raw retrieval instead): {exc}")
                group_limit = 1 if evidence_pack_mode else MAX_GROUP_DOCS
                candidates = self._apply_coverage_selection(
                    candidates,
                    final_k,
                    group_limit=group_limit,
                    evidence_pack_mode=evidence_pack_mode,
                    seen_chunk_ids=seen_chunk_ids,
                )
                if len(candidates) < final_k:
                    fallback = self._merge_dedupe_docs(candidates + doc_list)
                    candidates = fallback[:final_k]
                else:
                    candidates = candidates[:final_k]
                self._record_trace_stage(
                    run_id,
                    "rerank",
                    "selected_candidates",
                    payload={
                        "selected_count": len(candidates),
                        "source_locators": self._source_locators_from_docs(candidates),
                    },
                )
                return candidates

            def _coverage_followup_from_metadata(pool_docs, selected_docs, max_queries=2):
                pool_months = {
                    (getattr(doc, "metadata", {}) or {}).get("month_bucket")
                    for doc in pool_docs
                }
                selected_months = {
                    (getattr(doc, "metadata", {}) or {}).get("month_bucket")
                    for doc in selected_docs
                }
                pool_months = {m for m in pool_months if m and m != "undated"}
                selected_months = {m for m in selected_months if m and m != "undated"}

                pool_incidents = {
                    (getattr(doc, "metadata", {}) or {}).get("incident_key") or self._build_incident_key(doc)
                    for doc in pool_docs
                }
                selected_incidents = {
                    (getattr(doc, "metadata", {}) or {}).get("incident_key") or self._build_incident_key(doc)
                    for doc in selected_docs
                }
                pool_incidents = {i for i in pool_incidents if i}
                selected_incidents = {i for i in selected_incidents if i}

                missing_months = sorted(pool_months - selected_months, key=self._month_sort_key)
                lost_incident_diversity = len(pool_incidents) > len(selected_incidents)
                triggered = bool(missing_months) or lost_incident_diversity
                queries = []
                for month in missing_months[:max_queries]:
                    queries.append(f"{month} incident timeline what happened impact")
                    if len(queries) < max_queries:
                        queries.append(f"{month} complaint escalation chronology")
                    if len(queries) >= max_queries:
                        break
                if lost_incident_diversity and not queries:
                    month_hint = sorted(pool_months, key=self._month_sort_key)[0] if pool_months else "recent"
                    queries.append(f"{month_hint} incident chronology evidence")
                return queries[:max_queries], {
                    "triggered": triggered,
                    "pool_months": len(pool_months),
                    "selected_months": len(selected_months),
                    "pool_incidents": len(pool_incidents),
                    "selected_incidents": len(selected_incidents),
                }

            def _trim_followup_swap_pool(existing_pool, follow_pool, cap_value, seen_ids=None):
                seen_ids = seen_ids if isinstance(seen_ids, set) else set(seen_ids or [])
                follow_keys = {
                    self._doc_identity_key(doc)
                    for doc in follow_pool
                }
                combined = self._merge_dedupe_docs(existing_pool + follow_pool)
                signature_counts = {}
                for doc in combined:
                    metadata = getattr(doc, "metadata", {}) or {}
                    signature = metadata.get("incident_signature") or metadata.get("incident_key") or self._build_incident_key(doc)
                    signature_counts[signature] = signature_counts.get(signature, 0) + 1

                scored = []
                for doc in combined:
                    metadata = getattr(doc, "metadata", {}) or {}
                    relevance = metadata.get("relevance_score")
                    try:
                        relevance = float(relevance)
                    except (TypeError, ValueError):
                        relevance = 0.0
                    doc_key = str(metadata.get("chunk_id") or metadata.get("source_id") or self._doc_identity_key(doc))
                    role_kind = metadata.get("role_kind") or self._extract_role_kind(doc)
                    content = (getattr(doc, "page_content", "") or "")
                    advice_heavy = bool(
                        re.search(
                            r"\b(you should|we should|i recommend|recommend|suggest|consider|best practice|steps to|how to|guidance|advice|tips|as an ai)\b",
                            content,
                            flags=re.I,
                        )
                    )
                    signature = metadata.get("incident_signature") or metadata.get("incident_key") or self._build_incident_key(doc)
                    duplicate_penalty = max(0, signature_counts.get(signature, 0) - 1)
                    keep_score = relevance
                    if role_kind == "assistant":
                        keep_score -= 0.9
                    if advice_heavy:
                        keep_score -= 0.7
                    if doc_key in seen_ids and not self._is_must_include(doc):
                        keep_score -= 0.35
                    keep_score -= duplicate_penalty * 0.25
                    if self._is_must_include(doc):
                        keep_score += 3.0
                    scored.append((keep_score, doc))

                scored.sort(key=lambda item: item[0], reverse=True)
                trimmed = [doc for _score, doc in scored[:cap_value]]
                trimmed_keys = {self._doc_identity_key(doc) for doc in trimmed}
                dropped_count = max(0, len(existing_pool) - len([doc for doc in existing_pool if self._doc_identity_key(doc) in trimmed_keys]))
                added_count = len([doc for doc in trimmed if self._doc_identity_key(doc) in follow_keys])
                return trimmed, dropped_count, added_count

            def _build_context(doc_list):
                def _clamp(value, min_value, max_value):
                    return max(min_value, min(max_value, value))

                context_budget_chars = _clamp(
                    context_budget_tokens * TOKENS_TO_CHARS_RATIO,
                    min_value=12000,
                    max_value=MAX_PACKED_CONTEXT_CHARS,
                )
                context_blocks = []
                used_chars = 0
                was_truncated = False
                packed_count = 0
                citation_v2_enabled = self._frontier_enabled("citation_v2")
                citation_manager = CitationManager()

                for idx, doc in enumerate(doc_list, start=1):
                    metadata = getattr(doc, "metadata", {}) or {}
                    score = metadata.get("relevance_score", "N/A")
                    source = (
                        metadata.get("source")
                        or metadata.get("file_path")
                        or metadata.get("filename")
                        or "unknown"
                    )
                    chunk_id = metadata.get("chunk_id", "N/A")
                    header_label = f"Chunk {idx}"
                    if citation_v2_enabled:
                        source_locator = self._build_source_locator(
                            metadata, getattr(doc, "page_content", "") or ""
                        )
                        header_label = citation_manager.register(source_locator.source_id)
                    header = (
                        f"[{header_label} | chunk_id: {chunk_id} | "
                        f"score: {score} | source: {source}]"
                    )
                    content = doc.page_content.strip()
                    chunk_text = f"{header}\n{content}"

                    remaining = context_budget_chars - used_chars
                    if remaining <= 0:
                        was_truncated = True
                        break
                    if len(chunk_text) > remaining:
                        was_truncated = True
                        if remaining > len(header) + 20:
                            truncated_content = content[
                                : remaining - len(header) - 20
                            ].rstrip()
                            chunk_text = (
                                f"{header}\n{truncated_content}\n...[truncated]"
                            )
                        else:
                            break
                    context_blocks.append(chunk_text)
                    used_chars += len(chunk_text) + 2
                    packed_count += 1

                if was_truncated:
                    self.log(
                        "Context truncated during packing: "
                        f"packed_count={packed_count}, truncated={was_truncated}, "
                        f"used_chars={used_chars}, budget_chars={context_budget_chars}."
                    )

                return (
                    "\n\n".join(context_blocks),
                    was_truncated,
                    used_chars,
                    context_budget_chars,
                    packed_count,
                )

            def _append_context_if_enabled(iteration_label, context_text, truncated_flag):
                if not self.show_retrieved_context.get():
                    return
                status = " (truncated)" if truncated_flag else ""
                self.append_chat(
                    "source",
                    f"Retrieved context {iteration_label}{status}:\n{context_text}",
                )

            def _log_iteration_telemetry(
                iteration_id,
                output_style,
                agentic_mode,
                planner_subquery_count,
                query_count,
                digest_retrieved_count,
                digest_selected_count,
                raw_expanded_count,
                raw_unique_count,
                packed_docs,
                truncated_flag,
                trunc_used_chars,
                trunc_budget_chars,
                cap_reached_flag,
                retrieved_count,
                stage_timings_ms,
                selection_stats,
                coverage_stats,
                follow_up_queries,
                levels_used=None,
            ):
                truncation_note = (
                    f"{int(truncated_flag)} {trunc_used_chars}/{trunc_budget_chars}"
                )
                self.log(
                    "Iter "
                    f"{iteration_id} telemetry | style={output_style}, "
                    f"agentic={int(agentic_mode)}, planner_subqueries={planner_subquery_count}, "
                    f"queries={query_count}, levels={'+'.join(levels_used or ['L0'])}, "
                    f"digest={digest_retrieved_count}/{digest_selected_count}, raw={raw_expanded_count}/"
                    f"{raw_unique_count}/{packed_docs}, "
                    f"trunc={truncation_note}, cap_reached={int(cap_reached_flag)}, "
                    f"retrieved={retrieved_count}"
                )
                self._append_jsonl_telemetry(
                    {
                        "event": "iteration",
                        "run_id": run_id,
                        "iter": iteration_id,
                        "timing_ms": stage_timings_ms,
                        "agentic": int(agentic_mode),
                        "output_style": output_style,
                        "user_final_k": user_final_k,
                        "effective_final_k": final_k,
                        "packed_count": packed_docs,
                        "truncation": {
                            "was_truncated": bool(truncated_flag),
                            "used_chars": trunc_used_chars,
                            "budget_chars": trunc_budget_chars,
                        },
                        "retrieval_stats": {
                            "queries": query_count,
                            "planner_subqueries": planner_subquery_count,
                            "digest_retrieved_count": digest_retrieved_count,
                            "digest_selected_count": digest_selected_count,
                            "raw_expanded_count": raw_expanded_count,
                            "raw_unique_count": raw_unique_count,
                            "retrieved_count": retrieved_count,
                            "cap_reached": bool(cap_reached_flag),
                            "levels_used": levels_used or ["L0"],
                        },
                        "selection_stats": selection_stats,
                        "coverage_gate": {
                            **coverage_stats,
                            "follow_up_queries": follow_up_queries or [],
                        },
                    }
                )
                self._record_trace_stage(
                    run_id,
                    "context_pack",
                    "iteration_summary",
                    payload={
                        "packed_count": int(packed_docs),
                        "was_truncated": bool(truncated_flag),
                        "used_chars": int(trunc_used_chars),
                        "budget_chars": int(trunc_budget_chars),
                        "query_count": int(query_count),
                        "planner_subqueries": int(planner_subquery_count),
                    },
                    iteration=iteration_id,
                )

            seen_chunk_ids = set()

            if not resolved_settings["agentic_mode"]:
                iteration_started_at = time.perf_counter()
                follow_up_queries = []
                coverage_stats = {"triggered": False}
                planner_started_at = time.perf_counter()
                queries = [query]
                if self.use_sub_queries.get():
                    sub_queries = self._generate_sub_queries(query)
                    if sub_queries:
                        queries = [query, *sub_queries]
                self._record_agent_lightning_span(
                    run_id,
                    "Planner",
                    1,
                    planner_started_at,
                    input_payload={"query": query, "output_style": output_style},
                    output_payload={"queries": queries},
                    metrics={"subquery_count": max(0, len(queries) - 1)},
                )
                max_total_docs = max(1, int(self.subquery_max_docs.get()))
                retrieve_started_at = time.perf_counter()
                (
                    docs,
                    retrieved_count,
                    cap_reached,
                    digest_docs,
                    raw_expanded_count,
                    digest_retrieved_count,
                    digest_selected_count,
                    levels_used,
                ) = _retrieve_with_digest(
                    queries, min(total_docs_cap, max_total_docs), routing_candidate_k
                )
                self._record_agent_lightning_span(
                    run_id,
                    "Retrieve",
                    1,
                    retrieve_started_at,
                    input_payload={"queries": queries, "k": routing_candidate_k},
                    output_payload={"docs": len(docs), "levels": levels_used, "source_locators": self._source_locators_from_docs(docs)},
                    metrics={
                        "dense_count": int(raw_expanded_count),
                        "lexical_count": int(digest_selected_count),
                        "recursive_levels": levels_used or ["L0"],
                    },
                )
                self.log(
                    f"Retrieved {len(docs)} initial candidates from {len(queries)} query(s)."
                )
                rerank_started_at = time.perf_counter()
                if use_mini_digest:
                    routed_docs = self._route_with_mini_digest(docs, query, final_k)
                    self.log(
                        "Mini-digest routing selected "
                        f"{len(routed_docs)} candidate chunks."
                    )
                    candidate_docs = routed_docs
                else:
                    candidate_docs = docs
                self._record_agent_lightning_span(
                    run_id,
                    "Rerank",
                    1,
                    rerank_started_at,
                    input_payload={"candidate_docs": len(docs), "query": query},
                    output_payload={"candidate_docs": len(candidate_docs), "source_locators": self._source_locators_from_docs(candidate_docs)},
                    metrics={"novelty": len({(getattr(d, 'metadata', {}) or {}).get('chunk_id', '') for d in candidate_docs if (getattr(d, 'metadata', {}) or {}).get('chunk_id', '')})},
                )
                select_started_at = time.perf_counter()
                final_docs = _select_evidence_pack(
                    candidate_docs, query, is_evidence_pack, seen_chunk_ids=seen_chunk_ids
                )
                self._record_agent_lightning_span(
                    run_id,
                    "Select",
                    1,
                    select_started_at,
                    input_payload={"candidate_docs": len(candidate_docs), "final_k": final_k},
                    output_payload={"final_docs": len(final_docs)},
                    metrics={"coverage": float(len(final_docs) / max(1, final_k))},
                )

                generic_followups, generic_cov = _coverage_followup_from_metadata(candidate_docs, final_docs)
                self.log(
                    "Selection telemetry: "
                    f"final_docs={len(final_docs)}, months={generic_cov['selected_months']}/{generic_cov['pool_months']}, "
                    f"incidents={generic_cov['selected_incidents']}/{generic_cov['pool_incidents']}."
                )
                remaining_cap = max(0, total_docs_cap - len(docs))
                if generic_followups and resolved_settings["agentic_max_iterations"] > 1 and remaining_cap > 0:
                    self.log(f"Generic coverage gate triggered: follow-up queries={generic_followups}.")
                    follow_docs, follow_retrieved_count, follow_cap_reached = _retrieve_with_rrf(
                        generic_followups,
                        remaining_cap,
                        routing_candidate_k,
                    )
                    retrieved_count += follow_retrieved_count
                    cap_reached = cap_reached or follow_cap_reached
                    if follow_docs:
                        docs = self._merge_dedupe_docs(docs + follow_docs)
                        if use_mini_digest:
                            routed_docs = self._route_with_mini_digest(docs, query, final_k)
                            candidate_docs = routed_docs
                        else:
                            candidate_docs = docs
                        final_docs = _select_evidence_pack(
                            candidate_docs,
                            query,
                            is_evidence_pack,
                            seen_chunk_ids=seen_chunk_ids,
                        )
                        follow_up_queries = list(dict.fromkeys(follow_up_queries + generic_followups))

                if is_evidence_pack:
                    coverage = self.coverage_audit(final_docs, candidate_docs)
                    unique_incidents_value = coverage["incident_count"]
                    incident_floor = max(8, final_k // 2)
                    coverage_triggered = (
                        coverage["incident_count"] < incident_floor
                        or coverage["missing_indicators"]["months"]
                        or coverage["missing_indicators"]["channels"]
                    )
                    self.log(
                        "Coverage audit: incident_count="
                        f"{coverage['incident_count']}, months={coverage['selected_months']}/"
                        f"{coverage['available_months']}, channels={coverage['selected_channels']}/"
                        f"{coverage['available_channels']}, role_balance={coverage['role_balance']}."
                    )
                    if coverage_triggered:
                        follow_up_queries = self._generate_follow_up_queries(
                            coverage, candidate_docs
                        )
                        self.log(
                            "Coverage gate triggered: "
                            f"incident_floor={incident_floor}, queries={follow_up_queries}."
                        )
                        remaining_cap = max(0, total_docs_cap - len(docs))
                        if follow_up_queries and remaining_cap > 0:
                            follow_docs, follow_retrieved_count, follow_cap_reached = _retrieve_with_rrf(
                                follow_up_queries,
                                remaining_cap,
                                routing_candidate_k,
                            )
                            retrieved_count += follow_retrieved_count
                            cap_reached = cap_reached or follow_cap_reached
                            if follow_docs:
                                docs = self._merge_dedupe_docs(docs + follow_docs)
                                if use_mini_digest:
                                    routed_docs = self._route_with_mini_digest(
                                        docs, query, final_k
                                    )
                                    candidate_docs = routed_docs
                                    self.log(
                                        "Coverage follow-up routing selected "
                                        f"{len(routed_docs)} candidate chunks."
                                    )
                                else:
                                    candidate_docs = docs
                                final_docs = _select_evidence_pack(
                                    candidate_docs,
                                    query,
                                    is_evidence_pack,
                                    seen_chunk_ids=seen_chunk_ids,
                                )
                                unique_incidents_value = self.coverage_audit(
                                    final_docs, candidate_docs
                                )["incident_count"]
                                self.log(
                                    "Coverage follow-up retrieval added "
                                    f"{len(follow_docs)} chunks; reselected {len(final_docs)} chunks."
                                )
                        elif follow_up_queries and remaining_cap <= 0:
                            swap_k = 60
                            follow_docs, follow_retrieved_count, follow_cap_reached = _retrieve_with_rrf(
                                follow_up_queries,
                                swap_k,
                                min(routing_candidate_k, swap_k),
                            )
                            retrieved_count += follow_retrieved_count
                            cap_reached = cap_reached or follow_cap_reached
                            if follow_docs:
                                seed_n = min(len(docs), max(final_k * 4, 80))
                                existing_seed = self._apply_coverage_selection(
                                    docs,
                                    seed_n,
                                    group_limit=1 if is_evidence_pack else MAX_GROUP_DOCS,
                                    evidence_pack_mode=is_evidence_pack,
                                    seen_chunk_ids=seen_chunk_ids,
                                )
                                docs, dropped_count, added_count = _trim_followup_swap_pool(
                                    existing_seed,
                                    follow_docs,
                                    total_docs_cap,
                                    seen_ids=seen_chunk_ids,
                                )
                                if use_mini_digest:
                                    routed_docs = self._route_with_mini_digest(
                                        docs, query, final_k
                                    )
                                    candidate_docs = routed_docs
                                    self.log(
                                        "Coverage follow-up routing selected "
                                        f"{len(routed_docs)} candidate chunks."
                                    )
                                else:
                                    candidate_docs = docs
                                final_docs = _select_evidence_pack(
                                    candidate_docs,
                                    query,
                                    is_evidence_pack,
                                    seen_chunk_ids=seen_chunk_ids,
                                )
                                unique_incidents_value = self.coverage_audit(
                                    final_docs, candidate_docs
                                )["incident_count"]
                                self.log(
                                    f"Coverage follow-up swap: dropped={dropped_count}, "
                                    f"added={added_count}, cap={total_docs_cap}"
                                )
                        else:
                            self.log("Coverage follow-up skipped; no follow-up queries.")
                    coverage_stats = {
                        "triggered": bool(coverage_triggered),
                        "incident_floor": incident_floor,
                        "incident_count": coverage.get("incident_count", 0),
                    }
                else:
                    unique_incidents_value = len(final_docs)
                retrieval_selection_ms = int((time.perf_counter() - iteration_started_at) * 1000)
                seen_chunk_ids.update(
                    str((getattr(doc, "metadata", {}) or {}).get("chunk_id") or (getattr(doc, "metadata", {}) or {}).get("source_id") or self._doc_identity_key(doc))
                    for doc in final_docs
                )
                if is_evidence_pack:
                    trunc_budget_chars = max(
                        12000,
                        min(
                            MAX_PACKED_CONTEXT_CHARS,
                            context_budget_tokens * TOKENS_TO_CHARS_RATIO,
                        ),
                    )
                    (
                        context_text,
                        packed_count,
                        was_truncated,
                    ) = self._build_evidence_pack_context(
                        final_docs,
                        budget_chars=trunc_budget_chars,
                        per_doc_chars=600,
                    )
                    trunc_used_chars = len(context_text)
                else:
                    (
                        context_text,
                        was_truncated,
                        trunc_used_chars,
                        trunc_budget_chars,
                        packed_count,
                    ) = _build_context(final_docs)
                role_distribution = self._format_role_distribution(final_docs)
                selected_distribution = self._format_selected_distribution(final_docs)
                self._log_final_docs_selection(
                    retrieve_k,
                    candidate_k,
                    final_k,
                    trunc_used_chars,
                    trunc_budget_chars,
                    unique_incidents_value,
                    role_distribution,
                    final_k,
                    unique_incidents_value,
                    selected_distribution,
                )
                planner_subquery_count = 0
                if self.use_sub_queries.get():
                    planner_subquery_count = max(0, len(queries) - 1)
                selection_stats = {
                    "candidate_k": candidate_k,
                    "final_docs_count": len(final_docs),
                    "unique_incidents": unique_incidents_value,
                    "role_distribution": role_distribution,
                }
                self._record_agent_lightning_event(
                    run_id,
                    "selection",
                    {
                        "iter": 1,
                        "final_k": int(final_k),
                        "packed_count": int(packed_count),
                        "unique_incidents": int(unique_incidents_value),
                        "role_balance": role_distribution,
                    },
                )
                extract_started_at = time.perf_counter()
                extraction_payload = self._build_incident_export_payload(final_docs)
                self._record_agent_lightning_span(
                    run_id,
                    "ExtractIncidents",
                    1,
                    extract_started_at,
                    input_payload={"final_docs": len(final_docs)},
                    output_payload=extraction_payload,
                    metrics={"coverage": int(extraction_payload["incident_count"])},
                )
                self._record_agent_lightning_event(
                    run_id,
                    "extraction",
                    {
                        "iter": 1,
                        "incident_count": int(extraction_payload["incident_count"]),
                        "dated_count": int(extraction_payload["dated_count"]),
                        "undated_count": int(extraction_payload["undated_count"]),
                        "months_covered": extraction_payload["months_covered"],
                    },
                )
                _log_iteration_telemetry(
                    1,
                    self.output_style.get(),
                    resolved_settings["agentic_mode"],
                    planner_subquery_count,
                    len(queries),
                    digest_retrieved_count,
                    digest_selected_count,
                    raw_expanded_count,
                    len(docs),
                    packed_count,
                    was_truncated,
                    trunc_used_chars,
                    trunc_budget_chars,
                    cap_reached,
                    retrieved_count,
                    {
                        "retrieval_selection": retrieval_selection_ms,
                    },
                    selection_stats,
                    coverage_stats,
                    follow_up_queries,
                    levels_used,
                )
                _append_context_if_enabled("(single pass)", context_text, was_truncated)

                self.log("Generating Answer...")
                llm = self.get_llm()
                style_instruction = self._get_output_style_instruction()
                evidence_instruction = (
                    self._get_evidence_pack_instruction()
                    if is_evidence_pack
                    else ""
                )
                comprehension_artifacts = []
                comprehension_context = ""
                if use_comprehension_first:
                    comprehension_artifacts = precomputed_comprehension_artifacts or self.search_comprehension_artifacts(query, k=18)
                    if not comprehension_artifacts and final_docs:
                        source_map_seed, _ = self._build_source_cards(final_docs)
                        on_demand_artifacts = self._build_comprehension_artifacts(final_docs, "on_demand", source_map_seed)
                        if on_demand_artifacts:
                            self._upsert_comprehension_artifacts("on_demand", on_demand_artifacts)
                            self._write_comprehension_jsonl("on_demand", on_demand_artifacts)
                            comprehension_artifacts = on_demand_artifacts[:18]
                            self.log("Comprehension index built on-demand from retrieved chunks.")
                    comprehension_context = self._render_comprehension_context(comprehension_artifacts)
                prompt_parts = [self._get_system_instructions(resolved_settings)]
                if comprehension_context:
                    prompt_parts.append(
                        "Comprehension-first rule: Start from COMPREHENSION_ARTIFACTS (concepts, claims, takeaways, frameworks, entities), then corroborate with raw CONTEXT for citations and gap-filling."
                    )
                    prompt_parts.append(comprehension_context)
                if style_instruction:
                    prompt_parts.append(style_instruction)
                if evidence_instruction:
                    prompt_parts.append(evidence_instruction)
                prompt_parts.append(f"CONTEXT:\n{context_text}")
                system_prompt = "\n\n".join(prompt_parts)
                history_window = self._get_history_window(current_query=query)
                messages = [
                    self._system_message(content=system_prompt),
                    *history_window,
                    self._human_message(content=query),
                ]
                generation_started_at = time.perf_counter()
                generation_ms = 0
                is_blinkist_summary_style = self.output_style.get().strip() == "Blinkist-style summary"
                is_book_tutor_mode = resolved_settings.get("mode") == "Book Tutor"
                if is_evidence_pack:
                    response_content = _run_evidence_pack_two_stage(
                        llm,
                        query,
                        context_text,
                        final_docs,
                    )
                elif is_blinkist_summary_style:
                    response_content = _run_blinkist_summary_two_stage(
                        llm,
                        query,
                        final_docs,
                        digest_docs=digest_docs,
                    )
                elif is_book_tutor_mode:
                    response_content = _run_book_tutor_two_stage(
                        llm,
                        query,
                        final_docs,
                        digest_docs=digest_docs,
                    )
                else:
                    response = llm.invoke(messages)
                    response_content = response.content
                generation_ms = int((time.perf_counter() - generation_started_at) * 1000)
                self._record_agent_lightning_span(
                    run_id,
                    "Synthesize",
                    1,
                    generation_started_at,
                    input_payload={"context_chars": len(context_text), "docs": len(final_docs)},
                    output_payload=str(response_content or ""),
                    metrics={"novelty": len(set(str(response_content or "").split()))},
                )
                validation_started_at = time.perf_counter()
                validated_answer = self._validate_and_repair(
                    response_content,
                    context_text,
                    iteration_id=1,
                    evidence_pack_mode=is_evidence_pack,
                    synthesis_cards=self._last_evidence_pack_synthesis_cards,
                )
                validation_ms = int((time.perf_counter() - validation_started_at) * 1000)
                citation_pass_rate = min(1.0, self._count_citations(validated_answer) / max(1, self._count_claim_like_sentences(validated_answer)))
                self._record_agent_lightning_span(
                    run_id,
                    "VerifyCitations",
                    1,
                    validation_started_at,
                    input_payload=str(response_content or ""),
                    output_payload=str(validated_answer or ""),
                    metrics={"citation_pass_rate": citation_pass_rate},
                )
                self._record_agent_lightning_event(
                    run_id,
                    "generation",
                    {
                        "iter": 1,
                        "latency_ms": int(generation_ms),
                        "tokens_est": max(1, len(str(response_content or "")) // TOKENS_TO_CHARS_RATIO),
                        "chars": len(str(response_content or "")),
                    },
                )
                self._record_agent_lightning_event(
                    run_id,
                    "verification",
                    {
                        "iter": 1,
                        "claims_dropped": max(0, self._count_claim_like_sentences(response_content) - self._count_claim_like_sentences(validated_answer)),
                        "claims_cited": self._count_citations(validated_answer),
                    },
                )
                self._append_jsonl_telemetry(
                    {
                        "event": "iteration_stage_timings",
                        "run_id": run_id,
                        "iter": 1,
                        "timing_ms": {
                            "retrieval_selection": retrieval_selection_ms,
                            "generation": generation_ms,
                            "validation": validation_ms,
                        },
                    }
                )

                if is_evidence_pack:
                    source_map, source_cards_text = self._build_source_cards(final_docs)
                    self._latest_source_map = source_map
                    validated_answer = self._ensure_evidence_pack_template(
                        validated_answer,
                        list(self._latest_incidents or []),
                    )
                    self._run_on_ui(
                        self._refresh_evidence_pane,
                        source_map,
                        list(self._latest_incidents or []),
                        self._latest_grounding_html_path,
                    )
                    validated_answer = self._rewrite_evidence_pack_citations(
                        validated_answer, final_docs, source_map
                    )
                    if source_cards_text.strip():
                        validated_answer = f"{validated_answer.rstrip()}\n\n{source_cards_text}"
                elif self._frontier_enabled("citation_v2"):
                    source_map, _ = self._build_source_cards(final_docs)
                    self._latest_source_map = source_map
                    validated_answer = self._rewrite_evidence_pack_citations(
                        validated_answer, final_docs, source_map
                    )
                self.last_answer = validated_answer
                self._record_trace_stage(
                    run_id,
                    "final_answer",
                    "assistant_message",
                    payload={
                        "answer_chars": len(str(validated_answer or "")),
                        "citation_count": self._count_citations(validated_answer),
                    },
                )
                self.append_chat("agent", f"AI: {validated_answer}", run_id=run_id)
                self._append_history(self._ai_message(content=validated_answer))
                self._insert_session_message(
                    role="assistant",
                    content=validated_answer,
                    run_id=run_id,
                    sources_json=self._sources_to_json(final_docs),
                )
                self._run_on_ui(self.refresh_sessions_list)

                if is_evidence_pack:
                    self.append_chat("source", f"\n{source_cards_text}")
                else:
                    source_map, _ = self._build_source_cards(final_docs)
                    self._latest_source_map = source_map
                    self._latest_incidents = []
                    self._run_on_ui(self._refresh_evidence_pane, source_map, [], "")
                    if self._frontier_enabled("citation_v2"):
                        ordered = sorted(
                            source_map.values(),
                            key=lambda entry: int(str(entry.get("sid", "S999")).lstrip("S") or "999"),
                        )
                        sources_text = "\n".join(
                            [f"- [{entry.get('sid', 'S?')} | {entry.get('label', 'unknown')}]" for entry in ordered]
                        )
                    else:
                        sources_text = "\n".join(
                            [
                                (
                                    f"- [Chunk {idx} | chunk_id: "
                                    f"{getattr(d, 'metadata', {}).get('chunk_id', 'N/A')} | score: "
                                    f"{getattr(d, 'metadata', {}).get('relevance_score', 'N/A')} | "
                                    f"source: "
                                    f"{(getattr(d, 'metadata', {}) or {}).get('source') or (getattr(d, 'metadata', {}) or {}).get('file_path') or (getattr(d, 'metadata', {}) or {}).get('filename') or 'unknown'}]"
                                )
                                for idx, d in enumerate(final_docs, start=1)
                            ]
                        )
                    self.append_chat("source", f"\nSources used:\n{sources_text}")
                self._append_jsonl_telemetry(
                    {
                        "event": "run_end",
                        "run_id": run_id,
                        "iter": 0,
                        "timing_ms": {
                            "run_total": int((time.perf_counter() - run_started_at) * 1000),
                        },
                    }
                )
                self._finalize_agent_lightning_run(run_id, final_docs, validated_answer)
                return

            try:
                max_iterations_value = int(resolved_settings["agentic_max_iterations"])
            except (TypeError, ValueError):
                max_iterations_value = 2
            HARD_CAP = AGENTIC_MAX_ITERATIONS_HARD_CAP
            max_iterations = max(1, min(HARD_CAP, max_iterations_value))
            self.log(
                "Agentic run starting with resolved max_iterations="
                f"{max_iterations} (requested {max_iterations_value})."
            )
            total_retrieved = 0
            all_docs = []
            checklist = []
            section_plan = []
            latest_answer = ""
            validated_answer = ""
            latest_context_text = ""
            final_docs = []
            critic_queries = []

            last_iteration_id = 1
            planner_subquery_count = 0
            convergence_patience = 2
            stagnant_iterations = 0
            last_unique_incident_count = 0
            for iteration in range(1, max_iterations + 1):
                iteration_started_at = time.perf_counter()
                follow_up_queries = []
                coverage_stats = {"triggered": False}
                if iteration == 1:
                    planner_llm = self._get_llm_with_temperature(0.2)
                    if is_evidence_pack:
                        planner_prompt = (
                            "You are an evidence-pack retrieval planner. Given the user query and "
                            "output_style, return strict JSON with keys: checklist_items (array of "
                            "strings), retrieval_queries (array of 8-15 strings), section_plan "
                            "(optional array). Checklist must include: 6–12 strongest dated incidents, "
                            "2–4 supporting examples, timeline fields, impacts. Retrieval queries must be "
                            "generic coverage sweeps (not user-specified examples), including date sweeps "
                            "(months/years), channel terms (Teams/email/call/meeting/WhatsApp), and role "
                            "queries (formal grievance examples, key incidents, what happened impact "
                            "evidence). Ensure checklist and queries cover chronology/timeline, impacts, "
                            "grievances, and concrete examples. Do not include any extra text."
                        )
                    else:
                        planner_prompt = (
                            "You are a retrieval planner. Given the user query and output_style, "
                            "return strict JSON with keys: checklist_items (array of strings), "
                            "retrieval_queries (array of 4-10 strings), section_plan (optional array). "
                            "Do not include any extra text."
                        )
                    planner_messages = [
                        self._system_message(content=planner_prompt),
                        self._human_message(
                            content=json.dumps(
                                {
                                    "query": query,
                                    "output_style": output_style,
                                }
                            )
                        ),
                    ]
                    planner_started_at = time.perf_counter()
                    planner_response = planner_llm.invoke(planner_messages)
                    plan_payload = _extract_json_payload(planner_response.content) or {}
                    checklist = [
                        str(item).strip()
                        for item in plan_payload.get("checklist_items", [])
                        if str(item).strip()
                    ]
                    sub_queries = [
                        str(item).strip()
                        for item in plan_payload.get("retrieval_queries", [])
                        if str(item).strip()
                    ]
                    planner_subquery_count = len(sub_queries)
                    section_plan = [
                        str(item).strip()
                        for item in plan_payload.get("section_plan", [])
                        if str(item).strip()
                    ]
                    if not checklist:
                        checklist = [query.strip()]
                    seen_queries = set()
                    normalized_sub_queries = []
                    for candidate in [query, *sub_queries]:
                        key = candidate.lower().strip()
                        if key and key not in seen_queries:
                            seen_queries.add(key)
                            normalized_sub_queries.append(candidate)
                    if len(normalized_sub_queries) < 4:
                        fallback_queries = self._generate_sub_queries(query)
                        for candidate in fallback_queries:
                            key = candidate.lower().strip()
                            if key and key not in seen_queries:
                                seen_queries.add(key)
                                normalized_sub_queries.append(candidate)
                            if len(normalized_sub_queries) >= 4:
                                break
                    if len(normalized_sub_queries) < 4:
                        normalized_sub_queries.append(query)
                    iteration_queries = normalized_sub_queries[:10]
                    self._record_agent_lightning_span(
                        run_id,
                        "Planner",
                        iteration,
                        planner_started_at,
                        input_payload={"query": query, "output_style": output_style},
                        output_payload={"queries": iteration_queries, "checklist": checklist},
                        metrics={"subquery_count": len(iteration_queries), "checklist_items": len(checklist)},
                    )
                else:
                    if not critic_queries:
                        self.log("No critic follow-up queries; stopping iterations.")
                        break
                    iteration_queries = critic_queries

                prev_all_docs_count = len(all_docs)
                remaining_cap = max(0, total_docs_cap - total_retrieved)
                if remaining_cap == 0:
                    self.log("Total retrieved document cap reached; stopping iterations.")
                    break
                retrieve_started_at = time.perf_counter()
                (
                    docs,
                    retrieved_count,
                    cap_reached,
                    digest_docs,
                    raw_expanded_count,
                    digest_retrieved_count,
                    digest_selected_count,
                    levels_used,
                ) = _retrieve_with_digest(
                    iteration_queries, remaining_cap, routing_candidate_k
                )
                self._record_agent_lightning_span(
                    run_id,
                    "Retrieve",
                    iteration,
                    retrieve_started_at,
                    input_payload={"queries": iteration_queries, "remaining_cap": remaining_cap},
                    output_payload={"docs": len(docs), "levels": levels_used, "source_locators": self._source_locators_from_docs(docs)},
                    metrics={"dense_count": int(raw_expanded_count), "lexical_count": int(digest_selected_count), "recursive_levels": levels_used or ["L0"]},
                )
                total_retrieved += len(docs)
                all_docs = self._merge_dedupe_docs(all_docs + docs)
                new_incidents_added = len(all_docs) - prev_all_docs_count
                unique_incident_count = len(all_docs)
                if unique_incident_count <= last_unique_incident_count:
                    stagnant_iterations += 1
                else:
                    stagnant_iterations = 0
                    last_unique_incident_count = unique_incident_count
                stop_due_to_convergence = stagnant_iterations >= convergence_patience
                rerank_started_at = time.perf_counter()
                if use_mini_digest:
                    routed_docs = self._route_with_mini_digest(all_docs, query, final_k)
                    self.log(
                        "Mini-digest routing selected "
                        f"{len(routed_docs)} candidate chunks."
                    )
                    candidate_docs = routed_docs
                else:
                    candidate_docs = all_docs
                self._record_agent_lightning_span(
                    run_id,
                    "Rerank",
                    iteration,
                    rerank_started_at,
                    input_payload={"candidate_docs": len(all_docs)},
                    output_payload={"candidate_docs": len(candidate_docs), "source_locators": self._source_locators_from_docs(candidate_docs)},
                    metrics={"novelty": len({(getattr(d, 'metadata', {}) or {}).get('chunk_id', '') for d in candidate_docs if (getattr(d, 'metadata', {}) or {}).get('chunk_id', '')})},
                )
                select_started_at = time.perf_counter()
                final_docs = _select_evidence_pack(
                    candidate_docs, query, is_evidence_pack, seen_chunk_ids=seen_chunk_ids
                )
                self._record_agent_lightning_span(
                    run_id,
                    "Select",
                    iteration,
                    select_started_at,
                    input_payload={"candidate_docs": len(candidate_docs), "final_k": final_k},
                    output_payload={"final_docs": len(final_docs)},
                    metrics={"coverage": float(len(final_docs) / max(1, final_k))},
                )

                generic_followups, generic_cov = _coverage_followup_from_metadata(candidate_docs, final_docs)
                self.log(
                    "Selection telemetry: "
                    f"final_docs={len(final_docs)}, months={generic_cov['selected_months']}/{generic_cov['pool_months']}, "
                    f"incidents={generic_cov['selected_incidents']}/{generic_cov['pool_incidents']}."
                )
                remaining_cap = max(0, total_docs_cap - total_retrieved)
                if generic_followups and iteration < max_iterations and remaining_cap > 0:
                    self.log(f"Generic coverage gate triggered: follow-up queries={generic_followups}.")
                    follow_docs, follow_retrieved_count, follow_cap_reached = _retrieve_with_rrf(
                        generic_followups,
                        remaining_cap,
                        routing_candidate_k,
                    )
                    retrieved_count += follow_retrieved_count
                    cap_reached = cap_reached or follow_cap_reached
                    if follow_docs:
                        total_retrieved += len(follow_docs)
                        all_docs = self._merge_dedupe_docs(all_docs + follow_docs)
                        if use_mini_digest:
                            routed_docs = self._route_with_mini_digest(all_docs, query, final_k)
                            candidate_docs = routed_docs
                        else:
                            candidate_docs = all_docs
                        final_docs = _select_evidence_pack(
                            candidate_docs,
                            query,
                            is_evidence_pack,
                            seen_chunk_ids=seen_chunk_ids,
                        )
                        follow_up_queries = list(dict.fromkeys(follow_up_queries + generic_followups))

                if is_evidence_pack:
                    coverage = self.coverage_audit(final_docs, candidate_docs)
                    unique_incidents_value = coverage["incident_count"]
                    incident_floor = max(8, final_k // 2)
                    coverage_triggered = (
                        coverage["incident_count"] < incident_floor
                        or coverage["missing_indicators"]["months"]
                        or coverage["missing_indicators"]["channels"]
                    )
                    self.log(
                        "Coverage audit: incident_count="
                        f"{coverage['incident_count']}, months={coverage['selected_months']}/"
                        f"{coverage['available_months']}, channels={coverage['selected_channels']}/"
                        f"{coverage['available_channels']}, role_balance={coverage['role_balance']}."
                    )
                    if coverage_triggered:
                        follow_up_queries = self._generate_follow_up_queries(
                            coverage, candidate_docs
                        )
                        self.log(
                            "Coverage gate triggered: "
                            f"incident_floor={incident_floor}, queries={follow_up_queries}."
                        )
                        remaining_cap = max(0, total_docs_cap - total_retrieved)
                        if follow_up_queries and remaining_cap > 0:
                            follow_docs, follow_retrieved_count, follow_cap_reached = _retrieve_with_rrf(
                                follow_up_queries,
                                remaining_cap,
                                routing_candidate_k,
                            )
                            retrieved_count += follow_retrieved_count
                            cap_reached = cap_reached or follow_cap_reached
                            if follow_docs:
                                total_retrieved += len(follow_docs)
                                all_docs = self._merge_dedupe_docs(all_docs + follow_docs)
                                if use_mini_digest:
                                    routed_docs = self._route_with_mini_digest(
                                        all_docs, query, final_k
                                    )
                                    candidate_docs = routed_docs
                                    self.log(
                                        "Coverage follow-up routing selected "
                                        f"{len(routed_docs)} candidate chunks."
                                    )
                                else:
                                    candidate_docs = all_docs
                                final_docs = _select_evidence_pack(
                                    candidate_docs,
                                    query,
                                    is_evidence_pack,
                                    seen_chunk_ids=seen_chunk_ids,
                                )
                                unique_incidents_value = self.coverage_audit(
                                    final_docs, candidate_docs
                                )["incident_count"]
                                self.log(
                                    "Coverage follow-up retrieval added "
                                    f"{len(follow_docs)} chunks; reselected {len(final_docs)} chunks."
                                )
                        elif follow_up_queries and remaining_cap <= 0:
                            swap_k = 60
                            follow_docs, follow_retrieved_count, follow_cap_reached = _retrieve_with_rrf(
                                follow_up_queries,
                                swap_k,
                                min(routing_candidate_k, swap_k),
                            )
                            retrieved_count += follow_retrieved_count
                            cap_reached = cap_reached or follow_cap_reached
                            if follow_docs:
                                seed_n = min(len(all_docs), max(final_k * 4, 80))
                                existing_seed = self._apply_coverage_selection(
                                    all_docs,
                                    seed_n,
                                    group_limit=1 if is_evidence_pack else MAX_GROUP_DOCS,
                                    evidence_pack_mode=is_evidence_pack,
                                    seen_chunk_ids=seen_chunk_ids,
                                )
                                all_docs, dropped_count, added_count = _trim_followup_swap_pool(
                                    existing_seed,
                                    follow_docs,
                                    total_docs_cap,
                                    seen_ids=seen_chunk_ids,
                                )
                                total_retrieved = len(all_docs)
                                if use_mini_digest:
                                    routed_docs = self._route_with_mini_digest(
                                        all_docs, query, final_k
                                    )
                                    candidate_docs = routed_docs
                                    self.log(
                                        "Coverage follow-up routing selected "
                                        f"{len(routed_docs)} candidate chunks."
                                    )
                                else:
                                    candidate_docs = all_docs
                                final_docs = _select_evidence_pack(
                                    candidate_docs,
                                    query,
                                    is_evidence_pack,
                                    seen_chunk_ids=seen_chunk_ids,
                                )
                                unique_incidents_value = self.coverage_audit(
                                    final_docs, candidate_docs
                                )["incident_count"]
                                self.log(
                                    f"Coverage follow-up swap: dropped={dropped_count}, "
                                    f"added={added_count}, cap={total_docs_cap}"
                                )
                        else:
                            self.log("Coverage follow-up skipped; no follow-up queries.")
                    coverage_stats = {
                        "triggered": bool(coverage_triggered),
                        "incident_floor": incident_floor,
                        "incident_count": coverage.get("incident_count", 0),
                    }
                else:
                    unique_incidents_value = len(final_docs)
                retrieval_selection_ms = int((time.perf_counter() - iteration_started_at) * 1000)
                seen_chunk_ids.update(
                    str((getattr(doc, "metadata", {}) or {}).get("chunk_id") or (getattr(doc, "metadata", {}) or {}).get("source_id") or self._doc_identity_key(doc))
                    for doc in final_docs
                )
                if is_evidence_pack:
                    trunc_budget_chars = max(
                        12000,
                        min(
                            MAX_PACKED_CONTEXT_CHARS,
                            context_budget_tokens * TOKENS_TO_CHARS_RATIO,
                        ),
                    )
                    (
                        context_text,
                        packed_count,
                        was_truncated,
                    ) = self._build_evidence_pack_context(
                        final_docs,
                        budget_chars=trunc_budget_chars,
                        per_doc_chars=600,
                    )
                    trunc_used_chars = len(context_text)
                else:
                    (
                        context_text,
                        was_truncated,
                        trunc_used_chars,
                        trunc_budget_chars,
                        packed_count,
                    ) = _build_context(final_docs)
                role_distribution = self._format_role_distribution(final_docs)
                selected_distribution = self._format_selected_distribution(final_docs)
                self._log_final_docs_selection(
                    retrieve_k,
                    candidate_k,
                    final_k,
                    trunc_used_chars,
                    trunc_budget_chars,
                    unique_incidents_value,
                    role_distribution,
                    final_k,
                    new_incidents_added,
                    selected_distribution,
                )
                selection_stats = {
                    "candidate_k": candidate_k,
                    "final_docs_count": len(final_docs),
                    "unique_incidents": unique_incidents_value,
                    "new_incidents_added": new_incidents_added,
                    "role_distribution": role_distribution,
                }
                self._record_agent_lightning_event(
                    run_id,
                    "selection",
                    {
                        "iter": int(iteration),
                        "final_k": int(final_k),
                        "packed_count": int(packed_count),
                        "unique_incidents": int(unique_incidents_value),
                        "role_balance": role_distribution,
                    },
                )
                extract_started_at = time.perf_counter()
                extraction_payload = self._build_incident_export_payload(final_docs)
                self._record_agent_lightning_span(
                    run_id,
                    "ExtractIncidents",
                    iteration,
                    extract_started_at,
                    input_payload={"final_docs": len(final_docs)},
                    output_payload=extraction_payload,
                    metrics={"coverage": int(extraction_payload["incident_count"])},
                )
                self._record_agent_lightning_event(
                    run_id,
                    "extraction",
                    {
                        "iter": int(iteration),
                        "incident_count": int(extraction_payload["incident_count"]),
                        "dated_count": int(extraction_payload["dated_count"]),
                        "undated_count": int(extraction_payload["undated_count"]),
                        "months_covered": extraction_payload["months_covered"],
                    },
                )
                _log_iteration_telemetry(
                    iteration,
                    self.output_style.get(),
                    resolved_settings["agentic_mode"],
                    planner_subquery_count,
                    len(iteration_queries),
                    digest_retrieved_count,
                    digest_selected_count,
                    raw_expanded_count,
                    len(all_docs),
                    packed_count,
                    was_truncated,
                    trunc_used_chars,
                    trunc_budget_chars,
                    cap_reached,
                    retrieved_count,
                    {
                        "retrieval_selection": retrieval_selection_ms,
                    },
                    selection_stats,
                    coverage_stats,
                    follow_up_queries,
                    levels_used,
                )
                _append_context_if_enabled(
                    f"(iteration {iteration})", context_text, was_truncated
                )

                self.log("Generating Answer...")
                llm = self.get_llm()
                checklist_text = "\n".join(f"- {item}" for item in checklist)
                coverage_note = ""
                if iteration > 1:
                    coverage_note = (
                        "\nIf helpful, include a compact coverage table mapping checklist "
                        "items to evidence or omitted due to missing support."
                    )
                style_instruction = self._get_output_style_instruction()
                evidence_instruction = (
                    self._get_evidence_pack_instruction()
                    if is_evidence_pack
                    else ""
                )
                comprehension_artifacts = []
                comprehension_context = ""
                if use_comprehension_first:
                    comprehension_artifacts = precomputed_comprehension_artifacts or self.search_comprehension_artifacts(query, k=18)
                    if not comprehension_artifacts and final_docs:
                        source_map_seed, _ = self._build_source_cards(final_docs)
                        on_demand_artifacts = self._build_comprehension_artifacts(final_docs, "on_demand", source_map_seed)
                        if on_demand_artifacts:
                            self._upsert_comprehension_artifacts("on_demand", on_demand_artifacts)
                            self._write_comprehension_jsonl("on_demand", on_demand_artifacts)
                            comprehension_artifacts = on_demand_artifacts[:18]
                            self.log("Comprehension index built on-demand from retrieved chunks.")
                    comprehension_context = self._render_comprehension_context(comprehension_artifacts)
                prompt_parts = [self._get_system_instructions(resolved_settings)]
                if comprehension_context:
                    prompt_parts.append(
                        "Comprehension-first rule: Start from COMPREHENSION_ARTIFACTS (concepts, claims, takeaways, frameworks, entities), then corroborate with raw CONTEXT for citations and gap-filling."
                    )
                    prompt_parts.append(comprehension_context)
                if style_instruction:
                    prompt_parts.append(style_instruction)
                if evidence_instruction:
                    prompt_parts.append(evidence_instruction)
                if section_plan:
                    prompt_parts.append(
                        "SECTION PLAN:\n" + "\n".join(f"- {item}" for item in section_plan)
                    )
                prompt_parts.append(
                    "Strict rules: Use ONLY the context. Omit unsupported claims; deepen supported ones; "
                    "do not ask for more docs or missing info; do not use placeholders. If evidence "
                    "is thin, you may add one short 'Scope:' note at the top."
                )
                prompt_parts.append(f"CHECKLIST:\n{checklist_text}")
                prompt_parts.append(f"CONTEXT:\n{context_text}{coverage_note}")
                system_prompt = "\n\n".join(prompt_parts)
                history_window = self._get_history_window(current_query=query)
                messages = [
                    self._system_message(content=system_prompt),
                    *history_window,
                    self._human_message(content=query),
                ]
                generation_started_at = time.perf_counter()
                generation_ms = 0
                is_blinkist_summary_style = self.output_style.get().strip() == "Blinkist-style summary"
                is_book_tutor_mode = resolved_settings.get("mode") == "Book Tutor"
                if is_evidence_pack:
                    latest_answer = _run_evidence_pack_two_stage(
                        llm,
                        query,
                        context_text,
                        final_docs,
                        checklist_text=checklist_text,
                        section_plan_items=section_plan,
                        coverage_note=coverage_note,
                    )
                elif is_blinkist_summary_style:
                    latest_answer = _run_blinkist_summary_two_stage(
                        llm,
                        query,
                        final_docs,
                        digest_docs=digest_docs,
                    )
                elif is_book_tutor_mode:
                    latest_answer = _run_book_tutor_two_stage(
                        llm,
                        query,
                        final_docs,
                        digest_docs=digest_docs,
                    )
                else:
                    response = llm.invoke(messages)
                    latest_answer = response.content
                generation_ms = int((time.perf_counter() - generation_started_at) * 1000)
                self._record_agent_lightning_span(
                    run_id,
                    "Synthesize",
                    iteration,
                    generation_started_at,
                    input_payload={"context_chars": len(context_text), "docs": len(final_docs)},
                    output_payload=str(latest_answer or ""),
                    metrics={"novelty": len(set(str(latest_answer or "").split()))},
                )
                latest_context_text = context_text
                last_iteration_id = iteration
                self._append_jsonl_telemetry(
                    {
                        "event": "iteration_stage_timings",
                        "run_id": run_id,
                        "iter": iteration,
                        "timing_ms": {
                            "retrieval_selection": retrieval_selection_ms,
                            "generation": generation_ms,
                        },
                    }
                )

                if stop_due_to_convergence:
                    self.log(
                        "Unique incident count stalled at "
                        f"{unique_incident_count} for {stagnant_iterations} "
                        "iteration(s); stopping early."
                    )
                    break
                if iteration < max_iterations:
                    critic_llm = self._get_llm_with_temperature(0.2)
                    critic_prompt = (
                        "You are a critic. Review the answer against the checklist. "
                        "For each checklist item, mark it as FOUND with citations or "
                        "UNSUPPORTED. Unsupported means the answer should omit those details "
                        "(no placeholders) rather than request more docs, except one short "
                        "'Scope:' note at top when evidence is thin. If any items are UNSUPPORTED, propose new "
                        "retrieval_queries. Return strict JSON with keys: "
                        "checklist_review (array of {item, status, citations}), "
                        "retrieval_queries (array). Do not include extra text."
                    )
                    critic_messages = [
                        self._system_message(content=critic_prompt),
                        self._human_message(
                            content=(
                                f"Checklist:\n{checklist_text}\n\n"
                                f"Answer:\n{latest_answer}"
                            )
                        ),
                    ]
                    critic_response = critic_llm.invoke(critic_messages)
                    critic_payload = _extract_json_payload(critic_response.content) or {}
                    review_items = critic_payload.get("checklist_review", [])
                    missing_items = []
                    for review in review_items:
                        status = str(review.get("status", "")).strip().upper()
                        item = str(review.get("item", "")).strip()
                        if status == "UNSUPPORTED" and item:
                            missing_items.append(item)
                    critic_queries = [
                        str(item).strip()
                        for item in critic_payload.get("retrieval_queries", [])
                        if str(item).strip()
                    ][:3]
                    if not missing_items:
                        critic_queries = []

            if latest_answer:
                validation_started_at = time.perf_counter()
                validated_answer = self._validate_and_repair(
                    latest_answer,
                    latest_context_text,
                    iteration_id=last_iteration_id,
                    evidence_pack_mode=is_evidence_pack,
                    synthesis_cards=self._last_evidence_pack_synthesis_cards,
                )
                validation_ms = int((time.perf_counter() - validation_started_at) * 1000)
                citation_pass_rate = min(1.0, self._count_citations(validated_answer) / max(1, self._count_claim_like_sentences(validated_answer)))
                self._record_agent_lightning_span(
                    run_id,
                    "VerifyCitations",
                    last_iteration_id,
                    validation_started_at,
                    input_payload=str(latest_answer or ""),
                    output_payload=str(validated_answer or ""),
                    metrics={"citation_pass_rate": citation_pass_rate},
                )
                self._record_agent_lightning_event(
                    run_id,
                    "generation",
                    {
                        "iter": int(last_iteration_id),
                        "latency_ms": int(generation_ms),
                        "tokens_est": max(1, len(str(latest_answer or "")) // TOKENS_TO_CHARS_RATIO),
                        "chars": len(str(latest_answer or "")),
                    },
                )
                self._record_agent_lightning_event(
                    run_id,
                    "verification",
                    {
                        "iter": int(last_iteration_id),
                        "claims_dropped": max(0, self._count_claim_like_sentences(latest_answer) - self._count_claim_like_sentences(validated_answer)),
                        "claims_cited": self._count_citations(validated_answer),
                    },
                )
                self._append_jsonl_telemetry(
                    {
                        "event": "iteration_stage_timings",
                        "run_id": run_id,
                        "iter": last_iteration_id,
                        "timing_ms": {
                            "validation": validation_ms,
                        },
                    }
                )
                if is_evidence_pack:
                    source_map, source_cards_text = self._build_source_cards(final_docs)
                    self._latest_source_map = source_map
                    validated_answer = self._ensure_evidence_pack_template(
                        validated_answer,
                        list(self._latest_incidents or []),
                    )
                    self._run_on_ui(
                        self._refresh_evidence_pane,
                        source_map,
                        list(self._latest_incidents or []),
                        self._latest_grounding_html_path,
                    )
                    validated_answer = self._rewrite_evidence_pack_citations(
                        validated_answer, final_docs, source_map
                    )
                    if source_cards_text.strip():
                        validated_answer = f"{validated_answer.rstrip()}\n\n{source_cards_text}"
                elif self._frontier_enabled("citation_v2"):
                    source_map, _ = self._build_source_cards(final_docs)
                    self._latest_source_map = source_map
                    validated_answer = self._rewrite_evidence_pack_citations(
                        validated_answer, final_docs, source_map
                    )
                self.last_answer = validated_answer
                self._record_trace_stage(
                    run_id,
                    "final_answer",
                    "assistant_message",
                    payload={
                        "answer_chars": len(str(validated_answer or "")),
                        "citation_count": self._count_citations(validated_answer),
                    },
                )
                self.append_chat("agent", f"AI: {validated_answer}", run_id=run_id)
                self._append_history(self._ai_message(content=validated_answer))
                self._insert_session_message(
                    role="assistant",
                    content=validated_answer,
                    run_id=run_id,
                    sources_json=self._sources_to_json(final_docs),
                )
                self._run_on_ui(self.refresh_sessions_list)

            if is_evidence_pack:
                if not latest_answer:
                    _, source_cards_text = self._build_source_cards(final_docs)
                self.append_chat("source", f"\n{source_cards_text}")
            else:
                source_map, _ = self._build_source_cards(final_docs)
                self._latest_source_map = source_map
                self._latest_incidents = []
                self._run_on_ui(self._refresh_evidence_pane, source_map, [], "")
                if self._frontier_enabled("citation_v2"):
                    ordered = sorted(
                        source_map.values(),
                        key=lambda entry: int(str(entry.get("sid", "S999")).lstrip("S") or "999"),
                    )
                    sources_text = "\n".join(
                        [f"- [{entry.get('sid', 'S?')} | {entry.get('label', 'unknown')}]" for entry in ordered]
                    )
                else:
                    sources_text = "\n".join(
                        [
                            (
                                f"- [Chunk {idx} | chunk_id: "
                                f"{getattr(d, 'metadata', {}).get('chunk_id', 'N/A')} | score: "
                                f"{getattr(d, 'metadata', {}).get('relevance_score', 'N/A')} | "
                                f"source: "
                                f"{(getattr(d, 'metadata', {}) or {}).get('source') or (getattr(d, 'metadata', {}) or {}).get('file_path') or (getattr(d, 'metadata', {}) or {}).get('filename') or 'unknown'}]"
                            )
                            for idx, d in enumerate(final_docs, start=1)
                        ]
                    )
                self.append_chat("source", f"\nSources used:\n{sources_text}")

            self._append_jsonl_telemetry(
                {
                    "event": "run_end",
                    "run_id": run_id,
                    "iter": 0,
                    "timing_ms": {
                        "run_total": int((time.perf_counter() - run_started_at) * 1000),
                    },
                }
            )
            self._finalize_agent_lightning_run(run_id, final_docs, validated_answer or latest_answer)
        except Exception as e:
            self.log(f"RAG Error ({stage} failure): {e}")
            self.append_chat("system", f"Error ({stage} failure): {e}")
            self._append_jsonl_telemetry(
                {
                    "event": "run_error",
                    "run_id": run_id,
                    "iter": 0,
                    "stage": stage,
                    "error": str(e),
                }
            )
        finally:
            if self._active_run_id == run_id:
                self._active_run_id = None

    def _tag_citations_in_chat(self, start_index, end_index):
        text = self.chat_display.get(start_index, end_index)
        for match in re.finditer(r"S\d+", text or ""):
            start = self.chat_display.index(f"{start_index}+{match.start()}c")
            end = self.chat_display.index(f"{start_index}+{match.end()}c")
            self.chat_display.tag_add("citation", start, end)
    def append_chat(self, tag, message, run_id=None):
        def _append():
            self.chat_display.config(state="normal")
            start = self.chat_display.index(tk.END)
            self.chat_display.insert(tk.END, message + "\n", tag)
            end = self.chat_display.index(tk.END)
            self._tag_citations_in_chat(start, end)
            if tag == "agent":
                if run_id:
                    self._assistant_message_counter += 1
                    up_tag = f"feedback_up_{self._assistant_message_counter}"
                    down_tag = f"feedback_down_{self._assistant_message_counter}"
                    self.chat_display.insert(tk.END, "   ")
                    self.chat_display.insert(tk.END, "👍", up_tag)
                    self.chat_display.insert(tk.END, "  ")
                    self.chat_display.insert(tk.END, "👎", down_tag)
                    self.chat_display.tag_config(up_tag, foreground="#1b7f3a", underline=1)
                    self.chat_display.tag_config(down_tag, foreground="#a12f2f", underline=1)
                    self.chat_display.tag_bind(up_tag, "<Button-1>", lambda _e, rid=run_id: self._submit_feedback(rid, 1))
                    self.chat_display.tag_bind(down_tag, "<Button-1>", lambda _e, rid=run_id: self._submit_feedback(rid, -1))
                self.chat_display.insert(tk.END, "\n\n")
                if hasattr(self, "answer_text"):
                    answer_body = str(message).replace("AI:", "", 1).strip()
                    self._set_readonly_text(self.answer_text, answer_body)
                    self._tag_citations_in_answer()
            else:
                self.chat_display.insert(tk.END, "\n")
            self.chat_display.see(tk.END)
            self.chat_display.config(state="disabled")

        self._run_on_ui(_append)

    def clear_chat(self):
        self.chat_display.config(state="normal")
        self.chat_display.delete("1.0", tk.END)
        self.chat_display.config(state="disabled")
        self.last_answer = ""
        self.chat_history = []

    def save_chat(self):
        transcript = self.chat_display.get("1.0", tk.END).strip()
        if not transcript:
            messagebox.showinfo("No Chat History", "There is no chat transcript to save.")
            return
        save_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt")],
            title="Save Chat Transcript",
        )
        if not save_path:
            return
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(transcript + "\n")
            self.log(f"Chat transcript saved to {save_path}")
        except OSError as exc:
            messagebox.showerror("Save Failed", f"Could not save transcript: {exc}")

    def copy_last_answer(self):
        if not self.last_answer:
            messagebox.showinfo("No Answer", "There is no AI answer to copy yet.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.last_answer)
        self.root.update()
        self.log("Last answer copied to clipboard.")

    def export_notes_to_markdown(self):
        notes = (self.last_answer or "").strip()
        if not notes:
            messagebox.showinfo("No Notes", "There are no tutor notes to export yet.")
            return
        default_name = f"book_tutor_notes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
        save_path = filedialog.asksaveasfilename(
            defaultextension=".md",
            initialfile=default_name,
            filetypes=[("Markdown Files", "*.md"), ("All Files", "*.*")],
            title="Export Notes to Markdown",
        )
        if not save_path:
            return
        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(notes + "\n")
            self.log(f"Notes exported to Markdown: {save_path}")
        except OSError as exc:
            messagebox.showerror("Export Failed", f"Could not export notes: {exc}")


# Acceptance tests (comments only; do not execute):
# - Digest expansion: when filtering by ingest_id + chunk_id list, Chroma get should not throw "exactly one operator".
# - Lexical search: query containing "Sam.Weekes@gbe.gov.uk" should not crash; should return [] or results; must not disable lexical_db_available.
# - Agent loop: running with novelty tracking should not raise NameError; seen_chunk_ids should grow across iterations.
# - Ingestion should not emit utcnow() deprecation warning.
# - If citation_v2 enabled, answer uses [S#] and Sources shows readable labels (not chunk ids).
# - If citation_v2 disabled, legacy [Chunk N] citations still work end-to-end.
# - A generated answer includes [S#] citations and a Sources list with meaningful labels (not chunk-only labels).
# - Acceptance test (comment): trace export creates non-empty trace_events.jsonl with run_id, stage, event_type, latency_ms, payload fields.
# - Source cards include chapter/section and char offset locator for book-like raw text ingestion.
# - With "Build Comprehension Index" enabled, ingestion should create concept_cards rows in SQLite.
# - search_concepts("...") should return relevant concept_cards (title/kind/card_text/source refs) for topical queries.
# - Concept cards should preserve grounded S#-style source locators via source_refs_json entries.
# - Tutor mode produces flashcards and quiz for a query like "Teach me X from this book".
# - Given deliberately weak retrieval, claim-level grounding (CiteFix-lite) outputs a smaller but fully supported answer with no placeholders.


if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = AgenticRAGApp(root)
        root.mainloop()
    except Exception as e:
        print(f"Startup Error: {e}")
