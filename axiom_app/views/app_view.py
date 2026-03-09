"""PySide6 main window for the MVC Axiom application."""

from __future__ import annotations

import json
import pathlib
import sys
from importlib import resources
from typing import Any

from PySide6.QtCore import QEvent, QObject, QPoint, QRectF, QSignalBlocker, QSize, Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QKeyEvent, QPainter, QPainterPath, QPen, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QPlainTextEdit,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from axiom_app.models.session_types import EvidenceSource
from axiom_app.services.local_llm_recommender import LocalLlmRecommenderService
from axiom_app.services.wizard_recommendation import (
    describe_auto_recommendation,
    estimate_setup_cost,
    recommend_auto_settings,
)
from axiom_app.utils.model_presets import (
    get_llm_model_presets,
    list_llm_providers,
    provider_requires_custom_model,
    uses_custom_model_value,
)
from axiom_app.views.brain_canvas import BrainPanel
from axiom_app.views.styles import STYLE_CONFIG, UI_SPACING, apply_theme_to_app, get_palette, resolve_fonts
from axiom_app.views.widgets import AnimationEngine, CollapsibleFrame, IOSSegmentedToggle, RoundedCard, TooltipManager

APP_NAME = "Axiom"
APP_VERSION = "1.0"
APP_SUBTITLE = "Personal RAG Assistant"
MODE_OPTIONS = ["Q&A", "Summary", "Tutor", "Research", "Evidence Pack"]
_BRAND_ASSET_PACKAGE = "axiom_app.assets"
_BRAND_ASSET_NAME = "logo.png"
_CHAT_PRESETS = [
    {
        "title": "Ask Documents",
        "description": "Ground answers in your indexed files with citations.",
        "mode": "Q&A",
        "chat_path": "RAG",
    },
    {
        "title": "Chat Freely",
        "description": "Talk directly to the model without retrieval.",
        "mode": "Q&A",
        "chat_path": "Direct",
    },
    {
        "title": "Summarize",
        "description": "Condense a source into the most important ideas.",
        "mode": "Summary",
        "chat_path": "RAG",
    },
    {
        "title": "Learn",
        "description": "Use tutor-style prompts to understand the material.",
        "mode": "Tutor",
        "chat_path": "RAG",
    },
    {
        "title": "Research",
        "description": "Fan out across the workspace and compare evidence.",
        "mode": "Research",
        "chat_path": "RAG",
    },
    {
        "title": "Evidence Pack",
        "description": "Build a traceable answer pack with supporting sources.",
        "mode": "Evidence Pack",
        "chat_path": "RAG",
    },
]

_DEFAULT_WINDOW_W = 1480
_DEFAULT_WINDOW_H = 960
_MIN_WINDOW_W = 1180
_MIN_WINDOW_H = 760
_NAV_ITEMS = [
    ("chat", "Chat"),
    ("brain", "Brain"),
    ("settings", "Settings"),
    ("logs", "Logs"),
]

_SETTINGS_SPEC: list[tuple[str, list[tuple[str, str, str, list[str] | None]]]] = [
    ("Appearance & Startup", [
        ("theme", "Theme", "combobox", ["space_dust", "light", "dark"]),
        ("startup_mode_setting", "Startup Experience", "combobox", ["advanced", "basic", "test"]),
        ("ui_backend", "UI Backend", "combobox", ["pyside6"]),
    ]),
    ("Models: LLM", [
        ("llm_provider", "LLM Provider", "combobox", ["anthropic", "openai", "google", "xai", "local_lm_studio", "local_gguf", "mock"]),
        ("llm_model", "LLM Model", "entry", None),
        ("llm_model_custom", "Custom Model", "entry", None),
        ("llm_temperature", "Temperature", "entry", None),
        ("llm_max_tokens", "Max Tokens", "entry", None),
        ("verbose_mode", "Verbose Mode", "checkbutton", None),
    ]),
    ("Models: Local Runtime", [
        ("local_llm_url", "LM Studio URL", "entry", None),
        ("local_gguf_model_path", "GGUF Model Path", "file_browse", None),
        ("local_gguf_models_dir", "GGUF Models Dir", "entry", None),
        ("local_gguf_context_length", "Context Length", "entry", None),
        ("local_gguf_gpu_layers", "GPU Layers", "entry", None),
        ("local_gguf_threads", "CPU Threads", "entry", None),
    ]),
    ("Advanced: Hardware Overrides", [
        ("hardware_override_enabled", "Enable Overrides", "checkbutton", None),
        ("hardware_override_total_ram_gb", "Total RAM (GB)", "entry", None),
        ("hardware_override_available_ram_gb", "Available RAM (GB)", "entry", None),
        ("hardware_override_gpu_name", "GPU Name", "entry", None),
        ("hardware_override_gpu_vram_gb", "GPU VRAM (GB)", "entry", None),
        ("hardware_override_gpu_count", "GPU Count", "entry", None),
        ("hardware_override_backend", "Backend", "combobox", ["", "cpu_x86", "cpu_arm", "cuda", "metal", "rocm", "vulkan", "sycl", "ascend"]),
        ("hardware_override_unified_memory", "Unified Memory", "checkbutton", None),
    ]),
    ("Conversations: System Prompt", [
        ("system_instructions", "System Prompt", "text", None),
    ]),
    ("Models: Embeddings", [
        ("embeddings_backend", "Backend", "combobox", ["mock", "sentence_transformers", "voyage", "openai"]),
        ("embedding_provider", "Provider", "combobox", ["voyage", "openai", "google", "local_huggingface", "local_sentence_transformers", "mock"]),
        ("embedding_model", "Model", "entry", None),
        ("embedding_model_custom", "Custom Model", "entry", None),
        ("sentence_transformers_model", "ST Model", "entry", None),
        ("local_st_cache_dir", "ST Cache Dir", "entry", None),
        ("local_st_batch_size", "ST Batch Size", "entry", None),
        ("force_embedding_compat", "Force Compat", "checkbutton", None),
        ("cache_dir", "Axiom Cache Dir", "entry", None),
    ]),
    ("Documents & Retrieval: Storage", [
        ("vector_db_type", "DB Type", "combobox", ["json", "chroma", "weaviate"]),
        ("weaviate_url", "Weaviate URL", "entry", None),
        ("weaviate_api_key", "Weaviate Key", "entry_password", None),
    ]),
    ("Privacy & Storage: API Keys", [
        ("api_key_openai", "OpenAI", "entry_password", None),
        ("api_key_anthropic", "Anthropic", "entry_password", None),
        ("api_key_google", "Google", "entry_password", None),
        ("api_key_xai", "xAI", "entry_password", None),
        ("api_key_cohere", "Cohere", "entry_password", None),
        ("api_key_mistral", "Mistral", "entry_password", None),
        ("api_key_groq", "Groq", "entry_password", None),
        ("api_key_azure_openai", "Azure OpenAI", "entry_password", None),
        ("api_key_together", "Together AI", "entry_password", None),
        ("api_key_voyage", "Voyage", "entry_password", None),
        ("api_key_huggingface", "HuggingFace", "entry_password", None),
        ("api_key_fireworks", "Fireworks", "entry_password", None),
        ("api_key_perplexity", "Perplexity", "entry_password", None),
    ]),
    ("Documents & Retrieval: Ingestion", [
        ("document_loader", "Document Loader", "combobox", ["auto", "plain"]),
        ("chunk_size", "Chunk Size", "entry", None),
        ("chunk_overlap", "Chunk Overlap", "entry", None),
        ("structure_aware_ingestion", "Structure-Aware", "checkbutton", None),
        ("semantic_layout_ingestion", "Semantic Layout", "checkbutton", None),
        ("build_digest_index", "Build Digest Index", "checkbutton", None),
        ("build_comprehension_index", "Build Comprehension", "checkbutton", None),
        ("comprehension_extraction_depth", "Extraction Depth", "combobox", ["Standard", "Deep", "Exhaustive"]),
    ]),
    ("Documents & Retrieval: Querying", [
        ("top_k", "Top-K (final)", "entry", None),
        ("retrieval_k", "Retrieval K", "entry", None),
        ("retrieval_mode", "Retrieval Mode", "combobox", ["flat", "hierarchical"]),
        ("search_type", "Search Type", "combobox", ["similarity", "mmr"]),
        ("kg_query_mode", "KG Query Mode", "combobox", ["naive", "local", "global", "hybrid", "mix", "bypass"]),
        ("mmr_lambda", "MMR Lambda", "entry", None),
        ("use_reranker", "Use Reranker", "checkbutton", None),
        ("use_sub_queries", "Sub-Queries", "checkbutton", None),
        ("subquery_max_docs", "Max Sub-Q Docs", "entry", None),
    ]),
    ("Conversations: Defaults", [
        ("chat_history_max_turns", "History Turns", "entry", None),
        ("output_style", "Output Style", "combobox", ["Default answer", "Detailed answer", "Brief / exec summary", "Script / talk track", "Structured report", "Blinkist-style summary"]),
        ("selected_mode", "Mode", "combobox", MODE_OPTIONS),
    ]),
    ("Conversations: Retrieval Behavior", [
        ("agentic_mode", "Agentic Mode", "checkbutton", None),
        ("agentic_max_iterations", "Max Iterations", "entry", None),
        ("show_retrieved_context", "Show Context", "checkbutton", None),
    ]),
    ("Advanced: Experimental", [
        ("enable_summarizer", "Summarizer", "checkbutton", None),
        ("enable_langextract", "LangExtract", "checkbutton", None),
        ("enable_structured_extraction", "Structured Extraction", "checkbutton", None),
        ("enable_recursive_memory", "Recursive Memory", "checkbutton", None),
        ("enable_recursive_retrieval", "Recursive Retrieval", "checkbutton", None),
        ("enable_citation_v2", "Citation v2", "checkbutton", None),
        ("enable_claim_level_grounding_citefix_lite", "CiteFix Lite", "checkbutton", None),
        ("agent_lightning_enabled", "Lightning Mode", "checkbutton", None),
        ("prefer_comprehension_index", "Prefer Comprehension", "checkbutton", None),
        ("deepread_mode", "DeepRead Mode", "checkbutton", None),
        ("secure_mode", "Secure Mode", "checkbutton", None),
        ("experimental_override", "Experimental Override", "checkbutton", None),
    ]),
    ("Privacy & Storage: Logs", [
        ("log_dir", "Log Directory", "entry", None),
        ("log_level", "Log Level", "combobox", ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    ]),
]

_SETTINGS_EXPANDED = {
    "Appearance & Startup",
    "Models: LLM",
    "Models: Embeddings",
    "Conversations: Defaults",
}


def _crop_transparent_margins(pixmap: QPixmap) -> QPixmap:
    """Trim transparent padding so the sidebar logo uses the visible mark area."""
    if pixmap.isNull():
        return pixmap
    image = pixmap.toImage()
    if not image.hasAlphaChannel():
        return pixmap

    left = image.width()
    top = image.height()
    right = -1
    bottom = -1

    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 0:
                left = min(left, x)
                top = min(top, y)
                right = max(right, x)
                bottom = max(bottom, y)

    if right < left or bottom < top:
        return pixmap
    return pixmap.copy(left, top, right - left + 1, bottom - top + 1)


def _load_packaged_pixmap(package_name: str, resource_name: str) -> QPixmap:
    pixmap = QPixmap()
    data: bytes | None = None

    try:
        data = resources.files(package_name).joinpath(resource_name).read_bytes()
    except Exception:
        bundle_root = getattr(sys, "_MEIPASS", None)
        if bundle_root:
            candidate = pathlib.Path(bundle_root) / package_name.replace(".", "/") / resource_name
            if candidate.is_file():
                data = candidate.read_bytes()
        if data is None:
            package_dir = pathlib.Path(__file__).resolve().parents[1] / "assets" / resource_name
            if package_dir.is_file():
                data = package_dir.read_bytes()

    if data and pixmap.loadFromData(data):
        return _crop_transparent_margins(pixmap)
    return QPixmap()


class _BrandMark(QWidget):
    def __init__(self, palette: dict[str, str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._palette = dict(palette)
        self.setFixedSize(56, 56)

    def update_palette(self, palette: dict[str, str]) -> None:
        self._palette = dict(palette)
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(4, 4, -4, -4)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self._palette.get("accent_glow", "#0F4D79")))
        painter.drawEllipse(rect.adjusted(-2, -2, 2, 2))
        painter.setBrush(QColor(self._palette.get("primary", "#2EB7FF")))
        painter.drawEllipse(rect)
        path = QPainterPath()
        path.moveTo(rect.left() + 11, rect.bottom() - 11)
        path.lineTo(rect.center().x(), rect.top() + 11)
        path.lineTo(rect.right() - 11, rect.bottom() - 11)
        path.lineTo(rect.center().x(), rect.center().y() + 4)
        path.closeSubpath()
        painter.fillPath(path, QColor(self._palette.get("surface", "#091522")))


class _NavButton(QPushButton):
    def __init__(self, label: str, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(44)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class AppView(QMainWindow):
    closeRequested = Signal()
    sendRequested = Signal()
    cancelRequested = Signal()
    openFilesRequested = Signal()
    buildIndexRequested = Signal()
    saveSettingsRequested = Signal()
    newChatRequested = Signal()
    toggleSkillRequested = Signal()
    pinSkillRequested = Signal()
    muteSkillRequested = Signal()
    loadProfileRequested = Signal()
    saveProfileRequested = Signal()
    duplicateProfileRequested = Signal()
    feedbackRequested = Signal(int)
    historyOpenRequested = Signal()
    historyDeleteRequested = Signal()
    historyRenameRequested = Signal()
    historyDuplicateRequested = Signal()
    historyExportRequested = Signal()
    historyRefreshRequested = Signal()
    historySearchRequested = Signal()
    historySelectionRequested = Signal()
    historySkillFilterRequested = Signal()
    historyProfileFilterRequested = Signal()
    brainNodeSelected = Signal(str)
    brainNodeActivated = Signal(str)
    brainRefreshRequested = Signal()
    loadIndexRequested = Signal()
    addLocalGgufRequested = Signal()
    addLocalSentenceTransformerRequested = Signal()
    removeLocalModelRequested = Signal()
    activateLocalModelRequested = Signal(str)
    openLocalModelFolderRequested = Signal()
    installLocalDependencyRequested = Signal(object)
    refreshLocalGgufRecommendationsRequested = Signal(str)
    importLocalGgufRecommendationRequested = Signal()
    applyLocalGgufRecommendationRequested = Signal()
    editHardwareAssumptionsRequested = Signal()
    hereticAbliterateRequested = Signal()
    modeStateChanged = Signal(dict)
    quickModelChangeRequested = Signal(object)

    def __init__(self, theme_name: str = "space_dust", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme_name = theme_name
        self._palette = get_palette(theme_name)
        self._fonts = resolve_fonts()
        self._animator = AnimationEngine(self)
        self._local_llm_recommender = LocalLlmRecommenderService()
        self.tooltip_manager = TooltipManager(self, lambda: self._palette)
        self._allow_close = False
        self._chat_has_messages = False
        self._settings_data: dict[str, Any] = {}
        self._settings_widgets: dict[str, QWidget] = {}
        self._mode_state_callback = None
        self._history_rows: list[Any] = []
        self._available_index_rows: list[dict[str, Any]] = []
        self._log_buffer: list[str] = []
        self._cards: list[RoundedCard] = []
        self._nav_buttons: dict[str, _NavButton] = {}
        self._active_view = "chat"
        self._brand_logo_pixmap = QPixmap()
        self._chat_has_completed_response = False
        self._chat_feedback_pending = False
        self._chat_splitter_sizes = [820, 360]
        self._quick_model_popup_syncing = False

        self._load_icon()
        self._build()
        self.apply_theme(theme_name)
        self.switch_view("chat")

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        if watched is getattr(self, "prompt_entry", None) and isinstance(event, QKeyEvent):
            if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if event.modifiers() & Qt.ShiftModifier:
                    return False
                self.sendRequested.emit()
                return True
        return super().eventFilter(watched, event)

    def closeEvent(self, event: Any) -> None:
        if self._allow_close:
            event.accept()
            return
        event.ignore()
        self.closeRequested.emit()

    def dialog_parent(self) -> QWidget:
        return self

    def close_window(self) -> None:
        self._allow_close = True
        self.close()

    def show(self) -> None:
        super().show()
        self.raise_()
        self.activateWindow()

    def _build(self) -> None:
        self.setWindowTitle(f"{APP_NAME} - {APP_SUBTITLE}")
        self.resize(_DEFAULT_WINDOW_W, _DEFAULT_WINDOW_H)
        self.setMinimumSize(_MIN_WINDOW_W, _MIN_WINDOW_H)

        root = QWidget(self)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(UI_SPACING["l"], UI_SPACING["l"], UI_SPACING["l"], UI_SPACING["l"])
        root_layout.setSpacing(UI_SPACING["m"])
        self.setCentralWidget(root)

        shell = QWidget(root)
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(UI_SPACING["m"])
        root_layout.addWidget(shell, 1)

        sidebar_card, sidebar_layout = self._new_card()
        sidebar_card.setFixedWidth(240)
        shell_layout.addWidget(sidebar_card)
        self._build_sidebar(sidebar_layout)

        content_card, content_layout = self._new_card()
        shell_layout.addWidget(content_card, 1)
        self._build_pages(content_layout)

        footer = QWidget(root)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        self._status_label = QLabel("Ready.", footer)
        self._footer_label = QLabel(f"v{APP_VERSION}  PySide6", footer)
        footer_layout.addWidget(self._status_label, 1)
        footer_layout.addWidget(self._footer_label)
        root_layout.addWidget(footer)

    def _new_card(self) -> tuple[RoundedCard, QVBoxLayout]:
        card = RoundedCard(
            self,
            radius=STYLE_CONFIG.get("radius_lg", 28),
            bg=self._palette.get("surface", "#091522"),
            border_color=self._palette.get("border", "#17405F"),
            shadow_color=self._palette.get("workspace_shadow", "#010408"),
            shadow_offset=3,
            inner_padding=18,
        )
        layout = QVBoxLayout(card.inner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(UI_SPACING["m"])
        self._cards.append(card)
        return card, layout

    def _build_sidebar(self, layout: QVBoxLayout) -> None:
        brand_row = QHBoxLayout()
        brand_row.setSpacing(UI_SPACING["s"])
        self._brand_icon_stack = QStackedWidget(self)
        self._brand_icon_stack.setFixedSize(72, 72)
        self._brand_icon_stack.setObjectName("brandIconStack")

        self._brand_logo_label = QLabel(self)
        self._brand_logo_label.setObjectName("brandLogo")
        self._brand_logo_label.setAlignment(Qt.AlignCenter)
        self._brand_logo_label.setFixedSize(64, 64)

        self._brand_mark = _BrandMark(self._palette, self)

        self._brand_logo_page = QWidget(self)
        logo_page_layout = QVBoxLayout(self._brand_logo_page)
        logo_page_layout.setContentsMargins(0, 0, 0, 0)
        logo_page_layout.addWidget(self._brand_logo_label, 0, Qt.AlignCenter)

        self._brand_mark_page = QWidget(self)
        mark_page_layout = QVBoxLayout(self._brand_mark_page)
        mark_page_layout.setContentsMargins(0, 0, 0, 0)
        mark_page_layout.addWidget(self._brand_mark, 0, Qt.AlignCenter)

        self._brand_icon_stack.addWidget(self._brand_logo_page)
        self._brand_icon_stack.addWidget(self._brand_mark_page)
        brand_row.addWidget(self._brand_icon_stack, 0, Qt.AlignTop)
        text_layout = QVBoxLayout()
        self._brand_title = QLabel(APP_NAME, self)
        self._brand_title.setObjectName("brandTitle")
        self._brand_subtitle = QLabel(APP_SUBTITLE, self)
        self._brand_subtitle.setWordWrap(True)
        text_layout.addWidget(self._brand_title)
        text_layout.addWidget(self._brand_subtitle)
        brand_row.addLayout(text_layout, 1)
        brand_host = QWidget(self)
        brand_host.setLayout(brand_row)
        layout.addWidget(brand_host)
        self._apply_brand_logo()
        self.tooltip_manager.register(brand_host, f"{APP_NAME} {APP_VERSION}")

        nav_layout = QVBoxLayout()
        nav_layout.setSpacing(UI_SPACING["xs"])
        for key, label in _NAV_ITEMS:
            button = _NavButton(label, self)
            button.clicked.connect(lambda _checked=False, item=key: self.switch_view(item))
            self._nav_buttons[key] = button
            nav_layout.addWidget(button)
        nav_layout.addStretch(1)
        layout.addLayout(nav_layout, 1)

        badge = QLabel("Qt MVC runtime", self)
        badge.setObjectName("sidebarBadge")
        layout.addWidget(badge)

    def _build_pages(self, layout: QVBoxLayout) -> None:
        self._page_title = QLabel("Chat", self)
        self._page_title.setObjectName("pageTitle")
        layout.addWidget(self._page_title)

        self._stack = QStackedWidget(self)
        layout.addWidget(self._stack, 1)
        self._pages: dict[str, QWidget] = {}
        self._pages["chat"] = self._build_chat_page()
        self._pages["brain"] = self._build_brain_page()
        self._pages["settings"] = self._build_settings_page()
        self._pages["logs"] = self._build_logs_page()
        for page in self._pages.values():
            self._stack.addWidget(page)

    def _make_tree(self, columns: list[str], parent: QWidget | None = None) -> QTreeWidget:
        tree = QTreeWidget(parent or self)
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        tree.setSelectionMode(QTreeWidget.SingleSelection)
        tree.setHeaderLabels(columns)
        return tree

    def _build_chat_page(self) -> QWidget:
        page = QWidget(self)
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(UI_SPACING["m"])

        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(UI_SPACING["m"])
        header_copy = QVBoxLayout()
        header_copy.setContentsMargins(0, 0, 0, 0)
        header_copy.setSpacing(UI_SPACING["xs"])
        self._chat_context_summary = QLabel(page)
        self._chat_context_summary.setObjectName("chatContextSummary")
        self._chat_context_summary.setWordWrap(True)
        header_copy.addWidget(self._chat_context_summary)
        self._chat_context_hint = QLabel(
            "Choose a starter, then reopen conversation setup only when you need to change mode, source path, skill, or model.",
            page,
        )
        self._chat_context_hint.setObjectName("chatContextHint")
        self._chat_context_hint.setWordWrap(True)
        header_copy.addWidget(self._chat_context_hint)
        header.addLayout(header_copy, 1)
        self._conversation_setup_button = QPushButton("Conversation Setup", page)
        self._conversation_setup_button.setObjectName("conversationSetupButton")
        self._conversation_setup_button.clicked.connect(self._toggle_conversation_setup_popup)
        header.addWidget(self._conversation_setup_button)
        self.btn_new_chat = QPushButton("New Chat", page)
        self.btn_new_chat.clicked.connect(self.newChatRequested.emit)
        header.addWidget(self.btn_new_chat)
        root.addLayout(header)
        self._build_conversation_setup_popup()
        self._build_quick_model_popup()

        splitter = QSplitter(Qt.Horizontal, page)
        self._chat_splitter = splitter
        root.addWidget(splitter, 1)

        left = QWidget(splitter)
        left.setMinimumWidth(640)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(UI_SPACING["m"])

        self._conversation_shell = QFrame(left)
        self._conversation_shell.setObjectName("chatConversationCard")
        conversation_layout = QVBoxLayout(self._conversation_shell)
        conversation_layout.setContentsMargins(UI_SPACING["m"], UI_SPACING["m"], UI_SPACING["m"], UI_SPACING["m"])
        conversation_layout.setSpacing(UI_SPACING["s"])
        self._conversation_title = QLabel("Conversation", self._conversation_shell)
        self._conversation_title.setObjectName("chatSectionTitle")
        conversation_layout.addWidget(self._conversation_title)

        self._chat_state_stack = QStackedWidget(self._conversation_shell)
        self._chat_state_stack.setObjectName("chatStateStack")
        conversation_layout.addWidget(self._chat_state_stack, 1)

        self._chat_empty_state = QWidget(self._chat_state_stack)
        empty_layout = QVBoxLayout(self._chat_empty_state)
        empty_layout.setContentsMargins(UI_SPACING["xl"], UI_SPACING["xl"], UI_SPACING["xl"], UI_SPACING["xl"])
        self._chat_empty_inner = QWidget(self._chat_empty_state)
        self._chat_empty_inner.setMaximumWidth(760)
        self._chat_empty_inner.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        hero_layout = QVBoxLayout(self._chat_empty_inner)
        hero_layout.setContentsMargins(0, 0, 0, 0)
        hero_layout.setSpacing(UI_SPACING["m"])
        self._hero_greeting_label = QLabel("Start a conversation in plain language", self._chat_empty_inner)
        self._hero_greeting_label.setObjectName("heroGreeting")
        self._hero_greeting_label.setWordWrap(True)
        self._hero_greeting_label.setMaximumWidth(560)
        self._hero_copy_label = QLabel(
            "Choose the kind of help you want. Axiom will keep the advanced retrieval and model controls tucked away until you need them.",
            self._chat_empty_inner,
        )
        self._hero_copy_label.setObjectName("heroCopy")
        self._hero_copy_label.setWordWrap(True)
        self._hero_copy_label.setMaximumWidth(560)
        hero_layout.addWidget(self._hero_greeting_label)
        hero_layout.addWidget(self._hero_copy_label)
        preset_grid_host = QWidget(self._chat_empty_inner)
        preset_grid = QGridLayout(preset_grid_host)
        preset_grid.setContentsMargins(0, 0, 0, 0)
        preset_grid.setHorizontalSpacing(UI_SPACING["s"])
        preset_grid.setVerticalSpacing(UI_SPACING["s"])
        self._chat_preset_buttons: list[QPushButton] = []
        for index, preset in enumerate(_CHAT_PRESETS):
            button = QPushButton(
                f"{preset['title']}\n{preset['description']}",
                preset_grid_host,
            )
            button.setObjectName("chatPresetButton")
            button.setCursor(Qt.PointingHandCursor)
            button.setMinimumHeight(102)
            button.clicked.connect(
                lambda _checked=False, selected=dict(preset): self._apply_chat_preset(selected)
            )
            self._chat_preset_buttons.append(button)
            preset_grid.addWidget(button, index // 2, index % 2)
        hero_layout.addWidget(preset_grid_host)
        hero_row = QHBoxLayout()
        hero_row.setContentsMargins(0, 0, 0, 0)
        hero_row.setSpacing(0)
        hero_row.addStretch(1)
        hero_row.addWidget(self._chat_empty_inner)
        hero_row.addStretch(1)
        empty_layout.addStretch(1)
        empty_layout.addLayout(hero_row)
        empty_layout.addStretch(1)
        self._chat_state_stack.addWidget(self._chat_empty_state)

        self._chat_transcript_state = QWidget(self._chat_state_stack)
        transcript_layout = QVBoxLayout(self._chat_transcript_state)
        transcript_layout.setContentsMargins(0, 0, 0, 0)
        transcript_layout.setSpacing(0)
        self._chat_transcript = QPlainTextEdit(self._chat_transcript_state)
        self._chat_transcript.setObjectName("chatTranscript")
        self._chat_transcript.setReadOnly(True)
        self._chat_transcript_scrollbar = self._chat_transcript.verticalScrollBar()
        transcript_layout.addWidget(self._chat_transcript, 1)
        self._chat_state_stack.addWidget(self._chat_transcript_state)

        self._feedback_footer = QWidget(self._conversation_shell)
        self._feedback_footer.setObjectName("chatFeedbackBar")
        feedback_layout = QHBoxLayout(self._feedback_footer)
        feedback_layout.setContentsMargins(0, 0, 0, 0)
        feedback_layout.setSpacing(UI_SPACING["xs"])
        feedback_layout.addStretch(1)
        self.btn_feedback_up = QPushButton(self._feedback_footer)
        self.btn_feedback_up.setObjectName("chatFeedbackButton")
        self.btn_feedback_up.setCursor(Qt.PointingHandCursor)
        self.btn_feedback_up.setToolTip("Thumbs up")
        self.btn_feedback_up.setIcon(self._create_feedback_icon("#2ECC71", down=False))
        self.btn_feedback_up.setIconSize(QSize(20, 20))
        self.btn_feedback_up.setFixedSize(40, 40)
        self.btn_feedback_up.clicked.connect(lambda: self.feedbackRequested.emit(1))
        feedback_layout.addWidget(self.btn_feedback_up)
        self.btn_feedback_down = QPushButton(self._feedback_footer)
        self.btn_feedback_down.setObjectName("chatFeedbackButton")
        self.btn_feedback_down.setCursor(Qt.PointingHandCursor)
        self.btn_feedback_down.setToolTip("Thumbs down")
        self.btn_feedback_down.setIcon(self._create_feedback_icon("#E74C3C", down=True))
        self.btn_feedback_down.setIconSize(QSize(20, 20))
        self.btn_feedback_down.setFixedSize(40, 40)
        self.btn_feedback_down.clicked.connect(lambda: self.feedbackRequested.emit(-1))
        feedback_layout.addWidget(self.btn_feedback_down)
        conversation_layout.addWidget(self._feedback_footer, 0)

        left_layout.addWidget(self._conversation_shell, 1)

        self._composer_shell = QFrame(left)
        self._composer_shell.setObjectName("chatComposerCard")
        composer_layout = QVBoxLayout(self._composer_shell)
        composer_layout.setContentsMargins(UI_SPACING["m"], UI_SPACING["m"], UI_SPACING["m"], UI_SPACING["m"])
        composer_layout.setSpacing(UI_SPACING["s"])
        self._composer_title = QLabel("Ask Axiom", self._composer_shell)
        self._composer_title.setObjectName("chatSectionTitle")
        composer_layout.addWidget(self._composer_title)
        self._composer_meta = QLabel(self._composer_shell)
        self._composer_meta.setObjectName("chatContextHint")
        self._composer_meta.setWordWrap(True)
        composer_layout.addWidget(self._composer_meta)

        self.txt_input = QPlainTextEdit(self._composer_shell)
        self.txt_input.setObjectName("chatComposerInput")
        self.txt_input.setMinimumHeight(120)
        self.txt_input.setPlaceholderText("Type a question. Press Enter to send, Shift+Enter for a newline.")
        self.prompt_entry = self.txt_input
        self.prompt_entry.installEventFilter(self)
        self._prompt_scrollbar = self.txt_input.verticalScrollBar()
        composer_layout.addWidget(self.txt_input)
        action_row = QHBoxLayout()
        self._progress = QProgressBar(self._composer_shell)
        self._progress.setRange(0, 100)
        action_row.addWidget(self._progress, 1)
        self.btn_cancel_rag = QPushButton("Cancel", self._composer_shell)
        self.btn_cancel_rag.clicked.connect(self.cancelRequested.emit)
        self.btn_cancel_rag.setEnabled(False)
        action_row.addWidget(self.btn_cancel_rag)
        self.btn_send = QPushButton("Send", self._composer_shell)
        self.btn_send.clicked.connect(self.sendRequested.emit)
        action_row.addWidget(self.btn_send)
        composer_layout.addLayout(action_row)
        left_layout.addWidget(self._composer_shell, 0)
        splitter.addWidget(left)

        right = QTabWidget(splitter)
        self._evidence_tabs = right
        right.setObjectName("chatEvidenceTabs")
        right.setMinimumWidth(360)
        right.setDocumentMode(True)

        evidence_page = QWidget(right)
        evidence_layout = QVBoxLayout(evidence_page)
        evidence_layout.setContentsMargins(0, 0, 0, 0)
        evidence_layout.setSpacing(UI_SPACING["s"])
        evidence_layout.addWidget(QLabel("Sources", evidence_page))
        self._evidence_sources_tree = self._make_tree(["Source", "Score", "Snippet"], evidence_page)
        evidence_layout.addWidget(self._evidence_sources_tree, 1)
        evidence_layout.addWidget(QLabel("Grounding", evidence_page))
        self._grounding_browser = QTextBrowser(evidence_page)
        self._grounding_browser.anchorClicked.connect(lambda url: QDesktopServices.openUrl(url))
        evidence_layout.addWidget(self._grounding_browser, 1)

        process_page = QWidget(right)
        process_layout = QVBoxLayout(process_page)
        process_layout.setContentsMargins(0, 0, 0, 0)
        process_layout.setSpacing(UI_SPACING["s"])
        process_layout.addWidget(QLabel("Events", process_page))
        self._events_tree = self._make_tree(["Time", "Stage", "Event", "Summary"], process_page)
        process_layout.addWidget(self._events_tree, 1)
        process_layout.addWidget(QLabel("Trace", process_page))
        self._trace_tree = self._make_tree(["Time", "Stage", "Event", "Payload"], process_page)
        process_layout.addWidget(self._trace_tree, 1)

        structure_page = QWidget(right)
        structure_layout = QVBoxLayout(structure_page)
        structure_layout.setContentsMargins(0, 0, 0, 0)
        structure_layout.setSpacing(UI_SPACING["s"])
        structure_layout.addWidget(QLabel("Semantic Regions", structure_page))
        self._regions_tree = self._make_tree(["Document", "Region", "Summary"], structure_page)
        structure_layout.addWidget(self._regions_tree, 1)
        structure_layout.addWidget(QLabel("Outline", structure_page))
        self._outline_tree = self._make_tree(["Heading", "Meta"], structure_page)
        structure_layout.addWidget(self._outline_tree, 1)

        right.addTab(evidence_page, "Evidence")
        right.addTab(process_page, "Process")
        right.addTab(structure_page, "Structure")
        splitter.addWidget(right)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes(self._chat_splitter_sizes)
        splitter.splitterMoved.connect(self._remember_chat_splitter_sizes)

        self._refresh_chat_state()
        self.set_chat_response_ui(False, False)
        self._refresh_conversation_chrome()
        return page

    def _build_conversation_setup_popup(self) -> None:
        self._conversation_setup_popup = QFrame(self, Qt.Popup | Qt.FramelessWindowHint)
        self._conversation_setup_popup.setObjectName("conversationSetupPopup")
        self._conversation_setup_popup.setMinimumWidth(360)

        popup_layout = QVBoxLayout(self._conversation_setup_popup)
        popup_layout.setContentsMargins(UI_SPACING["m"], UI_SPACING["m"], UI_SPACING["m"], UI_SPACING["m"])
        popup_layout.setSpacing(UI_SPACING["s"])

        title = QLabel("Conversation Setup", self._conversation_setup_popup)
        title.setObjectName("quickModelPopupTitle")
        popup_layout.addWidget(title)

        hint = QLabel(
            "Session defaults live here. Use a starter card to begin quickly, then reopen this sheet only when you want to change the mode, source path, skill, or model.",
            self._conversation_setup_popup,
        )
        hint.setObjectName("quickModelPopupHint")
        hint.setWordWrap(True)
        popup_layout.addWidget(hint)

        popup_layout.addWidget(QLabel("Conversation mode", self._conversation_setup_popup))
        self._mode_combo = QComboBox(self._conversation_setup_popup)
        self._mode_combo.addItems(MODE_OPTIONS)
        self._mode_combo.currentTextChanged.connect(self._emit_mode_state)
        popup_layout.addWidget(self._mode_combo)

        popup_layout.addWidget(QLabel("Source path", self._conversation_setup_popup))
        self._rag_toggle = IOSSegmentedToggle(self._conversation_setup_popup, ["Use Sources", "Direct"], True, self._palette)
        self._rag_toggle.toggled.connect(self._on_toggle_changed)
        popup_layout.addWidget(self._rag_toggle)

        popup_layout.addWidget(QLabel("Primary skill", self._conversation_setup_popup))
        self._profile_combo = QComboBox(self._conversation_setup_popup)
        self._profile_combo.setMinimumWidth(220)
        self._profile_combo.currentTextChanged.connect(lambda *_args: self._update_skill_action_labels())
        popup_layout.addWidget(self._profile_combo)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(UI_SPACING["xs"])
        self.btn_profile_load = QPushButton("Toggle Skill", self._conversation_setup_popup)
        self.btn_profile_load.clicked.connect(self.toggleSkillRequested.emit)
        self.btn_profile_load.clicked.connect(self.loadProfileRequested.emit)
        actions.addWidget(self.btn_profile_load)
        self.btn_profile_save = QPushButton("Pin Skill", self._conversation_setup_popup)
        self.btn_profile_save.clicked.connect(self.pinSkillRequested.emit)
        self.btn_profile_save.clicked.connect(self.saveProfileRequested.emit)
        actions.addWidget(self.btn_profile_save)
        self.btn_profile_duplicate = QPushButton("Mute Skill", self._conversation_setup_popup)
        self.btn_profile_duplicate.clicked.connect(self.muteSkillRequested.emit)
        self.btn_profile_duplicate.clicked.connect(self.duplicateProfileRequested.emit)
        actions.addWidget(self.btn_profile_duplicate)
        popup_layout.addLayout(actions)

        popup_layout.addWidget(QLabel("Model", self._conversation_setup_popup))
        self._llm_status_badge = QToolButton(self._conversation_setup_popup)
        self._llm_status_badge.setObjectName("llmStatusBadge")
        self._llm_status_badge.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self._llm_status_badge.setText("")
        self._llm_status_badge.setCursor(Qt.PointingHandCursor)
        self._llm_status_badge.setFixedSize(46, 42)
        self._llm_status_badge.setIconSize(QSize(22, 22))
        self._llm_status_badge.setIcon(self._create_model_switch_icon())
        self._llm_status_badge.clicked.connect(self._toggle_quick_model_popup)
        popup_layout.addWidget(self._llm_status_badge, 0, Qt.AlignLeft)

    def _toggle_conversation_setup_popup(self) -> None:
        popup = getattr(self, "_conversation_setup_popup", None)
        if popup is None:
            return
        if popup.isVisible():
            self._hide_conversation_setup_popup()
            return
        self._show_conversation_setup_popup()

    def _show_conversation_setup_popup(self) -> None:
        popup = getattr(self, "_conversation_setup_popup", None)
        if popup is None:
            return
        self._refresh_conversation_chrome()
        popup.adjustSize()
        anchor = self._conversation_setup_button.mapToGlobal(QPoint(0, 0))
        popup.move(
            anchor
            + QPoint(
                max(0, self._conversation_setup_button.width() - popup.width()),
                self._conversation_setup_button.height() + UI_SPACING["xs"],
            )
        )
        popup.show()
        popup.raise_()
        popup.activateWindow()

    def _hide_conversation_setup_popup(self) -> None:
        popup = getattr(self, "_conversation_setup_popup", None)
        if popup is not None and popup.isVisible():
            popup.hide()

    def _apply_chat_preset(self, preset: dict[str, str]) -> None:
        self._mode_combo.setCurrentText(str(preset.get("mode", "Q&A") or "Q&A"))
        self._rag_toggle.set_value(str(preset.get("chat_path", "RAG")).strip().lower() != "direct")
        self._emit_mode_state()
        self.newChatRequested.emit()

    def _refresh_conversation_chrome(self) -> None:
        mode = self._mode_combo.currentText().strip() or "Q&A"
        chat_path = "Use sources" if self._rag_toggle.get_value() else "Direct"
        profile = self._profile_combo.currentText().strip() or "No skill selected"
        provider = str(self._settings_data.get("llm_provider", "") or "").strip() or "unset"
        model = str(
            self._settings_data.get("llm_model", "")
            or self._settings_data.get("llm_model_custom", "")
            or ""
        ).strip()
        model_summary = f"{provider}{(' / ' + model) if model else ''}"
        summary = f"{mode} · {chat_path} · {profile} · {model_summary}"
        self._chat_context_summary.setText(summary)
        self._composer_meta.setText(f"Current conversation: {summary}")

    def _build_brain_page(self) -> QWidget:
        page = QWidget(self)
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(UI_SPACING["m"])

        self._brain_panel = BrainPanel(page, palette=self._palette, animator=self._animator)
        self._brain_panel.openFilesRequested.connect(self.openFilesRequested.emit)
        self._brain_panel.buildIndexRequested.connect(self.buildIndexRequested.emit)
        self._brain_panel.newChatRequested.connect(self.newChatRequested.emit)
        self._brain_panel.loadIndexRequested.connect(self.loadIndexRequested.emit)
        self._brain_panel.historyOpenRequested.connect(self.historyOpenRequested.emit)
        self._brain_panel.historyDeleteRequested.connect(self.historyDeleteRequested.emit)
        self._brain_panel.historyRenameRequested.connect(self.historyRenameRequested.emit)
        self._brain_panel.historyDuplicateRequested.connect(self.historyDuplicateRequested.emit)
        self._brain_panel.historyExportRequested.connect(self.historyExportRequested.emit)
        self._brain_panel.historyRefreshRequested.connect(self.historyRefreshRequested.emit)
        self._brain_panel.historySearchRequested.connect(self.historySearchRequested.emit)
        self._brain_panel.historySelectionRequested.connect(self.historySelectionRequested.emit)
        self._brain_panel.historySkillFilterRequested.connect(self.historySkillFilterRequested.emit)
        self._brain_panel.historyProfileFilterRequested.connect(self.historyProfileFilterRequested.emit)
        self._brain_panel.brainNodeSelected.connect(self.brainNodeSelected.emit)
        self._brain_panel.brainNodeActivated.connect(self.brainNodeActivated.emit)
        self._brain_panel.brainRefreshRequested.connect(self.brainRefreshRequested.emit)

        self.btn_open_files = self._brain_panel.btn_open_files
        self.btn_build_index = self._brain_panel.btn_build_index
        self.btn_new_chat = self._brain_panel.btn_new_chat
        self.btn_history_new_chat = self._brain_panel.btn_new_chat
        self.btn_library_load_index = self._brain_panel.btn_library_load_index
        self.btn_history_refresh = self._brain_panel.btn_history_refresh
        self.btn_history_open = self._brain_panel.detail_panel.btn_open_session
        self.btn_history_delete = self._brain_panel.detail_panel.btn_delete_session
        self.btn_history_rename = self._brain_panel.detail_panel.btn_rename_session
        self.btn_history_duplicate = self._brain_panel.detail_panel.btn_duplicate_session
        self.btn_history_export = self._brain_panel.detail_panel.btn_export_session
        self._index_info_label = self._brain_panel._index_info_label
        self._available_index_combo = self._brain_panel._available_index_combo
        self._library_chunk_size = self._brain_panel._library_chunk_size
        self._library_chunk_overlap = self._brain_panel._library_chunk_overlap
        self._active_index_summary = self._brain_panel._active_index_summary_label
        self._file_list = self._brain_panel._file_list
        self._file_listbox = self._brain_panel._file_listbox
        self._history_search = self._brain_panel._history_search
        self._history_profile_filter = self._brain_panel._history_profile_filter

        root.addWidget(self._brain_panel, 1)
        return page

    def _build_settings_page(self) -> QWidget:
        page = QWidget(self)
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(UI_SPACING["m"])

        self._settings_scroll = QScrollArea(page)
        self._settings_scroll.setWidgetResizable(True)
        self._settings_scrollbar = self._settings_scroll.verticalScrollBar()
        holder = QWidget(self._settings_scroll)
        holder_layout = QVBoxLayout(holder)
        holder_layout.setContentsMargins(0, 0, 0, 0)
        holder_layout.setSpacing(UI_SPACING["m"])

        for title, rows in _SETTINGS_SPEC:
            section = CollapsibleFrame(holder, title, title in _SETTINGS_EXPANDED, self._animator)
            section_body = QWidget(section.content)
            form = QGridLayout(section_body)
            form.setContentsMargins(0, 0, 0, 0)
            form.setHorizontalSpacing(UI_SPACING["m"])
            form.setVerticalSpacing(UI_SPACING["s"])
            form.setColumnStretch(1, 1)
            row_index = 0
            for key, label, widget_type, options in rows:
                widget = self._build_settings_widget(widget_type, options, section_body)
                self._settings_widgets[key] = widget
                form.addWidget(QLabel(label, section_body), row_index, 0, Qt.AlignTop)
                form.addWidget(widget, row_index, 1)
                row_index += 1
            section.content_layout.addWidget(section_body)
            holder_layout.addWidget(section)

        local_models = CollapsibleFrame(holder, "Local Models", True, self._animator)
        local_body = QWidget(local_models.content)
        local_layout = QVBoxLayout(local_body)
        local_layout.setContentsMargins(0, 0, 0, 0)
        local_layout.setSpacing(UI_SPACING["s"])
        self._local_model_tree = self._make_tree(["Name", "Type", "Value", "State"], local_body)
        local_layout.addWidget(self._local_model_tree)
        button_row = QHBoxLayout()
        for attr, label, slot in (
            ("btn_add_local_gguf_model", "Add GGUF", self.addLocalGgufRequested.emit),
            ("btn_add_local_st_model", "Add Sentence Transformer", self.addLocalSentenceTransformerRequested.emit),
            ("btn_remove_local_model", "Remove", self.removeLocalModelRequested.emit),
        ):
            button = QPushButton(label, local_body)
            button.clicked.connect(slot)
            setattr(self, attr, button)
            button_row.addWidget(button)
        self.btn_activate_local_model_llm = QPushButton("Activate for LLM", local_body)
        self.btn_activate_local_model_llm.clicked.connect(lambda: self.activateLocalModelRequested.emit("llm"))
        button_row.addWidget(self.btn_activate_local_model_llm)
        self.btn_activate_local_model_embedding = QPushButton("Activate for Embedding", local_body)
        self.btn_activate_local_model_embedding.clicked.connect(lambda: self.activateLocalModelRequested.emit("embedding"))
        button_row.addWidget(self.btn_activate_local_model_embedding)
        self.btn_open_local_model_folder = QPushButton("Open Folder", local_body)
        self.btn_open_local_model_folder.clicked.connect(self.openLocalModelFolderRequested.emit)
        button_row.addWidget(self.btn_open_local_model_folder)
        local_layout.addLayout(button_row)
        install_row = QHBoxLayout()
        self.btn_install_local_gguf_dep = QPushButton("Install llama-cpp-python", local_body)
        self.btn_install_local_gguf_dep.clicked.connect(lambda: self.installLocalDependencyRequested.emit(["llama-cpp-python"]))
        install_row.addWidget(self.btn_install_local_gguf_dep)
        self.btn_install_local_st_dep = QPushButton("Install sentence-transformers", local_body)
        self.btn_install_local_st_dep.clicked.connect(lambda: self.installLocalDependencyRequested.emit(["sentence-transformers"]))
        install_row.addWidget(self.btn_install_local_st_dep)
        install_row.addStretch(1)
        local_layout.addLayout(install_row)
        self._local_model_dependency_label = QLabel("", local_body)
        self._local_model_dependency_label.setWordWrap(True)
        local_layout.addWidget(self._local_model_dependency_label)
        heretic_row = QHBoxLayout()
        self.btn_heretic_abliterate = QPushButton("Abliterate Model (Heretic)", local_body)
        self.btn_heretic_abliterate.setToolTip(
            "Use Heretic to remove safety alignment from a HuggingFace model, "
            "then convert the result to a local GGUF file."
        )
        self.btn_heretic_abliterate.clicked.connect(self.hereticAbliterateRequested.emit)
        heretic_row.addWidget(self.btn_heretic_abliterate)
        self.btn_install_heretic_dep = QPushButton("Install heretic-llm", local_body)
        self.btn_install_heretic_dep.clicked.connect(lambda: self.installLocalDependencyRequested.emit(["heretic-llm"]))
        heretic_row.addWidget(self.btn_install_heretic_dep)
        heretic_row.addStretch(1)
        local_layout.addLayout(heretic_row)
        local_models.content_layout.addWidget(local_body)
        holder_layout.addWidget(local_models)

        gguf_recommendations = CollapsibleFrame(holder, "Local GGUF Recommendations", True, self._animator)
        gguf_body = QWidget(gguf_recommendations.content)
        gguf_layout = QVBoxLayout(gguf_body)
        gguf_layout.setContentsMargins(0, 0, 0, 0)
        gguf_layout.setSpacing(UI_SPACING["s"])
        self._local_gguf_hardware_label = QLabel("", gguf_body)
        self._local_gguf_hardware_label.setWordWrap(True)
        gguf_layout.addWidget(self._local_gguf_hardware_label)
        self._local_gguf_advisory_label = QLabel("", gguf_body)
        self._local_gguf_advisory_label.setWordWrap(True)
        gguf_layout.addWidget(self._local_gguf_advisory_label)
        gguf_filters = QHBoxLayout()
        gguf_filters.addWidget(QLabel("Use case", gguf_body))
        self._local_gguf_use_case_combo = QComboBox(gguf_body)
        self._local_gguf_use_case_combo.addItems(["general", "chat", "reasoning", "coding"])
        self._local_gguf_use_case_combo.currentTextChanged.connect(
            self.refreshLocalGgufRecommendationsRequested.emit
        )
        gguf_filters.addWidget(self._local_gguf_use_case_combo)
        self.btn_refresh_local_gguf_recommendations = QPushButton("Refresh", gguf_body)
        self.btn_refresh_local_gguf_recommendations.clicked.connect(
            lambda: self.refreshLocalGgufRecommendationsRequested.emit(self._local_gguf_use_case_combo.currentText())
        )
        gguf_filters.addWidget(self.btn_refresh_local_gguf_recommendations)
        self.btn_edit_hardware_assumptions = QPushButton("Edit Hardware Assumptions", gguf_body)
        self.btn_edit_hardware_assumptions.clicked.connect(self.editHardwareAssumptionsRequested.emit)
        gguf_filters.addWidget(self.btn_edit_hardware_assumptions)
        gguf_filters.addStretch(1)
        gguf_layout.addLayout(gguf_filters)
        self._local_gguf_recommendation_tree = self._make_tree(
            ["Model", "Params", "Fit", "Quant", "Speed", "Context", "Source"],
            gguf_body,
        )
        self._local_gguf_recommendation_tree.itemSelectionChanged.connect(
            self._update_local_gguf_recommendation_details
        )
        gguf_layout.addWidget(self._local_gguf_recommendation_tree)
        gguf_button_row = QHBoxLayout()
        self.btn_import_local_gguf_recommendation = QPushButton("Import Selected", gguf_body)
        self.btn_import_local_gguf_recommendation.clicked.connect(
            self.importLocalGgufRecommendationRequested.emit
        )
        gguf_button_row.addWidget(self.btn_import_local_gguf_recommendation)
        self.btn_apply_local_gguf_recommendation = QPushButton("Apply as Local LLM", gguf_body)
        self.btn_apply_local_gguf_recommendation.clicked.connect(
            self.applyLocalGgufRecommendationRequested.emit
        )
        gguf_button_row.addWidget(self.btn_apply_local_gguf_recommendation)
        gguf_button_row.addStretch(1)
        gguf_layout.addLayout(gguf_button_row)
        self.btn_import_local_gguf_recommendation.setEnabled(False)
        self.btn_apply_local_gguf_recommendation.setEnabled(False)
        self._local_gguf_recommendation_notes = QLabel("", gguf_body)
        self._local_gguf_recommendation_notes.setWordWrap(True)
        gguf_layout.addWidget(self._local_gguf_recommendation_notes)
        gguf_recommendations.content_layout.addWidget(gguf_body)
        holder_layout.addWidget(gguf_recommendations)

        developer_tools = CollapsibleFrame(holder, "Advanced: Developer Tools", False, self._animator)
        developer_body = QWidget(developer_tools.content)
        developer_layout = QVBoxLayout(developer_body)
        developer_layout.setContentsMargins(0, 0, 0, 0)
        developer_layout.setSpacing(UI_SPACING["s"])
        developer_note = QLabel(
            "Developer-only controls stay out of the main workspace so the everyday surfaces remain calm.",
            developer_body,
        )
        developer_note.setWordWrap(True)
        developer_layout.addWidget(developer_note)
        self.btn_reset_test_mode = QPushButton("Reset Test Mode", developer_body)
        developer_layout.addWidget(self.btn_reset_test_mode, 0, Qt.AlignLeft)
        developer_tools.content_layout.addWidget(developer_body)
        holder_layout.addWidget(developer_tools)
        holder_layout.addStretch(1)

        self._settings_scroll.setWidget(holder)
        root.addWidget(self._settings_scroll, 1)

        footer = QHBoxLayout()
        footer.addStretch(1)
        self.btn_save_settings = QPushButton("Save Settings", page)
        self.btn_save_settings.clicked.connect(self.saveSettingsRequested.emit)
        footer.addWidget(self.btn_save_settings)
        root.addLayout(footer)
        return page

    def _build_logs_page(self) -> QWidget:
        page = QWidget(self)
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(UI_SPACING["m"])
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(UI_SPACING["s"])
        self._logs_search = QLineEdit(page)
        self._logs_search.setPlaceholderText("Filter the activity console")
        self._logs_search.textChanged.connect(self._render_logs_buffer)
        header.addWidget(self._logs_search, 1)
        self._logs_copy_button = QPushButton("Copy", page)
        self._logs_copy_button.clicked.connect(self._copy_logs)
        header.addWidget(self._logs_copy_button)
        self._logs_open_folder_button = QPushButton("Open Folder", page)
        self._logs_open_folder_button.clicked.connect(self._open_log_dir)
        header.addWidget(self._logs_open_folder_button)
        root.addLayout(header)
        self._logs_view = QPlainTextEdit(page)
        self._logs_view.setObjectName("logsView")
        self._logs_view.setReadOnly(True)
        self._logs_view_text = self._logs_view
        self._logs_view_scrollbar = self._logs_view.verticalScrollBar()
        root.addWidget(self._logs_view, 1)
        return page

    def _build_settings_widget(self, widget_type: str, options: list[str] | None, parent: QWidget) -> QWidget:
        if widget_type == "combobox":
            combo = QComboBox(parent)
            combo.addItems(list(options or []))
            return combo
        if widget_type == "checkbutton":
            return QCheckBox(parent)
        if widget_type == "text":
            edit = QTextEdit(parent)
            edit.setMinimumHeight(100)
            return edit
        if widget_type == "entry_password":
            edit = QLineEdit(parent)
            edit.setEchoMode(QLineEdit.Password)
            return edit
        if widget_type == "file_browse":
            host = QWidget(parent)
            row = QHBoxLayout(host)
            row.setContentsMargins(0, 0, 0, 0)
            edit = QLineEdit(host)
            browse = QPushButton("Browse...", host)
            browse.clicked.connect(lambda: edit.setText(QFileDialog.getOpenFileName(self, "Select file")[0] or edit.text()))
            row.addWidget(edit, 1)
            row.addWidget(browse)
            host._line_edit = edit  # type: ignore[attr-defined]
            return host
        return QLineEdit(parent)

    def apply_theme(self, theme_name: str) -> None:
        self._theme_name = theme_name
        self._palette = get_palette(theme_name)
        app = QApplication.instance()
        if app is not None:
            apply_theme_to_app(app, self._palette, self._fonts)
        for card in self._cards:
            card.configure_colors(
                bg=self._palette.get("surface", "#091522"),
                border_color=self._palette.get("border", "#17405F"),
                shadow_color=self._palette.get("workspace_shadow", "#010408"),
            )
        self._brand_mark.update_palette(self._palette)
        self._apply_brand_logo()
        self._rag_toggle.update_palette(self._palette)
        if hasattr(self, "_brain_panel"):
            self._brain_panel.update_palette(self._palette)
        self._apply_local_styles()
        self.refresh_llm_status_badge()

    def _apply_local_styles(self) -> None:
        nav_bg = self._palette.get("nav_hover_bg", "#0E2032")
        nav_active = self._palette.get("nav_active_bg", "#113B5C")
        text = self._palette.get("text", "#F2FAFF")
        muted = self._palette.get("muted_text", "#8AA5BE")
        border = self._palette.get("border", "#17405F")
        surface_alt = self._palette.get("surface_alt", "#13283D")
        supporting = self._palette.get("supporting_bg", surface_alt)
        surface = self._palette.get("surface", "#091522")
        self.setStyleSheet(
            f"""
            QLabel#brandTitle {{ font-size: 28px; font-weight: 700; }}
            QLabel#pageTitle {{ font-size: 32px; font-weight: 700; }}
            QLabel#heroGreeting {{ font-size: 34px; font-weight: 700; }}
            QLabel#heroCopy {{ color: {muted}; font-size: 14px; }}
            QLabel#chatContextSummary {{
                font-size: 18px;
                font-weight: 700;
                color: {text};
            }}
            QLabel#chatContextHint {{
                color: {muted};
                font-size: 13px;
            }}
            QLabel#brandLogo {{ background: transparent; border: none; }}
            QLabel#chatSectionTitle {{ color: {muted}; font-size: 13px; font-weight: 700; }}
            QLabel#sidebarBadge, QToolButton#llmStatusBadge {{
                background-color: {surface_alt};
                border: 1px solid {border};
                border-radius: 12px;
                padding: 6px 10px;
            }}
            QPushButton#conversationSetupButton {{
                background-color: {surface_alt};
                border: 1px solid {border};
                border-radius: 14px;
                padding: 10px 14px;
            }}
            QPushButton#conversationSetupButton:hover {{
                background-color: {nav_bg};
            }}
            QToolButton#llmStatusBadge:hover {{
                background-color: {nav_bg};
            }}
            QToolButton#llmStatusBadge::menu-indicator {{
                image: none;
                width: 0px;
            }}
            QFrame#conversationSetupPopup,
            QFrame#quickModelPopup {{
                background-color: {supporting};
                border: 1px solid {border};
                border-radius: 18px;
            }}
            QLabel#quickModelPopupTitle {{
                font-size: 13px;
                font-weight: 700;
                color: {text};
            }}
            QLabel#quickModelPopupHint {{
                color: {muted};
                font-size: 12px;
            }}
            _NavButton {{
                text-align: left;
                padding: 12px 14px;
                border-radius: 14px;
                color: {text};
            }}
            _NavButton:checked {{ background-color: {nav_active}; }}
            _NavButton:hover:!checked {{ background-color: {nav_bg}; }}
            QTextBrowser, QPlainTextEdit, QTextEdit, QTreeWidget, QListWidget {{
                border: 1px solid {border};
                border-radius: 16px;
            }}
            QFrame#chatConversationCard, QFrame#chatComposerCard {{
                background-color: {supporting};
                border: 1px solid {border};
                border-radius: 20px;
            }}
            QStackedWidget#chatStateStack {{
                background: transparent;
                border: none;
            }}
            QPlainTextEdit#chatTranscript {{
                background: transparent;
                border: none;
                padding: 0px;
            }}
            QPlainTextEdit#chatComposerInput {{
                border-radius: 16px;
            }}
            QPushButton#chatPresetButton {{
                text-align: left;
                padding: 16px 18px;
                border-radius: 18px;
                background-color: {surface_alt};
                border: 1px solid {border};
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton#chatPresetButton:hover {{
                background-color: {nav_bg};
                border-color: {self._palette.get("focus_ring", self._palette.get("primary", "#2EB7FF"))};
            }}
            QWidget#chatFeedbackBar {{
                background: transparent;
                border: none;
            }}
            QPushButton#chatFeedbackButton {{
                background-color: {surface_alt};
                border: 1px solid {border};
                border-radius: 14px;
                padding: 0px;
            }}
            QPushButton#chatFeedbackButton:hover {{
                background-color: {nav_bg};
            }}
            QPlainTextEdit#logsView {{
                background-color: {surface};
                padding: 12px;
            }}
            """
        )
        for key, button in self._nav_buttons.items():
            button.setChecked(key == self._active_view)
        self._brand_subtitle.setStyleSheet(f"color: {muted};")
        self._footer_label.setStyleSheet(f"color: {muted};")

    def _load_icon(self) -> None:
        self._brand_logo_pixmap = self._load_packaged_brand_pixmap()
        if not self._brand_logo_pixmap.isNull():
            self.setWindowIcon(QIcon(self._brand_logo_pixmap))

    def _load_packaged_brand_pixmap(self) -> QPixmap:
        return _load_packaged_pixmap(_BRAND_ASSET_PACKAGE, _BRAND_ASSET_NAME)

    def _apply_brand_logo(self) -> None:
        if not hasattr(self, "_brand_icon_stack"):
            return
        if self._brand_logo_pixmap.isNull():
            self._brand_icon_stack.setCurrentWidget(self._brand_mark_page)
            return
        scaled = self._brand_logo_pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self._brand_logo_label.setPixmap(scaled)
        self._brand_icon_stack.setCurrentWidget(self._brand_logo_page)

    @staticmethod
    def _create_model_switch_icon() -> QIcon:
        pixmap = QPixmap(28, 28)
        pixmap.fill(Qt.transparent)
        try:
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.Antialiasing, True)
            painter.translate(pixmap.width() / 2, pixmap.height() / 2)
            pen = QPen(QColor("#F2FAFF"))
            pen.setWidthF(2.0)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            petal = QRectF(-3.2, -11.2, 6.4, 11.0)
            for angle in range(0, 360, 60):
                painter.save()
                painter.rotate(float(angle))
                painter.drawEllipse(petal)
                painter.restore()
            painter.setBrush(QColor("#F2FAFF"))
            painter.setPen(Qt.NoPen)
            core = QPainterPath()
            core.moveTo(0.0, -3.8)
            core.lineTo(3.3, -1.9)
            core.lineTo(3.3, 1.9)
            core.lineTo(0.0, 3.8)
            core.lineTo(-3.3, 1.9)
            core.lineTo(-3.3, -1.9)
            core.closeSubpath()
            painter.drawPath(core)
            painter.end()
        except Exception:
            fallback = QPainter(pixmap)
            fallback.setRenderHint(QPainter.Antialiasing, True)
            fallback.setPen(QPen(QColor("#F2FAFF"), 2.0))
            fallback.drawEllipse(QRectF(4.0, 4.0, 20.0, 20.0))
            fallback.end()
        return QIcon(pixmap)

    def _build_quick_model_popup(self) -> None:
        self._quick_model_popup = QFrame(self, Qt.Popup | Qt.FramelessWindowHint)
        self._quick_model_popup.setObjectName("quickModelPopup")
        self._quick_model_popup.setMinimumWidth(320)

        popup_layout = QVBoxLayout(self._quick_model_popup)
        popup_layout.setContentsMargins(UI_SPACING["m"], UI_SPACING["m"], UI_SPACING["m"], UI_SPACING["m"])
        popup_layout.setSpacing(UI_SPACING["s"])

        title = QLabel("Switch model", self._quick_model_popup)
        title.setObjectName("quickModelPopupTitle")
        popup_layout.addWidget(title)

        hint = QLabel(
            "Preset choices apply immediately. Custom and local models use the inline apply action.",
            self._quick_model_popup,
        )
        hint.setObjectName("quickModelPopupHint")
        hint.setWordWrap(True)
        popup_layout.addWidget(hint)

        popup_layout.addWidget(QLabel("Provider", self._quick_model_popup))
        self._quick_model_provider_combo = QComboBox(self._quick_model_popup)
        self._quick_model_provider_combo.addItems(list_llm_providers())
        self._quick_model_provider_combo.currentTextChanged.connect(self._on_quick_model_provider_changed)
        popup_layout.addWidget(self._quick_model_provider_combo)

        popup_layout.addWidget(QLabel("Model", self._quick_model_popup))
        self._quick_model_model_combo = QComboBox(self._quick_model_popup)
        self._quick_model_model_combo.currentTextChanged.connect(self._on_quick_model_selection_changed)
        self._quick_model_model_combo.activated.connect(self._on_quick_model_activated)
        popup_layout.addWidget(self._quick_model_model_combo)

        self._quick_model_custom_row = QWidget(self._quick_model_popup)
        custom_row_layout = QHBoxLayout(self._quick_model_custom_row)
        custom_row_layout.setContentsMargins(0, 0, 0, 0)
        custom_row_layout.setSpacing(UI_SPACING["xs"])
        self._quick_model_custom_input = QLineEdit(self._quick_model_custom_row)
        self._quick_model_custom_input.setPlaceholderText("Enter a model id")
        self._quick_model_custom_input.returnPressed.connect(self._emit_quick_model_change_from_popup)
        custom_row_layout.addWidget(self._quick_model_custom_input, 1)
        self._quick_model_apply_button = QPushButton("Apply", self._quick_model_custom_row)
        self._quick_model_apply_button.clicked.connect(self._emit_quick_model_change_from_popup)
        custom_row_layout.addWidget(self._quick_model_apply_button)
        popup_layout.addWidget(self._quick_model_custom_row)

        self._sync_quick_model_popup_from_settings()

    def _toggle_quick_model_popup(self) -> None:
        popup = getattr(self, "_quick_model_popup", None)
        if popup is None or not self._llm_status_badge.isEnabled():
            return
        if popup.isVisible():
            self._hide_quick_model_popup()
            return
        self._show_quick_model_popup()

    def _show_quick_model_popup(self) -> None:
        popup = getattr(self, "_quick_model_popup", None)
        if popup is None:
            return
        self._sync_quick_model_popup_from_settings()
        popup.adjustSize()
        anchor = self._llm_status_badge.mapToGlobal(QPoint(0, 0))
        popup.move(
            anchor
            + QPoint(
                self._llm_status_badge.width() - popup.width(),
                self._llm_status_badge.height() + UI_SPACING["xs"],
            )
        )
        popup.show()
        popup.raise_()
        popup.activateWindow()

    def _hide_quick_model_popup(self) -> None:
        popup = getattr(self, "_quick_model_popup", None)
        if popup is not None and popup.isVisible():
            popup.hide()

    def _sync_quick_model_popup_from_settings(self) -> None:
        if not hasattr(self, "_quick_model_provider_combo"):
            return
        provider = str(self._settings_data.get("llm_provider", "anthropic") or "anthropic").strip() or "anthropic"
        model = str(self._settings_data.get("llm_model", "") or "").strip()
        custom_model = str(self._settings_data.get("llm_model_custom", "") or "").strip()
        self._quick_model_popup_syncing = True
        provider_blocker = QSignalBlocker(self._quick_model_provider_combo)
        self._quick_model_provider_combo.setCurrentText(provider)
        del provider_blocker
        self._populate_quick_model_presets(provider, model=model, custom_model=custom_model)
        self._quick_model_popup_syncing = False

    def _populate_quick_model_presets(self, provider: str, *, model: str, custom_model: str) -> None:
        presets = get_llm_model_presets(provider)
        effective_model = str(model or "").strip()
        effective_custom = str(custom_model or "").strip()
        if provider_requires_custom_model(provider):
            selected = "custom"
        elif effective_model in presets:
            selected = effective_model
        elif effective_custom or (effective_model and effective_model not in presets):
            selected = "custom"
        else:
            selected = presets[0] if presets else "custom"

        model_blocker = QSignalBlocker(self._quick_model_model_combo)
        self._quick_model_model_combo.clear()
        self._quick_model_model_combo.addItems(presets or ["custom"])
        self._quick_model_model_combo.setCurrentText(selected if selected in presets else (presets[0] if presets else "custom"))
        del model_blocker

        custom_blocker = QSignalBlocker(self._quick_model_custom_input)
        self._quick_model_custom_input.setText(effective_custom or effective_model)
        del custom_blocker
        self._on_quick_model_selection_changed(self._quick_model_model_combo.currentText())

    def _quick_model_uses_inline_apply(self) -> bool:
        return uses_custom_model_value(
            self._quick_model_provider_combo.currentText(),
            self._quick_model_model_combo.currentText(),
        )

    def _on_quick_model_provider_changed(self, provider: str) -> None:
        current_custom = self._quick_model_custom_input.text().strip()
        self._quick_model_popup_syncing = True
        self._populate_quick_model_presets(str(provider or "").strip(), model="", custom_model=current_custom)
        self._quick_model_popup_syncing = False

    def _on_quick_model_selection_changed(self, _value: str) -> None:
        show_inline = self._quick_model_uses_inline_apply()
        self._quick_model_custom_row.setVisible(show_inline)
        placeholder = "Enter a local model id" if provider_requires_custom_model(self._quick_model_provider_combo.currentText()) else "Enter a custom model id"
        self._quick_model_custom_input.setPlaceholderText(placeholder)

    def _on_quick_model_activated(self, _index: int) -> None:
        if self._quick_model_popup_syncing or self._quick_model_uses_inline_apply():
            return
        self._emit_quick_model_change_from_popup(close_popup=True)

    def _emit_quick_model_change_from_popup(self, *, close_popup: bool = True) -> None:
        uses_inline = self._quick_model_uses_inline_apply()
        custom_model = self._quick_model_custom_input.text().strip()
        selected_model = self._quick_model_model_combo.currentText().strip()
        payload = {
            "llm_provider": self._quick_model_provider_combo.currentText().strip(),
            "llm_model": custom_model if uses_inline else selected_model,
            "llm_model_custom": custom_model if uses_inline else "",
        }
        self.quickModelChangeRequested.emit(payload)
        if close_popup:
            self._hide_quick_model_popup()

    def _on_toggle_changed(self, value: bool) -> None:
        self._rag_toggle.set_value(value)
        self._emit_mode_state()

    def _emit_mode_state(self) -> None:
        payload = {
            "selected_mode": self._mode_combo.currentText().strip() or "Q&A",
            "chat_path": "RAG" if self._rag_toggle.get_value() else "Direct",
        }
        if callable(self._mode_state_callback):
            self._mode_state_callback(payload)
        self.modeStateChanged.emit(payload)
        self._refresh_conversation_chrome()

    def _refresh_chat_state(self) -> None:
        target = self._chat_transcript_state if self._chat_has_messages else self._chat_empty_state
        self._chat_state_stack.setCurrentWidget(target)

    def _remember_chat_splitter_sizes(self, *_args: Any) -> None:
        splitter = getattr(self, "_chat_splitter", None)
        if splitter is None:
            return
        sizes = list(splitter.sizes())
        if len(sizes) >= 2 and sizes[1] > 0:
            self._chat_splitter_sizes = sizes[:2]

    @staticmethod
    def _create_feedback_icon(color: str, *, down: bool) -> QIcon:
        pixmap = QPixmap(24, 24)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        if down:
            painter.translate(pixmap.width() / 2, pixmap.height() / 2)
            painter.rotate(180)
            painter.translate(-pixmap.width() / 2, -pixmap.height() / 2)
        fill = QColor(color)
        arm = QPainterPath()
        arm.addRoundedRect(QRectF(4.0, 9.5, 4.2, 8.2), 1.4, 1.4)
        hand = QPainterPath()
        hand.moveTo(8.2, 10.0)
        hand.lineTo(10.0, 8.6)
        hand.lineTo(10.8, 5.0)
        hand.cubicTo(11.0, 4.0, 11.6, 3.4, 12.6, 3.4)
        hand.lineTo(14.0, 3.4)
        hand.cubicTo(14.8, 3.4, 15.4, 4.1, 15.4, 5.0)
        hand.lineTo(15.4, 8.2)
        hand.lineTo(18.4, 8.2)
        hand.cubicTo(19.8, 8.2, 20.6, 9.1, 20.6, 10.5)
        hand.lineTo(20.6, 15.8)
        hand.cubicTo(20.6, 17.2, 19.8, 18.2, 18.4, 18.2)
        hand.lineTo(10.6, 18.2)
        hand.cubicTo(9.8, 18.2, 9.0, 17.9, 8.5, 17.3)
        hand.lineTo(8.2, 16.9)
        hand.closeSubpath()
        painter.setPen(Qt.NoPen)
        painter.fillPath(hand, fill)
        painter.fillPath(arm, fill)
        painter.end()
        return QIcon(pixmap)

    def set_chat_response_ui(self, has_completed_response: bool, feedback_pending: bool) -> None:
        self._chat_has_completed_response = bool(has_completed_response)
        self._chat_feedback_pending = bool(feedback_pending) and self._chat_has_completed_response
        self._feedback_footer.setVisible(self._chat_feedback_pending)
        if self._chat_has_completed_response:
            self._evidence_tabs.setVisible(True)
            sizes = list(self._chat_splitter_sizes)
            if len(sizes) < 2 or sizes[1] <= 0:
                sizes = [820, 360]
            self._chat_splitter.setSizes(sizes)
            return
        sizes = list(self._chat_splitter.sizes())
        if len(sizes) >= 2 and sizes[1] > 0:
            self._chat_splitter_sizes = sizes[:2]
        total = max(sum(sizes) or self.width() or _MIN_WINDOW_W, _MIN_WINDOW_W)
        self._evidence_tabs.setVisible(False)
        self._chat_splitter.setSizes([total, 0])

    def switch_view(self, key: str) -> None:
        self._active_view = key if key in self._pages else "chat"
        self._stack.setCurrentWidget(self._pages[self._active_view])
        self._page_title.setText(self._active_view.title())
        if self._active_view != "chat":
            self._hide_conversation_setup_popup()
            self._hide_quick_model_popup()
        self._apply_local_styles()

    def set_status(self, text: str) -> None:
        self._status_label.setText(str(text or ""))

    def set_index_info(self, text: str) -> None:
        if hasattr(self, "_brain_panel"):
            self._brain_panel.set_index_info(text)
            return
        self._index_info_label.setText(str(text or ""))

    def set_progress(self, current: int, total: int | None = None) -> None:
        if total is None:
            self._progress.setRange(0, 0)
            return
        self._progress.setRange(0, max(1, int(total)))
        self._progress.setValue(max(0, int(current)))

    def reset_progress(self) -> None:
        self._progress.setRange(0, 100)
        self._progress.setValue(0)

    def set_build_index_enabled(self, enabled: bool) -> None:
        self.btn_build_index.setEnabled(bool(enabled))

    def set_cancel_rag_enabled(self, enabled: bool) -> None:
        self.btn_cancel_rag.setEnabled(bool(enabled))

    def set_file_list(self, paths: list[str]) -> None:
        if hasattr(self, "_brain_panel"):
            self._brain_panel.set_file_list(paths)
            return
        self._file_list.clear()
        for path in paths:
            self._file_list.addItem(str(path))

    def get_prompt_text(self) -> str:
        return self.prompt_entry.toPlainText()

    def set_prompt_text(self, text: str) -> None:
        self.prompt_entry.setPlainText(str(text or ""))

    def clear_prompt(self) -> None:
        self.prompt_entry.clear()

    def append_chat(self, text: str, tag: str = "agent") -> None:
        _ = tag
        self._chat_has_messages = True
        self._refresh_chat_state()
        cursor = self._chat_transcript.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(str(text))
        self._chat_transcript.setTextCursor(cursor)
        self._chat_transcript.ensureCursorVisible()

    def clear_chat(self) -> None:
        self._chat_transcript.clear()
        self._chat_has_messages = False
        self._refresh_chat_state()
        self.set_chat_response_ui(False, False)

    def set_chat_transcript(self, messages: list[Any]) -> None:
        lines: list[str] = []
        for message in messages or []:
            role = str(getattr(message, "role", None) or getattr(message, "get", lambda *_args: "")("role") or "assistant").title()
            content = str(getattr(message, "content", None) or getattr(message, "get", lambda *_args: "")("content") or "")
            lines.append(f"{role}: {content}")
        self._chat_transcript.setPlainText("\n\n".join(lines))
        self._chat_has_messages = bool(lines)
        self._refresh_chat_state()
        if not lines:
            self.set_chat_response_ui(False, False)

    def append_log(self, line: str) -> None:
        text = str(line or "").rstrip("\n")
        self._log_buffer.append(text)
        self._render_logs_buffer()

    def _render_logs_buffer(self) -> None:
        if not hasattr(self, "_logs_view"):
            return
        query = self._logs_search.text().strip().casefold() if hasattr(self, "_logs_search") else ""
        rows = [row for row in self._log_buffer if not query or query in row.casefold()]
        self._logs_view.setPlainText("\n".join(rows))
        cursor = self._logs_view.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._logs_view.setTextCursor(cursor)
        self._logs_view.ensureCursorVisible()

    def _copy_logs(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._logs_view.toPlainText())

    def _open_log_dir(self) -> None:
        target = pathlib.Path(str(self._settings_data.get("log_dir", "logs") or "logs")).expanduser()
        if not target.is_absolute():
            target = pathlib.Path.cwd() / target
        target.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target)))

    def set_mode_state_callback(self, callback: Any) -> None:
        self._mode_state_callback = callback

    def get_chat_mode(self) -> str:
        return "rag" if self._rag_toggle.get_value() else "direct"

    def set_profile_options(self, labels: list[str], current: str) -> None:
        labels = list(labels or [])
        blocker = QSignalBlocker(self._profile_combo)
        self._profile_combo.clear()
        self._profile_combo.addItems(labels)
        self._profile_combo.setCurrentText(current if current in labels else (labels[0] if labels else ""))
        del blocker

        if hasattr(self, "_brain_panel"):
            self._brain_panel.set_profile_filter_options(labels)
            return

        selected = self._history_profile_filter.currentText()
        blocker = QSignalBlocker(self._history_profile_filter)
        self._history_profile_filter.clear()
        self._history_profile_filter.addItems(["All Skills", *labels])
        self._history_profile_filter.setCurrentText(selected if selected else "All Skills")
        del blocker
        self._update_skill_action_labels()
        self._refresh_conversation_chrome()

    def set_skill_options(self, labels: list[str], current: str) -> None:
        self.set_profile_options(labels, current)

    def set_skill_filter_options(self, labels: list[str], current: str = "") -> None:
        if hasattr(self, "_brain_panel"):
            setter = getattr(self._brain_panel, "set_skill_filter_options", None)
            if callable(setter):
                setter(labels, current)
                return
        self.set_profile_options(labels, current)

    def get_selected_profile_label(self) -> str:
        return self._profile_combo.currentText().strip()

    def get_selected_skill_id(self) -> str:
        return self.get_selected_profile_label()

    def select_profile_label(self, label: str) -> None:
        if label:
            self._profile_combo.setCurrentText(label)
        self._refresh_conversation_chrome()

    def select_skill_id(self, label: str) -> None:
        self.select_profile_label(label)

    def set_skill_rows(self, rows: list[dict[str, Any]]) -> None:
        self._skill_rows = list(rows or [])
        self._update_skill_action_labels()

    def set_session_skill_state(self, payload: dict[str, Any]) -> None:
        self._session_skill_state = dict(payload or {})
        self._update_skill_action_labels()

    def _update_skill_action_labels(self) -> None:
        selected = self.get_selected_profile_label()
        rows = {str(row.get("skill_id") or ""): dict(row) for row in getattr(self, "_skill_rows", []) or []}
        row = rows.get(selected, {})
        enabled = bool(row.get("enabled", False))
        pinned = bool(row.get("pinned", False))
        muted = bool(row.get("muted", False))
        self.btn_profile_load.setText("Disable Skill" if enabled else "Enable Skill")
        self.btn_profile_save.setText("Unpin Skill" if pinned else "Pin Skill")
        self.btn_profile_duplicate.setText("Unmute Skill" if muted else "Mute Skill")
        self._refresh_conversation_chrome()

    def refresh_llm_status_badge(self) -> None:
        provider = str(self._settings_data.get("llm_provider", "") or "").strip() or "unset"
        model = str(self._settings_data.get("llm_model", "") or self._settings_data.get("llm_model_custom", "") or "").strip()
        summary = f"{provider}{(' / ' + model) if model else ''}"
        tooltip = f"Switch model. Current: {summary}"
        self._llm_status_badge.setToolTip(tooltip)
        self._llm_status_badge.setStatusTip(tooltip)
        self._llm_status_badge.setAccessibleName(f"Models button. Current model: {summary}")
        self._llm_status_badge.setAccessibleDescription("Open the quick model switcher.")
        self._llm_status_badge.setProperty("llmSummary", summary)
        self._sync_quick_model_popup_from_settings()
        self._refresh_conversation_chrome()

    def set_model_switch_enabled(self, enabled: bool) -> None:
        self._llm_status_badge.setEnabled(bool(enabled))
        if not enabled:
            self._hide_quick_model_popup()

    def populate_settings(self, settings: dict[str, Any]) -> None:
        self._settings_data = dict(settings or {})
        for key, widget in self._settings_widgets.items():
            blocker = QSignalBlocker(widget)
            self._set_widget_value(widget, self._settings_data.get(key, ""))
            del blocker
        self._mode_combo.setCurrentText(str(self._settings_data.get("selected_mode", "Q&A") or "Q&A"))
        self._rag_toggle.set_value(str(self._settings_data.get("chat_path", "RAG")).strip().lower() != "direct")
        self._library_chunk_size.setValue(int(self._settings_data.get("chunk_size", 1000) or 1000))
        self._library_chunk_overlap.setValue(int(self._settings_data.get("chunk_overlap", 100) or 100))
        self.refresh_llm_status_badge()
        self._refresh_conversation_chrome()

    def collect_settings(self) -> dict[str, Any]:
        collected = dict(self._settings_data)
        for key, widget in self._settings_widgets.items():
            collected[key] = self._get_widget_value(widget)
        collected["selected_mode"] = self._mode_combo.currentText()
        collected["chat_path"] = "RAG" if self._rag_toggle.get_value() else "Direct"
        return collected

    def _set_widget_value(self, widget: QWidget, value: Any) -> None:
        text_value = "" if value is None else str(value)
        if isinstance(widget, QComboBox):
            widget.setCurrentText(text_value)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, QTextEdit):
            widget.setPlainText(text_value)
        elif isinstance(widget, QLineEdit):
            widget.setText(text_value)
        else:
            line_edit = getattr(widget, "_line_edit", None)
            if isinstance(line_edit, QLineEdit):
                line_edit.setText(text_value)

    def _get_widget_value(self, widget: QWidget) -> Any:
        if isinstance(widget, QComboBox):
            return widget.currentText()
        if isinstance(widget, QCheckBox):
            return widget.isChecked()
        if isinstance(widget, QTextEdit):
            return widget.toPlainText()
        if isinstance(widget, QLineEdit):
            return widget.text()
        line_edit = getattr(widget, "_line_edit", None)
        if isinstance(line_edit, QLineEdit):
            return line_edit.text()
        return ""

    def get_library_build_settings(self) -> dict[str, Any]:
        if hasattr(self, "_brain_panel"):
            return self._brain_panel.get_library_build_settings()
        return {"chunk_size": self._library_chunk_size.value(), "chunk_overlap": self._library_chunk_overlap.value()}

    def set_available_indexes(self, rows: list[dict[str, Any]], selected_path: str = "") -> None:
        self._available_index_rows = list(rows or [])
        if hasattr(self, "_brain_panel"):
            self._brain_panel.set_available_indexes(self._available_index_rows, selected_path)
            return
        blocker = QSignalBlocker(self._available_index_combo)
        self._available_index_combo.clear()
        for row in self._available_index_rows:
            self._available_index_combo.addItem(str(row.get("label", row.get("index_id", ""))), str(row.get("path", "")))
        if selected_path:
            index = self._available_index_combo.findData(str(selected_path))
            if index >= 0:
                self._available_index_combo.setCurrentIndex(index)
        del blocker

    def get_selected_available_index_path(self) -> str:
        if hasattr(self, "_brain_panel"):
            return self._brain_panel.get_selected_available_index_path()
        return str(self._available_index_combo.currentData() or "")

    def set_active_index_summary(self, summary: str, index_path: str = "") -> None:
        if hasattr(self, "_brain_panel"):
            self._brain_panel.set_active_index_summary(summary, index_path)
            return
        self._active_index_summary.setText(str(summary or ""))
        if index_path:
            index = self._available_index_combo.findData(str(index_path))
            if index >= 0:
                self._available_index_combo.setCurrentIndex(index)

    def set_local_model_rows(self, rows: list[dict[str, Any]], dependency_status: dict[str, Any] | None = None) -> None:
        self._local_model_tree.clear()
        for row in rows or []:
            state = []
            if row.get("active_llm"):
                state.append("LLM")
            if row.get("active_embedding"):
                state.append("Embedding")
            item = QTreeWidgetItem([
                str(row.get("name", "") or row.get("value", "")),
                str(row.get("model_type", "")),
                str(row.get("path", "") or row.get("value", "")),
                ", ".join(state) or "Inactive",
            ])
            item.setData(0, Qt.UserRole, str(row.get("entry_id", "")))
            self._local_model_tree.addTopLevelItem(item)
        if dependency_status:
            bits = [f"{name}={'yes' if ok else 'no'}" for name, ok in dependency_status.items()]
            self._local_model_dependency_label.setText("Dependencies: " + ", ".join(bits))
        else:
            self._local_model_dependency_label.setText("")

    def set_local_gguf_recommendations(self, payload: dict[str, Any]) -> None:
        rows = list(payload.get("rows") or [])
        hardware = dict(payload.get("hardware") or {})
        use_case = str(payload.get("use_case", "general") or "general")
        blocker = QSignalBlocker(self._local_gguf_use_case_combo)
        self._local_gguf_use_case_combo.setCurrentText(use_case)
        del blocker
        summary_bits = [
            f"RAM {float(hardware.get('available_ram_gb', 0.0) or 0.0):.1f}/{float(hardware.get('total_ram_gb', 0.0) or 0.0):.1f} GB free",
            f"CPU {int(hardware.get('total_cpu_cores', 0) or 0)} cores",
            f"backend={str(hardware.get('backend', 'cpu_x86') or 'cpu_x86')}",
        ]
        if hardware.get("has_gpu"):
            if hardware.get("unified_memory"):
                summary_bits.append(f"GPU {str(hardware.get('gpu_name') or 'Integrated')} (unified memory)")
            else:
                summary_bits.append(
                    f"GPU {str(hardware.get('gpu_name') or 'Detected')} ({float(hardware.get('gpu_vram_gb', 0.0) or 0.0):.1f} GB VRAM)"
                )
        else:
            summary_bits.append("GPU not detected")
        if hardware.get("override_enabled"):
            summary_bits.append("overrides active")
        self._local_gguf_hardware_label.setText("Hardware: " + " | ".join(summary_bits))
        advisory = "Recommendations are advisory only for this session." if payload.get("advisory_only") else ""
        self._local_gguf_advisory_label.setText(advisory)
        self._local_gguf_recommendation_tree.clear()
        for row in rows:
            item = QTreeWidgetItem(
                [
                    str(row.get("model_name", "")),
                    str(row.get("parameter_count", "")),
                    str(row.get("fit_level", "")),
                    str(row.get("best_quant", "")),
                    f"{float(row.get('estimated_tps', 0.0) or 0.0):.1f} tok/s",
                    str(row.get("recommended_context_length", "")),
                    str(row.get("source_provider", "") or row.get("provider", "")),
                ]
            )
            item.setData(0, Qt.UserRole, dict(row))
            self._local_gguf_recommendation_tree.addTopLevelItem(item)
        if self._local_gguf_recommendation_tree.topLevelItemCount() > 0:
            self._local_gguf_recommendation_tree.setCurrentItem(
                self._local_gguf_recommendation_tree.topLevelItem(0)
            )
        else:
            self._local_gguf_recommendation_notes.setText("No matching GGUF recommendations for the selected use case.")
            self._update_local_gguf_recommendation_actions()

    def _update_local_gguf_recommendation_details(self) -> None:
        payload = self.get_selected_local_gguf_recommendation()
        if not payload:
            self._local_gguf_recommendation_notes.setText("")
            self._update_local_gguf_recommendation_actions()
            return
        notes = list(payload.get("notes") or [])
        action_state = self._local_gguf_recommendation_action_state(payload)
        summary = (
            f"Fit {payload.get('fit_level', '')} via {payload.get('run_mode', '')}. "
            f"Needs {float(payload.get('memory_required_gb', 0.0) or 0.0):.1f} GB "
            f"from {float(payload.get('memory_available_gb', 0.0) or 0.0):.1f} GB budget."
        )
        detail_lines = [summary, *notes[:3]]
        if action_state["warning"]:
            detail_lines.append(str(action_state["warning"]))
        self._local_gguf_recommendation_notes.setText("\n".join(detail_lines))
        self._update_local_gguf_recommendation_actions()

    def get_selected_local_gguf_recommendation(self) -> dict[str, Any] | None:
        item = self._local_gguf_recommendation_tree.currentItem()
        if item is None:
            return None
        payload = item.data(0, Qt.UserRole)
        return dict(payload or {}) if isinstance(payload, dict) else None

    def _local_gguf_recommendation_action_state(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return {
                "can_import": False,
                "can_apply": False,
                "apply_label": "Apply as Local LLM",
                "warning": "",
            }
        fit_level = str(payload.get("fit_level") or "").strip().lower()
        has_source = bool(str(payload.get("source_repo") or payload.get("source_provider") or "").strip())
        warning = ""
        apply_label = "Apply as Local LLM"
        can_apply = has_source and fit_level != "too_tight"
        if fit_level == "marginal":
            apply_label = "Apply as Local LLM (Confirm)"
            warning = "Activation will ask for confirmation before switching to this model."
        elif fit_level == "too_tight":
            warning = "Activation is blocked for this recommendation. Import is still allowed."
        return {
            "can_import": has_source,
            "can_apply": can_apply,
            "apply_label": apply_label,
            "warning": warning,
        }

    def _update_local_gguf_recommendation_actions(self) -> None:
        state = self._local_gguf_recommendation_action_state(self.get_selected_local_gguf_recommendation())
        self.btn_import_local_gguf_recommendation.setEnabled(bool(state["can_import"]))
        self.btn_apply_local_gguf_recommendation.setEnabled(bool(state["can_apply"]))
        self.btn_apply_local_gguf_recommendation.setText(str(state["apply_label"]))

    @staticmethod
    def _format_byte_size(size_bytes: int) -> str:
        size = float(max(int(size_bytes or 0), 0))
        units = ["B", "KB", "MB", "GB", "TB"]
        unit = units[0]
        for unit in units:
            if size < 1024.0 or unit == units[-1]:
                break
            size /= 1024.0
        if unit == "B":
            return f"{int(size)} {unit}"
        return f"{size:.1f} {unit}"

    def pick_local_gguf_repo_file(
        self,
        candidates: list[dict[str, Any]],
        title: str = "Choose GGUF File",
        detail: str = "",
    ) -> str:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.resize(760, 420)
        root = QVBoxLayout(dialog)
        label = QLabel(detail or "Select the GGUF file to import.", dialog)
        label.setWordWrap(True)
        root.addWidget(label)
        tree = self._make_tree(["Filename", "Quant", "Size", "Hint"], dialog)
        root.addWidget(tree, 1)
        for row in candidates or []:
            item = QTreeWidgetItem(
                [
                    str(row.get("filename", "")),
                    str(row.get("quant", "") or ""),
                    self._format_byte_size(int(row.get("size_bytes", 0) or 0)),
                    str(row.get("hint", "") or ""),
                ]
            )
            item.setData(0, Qt.UserRole, str(row.get("filename", "") or ""))
            tree.addTopLevelItem(item)
        if tree.topLevelItemCount() > 0:
            tree.setCurrentItem(tree.topLevelItem(0))
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        root.addWidget(buttons)
        tree.itemDoubleClicked.connect(lambda *_args: dialog.accept())
        if dialog.exec() != QDialog.Accepted:
            return ""
        item = tree.currentItem()
        return str(item.data(0, Qt.UserRole) if item is not None else "")

    def prompt_heretic_abliteration(self) -> dict[str, Any] | None:
        """Show a dialog to collect HuggingFace model ID and heretic options.

        Returns a dict with ``hf_model_id`` and ``use_bnb_4bit``, or *None*
        if the user cancelled.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("Abliterate Model with Heretic")
        dialog.resize(520, 220)
        root = QVBoxLayout(dialog)

        root.addWidget(QLabel(
            "Enter a HuggingFace model ID to abliterate. The result will be "
            "converted to GGUF and registered as a local model.",
            dialog,
        ))

        form = QGridLayout()
        form.addWidget(QLabel("HuggingFace Model ID:", dialog), 0, 0)
        model_input = QLineEdit(dialog)
        model_input.setPlaceholderText("e.g. meta-llama/Llama-3.1-8B-Instruct")
        form.addWidget(model_input, 0, 1)

        bnb_checkbox = QCheckBox("Use 4-bit quantization (--bnb-4bit, reduces VRAM ~70%)", dialog)
        form.addWidget(bnb_checkbox, 1, 0, 1, 2)
        root.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        root.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return None
        hf_id = model_input.text().strip()
        if not hf_id:
            return None
        return {
            "hf_model_id": hf_id,
            "use_bnb_4bit": bnb_checkbox.isChecked(),
        }

    def show_hardware_override_editor(
        self,
        settings: dict[str, Any],
        detected_hardware: dict[str, Any],
    ) -> dict[str, Any] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Hardware Assumptions")
        dialog.resize(560, 360)
        root = QVBoxLayout(dialog)
        summary = QLabel(
            "Detected: "
            + str(detected_hardware.get("cpu_name", "CPU"))
            + " | "
            + str(detected_hardware.get("gpu_name", "No GPU"))
            + " | "
            + f"RAM {float(detected_hardware.get('available_ram_gb', 0.0) or 0.0):.1f}/{float(detected_hardware.get('total_ram_gb', 0.0) or 0.0):.1f} GB",
            dialog,
        )
        summary.setWordWrap(True)
        root.addWidget(summary)
        grid = QGridLayout()
        root.addLayout(grid)
        enabled = QCheckBox("Enable manual overrides", dialog)
        enabled.setChecked(bool(settings.get("hardware_override_enabled", False)))
        grid.addWidget(enabled, 0, 0, 1, 2)
        total_ram = QLineEdit(str(settings.get("hardware_override_total_ram_gb", 0) or 0), dialog)
        available_ram = QLineEdit(str(settings.get("hardware_override_available_ram_gb", 0) or 0), dialog)
        gpu_name = QLineEdit(str(settings.get("hardware_override_gpu_name", "") or ""), dialog)
        gpu_vram = QLineEdit(str(settings.get("hardware_override_gpu_vram_gb", 0) or 0), dialog)
        gpu_count = QLineEdit(str(settings.get("hardware_override_gpu_count", 0) or 0), dialog)
        backend = QComboBox(dialog)
        backend.addItems(["", "cpu_x86", "cpu_arm", "cuda", "metal", "rocm", "vulkan", "sycl", "ascend"])
        backend.setCurrentText(str(settings.get("hardware_override_backend", "") or ""))
        unified = QCheckBox("Unified memory", dialog)
        unified.setChecked(bool(settings.get("hardware_override_unified_memory", False)))
        for row, (label, widget) in enumerate(
            (
                ("Total RAM (GB)", total_ram),
                ("Available RAM (GB)", available_ram),
                ("GPU Name", gpu_name),
                ("GPU VRAM (GB)", gpu_vram),
                ("GPU Count", gpu_count),
                ("Backend", backend),
            ),
            start=1,
        ):
            grid.addWidget(QLabel(label, dialog), row, 0)
            grid.addWidget(widget, row, 1)
        grid.addWidget(unified, 7, 0, 1, 2)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        root.addWidget(buttons)
        if dialog.exec() != QDialog.Accepted:
            return None
        return {
            "hardware_override_enabled": enabled.isChecked(),
            "hardware_override_total_ram_gb": total_ram.text().strip(),
            "hardware_override_available_ram_gb": available_ram.text().strip(),
            "hardware_override_gpu_name": gpu_name.text().strip(),
            "hardware_override_gpu_vram_gb": gpu_vram.text().strip(),
            "hardware_override_gpu_count": gpu_count.text().strip(),
            "hardware_override_backend": backend.currentText().strip(),
            "hardware_override_unified_memory": unified.isChecked(),
        }

    def get_selected_local_model_id(self) -> str:
        item = self._local_model_tree.currentItem()
        return str(item.data(0, Qt.UserRole) if item is not None else "")

    def set_history_rows(self, rows: list[Any]) -> None:
        self._history_rows = list(rows or [])
        if hasattr(self, "_brain_panel"):
            self._brain_panel.set_history_rows(self._history_rows)
            return
        self._history_tree.clear()
        for row in self._history_rows:
            item = QTreeWidgetItem([
                str(getattr(row, "title", "")),
                str(getattr(row, "updated_at", "")),
                str(getattr(row, "mode", "")),
                str(getattr(row, "primary_skill_id", "") or ", ".join(getattr(row, "skill_ids", []) or [])),
            ])
            item.setData(0, Qt.UserRole, str(getattr(row, "session_id", "")))
            self._history_tree.addTopLevelItem(item)

    def get_selected_history_session_id(self) -> str:
        if hasattr(self, "_brain_panel"):
            return self._brain_panel.get_selected_history_session_id()
        item = self._history_tree.currentItem()
        return str(item.data(0, Qt.UserRole) if item is not None else "")

    def select_history_session(self, session_id: str) -> None:
        if hasattr(self, "_brain_panel"):
            self._brain_panel.select_history_session(session_id)
            return
        for row in range(self._history_tree.topLevelItemCount()):
            item = self._history_tree.topLevelItem(row)
            if str(item.data(0, Qt.UserRole) or "") == str(session_id):
                self._history_tree.setCurrentItem(item)
                break

    def get_history_search_query(self) -> str:
        if hasattr(self, "_brain_panel"):
            return self._brain_panel.get_history_search_query()
        return self._history_search.text().strip()

    def get_history_profile_filter(self) -> str:
        if hasattr(self, "_brain_panel"):
            return self._brain_panel.get_history_profile_filter()
        value = self._history_profile_filter.currentText().strip()
        return "" if value == "All Skills" else value

    def get_history_skill_filter(self) -> str:
        if hasattr(self, "_brain_panel"):
            getter = getattr(self._brain_panel, "get_history_skill_filter", None)
            if callable(getter):
                return str(getter() or "")
        return self.get_history_profile_filter()

    def bind_history_search(self, callback: Any) -> None:
        if hasattr(self, "_brain_panel"):
            self._brain_panel.bind_history_search(callback)
            return
        self._history_search.textChanged.connect(lambda *_args: callback())

    def bind_history_selection(self, callback: Any) -> None:
        if hasattr(self, "_brain_panel"):
            self._brain_panel.bind_history_selection(callback)
            return
        self._history_tree.itemSelectionChanged.connect(lambda: callback())

    def bind_history_profile_filter(self, callback: Any) -> None:
        if hasattr(self, "_brain_panel"):
            self._brain_panel.bind_history_profile_filter(callback)
            return
        self._history_profile_filter.currentTextChanged.connect(lambda *_args: callback())

    def bind_history_skill_filter(self, callback: Any) -> None:
        if hasattr(self, "_brain_panel"):
            binder = getattr(self._brain_panel, "bind_history_skill_filter", None)
            if callable(binder):
                binder(callback)
                return
        self.bind_history_profile_filter(callback)

    def set_history_detail(self, detail: Any) -> None:
        if hasattr(self, "_brain_panel"):
            self._brain_panel.set_history_detail(detail)
            return
        if detail is None:
            self._history_detail_browser.clear()
            return
        summary = getattr(detail, "summary", detail)
        lines = [
            f"Title: {getattr(summary, 'title', '')}",
            f"Primary Skill: {getattr(summary, 'primary_skill_id', '') or getattr(summary, 'active_profile', '')}",
            f"Skills: {', '.join(getattr(summary, 'skill_ids', []) or [])}",
            f"Mode: {getattr(summary, 'mode', '')}",
            f"Provider: {getattr(summary, 'llm_provider', '')}",
            "",
            "Messages:",
        ]
        for message in getattr(detail, "messages", []) or []:
            lines.append(f"- {getattr(message, 'role', '').title()}: {getattr(message, 'content', '')}")
        feedback = list(getattr(detail, "feedback", []) or [])
        if feedback:
            lines.extend(["", "Feedback:"])
            for item in feedback:
                lines.append(f"- vote={getattr(item, 'vote', 0)} note={getattr(item, 'note', '')}")
        self._history_detail_browser.setPlainText("\n".join(lines))

    def set_brain_graph(self, graph: Any, selected_node_id: str = "") -> None:
        if hasattr(self, "_brain_panel"):
            self._brain_panel.set_graph(graph, selected_node_id=selected_node_id)

    def select_brain_node(self, node_id: str, *, emit_signal: bool = False) -> None:
        if hasattr(self, "_brain_panel"):
            self._brain_panel.select_brain_node(node_id, emit_signal=emit_signal)

    def get_selected_brain_node_id(self) -> str:
        if hasattr(self, "_brain_panel"):
            return self._brain_panel.get_selected_brain_node_id()
        return ""

    def _populate_tree_from_rows(self, tree: QTreeWidget, rows: list[Any], columns: list[str]) -> None:
        tree.clear()
        for row in rows or []:
            values = [str(row.get(column, "")) for column in columns]
            item = QTreeWidgetItem(values)
            item.setData(0, Qt.UserRole, row)
            tree.addTopLevelItem(item)

    def render_evidence_sources(self, sources: list[EvidenceSource | dict[str, Any]]) -> None:
        self._evidence_sources_tree.clear()
        for raw in sources or []:
            source = raw if isinstance(raw, EvidenceSource) else EvidenceSource.from_dict(raw)
            score = f"{source.score:.3f}" if source.score is not None else ""
            item = QTreeWidgetItem([source.label or source.source, score, source.excerpt or source.snippet])
            item.setData(0, Qt.UserRole, source.to_dict())
            self._evidence_sources_tree.addTopLevelItem(item)

    def render_events(self, rows: list[dict[str, Any]]) -> None:
        normalized = [{"timestamp": row.get("timestamp") or row.get("ts") or row.get("time") or "", "stage": row.get("stage") or "", "event_type": row.get("event_type") or row.get("type") or "", "summary": json.dumps(row, ensure_ascii=False)[:240]} for row in rows or []]
        self._populate_tree_from_rows(self._events_tree, normalized, ["timestamp", "stage", "event_type", "summary"])

    def render_semantic_regions(self, rows: list[dict[str, Any]]) -> None:
        normalized = [{"document": row.get("document") or row.get("source") or "", "region": row.get("region") or row.get("header_path") or row.get("label") or "", "summary": row.get("summary") or row.get("snippet") or json.dumps(row, ensure_ascii=False)[:240]} for row in rows or []]
        self._populate_tree_from_rows(self._regions_tree, normalized, ["document", "region", "summary"])

    def render_document_outline(self, rows: list[dict[str, Any]], grounding_html_path: str) -> None:
        normalized = [{"heading": row.get("heading") or row.get("title") or row.get("label") or "", "meta": row.get("path") or row.get("summary") or json.dumps(row, ensure_ascii=False)[:200]} for row in rows or []]
        self._populate_tree_from_rows(self._outline_tree, normalized, ["heading", "meta"])
        if grounding_html_path:
            self.render_grounding_info(grounding_html_path)

    def render_trace_events(self, rows: list[dict[str, Any]]) -> None:
        normalized = [{"timestamp": row.get("timestamp") or "", "stage": row.get("stage") or "", "event_type": row.get("event_type") or "", "payload": json.dumps(row.get("payload") or row, ensure_ascii=False)[:240]} for row in rows or []]
        self._populate_tree_from_rows(self._trace_tree, normalized, ["timestamp", "stage", "event_type", "payload"])

    def render_grounding_info(self, text: str) -> None:
        value = str(text or "").strip()
        if value.endswith(".html") and pathlib.Path(value).exists():
            url = QUrl.fromLocalFile(value).toString()
            self._grounding_browser.setHtml(f'<p><a href="{url}">{value}</a></p>')
            return
        self._grounding_browser.setPlainText(value)

    def show_setup_wizard(self, initial_state: dict[str, Any], index_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Axiom Guided Setup")
        dialog.resize(860, 680)
        root = QVBoxLayout(dialog)

        tabs = QTabWidget(dialog)
        root.addWidget(tabs, 1)

        source_tab = QWidget(dialog)
        model_tab = QWidget(dialog)
        finish_tab = QWidget(dialog)
        ingest_tab = source_tab
        provider_tab = model_tab
        keys_tab = model_tab
        confirm_tab = finish_tab
        tabs.addTab(source_tab, "Source")
        tabs.addTab(model_tab, "Models")
        tabs.addTab(finish_tab, "Finish")

        for widget in (source_tab, model_tab, finish_tab):
            widget.setLayout(QGridLayout(widget))
            widget.layout().setContentsMargins(UI_SPACING["m"], UI_SPACING["m"], UI_SPACING["m"], UI_SPACING["m"])
            widget.layout().setHorizontalSpacing(UI_SPACING["m"])
            widget.layout().setVerticalSpacing(UI_SPACING["s"])

        index_map = {str(row.get("label", row.get("index_id", ""))): str(row.get("path", "")) for row in index_rows or []}

        file_edit = QLineEdit(str(initial_state.get("file_path", "") or ""), dialog)
        index_combo = QComboBox(dialog)
        index_combo.addItem("", "")
        for label, path in index_map.items():
            index_combo.addItem(label, path)
        if initial_state.get("selected_index_path"):
            idx = index_combo.findData(str(initial_state.get("selected_index_path")))
            if idx >= 0:
                index_combo.setCurrentIndex(idx)
        browse = QPushButton("Browse...", dialog)
        browse.clicked.connect(lambda: file_edit.setText(QFileDialog.getOpenFileName(dialog, "Select source file")[0] or file_edit.text()))
        source_tab.layout().addWidget(QLabel("New source file", dialog), 0, 0)
        source_tab.layout().addWidget(file_edit, 0, 1)
        source_tab.layout().addWidget(browse, 0, 2)
        source_tab.layout().addWidget(QLabel("Or restore existing index", dialog), 1, 0)
        source_tab.layout().addWidget(index_combo, 1, 1, 1, 2)
        source_tab.layout().addWidget(QLabel("Ingestion defaults", dialog), 2, 0, 1, 2)

        recommendation_label = QLabel("", dialog)
        recommendation_label.setWordWrap(True)
        apply_rec = QPushButton("Apply Recommendation", dialog)
        chunk_size = QSpinBox(dialog)
        chunk_size.setRange(1, 500000)
        chunk_size.setValue(int(initial_state.get("chunk_size", 1000) or 1000))
        chunk_overlap = QSpinBox(dialog)
        chunk_overlap.setRange(0, 100000)
        chunk_overlap.setValue(int(initial_state.get("chunk_overlap", 100) or 100))
        build_digest = QCheckBox("Build digest index", dialog)
        build_digest.setChecked(bool(initial_state.get("build_digest_index", True)))
        build_comprehension = QCheckBox("Build comprehension index", dialog)
        build_comprehension.setChecked(bool(initial_state.get("build_comprehension_index", False)))
        comprehension_depth = QComboBox(dialog)
        comprehension_depth.addItems(["Standard", "Deep", "Exhaustive"])
        comprehension_depth.setCurrentText(str(initial_state.get("comprehension_extraction_depth", "Standard") or "Standard"))
        prefer_comprehension = QCheckBox("Prefer comprehension index", dialog)
        prefer_comprehension.setChecked(bool(initial_state.get("prefer_comprehension_index", True)))
        deepread_mode = QCheckBox("Enable DeepRead", dialog)
        deepread_mode.setChecked(bool(initial_state.get("deepread_mode", False)))
        use_reranker = QCheckBox("Use reranker", dialog)
        use_reranker.setChecked(bool(initial_state.get("use_reranker", False)))
        ingest_tab.layout().addWidget(recommendation_label, 3, 0, 1, 2)
        ingest_tab.layout().addWidget(apply_rec, 3, 2)
        ingest_tab.layout().addWidget(QLabel("Chunk size", dialog), 4, 0)
        ingest_tab.layout().addWidget(chunk_size, 4, 1)
        ingest_tab.layout().addWidget(QLabel("Chunk overlap", dialog), 5, 0)
        ingest_tab.layout().addWidget(chunk_overlap, 5, 1)
        ingest_tab.layout().addWidget(build_digest, 6, 0, 1, 2)
        ingest_tab.layout().addWidget(build_comprehension, 7, 0, 1, 2)
        ingest_tab.layout().addWidget(QLabel("Comprehension depth", dialog), 8, 0)
        ingest_tab.layout().addWidget(comprehension_depth, 8, 1)
        ingest_tab.layout().addWidget(prefer_comprehension, 9, 0, 1, 2)
        ingest_tab.layout().addWidget(deepread_mode, 10, 0, 1, 2)
        ingest_tab.layout().addWidget(use_reranker, 11, 0, 1, 2)

        llm_provider = QComboBox(dialog)
        llm_provider.addItems(["anthropic", "openai", "google", "xai", "local_lm_studio", "local_gguf", "mock"])
        llm_provider.setCurrentText(str(initial_state.get("llm_provider", "anthropic") or "anthropic"))
        llm_model = QLineEdit(str(initial_state.get("llm_model", "") or ""), dialog)
        embedding_provider = QComboBox(dialog)
        embedding_provider.addItems(["voyage", "openai", "google", "local_huggingface", "local_sentence_transformers", "mock"])
        embedding_provider.setCurrentText(str(initial_state.get("embedding_provider", "voyage") or "voyage"))
        embedding_model = QLineEdit(str(initial_state.get("embedding_model", "") or ""), dialog)
        retrieval_k = QSpinBox(dialog)
        retrieval_k.setRange(1, 10000)
        retrieval_k.setValue(int(initial_state.get("retrieval_k", 25) or 25))
        top_k = QSpinBox(dialog)
        top_k.setRange(1, 10000)
        top_k.setValue(int(initial_state.get("top_k", 5) or 5))
        mmr_lambda = QLineEdit(str(initial_state.get("mmr_lambda", 0.5) or 0.5), dialog)
        retrieval_mode = QComboBox(dialog)
        retrieval_mode.addItems(["flat", "hierarchical"])
        retrieval_mode.setCurrentText(str(initial_state.get("retrieval_mode", "flat") or "flat"))
        agentic_mode = QCheckBox("Agentic retrieval", dialog)
        agentic_mode.setChecked(bool(initial_state.get("agentic_mode", False)))
        agentic_iterations = QSpinBox(dialog)
        agentic_iterations.setRange(1, 10)
        agentic_iterations.setValue(int(initial_state.get("agentic_max_iterations", 2) or 2))
        output_style = QComboBox(dialog)
        output_style.addItems(["Default answer", "Detailed answer", "Brief / exec summary", "Script / talk track", "Structured report", "Blinkist-style summary"])
        output_style.setCurrentText(str(initial_state.get("output_style", "Default answer") or "Default answer"))
        mode_preset = QComboBox(dialog)
        mode_preset.addItems(["Q&A", "Book summary", "Tutor", "Research", "Evidence Pack"])
        mode_preset.setCurrentText(str(initial_state.get("mode_preset", "Q&A") or "Q&A"))
        vector_backend = QComboBox(dialog)
        vector_backend.addItems(["json", "chroma", "weaviate"])
        vector_backend.setCurrentText(str(initial_state.get("vector_db_type", "json") or "json"))

        provider_rows = [
            ("LLM provider", llm_provider),
            ("LLM model", llm_model),
            ("Embedding provider", embedding_provider),
            ("Embedding model", embedding_model),
            ("Retrieval K", retrieval_k),
            ("Final K", top_k),
            ("MMR lambda", mmr_lambda),
            ("Retrieval mode", retrieval_mode),
            ("Agentic iterations", agentic_iterations),
            ("Output style", output_style),
            ("Mode preset", mode_preset),
            ("Vector backend", vector_backend),
        ]
        for row, (label, widget) in enumerate(provider_rows):
            provider_tab.layout().addWidget(QLabel(label, dialog), row, 0)
            provider_tab.layout().addWidget(widget, row, 1)
        provider_tab.layout().addWidget(agentic_mode, 7, 2)

        local_gguf_state = {
            "local_gguf_models_dir": str(initial_state.get("local_gguf_models_dir", "") or ""),
            "hardware_override_enabled": bool(initial_state.get("hardware_override_enabled", False)),
            "hardware_override_total_ram_gb": initial_state.get("hardware_override_total_ram_gb", 0),
            "hardware_override_available_ram_gb": initial_state.get("hardware_override_available_ram_gb", 0),
            "hardware_override_gpu_name": str(initial_state.get("hardware_override_gpu_name", "") or ""),
            "hardware_override_gpu_vram_gb": initial_state.get("hardware_override_gpu_vram_gb", 0),
            "hardware_override_gpu_count": initial_state.get("hardware_override_gpu_count", 0),
            "hardware_override_backend": str(initial_state.get("hardware_override_backend", "") or ""),
            "hardware_override_unified_memory": bool(initial_state.get("hardware_override_unified_memory", False)),
        }
        local_gguf_hardware_label = QLabel("", dialog)
        local_gguf_hardware_label.setWordWrap(True)
        local_gguf_advisory_label = QLabel("", dialog)
        local_gguf_advisory_label.setWordWrap(True)
        local_gguf_tree = self._make_tree(
            ["Model", "Params", "Fit", "Quant", "Speed", "Context", "Source"],
            dialog,
        )
        local_gguf_notes = QLabel("", dialog)
        local_gguf_notes.setWordWrap(True)
        refresh_local_gguf = QPushButton("Refresh GGUF Picks", dialog)
        edit_local_hardware = QPushButton("Edit Hardware Assumptions", dialog)
        import_local_gguf = QCheckBox("Import selected GGUF on finish", dialog)
        use_selected_local_gguf = QPushButton("Use Selected Recommendation", dialog)
        import_local_gguf.setEnabled(False)
        use_selected_local_gguf.setEnabled(False)
        provider_tab.layout().addWidget(QLabel("Local GGUF recommendations", dialog), 12, 0)
        provider_tab.layout().addWidget(local_gguf_hardware_label, 13, 0, 1, 3)
        provider_tab.layout().addWidget(local_gguf_advisory_label, 14, 0, 1, 3)
        provider_tab.layout().addWidget(refresh_local_gguf, 15, 0)
        provider_tab.layout().addWidget(edit_local_hardware, 15, 1)
        provider_tab.layout().addWidget(import_local_gguf, 15, 2)
        provider_tab.layout().addWidget(local_gguf_tree, 16, 0, 1, 3)
        provider_tab.layout().addWidget(use_selected_local_gguf, 17, 0)
        provider_tab.layout().addWidget(local_gguf_notes, 18, 0, 1, 3)

        openai_key = QLineEdit(str(initial_state.get("api_key_openai", "") or ""), dialog)
        anthropic_key = QLineEdit(str(initial_state.get("api_key_anthropic", "") or ""), dialog)
        google_key = QLineEdit(str(initial_state.get("api_key_google", "") or ""), dialog)
        xai_key = QLineEdit(str(initial_state.get("api_key_xai", "") or ""), dialog)
        for field in (openai_key, anthropic_key, google_key, xai_key):
            field.setEchoMode(QLineEdit.Password)
        keys_tab.layout().addWidget(QLabel("Provider keys", dialog), 19, 0, 1, 2)
        for row, (label, widget) in enumerate((("OpenAI key", openai_key), ("Anthropic key", anthropic_key), ("Google key", google_key), ("xAI key", xai_key))):
            target_row = 20 + row
            keys_tab.layout().addWidget(QLabel(label, dialog), target_row, 0)
            keys_tab.layout().addWidget(widget, target_row, 1)

        confirm_browser = QTextBrowser(dialog)
        confirm_tab.layout().addWidget(confirm_browser, 0, 0, 1, 2)

        def current_recommendation() -> dict[str, Any]:
            return recommend_auto_settings(
                file_path=file_edit.text().strip() or None,
                index_path=str(index_combo.currentData() or "").strip() or None,
            )

        def apply_recommendation() -> None:
            rec = current_recommendation()
            chunk_size.setValue(int(rec.get("chunk_size", chunk_size.value()) or chunk_size.value()))
            chunk_overlap.setValue(int(rec.get("chunk_overlap", chunk_overlap.value()) or chunk_overlap.value()))
            build_digest.setChecked(bool(rec.get("build_digest_index", build_digest.isChecked())))
            build_comprehension.setChecked(bool(rec.get("build_comprehension_index", build_comprehension.isChecked())))
            comprehension_depth.setCurrentText(str(rec.get("comprehension_extraction_depth", comprehension_depth.currentText()) or comprehension_depth.currentText()))
            prefer_comprehension.setChecked(bool(rec.get("prefer_comprehension_index", prefer_comprehension.isChecked())))
            retrieval_k.setValue(int(rec.get("retrieval_k", retrieval_k.value()) or retrieval_k.value()))
            top_k.setValue(int(rec.get("final_k", top_k.value()) or top_k.value()))
            mmr_lambda.setText(str(rec.get("mmr_lambda", mmr_lambda.text()) or mmr_lambda.text()))
            retrieval_mode.setCurrentText(str(rec.get("retrieval_mode", retrieval_mode.currentText()) or retrieval_mode.currentText()))
            agentic_mode.setChecked(bool(rec.get("agentic_mode", agentic_mode.isChecked())))
            agentic_iterations.setValue(int(rec.get("agentic_max_iterations", agentic_iterations.value()) or agentic_iterations.value()))
            use_reranker.setChecked(bool(rec.get("use_reranker", use_reranker.isChecked())))
            if bool(rec.get("deepread_mode")):
                deepread_mode.setChecked(True)
            refresh_summary()

        def current_local_gguf_use_case() -> str:
            return self._local_llm_recommender.wizard_mode_to_use_case(mode_preset.currentText())

        def selected_local_gguf_recommendation() -> dict[str, Any] | None:
            item = local_gguf_tree.currentItem()
            payload = item.data(0, Qt.UserRole) if item is not None else None
            return dict(payload or {}) if isinstance(payload, dict) else None

        def local_gguf_action_state(payload: dict[str, Any] | None) -> dict[str, Any]:
            if not isinstance(payload, dict):
                return {
                    "can_import": False,
                    "button_label": "Use Selected Recommendation",
                    "warning": "",
                }
            fit_level = str(payload.get("fit_level") or "").strip().lower()
            has_source = bool(str(payload.get("source_repo") or payload.get("source_provider") or "").strip())
            button_label = "Use Selected Recommendation"
            warning = ""
            if fit_level == "marginal":
                button_label = "Use Selected Recommendation (Confirm)"
                warning = "Activation will ask for confirmation before switching to this model."
            elif fit_level == "too_tight":
                button_label = "Import Only on Finish"
                warning = "Activation is blocked for this recommendation. It can still be imported."
            return {
                "can_import": has_source,
                "button_label": button_label,
                "warning": warning,
            }

        def update_local_gguf_actions() -> None:
            state = local_gguf_action_state(selected_local_gguf_recommendation())
            import_local_gguf.setEnabled(bool(state["can_import"]))
            use_selected_local_gguf.setEnabled(bool(state["can_import"]))
            use_selected_local_gguf.setText(str(state["button_label"]))

        def update_local_gguf_notes() -> None:
            payload = selected_local_gguf_recommendation()
            if not payload:
                local_gguf_notes.setText("")
                update_local_gguf_actions()
                return
            notes = list(payload.get("notes") or [])
            state = local_gguf_action_state(payload)
            summary = (
                f"Fit {payload.get('fit_level', '')} via {payload.get('run_mode', '')}. "
                f"Needs {float(payload.get('memory_required_gb', 0.0) or 0.0):.1f} GB "
                f"from {float(payload.get('memory_available_gb', 0.0) or 0.0):.1f} GB."
            )
            detail_lines = [summary, *notes[:3]]
            if state["warning"]:
                detail_lines.append(str(state["warning"]))
            local_gguf_notes.setText("\n".join(detail_lines))
            update_local_gguf_actions()

        def populate_local_gguf_recommendations(payload: dict[str, Any]) -> None:
            hardware = dict(payload.get("hardware") or {})
            summary_bits = [
                f"RAM {float(hardware.get('available_ram_gb', 0.0) or 0.0):.1f}/{float(hardware.get('total_ram_gb', 0.0) or 0.0):.1f} GB free",
                f"CPU {int(hardware.get('total_cpu_cores', 0) or 0)} cores",
                f"backend={str(hardware.get('backend', 'cpu_x86') or 'cpu_x86')}",
            ]
            if hardware.get("has_gpu"):
                if hardware.get("unified_memory"):
                    summary_bits.append(f"GPU {str(hardware.get('gpu_name') or 'Integrated')} (unified)")
                else:
                    summary_bits.append(
                        f"GPU {str(hardware.get('gpu_name') or 'Detected')} ({float(hardware.get('gpu_vram_gb', 0.0) or 0.0):.1f} GB VRAM)"
                    )
            else:
                summary_bits.append("GPU not detected")
            local_gguf_hardware_label.setText("Hardware: " + " | ".join(summary_bits))
            local_gguf_advisory_label.setText(
                "Recommendations are advisory only for this session."
                if payload.get("advisory_only")
                else ""
            )
            local_gguf_tree.clear()
            for row in payload.get("rows") or []:
                item = QTreeWidgetItem(
                    [
                        str(row.get("model_name", "")),
                        str(row.get("parameter_count", "")),
                        str(row.get("fit_level", "")),
                        str(row.get("best_quant", "")),
                        f"{float(row.get('estimated_tps', 0.0) or 0.0):.1f} tok/s",
                        str(row.get("recommended_context_length", "")),
                        str(row.get("source_provider", "") or row.get("provider", "")),
                    ]
                )
                item.setData(0, Qt.UserRole, dict(row))
                local_gguf_tree.addTopLevelItem(item)
            if local_gguf_tree.topLevelItemCount() > 0:
                local_gguf_tree.setCurrentItem(local_gguf_tree.topLevelItem(0))
            else:
                update_local_gguf_actions()
            update_local_gguf_notes()

        def refresh_local_gguf_recommendations() -> dict[str, Any]:
            payload = self._local_llm_recommender.recommend_models(
                use_case=current_local_gguf_use_case(),
                settings=local_gguf_state,
                current_mode=mode_preset.currentText(),
            )
            populate_local_gguf_recommendations(payload)
            return payload

        def use_selected_local_recommendation() -> None:
            payload = selected_local_gguf_recommendation()
            if not payload:
                return
            llm_provider.setCurrentText("local_gguf")
            llm_model.setText(str(payload.get("model_name", "") or ""))
            import_local_gguf.setChecked(True)
            refresh_summary()

        def edit_local_gguf_hardware() -> None:
            payload = refresh_local_gguf_recommendations()
            edited = self.show_hardware_override_editor(local_gguf_state, dict(payload.get("hardware") or {}))
            if not isinstance(edited, dict):
                return
            local_gguf_state.update(edited)
            refresh_local_gguf_recommendations()

        def summary_payload() -> dict[str, Any]:
            recommendation = current_recommendation()
            return {
                "file_path": file_edit.text().strip(),
                "selected_index_path": str(index_combo.currentData() or ""),
                "chunk_size": chunk_size.value(),
                "chunk_overlap": chunk_overlap.value(),
                "build_digest_index": build_digest.isChecked(),
                "build_comprehension_index": build_comprehension.isChecked(),
                "comprehension_extraction_depth": comprehension_depth.currentText(),
                "prefer_comprehension_index": prefer_comprehension.isChecked(),
                "llm_provider": llm_provider.currentText(),
                "llm_model": llm_model.text().strip(),
                "embedding_provider": embedding_provider.currentText(),
                "embedding_model": embedding_model.text().strip(),
                "retrieval_k": retrieval_k.value(),
                "top_k": top_k.value(),
                "mmr_lambda": mmr_lambda.text().strip(),
                "retrieval_mode": retrieval_mode.currentText(),
                "agentic_mode": agentic_mode.isChecked(),
                "agentic_max_iterations": agentic_iterations.value(),
                "output_style": output_style.currentText(),
                "use_reranker": use_reranker.isChecked(),
                "api_key_openai": openai_key.text().strip(),
                "api_key_anthropic": anthropic_key.text().strip(),
                "api_key_google": google_key.text().strip(),
                "api_key_xai": xai_key.text().strip(),
                "mode_preset": mode_preset.currentText(),
                "deepread_mode": deepread_mode.isChecked(),
                "vector_db_type": vector_backend.currentText(),
                "wizard_recommendation": recommendation,
                "selected_local_gguf_recommendation": selected_local_gguf_recommendation(),
                "import_local_gguf_recommendation": import_local_gguf.isChecked(),
                "local_gguf_use_case": current_local_gguf_use_case(),
                "local_gguf_models_dir": str(local_gguf_state.get("local_gguf_models_dir", "") or ""),
                "hardware_override_enabled": bool(local_gguf_state.get("hardware_override_enabled", False)),
                "hardware_override_total_ram_gb": local_gguf_state.get("hardware_override_total_ram_gb", 0),
                "hardware_override_available_ram_gb": local_gguf_state.get("hardware_override_available_ram_gb", 0),
                "hardware_override_gpu_name": str(local_gguf_state.get("hardware_override_gpu_name", "") or ""),
                "hardware_override_gpu_vram_gb": local_gguf_state.get("hardware_override_gpu_vram_gb", 0),
                "hardware_override_gpu_count": local_gguf_state.get("hardware_override_gpu_count", 0),
                "hardware_override_backend": str(local_gguf_state.get("hardware_override_backend", "") or ""),
                "hardware_override_unified_memory": bool(
                    local_gguf_state.get("hardware_override_unified_memory", False)
                ),
                "cost_estimate": estimate_setup_cost(
                    recommendation,
                    llm_provider=llm_provider.currentText(),
                    embedding_provider=embedding_provider.currentText(),
                ),
            }

        def refresh_summary(*_args: Any) -> None:
            recommendation_label.setText(describe_auto_recommendation(current_recommendation()))
            confirm_browser.setPlainText(json.dumps(summary_payload(), indent=2, ensure_ascii=False))

        apply_rec.clicked.connect(apply_recommendation)
        refresh_local_gguf.clicked.connect(refresh_local_gguf_recommendations)
        edit_local_hardware.clicked.connect(edit_local_gguf_hardware)
        use_selected_local_gguf.clicked.connect(use_selected_local_recommendation)
        local_gguf_tree.itemSelectionChanged.connect(update_local_gguf_notes)
        for signal in (
            file_edit.textChanged,
            index_combo.currentTextChanged,
            llm_provider.currentTextChanged,
            llm_model.textChanged,
            embedding_provider.currentTextChanged,
            embedding_model.textChanged,
            mmr_lambda.textChanged,
            retrieval_mode.currentTextChanged,
            output_style.currentTextChanged,
            mode_preset.currentTextChanged,
            vector_backend.currentTextChanged,
        ):
            signal.connect(refresh_summary)
        mode_preset.currentTextChanged.connect(lambda *_args: refresh_local_gguf_recommendations())
        for widget in (chunk_size, chunk_overlap, retrieval_k, top_k, agentic_iterations):
            widget.valueChanged.connect(refresh_summary)
        for widget in (build_digest, build_comprehension, prefer_comprehension, deepread_mode, use_reranker, agentic_mode):
            widget.toggled.connect(refresh_summary)
        comprehension_depth.currentTextChanged.connect(refresh_summary)
        populate_local_gguf_recommendations(dict(initial_state.get("local_gguf_recommendations") or {}))
        if local_gguf_tree.topLevelItemCount() == 0:
            refresh_local_gguf_recommendations()
        refresh_summary()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, parent=dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        root.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return None
        result = summary_payload()
        if result["mode_preset"] == "Book summary" and result["output_style"] in {"", "Default answer"}:
            result["output_style"] = "Blinkist-style summary"
        return result
