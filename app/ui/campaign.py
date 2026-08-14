# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Qt interfaces for SignalDojo automated test campaigns."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QSortFilterProxyModel, Qt, QThread, Signal, Slot
from PySide6.QtGui import QAction, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea, QSpinBox,
    QSplitter, QStackedWidget, QTabWidget, QTableView, QTableWidget, QTableWidgetItem, QToolButton, QVBoxLayout,
    QWidget, QDockWidget,
)

from app.campaign.comparison import ComparisonResult, compare_runs, export_comparison_plot, export_comparison_tables
from app.campaign.discovery import discover_files
from app.campaign.models import (
    CampaignExecutionSettings, CampaignReportSettings, InputMapping, MetadataRule,
    MetricDefinition, RequirementDefinition, RequirementStatus, RequirementType,
    RunStatus, Severity, TestCampaign,
)
from app.campaign.metrics import SCALAR_AGGREGATIONS
from app.campaign.workflow_adapter import import_block_ids, published_metric_nodes, workflow_snapshot
from app.application import settings


_STATUS_COLOURS = {
    RunStatus.PASSED: QColor("#bcd9b8"),
    RunStatus.FAILED: QColor("#e5b4b4"),
    RunStatus.WARNING: QColor("#e6d4a3"),
    RunStatus.ERROR: QColor("#d6bdd7"),
    RunStatus.RUNNING: QColor("#b8d0e8"),
    RunStatus.CANCELLED: QColor("#c6c9cd"),
}

_MAPPING_SOURCE_LABELS = {
    "run_file": "Current run file",
    "fixed_file": "Fixed file",
    "metadata_field": "Path from metadata field",
}

_METADATA_SOURCE_LABELS = {
    "filename_regex": "File name pattern",
    "parent_folder": "Parent folder",
    "sidecar_json": "Sidecar JSON",
    "file_column": "Imported file column",
    "file_property": "File property",
    "manual": "Manual value",
}

_AGGREGATION_LABELS = {
    "auto": "Automatic", "value": "Use scalar value", "mean": "Mean", "rms": "RMS",
    "standard_deviation": "Standard deviation", "minimum": "Minimum", "maximum": "Maximum",
    "peak_to_peak": "Peak-to-peak", "dominant_frequency": "Dominant frequency",
    "sample_count": "Sample count", "duration": "Duration", "rise_time": "Rise time",
    "settling_time": "Settling time", "first": "First value", "last": "Last value",
    "custom_expression": "Custom scalar expression",
}

_REQUIREMENT_LABELS = {
    RequirementType.UPPER_LIMIT: "Upper limit", RequirementType.LOWER_LIMIT: "Lower limit",
    RequirementType.INCLUSIVE_RANGE: "Inclusive range", RequirementType.EXCLUSIVE_RANGE: "Exclusive range",
    RequirementType.ABSOLUTE_TOLERANCE: "Target ± absolute tolerance",
    RequirementType.PERCENT_TOLERANCE: "Target ± percentage tolerance",
    RequirementType.WARNING_FAILURE_THRESHOLDS: "Warning and failure thresholds",
    RequirementType.BOOLEAN: "Boolean condition", RequirementType.MINIMUM_SAMPLE_COUNT: "Minimum sample count",
    RequirementType.PEAK_LIMIT: "Peak limit", RequirementType.RMS_LIMIT: "RMS limit",
    RequirementType.FREQUENCY_BAND_LIMIT: "Frequency-band limit",
    RequirementType.SETTLING_TIME_LIMIT: "Settling-time limit",
}


class DiscoveryWorker(QObject):
    completed = Signal(object)
    failed = Signal(str)
    progress = Signal(str, int, int)

    def __init__(self, campaign: TestCampaign) -> None:
        super().__init__(); self.campaign = campaign; self.cancelled = False

    @Slot()
    def run(self) -> None:
        try:
            paths = discover_files(
                self.campaign, is_cancelled=lambda: self.cancelled,
                progress=lambda path, index, total: self.progress.emit(path, index, total),
            )
        except Exception as exc:
            self.failed.emit(str(exc)); return
        self.completed.emit(paths)

    @Slot()
    def cancel(self) -> None:
        self.cancelled = True


class CampaignSetupDialog(QDialog):
    """Responsive, step-based editor for creating and editing test campaigns."""

    _STEP_HELP = (
        "Name the campaign and choose the workflow that will be applied to every run.",
        "Choose recordings, preview them, map Import Data blocks and define metadata extraction.",
        "Select the compact engineering metrics that will be retained for every run.",
        "Define pass, warning and failure criteria for the published metrics.",
        "Choose execution behaviour, report contents and campaign-level metadata.",
    )

    def __init__(self, campaign: TestCampaign | None, current_workflow: dict[str, Any], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("CampaignSetupDialog")
        self.setWindowTitle("Create New Test Campaign" if campaign is None else "Edit Test Campaign")
        self.setModal(True)
        self.setMinimumSize(720, 480)
        self._campaign = deepcopy(campaign) if campaign else TestCampaign(name="New Test Campaign")
        self._current_workflow = deepcopy(current_workflow)
        self._external_document: dict[str, Any] | None = None
        self._discovery_thread: QThread | None = None
        self._discovery_worker: DiscoveryWorker | None = None
        self._reject_after_discovery = False
        self._loading_campaign = False
        self._step_titles: list[str] = []
        self._apply_screen_safe_size()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        header = QFrame()
        header.setObjectName("CampaignSetupHeader")
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 16, 12)
        header_layout.setSpacing(3)
        self.dialog_title = QLabel(self.windowTitle())
        self.dialog_title.setObjectName("CampaignSetupTitle")
        self.step_heading = QLabel()
        self.step_heading.setObjectName("CampaignStepTitle")
        self.step_description = QLabel()
        self.step_description.setObjectName("CampaignStepDescription")
        self.step_description.setWordWrap(True)
        header_layout.addWidget(self.dialog_title)
        header_layout.addWidget(self.step_heading)
        header_layout.addWidget(self.step_description)
        outer.addWidget(header)

        body = QSplitter(Qt.Orientation.Horizontal)
        body.setObjectName("CampaignSetupBody")
        body.setChildrenCollapsible(False)
        self.step_list = QListWidget()
        self.step_list.setObjectName("CampaignSetupSteps")
        self.step_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.step_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.step_list.setMinimumWidth(165)
        self.step_list.setMaximumWidth(215)
        self.page_stack = QStackedWidget()
        # Retain the historic attribute name for plugin/UI-test compatibility.
        self.tabs = self.page_stack
        body.addWidget(self.step_list)
        body.addWidget(self.page_stack)
        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setSizes([190, 850])
        outer.addWidget(body, 1)

        self._create_general_tab()
        self._create_inputs_tab()
        self._create_metrics_tab()
        self._create_requirements_tab()
        self._create_report_tab()

        self.validation_frame = QFrame()
        self.validation_frame.setObjectName("CampaignValidationBanner")
        validation_layout = QHBoxLayout(self.validation_frame)
        validation_layout.setContentsMargins(12, 8, 12, 8)
        self.validation_label = QLabel()
        self.validation_label.setWordWrap(True)
        self.validation_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        validation_layout.addWidget(self.validation_label, 1)
        dismiss_validation = QToolButton()
        dismiss_validation.setText("×")
        dismiss_validation.setToolTip("Dismiss this message")
        dismiss_validation.clicked.connect(self._clear_validation)
        validation_layout.addWidget(dismiss_validation)
        self.validation_frame.hide()
        outer.addWidget(self.validation_frame)

        footer = QHBoxLayout()
        self.step_counter = QLabel()
        self.step_counter.setObjectName("CampaignStepCounter")
        self.back_button = QPushButton("← &Back")
        self.next_button = QPushButton("&Next →")
        self.cancel_button = QPushButton("Cancel")
        self.save_button = QPushButton("&Save Campaign")
        self.save_button.setObjectName("PrimaryCampaignButton")
        self.save_button.setDefault(True)
        self.back_button.clicked.connect(self._go_back)
        self.next_button.clicked.connect(self._go_next)
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self._accept)
        footer.addWidget(self.step_counter)
        footer.addStretch()
        footer.addWidget(self.back_button)
        footer.addWidget(self.next_button)
        footer.addSpacing(8)
        footer.addWidget(self.cancel_button)
        footer.addWidget(self.save_button)
        outer.addLayout(footer)

        self.step_list.currentRowChanged.connect(self._set_step)
        self._on_workflow_source_changed(self.workflow_choice.currentIndex())
        self._on_execution_mode_changed(self.execution_mode.currentText())
        self._loading_campaign = True
        try:
            self._load_campaign()
        finally:
            self._loading_campaign = False
        self._on_execution_mode_changed(self.execution_mode.currentText())
        self.step_list.setCurrentRow(0)

    def _apply_screen_safe_size(self) -> None:
        screen = self.screen() or QGuiApplication.primaryScreen()
        if screen is None:
            self.resize(1040, 660)
            return
        available = screen.availableGeometry()
        width = max(720, min(1120, int(available.width() * 0.90)))
        height = max(480, min(700, int(available.height() * 0.88)))
        self.resize(width, height)

    def _add_step(self, page: QWidget, title: str, description: str) -> None:
        page.setObjectName(f"CampaignStepPage{len(self._step_titles) + 1}")
        scroll = QScrollArea()
        scroll.setObjectName("CampaignStepScrollArea")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(page)
        self.page_stack.addWidget(scroll)
        self._step_titles.append(title)
        item = QListWidgetItem(f"{len(self._step_titles)}.  {title}")
        item.setToolTip(description)
        self.step_list.addItem(item)

    def _set_step(self, index: int) -> None:
        if not 0 <= index < self.page_stack.count():
            return
        self.page_stack.setCurrentIndex(index)
        self.step_heading.setText(self._step_titles[index])
        self.step_description.setText(self._STEP_HELP[index])
        self.step_counter.setText(f"Step {index + 1} of {self.page_stack.count()}")
        self.back_button.setEnabled(index > 0)
        self.next_button.setVisible(index < self.page_stack.count() - 1)
        if index == self.page_stack.count() - 1:
            self.save_button.setFocus(Qt.FocusReason.OtherFocusReason)

    def _go_back(self) -> None:
        self.step_list.setCurrentRow(max(0, self.step_list.currentRow() - 1))

    def _go_next(self) -> None:
        self.step_list.setCurrentRow(min(self.page_stack.count() - 1, self.step_list.currentRow() + 1))

    def _show_validation(self, messages: str | list[str], *, step: int | None = None) -> None:
        text = messages if isinstance(messages, str) else "\n".join(f"• {message}" for message in messages)
        self.validation_label.setText(text)
        self.validation_frame.show()
        if step is not None:
            self.step_list.setCurrentRow(step)

    def _clear_validation(self) -> None:
        self.validation_label.clear()
        self.validation_frame.hide()

    @staticmethod
    def _configure_table(table: QTableWidget, *, stretch_last: bool = True) -> None:
        table.setAlternatingRowColors(True)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        table.setWordWrap(False)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(stretch_last)

    def _create_general_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        intro = QLabel("A test campaign applies one validated SignalDojo workflow independently to every selected recording.")
        intro.setObjectName("CampaignPageIntro")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        details_box = QGroupBox("Campaign details")
        details_form = QFormLayout(details_box)
        details_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("For example: Motor current end-of-line validation")
        self.name_edit.setClearButtonEnabled(True)
        self.description_edit = QPlainTextEdit()
        self.description_edit.setPlaceholderText("Describe the test objective, product population and any important operating conditions.")
        self.description_edit.setMinimumHeight(90)
        self.description_edit.setMaximumHeight(130)
        details_form.addRow("Campaign name", self.name_edit)
        details_form.addRow("Description", self.description_edit)
        layout.addWidget(details_box)

        workflow_box = QGroupBox("Workflow")
        workflow_form = QFormLayout(workflow_box)
        workflow_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.workflow_choice = QComboBox()
        self.workflow_choice.addItems(["Use the current workflow", "Use another .sdojo workflow"])
        self.workflow_choice.setToolTip("A snapshot of the selected workflow is stored with the campaign for traceability.")
        self.workflow_choice.currentIndexChanged.connect(self._on_workflow_source_changed)
        self.workflow_path = QLineEdit()
        self.workflow_path.setPlaceholderText("Select a .sdojo workflow file")
        self.workflow_path.setClearButtonEnabled(True)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_workflow)
        self.workflow_external_row = QWidget()
        row_layout = QHBoxLayout(self.workflow_external_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(self.workflow_path, 1)
        row_layout.addWidget(browse)
        self.workflow_help = QLabel("The selected workflow is copied into the campaign definition. The original project is never modified when campaign files are substituted.")
        self.workflow_help.setWordWrap(True)
        self.workflow_help.setObjectName("CampaignHelpText")
        workflow_form.addRow("Workflow source", self.workflow_choice)
        workflow_form.addRow("Workflow file", self.workflow_external_row)
        workflow_form.addRow(self.workflow_help)
        layout.addWidget(workflow_box)
        layout.addStretch()
        self._add_step(page, "Basics", self._STEP_HELP[0])

    def _on_workflow_source_changed(self, index: int) -> None:
        external = index == 1
        self.workflow_external_row.setVisible(external)
        self.workflow_path.setEnabled(external)
        if hasattr(self, "mapping_table") and not self._loading_campaign:
            self.mapping_table.setRowCount(0)
            self._refresh_mapping_rows()

    def _create_inputs_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        source_box = QGroupBox("1. Select input recordings")
        form = QGridLayout(source_box)
        form.setColumnStretch(1, 1)
        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText("Optional folder containing test recordings")
        self.folder_edit.setClearButtonEnabled(True)
        folder_button = QPushButton("Choose folder…")
        folder_button.clicked.connect(self._browse_folder)
        self.files_edit = QLineEdit()
        self.files_edit.setPlaceholderText("Optional explicit file list")
        self.files_edit.setClearButtonEnabled(True)
        files_button = QPushButton("Choose files…")
        files_button.clicked.connect(self._browse_files)
        self.extensions_edit = QLineEdit(".csv,.tsv,.txt,.xlsx,.xls,.json,.npy,.npz,.h5,.hdf,.hdf5,.tdms")
        self.extensions_edit.setToolTip("Comma-separated extensions included during folder discovery.")
        self.recursive_check = QCheckBox("Search subfolders recursively")
        form.addWidget(QLabel("Input folder"), 0, 0)
        form.addWidget(self.folder_edit, 0, 1)
        form.addWidget(folder_button, 0, 2)
        form.addWidget(QLabel("Specific files"), 1, 0)
        form.addWidget(self.files_edit, 1, 1)
        form.addWidget(files_button, 1, 2)
        form.addWidget(QLabel("Included file types"), 2, 0)
        form.addWidget(self.extensions_edit, 2, 1, 1, 2)
        form.addWidget(self.recursive_check, 3, 1, 1, 2)
        layout.addWidget(source_box)

        discovery_row = QHBoxLayout()
        self.preview_button = QPushButton("Discover files")
        self.preview_button.setToolTip("Scan the selected folder and explicit files without running the workflow.")
        self.preview_button.clicked.connect(self._preview_files)
        self.cancel_discovery_button = QPushButton("Cancel")
        self.cancel_discovery_button.setEnabled(False)
        self.cancel_discovery_button.clicked.connect(self._cancel_discovery)
        self.discovery_summary = QLabel("Files have not been discovered yet.")
        self.discovery_summary.setObjectName("CampaignHelpText")
        discovery_row.addWidget(self.preview_button)
        discovery_row.addWidget(self.cancel_discovery_button)
        discovery_row.addWidget(self.discovery_summary, 1)
        layout.addLayout(discovery_row)
        self.discovery_progress = QProgressBar()
        self.discovery_progress.hide()
        layout.addWidget(self.discovery_progress)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        files_box = QGroupBox("Discovered files")
        files_layout = QVBoxLayout(files_box)
        self.file_preview = QListWidget()
        self.file_preview.setAlternatingRowColors(True)
        self.file_preview.setMinimumWidth(250)
        self.file_preview.setToolTip("Each discovered file becomes one independent campaign run.")
        files_layout.addWidget(self.file_preview)

        configuration_tabs = QTabWidget()
        mapping_page = QWidget()
        mapping_layout = QVBoxLayout(mapping_page)
        mapping_help = QLabel("Map each Import Data block to the current run file, a fixed file, or a metadata field.")
        mapping_help.setWordWrap(True)
        mapping_help.setObjectName("CampaignHelpText")
        mapping_layout.addWidget(mapping_help)
        self.mapping_table = QTableWidget(0, 3)
        self.mapping_table.setHorizontalHeaderLabels(["Import block ID", "Source", "Fixed path / metadata field"])
        self._configure_table(self.mapping_table)
        self.mapping_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.mapping_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.mapping_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        mapping_layout.addWidget(self.mapping_table, 1)
        configuration_tabs.addTab(mapping_page, "Input mapping")

        metadata_page = QWidget()
        metadata_layout = QVBoxLayout(metadata_page)
        metadata_help = QLabel("Extract run metadata safely from file names, folders, sidecar JSON, file content or manual values.")
        metadata_help.setWordWrap(True)
        metadata_help.setObjectName("CampaignHelpText")
        metadata_layout.addWidget(metadata_help)
        self.metadata_table = QTableWidget(0, 7)
        self.metadata_table.setHorizontalHeaderLabels(["Field", "Source", "Pattern", "Group", "Key / value", "Required", "Default"])
        self._configure_table(self.metadata_table, stretch_last=False)
        self.metadata_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.metadata_table.setColumnWidth(0, 130)
        self.metadata_table.setColumnWidth(1, 135)
        self.metadata_table.setColumnWidth(2, 180)
        metadata_layout.addWidget(self.metadata_table, 1)
        metadata_buttons = QHBoxLayout()
        add_rule = QPushButton("Add metadata rule")
        remove_rule = QPushButton("Remove selected")
        add_rule.clicked.connect(self._add_metadata_rule)
        remove_rule.clicked.connect(lambda: self.metadata_table.removeRow(self.metadata_table.currentRow()) if self.metadata_table.currentRow() >= 0 else None)
        metadata_buttons.addWidget(add_rule)
        metadata_buttons.addWidget(remove_rule)
        metadata_buttons.addStretch()
        metadata_layout.addLayout(metadata_buttons)
        configuration_tabs.addTab(metadata_page, "Metadata extraction")

        splitter.addWidget(files_box)
        splitter.addWidget(configuration_tabs)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([300, 650])
        layout.addWidget(splitter, 1)
        self._add_step(page, "Input files", self._STEP_HELP[1])

    def _create_metrics_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        intro = QLabel("Choose the named scalar or compact results retained for every run. Publish Metric blocks are detected automatically; suitable existing block outputs can also be mapped by node ID and port.")
        intro.setWordWrap(True)
        intro.setObjectName("CampaignPageIntro")
        layout.addWidget(intro)
        buttons = QHBoxLayout()
        add = QPushButton("Add metric")
        remove = QPushButton("Remove selected")
        detect = QPushButton("Detect Publish Metric blocks")
        add.clicked.connect(self._add_metric)
        remove.clicked.connect(lambda: self.metric_table.removeRow(self.metric_table.currentRow()) if self.metric_table.currentRow() >= 0 else None)
        detect.clicked.connect(self._detect_metrics)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addWidget(detect)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.metric_table = QTableWidget(0, 10)
        self.metric_table.setHorizontalHeaderLabels(["Enabled", "Name", "Display label", "Source node", "Port", "Aggregation", "Unit", "Format", "Expression", "Description"])
        self._configure_table(self.metric_table)
        header = self.metric_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(9, QHeaderView.ResizeMode.Stretch)
        for column, width in {1: 130, 2: 150, 3: 180, 6: 80, 7: 80, 8: 180}.items():
            self.metric_table.setColumnWidth(column, width)
        layout.addWidget(self.metric_table, 1)
        self._add_step(page, "Metrics", self._STEP_HELP[2])

    def _create_requirements_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        intro = QLabel("Convert published metrics into auditable pass, warning and failure decisions. Missing or invalid measurements are never treated as a pass.")
        intro.setWordWrap(True)
        intro.setObjectName("CampaignPageIntro")
        layout.addWidget(intro)
        buttons = QHBoxLayout()
        add = QPushButton("Add requirement")
        remove = QPushButton("Remove selected")
        add.clicked.connect(self._add_requirement)
        remove.clicked.connect(lambda: self.requirement_table.removeRow(self.requirement_table.currentRow()) if self.requirement_table.currentRow() >= 0 else None)
        buttons.addWidget(add)
        buttons.addWidget(remove)
        buttons.addStretch()
        layout.addLayout(buttons)
        self.requirement_table = QTableWidget(0, 15)
        self.requirement_table.setHorizontalHeaderLabels(["Enabled", "Name", "Metric", "Condition", "Severity", "Unit", "Lower", "Upper", "Target", "Tolerance", "Warning lower", "Warning upper", "Expected boolean", "Description", "Result message"])
        self._configure_table(self.requirement_table)
        header = self.requirement_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(14, QHeaderView.ResizeMode.Stretch)
        for column, width in {1: 150, 2: 130, 5: 70, 6: 80, 7: 80, 8: 80, 9: 90, 10: 105, 11: 105, 12: 115, 13: 190}.items():
            self.requirement_table.setColumnWidth(column, width)
        layout.addWidget(self.requirement_table, 1)
        self._add_step(page, "Requirements", self._STEP_HELP[3])

    def _create_report_tab(self) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        intro = QLabel("Configure how campaign runs are executed and which information appears in the consolidated report.")
        intro.setWordWrap(True)
        intro.setObjectName("CampaignPageIntro")
        layout.addWidget(intro)
        self.execution_report_tabs = QTabWidget()
        layout.addWidget(self.execution_report_tabs, 1)

        execution_page = QWidget()
        execution_layout = QVBoxLayout(execution_page)
        execution_layout.setContentsMargins(12, 12, 12, 12)
        execution_box = QGroupBox("Execution")
        execution_form = QFormLayout(execution_box)
        execution_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.reference_edit = QLineEdit()
        self.reference_edit.setPlaceholderText("Optional; can also be set later from the dashboard")
        self.execution_mode = QComboBox()
        self.execution_mode.addItems(["sequential", "parallel"])
        self.execution_mode.currentTextChanged.connect(self._on_execution_mode_changed)
        self.max_workers = QSpinBox()
        self.max_workers.setRange(1, 8)
        self.max_workers.setValue(2)
        self.max_workers.setToolTip("Bounded worker count used only in parallel mode.")
        self.reuse_check = QCheckBox("Reuse unchanged completed runs")
        self.reuse_check.setChecked(True)
        self.reuse_check.setToolTip("Completed runs are recalculated only if the input, workflow or campaign settings changed.")
        self.stop_on_error_check = QCheckBox("Stop scheduling new sequential runs after an execution error")
        self.detail_limit = QSpinBox()
        self.detail_limit.setRange(0, 10000)
        self.detail_limit.setValue(50)
        self.detail_limit.setToolTip("Maximum number of runs for which compact signal details are stored in the project.")
        self.max_signal_points = QSpinBox()
        self.max_signal_points.setRange(100, 1_000_000)
        self.max_signal_points.setValue(20_000)
        execution_form.addRow("Reference run ID", self.reference_edit)
        execution_form.addRow("Execution mode", self.execution_mode)
        execution_form.addRow("Maximum workers", self.max_workers)
        execution_form.addRow("Stored detail runs", self.detail_limit)
        execution_form.addRow("Points per retained signal", self.max_signal_points)
        execution_form.addRow(self.reuse_check)
        execution_form.addRow(self.stop_on_error_check)
        execution_layout.addWidget(execution_box)
        execution_note = QLabel("Sequential mode is the safest option for memory-heavy workflows and third-party plugins. Parallel mode isolates every run but may use substantially more memory.")
        execution_note.setWordWrap(True)
        execution_note.setObjectName("CampaignHelpText")
        execution_layout.addWidget(execution_note)
        execution_layout.addStretch()
        self.execution_report_tabs.addTab(execution_page, "Execution")

        report_page = QWidget()
        report_layout = QVBoxLayout(report_page)
        report_layout.setContentsMargins(12, 12, 12, 12)
        report_form = QFormLayout()
        report_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Folder for PDF, Excel and CSV campaign reports")
        self.output_edit.setClearButtonEnabled(True)
        output_button = QPushButton("Browse…")
        output_button.clicked.connect(self._browse_output)
        output_row = QWidget()
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.addWidget(self.output_edit, 1)
        output_layout.addWidget(output_button)
        self.template_edit = QLineEdit("Engineering Campaign")
        self.company_edit = QLineEdit()
        self.operator_edit = QLineEdit()
        self.equipment_edit = QLineEdit()
        self.logo_edit = QLineEdit()
        self.logo_edit.setClearButtonEnabled(True)
        logo_button = QPushButton("Browse…")
        logo_button.clicked.connect(self._browse_logo)
        logo_row = QWidget()
        logo_layout = QHBoxLayout(logo_row)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.addWidget(self.logo_edit, 1)
        logo_layout.addWidget(logo_button)
        self.test_description_edit = QPlainTextEdit()
        self.test_description_edit.setPlaceholderText("Optional description shown in the campaign report")
        self.test_description_edit.setMinimumHeight(70)
        self.test_description_edit.setMaximumHeight(100)
        report_form.addRow("Output directory", output_row)
        report_form.addRow("Report template", self.template_edit)
        report_form.addRow("Company", self.company_edit)
        report_form.addRow("Company logo", logo_row)
        report_form.addRow("Operator", self.operator_edit)
        report_form.addRow("Equipment / rig", self.equipment_edit)
        report_form.addRow("Test description", self.test_description_edit)
        report_layout.addLayout(report_form)
        report_box = QGroupBox("Included report sections")
        sections_layout = QGridLayout(report_box)
        self.report_sections: dict[str, QCheckBox] = {}
        labels = {
            "title": "Title page", "campaign": "Campaign information", "workflow": "Workflow diagram",
            "workflow_parameters": "Workflow parameters", "inputs": "Input-file summary", "summary": "Pass/fail summary",
            "requirements": "Requirement summary", "metric_statistics": "Metric statistics", "comparison_plots": "Comparison plots",
            "failed_runs": "Failed-run details", "errors": "Warnings and errors", "runs": "Full run table",
            "provenance": "Provenance and checksums", "signoff": "Sign-off page",
        }
        for index, (key, label) in enumerate(labels.items()):
            check = QCheckBox(label)
            check.setChecked(True)
            self.report_sections[key] = check
            sections_layout.addWidget(check, index // 2, index % 2)
        report_layout.addWidget(report_box)
        report_layout.addStretch()
        self.execution_report_tabs.addTab(report_page, "Report")

        metadata_page = QWidget()
        metadata_layout = QVBoxLayout(metadata_page)
        metadata_layout.setContentsMargins(12, 12, 12, 12)
        metadata_help = QLabel("Add campaign-level information such as operator, product, test rig, firmware version or test condition. These values are retained in reports and provenance records.")
        metadata_help.setWordWrap(True)
        metadata_help.setObjectName("CampaignHelpText")
        metadata_layout.addWidget(metadata_help)
        self.campaign_metadata_table = QTableWidget(0, 2)
        self.campaign_metadata_table.setHorizontalHeaderLabels(["Field", "Value"])
        self._configure_table(self.campaign_metadata_table)
        self.campaign_metadata_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        metadata_layout.addWidget(self.campaign_metadata_table, 1)
        metadata_buttons = QHBoxLayout()
        add_metadata = QPushButton("Add field")
        remove_metadata = QPushButton("Remove selected")
        add_metadata.clicked.connect(lambda: self.campaign_metadata_table.insertRow(self.campaign_metadata_table.rowCount()))
        remove_metadata.clicked.connect(lambda: self.campaign_metadata_table.removeRow(self.campaign_metadata_table.currentRow()) if self.campaign_metadata_table.currentRow() >= 0 else None)
        metadata_buttons.addWidget(add_metadata)
        metadata_buttons.addWidget(remove_metadata)
        metadata_buttons.addStretch()
        metadata_layout.addLayout(metadata_buttons)
        self.execution_report_tabs.addTab(metadata_page, "Campaign information")

        self._add_step(page, "Run & report", self._STEP_HELP[4])

    def _on_execution_mode_changed(self, mode: str) -> None:
        parallel = mode == "parallel"
        self.max_workers.setEnabled(parallel)
        self.max_workers.setToolTip("Maximum parallel campaign workers." if parallel else "Sequential mode always uses one worker.")


    @staticmethod
    def _set_item(table: QTableWidget, row: int, column: int, value: Any) -> None:
        table.setItem(row, column, QTableWidgetItem("" if value is None else str(value)))

    @staticmethod
    def _check_item(checked: bool) -> QTableWidgetItem:
        item = QTableWidgetItem(); item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable); item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked); return item

    def _workflow_document(self) -> dict[str, Any]:
        if self.workflow_choice.currentIndex() == 1:
            return self._external_document or {}
        return self._current_workflow

    def _refresh_mapping_rows(self) -> None:
        existing = {self.mapping_table.item(row, 0).text(): row for row in range(self.mapping_table.rowCount()) if self.mapping_table.item(row, 0)}
        for block_id in import_block_ids(self._workflow_document()):
            if block_id in existing: continue
            row = self.mapping_table.rowCount(); self.mapping_table.insertRow(row); self._set_item(self.mapping_table, row, 0, block_id)
            combo = QComboBox()
            for value, label in _MAPPING_SOURCE_LABELS.items(): combo.addItem(label, value)
            self.mapping_table.setCellWidget(row, 1, combo); self._set_item(self.mapping_table, row, 2, "")

    def _load_campaign(self) -> None:
        campaign = self._campaign
        self.name_edit.setText(campaign.name); self.description_edit.setPlainText(campaign.description); self.workflow_path.setText(campaign.workflow_path)
        self.workflow_choice.setCurrentIndex(1 if campaign.workflow_path else 0)
        if campaign.workflow_path:
            self._external_document = deepcopy(campaign.workflow_document) if campaign.workflow_document else None
            try:
                from app.project.io import load_project
                path = Path(campaign.workflow_path).expanduser()
                if path.exists():
                    self._external_document = load_project(path)
            except (OSError, ValueError):
                # Keep the last embedded snapshot for setup/report inspection.
                # Execution will still report the inaccessible authoritative path.
                pass
        self.folder_edit.setText(campaign.input_folder); self.files_edit.setText(";".join(campaign.explicit_files)); self.extensions_edit.setText(",".join(campaign.file_extensions)); self.recursive_check.setChecked(campaign.recursive)
        self._refresh_mapping_rows()
        by_block = {mapping.block_id: mapping for mapping in campaign.input_mappings}
        for row in range(self.mapping_table.rowCount()):
            block_id = self.mapping_table.item(row, 0).text(); mapping = by_block.get(block_id)
            if mapping:
                combo = self.mapping_table.cellWidget(row, 1); index = combo.findData(mapping.source); combo.setCurrentIndex(index if index >= 0 else 0)
                self._set_item(self.mapping_table, row, 2, mapping.fixed_path or mapping.metadata_field)
        for rule in campaign.metadata_rules: self._add_metadata_rule(rule)
        for metric in campaign.metrics: self._add_metric(metric)
        if not campaign.metrics: self._detect_metrics()
        for requirement in campaign.requirements: self._add_requirement(requirement)
        self.reference_edit.setText(campaign.reference_run_id); self.output_edit.setText(campaign.report.output_directory); self.template_edit.setText(campaign.report.template); self.company_edit.setText(campaign.report.company_name); self.logo_edit.setText(campaign.report.company_logo); self.operator_edit.setText(campaign.report.operator); self.equipment_edit.setText(campaign.report.equipment); self.test_description_edit.setPlainText(campaign.report.test_description)
        self.execution_mode.setCurrentText(campaign.execution.mode); self.max_workers.setValue(campaign.execution.max_workers); self.reuse_check.setChecked(campaign.execution.reuse_completed); self.stop_on_error_check.setChecked(campaign.execution.stop_on_error); self.detail_limit.setValue(campaign.execution.detailed_result_limit); self.max_signal_points.setValue(campaign.execution.maximum_signal_points)
        for key, check in self.report_sections.items(): check.setChecked(key in campaign.report.include_sections)
        for key, value in sorted(campaign.campaign_metadata.items()):
            row = self.campaign_metadata_table.rowCount(); self.campaign_metadata_table.insertRow(row); self._set_item(self.campaign_metadata_table, row, 0, key); self._set_item(self.campaign_metadata_table, row, 1, value)

    def _browse_workflow(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Campaign Workflow", self.workflow_path.text(), "SignalDojo (*.sdojo)")
        if not path: return
        try:
            from app.project.io import load_project
            self._external_document = load_project(path)
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Campaign Workflow", str(exc)); return
        self.workflow_path.setText(path); self.workflow_choice.setCurrentIndex(1); self.mapping_table.setRowCount(0); self._refresh_mapping_rows(); self._detect_metrics(clear=True)

    def _browse_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Campaign Input Folder", self.folder_edit.text())
        if path: self.folder_edit.setText(path)

    def _browse_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Select Campaign Input Files", "", "Supported data (*.csv *.tsv *.txt *.xlsx *.xls *.json *.npy *.npz *.h5 *.hdf *.hdf5 *.tdms);;All files (*)")
        if paths: self.files_edit.setText(";".join(paths))

    def _browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Campaign Output Directory", self.output_edit.text())
        if path: self.output_edit.setText(path)

    def _browse_logo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select Company Logo", self.logo_edit.text(), "Images (*.png *.jpg *.jpeg *.bmp);;All files (*)")
        if path: self.logo_edit.setText(path)

    def _preview_files(self) -> None:
        if self._discovery_thread: return
        self._clear_validation()
        try:
            campaign = self._read_campaign(include_tables=False)
        except (TypeError, ValueError) as exc:
            self._show_validation(f"Check the input settings: {exc}", step=1)
            return
        self.file_preview.clear(); self.discovery_summary.setText("Discovering files…"); self.discovery_progress.show(); self.discovery_progress.setRange(0, 0); self.preview_button.setEnabled(False); self.cancel_discovery_button.setEnabled(True)
        thread = QThread(self); worker = DiscoveryWorker(campaign); worker.moveToThread(thread); thread.started.connect(worker.run)
        worker.progress.connect(self._on_discovery_progress)
        worker.completed.connect(self._on_discovered); worker.failed.connect(self._on_discovery_failed); worker.completed.connect(thread.quit); worker.failed.connect(thread.quit)
        thread.finished.connect(self._cleanup_discovery); self._discovery_thread = thread; self._discovery_worker = worker; thread.start()

    def _cancel_discovery(self) -> None:
        if self._discovery_worker is not None:
            self._discovery_worker.cancel(); self.discovery_summary.setText("Cancelling file discovery…")

    @Slot(str, int, int)
    def _on_discovery_progress(self, path: str, index: int, total: int) -> None:
        self.discovery_progress.setRange(0, max(1, total)); self.discovery_progress.setValue(index)
        self.discovery_progress.setFormat(f"Checking {Path(path).name} — %v/%m")

    @Slot(object)
    def _on_discovered(self, paths: object) -> None:
        discovered = list(paths)
        for path in discovered: self.file_preview.addItem(str(path))
        count = len(discovered)
        self.discovery_summary.setText(f"{count} file{'s' if count != 1 else ''} discovered — each file will become one campaign run.")
        self.discovery_progress.setRange(0, max(1, count)); self.discovery_progress.setValue(count)

    @Slot(str)
    def _on_discovery_failed(self, message: str) -> None:
        self.discovery_summary.setText("File discovery failed.")
        self._show_validation(message, step=1)

    @Slot()
    def _cleanup_discovery(self) -> None:
        if self._discovery_worker: self._discovery_worker.deleteLater()
        if self._discovery_thread: self._discovery_thread.deleteLater()
        self._discovery_worker = None; self._discovery_thread = None; self.preview_button.setEnabled(True); self.cancel_discovery_button.setEnabled(False); self.discovery_progress.hide()
        if self._reject_after_discovery:
            self._reject_after_discovery = False
            super().reject()

    def reject(self) -> None:
        if self._discovery_thread is not None:
            self._reject_after_discovery = True
            self._cancel_discovery()
            self.discovery_summary.setText("Cancelling file discovery before closing…")
            return
        super().reject()

    def _add_metadata_rule(self, rule: MetadataRule | None = None) -> None:
        rule = rule or MetadataRule("test_id")
        row = self.metadata_table.rowCount(); self.metadata_table.insertRow(row); self._set_item(self.metadata_table, row, 0, rule.field_name)
        source = QComboBox()
        for value, label in _METADATA_SOURCE_LABELS.items(): source.addItem(label, value)
        index = source.findData(rule.source); source.setCurrentIndex(index if index >= 0 else 0); self.metadata_table.setCellWidget(row, 1, source)
        self._set_item(self.metadata_table, row, 2, rule.pattern); self._set_item(self.metadata_table, row, 3, rule.group); self._set_item(self.metadata_table, row, 4, rule.key or rule.value)
        self.metadata_table.setItem(row, 5, self._check_item(rule.required)); self._set_item(self.metadata_table, row, 6, rule.default)

    def _add_metric(self, metric: MetricDefinition | None = None) -> None:
        metric = metric or MetricDefinition(name="metric")
        row = self.metric_table.rowCount(); self.metric_table.insertRow(row); self.metric_table.setItem(row, 0, self._check_item(metric.enabled))
        for column, value in enumerate([metric.name, metric.label, metric.source_node_id, metric.source_port], 1): self._set_item(self.metric_table, row, column, value)
        aggregation = QComboBox()
        for value in SCALAR_AGGREGATIONS: aggregation.addItem(_AGGREGATION_LABELS.get(value, value.replace("_", " ").title()), value)
        index = aggregation.findData(metric.aggregation); aggregation.setCurrentIndex(index if index >= 0 else 0); self.metric_table.setCellWidget(row, 5, aggregation)
        for column, value in enumerate([metric.unit, metric.number_format, metric.expression, metric.description], 6): self._set_item(self.metric_table, row, column, value)

    def _detect_metrics(self, *, clear: bool = False) -> None:
        if clear: self.metric_table.setRowCount(0)
        existing = {self.metric_table.item(row, 1).text() for row in range(self.metric_table.rowCount()) if self.metric_table.item(row, 1)}
        for raw in published_metric_nodes(self._workflow_document()):
            params = dict(raw.get("parameters", {})); name = str(params.get("metric_name", "metric"))
            if name in existing: continue
            self._add_metric(MetricDefinition(name=name, label=str(params.get("display_label", "")), source_node_id=str(raw.get("id", "")), aggregation="value", unit=str(params.get("unit", "")), number_format=str(params.get("number_format", ".6g"))))
            existing.add(name)

    def _add_requirement(self, requirement: RequirementDefinition | None = None) -> None:
        requirement = requirement or RequirementDefinition(name="Upper limit", metric="metric")
        row = self.requirement_table.rowCount(); self.requirement_table.insertRow(row); self.requirement_table.setItem(row, 0, self._check_item(requirement.enabled))
        self._set_item(self.requirement_table, row, 1, requirement.name); self._set_item(self.requirement_table, row, 2, requirement.metric)
        condition = QComboBox()
        for item in RequirementType: condition.addItem(_REQUIREMENT_LABELS.get(item, item.value.replace("_", " ").title()), item.value)
        index = condition.findData(requirement.condition.value); condition.setCurrentIndex(index if index >= 0 else 0); self.requirement_table.setCellWidget(row, 3, condition)
        severity = QComboBox(); severity.addItems([item.value for item in Severity]); severity.setCurrentText(requirement.severity.value); self.requirement_table.setCellWidget(row, 4, severity)
        for column, value in enumerate([requirement.unit, requirement.lower, requirement.upper, requirement.target, requirement.tolerance, requirement.warning_lower, requirement.warning_upper], 5): self._set_item(self.requirement_table, row, column, value)
        expected = QComboBox(); expected.addItems(["true", "false"]); expected.setCurrentText("true" if requirement.expected_boolean else "false"); self.requirement_table.setCellWidget(row, 12, expected)
        self._set_item(self.requirement_table, row, 13, requirement.description); self._set_item(self.requirement_table, row, 14, requirement.result_message)

    @staticmethod
    def _text(table: QTableWidget, row: int, column: int) -> str:
        widget = table.cellWidget(row, column)
        if isinstance(widget, QComboBox):
            data = widget.currentData()
            return str(data).strip() if data is not None else widget.currentText().strip()
        item = table.item(row, column); return item.text().strip() if item else ""

    @staticmethod
    def _float(text: str) -> float | None:
        return None if not text.strip() else float(text)

    def _read_campaign(self, *, include_tables: bool = True) -> TestCampaign:
        campaign = deepcopy(self._campaign); campaign.name = self.name_edit.text().strip(); campaign.description = self.description_edit.toPlainText().strip()
        external = self.workflow_choice.currentIndex() == 1
        campaign.workflow_path = self.workflow_path.text().strip() if external else ""
        campaign.workflow_document = workflow_snapshot(self._workflow_document()) if self._workflow_document() else {}
        campaign.input_folder = self.folder_edit.text().strip(); campaign.explicit_files = [value.strip() for value in self.files_edit.text().split(";") if value.strip()]
        campaign.file_extensions = [value.strip() for value in self.extensions_edit.text().replace(";", ",").split(",") if value.strip()]; campaign.recursive = self.recursive_check.isChecked()
        if include_tables:
            campaign.input_mappings = []
            for row in range(self.mapping_table.rowCount()):
                block_id = self._text(self.mapping_table, row, 0); combo = self.mapping_table.cellWidget(row, 1); source = str(combo.currentData() or combo.currentText()) if combo else "run_file"; detail = self._text(self.mapping_table, row, 2)
                campaign.input_mappings.append(InputMapping(block_id, source, detail if source == "fixed_file" else "", detail if source == "metadata_field" else ""))
            campaign.metadata_rules = []
            for row in range(self.metadata_table.rowCount()):
                field, source, pattern, group, key_value, _required, default = [self._text(self.metadata_table, row, col) for col in range(7)]
                required_item = self.metadata_table.item(row, 5); required = bool(required_item and required_item.checkState() == Qt.CheckState.Checked)
                campaign.metadata_rules.append(MetadataRule(field, source or "filename_regex", pattern, group or "1", key_value if source in {"sidecar_json", "file_column", "file_property"} else "", key_value if source == "manual" else "", required, default))
            campaign.metrics = []
            for row in range(self.metric_table.rowCount()):
                enabled = self.metric_table.item(row, 0).checkState() == Qt.CheckState.Checked
                campaign.metrics.append(MetricDefinition(name=self._text(self.metric_table, row, 1), label=self._text(self.metric_table, row, 2), source_node_id=self._text(self.metric_table, row, 3), source_port=int(self._text(self.metric_table, row, 4) or 0), aggregation=self._text(self.metric_table, row, 5) or "auto", unit=self._text(self.metric_table, row, 6), number_format=self._text(self.metric_table, row, 7) or ".6g", expression=self._text(self.metric_table, row, 8), description=self._text(self.metric_table, row, 9), enabled=enabled))
            campaign.requirements = []
            for row in range(self.requirement_table.rowCount()):
                enabled = self.requirement_table.item(row, 0).checkState() == Qt.CheckState.Checked
                campaign.requirements.append(RequirementDefinition(name=self._text(self.requirement_table, row, 1), metric=self._text(self.requirement_table, row, 2), condition=RequirementType(self._text(self.requirement_table, row, 3) or RequirementType.UPPER_LIMIT.value), severity=Severity(self._text(self.requirement_table, row, 4) or Severity.FAILURE.value), unit=self._text(self.requirement_table, row, 5), lower=self._float(self._text(self.requirement_table, row, 6)), upper=self._float(self._text(self.requirement_table, row, 7)), target=self._float(self._text(self.requirement_table, row, 8)), tolerance=self._float(self._text(self.requirement_table, row, 9)), warning_lower=self._float(self._text(self.requirement_table, row, 10)), warning_upper=self._float(self._text(self.requirement_table, row, 11)), expected_boolean=self._text(self.requirement_table, row, 12).casefold() != "false", description=self._text(self.requirement_table, row, 13), result_message=self._text(self.requirement_table, row, 14), enabled=enabled))
        campaign.reference_run_id = self.reference_edit.text().strip(); campaign.execution = CampaignExecutionSettings(mode=self.execution_mode.currentText(), max_workers=self.max_workers.value(), reuse_completed=self.reuse_check.isChecked(), stop_on_error=self.stop_on_error_check.isChecked(), detailed_result_limit=self.detail_limit.value(), maximum_signal_points=self.max_signal_points.value())
        sections = [key for key, check in self.report_sections.items() if check.isChecked()]
        campaign.report = CampaignReportSettings(output_directory=self.output_edit.text().strip(), template=self.template_edit.text().strip() or "Engineering Campaign", company_name=self.company_edit.text().strip(), company_logo=self.logo_edit.text().strip(), operator=self.operator_edit.text().strip(), equipment=self.equipment_edit.text().strip(), test_description=self.test_description_edit.toPlainText().strip(), include_sections=sections)
        campaign.campaign_metadata = {}
        for row in range(self.campaign_metadata_table.rowCount()):
            key = self._text(self.campaign_metadata_table, row, 0); value = self._text(self.campaign_metadata_table, row, 1)
            if key: campaign.campaign_metadata[key] = value
        campaign.touch(); return campaign

    @staticmethod
    def _validation_step(errors: list[str]) -> int:
        rendered = " ".join(errors).casefold()
        if any(term in rendered for term in ("campaign name", "workflow")):
            return 0
        if any(term in rendered for term in ("input", "folder", "file", "mapping", "metadata", "import data")):
            return 1
        if "metric" in rendered:
            return 2
        if any(term in rendered for term in ("requirement", "limit", "tolerance", "severity")):
            return 3
        return 4

    def _accept(self) -> None:
        if self._discovery_thread is not None:
            self._show_validation("Wait for file discovery to finish, or cancel discovery before saving the campaign.", step=1)
            return
        try: campaign = self._read_campaign()
        except (TypeError, ValueError) as exc:
            self._show_validation(f"Invalid campaign value: {exc}", step=self.step_list.currentRow()); return
        errors = campaign.validate()
        if self.workflow_choice.currentIndex() == 1:
            workflow_path = Path(campaign.workflow_path).expanduser() if campaign.workflow_path else None
            if workflow_path is None:
                errors.append("Select an external .sdojo workflow file.")
            elif not workflow_path.exists():
                errors.append(f"External workflow does not exist: {workflow_path}")
            elif not workflow_path.is_file():
                errors.append(f"External workflow path is not a file: {workflow_path}")
            elif not campaign.workflow_document:
                errors.append("The external workflow could not be read. Select it again and correct any project validation errors.")
        if errors:
            self._show_validation(errors, step=self._validation_step(errors)); return
        self._clear_validation(); self._campaign = campaign; self.accept()

    def value(self) -> TestCampaign:
        return deepcopy(self._campaign)


class CampaignTableModel(QAbstractTableModel):
    """Scalable model/view representation of up to thousands of campaign runs."""

    def __init__(self, campaign: TestCampaign | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent); self.campaign = campaign; self.columns: list[tuple[str, str]] = []; self.refresh_columns()

    def set_campaign(self, campaign: TestCampaign | None) -> None:
        self.beginResetModel(); self.campaign = campaign; self.refresh_columns(); self.endResetModel()

    def refresh_columns(self) -> None:
        base = [("status", "Status"), ("file_name", "File"), ("processing_seconds", "Time (s)")]
        if not self.campaign: self.columns = base; return
        metadata = sorted({key for run in self.campaign.runs for key in run.user_metadata})
        metrics = sorted({key for run in self.campaign.runs for key in run.metrics} | {metric.name for metric in self.campaign.metrics if metric.enabled})
        requirements = sorted({result.requirement_name for run in self.campaign.runs for result in run.requirement_results} | {requirement.name for requirement in self.campaign.requirements if requirement.enabled})
        self.columns = base + [(f"metadata:{name}", name) for name in metadata] + [(f"metric:{name}", name) for name in metrics] + [(f"requirement:{name}", name) for name in requirements]

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int: return 0 if parent.isValid() or not self.campaign else len(self.campaign.runs)
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int: return 0 if parent.isValid() else len(self.columns)

    def _value(self, row: int, key: str) -> Any:
        run = self.campaign.runs[row]
        if key == "status": return run.status
        if key == "file_name": return run.file_name
        if key == "processing_seconds": return run.processing_seconds
        prefix, _, name = key.partition(":")
        if prefix == "metadata": return run.user_metadata.get(name, "")
        if prefix == "metric": return run.metrics.get(name, "")
        if prefix == "requirement":
            result = next((item for item in run.requirement_results if item.requirement_name == name), None)
            return result.status if result else RequirementStatus.NOT_EVALUATED
        return ""

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not self.campaign: return None
        value = self._value(index.row(), self.columns[index.column()][0])
        if role == Qt.ItemDataRole.DisplayRole:
            if isinstance(value, (RunStatus, RequirementStatus)): return value.value
            key = self.columns[index.column()][0]
            if key.startswith("metric:") and isinstance(value, (int, float, np.number)) and not isinstance(value, bool):
                metric_name = key.split(":", 1)[1]
                definition = next((item for item in self.campaign.metrics if item.name == metric_name), None)
                try:
                    return format(value, definition.number_format if definition else ".6g")
                except (TypeError, ValueError):
                    return f"{value:.6g}"
            if isinstance(value, float): return f"{value:.6g}"
            return str(value)
        if role == Qt.ItemDataRole.UserRole:
            return value.value if isinstance(value, (RunStatus, RequirementStatus)) else value
        if role == Qt.ItemDataRole.BackgroundRole:
            if isinstance(value, RunStatus): return _STATUS_COLOURS.get(value)
            if isinstance(value, RequirementStatus):
                mapping = {RequirementStatus.PASS: RunStatus.PASSED, RequirementStatus.FAIL: RunStatus.FAILED, RequirementStatus.WARNING: RunStatus.WARNING, RequirementStatus.ERROR: RunStatus.ERROR}
                return _STATUS_COLOURS.get(mapping.get(value))
        if role == Qt.ItemDataRole.ForegroundRole:
            if isinstance(value, (RunStatus, RequirementStatus)):
                return QColor("#11161c")
        if role == Qt.ItemDataRole.ToolTipRole and self.columns[index.column()][0].startswith("requirement:"):
            name = self.columns[index.column()][0].split(":", 1)[1]; run = self.campaign.runs[index.row()]; result = next((item for item in run.requirement_results if item.requirement_name == name), None); return result.explanation if result else "Not evaluated"
        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if role != Qt.ItemDataRole.DisplayRole: return None
        return self.columns[section][1] if orientation == Qt.Orientation.Horizontal else section + 1

    def run_id(self, row: int) -> str:
        return self.campaign.runs[row].run_id if self.campaign and 0 <= row < len(self.campaign.runs) else ""


class CampaignFilterProxyModel(QSortFilterProxyModel):
    """Search, status and metadata filtering for large campaign run models."""

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.search_text = ""
        self.status_filter = "All"
        self.metadata_field = "All metadata"
        self.metadata_value = ""
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortRole(Qt.ItemDataRole.UserRole)
        self.setDynamicSortFilter(True)

    def set_search(self, text: str) -> None:
        self.search_text = text.casefold().strip(); self.invalidateFilter()

    def set_status(self, status: str) -> None:
        self.status_filter = status; self.invalidateFilter()

    def set_metadata_field(self, field: str) -> None:
        self.metadata_field = field; self.invalidateFilter()

    def set_metadata_value(self, value: str) -> None:
        self.metadata_value = value.casefold().strip(); self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        model = self.sourceModel()
        if self.status_filter != "All":
            status = model.data(model.index(source_row, 0, source_parent), Qt.ItemDataRole.UserRole)
            if status != self.status_filter:
                return False
        campaign = getattr(model, "campaign", None)
        if self.metadata_value and campaign and 0 <= source_row < len(campaign.runs):
            metadata = campaign.runs[source_row].user_metadata
            if self.metadata_field == "All metadata":
                rendered = " ".join(str(value) for value in metadata.values()).casefold()
            else:
                rendered = str(metadata.get(self.metadata_field, "")).casefold()
            if self.metadata_value not in rendered:
                return False
        if not self.search_text:
            return True
        return any(
            self.search_text in str(model.data(model.index(source_row, column, source_parent), Qt.ItemDataRole.DisplayRole)).casefold()
            for column in range(model.columnCount())
        )


class CampaignDashboardDock(QDockWidget):
    run_requested = Signal()
    cancel_requested = Signal()
    retry_requested = Signal()
    compare_requested = Signal(object)
    report_requested = Signal()
    reference_changed = Signal(str)
    run_open_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Test Campaign", parent)
        self.setObjectName("CampaignDashboardDock")
        self._hidden_column_keys = set(settings().value("campaign/hidden_columns", [], type=list))
        panel = QWidget(); layout = QVBoxLayout(panel)
        self.empty_label = QLabel("No test campaign is configured. Use Campaign → New Test Campaign.")
        self.empty_label.setWordWrap(True); layout.addWidget(self.empty_label)
        summary = QHBoxLayout(); self.summary_label = QLabel(); self.summary_label.setWordWrap(True)
        self.progress = QProgressBar(); self.progress.setMinimumWidth(180)
        summary.addWidget(self.summary_label, 1); summary.addWidget(self.progress); layout.addLayout(summary)

        filters = QHBoxLayout()
        self.search = QLineEdit(); self.search.setPlaceholderText("Search runs, metrics or metadata…")
        self.status = QComboBox(); self.status.addItem("All"); self.status.addItems([status.value for status in RunStatus])
        self.metadata_field = QComboBox(); self.metadata_field.addItem("All metadata")
        self.metadata_value = QLineEdit(); self.metadata_value.setPlaceholderText("Metadata contains…")
        self.columns_button = QToolButton(); self.columns_button.setText("Columns"); self.columns_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.columns_menu = QMenu(self.columns_button); self.columns_button.setMenu(self.columns_menu)
        filters.addWidget(self.search, 1); filters.addWidget(QLabel("Status")); filters.addWidget(self.status)
        filters.addWidget(self.metadata_field); filters.addWidget(self.metadata_value); filters.addWidget(self.columns_button)
        layout.addLayout(filters)

        self.model = CampaignTableModel()
        self.proxy = CampaignFilterProxyModel(); self.proxy.setSourceModel(self.model)
        self.table = QTableView(); self.table.setObjectName("CampaignRunTable"); self.table.setModel(self.proxy); self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setWordWrap(False)
        # ResizeToContents scans every record and becomes expensive for 1,000+
        # run campaigns.  Interactive sections keep model/view population lazy.
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setColumnWidth(0, 95); self.table.setColumnWidth(1, 240); self.table.setColumnWidth(2, 90)
        self.table.doubleClicked.connect(self._open_index); layout.addWidget(self.table, 1)

        buttons = QHBoxLayout()
        self.run_button = QPushButton("Run Campaign"); self.run_button.setToolTip("Execute or resume all pending and changed campaign runs.")
        self.cancel_button = QPushButton("Cancel"); self.cancel_button.setToolTip("Request cancellation of the running campaign.")
        self.retry_button = QPushButton("Retry Failed"); self.retry_button.setToolTip("Retry failed, error and cancelled runs without recalculating unchanged passed runs.")
        self.compare_button = QPushButton("Compare Selected"); self.reference_button = QPushButton("Set Reference")
        self.report_button = QPushButton("Generate Report")
        for button in (self.run_button, self.cancel_button, self.retry_button, self.compare_button, self.reference_button, self.report_button):
            buttons.addWidget(button)
        buttons.addStretch(); layout.addLayout(buttons); self.setWidget(panel)

        self.search.textChanged.connect(self.proxy.set_search)
        self.status.currentTextChanged.connect(self.proxy.set_status)
        self.metadata_field.currentTextChanged.connect(self.proxy.set_metadata_field)
        self.metadata_value.textChanged.connect(self.proxy.set_metadata_value)
        self.run_button.clicked.connect(self.run_requested); self.cancel_button.clicked.connect(self.cancel_requested)
        self.retry_button.clicked.connect(self.retry_requested)
        self.compare_button.clicked.connect(lambda: self.compare_requested.emit(self.selected_run_ids()))
        self.reference_button.clicked.connect(self._set_reference); self.report_button.clicked.connect(self.report_requested)
        self.set_campaign(None); self.set_running(False)

    def set_campaign(self, campaign: TestCampaign | None) -> None:
        self.model.set_campaign(campaign)
        self.empty_label.setVisible(campaign is None); self.table.setVisible(campaign is not None)
        self._rebuild_metadata_fields(); self._rebuild_columns_menu(); self._refresh_summary()

    def _rebuild_metadata_fields(self) -> None:
        current = self.metadata_field.currentText()
        keys = sorted({key for run in (self.model.campaign.runs if self.model.campaign else []) for key in run.user_metadata})
        self.metadata_field.blockSignals(True); self.metadata_field.clear(); self.metadata_field.addItem("All metadata"); self.metadata_field.addItems(keys)
        self.metadata_field.setCurrentText(current if current in {"All metadata", *keys} else "All metadata")
        self.metadata_field.blockSignals(False); self.proxy.set_metadata_field(self.metadata_field.currentText())

    def _rebuild_columns_menu(self) -> None:
        self.columns_menu.clear()
        for column, (key, label) in enumerate(self.model.columns):
            visible = key not in self._hidden_column_keys
            self.table.setColumnHidden(column, not visible)
            action = QAction(label, self.columns_menu); action.setCheckable(True); action.setChecked(visible)
            action.toggled.connect(lambda checked, index=column, column_key=key: self._set_column_visible(index, column_key, checked))
            self.columns_menu.addAction(action)

    def _set_column_visible(self, index: int, key: str, visible: bool) -> None:
        self.table.setColumnHidden(index, not visible)
        if visible:
            self._hidden_column_keys.discard(key)
        else:
            self._hidden_column_keys.add(key)
        settings().setValue("campaign/hidden_columns", sorted(self._hidden_column_keys))

    def _refresh_summary(self) -> None:
        campaign = self.model.campaign
        if not campaign:
            self.summary_label.setText("No campaign"); self.progress.setRange(0, 1); self.progress.setValue(0); return
        counts = {status: sum(run.status == status for run in campaign.runs) for status in RunStatus}
        complete = sum(run.status not in {RunStatus.PENDING, RunStatus.RUNNING} for run in campaign.runs); total = len(campaign.runs)
        reference = campaign.run_by_id(campaign.reference_run_id)
        reference_text = reference.file_name if reference else "none"
        self.summary_label.setText(
            f"{total} runs — {counts[RunStatus.PASSED]} passed, {counts[RunStatus.FAILED]} failed, "
            f"{counts[RunStatus.WARNING]} warning, {counts[RunStatus.ERROR]} error, "
            f"{counts[RunStatus.RUNNING]} running, {counts[RunStatus.PENDING]} pending, "
            f"{counts[RunStatus.CANCELLED]} cancelled, {counts[RunStatus.SKIPPED]} skipped — "
            f"{campaign.last_execution_seconds:.2f} s — reference: {reference_text}"
        )
        self.progress.setRange(0, max(1, total)); self.progress.setValue(complete)

    def refresh(self) -> None:
        self.model.beginResetModel(); self.model.refresh_columns(); self.model.endResetModel()
        self._rebuild_metadata_fields(); self._rebuild_columns_menu(); self._refresh_summary()

    def set_running(self, running: bool) -> None:
        self.run_button.setEnabled(not running); self.retry_button.setEnabled(not running)
        self.compare_button.setEnabled(not running); self.report_button.setEnabled(not running)
        self.reference_button.setEnabled(not running); self.cancel_button.setEnabled(running)

    def selected_run_ids(self) -> list[str]:
        selection = self.table.selectionModel()
        if selection is None:
            return []
        source_rows = sorted({self.proxy.mapToSource(index).row() for index in selection.selectedRows()})
        return [self.model.run_id(row) for row in source_rows if self.model.run_id(row)]

    def _set_reference(self) -> None:
        selected = self.selected_run_ids()
        if len(selected) != 1:
            QMessageBox.information(self, "Reference Run", "Select exactly one run first."); return
        self.reference_changed.emit(selected[0])

    def _open_index(self, index: QModelIndex) -> None:
        source = self.proxy.mapToSource(index); run_id = self.model.run_id(source.row())
        if run_id:
            self.run_open_requested.emit(run_id)


class CampaignComparisonDialog(QDialog):
    """Interactive multi-run comparison with explicit alignment and reference deltas."""

    def __init__(self, campaign: TestCampaign, run_ids: list[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Campaign Run Comparison"); self.resize(1120, 700); self.setMinimumSize(850, 560)
        self.campaign = campaign; self.run_ids = run_ids[:50]; self.result: ComparisonResult | None = None
        self._colours: dict[str, QColor] = {}
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.reference = QComboBox()
        for run_id in self.run_ids:
            run = campaign.run_by_id(run_id); self.reference.addItem(run.file_name if run else run_id, run_id)
        reference_index = self.reference.findData(campaign.reference_run_id)
        self.reference.setCurrentIndex(reference_index if reference_index >= 0 else 0)
        self.alignment = QComboBox(); self.alignment.addItems(["exact", "interpolate_to_reference", "overlap"])
        self.mode = QComboBox(); self.mode.addItems(["overlay", "difference", "percentage_difference"])
        self.signal_key = QLineEdit(); self.signal_key.setPlaceholderText("Signal key (blank chooses first common signal)")
        refresh = QPushButton("Compare"); refresh.clicked.connect(self.refresh)
        export_tables = QPushButton("Export tables…"); export_tables.clicked.connect(self.export)
        export_plot = QPushButton("Export plot…"); export_plot.clicked.connect(self.export_plot)
        controls.addWidget(QLabel("Reference")); controls.addWidget(self.reference)
        controls.addWidget(QLabel("Alignment")); controls.addWidget(self.alignment)
        controls.addWidget(QLabel("Display")); controls.addWidget(self.mode)
        controls.addWidget(self.signal_key, 1); controls.addWidget(refresh); controls.addWidget(export_tables); controls.addWidget(export_plot)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        trace_panel = QWidget(); trace_layout = QVBoxLayout(trace_panel); trace_layout.addWidget(QLabel("Visible runs (double-click to change colour)"))
        self.trace_list = QListWidget(); self.trace_list.itemChanged.connect(lambda _item: self._render_plot()); self.trace_list.itemDoubleClicked.connect(self._choose_colour)
        trace_layout.addWidget(self.trace_list, 1); splitter.addWidget(trace_panel)
        self.tabs = QTabWidget(); splitter.addWidget(self.tabs); splitter.setStretchFactor(1, 4); layout.addWidget(splitter, 1)

        self.metric_table = QTableWidget(); self.metric_table.setSortingEnabled(True); self.metric_table.setAlternatingRowColors(True)
        self.tabs.addTab(self.metric_table, "Metrics")
        self.plot_container = QWidget(); plot_layout = QVBoxLayout(self.plot_container)
        self.cursor_label = QLabel("Cursor Δt: —    Δvalue: —"); plot_layout.addWidget(self.cursor_label)
        try:
            import pyqtgraph as pg
            self.plot = pg.PlotWidget(); self.plot.showGrid(x=True, y=True, alpha=0.25); self.plot.addLegend(); plot_layout.addWidget(self.plot)
            self._pg = pg
            self.cursor_a = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen(width=1.2)); self.cursor_b = pg.InfiniteLine(angle=90, movable=True, pen=pg.mkPen(width=1.2))
            self.cursor_a.sigPositionChanged.connect(self._update_cursors); self.cursor_b.sigPositionChanged.connect(self._update_cursors)
        except ImportError:
            self.plot = None; self._pg = None; self.cursor_a = None; self.cursor_b = None
            plot_layout.addWidget(QLabel("pyqtgraph is required to display comparison traces."))
        self.tabs.addTab(self.plot_container, "Signals")

        distribution = QWidget(); distribution_layout = QVBoxLayout(distribution)
        self.distribution_metric = QComboBox(); self.distribution_metric.currentTextChanged.connect(self._render_distribution)
        distribution_layout.addWidget(self.distribution_metric)
        if self._pg is not None:
            self.distribution_plot = self._pg.PlotWidget(); self.distribution_plot.showGrid(x=True, y=True, alpha=0.2); distribution_layout.addWidget(self.distribution_plot, 1)
        else:
            self.distribution_plot = None; distribution_layout.addWidget(QLabel("pyqtgraph is required for metric distributions."))
        self.tabs.addTab(distribution, "Distributions")

        self.warning_label = QLabel(); self.warning_label.setWordWrap(True); layout.addWidget(self.warning_label)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self.mode.currentTextChanged.connect(lambda _text: self._render_plot()); self.refresh()

    def _selected_reference_id(self) -> str:
        return str(self.reference.currentData() or self.reference.currentText())

    def _populate_trace_list(self) -> None:
        existing = {self.trace_list.item(index).data(Qt.ItemDataRole.UserRole): self.trace_list.item(index).checkState() for index in range(self.trace_list.count())}
        self.trace_list.blockSignals(True); self.trace_list.clear()
        if self.result:
            for index, compared in enumerate(self.result.signals):
                item = QListWidgetItem(compared.run_name); item.setData(Qt.ItemDataRole.UserRole, compared.run_id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(existing.get(compared.run_id, Qt.CheckState.Checked))
                colour = self._colours.setdefault(compared.run_id, QColor.fromHsv((index * 47) % 360, 190, 220))
                item.setForeground(colour); self.trace_list.addItem(item)
        self.trace_list.blockSignals(False)

    def _visible_run_ids(self) -> set[str]:
        return {
            str(self.trace_list.item(index).data(Qt.ItemDataRole.UserRole))
            for index in range(self.trace_list.count())
            if self.trace_list.item(index).checkState() == Qt.CheckState.Checked
        }

    def _choose_colour(self, item: QListWidgetItem) -> None:
        run_id = str(item.data(Qt.ItemDataRole.UserRole)); selected = QColorDialog.getColor(self._colours.get(run_id, QColor("#4477aa")), self, "Select trace colour")
        if selected.isValid():
            self._colours[run_id] = selected; item.setForeground(selected); self._render_plot()

    def refresh(self) -> None:
        try:
            self.result = compare_runs(
                self.campaign, self.run_ids, reference_run_id=self._selected_reference_id(),
                signal_key=self.signal_key.text().strip() or None, alignment=self.alignment.currentText(), maximum_traces=20,
            )
        except ValueError as exc:
            self.result = None; self.warning_label.setText(str(exc)); return
        frame = self.result.metrics
        self.metric_table.setSortingEnabled(False); self.metric_table.setRowCount(len(frame)); self.metric_table.setColumnCount(len(frame.columns))
        self.metric_table.setHorizontalHeaderLabels([str(column) for column in frame.columns])
        outlier_pairs = {(run_id, metric) for metric, run_ids in self.result.outliers.items() for run_id in run_ids}
        for visual_row, (_frame_index, record) in enumerate(frame.iterrows()):
            run_id = str(record.get("run_id", ""))
            for column, name in enumerate(frame.columns):
                value = record[name]
                item = QTableWidgetItem("" if pd.isna(value) else str(value)); item.setData(Qt.ItemDataRole.UserRole, value)
                if (run_id, str(name)) in outlier_pairs:
                    item.setBackground(QColor("#fff2cc")); item.setToolTip("Robust metric outlier")
                self.metric_table.setItem(visual_row, column, item)
        self.metric_table.setSortingEnabled(True); self.metric_table.resizeColumnsToContents()
        self._populate_trace_list(); self._populate_distribution_metrics(); self._render_plot()
        self.warning_label.setText("\n".join(self.result.warnings))

    def _render_plot(self) -> None:
        if self.plot is None or self.result is None:
            return
        self.plot.clear(); self.plot.addLegend()
        visible = self._visible_run_ids(); mode = self.mode.currentText()
        rendered = 0
        for item in self.result.signals:
            if item.run_id not in visible:
                continue
            signal = item.signal if mode == "overlay" else item.difference if mode == "difference" else item.percentage_difference
            if signal is None:
                continue
            colour = self._colours.get(item.run_id, QColor("#4477aa"))
            pen = self._pg.mkPen(colour.name(), width=1.5)
            self.plot.plot(signal.time, np.real(signal.values), pen=pen, name=item.run_name); rendered += 1
        if self.result.signals:
            first = self.result.signals[0]
            unit = first.signal.unit if mode != "percentage_difference" else "%"
            label = first.signal.name if mode == "overlay" else "Difference" if mode == "difference" else "Percentage difference"
            self.plot.setLabel("bottom", "Time", units="s"); self.plot.setLabel("left", label, units=unit)
            if self.cursor_a is not None and self.cursor_b is not None:
                start = float(first.signal.time[0]); stop = float(first.signal.time[-1])
                self.cursor_a.setValue(start + (stop - start) * 0.35); self.cursor_b.setValue(start + (stop - start) * 0.65)
                self.plot.addItem(self.cursor_a); self.plot.addItem(self.cursor_b); self._update_cursors()
        if rendered == 0:
            self.warning_label.setText("No comparison traces are currently visible.")

    def _update_cursors(self) -> None:
        if self.result is None or self.cursor_a is None or self.cursor_b is None or not self.result.signals:
            return
        x1, x2 = float(self.cursor_a.value()), float(self.cursor_b.value())
        visible = self._visible_run_ids(); compared = next((item for item in self.result.signals if item.run_id in visible), self.result.signals[0])
        signal = compared.signal if self.mode.currentText() == "overlay" else compared.difference if self.mode.currentText() == "difference" else compared.percentage_difference
        if signal is None:
            return
        y1 = float(np.interp(x1, signal.time, np.real(signal.values))); y2 = float(np.interp(x2, signal.time, np.real(signal.values)))
        self.cursor_label.setText(f"{compared.run_name} — Cursor Δt: {x2 - x1:.6g} s    Δvalue: {y2 - y1:.6g} {signal.unit}")

    def _populate_distribution_metrics(self) -> None:
        current = self.distribution_metric.currentText(); self.distribution_metric.blockSignals(True); self.distribution_metric.clear()
        if self.result is not None:
            for column in self.result.metrics.columns:
                if column in {"run_id", "file_name", "status"} or column.startswith(("metadata:", "difference:", "percent_difference:")):
                    continue
                if pd.to_numeric(self.result.metrics[column], errors="coerce").notna().any():
                    self.distribution_metric.addItem(str(column))
        self.distribution_metric.setCurrentText(current); self.distribution_metric.blockSignals(False); self._render_distribution(self.distribution_metric.currentText())

    def _render_distribution(self, metric: str) -> None:
        if self.distribution_plot is None or self.result is None or not metric:
            return
        values = pd.to_numeric(self.result.metrics[metric], errors="coerce").dropna().to_numpy(dtype=float)
        self.distribution_plot.clear()
        if not len(values):
            return
        bins = min(20, max(3, int(np.sqrt(len(values)))))
        counts, edges = np.histogram(values, bins=bins)
        widths = np.diff(edges); centers = edges[:-1] + widths / 2
        self.distribution_plot.addItem(self._pg.BarGraphItem(x=centers, height=counts, width=widths * 0.9))
        self.distribution_plot.setLabel("bottom", metric); self.distribution_plot.setLabel("left", "Runs")

    def export(self) -> None:
        if not self.result:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Comparison", "comparison.xlsx", "Excel (*.xlsx);;CSV (*.csv)")
        if not path:
            return
        try:
            export_comparison_tables(self.result, path)
        except Exception as exc:
            QMessageBox.critical(self, "Export Comparison", str(exc))

    def export_plot(self) -> None:
        if not self.result:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export Comparison Plot", "comparison.png", "PNG (*.png);;SVG (*.svg);;PDF (*.pdf)")
        if not path:
            return
        try:
            export_comparison_plot(self.result, path, mode=self.mode.currentText())
        except Exception as exc:
            QMessageBox.critical(self, "Export Comparison Plot", str(exc))

