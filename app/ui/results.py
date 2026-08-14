# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Result visualisation docks for spectra, tables and spectrograms."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDockWidget, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.application import settings
from app.core.models import ScalarResult, SignalData, SpectrogramData, SpectrumData, TableResult
from app.ui.formatting import format_number


def _save_frame(parent: QWidget, frame: pd.DataFrame, default_name: str) -> None:
    path, _ = QFileDialog.getSaveFileName(parent, "Export displayed data", default_name, "CSV (*.csv);;TSV (*.tsv);;Excel (*.xlsx);;JSON (*.json);;NumPy archive (*.npz)")
    if not path: return
    destination = Path(path); suffix = destination.suffix.lower()
    try:
        if suffix == ".csv": frame.to_csv(destination, index=False)
        elif suffix == ".tsv": frame.to_csv(destination, index=False, sep="\t")
        elif suffix == ".xlsx": frame.to_excel(destination, index=False)
        elif suffix == ".json": frame.to_json(destination, orient="records", indent=2)
        elif suffix == ".npz": np.savez(destination, **{str(column): frame[column].to_numpy() for column in frame.columns})
        else: raise ValueError("Choose CSV, TSV, XLSX, JSON or NPZ.")
    except Exception as exc:
        QMessageBox.critical(parent, "Export Data", str(exc))


def _copy_frame(frame: pd.DataFrame) -> None:
    QGuiApplication.clipboard().setText(frame.to_csv(index=False, sep="\t"))


def _export_plot(parent: QWidget, plot: pg.PlotWidget, default_name: str, draw_pdf) -> None:
    path, _ = QFileDialog.getSaveFileName(parent, "Export plot", default_name, "PNG (*.png);;SVG (*.svg);;PDF (*.pdf)")
    if not path: return
    destination = Path(path); suffix = destination.suffix.lower()
    try:
        if suffix in {".png", ".svg"}:
            import pyqtgraph.exporters
            exporter = pyqtgraph.exporters.ImageExporter(plot.plotItem) if suffix == ".png" else pyqtgraph.exporters.SVGExporter(plot.plotItem)
            exporter.export(str(destination))
        elif suffix == ".pdf": draw_pdf(destination)
        else: raise ValueError("Choose PNG, SVG or PDF.")
    except Exception as exc:
        QMessageBox.critical(parent, "Export Plot", str(exc))


class TableDock(QDockWidget):
    def __init__(self, title: str, value, maximum_rows: int = 10_000, parent=None) -> None:
        super().__init__(title, parent)
        container = QWidget(); layout = QVBoxLayout(container); controls = QHBoxLayout(); controls.addStretch(1)
        export = QPushButton("Export data…"); export.clicked.connect(lambda: _save_frame(self, self._frame, "table.csv"))
        copy = QPushButton("Copy table"); copy.clicked.connect(lambda: _copy_frame(self._frame))
        controls.addWidget(export); controls.addWidget(copy); layout.addLayout(controls)
        self.table = QTableWidget(); layout.addWidget(self.table, 1); self.setWidget(container); self.update_value(value, maximum_rows)

    def update_value(self, value, maximum_rows: int = 10_000) -> None:
        if isinstance(value, SignalData): frame = value.to_frame()
        elif isinstance(value, TableResult): frame = value.frame
        elif isinstance(value, ScalarResult): frame = pd.DataFrame({"name": [value.name], "value": [value.value], "unit": [value.unit]})
        else: frame = pd.DataFrame({"value": [repr(value)]})
        self._frame = frame.copy(); visible = frame.head(maximum_rows)
        app_settings = settings(); precision = app_settings.value("defaults/precision", 6, type=int); engineering = app_settings.value("defaults/engineering_notation", True, type=bool)
        self.table.clear(); self.table.setRowCount(len(visible)); self.table.setColumnCount(len(visible.columns)); self.table.setHorizontalHeaderLabels([str(c) for c in visible.columns])
        for row in range(len(visible)):
            for column in range(len(visible.columns)):
                item = QTableWidgetItem(format_number(visible.iat[row, column], precision, engineering)); item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable); self.table.setItem(row, column, item)
        self.table.resizeColumnsToContents()


class SpectrumDock(QDockWidget):
    def __init__(self, title: str, spectrum: SpectrumData, parent=None, *, log_frequency: bool = False, decibel: bool = False) -> None:
        super().__init__(title, parent)
        container = QWidget(); layout = QVBoxLayout(container); controls = QHBoxLayout(); self.readout = QLabel(); controls.addWidget(self.readout, 1)
        export_plot = QPushButton("Export plot…"); export_plot.clicked.connect(self.export_plot)
        export_data = QPushButton("Export data…"); export_data.clicked.connect(self.export_data)
        copy = QPushButton("Copy image"); copy.clicked.connect(lambda: QGuiApplication.clipboard().setPixmap(self.plot.grab()))
        controls.addWidget(export_plot); controls.addWidget(export_data); controls.addWidget(copy); layout.addLayout(controls)
        self.plot = pg.PlotWidget(); self.plot.showGrid(x=True, y=True, alpha=0.25); self.plot.setLabel("bottom", "Frequency", units="Hz"); layout.addWidget(self.plot, 1); self.setWidget(container)
        self.cursor_a = pg.InfiniteLine(angle=90, movable=True, label="A"); self.cursor_b = pg.InfiniteLine(angle=90, movable=True, label="B")
        self.cursor_a.sigPositionChanged.connect(self._update_readout); self.cursor_b.sigPositionChanged.connect(self._update_readout)
        self._spectrum = spectrum; self._log_frequency = log_frequency; self._decibel = decibel; self.update_spectrum(spectrum, log_frequency=log_frequency, decibel=decibel)

    def update_spectrum(self, spectrum: SpectrumData, *, log_frequency: bool = False, decibel: bool = False) -> None:
        self._spectrum = spectrum; self._log_frequency = log_frequency; self._decibel = decibel; self.plot.clear(); values = np.abs(spectrum.values)
        if decibel:
            power_scale = spectrum.scale.lower() in {"power", "power spectral density", "psd"}
            multiplier = 10.0 if power_scale else 20.0
            values = multiplier * np.log10(np.maximum(values, np.finfo(float).tiny))
            self.plot.setLabel("left", "Power" if power_scale else "Amplitude", units="dB")
        else: self.plot.setLabel("left", spectrum.scale)
        self._display_values = values; self.plot.setLogMode(x=log_frequency, y=False); self.plot.plot(spectrum.frequency, values)
        if len(spectrum.frequency):
            peak_frequency = float(spectrum.frequency[int(np.nanargmax(values))]); upper_frequency = float(spectrum.frequency[-1])
            self.cursor_a.setValue(peak_frequency); self.cursor_b.setValue(min(upper_frequency, peak_frequency * 1.25 if peak_frequency > 0 else upper_frequency * 0.25))
            self.plot.addItem(self.cursor_a, ignoreBounds=True); self.plot.addItem(self.cursor_b, ignoreBounds=True)
        self._update_readout()

    def _update_readout(self) -> None:
        if not len(self._spectrum.frequency): return
        frequency_a, frequency_b = float(self.cursor_a.value()), float(self.cursor_b.value())
        index_a = int(np.clip(np.searchsorted(self._spectrum.frequency, frequency_a), 0, len(self._spectrum.frequency)-1)); index_b = int(np.clip(np.searchsorted(self._spectrum.frequency, frequency_b), 0, len(self._spectrum.frequency)-1))
        peak_index = int(np.nanargmax(self._display_values)); app_settings = settings(); precision = app_settings.value("defaults/precision", 6, type=int); engineering = app_settings.value("defaults/engineering_notation", True, type=bool); resolution = np.median(np.diff(self._spectrum.frequency)) if len(self._spectrum.frequency)>1 else 0
        fmt = lambda value: format_number(value, precision, engineering)
        self.readout.setText(f"A: {fmt(self._spectrum.frequency[index_a])} Hz / {fmt(self._display_values[index_a])}   B: {fmt(self._spectrum.frequency[index_b])} Hz / {fmt(self._display_values[index_b])}   Δf: {fmt(abs(self._spectrum.frequency[index_b]-self._spectrum.frequency[index_a]))} Hz   ΔA: {fmt(abs(self._display_values[index_b]-self._display_values[index_a]))}   Peak: {fmt(self._spectrum.frequency[peak_index])} Hz   Resolution: {fmt(resolution)} Hz")

    def export_data(self) -> None:
        frame = pd.DataFrame({"frequency_hz": self._spectrum.frequency, "value": self._spectrum.values})
        if self._decibel:
            frame["display_value_db"] = self._display_values
        _save_frame(self, frame, "spectrum.csv")

    def export_plot(self) -> None:
        def draw(destination: Path) -> None:
            import matplotlib; matplotlib.use("Agg")
            from matplotlib import pyplot as plt
            figure, axis = plt.subplots(figsize=(10, 6)); axis.plot(self._spectrum.frequency, self._display_values); axis.set_xlabel("Frequency (Hz)"); axis.set_ylabel("Level (dB)" if self._decibel else self._spectrum.scale); axis.grid(True, alpha=0.3)
            if self._log_frequency: axis.set_xscale("log")
            figure.tight_layout(); figure.savefig(destination); plt.close(figure)
        _export_plot(self, self.plot, "spectrum.png", draw)


class SpectrogramDock(QDockWidget):
    def __init__(self, title: str, data: SpectrogramData, parent=None, *, minimum_frequency: float = 0.0, maximum_frequency: float = 0.0, colour_map: str = "viridis") -> None:
        super().__init__(title, parent)
        container = QWidget(); layout = QVBoxLayout(container); controls = QHBoxLayout(); controls.addStretch(1)
        export_plot = QPushButton("Export image…"); export_plot.clicked.connect(self.export_plot)
        export_data = QPushButton("Export data…"); export_data.clicked.connect(self.export_data)
        copy = QPushButton("Copy image"); copy.clicked.connect(lambda: QGuiApplication.clipboard().setPixmap(self.plot.grab()))
        controls.addWidget(export_plot); controls.addWidget(export_data); controls.addWidget(copy); layout.addLayout(controls)
        self.plot = pg.PlotWidget(); self.image = pg.ImageItem(); self.plot.addItem(self.image); self.plot.setLabel("bottom", "Time", units="s"); self.plot.setLabel("left", "Frequency", units="Hz"); layout.addWidget(self.plot, 1); self.setWidget(container)
        self.update_data(data, minimum_frequency=minimum_frequency, maximum_frequency=maximum_frequency, colour_map=colour_map)

    def update_data(self, data: SpectrogramData, *, minimum_frequency: float = 0.0, maximum_frequency: float = 0.0, colour_map: str = "viridis") -> None:
        self._data = data; self._minimum_frequency = minimum_frequency; self._maximum_frequency = maximum_frequency; self._colour_map = colour_map
        values = np.abs(data.values) if np.iscomplexobj(data.values) else data.values
        upper = maximum_frequency if maximum_frequency > 0 else float(data.frequency[-1]) if len(data.frequency) else 0.0
        mask = (data.frequency >= minimum_frequency) & (data.frequency <= upper); frequency = data.frequency[mask]; visible = values[mask, :]
        if not len(frequency): frequency = data.frequency; visible = values
        self._visible_frequency = frequency; self._visible_values = visible; self.image.setImage(visible.T, autoLevels=True)
        try:
            colour = pg.colormap.get(colour_map, source="matplotlib"); self.image.setLookupTable(colour.getLookupTable())
        except Exception: pass
        if len(data.time) > 1 and len(frequency) > 1:
            self.image.setRect(QRectF(float(data.time[0]), float(frequency[0]), float(data.time[-1]-data.time[0]), float(frequency[-1]-frequency[0])))

    def export_data(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export spectrogram data", "spectrogram.npz", "NumPy archive (*.npz);;CSV long format (*.csv)")
        if not path: return
        destination = Path(path)
        try:
            if destination.suffix.lower() == ".npz": np.savez(destination, time=self._data.time, frequency=self._visible_frequency, values=self._visible_values)
            elif destination.suffix.lower() == ".csv":
                frequency_grid, time_grid = np.meshgrid(self._visible_frequency, self._data.time, indexing="ij")
                pd.DataFrame({"time": time_grid.ravel(), "frequency_hz": frequency_grid.ravel(), "value": self._visible_values.ravel()}).to_csv(destination, index=False)
            else: raise ValueError("Choose NPZ or CSV.")
        except Exception as exc: QMessageBox.critical(self, "Export Spectrogram Data", str(exc))

    def export_plot(self) -> None:
        def draw(destination: Path) -> None:
            import matplotlib; matplotlib.use("Agg")
            from matplotlib import pyplot as plt
            figure, axis = plt.subplots(figsize=(10, 6)); mesh = axis.pcolormesh(self._data.time, self._visible_frequency, self._visible_values, shading="auto", cmap=self._colour_map); axis.set_xlabel("Time (s)"); axis.set_ylabel("Frequency (Hz)"); figure.colorbar(mesh, ax=axis); figure.tight_layout(); figure.savefig(destination); plt.close(figure)
        _export_plot(self, self.plot, "spectrogram.png", draw)
