# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Dynamic properties editor generated from block parameter schemas."""

from __future__ import annotations

from functools import partial
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.core.blocks import ParameterSpec, create_block
from app.ui.node_editor import NodeItem


class PropertiesPanel(QScrollArea):
    parameters_changed = Signal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._node: NodeItem | None = None
        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.addWidget(QLabel("Select a block to edit its settings."))
        self._layout.addStretch(1)
        self.setWidget(self._container)

    def show_node(self, node: NodeItem) -> None:
        self._node = node
        self._clear()
        title = QLabel(node.block.display_name)
        font = title.font(); font.setPointSize(font.pointSize() + 2); font.setBold(True); title.setFont(font)
        self._layout.addWidget(title)
        description = QLabel(node.block.description); description.setWordWrap(True); self._layout.addWidget(description)

        label_form = QFormLayout()
        label_editor = QLineEdit(node.custom_label)
        label_editor.setPlaceholderText(node.block.display_name)
        label_editor.editingFinished.connect(lambda: self._commit_label(label_editor.text()))
        label_form.addRow("Custom label", label_editor)
        self._layout.addLayout(label_form)

        normal_specs = [
            spec for spec in node.block.parameters
            if not spec.advanced and spec.is_visible(node.params)
        ]
        advanced_specs = [
            spec for spec in node.block.parameters
            if spec.advanced and spec.is_visible(node.params)
        ]
        self._add_form(normal_specs)
        if advanced_specs:
            button = QToolButton(); button.setText("Advanced settings"); button.setCheckable(True); button.setArrowType(Qt.ArrowType.RightArrow)
            advanced_container = QWidget(); advanced_container.setVisible(False)
            advanced_layout = QVBoxLayout(advanced_container); advanced_layout.setContentsMargins(0, 0, 0, 0)
            form = QFormLayout(); form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            for spec in advanced_specs:
                editor = self._make_editor(spec, node.params.get(spec.name, spec.default)); form.addRow(self._label(spec), editor)
            advanced_layout.addLayout(form)
            def toggle(checked: bool) -> None:
                advanced_container.setVisible(checked); button.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
            button.toggled.connect(toggle); self._layout.addWidget(button); self._layout.addWidget(advanced_container)

        reset = QPushButton("Reset block parameters")
        reset.clicked.connect(self._reset)
        self._layout.addWidget(reset)
        self._layout.addStretch(1)

    def _add_form(self, specs: list[ParameterSpec]) -> None:
        form = QFormLayout(); form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for spec in specs:
            editor = self._make_editor(spec, self._node.params.get(spec.name, spec.default) if self._node else spec.default)
            form.addRow(self._label(spec), editor)
        self._layout.addLayout(form)

    @staticmethod
    def _label(spec: ParameterSpec) -> QLabel:
        label = QLabel(spec.label)
        if spec.help_text: label.setToolTip(spec.help_text)
        return label

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None: widget.deleteLater()
            child_layout = item.layout()
            if child_layout is not None:
                while child_layout.count():
                    child = child_layout.takeAt(0)
                    if child.widget(): child.widget().deleteLater()

    def _make_editor(self, spec: ParameterSpec, value: Any) -> QWidget:
        if spec.kind in {"open_file", "save_file"}:
            wrapper = QWidget(); layout = QHBoxLayout(wrapper); layout.setContentsMargins(0, 0, 0, 0)
            line = QLineEdit(str(value)); line.editingFinished.connect(partial(self._commit_text, spec.name, line))
            button = QPushButton("Browse…"); button.clicked.connect(partial(self._browse_file, spec, line))
            layout.addWidget(line, 1); layout.addWidget(button); return wrapper
        if spec.kind == "multiline":
            editor = QPlainTextEdit(str(value)); editor.setMaximumHeight(120)
            editor.textChanged.connect(partial(self._commit_multiline, spec.name, editor)); return editor
        if spec.kind == "text":
            editor = QLineEdit(str(value)); editor.editingFinished.connect(partial(self._commit_text, spec.name, editor)); return editor
        if spec.kind == "float":
            editor = QDoubleSpinBox(); editor.setDecimals(10); editor.setKeyboardTracking(False)
            editor.setRange(float(spec.minimum if spec.minimum is not None else -1e15), float(spec.maximum if spec.maximum is not None else 1e15))
            editor.setValue(float(value)); editor.valueChanged.connect(partial(self._commit, spec.name)); return editor
        if spec.kind == "int":
            editor = QSpinBox(); editor.setKeyboardTracking(False)
            editor.setRange(int(spec.minimum if spec.minimum is not None else -2_000_000_000), int(spec.maximum if spec.maximum is not None else 2_000_000_000))
            editor.setValue(int(value)); editor.valueChanged.connect(partial(self._commit, spec.name)); return editor
        if spec.kind == "bool":
            editor = QCheckBox(); editor.setChecked(bool(value)); editor.toggled.connect(partial(self._commit, spec.name)); return editor
        if spec.kind == "choice":
            editor = QComboBox(); editor.addItems(list(spec.choices)); editor.setCurrentText(str(value)); editor.currentTextChanged.connect(partial(self._commit, spec.name)); return editor
        return QLabel(str(value))

    def _browse_file(self, spec: ParameterSpec, line: QLineEdit) -> None:
        file_filter = spec.file_filter or "All files (*)"
        if spec.kind == "open_file":
            path, _ = QFileDialog.getOpenFileName(self, "Choose input file", line.text(), f"{file_filter};;All files (*)")
        else:
            path, _ = QFileDialog.getSaveFileName(self, "Choose output file", line.text(), file_filter)
        if path:
            line.setText(path); self._commit(spec.name, path)

    def _commit_text(self, name: str, editor: QLineEdit) -> None:
        self._commit(name, editor.text())

    def _commit_multiline(self, name: str, editor: QPlainTextEdit) -> None:
        self._commit(name, editor.toPlainText())

    def _commit_label(self, label: str) -> None:
        if self._node is None: return
        self._node.set_label(label); self.parameters_changed.emit(self._node)

    def _reset(self) -> None:
        if self._node is None: return
        self._node.block = create_block(self._node.block_type)
        self._node.params = self._node.block.serialise_params()
        self.show_node(self._node); self.parameters_changed.emit(self._node)

    def _commit(self, name: str, value: Any) -> None:
        if self._node is None: return
        self._node.params[name] = value
        self._node.block = create_block(self._node.block_type, self._node.params)
        # Mode-dependent schemas (for example low/high/band filters and automatic
        # unit conversion) must update immediately when their controlling field is
        # changed.  Rebuilding only when another parameter depends on this field
        # avoids disturbing ordinary numeric editing.
        if any(
            any(dependency == name for dependency, _accepted in spec.visible_when)
            for spec in self._node.block.parameters
        ):
            self.show_node(self._node)
        self.parameters_changed.emit(self._node)
