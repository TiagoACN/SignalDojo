# Automated Test Campaigns

SignalDojo 1.2 applies one validated workflow independently to many engineering recordings. Each source file becomes a campaign run with its own checksum, metadata, metrics, requirements, warnings, errors and workflow provenance.

## Core concepts

**Campaign** — configuration, workflow association, file discovery, mappings, metadata rules, metrics, requirements, report options and persisted run results.

**Run** — one discovered source file. Its stable identifier is derived from its path relative to the selected input folder. Run results are reused only when the input checksum, workflow hash and campaign settings hash are unchanged.

**Metric** — a named compact result used in the dashboard, requirements and reports. Publish metrics with a **Publish Metric** block or map a suitable output from an existing statistics/analysis block.

**Requirement** — a declarative evaluation of one metric. Missing, non-finite or unit-incompatible data returns Error rather than passing silently.

**Reference run** — a selected run used for metric deltas and multi-run signal comparison.

## Create a campaign

1. Build or open the workflow that should be applied to every file.
2. Add **Publish Metric** blocks for the outputs that should become campaign columns.
3. Choose **Campaign → New Test Campaign** (`Ctrl+Shift+N`).
4. Select **Current workflow** or browse to another `.sdojo` project.
5. Select an input folder or multiple explicit files.
6. Choose extensions and enable recursive scanning when required.
7. Start discovery and review the deterministic file preview.
8. Map each workflow Import Data block:
   - **Run file** substitutes the current campaign file.
   - **Fixed file** uses one constant file for every run.
   - **Metadata field** reads a path produced by a metadata rule.
9. Configure metadata extraction rules.
10. Select metric definitions and configure requirements.
11. Optionally choose a reference run after discovery/execution.
12. Choose a report directory/template and report sections.
13. Save the `.sdojo` project before execution.

The setup dialog uses five guided steps—**Basics**, **Input files**, **Metrics**, **Requirements**, and **Run & report**—with an always-visible navigation footer. Each step scrolls independently, so controls remain reachable on a 1366×768 display and under Windows display scaling. Invalid mappings, inaccessible paths, missing metric names and invalid limits appear in a persistent validation banner and automatically return you to the relevant step.

## Metadata extraction

Rules are declarative and never use unrestricted `eval`.

| Source | Configuration | Example |
|---|---|---|
| Filename regex | Safe regular expression and group | `TEST-(?P<serial>[A-Z]\d+)` |
| Parent folder | Parent depth | Product family folder |
| File property | `name`, `stem`, `extension`, `parent`, `size_bytes`, `modified_utc` | Original file size |
| File column | First-row column name | Firmware version column |
| Sidecar JSON | Key in `recording.csv.json` or `recording.json` | Operator, rig and notes |
| Manual | Literal value | Campaign-wide test condition |

Mark a rule **Required** when execution should fail for that run if metadata is absent. Optional extraction failures are retained as warnings.

Recommended fields include Test ID, serial number, operator, test date, test rig, firmware/software version, test condition and notes. Arbitrary additional fields are supported.

## Publish Metric block

The Campaign category contains **Publish Metric**. It accepts scalar, signal, spectrum or compact table inputs and outputs a campaign-compatible scalar.

Properties:

- **Metric name** — stable machine-readable identifier used by requirements and exports.
- **Display label** — optional dashboard label.
- **Unit override** — blank preserves the inferred unit.
- **Description** and **numeric format**.
- **Aggregation** — automatic/value, mean, RMS, standard deviation, minimum, maximum, peak-to-peak, dominant frequency, sample count, duration, rise time, settling time, first, last or safe custom expression.

Inputs that cannot be represented as a compact campaign metric produce an actionable block error.

## Requirements

Supported conditions:

- Upper limit
- Lower limit
- Inclusive range
- Exclusive range
- Target with absolute tolerance
- Target with percentage tolerance
- Warning and failure thresholds
- Boolean condition
- Minimum sample count
- Peak limit
- RMS limit
- Frequency-band limit
- Settling-time limit

Each result records measured value, required limit, nearest margin, unit, status and explanation. Requirement statuses are Pass, Fail, Warning, Error, Skipped and Not evaluated. Run status aggregates the enabled requirement results and processing errors.

Use an explicit **Unit Conversion** block when the workflow metric unit differs from the requirement unit. SignalDojo does not silently reinterpret units.

## Execute and resume

Choose **Campaign → Run Campaign** (`Ctrl+Shift+F5`). The dashboard shows overall progress and the currently executing run. Execution runs in a background thread so the main window remains responsive.

- **Cancel Campaign** stops pending work and records cancelled state.
- **Retry Failed Runs** forces failed, error and cancelled runs while reusing unchanged successful runs.
- Sequential mode is safest and is the default.
- Parallel mode is bounded to a maximum of eight workers and should be used only when workflows and available memory permit it.
- Every run receives a newly constructed workflow graph with caching disabled inside that graph; results and block state cannot leak between runs.
- A corrupt file affects only its own run.
- Full datasets are released after metric extraction. A configurable limited number of decimated detail results is retained for reopening/comparison.

After saving, completed results are persisted in the campaign. Reopening the project avoids recalculation when the source checksum, workflow hash and campaign settings hash are unchanged. Changing one file invalidates only its run. Changing the workflow or metric/requirement settings invalidates the affected campaign results.

## Dashboard

Open **View → Test Campaign Dashboard** when hidden. The dashboard uses Qt model/view classes rather than one widget per cell, allowing responsive sorting/filtering for at least 1,000 run rows.

It shows total, completed, passed, failed, warning, error, cancelled/skipped and pending counts; progress; execution duration; file and metadata columns; metric values; and requirement statuses.

Available actions:

- Search across file/run/metadata text.
- Filter by status and metadata.
- Sort any visible column.
- Configure visible metric/requirement columns.
- Open a run's retained detailed results.
- Set/change the reference run.
- Select several rows for comparison.
- Retry failed runs or generate a report.

Statuses always include text, not colour alone.

## Compare runs

Select runs and choose **Campaign → Compare Selected Runs**.

The comparison workspace supports:

- Signal overlays with per-run visibility and configurable colours.
- A selected reference run.
- Absolute or percentage difference from reference.
- Synchronized cursors, shared zoom and pan.
- Metric comparison and outlier highlighting.
- Scalar metric distributions.
- PNG/SVG/PDF plot export and CSV/Excel comparison-table export.

Time-base handling is explicit:

- **Exact** requires compatible sample times.
- **Interpolate to reference** requires the compared signal to cover the full reference interval.
- **Overlap** clips to the common time interval and interpolates only within that overlap.

No extrapolation or silent sample-rate coercion occurs. The workspace limits simultaneous traces when required for responsiveness and explains the configured limit.

## Consolidated reports

Choose **Campaign → Generate Campaign Report**. Report generation runs in a background worker and can be cancelled.

Outputs:

- Professional paginated PDF.
- Excel workbook with Summary, Campaign, Inputs, Runs, Metrics, Requirements, Requirement Definitions, Workflow Parameters, Errors and Provenance sheets.
- CSV run-result table.

Optional sections include title/logo, campaign/test information, equipment/operator, workflow diagram and parameters, input summary, pass/fail and requirement summaries, metric statistics/distributions, comparison plots, failed-run detail, errors/warnings, full run table, software/workflow/checksum provenance and sign-off.

Worksheet names are sanitised. Text beginning with `=`, `+`, `-` or `@` is escaped to prevent spreadsheet formula injection.

## Motor-current example

Open `examples/motor_current_campaign/motor_current_campaign.sdojo`.

The workflow imports current recordings, publishes:

- `rms_current` in A
- `dominant_frequency` in Hz

and evaluates limits that intentionally classify:

- Four normal runs as Pass.
- One excessive-current run as Fail.
- One abnormal-frequency run as Fail.
- One noisy run as Warning.
- One malformed file as Error without aborting the campaign.

A normal run is stored as the reference. The project includes persisted completed results, so it can be inspected immediately. Use `generate_example.py` to regenerate deterministic input files and campaign results.

## Recovery and auditability

Campaigns preserve source paths, file name, input SHA-256, file metadata, custom metadata, start/completion times, duration, status, metrics, requirements, warnings/errors, workflow hash, settings hash, SignalDojo version and retained details.

Project autosave and crash recovery include campaign state. User projects, settings and plugins are stored outside the installation directory and are preserved during normal upgrades and uninstall.

## Troubleshooting

**No files discovered** — check the folder, selected extensions and recursive option.

**Input mapping invalid** — ensure each required Import Data block has exactly one mapping. Empty unmapped Import Data blocks are rejected.

**Missing metric** — verify the source node/port or matching Publish Metric name and run the workflow normally once to inspect its output.

**Unit mismatch** — add Unit Conversion or correct the requirement unit.

**Run changed after execution** — the source checksum or modification metadata changed; restore a stable file and retry.

**Comparison incompatible** — choose explicit overlap/interpolation or use existing SignalDojo resampling/alignment blocks in the workflow.

**Report cannot be written** — choose a writable local output directory and close any existing Excel/PDF file that is locked by another application.
