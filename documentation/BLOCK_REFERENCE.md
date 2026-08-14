# Block Reference

SignalDojo 1.2.6 registers **119** built-in blocks. This document is generated from the live block registry, so port declarations and parameter schemas match the application. Parameters marked advanced are collapsed in the Properties panel.

## Analysis

### Autocorrelation

Compute normalised non-negative-lag autocorrelation.

- Type identifier: `autocorrelation`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Maximum lag; 0 = full (`max_lag_samples`) | int | `0` | min 0 |

### Crest Factor

Compute crest factor.

- Type identifier: `crest_factor`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (scalar)

### Cross-Correlation

Compute full normalised cross-correlation and the best lag.

- Type identifier: `cross_correlation`
- Inputs: 2 (signal, signal); required: 2
- Outputs: 2 (signal, scalar)

### Descriptive Statistics

Calculate a comprehensive engineering statistics table.

- Type identifier: `descriptive_statistics`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (table)

### Envelope Detection

Compute the analytic-signal envelope using a Hilbert transform.

- Type identifier: `envelope_detection`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

### FFT

Compute a single-sided FFT magnitude or complex spectrum.

- Type identifier: `fft`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (spectrum)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Window (`window`) | choice | `'hann'` | choices: 'boxcar', 'hann', 'hamming', 'blackman', 'flattop' |
| Remove mean (`detrend`) | bool | `True` |  |
| Output (`output`) | choice | `'magnitude'` | choices: 'magnitude', 'power', 'complex' |

### Frequency-Band Energy

Calculate signal energy or mean-square power in a selected frequency band.

- Type identifier: `frequency_band_energy`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (scalar)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Lower frequency (Hz) (`lower_frequency`) | float | `0.0` |  |
| Upper frequency (Hz) (`upper_frequency`) | float | `10.0` |  |
| Quantity (`quantity`) | choice | `'energy'` | choices: 'energy', 'mean-square power' |

### Histogram

Calculate histogram bin counts and edges.

- Type identifier: `histogram`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (table)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Bins (`bins`) | int | `50` | min 1; max 100000 |
| Probability density (`density`) | bool | `False` |  |

### Kurtosis

Compute kurtosis.

- Type identifier: `kurtosis`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (scalar)

### Linear Regression

Fit y against x and return a results table plus fitted signal.

- Type identifier: `linear_regression`
- Inputs: 2 (signal, signal); required: 2
- Outputs: 2 (table, signal)

### Maximum Value

Compute maximum value.

- Type identifier: `maximum_value`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (scalar)

### Mean

Compute mean.

- Type identifier: `mean`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (scalar)

### Median

Compute median.

- Type identifier: `median`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (scalar)

### Minimum Value

Compute minimum value.

- Type identifier: `minimum_value`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (scalar)

### Numerical Differentiation

Differentiate with respect to the actual time vector.

- Type identifier: `numerical_derivative`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

### Numerical Integration

Cumulatively integrate with the trapezoidal rule.

- Type identifier: `numerical_integration`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Initial value (`initial`) | float | `0.0` |  |

### Peak Detection

Find peaks and expose a peak table plus a marker signal.

- Type identifier: `peak_detection`
- Inputs: 1 (signal); required: 1
- Outputs: 2 (table, signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Minimum height; blank uses none (`height`) | text | `''` |  |
| Minimum distance (`distance_samples`) | int | `1` | min 1 |
| Minimum prominence; blank uses none (`prominence`) | text | `''` |  |

### Peak-to-Peak

Compute peak-to-peak.

- Type identifier: `peak_to_peak`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (scalar)

### Power Spectral Density

Estimate PSD using Welch's method.

- Type identifier: `power_spectral_density`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (spectrum)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Segment length (`segment_length`) | int | `256` | min 8 |
| Overlap (%) (`overlap_percent`) | float | `50.0` | min 0.0; max 95.0 |
| Window (`window`) | choice | `'hann'` | choices: 'hann', 'hamming', 'blackman', 'flattop' |

### RMS

Compute rms.

- Type identifier: `rms`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (scalar)

### Short-Time Fourier Transform

Compute a complex STFT time-frequency matrix.

- Type identifier: `short_time_fourier_transform`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (spectrogram)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| FFT size (`fft_size`) | int | `256` | min 8 |
| Overlap (%) (`overlap_percent`) | float | `50.0` | min 0.0; max 95.0 |
| Window (`window`) | choice | `'hann'` | choices: 'hann', 'hamming', 'blackman', 'flattop' |

### Signal-to-Noise Ratio

Compute SNR between a reference signal and a noise signal.

- Type identifier: `signal_to_noise_ratio`
- Inputs: 2 (signal, signal); required: 2
- Outputs: 1 (scalar)

### Skewness

Compute skewness.

- Type identifier: `skewness`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (scalar)

### Spectrogram

Compute a magnitude or decibel spectrogram.

- Type identifier: `spectrogram`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (spectrogram)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| FFT size (`fft_size`) | int | `256` | min 8 |
| Overlap (%) (`overlap_percent`) | float | `50.0` | min 0.0; max 95.0 |
| Window (`window`) | choice | `'hann'` | choices: 'hann', 'hamming', 'blackman', 'flattop' |
| Scale (`scale`) | choice | `'decibel'` | choices: 'magnitude', 'power', 'decibel' |

### Standard Deviation

Compute standard deviation.

- Type identifier: `standard_deviation`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (scalar)

### Variance

Compute variance.

- Type identifier: `variance`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (scalar)

### Zero-Crossing Rate

Compute zero-crossing rate.

- Type identifier: `zero_crossing_rate`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (scalar)

## Campaign

### Publish Metric

Publish a named scalar campaign metric from a scalar, signal, spectrum or single-cell table. Signal inputs are reduced using the selected engineering aggregation.

- Type identifier: `publish_metric`
- Inputs: 1 (any); required: 1
- Outputs: 1 (scalar)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Metric name (`metric_name`) | text | `'metric'` |  |
| Display label (`display_label`) | text | `''` |  |
| Unit override (`unit`) | text | `''` |  |
| Description (`description`) | multiline | `''` |  |
| Numeric format (`number_format`) | text | `'.6g'` |  |
| Aggregation (`aggregation`) | choice | `'auto'` | choices: 'auto', 'value', 'mean', 'rms', 'standard_deviation', 'minimum', 'maximum', 'peak_to_peak', 'dominant_frequency', 'sample_count', 'duration', 'rise_time', 'settling_time', 'first', 'last', 'custom_expression' |
| Custom scalar expression (`expression`) | multiline | `'mean'` | shown when `aggregation` is 'custom_expression' |

## Custom Processing

### Custom Formula

Evaluate a validated NumPy-style expression using up to four named inputs.

- Type identifier: `custom_formula`
- Inputs: 4 (signal, signal, signal, signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Formula (`formula`) | multiline | `'output = input_1'` |  |
| Output name (`output_name`) | text | `'Formula result'` |  |
| Output unit; blank = first input unit (`output_unit`) | text | `''` |  |

### Restricted Python Expression

Advanced expression block using the same isolated safe evaluator; arbitrary Python execution is never exposed.

- Type identifier: `python_script`
- Inputs: 4 (signal, signal, signal, signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Formula (`formula`) | multiline | `'output = input_1'` |  |
| Output name (`output_name`) | text | `'Formula result'` |  |
| Output unit; blank = first input unit (`output_unit`) | text | `''` |  |
| Acknowledge restricted environment (`acknowledge_restrictions`) | bool | `False` |  |

## Filters

### Band-Pass Filter

Apply a butter bandpass digital filter.

- Type identifier: `band_pass`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Lower cutoff frequency (Hz) (`lower_cutoff`) | float | `5.0` | min 1e-12 |
| Upper cutoff frequency (Hz) (`upper_cutoff`) | float | `20.0` | min 1e-12 |
| Order (`order`) | int | `4` | min 1; max 20 |
| Zero phase (`zero_phase`) | bool | `True` |  |
| Causal initial conditions (`initial_conditions`) | choice | `'zero'` | choices: 'zero', 'steady_state'; shown when `zero_phase` is False; advanced |
| Edge padding (`edge_padding`) | choice | `'odd'` | choices: 'odd', 'even', 'constant', 'none'; shown when `zero_phase` is True |

### Band-Stop Filter

Apply a butter bandstop digital filter.

- Type identifier: `band_stop`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Lower cutoff frequency (Hz) (`lower_cutoff`) | float | `5.0` | min 1e-12 |
| Upper cutoff frequency (Hz) (`upper_cutoff`) | float | `20.0` | min 1e-12 |
| Order (`order`) | int | `4` | min 1; max 20 |
| Zero phase (`zero_phase`) | bool | `True` |  |
| Causal initial conditions (`initial_conditions`) | choice | `'zero'` | choices: 'zero', 'steady_state'; shown when `zero_phase` is False; advanced |
| Edge padding (`edge_padding`) | choice | `'odd'` | choices: 'odd', 'even', 'constant', 'none'; shown when `zero_phase` is True |

### Bessel Filter

Apply a configurable bessel digital filter.

- Type identifier: `bessel_filter`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Filter mode (`mode`) | choice | `'lowpass'` | choices: 'lowpass', 'highpass', 'bandpass', 'bandstop' |
| Cutoff frequency (Hz) (`cutoff`) | float | `10.0` | min 1e-12; shown when `mode` is 'lowpass' or 'highpass' |
| Lower cutoff frequency (Hz) (`lower_cutoff`) | float | `5.0` | min 1e-12; shown when `mode` is 'bandpass' or 'bandstop' |
| Upper cutoff frequency (Hz) (`upper_cutoff`) | float | `20.0` | min 1e-12; shown when `mode` is 'bandpass' or 'bandstop' |
| Order (`order`) | int | `4` | min 1; max 20 |
| Zero phase (`zero_phase`) | bool | `True` |  |
| Causal initial conditions (`initial_conditions`) | choice | `'zero'` | choices: 'zero', 'steady_state'; shown when `zero_phase` is False; advanced |
| Edge padding (`edge_padding`) | choice | `'odd'` | choices: 'odd', 'even', 'constant', 'none'; shown when `zero_phase` is True |

### Butterworth Filter

Apply a configurable butter digital filter.

- Type identifier: `butter_filter`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Filter mode (`mode`) | choice | `'lowpass'` | choices: 'lowpass', 'highpass', 'bandpass', 'bandstop' |
| Cutoff frequency (Hz) (`cutoff`) | float | `10.0` | min 1e-12; shown when `mode` is 'lowpass' or 'highpass' |
| Lower cutoff frequency (Hz) (`lower_cutoff`) | float | `5.0` | min 1e-12; shown when `mode` is 'bandpass' or 'bandstop' |
| Upper cutoff frequency (Hz) (`upper_cutoff`) | float | `20.0` | min 1e-12; shown when `mode` is 'bandpass' or 'bandstop' |
| Order (`order`) | int | `4` | min 1; max 20 |
| Zero phase (`zero_phase`) | bool | `True` |  |
| Causal initial conditions (`initial_conditions`) | choice | `'zero'` | choices: 'zero', 'steady_state'; shown when `zero_phase` is False; advanced |
| Edge padding (`edge_padding`) | choice | `'odd'` | choices: 'odd', 'even', 'constant', 'none'; shown when `zero_phase` is True |

### Chebyshev Type I Filter

Apply a configurable cheby1 digital filter.

- Type identifier: `cheby1_filter`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Filter mode (`mode`) | choice | `'lowpass'` | choices: 'lowpass', 'highpass', 'bandpass', 'bandstop' |
| Passband edge frequency (Hz) (`cutoff`) | float | `10.0` | min 1e-12; shown when `mode` is 'lowpass' or 'highpass' |
| Lower passband edge frequency (Hz) (`lower_cutoff`) | float | `5.0` | min 1e-12; shown when `mode` is 'bandpass' or 'bandstop' |
| Upper passband edge frequency (Hz) (`upper_cutoff`) | float | `20.0` | min 1e-12; shown when `mode` is 'bandpass' or 'bandstop' |
| Order (`order`) | int | `4` | min 1; max 20 |
| Passband ripple (dB) (`ripple`) | float | `1.0` | min 0.01 |
| Zero phase (`zero_phase`) | bool | `True` |  |
| Causal initial conditions (`initial_conditions`) | choice | `'zero'` | choices: 'zero', 'steady_state'; shown when `zero_phase` is False; advanced |
| Edge padding (`edge_padding`) | choice | `'odd'` | choices: 'odd', 'even', 'constant', 'none'; shown when `zero_phase` is True |

### Chebyshev Type II Filter

Apply a configurable cheby2 digital filter.

- Type identifier: `cheby2_filter`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Filter mode (`mode`) | choice | `'lowpass'` | choices: 'lowpass', 'highpass', 'bandpass', 'bandstop' |
| Stopband edge frequency (Hz) (`cutoff`) | float | `10.0` | min 1e-12; shown when `mode` is 'lowpass' or 'highpass' |
| Lower stopband edge frequency (Hz) (`lower_cutoff`) | float | `5.0` | min 1e-12; shown when `mode` is 'bandpass' or 'bandstop' |
| Upper stopband edge frequency (Hz) (`upper_cutoff`) | float | `20.0` | min 1e-12; shown when `mode` is 'bandpass' or 'bandstop' |
| Order (`order`) | int | `4` | min 1; max 20 |
| Stopband attenuation (dB) (`attenuation`) | float | `40.0` | min 1.0 |
| Zero phase (`zero_phase`) | bool | `True` |  |
| Causal initial conditions (`initial_conditions`) | choice | `'zero'` | choices: 'zero', 'steady_state'; shown when `zero_phase` is False; advanced |
| Edge padding (`edge_padding`) | choice | `'odd'` | choices: 'odd', 'even', 'constant', 'none'; shown when `zero_phase` is True |

### Custom Filter Coefficients

Apply user-provided numerator b and denominator a coefficients.

- Type identifier: `custom_filter_coefficients`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Numerator coefficients (`b`) | text | `'1'` |  |
| Denominator coefficients (`a`) | text | `'1'` |  |
| Zero phase (`zero_phase`) | bool | `False` |  |

### Elliptic Filter

Apply a configurable ellip digital filter.

- Type identifier: `ellip_filter`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Filter mode (`mode`) | choice | `'lowpass'` | choices: 'lowpass', 'highpass', 'bandpass', 'bandstop' |
| Passband edge frequency (Hz) (`cutoff`) | float | `10.0` | min 1e-12; shown when `mode` is 'lowpass' or 'highpass' |
| Lower passband edge frequency (Hz) (`lower_cutoff`) | float | `5.0` | min 1e-12; shown when `mode` is 'bandpass' or 'bandstop' |
| Upper passband edge frequency (Hz) (`upper_cutoff`) | float | `20.0` | min 1e-12; shown when `mode` is 'bandpass' or 'bandstop' |
| Order (`order`) | int | `4` | min 1; max 20 |
| Passband ripple (dB) (`ripple`) | float | `1.0` | min 0.01 |
| Stopband attenuation (dB) (`attenuation`) | float | `40.0` | min 1.0 |
| Zero phase (`zero_phase`) | bool | `True` |  |
| Causal initial conditions (`initial_conditions`) | choice | `'zero'` | choices: 'zero', 'steady_state'; shown when `zero_phase` is False; advanced |
| Edge padding (`edge_padding`) | choice | `'odd'` | choices: 'odd', 'even', 'constant', 'none'; shown when `zero_phase` is True |

### FIR Filter

Design and apply a windowed FIR low/high/band filter.

- Type identifier: `fir_filter`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Mode (`mode`) | choice | `'lowpass'` | choices: 'lowpass', 'highpass', 'bandpass', 'bandstop' |
| Cutoff frequency (Hz) (`cutoff`) | float | `10.0` | min 1e-12; shown when `mode` is 'lowpass' or 'highpass' |
| Lower cutoff frequency (Hz) (`lower_cutoff`) | float | `5.0` | min 1e-12; shown when `mode` is 'bandpass' or 'bandstop' |
| Upper cutoff frequency (Hz) (`upper_cutoff`) | float | `20.0` | min 1e-12; shown when `mode` is 'bandpass' or 'bandstop' |
| Number of taps (`taps`) | int | `101` | min 3; max 10001 |
| Window (`window`) | choice | `'hamming'` | choices: 'hamming', 'hann', 'blackman', 'kaiser' |
| Kaiser beta (`kaiser_beta`) | float | `8.6` | min 0.0; shown when `window` is 'kaiser' |
| Zero phase (`zero_phase`) | bool | `True` |  |

### High-Pass Filter

Apply a butter highpass digital filter.

- Type identifier: `high_pass`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Cutoff frequency (Hz) (`cutoff`) | float | `10.0` | min 1e-12 |
| Order (`order`) | int | `4` | min 1; max 20 |
| Zero phase (`zero_phase`) | bool | `True` |  |
| Causal initial conditions (`initial_conditions`) | choice | `'zero'` | choices: 'zero', 'steady_state'; shown when `zero_phase` is False; advanced |
| Edge padding (`edge_padding`) | choice | `'odd'` | choices: 'odd', 'even', 'constant', 'none'; shown when `zero_phase` is True |

### Low-Pass Filter

Apply a butter lowpass digital filter.

- Type identifier: `low_pass`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Cutoff frequency (Hz) (`cutoff`) | float | `10.0` | min 1e-12 |
| Order (`order`) | int | `4` | min 1; max 20 |
| Zero phase (`zero_phase`) | bool | `True` |  |
| Causal initial conditions (`initial_conditions`) | choice | `'zero'` | choices: 'zero', 'steady_state'; shown when `zero_phase` is False; advanced |
| Edge padding (`edge_padding`) | choice | `'odd'` | choices: 'odd', 'even', 'constant', 'none'; shown when `zero_phase` is True |

### Notch Filter

Remove a narrow frequency using a second-order IIR notch.

- Type identifier: `notch_filter`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Notch frequency (Hz) (`frequency`) | float | `50.0` | min 1e-12 |
| Quality factor (`quality_factor`) | float | `30.0` | min 0.1 |
| Zero phase (`zero_phase`) | bool | `True` |  |

## Inputs & Outputs

### Constant

Create a constant sampled signal.

- Type identifier: `constant`
- Inputs: 0 (none); required: 0
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Value (`value`) | float | `1.0` |  |
| Sample rate (Hz) (`sample_rate`) | float | `100.0` | min 1e-09 |
| Duration (s) (`duration`) | float | `1.0` | min 1e-09 |
| Signal name (`name`) | text | `'Constant'` |  |
| Unit (`unit`) | text | `''` |  |

### Data Table

Display signal samples or any tabular analysis result.

- Type identifier: `data_table`
- Inputs: 1 (any); required: 1
- Outputs: 0 (none)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Maximum displayed rows (`maximum_rows`) | int | `10000` | min 10 |

### Export Data

Export up to four signals or one table with metadata and processing history.

- Type identifier: `export_data`
- Inputs: 4 (any, any, any, any); required: 1
- Outputs: 0 (none)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Output file (`file_path`) | save_file | `''` |  |
| Write metadata sidecar (`include_metadata`) | bool | `True` |  |
| Include time values (`include_time`) | bool | `True` |  |
| Time column name (`time_column_name`) | text | `'time'` |  |
| Time representation (`time_representation`) | choice | `'seconds'` | choices: 'seconds', 'sample_index', 'datetime_iso' |
| Override signal column names (comma-separated) (`column_names`) | text | `''` |  |
| Include units in column headers (`units_in_headers`) | bool | `False` |  |
| Numeric precision (`precision`) | int | `10` | min 1; max 18 |
| Delimiter (`delimiter`) | text | `','` |  |
| Decimal separator (`decimal`) | text | `'.'` |  |
| Missing-value representation (`missing_value`) | text | `''` |  |
| Overwrite policy (`overwrite`) | choice | `'replace'` | choices: 'replace', 'error', 'increment' |

### Export Plot

Render up to four signals to PNG, SVG or PDF using Matplotlib.

- Type identifier: `export_plot`
- Inputs: 4 (signal, signal, signal, signal); required: 1
- Outputs: 0 (none)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Plot file (`file_path`) | save_file | `''` |  |
| Title (`title`) | text | `'SignalDojo Plot'` |  |
| Width (in) (`width_inches`) | float | `10.0` | min 1.0 |
| Height (in) (`height_inches`) | float | `6.0` | min 1.0 |
| DPI (`dpi`) | int | `150` | min 72; max 600 |

### Export Report

Create a self-contained professional HTML or PDF engineering report.

- Type identifier: `export_report`
- Inputs: 4 (any, any, any, any); required: 1
- Outputs: 0 (none)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Report file (`file_path`) | save_file | `''` |  |
| Project name (`project_name`) | text | `'SignalDojo Analysis'` |  |
| Project description (`project_description`) | multiline | `''` |  |
| Author (`author`) | text | `''` |  |

### Import Data

Import up to four signal channels from common engineering data files.

- Type identifier: `import_data`
- Inputs: 0 (none); required: 0
- Outputs: 4 (signal, signal, signal, signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| File (`file_path`) | open_file | `''` |  |
| Delimiter (`delimiter`) | text | `'auto'` |  |
| Header row (`header_row`) | int | `0` | min 0 |
| Metadata rows to skip (`skip_rows`) | int | `0` | min 0 |
| Excel sheet (`sheet_name`) | text | `'0'` |  |
| HDF5 dataset key (`dataset_key`) | text | `''` | advanced |
| Time column (`time_column`) | text | `''` |  |
| Automatically detect a likely time column (`auto_detect_time`) | bool | `True` |  |
| Signal columns (comma-separated) (`signal_columns`) | text | `''` |  |
| Legacy signal column (`signal_column`) | text | `''` | advanced |
| Sample rate when no time column (Hz) (`sample_rate`) | float | `100.0` | min 1e-12 |
| Output names (comma-separated) (`signal_names`) | text | `''` |  |
| Legacy single output name (`signal_name`) | text | `''` | advanced |
| Units (comma-separated) (`units`) | text | `''` |  |
| Legacy single output unit (`unit`) | text | `''` | advanced |
| Descriptions (semicolon-separated) (`descriptions`) | text | `''` |  |
| Time representation (`time_mode`) | choice | `'auto'` | choices: 'auto', 'seconds', 'datetime' |
| Decimal separator (`decimal`) | text | `'.'` |  |
| Thousands separator (`thousands`) | text | `''` |  |
| Missing values (`missing_policy`) | choice | `'interpolate'` | choices: 'interpolate', 'drop', 'zero', 'mean', 'preserve' |
| CSV chunk size (`chunk_size`) | int | `250000` | min 10000 |

### Manual Signal Generator

Create a signal from comma- or whitespace-separated values and optional time values.

- Type identifier: `manual_signal_generator`
- Inputs: 0 (none); required: 0
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Sample values (`values`) | multiline | `'0, 1, 0, -1'` |  |
| Time values; blank uses sample rate (`time_values`) | multiline | `''` |  |
| Sample rate (Hz) (`sample_rate`) | float | `100.0` | min 1e-12 |
| Signal name (`name`) | text | `'Manual signal'` |  |
| Unit (`unit`) | text | `''` |  |

### Multi-Signal Scope

Alias of Scope emphasising multi-channel comparison.

- Type identifier: `multi_signal_scope`
- Inputs: 4 (signal, signal, signal, signal); required: 1
- Outputs: 0 (none)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Title (`title`) | text | `'Signal Scope'` |  |
| Maximum display points (`max_display_points`) | int | `100000` | min 1000 |
| Show grid (`grid`) | bool | `True` |  |
| Show legend (`legend`) | bool | `True` |  |
| Line width (`line_width`) | float | `1.5` | min 0.1; max 10.0 |
| Line style (`line_style`) | choice | `'solid'` | choices: 'solid', 'dash', 'dot', 'dash-dot' |
| Show sample markers (`show_markers`) | bool | `False` |  |
| Annotate prominent peaks (`show_peaks`) | bool | `False` |  |
| Automatic axis scaling (`auto_scale`) | bool | `True` |  |
| Manual X minimum; blank = auto (`x_min`) | text | `''` | shown when `auto_scale` is False; advanced |
| Manual X maximum; blank = auto (`x_max`) | text | `''` | shown when `auto_scale` is False; advanced |
| Manual Y minimum; blank = auto (`y_min`) | text | `''` | shown when `auto_scale` is False; advanced |
| Manual Y maximum; blank = auto (`y_max`) | text | `''` | shown when `auto_scale` is False; advanced |

### Scope

Display up to four time-domain signals with measurement cursors.

- Type identifier: `scope`
- Inputs: 4 (signal, signal, signal, signal); required: 1
- Outputs: 0 (none)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Title (`title`) | text | `'Signal Scope'` |  |
| Maximum display points (`max_display_points`) | int | `100000` | min 1000 |
| Show grid (`grid`) | bool | `True` |  |
| Show legend (`legend`) | bool | `True` |  |
| Line width (`line_width`) | float | `1.5` | min 0.1; max 10.0 |
| Line style (`line_style`) | choice | `'solid'` | choices: 'solid', 'dash', 'dot', 'dash-dot' |
| Show sample markers (`show_markers`) | bool | `False` |  |
| Annotate prominent peaks (`show_peaks`) | bool | `False` |  |
| Automatic axis scaling (`auto_scale`) | bool | `True` |  |
| Manual X minimum; blank = auto (`x_min`) | text | `''` | shown when `auto_scale` is False; advanced |
| Manual X maximum; blank = auto (`x_max`) | text | `''` | shown when `auto_scale` is False; advanced |
| Manual Y minimum; blank = auto (`y_min`) | text | `''` | shown when `auto_scale` is False; advanced |
| Manual Y maximum; blank = auto (`y_max`) | text | `''` | shown when `auto_scale` is False; advanced |

### Spectrogram Viewer

Display a time-frequency matrix with configurable limits and colour scale.

- Type identifier: `spectrogram_viewer`
- Inputs: 1 (spectrogram); required: 1
- Outputs: 0 (none)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Title (`title`) | text | `'Spectrogram'` |  |
| Minimum frequency (Hz) (`minimum_frequency`) | float | `0.0` | min 0.0 |
| Maximum frequency; 0 = auto (`maximum_frequency`) | float | `0.0` | min 0.0 |
| Colour map (`colour_map`) | choice | `'viridis'` | choices: 'viridis', 'plasma', 'inferno', 'magma', 'cividis' |

### Spectrum Analyser

Display a spectrum or automatically calculate FFT from a signal.

- Type identifier: `spectrum_analyser`
- Inputs: 2 (signal, spectrum); required: 1
- Outputs: 0 (none)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Title (`title`) | text | `'Spectrum Analyser'` |  |
| Frequency scale (`frequency_scale`) | choice | `'linear'` | choices: 'linear', 'logarithmic' |
| Amplitude scale (`amplitude_scale`) | choice | `'linear'` | choices: 'linear', 'decibel' |
| Automatic FFT window (`window`) | choice | `'hann'` | choices: 'boxcar', 'hann', 'hamming', 'blackman' |

### Statistics Display

Display scalar or descriptive-statistics results.

- Type identifier: `statistics_display`
- Inputs: 1 (any); required: 1
- Outputs: 0 (none)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Maximum displayed rows (`maximum_rows`) | int | `10000` | min 10 |

### Time Vector

Create a signal whose values equal elapsed time.

- Type identifier: `time_vector`
- Inputs: 0 (none); required: 0
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Sample rate (Hz) (`sample_rate`) | float | `100.0` | min 1e-09 |
| Duration (s) (`duration`) | float | `1.0` | min 1e-09 |
| Signal name (`name`) | text | `'Time'` |  |

## Mathematics

### Absolute Value

Apply absolute value sample-by-sample.

- Type identifier: `absolute`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

### Add

Add two to four explicitly aligned signals.

- Type identifier: `add`
- Inputs: 4 (signal, signal, signal, signal); required: 2
- Outputs: 1 (signal)

### Clamp

Limit values to a lower and upper bound.

- Type identifier: `clamp`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Minimum (`minimum`) | float | `-1.0` |  |
| Maximum (`maximum`) | float | `1.0` |  |

### Divide

Divide two to four explicitly aligned signals.

- Type identifier: `divide`
- Inputs: 4 (signal, signal, signal, signal); required: 2
- Outputs: 1 (signal)

### Exponential

Apply exponential sample-by-sample.

- Type identifier: `exponential`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

### Gain

Multiply every sample by a constant gain.

- Type identifier: `gain`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Gain (`gain`) | float | `1.0` |  |

### Logarithm

Apply logarithm sample-by-sample.

- Type identifier: `logarithm`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

### Maximum

Maximum two to four explicitly aligned signals.

- Type identifier: `maximum`
- Inputs: 4 (signal, signal, signal, signal); required: 2
- Outputs: 1 (signal)

### Minimum

Minimum two to four explicitly aligned signals.

- Type identifier: `minimum`
- Inputs: 4 (signal, signal, signal, signal); required: 2
- Outputs: 1 (signal)

### Multiply

Multiply two to four explicitly aligned signals.

- Type identifier: `multiply`
- Inputs: 4 (signal, signal, signal, signal); required: 2
- Outputs: 1 (signal)

### Negate

Apply negate sample-by-sample.

- Type identifier: `negate`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

### Normalise

Scale a signal into a configurable range.

- Type identifier: `normalise`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Output minimum (`output_min`) | float | `0.0` |  |
| Output maximum (`output_max`) | float | `1.0` |  |

### Offset

Add a constant offset to every sample.

- Type identifier: `offset`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Offset (`offset`) | float | `0.0` |  |

### Power

Raise each sample to a configurable power.

- Type identifier: `power`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Exponent (`exponent`) | float | `2.0` |  |

### Square Root

Apply square root sample-by-sample.

- Type identifier: `square_root`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

### Standardise

Convert samples to zero-mean unit-standard-deviation z-scores.

- Type identifier: `standardise`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

### Subtract

Subtract two to four explicitly aligned signals.

- Type identifier: `subtract`
- Inputs: 4 (signal, signal, signal, signal); required: 2
- Outputs: 1 (signal)

## Resampling & Time

### Align by Cross-Correlation

Estimate lag by cross-correlation and shift the second signal.

- Type identifier: `align_cross_correlation`
- Inputs: 2 (signal, signal); required: 2
- Outputs: 2 (signal, signal)

### Align by Peak

Shift the second time axis so maximum absolute peaks coincide.

- Type identifier: `align_peak`
- Inputs: 2 (signal, signal); required: 2
- Outputs: 2 (signal, signal)

### Concatenate

Append two to four signals in sequence with a continuous generated time axis.

- Type identifier: `concatenate`
- Inputs: 4 (signal, signal, signal, signal); required: 2
- Outputs: 1 (signal)

### Crop by Sample

Keep samples in a zero-based half-open index interval.

- Type identifier: `crop_sample`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Start index (`start`) | int | `0` | min 0 |
| End index (`end`) | int | `100` | min 1 |

### Crop by Time

Keep samples within an inclusive time interval.

- Type identifier: `crop_time`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Start time (s) (`start`) | float | `0.0` |  |
| End time (s) (`end`) | float | `1.0` |  |

### Decimate

Low-pass filter and reduce sample rate.

- Type identifier: `decimate`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Factor (`factor`) | int | `2` | min 2; max 100 |
| Filter type (`filter_type`) | choice | `'iir'` | choices: 'iir', 'fir' |
| Zero phase (`zero_phase`) | bool | `True` |  |

### Delay

Delay sample values while preserving signal length.

- Type identifier: `delay`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Delay samples (`samples`) | int | `1` | min 0 |
| Fill value (`fill_value`) | float | `0.0` |  |

### Downsample

Keep every Nth sample without anti-alias filtering.

- Type identifier: `downsample`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Factor (`factor`) | int | `2` | min 2 |

### Interpolate

Interpolate a signal onto a configurable uniform time step.

- Type identifier: `interpolate`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Time step (s) (`time_step`) | float | `0.01` | min 1e-12 |
| Method (`method`) | choice | `'linear'` | choices: 'linear', 'nearest', 'cubic' |

### Merge Signals

Combine up to four aligned signals into a table.

- Type identifier: `merge_signals`
- Inputs: 4 (signal, signal, signal, signal); required: 2
- Outputs: 1 (table)

### Resample

Resample to a new uniform sampling frequency using polyphase filtering.

- Type identifier: `resample`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Target sample rate (Hz) (`target_rate`) | float | `100.0` | min 1e-09 |

### Segment Signal

Create a table of fixed-length overlapping segments.

- Type identifier: `segment_signal`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (table)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Segment length (`segment_samples`) | int | `256` | min 2 |
| Overlap (`overlap_samples`) | int | `128` | min 0 |

### Shift in Time

Move the time axis without changing sample values.

- Type identifier: `shift_time`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Shift (s) (`shift_seconds`) | float | `0.0` |  |

### Split Signal

Split a signal into up to four equal contiguous portions.

- Type identifier: `split_signal`
- Inputs: 1 (any); required: 1
- Outputs: 4 (signal, signal, signal, signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Parts (`parts`) | int | `2` | min 2; max 4 |

### Synchronise Signals

Interpolate two signals onto their overlapping common time axis.

- Type identifier: `synchronise_signals`
- Inputs: 2 (signal, signal); required: 2
- Outputs: 2 (signal, signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Target rate; 0 = highest input (Hz) (`target_rate`) | float | `0.0` | min 0.0 |

### Trigger-Based Extraction

Extract a window around the first threshold crossing.

- Type identifier: `trigger_extraction`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Threshold (`threshold`) | float | `0.0` |  |
| Edge (`edge`) | choice | `'rising'` | choices: 'rising', 'falling' |
| Pre-trigger samples (`pre_samples`) | int | `50` | min 0 |
| Post-trigger samples (`post_samples`) | int | `200` | min 1 |

### Upsample

Increase sampling rate using polyphase interpolation.

- Type identifier: `upsample`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Factor (`factor`) | int | `2` | min 2 |

### Windowing

Multiply a signal by a standard analysis window.

- Type identifier: `windowing`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Window (`window`) | choice | `'hann'` | choices: 'hann', 'hamming', 'blackman', 'bartlett', 'boxcar', 'flattop' |

## Signal Conditioning

### Baseline Correction

Subtract the median or the mean of an initial baseline interval.

- Type identifier: `baseline_correction`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Baseline duration (s) (`baseline_seconds`) | float | `0.5` | min 0.0 |
| Baseline statistic (`method`) | choice | `'median'` | choices: 'median', 'mean' |

### Clipping

Limit values to a lower and upper bound.

- Type identifier: `clipping`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Minimum (`minimum`) | float | `-1.0` |  |
| Maximum (`maximum`) | float | `1.0` |  |

### Deadband

Set values inside a symmetric deadband to zero.

- Type identifier: `deadband`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Threshold (`threshold`) | float | `0.1` | min 0.0 |

### Detrend

Remove a constant or linear trend.

- Type identifier: `detrend`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Trend type (`mode`) | choice | `'linear'` | choices: 'linear', 'constant' |

### Exponential Moving Average

Apply exponential smoothing.

- Type identifier: `exponential_moving_average`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Alpha (`alpha`) | float | `0.2` | min 1e-09; max 1.0 |

### Mean Subtraction

Subtract the signal mean.

- Type identifier: `mean_subtraction`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

### Median Filter

Suppress impulsive noise using a median filter.

- Type identifier: `median_filter`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Kernel size (odd) (`kernel_size`) | int | `5` | min 1 |
| Edge handling (`edge_mode`) | choice | `'nearest'` | choices: 'nearest', 'reflect', 'mirror', 'constant' |

### Missing-Value Interpolation

Interpolate NaN samples using a selected method.

- Type identifier: `missing_value_interpolation`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Method (`method`) | choice | `'linear'` | choices: 'linear', 'nearest', 'cubic', 'spline' |
| Spline order (`spline_order`) | int | `3` | min 1; max 5; shown when `method` is 'spline' |

### Moving Average

Smooth a signal using a centred moving-average window.

- Type identifier: `moving_average`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Window samples (`window_samples`) | int | `5` | min 1 |

### Outlier Removal

Replace robust z-score outliers by interpolation.

- Type identifier: `outlier_removal`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Modified z-score threshold (`threshold`) | float | `3.5` | min 0.1 |

### Rectification

Apply half-wave or full-wave rectification.

- Type identifier: `rectification`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Mode (`mode`) | choice | `'full_wave'` | choices: 'full_wave', 'positive_half', 'negative_half' |

### Remove DC Offset

Subtract the signal mean.

- Type identifier: `remove_dc`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

### Savitzky–Golay Filter

Smooth while preserving local polynomial features.

- Type identifier: `savitzky_golay`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Window length (odd) (`window_length`) | int | `11` | min 3 |
| Polynomial order (`polynomial_order`) | int | `3` | min 0 |

### Scaling

Apply y = scale × x + offset and optionally change units.

- Type identifier: `scaling`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Scale (`scale`) | float | `1.0` |  |
| Offset (`offset`) | float | `0.0` |  |
| Output unit (`output_unit`) | text | `''` |  |

### Signal Centring

Subtract the signal mean.

- Type identifier: `signal_centring`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

### Smoothing

Smooth a signal using a centred moving-average window.

- Type identifier: `smoothing`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Window samples (`window_samples`) | int | `5` | min 1 |

### Thresholding

Apply binary, zero-below or zero-above thresholding.

- Type identifier: `threshold`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Threshold (`threshold`) | float | `0.0` |  |
| Mode (`mode`) | choice | `'binary'` | choices: 'binary', 'zero_below', 'zero_above' |
| Binary high value (`high_value`) | float | `1.0` | shown when `mode` is 'binary' |

### Unit Conversion

Convert common SI/engineering units automatically or apply an explicit scale and offset.

- Type identifier: `unit_conversion`
- Inputs: 1 (signal); required: 1
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Use built-in unit conversion (`automatic`) | bool | `False` |  |
| Source unit; blank = signal metadata (`source_unit`) | text | `''` | shown when `automatic` is True |
| Target unit (`target_unit`) | text | `''` | shown when `automatic` is True |
| Manual scale (`scale`) | float | `1.0` | shown when `automatic` is False; advanced |
| Manual offset (`offset`) | float | `0.0` | shown when `automatic` is False; advanced |
| Manual output unit (`output_unit`) | text | `''` | shown when `automatic` is False; advanced |

## Signal Generators

### Chirp

Generate a swept-frequency chirp signal.

- Type identifier: `chirp`
- Inputs: 0 (none); required: 0
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Amplitude (`amplitude`) | float | `1.0` |  |
| Frequency (Hz) (`frequency`) | float | `1.0` | min 0.0 |
| Phase (degrees) (`phase`) | float | `0.0` |  |
| Offset (`offset`) | float | `0.0` |  |
| Sample rate (Hz) (`sample_rate`) | float | `1000.0` | min 1e-09 |
| Duration (s) (`duration`) | float | `1.0` | min 1e-09 |
| Signal name (`name`) | text | `'Generated signal'` |  |
| Unit (`unit`) | text | `''` |  |
| End frequency (Hz) (`end_frequency`) | float | `100.0` | min 0.0 |
| Sweep method (`method`) | choice | `'linear'` | choices: 'linear', 'quadratic', 'logarithmic', 'hyperbolic' |

### Custom Mathematical Signal

Generate a signal from a safe mathematical expression using t, frequency, amplitude, phase and offset.

- Type identifier: `custom_mathematical_signal`
- Inputs: 0 (none); required: 0
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Amplitude (`amplitude`) | float | `1.0` |  |
| Frequency (Hz) (`frequency`) | float | `1.0` | min 0.0 |
| Phase (degrees) (`phase`) | float | `0.0` |  |
| Offset (`offset`) | float | `0.0` |  |
| Sample rate (Hz) (`sample_rate`) | float | `1000.0` | min 1e-09 |
| Duration (s) (`duration`) | float | `1.0` | min 1e-09 |
| Signal name (`name`) | text | `'Generated signal'` |  |
| Unit (`unit`) | text | `''` |  |
| Formula (`formula`) | multiline | `'amplitude * sin(2*pi*frequency*t + phase) + offset'` |  |

### Gaussian Noise

Generate repeatable zero-mean Gaussian noise.

- Type identifier: `gaussian_noise`
- Inputs: 0 (none); required: 0
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Standard deviation (`amplitude`) | float | `1.0` | min 0.0 |
| Mean / offset (`offset`) | float | `0.0` |  |
| Sample rate (Hz) (`sample_rate`) | float | `1000.0` | min 1e-09 |
| Duration (s) (`duration`) | float | `1.0` | min 1e-09 |
| Signal name (`name`) | text | `'Gaussian noise'` |  |
| Unit (`unit`) | text | `''` |  |
| Random seed (`seed`) | int | `0` | min 0 |

### Pulse

Generate a periodic pulse train with configurable duty cycle.

- Type identifier: `pulse`
- Inputs: 0 (none); required: 0
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Amplitude (`amplitude`) | float | `1.0` |  |
| Frequency (Hz) (`frequency`) | float | `1.0` | min 0.0 |
| Phase (degrees) (`phase`) | float | `0.0` |  |
| Offset (`offset`) | float | `0.0` |  |
| Sample rate (Hz) (`sample_rate`) | float | `1000.0` | min 1e-09 |
| Duration (s) (`duration`) | float | `1.0` | min 1e-09 |
| Signal name (`name`) | text | `'Generated signal'` |  |
| Unit (`unit`) | text | `''` |  |
| Duty cycle (%) (`duty_cycle`) | float | `10.0` | min 0.001; max 100.0 |

### Ramp

Generate a linear ramp using an initial value and slope.

- Type identifier: `ramp`
- Inputs: 0 (none); required: 0
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Initial value (`initial_value`) | float | `0.0` |  |
| Slope (units/s) (`slope`) | float | `1.0` |  |
| Sample rate (Hz) (`sample_rate`) | float | `1000.0` | min 1e-09 |
| Duration (s) (`duration`) | float | `1.0` | min 1e-09 |
| Signal name (`name`) | text | `'Ramp'` |  |
| Unit (`unit`) | text | `''` |  |

### Sawtooth Wave

Generate a configurable sawtooth wave.

- Type identifier: `sawtooth`
- Inputs: 0 (none); required: 0
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Amplitude (`amplitude`) | float | `1.0` |  |
| Frequency (Hz) (`frequency`) | float | `1.0` | min 0.0 |
| Phase (degrees) (`phase`) | float | `0.0` |  |
| Offset (`offset`) | float | `0.0` |  |
| Sample rate (Hz) (`sample_rate`) | float | `1000.0` | min 1e-09 |
| Duration (s) (`duration`) | float | `1.0` | min 1e-09 |
| Signal name (`name`) | text | `'Generated signal'` |  |
| Unit (`unit`) | text | `''` |  |

### Sine Wave

Generate a configurable sine wave.

- Type identifier: `sine`
- Inputs: 0 (none); required: 0
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Amplitude (`amplitude`) | float | `1.0` |  |
| Frequency (Hz) (`frequency`) | float | `1.0` | min 0.0 |
| Phase (degrees) (`phase`) | float | `0.0` |  |
| Offset (`offset`) | float | `0.0` |  |
| Sample rate (Hz) (`sample_rate`) | float | `1000.0` | min 1e-09 |
| Duration (s) (`duration`) | float | `1.0` | min 1e-09 |
| Signal name (`name`) | text | `'Generated signal'` |  |
| Unit (`unit`) | text | `''` |  |

### Square Wave

Generate a configurable square wave.

- Type identifier: `square`
- Inputs: 0 (none); required: 0
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Amplitude (`amplitude`) | float | `1.0` |  |
| Frequency (Hz) (`frequency`) | float | `1.0` | min 0.0 |
| Phase (degrees) (`phase`) | float | `0.0` |  |
| Offset (`offset`) | float | `0.0` |  |
| Sample rate (Hz) (`sample_rate`) | float | `1000.0` | min 1e-09 |
| Duration (s) (`duration`) | float | `1.0` | min 1e-09 |
| Signal name (`name`) | text | `'Generated signal'` |  |
| Unit (`unit`) | text | `''` |  |

### Step

Generate a signal that changes from an initial value to a final value at a selected time.

- Type identifier: `step`
- Inputs: 0 (none); required: 0
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Initial value (`initial_value`) | float | `0.0` |  |
| Final value (`final_value`) | float | `1.0` |  |
| Step time (s) (`step_time`) | float | `0.5` | min 0.0 |
| Sample rate (Hz) (`sample_rate`) | float | `1000.0` | min 1e-09 |
| Duration (s) (`duration`) | float | `1.0` | min 1e-09 |
| Signal name (`name`) | text | `'Step'` |  |
| Unit (`unit`) | text | `''` |  |

### Triangle Wave

Generate a configurable triangle wave.

- Type identifier: `triangle`
- Inputs: 0 (none); required: 0
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Amplitude (`amplitude`) | float | `1.0` |  |
| Frequency (Hz) (`frequency`) | float | `1.0` | min 0.0 |
| Phase (degrees) (`phase`) | float | `0.0` |  |
| Offset (`offset`) | float | `0.0` |  |
| Sample rate (Hz) (`sample_rate`) | float | `1000.0` | min 1e-09 |
| Duration (s) (`duration`) | float | `1.0` | min 1e-09 |
| Signal name (`name`) | text | `'Generated signal'` |  |
| Unit (`unit`) | text | `''` |  |

### White Noise

Generate repeatable uniformly distributed white noise.

- Type identifier: `white_noise`
- Inputs: 0 (none); required: 0
- Outputs: 1 (signal)

| Parameter | Kind | Default | Constraints / visibility |
|---|---|---|---|
| Peak amplitude (`amplitude`) | float | `1.0` | min 0.0 |
| Offset (`offset`) | float | `0.0` |  |
| Sample rate (Hz) (`sample_rate`) | float | `1000.0` | min 1e-09 |
| Duration (s) (`duration`) | float | `1.0` | min 1e-09 |
| Signal name (`name`) | text | `'White noise'` |  |
| Unit (`unit`) | text | `''` |  |
| Random seed (`seed`) | int | `0` | min 0 |
