# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Supporting dialogs for previews, diagnostics and project metadata."""

from __future__ import annotations

import importlib.metadata
import json
import platform
from pathlib import Path
import sys
from typing import Any

import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QWizard,
    QWizardPage,
)

from app.application import APP_NAME, VERSION, user_data_dir
from app.core.blocks import PLUGIN_ERRORS, ImportDataBlock, ProcessingBlock


class ProjectInfoDialog(QDialog):
    def __init__(self, project: dict[str, Any], parent=None) -> None:
        super().__init__(parent); self.setWindowTitle("Project Information"); self.resize(600, 430)
        layout = QVBoxLayout(self); form = QFormLayout()
        self.name = QLineEdit(str(project.get("name", ""))); self.description = QPlainTextEdit(str(project.get("description", ""))); self.notes = QPlainTextEdit(str(project.get("notes", "")))
        self.description.setMaximumHeight(120); self.notes.setMaximumHeight(140)
        form.addRow("Project name", self.name); form.addRow("Description", self.description); form.addRow("Notes", self.notes); layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def value(self) -> dict[str, str]:
        return {"name": self.name.text().strip(), "description": self.description.toPlainText(), "notes": self.notes.toPlainText()}


class ImportPreviewDialog(QDialog):
    """Preview rows and write selected columns back into an Import Data block."""

    def __init__(self, block: ImportDataBlock, parent=None) -> None:
        super().__init__(parent); self.block = block; self.setWindowTitle("Import Preview"); self.resize(950, 650)
        layout = QVBoxLayout(self)
        self.status = QLabel(); layout.addWidget(self.status)
        controls = QHBoxLayout(); self.time_column = QComboBox(); self.signal_columns = QLineEdit(str(block.params.get("signal_columns", ""))); self.signal_columns.setPlaceholderText("Comma-separated signal columns")
        controls.addWidget(QLabel("Time column")); controls.addWidget(self.time_column); controls.addWidget(QLabel("Signal columns")); controls.addWidget(self.signal_columns, 1); layout.addLayout(controls)
        self.table = QTableWidget(); layout.addWidget(self.table, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)
        self._load_preview()

    def _load_preview(self) -> None:
        try:
            frame = self.block.preview(200)
        except Exception as exc:
            self.status.setText(f"Preview failed: {exc}"); return
        self.status.setText(f"Showing first {len(frame)} rows and {len(frame.columns)} columns.")
        columns = [str(column) for column in frame.columns]; self.time_column.addItem(""); self.time_column.addItems(columns); self.time_column.setCurrentText(str(self.block.params.get("time_column", "")))
        self.table.setRowCount(len(frame)); self.table.setColumnCount(len(columns)); self.table.setHorizontalHeaderLabels(columns)
        for row in range(len(frame)):
            for column in range(len(columns)):
                item = QTableWidgetItem(str(frame.iat[row, column])); item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable); self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()

    def apply(self) -> None:
        self.block.params["time_column"] = self.time_column.currentText(); self.block.params["signal_columns"] = self.signal_columns.text().strip()


class FilterResponseDialog(QDialog):
    def __init__(self, block: ProcessingBlock, parent=None) -> None:
        super().__init__(parent); self.block = block; self.setWindowTitle(f"{block.display_name} — Frequency Response"); self.resize(900, 650)
        layout = QVBoxLayout(self); controls = QHBoxLayout(); self.sample_rate = QDoubleSpinBox(); self.sample_rate.setRange(1e-6, 1e9); self.sample_rate.setValue(1000.0); self.sample_rate.setSuffix(" Hz")
        refresh = QPushButton("Refresh"); refresh.clicked.connect(self.refresh); controls.addWidget(QLabel("Preview sample rate")); controls.addWidget(self.sample_rate); controls.addWidget(refresh); controls.addStretch(1); layout.addLayout(controls)
        self.summary = QLabel(); self.summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); layout.addWidget(self.summary)
        tabs = QTabWidget(); self.magnitude = pg.PlotWidget(); self.phase = pg.PlotWidget(); tabs.addTab(self.magnitude, "Magnitude"); tabs.addTab(self.phase, "Phase"); layout.addWidget(tabs, 1)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close); close.rejected.connect(self.reject); layout.addWidget(close); self.refresh()

    def refresh(self) -> None:
        self.magnitude.clear(); self.phase.clear()
        response_method = getattr(self.block, "frequency_response", None)
        if not callable(response_method): return
        sample_rate = float(self.sample_rate.value())
        try: frequency, response = response_method(sample_rate)
        except Exception as exc:
            self.summary.setText(f"Invalid settings: {exc}"); self.magnitude.setTitle("Invalid filter settings"); return
        import numpy as np
        magnitude_db = 20 * np.log10(np.maximum(np.abs(response), np.finfo(float).tiny)); phase_deg = np.unwrap(np.angle(response)) * 180 / np.pi
        self.magnitude.plot(frequency, magnitude_db); self.magnitude.setLabel("bottom", "Frequency", units="Hz"); self.magnitude.setLabel("left", "Magnitude", units="dB"); self.magnitude.showGrid(x=True, y=True, alpha=0.25)
        self.phase.plot(frequency, phase_deg); self.phase.setLabel("bottom", "Frequency", units="Hz"); self.phase.setLabel("left", "Phase", units="°"); self.phase.showGrid(x=True, y=True, alpha=0.25)
        marker_values = []
        visible_parameters = {
            spec.name for spec in self.block.parameters if spec.is_visible(self.block.params)
        }
        for key in ("cutoff", "lower_cutoff", "upper_cutoff", "frequency"):
            if key in self.block.params and key in visible_parameters:
                try:
                    value = float(self.block.params[key])
                    if 0 < value < sample_rate / 2 and value not in marker_values: marker_values.append(value)
                except (TypeError, ValueError): pass
        for value in marker_values:
            self.magnitude.addItem(pg.InfiniteLine(value, angle=90, movable=False, label=f"{value:g} Hz"), ignoreBounds=True)
            self.phase.addItem(pg.InfiniteLine(value, angle=90, movable=False), ignoreBounds=True)
        nyquist = sample_rate / 2
        stability_method = getattr(self.block, "stability", None)
        stability_text = "Stability: not applicable or not reported"
        if callable(stability_method):
            try:
                stable, maximum_pole = stability_method(sample_rate)
                stability_text = f"Stability: {'stable' if stable else 'UNSTABLE'}; maximum pole magnitude {maximum_pole:.6g}"
            except Exception as exc:
                stability_text = f"Stability check failed: {exc}"
        self.summary.setText(f"Nyquist: {nyquist:g} Hz   Frequency points: {len(frequency)}   {stability_text}")


class DiagnosticsDialog(QDialog):
    def __init__(self, project_validation: str = "Not checked", parent=None) -> None:
        super().__init__(parent); self.setWindowTitle("SignalDojo Diagnostics"); self.resize(820, 620)
        layout = QVBoxLayout(self); text = QPlainTextEdit(); text.setReadOnly(True); layout.addWidget(text, 1)
        packages = {}
        for name in ("numpy", "scipy", "pandas", "PySide6", "pyqtgraph", "matplotlib", "openpyxl", "nptdms"):
            try: packages[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError: packages[name] = "not installed"
        log_path = user_data_dir() / "logs" / "signaldojo.log"
        try: recent_log = "\n".join(log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-120:])
        except OSError: recent_log = "Log unavailable."
        report = {
            "application": f"{APP_NAME} {VERSION}", "python": sys.version, "executable": sys.executable,
            "operating_system": platform.platform(), "machine": platform.machine(), "packages": packages,
            "project_validation": project_validation, "plugin_errors": PLUGIN_ERRORS,
            "user_data_directory": str(user_data_dir()), "log_file": str(log_path),
        }
        self.report_text = json.dumps(report, indent=2) + "\n\nRecent log entries\n" + "=" * 70 + "\n" + recent_log
        text.setPlainText(self.report_text)
        controls = QHBoxLayout(); controls.addStretch(1)
        copy = QPushButton("Copy report"); copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self.report_text))
        save = QPushButton("Save report…"); save.clicked.connect(self._save_report)
        controls.addWidget(copy); controls.addWidget(save); layout.addLayout(controls)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def _save_report(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Save diagnostics report", "SignalDojo-diagnostics.txt", "Text files (*.txt);;JSON and text (*.json *.txt)")
        if path:
            Path(path).write_text(self.report_text, encoding="utf-8")


class WelcomeDialog(QWizard):
    """First-run step-by-step tutorial rather than a passive splash message."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent); self.setWindowTitle("SignalDojo Quick Start Tutorial"); self.resize(760, 560); self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)
        pages = [
            (
                "Welcome to SignalDojo",
                "<h2>Build, analyse and master your signals.</h2><p>This short tutorial introduces the complete workflow: importing data, connecting processing blocks, inspecting results and saving a reusable project.</p>",
            ),
            (
                "1 — Import engineering data",
                "<ol><li>Drag <b>Import Data</b> from the left library.</li><li>Choose a CSV, Excel, JSON, NumPy, HDF5 or TDMS source.</li><li>Use <b>Workflow → Preview Selected Import</b> to inspect rows and choose channels.</li><li>SignalDojo can infer a likely time column; disable automatic detection when a fixed sample rate should be used instead.</li></ol>",
            ),
            (
                "2 — Construct the processing chain",
                "<ol><li>Drag a filter, mathematical, conditioning or analysis block onto the canvas.</li><li>Click an output port, then a compatible input port.</li><li>Select a block to edit its validated properties.</li><li>Use comments, groups, copy/paste, alignment and <b>Tidy Workflow</b> to keep complex projects readable.</li></ol>",
            ),
            (
                "3 — Inspect and measure",
                "<ol><li>Connect raw and processed signals to a <b>Scope</b>.</li><li>Add Spectrum Analyser, Spectrogram Viewer, Statistics Display or Data Table blocks as required.</li><li>Press <b>F5</b> to run. Use scope cursors, region RMS, trace visibility, zoom and peak annotations to inspect the result.</li></ol>",
            ),
            (
                "4 — Export and preserve",
                "<ol><li>Add Export Data, Export Plot or Export Report blocks.</li><li>Save the workflow as a versioned <b>.sdojo</b> project.</li><li>Open one of the three bundled examples from <b>File → Open Example</b>.</li><li>SignalDojo automatically maintains backups and a crash-recovery copy while a project is dirty.</li></ol><p>Press <b>Finish</b> and begin on the empty canvas.</p>",
            ),
        ]
        for title, body in pages:
            page = QWizardPage(); page.setTitle(title); layout = QVBoxLayout(page); label = QLabel(body); label.setWordWrap(True); label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction); layout.addWidget(label); layout.addStretch(1); self.addPage(page)


class PreferencesDialog(QDialog):
    def __init__(self, values: dict[str, Any], parent=None) -> None:
        super().__init__(parent); self.setWindowTitle("SignalDojo Preferences"); self.resize(540, 410)
        layout = QVBoxLayout(self); form = QFormLayout()
        self.sample_rate = QDoubleSpinBox(); self.sample_rate.setRange(1e-6, 1e9); self.sample_rate.setDecimals(6); self.sample_rate.setValue(float(values.get("default_sample_rate", 1000.0))); self.sample_rate.setSuffix(" Hz")
        self.unit = QLineEdit(str(values.get("default_unit", "")))
        from PySide6.QtWidgets import QSpinBox, QCheckBox
        self.precision = QSpinBox(); self.precision.setRange(3, 16); self.precision.setValue(int(values.get("numeric_precision", 6)))
        self.engineering = QCheckBox(); self.engineering.setChecked(bool(values.get("engineering_notation", True)))
        self.result_auto_open = QComboBox()
        self.result_auto_open.addItem("Smart — open a few results", "smart")
        self.result_auto_open.addItem("Keep new results closed", "none")
        self.result_auto_open.addItem("Open every result", "all")
        mode_index = self.result_auto_open.findData(str(values.get("result_auto_open_mode", "smart")))
        self.result_auto_open.setCurrentIndex(mode_index if mode_index >= 0 else 0)
        self.result_auto_open.setToolTip("Smart mode opens all results for small workflows, but limits large result sets to one useful tab. All results remain available from View → Results.")
        self.result_auto_open_limit = QSpinBox(); self.result_auto_open_limit.setRange(1, 20); self.result_auto_open_limit.setValue(int(values.get("result_auto_open_limit", 3)))
        self.result_auto_open_limit.setToolTip("Maximum number of display-block results that Smart mode opens automatically.")
        self.result_auto_open.currentIndexChanged.connect(lambda _index: self.result_auto_open_limit.setEnabled(self.result_auto_open.currentData() == "smart"))
        self.result_auto_open_limit.setEnabled(self.result_auto_open.currentData() == "smart")
        self.update_manifest_url = QLineEdit(str(values.get("update_manifest_url", ""))); self.update_manifest_url.setPlaceholderText("https://signaldojo.org/update.json")
        self.automatic_updates = QCheckBox(); self.automatic_updates.setChecked(bool(values.get("automatic_update_check", False)))
        form.addRow("Default sample rate", self.sample_rate); form.addRow("Default signal unit", self.unit); form.addRow("Displayed significant digits", self.precision); form.addRow("Engineering notation", self.engineering)
        form.addRow("Auto-open workflow results", self.result_auto_open); form.addRow("Smart-mode result limit", self.result_auto_open_limit)
        form.addRow("Update manifest URL", self.update_manifest_url); form.addRow("Check automatically", self.automatic_updates); layout.addLayout(form)
        note = QLabel("Result records are always retained. Closing or suppressing their tabs does not discard them; use View → Results or double-click a display block to reopen one."); note.setWordWrap(True); layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); layout.addWidget(buttons)

    def value(self) -> dict[str, Any]:
        return {"default_sample_rate": self.sample_rate.value(), "default_unit": self.unit.text(), "numeric_precision": self.precision.value(), "engineering_notation": self.engineering.isChecked(), "result_auto_open_mode": str(self.result_auto_open.currentData()), "result_auto_open_limit": self.result_auto_open_limit.value(), "update_manifest_url": self.update_manifest_url.text().strip(), "automatic_update_check": self.automatic_updates.isChecked()}
