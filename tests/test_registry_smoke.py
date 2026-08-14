# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.core.blocks import BLOCK_TYPES, create_block
from app.core.models import ScalarResult, SignalData, SpectrogramData, SpectrumData, TableResult


def _sample_values() -> tuple[SignalData, SignalData, SpectrumData, SpectrogramData, TableResult]:
    sample_rate = 1000.0
    time = np.arange(1000, dtype=float) / sample_rate
    first = SignalData(
        2.0 + np.sin(2 * np.pi * 5 * time) + 0.1 * np.sin(2 * np.pi * 50 * time),
        time,
        name="A",
        unit="V",
        sample_rate=sample_rate,
    )
    second = SignalData(
        1.0 + 0.5 * np.sin(2 * np.pi * 5 * time + 0.2),
        time,
        name="B",
        unit="V",
        sample_rate=sample_rate,
    )
    spectrum = SpectrumData(
        np.fft.rfftfreq(first.samples, 1 / sample_rate),
        np.abs(np.fft.rfft(first.values)),
        name="Spectrum",
        unit="V",
    )
    spectrogram = SpectrogramData(
        np.linspace(0, sample_rate / 2, 20),
        np.linspace(0, 1, 10),
        np.ones((20, 10)),
        name="Spectrogram",
    )
    table = TableResult(pd.DataFrame({"value": [1.0, 2.0]}), name="Table")
    return first, second, spectrum, spectrogram, table


def test_every_registered_block_constructs_and_executes_with_valid_inputs(tmp_path: Path) -> None:
    """Exercise every built-in block with a valid representative input.

    This is deliberately broad rather than numerically exhaustive. Dedicated tests
    cover the numerical behaviour of the important filters and analyses.
    """

    first, second, spectrum, spectrogram, table = _sample_values()
    dimensionless = SignalData(first.values.copy(), first.time.copy(), name="dimensionless", unit="", sample_rate=first.sample_rate)
    source_path = tmp_path / "source.csv"
    pd.DataFrame({"time": first.time, "a": first.values, "b": second.values}).to_csv(source_path, index=False)

    values = {
        "signal": first,
        "scalar": ScalarResult(1.0, "Scalar"),
        "table": table,
        "spectrum": spectrum,
        "spectrogram": spectrogram,
        "any": first,
    }

    for type_name, block_class in sorted(BLOCK_TYPES.items()):
        # Third-party plugins loaded by another test are outside this built-in smoke
        # matrix. Their own plugin test checks registration and execution.
        if block_class.category == "Tests":
            continue

        parameter_names = {parameter.name for parameter in block_class.parameters}
        parameters: dict[str, object] = {}
        if type_name == "import_data":
            parameters.update(
                file_path=str(source_path),
                time_column="time",
                signal_columns="a,b",
                sample_rate=1000.0,
            )
        if "file_path" in parameter_names and type_name.startswith("export_"):
            extension = {"export_data": ".csv", "export_plot": ".png", "export_report": ".html"}[type_name]
            parameters["file_path"] = str(tmp_path / f"{type_name}{extension}")
        if type_name == "python_script":
            parameters["acknowledge_restrictions"] = True
        if type_name == "trigger_extraction":
            parameters.update(threshold=2.1, pre_samples=0, post_samples=20)

        block = create_block(type_name, parameters)
        inputs: list[object | None] = []
        required_count = block.input_count if block.minimum_inputs is None else block.minimum_inputs
        for index, input_type in enumerate(block.input_types[: block.input_count]):
            if index >= required_count:
                inputs.append(None)
            elif input_type == "signal":
                if type_name in {"logarithm", "exponential"}:
                    inputs.append(dimensionless)
                else:
                    inputs.append(first if index % 2 == 0 else second)
            else:
                inputs.append(values[input_type])

        outputs = block.execute(inputs)
        assert isinstance(outputs, list), type_name
        assert len(outputs) == block.output_count, type_name
