# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
import pytest

pytest.importorskip("PySide6", reason="PySide6 is installed by the Windows development/build environment")
pytest.importorskip("pyqtgraph", reason="pyqtgraph is installed by the Windows development/build environment")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication, QGraphicsView

from app.core.models import SignalData, TableResult
from app.ui.main_window import MainWindow
from app.ui.node_editor import CommentItem, GroupItem, NODE_WIDTH, WorkflowScene, WorkflowView
from app.ui.results import TableDock
from app.ui.scope import ScopeDock


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_node_scene_editing_and_clipboard(qapp: QApplication) -> None:
    scene = WorkflowScene()
    source = scene.create_node("constant", QPointF(0, 0))
    gain = scene.create_node("gain", QPointF(300, 0))
    scene.add_connection(source.node_id, 0, gain.node_id, 0)
    source.setSelected(True); gain.setSelected(True)
    scene.copy_selected()
    pasted = scene.paste()
    assert len(pasted) == 2
    assert len(scene.connections) == 2
    scene.tidy_workflow()


def test_main_window_constructs_and_serialises(qapp: QApplication) -> None:
    window = MainWindow()
    window.scene.create_node("sine", QPointF(0, 0))
    document = window._project_payload(relative_paths=False)  # noqa: SLF001 - UI smoke test
    assert document["nodes"][0]["type"] == "sine"
    assert document["view"]["window_state"]
    window.deleteLater()


def test_scope_widget_constructs_with_advanced_controls(qapp: QApplication) -> None:
    time = np.arange(1000, dtype=float) / 1000
    signal = SignalData(np.sin(2 * np.pi * 5 * time), time, name="Scope test", unit="V", sample_rate=1000)
    dock = ScopeDock(
        "Scope",
        [signal],
        1000,
        show_markers=True,
        show_peaks=True,
        auto_scale=False,
        x_min="0",
        x_max="1",
        y_min="-2",
        y_max="2",
    )
    assert dock.trace_menu.actions()[0].text() == "Scope test"
    dock.deleteLater()


def test_node_move_rendering_bounds_include_ports(qapp: QApplication) -> None:
    scene = WorkflowScene()
    node = scene.create_node("constant", QPointF(0, 0))
    local_visual_bounds = node.boundingRect().united(node.childrenBoundingRect())
    assert local_visual_bounds.left() < 0
    assert local_visual_bounds.right() > NODE_WIDTH

    view = WorkflowView(scene)
    assert view.viewportUpdateMode() == QGraphicsView.ViewportUpdateMode.SmartViewportUpdate
    node.setPos(125, 75)
    qapp.processEvents()
    view.deleteLater()


def test_closed_result_dock_can_be_restored(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(MainWindow, "_initial_prompts", lambda self: None)
    window = MainWindow()
    # QWidget.isVisible() includes ancestor visibility. The application normally
    # shows MainWindow before the user can close or restore a result dock, so the
    # smoke test must exercise the same lifecycle rather than testing a child of
    # a permanently hidden parent.
    window.resize(1024, 720)
    window.show()
    qapp.processEvents()
    node = window.scene.create_node("data_table", QPointF(0, 0))
    dock = TableDock("Data Table", SignalData(np.arange(8, dtype=float), np.arange(8, dtype=float), sample_rate=1.0), 100, window)
    window._replace_result_dock(node.node_id, dock)  # noqa: SLF001 - result lifecycle smoke test
    qapp.processEvents()

    dock.close()
    qapp.processEvents()
    assert not dock.isVisible()
    assert node.node_id in window._result_docks  # noqa: SLF001

    window.show_result_for_node(node.node_id)
    qapp.processEvents()
    assert not dock.isHidden()
    assert dock.isVisible()
    assert dock.toggleViewAction().isChecked()

    window._rebuild_results_menu()  # noqa: SLF001
    assert any("Data Table" in action.text() for action in window.results_menu.actions())
    window.hide()
    window.deleteLater()
    qapp.processEvents()


def test_comment_and_group_annotations_are_editable(qapp: QApplication) -> None:
    scene = WorkflowScene()
    comment = scene.create_comment(QPointF(10, 20), "Original")
    assert isinstance(comment, CommentItem)
    comment.setPlainText("Edited")
    assert scene.comment_records()[0]["text"] == "Edited"

    group = scene.create_group(QPointF(0, 0), "Original group", size=(300, 200))
    assert isinstance(group, GroupItem)
    group.set_title("Renamed group")
    group.set_group_size(640, 360)
    record = scene.group_records()[0]
    assert record["title"] == "Renamed group"
    assert record["size"] == [640.0, 360.0]


def test_ports_support_click_selection_and_drag_setup(qapp: QApplication) -> None:
    scene = WorkflowScene()
    source = scene.create_node("constant", QPointF(0, 0))
    target = scene.create_node("gain", QPointF(300, 0))
    output_port = source.output_ports[0]
    input_port = target.input_ports[0]

    scene.port_clicked(output_port)
    assert scene.pending_output is output_port
    assert output_port._active is True  # noqa: SLF001 - visual state smoke test
    scene.port_clicked(input_port)
    assert len(scene.connections) == 1
    assert scene.pending_output is None
    assert output_port._active is False  # noqa: SLF001

    second_target = scene.create_node("offset", QPointF(600, 0))
    scene.begin_connection_drag(source.output_ports[0])
    assert scene._drag_item is not None  # noqa: SLF001
    scene.finish_connection_drag(second_target.input_ports[0].scene_position())
    assert len(scene.connections) == 2


def test_project_payload_contains_persisted_result_records(qapp: QApplication) -> None:
    window = MainWindow()
    node = window.scene.create_node("data_table", QPointF(0, 0))
    signal = SignalData(np.arange(8, dtype=float), np.arange(8, dtype=float), sample_rate=1.0)
    record = {"kind": "table", "title": "Data Table", "value": TableResult(signal.to_frame()), "options": {"maximum_rows": 100}}
    window._install_display_result(node.node_id, record, visible=False)  # noqa: SLF001
    document = window._project_payload(relative_paths=False)  # noqa: SLF001
    assert node.node_id in document["results"]["display"]
    assert document["results"]["visibility"][node.node_id] is False
    window.deleteLater()


def test_campaign_dashboard_model_handles_thousand_runs(qapp: QApplication) -> None:
    from app.campaign.models import CampaignRun, RunStatus, TestCampaign
    from app.ui.campaign import CampaignDashboardDock

    campaign = TestCampaign(name="Scale test")
    campaign.runs = [
        CampaignRun(
            run_id=f"run-{index:04d}", source_path=f"C:/data/run-{index:04d}.csv",
            file_name=f"run-{index:04d}.csv",
            status=RunStatus.FAILED if index % 10 == 0 else RunStatus.PASSED,
            user_metadata={"serial": f"SN{index:05d}", "rig": "A" if index % 2 else "B"},
            metrics={"rms": float(index) / 100.0},
        )
        for index in range(1000)
    ]
    dock = CampaignDashboardDock(); dock.set_campaign(campaign)
    assert dock.model.rowCount() == 1000
    dock.status.setCurrentText(RunStatus.FAILED.value); qapp.processEvents()
    assert dock.proxy.rowCount() == 100
    dock.status.setCurrentText("All"); dock.metadata_field.setCurrentText("serial"); dock.metadata_value.setText("SN00042"); qapp.processEvents()
    assert dock.proxy.rowCount() == 1
    dock.deleteLater()


def test_campaign_setup_and_commands_construct(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ui.campaign import CampaignSetupDialog
    from tests.campaign_helpers import workflow_document

    dialog = CampaignSetupDialog(None, workflow_document())
    assert dialog.windowTitle() == "Create New Test Campaign"
    assert dialog.minimumWidth() <= 1366 and dialog.minimumHeight() <= 768
    assert dialog.step_list.count() == 5
    assert dialog.page_stack.count() == 5
    assert all(dialog.page_stack.widget(index).widgetResizable() for index in range(dialog.page_stack.count()))
    assert dialog.save_button.text().replace("&", "") == "Save Campaign"
    assert dialog.execution_report_tabs.count() == 3
    assert dialog.metric_table.rowCount() == 3
    dialog.next_button.click(); qapp.processEvents()
    assert dialog.step_list.currentRow() == 1
    assert dialog.page_stack.currentIndex() == 1
    dialog.deleteLater()

    monkeypatch.setattr(MainWindow, "_initial_prompts", lambda self: None)
    window = MainWindow()
    command_text = {
        window.new_campaign_action.text(), window.open_campaign_action.text(), window.campaign_setup_action.text(),
        window.run_campaign_action.text(), window.cancel_campaign_action.text(), window.retry_campaign_action.text(),
        window.compare_campaign_action.text(), window.campaign_report_action.text(),
    }
    assert {
        "New Test Campaign…", "Open Campaign…", "Campaign Setup…", "Run Campaign", "Cancel Campaign",
        "Retry Failed Runs", "Compare Selected Runs…", "Generate Campaign Report…",
    } <= command_text
    window.deleteLater()


def test_campaign_run_detail_dock_is_reused(qapp: QApplication, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.campaign.models import CampaignRun, TestCampaign

    monkeypatch.setattr(MainWindow, "_initial_prompts", lambda self: None)
    window = MainWindow()
    run = CampaignRun(
        run_id="detail-run", source_path="C:/data/detail.csv", file_name="detail.csv",
        metrics={"rms": 1.25}, metric_units={"rms": "A"},
    )
    window.campaign = TestCampaign(name="Detail test", runs=[run])
    window.campaign_dashboard.set_campaign(window.campaign)

    window.open_campaign_run(run.run_id)
    first = window._campaign_detail_docks[run.run_id]  # noqa: SLF001
    first.close(); qapp.processEvents()
    window.open_campaign_run(run.run_id)

    assert window._campaign_detail_docks[run.run_id] is first  # noqa: SLF001
    assert not first.isHidden()
    window._clear_campaign_detail_docks()  # noqa: SLF001
    window.deleteLater()


def test_campaign_metric_format_is_used_in_dashboard_model(qapp: QApplication) -> None:
    from app.campaign.models import CampaignRun, MetricDefinition, TestCampaign
    from app.ui.campaign import CampaignTableModel

    item = TestCampaign(
        name="Formatting",
        metrics=[MetricDefinition("rms", "RMS", number_format=".2f")],
        runs=[CampaignRun("r1", "C:/run.csv", "run.csv", metrics={"rms": 1.23456})],
    )
    model = CampaignTableModel(item)
    metric_column = next(index for index, (key, _label) in enumerate(model.columns) if key == "metric:rms")
    assert model.data(model.index(0, metric_column), Qt.ItemDataRole.DisplayRole) == "1.23"
