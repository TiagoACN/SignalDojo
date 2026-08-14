# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Extraction and compact aggregation of campaign metrics."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from app.core.expression import UnsafeExpression, evaluate_expression
from app.core.models import ScalarResult, SignalData, SpectrumData, TableResult


SCALAR_AGGREGATIONS = (
    "auto", "value", "mean", "rms", "standard_deviation", "minimum", "maximum",
    "peak_to_peak", "dominant_frequency", "sample_count", "duration", "rise_time",
    "settling_time", "first", "last", "custom_expression",
)


def _finite_real(values: np.ndarray, label: str) -> np.ndarray:
    values = np.asarray(values)
    if np.iscomplexobj(values):
        raise ValueError(f"{label} requires real-valued data")
    values = values.astype(float, copy=False)
    finite = values[np.isfinite(values)]
    if not len(finite):
        raise ValueError(f"{label} contains no finite values")
    return finite


def _rise_time(signal: SignalData) -> float:
    values = _finite_real(signal.values, "Rise time")
    if len(values) != signal.samples:
        raise ValueError("Rise time cannot ignore missing samples; clean the signal first")
    initial = float(np.median(values[: max(1, min(len(values), len(values) // 10 or 1))]))
    final = float(np.median(values[-max(1, min(len(values), len(values) // 10 or 1)) :]))
    span = final - initial
    if math.isclose(span, 0.0, abs_tol=1e-15):
        raise ValueError("Rise time is undefined because the signal has no measurable step")
    low = initial + 0.1 * span
    high = initial + 0.9 * span
    if span > 0:
        low_indices = np.flatnonzero(values >= low); high_indices = np.flatnonzero(values >= high)
    else:
        low_indices = np.flatnonzero(values <= low); high_indices = np.flatnonzero(values <= high)
    if not len(low_indices) or not len(high_indices):
        raise ValueError("Signal never crosses the 10% and 90% rise-time thresholds")
    low_index, high_index = int(low_indices[0]), int(high_indices[0])
    if high_index < low_index:
        low_index, high_index = high_index, low_index
    return float(signal.time[high_index] - signal.time[low_index])


def _settling_time(signal: SignalData, tolerance_fraction: float = 0.02) -> float:
    values = _finite_real(signal.values, "Settling time")
    if len(values) != signal.samples:
        raise ValueError("Settling time cannot ignore missing samples; clean the signal first")
    tail_count = max(3, min(len(values), max(3, len(values) // 10)))
    final = float(np.median(values[-tail_count:]))
    initial = float(values[0])
    scale = max(abs(final - initial), abs(final), np.finfo(float).eps)
    tolerance = tolerance_fraction * scale
    outside = np.flatnonzero(np.abs(values - final) > tolerance)
    if not len(outside):
        return 0.0
    last_outside = int(outside[-1])
    if last_outside >= len(values) - 1:
        raise ValueError("Signal does not settle within the captured duration")
    return float(signal.time[last_outside + 1] - signal.time[0])


def _dominant_frequency(value: SignalData | SpectrumData) -> float:
    if isinstance(value, SignalData):
        if value.sample_rate is None or not value.is_uniform:
            raise ValueError("Dominant frequency requires a uniformly sampled signal with a known sample rate")
        samples = np.asarray(value.values)
        if np.any(~np.isfinite(samples)):
            raise ValueError("Dominant frequency cannot process NaN or infinite values")
        samples = samples - np.mean(samples)
        if np.iscomplexobj(samples):
            spectrum = np.fft.fft(samples)
            frequency = np.fft.fftfreq(len(samples), d=1.0 / value.sample_rate)
            mask = frequency >= 0
            frequency, magnitude = frequency[mask], np.abs(spectrum[mask])
        else:
            spectrum = np.fft.rfft(samples)
            frequency, magnitude = np.fft.rfftfreq(len(samples), d=1.0 / value.sample_rate), np.abs(spectrum)
    else:
        frequency, magnitude = np.asarray(value.frequency), np.abs(np.asarray(value.values))
    if len(magnitude) <= 1:
        raise ValueError("Dominant frequency requires at least two frequency bins")
    candidates = np.arange(len(magnitude))
    non_dc = candidates[np.abs(frequency) > np.finfo(float).eps]
    selected = non_dc if len(non_dc) else candidates
    return float(frequency[selected[int(np.nanargmax(magnitude[selected]))]])


def aggregate_metric(value: Any, aggregation: str = "auto", *, expression: str = "") -> tuple[Any, str, str]:
    """Return ``(compact value, unit, description)`` for a workflow output."""

    mode = str(aggregation or "auto").strip().lower()
    if isinstance(value, ScalarResult):
        if mode not in {"auto", "value", "first", "last"}:
            raise ValueError(f"Aggregation '{mode}' is not applicable to scalar result '{value.name}'")
        scalar = value.value
        if isinstance(scalar, complex):
            if not math.isclose(scalar.imag, 0.0, abs_tol=1e-12):
                raise ValueError("Complex scalar values are not suitable campaign metrics")
            scalar = float(scalar.real)
        return scalar, value.unit, value.description
    if isinstance(value, TableResult):
        if value.frame.size != 1:
            raise ValueError("A table campaign metric must contain exactly one cell")
        scalar = value.frame.iat[0, 0]
        if hasattr(scalar, "item"):
            scalar = scalar.item()
        return scalar, str(value.metadata.get("unit", "")), value.description
    if isinstance(value, SpectrumData):
        if mode not in {"auto", "dominant_frequency"}:
            raise ValueError("Spectrum outputs can currently publish only dominant frequency")
        return _dominant_frequency(value), "Hz", "Dominant non-DC spectral frequency"
    if not isinstance(value, SignalData):
        if isinstance(value, (bool, str, int, float)):
            return value, "", ""
        raise ValueError(f"{type(value).__name__} is not a compact campaign metric")

    values = np.asarray(value.values)
    finite = _finite_real(values, "Campaign metric") if mode not in {"dominant_frequency"} else values
    mode = "mean" if mode in {"auto", "value"} else mode
    unit = value.unit
    description = ""
    if mode == "mean": result = float(np.mean(finite)); description = "Mean"
    elif mode == "rms": result = float(np.sqrt(np.mean(np.square(finite)))); description = "Root mean square"
    elif mode == "standard_deviation": result = float(np.std(finite)); description = "Standard deviation"
    elif mode == "minimum": result = float(np.min(finite)); description = "Minimum"
    elif mode == "maximum": result = float(np.max(finite)); description = "Maximum"
    elif mode == "peak_to_peak": result = float(np.ptp(finite)); description = "Peak-to-peak"
    elif mode == "dominant_frequency": result = _dominant_frequency(value); unit = "Hz"; description = "Dominant non-DC frequency"
    elif mode == "sample_count": result = int(value.samples); unit = "samples"; description = "Sample count"
    elif mode == "duration": result = float(value.duration); unit = "s"; description = "Captured duration"
    elif mode == "rise_time": result = _rise_time(value); unit = "s"; description = "10–90% rise time"
    elif mode == "settling_time": result = _settling_time(value); unit = "s"; description = "2% settling time"
    elif mode == "first": result = float(finite[0]); description = "First finite sample"
    elif mode == "last": result = float(finite[-1]); description = "Last finite sample"
    elif mode == "custom_expression":
        variables = {
            "mean": float(np.mean(finite)), "rms": float(np.sqrt(np.mean(np.square(finite)))),
            "std": float(np.std(finite)), "minimum": float(np.min(finite)), "maximum": float(np.max(finite)),
            "peak_to_peak": float(np.ptp(finite)), "sample_count": int(value.samples), "duration": float(value.duration),
            "first": float(finite[0]), "last": float(finite[-1]),
        }
        try:
            evaluated = evaluate_expression(expression, variables)
        except UnsafeExpression as exc:
            raise ValueError(str(exc)) from exc
        array = np.asarray(evaluated)
        if array.ndim != 0:
            raise ValueError("Custom campaign metric expression must return a scalar")
        result = array.item(); description = f"Custom expression: {expression}"
    else:
        raise ValueError(f"Unsupported metric aggregation '{aggregation}'")
    if isinstance(result, float) and not math.isfinite(result):
        raise ValueError("Campaign metric result is NaN or infinite")
    return result, unit, description
