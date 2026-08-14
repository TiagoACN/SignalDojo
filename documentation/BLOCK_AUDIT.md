# Built-in Block Correctness Audit — SignalDojo 1.1.0

SignalDojo 1.1.0 was audited against the live registry rather than a hand-maintained block list.

## Audit layers

1. **Schema audit:** unique parameter names, valid defaults, numeric limits, choices, conditional visibility dependencies, port counts and declared result types for all 118 registered blocks.
2. **Complete execution matrix:** every registered built-in block is constructed and executed with representative valid data.
3. **Option matrix:** every declared `choice` value and both values of every boolean processing parameter are executed with valid representative inputs. The matrix currently covers more than 230 branches and is guarded against accidental reduction.
4. **Adverse-input matrix:** every non-I/O block is exercised with complex-valued, missing-value and irregularly sampled signals. A block must either return a structurally valid result or raise a readable `BlockError`; raw NumPy, SciPy or pandas exceptions fail the audit.
5. **Focused numerical tests:** frequency-region response and stability, family-specific cutoff semantics, zero-phase effective response, FIR parity, notch and custom coefficients, FFT amplitude/Parseval scaling, complex FFT/PSD/STFT ordering, interpolation domains, units, regression, trigger windows, histogram density, resampling metadata and missing-data behaviour.
6. **Import/export tests:** delimited text, Excel, JSON, NumPy, HDF5 and TDMS paths; timestamp and irregular-time handling; complex and heterogeneous export safety; and round trips where the format supports them.
7. **Workflow contracts:** runtime result-type checking, full-content cache signatures, source-file invalidation, cached warning preservation, project/result persistence, report generation, plugin loading and the complete acceptance workflow.
8. **Documentation contract:** `BLOCK_REFERENCE.md` is generated from the same registry used by the application, and a test fails if it becomes stale.

## Important corrections in 1.1.0

- Low-pass and high-pass filters use one cutoff frequency. Band-pass and band-stop filters use lower and upper cutoffs.
- Configurable IIR/FIR blocks expose only parameters relevant to the selected mode and family.
- Butterworth and magnitude-normalised Bessel filters use cutoff edges; Chebyshev I uses passband edges; Chebyshev II uses stopband edges; elliptic exposes its passband edge with both ripple and stopband attenuation.
- Forward-backward filter previews show the effective squared-magnitude response applied by zero-phase filtering.
- FIR tap parity, Kaiser-window configuration, custom coefficient stability and scalar transfer functions are validated explicitly.
- FFT `power` output is mean-square power per bin and preserves integrated mean-square power for every supported window.
- Frequency-Band Energy now distinguishes record energy (`unit²·s`) from mean-square band power (`unit²`), includes DC correctly and supports signed bands for complex signals.
- STFT frames no longer include artificial boundary-zero padding.
- Interpolation and synchronisation never extrapolate beyond the source or common overlap domain.
- Irregular time vectors cannot carry a misleading nominal sample rate, and missing-sample dropping recomputes sampling metadata.
- Complex sampled signals are preserved where the mathematics supports them; real-only blocks fail with a readable explanation.
- Derived units are not invented when an input unit is unknown, and dimensionless requirements are enforced for logarithm/exponential operations.
- Thresholding preserves missing samples rather than silently converting them to zero.
- HDF Series data, common NPZ time arrays, datetime imports and duplicate merged channel names are handled correctly.
- Lossy text/Excel/JSON export of complex data is blocked; heterogeneous `.npy` tables are rejected; `.npz` text columns are encoded without pickle.
- Workflow signatures hash complete array contents and include schema/metadata, preventing stale cached results after large-array or table-schema changes.

## Test result

The source package contains **170 cross-platform tests plus 8 PySide6 UI smoke tests**. On this validation host, all 170 cross-platform tests pass and the UI module is skipped because PySide6 is supplied by the Windows development/build environment. The Windows release script installs PySide6 and runs all 178 tests before PyInstaller or Inno Setup is allowed to package the application.

## Validation boundary

The numerical engine, persistence, documentation and source package are validated cross-platform. A Windows `.exe` and installer must still be produced and smoke-tested on Windows because PyInstaller does not cross-compile Windows binaries and Qt deployment is platform-specific. The supplied Windows build script performs compatibility checks, compilation, the full test suite, frozen-import verification and startup smoke testing, and aborts on any failure.
