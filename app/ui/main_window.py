# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Main SignalDojo desktop window."""

from __future__ import annotations

import json
import logging
from html import escape
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QPointF, QThread, QTimer, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QImage, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QFileDialog,
    QGraphicsView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from app.application import APP_NAME, VERSION, resource_path, settings
from app.campaign.comparison import available_signal_keys
from app.campaign.execution import CampaignExecutionSummary, CampaignRunner
from app.campaign.models import RunStatus, TestCampaign, campaign_from_dict, campaign_to_dict
from app.exporters.campaign_report import CampaignReportCancelled, export_campaign_report_bundle
from app.core.blocks import (
    BLOCK_TYPES,
    BlockError,
    DescriptiveStatisticsBlock,
    FFTBlock,
    ImportDataBlock,
)
from app.core.models import ScalarResult, SignalData, SpectrogramData, SpectrumData, TableResult
from app.core.result_policy import select_auto_open_result_ids
from app.core.workflow import Connection, ExecutionReport, WorkflowGraph, WorkflowNode
from app.exporters.project_report import export_project_report
from app.project.result_codec import deserialise_display_record, deserialise_result, serialise_display_record
from app.project.io import (
    PROJECT_VERSION,
    clear_recovery,
    load_project,
    recovery_available,
    recovery_path,
    save_project,
    save_recovery,
    validate_project_document,
)
from app.ui.dialogs import DiagnosticsDialog, FilterResponseDialog, ImportPreviewDialog, PreferencesDialog, ProjectInfoDialog, WelcomeDialog
from app.ui.campaign import CampaignComparisonDialog, CampaignDashboardDock, CampaignSetupDialog
from app.ui.node_editor import BlockLibrary, NodeItem, RESULT_BLOCK_TYPES, WorkflowScene, WorkflowView
from app.ui.properties import PropertiesPanel
from app.ui.results import SpectrogramDock, SpectrumDock, TableDock
from app.ui.scope import ScopeDock
from app.update.service import UpdateManifest, fetch_manifest, update_available

LOGGER = logging.getLogger(__name__)


def _available_memory_bytes() -> int:
    """Best-effort physical-memory query without adding a runtime dependency."""
    try:
        import os
        import sys
        if sys.platform == "win32":
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong), ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong), ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus(); status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.available_physical)
        page_size = int(os.sysconf("SC_PAGE_SIZE")); available_pages = int(os.sysconf("SC_AVPHYS_PAGES"))
        return page_size * available_pages
    except Exception:
        return 4 * 1024**3


def _human_bytes(value: int) -> str:
    amount = float(value)
    for suffix in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or suffix == "TiB": return f"{amount:.1f} {suffix}"
        amount /= 1024
    return f"{amount:.1f} TiB"


class WorkflowWorker(QObject):
    progress = Signal(str, int, int)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, graph: WorkflowGraph, targets: list[str] | None = None) -> None:
        super().__init__(); self.graph = graph; self.targets = targets; self._cancelled = False

    @Slot()
    def run(self) -> None:
        try:
            report = self.graph.execute(
                targets=self.targets,
                progress=lambda node_id, index, total: self.progress.emit(node_id, index, total),
                is_cancelled=lambda: self._cancelled,
                use_cache=True,
            )
        except Exception as exc:
            LOGGER.exception("Workflow execution failed"); self.failed.emit(str(exc)); return
        self.completed.emit(report)

    @Slot()
    def cancel(self) -> None:
        self._cancelled = True


class CampaignWorker(QObject):
    overall_progress = Signal(object, int, int)
    run_progress = Signal(str, str, int, int)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, runner: CampaignRunner, retry_failed: bool = False) -> None:
        super().__init__(); self.runner = runner; self.retry_failed = retry_failed

    @Slot()
    def run(self) -> None:
        try:
            callback = lambda run, index, total: self.overall_progress.emit(run, index, total)
            block_callback = lambda run, node_id, index, total: self.run_progress.emit(run.run_id, node_id, index, total)
            summary = self.runner.retry_failed(overall_progress=callback, run_progress=block_callback) if self.retry_failed else self.runner.execute(overall_progress=callback, run_progress=block_callback)
        except Exception as exc:
            LOGGER.exception("Campaign execution failed"); self.failed.emit(str(exc)); return
        self.completed.emit(summary)

    def cancel(self) -> None:
        self.runner.cancel()


class CampaignReportWorker(QObject):
    progress = Signal(str, int, int)
    completed = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, campaign: TestCampaign, output_directory: str, workflow_png: bytes) -> None:
        super().__init__()
        cloned = campaign_from_dict(campaign_to_dict(campaign))
        if cloned is None:
            raise ValueError("Campaign report snapshot could not be created.")
        self.campaign = cloned
        self.output_directory = output_directory
        self.workflow_png = workflow_png
        self._cancelled = False

    @Slot()
    def run(self) -> None:
        try:
            paths = export_campaign_report_bundle(
                self.campaign,
                self.output_directory,
                workflow_png=self.workflow_png,
                is_cancelled=lambda: self._cancelled,
                progress=lambda stage, index, total: self.progress.emit(stage, index, total),
            )
        except CampaignReportCancelled:
            self.cancelled.emit()
            return
        except Exception as exc:
            LOGGER.exception("Campaign report generation failed"); self.failed.emit(str(exc)); return
        self.completed.emit(paths)

    @Slot()
    def cancel(self) -> None:
        self._cancelled = True


class UpdateWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, manifest_url: str) -> None:
        super().__init__(); self.manifest_url = manifest_url

    @Slot()
    def run(self) -> None:
        try: self.completed.emit(fetch_manifest(self.manifest_url))
        except Exception as exc: self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — Untitled"); self.resize(1280, 760); self.setMinimumSize(1000, 620)
        self.current_project: Path | None = None
        self.project_info: dict[str, str] = {"name": "", "description": "", "notes": ""}
        self.dirty = False
        self._thread: QThread | None = None; self._worker: WorkflowWorker | None = None
        self._update_thread: QThread | None = None; self._update_worker: UpdateWorker | None = None; self._manual_update_check = False
        self.campaign: TestCampaign | None = None
        self._campaign_thread: QThread | None = None; self._campaign_worker: CampaignWorker | None = None; self._campaign_runner: CampaignRunner | None = None
        self._campaign_report_thread: QThread | None = None; self._campaign_report_worker: CampaignReportWorker | None = None
        self._campaign_detail_docks: dict[str, QDockWidget] = {}
        self._approved_large_sources: set[tuple[tuple[str, int, int], ...]] = set()
        self._running_graph: WorkflowGraph | None = None; self._execution_graph: WorkflowGraph | None = None
        self._result_docks: dict[str, QDockWidget] = {}
        self._display_results: dict[str, dict[str, Any]] = {}
        self._saved_output_metadata: dict[str, list[dict[str, Any]]] = {}
        self._suppress_changes = False
        self._undo_snapshots: list[str] = []; self._undo_index = -1

        self.scene = WorkflowScene(self); self.view = WorkflowView(self.scene, self); self.setCentralWidget(self.view)
        self.library = BlockLibrary(); self.library.itemDoubleClicked.connect(self._insert_library_item)
        self.properties = PropertiesPanel(); self.properties.parameters_changed.connect(self._on_parameters_changed)
        self.scene.node_selected.connect(self.properties.show_node); self.scene.node_selected.connect(self._inspect_node); self.scene.result_requested.connect(self.show_result_for_node); self.scene.graph_changed.connect(self._on_graph_changed); self.scene.message.connect(self.statusBar().showMessage)

        self._create_library_dock(); self._create_properties_dock(); self._create_inspector_dock(); self._create_minimap_dock(); self._create_campaign_dock(); self._create_actions(); self._create_menus(); self._create_toolbar()
        self.progress_bar = QProgressBar(); self.progress_bar.setVisible(False); self.progress_bar.setMaximumWidth(240); self.statusBar().addPermanentWidget(self.progress_bar)
        self.statusBar().showMessage("Ready")

        self.snapshot_timer = QTimer(self); self.snapshot_timer.setSingleShot(True); self.snapshot_timer.setInterval(250); self.snapshot_timer.timeout.connect(self._record_snapshot)
        self.auto_execute_timer = QTimer(self); self.auto_execute_timer.setSingleShot(True); self.auto_execute_timer.setInterval(700); self.auto_execute_timer.timeout.connect(lambda: self.run_workflow(silent_validation=True))
        self.autosave_timer = QTimer(self); self.autosave_timer.setInterval(30_000); self.autosave_timer.timeout.connect(self._autosave); self.autosave_timer.start()

        self._restore_window_state(); self._reset_undo_history(); self._update_recent_menu()
        QTimer.singleShot(0, self._initial_prompts)

    # ------------------------------------------------------------------ UI
    def _create_library_dock(self) -> None:
        dock = QDockWidget("Block Library", self); dock.setObjectName("BlockLibraryDock")
        panel = QWidget(); layout = QVBoxLayout(panel); layout.setContentsMargins(6, 6, 6, 6)
        search = QLineEdit(); search.setPlaceholderText("Search blocks…"); search.textChanged.connect(self.library.populate)
        layout.addWidget(search); layout.addWidget(self.library, 1); dock.setWidget(panel); self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        self.library_dock = dock

    def _create_properties_dock(self) -> None:
        dock = QDockWidget("Properties", self); dock.setObjectName("PropertiesDock"); dock.setWidget(self.properties); self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock); self.properties_dock = dock

    def _create_inspector_dock(self) -> None:
        self.inspector = QPlainTextEdit(); self.inspector.setReadOnly(True); self.inspector.setPlaceholderText("Select a block to inspect parameters, execution state, signal metadata and processing history.")
        dock = QDockWidget("Signal Inspector", self); dock.setObjectName("SignalInspectorDock"); dock.setWidget(self.inspector); self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock); self.inspector_dock = dock
        self.tabifyDockWidget(self.properties_dock, self.inspector_dock); self.properties_dock.raise_()

    def _create_minimap_dock(self) -> None:
        dock = QDockWidget("Workflow Minimap", self); dock.setObjectName("MinimapDock")
        self.minimap = QGraphicsView(self.scene); self.minimap.setInteractive(False); self.minimap.setMinimumHeight(150); self.minimap.setMaximumHeight(260)
        dock.setWidget(self.minimap); self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock); self.minimap_dock = dock
        self.scene.changed.connect(lambda _regions: self._refresh_minimap())

    def _create_campaign_dock(self) -> None:
        self.campaign_dashboard = CampaignDashboardDock(self)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.campaign_dashboard)
        self.campaign_dashboard.hide()
        self.campaign_dashboard.run_requested.connect(self.run_campaign)
        self.campaign_dashboard.cancel_requested.connect(self.cancel_campaign)
        self.campaign_dashboard.retry_requested.connect(self.retry_failed_campaign_runs)
        self.campaign_dashboard.compare_requested.connect(self.compare_campaign_runs)
        self.campaign_dashboard.report_requested.connect(self.generate_campaign_report)
        self.campaign_dashboard.reference_changed.connect(self.set_campaign_reference)
        self.campaign_dashboard.run_open_requested.connect(self.open_campaign_run)

    def _refresh_minimap(self) -> None:
        if self.scene.items(): self.minimap.fitInView(self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40), Qt.AspectRatioMode.KeepAspectRatio)

    def _create_actions(self) -> None:
        self.new_action = QAction("New", self); self.new_action.setShortcut(QKeySequence.StandardKey.New); self.new_action.triggered.connect(self.new_project)
        self.open_action = QAction("Open…", self); self.open_action.setShortcut(QKeySequence.StandardKey.Open); self.open_action.triggered.connect(self.open_project)
        self.save_action = QAction("Save", self); self.save_action.setShortcut(QKeySequence.StandardKey.Save); self.save_action.triggered.connect(self.save_project)
        self.save_as_action = QAction("Save As…", self); self.save_as_action.setShortcut(QKeySequence.StandardKey.SaveAs); self.save_as_action.triggered.connect(lambda: self.save_project(save_as=True))
        self.project_info_action = QAction("Project Information…", self); self.project_info_action.triggered.connect(self.edit_project_info)
        self.export_report_action = QAction("Export Project Report…", self); self.export_report_action.triggered.connect(self.export_project_report)
        self.preferences_action = QAction("Preferences…", self); self.preferences_action.triggered.connect(self.edit_preferences)
        self.exit_action = QAction("Exit", self); self.exit_action.setShortcut(QKeySequence.StandardKey.Quit); self.exit_action.triggered.connect(self.close)

        self.undo_action = QAction("Undo", self); self.undo_action.setShortcut(QKeySequence.StandardKey.Undo); self.undo_action.triggered.connect(self.undo)
        self.redo_action = QAction("Redo", self); self.redo_action.setShortcut(QKeySequence.StandardKey.Redo); self.redo_action.triggered.connect(self.redo)
        self.copy_action = QAction("Copy", self); self.copy_action.setShortcut(QKeySequence.StandardKey.Copy); self.copy_action.triggered.connect(self.scene.copy_selected)
        self.paste_action = QAction("Paste", self); self.paste_action.setShortcut(QKeySequence.StandardKey.Paste); self.paste_action.triggered.connect(self.scene.paste)
        self.duplicate_action = QAction("Duplicate", self); self.duplicate_action.setShortcut(QKeySequence("Ctrl+D")); self.duplicate_action.triggered.connect(self.scene.duplicate_selected)
        self.delete_action = QAction("Delete Selected", self); self.delete_action.setShortcut(QKeySequence.StandardKey.Delete); self.delete_action.triggered.connect(self.scene.delete_selected)
        self.comment_action = QAction("Add Comment", self); self.comment_action.setShortcut(QKeySequence("Ctrl+Shift+C")); self.comment_action.triggered.connect(self.add_comment)
        self.group_action = QAction("Add Group", self); self.group_action.setShortcut(QKeySequence("Ctrl+G")); self.group_action.triggered.connect(self.add_group)

        self.run_action = QAction("Run All", self); self.run_action.setShortcut(QKeySequence("F5")); self.run_action.triggered.connect(self.run_workflow)
        self.run_selected_action = QAction("Run Selected and Dependencies", self); self.run_selected_action.setShortcut(QKeySequence("Ctrl+F5")); self.run_selected_action.triggered.connect(self.run_selected)
        self.stop_action = QAction("Stop", self); self.stop_action.setShortcut(QKeySequence("Shift+F5")); self.stop_action.setEnabled(False); self.stop_action.triggered.connect(self.stop_workflow)
        self.reset_action = QAction("Reset Results", self); self.reset_action.setShortcut(QKeySequence("Ctrl+Shift+F5")); self.reset_action.triggered.connect(self.reset_execution_results)
        self.show_selected_result_action = QAction("Open Result for Selected Block", self); self.show_selected_result_action.setShortcut(QKeySequence("Ctrl+Shift+R")); self.show_selected_result_action.triggered.connect(self.show_selected_result)
        self.show_all_results_action = QAction("Show All Results", self); self.show_all_results_action.triggered.connect(self.show_all_results)
        self.hide_all_results_action = QAction("Hide All Results", self); self.hide_all_results_action.triggered.connect(self.hide_all_results)
        self.result_display_preferences_action = QAction("Result Display Preferences…", self); self.result_display_preferences_action.triggered.connect(self.edit_preferences)
        self.clear_cache_action = QAction("Clear Processing Cache", self); self.clear_cache_action.triggered.connect(self.clear_cache)
        self.validate_action = QAction("Validate Workflow", self); self.validate_action.triggered.connect(self.validate_workflow)
        self.preview_import_action = QAction("Preview Selected Import…", self); self.preview_import_action.triggered.connect(self.preview_selected_import)
        self.preview_filter_action = QAction("Preview Selected Filter Response…", self); self.preview_filter_action.triggered.connect(self.preview_selected_filter)
        self.auto_execute_action = QAction("Automatically Run After Changes", self); self.auto_execute_action.setCheckable(True)

        self.new_campaign_action = QAction("New Test Campaign…", self); self.new_campaign_action.setShortcut(QKeySequence("Ctrl+Shift+N")); self.new_campaign_action.triggered.connect(self.new_campaign)
        self.open_campaign_action = QAction("Open Campaign…", self); self.open_campaign_action.triggered.connect(self.open_campaign)
        self.campaign_setup_action = QAction("Campaign Setup…", self); self.campaign_setup_action.setShortcut(QKeySequence("Ctrl+Shift+E")); self.campaign_setup_action.triggered.connect(self.setup_campaign)
        self.run_campaign_action = QAction("Run Campaign", self); self.run_campaign_action.setShortcut(QKeySequence("Ctrl+Shift+F5")); self.run_campaign_action.triggered.connect(self.run_campaign)
        self.cancel_campaign_action = QAction("Cancel Campaign", self); self.cancel_campaign_action.setEnabled(False); self.cancel_campaign_action.triggered.connect(self.cancel_campaign)
        self.retry_campaign_action = QAction("Retry Failed Runs", self); self.retry_campaign_action.triggered.connect(self.retry_failed_campaign_runs)
        self.compare_campaign_action = QAction("Compare Selected Runs…", self); self.compare_campaign_action.triggered.connect(lambda: self.compare_campaign_runs(self.campaign_dashboard.selected_run_ids()))
        self.campaign_report_action = QAction("Generate Campaign Report…", self); self.campaign_report_action.triggered.connect(self.generate_campaign_report)
        self.cancel_campaign_report_action = QAction("Cancel Campaign Report", self); self.cancel_campaign_report_action.setEnabled(False); self.cancel_campaign_report_action.triggered.connect(self.cancel_campaign_report)

        self.fit_action = QAction("Fit Workflow", self); self.fit_action.setShortcut(QKeySequence("Ctrl+0")); self.fit_action.triggered.connect(self._fit_workflow)
        self.tidy_action = QAction("Tidy Workflow", self); self.tidy_action.setShortcut(QKeySequence("Ctrl+T")); self.tidy_action.triggered.connect(self.scene.tidy_workflow)
        self.snap_action = QAction("Snap to Grid", self); self.snap_action.setCheckable(True); self.snap_action.setChecked(True); self.snap_action.toggled.connect(lambda checked: setattr(self.scene, "snap_to_grid", checked))
        self.dark_action = QAction("Dark Theme", self); self.dark_action.setCheckable(True); self.dark_action.setChecked(True); self.dark_action.triggered.connect(self._apply_theme)

        self.welcome_action = QAction("Quick Start Tutorial", self); self.welcome_action.triggered.connect(lambda: WelcomeDialog(self).exec())
        self.block_help_action = QAction("Help for Selected Block", self); self.block_help_action.setShortcut(QKeySequence("F1")); self.block_help_action.triggered.connect(self.show_selected_block_help)
        self.documentation_action = QAction("Open Documentation", self); self.documentation_action.triggered.connect(self.open_documentation)
        self.issue_reporting_action = QAction("Issue Reporting Guide", self); self.issue_reporting_action.triggered.connect(self.open_issue_reporting)
        self.diagnostics_action = QAction("Diagnostics…", self); self.diagnostics_action.triggered.connect(self.show_diagnostics)
        self.check_updates_action = QAction("Check for Updates…", self); self.check_updates_action.triggered.connect(lambda: self.check_for_updates(manual=True))
        self.licence_action = QAction("Open Source Licence…", self); self.licence_action.triggered.connect(self.open_source_licence)
        self.trademark_action = QAction("Trademark Policy…", self); self.trademark_action.triggered.connect(self.open_trademark_policy)
        self.about_action = QAction("About SignalDojo", self); self.about_action.triggered.connect(self.show_about)

    def _create_menus(self) -> None:
        file_menu = self.menuBar().addMenu("&File"); file_menu.addActions([self.new_action, self.open_action]); file_menu.addSeparator(); file_menu.addActions([self.new_campaign_action, self.open_campaign_action])
        self.recent_menu = file_menu.addMenu("Recent Projects"); self.examples_menu = file_menu.addMenu("Open Example")
        self._populate_examples_menu(); file_menu.addSeparator(); file_menu.addActions([self.save_action, self.save_as_action, self.project_info_action, self.preferences_action, self.export_report_action]); file_menu.addSeparator(); file_menu.addAction(self.exit_action)

        edit_menu = self.menuBar().addMenu("&Edit"); edit_menu.addActions([self.undo_action, self.redo_action]); edit_menu.addSeparator(); edit_menu.addActions([self.copy_action, self.paste_action, self.duplicate_action, self.delete_action]); edit_menu.addSeparator(); edit_menu.addActions([self.comment_action, self.group_action])
        align_menu = edit_menu.addMenu("Align Selected")
        for label, mode in (("Left", "left"), ("Right", "right"), ("Top", "top"), ("Bottom", "bottom"), ("Horizontal Centres", "horizontal"), ("Vertical Centres", "vertical")):
            action = align_menu.addAction(label); action.triggered.connect(lambda _checked=False, m=mode: self.scene.align_selected(m))
        distribute = edit_menu.addMenu("Distribute Selected"); distribute.addAction("Horizontally").triggered.connect(lambda: self.scene.distribute_selected(True)); distribute.addAction("Vertically").triggered.connect(lambda: self.scene.distribute_selected(False))

        workflow_menu = self.menuBar().addMenu("&Workflow"); workflow_menu.addActions([self.run_action, self.run_selected_action, self.stop_action, self.reset_action]); workflow_menu.addSeparator(); workflow_menu.addActions([self.validate_action, self.clear_cache_action, self.auto_execute_action]); workflow_menu.addSeparator(); workflow_menu.addActions([self.preview_import_action, self.preview_filter_action])
        campaign_menu = self.menuBar().addMenu("&Campaign"); campaign_menu.addActions([self.new_campaign_action, self.open_campaign_action, self.campaign_setup_action]); campaign_menu.addSeparator(); campaign_menu.addActions([self.run_campaign_action, self.cancel_campaign_action, self.retry_campaign_action]); campaign_menu.addSeparator(); campaign_menu.addActions([self.compare_campaign_action, self.campaign_report_action, self.cancel_campaign_report_action])
        view_menu = self.menuBar().addMenu("&View"); view_menu.addActions([self.fit_action, self.tidy_action, self.snap_action, self.dark_action]); view_menu.addSeparator()
        self.results_menu = view_menu.addMenu("Results"); self.results_menu.aboutToShow.connect(self._rebuild_results_menu)
        view_menu.addSeparator(); view_menu.addAction(self.library_dock.toggleViewAction()); view_menu.addAction(self.properties_dock.toggleViewAction()); view_menu.addAction(self.inspector_dock.toggleViewAction()); view_menu.addAction(self.minimap_dock.toggleViewAction()); view_menu.addAction(self.campaign_dashboard.toggleViewAction())
        help_menu = self.menuBar().addMenu("&Help"); help_menu.addActions([self.welcome_action, self.block_help_action, self.documentation_action, self.issue_reporting_action, self.diagnostics_action, self.check_updates_action]); help_menu.addSeparator(); help_menu.addActions([self.licence_action, self.trademark_action]); help_menu.addSeparator(); help_menu.addAction(self.about_action)

    def _create_toolbar(self) -> None:
        toolbar = QToolBar("Main", self); toolbar.setObjectName("MainToolbar"); toolbar.setMovable(False)
        toolbar.addActions([self.new_action, self.open_action, self.save_action]); toolbar.addSeparator(); toolbar.addActions([self.undo_action, self.redo_action]); toolbar.addSeparator(); toolbar.addActions([self.run_action, self.run_selected_action, self.stop_action, self.reset_action]); toolbar.addSeparator(); campaign_label = QLabel("Test Campaign"); campaign_label.setObjectName("ToolbarSectionLabel"); toolbar.addWidget(campaign_label); toolbar.addActions([self.run_campaign_action, self.cancel_campaign_action]); toolbar.addSeparator(); toolbar.addActions([self.fit_action, self.tidy_action]); self.addToolBar(toolbar)

    def _populate_examples_menu(self) -> None:
        self.examples_menu.clear(); examples = resource_path("examples")
        if not examples.exists(): self.examples_menu.setEnabled(False); return
        self.examples_menu.setEnabled(True)
        for path in sorted(examples.rglob("*.sdojo")):
            relative = path.relative_to(examples)
            label = " / ".join(part.replace("_", " ").title() for part in relative.with_suffix("").parts)
            action = self.examples_menu.addAction(label); action.triggered.connect(lambda _checked=False, p=path: self.open_example(p))

    def _insert_library_item(self, item) -> None:
        type_name = item.data(Qt.ItemDataRole.UserRole)
        if type_name:
            self.library.mark_used(str(type_name))
            self.scene.create_node(str(type_name), self.view.mapToScene(self.view.viewport().rect().center()))

    # ----------------------------------------------------------- change/undo
    def _on_parameters_changed(self, node: NodeItem) -> None:
        self._execution_graph = self._execution_graph  # cache key will detect changed params
        self._on_graph_changed()

    def _mark_project_dirty(self) -> None:
        if self._suppress_changes:
            return
        if not self.dirty:
            self.dirty = True
            self._update_title()

    def _on_graph_changed(self, *_args) -> None:
        if self._suppress_changes: return
        self._prune_result_docks()
        self._mark_project_dirty()
        self.snapshot_timer.start()
        if self.auto_execute_action.isChecked() and self._thread is None: self.auto_execute_timer.start()

    def _snapshot_document(self) -> dict[str, Any]:
        # Result arrays are intentionally excluded from undo snapshots; otherwise a
        # few large scopes would multiply memory use for every small canvas movement.
        payload = self._project_payload(relative_paths=False, include_results=False)
        campaign = payload.get("campaign")
        if isinstance(campaign, dict):
            for run in campaign.get("runs", []):
                if isinstance(run, dict):
                    run["detail_results"] = {}
        return payload

    def _record_snapshot(self) -> None:
        snapshot = json.dumps(self._snapshot_document(), sort_keys=True, default=str)
        if self._undo_index >= 0 and self._undo_snapshots[self._undo_index] == snapshot: return
        self._undo_snapshots = self._undo_snapshots[: self._undo_index + 1]; self._undo_snapshots.append(snapshot)
        if len(self._undo_snapshots) > 100: self._undo_snapshots.pop(0)
        self._undo_index = len(self._undo_snapshots) - 1; self._update_undo_actions()

    def _reset_undo_history(self) -> None:
        self._undo_snapshots = [json.dumps(self._snapshot_document(), sort_keys=True, default=str)]; self._undo_index = 0; self._update_undo_actions()

    def _update_undo_actions(self) -> None:
        if hasattr(self, "undo_action"):
            self.undo_action.setEnabled(self._undo_index > 0); self.redo_action.setEnabled(self._undo_index < len(self._undo_snapshots) - 1)

    def undo(self) -> None:
        if self._undo_index <= 0: return
        self._undo_index -= 1; self._load_document(json.loads(self._undo_snapshots[self._undo_index]), project_dir=self.current_project.parent if self.current_project else None, reset_history=False, fit=False, preserve_results=True); self.dirty = True; self._update_title(); self._update_undo_actions()

    def redo(self) -> None:
        if self._undo_index >= len(self._undo_snapshots) - 1: return
        self._undo_index += 1; self._load_document(json.loads(self._undo_snapshots[self._undo_index]), project_dir=self.current_project.parent if self.current_project else None, reset_history=False, fit=False, preserve_results=True); self.dirty = True; self._update_title(); self._update_undo_actions()

    # --------------------------------------------------------------- project
    def _update_title(self) -> None:
        project_name = self.project_info.get("name") or (self.current_project.name if self.current_project else "Untitled")
        self.setWindowTitle(f"{APP_NAME} — {project_name}{'*' if self.dirty else ''}")

    def new_project(self) -> None:
        if not self._confirm_discard_changes(): return
        self._clear_campaign_detail_docks()
        self._suppress_changes = True; self.scene.loading = True; self.scene.clear_workflow(emit=False); self.scene.loading = False; self._suppress_changes = False
        self.current_project = None; self.project_info = {"name": "", "description": "", "notes": ""}; self.dirty = False; self._execution_graph = None; self._saved_output_metadata.clear(); self._clear_result_docks(clear_records=True); self.campaign = None; self.campaign_dashboard.set_campaign(None); self.campaign_dashboard.hide(); clear_recovery(); self._update_title(); self._reset_undo_history(); self.statusBar().showMessage("New project created", 3000)

    def open_project(self) -> None:
        if not self._confirm_discard_changes(): return
        path, _ = QFileDialog.getOpenFileName(self, "Open SignalDojo Project", "", "SignalDojo (*.sdojo)")
        if path: self.open_project_path(path, confirm_discard=False)

    def open_project_path(self, path: str | Path, *, confirm_discard: bool = True) -> bool:
        if confirm_discard and not self._confirm_discard_changes(): return False
        self._clear_campaign_detail_docks()
        source = Path(path).expanduser().resolve()
        try:
            document = load_project(source); self._load_document(document, project_dir=source.parent)
        except (ValueError, KeyError, TypeError, BlockError, OSError) as exc:
            QMessageBox.critical(self, "Open Project", str(exc)); return False
        self.current_project = source; self.dirty = False; self._execution_graph = None; self._update_title(); self._add_recent(source); self.statusBar().showMessage(f"Opened {source.name}", 4000); return True

    def open_example(self, path: str | Path) -> bool:
        """Open a bundled example as an unsaved template to protect installed files."""

        if not self._confirm_discard_changes(): return False
        self._clear_campaign_detail_docks()
        source = Path(path).expanduser().resolve()
        try:
            document = load_project(source); self._load_document(document, project_dir=source.parent)
        except (ValueError, KeyError, TypeError, BlockError, OSError) as exc:
            QMessageBox.critical(self, "Open Example", str(exc)); return False
        self.current_project = None
        self.project_info = {**self.project_info, "name": f"{self.project_info.get('name') or source.stem} (Example Copy)"}
        self.dirty = True; self._execution_graph = None; self._update_title(); self._reset_undo_history()
        self.statusBar().showMessage(f"Opened example template: {source.name}. Use Save As to keep your copy.", 6000)
        return True

    def save_project(self, save_as: bool = False) -> bool:
        path = self.current_project
        if save_as or path is None:
            selected, _ = QFileDialog.getSaveFileName(self, "Save SignalDojo Project", str(path or Path.home() / "Untitled.sdojo"), "SignalDojo (*.sdojo)")
            if not selected: return False
            path = Path(selected); path = path if path.suffix.lower() == ".sdojo" else path.with_suffix(".sdojo")
        try: save_project(path, self._project_payload(project_path=path, relative_paths=True))
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Save Project", f"Could not save project: {exc}"); return False
        self.current_project = path; self.dirty = False; clear_recovery(); self._update_title(); self._add_recent(path); self.statusBar().showMessage(f"Saved {path.name}", 4000); return True



    def _workflow_png(self) -> bytes:
        bounds = self.scene.itemsBoundingRect().adjusted(-50, -50, 50, 50)
        width = max(800, min(5000, int(bounds.width())))
        height = max(500, min(5000, int(bounds.height())))
        image = QImage(width, height, QImage.Format.Format_ARGB32); image.fill(Qt.GlobalColor.white)
        from PySide6.QtCore import QRectF
        painter = QPainter(image); self.scene.render(painter, QRectF(0, 0, width, height), bounds, Qt.AspectRatioMode.KeepAspectRatio); painter.end()
        data = QByteArray(); buffer = QBuffer(data); buffer.open(QIODevice.OpenModeFlag.WriteOnly); image.save(buffer, "PNG"); return bytes(data)

    def export_project_report(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(self, "Export Project Report", str((self.current_project or Path.home() / "SignalDojo_Report.sdojo").with_suffix(".html")), "HTML Report (*.html);;PDF Report (*.pdf)")
        if not selected: return
        results: list[Any] = []
        if self._execution_graph:
            for node in self._execution_graph.nodes.values(): results.extend(value for value in node.last_outputs if value is not None)
        try:
            export_project_report(selected, self._project_payload(relative_paths=False, include_results=False), self._workflow_png(), results, VERSION)
        except Exception as exc:
            LOGGER.exception("Project report export failed"); QMessageBox.critical(self, "Export Project Report", str(exc)); return
        self.statusBar().showMessage(f"Exported report: {selected}", 5000)

    def edit_preferences(self) -> None:
        app_settings = settings()
        values = {
            "default_sample_rate": app_settings.value("defaults/sample_rate", 1000.0, type=float),
            "default_unit": app_settings.value("defaults/unit", "", type=str),
            "numeric_precision": app_settings.value("defaults/precision", 6, type=int),
            "engineering_notation": app_settings.value("defaults/engineering_notation", True, type=bool),
            "result_auto_open_mode": app_settings.value("results/auto_open_mode", "smart", type=str),
            "result_auto_open_limit": app_settings.value("results/auto_open_limit", 3, type=int),
            "update_manifest_url": app_settings.value("updates/manifest_url", "", type=str),
            "automatic_update_check": app_settings.value("updates/automatic", False, type=bool),
        }
        dialog = PreferencesDialog(values, self)
        if dialog.exec():
            value = dialog.value()
            app_settings.setValue("defaults/sample_rate", value["default_sample_rate"])
            app_settings.setValue("defaults/unit", value["default_unit"])
            app_settings.setValue("defaults/precision", value["numeric_precision"])
            app_settings.setValue("defaults/engineering_notation", value["engineering_notation"])
            app_settings.setValue("results/auto_open_mode", value["result_auto_open_mode"])
            app_settings.setValue("results/auto_open_limit", value["result_auto_open_limit"])
            app_settings.setValue("updates/manifest_url", value["update_manifest_url"])
            app_settings.setValue("updates/automatic", value["automatic_update_check"])
            self.statusBar().showMessage("Preferences updated", 3000)

    def edit_project_info(self) -> None:
        dialog = ProjectInfoDialog(self.project_info, self)
        if dialog.exec(): self.project_info = dialog.value(); self._on_graph_changed(); self._update_title()

    @staticmethod
    def _relative_file_path(value: str, project_dir: Path) -> str:
        if not value: return value
        path = Path(value).expanduser()
        try: return str(path.resolve().relative_to(project_dir.resolve()))
        except (ValueError, OSError): return str(path)

    def _project_payload(self, *, project_path: Path | None = None, relative_paths: bool = False, include_results: bool = True) -> dict[str, Any]:
        project_dir = (project_path or self.current_project).parent if (project_path or self.current_project) else None
        nodes = []
        for node in self.scene.nodes.values():
            params = dict(node.params)
            if relative_paths and project_dir and "file_path" in params: params["file_path"] = self._relative_file_path(str(params["file_path"]), project_dir)
            output_metadata = self._saved_output_metadata.get(node.node_id, [])
            if self._execution_graph and node.node_id in self._execution_graph.nodes:
                output_metadata = [
                    self._result_inspection_payload(value)
                    for value in self._execution_graph.nodes[node.node_id].last_outputs
                    if value is not None
                ]
            nodes.append({
                "id": node.node_id,
                "type": node.block_type,
                "label": node.custom_label,
                "position": [node.pos().x(), node.pos().y()],
                "parameters": params,
                "output_metadata": output_metadata,
            })
        transform = self.view.transform()
        persisted_results = {"display": {}, "visibility": {}}
        if include_results:
            persisted_results = {
                "display": {node_id: serialise_display_record(record) for node_id, record in self._display_results.items()},
                "visibility": {
                    node_id: bool(self._result_docks.get(node_id) and not self._result_docks[node_id].isHidden())
                    for node_id in self._display_results
                },
            }
        payload = {
            "application_version": VERSION, "project": dict(self.project_info), "nodes": nodes,
            "connections": [{"source_id": r.source_id, "source_port": r.source_port, "target_id": r.target_id, "target_port": r.target_port} for r in self.scene.connection_records()],
            "comments": self.scene.comment_records(), "groups": self.scene.group_records(),
            "results": persisted_results,
            "view": {
                "dark_theme": self.dark_action.isChecked(),
                "snap_to_grid": self.snap_action.isChecked(),
                "auto_execute": self.auto_execute_action.isChecked(),
                "transform": [transform.m11(), transform.m12(), transform.m21(), transform.m22(), transform.dx(), transform.dy()],
                "window_state": bytes(self.saveState().toBase64()).decode("ascii"),
            },
        }
        if self.campaign is not None:
            campaign_copy = campaign_from_dict(campaign_to_dict(self.campaign))
            if campaign_copy is None:
                raise ValueError("Campaign could not be serialised.")
            # Campaigns associated with the current project retain an immutable
            # processing snapshot without recursively embedding campaign results.
            if not campaign_copy.workflow_path:
                campaign_copy.workflow_document = {
                    "format": "SignalDojo Project", "project_version": PROJECT_VERSION,
                    **{key: value for key, value in payload.items() if key != "results"},
                    "results": {"display": {}, "visibility": {}}, "campaign": None,
                }
            if relative_paths and project_dir:
                campaign_copy.workflow_path = self._relative_file_path(campaign_copy.workflow_path, project_dir)
                campaign_copy.input_folder = self._relative_file_path(campaign_copy.input_folder, project_dir)
                campaign_copy.explicit_files = [self._relative_file_path(value, project_dir) for value in campaign_copy.explicit_files]
                campaign_copy.report.output_directory = self._relative_file_path(campaign_copy.report.output_directory, project_dir)
                campaign_copy.report.company_logo = self._relative_file_path(campaign_copy.report.company_logo, project_dir)
                for mapping in campaign_copy.input_mappings:
                    if mapping.fixed_path:
                        mapping.fixed_path = self._relative_file_path(mapping.fixed_path, project_dir)
                for run in campaign_copy.runs:
                    run.source_path = self._relative_file_path(run.source_path, project_dir)
            payload["campaign"] = campaign_to_dict(campaign_copy)
        else:
            payload["campaign"] = None
        return payload

    def _resolve_node_file(self, params: dict[str, Any], project_dir: Path | None, type_name: str) -> None:
        raw = str(params.get("file_path", "")).strip()
        if not raw: return
        path = Path(raw).expanduser()
        if project_dir and not path.is_absolute(): path = (project_dir / path).resolve()
        if type_name == "import_data" and not path.exists() and project_dir:
            alternative = project_dir / path.name
            if alternative.exists(): path = alternative
            else:
                selected, _ = QFileDialog.getOpenFileName(self, f"Relink missing source: {path.name}", str(project_dir), "All files (*)")
                if selected: path = Path(selected)
        params["file_path"] = str(path)

    @staticmethod
    def _resolve_campaign_paths(campaign: TestCampaign, project_dir: Path | None) -> None:
        if project_dir is None: return
        def resolved(value: str) -> str:
            if not value: return value
            path = Path(value).expanduser()
            return str((project_dir / path).resolve()) if not path.is_absolute() else str(path)
        campaign.workflow_path = resolved(campaign.workflow_path)
        campaign.input_folder = resolved(campaign.input_folder)
        campaign.explicit_files = [resolved(value) for value in campaign.explicit_files]
        campaign.report.output_directory = resolved(campaign.report.output_directory)
        campaign.report.company_logo = resolved(campaign.report.company_logo)
        for mapping in campaign.input_mappings:
            if mapping.fixed_path: mapping.fixed_path = resolved(mapping.fixed_path)
        for run in campaign.runs:
            run.source_path = resolved(run.source_path)

    def _load_document(self, document: dict[str, Any], project_dir: Path | None = None, *, reset_history: bool = True, fit: bool = True, preserve_results: bool = False) -> None:
        self._suppress_changes = True; self.scene.loading = True; self.scene.clear_workflow(emit=False)
        self._saved_output_metadata = {
            str(raw.get("id")): list(raw.get("output_metadata", []))
            for raw in document.get("nodes", [])
            if isinstance(raw, dict) and isinstance(raw.get("output_metadata", []), list)
        }
        try:
            for raw_node in document.get("nodes", []):
                position = raw_node.get("position", [0.0, 0.0]); params = dict(raw_node.get("parameters", {})); type_name = str(raw_node["type"])
                self._resolve_node_file(params, project_dir, type_name)
                self.scene.create_node(type_name, QPointF(float(position[0]), float(position[1])), node_id=str(raw_node["id"]), params=params, label=str(raw_node.get("label", "")), emit=False)
            for raw_connection in document.get("connections", []):
                self.scene.add_connection(str(raw_connection["source_id"]), int(raw_connection.get("source_port", 0)), str(raw_connection["target_id"]), int(raw_connection.get("target_port", 0)), emit=False)
            for raw in document.get("comments", []): self.scene.create_comment(QPointF(*map(float, raw.get("position", [0, 0]))), str(raw.get("text", "Comment")), item_id=str(raw.get("id", "")) or None, emit=False)
            for raw in document.get("groups", []): self.scene.create_group(QPointF(*map(float, raw.get("position", [0, 0]))), str(raw.get("title", "Group")), item_id=str(raw.get("id", "")) or None, size=tuple(map(float, raw.get("size", [500, 300]))), emit=False)
        finally:
            self.scene.loading = False; self._suppress_changes = False
        self.project_info = {"name": "", "description": "", "notes": "", **document.get("project", {})}
        self.campaign = campaign_from_dict(document.get("campaign"))
        if self.campaign is not None:
            self._resolve_campaign_paths(self.campaign, project_dir)
            self.campaign_dashboard.set_campaign(self.campaign); self.campaign_dashboard.show()
        else:
            self.campaign_dashboard.set_campaign(None); self.campaign_dashboard.hide()
        view = document.get("view", {}); dark = bool(view.get("dark_theme", True)); self.dark_action.setChecked(dark); self._apply_theme(dark)
        snap = bool(view.get("snap_to_grid", True)); self.snap_action.setChecked(snap); self.scene.snap_to_grid = snap
        self.auto_execute_action.setChecked(bool(view.get("auto_execute", False)))
        window_state = str(view.get("window_state", ""))
        if window_state:
            self.restoreState(QByteArray.fromBase64(window_state.encode("ascii")))
        self._execution_graph = None
        if preserve_results:
            self._prune_result_docks()
        else:
            self._clear_result_docks(clear_records=True)
            self._restore_persisted_results(document.get("results", {}))
        transform_values = view.get("transform")
        if not fit and isinstance(transform_values, list) and len(transform_values) == 6:
            from PySide6.QtGui import QTransform
            self.view.setTransform(QTransform(*map(float, transform_values)))
        if fit: self._fit_workflow()
        self._refresh_minimap()
        if reset_history: self._reset_undo_history()

    def _result_inspection_payload(self, value: Any) -> dict[str, Any]:
        if isinstance(value, SignalData):
            return {"result_type": "signal", **value.to_metadata(), "value_dtype": str(value.values.dtype)}
        if isinstance(value, ScalarResult):
            return {"result_type": "scalar", "name": value.name, "value": value.value, "unit": value.unit, "description": value.description, "metadata": value.metadata}
        if isinstance(value, TableResult):
            return {"result_type": "table", "name": value.name, "rows": len(value.frame), "columns": [str(column) for column in value.frame.columns], "description": value.description, "metadata": value.metadata}
        if isinstance(value, SpectrumData):
            return {"result_type": "spectrum", "name": value.name, "bins": len(value.frequency), "unit": value.unit, "scale": value.scale, "metadata": value.metadata}
        if isinstance(value, SpectrogramData):
            return {"result_type": "spectrogram", "name": value.name, "shape": list(value.values.shape), "metadata": value.metadata}
        if value is None: return {"result_type": "unconnected or empty"}
        return {"result_type": type(value).__name__, "representation": repr(value)[:2000]}

    @Slot(object)
    def _inspect_node(self, node: NodeItem | None) -> None:
        if node is None:
            self.inspector.clear(); return
        payload: dict[str, Any] = {
            "block": node.custom_label or node.block.display_name,
            "type": node.block.type_name,
            "category": node.block.category,
            "description": node.block.description,
            "parameters": node.block.serialise_params(),
        }
        graph_node = self._execution_graph.nodes.get(node.node_id) if self._execution_graph and node.node_id in self._execution_graph.nodes else None
        if graph_node:
            payload["execution"] = {"state": graph_node.state, "duration_seconds": graph_node.execution_seconds, "warning": graph_node.warning}
            payload["outputs"] = [self._result_inspection_payload(value) for value in graph_node.last_outputs]
        else:
            payload["execution"] = {"state": "not executed"}
            saved_outputs = self._saved_output_metadata.get(node.node_id, [])
            if saved_outputs:
                payload["saved_output_metadata"] = saved_outputs
        self.inspector.setPlainText(json.dumps(payload, indent=2, default=str, ensure_ascii=False))

    def _refresh_selected_inspector(self) -> None:
        selected = self.scene.selected_nodes(); self._inspect_node(selected[0] if len(selected) == 1 else None)

    # -------------------------------------------------------------- execution
    def _build_graph(self) -> WorkflowGraph:
        graph = WorkflowGraph(); previous = self._execution_graph
        for item in self.scene.nodes.values():
            node = WorkflowNode(item.node_id, item.block, (item.pos().x(), item.pos().y()), item.custom_label)
            if previous and item.node_id in previous.nodes and previous.nodes[item.node_id].block.type_name == item.block.type_name:
                old = previous.nodes[item.node_id]; node.last_outputs = old.last_outputs; node.cache_key = old.cache_key; node.execution_seconds = old.execution_seconds
            graph.add_node(node)
        for record in self.scene.connection_records(): graph.add_connection(Connection(record.source_id, record.source_port, record.target_id, record.target_port))
        return graph

    def _confirm_large_source_processing(self, graph: WorkflowGraph, *, silent: bool) -> bool:
        records: list[tuple[str, int, int]] = []
        for node in graph.nodes.values():
            if node.block.type_name != "import_data": continue
            raw = str(node.block.params.get("file_path", "")).strip()
            if not raw: continue
            path = Path(raw).expanduser()
            try:
                stat = path.stat(); records.append((str(path.resolve()), int(stat.st_size), int(stat.st_mtime_ns)))
            except OSError:
                continue
        token = tuple(sorted(records))
        if not token or token in self._approved_large_sources: return True
        source_bytes = sum(record[1] for record in token)
        estimated_bytes = source_bytes * 8
        available_bytes = _available_memory_bytes()
        potentially_unsafe = source_bytes >= 1024**3 or estimated_bytes >= int(available_bytes * 0.55)
        if not potentially_unsafe: return True
        message = (
            f"The selected source files total {_human_bytes(source_bytes)}. SignalDojo may require roughly "
            f"{_human_bytes(estimated_bytes)} while importing and processing them; approximately "
            f"{_human_bytes(available_bytes)} is currently available.\n\n"
            "Close other applications, reduce the selected channels, crop the source data, or continue only if sufficient memory is available."
        )
        if silent:
            self.statusBar().showMessage("Automatic execution skipped because the workflow may exceed available memory.", 8000)
            return False
        response = QMessageBox.warning(self, "Large Dataset Warning", message, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Cancel)
        if response == QMessageBox.StandardButton.Yes:
            self._approved_large_sources.add(token); return True
        return False

    def run_selected(self) -> None:
        selected = [node.node_id for node in self.scene.selected_nodes()]
        if not selected: QMessageBox.information(self, "Run Selected", "Select at least one block."); return
        self.run_workflow(targets=selected)

    def run_workflow(self, _checked: bool = False, *, targets: list[str] | None = None, silent_validation: bool = False) -> None:
        if self._thread is not None: return
        if self._campaign_thread is not None:
            if not silent_validation:
                QMessageBox.information(
                    self, "Run Workflow",
                    "Wait for the test campaign to finish or cancel it before running the interactive workflow.",
                )
            return
        if not self.scene.nodes:
            if not silent_validation: QMessageBox.information(self, "Run Workflow", "Add at least one block to the workflow.")
            return
        for item in self.scene.nodes.values(): item.set_processing_state("idle")
        try:
            graph = self._build_graph(); subset = graph.ancestors(targets) if targets else None; graph.validate(subset)
        except (BlockError, ValueError) as exc:
            if not silent_validation: QMessageBox.warning(self, "Workflow Validation", str(exc))
            else: self.statusBar().showMessage(f"Automatic run skipped: {exc}", 5000)
            return
        if not self._confirm_large_source_processing(graph, silent=silent_validation): return
        self._running_graph = graph; self._thread = QThread(self); self._worker = WorkflowWorker(graph, targets); self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run); self._worker.progress.connect(self._on_progress); self._worker.completed.connect(self._on_completed); self._worker.failed.connect(self._on_failed); self._worker.completed.connect(self._thread.quit); self._worker.failed.connect(self._thread.quit); self._thread.finished.connect(self._cleanup_worker)
        self.run_action.setEnabled(False); self.run_selected_action.setEnabled(False); self.stop_action.setEnabled(True); self.progress_bar.setVisible(True); self.progress_bar.setRange(0, max(1, len(graph.nodes))); self.progress_bar.setValue(0); self.statusBar().showMessage("Processing workflow…"); self._thread.start()

    def stop_workflow(self) -> None:
        if self._worker is not None: self._worker.cancel(); self.statusBar().showMessage("Cancellation requested…")

    @Slot(str, int, int)
    def _on_progress(self, node_id: str, index: int, total: int) -> None:
        item = self.scene.nodes.get(node_id)
        if item: item.set_processing_state("processing")
        self.progress_bar.setRange(0, total); self.progress_bar.setValue(index); self.statusBar().showMessage(f"Processing block {index} of {total}…")

    @Slot(object)
    def _on_completed(self, report: ExecutionReport) -> None:
        graph = self._running_graph
        if graph is None: return
        self._execution_graph = graph
        self._saved_output_metadata = {
            node_id: [self._result_inspection_payload(value) for value in graph_node.last_outputs if value is not None]
            for node_id, graph_node in graph.nodes.items()
        }
        for node_id, graph_node in graph.nodes.items():
            item = self.scene.nodes.get(node_id)
            if item: item.set_processing_state(graph_node.state)
        result_count, visible_result_count = self._show_result_docks(graph, report)
        self._refresh_selected_inspector(); self._mark_project_dirty()
        signals = [output for outputs in report.outputs.values() for output in outputs if isinstance(output, SignalData)]
        sample_count = max((signal.samples for signal in signals), default=0); memory_mb = report.peak_memory_bytes / (1024 * 1024)
        warning_text = f" — {len(report.warnings)} warning(s)" if report.warnings else ""
        result_text = ""
        if result_count:
            hidden_count = max(0, result_count - visible_result_count)
            result_text = f" — {result_count} result(s) ready"
            if hidden_count:
                result_text += f", {hidden_count} available under View → Results"
        self.statusBar().showMessage(f"Completed in {report.duration_seconds:.3f} s — {len(report.executed_nodes)} executed, {len(report.cached_nodes)} cached{warning_text} — {sample_count:,} samples — peak traced memory {memory_mb:.1f} MB{result_text}", 15000)

    @Slot(str)
    def _on_failed(self, message: str) -> None:
        if self._running_graph:
            for node_id, graph_node in self._running_graph.nodes.items():
                item = self.scene.nodes.get(node_id)
                if item: item.set_processing_state(graph_node.state)
        self._refresh_selected_inspector(); QMessageBox.critical(self, "Processing Error", message); self.statusBar().showMessage("Workflow failed", 5000)

    @Slot()
    def _cleanup_worker(self) -> None:
        if self._worker: self._worker.deleteLater()
        if self._thread: self._thread.deleteLater()
        self._worker = None; self._thread = None; self.run_action.setEnabled(True); self.run_selected_action.setEnabled(True); self.stop_action.setEnabled(False); self.progress_bar.setVisible(False)

    def reset_execution_results(self) -> None:
        if self._thread is not None:
            QMessageBox.information(self, "Reset Results", "Stop the running workflow before resetting results.")
            return
        if self._execution_graph: self._execution_graph.clear_cache()
        self._execution_graph = None; self._running_graph = None; self._clear_result_docks(clear_records=True)
        for node in self.scene.nodes.values(): node.set_processing_state("idle")
        self.progress_bar.setValue(0); self._refresh_selected_inspector(); self._mark_project_dirty(); self.statusBar().showMessage("Execution results reset", 3000)

    def clear_cache(self) -> None:
        if self._execution_graph: self._execution_graph.clear_cache()
        for node in self.scene.nodes.values(): node.set_processing_state("idle")
        self.statusBar().showMessage("Processing cache cleared", 3000)

    def validate_workflow(self, *, show_success: bool = True) -> str:
        try: graph = self._build_graph(); graph.validate(); message = f"Workflow is valid: {len(graph.nodes)} blocks and {len(graph.connections)} connections."
        except (BlockError, ValueError) as exc:
            message = f"Workflow validation failed: {exc}"
            if show_success: QMessageBox.warning(self, "Workflow Validation", message)
            return message
        if show_success: QMessageBox.information(self, "Workflow Validation", message)
        return message

    def _connected_value(self, graph: WorkflowGraph, report: ExecutionReport, node_id: str, target_port: int) -> Any:
        for connection in graph.connections:
            if connection.target_id == node_id and connection.target_port == target_port:
                outputs = report.outputs.get(connection.source_id, graph.nodes[connection.source_id].last_outputs)
                return outputs[connection.source_port] if connection.source_port < len(outputs) else None
        return None

    def _replace_result_dock(self, node_id: str, dock: QDockWidget) -> None:
        old = self._result_docks.pop(node_id, None)
        if old:
            self.removeDockWidget(old)
            old.deleteLater()
        anchor = next((item for item in self._result_docks.values() if not item.isHidden()), None)
        dock.setObjectName(f"ResultDock_{node_id}")
        dock.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock)
        if anchor is not None:
            self.tabifyDockWidget(anchor, dock)
        self._result_docks[node_id] = dock
        dock.destroyed.connect(lambda _object=None, nid=node_id, tracked=dock: self._forget_result_dock(nid, tracked))
        dock.show()
        dock.raise_()

    def _dock_from_display_record(self, record: dict[str, Any]) -> QDockWidget:
        kind = str(record.get("kind", "")); title = str(record.get("title", "Result")); options = dict(record.get("options", {}))
        if kind == "scope":
            return ScopeDock(title, list(record.get("signals", [])), int(options.get("max_points", 100_000)), self,
                grid=bool(options.get("grid", True)), legend=bool(options.get("legend", True)), line_width=float(options.get("line_width", 1.5)),
                line_style=str(options.get("line_style", "solid")), show_markers=bool(options.get("show_markers", False)), show_peaks=bool(options.get("show_peaks", False)),
                auto_scale=bool(options.get("auto_scale", True)), x_min=str(options.get("x_min", "")), x_max=str(options.get("x_max", "")), y_min=str(options.get("y_min", "")), y_max=str(options.get("y_max", "")))
        if kind == "spectrum":
            return SpectrumDock(title, record["value"], self, log_frequency=bool(options.get("log_frequency", False)), decibel=bool(options.get("decibel", False)))
        if kind == "table":
            return TableDock(title, record["value"], int(options.get("maximum_rows", 10_000)), self)
        if kind == "spectrogram":
            return SpectrogramDock(title, record["value"], self, minimum_frequency=float(options.get("minimum_frequency", 0.0)), maximum_frequency=float(options.get("maximum_frequency", 0.0)), colour_map=str(options.get("colour_map", "viridis")))
        raise ValueError(f"Unsupported stored display result kind: {kind}")

    def _install_display_result(self, node_id: str, record: dict[str, Any], *, visible: bool = True) -> None:
        """Store a display result and create its dock only when it should be shown.

        Keeping hidden results as records rather than hidden QDockWidgets prevents a
        large workflow from constructing dozens of tabs after every execution. The
        dock is recreated lazily from the record when the user opens it.
        """
        self._display_results[node_id] = record
        if visible:
            self._replace_result_dock(node_id, self._dock_from_display_record(record))
            return
        old = self._result_docks.pop(node_id, None)
        if old is not None:
            self.removeDockWidget(old)
            old.deleteLater()

    def _restore_persisted_results(self, payload: Any) -> None:
        if not isinstance(payload, dict): return
        display = payload.get("display", {}); visibility = payload.get("visibility", {})
        if not isinstance(display, dict): return
        restored = 0
        for node_id, raw_record in display.items():
            if node_id != "__execution_summary__" and node_id not in self.scene.nodes: continue
            try:
                record = deserialise_display_record(dict(raw_record))
                self._install_display_result(str(node_id), record, visible=bool(visibility.get(node_id, False)))
                restored += 1
            except (KeyError, TypeError, ValueError, OSError) as exc:
                LOGGER.warning("Could not restore saved result %s: %s", node_id, exc)
        if restored:
            self.statusBar().showMessage(f"Restored {restored} saved result tab(s)", 5000)

    def _forget_result_dock(self, node_id: str, dock: QDockWidget) -> None:
        """Forget a result dock only when the destroyed object is still registered."""
        if self._result_docks.get(node_id) is dock:
            self._result_docks.pop(node_id, None)

    def _set_result_visible(self, node_id: str, visible: bool) -> bool:
        dock = self._result_docks.get(node_id)
        if dock is None and node_id in self._display_results:
            try:
                dock = self._dock_from_display_record(self._display_results[node_id])
                self._replace_result_dock(node_id, dock)
            except (KeyError, TypeError, ValueError) as exc:
                LOGGER.warning("Could not recreate result dock %s: %s", node_id, exc)
                return False
        if dock is None:
            return False
        if visible:
            # QDockWidget.close() hides (rather than deletes) result docks. Keep
            # the dock registered and restore both its direct visibility state and
            # its toggle action. ``isVisible()`` is only true when the main window
            # and all ancestors are visible, so tests must show the main window.
            toggle_action = dock.toggleViewAction()
            if toggle_action is not None:
                toggle_action.setChecked(True)
            dock.setVisible(True)
            dock.show()
            dock.raise_()
            dock.activateWindow()
        else:
            toggle_action = dock.toggleViewAction()
            if toggle_action is not None:
                toggle_action.setChecked(False)
            dock.hide()
        return True

    @Slot(str)
    def show_result_for_node(self, node_id: str) -> None:
        """Restore a previously generated or project-persisted result dock."""
        if self._set_result_visible(node_id, True):
            self.statusBar().showMessage("Result restored", 2500)
            return
        node = self.scene.nodes.get(node_id)
        if node is None:
            QMessageBox.information(self, "Open Result", "That result is no longer part of the current workflow.")
            return
        if node.block_type not in RESULT_BLOCK_TYPES:
            QMessageBox.information(self, "Open Result", "The selected block does not own a result window.")
            return
        QMessageBox.information(self, "Open Result", "No result is available for this block yet. Run the workflow first.")

    def show_selected_result(self) -> None:
        nodes = self.scene.selected_nodes()
        if len(nodes) != 1:
            QMessageBox.information(self, "Open Result", "Select exactly one display block first.")
            return
        self.show_result_for_node(nodes[0].node_id)

    def _available_result_ids(self) -> set[str]:
        """Return every result that can currently be opened.

        Most result docks have a serialisable record in ``_display_results``.
        A newly-created or legacy dock can briefly exist before that record is
        installed, though, and it must still appear in View > Results.
        """
        return set(self._display_results) | set(self._result_docks)

    def show_all_results(self) -> None:
        result_ids = self._available_result_ids()
        if not result_ids:
            QMessageBox.information(self, "Results", "No workflow results are currently available. Run the workflow first.")
            return
        restored = sum(1 for node_id in result_ids if self._set_result_visible(node_id, True))
        self.statusBar().showMessage(f"Restored {restored} result tab(s)", 3000)

    def hide_all_results(self) -> None:
        for dock in self._result_docks.values():
            dock.hide()
        result_count = len(self._available_result_ids())
        if result_count:
            self.statusBar().showMessage(f"Hidden {result_count} result tab(s)", 3000)

    def _result_menu_label(self, node_id: str, dock: QDockWidget | None = None) -> str:
        if node_id == "__execution_summary__":
            return "Execution Summary"
        node = self.scene.nodes.get(node_id)
        record = self._display_results.get(node_id, {})
        title = dock.windowTitle().strip() if dock is not None else str(record.get("title", "")).strip()
        block_name = (node.custom_label or node.block.display_name) if node is not None else title or "Result"
        return block_name if not title or title == block_name else f"{block_name} — {title}"

    def _rebuild_results_menu(self) -> None:
        self.results_menu.clear()
        self.results_menu.addAction(self.show_selected_result_action)
        self.results_menu.addAction(self.show_all_results_action)
        self.results_menu.addAction(self.hide_all_results_action)
        self.results_menu.addAction(self.result_display_preferences_action)
        self.results_menu.addSeparator()
        result_ids = self._available_result_ids()
        if not result_ids:
            empty = self.results_menu.addAction("No results available — run the workflow first")
            empty.setEnabled(False)
            return
        for node_id in sorted(result_ids, key=lambda nid: self._result_menu_label(nid, self._result_docks.get(nid)).lower()):
            dock = self._result_docks.get(node_id)
            action = self.results_menu.addAction(self._result_menu_label(node_id, dock))
            action.setCheckable(True); action.setChecked(bool(dock and dock.isVisible()))
            action.triggered.connect(lambda checked=False, nid=node_id: self._set_result_visible(nid, checked))

    def _prune_result_docks(self) -> None:
        """Remove result tabs and saved payloads whose workflow blocks were deleted."""
        stale_ids = [
            node_id
            for node_id in self._available_result_ids()
            if node_id != "__execution_summary__" and node_id not in self.scene.nodes
        ]
        for node_id in stale_ids:
            self._display_results.pop(node_id, None)
            dock = self._result_docks.pop(node_id, None)
            if dock is not None: self.removeDockWidget(dock); dock.deleteLater()

    def _show_result_docks(self, graph: WorkflowGraph, report: ExecutionReport) -> tuple[int, int]:
        """Store generated display results and apply the configured opening policy.

        Returns ``(primary_result_count, visible_primary_result_count)`` so the
        completion message can tell the user when additional results are waiting
        in View → Results.
        """
        display_types = {"scope", "multi_signal_scope", "spectrum_analyser", "data_table", "statistics_display", "spectrogram_viewer"}
        records: list[tuple[str, dict[str, Any]]] = []
        display_node_ids = {node_id for node_id, node in graph.nodes.items() if node.block.type_name in display_types}
        previously_visible = {node_id for node_id, dock in self._result_docks.items() if not dock.isHidden()}
        selected_nodes = self.scene.selected_nodes()
        selected_result_id = selected_nodes[0].node_id if len(selected_nodes) == 1 else None

        for node_id, node in graph.nodes.items():
            type_name = node.block.type_name
            if type_name not in display_types:
                continue
            record: dict[str, Any] | None = None
            if type_name in {"scope", "multi_signal_scope"}:
                signals = [value for port in range(node.block.input_count) if isinstance((value := self._connected_value(graph, report, node_id, port)), SignalData)]
                if signals:
                    record = {"kind": "scope", "title": str(node.block.params.get("title", "Signal Scope")), "signals": signals, "options": {
                        "max_points": int(node.block.params.get("max_display_points", 100_000)), "grid": bool(node.block.params.get("grid", True)), "legend": bool(node.block.params.get("legend", True)),
                        "line_width": float(node.block.params.get("line_width", 1.5)), "line_style": str(node.block.params.get("line_style", "solid")), "show_markers": bool(node.block.params.get("show_markers", False)),
                        "show_peaks": bool(node.block.params.get("show_peaks", False)), "auto_scale": bool(node.block.params.get("auto_scale", True)), "x_min": str(node.block.params.get("x_min", "")),
                        "x_max": str(node.block.params.get("x_max", "")), "y_min": str(node.block.params.get("y_min", "")), "y_max": str(node.block.params.get("y_max", "")),}}
            elif type_name == "spectrum_analyser":
                spectrum = self._connected_value(graph, report, node_id, 1)
                if not isinstance(spectrum, SpectrumData):
                    signal = self._connected_value(graph, report, node_id, 0)
                    if isinstance(signal, SignalData):
                        spectrum = FFTBlock(window=node.block.params.get("window", "hann")).execute([signal])[0]
                if isinstance(spectrum, SpectrumData):
                    record = {"kind": "spectrum", "title": str(node.block.params.get("title", "Spectrum Analyser")), "value": spectrum, "options": {"log_frequency": node.block.params.get("frequency_scale") == "logarithmic", "decibel": node.block.params.get("amplitude_scale") == "decibel"}}
            elif type_name in {"data_table", "statistics_display"}:
                value = self._connected_value(graph, report, node_id, 0)
                if type_name == "statistics_display" and isinstance(value, SignalData):
                    value = DescriptiveStatisticsBlock().execute([value])[0]
                if value is not None:
                    title = node.block.display_name
                    maximum_rows = int(node.block.params.get("maximum_rows", 10_000))
                    if isinstance(value, SignalData):
                        stored = TableResult(value.to_frame(), name=value.name)
                    elif isinstance(value, ScalarResult):
                        stored = TableResult(pd.DataFrame({"name": [value.name], "value": [value.value], "unit": [value.unit]}), name=title)
                    elif isinstance(value, TableResult):
                        stored = value
                    else:
                        stored = TableResult(pd.DataFrame({"value": [repr(value)]}), name=title)
                    record = {"kind": "table", "title": title, "value": stored, "options": {"maximum_rows": maximum_rows}}
            elif type_name == "spectrogram_viewer":
                value = self._connected_value(graph, report, node_id, 0)
                if isinstance(value, SpectrogramData):
                    record = {"kind": "spectrogram", "title": str(node.block.params.get("title", "Spectrogram")), "value": value, "options": {"minimum_frequency": float(node.block.params.get("minimum_frequency", 0.0)), "maximum_frequency": float(node.block.params.get("maximum_frequency", 0.0)), "colour_map": str(node.block.params.get("colour_map", "viridis"))}}
            if record is not None:
                records.append((node_id, record))

        summary_rows = []
        for node_id in report.executed_nodes + report.cached_nodes:
            graph_node = graph.nodes[node_id]
            summary_rows.append({"block": graph_node.label or graph_node.block.display_name, "state": graph_node.state, "execution_ms": graph_node.execution_seconds * 1000, "outputs": len(graph_node.last_outputs)})
        summary_id: str | None = None
        if summary_rows:
            summary_id = "__execution_summary__"
            records.append((summary_id, {"kind": "table", "title": "Execution Summary", "value": TableResult(pd.DataFrame(summary_rows), name="Execution Summary"), "options": {"maximum_rows": 10_000}}))

        produced_ids = {node_id for node_id, _record in records}
        for stale_id in (display_node_ids | {"__execution_summary__"}) - produced_ids:
            self._display_results.pop(stale_id, None)
            stale_dock = self._result_docks.pop(stale_id, None)
            if stale_dock is not None:
                self.removeDockWidget(stale_dock)
                stale_dock.deleteLater()

        primary_ids = [node_id for node_id, _record in records if node_id != summary_id]
        app_settings = settings()
        visible_ids = select_auto_open_result_ids(
            primary_ids,
            summary_result_id=summary_id,
            previously_visible_ids=previously_visible,
            selected_result_id=selected_result_id,
            mode=app_settings.value("results/auto_open_mode", "smart", type=str),
            smart_limit=app_settings.value("results/auto_open_limit", 3, type=int),
        )
        for node_id, record in records:
            self._install_display_result(node_id, record, visible=node_id in visible_ids)

        visible_primary = sum(node_id in visible_ids for node_id in primary_ids)
        return len(primary_ids), visible_primary

    def _clear_result_docks(self, *, clear_records: bool = False) -> None:
        docks = list(self._result_docks.values()); self._result_docks.clear()
        for dock in docks: self.removeDockWidget(dock); dock.deleteLater()
        if clear_records: self._display_results.clear()

    # --------------------------------------------------------------- campaigns
    def _current_campaign_workflow_document(self) -> dict[str, Any]:
        payload = self._project_payload(relative_paths=False, include_results=False)
        payload["campaign"] = None
        payload["results"] = {"display": {}, "visibility": {}}
        return {"format": "SignalDojo Project", "project_version": PROJECT_VERSION, **payload}

    def new_campaign(self) -> None:
        if not self.scene.nodes:
            QMessageBox.information(self, "New Test Campaign", "Create or open a workflow before creating a campaign.")
            return
        dialog = CampaignSetupDialog(None, self._current_campaign_workflow_document(), self)
        if not dialog.exec(): return
        self.campaign = dialog.value(); self.campaign_dashboard.set_campaign(self.campaign); self.campaign_dashboard.show(); self._mark_project_dirty()
        self.statusBar().showMessage("Test campaign created. Save the project before execution.", 6000)

    def open_campaign(self) -> None:
        if not self._confirm_discard_changes(): return
        path, _ = QFileDialog.getOpenFileName(self, "Open SignalDojo Campaign", "", "SignalDojo campaign project (*.sdojo)")
        if not path: return
        try:
            document = load_project(path)
            if not document.get("campaign"):
                raise ValueError("The selected SignalDojo project does not contain a test campaign.")
        except (ValueError, OSError) as exc:
            QMessageBox.critical(self, "Open Campaign", str(exc)); return
        self.open_project_path(path, confirm_discard=False)

    def setup_campaign(self) -> None:
        if self.campaign is None:
            self.new_campaign(); return
        dialog = CampaignSetupDialog(self.campaign, self._current_campaign_workflow_document(), self)
        if not dialog.exec(): return
        self.campaign = dialog.value(); self.campaign_dashboard.set_campaign(self.campaign); self.campaign_dashboard.show(); self._mark_project_dirty(); self.statusBar().showMessage("Campaign settings updated", 4000)

    def _start_campaign(self, *, retry_failed: bool = False) -> None:
        if self._campaign_thread is not None:
            return
        if self._thread is not None:
            QMessageBox.information(
                self, "Run Campaign",
                "Wait for the interactive workflow to finish or stop it before running a campaign.",
            )
            return
        if self._campaign_report_thread is not None:
            QMessageBox.information(
                self, "Run Campaign",
                "Wait for campaign report generation to finish or cancel it first.",
            )
            return
        if self.campaign is None:
            QMessageBox.information(self, "Run Campaign", "Create or open a test campaign first."); return
        if self.current_project is None:
            QMessageBox.information(self, "Run Campaign", "Save the project before executing its campaign so workflow and result provenance have a stable location.")
            if not self.save_project(save_as=True): return
        if not self.campaign.workflow_path:
            self.campaign.workflow_document = self._current_campaign_workflow_document()
        errors = self.campaign.validate()
        if errors:
            QMessageBox.warning(self, "Campaign Validation", "\n".join(f"• {error}" for error in errors)); return
        self._campaign_runner = CampaignRunner(self.campaign, project_directory=self.current_project.parent if self.current_project else None)
        self._campaign_thread = QThread(self); self._campaign_worker = CampaignWorker(self._campaign_runner, retry_failed); self._campaign_worker.moveToThread(self._campaign_thread)
        self._campaign_thread.started.connect(self._campaign_worker.run); self._campaign_worker.overall_progress.connect(self._on_campaign_progress); self._campaign_worker.run_progress.connect(self._on_campaign_run_progress); self._campaign_worker.completed.connect(self._on_campaign_completed); self._campaign_worker.failed.connect(self._on_campaign_failed); self._campaign_worker.completed.connect(self._campaign_thread.quit); self._campaign_worker.failed.connect(self._campaign_thread.quit); self._campaign_thread.finished.connect(self._cleanup_campaign_worker)
        self.campaign_dashboard.set_running(True); self.campaign_dashboard.show(); self.run_campaign_action.setEnabled(False); self.cancel_campaign_action.setEnabled(True); self.progress_bar.setVisible(True); self.progress_bar.setRange(0, max(1, len(self.campaign.runs))); self.progress_bar.setValue(0); self.statusBar().showMessage("Preparing test campaign…"); self._campaign_thread.start()

    def run_campaign(self, _checked: bool = False) -> None:
        self._start_campaign(retry_failed=False)

    def retry_failed_campaign_runs(self) -> None:
        if self.campaign is None: QMessageBox.information(self, "Retry Failed Runs", "No campaign is open."); return
        if not any(run.status in {RunStatus.ERROR, RunStatus.FAILED, RunStatus.CANCELLED} for run in self.campaign.runs):
            QMessageBox.information(self, "Retry Failed Runs", "There are no failed, error or cancelled runs to retry."); return
        self._start_campaign(retry_failed=True)

    def cancel_campaign(self) -> None:
        if self._campaign_worker is not None:
            self._campaign_worker.cancel(); self.statusBar().showMessage("Campaign cancellation requested…")

    @Slot(object, int, int)
    def _on_campaign_progress(self, run: object, index: int, total: int) -> None:
        self.progress_bar.setRange(0, max(1, total)); self.progress_bar.setValue(index); self.campaign_dashboard.refresh()
        name = getattr(run, "file_name", "run"); status = getattr(getattr(run, "status", None), "value", "")
        self.statusBar().showMessage(f"Campaign run {index} of {total}: {name} — {status}")

    @Slot(str, str, int, int)
    def _on_campaign_run_progress(self, run_id: str, node_id: str, index: int, total: int) -> None:
        self.statusBar().showMessage(f"Campaign {run_id[:8]} — block {index} of {total} ({node_id})")

    @Slot(object)
    def _on_campaign_completed(self, summary: CampaignExecutionSummary) -> None:
        self.campaign_dashboard.refresh(); self._mark_project_dirty()
        self.statusBar().showMessage(
            f"Campaign completed in {summary.duration_seconds:.2f} s — {summary.passed_runs} passed, {summary.failed_runs} failed, "
            f"{summary.warning_runs} warning, {summary.error_runs} error, {summary.reused_runs} reused", 15000,
        )

    @Slot(str)
    def _on_campaign_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Campaign Error", message); self.statusBar().showMessage("Campaign execution failed", 6000)

    @Slot()
    def _cleanup_campaign_worker(self) -> None:
        if self._campaign_worker: self._campaign_worker.deleteLater()
        if self._campaign_thread: self._campaign_thread.deleteLater()
        self._campaign_worker = None; self._campaign_thread = None; self._campaign_runner = None
        self.campaign_dashboard.set_running(False); self.run_campaign_action.setEnabled(True); self.cancel_campaign_action.setEnabled(False); self.progress_bar.setVisible(False)

    def set_campaign_reference(self, run_id: str) -> None:
        if not self.campaign or not self.campaign.run_by_id(run_id): return
        self.campaign.reference_run_id = run_id; self.campaign.touch(); self._mark_project_dirty(); self.campaign_dashboard.refresh(); self.statusBar().showMessage(f"Reference run set to {run_id}", 4000)

    @Slot(object)
    def compare_campaign_runs(self, run_ids: object) -> None:
        selected = [str(value) for value in (run_ids or [])]
        if self.campaign is None: QMessageBox.information(self, "Compare Runs", "No campaign is open."); return
        if len(selected) < 2: QMessageBox.information(self, "Compare Runs", "Select at least two campaign runs in the dashboard."); return
        CampaignComparisonDialog(self.campaign, selected, self).exec()

    def open_campaign_run(self, run_id: str) -> None:
        if not self.campaign:
            return
        run = self.campaign.run_by_id(run_id)
        if run is None:
            return

        # Closing a campaign detail dock hides it rather than destroying it.
        # Reuse that dock when the user opens the same run again instead of
        # creating hidden duplicates and leaking Qt widgets.
        existing = self._campaign_detail_docks.get(run_id)
        if existing is not None:
            existing.setVisible(True); existing.show(); existing.raise_()
            signal_dock = self._campaign_detail_docks.get(f"{run_id}:signals")
            if signal_dock is not None:
                signal_dock.setVisible(True); signal_dock.show(); signal_dock.raise_()
            return

        rows = [{"type": "metric", "name": name, "value": value, "unit": run.metric_units.get(name, ""), "status": "", "explanation": ""} for name, value in run.metrics.items()]
        rows.extend({"type": "requirement", "name": result.requirement_name, "value": result.measured_value, "unit": result.unit, "status": result.status.value, "explanation": result.explanation} for result in run.requirement_results)
        rows.extend({"type": "warning", "name": "Warning", "value": "", "unit": "", "status": RunStatus.WARNING.value, "explanation": warning} for warning in run.warnings)
        rows.extend({"type": "error", "name": "Error", "value": "", "unit": "", "status": RunStatus.ERROR.value, "explanation": error} for error in run.errors)
        table = TableResult(pd.DataFrame(rows), name=f"Campaign Run — {run.file_name}")
        dock = TableDock(f"Campaign Run — {run.file_name}", table, 10_000, self); dock.setObjectName(f"CampaignRun_{run_id}"); dock.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False); self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, dock); dock.show(); dock.raise_(); self._campaign_detail_docks[run_id] = dock
        signals: list[SignalData] = []
        for payload in run.detail_results.values():
            try:
                value = deserialise_result(payload)
                if isinstance(value, SignalData): signals.append(value)
            except Exception: continue
            if len(signals) >= 4: break
        if signals:
            scope = ScopeDock(f"Run Signals — {run.file_name}", signals, self.campaign.execution.maximum_signal_points, self); scope.setObjectName(f"CampaignRunSignals_{run_id}"); scope.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False); self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, scope); self.tabifyDockWidget(dock, scope); scope.show(); scope.raise_(); self._campaign_detail_docks[f"{run_id}:signals"] = scope

    def _clear_campaign_detail_docks(self) -> None:
        for dock in self._campaign_detail_docks.values():
            self.removeDockWidget(dock); dock.deleteLater()
        self._campaign_detail_docks.clear()

    def generate_campaign_report(self) -> None:
        if self.campaign is None: QMessageBox.information(self, "Campaign Report", "No campaign is open."); return
        if self._campaign_report_thread is not None: return
        if self._campaign_thread is not None or self._thread is not None:
            QMessageBox.information(self, "Campaign Report", "Wait for processing to finish before generating a campaign report."); return
        output = QFileDialog.getExistingDirectory(self, "Campaign Report Output Directory", self.campaign.report.output_directory or str(Path.home()))
        if not output: return
        self.campaign.report.output_directory = output
        self._campaign_report_thread = QThread(self); self._campaign_report_worker = CampaignReportWorker(self.campaign, output, self._workflow_png()); self._campaign_report_worker.moveToThread(self._campaign_report_thread)
        self._campaign_report_thread.started.connect(self._campaign_report_worker.run)
        self._campaign_report_worker.progress.connect(self._on_campaign_report_progress)
        self._campaign_report_worker.completed.connect(self._on_campaign_report_completed)
        self._campaign_report_worker.failed.connect(self._on_campaign_report_failed)
        self._campaign_report_worker.cancelled.connect(self._on_campaign_report_cancelled)
        self._campaign_report_worker.completed.connect(self._campaign_report_thread.quit)
        self._campaign_report_worker.failed.connect(self._campaign_report_thread.quit)
        self._campaign_report_worker.cancelled.connect(self._campaign_report_thread.quit)
        self._campaign_report_thread.finished.connect(self._cleanup_campaign_report_worker)
        self.campaign_report_action.setEnabled(False); self.cancel_campaign_report_action.setEnabled(True)
        self.progress_bar.setVisible(True); self.progress_bar.setRange(0, 3); self.progress_bar.setValue(0)
        self.statusBar().showMessage("Generating campaign PDF, Excel and CSV reports…"); self._campaign_report_thread.start()

    def cancel_campaign_report(self) -> None:
        if self._campaign_report_worker is not None:
            self._campaign_report_worker.cancel()
            self.statusBar().showMessage("Campaign report cancellation requested…")

    @Slot(str, int, int)
    def _on_campaign_report_progress(self, stage: str, index: int, total: int) -> None:
        self.progress_bar.setRange(0, max(1, total)); self.progress_bar.setValue(index)
        self.statusBar().showMessage(stage)

    @Slot(object)
    def _on_campaign_report_completed(self, paths: object) -> None:
        self._mark_project_dirty(); rendered = ", ".join(str(path) for path in dict(paths).values()); self.statusBar().showMessage(f"Campaign reports generated: {rendered}", 12000)

    @Slot(str)
    def _on_campaign_report_failed(self, message: str) -> None:
        QMessageBox.critical(self, "Campaign Report", message)

    @Slot()
    def _on_campaign_report_cancelled(self) -> None:
        self.statusBar().showMessage("Campaign report generation cancelled", 5000)

    @Slot()
    def _cleanup_campaign_report_worker(self) -> None:
        if self._campaign_report_worker: self._campaign_report_worker.deleteLater()
        if self._campaign_report_thread: self._campaign_report_thread.deleteLater()
        self._campaign_report_worker = None; self._campaign_report_thread = None
        self.campaign_report_action.setEnabled(True); self.cancel_campaign_report_action.setEnabled(False); self.progress_bar.setVisible(False)

    # --------------------------------------------------------------- previews
    def _single_selected_node(self) -> NodeItem | None:
        nodes = self.scene.selected_nodes()
        if len(nodes) != 1: QMessageBox.information(self, "SignalDojo", "Select exactly one block first."); return None
        return nodes[0]

    def preview_selected_import(self) -> None:
        node = self._single_selected_node()
        if node is None: return
        if not isinstance(node.block, ImportDataBlock): QMessageBox.information(self, "Import Preview", "Select an Import Data block."); return
        dialog = ImportPreviewDialog(node.block, self)
        if dialog.exec(): dialog.apply(); node.params = node.block.serialise_params(); self.properties.show_node(node); self._on_graph_changed()

    def preview_selected_filter(self) -> None:
        node = self._single_selected_node()
        if node is None: return
        if not callable(getattr(node.block, "frequency_response", None)): QMessageBox.information(self, "Filter Preview", "The selected block does not expose a frequency response."); return
        FilterResponseDialog(node.block, self).exec()

    # ------------------------------------------------------------ annotations
    def add_comment(self) -> None:
        self.scene.create_comment(self.view.mapToScene(self.view.viewport().rect().center()))

    def add_group(self) -> None:
        self.scene.create_group(self.view.mapToScene(self.view.viewport().rect().center()) - QPointF(250, 150))

    def _fit_workflow(self) -> None:
        if self.scene.items(): self.view.fitInView(self.scene.itemsBoundingRect().adjusted(-80, -80, 80, 80), Qt.AspectRatioMode.KeepAspectRatio)

    # ------------------------------------------------------------- appearance
    def _apply_theme(self, dark: bool) -> None:
        app = QApplication.instance()
        if app is None:
            return
        if dark:
            app.setStyleSheet(
                """
                QMainWindow,QDockWidget,QMenuBar,QMenu,QWidget { background:#20262d; color:#edf1f5; }
                QLineEdit,QPlainTextEdit,QSpinBox,QDoubleSpinBox,QComboBox,QListWidget,QTableWidget,QTableView {
                    background:#151a20; color:#edf1f5; border:1px solid #46515d; padding:4px;
                    alternate-background-color:#1b2128; selection-background-color:#355c85;
                    selection-color:#ffffff; gridline-color:#394450;
                }
                QTableView#CampaignRunTable { background:#131920; alternate-background-color:#182029; gridline-color:#394450; }
                QPushButton,QToolButton { background:#35414d; border:1px solid #536170; padding:5px 9px; border-radius:3px; }
                QPushButton:hover,QToolButton:hover { background:#40505f; }
                QPushButton:disabled,QToolButton:disabled { color:#7f8b96; background:#2a333c; border-color:#394550; }
                QToolBar { border-bottom:1px solid #3a444f; spacing:4px; }
                QLabel#ToolbarSectionLabel { font-weight:700; color:#cfe2f3; padding-left:6px; padding-right:4px; }
                QHeaderView::section { background:#2d3741; color:#edf1f5; padding:5px; border:1px solid #3d4753; }

                QDialog#CampaignSetupDialog { background:#1b2128; }
                QFrame#CampaignSetupHeader { background:#27313b; border:1px solid #3d4956; border-radius:7px; }
                QLabel#CampaignSetupTitle { font-size:18px; font-weight:700; color:#ffffff; }
                QLabel#CampaignStepTitle { font-size:13px; font-weight:650; color:#bcd8ef; }
                QLabel#CampaignStepDescription,QLabel#CampaignHelpText { color:#aebbc7; }
                QLabel#CampaignPageIntro { color:#d8e4ee; font-size:13px; }
                QLabel#CampaignStepCounter { color:#aebbc7; }
                QListWidget#CampaignSetupSteps { background:#151a20; border:1px solid #3c4854; border-radius:6px; padding:5px; outline:none; }
                QListWidget#CampaignSetupSteps::item { padding:11px 9px; margin:2px; border-radius:4px; }
                QListWidget#CampaignSetupSteps::item:selected { background:#355c85; color:#ffffff; }
                QListWidget#CampaignSetupSteps::item:hover:!selected { background:#26313b; }
                QScrollArea#CampaignStepScrollArea { border:none; background:transparent; }
                QScrollArea#CampaignStepScrollArea > QWidget > QWidget { background:#1b2128; }
                QDialog#CampaignSetupDialog QGroupBox { border:1px solid #3c4854; border-radius:6px; margin-top:12px; padding-top:8px; font-weight:600; }
                QDialog#CampaignSetupDialog QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; color:#dce7f0; }
                QDialog#CampaignSetupDialog QTabWidget::pane { border:1px solid #3c4854; border-radius:4px; }
                QDialog#CampaignSetupDialog QTabBar::tab { background:#27313a; border:1px solid #3c4854; padding:7px 12px; }
                QDialog#CampaignSetupDialog QTabBar::tab:selected { background:#355c85; color:#ffffff; }
                QFrame#CampaignValidationBanner { background:#4b2d31; border:1px solid #a65a63; border-radius:6px; }
                QPushButton#PrimaryCampaignButton { background:#2f70a8; border:1px solid #5794c5; color:#ffffff; font-weight:650; padding:6px 14px; }
                QPushButton#PrimaryCampaignButton:hover { background:#397fb9; }
                """
            )
            self.view.setStyleSheet("background:#171c22")
        else:
            app.setStyleSheet(
                """
                QTableView,QTableWidget { background:#ffffff; color:#1f2730; alternate-background-color:#f3f6f9;
                    selection-background-color:#cfe3f7; selection-color:#11161c; gridline-color:#d2dae3;
                    border:1px solid #c9d3dd; padding:4px; }
                QTableView#CampaignRunTable { gridline-color:#d6dee7; }
                QHeaderView::section { background:#edf2f6; color:#1f2730; padding:5px; border:1px solid #d0d8e0; }
                QLabel#ToolbarSectionLabel { font-weight:700; color:#39516b; padding-left:6px; padding-right:4px; }

                QDialog#CampaignSetupDialog { background:#f3f6f8; }
                QFrame#CampaignSetupHeader { background:#ffffff; border:1px solid #d2dae2; border-radius:7px; }
                QLabel#CampaignSetupTitle { font-size:18px; font-weight:700; color:#17212b; }
                QLabel#CampaignStepTitle { font-size:13px; font-weight:650; color:#315f86; }
                QLabel#CampaignStepDescription,QLabel#CampaignHelpText { color:#5d6b78; }
                QLabel#CampaignPageIntro { color:#334452; font-size:13px; }
                QLabel#CampaignStepCounter { color:#5d6b78; }
                QListWidget#CampaignSetupSteps { background:#ffffff; border:1px solid #d2dae2; border-radius:6px; padding:5px; outline:none; }
                QListWidget#CampaignSetupSteps::item { padding:11px 9px; margin:2px; border-radius:4px; }
                QListWidget#CampaignSetupSteps::item:selected { background:#d4e7f7; color:#17324a; }
                QListWidget#CampaignSetupSteps::item:hover:!selected { background:#eef4f8; }
                QScrollArea#CampaignStepScrollArea { border:none; background:transparent; }
                QScrollArea#CampaignStepScrollArea > QWidget > QWidget { background:#f3f6f8; }
                QDialog#CampaignSetupDialog QGroupBox { border:1px solid #d2dae2; border-radius:6px; margin-top:12px; padding-top:8px; font-weight:600; background:#ffffff; }
                QDialog#CampaignSetupDialog QGroupBox::title { subcontrol-origin:margin; left:10px; padding:0 5px; color:#273846; }
                QDialog#CampaignSetupDialog QTabWidget::pane { border:1px solid #d2dae2; border-radius:4px; background:#ffffff; }
                QDialog#CampaignSetupDialog QTabBar::tab { background:#edf2f6; border:1px solid #d2dae2; padding:7px 12px; }
                QDialog#CampaignSetupDialog QTabBar::tab:selected { background:#d4e7f7; color:#17324a; }
                QFrame#CampaignValidationBanner { background:#fff1f1; border:1px solid #d68a8a; border-radius:6px; color:#721c24; }
                QPushButton#PrimaryCampaignButton { background:#2f70a8; border:1px solid #245e8d; color:#ffffff; font-weight:650; padding:6px 14px; border-radius:3px; }
                QPushButton#PrimaryCampaignButton:hover { background:#397fb9; }
                """
            )
            self.view.setStyleSheet("background:#f4f6f8")
        self.view.set_theme(dark)

    # ----------------------------------------------------------- help/recent
    def _add_recent(self, path: Path) -> None:
        app_settings = settings(); recent = [str(path)] + [str(item) for item in app_settings.value("recent/projects", [], type=list) if str(item) != str(path)]; app_settings.setValue("recent/projects", recent[:10]); self._update_recent_menu()

    def _update_recent_menu(self) -> None:
        if not hasattr(self, "recent_menu"): return
        self.recent_menu.clear(); recent = settings().value("recent/projects", [], type=list)
        for raw in recent:
            path = Path(str(raw)); action = self.recent_menu.addAction(path.name); action.setToolTip(str(path)); action.setEnabled(path.exists()); action.triggered.connect(lambda _checked=False, p=path: self.open_project_path(p))
        if not recent: self.recent_menu.addAction("No recent projects").setEnabled(False)

    def open_documentation(self) -> None:
        path = resource_path("documentation/index.html")
        if not path.exists(): path = resource_path("README.md")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def show_selected_block_help(self) -> None:
        nodes = self.scene.selected_nodes()
        block_cls = nodes[0].block.__class__ if len(nodes) == 1 else None
        if block_cls is None:
            item = self.library.currentItem()
            type_name = str(item.data(Qt.ItemDataRole.UserRole)) if item and item.data(Qt.ItemDataRole.UserRole) else ""
            block_cls = BLOCK_TYPES.get(type_name)
        if block_cls is None:
            QMessageBox.information(self, "Block Help", "Select a workflow block or a block-library item, then press F1.")
            return
        inputs = ", ".join(block_cls.input_types) if block_cls.input_count else "None"
        outputs = ", ".join(block_cls.output_types) if block_cls.output_count else "None"
        rows = "".join(
            f"<tr><td><b>{escape(spec.label)}</b></td><td>{escape(str(spec.default))}</td><td>{escape(spec.kind)}</td></tr>"
            for spec in block_cls.parameters
        )
        html = (
            f"<h2>{escape(block_cls.display_name)}</h2><p>{escape(block_cls.description)}</p>"
            f"<p><b>Category:</b> {escape(block_cls.category)}<br><b>Inputs:</b> {escape(inputs)}<br><b>Outputs:</b> {escape(outputs)}</p>"
            f"<h3>Parameters</h3><table cellspacing='6'><tr><th align='left'>Name</th><th align='left'>Default</th><th align='left'>Type</th></tr>{rows or '<tr><td colspan=3>None</td></tr>'}</table>"
        )
        box = QMessageBox(self); box.setWindowTitle(f"{block_cls.display_name} — Help"); box.setIcon(QMessageBox.Icon.Information); box.setTextFormat(Qt.TextFormat.RichText); box.setText(html); box.exec()

    def open_issue_reporting(self) -> None:
        path = resource_path("documentation/ISSUE_REPORTING.md")
        if not path.exists(): path = resource_path("documentation/TROUBLESHOOTING.md")
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def show_diagnostics(self) -> None:
        DiagnosticsDialog(self.validate_workflow(show_success=False), self).exec()

    def check_for_updates(self, *, manual: bool = True) -> None:
        if self._update_thread is not None: return
        manifest_url = settings().value("updates/manifest_url", "", type=str).strip()
        if not manifest_url:
            if manual: QMessageBox.information(self, "Check for Updates", "No update manifest URL is configured. A distributor can configure one in Preferences.")
            return
        self._manual_update_check = manual; self.check_updates_action.setEnabled(False); self.statusBar().showMessage("Checking for updates…")
        self._update_thread = QThread(self); self._update_worker = UpdateWorker(manifest_url); self._update_worker.moveToThread(self._update_thread)
        self._update_thread.started.connect(self._update_worker.run); self._update_worker.completed.connect(self._on_update_manifest); self._update_worker.failed.connect(self._on_update_error)
        self._update_worker.completed.connect(self._update_thread.quit); self._update_worker.failed.connect(self._update_thread.quit); self._update_thread.finished.connect(self._cleanup_update_worker); self._update_thread.start()

    @Slot(object)
    def _on_update_manifest(self, manifest: UpdateManifest) -> None:
        if update_available(VERSION, manifest):
            response = QMessageBox.information(self, "SignalDojo Update", f"SignalDojo {manifest.version} is available.\n\nOpen the distributor download page?", QMessageBox.StandardButton.Open | QMessageBox.StandardButton.Cancel)
            if response == QMessageBox.StandardButton.Open: QDesktopServices.openUrl(QUrl(manifest.download_url))
        elif self._manual_update_check:
            QMessageBox.information(self, "SignalDojo Update", f"SignalDojo {VERSION} is up to date.")
        self.statusBar().showMessage("Update check completed", 4000)

    @Slot(str)
    def _on_update_error(self, message: str) -> None:
        if self._manual_update_check: QMessageBox.warning(self, "Check for Updates", f"The update manifest could not be read:\n\n{message}")
        else: LOGGER.warning("Automatic update check failed: %s", message)
        self.statusBar().showMessage("Update check failed", 4000)

    @Slot()
    def _cleanup_update_worker(self) -> None:
        if self._update_worker: self._update_worker.deleteLater()
        if self._update_thread: self._update_thread.deleteLater()
        self._update_worker = None; self._update_thread = None; self.check_updates_action.setEnabled(True)

    def open_source_licence(self) -> None:
        path = resource_path("LICENSE")
        if not path.exists():
            QMessageBox.warning(self, "Open Source Licence", "The bundled GNU GPL licence file could not be found.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def open_trademark_policy(self) -> None:
        path = resource_path("TRADEMARK_POLICY.md")
        if not path.exists():
            QMessageBox.warning(self, "Trademark Policy", "The bundled trademark policy could not be found.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            "About SignalDojo",
            f"<h2>SignalDojo {VERSION}</h2>"
            "<p><b>Build, analyse and master your signals.</b></p>"
            "<p>A professional block-based signal-processing environment for engineers, researchers and laboratory teams.</p>"
            f"<p>{len(BLOCK_TYPES)} processing and display blocks are currently registered.</p>"
            "<p><b>Free and open-source software</b><br>"
            "Created and maintained by <b>Tiago Alvarez Calderon Newton</b> with contributions from the SignalDojo community.<br>Copyright © 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors.<br>"
            "Licensed under the GNU General Public License, version 3 or any later version. "
            "You may redistribute and/or modify SignalDojo under those terms.</p>"
            "<p><b>There is absolutely no warranty</b>, to the extent permitted by law. "
            "Use Help → Open Source Licence to read the complete terms.</p>"
            "<p>The SignalDojo name and logo are addressed separately by the Trademark Policy so unofficial modified builds do not imply project endorsement.</p>",
        )

    # --------------------------------------------------------------- recovery
    def _autosave(self) -> None:
        if not self.dirty or self._thread is not None or self._campaign_thread is not None or self._campaign_report_thread is not None: return
        try: save_recovery(self._project_payload(relative_paths=False)); self.statusBar().showMessage("Autosaved recovery copy", 1500)
        except Exception: LOGGER.exception("Could not write recovery autosave")

    def _initial_prompts(self) -> None:
        if recovery_available():
            response = QMessageBox.question(self, "Recover Autosaved Project", f"SignalDojo found a recovery project from a previous session. Open it?\n\n{recovery_path()}", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if response == QMessageBox.StandardButton.Yes: self.open_project_path(recovery_path(), confirm_discard=False); self.current_project = None; self.dirty = True; self._update_title()
            else: clear_recovery()
        app_settings = settings()
        if not app_settings.value("welcome/shown_v1", False, type=bool): WelcomeDialog(self).exec(); app_settings.setValue("welcome/shown_v1", True)
        if app_settings.value("updates/automatic", False, type=bool): self.check_for_updates(manual=False)

    def _confirm_discard_changes(self) -> bool:
        if not self.dirty: return True
        response = QMessageBox.question(self, "Unsaved Changes", "Save changes to the current project?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
        if response == QMessageBox.StandardButton.Save: return self.save_project()
        if response == QMessageBox.StandardButton.Discard: return True
        return False

    def _restore_window_state(self) -> None:
        app_settings = settings(); geometry = app_settings.value("window/geometry"); state = app_settings.value("window/state")
        if geometry: self.restoreGeometry(geometry)
        if state: self.restoreState(state)
        dark = app_settings.value("appearance/dark", True, type=bool); self.dark_action.setChecked(dark); self._apply_theme(dark)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if self._thread is not None: QMessageBox.information(self, "SignalDojo", "Stop the running workflow before closing."); event.ignore(); return
        if self._campaign_thread is not None: QMessageBox.information(self, "SignalDojo", "Cancel the running test campaign before closing."); event.ignore(); return
        if self._campaign_report_thread is not None: QMessageBox.information(self, "SignalDojo", "Cancel campaign report generation before closing."); event.ignore(); return
        if self._update_thread is not None: QMessageBox.information(self, "SignalDojo", "The update check is still running. Close SignalDojo after it finishes."); event.ignore(); return
        if not self._confirm_discard_changes(): event.ignore(); return
        app_settings = settings(); app_settings.setValue("window/geometry", self.saveGeometry()); app_settings.setValue("window/state", self.saveState()); app_settings.setValue("appearance/dark", self.dark_action.isChecked())
        clear_recovery(); event.accept()
