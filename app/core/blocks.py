# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""SignalDojo processing-block library.

Blocks are intentionally UI-independent.  Each block declares its ports, parameter
schema and processing method, allowing the node editor, serializer and plugin system
to work from a single registry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
import importlib.util
import json
import math
from pathlib import Path
import re
from typing import Any, Callable, ClassVar, Iterable

import numpy as np
import pandas as pd
from scipy import integrate as scipy_integrate
from scipy import signal as scipy_signal
from scipy import stats as scipy_stats

from .expression import UnsafeExpression, evaluate_expression
from .models import (
    ScalarResult,
    SignalData,
    SpectrogramData,
    SpectrumData,
    TableResult,
    signals_to_frame,
)


class BlockError(RuntimeError):
    """Human-readable processing error associated with a block."""


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    name: str
    label: str
    kind: str
    default: Any
    minimum: float | int | None = None
    maximum: float | int | None = None
    choices: tuple[str, ...] = ()
    help_text: str = ""
    file_filter: str = ""
    advanced: bool = False
    visible_when: tuple[tuple[str, tuple[Any, ...]], ...] = ()

    def is_visible(self, params: dict[str, Any]) -> bool:
        """Return whether this parameter should be shown for the current settings.

        Visibility is a presentation concern only; block execution must still validate
        every parameter that is relevant to the selected processing mode.  Storing the
        rule in the schema keeps the Qt properties panel, block help and future plugin
        editors in agreement.
        """

        return all(params.get(name) in accepted for name, accepted in self.visible_when)


class ProcessingBlock(ABC):
    """Base class for UI-independent processing blocks."""

    type_name: ClassVar[str]
    display_name: ClassVar[str]
    category: ClassVar[str]
    description: ClassVar[str]
    input_count: ClassVar[int] = 1
    minimum_inputs: ClassVar[int | None] = None
    output_count: ClassVar[int] = 1
    input_types: ClassVar[tuple[str, ...]] = ("any",)
    output_types: ClassVar[tuple[str, ...]] = ("any",)
    parameters: ClassVar[tuple[ParameterSpec, ...]] = ()
    cacheable: ClassVar[bool] = True

    def __init__(self, **params: Any) -> None:
        self.params = {spec.name: spec.default for spec in self.parameters}
        known = set(self.params)
        # A block's parameter schema is its public contract.  Keeping unknown keys
        # from older projects caused obsolete settings (such as low-pass lower/upper
        # cutoffs) to leak into previews and saved files.  Migration-aware blocks can
        # translate legacy names before calling this constructor.
        self.params.update({name: value for name, value in params.items() if name in known})

    def validate_parameters(self) -> None:
        """Apply schema-level validation shared by every built-in and plugin block."""

        for spec in self.parameters:
            if not spec.is_visible(self.params):
                continue
            value = self.params.get(spec.name, spec.default)
            if spec.kind in {"int", "float"}:
                try:
                    numeric = float(value)
                except (TypeError, ValueError) as exc:
                    raise BlockError(f"{spec.label} must be numeric.") from exc
                if not math.isfinite(numeric):
                    raise BlockError(f"{spec.label} must be finite.")
                if spec.kind == "int" and not numeric.is_integer():
                    raise BlockError(f"{spec.label} must be an integer.")
                if spec.minimum is not None and numeric < float(spec.minimum):
                    raise BlockError(f"{spec.label} must be at least {spec.minimum}.")
                if spec.maximum is not None and numeric > float(spec.maximum):
                    raise BlockError(f"{spec.label} must not exceed {spec.maximum}.")
            elif spec.kind == "choice" and spec.choices and str(value) not in spec.choices:
                options = ", ".join(spec.choices)
                raise BlockError(f"{spec.label} must be one of: {options}.")

    def validate(self, inputs: list[Any]) -> None:
        self.validate_parameters()
        if len(inputs) != self.input_count:
            raise BlockError(
                f"{self.display_name} exposes {self.input_count} input port(s), "
                f"but received an invalid input vector of length {len(inputs)}."
            )
        required = self.input_count if self.minimum_inputs is None else self.minimum_inputs
        connected = sum(value is not None for value in inputs)
        if connected < required:
            raise BlockError(f"{self.display_name} requires at least {required} connected input(s).")

    @abstractmethod
    def execute(self, inputs: list[Any]) -> list[Any]:
        """Process inputs and return a fixed-length output list."""

    def serialise_params(self) -> dict[str, Any]:
        return dict(self.params)


BLOCK_TYPES: dict[str, type[ProcessingBlock]] = {}
PLUGIN_ERRORS: list[str] = []


def register_block(cls: type[ProcessingBlock]) -> type[ProcessingBlock]:
    if not getattr(cls, "type_name", ""):
        raise ValueError("Registered blocks require a type_name.")
    BLOCK_TYPES[cls.type_name] = cls
    return cls


def create_block(type_name: str, params: dict[str, Any] | None = None) -> ProcessingBlock:
    try:
        block_type = BLOCK_TYPES[type_name]
    except KeyError as exc:
        raise BlockError(f"Unknown block type: {type_name}") from exc
    return block_type(**(params or {}))


def require_signal(value: Any, block_name: str) -> SignalData:
    if not isinstance(value, SignalData):
        raise BlockError(f"{block_name} requires a sampled signal input.")
    return value


def require_spectrum(value: Any, block_name: str) -> SpectrumData:
    if not isinstance(value, SpectrumData):
        raise BlockError(f"{block_name} requires a spectrum input.")
    return value


def connected_signals(inputs: list[Any], block_name: str) -> list[SignalData]:
    return [require_signal(value, block_name) for value in inputs if value is not None]


def require_aligned(signals: Iterable[SignalData], block_name: str) -> list[SignalData]:
    values = list(signals)
    if not values:
        raise BlockError(f"{block_name} requires at least one signal.")
    base = values[0]
    for other in values[1:]:
        if other.samples != base.samples or not np.allclose(other.time, base.time, rtol=1e-7, atol=1e-12):
            raise BlockError(
                f"{block_name} received signals with different time vectors. "
                "Insert an explicit Resample or Synchronise Signals block."
            )
    return values


def require_uniform(signal: SignalData, block_name: str) -> None:
    if not signal.is_uniform:
        raise BlockError(f"{block_name} requires uniformly sampled data. Resample the signal first.")
    if signal.sample_rate is None:
        raise BlockError(f"{block_name} requires a known sample rate.")


def finite_values(signal: SignalData, block_name: str) -> np.ndarray:
    values = np.asarray(signal.values)
    if np.any(~np.isfinite(values)):
        raise BlockError(f"{block_name} cannot process NaN or infinite values. Interpolate or remove them first.")
    return values


def finite_real_values(signal: SignalData, block_name: str) -> np.ndarray:
    """Return finite real-valued samples or raise a readable block error."""

    values = finite_values(signal, block_name)
    if np.iscomplexobj(values):
        raise BlockError(f"{block_name} requires a real-valued signal.")
    return values


def require_matching_units(signals: Iterable[SignalData], block_name: str) -> None:
    """Require exact unit agreement when a calculation compares amplitudes.

    A blank unit means unknown, not dimensionless.  Mixing an unknown unit with a
    known unit is therefore rejected rather than silently treating them as equal.
    """

    units = [signal.unit.strip() for signal in signals]
    if len(set(units)) > 1:
        rendered = ", ".join(unit or "<unspecified>" for unit in units)
        raise BlockError(
            f"{block_name} received incompatible units: {rendered}. "
            "Insert explicit Unit Conversion blocks first."
        )


def power_unit(unit: str, exponent: float) -> str:
    """Return a readable engineering unit after exponentiation."""

    if not unit or exponent == 0:
        return ""
    if exponent == 1:
        return unit
    if float(exponent).is_integer():
        integer = int(exponent)
        superscripts = str.maketrans("-0123456789", "⁻⁰¹²³⁴⁵⁶⁷⁸⁹")
        return f"{unit}{str(integer).translate(superscripts)}"
    return f"{unit}^{exponent:g}"


def history(block: ProcessingBlock, **details: Any) -> dict[str, Any]:
    return {"block": block.display_name, "timestamp_utc": datetime.now(timezone.utc).isoformat(), **details}


def normalise_window(name: str) -> str:
    mapping = {"rectangular": "boxcar", "hanning": "hann"}
    return mapping.get(name.lower(), name.lower())


def inferred_uniform_rate(time_values: np.ndarray) -> float | None:
    """Return the sampling rate represented by a time vector, if it is uniform."""

    time_values = np.asarray(time_values, dtype=float)
    if len(time_values) < 2:
        return None
    delta = np.diff(time_values)
    median_delta = float(np.median(delta))
    if median_delta <= 0 or not np.allclose(delta, median_delta, rtol=1e-4, atol=1e-12):
        return None
    return float(1.0 / median_delta)


def zero_phase_response(response: np.ndarray, enabled: bool) -> np.ndarray:
    """Return the effective response of forward-backward filtering.

    ``filtfilt``/``sosfiltfilt`` applies the designed filter once forward and once
    backward.  The resulting response is zero phase with magnitude ``|H|²``.  Older
    previews displayed the one-pass response even when zero-phase execution was
    selected, understating attenuation and the effective order.
    """

    return response * np.conjugate(response) if enabled else response


# ---------------------------------------------------------------------------
# Inputs and outputs
# ---------------------------------------------------------------------------


@register_block
class ImportDataBlock(ProcessingBlock):
    type_name = "import_data"
    display_name = "Import Data"
    category = "Inputs & Outputs"
    description = "Import up to four signal channels from common engineering data files."
    input_count = 0
    output_count = 4
    output_types = ("signal", "signal", "signal", "signal")
    parameters = (
        ParameterSpec("file_path", "File", "open_file", "", file_filter="Signal data (*.csv *.tsv *.txt *.xlsx *.json *.npy *.npz *.h5 *.hdf5 *.tdms)"),
        ParameterSpec("delimiter", "Delimiter", "text", "auto"),
        ParameterSpec("header_row", "Header row", "int", 0, 0),
        ParameterSpec("skip_rows", "Metadata rows to skip", "int", 0, 0),
        ParameterSpec("sheet_name", "Excel sheet", "text", "0"),
        ParameterSpec("dataset_key", "HDF5 dataset key", "text", "", advanced=True),
        ParameterSpec("time_column", "Time column", "text", ""),
        ParameterSpec("auto_detect_time", "Automatically detect a likely time column", "bool", True),
        ParameterSpec("signal_columns", "Signal columns (comma-separated)", "text", ""),
        ParameterSpec("signal_column", "Legacy signal column", "text", "", advanced=True),
        ParameterSpec("sample_rate", "Sample rate when no time column (Hz)", "float", 100.0, 1e-12),
        ParameterSpec("signal_names", "Output names (comma-separated)", "text", ""),
        ParameterSpec("signal_name", "Legacy single output name", "text", "", advanced=True),
        ParameterSpec("units", "Units (comma-separated)", "text", ""),
        ParameterSpec("unit", "Legacy single output unit", "text", "", advanced=True),
        ParameterSpec("descriptions", "Descriptions (semicolon-separated)", "text", ""),
        ParameterSpec("time_mode", "Time representation", "choice", "auto", choices=("auto", "seconds", "datetime")),
        ParameterSpec("decimal", "Decimal separator", "text", "."),
        ParameterSpec("thousands", "Thousands separator", "text", ""),
        ParameterSpec("missing_policy", "Missing values", "choice", "interpolate", choices=("interpolate", "drop", "zero", "mean", "preserve")),
        ParameterSpec("chunk_size", "CSV chunk size", "int", 250_000, 10_000),
    )

    def validate(self, inputs: list[Any]) -> None:
        super().validate(inputs)
        raw = str(self.params.get("file_path", "")).strip()
        if not raw:
            raise BlockError("Choose a source data file.")
        path = Path(raw).expanduser()
        if not path.exists():
            raise BlockError(f"Source file does not exist: {path}")

    @staticmethod
    def _as_frame(value: Any, source_label: str) -> pd.DataFrame:
        """Normalise table-like reader results to a DataFrame."""

        if isinstance(value, pd.Series):
            return value.to_frame()
        if isinstance(value, pd.DataFrame):
            return value
        raise BlockError(f"{source_label} did not contain a pandas table or series.")

    def _csv_kwargs(self) -> dict[str, Any]:
        delimiter = str(self.params.get("delimiter", "auto"))
        kwargs: dict[str, Any] = {
            "skiprows": int(self.params.get("skip_rows", 0)),
            "header": int(self.params.get("header_row", 0)),
            "decimal": str(self.params.get("decimal", ".")) or ".",
        }
        thousands = str(self.params.get("thousands", ""))
        if thousands:
            kwargs["thousands"] = thousands
        if delimiter.lower() == "auto":
            kwargs.update(sep=None, engine="python")
        else:
            kwargs["sep"] = "\t" if delimiter == "\\t" else delimiter
        return kwargs

    def preview(self, rows: int = 200) -> pd.DataFrame:
        """Read only a small preview where the source format permits it."""

        path = Path(str(self.params.get("file_path", ""))).expanduser()
        if not path.exists():
            raise BlockError(f"Source file does not exist: {path}")
        suffix = path.suffix.lower()
        rows = max(1, int(rows))
        if suffix in {".csv", ".tsv", ".txt"}:
            kwargs = self._csv_kwargs()
            if suffix == ".tsv" and str(self.params.get("delimiter", "auto")).lower() == "auto":
                kwargs = {**kwargs, "sep": "\t", "engine": "c"}
            return pd.read_csv(path, nrows=rows, **kwargs)
        if suffix == ".xlsx":
            sheet_raw = str(self.params.get("sheet_name", "0"))
            sheet: str | int = int(sheet_raw) if sheet_raw.isdigit() else sheet_raw
            return pd.read_excel(
                path,
                sheet_name=sheet,
                skiprows=int(self.params.get("skip_rows", 0)),
                header=int(self.params.get("header_row", 0)),
                nrows=rows,
            )
        if suffix == ".json":
            try:
                return pd.read_json(path).head(rows)
            except ValueError:
                return pd.read_json(path, lines=True, nrows=rows)
        if suffix == ".npy":
            array = np.load(path, mmap_mode="r", allow_pickle=False)
            if array.ndim == 1:
                return pd.DataFrame({path.stem: np.asarray(array[:rows])})
            if array.ndim == 2:
                visible = np.asarray(array[:rows, :])
                return pd.DataFrame(visible, columns=[f"channel_{index + 1}" for index in range(array.shape[1])])
            raise BlockError("NPY data must be one- or two-dimensional.")
        if suffix == ".npz":
            columns: dict[str, np.ndarray] = {}
            with np.load(path, allow_pickle=False) as archive:
                for key in archive.files:
                    array = np.asarray(archive[key]).squeeze()
                    if array.ndim == 1:
                        columns[key] = array[:rows]
            if not columns:
                raise BlockError("NPZ archive contains no one-dimensional arrays to preview.")
            minimum = min(len(value) for value in columns.values())
            return pd.DataFrame({key: value[:minimum] for key, value in columns.items()})
        if suffix in {".h5", ".hdf5"}:
            try:
                key = str(self.params.get("dataset_key", "")).strip() or None
                return self._as_frame(pd.read_hdf(path, key=key, start=0, stop=rows), "HDF5 dataset")
            except (ImportError, ValueError, KeyError, TypeError) as exc:
                raise BlockError("HDF5 preview requires PyTables and a valid dataset key when the file contains multiple datasets.") from exc
        if suffix == ".tdms":
            try:
                from nptdms import TdmsFile  # type: ignore
            except ImportError as exc:
                raise BlockError("TDMS preview requires the optional 'nptdms' package.") from exc
            frames: list[pd.DataFrame] = []
            tdms = TdmsFile.read(path)
            for group in tdms.groups():
                frame = group.as_dataframe(time_index=False).head(rows)
                cleaned_columns = [str(column).split("/")[-1].strip("\'") for column in frame.columns]
                frame.columns = [f"{group.name}/{column}" for column in cleaned_columns]
                frames.append(frame.reset_index(drop=True))
            return pd.concat(frames, axis=1).head(rows) if frames else pd.DataFrame()
        raise BlockError(f"Preview is not supported for {suffix or 'this file type'}.")

    def _read_table(self, path: Path) -> pd.DataFrame:
        suffix = path.suffix.lower()
        if suffix in {".csv", ".tsv", ".txt"}:
            kwargs = self._csv_kwargs()
            if suffix == ".tsv" and str(self.params.get("delimiter", "auto")).lower() == "auto":
                kwargs = {**kwargs, "sep": "\t", "engine": "c"}
            # Chunking keeps the UI worker responsive and avoids parser spikes.  pandas
            # still creates the final frame because downstream blocks require random access.
            chunks = pd.read_csv(path, chunksize=int(self.params.get("chunk_size", 250_000)), **kwargs)
            return pd.concat(chunks, ignore_index=True)
        if suffix == ".xlsx":
            sheet_raw = str(self.params.get("sheet_name", "0"))
            sheet: str | int = int(sheet_raw) if sheet_raw.isdigit() else sheet_raw
            return pd.read_excel(
                path,
                sheet_name=sheet,
                skiprows=int(self.params.get("skip_rows", 0)),
                header=int(self.params.get("header_row", 0)),
            )
        if suffix == ".json":
            try:
                return pd.read_json(path)
            except ValueError:
                return pd.read_json(path, lines=True)
        if suffix in {".h5", ".hdf5"}:
            try:
                key = str(self.params.get("dataset_key", "")).strip() or None
                return self._as_frame(pd.read_hdf(path, key=key), "HDF5 dataset")
            except (ImportError, ValueError, KeyError) as exc:
                raise BlockError("HDF5 import requires PyTables and a valid dataset key when the file contains multiple datasets.") from exc
        if suffix == ".tdms":
            try:
                from nptdms import TdmsFile  # type: ignore
            except ImportError as exc:
                raise BlockError("TDMS import requires the optional 'nptdms' package.") from exc
            frames: list[pd.DataFrame] = []
            tdms = TdmsFile.read(path)
            for group in tdms.groups():
                frame = group.as_dataframe(time_index=False)
                cleaned_columns = [str(column).split("/")[-1].strip("'") for column in frame.columns]
                frame.columns = [f"{group.name}/{column}" for column in cleaned_columns]
                frames.append(frame.reset_index(drop=True))
            return pd.concat(frames, axis=1)
        raise BlockError(f"Unsupported tabular file type: {suffix}")

    @staticmethod
    def _split_list(value: Any) -> list[str]:
        return [item.strip() for item in str(value or "").split(",") if item.strip()]

    @staticmethod
    def _infer_time_column(frame: pd.DataFrame) -> str:
        """Return a likely time column without guessing from arbitrary signal data."""

        preferred = (
            "time", "timestamp", "datetime", "date_time", "elapsed_time",
            "elapsed", "time_s", "seconds", "sec", "t",
        )
        normalised = {str(column).strip().lower().replace(" ", "_"): str(column) for column in frame.columns}
        ordered = [normalised[name] for name in preferred if name in normalised]
        ordered.extend(str(column) for column in frame.columns if str(column) not in ordered)
        for column in ordered:
            label = str(column).strip().lower().replace(" ", "_")
            if label not in preferred and not any(token in label for token in ("time", "date")):
                continue
            series = frame[column]
            numeric = pd.to_numeric(series, errors="coerce")
            if numeric.notna().mean() >= 0.95:
                values = numeric.dropna().to_numpy(dtype=float)
                if len(values) > 1 and np.all(np.diff(values) > 0):
                    return str(column)
            parsed = pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
            if parsed.notna().mean() >= 0.95:
                values = parsed.dropna().astype("int64").to_numpy(dtype=np.int64)
                if len(values) > 1 and np.all(np.diff(values) > 0):
                    return str(column)
        return ""

    def _convert_time(self, series: pd.Series) -> np.ndarray:
        mode = str(self.params.get("time_mode", "auto"))
        numeric = pd.to_numeric(series, errors="coerce")
        self._time_attributes = {"time_representation": "seconds"}
        # Numeric columns remain numeric even when they contain missing values; those
        # missing timestamps are rejected explicitly after conversion.  Falling back
        # to datetime parsing for a float column produced a misleading timestamp error.
        numeric_source = pd.api.types.is_numeric_dtype(series.dtype)
        if mode == "seconds" or (mode == "auto" and (numeric_source or numeric.notna().mean() >= 0.9)):
            return numeric.to_numpy(dtype=float)
        parsed = pd.to_datetime(series, errors="coerce", utc=True, format="mixed")
        if parsed.isna().any():
            raise BlockError("The selected time column contains invalid timestamps.")
        nanoseconds = parsed.astype("int64").to_numpy(dtype=np.int64)
        self._time_attributes = {
            "time_representation": "datetime",
            "time_origin_utc": parsed.iloc[0].isoformat(),
        }
        return (nanoseconds - nanoseconds[0]).astype(float) / 1e9

    def _apply_missing_policy(self, frame: pd.DataFrame, value_columns: list[str]) -> pd.DataFrame:
        """Apply missing-value handling to signal columns, never to timestamps."""

        policy = str(self.params.get("missing_policy", "interpolate"))
        if not frame[value_columns].isna().any().any():
            return frame
        if policy == "interpolate":
            result = frame.copy()
            indexed = result.set_index("__time__")
            indexed[value_columns] = indexed[value_columns].interpolate(method="index", limit_direction="both")
            result = indexed.reset_index()
        elif policy == "drop":
            result = frame.dropna(subset=value_columns)
        elif policy == "zero":
            result = frame.copy()
            result[value_columns] = result[value_columns].fillna(0.0)
        elif policy == "mean":
            result = frame.copy()
            result[value_columns] = result[value_columns].fillna(result[value_columns].mean())
        elif policy == "preserve":
            result = frame
        else:
            raise BlockError(f"Unknown missing-value policy: {policy}")
        if policy != "preserve" and result[value_columns].isna().any().any():
            unresolved = [column for column in value_columns if result[column].isna().any()]
            raise BlockError(
                "Missing-value handling could not produce finite data for: " + ", ".join(unresolved)
            )
        return result

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        path = Path(str(self.params["file_path"])).expanduser().resolve()
        suffix = path.suffix.lower()
        names = self._split_list(self.params.get("signal_names"))
        if not names and str(self.params.get("signal_name", "")).strip():
            names = [str(self.params.get("signal_name")).strip()]
        units = self._split_list(self.params.get("units"))
        if not units and str(self.params.get("unit", "")).strip():
            units = [str(self.params.get("unit")).strip()]
        descriptions = [item.strip() for item in str(self.params.get("descriptions", "")).split(";")]
        outputs: list[SignalData | None] = []
        try:
            if suffix in {".npy", ".npz"}:
                arrays: list[tuple[str, np.ndarray]] = []
                explicit_time: np.ndarray | None = None
                time_key = str(self.params.get("time_column", "")).strip()
                if suffix == ".npy":
                    array = np.asarray(np.load(path, mmap_mode="r", allow_pickle=False))
                    if array.ndim == 1:
                        arrays = [(path.stem, array)]
                    elif array.ndim == 2:
                        available = [f"channel_{i + 1}" for i in range(array.shape[1])]
                        requested = self._split_list(self.params.get("signal_columns")) or available
                        for key in requested[:4]:
                            if key not in available:
                                raise BlockError(f"NPY column '{key}' was not found. Available columns: {', '.join(available)}")
                            arrays.append((key, array[:, available.index(key)]))
                    else:
                        raise BlockError("NPY data must be one- or two-dimensional.")
                else:
                    with np.load(path, allow_pickle=False) as archive:
                        if not time_key and bool(self.params.get("auto_detect_time", True)):
                            normalised_keys = {
                                str(key).strip().lower().replace(" ", "_"): key
                                for key in archive.files
                            }
                            for candidate in ("time", "timestamp", "elapsed_time", "seconds", "t"):
                                key = normalised_keys.get(candidate)
                                if key is None:
                                    continue
                                candidate_time = np.asarray(archive[key]).squeeze()
                                if (
                                    candidate_time.ndim == 1
                                    and np.issubdtype(candidate_time.dtype, np.number)
                                    and np.all(np.isfinite(candidate_time))
                                    and (len(candidate_time) < 2 or np.all(np.diff(candidate_time.astype(float)) > 0))
                                ):
                                    time_key = str(key)
                                    break
                        if time_key:
                            if time_key not in archive.files:
                                raise BlockError(f"NPZ time array '{time_key}' was not found.")
                            explicit_time = np.asarray(archive[time_key]).squeeze()
                            if explicit_time.ndim != 1:
                                raise BlockError(f"NPZ time array '{time_key}' is not one-dimensional.")
                        requested = self._split_list(self.params.get("signal_columns"))
                        keys = requested or [key for key in archive.files if key != time_key]
                        for key in keys[:4]:
                            if key not in archive.files:
                                raise BlockError(f"NPZ array '{key}' was not found.")
                            array = np.asarray(archive[key]).squeeze()
                            if array.ndim != 1:
                                raise BlockError(f"NPZ array '{key}' is not one-dimensional.")
                            arrays.append((key, array))
                if not arrays:
                    raise BlockError("No one-dimensional NumPy signal arrays were selected.")
                if explicit_time is None:
                    fs = float(self.params["sample_rate"])
                    if fs <= 0:
                        raise BlockError("Sample rate must be greater than zero.")
                else:
                    explicit_time = np.asarray(explicit_time, dtype=float)
                    if np.any(~np.isfinite(explicit_time)) or (len(explicit_time) > 1 and np.any(np.diff(explicit_time) <= 0)):
                        raise BlockError("NumPy time values must be finite and strictly increasing.")
                    if len(explicit_time) > 1:
                        delta = np.diff(explicit_time)
                        fs = float(1.0 / np.median(delta)) if np.allclose(delta, np.median(delta), rtol=1e-4, atol=1e-12) else None
                    else:
                        fs = float(self.params["sample_rate"])
                for i, (column_name, raw_values) in enumerate(arrays[:4]):
                    raw_array = np.asarray(raw_values)
                    if not np.issubdtype(raw_array.dtype, np.number):
                        raise BlockError(f"NumPy signal '{column_name}' is not numeric.")
                    values = raw_array.astype(complex if np.iscomplexobj(raw_array) else float, copy=False)
                    generated_rate = float(self.params["sample_rate"])
                    time_values = np.arange(len(values), dtype=float) / generated_rate if explicit_time is None else explicit_time
                    if len(time_values) != len(values):
                        raise BlockError(f"NumPy signal '{column_name}' and time array have different lengths.")
                    selected = pd.DataFrame({"__time__": time_values, column_name: values})
                    selected = self._apply_missing_policy(selected, [column_name])
                    time_values = selected["__time__"].to_numpy(dtype=float)
                    values = selected[column_name].to_numpy()
                    # Dropping missing samples can turn an originally uniform time
                    # vector into an irregular one.  Never retain the pre-policy rate
                    # in that case; downstream filters must require explicit resampling.
                    final_rate = (
                        float(self.params["sample_rate"])
                        if len(time_values) < 2
                        else inferred_uniform_rate(time_values)
                    )
                    outputs.append(
                        SignalData(
                            values=values,
                            time=time_values,
                            name=names[i] if i < len(names) else column_name,
                            unit=units[i] if i < len(units) else "",
                            sample_rate=final_rate,
                            source_file=str(path),
                            channel_name=column_name,
                            description=descriptions[i] if i < len(descriptions) else "",
                            processing_history=[history(self, source=str(path), channel=column_name)],
                            attributes={"time_representation": "seconds" if explicit_time is not None else "generated"},
                        )
                    )
            else:
                frame = self._as_frame(self._read_table(path), "Imported data")
                self._time_attributes = {"time_representation": "generated"}
                if frame.empty:
                    raise BlockError("The selected file contains no rows.")
                frame.columns = [str(column) for column in frame.columns]
                time_col = str(self.params.get("time_column", "")).strip()
                if not time_col and bool(self.params.get("auto_detect_time", True)):
                    time_col = self._infer_time_column(frame)
                requested = self._split_list(self.params.get("signal_columns"))
                legacy = str(self.params.get("signal_column", "")).strip()
                if not requested and legacy:
                    requested = [legacy]
                if not requested:
                    numeric_columns = [
                        str(c)
                        for c in frame.columns
                        if c != time_col and pd.to_numeric(frame[c], errors="coerce").notna().mean() > 0.75
                    ]
                    requested = numeric_columns[:4]
                if not requested:
                    raise BlockError("No numeric signal columns could be inferred.")
                missing = [column for column in requested if column not in frame.columns]
                if missing:
                    raise BlockError(f"Signal column(s) not found: {', '.join(missing)}")
                if time_col:
                    if time_col not in frame.columns:
                        raise BlockError(f"Time column '{time_col}' was not found.")
                    time_values = self._convert_time(frame[time_col])
                else:
                    fs = float(self.params["sample_rate"])
                    if fs <= 0:
                        raise BlockError("Sample rate must be greater than zero.")
                    time_values = np.arange(len(frame), dtype=float) / fs
                if np.any(~np.isfinite(time_values)):
                    raise BlockError("Time data contains missing, NaN or infinite values.")
                if len(time_values) > 1 and np.any(np.diff(time_values) <= 0):
                    raise BlockError("Time values must be strictly increasing.")
                selected = pd.DataFrame({"__time__": time_values})
                invalid_by_column: dict[str, int] = {}
                missing_by_column: dict[str, int] = {}
                for column in requested[:4]:
                    raw_series = frame[column]
                    numeric_series = pd.to_numeric(raw_series, errors="coerce")
                    invalid_by_column[column] = int((raw_series.notna() & numeric_series.isna()).sum())
                    missing_by_column[column] = int(numeric_series.isna().sum())
                    selected[column] = numeric_series
                rows_before_policy = len(selected)
                selected = self._apply_missing_policy(selected, requested[:4])
                rows_removed = rows_before_policy - len(selected)
                final_time = selected["__time__"].to_numpy(dtype=float)
                if len(final_time) < 1:
                    raise BlockError("No valid samples remain after missing-value handling.")
                if np.any(np.diff(final_time) <= 0):
                    raise BlockError("Time values must be strictly increasing.")
                for i, column in enumerate(requested[:4]):
                    values = selected[column].to_numpy(dtype=float)
                    outputs.append(
                        SignalData(
                            values=values,
                            time=final_time,
                            name=names[i] if i < len(names) else column,
                            unit=units[i] if i < len(units) else "",
                            source_file=str(path),
                            channel_name=column,
                            description=descriptions[i] if i < len(descriptions) else "",
                            processing_history=[history(
                                self, source=str(path), channel=column, missing_policy=self.params.get("missing_policy"),
                                invalid_values=invalid_by_column.get(column, 0), missing_values=missing_by_column.get(column, 0), rows_removed=rows_removed,
                            )],
                            attributes={
                                **self._time_attributes,
                                "import_quality": {
                                    "invalid_values": invalid_by_column.get(column, 0),
                                    "missing_values_before_policy": missing_by_column.get(column, 0),
                                    "rows_removed": rows_removed,
                                    "missing_policy": self.params.get("missing_policy"),
                                },
                            },
                        )
                    )
            while len(outputs) < self.output_count:
                outputs.append(None)
            return outputs
        except BlockError:
            raise
        except Exception as exc:  # parser messages differ by engine/version
            raise BlockError(f"Could not import '{path.name}': {exc}") from exc


class GeneratorBlock(ProcessingBlock):
    input_count = 0
    output_types = ("signal",)
    parameters = (
        ParameterSpec("amplitude", "Amplitude", "float", 1.0),
        ParameterSpec("frequency", "Frequency (Hz)", "float", 1.0, 0.0),
        ParameterSpec("phase", "Phase (degrees)", "float", 0.0),
        ParameterSpec("offset", "Offset", "float", 0.0),
        ParameterSpec("sample_rate", "Sample rate (Hz)", "float", 1000.0, 1e-9),
        ParameterSpec("duration", "Duration (s)", "float", 1.0, 1e-9),
        ParameterSpec("name", "Signal name", "text", "Generated signal"),
        ParameterSpec("unit", "Unit", "text", ""),
    )
    enforce_frequency_nyquist: ClassVar[bool] = True

    def waveform(self, time_values: np.ndarray, phase_rad: float) -> np.ndarray:
        raise NotImplementedError

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        fs = float(self.params["sample_rate"])
        duration = float(self.params["duration"])
        if fs <= 0 or duration <= 0:
            raise BlockError("Sample rate and duration must be greater than zero.")
        if self.enforce_frequency_nyquist and "frequency" in self.params:
            frequency = float(self.params["frequency"])
            if frequency < 0:
                raise BlockError("Frequency cannot be negative.")
            if frequency >= fs / 2 and frequency > 0:
                raise BlockError(f"Frequency must be below Nyquist ({fs / 2:g} Hz).")
        samples = max(1, int(round(fs * duration)))
        time_values = np.arange(samples, dtype=float) / fs
        phase = math.radians(float(self.params.get("phase", 0.0)))
        values = float(self.params.get("offset", 0.0)) + float(self.params.get("amplitude", 1.0)) * self.waveform(time_values, phase)
        return [
            SignalData(
                values=values,
                time=time_values,
                name=str(self.params.get("name") or self.display_name),
                unit=str(self.params.get("unit", "")),
                sample_rate=fs,
                processing_history=[history(self, parameters=self.serialise_params())],
            )
        ]


def _register_generator(type_name: str, display_name: str, waveform: Callable[[np.ndarray, float, float], np.ndarray]) -> None:
    def method(self: GeneratorBlock, t: np.ndarray, phase: float) -> np.ndarray:
        return waveform(t, float(self.params["frequency"]), phase)

    cls = type(
        re.sub(r"\W+", "", display_name) + "Block",
        (GeneratorBlock,),
        {
            "type_name": type_name,
            "display_name": display_name,
            "category": "Signal Generators",
            "description": f"Generate a configurable {display_name.lower()}.",
            "waveform": method,
        },
    )
    register_block(cls)


_register_generator("sine", "Sine Wave", lambda t, f, p: np.sin(2 * np.pi * f * t + p))
_register_generator("square", "Square Wave", lambda t, f, p: scipy_signal.square(2 * np.pi * f * t + p))
_register_generator("triangle", "Triangle Wave", lambda t, f, p: scipy_signal.sawtooth(2 * np.pi * f * t + p, width=0.5))
_register_generator("sawtooth", "Sawtooth Wave", lambda t, f, p: scipy_signal.sawtooth(2 * np.pi * f * t + p))


@register_block
class PulseGeneratorBlock(GeneratorBlock):
    type_name = "pulse"
    display_name = "Pulse"
    category = "Signal Generators"
    description = "Generate a periodic pulse train with configurable duty cycle."
    parameters = GeneratorBlock.parameters + (
        ParameterSpec("duty_cycle", "Duty cycle (%)", "float", 10.0, 0.001, 100.0),
    )

    def waveform(self, time_values: np.ndarray, phase_rad: float) -> np.ndarray:
        duty = float(self.params["duty_cycle"]) / 100.0
        return (scipy_signal.square(2 * np.pi * float(self.params["frequency"]) * time_values + phase_rad, duty=duty) + 1.0) / 2.0


@register_block
class StepGeneratorBlock(ProcessingBlock):
    type_name = "step"
    display_name = "Step"
    category = "Signal Generators"
    description = "Generate a signal that changes from an initial value to a final value at a selected time."
    input_count = 0
    output_types = ("signal",)
    parameters = (
        ParameterSpec("initial_value", "Initial value", "float", 0.0),
        ParameterSpec("final_value", "Final value", "float", 1.0),
        ParameterSpec("step_time", "Step time (s)", "float", 0.5, 0.0),
        ParameterSpec("sample_rate", "Sample rate (Hz)", "float", 1000.0, 1e-9),
        ParameterSpec("duration", "Duration (s)", "float", 1.0, 1e-9),
        ParameterSpec("name", "Signal name", "text", "Step"),
        ParameterSpec("unit", "Unit", "text", ""),
    )

    def __init__(self, **params: Any) -> None:
        # Migrate projects created before 1.1, where Step reused the generic
        # amplitude/frequency/offset generator schema.
        migrated = dict(params)
        if "final_value" not in migrated and "amplitude" in migrated:
            migrated["final_value"] = float(migrated.get("offset", 0.0)) + float(migrated["amplitude"])
        if "initial_value" not in migrated and "offset" in migrated:
            migrated["initial_value"] = float(migrated["offset"])
        if "step_time" not in migrated and float(migrated.get("frequency", 0.0) or 0.0) > 0:
            migrated["step_time"] = 1.0 / float(migrated["frequency"])
        super().__init__(**migrated)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        fs, duration = float(self.params["sample_rate"]), float(self.params["duration"])
        step_time = float(self.params["step_time"])
        if step_time >= duration:
            raise BlockError("Step time must be less than the signal duration.")
        samples = max(1, int(round(fs * duration)))
        time_values = np.arange(samples, dtype=float) / fs
        values = np.where(time_values >= step_time, float(self.params["final_value"]), float(self.params["initial_value"]))
        return [SignalData(values, time_values, name=str(self.params["name"]), unit=str(self.params["unit"]), sample_rate=fs, processing_history=[history(self, parameters=self.serialise_params())])]


@register_block
class RampGeneratorBlock(ProcessingBlock):
    type_name = "ramp"
    display_name = "Ramp"
    category = "Signal Generators"
    description = "Generate a linear ramp using an initial value and slope."
    input_count = 0
    output_types = ("signal",)
    parameters = (
        ParameterSpec("initial_value", "Initial value", "float", 0.0),
        ParameterSpec("slope", "Slope (units/s)", "float", 1.0),
        ParameterSpec("sample_rate", "Sample rate (Hz)", "float", 1000.0, 1e-9),
        ParameterSpec("duration", "Duration (s)", "float", 1.0, 1e-9),
        ParameterSpec("name", "Signal name", "text", "Ramp"),
        ParameterSpec("unit", "Unit", "text", ""),
    )

    def __init__(self, **params: Any) -> None:
        migrated = dict(params)
        if "initial_value" not in migrated and "offset" in migrated:
            migrated["initial_value"] = float(migrated["offset"])
        if "slope" not in migrated and ("amplitude" in migrated or "frequency" in migrated):
            migrated["slope"] = float(migrated.get("amplitude", 1.0)) * max(float(migrated.get("frequency", 1.0)), 1e-12)
        super().__init__(**migrated)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        fs, duration = float(self.params["sample_rate"]), float(self.params["duration"])
        samples = max(1, int(round(fs * duration)))
        time_values = np.arange(samples, dtype=float) / fs
        values = float(self.params["initial_value"]) + float(self.params["slope"]) * time_values
        return [SignalData(values, time_values, name=str(self.params["name"]), unit=str(self.params["unit"]), sample_rate=fs, processing_history=[history(self, parameters=self.serialise_params())])]


@register_block
class WhiteNoiseBlock(GeneratorBlock):
    type_name = "white_noise"
    display_name = "White Noise"
    category = "Signal Generators"
    description = "Generate repeatable uniformly distributed white noise."
    parameters = (
        ParameterSpec("amplitude", "Peak amplitude", "float", 1.0, 0.0),
        ParameterSpec("offset", "Offset", "float", 0.0),
        ParameterSpec("sample_rate", "Sample rate (Hz)", "float", 1000.0, 1e-9),
        ParameterSpec("duration", "Duration (s)", "float", 1.0, 1e-9),
        ParameterSpec("name", "Signal name", "text", "White noise"),
        ParameterSpec("unit", "Unit", "text", ""),
        ParameterSpec("seed", "Random seed", "int", 0, 0),
    )
    enforce_frequency_nyquist = False

    def waveform(self, time_values: np.ndarray, phase_rad: float) -> np.ndarray:
        return np.random.default_rng(int(self.params["seed"])).uniform(-1.0, 1.0, len(time_values))


@register_block
class GaussianNoiseBlock(WhiteNoiseBlock):
    type_name = "gaussian_noise"
    display_name = "Gaussian Noise"
    description = "Generate repeatable zero-mean Gaussian noise."
    parameters = (
        ParameterSpec("amplitude", "Standard deviation", "float", 1.0, 0.0),
        ParameterSpec("offset", "Mean / offset", "float", 0.0),
        ParameterSpec("sample_rate", "Sample rate (Hz)", "float", 1000.0, 1e-9),
        ParameterSpec("duration", "Duration (s)", "float", 1.0, 1e-9),
        ParameterSpec("name", "Signal name", "text", "Gaussian noise"),
        ParameterSpec("unit", "Unit", "text", ""),
        ParameterSpec("seed", "Random seed", "int", 0, 0),
    )

    def waveform(self, time_values: np.ndarray, phase_rad: float) -> np.ndarray:
        return np.random.default_rng(int(self.params["seed"])).normal(0.0, 1.0, len(time_values))


@register_block
class ChirpBlock(GeneratorBlock):
    type_name = "chirp"
    display_name = "Chirp"
    category = "Signal Generators"
    description = "Generate a swept-frequency chirp signal."
    parameters = GeneratorBlock.parameters + (
        ParameterSpec("end_frequency", "End frequency (Hz)", "float", 100.0, 0.0),
        ParameterSpec("method", "Sweep method", "choice", "linear", choices=("linear", "quadratic", "logarithmic", "hyperbolic")),
    )

    def waveform(self, time_values: np.ndarray, phase_rad: float) -> np.ndarray:
        return scipy_signal.chirp(
            time_values,
            f0=float(self.params["frequency"]),
            f1=float(self.params["end_frequency"]),
            t1=float(self.params["duration"]),
            method=str(self.params["method"]),
            phi=math.degrees(phase_rad),
        )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        fs = float(self.params["sample_rate"])
        start, end = float(self.params["frequency"]), float(self.params["end_frequency"])
        if max(start, end) >= fs / 2:
            raise BlockError(f"Chirp start and end frequencies must be below Nyquist ({fs / 2:g} Hz).")
        if str(self.params["method"]) in {"logarithmic", "hyperbolic"} and (start <= 0 or end <= 0):
            raise BlockError("Logarithmic and hyperbolic chirps require positive start and end frequencies.")
        return super().execute(inputs)


@register_block
class ConstantBlock(ProcessingBlock):
    type_name = "constant"
    display_name = "Constant"
    category = "Inputs & Outputs"
    description = "Create a constant sampled signal."
    input_count = 0
    output_types = ("signal",)
    parameters = (
        ParameterSpec("value", "Value", "float", 1.0),
        ParameterSpec("sample_rate", "Sample rate (Hz)", "float", 100.0, 1e-9),
        ParameterSpec("duration", "Duration (s)", "float", 1.0, 1e-9),
        ParameterSpec("name", "Signal name", "text", "Constant"),
        ParameterSpec("unit", "Unit", "text", ""),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        fs = float(self.params["sample_rate"])
        duration = float(self.params["duration"])
        samples = max(1, int(round(fs * duration)))
        time_values = np.arange(samples) / fs
        return [SignalData(np.full(samples, float(self.params["value"])), time_values, name=str(self.params["name"]), unit=str(self.params["unit"]), sample_rate=fs, processing_history=[history(self)])]


@register_block
class TimeVectorBlock(ConstantBlock):
    type_name = "time_vector"
    display_name = "Time Vector"
    description = "Create a signal whose values equal elapsed time."
    parameters = (
        ParameterSpec("sample_rate", "Sample rate (Hz)", "float", 100.0, 1e-9),
        ParameterSpec("duration", "Duration (s)", "float", 1.0, 1e-9),
        ParameterSpec("name", "Signal name", "text", "Time"),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        fs = float(self.params["sample_rate"])
        duration = float(self.params["duration"])
        samples = max(1, int(round(fs * duration)))
        time_values = np.arange(samples) / fs
        return [SignalData(time_values.copy(), time_values, name=str(self.params.get("name") or "Time"), unit="s", sample_rate=fs, processing_history=[history(self)])]


# ---------------------------------------------------------------------------
# Mathematical operations and custom formula
# ---------------------------------------------------------------------------


class MultiSignalMathBlock(ProcessingBlock):
    input_count = 4
    minimum_inputs = 2
    input_types = ("signal",) * 4
    output_types = ("signal",)
    operation_name: ClassVar[str] = "operation"
    requires_same_units: ClassVar[bool] = False
    unit_mode: ClassVar[str] = "first"
    real_only: ClassVar[bool] = False

    @abstractmethod
    def combine(self, arrays: list[np.ndarray]) -> np.ndarray:
        pass

    def result_unit(self, signals: list[SignalData]) -> str:
        if self.requires_same_units:
            require_matching_units(signals, self.display_name)
        if self.unit_mode == "multiply":
            # An unspecified factor makes the derived unit unknown; omitting that
            # factor and reporting only the known units would be scientifically
            # misleading.
            return "·".join(signal.unit for signal in signals) if all(signal.unit for signal in signals) else ""
        if self.unit_mode == "divide":
            if not all(signal.unit for signal in signals):
                return ""
            numerator = signals[0].unit
            denominator = "·".join(signal.unit for signal in signals[1:])
            return f"{numerator}/({denominator})"
        return signals[0].unit

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        signals = require_aligned(connected_signals(inputs, self.display_name), self.display_name)
        if self.real_only and any(np.iscomplexobj(signal.values) for signal in signals):
            raise BlockError(f"{self.display_name} requires real-valued signals.")
        arrays = [signal.values for signal in signals]
        with np.errstate(all="ignore"):
            result = np.asarray(self.combine(arrays))
        finite_inputs = np.logical_and.reduce([np.isfinite(array) for array in arrays])
        if np.any(finite_inputs & ~np.isfinite(result)):
            raise BlockError(f"{self.display_name} produced NaN or infinity from finite inputs. Check domains and zero denominators.")
        return [signals[0].with_values(result, unit=self.result_unit(signals), history_entry=history(self, inputs=len(signals)), name=f"{self.display_name} result")]


def _divide_arrays(arrays: list[np.ndarray]) -> np.ndarray:
    for denominator in arrays[1:]:
        if np.any(np.asarray(denominator) == 0):
            raise BlockError("Divide encountered a zero denominator.")
    return np.divide.reduce(np.stack(arrays), axis=0)


def _register_multi_math(
    type_name: str,
    display_name: str,
    combiner: Callable[[list[np.ndarray]], np.ndarray],
    *,
    requires_same_units: bool = False,
    unit_mode: str = "first",
    real_only: bool = False,
) -> None:
    cls = type(
        display_name.replace(" ", "") + "Block",
        (MultiSignalMathBlock,),
        {
            "type_name": type_name,
            "display_name": display_name,
            "category": "Mathematics",
            "description": f"{display_name} two to four explicitly aligned signals.",
            "combine": lambda self, arrays: combiner(arrays),
            "requires_same_units": requires_same_units,
            "unit_mode": unit_mode,
            "real_only": real_only,
        },
    )
    register_block(cls)


_register_multi_math("add", "Add", lambda a: np.sum(np.stack(a), axis=0), requires_same_units=True)
_register_multi_math("subtract", "Subtract", lambda a: a[0] - np.sum(np.stack(a[1:]), axis=0), requires_same_units=True)
_register_multi_math("multiply", "Multiply", lambda a: np.prod(np.stack(a), axis=0), unit_mode="multiply")
_register_multi_math("divide", "Divide", _divide_arrays, unit_mode="divide")
_register_multi_math("minimum", "Minimum", lambda a: np.min(np.stack(a), axis=0), requires_same_units=True, real_only=True)
_register_multi_math("maximum", "Maximum", lambda a: np.max(np.stack(a), axis=0), requires_same_units=True, real_only=True)


class UnaryMathBlock(ProcessingBlock):
    category = "Mathematics"
    input_types = ("signal",)
    output_types = ("signal",)
    operation: ClassVar[Callable[[np.ndarray], np.ndarray]]
    input_must_be_dimensionless: ClassVar[bool] = False
    output_unit_mode: ClassVar[str] = "preserve"

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        if self.input_must_be_dimensionless and source.unit:
            raise BlockError(f"{self.display_name} requires a dimensionless input; received unit '{source.unit}'.")
        with np.errstate(all="ignore"):
            values = np.asarray(self.operation(source.values))
        if np.any(np.isfinite(source.values) & ~np.isfinite(values)):
            raise BlockError(f"{self.display_name} is undefined for one or more finite input samples.")
        if self.output_unit_mode == "dimensionless":
            unit = ""
        elif self.output_unit_mode == "square_root":
            unit = f"sqrt({source.unit})" if source.unit else ""
        else:
            unit = source.unit
        return [source.with_values(values, unit=unit, history_entry=history(self), name=f"{source.name} ({self.display_name.lower()})")]


def _register_unary(
    type_name: str,
    display_name: str,
    function: Callable[[np.ndarray], np.ndarray],
    *,
    input_must_be_dimensionless: bool = False,
    output_unit_mode: str = "preserve",
) -> None:
    cls = type(
        display_name.replace(" ", "").replace("-", "") + "Block",
        (UnaryMathBlock,),
        {
            "type_name": type_name,
            "display_name": display_name,
            "description": f"Apply {display_name.lower()} sample-by-sample.",
            "operation": staticmethod(function),
            "input_must_be_dimensionless": input_must_be_dimensionless,
            "output_unit_mode": output_unit_mode,
        },
    )
    register_block(cls)


_register_unary("absolute", "Absolute Value", np.abs)
_register_unary("negate", "Negate", np.negative)
_register_unary("square_root", "Square Root", np.sqrt, output_unit_mode="square_root")
_register_unary("logarithm", "Logarithm", np.log, input_must_be_dimensionless=True, output_unit_mode="dimensionless")
_register_unary("exponential", "Exponential", np.exp, input_must_be_dimensionless=True, output_unit_mode="dimensionless")


@register_block
class GainBlock(ProcessingBlock):
    type_name = "gain"
    display_name = "Gain"
    category = "Mathematics"
    description = "Multiply every sample by a constant gain."
    input_types = ("signal",)
    output_types = ("signal",)
    parameters = (ParameterSpec("gain", "Gain", "float", 1.0),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        gain = float(self.params["gain"])
        return [source.with_values(source.values * gain, history_entry=history(self, gain=gain))]


@register_block
class OffsetBlock(GainBlock):
    type_name = "offset"
    display_name = "Offset"
    description = "Add a constant offset to every sample."
    parameters = (ParameterSpec("offset", "Offset", "float", 0.0),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        offset = float(self.params["offset"])
        return [source.with_values(source.values + offset, history_entry=history(self, offset=offset))]


@register_block
class PowerBlock(GainBlock):
    type_name = "power"
    display_name = "Power"
    description = "Raise each sample to a configurable power."
    parameters = (ParameterSpec("exponent", "Exponent", "float", 2.0),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        exponent = float(self.params["exponent"])
        with np.errstate(all="ignore"):
            values = np.power(source.values, exponent)
        if np.any(np.isfinite(source.values) & ~np.isfinite(values)):
            raise BlockError("Power produced NaN or infinity. Check negative bases, fractional exponents and overflow.")
        return [source.with_values(values, unit=power_unit(source.unit, exponent), history_entry=history(self, exponent=exponent))]


@register_block
class ClampBlock(GainBlock):
    type_name = "clamp"
    display_name = "Clamp"
    description = "Limit values to a lower and upper bound."
    parameters = (ParameterSpec("minimum", "Minimum", "float", -1.0), ParameterSpec("maximum", "Maximum", "float", 1.0))

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        if np.iscomplexobj(source.values):
            raise BlockError("Clamp requires a real-valued signal.")
        lower, upper = float(self.params["minimum"]), float(self.params["maximum"])
        if lower > upper:
            raise BlockError("Minimum cannot exceed maximum.")
        return [source.with_values(np.clip(source.values, lower, upper), history_entry=history(self, minimum=lower, maximum=upper))]


@register_block
class NormaliseBlock(GainBlock):
    type_name = "normalise"
    display_name = "Normalise"
    description = "Scale a signal into a configurable range."
    parameters = (ParameterSpec("output_min", "Output minimum", "float", 0.0), ParameterSpec("output_max", "Output maximum", "float", 1.0))

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        values_in = finite_real_values(source, self.display_name)
        low, high = float(self.params["output_min"]), float(self.params["output_max"])
        if low >= high:
            raise BlockError("Output minimum must be less than output maximum.")
        source_low, source_high = np.min(values_in), np.max(values_in)
        if source_high == source_low:
            raise BlockError("A constant signal cannot be normalised.")
        values = (values_in - source_low) / (source_high - source_low) * (high - low) + low
        return [source.with_values(values, unit="", history_entry=history(self, output_min=low, output_max=high))]


@register_block
class StandardiseBlock(GainBlock):
    type_name = "standardise"
    display_name = "Standardise"
    description = "Convert samples to zero-mean unit-standard-deviation z-scores."
    parameters = ()

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        values_in = finite_values(source, self.display_name)
        standard_deviation = np.std(values_in)
        if standard_deviation == 0:
            raise BlockError("A constant signal cannot be standardised.")
        return [source.with_values((values_in - np.mean(values_in)) / standard_deviation, history_entry=history(self), unit="")]


@register_block
class CustomFormulaBlock(ProcessingBlock):
    type_name = "custom_formula"
    display_name = "Custom Formula"
    category = "Custom Processing"
    description = "Evaluate a validated NumPy-style expression using up to four named inputs."
    input_count = 4
    minimum_inputs = 1
    input_types = ("signal",) * 4
    output_types = ("signal",)
    parameters = (
        ParameterSpec("formula", "Formula", "multiline", "output = input_1"),
        ParameterSpec("output_name", "Output name", "text", "Formula result"),
        ParameterSpec("output_unit", "Output unit; blank = first input unit", "text", ""),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        signals = require_aligned(connected_signals(inputs, self.display_name), self.display_name)
        variables: dict[str, Any] = {}
        signal_index = 0
        for port_index, value in enumerate(inputs, start=1):
            if value is not None:
                variables[f"input_{port_index}"] = require_signal(value, self.display_name).values
                signal_index += 1
        try:
            output = evaluate_expression(str(self.params["formula"]), variables)
        except UnsafeExpression as exc:
            raise BlockError(str(exc)) from exc
        output_array = np.asarray(output)
        if output_array.ndim == 0:
            output_array = np.full(signals[0].samples, output_array.item())
        if output_array.ndim != 1 or len(output_array) != signals[0].samples:
            raise BlockError("Formula output must be a scalar or a one-dimensional array matching the input length.")
        output_unit = str(self.params.get("output_unit", "")) or signals[0].unit
        return [signals[0].with_values(
            output_array,
            unit=output_unit,
            history_entry=history(self, formula=str(self.params["formula"]), output_unit=output_unit),
            name=str(self.params["output_name"]),
        )]


@register_block
class PythonScriptBlock(CustomFormulaBlock):
    type_name = "python_script"
    display_name = "Restricted Python Expression"
    description = "Advanced expression block using the same isolated safe evaluator; arbitrary Python execution is never exposed."
    parameters = CustomFormulaBlock.parameters + (ParameterSpec("acknowledge_restrictions", "Acknowledge restricted environment", "bool", False),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        if not bool(self.params.get("acknowledge_restrictions", False)):
            raise BlockError("Enable 'Acknowledge restricted environment' before using this advanced block.")
        return super().execute(inputs)


# ---------------------------------------------------------------------------
# Conditioning
# ---------------------------------------------------------------------------


class ConditioningBlock(ProcessingBlock):
    category = "Signal Conditioning"
    input_types = ("signal",)
    output_types = ("signal",)


@register_block
class RemoveDCBlock(ConditioningBlock):
    type_name = "remove_dc"
    display_name = "Remove DC Offset"
    description = "Subtract the signal mean."

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        values = finite_values(source, self.display_name)
        return [source.with_values(values - np.mean(values), history_entry=history(self))]


@register_block
class DetrendBlock(ConditioningBlock):
    type_name = "detrend"
    display_name = "Detrend"
    description = "Remove a constant or linear trend."
    parameters = (ParameterSpec("mode", "Trend type", "choice", "linear", choices=("linear", "constant")),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        values = scipy_signal.detrend(finite_values(source, self.display_name), type=str(self.params["mode"]))
        return [source.with_values(values, history_entry=history(self, mode=self.params["mode"]))]


@register_block
class BaselineCorrectionBlock(ConditioningBlock):
    type_name = "baseline_correction"
    display_name = "Baseline Correction"
    description = "Subtract the median or the mean of an initial baseline interval."
    parameters = (
        ParameterSpec("baseline_seconds", "Baseline duration (s)", "float", 0.5, 0.0),
        ParameterSpec("method", "Baseline statistic", "choice", "median", choices=("median", "mean")),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        if np.iscomplexobj(source.values):
            raise BlockError("Baseline Correction requires a real-valued signal.")
        end_time = source.time[0] + float(self.params["baseline_seconds"])
        mask = source.time <= end_time
        if not np.any(mask):
            raise BlockError("The baseline interval contains no samples.")
        baseline = np.nanmedian(source.values[mask]) if self.params["method"] == "median" else np.nanmean(source.values[mask])
        if not np.isfinite(baseline):
            raise BlockError("The baseline interval contains no finite samples.")
        return [source.with_values(source.values - baseline, history_entry=history(self, baseline=float(baseline)))]


@register_block
class ScalingBlock(ConditioningBlock):
    type_name = "scaling"
    display_name = "Scaling"
    description = "Apply y = scale × x + offset and optionally change units."
    parameters = (
        ParameterSpec("scale", "Scale", "float", 1.0),
        ParameterSpec("offset", "Offset", "float", 0.0),
        ParameterSpec("output_unit", "Output unit", "text", ""),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        scale, offset = float(self.params["scale"]), float(self.params["offset"])
        unit = str(self.params.get("output_unit") or source.unit)
        return [source.with_values(source.values * scale + offset, unit=unit, history_entry=history(self, scale=scale, offset=offset, unit=unit))]


@register_block
class UnitConversionBlock(ScalingBlock):
    type_name = "unit_conversion"
    display_name = "Unit Conversion"
    description = "Convert common SI/engineering units automatically or apply an explicit scale and offset."
    parameters = (
        ParameterSpec("automatic", "Use built-in unit conversion", "bool", False),
        ParameterSpec("source_unit", "Source unit; blank = signal metadata", "text", "", visible_when=(("automatic", (True,)),)),
        ParameterSpec("target_unit", "Target unit", "text", "", visible_when=(("automatic", (True,)),)),
        ParameterSpec("scale", "Manual scale", "float", 1.0, advanced=True, visible_when=(("automatic", (False,)),)),
        ParameterSpec("offset", "Manual offset", "float", 0.0, advanced=True, visible_when=(("automatic", (False,)),)),
        ParameterSpec("output_unit", "Manual output unit", "text", "", advanced=True, visible_when=(("automatic", (False,)),)),
    )

    # Unit definition: dimension, multiplier to base unit, additive offset to base.
    _UNITS: ClassVar[dict[str, tuple[str, float, float]]] = {
        "V": ("voltage", 1.0, 0.0), "mV": ("voltage", 1e-3, 0.0), "uV": ("voltage", 1e-6, 0.0), "µV": ("voltage", 1e-6, 0.0), "kV": ("voltage", 1e3, 0.0),
        "A": ("current", 1.0, 0.0), "mA": ("current", 1e-3, 0.0), "uA": ("current", 1e-6, 0.0), "µA": ("current", 1e-6, 0.0), "kA": ("current", 1e3, 0.0),
        "m": ("length", 1.0, 0.0), "cm": ("length", 1e-2, 0.0), "mm": ("length", 1e-3, 0.0), "um": ("length", 1e-6, 0.0), "µm": ("length", 1e-6, 0.0), "km": ("length", 1e3, 0.0),
        "s": ("time", 1.0, 0.0), "ms": ("time", 1e-3, 0.0), "us": ("time", 1e-6, 0.0), "µs": ("time", 1e-6, 0.0), "ns": ("time", 1e-9, 0.0), "min": ("time", 60.0, 0.0), "h": ("time", 3600.0, 0.0),
        "Hz": ("frequency", 1.0, 0.0), "kHz": ("frequency", 1e3, 0.0), "MHz": ("frequency", 1e6, 0.0), "GHz": ("frequency", 1e9, 0.0),
        "N": ("force", 1.0, 0.0), "mN": ("force", 1e-3, 0.0), "kN": ("force", 1e3, 0.0),
        "Pa": ("pressure", 1.0, 0.0), "kPa": ("pressure", 1e3, 0.0), "MPa": ("pressure", 1e6, 0.0), "bar": ("pressure", 1e5, 0.0),
        "W": ("power", 1.0, 0.0), "mW": ("power", 1e-3, 0.0), "kW": ("power", 1e3, 0.0),
        "J": ("energy", 1.0, 0.0), "mJ": ("energy", 1e-3, 0.0), "kJ": ("energy", 1e3, 0.0),
        "rad": ("angle", 1.0, 0.0), "deg": ("angle", np.pi / 180.0, 0.0), "°": ("angle", np.pi / 180.0, 0.0),
        "m/s^2": ("acceleration", 1.0, 0.0), "m/s²": ("acceleration", 1.0, 0.0), "g": ("acceleration", 9.80665, 0.0),
        "K": ("temperature", 1.0, 0.0), "C": ("temperature", 1.0, 273.15), "°C": ("temperature", 1.0, 273.15), "F": ("temperature", 5.0 / 9.0, 255.3722222222222), "°F": ("temperature", 5.0 / 9.0, 255.3722222222222),
    }

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        if not bool(self.params.get("automatic", False)):
            scale, offset = float(self.params["scale"]), float(self.params["offset"]); unit = str(self.params.get("output_unit") or source.unit)
            return [source.with_values(source.values * scale + offset, unit=unit, history_entry=history(self, mode="manual", scale=scale, offset=offset, unit=unit))]
        source_unit = str(self.params.get("source_unit") or source.unit).strip(); target_unit = str(self.params.get("target_unit", "")).strip()
        if source_unit not in self._UNITS:
            raise BlockError(f"Unsupported source unit '{source_unit}'. Use manual conversion for custom units.")
        if target_unit not in self._UNITS:
            raise BlockError(f"Unsupported target unit '{target_unit}'. Use manual conversion for custom units.")
        source_dimension, source_scale, source_offset = self._UNITS[source_unit]; target_dimension, target_scale, target_offset = self._UNITS[target_unit]
        if source_dimension != target_dimension:
            raise BlockError(f"Cannot convert {source_unit} ({source_dimension}) to {target_unit} ({target_dimension}).")
        base_values = source.values * source_scale + source_offset
        converted = (base_values - target_offset) / target_scale
        return [source.with_values(converted, unit=target_unit, history_entry=history(self, mode="automatic", source_unit=source_unit, target_unit=target_unit))]


@register_block
class DeadbandBlock(ConditioningBlock):
    type_name = "deadband"
    display_name = "Deadband"
    description = "Set values inside a symmetric deadband to zero."
    parameters = (ParameterSpec("threshold", "Threshold", "float", 0.1, 0.0),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        threshold = float(self.params["threshold"])
        values = np.where(np.abs(source.values) < threshold, 0.0, source.values)
        return [source.with_values(values, history_entry=history(self, threshold=threshold))]


@register_block
class ThresholdBlock(ConditioningBlock):
    type_name = "threshold"
    display_name = "Thresholding"
    description = "Apply binary, zero-below or zero-above thresholding."
    parameters = (
        ParameterSpec("threshold", "Threshold", "float", 0.0),
        ParameterSpec("mode", "Mode", "choice", "binary", choices=("binary", "zero_below", "zero_above")),
        ParameterSpec("high_value", "Binary high value", "float", 1.0, visible_when=(("mode", ("binary",)),)),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        if np.iscomplexobj(source.values):
            raise BlockError("Thresholding requires a real-valued signal.")
        threshold = float(self.params["threshold"])
        mode = str(self.params["mode"])
        finite = np.isfinite(source.values)
        values = source.values.astype(float, copy=True)
        if mode == "binary":
            values[finite] = np.where(source.values[finite] >= threshold, float(self.params["high_value"]), 0.0)
        elif mode == "zero_below":
            values[finite] = np.where(source.values[finite] >= threshold, source.values[finite], 0.0)
        else:
            values[finite] = np.where(source.values[finite] <= threshold, source.values[finite], 0.0)
        unit = "" if mode == "binary" else source.unit
        return [source.with_values(values, unit=unit, history_entry=history(self, threshold=threshold, mode=mode))]


@register_block
class RectificationBlock(ConditioningBlock):
    type_name = "rectification"
    display_name = "Rectification"
    description = "Apply half-wave or full-wave rectification."
    parameters = (ParameterSpec("mode", "Mode", "choice", "full_wave", choices=("full_wave", "positive_half", "negative_half")),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        mode = str(self.params["mode"])
        if mode == "full_wave":
            values = np.abs(source.values)
        elif mode == "positive_half":
            if np.iscomplexobj(source.values):
                raise BlockError("Half-wave rectification requires a real-valued signal.")
            values = np.maximum(source.values, 0)
        else:
            if np.iscomplexobj(source.values):
                raise BlockError("Half-wave rectification requires a real-valued signal.")
            values = np.minimum(source.values, 0)
        return [source.with_values(values, history_entry=history(self, mode=mode))]


@register_block
class MovingAverageBlock(ConditioningBlock):
    type_name = "moving_average"
    display_name = "Moving Average"
    description = "Smooth a signal using a centred moving-average window."
    parameters = (ParameterSpec("window_samples", "Window samples", "int", 5, 1),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        window = int(self.params["window_samples"])
        if window > source.samples:
            raise BlockError("Window cannot exceed the signal length.")
        values_in = finite_values(source, self.display_name)
        left = (window - 1) // 2
        right = window // 2
        indexes = np.arange(source.samples)
        starts = np.maximum(0, indexes - left)
        ends = np.minimum(source.samples, indexes + right + 1)
        accumulator_dtype = np.result_type(values_in, float)
        cumulative = np.concatenate((
            np.zeros(1, dtype=accumulator_dtype),
            np.cumsum(values_in, dtype=accumulator_dtype),
        ))
        values = (cumulative[ends] - cumulative[starts]) / (ends - starts)
        return [source.with_values(values, history_entry=history(self, window_samples=window))]


@register_block
class ExponentialMovingAverageBlock(ConditioningBlock):
    type_name = "exponential_moving_average"
    display_name = "Exponential Moving Average"
    description = "Apply exponential smoothing."
    parameters = (ParameterSpec("alpha", "Alpha", "float", 0.2, 1e-9, 1.0),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        alpha = float(self.params["alpha"])
        values_in = finite_values(source, self.display_name)
        values = np.empty_like(values_in, dtype=np.result_type(values_in, float))
        values[0] = values_in[0]
        for index in range(1, source.samples):
            values[index] = alpha * values_in[index] + (1.0 - alpha) * values[index - 1]
        return [source.with_values(values, history_entry=history(self, alpha=alpha))]


@register_block
class MedianFilterBlock(ConditioningBlock):
    type_name = "median_filter"
    display_name = "Median Filter"
    description = "Suppress impulsive noise using a median filter."
    parameters = (
        ParameterSpec("kernel_size", "Kernel size (odd)", "int", 5, 1),
        ParameterSpec("edge_mode", "Edge handling", "choice", "nearest", choices=("nearest", "reflect", "mirror", "constant")),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        kernel = int(self.params["kernel_size"])
        if kernel % 2 == 0:
            raise BlockError("Median-filter kernel size must be odd.")
        if kernel > source.samples:
            raise BlockError("Median-filter kernel size cannot exceed the signal length.")
        from scipy import ndimage as scipy_ndimage
        values = scipy_ndimage.median_filter(finite_real_values(source, self.display_name), size=kernel, mode=str(self.params["edge_mode"]))
        return [source.with_values(values, history_entry=history(self, kernel_size=kernel, edge_mode=self.params["edge_mode"]))]


@register_block
class SavitzkyGolayBlock(ConditioningBlock):
    type_name = "savitzky_golay"
    display_name = "Savitzky–Golay Filter"
    description = "Smooth while preserving local polynomial features."
    parameters = (
        ParameterSpec("window_length", "Window length (odd)", "int", 11, 3),
        ParameterSpec("polynomial_order", "Polynomial order", "int", 3, 0),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        window, order = int(self.params["window_length"]), int(self.params["polynomial_order"])
        if window % 2 == 0 or order >= window:
            raise BlockError("Window length must be odd and greater than the polynomial order.")
        if window > source.samples:
            raise BlockError("Savitzky–Golay window length cannot exceed the signal length.")
        values = scipy_signal.savgol_filter(finite_real_values(source, self.display_name), window, order)
        return [source.with_values(values, history_entry=history(self, window=window, order=order))]


@register_block
class OutlierRemovalBlock(ConditioningBlock):
    type_name = "outlier_removal"
    display_name = "Outlier Removal"
    description = "Replace robust z-score outliers by interpolation."
    parameters = (ParameterSpec("threshold", "Modified z-score threshold", "float", 3.5, 0.1),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        finite_real_values(source, self.display_name)
        median = np.nanmedian(source.values)
        deviation = np.nanmedian(np.abs(source.values - median))
        if deviation == 0:
            return [source.with_values(source.values.copy(), history_entry=history(self, replaced=0))]
        score = 0.6745 * (source.values - median) / deviation
        values = source.values.astype(float, copy=True)
        mask = np.abs(score) > float(self.params["threshold"])
        values[mask] = np.nan
        values = pd.Series(values, index=source.time).interpolate(method="index", limit_direction="both").to_numpy()
        return [source.with_values(values, history_entry=history(self, replaced=int(mask.sum())))]


@register_block
class MissingValueInterpolationBlock(ConditioningBlock):
    type_name = "missing_value_interpolation"
    display_name = "Missing-Value Interpolation"
    description = "Interpolate NaN samples using a selected method."
    parameters = (
        ParameterSpec("method", "Method", "choice", "linear", choices=("linear", "nearest", "cubic", "spline")),
        ParameterSpec("spline_order", "Spline order", "int", 3, 1, 5, visible_when=(("method", ("spline",)),)),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        if np.count_nonzero(np.isfinite(source.values)) == 0:
            raise BlockError("Missing-Value Interpolation requires at least one finite sample.")
        series = pd.Series(source.values, index=source.time)
        method = str(self.params["method"])
        try:
            kwargs: dict[str, Any] = {"method": method, "limit_direction": "both"}
            if method == "spline":
                kwargs["order"] = int(self.params["spline_order"])
            values = series.interpolate(**kwargs).to_numpy()
        except (ValueError, ImportError) as exc:
            raise BlockError(f"Interpolation method '{method}' failed: {exc}") from exc
        if np.any(~np.isfinite(values)):
            raise BlockError(
                f"Interpolation method '{method}' could not fill all missing values. "
                "Try linear interpolation or provide more valid samples."
            )
        return [source.with_values(values, history_entry=history(self, method=method))]


# aliases demanded by the specification and useful for search
for alias_name, alias_display, base, category in (
    ("mean_subtraction", "Mean Subtraction", RemoveDCBlock, "Signal Conditioning"),
    ("signal_centring", "Signal Centring", RemoveDCBlock, "Signal Conditioning"),
    ("smoothing", "Smoothing", MovingAverageBlock, "Signal Conditioning"),
    ("clipping", "Clipping", ClampBlock, "Signal Conditioning"),
):
    register_block(type(
        alias_display.replace(" ", "") + "Block",
        (base,),
        {"type_name": alias_name, "display_name": alias_display, "category": category},
    ))


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------


def _digital_filter_parameters(kind: str, family: str, *, configurable: bool) -> tuple[ParameterSpec, ...]:
    """Build a mode- and family-correct digital-filter parameter schema."""

    if family == "cheby2":
        single_edge_label = "Stopband edge frequency (Hz)"
        lower_edge_label = "Lower stopband edge frequency (Hz)"
        upper_edge_label = "Upper stopband edge frequency (Hz)"
    elif family in {"cheby1", "ellip"}:
        single_edge_label = "Passband edge frequency (Hz)"
        lower_edge_label = "Lower passband edge frequency (Hz)"
        upper_edge_label = "Upper passband edge frequency (Hz)"
    else:
        single_edge_label = "Cutoff frequency (Hz)"
        lower_edge_label = "Lower cutoff frequency (Hz)"
        upper_edge_label = "Upper cutoff frequency (Hz)"
    edge_help = (
        "This is the single-pass prototype edge. When Zero phase is enabled, "
        "forward-backward filtering squares the magnitude response; use the response preview to inspect the effective edge."
    )

    specs: list[ParameterSpec] = []
    if configurable:
        specs.append(ParameterSpec(
            "mode", "Filter mode", "choice", "lowpass",
            choices=("lowpass", "highpass", "bandpass", "bandstop"),
        ))
        specs.extend((
            ParameterSpec(
                "cutoff", single_edge_label, "float", 10.0, 1e-12,
                help_text=edge_help,
                visible_when=(("mode", ("lowpass", "highpass")),),
            ),
            ParameterSpec(
                "lower_cutoff", lower_edge_label, "float", 5.0, 1e-12,
                help_text=edge_help,
                visible_when=(("mode", ("bandpass", "bandstop")),),
            ),
            ParameterSpec(
                "upper_cutoff", upper_edge_label, "float", 20.0, 1e-12,
                help_text=edge_help,
                visible_when=(("mode", ("bandpass", "bandstop")),),
            ),
        ))
    elif kind in {"bandpass", "bandstop"}:
        specs.extend((
            ParameterSpec("lower_cutoff", lower_edge_label, "float", 5.0, 1e-12, help_text=edge_help),
            ParameterSpec("upper_cutoff", upper_edge_label, "float", 20.0, 1e-12, help_text=edge_help),
        ))
    else:
        specs.append(ParameterSpec("cutoff", single_edge_label, "float", 10.0, 1e-12, help_text=edge_help))

    specs.append(ParameterSpec("order", "Order", "int", 4, 1, 20))
    if family in {"cheby1", "ellip"}:
        specs.append(ParameterSpec("ripple", "Passband ripple (dB)", "float", 1.0, 0.01))
    if family in {"cheby2", "ellip"}:
        specs.append(ParameterSpec("attenuation", "Stopband attenuation (dB)", "float", 40.0, 1.0))
    specs.extend((
        ParameterSpec("zero_phase", "Zero phase", "bool", True),
        ParameterSpec(
            "initial_conditions", "Causal initial conditions", "choice", "zero",
            choices=("zero", "steady_state"), advanced=True,
            visible_when=(("zero_phase", (False,)),),
        ),
        ParameterSpec(
            "edge_padding", "Edge padding", "choice", "odd",
            choices=("odd", "even", "constant", "none"),
            visible_when=(("zero_phase", (True,)),),
        ),
    ))
    return tuple(specs)


class DigitalFilterBlock(ProcessingBlock):
    category = "Filters"
    input_types = ("signal",)
    output_types = ("signal",)
    filter_kind: ClassVar[str] = "lowpass"
    family: ClassVar[str] = "butter"
    parameters = _digital_filter_parameters("lowpass", "butter", configurable=False)

    def effective_filter_kind(self) -> str:
        return str(self.params.get("mode", "lowpass")) if self.filter_kind == "configurable" else self.filter_kind

    def design(self, sample_rate: float) -> np.ndarray:
        self.validate_parameters()
        if not math.isfinite(sample_rate) or sample_rate <= 0:
            raise BlockError("Sample rate must be greater than zero.")
        order = int(self.params["order"]); filter_kind = self.effective_filter_kind()
        if filter_kind in {"bandpass", "bandstop"}:
            lower, upper = float(self.params["lower_cutoff"]), float(self.params["upper_cutoff"])
            if not 0 < lower < upper < sample_rate / 2:
                raise BlockError(f"Cut-offs must satisfy 0 < lower < upper < Nyquist ({sample_rate / 2:g} Hz).")
            wn: float | tuple[float, float] = (lower, upper)
        else:
            cutoff = float(self.params["cutoff"])
            if not 0 < cutoff < sample_rate / 2:
                raise BlockError(f"Cut-off must be between 0 and Nyquist ({sample_rate / 2:g} Hz).")
            wn = cutoff
        kwargs: dict[str, Any] = {"N": order, "Wn": wn, "btype": filter_kind, "fs": sample_rate, "output": "sos"}
        if self.family == "butter":
            return scipy_signal.butter(**kwargs)
        if self.family == "cheby1":
            return scipy_signal.cheby1(rp=float(self.params["ripple"]), **kwargs)
        if self.family == "cheby2":
            return scipy_signal.cheby2(rs=float(self.params["attenuation"]), **kwargs)
        if self.family == "ellip":
            return scipy_signal.ellip(rp=float(self.params["ripple"]), rs=float(self.params["attenuation"]), **kwargs)
        if self.family == "bessel":
            return scipy_signal.bessel(norm="mag", **kwargs)
        raise BlockError(f"Unsupported filter family: {self.family}")

    def frequency_response(self, sample_rate: float, points: int = 2048) -> tuple[np.ndarray, np.ndarray]:
        sos = self.design(sample_rate)
        frequency, response = scipy_signal.sosfreqz(sos, worN=points, fs=sample_rate)
        return frequency, zero_phase_response(response, bool(self.params["zero_phase"]))

    def stability(self, sample_rate: float) -> tuple[bool, float]:
        sos = self.design(sample_rate)
        poles = np.concatenate([np.roots(section[3:]) for section in sos]) if len(sos) else np.asarray([])
        maximum = float(np.max(np.abs(poles))) if len(poles) else 0.0
        return maximum < 1.0, maximum

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        require_uniform(source, self.display_name)
        values = finite_values(source, self.display_name)
        sos = self.design(float(source.sample_rate))
        try:
            if bool(self.params["zero_phase"]):
                padtype = None if self.params["edge_padding"] == "none" else str(self.params["edge_padding"])
                output = scipy_signal.sosfiltfilt(sos, values, padtype=padtype)
            else:
                if str(self.params.get("initial_conditions", "zero")) == "steady_state":
                    initial = scipy_signal.sosfilt_zi(sos) * values[0]
                    output, _ = scipy_signal.sosfilt(sos, values, zi=initial)
                else:
                    output = scipy_signal.sosfilt(sos, values)
        except ValueError as exc:
            raise BlockError("Signal is too short for this zero-phase filter; reduce order or disable zero phase.") from exc
        return [source.with_values(output, history_entry=history(self, family=self.family, kind=self.effective_filter_kind(), parameters=self.serialise_params()), name=f"{source.name} ({self.display_name})")]


def _register_filter(type_name: str, display_name: str, kind: str, family: str = "butter", *, configurable: bool = False) -> None:
    parameters = _digital_filter_parameters(kind, family, configurable=configurable)
    register_block(type(
        display_name.replace(" ", "").replace("-", "") + "Block",
        (DigitalFilterBlock,),
        {
            "type_name": type_name,
            "display_name": display_name,
            "description": f"Apply a configurable {family} digital filter." if configurable else f"Apply a {family} {kind} digital filter.",
            "filter_kind": "configurable" if configurable else kind,
            "family": family,
            "parameters": parameters,
        },
    ))


_register_filter("low_pass", "Low-Pass Filter", "lowpass")
_register_filter("high_pass", "High-Pass Filter", "highpass")
_register_filter("band_pass", "Band-Pass Filter", "bandpass")
_register_filter("band_stop", "Band-Stop Filter", "bandstop")
for family, label in (("butter", "Butterworth"), ("cheby1", "Chebyshev Type I"), ("cheby2", "Chebyshev Type II"), ("ellip", "Elliptic"), ("bessel", "Bessel")):
    _register_filter(f"{family}_filter", f"{label} Filter", "configurable", family, configurable=True)


@register_block
class NotchFilterBlock(ProcessingBlock):
    type_name = "notch_filter"
    display_name = "Notch Filter"
    category = "Filters"
    description = "Remove a narrow frequency using a second-order IIR notch."
    input_types = ("signal",)
    output_types = ("signal",)
    parameters = (
        ParameterSpec("frequency", "Notch frequency (Hz)", "float", 50.0, 1e-12),
        ParameterSpec("quality_factor", "Quality factor", "float", 30.0, 0.1),
        ParameterSpec("zero_phase", "Zero phase", "bool", True),
    )

    def _coefficients(self, sample_rate: float) -> tuple[np.ndarray, np.ndarray]:
        self.validate_parameters()
        if not math.isfinite(sample_rate) or sample_rate <= 0:
            raise BlockError("Sample rate must be greater than zero.")
        frequency = float(self.params["frequency"])
        if not 0 < frequency < sample_rate / 2:
            raise BlockError(f"Notch frequency must be between 0 and Nyquist ({sample_rate / 2:g} Hz).")
        try:
            return scipy_signal.iirnotch(frequency, float(self.params["quality_factor"]), fs=sample_rate)
        except ValueError as exc:
            raise BlockError(f"Could not design the notch filter: {exc}") from exc

    def frequency_response(self, sample_rate: float, points: int = 2048) -> tuple[np.ndarray, np.ndarray]:
        b, a = self._coefficients(sample_rate)
        frequency, response = scipy_signal.freqz(b, a, worN=points, fs=sample_rate)
        return frequency, zero_phase_response(response, bool(self.params["zero_phase"]))

    def stability(self, sample_rate: float) -> tuple[bool, float]:
        _b, a = self._coefficients(sample_rate)
        maximum = float(np.max(np.abs(np.roots(a))))
        return maximum < 1.0, maximum

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        require_uniform(source, self.display_name)
        frequency = float(self.params["frequency"])
        b, a = self._coefficients(float(source.sample_rate))
        source_values = finite_values(source, self.display_name)
        try:
            values = scipy_signal.filtfilt(b, a, source_values) if bool(self.params["zero_phase"]) else scipy_signal.lfilter(b, a, source_values)
        except ValueError as exc:
            raise BlockError("Signal is too short for this zero-phase notch filter; disable zero phase or provide more samples.") from exc
        return [source.with_values(values, history_entry=history(self, frequency=frequency, quality_factor=self.params["quality_factor"]))]


@register_block
class FIRFilterBlock(ProcessingBlock):
    type_name = "fir_filter"
    display_name = "FIR Filter"
    category = "Filters"
    description = "Design and apply a windowed FIR low/high/band filter."
    input_types = ("signal",)
    output_types = ("signal",)
    parameters = (
        ParameterSpec("mode", "Mode", "choice", "lowpass", choices=("lowpass", "highpass", "bandpass", "bandstop")),
        ParameterSpec("cutoff", "Cutoff frequency (Hz)", "float", 10.0, 1e-12, visible_when=(("mode", ("lowpass", "highpass")),)),
        ParameterSpec("lower_cutoff", "Lower cutoff frequency (Hz)", "float", 5.0, 1e-12, visible_when=(("mode", ("bandpass", "bandstop")),)),
        ParameterSpec("upper_cutoff", "Upper cutoff frequency (Hz)", "float", 20.0, 1e-12, visible_when=(("mode", ("bandpass", "bandstop")),)),
        ParameterSpec("taps", "Number of taps", "int", 101, 3, 10001),
        ParameterSpec("window", "Window", "choice", "hamming", choices=("hamming", "hann", "blackman", "kaiser")),
        ParameterSpec("kaiser_beta", "Kaiser beta", "float", 8.6, 0.0, visible_when=(("window", ("kaiser",)),)),
        ParameterSpec("zero_phase", "Zero phase", "bool", True),
    )

    def design(self, sample_rate: float) -> np.ndarray:
        self.validate_parameters()
        if not math.isfinite(sample_rate) or sample_rate <= 0:
            raise BlockError("Sample rate must be greater than zero.")
        taps = int(self.params["taps"])
        mode = str(self.params["mode"])
        if taps % 2 == 0 and mode in {"highpass", "bandstop"}:
            raise BlockError("High-pass and band-stop FIR filters require an odd tap count because their passband includes Nyquist.")
        cutoff: float | list[float]
        if mode in {"bandpass", "bandstop"}:
            cutoff = [float(self.params["lower_cutoff"]), float(self.params["upper_cutoff"])]
            if not 0 < cutoff[0] < cutoff[1] < sample_rate / 2:
                raise BlockError("Band edges must satisfy 0 < lower < upper < Nyquist.")
        else:
            cutoff = float(self.params["cutoff"])
            if not 0 < cutoff < sample_rate / 2:
                raise BlockError("Cut-off must be below Nyquist.")
        pass_zero: bool | str = {"lowpass": "lowpass", "highpass": "highpass", "bandpass": "bandpass", "bandstop": "bandstop"}[mode]
        window: Any = ("kaiser", float(self.params["kaiser_beta"])) if self.params["window"] == "kaiser" else self.params["window"]
        try:
            return scipy_signal.firwin(taps, cutoff, pass_zero=pass_zero, fs=sample_rate, window=window)
        except ValueError as exc:
            raise BlockError(f"Could not design FIR filter: {exc}") from exc

    def frequency_response(self, sample_rate: float, points: int = 2048) -> tuple[np.ndarray, np.ndarray]:
        frequency, response = scipy_signal.freqz(self.design(sample_rate), worN=points, fs=sample_rate)
        return frequency, zero_phase_response(response, bool(self.params["zero_phase"]))

    def stability(self, sample_rate: float) -> tuple[bool, float]:
        self.design(sample_rate)
        return True, 0.0  # finite impulse response has no recursive poles

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        require_uniform(source, self.display_name)
        taps = self.design(float(source.sample_rate))
        source_values = finite_values(source, self.display_name)
        try:
            values = scipy_signal.filtfilt(taps, [1.0], source_values) if bool(self.params["zero_phase"]) else scipy_signal.lfilter(taps, [1.0], source_values)
        except ValueError as exc:
            raise BlockError("Signal is too short for this zero-phase FIR filter; reduce taps or disable zero phase.") from exc
        return [source.with_values(values, history_entry=history(self, parameters=self.serialise_params()))]


@register_block
class CustomCoefficientsBlock(ProcessingBlock):
    type_name = "custom_filter_coefficients"
    display_name = "Custom Filter Coefficients"
    category = "Filters"
    description = "Apply user-provided numerator b and denominator a coefficients."
    input_types = ("signal",)
    output_types = ("signal",)
    parameters = (
        ParameterSpec("b", "Numerator coefficients", "text", "1"),
        ParameterSpec("a", "Denominator coefficients", "text", "1"),
        ParameterSpec("zero_phase", "Zero phase", "bool", False),
    )

    @staticmethod
    def _parse(text: str) -> np.ndarray:
        try:
            values = np.asarray([float(item.strip()) for item in text.split(",") if item.strip()], dtype=float)
        except ValueError as exc:
            raise BlockError("Filter coefficients must be comma-separated numbers.") from exc
        if not len(values):
            raise BlockError("At least one coefficient is required.")
        if np.any(~np.isfinite(values)):
            raise BlockError("Filter coefficients must be finite numbers.")
        return values

    def frequency_response(self, sample_rate: float, points: int = 2048) -> tuple[np.ndarray, np.ndarray]:
        self.validate_parameters()
        if not math.isfinite(sample_rate) or sample_rate <= 0:
            raise BlockError("Sample rate must be finite and greater than zero.")
        b, a = self._parse(str(self.params["b"])), self._parse(str(self.params["a"]))
        if a[0] == 0:
            raise BlockError("The first denominator coefficient cannot be zero.")
        frequency, response = scipy_signal.freqz(b, a, worN=points, fs=sample_rate)
        return frequency, zero_phase_response(response, bool(self.params["zero_phase"]))

    def stability(self, sample_rate: float) -> tuple[bool, float]:
        del sample_rate
        self.validate_parameters()
        a = self._parse(str(self.params["a"]))
        if a[0] == 0:
            raise BlockError("The first denominator coefficient cannot be zero.")
        poles = np.roots(a) if len(a) > 1 else np.asarray([])
        maximum = float(np.max(np.abs(poles))) if len(poles) else 0.0
        return maximum < 1.0, maximum

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        b, a = self._parse(str(self.params["b"])), self._parse(str(self.params["a"]))
        if a[0] == 0:
            raise BlockError("The first denominator coefficient cannot be zero.")
        poles = np.roots(a) if len(a) > 1 else np.asarray([])
        if np.any(np.abs(poles) >= 1):
            raise BlockError("The supplied IIR coefficients are unstable (pole magnitude ≥ 1).")
        source_values = finite_values(source, self.display_name)
        zero_phase = bool(self.params["zero_phase"])
        try:
            if len(a) == 1 and len(b) == 1:
                # scipy.signal.filtfilt rejects a scalar transfer function even
                # though its forward-backward result is well defined.  Handle the
                # constant-gain/identity case explicitly.
                gain = float(b[0] / a[0])
                values = source_values * (gain * gain if zero_phase else gain)
            elif zero_phase:
                values = scipy_signal.filtfilt(b, a, source_values)
            else:
                values = scipy_signal.lfilter(b, a, source_values)
        except ValueError as exc:
            raise BlockError("Signal is too short for zero-phase filtering with these coefficients.") from exc
        return [source.with_values(values, history_entry=history(self, b=b.tolist(), a=a.tolist(), zero_phase=zero_phase))]


# ---------------------------------------------------------------------------
# Resampling and time processing
# ---------------------------------------------------------------------------


class TimeProcessingBlock(ProcessingBlock):
    category = "Resampling & Time"
    input_types = ("signal",)
    output_types = ("signal",)


@register_block
class ResampleBlock(TimeProcessingBlock):
    type_name = "resample"
    display_name = "Resample"
    description = "Resample to a new uniform sampling frequency using polyphase filtering."
    parameters = (ParameterSpec("target_rate", "Target sample rate (Hz)", "float", 100.0, 1e-9),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        require_uniform(source, self.display_name)
        target = float(self.params["target_rate"])
        from fractions import Fraction
        ratio = Fraction(target / float(source.sample_rate)).limit_denominator(10000)
        values = scipy_signal.resample_poly(finite_values(source, self.display_name), ratio.numerator, ratio.denominator)
        time_values = source.time[0] + np.arange(len(values)) / target
        return [source.with_values(values, time=time_values, sample_rate=target, history_entry=history(self, target_rate=target))]


@register_block
class DownsampleBlock(TimeProcessingBlock):
    type_name = "downsample"
    display_name = "Downsample"
    description = "Keep every Nth sample without anti-alias filtering."
    parameters = (ParameterSpec("factor", "Factor", "int", 2, 2),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        factor = int(self.params["factor"])
        fs = float(source.sample_rate) / factor if source.sample_rate and source.is_uniform else None
        return [source.with_values(source.values[::factor], time=source.time[::factor], sample_rate=fs, history_entry=history(self, factor=factor))]


@register_block
class UpsampleBlock(TimeProcessingBlock):
    type_name = "upsample"
    display_name = "Upsample"
    description = "Increase sampling rate using polyphase interpolation."
    parameters = (ParameterSpec("factor", "Factor", "int", 2, 2),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        require_uniform(source, self.display_name)
        factor = int(self.params["factor"])
        values = scipy_signal.resample_poly(finite_values(source, self.display_name), factor, 1)
        fs = float(source.sample_rate) * factor
        time_values = source.time[0] + np.arange(len(values)) / fs
        return [source.with_values(values, time=time_values, sample_rate=fs, history_entry=history(self, factor=factor))]


@register_block
class DecimateBlock(TimeProcessingBlock):
    type_name = "decimate"
    display_name = "Decimate"
    description = "Low-pass filter and reduce sample rate."
    parameters = (
        ParameterSpec("factor", "Factor", "int", 2, 2, 100),
        ParameterSpec("filter_type", "Filter type", "choice", "iir", choices=("iir", "fir")),
        ParameterSpec("zero_phase", "Zero phase", "bool", True),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        require_uniform(source, self.display_name)
        factor = int(self.params["factor"])
        try:
            values = scipy_signal.decimate(finite_values(source, self.display_name), factor, ftype=str(self.params["filter_type"]), zero_phase=bool(self.params["zero_phase"]))
        except ValueError as exc:
            raise BlockError("Signal is too short for the selected decimation settings.") from exc
        fs = float(source.sample_rate) / factor
        time_values = source.time[0] + np.arange(len(values)) / fs
        return [source.with_values(values, time=time_values, sample_rate=fs, history_entry=history(self, factor=factor))]


@register_block
class InterpolateBlock(TimeProcessingBlock):
    type_name = "interpolate"
    display_name = "Interpolate"
    description = "Interpolate a signal onto a configurable uniform time step."
    parameters = (ParameterSpec("time_step", "Time step (s)", "float", 0.01, 1e-12), ParameterSpec("method", "Method", "choice", "linear", choices=("linear", "nearest", "cubic")))

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        if source.samples < 2:
            raise BlockError("Interpolate requires at least two samples.")
        if np.any(~np.isfinite(source.values)):
            raise BlockError("Interpolate requires finite input values. Use Missing-Value Interpolation first.")
        step = float(self.params["time_step"])
        # Construct only points inside the source domain.  Using ``arange`` with
        # an expanded stop could add one sample beyond the final timestamp and
        # silently extrapolate/hold the endpoint.
        intervals = int(np.floor((source.time[-1] - source.time[0]) / step + 1e-12))
        new_time = source.time[0] + np.arange(intervals + 1, dtype=float) * step
        if self.params["method"] == "linear":
            values = np.interp(new_time, source.time, source.values)
        else:
            from scipy.interpolate import interp1d
            method = str(self.params["method"])
            minimum_samples = 4 if method == "cubic" else 2
            if source.samples < minimum_samples:
                raise BlockError(f"{method.title()} interpolation requires at least {minimum_samples} samples.")
            values = interp1d(source.time, source.values, kind=method, bounds_error=False, fill_value="extrapolate")(new_time)
        return [source.with_values(values, time=new_time, sample_rate=1.0 / step, history_entry=history(self, time_step=step, method=self.params["method"]))]


@register_block
class CropTimeBlock(TimeProcessingBlock):
    type_name = "crop_time"
    display_name = "Crop by Time"
    description = "Keep samples within an inclusive time interval."
    parameters = (ParameterSpec("start", "Start time (s)", "float", 0.0), ParameterSpec("end", "End time (s)", "float", 1.0))

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        start, end = float(self.params["start"]), float(self.params["end"])
        if start >= end:
            raise BlockError("Start time must be less than end time.")
        mask = (source.time >= start) & (source.time <= end)
        if not np.any(mask):
            raise BlockError("The crop interval contains no samples.")
        return [source.with_values(source.values[mask], time=source.time[mask], history_entry=history(self, start=start, end=end))]


@register_block
class CropSampleBlock(TimeProcessingBlock):
    type_name = "crop_sample"
    display_name = "Crop by Sample"
    description = "Keep samples in a zero-based half-open index interval."
    parameters = (ParameterSpec("start", "Start index", "int", 0, 0), ParameterSpec("end", "End index", "int", 100, 1))

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        start, end = int(self.params["start"]), min(int(self.params["end"]), source.samples)
        if start >= end:
            raise BlockError("Start index must be less than end index.")
        return [source.with_values(source.values[start:end], time=source.time[start:end], history_entry=history(self, start=start, end=end))]


@register_block
class ShiftTimeBlock(TimeProcessingBlock):
    type_name = "shift_time"
    display_name = "Shift in Time"
    description = "Move the time axis without changing sample values."
    parameters = (ParameterSpec("shift_seconds", "Shift (s)", "float", 0.0),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        shift = float(self.params["shift_seconds"])
        return [source.with_values(source.values.copy(), time=source.time + shift, history_entry=history(self, shift_seconds=shift))]


@register_block
class DelayBlock(TimeProcessingBlock):
    type_name = "delay"
    display_name = "Delay"
    description = "Delay sample values while preserving signal length."
    parameters = (ParameterSpec("samples", "Delay samples", "int", 1, 0), ParameterSpec("fill_value", "Fill value", "float", 0.0))

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        count = int(self.params["samples"])
        if count >= source.samples:
            raise BlockError("Delay must be shorter than the signal.")
        output = np.full(source.values.shape, float(self.params["fill_value"]), dtype=np.result_type(source.values, float))
        if count:
            output[count:] = source.values[:-count]
        else:
            output[:] = source.values
        return [source.with_values(output, history_entry=history(self, samples=count))]


class TwoSignalTimeBlock(ProcessingBlock):
    category = "Resampling & Time"
    input_count = 2
    input_types = ("signal", "signal")
    output_count = 2
    output_types = ("signal", "signal")


@register_block
class SynchroniseSignalsBlock(TwoSignalTimeBlock):
    type_name = "synchronise_signals"
    display_name = "Synchronise Signals"
    description = "Interpolate two signals onto their overlapping common time axis."
    parameters = (ParameterSpec("target_rate", "Target rate; 0 = highest input (Hz)", "float", 0.0, 0.0),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        first, second = require_signal(inputs[0], self.display_name), require_signal(inputs[1], self.display_name)
        start, end = max(first.time[0], second.time[0]), min(first.time[-1], second.time[-1])
        if start >= end:
            raise BlockError("Signals do not overlap in time.")
        target = float(self.params["target_rate"]) or max(first.sample_rate or 0, second.sample_rate or 0)
        if target <= 0:
            raise BlockError("A target rate is required when input sample rates are unknown.")
        intervals = int(np.floor((end - start) * target + 1e-12))
        time_values = start + np.arange(intervals + 1, dtype=float) / target
        outputs = []
        for signal in (first, second):
            outputs.append(signal.with_values(np.interp(time_values, signal.time, finite_values(signal, self.display_name)), time=time_values, sample_rate=target, history_entry=history(self, target_rate=target)))
        return outputs


@register_block
class AlignPeakBlock(TwoSignalTimeBlock):
    type_name = "align_peak"
    display_name = "Align by Peak"
    description = "Shift the second time axis so maximum absolute peaks coincide."

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        first, second = require_signal(inputs[0], self.display_name), require_signal(inputs[1], self.display_name)
        first_values = finite_values(first, self.display_name)
        second_values = finite_values(second, self.display_name)
        shift = first.time[int(np.argmax(np.abs(first_values)))] - second.time[int(np.argmax(np.abs(second_values)))]
        return [first, second.with_values(second.values.copy(), time=second.time + shift, history_entry=history(self, shift_seconds=float(shift)))]


@register_block
class AlignCrossCorrelationBlock(TwoSignalTimeBlock):
    type_name = "align_cross_correlation"
    display_name = "Align by Cross-Correlation"
    description = "Estimate lag by cross-correlation and shift the second signal."

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        first, second = require_aligned([require_signal(inputs[0], self.display_name), require_signal(inputs[1], self.display_name)], self.display_name)
        require_uniform(first, self.display_name)
        first_values = finite_values(first, self.display_name)
        second_values = finite_values(second, self.display_name)
        correlation = scipy_signal.correlate(first_values - np.mean(first_values), second_values - np.mean(second_values), mode="full", method="fft")
        lag = int(scipy_signal.correlation_lags(first.samples, second.samples, mode="full")[np.argmax(np.abs(correlation))])
        shift = lag / float(first.sample_rate)
        return [first, second.with_values(second.values.copy(), time=second.time + shift, history_entry=history(self, lag_samples=lag, shift_seconds=shift))]


@register_block
class MergeSignalsBlock(ProcessingBlock):
    type_name = "merge_signals"
    display_name = "Merge Signals"
    category = "Resampling & Time"
    description = "Combine up to four aligned signals into a table."
    input_count = 4
    minimum_inputs = 2
    input_types = ("signal",) * 4
    output_types = ("table",)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        signals = require_aligned(connected_signals(inputs, self.display_name), self.display_name)
        frame = signals_to_frame(signals)
        signal_columns = [str(column) for column in frame.columns if column != "time"]
        units = {column: signal.unit for column, signal in zip(signal_columns, signals, strict=True)}
        return [TableResult(frame, name="Merged signals", metadata={"units": units})]


@register_block
class SplitSignalBlock(ProcessingBlock):
    type_name = "split_signal"
    display_name = "Split Signal"
    category = "Resampling & Time"
    description = "Split a signal into up to four equal contiguous portions."
    output_count = 4
    output_types = ("signal",) * 4
    parameters = (ParameterSpec("parts", "Parts", "int", 2, 2, 4),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        parts = int(self.params["parts"])
        if parts > source.samples:
            raise BlockError("The number of parts cannot exceed the number of samples.")
        index_chunks = np.array_split(np.arange(source.samples), parts)
        outputs: list[Any] = [source.with_values(source.values[idx], time=source.time[idx], history_entry=history(self, part=i + 1, parts=parts), name=f"{source.name} part {i + 1}") for i, idx in enumerate(index_chunks) if len(idx)]
        while len(outputs) < 4:
            outputs.append(None)
        return outputs


@register_block
class ConcatenateBlock(ProcessingBlock):
    type_name = "concatenate"
    display_name = "Concatenate"
    category = "Resampling & Time"
    description = "Append two to four signals in sequence with a continuous generated time axis."
    input_count = 4
    minimum_inputs = 2
    input_types = ("signal",) * 4
    output_types = ("signal",)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        signals = connected_signals(inputs, self.display_name)
        rates = {round(float(s.sample_rate or 0), 9) for s in signals}
        if len(rates) != 1 or 0 in rates:
            raise BlockError("All concatenated signals must have the same known sample rate.")
        if len({s.unit for s in signals}) > 1:
            raise BlockError("Signals must use the same unit before concatenation.")
        fs = float(signals[0].sample_rate)
        values = np.concatenate([s.values for s in signals])
        time_values = signals[0].time[0] + np.arange(len(values)) / fs
        return [signals[0].with_values(values, time=time_values, history_entry=history(self, inputs=len(signals)), name="Concatenated signal")]


@register_block
class WindowingBlock(TimeProcessingBlock):
    type_name = "windowing"
    display_name = "Windowing"
    description = "Multiply a signal by a standard analysis window."
    parameters = (ParameterSpec("window", "Window", "choice", "hann", choices=("hann", "hamming", "blackman", "bartlett", "boxcar", "flattop")),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        window = scipy_signal.get_window(normalise_window(str(self.params["window"])), source.samples)
        return [source.with_values(source.values * window, history_entry=history(self, window=self.params["window"]))]


@register_block
class SegmentSignalBlock(TimeProcessingBlock):
    type_name = "segment_signal"
    display_name = "Segment Signal"
    description = "Create a table of fixed-length overlapping segments."
    output_types = ("table",)
    parameters = (ParameterSpec("segment_samples", "Segment length", "int", 256, 2), ParameterSpec("overlap_samples", "Overlap", "int", 128, 0))

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        length, overlap = int(self.params["segment_samples"]), int(self.params["overlap_samples"])
        if overlap >= length:
            raise BlockError("Overlap must be smaller than segment length.")
        starts = range(0, max(0, source.samples - length + 1), length - overlap)
        rows = []
        for segment_id, start in enumerate(starts):
            for local_index, value in enumerate(source.values[start:start + length]):
                rows.append((segment_id, local_index, source.time[start + local_index], value))
        if not rows:
            raise BlockError("Signal is shorter than the selected segment length.")
        return [TableResult(pd.DataFrame(rows, columns=["segment", "sample", "time", "value"]), name=f"{source.name} segments")]


@register_block
class TriggerExtractionBlock(TimeProcessingBlock):
    type_name = "trigger_extraction"
    display_name = "Trigger-Based Extraction"
    description = "Extract a window around the first threshold crossing."
    parameters = (
        ParameterSpec("threshold", "Threshold", "float", 0.0),
        ParameterSpec("edge", "Edge", "choice", "rising", choices=("rising", "falling")),
        ParameterSpec("pre_samples", "Pre-trigger samples", "int", 50, 0),
        ParameterSpec("post_samples", "Post-trigger samples", "int", 200, 1),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        source_values = finite_real_values(source, self.display_name)
        threshold = float(self.params["threshold"])
        if self.params["edge"] == "rising":
            crossing = np.flatnonzero((source_values[:-1] < threshold) & (source_values[1:] >= threshold)) + 1
        else:
            crossing = np.flatnonzero((source_values[:-1] > threshold) & (source_values[1:] <= threshold)) + 1
        if not len(crossing):
            raise BlockError("No matching threshold crossing was found.")
        trigger = int(crossing[0])
        start = max(0, trigger - int(self.params["pre_samples"]))
        # Include the trigger sample itself plus the requested number of samples
        # after it.  Earlier versions returned one fewer post-trigger sample.
        end = min(source.samples, trigger + int(self.params["post_samples"]) + 1)
        relative_time = source.time[start:end] - source.time[trigger]
        return [source.with_values(source.values[start:end], time=relative_time, history_entry=history(
            self,
            trigger_index=trigger,
            pre_samples=trigger - start,
            post_samples=end - trigger - 1,
        ))]


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


class ScalarAnalysisBlock(ProcessingBlock):
    category = "Analysis"
    input_types = ("signal",)
    output_types = ("scalar",)
    unit_mode: ClassVar[str] = "source"
    statistic: ClassVar[Callable[[np.ndarray], float | complex]]
    real_only: ClassVar[bool] = False

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        values = np.asarray(source.values)
        finite_mask = np.isfinite(values)
        if not np.any(finite_mask):
            raise BlockError(f"{self.display_name} cannot process a signal with no finite values.")
        if self.real_only and np.iscomplexobj(values):
            raise BlockError(f"{self.display_name} requires a real-valued signal.")
        values = values[finite_mask]
        with np.errstate(all="ignore"):
            raw = self.statistic(values)
        if not np.isscalar(raw) or not np.isfinite(raw):
            raise BlockError(f"{self.display_name} is undefined for this signal.")
        value: float | complex
        if np.iscomplexobj(raw) and not np.isclose(np.imag(raw), 0.0):
            value = complex(raw)
        else:
            value = float(np.real(raw))
        if self.unit_mode == "dimensionless":
            unit = ""
        elif self.unit_mode == "squared":
            unit = f"{source.unit}²" if source.unit else ""
        else:
            unit = source.unit
        return [ScalarResult(value, self.display_name, unit, metadata={"source": source.name})]


def _register_scalar(
    type_name: str,
    display_name: str,
    function: Callable[[np.ndarray], float | complex],
    unit_mode: str = "source",
    *,
    real_only: bool = False,
) -> None:
    register_block(type(
        display_name.replace(" ", "").replace("-", "") + "Block",
        (ScalarAnalysisBlock,),
        {
            "type_name": type_name,
            "display_name": display_name,
            "description": f"Compute {display_name.lower()}.",
            "statistic": staticmethod(function),
            "unit_mode": unit_mode,
            "real_only": real_only,
        },
    ))


_register_scalar("rms", "RMS", lambda x: np.sqrt(np.nanmean(np.abs(x) ** 2)))
_register_scalar("mean", "Mean", np.nanmean)
_register_scalar("median", "Median", np.nanmedian, real_only=True)
_register_scalar("minimum_value", "Minimum Value", np.nanmin, real_only=True)
_register_scalar("maximum_value", "Maximum Value", np.nanmax, real_only=True)
_register_scalar("standard_deviation", "Standard Deviation", np.nanstd)
_register_scalar("variance", "Variance", np.nanvar, "squared")
_register_scalar("peak_to_peak", "Peak-to-Peak", lambda x: np.nanmax(x) - np.nanmin(x), real_only=True)
_register_scalar("crest_factor", "Crest Factor", lambda x: np.nanmax(np.abs(x)) / np.sqrt(np.nanmean(np.abs(x) ** 2)), "dimensionless")
_register_scalar("kurtosis", "Kurtosis", lambda x: scipy_stats.kurtosis(x, nan_policy="omit"), "dimensionless", real_only=True)
_register_scalar("skewness", "Skewness", lambda x: scipy_stats.skew(x, nan_policy="omit"), "dimensionless", real_only=True)
_register_scalar("zero_crossing_rate", "Zero-Crossing Rate", lambda x: np.count_nonzero(np.diff(np.signbit(x))) / max(1, len(x) - 1), "dimensionless", real_only=True)


@register_block
class DescriptiveStatisticsBlock(ProcessingBlock):
    type_name = "descriptive_statistics"
    display_name = "Descriptive Statistics"
    category = "Analysis"
    description = "Calculate a comprehensive engineering statistics table."
    input_types = ("signal",)
    output_types = ("table",)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        values = np.asarray(source.values)
        if np.iscomplexobj(values):
            raise BlockError("Descriptive Statistics requires a real-valued signal. Analyse magnitude or phase explicitly.")
        if not np.any(np.isfinite(values)):
            raise BlockError("Descriptive Statistics cannot process a signal with no finite values.")
        finite = values[np.isfinite(values)]
        data = {
            "total_samples": source.samples,
            "finite_count": int(finite.size),
            "duration_s": source.duration,
            "sample_rate_hz": source.sample_rate,
            "mean": np.mean(finite),
            "median": np.median(finite),
            "minimum": np.min(finite),
            "maximum": np.max(finite),
            "peak_to_peak": np.max(finite) - np.min(finite),
            "rms": np.sqrt(np.mean(np.abs(finite) ** 2)),
            "std": np.std(finite),
            "variance": np.var(finite),
            "skewness": scipy_stats.skew(finite),
            "kurtosis": scipy_stats.kurtosis(finite),
            "nan_count": int(np.count_nonzero(np.isnan(values))),
            "infinite_count": int(np.count_nonzero(np.isinf(values))),
        }
        return [TableResult(pd.DataFrame({"metric": list(data), "value": list(data.values())}), name=f"{source.name} statistics", metadata={"unit": source.unit})]


@register_block
class PeakDetectionBlock(ProcessingBlock):
    type_name = "peak_detection"
    display_name = "Peak Detection"
    category = "Analysis"
    description = "Find peaks and expose a peak table plus a marker signal."
    input_types = ("signal",)
    output_count = 2
    output_types = ("table", "signal")
    parameters = (
        ParameterSpec("height", "Minimum height; blank uses none", "text", ""),
        ParameterSpec("distance_samples", "Minimum distance", "int", 1, 1),
        ParameterSpec("prominence", "Minimum prominence; blank uses none", "text", ""),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        values = finite_values(source, self.display_name)
        if np.iscomplexobj(values):
            raise BlockError("Peak Detection requires a real-valued signal.")
        kwargs: dict[str, Any] = {"distance": int(self.params["distance_samples"])}
        for key in ("height", "prominence"):
            raw = str(self.params[key]).strip()
            if raw:
                try:
                    kwargs[key] = float(raw)
                except ValueError as exc:
                    raise BlockError(f"{key.replace('_', ' ').title()} must be numeric or blank.") from exc
        indexes, properties = scipy_signal.find_peaks(values, **kwargs)
        frame = pd.DataFrame({"sample": indexes, "time": source.time[indexes], "amplitude": source.values[indexes]})
        for key, value in properties.items():
            if np.ndim(value) == 1 and len(value) == len(indexes):
                frame[key] = value
        markers = np.full(source.samples, np.nan)
        markers[indexes] = source.values[indexes]
        return [
            TableResult(frame, name=f"{source.name} peaks", metadata={"amplitude_unit": source.unit}),
            source.with_values(
                markers,
                history_entry=history(self, peaks=len(indexes)),
                name=f"{source.name} peak markers",
                attributes={"intentional_non_finite_markers": True},
            ),
        ]


@register_block
class EnvelopeDetectionBlock(ConditioningBlock):
    type_name = "envelope_detection"
    display_name = "Envelope Detection"
    category = "Analysis"
    description = "Compute the analytic-signal envelope using a Hilbert transform."

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        values = np.abs(scipy_signal.hilbert(finite_real_values(source, self.display_name)))
        return [source.with_values(values, history_entry=history(self), name=f"{source.name} envelope")]


@register_block
class NumericalDerivativeBlock(ConditioningBlock):
    type_name = "numerical_derivative"
    display_name = "Numerical Differentiation"
    category = "Analysis"
    description = "Differentiate with respect to the actual time vector."

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        if source.samples < 2:
            raise BlockError("Numerical Differentiation requires at least two samples.")
        values = finite_values(source, self.display_name)
        unit = f"{source.unit}/s" if source.unit else "1/s"
        return [source.with_values(np.gradient(values, source.time), unit=unit, history_entry=history(self), name=f"d({source.name})/dt")]


@register_block
class NumericalIntegrationBlock(ConditioningBlock):
    type_name = "numerical_integration"
    display_name = "Numerical Integration"
    category = "Analysis"
    description = "Cumulatively integrate with the trapezoidal rule."
    parameters = (ParameterSpec("initial", "Initial value", "float", 0.0),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        values = scipy_integrate.cumulative_trapezoid(finite_values(source, self.display_name), source.time, initial=float(self.params["initial"]))
        unit = f"{source.unit}·s" if source.unit else "s"
        return [source.with_values(values, unit=unit, history_entry=history(self), name=f"∫{source.name}dt")]


@register_block
class AutocorrelationBlock(ConditioningBlock):
    type_name = "autocorrelation"
    display_name = "Autocorrelation"
    category = "Analysis"
    description = "Compute normalised non-negative-lag autocorrelation."
    parameters = (ParameterSpec("max_lag_samples", "Maximum lag; 0 = full", "int", 0, 0),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        require_uniform(source, self.display_name)
        values = finite_values(source, self.display_name)
        centred = values - np.mean(values)
        energy = float(np.sum(np.abs(centred) ** 2))
        if energy <= np.finfo(float).eps:
            raise BlockError("Autocorrelation is undefined for a constant signal.")
        correlation = scipy_signal.correlate(centred, centred, mode="full", method="fft")[source.samples - 1:]
        correlation = correlation / correlation[0]
        count = min(int(self.params["max_lag_samples"]) or len(correlation), len(correlation))
        correlation = correlation[:count]
        fs = source.sample_rate or 1.0
        lag = np.arange(len(correlation)) / fs
        return [SignalData(correlation, lag, name=f"{source.name} autocorrelation", unit="", sample_rate=fs, processing_history=source.processing_history + [history(self)])]


@register_block
class CrossCorrelationBlock(TwoSignalTimeBlock):
    type_name = "cross_correlation"
    display_name = "Cross-Correlation"
    category = "Analysis"
    description = "Compute full normalised cross-correlation and the best lag."
    output_types = ("signal", "scalar")

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        first, second = require_aligned([require_signal(inputs[0], self.display_name), require_signal(inputs[1], self.display_name)], self.display_name)
        require_uniform(first, self.display_name)
        first_values = finite_values(first, self.display_name); second_values = finite_values(second, self.display_name)
        first_centred = first_values - np.mean(first_values); second_centred = second_values - np.mean(second_values)
        normaliser = float(np.linalg.norm(first_centred) * np.linalg.norm(second_centred))
        if normaliser <= np.finfo(float).eps:
            raise BlockError("Cross-Correlation is undefined when either signal is constant.")
        correlation = scipy_signal.correlate(first_centred, second_centred, mode="full", method="fft") / normaliser
        lags = scipy_signal.correlation_lags(first.samples, second.samples, mode="full")
        lag_seconds = lags / float(first.sample_rate)
        best = float(lag_seconds[np.argmax(np.abs(correlation))])
        return [SignalData(correlation, lag_seconds, name="Cross-correlation", unit="", sample_rate=first.sample_rate), ScalarResult(best, "Best lag", "s")]


class SpectrumAnalysisBlock(ProcessingBlock):
    category = "Analysis"
    input_types = ("signal",)
    output_types = ("spectrum",)


@register_block
class FFTBlock(SpectrumAnalysisBlock):
    type_name = "fft"
    display_name = "FFT"
    description = "Compute a single-sided FFT magnitude or complex spectrum."
    parameters = (
        ParameterSpec("window", "Window", "choice", "hann", choices=("boxcar", "hann", "hamming", "blackman", "flattop")),
        ParameterSpec("detrend", "Remove mean", "bool", True),
        ParameterSpec("output", "Output", "choice", "magnitude", choices=("magnitude", "power", "complex")),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        require_uniform(source, self.display_name)
        values = finite_values(source, self.display_name)
        if bool(self.params["detrend"]):
            values = values - np.mean(values)
        window = scipy_signal.get_window(normalise_window(str(self.params["window"])), source.samples)
        coherent_gain = np.sum(window)
        if np.isclose(coherent_gain, 0.0):
            raise BlockError("Selected FFT window has zero coherent gain.")
        mode = str(self.params["output"])
        if np.iscomplexobj(values):
            transformed = np.fft.fft(values * window)
            frequency = np.fft.fftfreq(source.samples, d=1.0 / float(source.sample_rate))
            order = np.argsort(frequency)
            frequency = frequency[order]
            complex_amplitude = transformed[order] / coherent_gain
            one_sided = False
        else:
            transformed = np.fft.rfft(values * window)
            # Interior real-signal bins represent both positive and negative
            # frequencies. DC and Nyquist occur only once.
            factor = np.ones(len(transformed), dtype=float)
            if source.samples % 2 == 0:
                if len(factor) > 2:
                    factor[1:-1] = 2.0
            elif len(factor) > 1:
                factor[1:] = 2.0
            complex_amplitude = transformed * factor / coherent_gain
            frequency = np.fft.rfftfreq(source.samples, d=1.0 / float(source.sample_rate))
            one_sided = True
        if mode == "magnitude":
            output = np.abs(complex_amplitude)
        elif mode == "power":
            # A per-bin mean-square spectrum is the density spectrum multiplied by
            # its bin width.  ``scaling="spectrum"`` uses coherent-gain
            # normalisation and therefore overstates total power for non-rectangular
            # windows (for example by 1.5x for Hann).  Density/bin-width
            # normalisation preserves integrated mean-square power for every
            # supported window.
            frequency, density = scipy_signal.periodogram(
                values,
                fs=float(source.sample_rate),
                window=normalise_window(str(self.params["window"])),
                detrend=False,
                return_onesided=not np.iscomplexobj(values),
                scaling="density",
            )
            if len(frequency) > 1:
                bin_width = float(abs(frequency[1] - frequency[0]))
            else:
                bin_width = float(source.sample_rate) / max(source.samples, 1)
            output = density * bin_width
            if np.iscomplexobj(values):
                order = np.argsort(frequency)
                frequency, output = frequency[order], output[order]
        else:
            output = complex_amplitude
        return [SpectrumData(
            frequency,
            output,
            name=f"{source.name} FFT",
            unit=source.unit if mode != "power" else (f"{source.unit}²" if source.unit else ""),
            scale=mode,
            metadata={"window": self.params["window"], "one_sided": one_sided, "normalisation": "amplitude" if mode != "power" else "mean-square power"},
        )]


@register_block
class PowerSpectralDensityBlock(SpectrumAnalysisBlock):
    type_name = "power_spectral_density"
    display_name = "Power Spectral Density"
    description = "Estimate PSD using Welch's method."
    parameters = (
        ParameterSpec("segment_length", "Segment length", "int", 256, 8),
        ParameterSpec("overlap_percent", "Overlap (%)", "float", 50.0, 0.0, 95.0),
        ParameterSpec("window", "Window", "choice", "hann", choices=("hann", "hamming", "blackman", "flattop")),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        require_uniform(source, self.display_name)
        values_in = finite_values(source, self.display_name)
        segment = min(int(self.params["segment_length"]), source.samples)
        overlap = int(segment * float(self.params["overlap_percent"]) / 100.0)
        one_sided = not np.iscomplexobj(values_in)
        frequency, values = scipy_signal.welch(
            values_in,
            fs=float(source.sample_rate),
            window=str(self.params["window"]),
            nperseg=segment,
            noverlap=overlap,
            return_onesided=one_sided,
        )
        if not one_sided:
            order = np.argsort(frequency)
            frequency, values = frequency[order], values[order]
        return [SpectrumData(frequency, values, name=f"{source.name} PSD", unit=f"{source.unit}²/Hz" if source.unit else "1/Hz", scale="power spectral density")]


@register_block
class ShortTimeFourierTransformBlock(ProcessingBlock):
    type_name = "short_time_fourier_transform"
    display_name = "Short-Time Fourier Transform"
    category = "Analysis"
    description = "Compute a complex STFT time-frequency matrix."
    input_types = ("signal",)
    output_types = ("spectrogram",)
    parameters = (
        ParameterSpec("fft_size", "FFT size", "int", 256, 8),
        ParameterSpec("overlap_percent", "Overlap (%)", "float", 50.0, 0.0, 95.0),
        ParameterSpec("window", "Window", "choice", "hann", choices=("hann", "hamming", "blackman", "flattop")),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        require_uniform(source, self.display_name)
        values = finite_values(source, self.display_name)
        size = min(int(self.params["fft_size"]), source.samples)
        overlap = int(size * float(self.params["overlap_percent"]) / 100.0)
        one_sided = not np.iscomplexobj(values)
        frequency, time_values, z = scipy_signal.stft(
            values,
            fs=float(source.sample_rate),
            window=str(self.params["window"]),
            nperseg=size,
            noverlap=overlap,
            return_onesided=one_sided,
            boundary=None,
            padded=False,
        )
        if not one_sided:
            order = np.argsort(frequency)
            frequency, z = frequency[order], z[order, :]
        return [SpectrogramData(frequency, time_values + source.time[0], z, name=f"{source.name} STFT", unit=source.unit, metadata={"complex": True, "one_sided": one_sided})]


@register_block
class SpectrogramBlock(ShortTimeFourierTransformBlock):
    type_name = "spectrogram"
    display_name = "Spectrogram"
    description = "Compute a magnitude or decibel spectrogram."
    parameters = ShortTimeFourierTransformBlock.parameters + (ParameterSpec("scale", "Scale", "choice", "decibel", choices=("magnitude", "power", "decibel")),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        result = super().execute(inputs)[0]
        assert isinstance(result, SpectrogramData)
        magnitude = np.abs(result.values)
        scale = str(self.params["scale"])
        if scale == "power":
            result.values = magnitude ** 2
            result.unit = f"{result.unit}²" if result.unit else ""
        elif scale == "decibel":
            result.values = 20 * np.log10(np.maximum(magnitude, np.finfo(float).tiny))
            result.metadata["reference_unit"] = result.unit
            result.unit = "dB"
        else:
            result.values = magnitude
        result.metadata["scale"] = scale
        return [result]


@register_block
class FrequencyBandEnergyBlock(ProcessingBlock):
    type_name = "frequency_band_energy"
    display_name = "Frequency-Band Energy"
    category = "Analysis"
    description = "Calculate signal energy or mean-square power in a selected frequency band."
    input_types = ("signal",)
    output_types = ("scalar",)
    parameters = (
        ParameterSpec("lower_frequency", "Lower frequency (Hz)", "float", 0.0),
        ParameterSpec("upper_frequency", "Upper frequency (Hz)", "float", 10.0),
        ParameterSpec("quantity", "Quantity", "choice", "energy", choices=("energy", "mean-square power")),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        require_uniform(source, self.display_name)
        values = finite_values(source, self.display_name)
        lower, upper = float(self.params["lower_frequency"]), float(self.params["upper_frequency"])
        if upper <= lower:
            raise BlockError("Upper frequency must be greater than lower frequency.")
        nyquist = float(source.sample_rate) / 2.0
        complex_input = bool(np.iscomplexobj(values))
        if complex_input:
            if lower < -nyquist or upper > nyquist:
                raise BlockError(f"For complex signals the frequency band must remain within ±Nyquist (±{nyquist:g} Hz).")
        elif lower < 0 or upper > nyquist:
            raise BlockError(f"For real signals the frequency band must remain between 0 and Nyquist ({nyquist:g} Hz).")

        frequency, density = scipy_signal.periodogram(
            values,
            fs=float(source.sample_rate),
            window="boxcar",
            detrend=False,
            return_onesided=not complex_input,
            scaling="density",
        )
        if complex_input:
            order = np.argsort(frequency)
            frequency, density = frequency[order], density[order]
        mask = (frequency >= lower) & (frequency <= upper)
        if not np.any(mask):
            resolution = float(source.sample_rate) / max(source.samples, 1)
            raise BlockError(f"Selected band contains no spectrum bins at the current {resolution:g} Hz resolution.")
        bin_width = float(source.sample_rate) / max(source.samples, 1)
        mean_square_power = float(np.sum(np.real(density[mask])) * bin_width)
        quantity = str(self.params["quantity"])
        if quantity == "energy":
            observation_time = source.samples / float(source.sample_rate)
            value = mean_square_power * observation_time
            unit = f"{source.unit}²·s" if source.unit else "s"
            name = f"Energy {lower:g}–{upper:g} Hz"
        else:
            value = mean_square_power
            unit = f"{source.unit}²" if source.unit else ""
            name = f"Mean-square power {lower:g}–{upper:g} Hz"
        return [ScalarResult(value, name, unit, metadata={"lower_frequency": lower, "upper_frequency": upper, "quantity": quantity})]


@register_block
class SignalToNoiseRatioBlock(TwoSignalTimeBlock):
    type_name = "signal_to_noise_ratio"
    display_name = "Signal-to-Noise Ratio"
    category = "Analysis"
    description = "Compute SNR between a reference signal and a noise signal."
    output_count = 1
    output_types = ("scalar",)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        reference, noise = require_aligned([require_signal(inputs[0], self.display_name), require_signal(inputs[1], self.display_name)], self.display_name)
        require_matching_units([reference, noise], self.display_name)
        reference_values = finite_values(reference, self.display_name)
        noise_values = finite_values(noise, self.display_name)
        signal_power = float(np.mean(np.abs(reference_values) ** 2))
        noise_power = float(np.mean(np.abs(noise_values) ** 2))
        if signal_power <= 0:
            raise BlockError("Reference-signal power must be greater than zero.")
        if noise_power <= 0:
            raise BlockError("Noise power must be greater than zero.")
        return [ScalarResult(float(10 * np.log10(signal_power / noise_power)), "Signal-to-Noise Ratio", "dB")]


@register_block
class LinearRegressionBlock(TwoSignalTimeBlock):
    type_name = "linear_regression"
    display_name = "Linear Regression"
    category = "Analysis"
    description = "Fit y against x and return a results table plus fitted signal."
    output_types = ("table", "signal")

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        x, y = require_aligned([require_signal(inputs[0], self.display_name), require_signal(inputs[1], self.display_name)], self.display_name)
        if np.iscomplexobj(x.values) or np.iscomplexobj(y.values):
            raise BlockError("Linear Regression requires real-valued signals.")
        valid = np.isfinite(x.values) & np.isfinite(y.values)
        if np.count_nonzero(valid) < 2:
            raise BlockError("Linear Regression requires at least two paired finite samples.")
        x_values = np.asarray(x.values[valid], dtype=float)
        y_values = np.asarray(y.values[valid], dtype=float)
        if np.allclose(x_values, x_values[0]):
            raise BlockError("Linear Regression requires variation in the x signal.")
        result = scipy_stats.linregress(x_values, y_values)
        slope_unit = f"{y.unit}/{x.unit}" if y.unit and x.unit else ""
        table = TableResult(
            pd.DataFrame({
                "metric": ["slope", "intercept", "r_value", "p_value", "standard_error", "paired_samples"],
                "value": [result.slope, result.intercept, result.rvalue, result.pvalue, result.stderr, int(np.count_nonzero(valid))],
                "unit": [slope_unit, y.unit, "", "", slope_unit, ""],
            }),
            name="Linear regression",
        )
        fitted_values = result.intercept + result.slope * np.asarray(x.values, dtype=float)
        fitted = y.with_values(fitted_values, history_entry=history(self, paired_samples=int(np.count_nonzero(valid))), name=f"{y.name} fitted")
        return [table, fitted]


@register_block
class HistogramBlock(ProcessingBlock):
    type_name = "histogram"
    display_name = "Histogram"
    category = "Analysis"
    description = "Calculate histogram bin counts and edges."
    input_types = ("signal",)
    output_types = ("table",)
    parameters = (ParameterSpec("bins", "Bins", "int", 50, 1, 100000), ParameterSpec("density", "Probability density", "bool", False))

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        source = require_signal(inputs[0], self.display_name)
        if np.iscomplexobj(source.values):
            raise BlockError("Histogram requires a real-valued signal.")
        finite = source.values[np.isfinite(source.values)]
        if finite.size == 0:
            raise BlockError("Histogram cannot process a signal with no finite values.")
        counts, edges = np.histogram(finite, bins=int(self.params["bins"]), density=bool(self.params["density"]))
        centres = (edges[:-1] + edges[1:]) / 2
        value_column = "density" if bool(self.params["density"]) else "count"
        metadata = {
            "bin_unit": source.unit,
            "value_unit": f"1/{source.unit}" if bool(self.params["density"]) and source.unit else "",
        }
        return [TableResult(
            pd.DataFrame({"bin_centre": centres, "lower_edge": edges[:-1], "upper_edge": edges[1:], value_column: counts}),
            name=f"{source.name} histogram",
            metadata=metadata,
        )]


# ---------------------------------------------------------------------------
# Display and export blocks
# ---------------------------------------------------------------------------


class DisplayBlock(ProcessingBlock):
    category = "Inputs & Outputs"
    cacheable = False


@register_block
class ScopeBlock(DisplayBlock):
    type_name = "scope"
    display_name = "Scope"
    description = "Display up to four time-domain signals with measurement cursors."
    input_count = 4
    minimum_inputs = 1
    output_count = 0
    input_types = ("signal",) * 4
    output_types = ()
    parameters = (
        ParameterSpec("title", "Title", "text", "Signal Scope"),
        ParameterSpec("max_display_points", "Maximum display points", "int", 100_000, 1_000),
        ParameterSpec("grid", "Show grid", "bool", True),
        ParameterSpec("legend", "Show legend", "bool", True),
        ParameterSpec("line_width", "Line width", "float", 1.5, 0.1, 10.0),
        ParameterSpec("line_style", "Line style", "choice", "solid", choices=("solid", "dash", "dot", "dash-dot")),
        ParameterSpec("show_markers", "Show sample markers", "bool", False),
        ParameterSpec("show_peaks", "Annotate prominent peaks", "bool", False),
        ParameterSpec("auto_scale", "Automatic axis scaling", "bool", True),
        ParameterSpec("x_min", "Manual X minimum; blank = auto", "text", "", advanced=True, visible_when=(("auto_scale", (False,)),)),
        ParameterSpec("x_max", "Manual X maximum; blank = auto", "text", "", advanced=True, visible_when=(("auto_scale", (False,)),)),
        ParameterSpec("y_min", "Manual Y minimum; blank = auto", "text", "", advanced=True, visible_when=(("auto_scale", (False,)),)),
        ParameterSpec("y_max", "Manual Y maximum; blank = auto", "text", "", advanced=True, visible_when=(("auto_scale", (False,)),)),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        connected_signals(inputs, self.display_name)
        if not bool(self.params["auto_scale"]):
            parsed: dict[str, float | None] = {}
            for name in ("x_min", "x_max", "y_min", "y_max"):
                raw = str(self.params.get(name, "")).strip()
                try:
                    parsed[name] = None if not raw else float(raw)
                except ValueError as exc:
                    raise BlockError(f"{name.replace('_', ' ').upper()} must be numeric or blank.") from exc
            if parsed["x_min"] is not None and parsed["x_max"] is not None and parsed["x_min"] >= parsed["x_max"]:
                raise BlockError("Manual X minimum must be less than X maximum.")
            if parsed["y_min"] is not None and parsed["y_max"] is not None and parsed["y_min"] >= parsed["y_max"]:
                raise BlockError("Manual Y minimum must be less than Y maximum.")
        return []


@register_block
class MultiSignalScopeBlock(ScopeBlock):
    type_name = "multi_signal_scope"
    display_name = "Multi-Signal Scope"
    description = "Alias of Scope emphasising multi-channel comparison."


@register_block
class SpectrumAnalyserBlock(DisplayBlock):
    type_name = "spectrum_analyser"
    display_name = "Spectrum Analyser"
    description = "Display a spectrum or automatically calculate FFT from a signal."
    input_count = 2
    minimum_inputs = 1
    input_types = ("signal", "spectrum")
    output_count = 0
    output_types = ()
    parameters = (
        ParameterSpec("title", "Title", "text", "Spectrum Analyser"),
        ParameterSpec("frequency_scale", "Frequency scale", "choice", "linear", choices=("linear", "logarithmic")),
        ParameterSpec("amplitude_scale", "Amplitude scale", "choice", "linear", choices=("linear", "decibel")),
        ParameterSpec("window", "Automatic FFT window", "choice", "hann", choices=("boxcar", "hann", "hamming", "blackman")),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        if inputs[0] is not None:
            require_signal(inputs[0], self.display_name)
        if inputs[1] is not None:
            require_spectrum(inputs[1], self.display_name)
        return []


@register_block
class DataTableBlock(DisplayBlock):
    type_name = "data_table"
    display_name = "Data Table"
    description = "Display signal samples or any tabular analysis result."
    input_types = ("any",)
    output_count = 0
    output_types = ()
    parameters = (ParameterSpec("maximum_rows", "Maximum displayed rows", "int", 10_000, 10),)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        if not isinstance(inputs[0], (SignalData, TableResult, ScalarResult)):
            raise BlockError("Data Table accepts a signal, scalar or table result.")
        return []


@register_block
class StatisticsDisplayBlock(DataTableBlock):
    type_name = "statistics_display"
    display_name = "Statistics Display"
    description = "Display scalar or descriptive-statistics results."


@register_block
class SpectrogramViewerBlock(DisplayBlock):
    type_name = "spectrogram_viewer"
    display_name = "Spectrogram Viewer"
    description = "Display a time-frequency matrix with configurable limits and colour scale."
    input_types = ("spectrogram",)
    output_count = 0
    output_types = ()
    parameters = (
        ParameterSpec("title", "Title", "text", "Spectrogram"),
        ParameterSpec("minimum_frequency", "Minimum frequency (Hz)", "float", 0.0, 0.0),
        ParameterSpec("maximum_frequency", "Maximum frequency; 0 = auto", "float", 0.0, 0.0),
        ParameterSpec("colour_map", "Colour map", "choice", "viridis", choices=("viridis", "plasma", "inferno", "magma", "cividis")),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        if not isinstance(inputs[0], SpectrogramData):
            raise BlockError("Spectrogram Viewer requires a Spectrogram result.")
        minimum = float(self.params["minimum_frequency"])
        maximum = float(self.params["maximum_frequency"])
        if maximum and maximum <= minimum:
            raise BlockError("Maximum frequency must exceed minimum frequency, or be 0 for automatic.")
        return []


@register_block
class ExportDataBlock(ProcessingBlock):
    type_name = "export_data"
    display_name = "Export Data"
    category = "Inputs & Outputs"
    description = "Export up to four signals or one table with metadata and processing history."
    input_count = 4
    minimum_inputs = 1
    input_types = ("any",) * 4
    output_count = 0
    output_types = ()
    cacheable = False
    parameters = (
        ParameterSpec("file_path", "Output file", "save_file", "", file_filter="CSV (*.csv);;TSV (*.tsv);;Excel (*.xlsx);;JSON (*.json);;NumPy (*.npy *.npz);;HDF5 (*.h5)"),
        ParameterSpec("include_metadata", "Write metadata sidecar", "bool", True),
        ParameterSpec("include_time", "Include time values", "bool", True),
        ParameterSpec("time_column_name", "Time column name", "text", "time"),
        ParameterSpec("time_representation", "Time representation", "choice", "seconds", choices=("seconds", "sample_index", "datetime_iso")),
        ParameterSpec("column_names", "Override signal column names (comma-separated)", "text", ""),
        ParameterSpec("units_in_headers", "Include units in column headers", "bool", False),
        ParameterSpec("precision", "Numeric precision", "int", 10, 1, 18),
        ParameterSpec("delimiter", "Delimiter", "text", ","),
        ParameterSpec("decimal", "Decimal separator", "text", "."),
        ParameterSpec("missing_value", "Missing-value representation", "text", ""),
        ParameterSpec("overwrite", "Overwrite policy", "choice", "replace", choices=("replace", "error", "increment")),
    )

    def _resolve_path(self) -> Path:
        raw = str(self.params.get("file_path", "")).strip()
        if not raw:
            raise BlockError("Choose an output file.")
        path = Path(raw).expanduser()
        if path.exists():
            policy = str(self.params["overwrite"])
            if policy == "error":
                raise BlockError(f"Output file already exists: {path}")
            if policy == "increment":
                index = 2
                candidate = path
                while candidate.exists():
                    candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
                    index += 1
                path = candidate
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _frame_contains_complex(frame: pd.DataFrame) -> bool:
        """Detect complex samples, including complex values stored in object columns."""

        for column in frame.columns:
            array = frame[column].to_numpy()
            if np.iscomplexobj(array):
                return True
            if array.dtype == object:
                for value in array:
                    if isinstance(value, (complex, np.complexfloating)):
                        return True
        return False

    def execute(self, inputs: list[Any]) -> list[Any]:
        if len(inputs) < self.input_count:
            inputs = list(inputs) + [None] * (self.input_count - len(inputs))
        self.validate(inputs)
        values = [value for value in inputs if value is not None]
        path = self._resolve_path()
        suffix = path.suffix.lower()
        precision = int(self.params["precision"])
        if suffix not in {".csv", ".tsv", ".xlsx", ".json", ".npy", ".npz", ".h5", ".hdf5"}:
            raise BlockError("Export extension must be .csv, .tsv, .xlsx, .json, .npy, .npz, .h5 or .hdf5.")
        delimiter = str(self.params["delimiter"])
        decimal = str(self.params["decimal"])
        if suffix == ".csv" and not delimiter:
            raise BlockError("CSV delimiter cannot be empty.")
        if len(decimal) != 1:
            raise BlockError("Decimal separator must be exactly one character.")
        metadata: dict[str, Any] = {"exported_utc": datetime.now(timezone.utc).isoformat(), "items": []}
        try:
            if len(values) == 1 and isinstance(values[0], TableResult):
                frame = values[0].frame.copy()
                metadata["items"].append({"type": "table", "name": values[0].name, **values[0].metadata})
            elif len(values) == 1 and isinstance(values[0], ScalarResult):
                frame = pd.DataFrame({"name": [values[0].name], "value": [values[0].value], "unit": [values[0].unit]})
                metadata["items"].append({"type": "scalar", "name": values[0].name})
            else:
                signals = [require_signal(value, self.display_name) for value in values]
                try:
                    frame = signals_to_frame(signals)
                except ValueError as exc:
                    raise BlockError(str(exc)) from exc
                time_name = str(self.params.get("time_column_name", "time")).strip() or "time"
                signal_names_before_export = [str(column) for column in frame.columns if column != "time"]
                if time_name in signal_names_before_export:
                    raise BlockError(f"Time column name '{time_name}' conflicts with an exported signal name.")
                frame = frame.rename(columns={"time": time_name})
                time_representation = str(self.params.get("time_representation", "seconds"))
                if time_representation == "sample_index":
                    frame[time_name] = np.arange(len(frame), dtype=np.int64)
                elif time_representation == "datetime_iso":
                    origin = signals[0].attributes.get("time_origin_utc")
                    if not origin:
                        raise BlockError("Datetime export requires an input imported from timestamp data.")
                    start = pd.Timestamp(origin)
                    frame[time_name] = (start + pd.to_timedelta(signals[0].time, unit="s")).astype(str)
                elif time_representation != "seconds":
                    raise BlockError(f"Unknown time representation: {time_representation}")
                if not bool(self.params.get("include_time", True)):
                    frame = frame.drop(columns=[time_name])
                overrides = ImportDataBlock._split_list(self.params.get("column_names"))
                signal_columns = [column for column in frame.columns if column != time_name]
                if overrides:
                    if len(overrides) != len(signal_columns):
                        raise BlockError("Column-name overrides must match the number of exported signals.")
                    if bool(self.params.get("include_time", True)) and time_name in overrides:
                        raise BlockError(f"Column-name override '{time_name}' conflicts with the time column name.")
                    if len(set(overrides)) != len(overrides):
                        raise BlockError("Column-name overrides must be unique.")
                    frame = frame.rename(columns=dict(zip(signal_columns, overrides, strict=True)))
                    signal_columns = overrides
                if bool(self.params.get("units_in_headers", False)):
                    renamed = {}
                    for column, signal in zip(signal_columns, signals, strict=True):
                        if signal.unit: renamed[column] = f"{column} [{signal.unit}]"
                    frame = frame.rename(columns=renamed)
                metadata["time_representation"] = time_representation
                metadata["items"] = [signal.to_metadata() for signal in signals]
                if len(signals) == 1:
                    metadata.update(signals[0].to_metadata())
            contains_complex = self._frame_contains_complex(frame)
            if contains_complex and suffix in {".csv", ".tsv", ".xlsx", ".json"}:
                raise BlockError(
                    "Complex-valued data must be exported as .npy, .npz or HDF5 to preserve real and imaginary components."
                )
            missing_value = str(self.params.get("missing_value", ""))
            if suffix == ".csv":
                frame.to_csv(path, index=False, sep=delimiter, decimal=decimal, float_format=f"%.{precision}g", na_rep=missing_value)
            elif suffix == ".tsv":
                frame.to_csv(path, index=False, sep="\t", decimal=decimal, float_format=f"%.{precision}g", na_rep=missing_value)
            elif suffix == ".xlsx":
                frame.to_excel(path, index=False, na_rep=missing_value)
            elif suffix == ".json":
                if missing_value:
                    frame.where(frame.notna(), missing_value).to_json(path, orient="records", indent=2)
                else:
                    frame.to_json(path, orient="records", indent=2)
            elif suffix == ".npy":
                array = frame.to_numpy()
                if array.dtype.hasobject:
                    raise BlockError(
                        "NPY export requires a homogeneous numeric table. Use NPZ or HDF5 for mixed text/numeric columns."
                    )
                np.save(path, array, allow_pickle=False)
            elif suffix == ".npz":
                arrays: dict[str, np.ndarray] = {}
                for column in frame.columns:
                    array = frame[column].to_numpy()
                    # NumPy object arrays require pickle and cannot be reopened by
                    # SignalDojo's safe allow_pickle=False importer. Encode mixed,
                    # text and extension-dtype columns as Unicode instead.
                    if array.dtype.hasobject:
                        array = frame[column].astype("string").fillna(missing_value).to_numpy(dtype=str)
                    arrays[str(column)] = array
                np.savez(path, **arrays)
            elif suffix in {".h5", ".hdf5"}:
                try:
                    frame.to_hdf(path, key="signals", mode="w")
                except ImportError as exc:
                    raise BlockError("HDF5 export requires the optional PyTables package.") from exc
            if bool(self.params["include_metadata"]):
                path.with_suffix(path.suffix + ".metadata.json").write_text(json.dumps(metadata, indent=2, default=str), encoding="utf-8")
            return []
        except BlockError:
            raise
        except (OSError, ValueError, TypeError, ImportError) as exc:
            raise BlockError(f"Could not write export file: {exc}") from exc


@register_block
class ExportPlotBlock(ProcessingBlock):
    type_name = "export_plot"
    display_name = "Export Plot"
    category = "Inputs & Outputs"
    description = "Render up to four signals to PNG, SVG or PDF using Matplotlib."
    input_count = 4
    minimum_inputs = 1
    input_types = ("signal",) * 4
    output_count = 0
    output_types = ()
    cacheable = False
    parameters = (
        ParameterSpec("file_path", "Plot file", "save_file", "", file_filter="PNG (*.png);;SVG (*.svg);;PDF (*.pdf)"),
        ParameterSpec("title", "Title", "text", "SignalDojo Plot"),
        ParameterSpec("width_inches", "Width (in)", "float", 10.0, 1.0),
        ParameterSpec("height_inches", "Height (in)", "float", 6.0, 1.0),
        ParameterSpec("dpi", "DPI", "int", 150, 72, 600),
    )

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        signals = connected_signals(inputs, self.display_name)
        path = Path(str(self.params["file_path"])).expanduser()
        if path.suffix.lower() not in {".png", ".svg", ".pdf"}:
            raise BlockError("Plot file must use .png, .svg or .pdf.")
        path.parent.mkdir(parents=True, exist_ok=True)
        import matplotlib
        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
        figure, axis = plt.subplots(figsize=(float(self.params["width_inches"]), float(self.params["height_inches"])))
        for signal in signals:
            if np.iscomplexobj(signal.values):
                axis.plot(signal.time, np.real(signal.values), label=f"{signal.name} — real")
                axis.plot(signal.time, np.imag(signal.values), label=f"{signal.name} — imaginary")
            else:
                axis.plot(signal.time, signal.values, label=signal.name)
        axis.set_title(str(self.params["title"]))
        axis.set_xlabel("Time (s)")
        units = {signal.unit for signal in signals if signal.unit}
        axis.set_ylabel(next(iter(units)) if len(units) == 1 else "Amplitude")
        axis.grid(True, alpha=0.3)
        axis.legend()
        figure.tight_layout()
        figure.savefig(path, dpi=int(self.params["dpi"]))
        plt.close(figure)
        return []


@register_block
class ExportReportBlock(ProcessingBlock):
    type_name = "export_report"
    display_name = "Export Report"
    category = "Inputs & Outputs"
    description = "Create a self-contained professional HTML or PDF engineering report."
    input_count = 4
    minimum_inputs = 1
    input_types = ("any",) * 4
    output_count = 0
    output_types = ()
    cacheable = False
    parameters = (
        ParameterSpec("file_path", "Report file", "save_file", "", file_filter="HTML (*.html);;PDF (*.pdf)"),
        ParameterSpec("project_name", "Project name", "text", "SignalDojo Analysis"),
        ParameterSpec("project_description", "Project description", "multiline", ""),
        ParameterSpec("author", "Author", "text", ""),
    )

    def _sections(self, values: list[Any]) -> tuple[list[str], list[SignalData]]:
        sections: list[str] = []
        signals: list[SignalData] = []
        for value in values:
            if isinstance(value, SignalData):
                signals.append(value)
                rows = "".join(
                    f"<tr><th>{escape(str(key))}</th><td>{escape(str(item))}</td></tr>"
                    for key, item in value.to_metadata().items() if key != "processing_history"
                )
                history_rows = "".join(f"<li><code>{escape(json.dumps(entry, default=str))}</code></li>" for entry in value.processing_history)
                sections.append(f"<h2>{escape(value.name)}</h2><table>{rows}</table><h3>Processing history</h3><ol>{history_rows}</ol>")
            elif isinstance(value, ScalarResult):
                sections.append(f"<h2>{escape(value.name)}</h2><p class='metric'>{escape(str(value.value))} {escape(value.unit)}</p>")
            elif isinstance(value, TableResult):
                sections.append(f"<h2>{escape(value.name)}</h2>{value.frame.head(1000).to_html(index=False, escape=True)}")
            elif isinstance(value, SpectrumData):
                sections.append(f"<h2>{escape(value.name)}</h2><p>{len(value.frequency)} frequency bins; scale: {escape(value.scale)}.</p>")
            elif isinstance(value, SpectrogramData):
                sections.append(f"<h2>{escape(value.name)}</h2><p>{value.values.shape[0]} frequency bins × {value.values.shape[1]} time frames.</p>")
        return sections, signals

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        values = [value for value in inputs if value is not None]
        path = Path(str(self.params["file_path"])).expanduser()
        if path.suffix.lower() not in {".html", ".pdf"}:
            raise BlockError("Report file must use .html or .pdf.")
        path.parent.mkdir(parents=True, exist_ok=True)
        sections, signals = self._sections(values)
        if path.suffix.lower() == ".html":
            plot_html = ""
            if signals:
                import base64
                from io import BytesIO
                import matplotlib
                matplotlib.use("Agg")
                from matplotlib import pyplot as plt
                fig, ax = plt.subplots(figsize=(10, 5))
                for signal in signals:
                    indices = np.linspace(0, signal.samples - 1, min(signal.samples, 100_000), dtype=int)
                    if np.iscomplexobj(signal.values):
                        ax.plot(signal.time[indices], np.real(signal.values[indices]), label=f"{signal.name} — real")
                        ax.plot(signal.time[indices], np.imag(signal.values[indices]), label=f"{signal.name} — imaginary")
                    else:
                        ax.plot(signal.time[indices], signal.values[indices], label=signal.name)
                ax.set_xlabel("Time (s)"); ax.set_ylabel("Amplitude"); ax.grid(True, alpha=0.3); ax.legend(); fig.tight_layout()
                buffer = BytesIO(); fig.savefig(buffer, format="png", dpi=140); plt.close(fig)
                plot_html = f"<h2>Selected signals</h2><img src='data:image/png;base64,{base64.b64encode(buffer.getvalue()).decode()}' />"
            project_name = escape(str(self.params["project_name"]))
            project_description = escape(str(self.params["project_description"]))
            author = escape(str(self.params["author"]))
            html = f"""<!doctype html><html><head><meta charset='utf-8'><title>{project_name}</title><style>body{{font-family:Segoe UI,Arial,sans-serif;max-width:1100px;margin:40px auto;color:#17202a}}h1{{border-bottom:3px solid #245b85;padding-bottom:12px}}table{{border-collapse:collapse;width:100%;margin:12px 0}}th,td{{border:1px solid #ccd4dc;padding:7px;text-align:left}}th{{background:#edf2f6}}img{{max-width:100%}}code{{white-space:pre-wrap;word-break:break-word}}.metric{{font-size:2rem;font-weight:600}}</style></head><body><h1>{project_name}</h1><p>{project_description}</p><p><strong>Author:</strong> {author}<br><strong>Exported:</strong> {datetime.now(timezone.utc).isoformat()}<br><strong>Application:</strong> SignalDojo</p>{plot_html}{''.join(sections)}</body></html>"""
            path.write_text(html, encoding="utf-8")
        else:
            import matplotlib
            matplotlib.use("Agg")
            from matplotlib import pyplot as plt
            from matplotlib.backends.backend_pdf import PdfPages
            with PdfPages(path) as pdf:
                fig = plt.figure(figsize=(8.27, 11.69)); fig.text(0.08, 0.92, str(self.params["project_name"]), fontsize=22, weight="bold"); fig.text(0.08, 0.86, str(self.params["project_description"]), fontsize=11, wrap=True); fig.text(0.08, 0.80, f"Author: {self.params['author']}\nExported: {datetime.now(timezone.utc).isoformat()}\nApplication: SignalDojo", fontsize=10); pdf.savefig(fig); plt.close(fig)
                if signals:
                    fig, ax = plt.subplots(figsize=(11.69, 8.27))
                    for signal in signals:
                        idx = np.linspace(0, signal.samples - 1, min(signal.samples, 100_000), dtype=int)
                        if np.iscomplexobj(signal.values):
                            ax.plot(signal.time[idx], np.real(signal.values[idx]), label=f"{signal.name} — real")
                            ax.plot(signal.time[idx], np.imag(signal.values[idx]), label=f"{signal.name} — imaginary")
                        else:
                            ax.plot(signal.time[idx], signal.values[idx], label=signal.name)
                    ax.set_title("Selected signals"); ax.set_xlabel("Time (s)"); ax.set_ylabel("Amplitude"); ax.grid(True, alpha=0.3); ax.legend(); fig.tight_layout(); pdf.savefig(fig); plt.close(fig)
                for value in values:
                    fig = plt.figure(figsize=(8.27, 11.69)); fig.text(0.08, 0.94, getattr(value, "name", type(value).__name__), fontsize=18, weight="bold")
                    if isinstance(value, SignalData):
                        text = json.dumps(value.to_metadata(), indent=2, default=str)
                    elif isinstance(value, ScalarResult):
                        text = f"{value.value} {value.unit}\n\n{value.description}"
                    elif isinstance(value, TableResult):
                        text = value.frame.head(60).to_string(index=False)
                    else:
                        text = repr(value)
                    fig.text(0.08, 0.89, text[:8000], family="monospace", fontsize=7, va="top"); pdf.savefig(fig); plt.close(fig)
        return []



@register_block
class PublishMetricBlock(ProcessingBlock):
    """Publish a compact named result for automated test campaigns."""

    type_name = "publish_metric"
    display_name = "Publish Metric"
    category = "Campaign"
    description = (
        "Publish a named scalar campaign metric from a scalar, signal, spectrum or "
        "single-cell table. Signal inputs are reduced using the selected engineering aggregation."
    )
    input_types = ("any",)
    output_types = ("scalar",)
    parameters = (
        ParameterSpec("metric_name", "Metric name", "text", "metric", help_text="Stable identifier used by campaign requirements and exports."),
        ParameterSpec("display_label", "Display label", "text", "", help_text="Optional human-readable dashboard label."),
        ParameterSpec("unit", "Unit override", "text", "", help_text="Blank preserves the source or inferred engineering unit."),
        ParameterSpec("description", "Description", "multiline", ""),
        ParameterSpec("number_format", "Numeric format", "text", ".6g", help_text="Python format specification used by campaign tables and reports."),
        ParameterSpec(
            "aggregation", "Aggregation", "choice", "auto",
            choices=(
                "auto", "value", "mean", "rms", "standard_deviation", "minimum", "maximum",
                "peak_to_peak", "dominant_frequency", "sample_count", "duration", "rise_time",
                "settling_time", "first", "last", "custom_expression",
            ),
        ),
        ParameterSpec(
            "expression", "Custom scalar expression", "multiline", "mean",
            help_text="Safe expression using mean, rms, std, minimum, maximum, peak_to_peak, sample_count, duration, first and last.",
            visible_when=(("aggregation", ("custom_expression",)),),
        ),
    )

    def validate_parameters(self) -> None:
        super().validate_parameters()
        name = str(self.params.get("metric_name", "")).strip()
        if not name:
            raise BlockError("Metric name is required.")
        if len(name) > 128:
            raise BlockError("Metric name must not exceed 128 characters.")
        number_format = str(self.params.get("number_format", ".6g")).strip()
        try:
            format(1.2345, number_format)
        except (ValueError, TypeError) as exc:
            raise BlockError(f"Numeric format '{number_format}' is invalid.") from exc

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        from app.campaign.metrics import aggregate_metric

        try:
            value, inferred_unit, inferred_description = aggregate_metric(
                inputs[0], str(self.params["aggregation"]), expression=str(self.params.get("expression", "")),
            )
        except ValueError as exc:
            raise BlockError(
                f"Input is not suitable as a compact campaign metric: {exc}. "
                "Select a scalar-compatible aggregation or publish a scalar analysis output."
            ) from exc
        metric_name = str(self.params["metric_name"]).strip()
        description = str(self.params.get("description", "")).strip() or inferred_description
        unit = str(self.params.get("unit", "")).strip() or inferred_unit
        return [ScalarResult(
            value=value,
            name=str(self.params.get("display_label", "")).strip() or metric_name,
            unit=unit,
            description=description,
            metadata={
                "published_metric": True,
                "metric_name": metric_name,
                "display_label": str(self.params.get("display_label", "")).strip() or metric_name,
                "number_format": str(self.params.get("number_format", ".6g")),
                "aggregation": str(self.params.get("aggregation", "auto")),
            },
        )]

# ---------------------------------------------------------------------------
# Plugins
# ---------------------------------------------------------------------------


def load_plugins(directories: Iterable[str | Path]) -> list[str]:
    """Load Python modules containing ``ProcessingBlock`` subclasses.

    A plugin may call :func:`register_block` directly or expose a ``BLOCKS`` iterable.
    Errors are isolated and returned to the diagnostics window rather than crashing the
    application at startup.
    """

    loaded: list[str] = []
    for directory in directories:
        root = Path(directory).expanduser()
        if not root.exists():
            continue
        for path in sorted(root.glob("*.py")):
            if path.name.startswith("_"):
                continue
            module_name = f"signaldojo_plugin_{path.stem}_{abs(hash(path))}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec is None or spec.loader is None:
                    raise ImportError("Could not create a module specification.")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                for block_cls in getattr(module, "BLOCKS", ()):
                    register_block(block_cls)
                loaded.append(str(path))
            except Exception as exc:  # plugins are untrusted extension points
                PLUGIN_ERRORS.append(f"{path}: {exc}")
    return loaded

# Stable class aliases retained for public API compatibility and plugin authors.
LowPassBlock = BLOCK_TYPES["low_pass"]
HighPassBlock = BLOCK_TYPES["high_pass"]
BandPassBlock = BLOCK_TYPES["band_pass"]
BandStopBlock = BLOCK_TYPES["band_stop"]
ButterworthFilterBlock = BLOCK_TYPES["butter_filter"]
ChebyshevTypeIFilterBlock = BLOCK_TYPES["cheby1_filter"]
ChebyshevTypeIIFilterBlock = BLOCK_TYPES["cheby2_filter"]
EllipticFilterBlock = BLOCK_TYPES["ellip_filter"]
BesselFilterBlock = BLOCK_TYPES["bessel_filter"]

@register_block
class ManualSignalGeneratorBlock(ProcessingBlock):
    type_name = "manual_signal_generator"
    display_name = "Manual Signal Generator"
    category = "Inputs & Outputs"
    description = "Create a signal from comma- or whitespace-separated values and optional time values."
    input_count = 0
    output_types = ("signal",)
    parameters = (
        ParameterSpec("values", "Sample values", "multiline", "0, 1, 0, -1"),
        ParameterSpec("time_values", "Time values; blank uses sample rate", "multiline", ""),
        ParameterSpec("sample_rate", "Sample rate (Hz)", "float", 100.0, 1e-12),
        ParameterSpec("name", "Signal name", "text", "Manual signal"),
        ParameterSpec("unit", "Unit", "text", ""),
    )

    @staticmethod
    def _numbers(text: str) -> np.ndarray:
        try:
            return np.asarray([float(value) for value in re.split(r"[\s,;]+", text.strip()) if value], dtype=float)
        except ValueError as exc:
            raise BlockError("Manual values must be numeric and separated by commas, semicolons or whitespace.") from exc

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        values = self._numbers(str(self.params["values"]))
        if not len(values):
            raise BlockError("Enter at least one sample value.")
        raw_time = str(self.params.get("time_values", "")).strip()
        if raw_time:
            time_values = self._numbers(raw_time)
            if len(time_values) != len(values):
                raise BlockError("Manual time and value lists must have equal length.")
            sample_rate = None
        else:
            sample_rate = float(self.params["sample_rate"])
            time_values = np.arange(len(values), dtype=float) / sample_rate
        return [SignalData(values, time_values, name=str(self.params["name"]), unit=str(self.params["unit"]), sample_rate=sample_rate, processing_history=[history(self)])]


@register_block
class CustomMathematicalSignalBlock(GeneratorBlock):
    type_name = "custom_mathematical_signal"
    display_name = "Custom Mathematical Signal"
    category = "Signal Generators"
    description = "Generate a signal from a safe mathematical expression using t, frequency, amplitude, phase and offset."
    parameters = GeneratorBlock.parameters + (ParameterSpec("formula", "Formula", "multiline", "amplitude * sin(2*pi*frequency*t + phase) + offset"),)

    def waveform(self, time_values: np.ndarray, phase_rad: float) -> np.ndarray:
        # GeneratorBlock applies amplitude and offset itself, therefore this block
        # overrides execute instead of using waveform.
        return np.zeros_like(time_values)

    def execute(self, inputs: list[Any]) -> list[Any]:
        self.validate(inputs)
        fs, duration = float(self.params["sample_rate"]), float(self.params["duration"])
        frequency = float(self.params["frequency"])
        if frequency >= fs / 2 and frequency > 0:
            raise BlockError(f"Frequency must be below Nyquist ({fs / 2:g} Hz).")
        samples = max(1, int(round(fs * duration)))
        time_values = np.arange(samples, dtype=float) / fs
        variables = {
            "t": time_values,
            "frequency": frequency,
            "amplitude": float(self.params["amplitude"]),
            "phase": math.radians(float(self.params["phase"])),
            "offset": float(self.params["offset"]),
        }
        try:
            output = evaluate_expression(str(self.params["formula"]), variables)
        except UnsafeExpression as exc:
            raise BlockError(str(exc)) from exc
        output = np.asarray(output)
        if output.ndim == 0:
            output = np.full(samples, output.item())
        if output.ndim != 1 or len(output) != samples:
            raise BlockError("Custom mathematical signal formula must return a scalar or one value per time sample.")
        return [SignalData(output, time_values, name=str(self.params["name"]), unit=str(self.params["unit"]), sample_rate=fs, processing_history=[history(self, formula=self.params["formula"])])]
