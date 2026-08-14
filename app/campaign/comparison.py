# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Multi-run campaign comparison, alignment and outlier analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from app.core.models import SignalData
from app.project.result_codec import deserialise_result

from .models import CampaignRun, TestCampaign


@dataclass(slots=True)
class ComparedSignal:
    run_id: str
    run_name: str
    signal_key: str
    signal: SignalData
    difference: SignalData | None = None
    percentage_difference: SignalData | None = None


@dataclass(slots=True)
class ComparisonResult:
    reference_run_id: str
    metrics: pd.DataFrame
    signals: list[ComparedSignal] = field(default_factory=list)
    outliers: dict[str, list[str]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def available_signal_keys(run: CampaignRun) -> list[str]:
    output: list[str] = []
    for key, payload in run.detail_results.items():
        try:
            if str(payload.get("type", "")) == "signal":
                output.append(key)
        except AttributeError:
            continue
    return sorted(output)


def _signal(run: CampaignRun, key: str) -> SignalData:
    payload = run.detail_results.get(key)
    if not isinstance(payload, dict):
        raise ValueError(f"Run '{run.file_name}' does not contain detailed signal '{key}'.")
    value = deserialise_result(payload)
    if not isinstance(value, SignalData):
        raise ValueError(f"Detailed result '{key}' in run '{run.file_name}' is not a signal.")
    return value


def _align(reference: SignalData, other: SignalData, mode: str) -> tuple[SignalData, SignalData]:
    if reference.unit != other.unit:
        raise ValueError(
            f"Cannot compare '{reference.name}' ({reference.unit or 'unspecified'}) with "
            f"'{other.name}' ({other.unit or 'unspecified'}). Insert explicit unit conversion in the workflow."
        )
    mode = mode.lower()
    if mode == "exact":
        if reference.samples != other.samples or not np.allclose(reference.time, other.time, rtol=1e-7, atol=1e-12):
            raise ValueError("Signals have different time bases. Choose overlap interpolation or resample them in the workflow.")
        return reference, other
    if mode not in {"interpolate_to_reference", "overlap"}:
        raise ValueError(f"Unknown comparison alignment mode '{mode}'.")
    if mode == "interpolate_to_reference":
        if float(other.time[0]) > float(reference.time[0]) or float(other.time[-1]) < float(reference.time[-1]):
            raise ValueError(
                "The compared signal does not cover the complete reference time range. "
                "Choose overlap interpolation or resample/crop the signals explicitly in the workflow."
            )
        target_time = reference.time
        reference_values = reference.values
    else:
        start = max(float(reference.time[0]), float(other.time[0]))
        stop = min(float(reference.time[-1]), float(other.time[-1]))
        if stop <= start:
            raise ValueError("Signals have no overlapping time interval.")
        reference_mask = (reference.time >= start) & (reference.time <= stop)
        target_time = reference.time[reference_mask]
        reference_values = reference.values[reference_mask]
    if len(target_time) < 2:
        raise ValueError("Signals have fewer than two reference samples in their overlapping interval.")
    if np.iscomplexobj(other.values):
        values = np.interp(target_time, other.time, np.real(other.values)) + 1j * np.interp(target_time, other.time, np.imag(other.values))
    else:
        values = np.interp(target_time, other.time, other.values)
    return (
        reference.with_values(reference_values, time=target_time, sample_rate=None),
        other.with_values(values, time=target_time, sample_rate=None),
    )


def metric_table(runs: Iterable[CampaignRun]) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    all_metrics = sorted({name for run in runs for name in run.metrics})
    for run in runs:
        record: dict[str, Any] = {
            "run_id": run.run_id, "file_name": run.file_name, "status": run.status.value,
            **{f"metadata:{key}": value for key, value in run.user_metadata.items()},
        }
        record.update({name: run.metrics.get(name) for name in all_metrics})
        records.append(record)
    return pd.DataFrame(records)



def metric_comparison_frame(runs: Iterable[CampaignRun], reference_run_id: str) -> pd.DataFrame:
    """Return raw metric values plus explicit deltas from the selected reference."""

    frame = metric_table(runs)
    if frame.empty:
        return frame
    reference_rows = frame[frame["run_id"].astype(str) == str(reference_run_id)]
    if reference_rows.empty:
        raise ValueError("The reference run is not present in the metric comparison table.")
    reference = reference_rows.iloc[0]
    reserved = {"run_id", "file_name", "status"}
    for column in list(frame.columns):
        if column in reserved or column.startswith("metadata:"):
            continue
        numeric = pd.to_numeric(frame[column], errors="coerce")
        try:
            reference_value = float(reference[column])
        except (TypeError, ValueError):
            continue
        if not np.isfinite(reference_value):
            continue
        delta = numeric - reference_value
        frame[f"difference:{column}"] = delta
        if abs(reference_value) <= np.finfo(float).eps:
            frame[f"percent_difference:{column}"] = np.nan
        else:
            frame[f"percent_difference:{column}"] = 100.0 * delta / reference_value
    return frame

def detect_metric_outliers(frame: pd.DataFrame, *, threshold: float = 3.5) -> dict[str, list[str]]:
    outliers: dict[str, list[str]] = {}
    if frame.empty or "run_id" not in frame:
        return outliers
    for column in frame.columns:
        if column in {"run_id", "file_name", "status"} or column.startswith("metadata:"):
            continue
        values = pd.to_numeric(frame[column], errors="coerce")
        valid = values.dropna()
        if len(valid) < 4:
            continue
        median = float(valid.median())
        deviations = np.abs(valid.to_numpy(dtype=float) - median)
        mad = float(np.median(deviations))
        if mad <= np.finfo(float).eps:
            continue
        robust_z = 0.67448975 * deviations / mad
        indices = valid.index[robust_z > threshold]
        if len(indices):
            outliers[column] = [str(frame.loc[index, "run_id"]) for index in indices]
    return outliers


def compare_runs(
    campaign: TestCampaign,
    run_ids: Iterable[str],
    *,
    reference_run_id: str | None = None,
    signal_key: str | None = None,
    alignment: str = "exact",
    maximum_traces: int = 20,
) -> ComparisonResult:
    selected_ids = list(dict.fromkeys(str(run_id) for run_id in run_ids))
    runs = [run for run_id in selected_ids if (run := campaign.run_by_id(run_id)) is not None]
    if len(runs) < 2:
        raise ValueError("Select at least two campaign runs for comparison.")
    reference_id = reference_run_id or campaign.reference_run_id or runs[0].run_id
    reference = next((run for run in runs if run.run_id == reference_id), None)
    if reference is None:
        raise ValueError("The selected reference run is not part of the comparison.")
    raw_frame = metric_table(runs)
    frame = metric_comparison_frame(runs, reference_id)
    result = ComparisonResult(reference_id, frame, outliers=detect_metric_outliers(raw_frame))
    if alignment != "exact":
        result.warnings.append(
            "Signals were interpolated for comparison. This changes only the comparison view; retained campaign results are not modified."
        )
    if not signal_key:
        common = set(available_signal_keys(runs[0]))
        for run in runs[1:]:
            common &= set(available_signal_keys(run))
        signal_key = sorted(common)[0] if common else None
    if signal_key:
        if len(runs) > maximum_traces:
            result.warnings.append(
                f"Only the first {maximum_traces} of {len(runs)} selected runs are rendered to keep comparison responsive."
            )
            runs = runs[:maximum_traces]
            if reference not in runs:
                runs[-1] = reference
        reference_signal = _signal(reference, signal_key)
        for run in runs:
            signal = _signal(run, signal_key)
            aligned_ref, aligned = _align(reference_signal, signal, alignment)
            delta_values = aligned.values - aligned_ref.values
            difference = aligned.with_values(delta_values, name=f"{run.file_name} − reference")
            denominator = np.asarray(aligned_ref.values)
            percent = np.full(len(denominator), np.nan, dtype=float)
            nonzero = np.abs(denominator) > np.finfo(float).eps
            percent[nonzero] = 100.0 * np.real(delta_values[nonzero] / denominator[nonzero])
            percentage = aligned.with_values(percent, name=f"{run.file_name} % difference", unit="%")
            result.signals.append(ComparedSignal(run.run_id, run.file_name, signal_key, aligned, difference, percentage))
    return result


def _spreadsheet_safe(value: Any) -> Any:
    if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def export_comparison_tables(result: ComparisonResult, path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    metrics = result.metrics.map(_spreadsheet_safe) if not result.metrics.empty else result.metrics
    if destination.suffix.lower() == ".xlsx":
        with pd.ExcelWriter(destination, engine="openpyxl") as writer:
            metrics.to_excel(writer, sheet_name="Metrics", index=False)
            for index, item in enumerate(result.signals[:10], 1):
                columns: dict[str, Any] = {"time": item.signal.time}
                for name, signal in (
                    ("value", item.signal),
                    ("difference", item.difference),
                    ("percentage_difference", item.percentage_difference),
                ):
                    if signal is None:
                        columns[name] = np.nan
                    elif np.iscomplexobj(signal.values):
                        columns[f"{name}_real"] = np.real(signal.values)
                        columns[f"{name}_imag"] = np.imag(signal.values)
                    else:
                        columns[name] = signal.values
                pd.DataFrame(columns).to_excel(writer, sheet_name=f"Signal_{index}", index=False)
    else:
        metrics.to_csv(destination, index=False)
    return destination


def export_comparison_plot(result: ComparisonResult, path: str | Path, *, mode: str = "overlay") -> Path:
    """Export the selected comparison traces as PNG, SVG or PDF."""

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not result.signals:
        raise ValueError("The comparison contains no retained signal traces to plot.")
    mode = mode.lower()
    if mode not in {"overlay", "difference", "percentage_difference"}:
        raise ValueError(f"Unsupported comparison plot mode '{mode}'.")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 6.5))
    for item in result.signals:
        signal = item.signal if mode == "overlay" else item.difference if mode == "difference" else item.percentage_difference
        if signal is None:
            continue
        ax.plot(signal.time, np.real(signal.values), linewidth=1.2, label=item.run_name)
    ax.set_xlabel("Time (s)")
    first = result.signals[0]
    if mode == "overlay":
        ax.set_ylabel(f"{first.signal.name} ({first.signal.unit})" if first.signal.unit else first.signal.name)
        ax.set_title("Campaign run overlay")
    elif mode == "difference":
        ax.set_ylabel(f"Difference ({first.signal.unit})" if first.signal.unit else "Difference")
        ax.set_title("Difference from reference")
    else:
        ax.set_ylabel("Percentage difference (%)")
        ax.set_title("Percentage difference from reference")
    ax.grid(alpha=0.25); ax.legend(loc="best", fontsize=8); fig.tight_layout(); fig.savefig(destination, dpi=160); plt.close(fig)
    return destination
