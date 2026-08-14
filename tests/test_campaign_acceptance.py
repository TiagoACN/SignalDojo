# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from app.campaign.comparison import compare_runs
from app.campaign.execution import CampaignRunner
from app.campaign.models import campaign_from_dict, campaign_to_dict, RunStatus
from app.exporters.campaign_report import export_campaign_report_bundle
from app.project.io import load_project, save_project
from tests.campaign_helpers import campaign, create_motor_files, create_recording


def test_motor_current_campaign_acceptance_workflow(tmp_path: Path) -> None:
    inputs = tmp_path / "recordings"
    files = create_motor_files(inputs)
    item = campaign(inputs)

    first = CampaignRunner(item, project_directory=tmp_path).execute()
    assert first.total_runs == 8 and first.error_runs == 1
    assert next(run for run in item.runs if run.file_name == files["excessive"].name).status == RunStatus.FAILED
    assert next(run for run in item.runs if run.file_name == files["frequency"].name).status == RunStatus.FAILED
    assert next(run for run in item.runs if run.file_name == files["noisy"].name).status == RunStatus.WARNING

    normals = [run for run in item.runs if "normal" in run.file_name]
    item.reference_run_id = normals[0].run_id
    comparison = compare_runs(item, [run.run_id for run in normals[:3]], reference_run_id=item.reference_run_id)
    assert comparison.signals and len(comparison.metrics) == 3

    reports = export_campaign_report_bundle(item, tmp_path / "reports")
    assert all(path.exists() and path.stat().st_size for path in reports.values())

    project_path = tmp_path / "motor_campaign.sdojo"
    payload = deepcopy(item.workflow_document)
    payload.pop("format", None); payload.pop("project_version", None)
    payload["campaign"] = campaign_to_dict(item)
    save_project(project_path, payload)
    loaded_document = load_project(project_path)
    reopened = campaign_from_dict(loaded_document["campaign"])
    assert reopened is not None and len(reopened.runs) == 8
    reused = CampaignRunner(reopened, project_directory=tmp_path).execute()
    assert reused.reused_runs == 8

    create_recording(files["normal_1"], base=1.7, seed=300)
    one_changed = CampaignRunner(reopened, project_directory=tmp_path).execute()
    assert one_changed.executed_runs == 1 and one_changed.reused_runs == 7

    reopened.workflow_document["nodes"][1]["parameters"]["cutoff"] = 95.0
    workflow_changed = CampaignRunner(reopened, project_directory=tmp_path).execute()
    assert workflow_changed.executed_runs == 8 and workflow_changed.reused_runs == 0
