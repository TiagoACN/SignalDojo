# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Regression tests for workflow-canvas partial repaint artefacts.

These checks deliberately avoid importing PySide6 so they also run in headless
source-validation environments. The Qt UI smoke suite performs the corresponding
runtime assertions when PySide6 is installed.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE_EDITOR = ROOT / "app" / "ui" / "node_editor.py"


def _source() -> str:
    return NODE_EDITOR.read_text(encoding="utf-8")


def test_moving_nodes_invalidate_complete_child_paint_region() -> None:
    source = _source()
    assert "def _visual_scene_bounds(self) -> QRectF:" in source
    assert "self.childrenBoundingRect()" in source
    assert "self._previous_visual_scene_bounds = self._visual_scene_bounds()" in source
    assert "scene.update(dirty)" in source


def test_workflow_view_uses_smart_partial_updates() -> None:
    source = _source()
    assert "QGraphicsView.ViewportUpdateMode.SmartViewportUpdate" in source
    assert "QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate" not in source


def test_connection_bounds_cover_custom_arrowhead() -> None:
    source = _source()
    assert "_ARROW_PAINT_MARGIN = 13.0" in source
    assert "def boundingRect(self) -> QRectF" in source
    assert "super().boundingRect().adjusted(-margin, -margin, margin, margin)" in source
