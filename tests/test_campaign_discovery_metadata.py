# SPDX-FileCopyrightText: 2026 Tiago Alvarez Calderon Newton and SignalDojo Contributors
# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from app.campaign.discovery import discover_files, extract_metadata, reconcile_runs
from app.campaign.models import MetadataRule, RunStatus
from tests.campaign_helpers import campaign, create_recording


def test_file_discovery_recursive_filters_and_stable_ids(tmp_path: Path) -> None:
    root = tmp_path / "inputs"; nested = root / "nested"; nested.mkdir(parents=True)
    create_recording(root / "A.csv"); create_recording(nested / "B.csv"); (root / "ignored.bin").write_bytes(b"x")
    item = campaign(root); item.metadata_rules = []; item.recursive = False
    assert [path.name for path in discover_files(item)] == ["A.csv"]
    item.recursive = True
    paths = discover_files(item)
    runs = reconcile_runs(item, paths)
    first_ids = [run.run_id for run in runs]
    assert [path.name for path in paths] == ["A.csv", "B.csv"]
    assert [run.run_id for run in reconcile_runs(item, paths)] == first_ids


def test_metadata_rules_filename_parent_sidecar_column_and_manual(tmp_path: Path) -> None:
    root = tmp_path / "Rig-7"; root.mkdir(); path = root / "UNIT-123_test.csv"
    pd.DataFrame({"operator": ["Tiago"], "value": [1.0]}).to_csv(path, index=False)
    path.with_suffix(path.suffix + ".json").write_text(json.dumps({"firmware": "2.4.1"}), encoding="utf-8")
    rules = [
        MetadataRule("serial", "filename_regex", r"UNIT-(\d+)", "1", required=True),
        MetadataRule("rig", "parent_folder", group="1"),
        MetadataRule("firmware", "sidecar_json", key="firmware"),
        MetadataRule("operator", "file_column", key="operator"),
        MetadataRule("condition", "manual", value="ambient"),
    ]
    metadata, warnings = extract_metadata(path, rules)
    assert warnings == []
    assert metadata == {"serial": "123", "rig": "Rig-7", "firmware": "2.4.1", "operator": "Tiago", "condition": "ambient"}


def test_required_metadata_failure_is_actionable(tmp_path: Path) -> None:
    path = tmp_path / "input.csv"; create_recording(path)
    with pytest.raises(ValueError, match="Required metadata 'serial'"):
        extract_metadata(path, [MetadataRule("serial", "filename_regex", r"UNIT-(\d+)", required=True)])


def test_changed_input_invalidates_only_matching_run(tmp_path: Path) -> None:
    root = tmp_path / "inputs"; root.mkdir(); first = root / "TEST-A001.csv"; second = root / "TEST-A002.csv"; create_recording(first); create_recording(second, seed=2)
    item = campaign(root); runs = reconcile_runs(item, discover_files(item));
    for run in runs: run.status = RunStatus.PASSED; run.metrics = {"x": 1}; run.workflow_hash = "workflow"; run.settings_hash = "settings"
    first.write_text(first.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    updated = reconcile_runs(item, discover_files(item))
    states = {run.file_name: run.status for run in updated}
    assert states[first.name] == RunStatus.PENDING
    assert states[second.name] == RunStatus.PASSED


def test_metadata_file_properties_and_unsafe_regex(tmp_path: Path) -> None:
    from app.campaign.discovery import extract_metadata
    from app.campaign.models import MetadataRule

    path = tmp_path / "UNIT-17.csv"
    path.write_text("time,current\n0,1\n", encoding="utf-8")
    metadata, warnings = extract_metadata(path, [
        MetadataRule("file_stem", "file_property", key="stem", required=True),
        MetadataRule("bytes", "file_property", key="size_bytes", required=True),
    ])
    assert warnings == []
    assert metadata["file_stem"] == "UNIT-17"
    assert metadata["bytes"] == path.stat().st_size

    with pytest.raises(ValueError, match="nested repetition"):
        extract_metadata(path, [MetadataRule("bad", "filename_regex", pattern=r"(.*)+", required=True)])
