# Build SignalDojo — Professional Block-Based Signal Processing Application

Create a complete, production-ready Windows desktop application named **SignalDojo** using Python.

SignalDojo is intended for engineers, researchers, data scientists, test engineers, students, and laboratory professionals who need to import sensor data, process it through a visual block-based workflow, inspect the results, and export the processed data without writing code.

The application must be capable of being compiled into a standalone Windows `.exe` installer containing everything required to run it. The end user must not need Python or any external dependencies installed.

## 1. Product vision

SignalDojo should provide an intuitive visual environment in which users can:

1. Import sensor data from common file formats.
2. construct signal-processing workflows by dragging blocks onto a canvas.
3. Connect blocks together using directional signal connections.
4. Configure each block through a clear properties panel.
5. Preview and analyse signals using interactive scopes and plots.
6. Run the complete processing pipeline.
7. Export processed data, charts, and workflow configurations.
8. Save and reopen projects.

The experience should resemble a simplified combination of MATLAB Simulink, LabVIEW, Node-RED, and a modern scientific plotting application, while remaining approachable and visually polished.

The application should be professionally relevant and suitable for real engineering and scientific work, not merely a demonstration.

---

# 2. Preferred technology stack

Use:

* Python 3.11 or newer.
* PySide6 for the desktop interface.
* NumPy for numerical operations.
* SciPy for signal-processing functions.
* pandas for tabular data handling.
* pyqtgraph for fast interactive plotting.
* openpyxl for Excel support.
* A suitable permissively licensed node-editor framework, or a custom node-editor implementation using Qt Graphics View.
* PyInstaller for creating a standalone executable.
* Inno Setup, NSIS, or another reliable installer system for producing the final Windows installer.

Only use dependencies that permit commercial redistribution.

Keep the processing engine separate from the user interface so that the system can later support plugins, automated testing, scripting, and additional platforms.

---

# 3. User interface

Create a polished, modern engineering interface with the following layout.

## Main window

The main window should contain:

* A top menu bar.
* A professional toolbar.
* A searchable block library on the left.
* A central node-based workflow canvas.
* A properties and configuration panel on the right.
* An optional data preview or signal inspector panel.
* A bottom status bar showing processing state, sample count, duration, warnings, and errors.
* Dockable and resizable panels.
* Dark and light themes.
* Undo and redo support.

The interface should remain usable on standard laptop displays and scale correctly on high-DPI monitors.

## Workflow canvas

The canvas must support:

* Dragging blocks from the library.
* Moving and arranging blocks.
* Connecting output ports to compatible input ports.
* Multiple inputs and outputs where appropriate.
* Zooming and panning.
* Box selection.
* Copy, paste, duplicate, and delete.
* Alignment and distribution tools.
* Optional snap-to-grid.
* Connection validation.
* Clear indication of signal direction.
* Visual indication of selected, processing, completed, warning, and failed blocks.
* Automatic organisation or “tidy workflow” functionality.
* Comments, labels, and grouping boxes.
* Minimap for large workflows.
* Context menus.
* Keyboard shortcuts.

Prevent invalid connections, such as connecting two output ports or creating circular processing dependencies unless a future feedback-loop feature explicitly supports them.

---

# 4. Data import

Create an **Import Data** block capable of reading:

* CSV files.
* TSV and other delimited text files.
* Microsoft Excel `.xlsx` files.
* JSON data where appropriate.
* NumPy `.npy` and `.npz` files.
* Optional support for HDF5 and TDMS if it can be implemented reliably.

The importer must allow the user to:

* Select the file.
* Preview the first rows.
* Select the header row.
* Choose the delimiter.
* Select one or more signal columns.
* Select or define the time column.
* Define the sampling frequency when no time column exists.
* Define units and signal names.
* Handle timestamps.
* Skip metadata rows.
* Configure decimal and thousands separators.
* Handle missing values.
* Detect invalid rows.
* Choose whether to interpolate, remove, replace, or preserve missing values.
* Import very large datasets without freezing the interface.

Automatically infer likely time columns, signal columns, sampling rates, and data types, but always allow the user to override the inference.

Represent each signal using structured metadata, including:

* Signal name.
* Time values.
* Sample values.
* Sampling frequency.
* Unit.
* Source file.
* Channel name.
* Description.
* Processing history.

---

# 5. Block categories

Organise the block library into clear categories.

## Inputs and outputs

Include:

* Import Data.
* Manual Signal Generator.
* Constant.
* Time Vector.
* Scope.
* Multi-Signal Scope.
* Spectrum Analyser.
* Data Table.
* Statistics Display.
* Export Data.
* Export Plot.
* Export Report.

## Signal generators

Include:

* Sine wave.
* Square wave.
* Triangle wave.
* Sawtooth wave.
* Pulse.
* Step.
* Ramp.
* White noise.
* Gaussian noise.
* Chirp.
* Custom mathematical signal.

Allow the user to configure amplitude, frequency, phase, offset, sampling frequency, duration, and other relevant parameters.

## Basic mathematical operations

Include:

* Add.
* Subtract.
* Multiply.
* Divide.
* Absolute value.
* Negate.
* Power.
* Square root.
* Logarithm.
* Exponential.
* Minimum.
* Maximum.
* Clamp.
* Normalise.
* Standardise.
* Offset.
* Gain.
* Custom equation.

Blocks such as Add, Subtract, Multiply, and Divide should support two or more input signals and clearly define how differences in time vectors or sampling rates are handled.

## Signal conditioning

Include:

* Remove DC offset.
* Detrend.
* Mean subtraction.
* Baseline correction.
* Signal centring.
* Scaling.
* Unit conversion.
* Clipping.
* Deadband.
* Thresholding.
* Rectification.
* Smoothing.
* Moving average.
* Exponential moving average.
* Median filter.
* Savitzky–Golay filter.
* Outlier removal.
* Missing-value interpolation.

## Filters

Include configurable implementations of:

* Low-pass filter.
* High-pass filter.
* Band-pass filter.
* Band-stop filter.
* Notch filter.
* Butterworth filter.
* Chebyshev Type I filter.
* Chebyshev Type II filter.
* Elliptic filter.
* Bessel filter.
* FIR filter.
* Moving-average filter.
* Median filter.
* Custom filter coefficients.

Filter blocks must allow configuration of relevant parameters such as:

* Cut-off frequency.
* Lower and upper cut-off frequencies.
* Filter order.
* Ripple.
* Attenuation.
* Sampling frequency.
* Zero-phase or causal filtering.
* Initial conditions where appropriate.
* Edge handling.

Validate all settings. For example, prevent a cut-off frequency from exceeding the Nyquist frequency and explain the problem clearly.

Provide an optional frequency-response preview showing:

* Magnitude response.
* Phase response.
* Cut-off frequencies.
* Nyquist frequency.
* Filter stability warnings.

## Resampling and time processing

Include:

* Resample.
* Downsample.
* Upsample.
* Decimate.
* Interpolate.
* Crop by time.
* Crop by sample.
* Shift in time.
* Delay.
* Synchronise signals.
* Align by peak.
* Align by cross-correlation.
* Merge signals.
* Split signal.
* Concatenate.
* Windowing.
* Segment signal.
* Trigger-based extraction.

## Analysis

Include:

* Descriptive statistics.
* RMS.
* Mean.
* Median.
* Minimum and maximum.
* Standard deviation.
* Variance.
* Peak-to-peak.
* Crest factor.
* Kurtosis.
* Skewness.
* Zero-crossing rate.
* Peak detection.
* Envelope detection.
* Numerical differentiation.
* Numerical integration.
* Autocorrelation.
* Cross-correlation.
* FFT.
* Power spectral density.
* Short-time Fourier transform.
* Spectrogram.
* Frequency-band energy.
* Signal-to-noise ratio.
* Linear regression.
* Histogram.
* Custom Python expression.

Analysis blocks should expose their results to display blocks and, where appropriate, to downstream processing blocks.

---

# 6. Custom processing

Create a **Custom Formula** block that allows users to define mathematical expressions using named inputs.

Examples:

* `output = input_1 * 2 + input_2`
* `output = abs(signal - mean(signal))`
* `output = where(signal > threshold, signal, 0)`

The application must validate formulas before execution and present readable errors.

Do not expose unrestricted Python execution by default. Use a safe expression parser or restricted environment.

Optionally provide an advanced **Python Script Block** behind a clear warning and advanced-user setting. If implemented, isolate the execution as much as reasonably possible and document the security implications.

Create a plugin architecture that allows additional processing blocks to be added later without modifying the core application.

---

# 7. Signal compatibility and metadata

Every block must define:

* Number and type of inputs.
* Number and type of outputs.
* Accepted data types.
* Required metadata.
* Parameter schema.
* Validation rules.
* Processing method.
* Error messages.
* Display name and description.
* Category and icon.

The processing engine must manage:

* Signals with different lengths.
* Signals with different sample rates.
* Unevenly sampled data.
* Missing samples.
* Timestamps.
* Multiple channels.
* Units.
* NaN and infinite values.
* Complex-valued frequency-domain data.
* Scalar results.
* Table results.

Do not silently resample or truncate signals. Inform the user and require an explicit policy or processing block.

Preserve signal metadata through the workflow wherever possible.

Add a visible processing-history record so users can understand how an output signal was produced.

---

# 8. Scopes and visualisation

Create a professional interactive **Scope** block.

The scope should support:

* One or multiple signals.
* Time-domain plotting.
* Automatic or manual axis scaling.
* Zoom and pan.
* Cursor measurements.
* Delta-time and delta-amplitude measurements.
* Signal legend.
* Grid display.
* Line style and thickness options.
* Signal visibility toggles.
* Units on axes.
* Channel names.
* Markers.
* Peak annotations.
* Region selection.
* Exporting the displayed data.
* Exporting plots as PNG, SVG, and PDF.
* Copying plots to the clipboard.
* Full-screen view.
* Live updates during parameter changes where practical.
* Downsampling for display without modifying the underlying data.

Create a **Spectrum Analyser** capable of displaying:

* FFT magnitude.
* Power spectral density.
* Linear or logarithmic frequency scale.
* Linear amplitude or decibel scale.
* Frequency cursors.
* Peak frequency detection.
* Window selection.
* Frequency resolution information.

Create a **Spectrogram** viewer with configurable FFT size, overlap, window type, frequency limits, and colour scale.

Plot rendering must remain responsive with large datasets.

---

# 9. Workflow execution

Implement a directed acyclic graph processing engine.

The engine must:

1. Validate the complete workflow.
2. Determine the correct block execution order.
3. Process only blocks that have changed where possible.
4. Cache intermediate results.
5. Invalidate downstream caches when upstream settings change.
6. Report progress.
7. Support cancellation.
8. Run expensive processing outside the main interface thread.
9. Prevent the interface from freezing.
10. Provide readable errors associated with the exact block that failed.

Support both:

* Manual execution using a Run button.
* Optional automatic execution after changes, using a short debounce delay.

Add execution controls for:

* Run all.
* Run selected block and dependencies.
* Stop.
* Reset.
* Clear cache.

Display execution duration and memory usage where practical.

---

# 10. Data export

The **Export Data** block must support:

* CSV.
* TSV.
* Excel.
* JSON.
* NumPy.
* Optional HDF5.

Allow users to export:

* One signal.
* Multiple signals.
* Time values.
* Metadata.
* Processing history.
* Scalar analysis results.
* Tabular analysis results.

The user must be able to configure:

* Output directory.
* File name.
* Overwrite behaviour.
* Column names.
* Units in headers.
* Numeric precision.
* Time representation.
* Delimiter.
* Decimal separator.
* Missing-value representation.

Also provide a report export feature capable of producing a professional HTML or PDF report containing:

* Project name.
* Project description.
* Source files.
* Workflow diagram.
* Processing settings.
* Selected plots.
* Statistics.
* Export date.
* Signal metadata.
* Application version.

---

# 11. Project management

Create a native SignalDojo project format, such as `.sdojo`.

A project must save:

* Block positions.
* Connections.
* Block parameters.
* Comments and groups.
* File references.
* Signal metadata.
* Scope layout and visual settings.
* Theme and interface layout.
* Project notes.
* Application version.

Prefer a documented JSON-based project structure, optionally packaged as a ZIP archive.

Provide:

* New Project.
* Open Project.
* Save.
* Save As.
* Recent Projects.
* Autosave.
* Crash recovery.
* Project validation.
* Compatibility handling for older project versions.

When source files are moved or missing, allow the user to locate and relink them.

Optionally allow source files to be embedded into the project, while warning about project size.

---

# 12. Professional usability features

Include:

* A first-run welcome screen.
* A short interactive tutorial.
* Example projects.
* Tooltips.
* Searchable block library.
* Favourites or recently used blocks.
* Context-sensitive help.
* Meaningful empty states.
* Clear validation messages.
* Keyboard shortcuts.
* Recent-files menu.
* Autosave and recovery.
* Automatic update-ready architecture.
* About window.
* Application version and build information.
* Link to documentation and issue reporting.
* User-configurable default units and sampling frequency.
* SI unit support.
* Engineering notation.
* Configurable numeric precision.

Create at least three bundled example projects:

1. Removing noise from an accelerometer signal.
2. Applying a notch filter to remove 50 Hz mains interference.
3. Comparing raw and filtered motor-current data using scopes and FFT analysis.

Use synthetic sample data so the examples work immediately after installation.

---

# 13. Reliability and error handling

The application must never fail silently.

Create clear handling for:

* Unsupported files.
* Corrupt files.
* Missing columns.
* Non-numeric data.
* Invalid timestamps.
* Impossible filter parameters.
* Missing sample rate.
* Incompatible signal lengths.
* Incompatible signal units.
* Memory limits.
* Missing source files.
* Invalid workflow connections.
* Circular dependencies.
* Export permission errors.
* Disk-space errors.

Present errors using human-readable explanations and, where possible, a suggested correction.

Write technical details to a rotating log file.

Add an optional diagnostics window containing:

* Application version.
* Python runtime information.
* Operating-system information.
* Installed package versions.
* Recent log entries.
* Project validation information.

Do not expose sensitive file contents in diagnostic reports unless the user explicitly chooses to include them.

---

# 14. Performance

Design SignalDojo to handle large datasets efficiently.

Requirements:

* Avoid unnecessary copies of large arrays.
* Use NumPy vectorisation.
* Load large files in chunks where appropriate.
* Use worker threads or processes for expensive operations.
* Use display decimation for plots.
* Cache intermediate processing results.
* Show memory warnings before potentially unsafe operations.
* Allow the user to cancel long-running processing.
* Keep the interface responsive.

The application should comfortably process ordinary sensor datasets containing millions of samples on a modern engineering laptop.

---

# 15. Architecture

Use a clean, maintainable project structure such as:

```text
SignalDojo/
├── app/
│   ├── main.py
│   ├── application.py
│   ├── ui/
│   ├── node_editor/
│   ├── blocks/
│   │   ├── inputs/
│   │   ├── outputs/
│   │   ├── filters/
│   │   ├── maths/
│   │   ├── conditioning/
│   │   ├── analysis/
│   │   └── visualisation/
│   ├── processing/
│   ├── data_models/
│   ├── project/
│   ├── plugins/
│   ├── exporters/
│   ├── resources/
│   └── utilities/
├── tests/
├── examples/
├── documentation/
├── installer/
├── build_scripts/
├── requirements.txt
├── pyproject.toml
├── README.md
├── LICENSES.md
└── CHANGELOG.md
```

Use:

* Type hints.
* Dataclasses or clearly defined models.
* Separation of concerns.
* Dependency injection where useful.
* Centralised logging.
* Centralised configuration.
* Consistent naming conventions.
* Docstrings for public classes and functions.
* Minimal global state.

The processing blocks should not depend directly on the user-interface classes.

---

# 16. Testing

Add automated tests using pytest.

Tests should cover:

* Data import.
* Signal metadata.
* Filter correctness.
* Mathematical blocks.
* Resampling.
* FFT and analysis functions.
* Workflow ordering.
* Cache invalidation.
* Project save and load.
* Invalid connection handling.
* Missing-file recovery.
* Data export.
* Formula validation.

For filter and analysis tests, compare results against known numerical outputs with appropriate tolerances.

Add basic interface tests where practical.

Include a repeatable smoke-test procedure for the packaged Windows executable.

---

# 17. Branding

Use the name **SignalDojo** consistently.

The visual identity should communicate:

* Precision.
* Engineering.
* Scientific analysis.
* Control.
* Signal flow.
* Modern professional software.

Create:

* A SignalDojo application icon.
* Splash screen.
* About dialog.
* Installer branding.
* Consistent placeholder icons for blocks.
* A restrained professional colour palette.

Avoid a playful or game-like appearance despite the “Dojo” name. The product should feel credible in a laboratory, engineering consultancy, university, or industrial R&D environment.

Suggested tagline:

**SignalDojo — Build, analyse and master your signals.**

---

# 18. Windows executable and installer

Produce a complete Windows build process.

The final installer must:

* Install SignalDojo without requiring Python.
* Bundle all required runtime dependencies.
* Install the application in a standard Windows location.
* Create a Start menu shortcut.
* Optionally create a desktop shortcut.
* Register the `.sdojo` project file extension.
* Include the application icon.
* Include version information.
* Include an uninstaller.
* Avoid triggering unnecessary administrator permissions where possible.
* Work on clean 64-bit Windows 10 and Windows 11 machines.
* Preserve user projects and settings during upgrades.
* Display the licence and installation location.
* Provide a clear installation completion screen.

Create scripts for:

1. Creating a clean virtual environment.
2. Installing exact dependency versions.
3. Running tests.
4. Building the executable.
5. Collecting Qt plugins and required data files.
6. Building the installer.
7. Producing checksums.
8. Creating a distributable release folder.

Include detailed build instructions.

The build process should be repeatable from a clean checkout.

---

# 19. Documentation

Create:

* A professional `README.md`.
* Installation instructions.
* User guide.
* Quick-start guide.
* Developer guide.
* Plugin-development guide.
* Architecture overview.
* Block reference.
* Troubleshooting guide.
* Packaging guide.
* Release checklist.
* Third-party licence notice.

The quick-start guide should explain how to:

1. Import a CSV file.
2. Choose a time and signal column.
3. Add a low-pass filter.
4. Connect the imported signal to the filter.
5. Connect the filter to a scope.
6. Run the workflow.
7. Compare the original and filtered signals.
8. Export the result.

---

# 20. Development approach

Build the application in functional stages.

## Stage 1 — Working foundation

Implement:

* Main window.
* Node editor.
* Import Data block.
* Gain block.
* Offset block.
* Low-pass filter block.
* Scope block.
* Export Data block.
* Workflow execution.
* Project saving and loading.

This stage must already be functional and testable.

## Stage 2 — Core engineering functionality

Add:

* Main filter collection.
* Mathematical operations.
* Signal generators.
* Statistics.
* FFT.
* Resampling.
* Improved scope tools.
* Large-file handling.
* Undo and redo.
* Error reporting.

## Stage 3 — Professional release

Add:

* Themes.
* Tutorials.
* Example projects.
* Reports.
* Plugin support.
* Full automated tests.
* Installer.
* Branding.
* Documentation.
* Crash recovery.
* Diagnostics.

Do not create empty placeholder buttons or non-functional menu options. Every visible feature must either work or be clearly marked as unavailable in the current version.

---

# 21. Deliverables

Provide the complete project, including:

* All Python source files.
* UI resources.
* Icons and branding assets.
* Sample datasets.
* Example projects.
* Automated tests.
* Dependency files.
* PyInstaller configuration.
* Installer configuration.
* Build scripts.
* Documentation.
* Licence information.
* Release checklist.

Also provide:

* The exact command used to run the application in development.
* The exact commands required to run tests.
* The exact commands required to build the executable.
* The exact commands required to build the installer.
* The expected final file locations.
* A list of known limitations.

Do not provide only pseudocode, isolated examples, or a high-level design. Generate complete, runnable code.

---

# 22. Acceptance criteria

The project is acceptable when a user can perform the following sequence on a clean Windows computer:

1. Install SignalDojo using a single `.exe` installer.
2. Launch it without Python installed.
3. Import a CSV containing a time column and sensor values.
4. Drag the imported signal block onto the canvas.
5. Add a low-pass filter.
6. Configure the filter cut-off frequency and order.
7. Connect the signal to the filter.
8. Add a scope.
9. Connect both the raw and filtered signals to the scope.
10. Run the workflow.
11. Zoom into the plotted signals.
12. Inspect values using cursors.
13. Export the filtered signal to CSV.
14. Save the workflow as a `.sdojo` project.
15. Close the application.
16. Reopen the project and reproduce the same result.

The application should look polished, respond reliably, provide scientifically correct results, and be structured so that it can grow into a commercially viable engineering product.
