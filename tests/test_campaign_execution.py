# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest

from app.campaign.execution import CampaignRunner
from app.campaign.models import InputMapping, MetadataRule, RunStatus
from app.project.io import save_project
from tests.campaign_helpers import campaign, create_motor_files, create_recording, workflow_document


def test_batch_execution_isolates_failure_and_classifies_runs(tmp_path: Path) -> None:
    files = create_motor_files(tmp_path)
    item = campaign(tmp_path)
    summary = CampaignRunner(item).execute()
    assert summary.total_runs == 8
    by_name = {run.file_name: run for run in item.runs}
    assert by_name[files["excessive"].name].status == RunStatus.FAILED
    assert by_name[files["frequency"].name].status == RunStatus.FAILED
    assert by_name[files["noisy"].name].status == RunStatus.WARNING
    assert by_name[files["malformed"].name].status == RunStatus.ERROR
    assert sum(run.status == RunStatus.PASSED for run in item.runs) == 4
    assert all(run.workflow_hash and run.input_checksum and run.signaldojo_version for run in item.runs)


def test_identical_second_execution_reuses_all_completed_runs(tmp_path: Path) -> None:
    create_motor_files(tmp_path)
    item = campaign(tmp_path)
    first = CampaignRunner(item).execute()
    second = CampaignRunner(item).execute()
    assert first.executed_runs == 8
    assert second.reused_runs == 8
    assert second.executed_runs == 0
    assert all(run.reused for run in item.runs)


def test_changing_one_input_invalidates_only_that_run(tmp_path: Path) -> None:
    files = create_motor_files(tmp_path)
    item = campaign(tmp_path)
    CampaignRunner(item).execute()
    create_recording(files["normal_1"], base=1.6, seed=99)
    second = CampaignRunner(item).execute()
    assert second.executed_runs == 1
    assert second.reused_runs == 7
    changed = next(run for run in item.runs if run.file_name == files["normal_1"].name)
    assert not changed.reused


def test_workflow_change_invalidates_every_run(tmp_path: Path) -> None:
    create_motor_files(tmp_path)
    item = campaign(tmp_path)
    CampaignRunner(item).execute()
    item.workflow_document = workflow_document(cutoff=100.0)
    summary = CampaignRunner(item).execute()
    assert summary.executed_runs == 8
    assert summary.reused_runs == 0


def test_retry_failed_run_after_file_is_corrected(tmp_path: Path) -> None:
    files = create_motor_files(tmp_path)
    item = campaign(tmp_path)
    CampaignRunner(item).execute()
    malformed = next(run for run in item.runs if run.file_name == files["malformed"].name)
    assert malformed.status == RunStatus.ERROR
    create_recording(files["malformed"], seed=100)
    summary = CampaignRunner(item).retry_failed()
    assert summary.executed_runs >= 3  # Requirement failures and the corrected error are retried.
    malformed = next(run for run in item.runs if run.file_name == files["malformed"].name)
    assert malformed.status == RunStatus.PASSED


def test_required_metadata_failure_is_isolated_to_one_run(tmp_path: Path) -> None:
    create_recording(tmp_path / "TEST-A001_valid.csv")
    create_recording(tmp_path / "bad_name.csv")
    item = campaign(tmp_path)
    item.metadata_rules = [MetadataRule("test_id", "filename_regex", r"^(TEST-[A-Z]\d+)", required=True)]
    summary = CampaignRunner(item).execute()
    assert summary.total_runs == 2
    bad = next(run for run in item.runs if run.file_name == "bad_name.csv")
    valid = next(run for run in item.runs if run.file_name == "TEST-A001_valid.csv")
    assert bad.status == RunStatus.ERROR and bad.preparation_errors
    assert valid.status == RunStatus.PASSED


def test_cancelled_prepared_campaign_marks_pending_runs_cancelled(tmp_path: Path) -> None:
    create_motor_files(tmp_path)
    item = campaign(tmp_path)
    runner = CampaignRunner(item)
    runner.prepare()
    runner.cancel()
    summary = runner.execute(prepare=False)
    assert summary.cancelled_runs == 8
    assert all(run.status == RunStatus.CANCELLED for run in item.runs)


def test_parallel_mode_is_deterministic(tmp_path: Path) -> None:
    create_motor_files(tmp_path)
    sequential = campaign(tmp_path)
    CampaignRunner(sequential).execute()
    expected = {run.file_name: (run.status, deepcopy(run.metrics)) for run in sequential.runs}
    parallel = campaign(tmp_path)
    parallel.execution.mode = "parallel"
    parallel.execution.max_workers = 3
    CampaignRunner(parallel).execute()
    actual = {run.file_name: (run.status, run.metrics) for run in parallel.runs}
    assert actual == expected


def test_missing_configured_metric_is_an_error_not_a_silent_pass(tmp_path: Path) -> None:
    create_recording(tmp_path / "TEST-A001.csv")
    item = campaign(tmp_path)
    item.metrics[0].source_node_id = "missing-node"
    item.requirements = []
    CampaignRunner(item).execute()
    run = item.runs[0]
    assert run.status == RunStatus.ERROR
    assert any("Metric 'rms_current' was not produced" in error for error in run.errors)


def test_prepare_rejects_unmapped_empty_import_block(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"; create_motor_files(inputs)
    item = campaign(inputs)
    item.workflow_document["nodes"].append({
        "id": "second_import", "type": "import_data", "label": "Required auxiliary input",
        "position": [0, 400], "parameters": {"file_path": "", "time_column": "time", "signal_columns": "current"},
    })
    with pytest.raises(ValueError, match="second_import"):
        CampaignRunner(item, project_directory=tmp_path).prepare()


def test_runner_resolves_project_relative_campaign_inputs(tmp_path: Path) -> None:
    project_dir = tmp_path / "project"
    inputs = project_dir / "recordings"
    inputs.mkdir(parents=True)
    create_recording(inputs / "normal.csv", amplitude=1.0, frequency=10.0)
    item = campaign(inputs)
    item.input_folder = "recordings"
    runner = CampaignRunner(item, project_directory=project_dir)

    runs = runner.prepare()

    assert len(runs) == 1
    assert Path(runs[0].source_path) == (inputs / "normal.csv").resolve()
    # Persisted configuration remains portable instead of being rewritten to
    # an absolute machine-specific path by the execution engine.
    assert item.input_folder == "recordings"


def test_sequential_cancellation_after_first_run_preserves_completed_work(tmp_path: Path) -> None:
    create_motor_files(tmp_path)
    item = campaign(tmp_path)
    runner = CampaignRunner(item)

    def progress(_run, index: int, _total: int) -> None:
        if index == 1:
            runner.cancel()

    summary = runner.execute(overall_progress=progress)

    assert summary.executed_runs == 1
    assert summary.cancelled_runs == 7
    assert sum(run.status not in {RunStatus.CANCELLED, RunStatus.PENDING} for run in item.runs) == 1


def test_parallel_cancellation_does_not_escape_cancelled_future_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    create_motor_files(tmp_path)
    item = campaign(tmp_path)
    item.execution.mode = "parallel"
    item.execution.max_workers = 2
    runner = CampaignRunner(item)
    original = runner._execute_run  # noqa: SLF001 - cancellation integration test

    def execute_and_cancel(run, *args, **kwargs):
        result = original(run, *args, **kwargs)
        runner.cancel()
        return result

    monkeypatch.setattr(runner, "_execute_run", execute_and_cancel)
    summary = runner.execute()

    assert summary.total_runs == 8
    assert summary.cancelled_runs >= 1
    assert all(run.status != RunStatus.RUNNING for run in item.runs)


def test_fixed_mapped_input_checksum_invalidates_every_dependent_run(tmp_path: Path) -> None:
    inputs = tmp_path / "recordings"
    create_motor_files(inputs)
    auxiliary = tmp_path / "ambient.csv"
    create_recording(auxiliary, base=0.2, seed=901)
    document = workflow_document()
    document["nodes"].append({
        "id": "auxiliary", "type": "import_data", "label": "Ambient channel", "position": [0, 320],
        "parameters": {
            "file_path": "", "time_column": "time", "signal_columns": "current", "sample_rate": 1000.0,
            "signal_names": "Ambient", "units": "A", "missing_policy": "preserve",
        },
    })
    item = campaign(inputs, document=document)
    item.input_mappings.append(InputMapping("auxiliary", "fixed_file", fixed_path=str(auxiliary)))

    first = CampaignRunner(item, project_directory=tmp_path).execute()
    assert first.executed_runs == 8
    assert all(set(run.mapped_input_checksums) == {"import", "auxiliary"} for run in item.runs)
    assert all(run.workflow_version == "1.2.6" for run in item.runs)

    unchanged = CampaignRunner(item, project_directory=tmp_path).execute()
    assert unchanged.reused_runs == 8

    create_recording(auxiliary, base=0.4, seed=902)
    changed = CampaignRunner(item, project_directory=tmp_path).execute()
    assert changed.executed_runs == 8 and changed.reused_runs == 0


def test_external_workflow_is_authoritative_and_snapshot_is_refreshed(tmp_path: Path) -> None:
    inputs = tmp_path / "recordings"
    create_motor_files(inputs)
    external = tmp_path / "external.sdojo"
    document = workflow_document(cutoff=120.0)
    payload = dict(document); payload.pop("format", None); payload.pop("project_version", None)
    save_project(external, payload)

    item = campaign(inputs)
    item.workflow_path = str(external)
    item.workflow_document = {"application_version": "stale", "nodes": [], "connections": []}
    first = CampaignRunner(item, project_directory=tmp_path).execute()
    assert first.executed_runs == 8
    assert item.workflow_document["application_version"] == "1.2.6"
    assert all(run.workflow_version == "1.2.6" for run in item.runs)

    updated = workflow_document(cutoff=90.0)
    payload = dict(updated); payload.pop("format", None); payload.pop("project_version", None)
    save_project(external, payload)
    second = CampaignRunner(item, project_directory=tmp_path).execute()
    assert second.executed_runs == 8 and second.reused_runs == 0


def test_signaldojo_version_change_invalidates_only_stale_run(tmp_path: Path) -> None:
    inputs = tmp_path / "recordings"
    create_motor_files(inputs)
    item = campaign(inputs)
    CampaignRunner(item, project_directory=tmp_path).execute()
    item.runs[0].signaldojo_version = "1.1.0"

    summary = CampaignRunner(item, project_directory=tmp_path).execute()
    assert summary.executed_runs == 1 and summary.reused_runs == 7
