# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.core.blocks import (
    BLOCK_TYPES,
    BandPassBlock,
    BlockError,
    CustomFormulaBlock,
    CustomMathematicalSignalBlock,
    DescriptiveStatisticsBlock,
    FFTBlock,
    FrequencyBandEnergyBlock,
    HistogramBlock,
    ImportDataBlock,
    LinearRegressionBlock,
    ManualSignalGeneratorBlock,
    NotchFilterBlock,
    PeakDetectionBlock,
    PowerSpectralDensityBlock,
    ResampleBlock,
    ShortTimeFourierTransformBlock,
    SignalToNoiseRatioBlock,
    SpectrogramBlock,
    SynchroniseSignalsBlock,
    create_block,
)
from app.core.models import SignalData, SpectrogramData, SpectrumData, TableResult


def sine_signal(frequency: float = 12.0, sample_rate: float = 1000.0, duration: float = 2.0) -> SignalData:
    time = np.arange(int(sample_rate * duration)) / sample_rate
    return SignalData(np.sin(2 * np.pi * frequency * time), time, name="sine", unit="V", sample_rate=sample_rate)


def test_registry_has_professional_coverage() -> None:
    assert len(BLOCK_TYPES) >= 110
    for required in ("high_pass", "band_pass", "notch_filter", "fir_filter", "spectrogram", "custom_formula", "export_report", "synchronise_signals"):
        assert required in BLOCK_TYPES


def test_manual_and_custom_signal_generators() -> None:
    manual = ManualSignalGeneratorBlock(values="1, 2, 3", sample_rate=10, name="manual").execute([])[0]
    assert manual.samples == 3
    custom = CustomMathematicalSignalBlock(formula="amplitude*sin(2*pi*frequency*t)", amplitude=2, frequency=5, sample_rate=1000, duration=1).execute([])[0]
    assert np.max(custom.values) == pytest.approx(2.0, rel=1e-3)


def test_custom_formula_is_safe_and_vectorised() -> None:
    source = sine_signal()
    output = CustomFormulaBlock(formula="output = where(input_1 > 0, input_1 * 2, 0)").execute([source, None, None, None])[0]
    assert np.all(output.values[source.values <= 0] == 0)
    with pytest.raises(BlockError, match="unsupported|approved|Unknown"):
        CustomFormulaBlock(formula="__import__('os').system('x')").execute([source, None, None, None])


def test_filter_collection_reduces_out_of_band_energy() -> None:
    fs = 1000.0; time = np.arange(3000) / fs
    source = SignalData(np.sin(2*np.pi*10*time) + 0.8*np.sin(2*np.pi*100*time), time, sample_rate=fs)
    band = BandPassBlock(lower_cutoff=8, upper_cutoff=15, order=4).execute([source])[0]
    fft = np.abs(np.fft.rfft(band.values)); freq = np.fft.rfftfreq(band.samples, 1/fs)
    assert fft[np.argmin(abs(freq-10))] > fft[np.argmin(abs(freq-100))] * 50
    notch = NotchFilterBlock(frequency=100, quality_factor=30).execute([source])[0]
    fft_notch = np.abs(np.fft.rfft(notch.values))
    assert fft_notch[np.argmin(abs(freq-100))] < np.abs(np.fft.rfft(source.values))[np.argmin(abs(freq-100))] * 0.1


@pytest.mark.parametrize("block_type", ["butter_filter", "cheby1_filter", "cheby2_filter", "ellip_filter", "bessel_filter"])
def test_filter_families_execute(block_type: str) -> None:
    output = create_block(block_type, {"cutoff": 30, "order": 3, "zero_phase": False}).execute([sine_signal()])[0]
    assert output.samples == 2000
    assert np.all(np.isfinite(output.values))


def test_resample_and_synchronise_are_explicit() -> None:
    source = sine_signal(sample_rate=1000)
    resampled = ResampleBlock(target_rate=250).execute([source])[0]
    assert resampled.sample_rate == pytest.approx(250)
    assert resampled.samples == pytest.approx(source.samples / 4, abs=2)
    second_time = np.arange(500) / 200 + 0.1
    second = SignalData(np.sin(2*np.pi*12*second_time), second_time, sample_rate=200)
    first_sync, second_sync = SynchroniseSignalsBlock(target_rate=100).execute([source, second])
    np.testing.assert_allclose(first_sync.time, second_sync.time)


def test_fft_psd_and_spectrogram_identify_frequency() -> None:
    source = sine_signal(37.0, 1000.0, 4.0)
    spectrum = FFTBlock(window="hann").execute([source])[0]
    assert isinstance(spectrum, SpectrumData)
    assert spectrum.frequency[np.argmax(np.abs(spectrum.values))] == pytest.approx(37.0, abs=0.3)
    psd = PowerSpectralDensityBlock(segment_length=1024).execute([source])[0]
    assert psd.frequency[np.argmax(psd.values)] == pytest.approx(37.0, abs=1.0)
    spectrogram = SpectrogramBlock(fft_size=256).execute([source])[0]
    assert isinstance(spectrogram, SpectrogramData)
    assert spectrogram.values.shape == (len(spectrogram.frequency), len(spectrogram.time))


def test_peak_and_statistics_outputs() -> None:
    source = sine_signal(5, 500, 2)
    table, markers = PeakDetectionBlock(distance_samples=50, height="0.9").execute([source])
    assert isinstance(table, TableResult)
    assert 8 <= len(table.frame) <= 12
    assert np.count_nonzero(np.isfinite(markers.values)) == len(table.frame)
    stats = DescriptiveStatisticsBlock().execute([source])[0]
    assert "rms" in set(stats.frame["metric"])


def test_import_multiple_channels(tmp_path: Path) -> None:
    path = tmp_path / "multi.csv"
    pd.DataFrame({"time": [0, .1, .2], "x": [1, 2, 3], "y": [4, 5, 6]}).to_csv(path, index=False)
    outputs = ImportDataBlock(file_path=str(path), time_column="time", signal_columns="x,y", signal_names="X,Y", units="V,A").execute([])
    assert outputs[0].name == "X" and outputs[1].name == "Y"
    assert outputs[0].unit == "V" and outputs[1].unit == "A"
    assert outputs[2] is None and outputs[3] is None


def test_import_automatically_detects_time_column(tmp_path: Path) -> None:
    path = tmp_path / "automatic_time.csv"
    pd.DataFrame({"timestamp": [0.0, 0.1, 0.2], "sensor": [4.0, 5.0, 6.0]}).to_csv(path, index=False)
    signal = ImportDataBlock(file_path=str(path), signal_columns="sensor", auto_detect_time=True).execute([])[0]
    np.testing.assert_allclose(signal.time, [0.0, 0.1, 0.2])
    assert signal.sample_rate == pytest.approx(10.0)


def test_hdf5_import_and_export_round_trip(tmp_path: Path) -> None:
    from app.core.blocks import ExportDataBlock
    source = sine_signal(7.0, 200.0, 1.0)
    path = tmp_path / "signal.h5"
    ExportDataBlock(file_path=str(path), include_metadata=True).execute([source, None, None, None])
    assert path.exists() and path.with_suffix(".h5.metadata.json").exists()
    imported = ImportDataBlock(file_path=str(path), time_column="time", signal_columns=source.name).execute([])[0]
    np.testing.assert_allclose(imported.time, source.time)
    np.testing.assert_allclose(imported.values, source.values)


def test_import_preview_reads_only_requested_rows(tmp_path: Path) -> None:
    path = tmp_path / "large_preview.csv"
    pd.DataFrame({"time": np.arange(1000) / 100, "sensor": np.arange(1000)}).to_csv(path, index=False)
    block = ImportDataBlock(file_path=str(path))
    preview = block.preview(17)
    assert len(preview) == 17
    assert list(preview.columns) == ["time", "sensor"]


def test_timestamp_import_and_datetime_export(tmp_path: Path) -> None:
    from app.core.blocks import ExportDataBlock

    source = tmp_path / "timestamps.csv"
    timestamps = pd.date_range("2026-07-28T10:00:00Z", periods=4, freq="250ms")
    pd.DataFrame({"timestamp": timestamps.astype(str), "sensor": [1.0, np.nan, 3.0, 4.0]}).to_csv(source, index=False)
    signal = ImportDataBlock(
        file_path=str(source),
        signal_columns="sensor",
        auto_detect_time=True,
        missing_policy="interpolate",
        units="mV",
    ).execute([])[0]
    assert signal.attributes["time_representation"] == "datetime"
    assert signal.sample_rate == pytest.approx(4.0)

    output = tmp_path / "timestamps_export.csv"
    ExportDataBlock(
        file_path=str(output),
        time_representation="datetime_iso",
        column_names="Sensor A",
        units_in_headers=True,
        missing_value="MISSING",
    ).execute([signal, None, None, None])
    frame = pd.read_csv(output)
    assert list(frame.columns) == ["time", "Sensor A [mV]"]
    assert frame["time"].iloc[0].startswith("2026-07-28")
    assert frame["Sensor A [mV]"].iloc[1] == pytest.approx(2.0)


def test_export_rejects_conflicting_time_column_name(tmp_path: Path) -> None:
    from app.core.blocks import ExportDataBlock

    source = sine_signal()
    source.name = "timestamp"
    with pytest.raises(BlockError, match="conflicts"):
        ExportDataBlock(file_path=str(tmp_path / "bad.csv"), time_column_name="timestamp").execute([source, None, None, None])


def test_mathematics_enforces_units_and_domains() -> None:
    from app.core.blocks import create_block

    volts = sine_signal(); volts.unit = "V"
    amps = sine_signal(); amps.unit = "A"
    with pytest.raises(BlockError, match="incompatible units"):
        create_block("add").execute([volts, amps, None, None])
    multiplied = create_block("multiply").execute([volts, amps, None, None])[0]
    assert multiplied.unit == "V·A"
    zeros = sine_signal(); zeros.values[:] = 0
    with pytest.raises(BlockError, match="zero denominator"):
        create_block("divide").execute([volts, zeros, None, None])
    negative = sine_signal(); negative.values[:] = -1
    with pytest.raises(BlockError, match="undefined"):
        create_block("square_root").execute([negative])


@pytest.mark.parametrize("block_type", ["butter_filter", "cheby1_filter", "cheby2_filter", "ellip_filter", "bessel_filter"])
def test_configurable_filter_families_support_all_modes(block_type: str) -> None:
    source = sine_signal(sample_rate=500.0)
    for mode, parameters in (
        ("lowpass", {"cutoff": 30.0}),
        ("highpass", {"cutoff": 3.0}),
        ("bandpass", {"lower_cutoff": 5.0, "upper_cutoff": 30.0}),
        ("bandstop", {"lower_cutoff": 40.0, "upper_cutoff": 60.0}),
    ):
        output = create_block(block_type, {"mode": mode, "order": 3, "zero_phase": False, **parameters}).execute([source])[0]
        assert output.samples == source.samples
        assert np.all(np.isfinite(output.values))


def test_unit_conversion_supports_si_prefixes_and_temperature() -> None:
    from app.core.blocks import create_block

    source = sine_signal(); source.values = np.array([0.0, 1.0, 2.0]); source.time = np.array([0.0, 0.1, 0.2]); source.sample_rate = 10.0; source.unit = "V"
    millivolts = create_block("unit_conversion", {"automatic": True, "target_unit": "mV"}).execute([source])[0]
    np.testing.assert_allclose(millivolts.values, [0.0, 1000.0, 2000.0]); assert millivolts.unit == "mV"
    celsius = source.with_values(np.array([0.0, 100.0]), time=np.array([0.0, 1.0]), sample_rate=1.0, unit="°C")
    kelvin = create_block("unit_conversion", {"automatic": True, "target_unit": "K"}).execute([celsius])[0]
    np.testing.assert_allclose(kelvin.values, [273.15, 373.15])
    with pytest.raises(BlockError, match="Cannot convert"):
        create_block("unit_conversion", {"automatic": True, "source_unit": "V", "target_unit": "A"}).execute([source])


def test_import_records_data_quality_information(tmp_path: Path) -> None:
    path = tmp_path / "quality.csv"
    pd.DataFrame({"time": [0.0, 0.1, 0.2, 0.3], "sensor": [1.0, "bad", None, 4.0]}).to_csv(path, index=False)
    signal = ImportDataBlock(file_path=str(path), time_column="time", signal_columns="sensor", missing_policy="interpolate").execute([])[0]
    quality = signal.attributes["import_quality"]
    assert quality["invalid_values"] == 1
    assert quality["missing_values_before_policy"] == 2
    assert quality["rows_removed"] == 0
    assert np.all(np.isfinite(signal.values))


def test_fft_one_sided_scaling_preserves_dc_and_sine_amplitude() -> None:
    sample_rate = 1024.0
    samples = 1024
    time = np.arange(samples) / sample_rate
    dc = SignalData(np.full(samples, 3.0), time, sample_rate=sample_rate)
    dc_spectrum = FFTBlock(window="boxcar", detrend=False, output="magnitude").execute([dc])[0]
    assert dc_spectrum.values[0] == pytest.approx(3.0, rel=1e-12)

    sine = SignalData(2.5 * np.sin(2 * np.pi * 64 * time), time, sample_rate=sample_rate)
    sine_spectrum = FFTBlock(window="boxcar", detrend=False, output="magnitude").execute([sine])[0]
    peak = int(np.argmax(sine_spectrum.values))
    assert sine_spectrum.frequency[peak] == pytest.approx(64.0)
    assert sine_spectrum.values[peak] == pytest.approx(2.5, rel=1e-10)
    assert sine_spectrum.values[-1] < 1e-10  # Nyquist must not be doubled.


def test_spectral_analysis_rejects_non_finite_values() -> None:
    source = sine_signal()
    source.values[10] = np.nan
    for block in (
        FFTBlock(),
        PowerSpectralDensityBlock(),
        ShortTimeFourierTransformBlock(),
        FrequencyBandEnergyBlock(lower_frequency=1.0, upper_frequency=20.0),
    ):
        with pytest.raises(BlockError, match="NaN|infinite"):
            block.execute([source])


def test_snr_supports_complex_values_and_validates_zero_power() -> None:
    time = np.arange(100) / 100.0
    reference = SignalData(np.ones(100, dtype=complex) * (1 + 1j), time, sample_rate=100.0)
    noise = SignalData(np.ones(100, dtype=complex) * 0.1j, time, sample_rate=100.0)
    result = SignalToNoiseRatioBlock().execute([reference, noise])[0]
    assert result.value == pytest.approx(10 * np.log10(200.0))
    zero = SignalData(np.zeros(100), time, sample_rate=100.0)
    with pytest.raises(BlockError, match="Noise power"):
        SignalToNoiseRatioBlock().execute([reference, zero])


def test_histogram_and_regression_fail_readably_for_invalid_data() -> None:
    time = np.arange(5, dtype=float)
    invalid = SignalData(np.full(5, np.nan), time, sample_rate=1.0)
    with pytest.raises(BlockError, match="no finite values"):
        HistogramBlock().execute([invalid])

    constant_x = SignalData(np.ones(5), time, sample_rate=1.0)
    y = SignalData(np.arange(5, dtype=float), time, sample_rate=1.0)
    with pytest.raises(BlockError, match="variation"):
        LinearRegressionBlock().execute([constant_x, y])


def test_export_rejects_override_collision_and_duplicate_names(tmp_path: Path) -> None:
    from app.core.blocks import ExportDataBlock

    first = sine_signal(); first.name = "first"
    second = sine_signal(20); second.name = "second"
    with pytest.raises(BlockError, match="time column"):
        ExportDataBlock(file_path=str(tmp_path / "time_collision.csv"), column_names="time,other").execute([first, second, None, None])
    with pytest.raises(BlockError, match="unique"):
        ExportDataBlock(file_path=str(tmp_path / "duplicate.csv"), column_names="same,same").execute([first, second, None, None])


def test_numpy_preview_and_npz_time_array(tmp_path: Path) -> None:
    npy = tmp_path / "matrix.npy"
    np.save(npy, np.column_stack((np.arange(20), np.arange(20) * 2)))
    preview = ImportDataBlock(file_path=str(npy)).preview(5)
    assert list(preview.columns) == ["channel_1", "channel_2"]
    assert len(preview) == 5

    npz = tmp_path / "timed.npz"
    time = np.array([0.0, 0.1, 0.2, 0.3])
    np.savez(npz, time=time, sensor=np.array([1.0, 2.0, 3.0, 4.0]))
    preview_npz = ImportDataBlock(file_path=str(npz)).preview(3)
    assert set(preview_npz.columns) == {"time", "sensor"}
    signal = ImportDataBlock(file_path=str(npz), time_column="time", signal_columns="sensor").execute([])[0]
    np.testing.assert_allclose(signal.time, time)
    assert signal.sample_rate == pytest.approx(10.0)


def test_import_preserves_channel_descriptions(tmp_path: Path) -> None:
    path = tmp_path / "described.csv"
    pd.DataFrame({"time": [0.0, 0.1], "x": [1.0, 2.0], "y": [3.0, 4.0]}).to_csv(path, index=False)
    outputs = ImportDataBlock(
        file_path=str(path),
        time_column="time",
        signal_columns="x,y",
        descriptions="Accelerometer X axis;Accelerometer Y axis",
    ).execute([])
    assert outputs[0].description == "Accelerometer X axis"
    assert outputs[1].description == "Accelerometer Y axis"


def test_scalar_analysis_units_and_undefined_cases() -> None:
    from app.core.blocks import create_block

    time = np.arange(4, dtype=float)
    signal = SignalData(np.array([1.0, -1.0, 1.0, -1.0]), time, unit="V", sample_rate=1.0)
    assert create_block("rms").execute([signal])[0].value == pytest.approx(1.0)
    assert create_block("variance").execute([signal])[0].unit == "V²"
    assert create_block("crest_factor").execute([signal])[0].value == pytest.approx(1.0)

    constant = SignalData(np.ones(4), time, sample_rate=1.0)
    with pytest.raises(BlockError, match="constant signal"):
        create_block("autocorrelation").execute([constant])
    with pytest.raises(BlockError, match="either signal is constant"):
        create_block("cross_correlation").execute([constant, signal])
