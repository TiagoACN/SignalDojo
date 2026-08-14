# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from pathlib import Path

from app.campaign.models import (
    CampaignRun, RequirementResult, RequirementStatus, RunStatus,
    campaign_from_dict, campaign_to_dict,
)
from app.project.io import PROJECT_VERSION, load_project, migrate_project, save_project
from tests.campaign_helpers import campaign, workflow_document


def test_campaign_model_serialisation_round_trip(tmp_path: Path) -> None:
    item = campaign(tmp_path)
    item.runs = [CampaignRun(
        "run-1", str(tmp_path / "one.csv"), "one.csv", input_checksum="abc", status=RunStatus.FAILED,
        metrics={"rms_current": 2.3}, metric_units={"rms_current": "A"},
        workflow_version="1.2.6", mapped_input_checksums={"import": "abc"},
        mapped_input_metadata={"import": {"path": "one.csv", "size_bytes": 12}},
        requirement_results=[RequirementResult("RMS", "rms_current", 2.3, "≤ 2", -0.3, "A", RequirementStatus.FAIL, "too high")],
    )]
    restored = campaign_from_dict(json.loads(json.dumps(campaign_to_dict(item))))
    assert restored is not None
    assert restored.name == item.name
    assert restored.runs[0].status == RunStatus.FAILED
    assert restored.runs[0].requirement_results[0].status == RequirementStatus.FAIL
    assert restored.runs[0].workflow_version == "1.2.6"
    assert restored.runs[0].mapped_input_checksums == {"import": "abc"}
    assert restored.metrics[0].source_node_id == "publish_rms"


def test_project_schema_migrates_1_1_without_campaign() -> None:
    legacy = workflow_document(); legacy["project_version"] = 3; legacy.pop("campaign", None)
    migrated = migrate_project(legacy)
    assert migrated["project_version"] == PROJECT_VERSION == 4
    assert migrated["campaign"] is None


def test_project_save_and_open_persists_campaign(tmp_path: Path) -> None:
    item = campaign(tmp_path)
    payload = workflow_document(); payload.pop("format"); payload.pop("project_version")
    payload["campaign"] = campaign_to_dict(item)
    destination = tmp_path / "campaign.sdojo"
    save_project(destination, payload)
    loaded = load_project(destination)
    restored = campaign_from_dict(loaded["campaign"])
    assert restored is not None
    assert restored.name == item.name
    assert restored.workflow_document["nodes"][0]["type"] == "import_data"


def test_campaign_schema_zero_migrates_to_current_defaults() -> None:
    from app.campaign.models import CAMPAIGN_SCHEMA_VERSION, migrate_campaign_dict

    migrated = migrate_campaign_dict({
        "name": "Legacy campaign",
        "workflow_document": workflow_document(),
        "input_folder": "inputs",
        "file_extensions": [".csv"],
        "input_mappings": [{"block_id": "import", "source": "run_file"}],
        "metrics": [{"name": "rms_current", "source_node_id": "publish_rms", "aggregation": "value"}],
        "runs": [{"run_id": "r1", "source_path": "a.csv", "file_name": "a.csv"}],
    })
    assert migrated["schema_version"] == CAMPAIGN_SCHEMA_VERSION
    assert migrated["execution"]["reuse_completed"] is True
    assert migrated["report"]["include_sections"]
    assert migrated["runs"][0]["detail_results"] == {}
    assert migrated["runs"][0]["mapped_input_checksums"] == {}
    assert migrated["runs"][0]["workflow_version"] == ""


def test_project_validation_reports_damaged_campaign_configuration(tmp_path: Path) -> None:
    from app.project.io import validate_project_document

    item = campaign(tmp_path)
    item.metrics[0].name = ""
    payload = workflow_document()
    payload["project_version"] = PROJECT_VERSION
    payload["campaign"] = campaign_to_dict(item)

    errors = validate_project_document(payload)

    assert any(error.startswith("Campaign:") and "metric" in error.casefold() for error in errors)
