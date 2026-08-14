## 1.2.6

- Relicensed SignalDojo original application code from MIT to GNU GPL version 3 or any later version (`GPL-3.0-or-later`).
- Replaced the installer’s conventional licence-acceptance page with an informational open-source notice, reflecting that GPL acceptance is not required merely to receive or run the program.
- Added the complete GPL text, copyright notice, corresponding-source guidance, open-source distribution documentation and a separate trademark policy for the SignalDojo name and logo.
- Added Help-menu actions for the full open-source licence and trademark policy, and expanded the About dialog with GPL rights and no-warranty notices.
- Updated PyInstaller and Inno Setup packaging so legal, source and trademark documents are included in official Windows distributions.

## 1.2.4

- Added configurable workflow result auto-open behaviour under **File → Preferences** and **View → Results → Result Display Preferences**.
- Added Smart result display mode: small workflows open all display results, while large workflows open only one useful result and retain the remainder for on-demand access.
- Preserved result tabs the user already had open across subsequent executions.
- Stopped constructing hidden result docks eagerly; unopened results are recreated lazily when selected, reducing tab clutter and Qt widget overhead.
- Tabified manually opened result docks into a single result area and improved completion messages to report how many additional results are available.
- Added UI-independent regression tests for Smart, closed and open-all policies.

## 1.2.3

- Redesigned **Create New Test Campaign** as a responsive, five-step setup experience that remains usable on 1366×768 displays and under Windows display scaling.
- Added a persistent navigation sidebar, Back/Next controls, screen-aware sizing, scrollable step pages and an always-visible Save Campaign action.
- Reorganised input discovery, mapping and metadata extraction into clearer task-focused panels.
- Reorganised execution, reporting and campaign metadata into separate sub-tabs to prevent vertical clipping.
- Added clearer validation banners that take users directly to the step requiring attention.
- Replaced technical values such as `run_file`, `filename_regex` and `upper_limit` with readable UI labels while preserving their stored schema values.
- Improved table sizing, selection behaviour, tooltips, empty states and dark/light theme styling for the campaign setup workflow.

## 1.2.2

- Corrected the campaign dock and toolbar section heading to the singular **Test Campaign**.
- Retained the improved dark-mode campaign table styling introduced in 1.2.1.
- Aligned installer, build-script, package and executable metadata versions.

# Changelog

## 1.2.0

- Added first-class Automated Test Campaigns stored compatibly inside `.sdojo` projects.
- Added typed campaign/run/metric/requirement models, campaign schema migration and backward-compatible project version 4 migration from SignalDojo 1.1.
- Added deterministic file discovery, recursive scanning, explicit file lists, SHA-256 provenance and safe metadata extraction from filenames, folders, file properties, first-row columns, sidecar JSON and manual values.
- Added isolated sequential and bounded-parallel campaign execution with progress, cancellation, retry, partial-failure isolation, persisted reuse and per-run workflow/settings invalidation.
- Added the **Publish Metric** block and campaign aggregation of scalar, signal, spectrum and compact table results.
- Added upper/lower/range/tolerance/Boolean/sample-count/peak/RMS/frequency-band/settling-time requirements with Pass, Fail, Warning, Error, Skipped and Not evaluated results.
- Added a scalable campaign dashboard with sorting, search, status/metadata filters, configurable columns, reference selection and detailed result reopening.
- Added multi-run signal and metric comparison, reference difference/percentage difference, explicit time-base alignment, synchronized cursors, distributions, outlier highlighting and plot/table export.
- Extended the report stack with deterministic campaign PDF, Excel and CSV reports, worksheet sanitisation, spreadsheet formula-injection protection and provenance/sign-off sections.
- Added background file discovery and report generation with visible cancellation.
- Added a generated eight-run motor-current campaign demonstrating normal, excessive-RMS, abnormal-frequency, noisy and malformed recordings.
- Added campaign unit, integration, acceptance, report and Qt model/view smoke tests while retaining the complete SignalDojo 1.1 block-audit suite.
- Updated PyInstaller collection, packaged-import verification, Inno Setup metadata and the Windows upgrade pipeline for version 1.2.0.

## 1.1.0

- Completed a block-by-block schema, branch, numerical and adverse-input audit across all 118 built-in blocks.
- Corrected low-pass and high-pass schemas to expose one cutoff, while band filters expose lower and upper cutoffs; configurable filter fields now change with mode and family.
- Corrected filter-family edge semantics and labels, including magnitude-normalised Bessel cutoffs, Chebyshev passband/stopband edges and effective forward-backward `|H|²` response previews.
- Corrected FIR tap-parity validation, notch/custom-coefficient validation, scalar custom-filter coefficients and readable short-signal failures.
- Corrected FFT power-spectrum normalisation so every supported window preserves integrated mean-square power, and removed synthetic zero-padding from STFT/spectrogram time frames.
- Corrected Frequency-Band Energy to distinguish physical signal energy (`unit²·s`) from mean-square band power (`unit²`), preserve DC and support signed bands for complex signals.
- Improved complex-signal support in smoothing and spectral blocks while making real-only operations reject complex data with readable errors.
- Corrected irregular sampling metadata after import, interpolation and drop operations; prohibited extrapolation in synchronisation/interpolation blocks and rejected contradictory sample-rate metadata.
- Improved CSV/Excel/JSON/HDF5/TDMS/NumPy import behaviour, including HDF Series support, robust time inference, NPZ time-vector discovery and safe complex-value preservation.
- Hardened export of complex, heterogeneous and text data so lossy formats fail clearly and NumPy archives remain loadable with `allow_pickle=False`.
- Corrected trigger extraction, duplicate-channel merge metadata, signal-column naming, Bessel cutoff meaning, threshold NaN preservation and multiple unit/domain rules.
- Strengthened project/result model validation and full-content workflow cache signatures; cached quality warnings now remain visible until invalidation.
- Added conditional parameter visibility to the properties panel and generated `documentation/BLOCK_REFERENCE.md` directly from the live registry.
- Added a complete execution matrix for all 118 blocks, more than 230 declared choice/boolean processing paths, complex/missing/irregular adverse-input checks and focused numerical regressions.
- The cross-platform suite contains 170 tests, and the Windows build adds 8 PySide6 UI smoke tests before packaging.

## 1.0.8

- Fixed the Results menu so live result docks are listed even during the brief lifecycle where no serialisable display record has been installed yet.
- Made Show All Results, Hide All Results, and stale-result pruning use the union of stored result records and currently registered result docks.
- Added a regression contract for dock-only result menu entries and updated the Windows release metadata.

## 1.0.7

- Fixed the final Windows Qt smoke-test failure by exercising result-dock restoration with a visible main window, matching real application usage and Qt visibility semantics.
- Strengthened result restoration by synchronising the dock's visibility and `toggleViewAction()` state after a result tab is closed.
- Prevented first-run dialogs and unsaved-project prompts from interfering with the headless Qt smoke test.
- Revalidated the full Python 3.11 source, processing, persistence, packaging and installer configuration.

## 1.0.6

- Fixed the Windows release test suite so result-persistence UI smoke tests construct valid signals with explicit time vectors.
- Made the Python 3.11 compatibility helper detect invalid f-string syntax when the checker itself is running on Python 3.11.
- Corrected the executable numeric version resource to match the product version.
- Hardened the Windows release pipeline: PowerShell scripts are checked for ambiguous variable interpolation, Inno Setup is required for a full installer build, and the expected installer is verified before checksums are produced.
- Added regression tests for PowerShell build-script safety and installer configuration.

## 1.0.5

- Added reliable inline and dialog editing for comments.
- Added group renaming, numeric size controls, and drag resize handles.
- Added selected-port and compatible-target highlighting.
- Added drag-to-connect while preserving the two-click connection workflow.
- Lightened grid lines in light mode.
- Persisted compressed result tabs in `.sdojo` projects and restored them without reprocessing.

## 1.0.4

- Added a persistent **View → Results** browser for reopening result docks after their tabs are closed.
- Added **Open Result for Selected Block**, **Show All Results**, and **Hide All Results** commands.
- Added **Open Latest Result** to display-block context menus and double-click activation for display blocks.
- Result docks now explicitly remain alive when closed, allowing their latest in-memory result to be restored without rerunning the workflow.
- Removed orphaned result tabs automatically when their owning workflow block is deleted.

## 1.0.3

- Fixed node-port afterimages while dragging blocks on the workflow canvas.
- Explicitly invalidated the complete old and new painted regions of moving nodes, including child ports outside the node rectangle.
- Changed the workflow canvas to Qt's smart viewport update mode.
- Expanded connection bounds to include custom-painted arrowheads and prevent similar partial-redraw artefacts.
- Added rendering-regression tests for dirty-region handling and viewport configuration.

## 1.0.2

- Fixed a Python 3.11 syntax failure in TDMS column-name normalisation caused by a PEP 701-only f-string.
- Added repository-wide Python 3.11 compatibility validation, including detection when tests run under Python 3.12 or 3.13.
- Added compatibility validation to source launch, test, executable and installer build scripts.
- Re-ran the full processing, persistence, packaging and acceptance test suite.

## 1.0.1

- Fixed Windows PyInstaller builds omitting `app.core.blocks` and other first-party package modules.
- Added a root executable launcher to avoid package-as-script analysis ambiguity.
- Added an explicit first-party hidden-import list plus automatic `app.*` submodule collection.
- Added a dedicated PyInstaller hook for the local `app` package.
- Added a packaged-import self-test that makes the build fail before release when a critical module is absent.

## 1.0.0

- Expanded from six MVP blocks to 118 registered blocks across eight categories.
- Added typed result models, safe formulas, spectral/time-frequency analysis and broad import/export support.
- Added incremental DAG caching, run-selected, memory reporting and source-file change detection.
- Added copy/paste, undo/redo, grouping, comments, alignment, tidy layout, minimap and typed connection validation.
- Added import preview, filter-response preview, scope region measurements, spectrum/table/spectrogram docks and workflow reports.
- Added versioned project migration, backups, autosave/recovery, relative paths and missing-file relinking.
- Added plugin discovery, diagnostics, preferences, tutorial, recent projects and three complete examples.
- Updated Windows build, installer, documentation and test infrastructure.

## 0.1.0

- Initial Stage-1 MVP with Import, Gain, Offset, Low-Pass, Scope and Export blocks.
