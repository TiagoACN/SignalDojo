# Developer Guide

## Environment

Use Python 3.11 on Windows. Run `build_scripts/create_environment.ps1`, then `python -m app.main`.

## Adding a built-in block

Subclass `ProcessingBlock`, declare `type_name`, `display_name`, `category`, `description`, fixed input/output counts, port types and a tuple of `ParameterSpec`. Decorate the class with `@register_block`. Keep Qt imports out of processing modules. Validate physical constraints before calling NumPy/SciPy and raise `BlockError` with a correction-oriented message.

## Result types

Use `SignalData` for one-dimensional sampled signals, `ScalarResult` for named values, `TableResult` for dataframes, `SpectrumData` for one-dimensional frequency results and `SpectrogramData` for frequency-by-time matrices.

## Tests

Numerical tests should compare known frequencies, amplitudes or SciPy reference outputs with explicit tolerances. Persistence tests should exercise migration and corrupt input. Workflow tests should cover cycles, type mismatches, dependency ordering and cache reuse.

## Logging

Use module-level `logging.getLogger(__name__)`. Logs rotate under `%USERPROFILE%\.signaldojo\logs`.

## Campaign API

Keep campaign processing independent from Qt. `TestCampaign` and related dataclasses are serialised with `campaign_to_dict` and reconstructed/migrated with `campaign_from_dict`. New persisted fields require an explicit campaign-schema migration and project-schema compatibility test.

`CampaignRunner` must construct a fresh workflow graph for every run and must not mutate the source workflow document. Campaign plugins or command-line callers can use it without creating a `QApplication`.

Metric publishers should return `ScalarResult` with `metadata["published_metric"] = True` and a stable `metric_name`. Prefer the built-in **Publish Metric** block. Do not duplicate requirement evaluation inside blocks; specialised names such as RMS limit remain aliases in the campaign requirements layer.

Campaign tests should cover serialization, invalidation, partial failures and deterministic reports. Any new metadata rule must be declarative and must not execute arbitrary user code.
