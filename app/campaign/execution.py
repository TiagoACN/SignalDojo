# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Isolated, resumable batch execution for SignalDojo test campaigns."""

from __future__ import annotations

from concurrent.futures import CancelledError, Future, ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import dataclass
import logging
from pathlib import Path
from threading import Event, Lock
from time import perf_counter
from typing import Any, Callable, Iterable

import numpy as np
import pandas as pd

from app.version import VERSION
from app.core.blocks import BlockError
from app.core.models import ScalarResult, SignalData, SpectrumData, TableResult
from app.core.workflow import ExecutionReport
from app.project.io import load_project
from app.project.result_codec import serialise_result

from .discovery import DiscoveryCancelled, discover_files, file_checksum, reconcile_runs
from .metrics import aggregate_metric
from .models import (
    CampaignRun, RunStatus, TestCampaign, TERMINAL_RUN_STATUSES, utc_now,
)
from .requirements import aggregate_run_status, evaluate_requirements
from .workflow_adapter import (
    build_campaign_graph, campaign_settings_hash, resolved_input_paths,
    validate_input_mappings, workflow_hash, workflow_snapshot, workflow_version,
)

LOGGER = logging.getLogger(__name__)


class CampaignCancelled(RuntimeError):
    pass


@dataclass(slots=True)
class CampaignExecutionSummary:
    total_runs: int
    executed_runs: int
    reused_runs: int
    passed_runs: int
    failed_runs: int
    warning_runs: int
    error_runs: int
    cancelled_runs: int
    duration_seconds: float


class CampaignRunner:
    """Execute a campaign sequentially or with conservative bounded parallelism."""

    def __init__(self, campaign: TestCampaign, *, project_directory: str | Path | None = None) -> None:
        self.campaign = campaign
        self.project_directory = Path(project_directory).resolve() if project_directory else None
        self._cancel = Event()
        self._lock = Lock()
        self._detail_slots_used = sum(bool(run.detail_results) for run in campaign.runs)

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def _workflow_document(self) -> dict[str, Any]:
        # An external workflow path remains authoritative so edits to that file
        # invalidate prior campaign results.  A snapshot is retained alongside
        # the path for reporting and auditability.
        if self.campaign.workflow_path:
            path = Path(self.campaign.workflow_path).expanduser()
            if self.project_directory and not path.is_absolute():
                path = self.project_directory / path
            document = load_project(path)
            self.campaign.workflow_document = workflow_snapshot(document)
            return document
        if self.campaign.workflow_document:
            return deepcopy(self.campaign.workflow_document)
        raise ValueError("Campaign has no associated workflow.")

    def _resolved_discovery_campaign(self) -> TestCampaign:
        """Return an isolated campaign copy with project-relative inputs resolved.

        ``.sdojo`` projects deliberately store portable relative paths.  The Qt
        layer resolves those paths when a project is opened, but the campaign
        engine is also a public, UI-independent API used by tests, plugins and
        command-line automation.  Resolving here makes those callers behave
        identically without mutating the persisted campaign document.
        """

        runtime = deepcopy(self.campaign)
        if not self.project_directory:
            return runtime

        def resolve(raw: str) -> str:
            if not raw:
                return raw
            path = Path(raw).expanduser()
            return str((self.project_directory / path).resolve()) if not path.is_absolute() else str(path.resolve())

        runtime.input_folder = resolve(runtime.input_folder)
        runtime.explicit_files = [resolve(value) for value in runtime.explicit_files]
        return runtime

    @staticmethod
    def _invalidate_run(run: CampaignRun, *, errors: list[str] | None = None) -> None:
        run.status = RunStatus.ERROR if errors else RunStatus.PENDING
        run.metrics.clear(); run.metric_units.clear(); run.requirement_results.clear(); run.detail_results.clear()
        run.errors = list(errors or []); run.completed_utc = ""; run.workflow_hash = ""; run.workflow_version = ""; run.settings_hash = ""
        run.reused = False

    def _refresh_mapped_input_provenance(
        self,
        document: dict[str, Any],
        runs: list[CampaignRun],
        *,
        calculate_checksums: bool,
    ) -> None:
        checksum_cache: dict[str, str] = {}
        for run in runs:
            if self.cancelled:
                raise DiscoveryCancelled("Campaign preparation was cancelled.")
            old_checksums = dict(run.mapped_input_checksums)
            checksums: dict[str, str] = {}
            metadata: dict[str, dict[str, Any]] = {}
            mapping_errors: list[str] = []
            try:
                paths = resolved_input_paths(
                    document, self.campaign, run, project_directory=self.project_directory,
                )
                source_path = Path(run.source_path).resolve()
                for block_id, path in paths.items():
                    if not path.exists():
                        raise ValueError(f"Import Data block '{block_id}' maps to missing file '{path}'")
                    if not path.is_file():
                        raise ValueError(f"Import Data block '{block_id}' maps to non-file path '{path}'")
                    stat = path.stat()
                    rendered = str(path)
                    if calculate_checksums:
                        if path == source_path and run.input_checksum:
                            checksum = run.input_checksum
                        else:
                            checksum = checksum_cache.get(rendered)
                            if checksum is None:
                                checksum = file_checksum(path, is_cancelled=self.cancelled)
                                checksum_cache[rendered] = checksum
                        checksums[block_id] = checksum
                    metadata[block_id] = {
                        "path": rendered,
                        "size_bytes": stat.st_size,
                        "modified_utc": pd.Timestamp(stat.st_mtime, unit="s", tz="UTC").isoformat(),
                    }
            except (BlockError, OSError, ValueError) as exc:
                mapping_errors.append(
                    f"{run.file_name}: input mapping could not be prepared: {exc}. "
                    "Correct the mapped path or metadata extraction rule and retry the run."
                )

            changed = bool((run.is_complete or run.metrics) and old_checksums != checksums)
            if changed or mapping_errors:
                self._invalidate_run(run, errors=mapping_errors or None)
                if mapping_errors:
                    run.preparation_errors = list(dict.fromkeys([*run.preparation_errors, *mapping_errors]))
            run.mapped_input_checksums = checksums
            run.mapped_input_metadata = metadata

    def prepare(
        self,
        *,
        progress: Callable[[str, int, int], None] | None = None,
        calculate_checksums: bool = True,
        document: dict[str, Any] | None = None,
    ) -> list[CampaignRun]:
        errors = self.campaign.validate()
        if errors:
            raise ValueError("Campaign configuration is invalid: " + "; ".join(errors))
        document = deepcopy(document) if document is not None else self._workflow_document()
        mapping_errors = validate_input_mappings(document, self.campaign.input_mappings)
        if mapping_errors:
            raise ValueError("Campaign input mapping is invalid: " + "; ".join(mapping_errors))

        runtime = self._resolved_discovery_campaign()
        paths = discover_files(runtime, is_cancelled=self.cancelled, progress=progress)
        runs = reconcile_runs(
            runtime, paths, calculate_checksums=calculate_checksums,
            is_cancelled=self.cancelled, progress=progress,
        )
        self.campaign.runs = runs
        self._refresh_mapped_input_provenance(document, runs, calculate_checksums=calculate_checksums)
        # Reconciliation may invalidate and remove retained details for changed
        # inputs. Recount after preparation so the storage budget is accurate.
        self._detail_slots_used = sum(bool(run.detail_results) for run in runs)
        self.campaign.touch()
        return runs

    @staticmethod
    def _downsample_signal(signal: SignalData, maximum_points: int) -> SignalData:
        if signal.samples <= maximum_points:
            return signal
        indices = np.linspace(0, signal.samples - 1, maximum_points, dtype=int)
        return signal.with_values(signal.values[indices], time=signal.time[indices], sample_rate=None, attributes={"campaign_display_decimated": True})

    def _reserve_detail_slot(self, *, had_details: bool) -> bool:
        limit = max(0, int(self.campaign.execution.detailed_result_limit))
        if limit == 0:
            return False
        with self._lock:
            if had_details:
                return True
            if self._detail_slots_used >= limit:
                return False
            self._detail_slots_used += 1
            return True

    def _capture_details(self, report: ExecutionReport) -> dict[str, Any]:
        maximum_points = max(100, int(self.campaign.execution.maximum_signal_points))
        records: dict[str, Any] = {}
        signal_count = 0
        for node_id, outputs in report.outputs.items():
            for port, value in enumerate(outputs):
                key = f"{node_id}:{port}"
                try:
                    if isinstance(value, SignalData):
                        if signal_count >= 12:
                            continue
                        records[key] = serialise_result(self._downsample_signal(value, maximum_points)); signal_count += 1
                    elif isinstance(value, SpectrumData):
                        if len(value.frequency) > maximum_points:
                            indices = np.linspace(0, len(value.frequency) - 1, maximum_points, dtype=int)
                            value = SpectrumData(value.frequency[indices], value.values[indices], value.name, value.unit, value.scale, dict(value.metadata))
                        records[key] = serialise_result(value)
                    elif isinstance(value, ScalarResult):
                        records[key] = serialise_result(value)
                    elif isinstance(value, TableResult) and len(value.frame) <= 1000 and len(value.frame.columns) <= 50:
                        records[key] = serialise_result(value)
                except (TypeError, ValueError, OSError) as exc:
                    LOGGER.debug("Could not retain campaign detail result %s: %s", key, exc)
        return records

    @staticmethod
    def _output(report: ExecutionReport, node_id: str, port: int) -> Any:
        values = report.outputs.get(node_id)
        if values is None or not 0 <= port < len(values):
            raise ValueError(f"Workflow output {node_id}:{port} is unavailable")
        return values[port]

    def _extract_metrics(self, report: ExecutionReport) -> tuple[dict[str, Any], dict[str, str], list[str], list[str]]:
        metrics: dict[str, Any] = {}
        units: dict[str, str] = {}
        warnings: list[str] = []
        errors: list[str] = []
        published: dict[str, ScalarResult] = {}
        duplicate_published: set[str] = set()
        for outputs in report.outputs.values():
            for value in outputs:
                if not isinstance(value, ScalarResult) or not value.metadata.get("published_metric"):
                    continue
                name = str(value.metadata.get("metric_name") or value.name).strip()
                if not name:
                    errors.append("A Publish Metric block produced an empty metric name.")
                    continue
                if name in published:
                    duplicate_published.add(name)
                else:
                    published[name] = value
        if duplicate_published:
            errors.append(
                "Duplicate Publish Metric names were produced: " + ", ".join(sorted(duplicate_published))
                + ". Give every published metric a unique name."
            )

        definitions = [metric for metric in self.campaign.metrics if metric.enabled]
        for definition in definitions:
            try:
                if definition.source_node_id:
                    value = self._output(report, definition.source_node_id, int(definition.source_port))
                elif definition.name in published:
                    value = published[definition.name]
                else:
                    raise ValueError("no source block is configured and no matching Publish Metric output was found")
                compact, inferred_unit, _description = aggregate_metric(
                    value, definition.aggregation, expression=definition.expression,
                )
                if isinstance(compact, np.generic):
                    compact = compact.item()
                if isinstance(compact, float) and not np.isfinite(compact):
                    raise ValueError("metric value is NaN or infinite")
                metrics[definition.name] = compact
                units[definition.name] = definition.unit or inferred_unit
            except Exception as exc:
                errors.append(
                    f"Metric '{definition.name}' was not produced: {exc}. "
                    "Check its source node, output port and aggregation."
                )
        for name, value in published.items():
            if name in metrics or name in duplicate_published:
                continue
            try:
                compact, inferred_unit, _ = aggregate_metric(value, "value")
                metrics[name] = compact
                units[name] = inferred_unit
            except ValueError as exc:
                warnings.append(f"Published metric '{name}' was rejected: {exc}.")
        return metrics, units, warnings, errors

    def _execute_run(
        self,
        run: CampaignRun,
        document: dict[str, Any],
        current_workflow_hash: str,
        current_workflow_version: str,
        current_settings_hash: str,
        *,
        run_progress: Callable[[CampaignRun, str, int, int], None] | None = None,
        force: bool = False,
    ) -> CampaignRun:
        if self.cancelled:
            run.status = RunStatus.CANCELLED
            return run
        reusable = (
            not force and self.campaign.execution.reuse_completed and run.status in TERMINAL_RUN_STATUSES
            and run.status != RunStatus.CANCELLED and run.workflow_hash == current_workflow_hash
            and run.workflow_version == current_workflow_version
            and run.settings_hash == current_settings_hash and bool(run.input_checksum)
            and bool(run.mapped_input_checksums) and run.signaldojo_version == VERSION
        )
        if reusable:
            run.reused = True
            return run
        run.reused = False
        had_details = bool(run.detail_results)
        run.started_utc = utc_now(); run.completed_utc = ""; run.status = RunStatus.RUNNING
        run.metrics.clear(); run.metric_units.clear(); run.requirement_results.clear(); run.errors.clear(); run.detail_results.clear()
        run.warnings = [warning for warning in run.warnings if warning.startswith("Metadata '")]
        started = perf_counter()
        try:
            if run.preparation_errors:
                raise ValueError("; ".join(run.preparation_errors))
            graph = build_campaign_graph(document, self.campaign, run, project_directory=self.project_directory)
            report = graph.execute(
                progress=(lambda node_id, index, total: run_progress(run, node_id, index, total)) if run_progress else None,
                is_cancelled=self.cancelled,
                use_cache=False,
            )
            metrics, units, metric_warnings, metric_errors = self._extract_metrics(report)
            run.metrics = metrics; run.metric_units = units
            run.warnings = list(dict.fromkeys([*run.warnings, *report.warnings, *metric_warnings]))
            run.errors.extend(metric_errors)
            run.requirement_results = evaluate_requirements(self.campaign.requirements, metrics, units)
            run.status = aggregate_run_status(run.requirement_results, has_errors=bool(metric_errors))
            if self.cancelled:
                run.status = RunStatus.CANCELLED
            elif self._reserve_detail_slot(had_details=had_details):
                run.detail_results = self._capture_details(report)
            else:
                run.warnings.append(
                    "Detailed signal results were not retained because the campaign detail-result limit was reached. "
                    "Metrics, requirements and provenance remain available."
                )
        except BlockError as exc:
            if self.cancelled or "cancelled" in str(exc).casefold():
                run.status = RunStatus.CANCELLED
                run.errors.append("Execution was cancelled.")
            else:
                run.status = RunStatus.ERROR
                run.errors.append(f"{run.file_name}: {exc}")
        except Exception as exc:
            LOGGER.exception("Campaign run failed: %s", run.file_name)
            run.status = RunStatus.ERROR
            run.errors.append(f"{run.file_name}: {exc}. Check the file format, import mapping and required columns.")
        finally:
            run.processing_seconds = perf_counter() - started
            run.completed_utc = utc_now()
            run.workflow_hash = current_workflow_hash
            run.workflow_version = current_workflow_version
            run.settings_hash = current_settings_hash
            run.signaldojo_version = VERSION
            # A mapped file replaced while it was being processed must never be
            # reported as an auditable deterministic result. Preparation hashes
            # catch changes between sessions; these stat snapshots catch common
            # mid-run replacements without hashing every large file twice.
            try:
                for block_id, before in run.mapped_input_metadata.items():
                    path = Path(str(before.get("path", "")))
                    stat = path.stat()
                    modified = pd.Timestamp(stat.st_mtime, unit="s", tz="UTC").isoformat()
                    if int(before.get("size_bytes", stat.st_size)) != stat.st_size or str(before.get("modified_utc", "")) != modified:
                        run.status = RunStatus.ERROR
                        run.errors.append(
                            f"{run.file_name}: mapped input '{block_id}' changed while the run was executing. "
                            "Restore stable input files and retry this run."
                        )
                        run.metrics.clear(); run.metric_units.clear(); run.requirement_results.clear(); run.detail_results.clear()
                        break
            except OSError as exc:
                run.status = RunStatus.ERROR
                run.errors.append(f"{run.file_name}: a mapped input could not be rechecked after execution: {exc}")
        return run

    def execute(
        self,
        *,
        overall_progress: Callable[[CampaignRun, int, int], None] | None = None,
        run_progress: Callable[[CampaignRun, str, int, int], None] | None = None,
        force_run_ids: Iterable[str] | None = None,
        prepare: bool = True,
    ) -> CampaignExecutionSummary:
        started = perf_counter()
        document = self._workflow_document()
        if prepare:
            self.prepare(document=document)
        current_workflow_hash = workflow_hash(document)
        current_workflow_version = workflow_version(document)
        current_settings_hash = campaign_settings_hash(self.campaign)
        forced = set(force_run_ids or ())
        runs = list(self.campaign.runs)
        total = len(runs)
        executed_count = 0
        reused_count = 0

        def complete(run: CampaignRun, index: int) -> None:
            nonlocal executed_count, reused_count
            if run.reused:
                reused_count += 1
            elif not (run.status == RunStatus.CANCELLED and not run.started_utc):
                # Runs cancelled before a worker began are accounted for as
                # cancelled, not as executed work.
                executed_count += 1
            if overall_progress:
                overall_progress(run, index, total)

        mode = self.campaign.execution.mode
        if mode == "parallel" and self.campaign.execution.max_workers > 1 and total > 1:
            workers = min(max(1, int(self.campaign.execution.max_workers)), 8, total)
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="SignalDojoCampaign") as pool:
                futures: dict[Future[CampaignRun], CampaignRun] = {
                    pool.submit(self._execute_run, run, document, current_workflow_hash, current_workflow_version, current_settings_hash,
                                run_progress=run_progress, force=run.run_id in forced): run
                    for run in runs
                }
                completed = 0
                for future in as_completed(futures):
                    completed += 1
                    run = futures[future]
                    try:
                        run = future.result()
                    except CancelledError:
                        run.status = RunStatus.CANCELLED
                        run.errors.append("Execution was cancelled before this run started.")
                        run.completed_utc = utc_now()
                        run.signaldojo_version = VERSION
                    complete(run, completed)
                    if self.cancelled:
                        for pending in futures:
                            pending.cancel()
        else:
            for index, run in enumerate(runs, 1):
                if self.cancelled:
                    if run.status == RunStatus.PENDING:
                        run.status = RunStatus.CANCELLED
                    complete(run, index)
                    continue
                self._execute_run(
                    run, document, current_workflow_hash, current_workflow_version, current_settings_hash,
                    run_progress=run_progress, force=run.run_id in forced,
                )
                complete(run, index)
                if self.campaign.execution.stop_on_error and run.status == RunStatus.ERROR:
                    for remaining in runs[index:]:
                        if remaining.status == RunStatus.RUNNING:
                            remaining.status = RunStatus.PENDING
                    break
        self.campaign.last_execution_seconds = perf_counter() - started
        self.campaign.last_workflow_hash = current_workflow_hash
        self.campaign.touch()
        counts = {status: sum(run.status == status for run in runs) for status in RunStatus}
        return CampaignExecutionSummary(
            total_runs=total, executed_runs=executed_count, reused_runs=reused_count,
            passed_runs=counts[RunStatus.PASSED], failed_runs=counts[RunStatus.FAILED],
            warning_runs=counts[RunStatus.WARNING], error_runs=counts[RunStatus.ERROR],
            cancelled_runs=counts[RunStatus.CANCELLED], duration_seconds=self.campaign.last_execution_seconds,
        )

    def retry_failed(
        self,
        *,
        overall_progress: Callable[[CampaignRun, int, int], None] | None = None,
        run_progress: Callable[[CampaignRun, str, int, int], None] | None = None,
    ) -> CampaignExecutionSummary:
        failed_ids = [run.run_id for run in self.campaign.runs if run.status in {RunStatus.ERROR, RunStatus.FAILED, RunStatus.CANCELLED}]
        return self.execute(overall_progress=overall_progress, run_progress=run_progress, force_run_ids=failed_ids, prepare=True)
