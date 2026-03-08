"""Detail sidebar for Brain graph selections."""

from __future__ import annotations

from html import escape
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from axiom_app.models.brain_graph import BrainGraph, BrainNode
from axiom_app.views.widgets import AnimationEngine, CollapsibleFrame, RoundedCard


class BrainDetailPanel(QWidget):
    """Right-hand sidebar showing the current Brain selection."""

    loadIndexRequested = Signal()
    openSessionRequested = Signal()
    renameSessionRequested = Signal()
    duplicateSessionRequested = Signal()
    exportSessionRequested = Signal()
    deleteSessionRequested = Signal()
    memberActivated = Signal(str)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        palette: dict[str, str] | None = None,
        animator: AnimationEngine | None = None,
    ) -> None:
        super().__init__(parent)
        self._palette = dict(palette or {})
        self._animator = animator
        self._node: BrainNode | None = None
        self._graph: BrainGraph | None = None
        self._index_row: dict[str, Any] | None = None
        self._session_detail: Any | None = None
        self._loaded_files: list[str] = []
        self._active_index_summary = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._card = RoundedCard(
            self,
            radius=20,
            bg=self._palette.get("surface", "#091522"),
            border_color=self._palette.get("border", "#17405F"),
            shadow_color=self._palette.get("workspace_shadow", "#010408"),
            shadow_offset=2,
            inner_padding=18,
        )
        root.addWidget(self._card)

        layout = QVBoxLayout(self._card.inner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        self._title_label = QLabel("Axiom Brain", self._card.inner)
        self._title_label.setObjectName("brainDetailTitle")
        self._title_label.setWordWrap(True)
        layout.addWidget(self._title_label)

        self._subtitle_label = QLabel("Select a node to inspect it.", self._card.inner)
        self._subtitle_label.setObjectName("brainDetailSubtitle")
        self._subtitle_label.setWordWrap(True)
        layout.addWidget(self._subtitle_label)

        self._metadata_section = CollapsibleFrame(self._card.inner, "Metadata", True, self._animator)
        self._metadata_browser = QTextBrowser(self._metadata_section.content)
        self._metadata_browser.setOpenExternalLinks(False)
        self._metadata_browser.setMinimumHeight(180)
        self._metadata_section.content_layout.addWidget(self._metadata_browser)
        layout.addWidget(self._metadata_section)

        self._members_section = CollapsibleFrame(self._card.inner, "Related", True, self._animator)
        self._members_list = QListWidget(self._members_section.content)
        self._members_list.itemDoubleClicked.connect(self._on_member_double_clicked)
        self._members_section.content_layout.addWidget(self._members_list)
        layout.addWidget(self._members_section)

        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(8)
        layout.addLayout(actions_row)

        self.btn_load_index = QPushButton("Load Index", self._card.inner)
        self.btn_load_index.clicked.connect(self.loadIndexRequested.emit)
        actions_row.addWidget(self.btn_load_index)

        self.btn_open_session = QPushButton("Open Session", self._card.inner)
        self.btn_open_session.clicked.connect(self.openSessionRequested.emit)
        actions_row.addWidget(self.btn_open_session)

        self.btn_rename_session = QPushButton("Rename", self._card.inner)
        self.btn_rename_session.clicked.connect(self.renameSessionRequested.emit)
        actions_row.addWidget(self.btn_rename_session)

        self.btn_duplicate_session = QPushButton("Duplicate", self._card.inner)
        self.btn_duplicate_session.clicked.connect(self.duplicateSessionRequested.emit)
        actions_row.addWidget(self.btn_duplicate_session)

        self.btn_export_session = QPushButton("Export", self._card.inner)
        self.btn_export_session.clicked.connect(self.exportSessionRequested.emit)
        actions_row.addWidget(self.btn_export_session)

        self.btn_delete_session = QPushButton("Delete", self._card.inner)
        self.btn_delete_session.clicked.connect(self.deleteSessionRequested.emit)
        actions_row.addWidget(self.btn_delete_session)

        actions_row.addStretch(1)
        self.update_palette(self._palette)
        self._render()

    def update_palette(self, palette: dict[str, str]) -> None:
        self._palette = dict(palette or {})
        self._card.configure_colors(
            bg=self._palette.get("surface", "#091522"),
            border_color=self._palette.get("border", "#17405F"),
            shadow_color=self._palette.get("workspace_shadow", "#010408"),
        )
        muted = self._palette.get("muted_text", "#8AA5BE")
        text = self._palette.get("text", "#F2FAFF")
        surface_alt = self._palette.get("surface_alt", "#13283D")
        border = self._palette.get("border", "#17405F")
        self._title_label.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {text};")
        self._subtitle_label.setStyleSheet(f"color: {muted};")
        list_style = (
            f"QListWidget {{ background-color: {surface_alt}; border: 1px solid {border}; border-radius: 12px; }}"
            f"QTextBrowser {{ background-color: {surface_alt}; border: 1px solid {border}; border-radius: 12px; }}"
        )
        self._members_list.setStyleSheet(list_style)
        self._metadata_browser.setStyleSheet(list_style)

    def set_state(
        self,
        node: BrainNode | None,
        graph: BrainGraph | None,
        *,
        index_row: dict[str, Any] | None = None,
        session_detail: Any | None = None,
        loaded_files: list[str] | None = None,
        active_index_summary: str = "",
    ) -> None:
        self._node = node
        self._graph = graph
        self._index_row = dict(index_row or {}) if index_row else None
        self._session_detail = session_detail
        self._loaded_files = list(loaded_files or [])
        self._active_index_summary = str(active_index_summary or "")
        self._render()

    def _render(self) -> None:
        node = self._node
        if node is None:
            self._title_label.setText("Axiom Brain")
            self._subtitle_label.setText("Select a node to inspect it.")
            self._metadata_browser.setHtml(self._workspace_summary_html())
            self._populate_list("Loaded Files", self._loaded_file_items())
            self._set_actions(node_type="")
            return

        if node.node_type == "index":
            self._title_label.setText(node.label)
            self._subtitle_label.setText("Index node")
            self._metadata_browser.setHtml(self._index_html(node))
            source_files = [str(item) for item in (node.metadata.get("source_files") or []) if str(item).strip()]
            related_sessions = self._related_items(node, edge_type="uses_index", incoming=True)
            items = [(path, "") for path in source_files]
            items.extend(related_sessions)
            self._populate_list("Source Files / Sessions", items)
            self._set_actions(node_type="index")
            return

        if node.node_type == "session":
            self._title_label.setText(node.label)
            self._subtitle_label.setText("Chat session node")
            self._metadata_browser.setHtml(self._session_html(node))
            self._populate_list("Related Nodes", self._session_related_items(node))
            self._set_actions(node_type="session")
            return

        self._title_label.setText(node.label)
        self._subtitle_label.setText(self._category_subtitle(node))
        self._metadata_browser.setHtml(self._category_html(node))
        self._populate_list("Members", self._category_items(node))
        self._set_actions(node_type="category")

    def _workspace_summary_html(self) -> str:
        files = "<br>".join(escape(item) for item in self._loaded_files[:8]) or "No files loaded."
        summary = escape(self._active_index_summary or "No active index selected.")
        return (
            "<p><b>Workspace</b></p>"
            f"<p>{summary}</p>"
            "<p><b>Loaded files</b></p>"
            f"<p>{files}</p>"
        )

    def _index_html(self, node: BrainNode) -> str:
        data = dict(node.metadata or {})
        bits = [
            ("Created", data.get("created_at", "")),
            ("Backend", data.get("vector_backend", "")),
            ("Documents", data.get("document_count", 0)),
            ("Chunks", data.get("chunk_count", 0)),
            ("Collection", data.get("collection_name", "")),
            ("Embedding", data.get("embedding_signature", "")),
            ("Path", data.get("path", "")),
        ]
        return self._kv_html(bits)

    def _session_html(self, node: BrainNode) -> str:
        data = dict(node.metadata or {})
        detail = self._session_detail
        messages = list(getattr(detail, "messages", []) or [])
        preview = []
        for message in messages[-6:]:
            role = escape(str(getattr(message, "role", "") or "").title())
            content = escape(str(getattr(message, "content", "") or ""))
            preview.append(f"<p><b>{role}</b>: {content}</p>")
        if not preview and data.get("summary"):
            preview.append(f"<p>{escape(str(data.get('summary', '')))}</p>")
        bits = [
            ("Updated", data.get("updated_at", "")),
            ("Mode", data.get("mode", "")),
            ("Primary Skill", data.get("primary_skill_id", data.get("active_profile", ""))),
            ("Skills", ", ".join(str(item) for item in (data.get("skill_ids") or []) if str(item).strip())),
            ("Provider", data.get("llm_provider", "")),
            ("Model", data.get("llm_model", "")),
            ("Index", data.get("index_id", "")),
        ]
        return self._kv_html(bits) + "<p><b>Transcript Preview</b></p>" + "".join(preview or ["<p>No messages yet.</p>"])

    def _category_html(self, node: BrainNode) -> str:
        data = dict(node.metadata or {})
        bits = [
            ("Type", self._category_subtitle(node)),
            ("Members", data.get("member_count", 0)),
            ("Sessions", data.get("session_count", 0)),
            ("Indexes", data.get("index_count", 0)),
        ]
        if node.node_id == "category:brain":
            bits.extend(
                [
                    ("Nodes", len(getattr(self._graph, "nodes", {}) or {})),
                    ("Edges", len(getattr(self._graph, "edges", []) or [])),
                ]
            )
        return self._kv_html(bits)

    @staticmethod
    def _kv_html(rows: list[tuple[str, Any]]) -> str:
        parts = ["<table cellspacing='0' cellpadding='4'>"]
        for label, value in rows:
            if value in ("", None):
                continue
            parts.append(
                "<tr>"
                f"<td><b>{escape(str(label))}</b></td>"
                f"<td>{escape(str(value))}</td>"
                "</tr>"
            )
        parts.append("</table>")
        return "".join(parts)

    def _populate_list(self, title: str, items: list[tuple[str, str]]) -> None:
        self._members_section.title_label.setText(title)
        self._members_list.clear()
        if not items:
            placeholder = QListWidgetItem("Nothing to show.")
            placeholder.setFlags(Qt.NoItemFlags)
            self._members_list.addItem(placeholder)
            return
        for label, node_id in items:
            item = QListWidgetItem(label)
            item.setData(Qt.UserRole, str(node_id or ""))
            self._members_list.addItem(item)

    def _set_actions(self, *, node_type: str) -> None:
        is_index = node_type == "index"
        is_session = node_type == "session"
        self.btn_load_index.setVisible(is_index)
        self.btn_open_session.setVisible(is_session)
        self.btn_rename_session.setVisible(is_session)
        self.btn_duplicate_session.setVisible(is_session)
        self.btn_export_session.setVisible(is_session)
        self.btn_delete_session.setVisible(is_session)

    def _loaded_file_items(self) -> list[tuple[str, str]]:
        return [(str(item), "") for item in self._loaded_files]

    def _related_items(self, node: BrainNode, *, edge_type: str, incoming: bool = False) -> list[tuple[str, str]]:
        if self._graph is None:
            return []
        neighbors = self._graph.neighbors(
            node.node_id,
            edge_type=edge_type,
            include_incoming=incoming,
            include_outgoing=not incoming,
        )
        return [(self._member_label(item), item.node_id) for item in neighbors]

    def _session_related_items(self, node: BrainNode) -> list[tuple[str, str]]:
        if self._graph is None:
            return []
        items = []
        for related in self._graph.neighbors(node.node_id, edge_type="uses_index", include_incoming=False, include_outgoing=True):
            items.append((self._member_label(related), related.node_id))
        for related in self._graph.neighbors(node.node_id, edge_type="category_member", include_incoming=False, include_outgoing=True):
            items.append((self._member_label(related), related.node_id))
        return items

    def _category_items(self, node: BrainNode) -> list[tuple[str, str]]:
        if self._graph is None:
            return []
        members = self._graph.category_members(node.node_id)
        return [(self._member_label(item), item.node_id) for item in members]

    @staticmethod
    def _member_label(node: BrainNode) -> str:
        kind = node.node_type.title()
        return f"{node.label} [{kind}]"

    @staticmethod
    def _category_subtitle(node: BrainNode) -> str:
        data = dict(node.metadata or {})
        kind = str(data.get("category_kind", "category") or "category").replace("_", " ").title()
        return f"{kind} node"

    def _on_member_double_clicked(self, item: QListWidgetItem) -> None:
        node_id = str(item.data(Qt.UserRole) or "")
        if node_id:
            self.memberActivated.emit(node_id)
