<div align="center">

<img src="resources/signaldojo.png" alt="SignalDojo logo" width="150">

# SignalDojo

### Visual signal processing and automated engineering testing — without writing code

SignalDojo is a free and open-source desktop application for importing, processing, analysing, visualising and batch-testing sampled engineering data through graphical block-based workflows.

Version **1.2.6** — production-hardening and attribution release.

[![Version](https://img.shields.io/badge/version-1.2.6-4c78a8)](./CHANGELOG.md)
[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-3776AB?logo=python&logoColor=white)](./pyproject.toml)
[![Qt](https://img.shields.io/badge/UI-PySide6-41CD52?logo=qt&logoColor=white)](./requirements.txt)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-blue)](./LICENSE)
[![Platform](https://img.shields.io/badge/primary%20platform-Windows%2010%20%7C%2011-0078D4?logo=windows)](#installation)
[![Tests](https://img.shields.io/badge/tests-248%20passed-success)](./VALIDATION_1.2.6.md)

**Build workflows visually. Process one recording or one thousand. Extract engineering metrics. Evaluate requirements. Compare runs. Generate reports.**

[Download](#installation) · [Quick Start](#quick-start) · [Test Campaigns](#automated-test-campaigns) · [Documentation](#documentation) · [Contributing](#contributing) · [License](#license-and-redistribution)

</div>

---

## Why SignalDojo?

Engineering data analysis often starts simply: import a CSV, filter a signal, calculate a metric and make a plot. The difficulty appears when that analysis has to be repeated consistently across dozens or hundreds of recordings, shared with another engineer, audited later, or turned into a repeatable test process.

SignalDojo turns that process into a visual workflow.

Instead of maintaining one-off scripts for every analysis, you can connect reusable processing blocks on a canvas, inspect intermediate results, save the complete workflow as a `.sdojo` project and run it again on new data. **Automated Test Campaigns** extend the same idea to batch testing: apply one workflow independently to many recordings, publish named metrics, evaluate pass/fail requirements and export a consolidated report.

Typical use cases include:

- Motor-current and electrical-signal analysis
- Product validation and engineering test campaigns
- Accelerometer and sensor-data processing
- Filter design and signal conditioning
- FFT, PSD and time-frequency analysis
- Repeated laboratory measurements
- Pass/fail evaluation of recorded tests
- Comparing production units or prototypes against a reference
- Preparing engineering reports from large collections of test files
- Teaching and learning practical signal processing

---

## Creator and project stewardship

SignalDojo was created by **Tiago Alvarez Calderon Newton** and is maintained as an open-source engineering project with contributions from the SignalDojo community. Creator and copyright attribution is documented in [`CREDITS.md`](CREDITS.md) and [`COPYRIGHT`](COPYRIGHT).

Official Windows builds are distributed through the SignalDojo project's designated release channels. The software itself remains available under GPL-3.0-or-later; the separate [`TRADEMARK_POLICY.md`](TRADEMARK_POLICY.md) exists to distinguish official SignalDojo releases from unofficial modified builds without reducing the rights granted by the GPL.

---

## Highlights

### Visual workflow editor

- Drag-and-drop block-based processing canvas
- Typed ports and connection validation
- Automatic cycle prevention
- Searchable block library
- Properties editor with validation
- Undo / redo
- Copy / paste / duplicate
- Comments and resizable groups
- Alignment and distribution tools
- Automatic workflow layout
- Minimap and zoom/pan navigation
- Dark and light themes
- High-DPI support
- Persistent dock layouts

### Signal processing and analysis

SignalDojo 1.2.6 contains **119 built-in blocks** covering major workflows such as:

- Data import and export
- Signal generation
- Signal conditioning
- Digital filtering
- FIR and notch filtering
- Custom filter coefficients
- Resampling and synchronisation
- Mathematical operations
- Safe custom expressions
- Descriptive statistics
- RMS, mean, standard deviation, min/max and peak-to-peak analysis
- Peak detection
- Envelope detection
- Numerical differentiation and integration
- Autocorrelation and cross-correlation
- FFT and spectrum analysis
- PSD and spectral measurements
- STFT and spectrograms
- Frequency-band energy
- Signal-to-noise ratio
- Linear regression
- Histograms
- Campaign metric publishing

SignalDojo deliberately avoids silently fixing incompatible data. For example, signals with different time bases are not silently truncated or resampled; insert the appropriate **Resample** or **Synchronise Signals** operation explicitly so the engineering decision remains visible in the workflow.

### Interactive results

- Multi-signal scopes
- Spectrum displays
- Spectrograms
- Tables and statistics
- Zoom and pan
- Cursors and measurement regions
- RMS measurements
- Plot export
- Persistent result docks
- Reopen results without rerunning the workflow
- Smart result-tab management for large workflows

By default, workflows with only a few display results open them automatically. Larger workflows open a useful result while keeping the rest available through **View → Results**, preventing large stacks of unwanted tabs.

### Reproducible projects

Projects use the `.sdojo` format and store the workflow together with the information required to reconstruct it.

Features include:

- Versioned JSON project format
- Relative file paths where possible
- Atomic saves
- `.bak` backups
- Autosave and crash recovery
- Persisted display results
- Schema migration
- Compatibility with SignalDojo 1.1 projects
- Project notes and metadata
- Workflow layout persistence

---

# Automated Test Campaigns

SignalDojo 1.2 introduced a first-class **Test Campaign** system for turning a normal signal-processing workflow into a repeatable engineering test.

A single campaign can discover hundreds or thousands of recordings, process each recording independently and retain a compact set of results and provenance for every run.

## Example

A motor-current validation workflow might be:

```text
80 motor-current CSV files
        │
        ▼
Import Data
        │
        ▼
Signal conditioning / filtering
        │
        ├───────────────┐
        ▼               ▼
       RMS             FFT
        │               │
        ▼               ▼
 Publish Metric    Publish Metric
 "rms_current"    "dominant_frequency"
        │               │
        └───────┬───────┘
                ▼
        Campaign requirements
                │
                ▼
     Pass / Fail / Warning
                │
                ▼
 PDF + Excel + CSV report
```

Instead of manually opening all 80 files, the workflow is defined once and reused consistently.

## Campaign capabilities

- Input folder or explicit file list
- Extension filters
- Recursive folder discovery
- Preview of discovered files
- Mapping files to workflow **Import Data** blocks
- Stable run identifiers
- SHA-256 source-file checksums
- Per-run provenance
- Safe metadata extraction
- Sequential execution
- Conservatively bounded parallel execution
- Overall and per-run progress
- Cancellation
- Failed-run retry
- Failure isolation — one damaged file does not abort the entire campaign
- Persisted completed results
- Selective cache invalidation
- Reference-run selection
- Multi-run comparison
- Consolidated reporting

### Metadata sources

Campaign metadata can come from:

- File names using safe patterns
- Parent folder names
- Imported file properties
- First-row columns
- Sidecar JSON files
- Manual values
- Arbitrary custom metadata fields

No unrestricted `eval` is used for metadata extraction.

### Publish Metric

The **Publish Metric** block exposes compact engineering results to a Test Campaign using stable metric names.

Typical published metrics include:

- RMS
- Mean
- Standard deviation
- Minimum
- Maximum
- Peak-to-peak
- Dominant frequency
- Frequency-band energy
- Rise time
- Settling time
- Sample count
- Duration
- Safe custom scalar expressions

Suitable outputs from existing analysis blocks can also be used directly, avoiding duplicate processing logic.

### Requirements

Campaign requirements support:

- Upper limit
- Lower limit
- Inclusive range
- Exclusive range
- Target with absolute tolerance
- Target with percentage tolerance
- Warning and failure thresholds
- Boolean conditions
- Minimum sample count
- Peak limits
- RMS limits
- Frequency-band limits
- Settling-time limits

Requirement results use explicit states:

`Pass` · `Fail` · `Warning` · `Error` · `Skipped` · `Not evaluated`

Missing, invalid, NaN or incompatible values never silently pass.

### Campaign dashboard

The Test Campaign dashboard uses Qt's model/view architecture and is designed for large run sets rather than creating a widget for every row.

It provides:

- Total run count
- Passed / failed / warning / error / pending counts
- Overall progress
- Search
- Status filtering
- Metadata filtering
- Sorting
- Configurable metric columns
- Requirement status columns
- Reference selection
- Opening detailed results for individual runs
- Retry controls
- Report generation

### Multi-run comparison

Select campaign runs and compare them in a dedicated workspace:

- Signal overlays
- Reference run
- Difference from reference
- Percentage difference
- Synchronized cursors
- Shared zoom and pan
- Run visibility controls
- Metric comparison table
- Scalar distributions
- Outlier highlighting
- Plot/table export
- Explicit alignment and resampling policies for differing time bases

SignalDojo does **not** silently compare incompatible sample grids.

### Campaign reports

Campaign reports can be exported as:

- **PDF**
- **Excel workbook**
- **CSV result table**

The Excel output can contain separate worksheets such as:

- Summary
- Campaign
- Inputs
- Runs
- Metrics
- Requirements
- Errors
- Provenance

Exports sanitize worksheet names and protect text fields against spreadsheet formula injection.

---

# Supported data formats

## Import

| Format | Support |
|---|---|
| CSV | ✅ |
| TSV | ✅ |
| Delimited text | ✅ |
| Excel (`.xlsx`, `.xls` where supported) | ✅ |
| JSON | ✅ |
| NumPy (`.npy`, `.npz`) | ✅ |
| HDF5 | ✅ |
| TDMS | ✅ |

Import Data can expose multiple selected signal columns. Time may come from numeric seconds or timestamps; if no explicit time column exists, a sample rate can be supplied.

Missing-value policies include interpolation, dropping, replacement and preservation where supported by the operation.

## Export

| Format | Support |
|---|---|
| CSV / TSV | ✅ |
| Excel | ✅ |
| JSON | ✅ |
| NumPy | ✅ |
| HDF5 | ✅ |
| Plot image / vector export | ✅ |
| Project report | ✅ |
| Campaign PDF / Excel / CSV | ✅ |

SignalDojo rejects unsupported lossy conversions rather than silently corrupting complex or heterogeneous data.

---

# Installation

## Recommended: Windows installer

SignalDojo's primary packaged platform is **64-bit Windows 10/11**.

Open the repository's **Releases** page and download the latest official installer:

**`SignalDojo-1.2.6-win64-setup.exe`**

> Official releases should publish the Windows installer, portable ZIP and exact corresponding source archive together.

The installer bundles Python, Qt and runtime dependencies. **End users do not need to install Python separately.**

The installer provides:

- Start Menu shortcut
- Optional desktop shortcut
- `.sdojo` file association
- Upgrade support
- Preservation of user projects, campaigns, settings and plugins
- Open-source information before installation

### Portable build

For a no-install version, use:

**`SignalDojo-1.2.6-win64-portable.zip`**

Extract it and run `SignalDojo.exe` from the extracted directory.

### Verify downloads

Official releases include:

```text
SHA256SUMS.txt
```

Use it to verify that downloaded release files have not changed.

On Windows PowerShell:

```powershell
Get-FileHash .\SignalDojo-1.2.6-win64-setup.exe -Algorithm SHA256
```

Compare the result with the corresponding entry in `SHA256SUMS.txt`.

---

# Quick Start

## Analyse a single recording

1. Launch SignalDojo.
2. Choose **File → Open Example → Noise Filter Example**, or create a new project.
3. Drag **Import Data** from **Inputs & Outputs** onto the workflow canvas.
4. Select the block and choose your data file.
5. Configure the time and signal columns.
6. Use **Workflow → Preview Selected Import** to inspect the data.
7. Add processing blocks such as **Low-Pass Filter**, statistics or FFT.
8. Connect them visually.
9. Add a **Scope**, **Spectrum Analyser**, **Spectrogram Viewer** or **Data Table**.
10. Press **F5** to execute the workflow.
11. Save it with **Ctrl+S** as a `.sdojo` project.

A simple workflow can look like:

```text
Import Data ──┬──────────────► Scope (raw)
              │
              ▼
       Low-Pass Filter ──────► Scope (filtered)
              │
              ▼
          Export Data
```

## Run a Test Campaign

The repository includes a complete generated example under:

```text
examples/motor_current_campaign/
```

It contains eight recordings representing:

- Several normal runs
- Excessive RMS current
- Abnormal dominant frequency
- A noisy run
- A malformed/incomplete file

To try it:

1. Open `examples/motor_current_campaign/motor_current_campaign.sdojo`.
2. Open **Campaign → Campaign Setup**.
3. Review the input discovery and mapping.
4. Review the published RMS-current and dominant-frequency metrics.
5. Review the configured requirements.
6. Press **Ctrl+Shift+F5** to run the campaign.
7. Filter the Test Campaign dashboard for failed or warning runs.
8. Select runs and choose **Compare Selected Runs**.
9. Select a normal reference run.
10. Generate the campaign report.

See [`documentation/TEST_CAMPAIGNS.md`](documentation/TEST_CAMPAIGNS.md) for the complete walkthrough.

---

# Keyboard shortcuts

| Action | Shortcut |
|---|---|
| Save project | `Ctrl+S` |
| Run workflow | `F5` |
| Run selected blocks + dependencies | `Ctrl+F5` |
| Cancel workflow | `Shift+F5` |
| Open selected block's latest result | `Ctrl+Shift+R` |
| Run / resume Test Campaign | `Ctrl+Shift+F5` |
| New Test Campaign | `Ctrl+Shift+N` |
| Campaign Setup | `Ctrl+Shift+E` |
| Fit workflow | `Ctrl+0` |
| Tidy workflow | `Ctrl+T` |
| Block help | `F1` |

---

# Running from source

## Requirements

- Python **3.11, 3.12 or 3.13**
- 64-bit Python recommended
- Git, if cloning the repository

Create an environment on Windows:

```powershell
git clone <YOUR_REPOSITORY_URL>
cd SignalDojo

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m app.main
```

On Linux/macOS, activate the virtual environment with:

```bash
source .venv/bin/activate
```

The packaged release is Windows-focused, while the processing, persistence, campaign and export layers are designed to be testable cross-platform.

## Runtime dependencies

SignalDojo currently pins:

- PySide6 6.8.2.1
- NumPy 2.2.3
- SciPy 1.15.1
- pandas 2.2.3
- pyqtgraph 0.13.7
- Matplotlib 3.10.0
- openpyxl 3.1.5
- nptdms 1.10.0
- PyTables 3.10.2

See [`requirements.txt`](requirements.txt) and [`pyproject.toml`](pyproject.toml) for the authoritative dependency list.

---

# Development

## Run the tests

Install development dependencies:

```powershell
pip install -r requirements-dev.txt
pytest
```

SignalDojo 1.2.6's validated suite contains **248 passing tests** in the release validation environment. The suite covers, among other areas:

- Block correctness
- Processing behaviour
- Complex signals
- Missing data
- Irregular sampling
- Filter semantics
- Spectral normalisation
- Project persistence and migration
- Cache correctness
- Result persistence
- Campaign models and serialization
- File discovery
- Metadata extraction
- Input mapping
- Batch execution
- Cancellation
- Partial failure isolation
- Retry behaviour
- Metric extraction
- Every campaign requirement family
- NaN and missing-data behaviour
- Reference-run comparison
- Different sample rates
- Report generation
- Formula-injection prevention
- UI model contracts
- Packaging configuration
- Open-source release/licence contracts

The Windows packaging process also runs PySide6 graphical smoke tests in its Windows environment.

## Python 3.11 compatibility check

```powershell
python .\build_scripts\check_python311_compatibility.py
```

The 1.2.6 release validation passed this check for **74 source files**.

---

# Building the Windows release

A final Windows package must be built on Windows because PyInstaller does not cross-compile Windows bootloaders and the Qt deployment is platform-specific.

## Requirements

- 64-bit Python 3.11
- Inno Setup 6
- PowerShell

Run:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_scripts\build_windows.ps1
```

Expected output:

```text
dist\SignalDojo\SignalDojo.exe
release\SignalDojo-1.2.6-win64-portable.zip
release\SignalDojo-1.2.6-win64-setup.exe
release\SignalDojo-1.2.6-source.zip
release\SHA256SUMS.txt
```

Use:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_scripts\build_windows.ps1 -PortableOnly
```

when you only need the portable package and do not want to run the Inno Setup stage.

The build pipeline checks the Python environment, executes the tests, validates packaged imports, builds the executable, smoke-tests it and prepares release checksums/source packaging.

---

# Project structure

```text
SignalDojo/
├── app/
│   ├── campaign/          # Campaign models, discovery, execution, metrics,
│   │                      # requirements, workflow adaptation and comparison
│   ├── core/              # Result models, block registry and DAG execution
│   ├── exporters/         # Project and Test Campaign report generation
│   ├── plugins/           # Bundled plugin location
│   ├── project/           # .sdojo persistence, migration and recovery
│   ├── ui/                # Main window, canvas, campaign UI and result viewers
│   ├── update/            # Update-related application support
│   ├── application.py
│   ├── main.py
│   └── version.py
│
├── build_scripts/         # Development, testing and Windows build scripts
├── documentation/         # User, developer, plugin and release documentation
├── examples/              # Example workflows, datasets and campaign
├── installer/             # Inno Setup configuration and installer notices
├── pyinstaller_hooks/     # PyInstaller application hooks
├── resources/             # Icons, artwork and Windows version resources
├── tests/                 # Unit, integration, acceptance and UI contract tests
├── SignalDojo.spec        # PyInstaller specification
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── LICENSE
├── COPYING
├── TRADEMARK_POLICY.md
└── README.md
```

For a deeper description of the architecture, see [`documentation/ARCHITECTURE.md`](documentation/ARCHITECTURE.md).

---

# Plugin development

SignalDojo supports bundled and per-user plugins while preserving the central block registry API.

An example plugin is included at:

```text
examples/example_plugin.py
```

The plugin guide covers:

- Defining a custom block
- Inputs and outputs
- Parameter schemas
- Registration
- Processing functions
- Result types
- User plugin locations
- Packaging considerations

See [`documentation/PLUGIN_GUIDE.md`](documentation/PLUGIN_GUIDE.md).

When distributing plugins, ensure their licensing is compatible with how they interact with and are distributed alongside SignalDojo. If you are uncertain about GPL compatibility for a particular distribution model, obtain appropriate legal advice.

---

# Documentation

| Document | Purpose |
|---|---|
| [`QUICK_START.md`](documentation/QUICK_START.md) | First workflow and Test Campaign overview |
| [`USER_GUIDE.md`](documentation/USER_GUIDE.md) | Detailed application usage |
| [`TEST_CAMPAIGNS.md`](documentation/TEST_CAMPAIGNS.md) | Automated Test Campaign workflow |
| [`BLOCK_REFERENCE.md`](documentation/BLOCK_REFERENCE.md) | Generated built-in block reference |
| [`PLUGIN_GUIDE.md`](documentation/PLUGIN_GUIDE.md) | Extending SignalDojo with plugins |
| [`DEVELOPER_GUIDE.md`](documentation/DEVELOPER_GUIDE.md) | Development information |
| [`ARCHITECTURE.md`](documentation/ARCHITECTURE.md) | Application architecture |
| [`PACKAGING.md`](documentation/PACKAGING.md) | Windows packaging process |
| [`TROUBLESHOOTING.md`](documentation/TROUBLESHOOTING.md) | Common problems and fixes |
| [`ISSUE_REPORTING.md`](documentation/ISSUE_REPORTING.md) | How to create a useful bug report |
| [`RELEASE_CHECKLIST.md`](documentation/RELEASE_CHECKLIST.md) | Release validation checklist |

---

# Examples

The repository includes ready-to-run projects and data:

### Noise filtering

```text
examples/noise_filter_example.sdojo
examples/noisy_accelerometer.csv
```

Demonstrates importing noisy sampled data, filtering it and comparing the result visually.

### 50 Hz notch filtering

```text
examples/notch_50hz_example.sdojo
examples/mains_interference.csv
```

Demonstrates removing mains-frequency interference.

### Motor-current analysis

```text
examples/motor_current_analysis.sdojo
examples/motor_current.csv
```

Demonstrates a typical electrical/motor signal-analysis workflow.

### Automated motor-current campaign

```text
examples/motor_current_campaign/
```

Demonstrates repeated processing, published metrics, requirements, failure isolation, reference comparison, persisted results and campaign reporting across eight generated recordings.

---

# Design principles

SignalDojo development follows several principles that are especially important for engineering software:

### Explicit over implicit

The application should not silently resample, extrapolate, coerce incompatible units or hide invalid data. Engineering transformations should be visible and reproducible.

### Deterministic processing

Identical input data and workflow settings should produce identical results. Cache keys include processing configuration and source provenance so stale results are invalidated when inputs change.

### Failure isolation

A bad campaign recording should fail that run, not destroy the entire campaign. Errors are recorded with the affected run and processing continues where possible.

### Provenance

Projects and campaign results retain source paths, checksums, workflow information, application version and processing metadata needed to understand how results were produced.

### Local-first engineering data

Signal processing and Test Campaign execution are performed locally. SignalDojo does not require cloud accounts or mandatory internet connectivity for normal analysis.

### Usability without hiding engineering decisions

The graphical interface aims to reduce repetitive coding while keeping signal-processing choices explicit and inspectable.

---

# Contributing

Contributions are welcome.

Useful contributions include:

- Bug fixes
- New processing blocks
- Additional import/export formats
- Performance improvements
- Test coverage
- Documentation improvements
- Example workflows
- Accessibility and UI improvements
- Reproducible issue reports

## Suggested workflow

1. Fork the repository.
2. Create a feature branch.
3. Make a focused change.
4. Add or update tests for changed behaviour.
5. Run the full test suite.
6. Update documentation where needed.
7. Open a pull request explaining:
   - What changed
   - Why it changed
   - How it was tested
   - Any compatibility implications

Example:

```bash
git checkout -b feature/my-improvement
pytest
git add .
git commit -m "Add my improvement"
git push origin feature/my-improvement
```

Please do not weaken, skip or remove existing tests simply to make a change pass. Fix the implementation or update tests only when intended behaviour has genuinely changed.

Before contributing substantial code, read the developer and architecture documentation.

---

# Reporting bugs

When reporting a bug, include where possible:

- SignalDojo version
- Windows version / operating system
- Whether you are using the installer, portable build or source
- Steps to reproduce the issue
- Expected behaviour
- Actual behaviour
- Complete error/traceback text
- A minimal `.sdojo` project or sample dataset when it can be shared safely

See [`documentation/ISSUE_REPORTING.md`](documentation/ISSUE_REPORTING.md) for the full checklist.

Do **not** upload confidential company or laboratory datasets to a public issue tracker.

---

# Support SignalDojo

SignalDojo is free and open-source software. If it saves you time or is useful in your engineering work, you can help support continued development.

### ❤️ [Support SignalDojo through PayPal](https://paypal.me/SIGNALDOJO)

Financial support is voluntary and does not change the rights granted by the GPL. SignalDojo remains available to use, inspect, modify and redistribute under its open-source licence whether or not you contribute financially.

Other ways to help:

- ⭐ Star the repository
- 🐛 Report reproducible bugs
- 📖 Improve documentation
- 🧪 Contribute tests
- 🔧 Submit useful blocks or fixes
- 🎓 Share SignalDojo with engineering students, laboratories and teams
- 💬 Share examples of how you use the application

---

# License and redistribution

SignalDojo 1.2.6 is free and open-source software licensed under the **GNU General Public License, version 3 or any later version** (`GPL-3.0-or-later`).

In practical terms, the GPL allows you to:

- Use SignalDojo for any purpose
- Study the source code
- Modify the source code
- Make copies
- Redistribute the software
- Redistribute modified versions under the GPL's terms

If you distribute covered binaries or modified versions, you must satisfy the applicable GPL requirements, including the corresponding-source obligations in GPL section 6.

See:

- [`LICENSE`](LICENSE)
- [`COPYING`](COPYING)
- [`SOURCE_CODE.md`](SOURCE_CODE.md)
- [`LICENSES.md`](LICENSES.md)
- [`COPYRIGHT`](COPYRIGHT)

Earlier SignalDojo releases through version 1.2.4 were distributed under the MIT licence. The historical notice is preserved in [`PREVIOUS_MIT_NOTICE.txt`](PREVIOUS_MIT_NOTICE.txt).

## SignalDojo name and logo

The software licence and project branding are separate matters.

The GPL permits forks and modified redistributions. The project's separate [`TRADEMARK_POLICY.md`](TRADEMARK_POLICY.md) asks unofficial modified distributions to use distinct primary branding and not imply that they are official SignalDojo releases.

Examples of acceptable factual descriptions include:

> “ExampleLab Analyzer — based on SignalDojo”

rather than presenting a modified third-party build as though it were an official SignalDojo release.

The trademark policy is currently marked as a **draft for legal review**. It does not reduce the rights granted to the code by the GPL.

---

# Third-party software

SignalDojo depends on third-party open-source libraries, including Qt/PySide6, NumPy, SciPy, pandas, pyqtgraph, Matplotlib, openpyxl, nptdms and PyTables.

These components remain subject to their own copyright notices and licence terms.

See [`LICENSES.md`](LICENSES.md) and the notices distributed with the release for details.

---

# Release integrity and official builds

The SignalDojo project may provide tested **official Windows binaries** for convenience. GPL licensing does not prevent third parties from building or redistributing SignalDojo, but third-party binaries are not automatically official or tested by the project maintainer.

For official releases, publish together:

```text
SignalDojo-X.Y.Z-win64-setup.exe
SignalDojo-X.Y.Z-win64-portable.zip
SignalDojo-X.Y.Z-source.zip
SHA256SUMS.txt
```

This makes the trusted binary, portable package, corresponding source and checksums available from the same release.

---

# Current release validation

SignalDojo 1.2.6 is the production-hardening and attribution release. In addition to preserving the full SignalDojo 1.2 feature set, it finalises creator attribution, production-facing URLs, installer metadata and automated release-readiness gates.

SignalDojo 1.2.6 was validated with:

- **248 tests passed**
- Python 3.11 compatibility validation across **74 source files**
- Repository-wide Python compilation
- Python wheel metadata/build validation
- Package/version consistency checks
- GPL/open-source release contract tests
- Source-checksum validation
- Clean archive extraction checks

A Windows executable and Inno Setup installer must still be built and smoke-tested on Windows because Windows PyInstaller and Qt packaging cannot be validated by cross-compiling from Linux.

See [`VALIDATION_1.2.6.md`](VALIDATION_1.2.6.md).

---

# Roadmap ideas

Possible future directions include:

- Additional engineering data formats
- More reusable example campaigns
- Improved large-campaign visualisation
- Additional statistical and reliability-analysis blocks
- Better workflow templates
- Accessibility improvements
- Performance optimisation for very large datasets
- Expanded plugin tooling
- Community-contributed blocks and examples

Roadmap items are not commitments. New functionality should preserve SignalDojo's local-first, reproducible and engineering-focused design.

---

<div align="center">

## Build. Analyse. Test. Repeat.

**SignalDojo — visual signal processing for engineering data.**

If SignalDojo is useful to you, consider starring the repository, sharing it with another engineer, or supporting its continued development.

</div>
