# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.core.blocks import (
    BLOCK_TYPES,
    BlockError,
    ExportDataBlock,
    FFTBlock,
    FIRFilterBlock,
    ImportDataBlock,
    MissingValueInterpolationBlock,
    NotchFilterBlock,
    SignalToNoiseRatioBlock,
    create_block,
)
from app.core.models import SignalData, SpectrumData
from app.core.workflow import WorkflowGraph, WorkflowNode


def signal(
    values: np.ndarray | list[float] | list[complex],
    *,
    sample_rate: float = 1000.0,
    unit: str = "V",
    name: str = "signal",
) -> SignalData:
    array = np.asarray(values)
    time = np.arange(len(array), dtype=float) / sample_rate
    return SignalData(array, time, name=name, unit=unit, sample_rate=sample_rate)


def multitone(sample_rate: float = 1000.0, duration: float = 4.0) -> SignalData:
    time = np.arange(int(sample_rate * duration), dtype=float) / sample_rate
    values = (
        np.sin(2 * np.pi * 10 * time)
        + np.sin(2 * np.pi * 60 * time)
        + np.sin(2 * np.pi * 200 * time)
    )
    return SignalData(values, time, unit="V", sample_rate=sample_rate)


def response_at(block_type: str, parameters: dict[str, object], frequency: float, sample_rate: float = 1000.0) -> float:
    block = create_block(block_type, parameters)
    frequencies, response = block.frequency_response(sample_rate, points=32768)  # type: ignore[attr-defined]
    return float(np.abs(response[np.argmin(np.abs(frequencies - frequency))]))


def test_every_parameter_schema_is_internally_consistent() -> None:
    supported_types = {"any", "signal", "scalar", "table", "spectrum", "spectrogram"}
    for type_name, block_type in BLOCK_TYPES.items():
        names = [spec.name for spec in block_type.parameters]
        assert len(names) == len(set(names)), type_name
        assert block_type.input_count >= 0 and block_type.output_count >= 0
        assert set(block_type.input_types).issubset(supported_types), type_name
        assert set(block_type.output_types).issubset(supported_types), type_name
        if block_type.input_count:
            assert block_type.input_types, type_name
        if block_type.output_count:
            assert block_type.output_types, type_name
        by_name = {spec.name: spec for spec in block_type.parameters}
        for spec in block_type.parameters:
            if spec.kind == "choice":
                assert spec.default in spec.choices, (type_name, spec.name)
            if spec.minimum is not None and isinstance(spec.default, (int, float)):
                assert spec.default >= spec.minimum, (type_name, spec.name)
            if spec.maximum is not None and isinstance(spec.default, (int, float)):
                assert spec.default <= spec.maximum, (type_name, spec.name)
            for dependency, accepted in spec.visible_when:
                assert dependency in by_name, (type_name, spec.name, dependency)
                dependency_spec = by_name[dependency]
                if dependency_spec.kind == "choice":
                    assert set(accepted).issubset(set(dependency_spec.choices))
                if dependency_spec.kind == "bool":
                    assert set(accepted).issubset({True, False})


def test_filter_schemas_show_only_relevant_cutoffs() -> None:
    assert [spec.name for spec in BLOCK_TYPES["low_pass"].parameters if "cutoff" in spec.name] == ["cutoff"]
    assert [spec.name for spec in BLOCK_TYPES["high_pass"].parameters if "cutoff" in spec.name] == ["cutoff"]
    assert [spec.name for spec in BLOCK_TYPES["band_pass"].parameters if "cutoff" in spec.name] == ["lower_cutoff", "upper_cutoff"]
    assert [spec.name for spec in BLOCK_TYPES["band_stop"].parameters if "cutoff" in spec.name] == ["lower_cutoff", "upper_cutoff"]

    configurable = create_block("butter_filter", {"mode": "lowpass"})
    visibility = {spec.name: spec.is_visible(configurable.params) for spec in configurable.parameters}
    assert visibility["cutoff"] and not visibility["lower_cutoff"] and not visibility["upper_cutoff"]
    configurable.params["mode"] = "bandpass"
    visibility = {spec.name: spec.is_visible(configurable.params) for spec in configurable.parameters}
    assert not visibility["cutoff"] and visibility["lower_cutoff"] and visibility["upper_cutoff"]


def test_filter_family_specific_parameters_are_not_exposed_when_unused() -> None:
    assert "ripple" not in {p.name for p in BLOCK_TYPES["butter_filter"].parameters}
    assert "attenuation" not in {p.name for p in BLOCK_TYPES["butter_filter"].parameters}
    assert "ripple" in {p.name for p in BLOCK_TYPES["cheby1_filter"].parameters}
    assert "attenuation" not in {p.name for p in BLOCK_TYPES["cheby1_filter"].parameters}
    assert "ripple" not in {p.name for p in BLOCK_TYPES["cheby2_filter"].parameters}
    assert "attenuation" in {p.name for p in BLOCK_TYPES["cheby2_filter"].parameters}
    assert {"ripple", "attenuation"}.issubset({p.name for p in BLOCK_TYPES["ellip_filter"].parameters})
    assert not ({"ripple", "attenuation"} & {p.name for p in BLOCK_TYPES["bessel_filter"].parameters})


def test_butterworth_filter_modes_have_correct_frequency_regions() -> None:
    assert response_at("low_pass", {"cutoff": 30.0, "order": 4}, 10.0) > 0.95
    assert response_at("low_pass", {"cutoff": 30.0, "order": 4}, 200.0) < 0.01
    assert response_at("high_pass", {"cutoff": 30.0, "order": 4}, 5.0) < 0.01
    assert response_at("high_pass", {"cutoff": 30.0, "order": 4}, 200.0) > 0.95
    assert response_at("band_pass", {"lower_cutoff": 40.0, "upper_cutoff": 80.0, "order": 4}, 60.0) > 0.95
    assert response_at("band_pass", {"lower_cutoff": 40.0, "upper_cutoff": 80.0, "order": 4}, 10.0) < 0.02
    assert response_at("band_stop", {"lower_cutoff": 40.0, "upper_cutoff": 80.0, "order": 4}, 60.0) < 0.02
    assert response_at("band_stop", {"lower_cutoff": 40.0, "upper_cutoff": 80.0, "order": 4}, 200.0) > 0.95


@pytest.mark.parametrize("family", ["butter_filter", "cheby1_filter", "cheby2_filter", "ellip_filter", "bessel_filter"])
@pytest.mark.parametrize(
    ("mode", "cutoffs"),
    [
        ("lowpass", {"cutoff": 80.0}),
        ("highpass", {"cutoff": 20.0}),
        ("bandpass", {"lower_cutoff": 20.0, "upper_cutoff": 100.0}),
        ("bandstop", {"lower_cutoff": 40.0, "upper_cutoff": 80.0}),
    ],
)
def test_all_iir_families_design_stable_filters(family: str, mode: str, cutoffs: dict[str, float]) -> None:
    block = create_block(family, {"mode": mode, "order": 4, **cutoffs})
    stable, maximum_pole = block.stability(1000.0)  # type: ignore[attr-defined]
    assert stable and maximum_pole < 1.0
    frequencies, response = block.frequency_response(1000.0)  # type: ignore[attr-defined]
    assert len(frequencies) == len(response)
    assert np.all(np.isfinite(response))


def test_fir_tap_parity_rules_match_firwin() -> None:
    lowpass = FIRFilterBlock(mode="lowpass", cutoff=50.0, taps=100, zero_phase=False)
    assert len(lowpass.design(1000.0)) == 100
    bandpass = FIRFilterBlock(mode="bandpass", lower_cutoff=20.0, upper_cutoff=80.0, taps=100, zero_phase=False)
    assert len(bandpass.design(1000.0)) == 100
    with pytest.raises(BlockError, match="odd tap count"):
        FIRFilterBlock(mode="highpass", cutoff=50.0, taps=100).design(1000.0)
    with pytest.raises(BlockError, match="odd tap count"):
        FIRFilterBlock(mode="bandstop", lower_cutoff=20.0, upper_cutoff=80.0, taps=100).design(1000.0)


def test_notch_validation_and_short_signal_errors_are_readable() -> None:
    with pytest.raises(BlockError, match="Nyquist"):
        NotchFilterBlock(frequency=600.0).frequency_response(1000.0)
    short = signal([1.0, 2.0, 3.0, 4.0], sample_rate=1000.0)
    with pytest.raises(BlockError, match="too short"):
        NotchFilterBlock(frequency=50.0, zero_phase=True).execute([short])


def test_specialised_generator_schemas_and_values() -> None:
    assert "frequency" not in {p.name for p in BLOCK_TYPES["step"].parameters}
    assert "frequency" not in {p.name for p in BLOCK_TYPES["ramp"].parameters}
    assert "frequency" not in {p.name for p in BLOCK_TYPES["white_noise"].parameters}
    assert "value" not in {p.name for p in BLOCK_TYPES["time_vector"].parameters}

    step = create_block("step", {"initial_value": -2.0, "final_value": 3.0, "step_time": 0.4, "sample_rate": 10.0, "duration": 1.0}).execute([])[0]
    np.testing.assert_allclose(step.values[:4], -2.0)
    np.testing.assert_allclose(step.values[4:], 3.0)

    ramp = create_block("ramp", {"initial_value": 2.0, "slope": 3.0, "sample_rate": 10.0, "duration": 1.0}).execute([])[0]
    np.testing.assert_allclose(ramp.values, 2.0 + 3.0 * ramp.time)

    pulse = create_block("pulse", {"frequency": 10.0, "duty_cycle": 25.0, "sample_rate": 1000.0, "duration": 2.0}).execute([])[0]
    assert np.mean(pulse.values) == pytest.approx(0.25, abs=0.02)


def test_generators_reject_aliasing_and_invalid_chirps() -> None:
    with pytest.raises(BlockError, match="Nyquist"):
        create_block("sine", {"frequency": 500.0, "sample_rate": 1000.0}).execute([])
    with pytest.raises(BlockError, match="Nyquist"):
        create_block("chirp", {"frequency": 10.0, "end_frequency": 600.0, "sample_rate": 1000.0}).execute([])
    with pytest.raises(BlockError, match="positive"):
        create_block("chirp", {"frequency": 0.0, "end_frequency": 100.0, "method": "logarithmic"}).execute([])


def test_noise_generators_are_repeatable_and_use_clear_amplitude_semantics() -> None:
    first = create_block("white_noise", {"seed": 42, "amplitude": 2.0, "sample_rate": 1000.0, "duration": 2.0}).execute([])[0]
    second = create_block("white_noise", {"seed": 42, "amplitude": 2.0, "sample_rate": 1000.0, "duration": 2.0}).execute([])[0]
    np.testing.assert_allclose(first.values, second.values)
    assert np.max(np.abs(first.values)) <= 2.0

    gaussian = create_block("gaussian_noise", {"seed": 4, "amplitude": 3.0, "sample_rate": 5000.0, "duration": 2.0}).execute([])[0]
    assert np.std(gaussian.values) == pytest.approx(3.0, rel=0.06)


def test_unit_metadata_for_mathematical_blocks() -> None:
    source = signal([1.0, 4.0, 9.0], sample_rate=1.0, unit="V²")
    square_root = create_block("square_root").execute([source])[0]
    assert square_root.unit == "sqrt(V²)"

    volts = signal([1.0, 2.0, 3.0], sample_rate=1.0, unit="V")
    squared = create_block("power", {"exponent": 2.0}).execute([volts])[0]
    assert squared.unit == "V²"
    normalised = create_block("normalise").execute([volts])[0]
    assert normalised.unit == ""
    with pytest.raises(BlockError, match="dimensionless"):
        create_block("logarithm").execute([volts])


def test_unit_sensitive_blocks_reject_unknown_known_mixes() -> None:
    known = signal([1.0, 2.0, 3.0], sample_rate=1.0, unit="V")
    unknown = signal([1.0, 2.0, 3.0], sample_rate=1.0, unit="")
    with pytest.raises(BlockError, match="incompatible units"):
        create_block("add").execute([known, unknown, None, None])
    with pytest.raises(BlockError, match="incompatible units"):
        SignalToNoiseRatioBlock().execute([known, unknown])


def test_real_only_blocks_reject_complex_inputs_readably() -> None:
    complex_signal = signal(np.exp(1j * np.linspace(0, 1, 32)), sample_rate=32.0)
    for type_name in ("minimum", "maximum", "clamp", "normalise", "threshold", "median_filter", "savitzky_golay", "histogram"):
        block = create_block(type_name)
        inputs = [complex_signal, complex_signal, None, None] if block.input_count == 4 else [complex_signal]
        with pytest.raises(BlockError, match="real-valued"):
            block.execute(inputs)


def test_irregular_time_does_not_claim_a_sample_rate() -> None:
    irregular = SignalData(np.arange(6.0), np.array([0.0, 0.1, 0.25, 0.5, 0.9, 1.4]))
    assert irregular.sample_rate is None
    downsampled = create_block("downsample", {"factor": 2}).execute([irregular])[0]
    assert downsampled.sample_rate is None
    with pytest.raises(ValueError, match="does not match"):
        SignalData(np.arange(4.0), np.arange(4.0) / 10.0, sample_rate=20.0)


def test_missing_value_interpolation_spline_and_import_time_validation(tmp_path: Path) -> None:
    source = signal([0.0, 1.0, np.nan, 9.0, 16.0, 25.0], sample_rate=1.0)
    interpolated = MissingValueInterpolationBlock(method="spline", spline_order=2).execute([source])[0]
    assert np.all(np.isfinite(interpolated.values))

    path = tmp_path / "bad_time.csv"
    pd.DataFrame({"time": [0.0, np.nan, 0.2], "value": [1.0, 2.0, 3.0]}).to_csv(path, index=False)
    with pytest.raises(BlockError, match="Time data"):
        ImportDataBlock(file_path=str(path), time_column="time", signal_columns="value", missing_policy="interpolate").execute([])


def test_median_filter_uses_nonzero_padding_at_edges() -> None:
    source = signal(np.ones(9), sample_rate=1.0)
    filtered = create_block("median_filter", {"kernel_size": 5, "edge_mode": "nearest"}).execute([source])[0]
    np.testing.assert_allclose(filtered.values, 1.0)


def test_trigger_post_samples_excludes_off_by_one() -> None:
    values = np.zeros(20)
    values[5:] = 1.0
    source = signal(values, sample_rate=10.0)
    extracted = create_block("trigger_extraction", {"threshold": 0.5, "pre_samples": 2, "post_samples": 4}).execute([source])[0]
    assert extracted.samples == 2 + 1 + 4
    assert extracted.time[2] == pytest.approx(0.0)


def test_complex_fft_psd_and_stft_are_two_sided_and_sorted() -> None:
    sample_rate = 1000.0
    time = np.arange(2000, dtype=float) / sample_rate
    source = SignalData(np.exp(1j * 2 * np.pi * 75.0 * time), time, unit="V", sample_rate=sample_rate)

    fft = FFTBlock(window="boxcar", detrend=False).execute([source])[0]
    assert isinstance(fft, SpectrumData)
    assert fft.metadata["one_sided"] is False
    assert np.all(np.diff(fft.frequency) > 0)
    assert fft.frequency[np.argmax(np.abs(fft.values))] == pytest.approx(75.0, abs=0.6)

    psd = create_block("power_spectral_density", {"segment_length": 512}).execute([source])[0]
    assert np.all(np.diff(psd.frequency) > 0)
    assert psd.frequency[0] < 0 < psd.frequency[-1]

    stft = create_block("short_time_fourier_transform", {"fft_size": 256}).execute([source])[0]
    assert np.all(np.diff(stft.frequency) > 0)
    assert stft.metadata["one_sided"] is False


def test_numpy_complex_import_and_lossless_export(tmp_path: Path) -> None:
    values = np.exp(1j * np.linspace(0.0, 2.0, 32))
    source_path = tmp_path / "complex.npy"
    np.save(source_path, values)
    imported = ImportDataBlock(file_path=str(source_path), sample_rate=100.0).execute([])[0]
    assert np.iscomplexobj(imported.values)
    np.testing.assert_allclose(imported.values, values)

    with pytest.raises(BlockError, match="Complex-valued"):
        ExportDataBlock(file_path=str(tmp_path / "complex.csv")).execute([imported, None, None, None])
    npz = tmp_path / "complex.npz"
    ExportDataBlock(file_path=str(npz)).execute([imported, None, None, None])
    with np.load(npz, allow_pickle=False) as archive:
        assert any(np.iscomplexobj(archive[key]) for key in archive.files)


def test_linear_regression_uses_paired_finite_rows() -> None:
    x = signal([0.0, 1.0, 2.0, 3.0], sample_rate=1.0, unit="s", name="x")
    y = signal([1.0, 3.0, np.nan, 7.0], sample_rate=1.0, unit="V", name="y")
    table, fitted = create_block("linear_regression").execute([x, y])
    metrics = dict(zip(table.frame["metric"], table.frame["value"], strict=True))
    assert metrics["slope"] == pytest.approx(2.0)
    assert metrics["intercept"] == pytest.approx(1.0)
    assert metrics["paired_samples"] == 3
    assert fitted.unit == "V"


def test_histogram_labels_density_output_correctly() -> None:
    result = create_block("histogram", {"bins": 5, "density": True}).execute([signal(np.arange(10.0), sample_rate=1.0, unit="V")])[0]
    assert "density" in result.frame.columns and "count" not in result.frame.columns
    assert result.metadata["value_unit"] == "1/V"


class _BadOutputBlock:
    """Minimal block-like object used to verify runtime output contracts."""

    type_name = "bad_output"
    display_name = "Bad Output"
    input_count = 0
    minimum_inputs = None
    output_count = 1
    input_types: tuple[str, ...] = ()
    output_types = ("signal",)
    params: dict[str, object] = {}
    cacheable = False

    def serialise_params(self) -> dict[str, object]:
        return {}

    def execute(self, inputs: list[object]) -> list[object]:
        del inputs
        return ["not a signal"]


def test_workflow_rejects_runtime_output_type_mismatches() -> None:
    graph = WorkflowGraph()
    graph.add_node(WorkflowNode("bad", _BadOutputBlock()))  # type: ignore[arg-type]
    with pytest.raises(BlockError, match="declared type 'signal'"):
        graph.execute()


def test_hidden_parameters_do_not_invalidate_active_filter_mode() -> None:
    block = create_block(
        "butter_filter",
        {"mode": "lowpass", "cutoff": 50.0, "lower_cutoff": -10.0, "upper_cutoff": -5.0},
    )
    frequencies, response = block.frequency_response(1000.0)  # type: ignore[attr-defined]
    assert len(frequencies) == len(response)


def test_zero_phase_previews_match_forward_backward_response() -> None:
    causal = create_block("low_pass", {"cutoff": 40.0, "order": 3, "zero_phase": False})
    zero_phase = create_block("low_pass", {"cutoff": 40.0, "order": 3, "zero_phase": True})
    frequencies, causal_response = causal.frequency_response(1000.0)  # type: ignore[attr-defined]
    zero_frequencies, zero_response = zero_phase.frequency_response(1000.0)  # type: ignore[attr-defined]
    np.testing.assert_allclose(zero_frequencies, frequencies)
    np.testing.assert_allclose(zero_response, causal_response * np.conjugate(causal_response), rtol=1e-12, atol=1e-12)
    assert np.max(np.abs(np.angle(zero_response))) < 1e-12


def test_fft_power_spectrum_obeys_parseval_for_boxcar_sine() -> None:
    sample_rate = 1000.0
    time = np.arange(2000, dtype=float) / sample_rate
    source = SignalData(np.sin(2 * np.pi * 50.0 * time), time, unit="V", sample_rate=sample_rate)
    spectrum = FFTBlock(window="boxcar", detrend=False, output="power").execute([source])[0]
    assert np.sum(spectrum.values) == pytest.approx(np.mean(source.values**2), rel=1e-10, abs=1e-12)
    assert spectrum.unit == "V²"
    assert spectrum.metadata["normalisation"] == "mean-square power"


def test_stft_does_not_invent_zero_padded_time_frames() -> None:
    source = signal(np.sin(2 * np.pi * 5 * np.arange(1000) / 1000), sample_rate=1000.0)
    result = create_block("short_time_fourier_transform", {"fft_size": 256, "overlap_percent": 50.0}).execute([source])[0]
    assert result.time[0] >= source.time[0]
    assert result.time[-1] <= source.time[-1]


def test_complex_smoothing_preserves_real_and_imaginary_components() -> None:
    values = np.array([1 + 1j, 2 + 3j, 5 + 8j, 9 + 13j], dtype=complex)
    source = signal(values, sample_rate=10.0)
    moving = create_block("moving_average", {"window_samples": 3}).execute([source])[0]
    expected = np.array([(values[0] + values[1]) / 2, np.mean(values[:3]), np.mean(values[1:4]), np.mean(values[2:4])])
    np.testing.assert_allclose(moving.values, expected)
    ema = create_block("exponential_moving_average", {"alpha": 0.5}).execute([source])[0]
    expected_ema = np.empty_like(values)
    expected_ema[0] = values[0]
    for index in range(1, len(values)):
        expected_ema[index] = 0.5 * values[index] + 0.5 * expected_ema[index - 1]
    np.testing.assert_allclose(ema.values, expected_ema)


def test_threshold_preserves_missing_samples_instead_of_turning_them_into_zero() -> None:
    source = signal([np.nan, -1.0, 2.0], sample_rate=1.0)
    binary = create_block("threshold", {"threshold": 0.0, "mode": "binary", "high_value": 1.0}).execute([source])[0]
    assert np.isnan(binary.values[0])
    np.testing.assert_allclose(binary.values[1:], [0.0, 1.0])


def test_irregular_time_rejects_stale_explicit_sample_rate() -> None:
    with pytest.raises(ValueError, match="irregular time vector"):
        SignalData(np.arange(4.0), np.array([0.0, 0.1, 0.25, 0.4]), sample_rate=10.0)
    with pytest.raises(ValueError, match="finite"):
        SignalData(np.arange(3.0), np.arange(3.0), sample_rate=float("nan"))


def test_numpy_drop_policy_recomputes_sampling_metadata(tmp_path: Path) -> None:
    path = tmp_path / "missing.npy"
    np.save(path, np.array([1.0, np.nan, 3.0, 4.0]))
    output = ImportDataBlock(file_path=str(path), sample_rate=10.0, missing_policy="drop").execute([])[0]
    assert output.sample_rate is None
    np.testing.assert_allclose(output.time, [0.0, 0.2, 0.3])


def test_unknown_units_do_not_produce_false_derived_units() -> None:
    volts = signal([1.0, 2.0], sample_rate=1.0, unit="V")
    unknown = signal([2.0, 4.0], sample_rate=1.0, unit="")
    multiplied = create_block("multiply").execute([volts, unknown, None, None])[0]
    divided = create_block("divide").execute([volts, unknown, None, None])[0]
    assert multiplied.unit == ""
    assert divided.unit == ""


def test_custom_mathematical_signal_enforces_nyquist() -> None:
    with pytest.raises(BlockError, match="Nyquist"):
        create_block("custom_mathematical_signal", {"frequency": 600.0, "sample_rate": 1000.0}).execute([])


def test_custom_coefficients_reject_nonfinite_values() -> None:
    block = create_block("custom_filter_coefficients", {"b": "1, inf", "a": "1"})
    with pytest.raises(BlockError, match="finite"):
        block.frequency_response(1000.0)  # type: ignore[attr-defined]


def test_table_object_column_complex_export_is_not_silently_lossy(tmp_path: Path) -> None:
    from app.core.models import TableResult

    table = TableResult(pd.DataFrame({"mixed": pd.Series([1 + 2j, "label"], dtype=object)}))
    with pytest.raises(BlockError, match="Complex-valued"):
        ExportDataBlock(file_path=str(tmp_path / "table.csv")).execute([table, None, None, None])


def test_alias_categories_match_the_block_library() -> None:
    assert BLOCK_TYPES["clipping"].category == "Signal Conditioning"
    assert BLOCK_TYPES["smoothing"].category == "Signal Conditioning"


def test_npz_automatically_detects_a_standard_time_array(tmp_path: Path) -> None:
    path = tmp_path / "auto_time.npz"
    time = np.array([0.0, 0.1, 0.2, 0.3])
    np.savez(path, time=time, sensor=np.array([2.0, 3.0, 4.0, 5.0]))
    output = ImportDataBlock(file_path=str(path), signal_columns="sensor", auto_detect_time=True).execute([])[0]
    np.testing.assert_allclose(output.time, time)
    assert output.sample_rate == pytest.approx(10.0)


def test_interpolation_does_not_create_samples_outside_source_domain() -> None:
    source = SignalData(
        np.array([0.0, 1.0, 2.0]),
        np.array([0.0, 0.11, 0.26]),
        name="irregular",
    )
    result = create_block("interpolate", {"time_step": 0.1, "method": "linear"}).execute([source])[0]
    assert result.time[-1] <= source.time[-1]
    np.testing.assert_allclose(result.time, [0.0, 0.1, 0.2])


def test_synchronise_does_not_extrapolate_beyond_overlap() -> None:
    first = SignalData(np.arange(11.0), np.arange(11.0) / 10.0, sample_rate=10.0)
    second_time = np.arange(10.0) / 10.0 + 0.04
    second = SignalData(np.arange(10.0), second_time, sample_rate=10.0)
    first_sync, second_sync = create_block("synchronise_signals", {"target_rate": 10.0}).execute([first, second])
    overlap_end = min(first.time[-1], second.time[-1])
    assert first_sync.time[-1] <= overlap_end
    assert second_sync.time[-1] <= overlap_end


def test_npy_rejects_heterogeneous_tables_and_npz_remains_pickle_free(tmp_path: Path) -> None:
    from app.core.models import TableResult

    table = TableResult(pd.DataFrame({"label": ["a", "b"], "value": [1.0, 2.0]}))
    with pytest.raises(BlockError, match="homogeneous numeric"):
        ExportDataBlock(file_path=str(tmp_path / "mixed.npy")).execute([table, None, None, None])

    target = tmp_path / "mixed.npz"
    ExportDataBlock(file_path=str(target)).execute([table, None, None, None])
    with np.load(target, allow_pickle=False) as archive:
        np.testing.assert_array_equal(archive["label"], np.array(["a", "b"]))
        np.testing.assert_allclose(archive["value"], [1.0, 2.0])


def test_large_signal_signature_hashes_every_sample() -> None:
    # More than 16 MB exercises the former sampled-signature path.  Mutating an
    # interior sample that is not one of 4096 evenly spaced probes must invalidate
    # the cache signature.
    count = 2_100_000
    values = np.zeros(count, dtype=np.float64)
    time = np.arange(count, dtype=np.float64) / 1000.0
    first = SignalData(values, time, sample_rate=1000.0)
    signature_before = first.signature()
    values[1_234_567] = 1.0
    signature_after = first.signature()
    assert signature_before != signature_after


def test_result_signatures_include_schema_dtype_and_description() -> None:
    from app.core.models import ScalarResult, SpectrogramData, TableResult, result_signature

    scalar_a = ScalarResult(1.0, "Metric", description="first")
    scalar_b = ScalarResult(1.0, "Metric", description="second")
    assert scalar_a.signature() != scalar_b.signature()

    table_a = TableResult(pd.DataFrame({"a": [1, 2]}))
    table_b = TableResult(pd.DataFrame({"b": [1, 2]}))
    assert table_a.signature() != table_b.signature()
    assert TableResult(pd.DataFrame({"objects": [[1, 2], {"x": 1}]})).signature()

    assert result_signature(np.array([1], dtype=np.int64)) != result_signature(np.array([1.0], dtype=np.float64))

    spectrum_int = SpectrumData(np.array([0.0]), np.array([1], dtype=np.int64))
    spectrum_float = SpectrumData(np.array([0.0]), np.array([1.0], dtype=np.float64))
    assert spectrum_int.signature() != spectrum_float.signature()

    spectrogram = SpectrogramData(np.array([0.0, 1.0]), np.array([0.0, 1.0]), np.ones((2, 2)))
    assert spectrogram.signature()


def test_signal_named_time_does_not_overwrite_time_axis() -> None:
    source = signal([10.0, 20.0], sample_rate=2.0, name="time")
    frame = source.to_frame()
    assert list(frame.columns) == ["time", "time_2"]
    np.testing.assert_allclose(frame["time"], source.time)
    np.testing.assert_allclose(frame["time_2"], source.values)


def test_frequency_domain_models_reject_invalid_axes_and_values() -> None:
    from app.core.models import SpectrogramData

    with pytest.raises(ValueError, match="strictly increasing"):
        SpectrumData(np.array([0.0, 0.0]), np.ones(2))
    with pytest.raises(ValueError, match="numeric"):
        SpectrumData(np.array([0.0]), np.array(["bad"], dtype=object))
    with pytest.raises(ValueError, match="strictly increasing"):
        SpectrogramData(np.array([0.0, 1.0]), np.array([0.0, 0.0]), np.ones((2, 2)))


def test_custom_scalar_coefficients_support_causal_and_zero_phase_gain() -> None:
    source = signal([1.0, -2.0, 3.0], sample_rate=10.0)
    causal = create_block("custom_filter_coefficients", {"b": "2", "a": "1", "zero_phase": False}).execute([source])[0]
    zero_phase = create_block("custom_filter_coefficients", {"b": "2", "a": "1", "zero_phase": True}).execute([source])[0]
    np.testing.assert_allclose(causal.values, source.values * 2.0)
    np.testing.assert_allclose(zero_phase.values, source.values * 4.0)


def test_filter_edge_labels_match_family_semantics_and_bessel_cutoff_is_minus_3db() -> None:
    labels = {spec.name: spec.label for spec in BLOCK_TYPES["cheby1_filter"].parameters}
    assert labels["cutoff"].startswith("Passband edge")
    labels = {spec.name: spec.label for spec in BLOCK_TYPES["cheby2_filter"].parameters}
    assert labels["cutoff"].startswith("Stopband edge")
    labels = {spec.name: spec.label for spec in BLOCK_TYPES["bessel_filter"].parameters}
    assert labels["cutoff"].startswith("Cutoff")

    block = create_block("bessel_filter", {"mode": "lowpass", "cutoff": 50.0, "order": 4, "zero_phase": False})
    frequencies, response = block.frequency_response(1000.0)  # type: ignore[attr-defined]
    at_cutoff = np.abs(response[np.argmin(np.abs(frequencies - 50.0))])
    assert at_cutoff == pytest.approx(1.0 / np.sqrt(2.0), rel=0.02)


def test_hdf_series_import_and_preview_are_normalised_to_dataframes(tmp_path: Path) -> None:
    pytest.importorskip("tables")
    path = tmp_path / "series.h5"
    pd.Series([1.0, 2.0, 3.0], name="sensor").to_hdf(path, key="sensor")
    block = ImportDataBlock(file_path=str(path), dataset_key="sensor", signal_columns="sensor", sample_rate=10.0)
    preview = block.preview()
    assert isinstance(preview, pd.DataFrame)
    assert list(preview.columns) == ["sensor"]
    output = block.execute([])[0]
    np.testing.assert_allclose(output.values, [1.0, 2.0, 3.0])


def test_merge_signals_metadata_tracks_deduplicated_column_names() -> None:
    first = signal([1.0, 2.0], sample_rate=2.0, name="sensor", unit="V")
    second = signal([3.0, 4.0], sample_rate=2.0, name="sensor", unit="mV")
    result = create_block("merge_signals").execute([first, second, None, None])[0]
    assert list(result.frame.columns) == ["time", "sensor", "sensor_2"]
    assert result.metadata["units"] == {"sensor": "V", "sensor_2": "mV"}


def test_combined_export_rejects_subtly_misaligned_time_vectors() -> None:
    from app.core.models import signals_to_frame

    first = signal([1.0, 2.0, 3.0], sample_rate=10.0)
    shifted_time = first.time.copy()
    shifted_time[1] += 5e-7
    # Keep the perturbed vector strictly increasing and intentionally irregular.
    second = SignalData(first.values.copy(), shifted_time, name="other", unit="V")
    with pytest.raises(ValueError, match="same time vector"):
        signals_to_frame([first, second])


@pytest.mark.parametrize("window", ["boxcar", "hann", "hamming", "blackman", "flattop"])
def test_fft_power_spectrum_preserves_total_mean_square_for_every_window(window: str) -> None:
    sample_rate = 1024.0
    time = np.arange(2048, dtype=float) / sample_rate
    source = SignalData(np.sin(2 * np.pi * 64.0 * time), time, unit="V", sample_rate=sample_rate)
    spectrum = FFTBlock(window=window, detrend=False, output="power").execute([source])[0]
    assert np.sum(spectrum.values) == pytest.approx(np.mean(source.values**2), rel=1e-10, abs=1e-12)


def test_frequency_band_energy_distinguishes_energy_from_mean_square_power() -> None:
    sample_rate = 1000.0
    time = np.arange(2000, dtype=float) / sample_rate
    values = 2.0 + np.sin(2 * np.pi * 50.0 * time)
    source = SignalData(values, time, unit="V", sample_rate=sample_rate)

    mean_square = create_block(
        "frequency_band_energy",
        {"lower_frequency": 0.0, "upper_frequency": sample_rate / 2, "quantity": "mean-square power"},
    ).execute([source])[0]
    energy = create_block(
        "frequency_band_energy",
        {"lower_frequency": 0.0, "upper_frequency": sample_rate / 2, "quantity": "energy"},
    ).execute([source])[0]

    expected_mean_square = float(np.mean(np.abs(values) ** 2))
    expected_energy = float(np.sum(np.abs(values) ** 2) / sample_rate)
    assert mean_square.value == pytest.approx(expected_mean_square, rel=1e-12)
    assert mean_square.unit == "V²"
    assert energy.value == pytest.approx(expected_energy, rel=1e-12)
    assert energy.unit == "V²·s"


def test_frequency_band_energy_supports_signed_complex_bands() -> None:
    sample_rate = 1000.0
    time = np.arange(2000, dtype=float) / sample_rate
    source = SignalData(np.exp(-1j * 2 * np.pi * 75.0 * time), time, unit="V", sample_rate=sample_rate)
    negative = create_block(
        "frequency_band_energy",
        {"lower_frequency": -80.0, "upper_frequency": -70.0, "quantity": "mean-square power"},
    ).execute([source])[0]
    positive = create_block(
        "frequency_band_energy",
        {"lower_frequency": 70.0, "upper_frequency": 80.0, "quantity": "mean-square power"},
    ).execute([source])[0]
    assert negative.value == pytest.approx(1.0, rel=1e-10)
    assert positive.value < 1e-20
