# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.core.blocks import (
    BlockError,
    ExportDataBlock,
    GainBlock,
    ImportDataBlock,
    LowPassBlock,
    OffsetBlock,
)
from app.core.models import SignalData
from app.core.workflow import Connection, WorkflowGraph, WorkflowNode


def make_signal(sample_rate: float = 500.0, duration: float = 2.0) -> SignalData:
    time = np.arange(int(sample_rate * duration)) / sample_rate
    values = np.sin(2 * np.pi * 5 * time) + 0.5 * np.sin(2 * np.pi * 100 * time)
    return SignalData(values=values, time=time, name="test", unit="V")


def test_signal_infers_sample_rate() -> None:
    signal = make_signal(200.0)
    assert signal.sample_rate == pytest.approx(200.0, rel=1e-8)
    assert signal.duration == pytest.approx(signal.time[-1])


def test_gain_and_offset_preserve_metadata() -> None:
    source = make_signal()
    gained = GainBlock(gain=2.0).execute([source])[0]
    shifted = OffsetBlock(offset=-1.0).execute([gained])[0]
    np.testing.assert_allclose(shifted.values, source.values * 2.0 - 1.0)
    assert shifted.unit == "V"
    assert len(shifted.processing_history) == 2


def test_low_pass_reduces_high_frequency_component() -> None:
    source = make_signal()
    filtered = LowPassBlock(cutoff=20.0, order=4, zero_phase=True).execute([source])[0]
    spectrum_before = np.abs(np.fft.rfft(source.values))
    spectrum_after = np.abs(np.fft.rfft(filtered.values))
    frequencies = np.fft.rfftfreq(source.samples, d=1 / source.sample_rate)
    high_bin = int(np.argmin(np.abs(frequencies - 100.0)))
    low_bin = int(np.argmin(np.abs(frequencies - 5.0)))
    assert spectrum_after[high_bin] < spectrum_before[high_bin] * 0.05
    assert spectrum_after[low_bin] > spectrum_before[low_bin] * 0.85


def test_low_pass_rejects_cutoff_above_nyquist() -> None:
    with pytest.raises(BlockError, match="Nyquist"):
        LowPassBlock(cutoff=300.0).execute([make_signal(500.0)])


def test_import_csv_and_export_metadata(tmp_path: Path) -> None:
    source_file = tmp_path / "input.csv"
    pd.DataFrame({"time": [0.0, 0.1, 0.2], "sensor": [1.0, 2.0, 3.0]}).to_csv(
        source_file, index=False
    )
    imported = ImportDataBlock(
        file_path=str(source_file),
        time_column="time",
        signal_column="sensor",
        signal_name="Force",
        unit="N",
    ).execute([])[0]
    assert imported.sample_rate == pytest.approx(10.0)
    assert imported.name == "Force"

    output_file = tmp_path / "output.csv"
    ExportDataBlock(file_path=str(output_file), include_metadata=True).execute([imported])
    assert output_file.exists()
    metadata = json.loads((tmp_path / "output.csv.metadata.json").read_text())
    assert metadata["unit"] == "N"
    assert metadata["samples"] == 3


def test_workflow_executes_in_dependency_order() -> None:
    graph = WorkflowGraph()
    graph.add_node(WorkflowNode("import", ImportDataBlock(file_path="missing.csv")))
    graph.add_node(WorkflowNode("gain", GainBlock(gain=2.0)))
    graph.add_connection(Connection("import", 0, "gain", 0))
    assert graph.topological_order() == ["import", "gain"]


def test_workflow_rejects_cycles() -> None:
    graph = WorkflowGraph()
    graph.add_node(WorkflowNode("a", GainBlock()))
    graph.add_node(WorkflowNode("b", OffsetBlock()))
    graph.add_connection(Connection("a", 0, "b", 0))
    with pytest.raises(BlockError, match="circular"):
        graph.add_connection(Connection("b", 0, "a", 0))


def test_scope_accepts_one_to_four_optional_signals() -> None:
    from app.core.blocks import ScopeBlock

    source = make_signal()
    assert ScopeBlock().execute([source, None, None, None]) == []
    with pytest.raises(BlockError, match="at least 1"):
        ScopeBlock().execute([None, None, None, None])


def test_parameter_schema_validation_rejects_out_of_range_and_invalid_choice() -> None:
    from app.core.blocks import BlockError, FFTBlock, MovingAverageBlock
    import pytest

    with pytest.raises(BlockError, match="at least"):
        MovingAverageBlock(window_samples=0).execute([make_signal()])
    with pytest.raises(BlockError, match="one of"):
        FFTBlock(window="not-a-window").execute([make_signal()])
