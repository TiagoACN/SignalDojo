# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

from pathlib import Path

from app.campaign.execution import CampaignRunner
from app.campaign.models import RunStatus, campaign_from_dict
from app.project.io import load_project


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "motor_current_campaign" / "motor_current_campaign.sdojo"


def test_bundled_motor_campaign_opens_and_reuses_portable_results() -> None:
    document = load_project(EXAMPLE)
    item = campaign_from_dict(document.get("campaign"))
    assert item is not None
    assert len(item.runs) == 8

    summary = CampaignRunner(item, project_directory=EXAMPLE.parent).execute()

    assert summary.reused_runs == 8
    assert summary.executed_runs == 0
    assert sum(run.status == RunStatus.PASSED for run in item.runs) == 4
    assert sum(run.status == RunStatus.FAILED for run in item.runs) == 2
    assert sum(run.status == RunStatus.WARNING for run in item.runs) == 1
    assert sum(run.status == RunStatus.ERROR for run in item.runs) == 1
    assert item.reference_run_id and item.run_by_id(item.reference_run_id) is not None
