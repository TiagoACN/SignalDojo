# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.core.models import ScalarResult, SignalData, SpectrogramData, SpectrumData, TableResult
from app.project.io import PROJECT_VERSION, load_project, save_project
from app.project.result_codec import (
    deserialise_display_record,
    deserialise_result,
    serialise_display_record,
    serialise_result,
)


def test_signal_result_round_trip_preserves_complex_values_and_metadata() -> None:
    signal = SignalData(
        values=np.array([1 + 2j, 3 - 4j, 5 + 0j]),
        time=np.array([0.0, 0.1, 0.2]),
        name="Current",
        unit="A",
        sample_rate=10.0,
        source_file="capture.csv",
        channel_name="motor",
        description="Complex test signal",
        processing_history=[{"block": "fft", "gain": np.float64(2.0)}],
        attributes={"quality": {"valid": True}, "limit": float("inf")},
    )

    restored = deserialise_result(serialise_result(signal))

    assert isinstance(restored, SignalData)
    np.testing.assert_array_equal(restored.values, signal.values)
    np.testing.assert_array_equal(restored.time, signal.time)
    assert restored.name == signal.name
    assert restored.unit == signal.unit
    assert restored.processing_history == [{"block": "fft", "gain": 2.0}]
    assert np.isinf(restored.attributes["limit"])


def test_all_display_result_types_round_trip() -> None:
    signal = SignalData(np.arange(5.0), np.arange(5.0) / 10.0, name="Signal", unit="V", sample_rate=10.0)
    spectrum = SpectrumData(np.array([0.0, 1.0]), np.array([1.0, 0.5]), name="FFT", unit="V", scale="magnitude")
    spectrogram = SpectrogramData(
        np.array([0.0, 1.0]),
        np.array([0.0, 0.5, 1.0]),
        np.arange(6.0).reshape(2, 3),
        name="STFT",
        unit="V",
    )
    table = TableResult(
        pd.DataFrame({"count": pd.Series([1, 2], dtype="int64"), "label": ["a", "b"], "value": [1 + 2j, 3 + 4j], "optional": [pd.NA, "present"]}),
        name="Summary",
    )

    records = [
        {"kind": "scope", "title": "Scope", "signals": [signal], "options": {"max_points": 1000, "grid": True}},
        {"kind": "spectrum", "title": "Spectrum", "value": spectrum, "options": {"decibel": True}},
        {"kind": "spectrogram", "title": "Spectrogram", "value": spectrogram, "options": {"colour_map": "viridis"}},
        {"kind": "table", "title": "Table", "value": table, "options": {"maximum_rows": 100}},
        {"kind": "table", "title": "Scalar", "value": TableResult(pd.DataFrame({"value": [3.2]})), "options": {}},
    ]

    restored = [deserialise_display_record(serialise_display_record(record)) for record in records]

    assert isinstance(restored[0]["signals"][0], SignalData)
    assert isinstance(restored[1]["value"], SpectrumData)
    assert isinstance(restored[2]["value"], SpectrogramData)
    assert isinstance(restored[3]["value"], TableResult)
    pd.testing.assert_frame_equal(restored[3]["value"].frame, table.frame)


def test_scalar_result_round_trip() -> None:
    value = ScalarResult(2 + 3j, "Impedance", "ohm", metadata={"source": "fit"})
    restored = deserialise_result(serialise_result(value))
    assert isinstance(restored, ScalarResult)
    assert restored.value == 2 + 3j
    assert restored.metadata == {"source": "fit"}


def test_project_round_trip_preserves_compressed_display_results(tmp_path: Path) -> None:
    path = tmp_path / "with-results.sdojo"
    signal = SignalData(np.linspace(0, 1, 100), np.linspace(0, 0.99, 100), name="Saved", unit="mV", sample_rate=100.0)
    record = {"kind": "scope", "title": "Saved Scope", "signals": [signal], "options": {"max_points": 100_000, "grid": True}}
    payload = {
        "nodes": [
            {"id": "scope", "type": "scope", "position": [0, 0], "parameters": {}, "output_metadata": []},
        ],
        "connections": [],
        "results": {
            "display": {"scope": serialise_display_record(record)},
            "visibility": {"scope": False},
        },
    }

    save_project(path, payload)
    loaded = load_project(path)

    assert loaded["project_version"] == PROJECT_VERSION
    assert loaded["results"]["visibility"]["scope"] is False
    restored = deserialise_display_record(loaded["results"]["display"]["scope"])
    np.testing.assert_allclose(restored["signals"][0].values, signal.values)
    assert restored["title"] == "Saved Scope"


def test_version_two_project_migrates_to_empty_persisted_results(tmp_path: Path) -> None:
    path = tmp_path / "version-two.sdojo"
    path.write_text(
        '{"format":"SignalDojo Project","project_version":2,"nodes":[],"connections":[],"view":{}}',
        encoding="utf-8",
    )
    loaded = load_project(path)
    assert loaded["project_version"] == PROJECT_VERSION
    assert loaded["results"] == {"display": {}, "visibility": {}}


def test_legacy_irregular_signal_result_discards_contradictory_sample_rate() -> None:
    """Old projects remain readable when they stored a nominal rate for uneven time."""

    legacy = SignalData(
        np.arange(5.0),
        np.array([0.0, 0.1, 0.24, 0.39, 0.55]),
        name="Legacy irregular",
    )
    payload = serialise_result(legacy)
    payload["sample_rate"] = 10.0  # Emulate the stale metadata written by 1.0.x.

    restored = deserialise_result(payload)

    assert isinstance(restored, SignalData)
    assert restored.sample_rate is None
    assert restored.attributes["project_migration"]["discarded_sample_rate_hz"] == 10.0
    np.testing.assert_array_equal(restored.values, legacy.values)
    np.testing.assert_array_equal(restored.time, legacy.time)
