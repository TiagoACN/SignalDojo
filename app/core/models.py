# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Core data models for SignalDojo.

The processing engine deliberately has no Qt dependency.  UI widgets consume these
small immutable-ish data containers and can therefore be tested independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


_KEEP_SAMPLE_RATE = object()


@dataclass(slots=True)
class SignalData:
    """A one-dimensional sampled signal with engineering metadata."""

    values: np.ndarray
    time: np.ndarray
    name: str = "Signal"
    unit: str = ""
    sample_rate: float | None = None
    source_file: str | None = None
    channel_name: str | None = None
    description: str = ""
    processing_history: list[dict[str, Any]] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.values = np.asarray(self.values)
        self.time = np.asarray(self.time, dtype=float)
        if self.values.ndim != 1:
            raise ValueError("Signal values must be one-dimensional.")
        if self.time.ndim != 1:
            raise ValueError("Signal time values must be one-dimensional.")
        if len(self.values) != len(self.time):
            raise ValueError("Signal values and time arrays must have equal length.")
        if len(self.values) == 0:
            raise ValueError("Signal cannot be empty.")
        if not np.issubdtype(self.values.dtype, np.number):
            raise ValueError("Signal values must be numeric.")
        if np.any(~np.isfinite(self.time)):
            raise ValueError("Signal time values contain NaN or infinity.")
        if len(self.time) > 1 and np.any(np.diff(self.time) <= 0):
            raise ValueError("Signal time values must be strictly increasing.")
        if self.sample_rate is None and len(self.time) > 1:
            delta = np.diff(self.time)
            median_delta = float(np.median(delta))
            # A single sample-rate value is meaningful only for uniformly sampled
            # data.  Earlier versions stored the reciprocal median interval even for
            # uneven timestamps, which could make filters appear usable when they were
            # not.  Irregular signals now retain ``None`` until explicitly resampled.
            if np.allclose(delta, median_delta, rtol=1e-4, atol=1e-12):
                self.sample_rate = float(1.0 / median_delta)
        if self.sample_rate is not None:
            if not np.isfinite(self.sample_rate) or self.sample_rate <= 0:
                raise ValueError("Sample rate must be finite and greater than zero.")
            if len(self.time) > 1:
                if not self.is_uniform:
                    raise ValueError("A sample rate cannot be assigned to an irregular time vector. Resample the signal first.")
                inferred_rate = float(1.0 / np.median(np.diff(self.time)))
                if not np.isclose(float(self.sample_rate), inferred_rate, rtol=1e-4, atol=1e-9):
                    raise ValueError(
                        f"Sample rate {self.sample_rate:g} Hz does not match the time vector ({inferred_rate:g} Hz)."
                    )

    @property
    def duration(self) -> float:
        return float(self.time[-1] - self.time[0]) if len(self.time) > 1 else 0.0

    @property
    def samples(self) -> int:
        return int(len(self.values))

    @property
    def is_uniform(self) -> bool:
        if self.samples < 3:
            return True
        delta = np.diff(self.time)
        return bool(np.allclose(delta, np.median(delta), rtol=1e-4, atol=1e-12))

    @property
    def contains_non_finite(self) -> bool:
        return bool(np.any(~np.isfinite(self.values)))

    def with_values(
        self,
        values: np.ndarray,
        *,
        time: np.ndarray | None = None,
        history_entry: dict[str, Any] | None = None,
        name: str | None = None,
        unit: str | None = None,
        sample_rate: float | None | object = _KEEP_SAMPLE_RATE,
        attributes: dict[str, Any] | None = None,
    ) -> "SignalData":
        """Return a derived signal while preserving metadata."""

        history = list(self.processing_history)
        if history_entry:
            history.append(history_entry)
        merged_attributes = dict(self.attributes)
        if attributes:
            merged_attributes.update(attributes)
        return replace(
            self,
            values=np.asarray(values),
            time=self.time if time is None else np.asarray(time, dtype=float),
            processing_history=history,
            name=self.name if name is None else name,
            unit=self.unit if unit is None else unit,
            sample_rate=self.sample_rate if sample_rate is _KEEP_SAMPLE_RATE else sample_rate,
            attributes=merged_attributes,
        )

    def finite_copy(self) -> "SignalData":
        """Return a signal with rows containing NaN/Inf removed."""

        mask = np.isfinite(self.time) & np.isfinite(self.values)
        if not np.any(mask):
            raise ValueError("Signal contains no finite samples.")
        return self.with_values(self.values[mask], time=self.time[mask], sample_rate=None)

    def to_metadata(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "unit": self.unit,
            "sample_rate": self.sample_rate,
            "source_file": self.source_file,
            "channel_name": self.channel_name,
            "description": self.description,
            "samples": self.samples,
            "duration": self.duration,
            "uniform_sampling": self.is_uniform,
            "processing_history": self.processing_history,
            "attributes": self.attributes,
        }

    def signature(self) -> str:
        """Fast-enough content signature used by incremental workflow caching."""

        hasher = sha256()
        hasher.update(str(self.values.dtype).encode())
        hasher.update(str(self.values.shape).encode())
        # Hash the complete arrays, including large datasets.  Earlier releases
        # sampled only 4096 positions above 16 MB, so changing an unsampled value could
        # leave the workflow cache signature unchanged and return stale processing
        # results.  Chunked updates keep the peak temporary memory bounded while
        # retaining deterministic content correctness.
        for array in (self.values, self.time):
            contiguous = np.ascontiguousarray(array)
            raw = memoryview(contiguous).cast("B")
            chunk_bytes = 8 * 1024 * 1024
            for start in range(0, len(raw), chunk_bytes):
                hasher.update(raw[start:start + chunk_bytes])
        hasher.update(self.name.encode("utf-8", "replace"))
        hasher.update(self.unit.encode("utf-8", "replace"))
        hasher.update(repr((
            self.sample_rate,
            self.source_file,
            self.channel_name,
            self.description,
            self.processing_history,
            self.attributes,
        )).encode("utf-8", "replace"))
        return hasher.hexdigest()

    def to_frame(self, value_name: str | None = None) -> pd.DataFrame:
        requested = str(value_name or self.name or "value")
        # A signal named ``time`` must not overwrite the independent time axis in
        # the resulting table.
        column_name = "time_2" if requested == "time" else requested
        return pd.DataFrame({"time": self.time, column_name: self.values})

    @staticmethod
    def normalise_path(path: str | Path) -> str:
        return str(Path(path).expanduser().resolve())


@dataclass(slots=True)
class ScalarResult:
    """Named scalar analysis result."""

    value: float | complex | str
    name: str
    unit: str = ""
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def signature(self) -> str:
        return sha256(
            repr((self.value, self.name, self.unit, self.description, self.metadata)).encode("utf-8", "replace")
        ).hexdigest()


@dataclass(slots=True)
class TableResult:
    """Tabular analysis result suitable for a data-grid display or export."""

    frame: pd.DataFrame
    name: str = "Table"
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.frame, pd.DataFrame):
            self.frame = pd.DataFrame(self.frame)

    def signature(self) -> str:
        hasher = sha256()
        hasher.update(repr((tuple(self.frame.columns), tuple(map(str, self.frame.dtypes)), self.frame.index.name)).encode("utf-8", "replace"))
        try:
            hasher.update(pd.util.hash_pandas_object(self.frame, index=True).values.tobytes())
        except (TypeError, ValueError):
            # Object tables may contain otherwise unhashable values such as lists or
            # dictionaries.  A stable textual fallback is preferable to crashing the
            # workflow cache for a perfectly displayable table.
            rendered = self.frame.map(lambda value: repr(value))
            hasher.update(pd.util.hash_pandas_object(rendered, index=True).values.tobytes())
        hasher.update(repr((self.name, self.description, self.metadata)).encode("utf-8", "replace"))
        return hasher.hexdigest()


@dataclass(slots=True)
class SpectrumData:
    """Frequency-domain result used by spectrum and spectrogram visualisers."""

    frequency: np.ndarray
    values: np.ndarray
    name: str = "Spectrum"
    unit: str = ""
    scale: str = "magnitude"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.frequency = np.asarray(self.frequency, dtype=float)
        self.values = np.asarray(self.values)
        if self.frequency.ndim != 1 or self.values.ndim != 1:
            raise ValueError("Spectrum axes must be one-dimensional.")
        if len(self.frequency) != len(self.values):
            raise ValueError("Spectrum frequency and value arrays must have equal length.")
        if len(self.frequency) == 0:
            raise ValueError("Spectrum cannot be empty.")
        if not np.issubdtype(self.values.dtype, np.number):
            raise ValueError("Spectrum values must be numeric.")
        if np.any(~np.isfinite(self.frequency)):
            raise ValueError("Spectrum frequency values must be finite.")
        if len(self.frequency) > 1 and np.any(np.diff(self.frequency) <= 0):
            raise ValueError("Spectrum frequency values must be strictly increasing.")

    def signature(self) -> str:
        hasher = sha256()
        hasher.update(repr((self.frequency.dtype.str, self.frequency.shape, self.values.dtype.str, self.values.shape)).encode())
        hasher.update(np.ascontiguousarray(self.frequency).view(np.uint8))
        hasher.update(np.ascontiguousarray(self.values).view(np.uint8))
        hasher.update(repr((self.name, self.unit, self.scale, self.metadata)).encode("utf-8", "replace"))
        return hasher.hexdigest()


@dataclass(slots=True)
class SpectrogramData:
    """Time-frequency matrix output."""

    frequency: np.ndarray
    time: np.ndarray
    values: np.ndarray
    name: str = "Spectrogram"
    unit: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.frequency = np.asarray(self.frequency, dtype=float)
        self.time = np.asarray(self.time, dtype=float)
        self.values = np.asarray(self.values)
        if self.frequency.ndim != 1 or self.time.ndim != 1:
            raise ValueError("Spectrogram axes must be one-dimensional.")
        if len(self.frequency) == 0 or len(self.time) == 0:
            raise ValueError("Spectrogram axes cannot be empty.")
        if np.any(~np.isfinite(self.frequency)) or np.any(~np.isfinite(self.time)):
            raise ValueError("Spectrogram axes must contain finite values.")
        if len(self.frequency) > 1 and np.any(np.diff(self.frequency) <= 0):
            raise ValueError("Spectrogram frequency values must be strictly increasing.")
        if len(self.time) > 1 and np.any(np.diff(self.time) <= 0):
            raise ValueError("Spectrogram time values must be strictly increasing.")
        if not np.issubdtype(self.values.dtype, np.number):
            raise ValueError("Spectrogram values must be numeric.")
        if self.values.shape != (len(self.frequency), len(self.time)):
            raise ValueError("Spectrogram matrix shape must be frequency × time.")

    def signature(self) -> str:
        hasher = sha256()
        hasher.update(repr((self.frequency.dtype.str, self.frequency.shape, self.time.dtype.str, self.time.shape, self.values.dtype.str, self.values.shape)).encode())
        hasher.update(np.ascontiguousarray(self.frequency).view(np.uint8))
        hasher.update(np.ascontiguousarray(self.time).view(np.uint8))
        hasher.update(np.ascontiguousarray(self.values).view(np.uint8))
        hasher.update(repr((self.name, self.unit, self.metadata)).encode("utf-8", "replace"))
        return hasher.hexdigest()


ResultValue = SignalData | ScalarResult | TableResult | SpectrumData | SpectrogramData


def result_signature(value: Any) -> str:
    if value is None:
        return "none"
    signature_method = getattr(value, "signature", None)
    if callable(signature_method):
        return str(signature_method())
    if isinstance(value, np.ndarray):
        hasher = sha256(repr((value.dtype.str, value.shape)).encode())
        hasher.update(np.ascontiguousarray(value).view(np.uint8))
        return hasher.hexdigest()
    return sha256(repr(value).encode("utf-8", "replace")).hexdigest()


def signals_to_frame(signals: Iterable[SignalData], *, require_aligned: bool = True) -> pd.DataFrame:
    signal_list = list(signals)
    if not signal_list:
        return pd.DataFrame()
    base = signal_list[0]
    frame = pd.DataFrame({"time": base.time})
    for index, signal in enumerate(signal_list):
        if require_aligned and (
            signal.samples != base.samples
            or not np.allclose(signal.time, base.time, rtol=1e-7, atol=1e-12)
        ):
            raise ValueError("Signals must share the same time vector for a combined export.")
        name = signal.name or f"signal_{index + 1}"
        candidate = name
        suffix = 2
        while candidate in frame.columns:
            candidate = f"{name}_{suffix}"
            suffix += 1
        frame[candidate] = signal.values
    return frame
