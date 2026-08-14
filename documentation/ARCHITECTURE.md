# Architecture Overview

SignalDojo uses a strict separation between processing and presentation.

- `app.core.models` defines signals, scalars, tables, spectra and spectrograms.
- `app.core.blocks` defines parameter schemas, typed ports, validation and numerical processing.
- `app.core.workflow` validates the DAG, orders execution, fingerprints inputs/parameters, caches outputs and attributes failures to blocks.
- `app.project.io` owns project-version migration, validation, atomic writes, backups and recovery.
- `app.ui` renders the registry into a node editor and dynamic properties panel. UI classes never implement numerical algorithms.
- `app.exporters` provides graph-aware report export.
- `app.update` provides manifest/version/checksum primitives for a distributor-configured update channel.

## Data flow

A connection maps one fixed source output port to one fixed target input port. Each block returns exactly its declared number of outputs. Optional outputs are represented by `None`. Signal operations preserve metadata and append processing-history records.

## Cache model

A node cache key hashes block type, serialised parameters, source-file size/modification time and upstream result signatures. A parameter or upstream change changes the key and naturally invalidates downstream reuse. Non-deterministic output blocks such as displays and exports are marked non-cacheable.

## Threading

The UI builds a core graph and executes it in a `QThread` worker. Progress signals return to the main thread. Blocks are synchronous functions; parallel branch execution is deliberately not enabled because NumPy/SciPy already use native parallelism in some operations and uncontrolled branch concurrency can increase memory pressure.

## Campaign subsystem

Campaign processing is UI-independent and lives in `app.campaign`:

- `models` defines typed, versioned campaign/run/metric/requirement records and serialisation.
- `discovery` performs deterministic local file discovery, checksums and safe metadata extraction.
- `workflow_adapter` clones the associated project into a fresh graph and substitutes Import Data parameters without mutating the source workflow.
- `execution` orchestrates isolated sequential or bounded-parallel runs, cancellation, retry, compact detail retention and persisted reuse.
- `metrics` converts suitable workflow outputs into named compact engineering metrics.
- `requirements` validates/evaluates requirements and aggregates run status.
- `comparison` performs explicit time-base alignment, reference differences, outlier analysis and comparison export.

The optional `campaign` member in project schema version 4 keeps SignalDojo 1.1 projects backward-compatible. Campaign result reuse requires matching input checksum, workflow hash and campaign settings hash. The UI (`app.ui.campaign`) contains setup, model/view dashboard and comparison widgets but no campaign-processing algorithms.

Campaign report generation extends `app.exporters` and reuses the application's workflow/result representation. Long campaign execution, discovery and report generation are moved off the Qt main thread.
