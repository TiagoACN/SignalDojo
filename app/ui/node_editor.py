# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Qt Graphics View based workflow editor.

The editor is deliberately thin: processing and connection rules live in the core
workflow module.  This file owns interaction, layout, copy/paste and annotations.
"""

from __future__ import annotations

import copy
import math
import uuid
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QByteArray, QDataStream, QIODevice, QLineF, QMimeData, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QDrag, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QPolygonF, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsPathItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QVBoxLayout,
)

from app.core.blocks import BLOCK_TYPES, create_block

MIME_TYPE = "application/x-signaldojo-block"
NODE_WIDTH = 205.0
NODE_HEIGHT = 94.0
PORT_RADIUS = 7.0
GRID_SIZE = 25.0
RESULT_BLOCK_TYPES = frozenset(
    {
        "scope",
        "multi_signal_scope",
        "spectrum_analyser",
        "data_table",
        "statistics_display",
        "spectrogram_viewer",
    }
)

_CATEGORY_COLOURS = {
    "Inputs & Outputs": "#4ba3ff",
    "Signal Generators": "#55c271",
    "Mathematics": "#c98bea",
    "Signal Conditioning": "#f1b84b",
    "Filters": "#46c5c1",
    "Resampling & Time": "#f08a73",
    "Analysis": "#8b72d6",
    "Custom Processing": "#d6a552",
}


def _category_colour(category: str) -> QColor:
    return QColor(_CATEGORY_COLOURS.get(category, "#9fb0bf"))


def _port_type(types: tuple[str, ...], index: int) -> str:
    if not types:
        return "any"
    return types[index] if index < len(types) else types[-1]


class BlockLibrary(QListWidget):
    """Searchable drag source containing every registered processing block."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSpacing(3)
        self.populate()

    def _add_header(self, text: str) -> None:
        header = QListWidgetItem(text)
        header.setFlags(Qt.ItemFlag.NoItemFlags)
        font = header.font(); font.setBold(True); header.setFont(font)
        self.addItem(header)

    def _add_block(self, block_cls) -> None:
        item = QListWidgetItem(block_cls.display_name)
        icon = QPixmap(12, 12); icon.fill(_category_colour(block_cls.category)); item.setIcon(QIcon(icon))
        item.setToolTip(block_cls.description)
        item.setData(Qt.ItemDataRole.UserRole, block_cls.type_name)
        self.addItem(item)

    def populate(self, search_text: str = "") -> None:
        from app.application import settings

        self._search_text = search_text.strip().lower()
        self.clear()
        all_blocks = {block_cls.type_name: block_cls for block_cls in BLOCK_TYPES.values()}
        app_settings = settings()
        favourites = [str(value) for value in app_settings.value("blocks/favourites", [], type=list) if str(value) in all_blocks]
        recent = [str(value) for value in app_settings.value("blocks/recent", [], type=list) if str(value) in all_blocks]

        def matches(block_cls) -> bool:
            haystack = f"{block_cls.display_name} {block_cls.category} {block_cls.description}".lower()
            return not self._search_text or self._search_text in haystack

        if favourites:
            visible = [all_blocks[name] for name in favourites if matches(all_blocks[name])]
            if visible:
                self._add_header("Favourites")
                for block_cls in visible: self._add_block(block_cls)
        if recent:
            visible = [all_blocks[name] for name in recent[:8] if matches(all_blocks[name])]
            if visible:
                self._add_header("Recently Used")
                for block_cls in visible: self._add_block(block_cls)

        grouped = sorted(BLOCK_TYPES.values(), key=lambda cls: (cls.category, cls.display_name))
        last_category = None
        for block_cls in grouped:
            if not matches(block_cls):
                continue
            if block_cls.category != last_category:
                self._add_header(block_cls.category)
                last_category = block_cls.category
            self._add_block(block_cls)

    def mark_used(self, type_name: str) -> None:
        from app.application import settings
        app_settings = settings()
        recent = [str(value) for value in app_settings.value("blocks/recent", [], type=list)]
        recent = [type_name] + [value for value in recent if value != type_name]
        app_settings.setValue("blocks/recent", recent[:12])

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        from app.application import settings
        item = self.itemAt(event.pos())
        type_name = str(item.data(Qt.ItemDataRole.UserRole)) if item and item.data(Qt.ItemDataRole.UserRole) else ""
        if not type_name:
            super().contextMenuEvent(event); return
        app_settings = settings()
        favourites = [str(value) for value in app_settings.value("blocks/favourites", [], type=list)]
        menu = QMenu(self)
        toggle = menu.addAction("Remove from Favourites" if type_name in favourites else "Add to Favourites")
        chosen = menu.exec(event.globalPos())
        if chosen == toggle:
            if type_name in favourites: favourites = [value for value in favourites if value != type_name]
            else: favourites.insert(0, type_name)
            app_settings.setValue("blocks/favourites", favourites)
            self.populate(self._search_text)

    def startDrag(self, supported_actions: Qt.DropAction) -> None:  # noqa: N802
        item = self.currentItem()
        if not item:
            return
        type_name = item.data(Qt.ItemDataRole.UserRole)
        if not type_name:
            return
        mime = QMimeData()
        payload = QByteArray()
        stream = QDataStream(payload, QIODevice.OpenModeFlag.WriteOnly)
        stream.writeQString(str(type_name))
        mime.setData(MIME_TYPE, payload)
        self.mark_used(str(type_name))
        drag = QDrag(self); drag.setMimeData(mime); drag.exec(Qt.DropAction.CopyAction)


class PortItem(QGraphicsEllipseItem):
    """Interactive typed port supporting both click-to-connect and drag-to-connect."""

    _ACTIVE_COLOUR = QColor("#ffbf47")
    _TARGET_COLOUR = QColor("#f4e66d")

    def __init__(self, node: "NodeItem", kind: str, index: int, position: QPointF) -> None:
        super().__init__(-PORT_RADIUS, -PORT_RADIUS, PORT_RADIUS * 2, PORT_RADIUS * 2, node)
        self.node = node
        self.kind = kind
        self.index = index
        self.setPos(position)
        self._base_colour = QColor("#4ba3ff") if kind == "output" else QColor("#7bd88f")
        self._active = False
        self._drag_target = False
        self._hovered = False
        self._press_scene_position: QPointF | None = None
        self._dragging = False
        self.setBrush(QBrush(self._base_colour))
        self.setPen(QPen(QColor("#151a20"), 1.5))
        self.setZValue(4)
        self.setAcceptHoverEvents(True)
        types = node.block.output_types if kind == "output" else node.block.input_types
        self.data_type = _port_type(types, index)
        self.setToolTip(f"{kind.title()} {index + 1} — {self.data_type}")

    def _refresh_colour(self) -> None:
        if self._drag_target:
            colour = self._TARGET_COLOUR
        elif self._active:
            colour = self._ACTIVE_COLOUR
        elif self._hovered:
            colour = self._base_colour.lighter(125)
        else:
            colour = self._base_colour
        self.setBrush(QBrush(colour))
        self.update()

    def set_active(self, active: bool) -> None:
        self._active = bool(active)
        self._refresh_colour()

    def set_drag_target(self, active: bool) -> None:
        self._drag_target = bool(active)
        self._refresh_colour()

    def hoverEnterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self._refresh_colour()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self._refresh_colour()
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_scene_position = event.scenePos()
            self._dragging = False
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        scene = self.scene()
        if (
            isinstance(scene, WorkflowScene)
            and self._press_scene_position is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            distance = QLineF(self._press_scene_position, event.scenePos()).length()
            if not self._dragging and distance >= 6.0:
                self._dragging = True
                scene.begin_connection_drag(self)
            if self._dragging:
                scene.update_connection_drag(event.scenePos())
                event.accept()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        scene = self.scene()
        if event.button() == Qt.MouseButton.LeftButton and isinstance(scene, WorkflowScene):
            if self._dragging:
                scene.finish_connection_drag(event.scenePos())
            else:
                scene.port_clicked(self)
            self._press_scene_position = None
            self._dragging = False
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def scene_position(self) -> QPointF:
        return self.mapToScene(QPointF(0, 0))


class NodeItem(QGraphicsRectItem):
    def __init__(self, type_name: str, *, node_id: str | None = None, params: dict[str, Any] | None = None, label: str = "") -> None:
        super().__init__(0, 0, NODE_WIDTH, NODE_HEIGHT)
        self.node_id = node_id or uuid.uuid4().hex
        self.block_type = type_name
        self.block = create_block(type_name, params)
        self.params = self.block.serialise_params()
        self.custom_label = label
        self.input_ports: list[PortItem] = []
        self.output_ports: list[PortItem] = []
        self.state = "idle"
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setBrush(QBrush(QColor("#28313b")))
        self.setPen(QPen(QColor("#677585"), 1.4))

        self.title_item = QGraphicsTextItem(label or self.block.display_name, self)
        self.title_item.setDefaultTextColor(QColor("#f2f4f7")); self.title_item.setPos(12, 8)
        font = self.title_item.font(); font.setBold(True); self.title_item.setFont(font)
        category = QGraphicsTextItem(self.block.category, self)
        category.setDefaultTextColor(QColor("#9fb0bf")); category.setPos(12, 34)
        category_font = category.font(); category_font.setPointSize(max(7, category_font.pointSize() - 1)); category.setFont(category_font)
        type_text = QGraphicsTextItem(f"{self.block.input_count} in • {self.block.output_count} out", self)
        type_text.setDefaultTextColor(QColor("#7f91a2")); type_text.setPos(12, 57)
        tiny = type_text.font(); tiny.setPointSize(max(7, tiny.pointSize() - 2)); type_text.setFont(tiny)
        self.setToolTip(self.block.description)
        category_icon = QGraphicsEllipseItem(0, 0, 12, 12, self); category_icon.setPos(NODE_WIDTH - 25, 13); category_icon.setBrush(QBrush(_category_colour(self.block.category))); icon_pen = QPen(); icon_pen.setStyle(Qt.PenStyle.NoPen); category_icon.setPen(icon_pen)

        for index in range(self.block.input_count):
            y = NODE_HEIGHT * (index + 1) / (self.block.input_count + 1)
            self.input_ports.append(PortItem(self, "input", index, QPointF(0, y)))
        for index in range(self.block.output_count):
            y = NODE_HEIGHT * (index + 1) / (self.block.output_count + 1)
            self.output_ports.append(PortItem(self, "output", index, QPointF(NODE_WIDTH, y)))

    def set_label(self, label: str) -> None:
        self.custom_label = label
        self.title_item.setPlainText(label or self.block.display_name)

    def _visual_scene_bounds(self) -> QRectF:
        """Return the complete painted area of this node and all child items.

        The ports are child graphics items centred on the node boundary, so half of
        each port lies outside the rectangle painted by ``QGraphicsRectItem``.  Qt's
        partial viewport update modes can otherwise omit those outer halves when the
        parent moves, leaving temporary trails until a larger repaint occurs.
        """
        local_bounds = self.boundingRect().united(self.childrenBoundingRect())
        return self.mapRectToScene(local_bounds).adjusted(-3.0, -3.0, 3.0, 3.0)

    def itemChange(self, change, value):  # noqa: N802
        scene = self.scene()
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and isinstance(scene, WorkflowScene):
            # Save the old complete paint region before Qt applies the new position.
            # The explicit dirty-region update in ItemPositionHasChanged clears the
            # portions of child ports that extend outside the node's own rectangle.
            self._previous_visual_scene_bounds = self._visual_scene_bounds()
            if scene.snap_to_grid:
                point = value
                value = QPointF(round(point.x() / GRID_SIZE) * GRID_SIZE, round(point.y() / GRID_SIZE) * GRID_SIZE)
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and isinstance(scene, WorkflowScene):
            scene.update_connections_for_node(self.node_id)
            previous = getattr(self, "_previous_visual_scene_bounds", QRectF())
            current = self._visual_scene_bounds()
            dirty = previous.united(current) if not previous.isNull() else current
            scene.update(dirty)
            self._previous_visual_scene_bounds = current
            if not scene.loading:
                scene.graph_changed.emit()
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged and bool(value) and isinstance(scene, WorkflowScene):
            scene.node_selected.emit(self)
        return result

    def set_processing_state(self, state: str) -> None:
        self.state = state
        colours = {
            "idle": "#677585", "processing": "#4ba3ff", "completed": "#55c271",
            "cached": "#8b72d6", "failed": "#e35d6a", "warning": "#f1b84b",
        }
        self.setPen(QPen(QColor(colours.get(state, colours["idle"])), 2.4))

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        """Open the latest result when a display block is double-clicked."""
        scene = self.scene()
        if self.block_type in RESULT_BLOCK_TYPES and isinstance(scene, WorkflowScene):
            scene.result_requested.emit(self.node_id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        scene = self.scene()
        if not isinstance(scene, WorkflowScene):
            return
        menu = QMenu()
        open_result = None
        if self.block_type in RESULT_BLOCK_TYPES:
            open_result = menu.addAction("Open Latest Result")
            menu.addSeparator()
        duplicate = menu.addAction("Duplicate")
        delete = menu.addAction("Delete")
        selected = menu.exec(event.screenPos())
        if open_result is not None and selected == open_result:
            scene.result_requested.emit(self.node_id)
        elif selected == duplicate:
            self.setSelected(True); scene.duplicate_selected()
        elif selected == delete:
            self.setSelected(True); scene.delete_selected()


class PendingConnectionItem(QGraphicsPathItem):
    """Transient cable rendered while the user creates a connection."""

    def __init__(self, source: PortItem) -> None:
        super().__init__()
        self.source = source
        self.setPen(QPen(QColor("#ffbf47"), 2.2, Qt.PenStyle.DashLine))
        self.setZValue(-0.5)
        self.update_to(source.scene_position())

    @staticmethod
    def _path_between(start: QPointF, end: QPointF) -> QPainterPath:
        distance = max(55.0, abs(end.x() - start.x()) * 0.5)
        path = QPainterPath(start)
        path.cubicTo(start + QPointF(distance, 0), end - QPointF(distance, 0), end)
        return path

    def update_to(self, cursor: QPointF) -> None:
        port_position = self.source.scene_position()
        start, end = (port_position, cursor) if self.source.kind == "output" else (cursor, port_position)
        self.setPath(self._path_between(start, end))


class ConnectionItem(QGraphicsPathItem):
    _ARROW_PAINT_MARGIN = 13.0

    def __init__(self, source: PortItem, target: PortItem) -> None:
        super().__init__()
        self.source = source; self.target = target
        self.setPen(QPen(QColor("#9fb3c8"), 2.2))
        self.setZValue(-1)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.update_path()

    def update_path(self) -> None:
        start, end = self.source.scene_position(), self.target.scene_position()
        distance = max(55.0, abs(end.x() - start.x()) * 0.5)
        path = QPainterPath(start)
        path.cubicTo(start + QPointF(distance, 0), end - QPointF(distance, 0), end)
        self.setPath(path)

    def boundingRect(self) -> QRectF:  # noqa: N802
        """Include the custom arrowhead painted outside the centre-line path."""
        margin = self._ARROW_PAINT_MARGIN + self.pen().widthF()
        return super().boundingRect().adjusted(-margin, -margin, margin, margin)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        super().paint(painter, option, widget)
        end = self.target.scene_position()
        start = self.path().pointAtPercent(0.94)
        line = QLineF(start, end)
        angle = math.atan2(-line.dy(), line.dx())
        size = 9.0
        p1 = end - QPointF(math.cos(angle - math.pi / 3) * size, -math.sin(angle - math.pi / 3) * size)
        p2 = end - QPointF(math.cos(angle + math.pi / 3) * size, -math.sin(angle + math.pi / 3) * size)
        painter.setPen(self.pen()); painter.setBrush(self.pen().color()); painter.drawPolygon(QPolygonF([end, p1, p2]))


class CommentItem(QGraphicsTextItem):
    """Movable annotation with reliable inline and dialog-based editing."""

    def __init__(self, text: str = "Comment", item_id: str | None = None) -> None:
        super().__init__(text)
        self.item_id = item_id or uuid.uuid4().hex
        self._text_before_edit = text
        self._editing = False
        self.setDefaultTextColor(QColor("#f0d77c"))
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(2)
        self.setToolTip("Double-click to edit this comment")

    def begin_edit(self) -> None:
        self._editing = True
        self._text_before_edit = self.toPlainText()
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        cursor = self.textCursor()
        cursor.select(QTextCursor.SelectionType.Document)
        self.setTextCursor(cursor)

    def finish_edit(self, *, accept: bool = True) -> None:
        if not self._editing:
            return
        if not accept:
            self.setPlainText(self._text_before_edit)
        self._editing = False
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        self.clearFocus()
        scene = self.scene()
        if isinstance(scene, WorkflowScene) and not scene.loading:
            scene.graph_changed.emit()

    def edit_in_dialog(self) -> None:
        parent = self.scene().views()[0] if self.scene() and self.scene().views() else None
        text, accepted = QInputDialog.getMultiLineText(parent, "Edit Comment", "Comment text:", self.toPlainText())
        if accepted:
            self.setPlainText(text)
            scene = self.scene()
            if isinstance(scene, WorkflowScene) and not scene.loading:
                scene.graph_changed.emit()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.begin_edit()
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if self._editing and event.key() == Qt.Key.Key_Escape:
            self.finish_edit(accept=False)
            event.accept()
            return
        if self._editing and event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter} and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.finish_edit()
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu()
        edit = menu.addAction("Edit Comment…")
        delete = menu.addAction("Delete")
        selected = menu.exec(event.screenPos())
        if selected == edit:
            self.edit_in_dialog()
        elif selected == delete:
            self.setSelected(True)
            scene = self.scene()
            if isinstance(scene, WorkflowScene):
                scene.delete_selected()

    def itemChange(self, change, value):  # noqa: N802
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            scene = self.scene()
            if isinstance(scene, WorkflowScene) and not scene.loading:
                scene.graph_changed.emit()
        return result

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self.finish_edit()


class GroupPropertiesDialog(QDialog):
    def __init__(self, title: str, width: float, height: float, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Group Properties")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.title_edit = QLineEdit(title)
        self.width_edit = QDoubleSpinBox(); self.width_edit.setRange(160.0, 5000.0); self.width_edit.setDecimals(0); self.width_edit.setSuffix(" px"); self.width_edit.setValue(width)
        self.height_edit = QDoubleSpinBox(); self.height_edit.setRange(100.0, 5000.0); self.height_edit.setDecimals(0); self.height_edit.setSuffix(" px"); self.height_edit.setValue(height)
        form.addRow("Name", self.title_edit); form.addRow("Width", self.width_edit); form.addRow("Height", self.height_edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def values(self) -> tuple[str, float, float]:
        return self.title_edit.text().strip() or "Group", self.width_edit.value(), self.height_edit.value()


class GroupResizeHandle(QGraphicsRectItem):
    SIZE = 14.0

    def __init__(self, group: "GroupItem") -> None:
        super().__init__(-self.SIZE / 2, -self.SIZE / 2, self.SIZE, self.SIZE, group)
        self.group = group
        self.setBrush(QBrush(QColor("#9fc7e4")))
        self.setPen(QPen(QColor("#355a73"), 1.0))
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setZValue(10)
        self.setVisible(False)
        self._resizing = False

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._resizing = True
            self.group.setSelected(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._resizing:
            local = self.group.mapFromScene(event.scenePos())
            self.group.set_group_size(local.x(), local.y(), emit=False)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if self._resizing and event.button() == Qt.MouseButton.LeftButton:
            self._resizing = False
            scene = self.group.scene()
            if isinstance(scene, WorkflowScene) and not scene.loading:
                scene.graph_changed.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)


class GroupItem(QGraphicsRectItem):
    MIN_WIDTH = 160.0
    MIN_HEIGHT = 100.0

    def __init__(self, title: str = "Group", item_id: str | None = None, size: tuple[float, float] = (500.0, 300.0)) -> None:
        super().__init__(0, 0, max(self.MIN_WIDTH, size[0]), max(self.MIN_HEIGHT, size[1]))
        self.item_id = item_id or uuid.uuid4().hex
        self.title = title or "Group"
        self.setBrush(QBrush(QColor(55, 75, 95, 45)))
        self.setPen(QPen(QColor("#607f99"), 1.5, Qt.PenStyle.DashLine))
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setZValue(-2)
        self.label_item = QGraphicsTextItem(self.title, self)
        self.label_item.setDefaultTextColor(QColor("#9fc7e4")); self.label_item.setPos(8, 4)
        self.label_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.resize_handle = GroupResizeHandle(self)
        self._position_handle()
        self.setToolTip("Double-click to rename; drag the bottom-right handle to resize")

    def _position_handle(self) -> None:
        self.resize_handle.setPos(self.rect().bottomRight())

    def set_title(self, title: str, *, emit: bool = True) -> None:
        self.title = title.strip() or "Group"
        self.label_item.setPlainText(self.title)
        scene = self.scene()
        if emit and isinstance(scene, WorkflowScene) and not scene.loading:
            scene.graph_changed.emit()

    def set_group_size(self, width: float, height: float, *, emit: bool = True) -> None:
        width = max(self.MIN_WIDTH, float(width)); height = max(self.MIN_HEIGHT, float(height))
        self.setRect(0, 0, width, height)
        self._position_handle()
        scene = self.scene()
        if emit and isinstance(scene, WorkflowScene) and not scene.loading:
            scene.graph_changed.emit()

    def edit_properties(self) -> None:
        parent = self.scene().views()[0] if self.scene() and self.scene().views() else None
        dialog = GroupPropertiesDialog(self.title, self.rect().width(), self.rect().height(), parent)
        if dialog.exec():
            title, width, height = dialog.values()
            self.set_title(title, emit=False)
            self.set_group_size(width, height, emit=False)
            scene = self.scene()
            if isinstance(scene, WorkflowScene) and not scene.loading:
                scene.graph_changed.emit()

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802
        self.edit_properties()
        event.accept()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = QMenu()
        edit = menu.addAction("Group Properties…")
        delete = menu.addAction("Delete")
        selected = menu.exec(event.screenPos())
        if selected == edit:
            self.edit_properties()
        elif selected == delete:
            self.setSelected(True)
            scene = self.scene()
            if isinstance(scene, WorkflowScene):
                scene.delete_selected()

    def itemChange(self, change, value):  # noqa: N802
        result = super().itemChange(change, value)
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged and hasattr(self, "resize_handle"):
            self.resize_handle.setVisible(bool(value))
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            scene = self.scene()
            if isinstance(scene, WorkflowScene) and not scene.loading:
                scene.graph_changed.emit()
        return result


@dataclass(frozen=True, slots=True)
class ConnectionRecord:
    source_id: str
    source_port: int
    target_id: str
    target_port: int


class WorkflowScene(QGraphicsScene):
    node_selected = Signal(object)
    result_requested = Signal(str)
    graph_changed = Signal()
    message = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setSceneRect(-5000, -5000, 10000, 10000)
        self.nodes: dict[str, NodeItem] = {}
        self.connections: list[ConnectionItem] = []
        self.comments: dict[str, CommentItem] = {}
        self.groups: dict[str, GroupItem] = {}
        self.pending_output: PortItem | None = None
        self.pending_input: PortItem | None = None
        self._drag_item: PendingConnectionItem | None = None
        self._drag_source: PortItem | None = None
        self._drag_target: PortItem | None = None
        self.snap_to_grid = True
        self.loading = False
        self._clipboard: dict[str, Any] | None = None

    def create_node(self, type_name: str, position: QPointF, *, node_id: str | None = None, params: dict[str, Any] | None = None, label: str = "", emit: bool = True) -> NodeItem:
        if params is None:
            from app.application import settings
            defaults = settings()
            block_cls = BLOCK_TYPES[type_name]
            generated = {spec.name: spec.default for spec in block_cls.parameters}
            if "sample_rate" in generated:
                generated["sample_rate"] = defaults.value("defaults/sample_rate", generated["sample_rate"], type=float)
            if "unit" in generated:
                generated["unit"] = defaults.value("defaults/unit", generated["unit"], type=str)
            params = generated
        node = NodeItem(type_name, node_id=node_id, params=params, label=label)
        node.setPos(position); self.addItem(node); self.nodes[node.node_id] = node
        if emit and not self.loading: self.graph_changed.emit()
        return node

    def create_comment(self, position: QPointF, text: str = "Comment", *, item_id: str | None = None, emit: bool = True) -> CommentItem:
        item = CommentItem(text, item_id); item.setPos(position); self.addItem(item); self.comments[item.item_id] = item
        if emit and not self.loading: self.graph_changed.emit()
        return item

    def create_group(self, position: QPointF, title: str = "Group", *, item_id: str | None = None, size: tuple[float, float] = (500.0, 300.0), emit: bool = True) -> GroupItem:
        item = GroupItem(title, item_id, size); item.setPos(position); self.addItem(item); self.groups[item.item_id] = item
        if emit and not self.loading: self.graph_changed.emit()
        return item

    def _would_create_cycle(self, source_id: str, target_id: str) -> bool:
        downstream: dict[str, list[str]] = {}
        for record in self.connection_records():
            downstream.setdefault(record.source_id, []).append(record.target_id)
        downstream.setdefault(source_id, []).append(target_id)
        stack, visited = [target_id], set()
        while stack:
            current = stack.pop()
            if current == source_id: return True
            if current in visited: continue
            visited.add(current); stack.extend(downstream.get(current, []))
        return False

    def _clear_port_interaction(self) -> None:
        for port in (self.pending_output, self.pending_input, self._drag_source, self._drag_target):
            if port is not None:
                port.set_active(False)
                port.set_drag_target(False)
        self.pending_output = None
        self.pending_input = None
        self._drag_source = None
        self._drag_target = None
        if self._drag_item is not None:
            self.removeItem(self._drag_item)
            self._drag_item = None

    def _select_pending_port(self, port: PortItem) -> None:
        self._clear_port_interaction()
        if port.kind == "output":
            self.pending_output = port
            self.message.emit(f"Select or drag to an input for {port.node.block.display_name}.")
        else:
            self.pending_input = port
            self.message.emit(f"Select or drag from an output for {port.node.block.display_name}.")
        port.set_active(True)

    def _connection_error(self, source: PortItem, target: PortItem) -> str | None:
        if source.node is target.node:
            return "A block cannot connect to itself."
        if any(connection.target is target for connection in self.connections):
            return "That input is already connected."
        if target.data_type != "any" and source.data_type != target.data_type:
            return f"Incompatible connection: {source.data_type} cannot feed {target.data_type}."
        if self._would_create_cycle(source.node.node_id, target.node.node_id):
            return "Connection rejected because it would create a circular dependency."
        return None

    def _connect_ports(self, first: PortItem, second: PortItem) -> bool:
        if first.kind == second.kind:
            self.message.emit("Connect an output port to an input port.")
            return False
        source, target = (first, second) if first.kind == "output" else (second, first)
        error = self._connection_error(source, target)
        if error:
            self.message.emit(error)
            return False
        self.add_connection(source.node.node_id, source.index, target.node.node_id, target.index)
        self.message.emit(f"Connected {source.node.block.display_name} to {target.node.block.display_name}.")
        return True

    def port_clicked(self, port: PortItem) -> None:
        """Handle the existing two-click connection workflow in either direction."""
        counterpart = self.pending_input if port.kind == "output" else self.pending_output
        current = self.pending_output if port.kind == "output" else self.pending_input
        if current is port:
            self._clear_port_interaction()
            self.message.emit("Connection selection cancelled.")
            return
        if counterpart is None:
            self._select_pending_port(port)
            return
        self._connect_ports(port, counterpart)
        self._clear_port_interaction()

    def _port_at(self, position: QPointF, *, exclude: PortItem | None = None) -> PortItem | None:
        for item in self.items(position):
            if isinstance(item, PortItem) and item is not exclude:
                return item
        return None

    def begin_connection_drag(self, source: PortItem) -> None:
        self._clear_port_interaction()
        self._drag_source = source
        source.set_active(True)
        self._drag_item = PendingConnectionItem(source)
        self.addItem(self._drag_item)
        self.message.emit("Drag the cable onto a compatible port, or release on empty space to keep click-to-connect active.")

    def update_connection_drag(self, position: QPointF) -> None:
        if self._drag_item is None or self._drag_source is None:
            return
        self._drag_item.update_to(position)
        candidate = self._port_at(position, exclude=self._drag_source)
        if candidate is not None and candidate.kind == self._drag_source.kind:
            candidate = None
        if candidate is self._drag_target:
            return
        if self._drag_target is not None:
            self._drag_target.set_drag_target(False)
        self._drag_target = candidate
        if candidate is not None:
            candidate.set_drag_target(True)

    def finish_connection_drag(self, position: QPointF) -> None:
        source = self._drag_source
        candidate = self._port_at(position, exclude=source) if source is not None else None
        if candidate is not None and source is not None and candidate.kind != source.kind:
            self._connect_ports(source, candidate)
            self._clear_port_interaction()
            return
        # Releasing away from a port gracefully falls back to the click workflow.
        if source is not None:
            self._select_pending_port(source)
        else:
            self._clear_port_interaction()

    def cancel_connection_interaction(self) -> None:
        self._clear_port_interaction()
        self.message.emit("Connection selection cancelled.")

    def add_connection(self, source_id: str, source_port: int, target_id: str, target_port: int, *, emit: bool = True) -> ConnectionItem:
        source_node, target_node = self.nodes[source_id], self.nodes[target_id]
        if source_port >= len(source_node.output_ports) or target_port >= len(target_node.input_ports):
            raise ValueError("Connection references an unavailable port.")
        if any(c.target.node.node_id == target_id and c.target.index == target_port for c in self.connections):
            raise ValueError("That target port is already connected.")
        source, target = source_node.output_ports[source_port], target_node.input_ports[target_port]
        if target.data_type != "any" and source.data_type != target.data_type:
            raise ValueError(f"Incompatible port types: {source.data_type} → {target.data_type}")
        if self._would_create_cycle(source_id, target_id):
            raise ValueError("Connection would create a cycle.")
        item = ConnectionItem(source, target); self.addItem(item); self.connections.append(item)
        if emit and not self.loading: self.graph_changed.emit()
        return item

    def update_connections_for_node(self, node_id: str) -> None:
        for connection in self.connections:
            if connection.source.node.node_id == node_id or connection.target.node.node_id == node_id:
                connection.update_path()

    def selected_nodes(self) -> list[NodeItem]:
        return [item for item in self.selectedItems() if isinstance(item, NodeItem)]

    def delete_selected(self) -> None:
        selected = list(self.selectedItems())
        selected_connections = [item for item in selected if isinstance(item, ConnectionItem)]
        selected_nodes = [item for item in selected if isinstance(item, NodeItem)]
        selected_comments = [item for item in selected if isinstance(item, CommentItem)]
        selected_groups = [item for item in selected if isinstance(item, GroupItem)]
        node_ids = {node.node_id for node in selected_nodes}
        interaction_ports = (self.pending_output, self.pending_input, self._drag_source, self._drag_target)
        if any(port is not None and port.node.node_id in node_ids for port in interaction_ports):
            self._clear_port_interaction()
        selected_connections.extend(c for c in self.connections if c.source.node.node_id in node_ids or c.target.node.node_id in node_ids)
        for connection in set(selected_connections):
            if connection in self.connections: self.connections.remove(connection)
            self.removeItem(connection)
        for node in selected_nodes: self.nodes.pop(node.node_id, None); self.removeItem(node)
        for item in selected_comments: self.comments.pop(item.item_id, None); self.removeItem(item)
        for item in selected_groups: self.groups.pop(item.item_id, None); self.removeItem(item)
        if selected: self.graph_changed.emit()

    def copy_selected(self) -> None:
        nodes = self.selected_nodes()
        ids = {node.node_id for node in nodes}
        self._clipboard = {
            "nodes": [{"old_id": n.node_id, "type": n.block_type, "position": [n.pos().x(), n.pos().y()], "parameters": copy.deepcopy(n.params), "label": n.custom_label} for n in nodes],
            "connections": [
                {
                    "source_id": record.source_id,
                    "source_port": record.source_port,
                    "target_id": record.target_id,
                    "target_port": record.target_port,
                }
                for record in self.connection_records()
                if record.source_id in ids and record.target_id in ids
            ],
        }
        self.message.emit(f"Copied {len(nodes)} block(s).")

    def paste(self, offset: QPointF = QPointF(35, 35)) -> list[NodeItem]:
        if not self._clipboard: return []
        self.clearSelection(); id_map: dict[str, str] = {}; created: list[NodeItem] = []
        for raw in self._clipboard["nodes"]:
            node = self.create_node(raw["type"], QPointF(raw["position"][0], raw["position"][1]) + offset, params=copy.deepcopy(raw["parameters"]), label=raw.get("label", ""), emit=False)
            id_map[raw["old_id"]] = node.node_id; node.setSelected(True); created.append(node)
        for raw in self._clipboard["connections"]:
            self.add_connection(id_map[raw["source_id"]], int(raw["source_port"]), id_map[raw["target_id"]], int(raw["target_port"]), emit=False)
        if created: self.graph_changed.emit()
        return created

    def duplicate_selected(self) -> list[NodeItem]:
        self.copy_selected(); return self.paste()

    def align_selected(self, mode: str) -> None:
        nodes = self.selected_nodes()
        if len(nodes) < 2: return
        if mode == "left": value = min(n.x() for n in nodes); [n.setX(value) for n in nodes]
        elif mode == "right": value = max(n.x() + NODE_WIDTH for n in nodes); [n.setX(value - NODE_WIDTH) for n in nodes]
        elif mode == "top": value = min(n.y() for n in nodes); [n.setY(value) for n in nodes]
        elif mode == "bottom": value = max(n.y() + NODE_HEIGHT for n in nodes); [n.setY(value - NODE_HEIGHT) for n in nodes]
        elif mode == "horizontal": value = sum(n.y() for n in nodes) / len(nodes); [n.setY(value) for n in nodes]
        elif mode == "vertical": value = sum(n.x() for n in nodes) / len(nodes); [n.setX(value) for n in nodes]
        self.graph_changed.emit()

    def distribute_selected(self, horizontal: bool) -> None:
        nodes = self.selected_nodes()
        if len(nodes) < 3: return
        nodes.sort(key=lambda n: n.x() if horizontal else n.y())
        first = nodes[0].x() if horizontal else nodes[0].y(); last = nodes[-1].x() if horizontal else nodes[-1].y()
        step = (last - first) / (len(nodes) - 1)
        for index, node in enumerate(nodes[1:-1], 1):
            if horizontal: node.setX(first + index * step)
            else: node.setY(first + index * step)
        self.graph_changed.emit()

    def tidy_workflow(self) -> None:
        if not self.nodes: return
        incoming = {node_id: 0 for node_id in self.nodes}; downstream: dict[str, list[str]] = {}
        for record in self.connection_records():
            incoming[record.target_id] += 1; downstream.setdefault(record.source_id, []).append(record.target_id)
        queue = [(node_id, 0) for node_id, degree in incoming.items() if degree == 0]
        levels: dict[int, list[str]] = {}; visited = set()
        while queue:
            node_id, level = queue.pop(0)
            if node_id in visited: continue
            visited.add(node_id); levels.setdefault(level, []).append(node_id)
            for child in downstream.get(node_id, []): queue.append((child, level + 1))
        for node_id in self.nodes:
            if node_id not in visited: levels.setdefault(0, []).append(node_id)
        for level, node_ids in levels.items():
            for row, node_id in enumerate(sorted(node_ids)):
                self.nodes[node_id].setPos(level * 300.0, row * 145.0)
        self.graph_changed.emit()

    def clear_workflow(self, *, emit: bool = True) -> None:
        self._clear_port_interaction()
        self.clear(); self.nodes.clear(); self.connections.clear(); self.comments.clear(); self.groups.clear(); self.pending_output = None; self.pending_input = None
        if emit and not self.loading: self.graph_changed.emit()

    def connection_records(self) -> list[ConnectionRecord]:
        return [ConnectionRecord(item.source.node.node_id, item.source.index, item.target.node.node_id, item.target.index) for item in self.connections]

    def comment_records(self) -> list[dict[str, Any]]:
        return [{"id": item.item_id, "text": item.toPlainText(), "position": [item.pos().x(), item.pos().y()]} for item in self.comments.values()]

    def group_records(self) -> list[dict[str, Any]]:
        return [{"id": item.item_id, "title": item.title, "position": [item.pos().x(), item.pos().y()], "size": [item.rect().width(), item.rect().height()]} for item in self.groups.values()]


class WorkflowView(QGraphicsView):
    def __init__(self, scene: WorkflowScene, parent=None) -> None:
        super().__init__(scene, parent)
        self.setAcceptDrops(True); self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._dark_theme = True
        self.setBackgroundBrush(QBrush(QColor("#171c22")))
        self._panning = False; self._last_pan = QPointF()

    def set_theme(self, dark: bool) -> None:
        self._dark_theme = bool(dark)
        self.setBackgroundBrush(QBrush(QColor("#171c22" if dark else "#f4f6f8")))
        self.viewport().update()

    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        super().drawBackground(painter, rect)
        left = math.floor(rect.left() / GRID_SIZE) * GRID_SIZE; top = math.floor(rect.top() / GRID_SIZE) * GRID_SIZE
        grid_colour = QColor("#242b33" if self._dark_theme else "#e2e7ec")
        painter.setPen(QPen(grid_colour, 1))
        x = left
        while x < rect.right(): painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom())); x += GRID_SIZE
        y = top
        while y < rect.bottom(): painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y)); y += GRID_SIZE

    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(MIME_TYPE): event.acceptProposedAction()
        else: super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if event.mimeData().hasFormat(MIME_TYPE): event.acceptProposedAction()
        else: super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # noqa: N802
        if not event.mimeData().hasFormat(MIME_TYPE): super().dropEvent(event); return
        stream = QDataStream(event.mimeData().data(MIME_TYPE), QIODevice.OpenModeFlag.ReadOnly)
        type_name = stream.readQString(); scene = self.scene()
        if isinstance(scene, WorkflowScene): scene.create_node(type_name, self.mapToScene(event.position().toPoint()))
        event.acceptProposedAction()

    def wheelEvent(self, event) -> None:  # noqa: N802
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15; self.scale(factor, factor)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True; self._last_pan = event.position(); self.setCursor(Qt.CursorShape.ClosedHandCursor); event.accept(); return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._panning:
            delta = event.position() - self._last_pan; self._last_pan = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - int(delta.x())); self.verticalScrollBar().setValue(self.verticalScrollBar().value() - int(delta.y())); event.accept(); return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False; self.unsetCursor(); event.accept(); return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        scene = self.scene()
        if isinstance(scene, WorkflowScene):
            if event.key() == Qt.Key.Key_Escape: scene.cancel_connection_interaction(); return
            if event.key() == Qt.Key.Key_F2:
                selected = scene.selectedItems()
                if len(selected) == 1 and isinstance(selected[0], CommentItem): selected[0].begin_edit(); return
                if len(selected) == 1 and isinstance(selected[0], GroupItem): selected[0].edit_properties(); return
            if event.key() in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}: scene.delete_selected(); return
            if event.matches(QKeySequence.StandardKey.Copy): scene.copy_selected(); return
            if event.matches(QKeySequence.StandardKey.Paste): scene.paste(); return
        super().keyPressEvent(event)
