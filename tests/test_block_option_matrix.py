# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from app.core.blocks import BLOCK_TYPES, BlockError, create_block
from app.core.models import ScalarResult, SignalData, SpectrogramData, SpectrumData, TableResult


def _fixtures() -> tuple[SignalData, SignalData, SpectrumData, SpectrogramData, TableResult, ScalarResult]:
    sample_rate = 1000.0
    time = np.arange(4000, dtype=float) / sample_rate
    first = SignalData(
        2.0 + np.sin(2 * np.pi * 10 * time) + 0.2 * np.sin(2 * np.pi * 100 * time),
        time,
        name="A",
        unit="V",
        sample_rate=sample_rate,
    )
    second = SignalData(
        1.0 + 0.5 * np.sin(2 * np.pi * 10 * time + 0.2),
        time,
        name="B",
        unit="V",
        sample_rate=sample_rate,
    )
    spectrum = SpectrumData(
        np.fft.rfftfreq(first.samples, 1.0 / sample_rate),
        np.abs(np.fft.rfft(first.values)),
        unit="V",
    )
    spectrogram = SpectrogramData(np.arange(4.0), np.arange(3.0), np.ones((4, 3)))
    table = TableResult(pd.DataFrame({"value": [1.0, 2.0]}))
    return first, second, spectrum, spectrogram, table, ScalarResult(1.0, "Scalar")


def _inputs(block, values: dict[str, object]) -> list[object | None]:
    required = block.input_count if block.minimum_inputs is None else block.minimum_inputs
    return [values[input_type] if index < required else None for index, input_type in enumerate(block.input_types[: block.input_count])]


def _base_parameters(type_name: str, parameter_names: set[str], tmp_path: Path, source_path: Path) -> dict[str, object]:
    parameters: dict[str, object] = {}
    if type_name == "import_data":
        parameters.update(file_path=str(source_path), time_column="time", signal_columns="a")
    if type_name.startswith("export_"):
        extension = {"export_data": ".csv", "export_plot": ".png", "export_report": ".html"}[type_name]
        parameters["file_path"] = str(tmp_path / f"{type_name}{extension}")
    if type_name == "python_script":
        parameters["acknowledge_restrictions"] = True
    if type_name == "trigger_extraction":
        parameters.update(threshold=2.1, pre_samples=0, post_samples=20)
    if "cutoff" in parameter_names:
        parameters["cutoff"] = 50.0
    if "lower_cutoff" in parameter_names:
        parameters["lower_cutoff"] = 20.0
    if "upper_cutoff" in parameter_names:
        parameters["upper_cutoff"] = 80.0
    return parameters


def test_every_choice_and_boolean_processing_branch_executes(tmp_path: Path) -> None:
    """Exercise every declared choice and boolean branch with valid representative data."""

    first, second, spectrum, spectrogram, table, scalar = _fixtures()
    values: dict[str, object] = {
        "signal": first,
        "scalar": scalar,
        "table": table,
        "spectrum": spectrum,
        "spectrogram": spectrogram,
        "any": first,
    }
    source_path = tmp_path / "source.csv"
    pd.DataFrame({"time": first.time[:100], "a": first.values[:100]}).to_csv(source_path, index=False)
    datetime_path = tmp_path / "datetime.csv"
    datetime_values = pd.date_range("2026-01-01", periods=100, freq="10ms", tz="UTC")
    pd.DataFrame({"time": datetime_values.astype(str), "a": first.values[:100]}).to_csv(datetime_path, index=False)
    datetime_signal = SignalData(
        first.values[:100],
        np.arange(100, dtype=float) / 100.0,
        name="A",
        unit="V",
        sample_rate=100.0,
        attributes={"time_origin_utc": datetime_values[0].isoformat(), "time_representation": "datetime"},
    )
    missing_signal = SignalData(
        np.array([0.0, 1.0, np.nan, 9.0, 16.0, 25.0]),
        np.arange(6, dtype=float),
        sample_rate=1.0,
    )
    step_signal = SignalData(
        np.r_[np.zeros(500), np.ones(3500)],
        first.time,
        name="Step response",
        unit="V",
        sample_rate=first.sample_rate,
    )

    exercised = 0
    for type_name, block_class in sorted(BLOCK_TYPES.items()):
        if block_class.category == "Tests":
            continue
        parameter_names = {parameter.name for parameter in block_class.parameters}
        branch_specs = [parameter for parameter in block_class.parameters if parameter.kind in {"choice", "bool"}]
        for spec in branch_specs:
            alternatives: tuple[object, ...] = spec.choices if spec.kind == "choice" else (False, True)
            for alternative in alternatives:
                parameters = _base_parameters(type_name, parameter_names, tmp_path, source_path)
                parameters[spec.name] = alternative

                if type_name == "import_data" and spec.name == "time_mode" and alternative == "datetime":
                    parameters["file_path"] = str(datetime_path)
                if type_name == "chirp" and alternative in {"logarithmic", "hyperbolic"}:
                    parameters.update(frequency=10.0, end_frequency=100.0)
                if type_name == "fir_filter" and parameters.get("mode") in {"highpass", "bandstop"}:
                    parameters["taps"] = 101
                if spec.name == "initial_conditions":
                    parameters["zero_phase"] = False
                if spec.name == "edge_padding":
                    parameters["zero_phase"] = True
                if type_name == "unit_conversion" and spec.name == "automatic" and alternative is True:
                    parameters.update(source_unit="V", target_unit="mV")
                if type_name in {"scope", "multi_signal_scope"} and spec.name == "auto_scale" and alternative is False:
                    parameters.update(x_min="0", x_max="1", y_min="-1", y_max="3")

                # Give each export branch a unique destination and suitable datetime metadata.
                if type_name.startswith("export_"):
                    extension = {"export_data": ".csv", "export_plot": ".png", "export_report": ".html"}[type_name]
                    parameters["file_path"] = str(tmp_path / f"{type_name}_{spec.name}_{alternative}{extension}")

                block = create_block(type_name, parameters)
                block_inputs = _inputs(block, values)
                if type_name in {"signal_to_noise_ratio", "linear_regression", "cross_correlation", "align_cross_correlation", "align_peak", "synchronise_signals"}:
                    block_inputs = [first, second]
                elif type_name == "missing_value_interpolation":
                    block_inputs = [missing_signal]
                elif type_name == "spectrum_analyser":
                    block_inputs = [first, None]
                elif type_name == "export_data" and spec.name == "time_representation" and alternative == "datetime_iso":
                    block_inputs = [datetime_signal, None, None, None]
                elif type_name == "publish_metric" and spec.name == "aggregation" and alternative in {"rise_time", "settling_time"}:
                    block_inputs = [step_signal]

                if type_name == "python_script" and spec.name == "acknowledge_restrictions" and alternative is False:
                    try:
                        block.execute(block_inputs)
                    except BlockError as exc:
                        assert "Acknowledge" in str(exc)
                    else:
                        raise AssertionError("Restricted Python block must require acknowledgement")
                else:
                    outputs = block.execute(block_inputs)
                    assert isinstance(outputs, list), (type_name, spec.name, alternative)
                    assert len(outputs) == block.output_count, (type_name, spec.name, alternative)
                exercised += 1

    # Guards against accidentally reducing the audit matrix when schemas change.
    assert exercised >= 230


def test_blocks_fail_readably_for_complex_missing_and_irregular_inputs() -> None:
    """No built-in processing block may leak an unhandled library exception."""

    first, second, spectrum, spectrogram, table, scalar = _fixtures()
    irregular_time = np.cumsum(np.r_[0.0, np.where(np.arange(first.samples - 1) % 2, 0.0009, 0.0011)])
    variants = {
        "complex": SignalData(first.values + 0.2j * second.values, first.time, name="complex", unit="V", sample_rate=first.sample_rate),
        "missing": SignalData(np.where(np.arange(first.samples) == first.samples // 2, np.nan, first.values), first.time, name="missing", unit="V", sample_rate=first.sample_rate),
        "irregular": SignalData(first.values.copy(), irregular_time, name="irregular", unit="V"),
    }

    for variant_name, variant in variants.items():
        values: dict[str, object] = {
            "signal": variant,
            "scalar": scalar,
            "table": table,
            "spectrum": spectrum,
            "spectrogram": spectrogram,
            "any": variant,
        }
        for type_name, block_class in sorted(BLOCK_TYPES.items()):
            if type_name in {"import_data", "export_data", "export_plot", "export_report"} or block_class.category == "Tests":
                continue
            parameters: dict[str, object] = {}
            if type_name == "python_script":
                parameters["acknowledge_restrictions"] = True
            if type_name == "trigger_extraction":
                parameters.update(threshold=2.1, pre_samples=0, post_samples=20)
            block = create_block(type_name, parameters)
            block_inputs = _inputs(block, values)
            if type_name in {"signal_to_noise_ratio", "linear_regression", "cross_correlation", "align_cross_correlation", "align_peak", "synchronise_signals"}:
                block_inputs = [variant, second]
            elif type_name == "spectrum_analyser":
                block_inputs = [variant, None]
            try:
                outputs = block.execute(block_inputs)
                assert isinstance(outputs, list), (variant_name, type_name)
                assert len(outputs) == block.output_count, (variant_name, type_name)
            except BlockError:
                # Domain/type rejection is expected for many blocks; the contract is
                # that users receive a readable BlockError instead of a raw NumPy,
                # SciPy or pandas exception.
                pass
