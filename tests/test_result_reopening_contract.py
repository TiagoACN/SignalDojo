# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_result_docks_are_kept_alive_and_have_a_restore_menu() -> None:
    source = (ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert "WA_DeleteOnClose, False" in source
    assert 'view_menu.addMenu("Results")' in source
    assert "def show_result_for_node" in source
    assert "def show_all_results" in source
    assert "def hide_all_results" in source
    assert "def _rebuild_results_menu" in source
    assert "dock.toggleViewAction()" in source
    assert "dock.setVisible(True)" in source


def test_display_blocks_can_request_their_latest_result() -> None:
    source = (ROOT / "app" / "ui" / "node_editor.py").read_text(encoding="utf-8")
    assert "RESULT_BLOCK_TYPES" in source
    assert 'result_requested = Signal(str)' in source
    assert 'menu.addAction("Open Latest Result")' in source
    assert "def mouseDoubleClickEvent" in source


def test_results_menu_includes_registered_docks_without_saved_records() -> None:
    source = (ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
    assert "def _available_result_ids" in source
    assert "set(self._display_results) | set(self._result_docks)" in source
    assert "result_ids = self._available_result_ids()" in source
    assert "for node_id in sorted(result_ids" in source
