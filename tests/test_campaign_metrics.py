# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.campaign.metrics import aggregate_metric
from app.core.blocks import BlockError, create_block
from app.core.models import ScalarResult, SignalData, SpectrumData, TableResult


def signal(values: np.ndarray, sample_rate: float = 100.0, unit: str = "A") -> SignalData:
    values = np.asarray(values, dtype=float)
    return SignalData(values, np.arange(len(values), dtype=float) / sample_rate, name="Current", unit=unit, sample_rate=sample_rate)


def test_signal_metric_aggregations() -> None:
    item = signal(np.array([1.0, 2.0, 3.0, 4.0]))
    expected = {
        "mean": 2.5,
        "rms": np.sqrt(7.5),
        "standard_deviation": np.std([1, 2, 3, 4]),
        "minimum": 1.0,
        "maximum": 4.0,
        "peak_to_peak": 3.0,
        "sample_count": 4,
        "duration": 0.03,
        "first": 1.0,
        "last": 4.0,
    }
    for aggregation, value in expected.items():
        actual, _unit, _description = aggregate_metric(item, aggregation)
        assert actual == pytest.approx(value)
    custom, _, _ = aggregate_metric(item, "custom_expression", expression="rms / maximum")
    assert custom == pytest.approx(np.sqrt(7.5) / 4.0)


def test_frequency_rise_and_settling_metrics() -> None:
    fs = 1000.0
    time = np.arange(1000) / fs
    sine = SignalData(np.sin(2 * np.pi * 37 * time), time, sample_rate=fs)
    dominant, unit, _ = aggregate_metric(sine, "dominant_frequency")
    assert dominant == pytest.approx(37.0, abs=1.0)
    assert unit == "Hz"
    step_values = np.zeros(1000)
    ramp = np.linspace(0, 1, 101)
    step_values[100:201] = ramp
    step_values[201:] = 1.0
    step = SignalData(step_values, time, sample_rate=fs)
    rise, _, _ = aggregate_metric(step, "rise_time")
    settle, _, _ = aggregate_metric(step, "settling_time")
    assert rise == pytest.approx(0.08, abs=0.003)
    assert settle >= rise


def test_scalar_table_and_spectrum_metrics() -> None:
    scalar, unit, _ = aggregate_metric(ScalarResult(3.5, "Metric", "V"), "value")
    assert scalar == 3.5 and unit == "V"
    table, _, _ = aggregate_metric(TableResult(pd.DataFrame([[7.0]]), metadata={"unit": "N"}), "auto")
    assert table == 7.0
    spectrum = SpectrumData(np.array([0.0, 10.0, 20.0]), np.array([1.0, 8.0, 2.0]))
    frequency, unit, _ = aggregate_metric(spectrum, "dominant_frequency")
    assert frequency == 10.0 and unit == "Hz"
    with pytest.raises(ValueError, match="exactly one cell"):
        aggregate_metric(TableResult(pd.DataFrame([[1, 2]])), "auto")


def test_nonfinite_and_irregular_frequency_metrics_are_rejected() -> None:
    with pytest.raises(ValueError, match="no finite"):
        aggregate_metric(signal(np.array([np.nan, np.inf])), "mean")
    irregular = SignalData(np.array([1.0, 2.0, 3.0]), np.array([0.0, 0.01, 0.03]))
    with pytest.raises(ValueError, match="uniformly sampled"):
        aggregate_metric(irregular, "dominant_frequency")


def test_publish_metric_block_metadata_and_validation() -> None:
    block = create_block("publish_metric", {
        "metric_name": "rms_current", "display_label": "RMS current", "unit": "A",
        "aggregation": "rms", "number_format": ".3f",
    })
    output = block.execute([signal(np.array([3.0, 4.0]))])[0]
    assert isinstance(output, ScalarResult)
    assert output.value == pytest.approx(np.sqrt(12.5))
    assert output.metadata["published_metric"] is True
    assert output.metadata["metric_name"] == "rms_current"
    with pytest.raises(BlockError, match="not suitable"):
        create_block("publish_metric", {"metric_name": "bad", "aggregation": "mean"}).execute([
            TableResult(pd.DataFrame([[1, 2]]))
        ])
