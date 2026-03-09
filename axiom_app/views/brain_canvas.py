"""Interactive Brain canvas and container widgets."""

from __future__ import annotations

from math import hypot
from typing import Any

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen, QWheelEvent
from PySide6.QtWidgets import (
    QComboBox,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from axiom_app.models.brain_graph import BrainEdge, BrainGraph, BrainNode
from axiom_app.views.brain_detail_panel import BrainDetailPanel
from axiom_app.views.widgets import AnimationEngine, RoundedCard


def _node_fill(node: BrainNode, palette: dict[str, str]) -> QColor:
    if node.node_type == "index":
        return QColor(palette.get("brain_index_node", palette.get("primary", "#2EB7FF")))
    if node.node_type == "session":
        return QColor(palette.get("brain_session_node", palette.get("success", "#35A886")))
    return QColor(palette.get("brain_category_node", palette.get("warning", "#E0A94F")))


def _node_radius(node: BrainNode) -> float:
    if node.node_type == "category":
        base = 38.0
    elif node.node_type == "index":
        base = 28.0
    else:
        base = 24.0
    if node.node_type == "session":
        timestamp = str(node.metadata.get("updated_at") or node.metadata.get("created_at") or "")
        if timestamp:
            base += 3.0
    return base


def _tooltip_text(node: BrainNode) -> str:
    lines = [node.label, f"type: {node.node_type}"]
    for key, value in sorted(dict(node.metadata or {}).items()):
        if value in ("", None, [], {}, ()):
            continue
        label = str(key).replace("_", " ")
        lines.append(f"{label}: {value}")
    return "\n".join(lines)


def _truncate(text: str, limit: int = 24) -> str:
    clean = " ".join(str(text or "").split())
    if len(clean) <= limit:
        return clean
    return clean[: max(1, limit - 1)] + "…"


class BrainNodeItem(QGraphicsObject):
    clicked = Signal(str)
    activated = Signal(str)
    positionChanged = Signal(str, float, float)

    def __init__(self, node: BrainNode, palette: dict[str, str]) -> None:
        super().__init__()
        self.node = node
        self._palette = dict(palette or {})
        self._radius = _node_radius(node)
        self.setFlags(
            QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setCacheMode(QGraphicsItem.DeviceCoordinateCache)
        self.setCursor(Qt.OpenHandCursor)
        self.setToolTip(_tooltip_text(node))
        self.setZValue(10)

    def update_node(self, node: BrainNode, palette: dict[str, str]) -> None:
        self.prepareGeometryChange()
        self.node = node
        self._palette = dict(palette or {})
        self._radius = _node_radius(node)
        self.setToolTip(_tooltip_text(node))
        self.update()

    def boundingRect(self) -> QRectF:
        pad = 8.0
        diameter = self._radius * 2.0
        return QRectF(-self._radius - pad, -self._radius - pad, diameter + pad * 2.0, diameter + pad * 2.0)

    def paint(self, painter: QPainter, _option: Any, _widget: QWidget | None = None) -> None:
        fill = _node_fill(self.node, self._palette)
        border = QColor(self._palette.get("brain_edge", self._palette.get("border", "#17405F")))
        text = QColor(self._palette.get("text", "#F2FAFF"))
        if self.isSelected():
            border = QColor(self._palette.get("focus_ring", self._palette.get("primary", "#2EB7FF")))
            border.setAlpha(255)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(border, 2.0 if self.isSelected() else 1.35))
        painter.setBrush(QBrush(fill))
        painter.drawEllipse(QPointF(0.0, 0.0), self._radius, self._radius)

        painter.setPen(text)
        label = _truncate(self.node.label, 26 if self.node.node_type == "category" else 22)
        font = painter.font()
        font.setBold(True)
        font.setPointSize(9 if self.node.node_type != "category" else 10)
        painter.setFont(font)
        text_rect = QRectF(-self._radius + 4.0, -11.0, self._radius * 2.0 - 8.0, 22.0)
        painter.drawText(text_rect, Qt.AlignCenter | Qt.TextWordWrap, label)

    def mousePressEvent(self, event: Any) -> None:
        self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.node.node_id)

    def mouseDoubleClickEvent(self, event: Any) -> None:
        super().mouseDoubleClickEvent(event)
        if event.button() == Qt.LeftButton:
            self.activated.emit(self.node.node_id)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: Any) -> Any:
        if change == QGraphicsItem.ItemPositionHasChanged:
            pos = self.pos()
            self.node.x = float(pos.x())
            self.node.y = float(pos.y())
            self.positionChanged.emit(self.node.node_id, self.node.x, self.node.y)
        return super().itemChange(change, value)


class BrainEdgeItem(QGraphicsPathItem):
    def __init__(
        self,
        source_item: BrainNodeItem,
        target_item: BrainNodeItem,
        edge: BrainEdge,
        palette: dict[str, str],
    ) -> None:
        super().__init__()
        self.source_item = source_item
        self.target_item = target_item
        self.edge = edge
        self._palette = dict(palette or {})
        self.setZValue(-10)
        self.setAcceptedMouseButtons(Qt.NoButton)
        self.update_palette(self._palette)
        self.update_path()
        self.source_item.positionChanged.connect(lambda *_args: self.update_path())
        self.target_item.positionChanged.connect(lambda *_args: self.update_path())

    def update_palette(self, palette: dict[str, str]) -> None:
        self._palette = dict(palette or {})
        color_key = "brain_edge_category" if self.edge.edge_type == "category_member" else "brain_edge"
        color = QColor(self._palette.get(color_key, self._palette.get("brain_edge", "#2EB7FF")))
        pen = QPen(color, 1.25 if self.edge.edge_type == "category_member" else 1.85)
        if self.edge.edge_type == "category_member":
            pen.setStyle(Qt.DashLine)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        self.setPen(pen)

    def update_path(self) -> None:
        start = self.source_item.scenePos()
        end = self.target_item.scenePos()
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        path = QPainterPath(start)
        if abs(dx) < 1.0 and abs(dy) < 1.0:
            path.lineTo(end)
        else:
            control_dx = max(30.0, abs(dx) * 0.35)
            c1 = QPointF(start.x() + control_dx, start.y() + dy * 0.1)
            c2 = QPointF(end.x() - control_dx, end.y() - dy * 0.1)
            path.cubicTo(c1, c2, end)
        self.setPath(path)


class BrainCanvasView(QGraphicsView):
    nodeSelected = Signal(str)
    nodeActivated = Signal(str)
    nodeMoved = Signal(str, float, float)

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
        self._graph: BrainGraph | None = None
        self._node_items: dict[str, BrainNodeItem] = {}
        self._edge_items: dict[tuple[str, str, str], BrainEdgeItem] = {}
        self._selected_node_id = ""
        self._current_filter = ""
        self._middle_pan = False
        self._middle_origin = QPoint()
        self._selection_blocked = False

        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setBackgroundBrush(QColor(self._palette.get("brain_canvas_bg", self._palette.get("workspace_bg", "#060F18"))))

    def update_palette(self, palette: dict[str, str]) -> None:
        self._palette = dict(palette or {})
        self.setBackgroundBrush(QColor(self._palette.get("brain_canvas_bg", self._palette.get("workspace_bg", "#060F18"))))
        for item in self._node_items.values():
            item.update_node(item.node, self._palette)
        for item in self._edge_items.values():
            item.update_palette(self._palette)
            item.update_path()
        self.viewport().update()

    def set_graph(self, graph: BrainGraph | None, *, selected_node_id: str = "", animate: bool = True) -> None:
        self._graph = graph
        if graph is None:
            self._scene.clear()
            self._node_items.clear()
            self._edge_items.clear()
            self._selected_node_id = ""
            return

        existing_node_ids = set(self._node_items)
        graph_node_ids = set(graph.nodes)
        for node_id in existing_node_ids - graph_node_ids:
            item = self._node_items.pop(node_id)
            self._scene.removeItem(item)
        for key in list(self._edge_items):
            edge_item = self._edge_items.pop(key)
            self._scene.removeItem(edge_item)

        for node_id, node in graph.nodes.items():
            item = self._node_items.get(node_id)
            if item is None:
                item = BrainNodeItem(node, self._palette)
                item.clicked.connect(self._on_item_clicked)
                item.activated.connect(self.nodeActivated.emit)
                item.positionChanged.connect(self.nodeMoved.emit)
                self._node_items[node_id] = item
                self._scene.addItem(item)
                item.setPos(QPointF(node.x, node.y))
            item.update_node(node, self._palette)
            self._move_item(item, node.x, node.y, animate=animate and node_id in existing_node_ids)

        for edge in graph.edges:
            source_item = self._node_items.get(edge.source_id)
            target_item = self._node_items.get(edge.target_id)
            if source_item is None or target_item is None:
                continue
            key = (edge.source_id, edge.target_id, edge.edge_type)
            edge_item = BrainEdgeItem(source_item, target_item, edge, self._palette)
            self._edge_items[key] = edge_item
            self._scene.addItem(edge_item)

        self.apply_filter(self._current_filter)
        preferred = selected_node_id or self._selected_node_id or "category:brain"
        if preferred in self._node_items:
            self.select_node(preferred, emit_signal=False)
        self._scene.setSceneRect(self._scene.itemsBoundingRect().adjusted(-160.0, -160.0, 160.0, 160.0))

    def refresh_layout(self, iterations: int = 120) -> None:
        if self._graph is None:
            return
        self._graph.apply_force_layout(iterations=iterations)
        self.set_graph(self._graph, selected_node_id=self._selected_node_id, animate=True)

    def apply_filter(self, text: str) -> None:
        self._current_filter = str(text or "").strip().casefold()
        if not self._current_filter:
            for item in self._node_items.values():
                item.setVisible(True)
                item.setOpacity(1.0)
            for item in self._edge_items.values():
                item.setVisible(True)
            return

        direct_matches = {
            node_id
            for node_id, item in self._node_items.items()
            if self._matches_filter(item.node, self._current_filter)
        }
        visible_ids = set(direct_matches)
        category_matches = {
            node_id
            for node_id in direct_matches
            if self._node_items[node_id].node.node_type == "category"
        }
        expanded = True
        while expanded:
            expanded = False
            for edge in getattr(self._graph, "edges", []) or []:
                if edge.edge_type == "uses_index":
                    if edge.source_id in visible_ids and edge.target_id not in visible_ids:
                        visible_ids.add(edge.target_id)
                        expanded = True
                    elif edge.target_id in visible_ids and edge.source_id not in visible_ids:
                        visible_ids.add(edge.source_id)
                        expanded = True
                    continue
                if edge.edge_type != "category_member":
                    continue
                if edge.source_id in visible_ids and edge.target_id not in visible_ids:
                    visible_ids.add(edge.target_id)
                    expanded = True
                elif edge.target_id in category_matches and edge.source_id not in visible_ids:
                    visible_ids.add(edge.source_id)
                    expanded = True

        for node_id, item in self._node_items.items():
            visible = node_id in visible_ids
            item.setVisible(visible)
            item.setOpacity(1.0 if visible else 0.0)
        for edge_item in self._edge_items.values():
            visible = edge_item.source_item.isVisible() and edge_item.target_item.isVisible()
            edge_item.setVisible(visible)

    def select_node(self, node_id: str, *, emit_signal: bool = True) -> None:
        target_id = str(node_id or "")
        if target_id not in self._node_items:
            return
        self._selection_blocked = True
        try:
            for item_id, item in self._node_items.items():
                item.setSelected(item_id == target_id)
            self._selected_node_id = target_id
        finally:
            self._selection_blocked = False
        if emit_signal:
            self.nodeSelected.emit(target_id)

    def selected_node_id(self) -> str:
        return self._selected_node_id

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y()
        if delta == 0:
            return
        factor = 1.15 if delta > 0 else 1.0 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event: Any) -> None:
        if event.button() == Qt.MiddleButton:
            self._middle_pan = True
            self._middle_origin = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: Any) -> None:
        if self._middle_pan:
            delta = event.pos() - self._middle_origin
            self._middle_origin = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: Any) -> None:
        if event.button() == Qt.MiddleButton and self._middle_pan:
            self._middle_pan = False
            self.setCursor(Qt.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _move_item(self, item: BrainNodeItem, x_pos: float, y_pos: float, *, animate: bool) -> None:
        target = QPointF(float(x_pos), float(y_pos))
        if not animate or self._animator is None:
            item.setPos(target)
            return
        start = item.pos()
        if hypot(target.x() - start.x(), target.y() - start.y()) < 2.0:
            item.setPos(target)
            return

        self._animator.animate_value(
            f"brain_node_{item.node.node_id}",
            0.0,
            1.0,
            240,
            12,
            lambda value, source=start, dest=target, node_item=item: node_item.setPos(
                QPointF(
                    source.x() + (dest.x() - source.x()) * float(value),
                    source.y() + (dest.y() - source.y()) * float(value),
                )
            ),
        )

    def _on_item_clicked(self, node_id: str) -> None:
        if self._selection_blocked:
            return
        self.select_node(str(node_id or ""), emit_signal=True)

    @staticmethod
    def _matches_filter(node: BrainNode, text: str) -> bool:
        if text in str(node.label or "").casefold():
            return True
        for value in dict(node.metadata or {}).values():
            if text in str(value).casefold():
                return True
        return False


class BrainPanel(QWidget):
    openFilesRequested = Signal()
    buildIndexRequested = Signal()
    newChatRequested = Signal()
    loadIndexRequested = Signal()
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
        self._brain_graph: BrainGraph | None = None
        self._available_index_rows: list[dict[str, Any]] = []
        self._history_rows: list[Any] = []
        self._session_details: dict[str, Any] = {}
        self._loaded_files: list[str] = []
        self._active_index_summary = ""
        self._selected_node_id = ""
        self._surface = "overview"
        self._overview_cards: list[RoundedCard] = []
        self._surface_buttons: dict[str, QPushButton] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)

        intro = QVBoxLayout()
        intro.setContentsMargins(0, 0, 0, 0)
        intro.setSpacing(4)
        self._overview_title = QLabel("Workspace overview", self)
        self._overview_title.setWordWrap(True)
        intro.addWidget(self._overview_title)
        self._overview_subtitle = QLabel(
            "See the active index, recent conversations, and workspace health before diving into the map.",
            self,
        )
        self._overview_subtitle.setWordWrap(True)
        intro.addWidget(self._overview_subtitle)
        root.addLayout(intro)

        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.setSpacing(8)
        root.addLayout(toolbar)

        self.btn_open_files = QPushButton("Add Files", self)
        self.btn_open_files.clicked.connect(self.openFilesRequested.emit)
        toolbar.addWidget(self.btn_open_files)

        self.btn_build_index = QPushButton("Build Index", self)
        self.btn_build_index.clicked.connect(self.buildIndexRequested.emit)
        toolbar.addWidget(self.btn_build_index)

        self._available_index_combo = QComboBox(self)
        self._available_index_combo.setMinimumWidth(240)
        toolbar.addWidget(self._available_index_combo, 1)

        self.btn_library_load_index = QPushButton("Load Index", self)
        self.btn_library_load_index.clicked.connect(self.loadIndexRequested.emit)
        toolbar.addWidget(self.btn_library_load_index)

        self.btn_new_chat = QPushButton("New Chat", self)
        self.btn_new_chat.clicked.connect(self.newChatRequested.emit)
        toolbar.addWidget(self.btn_new_chat)

        surface_row = QHBoxLayout()
        surface_row.setContentsMargins(0, 0, 0, 0)
        surface_row.setSpacing(8)
        root.addLayout(surface_row)

        self._history_search = QLineEdit(self)
        self._history_search.setPlaceholderText("Search indexes, sessions, or metadata")
        self._history_search.textChanged.connect(self._on_search_changed)
        surface_row.addWidget(self._history_search, 1)

        self._history_profile_filter = QComboBox(self)
        self._history_profile_filter.currentTextChanged.connect(self._on_profile_filter_changed)
        surface_row.addWidget(self._history_profile_filter)

        for key, label in (("overview", "Overview"), ("map", "Map")):
            button = QPushButton(label, self)
            button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, surface=key: self._set_surface(surface))
            self._surface_buttons[key] = button
            surface_row.addWidget(button)

        self.btn_history_refresh = QPushButton("Refresh", self)
        self.btn_history_refresh.clicked.connect(self._emit_refresh_requested)
        surface_row.addWidget(self.btn_history_refresh)

        self.btn_brain_layout = QPushButton("Relayout", self)
        self.btn_brain_layout.clicked.connect(self.refresh_layout)
        surface_row.addWidget(self.btn_brain_layout)

        self._library_chunk_size = QSpinBox(self)
        self._library_chunk_size.setRange(1, 500000)
        self._library_chunk_size.setValue(1000)
        self._library_chunk_size.hide()

        self._library_chunk_overlap = QSpinBox(self)
        self._library_chunk_overlap.setRange(0, 100000)
        self._library_chunk_overlap.setValue(100)
        self._library_chunk_overlap.hide()

        self._file_list = QListWidget(self)
        self._file_list.setVisible(False)
        self._file_listbox = self._file_list

        self._surface_stack = QStackedWidget(self)
        root.addWidget(self._surface_stack, 1)

        self._overview_page = QWidget(self)
        overview_layout = QVBoxLayout(self._overview_page)
        overview_layout.setContentsMargins(0, 0, 0, 0)
        overview_layout.setSpacing(12)

        overview_cards_row = QHBoxLayout()
        overview_cards_row.setContentsMargins(0, 0, 0, 0)
        overview_cards_row.setSpacing(12)
        self._index_card, index_layout = self._new_overview_card()
        self._index_info_label = QLabel("No index built.", self._index_card.inner)
        self._index_info_label.setWordWrap(True)
        index_layout.addWidget(QLabel("Active index", self._index_card.inner))
        index_layout.addWidget(self._index_info_label)
        overview_cards_row.addWidget(self._index_card, 1)

        self._files_card, files_layout = self._new_overview_card()
        self._files_summary_label = QLabel("No files loaded yet.", self._files_card.inner)
        self._files_summary_label.setWordWrap(True)
        files_layout.addWidget(QLabel("Workspace sources", self._files_card.inner))
        files_layout.addWidget(self._files_summary_label)
        overview_cards_row.addWidget(self._files_card, 1)

        self._sessions_card, sessions_layout = self._new_overview_card()
        self._sessions_summary_label = QLabel("No conversations yet.", self._sessions_card.inner)
        self._sessions_summary_label.setWordWrap(True)
        sessions_layout.addWidget(QLabel("Recent conversations", self._sessions_card.inner))
        sessions_layout.addWidget(self._sessions_summary_label)
        overview_cards_row.addWidget(self._sessions_card, 1)

        self._health_card, health_layout = self._new_overview_card()
        self._active_index_summary_label = QLabel("No persisted index selected.", self._health_card.inner)
        self._active_index_summary_label.setWordWrap(True)
        health_layout.addWidget(QLabel("Workspace status", self._health_card.inner))
        health_layout.addWidget(self._active_index_summary_label)
        overview_cards_row.addWidget(self._health_card, 1)
        overview_layout.addLayout(overview_cards_row)

        overview_body = QSplitter(Qt.Horizontal, self._overview_page)
        overview_body.setChildrenCollapsible(False)
        overview_layout.addWidget(overview_body, 1)

        history_host = QWidget(overview_body)
        history_layout = QVBoxLayout(history_host)
        history_layout.setContentsMargins(0, 0, 0, 0)
        history_layout.setSpacing(8)
        history_layout.addWidget(QLabel("Recent work", history_host))
        self._history_list = QListWidget(history_host)
        self._history_list.currentItemChanged.connect(self._on_overview_history_selection)
        self._history_list.itemDoubleClicked.connect(self._on_overview_history_activated)
        history_layout.addWidget(self._history_list, 1)
        overview_body.addWidget(history_host)

        detail_host = QWidget(overview_body)
        detail_layout = QVBoxLayout(detail_host)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(8)
        detail_layout.addWidget(QLabel("Selection details", detail_host))
        self._overview_detail = QTextBrowser(detail_host)
        detail_layout.addWidget(self._overview_detail, 1)
        self._open_map_button = QPushButton("Open Map", detail_host)
        self._open_map_button.clicked.connect(lambda: self._set_surface("map"))
        detail_layout.addWidget(self._open_map_button, 0, Qt.AlignLeft)
        overview_body.addWidget(detail_host)
        overview_body.setStretchFactor(0, 3)
        overview_body.setStretchFactor(1, 2)
        overview_body.setSizes([700, 420])
        self._surface_stack.addWidget(self._overview_page)

        self._map_page = QWidget(self)
        map_layout = QVBoxLayout(self._map_page)
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(0)
        splitter = QSplitter(Qt.Horizontal, self._map_page)
        splitter.setChildrenCollapsible(False)
        map_layout.addWidget(splitter, 1)

        canvas_host = QWidget(splitter)
        canvas_layout = QVBoxLayout(canvas_host)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)
        self.canvas = BrainCanvasView(canvas_host, palette=self._palette, animator=self._animator)
        self.canvas.nodeSelected.connect(self._on_canvas_node_selected)
        self.canvas.nodeActivated.connect(self._on_canvas_node_activated)
        self.canvas.nodeMoved.connect(self._on_canvas_node_moved)
        canvas_layout.addWidget(self.canvas, 1)
        splitter.addWidget(canvas_host)

        self.detail_panel = BrainDetailPanel(splitter, palette=self._palette, animator=self._animator)
        self.detail_panel.setMinimumWidth(320)
        self.detail_panel.loadIndexRequested.connect(self.loadIndexRequested.emit)
        self.detail_panel.openSessionRequested.connect(self.historyOpenRequested.emit)
        self.detail_panel.renameSessionRequested.connect(self.historyRenameRequested.emit)
        self.detail_panel.duplicateSessionRequested.connect(self.historyDuplicateRequested.emit)
        self.detail_panel.exportSessionRequested.connect(self.historyExportRequested.emit)
        self.detail_panel.deleteSessionRequested.connect(self.historyDeleteRequested.emit)
        self.detail_panel.memberActivated.connect(lambda node_id: self.select_brain_node(node_id, emit_signal=True))
        splitter.addWidget(self.detail_panel)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([920, 340])
        self._surface_stack.addWidget(self._map_page)

        self.update_palette(self._palette)
        self._set_surface("overview")
        self._sync_summary_cards()

    def update_palette(self, palette: dict[str, str]) -> None:
        self._palette = dict(palette or {})
        muted = self._palette.get("muted_text", "#8AA5BE")
        text = self._palette.get("text", "#F2FAFF")
        surface_alt = self._palette.get("surface_alt", "#13283D")
        border = self._palette.get("border", "#17405F")
        nav_active = self._palette.get("nav_active_bg", "#113B5C")
        nav_hover = self._palette.get("nav_hover_bg", "#0E2032")
        self._overview_title.setStyleSheet(f"font-size: 26px; font-weight: 700; color: {text};")
        self._overview_subtitle.setStyleSheet(f"color: {muted};")
        self._history_list.setStyleSheet(
            f"QListWidget {{ background-color: {surface_alt}; border: 1px solid {border}; border-radius: 16px; }}"
        )
        self._overview_detail.setStyleSheet(
            f"QTextBrowser {{ background-color: {surface_alt}; border: 1px solid {border}; border-radius: 16px; }}"
        )
        for card in self._overview_cards:
            card.configure_colors(
                bg=self._palette.get("surface", "#091522"),
                border_color=border,
                shadow_color=self._palette.get("workspace_shadow", "#010408"),
            )
        for key, button in self._surface_buttons.items():
            button.setStyleSheet(
                f"QPushButton {{ border: 1px solid {border}; border-radius: 12px; padding: 8px 12px; }}"
                f"QPushButton:checked {{ background-color: {nav_active}; }}"
                f"QPushButton:hover:!checked {{ background-color: {nav_hover}; }}"
            )
            button.setChecked(key == self._surface)
        self._index_info_label.setStyleSheet(f"color: {muted};")
        self._files_summary_label.setStyleSheet(f"color: {muted};")
        self._sessions_summary_label.setStyleSheet(f"color: {muted};")
        self._active_index_summary_label.setStyleSheet(f"color: {muted};")
        self.canvas.update_palette(self._palette)
        self.detail_panel.update_palette(self._palette)
        self._render_overview_detail()

    def set_graph(self, graph: BrainGraph | None, *, selected_node_id: str = "") -> None:
        self._brain_graph = graph
        self.canvas.set_graph(graph, selected_node_id=selected_node_id, animate=True)
        self._selected_node_id = self.canvas.selected_node_id()
        self._sync_detail_panel()
        self._sync_summary_cards()

    def refresh_layout(self) -> None:
        self.canvas.refresh_layout()
        self._sync_detail_panel()

    def set_graph_filter(self, text: str) -> None:
        self.canvas.apply_filter(text)

    def set_index_info(self, text: str) -> None:
        self._index_info_label.setText(str(text or ""))

    def set_available_indexes(self, rows: list[dict[str, Any]], selected_path: str = "") -> None:
        self._available_index_rows = list(rows or [])
        current = str(selected_path or self._available_index_combo.currentData() or "")
        self._available_index_combo.blockSignals(True)
        self._available_index_combo.clear()
        for row in self._available_index_rows:
            label = str(row.get("label", row.get("index_id", "")) or row.get("index_id", ""))
            self._available_index_combo.addItem(label, str(row.get("path", "") or ""))
        if current:
            index = self._available_index_combo.findData(current)
            if index >= 0:
                self._available_index_combo.setCurrentIndex(index)
        self._available_index_combo.blockSignals(False)
        self._sync_detail_panel()

    def get_selected_available_index_path(self) -> str:
        node = self._selected_node()
        if node is not None and node.node_type == "index":
            return str(node.metadata.get("path", "") or "")
        return str(self._available_index_combo.currentData() or "")

    def set_active_index_summary(self, summary: str, index_path: str = "") -> None:
        self._active_index_summary = str(summary or "")
        self._active_index_summary_label.setText(self._active_index_summary or "No persisted index selected.")
        if index_path:
            index = self._available_index_combo.findData(str(index_path))
            if index >= 0:
                self._available_index_combo.setCurrentIndex(index)
        self._sync_detail_panel()
        self._sync_summary_cards()

    def set_file_list(self, paths: list[str]) -> None:
        self._loaded_files = [str(path) for path in (paths or [])]
        self._file_list.clear()
        for path in self._loaded_files:
            self._file_list.addItem(path)
        self._sync_detail_panel()
        self._sync_summary_cards()

    def get_library_build_settings(self) -> dict[str, Any]:
        return {
            "chunk_size": self._library_chunk_size.value(),
            "chunk_overlap": self._library_chunk_overlap.value(),
        }

    def set_history_rows(self, rows: list[Any]) -> None:
        self._history_rows = list(rows or [])
        valid_sessions = {str(getattr(row, "session_id", "") or "") for row in self._history_rows}
        self._session_details = {key: value for key, value in self._session_details.items() if key in valid_sessions}
        self._populate_history_list()
        self._sync_detail_panel()
        self._sync_summary_cards()

    def get_selected_history_session_id(self) -> str:
        node = self._selected_node()
        if node is not None and node.node_type == "session":
            return str(node.metadata.get("session_id", "") or "")
        item = self._history_list.currentItem()
        return str(item.data(Qt.UserRole) or "") if item is not None else ""

    def select_history_session(self, session_id: str) -> None:
        if not session_id:
            return
        for index in range(self._history_list.count()):
            item = self._history_list.item(index)
            if str(item.data(Qt.UserRole) or "") == str(session_id):
                self._history_list.setCurrentItem(item)
                break
        self.select_brain_node(f"session:{session_id}", emit_signal=False)

    def get_history_search_query(self) -> str:
        return self._history_search.text().strip()

    def get_history_profile_filter(self) -> str:
        value = self._history_profile_filter.currentText().strip()
        return "" if value == "All Skills" else value

    def get_history_skill_filter(self) -> str:
        return self.get_history_profile_filter()

    def bind_history_search(self, callback: Any) -> None:
        self._history_search.textChanged.connect(lambda *_args: callback())

    def bind_history_selection(self, callback: Any) -> None:
        self.brainNodeSelected.connect(lambda node_id: callback() if str(node_id).startswith("session:") else None)

    def bind_history_profile_filter(self, callback: Any) -> None:
        self._history_profile_filter.currentTextChanged.connect(lambda *_args: callback())

    def bind_history_skill_filter(self, callback: Any) -> None:
        self.bind_history_profile_filter(callback)

    def set_history_detail(self, detail: Any) -> None:
        if detail is None:
            return
        summary = getattr(detail, "summary", detail)
        session_id = str(getattr(summary, "session_id", "") or "")
        if not session_id:
            return
        self._session_details[session_id] = detail
        selected = self.get_selected_history_session_id()
        if selected == session_id:
            self._sync_detail_panel()

    def set_profile_filter_options(self, labels: list[str], current: str = "") -> None:
        self._history_profile_filter.blockSignals(True)
        selected = current or self._history_profile_filter.currentText() or "All Skills"
        self._history_profile_filter.clear()
        self._history_profile_filter.addItems(["All Skills", *list(labels or [])])
        self._history_profile_filter.setCurrentText(selected if selected else "All Skills")
        self._history_profile_filter.blockSignals(False)

    def set_skill_filter_options(self, labels: list[str], current: str = "") -> None:
        self.set_profile_filter_options(labels, current)

    def select_brain_node(self, node_id: str, *, emit_signal: bool = False) -> None:
        self.canvas.select_node(node_id, emit_signal=emit_signal)
        self._selected_node_id = self.canvas.selected_node_id()
        self._sync_detail_panel()

    def get_selected_brain_node_id(self) -> str:
        return self.canvas.selected_node_id()

    def _emit_refresh_requested(self) -> None:
        self.historyRefreshRequested.emit()
        self.brainRefreshRequested.emit()

    def _on_search_changed(self, text: str) -> None:
        self.set_graph_filter(text)
        self._populate_history_list()
        self.historySearchRequested.emit()

    def _on_profile_filter_changed(self, _text: str) -> None:
        self.historySkillFilterRequested.emit()
        self.historyProfileFilterRequested.emit()

    def _on_canvas_node_selected(self, node_id: str) -> None:
        self._selected_node_id = str(node_id or "")
        self._sync_detail_panel()
        self.brainNodeSelected.emit(self._selected_node_id)

    def _on_canvas_node_activated(self, node_id: str) -> None:
        self._selected_node_id = str(node_id or "")
        self._sync_detail_panel()
        self.brainNodeActivated.emit(self._selected_node_id)

    def _on_canvas_node_moved(self, node_id: str, x_pos: float, y_pos: float) -> None:
        if self._brain_graph is None:
            return
        node = self._brain_graph.get_node(node_id)
        if node is None:
            return
        node.x = float(x_pos)
        node.y = float(y_pos)

    def _selected_node(self) -> BrainNode | None:
        if self._brain_graph is None:
            return None
        selected_id = self.canvas.selected_node_id() or self._selected_node_id or "category:brain"
        node = self._brain_graph.get_node(selected_id)
        if node is None:
            node = self._brain_graph.get_node("category:brain")
        return node

    def _sync_detail_panel(self) -> None:
        node = self._selected_node()
        index_row = self._index_row_for(node)
        session_detail = None
        if node is not None and node.node_type == "session":
            session_detail = self._session_details.get(str(node.metadata.get("session_id", "") or ""))
        self.detail_panel.set_state(
            node,
            self._brain_graph,
            index_row=index_row,
            session_detail=session_detail,
            loaded_files=self._loaded_files,
            active_index_summary=self._active_index_summary,
        )
        self._render_overview_detail()

    def _index_row_for(self, node: BrainNode | None) -> dict[str, Any] | None:
        if node is None or node.node_type != "index":
            return None
        path = str(node.metadata.get("path", "") or "")
        index_id = str(node.label or "")
        collection_name = str(node.metadata.get("collection_name", "") or "")
        for row in self._available_index_rows:
            if path and str(row.get("path", "") or "") == path:
                return dict(row)
            if index_id and str(row.get("index_id", "") or "") == index_id:
                return dict(row)
            if collection_name and str(row.get("collection_name", "") or "") == collection_name:
                return dict(row)
        return None

    def _new_overview_card(self) -> tuple[RoundedCard, QVBoxLayout]:
        card = RoundedCard(
            self,
            radius=20,
            bg=self._palette.get("surface", "#091522"),
            border_color=self._palette.get("border", "#17405F"),
            shadow_color=self._palette.get("workspace_shadow", "#010408"),
            shadow_offset=2,
            inner_padding=16,
        )
        layout = QVBoxLayout(card.inner)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._overview_cards.append(card)
        return card, layout

    def _set_surface(self, surface: str) -> None:
        self._surface = surface if surface in {"overview", "map"} else "overview"
        if self._surface == "map":
            self._surface_stack.setCurrentWidget(self._map_page)
        else:
            self._surface_stack.setCurrentWidget(self._overview_page)
        self.btn_brain_layout.setVisible(self._surface == "map")
        self.update_palette(self._palette)

    def _populate_history_list(self) -> None:
        query = self._history_search.text().strip().casefold()
        self._history_list.clear()
        for row in self._history_rows:
            title = str(getattr(row, "title", "") or getattr(row, "session_id", "") or "").strip()
            summary = str(getattr(row, "summary", "") or "").strip()
            profile = str(getattr(row, "primary_skill_id", "") or getattr(row, "active_profile", "") or "").strip()
            mode = str(getattr(row, "mode", "") or "Q&A").strip()
            haystack = " ".join(bit for bit in (title, summary, profile, mode) if bit).casefold()
            if query and query not in haystack:
                continue
            item = QListWidgetItem(f"{title or 'Untitled'}\n{mode} · {profile or 'No skill'}")
            item.setData(Qt.UserRole, str(getattr(row, "session_id", "") or ""))
            self._history_list.addItem(item)

    def _sync_summary_cards(self) -> None:
        source_count = len(self._loaded_files)
        session_count = len(self._history_rows)
        self._files_summary_label.setText(
            f"{source_count} file{'s' if source_count != 1 else ''} loaded."
            + (f"\nLatest: {self._loaded_files[-1]}" if self._loaded_files else "")
        )
        if session_count:
            latest = self._history_rows[0]
            latest_title = str(getattr(latest, "title", "") or getattr(latest, "session_id", "") or "Recent chat")
            self._sessions_summary_label.setText(
                f"{session_count} conversation{'s' if session_count != 1 else ''} in this workspace.\nLatest: {latest_title}"
            )
        else:
            self._sessions_summary_label.setText("No conversations yet.")

    def _render_overview_detail(self) -> None:
        node = self._selected_node()
        if node is None:
            files = "<br>".join(str(item) for item in self._loaded_files[:8]) or "No files loaded."
            summary = self._active_index_summary or "No active index selected."
            self._overview_detail.setHtml(
                f"<p><b>Workspace</b></p><p>{summary}</p><p><b>Loaded files</b></p><p>{files}</p>"
            )
            return
        detail = [f"<p><b>{node.label}</b></p>", f"<p>Type: {node.node_type}</p>"]
        for key, value in list(dict(node.metadata or {}).items())[:8]:
            if value in ("", None, [], {}, ()):
                continue
            detail.append(f"<p><b>{key.replace('_', ' ').title()}</b>: {value}</p>")
        self._overview_detail.setHtml("".join(detail))

    def _on_overview_history_selection(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        session_id = str(current.data(Qt.UserRole) or "") if current is not None else ""
        if not session_id:
            self._render_overview_detail()
            return
        self.select_history_session(session_id)
        self.historySelectionRequested.emit()

    def _on_overview_history_activated(self, item: QListWidgetItem) -> None:
        session_id = str(item.data(Qt.UserRole) or "")
        if not session_id:
            return
        self.select_history_session(session_id)
        self.historyOpenRequested.emit()
