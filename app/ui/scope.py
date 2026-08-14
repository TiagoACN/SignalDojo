# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Interactive multi-signal scope dock for SignalDojo."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QDockWidget, QFileDialog, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton, QVBoxLayout, QWidget

from app.application import settings
from app.core.models import SignalData, signals_to_frame
from app.ui.formatting import format_number


class ScopeDock(QDockWidget):
    """Responsive engineering scope with traces, cursors and export tools."""

    def __init__(
        self,
        title: str,
        signals: list[SignalData],
        max_points: int,
        parent=None,
        *,
        grid: bool = True,
        legend: bool = True,
        line_width: float = 1.5,
        line_style: str = "solid",
        show_markers: bool = False,
        show_peaks: bool = False,
        auto_scale: bool = True,
        x_min: str = "",
        x_max: str = "",
        y_min: str = "",
        y_max: str = "",
    ) -> None:
        super().__init__(title, parent)
        self._signals: list[SignalData] = []
        self._max_points = max_points
        self._grid = grid; self._legend_enabled = legend; self._line_width = line_width
        self._line_style = line_style; self._show_markers = show_markers; self._show_peaks = show_peaks
        self._auto_scale = auto_scale; self._manual_ranges = (x_min, x_max, y_min, y_max)
        self._trace_items: list[object] = []; self._peak_items: list[object] = []
        container = QWidget(); layout = QVBoxLayout(container); layout.setContentsMargins(4, 4, 4, 4)
        controls = QHBoxLayout()
        self.cursor_readout = QLabel("Cursor measurements"); self.cursor_readout.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.trace_menu = QMenu(self); trace_button = QPushButton("Traces"); trace_button.setMenu(self.trace_menu)
        auto_button = QPushButton("Autoscale"); auto_button.clicked.connect(lambda: self.plot.enableAutoRange())
        export_button = QPushButton("Export plot…"); export_button.clicked.connect(self.export_plot)
        data_button = QPushButton("Export data…"); data_button.clicked.connect(self.export_data)
        copy_button = QPushButton("Copy image"); copy_button.clicked.connect(self.copy_image)
        full_button = QPushButton("Full screen"); full_button.clicked.connect(self.toggle_fullscreen)
        controls.addWidget(self.cursor_readout, 1); controls.addWidget(trace_button); controls.addWidget(auto_button); controls.addWidget(export_button); controls.addWidget(data_button); controls.addWidget(copy_button); controls.addWidget(full_button)
        layout.addLayout(controls)
        self.plot = pg.PlotWidget(); self.plot.showGrid(x=grid, y=grid, alpha=0.25); self.legend = self.plot.addLegend() if legend else None
        self.plot.setLabel("bottom", "Time", units="s"); self.plot.setDownsampling(auto=True, mode="peak"); self.plot.setClipToView(True)
        layout.addWidget(self.plot, 1); self.setWidget(container)
        self.cursor_a = pg.InfiniteLine(angle=90, movable=True, label="A", labelOpts={"position": 0.92})
        self.cursor_b = pg.InfiniteLine(angle=90, movable=True, label="B", labelOpts={"position": 0.82})
        self.region = pg.LinearRegionItem(movable=True, brush=(100, 140, 180, 35)); self.region.setZValue(-10)
        self.cursor_a.sigPositionChanged.connect(self._update_cursor_readout); self.cursor_b.sigPositionChanged.connect(self._update_cursor_readout); self.region.sigRegionChanged.connect(self._update_cursor_readout)
        self.update_signals(
            signals, max_points, grid=grid, legend=legend, line_width=line_width,
            line_style=line_style, show_markers=show_markers, show_peaks=show_peaks,
            auto_scale=auto_scale, x_min=x_min, x_max=x_max, y_min=y_min, y_max=y_max,
        )

    @staticmethod
    def _optional_float(value: str) -> float | None:
        try:
            return float(str(value).strip()) if str(value).strip() else None
        except ValueError:
            return None

    def update_signals(
        self,
        signals: list[SignalData],
        max_points: int,
        *,
        grid: bool | None = None,
        legend: bool | None = None,
        line_width: float | None = None,
        line_style: str | None = None,
        show_markers: bool | None = None,
        show_peaks: bool | None = None,
        auto_scale: bool | None = None,
        x_min: str | None = None,
        x_max: str | None = None,
        y_min: str | None = None,
        y_max: str | None = None,
    ) -> None:
        self._signals = list(signals); self._max_points = max_points
        if grid is not None: self._grid = grid
        if legend is not None: self._legend_enabled = legend
        if line_width is not None: self._line_width = line_width
        if line_style is not None: self._line_style = line_style
        if show_markers is not None: self._show_markers = show_markers
        if show_peaks is not None: self._show_peaks = show_peaks
        if auto_scale is not None: self._auto_scale = auto_scale
        ranges = list(self._manual_ranges)
        for index, value in enumerate((x_min, x_max, y_min, y_max)):
            if value is not None: ranges[index] = value
        self._manual_ranges = tuple(ranges)

        self.plot.clear(); self.trace_menu.clear(); self._trace_items.clear(); self._peak_items.clear(); self.plot.showGrid(x=self._grid, y=self._grid, alpha=0.25)
        if self.legend is not None:
            self.legend.clear(); self.legend.setVisible(self._legend_enabled)
        if not signals:
            self.cursor_readout.setText("No signals connected."); return
        units = {signal.unit for signal in signals if signal.unit}
        self.plot.setLabel("left", "Amplitude", units=next(iter(units)) if len(units) == 1 else None)
        style_map = {
            "solid": Qt.PenStyle.SolidLine,
            "dash": Qt.PenStyle.DashLine,
            "dot": Qt.PenStyle.DotLine,
            "dash-dot": Qt.PenStyle.DashDotLine,
        }
        for signal in signals:
            if signal.samples > max_points:
                indices = np.linspace(0, signal.samples - 1, max_points, dtype=int); time = signal.time[indices]; values = signal.values[indices]
            else:
                time, values = signal.time, signal.values
            trace = self.plot.plot(
                time,
                values,
                name=signal.name,
                pen=pg.mkPen(width=self._line_width, style=style_map.get(self._line_style, Qt.PenStyle.SolidLine)),
                symbol="o" if self._show_markers else None,
                symbolSize=4,
            )
            self._trace_items.append(trace)
            action = self.trace_menu.addAction(signal.name); action.setCheckable(True); action.setChecked(True); action.toggled.connect(trace.setVisible)
            if self._show_peaks and signal.samples >= 3:
                try:
                    from scipy.signal import find_peaks
                    real_values = np.real(np.asarray(signal.values, dtype=complex)).astype(float)
                    finite = np.isfinite(real_values)
                    clean = np.where(finite, real_values, np.nanmedian(real_values[finite]) if np.any(finite) else 0.0)
                    peak_indices, properties = find_peaks(clean, prominence=max(float(np.nanstd(clean)) * 0.25, np.finfo(float).eps))
                    if len(peak_indices):
                        strongest = peak_indices[np.argsort(clean[peak_indices])[-8:]]
                        marker = self.plot.plot(signal.time[strongest], clean[strongest], pen=None, symbol="t", symbolSize=9)
                        self._peak_items.append(marker)
                        for peak_index in strongest:
                            label = pg.TextItem(f"{clean[peak_index]:.4g}", anchor=(0.5, 1.25)); label.setPos(float(signal.time[peak_index]), float(clean[peak_index])); self.plot.addItem(label); self._peak_items.append(label)
                except Exception:
                    # Peak annotation is a display aid and must never prevent the
                    # underlying scope from opening.
                    pass
        minimum_time = min(float(signal.time[0]) for signal in signals); maximum_time = max(float(signal.time[-1]) for signal in signals); span = max(maximum_time - minimum_time, 1e-9)
        self.cursor_a.setValue(minimum_time + span * 0.25); self.cursor_b.setValue(minimum_time + span * 0.75); self.region.setRegion((minimum_time + span * 0.35, minimum_time + span * 0.65))
        self.plot.addItem(self.cursor_a, ignoreBounds=True); self.plot.addItem(self.cursor_b, ignoreBounds=True); self.plot.addItem(self.region, ignoreBounds=True)
        if self._auto_scale:
            self.plot.enableAutoRange()
        else:
            xmin, xmax, ymin, ymax = (self._optional_float(value) for value in self._manual_ranges)
            if xmin is not None and xmax is not None and xmax > xmin: self.plot.setXRange(xmin, xmax, padding=0)
            if ymin is not None and ymax is not None and ymax > ymin: self.plot.setYRange(ymin, ymax, padding=0)
        self._update_cursor_readout()

    def _update_cursor_readout(self) -> None:
        if not self._signals: return
        signal = self._signals[0]; x_a, x_b = float(self.cursor_a.value()), float(self.cursor_b.value())
        index_a = int(np.clip(np.searchsorted(signal.time, x_a), 0, signal.samples - 1)); index_b = int(np.clip(np.searchsorted(signal.time, x_b), 0, signal.samples - 1))
        y_a, y_b = float(np.real(signal.values[index_a])), float(np.real(signal.values[index_b])); unit = f" {signal.unit}" if signal.unit else ""
        r0, r1 = self.region.getRegion(); region_mask = (signal.time >= r0) & (signal.time <= r1); region_rms = float(np.sqrt(np.nanmean(np.abs(signal.values[region_mask]) ** 2))) if np.any(region_mask) else float("nan")
        app_settings = settings(); precision = app_settings.value("defaults/precision", 6, type=int); engineering = app_settings.value("defaults/engineering_notation", True, type=bool)
        fmt = lambda value: format_number(value, precision, engineering)
        self.cursor_readout.setText(f"{signal.name}: A {fmt(signal.time[index_a])}s/{fmt(y_a)}{unit}   B {fmt(signal.time[index_b])}s/{fmt(y_b)}{unit}   Δt {fmt(abs(signal.time[index_b]-signal.time[index_a]))}s   ΔA {fmt(abs(y_b-y_a))}{unit}   Region RMS {fmt(region_rms)}{unit}")

    def export_plot(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export scope", "scope.png", "PNG (*.png);;SVG (*.svg);;PDF (*.pdf)")
        if not path: return
        suffix = Path(path).suffix.lower()
        if suffix in {".png", ".svg"}:
            import pyqtgraph.exporters
            exporter = pyqtgraph.exporters.ImageExporter(self.plot.plotItem) if suffix == ".png" else pyqtgraph.exporters.SVGExporter(self.plot.plotItem)
            exporter.export(path)
        else:
            import matplotlib
            matplotlib.use("Agg")
            from matplotlib import pyplot as plt
            figure, axis = plt.subplots(figsize=(10, 6))
            for signal in self._signals: axis.plot(signal.time, signal.values, label=signal.name)
            axis.set_xlabel("Time (s)"); axis.set_ylabel("Amplitude"); axis.grid(True, alpha=0.3); axis.legend(); figure.tight_layout(); figure.savefig(path); plt.close(figure)

    def export_data(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export scope data", "scope_data.csv", "CSV (*.csv);;TSV (*.tsv);;Excel (*.xlsx);;JSON (*.json);;NumPy archive (*.npz)")
        if not path: return
        destination = Path(path); suffix = destination.suffix.lower()
        try:
            try:
                frame = signals_to_frame(self._signals)
            except ValueError:
                # Non-aligned traces are exported losslessly in long format rather than
                # silently truncating or resampling them.
                import pandas as pd
                frame = pd.concat(
                    [
                        pd.DataFrame({"signal": signal.name, "time": signal.time, "value": signal.values, "unit": signal.unit})
                        for signal in self._signals
                    ],
                    ignore_index=True,
                )
            if suffix == ".csv": frame.to_csv(destination, index=False)
            elif suffix == ".tsv": frame.to_csv(destination, index=False, sep="\t")
            elif suffix == ".xlsx": frame.to_excel(destination, index=False)
            elif suffix == ".json": frame.to_json(destination, orient="records", indent=2)
            elif suffix == ".npz":
                arrays = {str(column): frame[column].to_numpy() for column in frame.columns}
                np.savez(destination, **arrays)
            else: raise ValueError("Choose CSV, TSV, XLSX, JSON or NPZ.")
        except Exception as exc:
            QMessageBox.critical(self, "Export Scope Data", str(exc))

    def copy_image(self) -> None:
        QGuiApplication.clipboard().setPixmap(self.plot.grab())

    def toggle_fullscreen(self) -> None:
        self.setFloating(True)
        if self.isFullScreen(): self.showNormal()
        else: self.showFullScreen()

