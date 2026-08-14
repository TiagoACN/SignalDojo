# User Guide

## Workspace

The main window has a searchable block library, central workflow canvas, properties panel, minimap, status/progress area and dockable result viewers. Panels can be resized, moved and hidden from the View menu.

## Constructing workflows

Drag a block from the library or double-click it. Click an output port, then a compatible input port. Port tooltips identify data types. SignalDojo rejects duplicate inputs, incompatible types, self-connections and circular dependencies.

Use middle-mouse drag to pan, the wheel to zoom, rubber-band selection for multiple items, and Delete to remove selected items. Ctrl+C/Ctrl+V and Ctrl+D copy, paste and duplicate. Edit menu commands align and distribute selected blocks. **Tidy Workflow** arranges blocks by dependency level.

Comments are editable yellow notes. Group boxes visually organise work but do not alter processing semantics.

## Configuring blocks

Select a block to open its properties. Changes are validated during execution and invalidate the relevant processing cache. File parameters use native file pickers. Advanced parameters are collapsed by default.

## Execution

- **F5:** run all blocks.
- **Ctrl+F5:** run selected blocks and all dependencies.
- **Shift+F5:** request cancellation.
- **Clear Processing Cache:** force all blocks to recompute.
- **Automatically Run After Changes:** debounce changes and rerun when the workflow is valid.

Completed blocks are green, cached blocks purple, processing blocks blue and failures red. The status bar reports duration, cache reuse, sample count and peak traced memory.

## Importing data

Import Data supports CSV, TSV, text, Excel, JSON, NPY, NPZ, optional HDF5 and optional TDMS. It can expose up to four selected signal columns. Configure time as numeric seconds or timestamps; when no time column exists, provide a sample rate. Missing values may be interpolated, dropped, replaced with zero/mean, or preserved.

## Visualisation

Scope supports four signals, display decimation, zoom/pan, grid/legend controls, two time cursors, a movable measurement region, RMS readout, clipboard copy and PNG/SVG/PDF export. Spectrum Analyser accepts either a signal or a Spectrum result. Spectrogram Viewer displays time-frequency matrices. Data Table and Statistics Display show tabular/scalar results.

Closing a result tab hides it but keeps its latest result in memory. Restore it from **View → Results**, select its display block and press **Ctrl+Shift+R**, choose **Open Latest Result** from the block's context menu, or double-click the display block. **Show All Results** restores every hidden result tab. Results remain available until they are reset, replaced by a later workflow run, their owning block is deleted, or the project is closed.

By default, **Smart** result display opens every display-block result when a workflow has three or fewer results. For larger workflows, SignalDojo opens one useful result and keeps the others available on demand, preventing a large tab stack. Change this under **File → Preferences → Auto-open workflow results** or **View → Results → Result Display Preferences**. Existing result tabs that you deliberately left open remain open after rerunning the workflow.

## Projects and recovery

`.sdojo` is a documented JSON project format. It stores blocks, parameters, positions, connections, labels, comments, groups, project notes and view preferences. Files inside the project directory are stored relatively. Existing project files receive `.bak` backups before replacement. Dirty projects are periodically written to `%USERPROFILE%\.signaldojo\recovery\autosave.sdojo` and offered after an interrupted session.

## Reports

**File → Export Project Report** creates HTML or PDF containing project metadata, source files, workflow diagram, block settings, selected processed signals, tables, statistics and application version. Export Report blocks can also create reports inside workflows.

## Automated test campaigns

SignalDojo 1.2 can apply the current workflow to a folder or explicit list of files. Create and configure campaigns from the **Campaign** menu. Each run is isolated, records its checksum and provenance, publishes compact metrics, evaluates requirements and persists completed results for reuse after reopening.

Use **Publish Metric** to assign stable names to campaign outputs. The campaign requirements layer supports limits, ranges, tolerances, warning/failure zones, Boolean checks and specialised engineering aliases. Missing or invalid values return Error rather than passing.

The Test Campaign Dashboard supports search, sorting, status and metadata filters, configurable columns, reference selection, run-detail reopening, retry and report generation. Select multiple runs to open the comparison workspace. See `TEST_CAMPAIGNS.md` for the complete setup, execution, comparison and reporting procedure.
