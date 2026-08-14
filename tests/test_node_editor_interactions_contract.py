# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Headless source contracts for the interactive canvas additions.

The real Qt smoke tests exercise these paths when PySide6 is installed. These checks
ensure release validation still catches accidental removal on non-Qt build hosts.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE_EDITOR = (ROOT / "app" / "ui" / "node_editor.py").read_text(encoding="utf-8")
MAIN_WINDOW = (ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
PROJECT_IO = (ROOT / "app" / "project" / "io.py").read_text(encoding="utf-8")


def test_comments_support_inline_and_dialog_editing() -> None:
    assert "def begin_edit(self)" in NODE_EDITOR
    assert "QInputDialog.getMultiLineText" in NODE_EDITOR
    assert 'menu.addAction("Edit Comment…")' in NODE_EDITOR
    assert "Qt.TextInteractionFlag.TextEditorInteraction" in NODE_EDITOR


def test_groups_support_name_and_size_editing() -> None:
    assert "class GroupPropertiesDialog" in NODE_EDITOR
    assert "class GroupResizeHandle" in NODE_EDITOR
    assert "def set_title(self, title: str" in NODE_EDITOR
    assert "def set_group_size(self, width: float, height: float" in NODE_EDITOR
    assert "SizeFDiagCursor" in NODE_EDITOR


def test_ports_support_highlighting_click_and_drag_connection_modes() -> None:
    assert '_ACTIVE_COLOUR = QColor("#ffbf47")' in NODE_EDITOR
    assert "def port_clicked(self, port: PortItem)" in NODE_EDITOR
    assert "def begin_connection_drag(self, source: PortItem)" in NODE_EDITOR
    assert "def update_connection_drag(self, position: QPointF)" in NODE_EDITOR
    assert "def finish_connection_drag(self, position: QPointF)" in NODE_EDITOR
    assert "class PendingConnectionItem" in NODE_EDITOR


def test_light_theme_uses_a_light_grid_colour() -> None:
    assert '"#242b33" if self._dark_theme else "#e2e7ec"' in NODE_EDITOR
    assert "self.view.set_theme(dark)" in MAIN_WINDOW


def test_projects_persist_and_restore_display_results() -> None:
    assert 'PROJECT_VERSION = 4' in PROJECT_IO
    assert '"results": persisted_results' in MAIN_WINDOW
    assert "serialise_display_record(record)" in MAIN_WINDOW
    assert "def _restore_persisted_results" in MAIN_WINDOW
    assert "deserialise_display_record" in MAIN_WINDOW
